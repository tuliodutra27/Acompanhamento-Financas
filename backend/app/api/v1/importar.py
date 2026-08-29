"""Importação da nota a partir do HTML capturado no navegador do usuário.

**Por que este caminho existe.** O portal da SEFAZ recusa a consulta feita pelo servidor
(testado ao vivo, com `curl` e com Chromium headless), mas abre normalmente no navegador
do usuário. Então a extração automática não precisa de truque nenhum: quem lê a página é
o navegador que já tem acesso legítimo a ela. O parser é o mesmo do caminho automático
(`layout_padrao.parsear_pagina`) — nada é duplicado.

**Por que POST de formulário e não `fetch`.** A primeira versão usava `fetch` com corpo
`text/plain`, na expectativa de que uma "requisição simples" dispensasse CORS. Dispensa
apenas o *preflight*: a resposta ainda precisa de `Access-Control-Allow-Origin`, e sem
isso o `fetch` rejeita com `TypeError: Failed to fetch` — mesmo tendo a requisição
chegado e sido processada. O envio por `<form target="_blank">` é uma **navegação**, não
uma requisição de script: CORS não se aplica, o resultado aparece numa aba nova, e a API
não precisa liberar origens externas.
"""

from __future__ import annotations

import gzip
import logging
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import ParseFalhou
from app.adapters.layout_padrao import parsear_pagina
from app.core.auth import esta_autenticado, token_importacao_valido
from app.core.chave_nfce import (
    ChaveInvalida,
    candidatos_de_chave,
    extrair_chave_de_html,
    ler_chave,
)
from app.core.db import get_session
from app.models.enums import OrigemEntrada, StatusNota
from app.models.item_nota import ItemNota
from app.models.nota_fiscal import NotaFiscal
from app.services.ingestao import garantir_estabelecimento
from app.services.normalizacao import autovincular_itens

logger = logging.getLogger(__name__)

router = APIRouter(tags=["importar"])

TAMANHO_MAXIMO_HTML = 8 * 1024 * 1024

# O atalho é servido de dentro da página da SEFAZ, ou seja, de outra origem. O envio por
# formulário não precisa disto (navegação não passa por CORS), mas um atalho que use
# `fetch` precisa, ou a resposta é bloqueada e o usuário vê "Failed to fetch" mesmo com a
# importação tendo funcionado — foi o que aconteceu na prática.
#
# Liberar a origem é seguro **porque esta rota não aceita o cookie de sessão como
# credencial**: ela exige o token de importação na URL. Uma página de terceiros que
# tentasse chamá-la em nome do usuário autenticado não teria o token, e o cookie sozinho
# não abre a porta. É o inverso do risco clássico de `Access-Control-Allow-Origin: *`
# com `allow_credentials`.
CABECALHOS_CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
}


@router.options("/notas/importar-html")
async def importar_html_preflight() -> Response:
    """Responde ao preflight, caso o atalho envie um Content-Type não simples."""
    return Response(status_code=204, headers=CABECALHOS_CORS)


