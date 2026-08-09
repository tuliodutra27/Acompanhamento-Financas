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

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import ParseFalhou
from app.adapters.layout_padrao import parsear_pagina
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


def _pagina(titulo: str, corpo: str, cor: str = "#0f766e") -> HTMLResponse:
    """Resposta legível no navegador — o atalho abre isto numa aba nova."""
    return HTMLResponse(
        f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <title>{titulo}</title><style>
        body{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:#0d0d0d;
        color:#fff;margin:0;padding:2rem 1.25rem;line-height:1.6}}
        .caixa{{max-width:640px;margin:0 auto;background:#1a1a19;border:1px solid #2c2c2a;
        border-radius:12px;padding:1.25rem}}
        h1{{font-size:1.15rem;margin:0 0 .75rem;color:{cor}}}
        code{{background:#232322;padding:.1rem .35rem;border-radius:4px;font-size:.85em}}
        ul{{padding-left:1.2rem}} a{{color:#3987e5}}
        </style></head><body><div class="caixa"><h1>{titulo}</h1>{corpo}</div></body></html>"""
    )


async def _extrair_html_do_corpo(requisicao: Request) -> tuple[str, bool]:
    """Devolve ``(html, veio_de_formulario)``.

    Aceita as duas formas porque servem a públicos diferentes: o formulário é o que o
    atalho usa no navegador (sem CORS), e o `text/plain` é o que scripts e testes usam.
    """
    tipo = (requisicao.headers.get("content-type") or "").lower()
    bruto = await requisicao.body()
    texto = bruto.decode("utf-8", errors="replace")

    if "application/x-www-form-urlencoded" in tipo:
        campos = parse_qs(texto, keep_blank_values=True)
        return (campos.get("html", [""])[0], True)

    return (texto, False)


@router.post("/notas/importar-html")
async def importar_html(
    requisicao: Request,
    url: str | None = Query(None, description="URL da página de onde o HTML veio"),
    chave: str | None = Query(None, description="Chave de acesso, se já conhecida"),
    sessao: AsyncSession = Depends(get_session),
):
    """Recebe o HTML de uma nota aberta no navegador e importa os itens."""
    html, de_formulario = await _extrair_html_do_corpo(requisicao)

    def falhar(titulo: str, corpo_html: str, codigo: str, http: int = 400):
        if de_formulario:
            return _pagina(titulo, corpo_html, cor="#d03b3b")
        return JSONResponse(
            status_code=http,
            content={"erro": {"codigo": codigo, "mensagem": titulo, "detalhes": {}}},
        )

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
        return {
            "nota_id": nota.id,
            "importados": 0,
            "mensagem": f"Nota já importada com {len(nota.itens)} itens.",
        }

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
    )