def _pagina(
    titulo: str, corpo: str, cor: str = "#0f766e", status: int = 200
) -> HTMLResponse:
    """Resposta legível no navegador — o atalho abre isto numa aba nova.

    O status acompanha o resultado mesmo quando a resposta é uma página: o navegador
    renderiza o corpo de um 4xx normalmente, e devolver 200 numa falha esconderia o erro
    de qualquer log ou verificação automática.
    """
    return HTMLResponse(
        status_code=status,
        content=f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <title>{titulo}</title><style>
        body{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:#0d0d0d;
        color:#fff;margin:0;padding:2rem 1.25rem;line-height:1.6}}
        .caixa{{max-width:640px;margin:0 auto;background:#1a1a19;border:1px solid #2c2c2a;
        border-radius:12px;padding:1.25rem}}
        h1{{font-size:1.15rem;margin:0 0 .75rem;color:{cor}}}
        code{{background:#232322;padding:.1rem .35rem;border-radius:4px;font-size:.85em}}
        ul{{padding-left:1.2rem}} a{{color:#3987e5}}
        </style></head><body><div class="caixa"><h1>{titulo}</h1>{corpo}</div></body></html>""",
    )


def _veio_de_formulario(requisicao: Request) -> bool:
    tipo = (requisicao.headers.get("content-type") or "").lower()
    return "application/x-www-form-urlencoded" in tipo


async def _ler_html_do_corpo(requisicao: Request, de_formulario: bool) -> str:
    """Aceita duas formas de envio porque servem a públicos diferentes.

    O formulário é o que o atalho usa no navegador (sem CORS); o `text/plain` é o que
    scripts e testes usam.
    """
    texto = (await requisicao.body()).decode("utf-8", errors="replace")
    if de_formulario:
        return parse_qs(texto, keep_blank_values=True).get("html", [""])[0]
    return texto


@router.post("/notas/importar-html")
async def importar_html(
    requisicao: Request,
    url: str | None = Query(None, description="URL da página de onde o HTML veio"),
    chave: str | None = Query(None, description="Chave de acesso, se já conhecida"),
    token: str | None = Query(None, description="Token do atalho de importação"),
    sessao: AsyncSession = Depends(get_session),
):
    """Recebe o HTML de uma nota aberta no navegador e importa os itens."""
    de_formulario = _veio_de_formulario(requisicao)

    def falhar(titulo: str, corpo_html: str, codigo: str, http: int = 400):
        if de_formulario:
            return _pagina(titulo, corpo_html, cor="#d03b3b", status=http)
        return JSONResponse(
            status_code=http,
            content={"erro": {"codigo": codigo, "mensagem": titulo, "detalhes": {}}},
            headers=CABECALHOS_CORS,
        )

    # Autorização antes de ler o corpo: são até 8 MB, e não há por que recebê-los de
    # quem não pode importar. Vale a sessão (uso a partir do próprio app) **ou** o token
    # do atalho (uso a partir do site da SEFAZ, onde o cookie de sessão não é enviado —
    # ver app/core/auth.py).
    if not (token_importacao_valido(token) or esta_autenticado(requisicao)):
        return falhar(
            "Atalho não autorizado",
            (
                "<p>Este atalho foi instalado antes do login existir, ou a chave "
                "secreta do servidor mudou.</p><p>Abra o app, entre com sua senha e "
                "instale o atalho de novo na tela <strong>Importar</strong>.</p>"
            ),
            "NAO_AUTENTICADO",
            http=401,
        )

    html = await _ler_html_do_corpo(requisicao, de_formulario)

    if not html.strip():
        return falhar(
            "Nada foi enviado",
            "<p>O atalho não conseguiu ler o conteúdo da página.</p>",
            "HTML_VAZIO",
        )
    if len(html) > TAMANHO_MAXIMO_HTML:
        return falhar(
            "Página muito grande",
            f"<p>{len(html) // 1024} KB — acima do limite.</p>",
            "HTML_GRANDE",
        )

    # A chave pode vir do parâmetro, da URL de origem, ou da própria página. Nesta
    # última é essencial validar candidato por candidato: a página está cheia de outros
    # números (códigos de produto, IDs de componente), e só o dígito verificador
    # distingue a chave de um número do tamanho certo.
    chave_encontrada = None
    for candidato in (chave, url, html):
        if not candidato:
            continue
        try:
            chave_encontrada = extrair_chave_de_html(candidato)
            break
        except ChaveInvalida:
            continue

    if not chave_encontrada:
        candidatos = candidatos_de_chave(html)
        logger.warning(
            "importação sem chave válida: url=%s tamanho=%d candidatos=%d",
            url,
            len(html),
            len(candidatos),
        )
        return falhar(
            "Não encontrei a chave de acesso nesta página",
            (
                "<p>A página foi recebida, mas nenhuma sequência de 44 dígitos com "
                "dígito verificador válido apareceu nela.</p><ul>"
                f"<li>tamanho recebido: <code>{len(html) // 1024} KB</code></li>"
                f"<li>candidatos de 44 dígitos encontrados: <code>{len(candidatos)}</code></li>"
                f"<li>tem a tabela de itens: <code>"
                f"{'sim' if 'tabResult' in html else 'não'}</code></li>"
                "</ul><p>Se a página mostra a chave de acesso, mande esses números "
                "para quem mantém o app. Alternativa: use a aba "
                "<strong>Consulta completa</strong> do portal, que exibe a chave.</p>"
            ),
            "CHAVE_INVALIDA",
        )

    dados = ler_chave(chave_encontrada)

    try:
        bruta = parsear_pagina(html)
    except ParseFalhou as exc:
        logger.warning(
            "importação sem itens legíveis: chave=%s motivo=%s",
            chave_encontrada,
            exc.motivo.value,
        )
        return falhar(
            "A página não tem a lista de itens",
            (
                f"<p>A chave <code>{chave_encontrada}</code> foi reconhecida, mas os "
                "produtos não foram encontrados no HTML.</p>"
                f"<ul><li>motivo: <code>{exc.motivo.value}</code></li>"
                f"<li>detalhe: <code>{exc.detalhe or '—'}</code></li></ul>"
                "<p>Abra a tela da nota que <strong>lista os produtos</strong> e use o "
                "atalho lá.</p>"
            ),
            "SEM_ITENS",
            http=409,
        )

    nota = await sessao.scalar(
        select(NotaFiscal).where(NotaFiscal.chave_acesso == chave_encontrada)
    )

    if nota is None:
        nota = NotaFiscal(
            chave_acesso=chave_encontrada,
            uf=dados.uf,
            cnpj_emitente=dados.cnpj_emitente,
            ano_mes_chave=dados.ano_mes,
            origem_entrada=OrigemEntrada.qrcode,
            url_consulta=url,
            status=StatusNota.pendente,
        )
        await garantir_estabelecimento(sessao, cnpj=dados.cnpj_emitente, uf=dados.uf)
        sessao.add(nota)
        await sessao.flush()
    elif nota.itens:
        # Não sobrescrever itens existentes: podem ter vínculos de produto feitos à
        # mão, o dado mais caro de reproduzir aqui.
        if de_formulario:
            return RedirectResponse(f"/notas/{nota.id}", status_code=303)
        return JSONResponse(
            content={
                "nota_id": nota.id,
                "importados": 0,
                "mensagem": f"Nota já importada com {len(nota.itens)} itens.",
            },
            headers=CABECALHOS_CORS,
        )

    nota.emitida_em = bruta.emitida_em or nota.emitida_em
    nota.valor_total = bruta.valor_total or nota.valor_total
    nota.payload_bruto = gzip.compress(html.encode("utf-8", errors="replace"))
    nota.adapter_usado = "navegador_do_usuario"
    nota.erro_detalhe = None

    if bruta.cnpj_emitente:
        nota.cnpj_emitente = bruta.cnpj_emitente
    await garantir_estabelecimento(
        sessao,
        cnpj=nota.cnpj_emitente,
        uf=bruta.uf or nota.uf,
        razao_social=bruta.nome_estabelecimento,
        municipio=bruta.municipio,
    )

    itens = [
        ItemNota(
            nota_id=nota.id,
            descricao_origem=item.descricao,
            gtin=item.gtin,
            quantidade=item.quantidade,
            unidade=item.unidade,
            valor_unitario=item.valor_unitario,
            valor_total=item.valor_total,
        )
        for item in bruta.itens
    ]
    sessao.add_all(itens)
    await sessao.flush()

    vinculados = await autovincular_itens(sessao, itens)
    nota.status = StatusNota.ok
    await sessao.commit()

    logger.info(
        "nota importada do navegador: chave=%s itens=%d vinculados=%d",
        chave_encontrada,
        len(itens),
        vinculados,
    )

    # Formulário → navega direto para a nota, que é o que o usuário quer ver.
    if de_formulario:
        return RedirectResponse(f"/notas/{nota.id}", status_code=303)

    return JSONResponse(
        status_code=201,
        content={
            "nota_id": nota.id,
            "importados": len(itens),
            "vinculados_automaticamente": vinculados,
            "pendentes_de_produto": len(itens) - vinculados,
            "estabelecimento": bruta.nome_estabelecimento,
            "mensagem": f"{len(itens)} itens importados.",
        },
        headers=CABECALHOS_CORS,
    )
