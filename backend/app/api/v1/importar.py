"""Importação da nota a partir do HTML capturado no navegador do usuário.

**Por que este caminho existe.** O portal da SEFAZ-RJ recusa a consulta feita pelo
servidor — testado ao vivo, tanto com `curl` (que recebe o desafio JavaScript do F5)
quanto com Chromium headless (que, passando o desafio, recebe uma página de bloqueio).
No navegador do próprio usuário, porém, a nota abre normalmente.

Então a extração automática não precisa de nenhum truque: quem busca a página passa a
ser o navegador que já tem acesso legítimo a ela. Um atalho (bookmarklet) lê o HTML da
nota já aberta e o envia para cá; o parser é o mesmo usado no caminho automático
(`layout_padrao.parsear_pagina`), então nada é duplicado.

**Corpo `text/plain` de propósito.** Enviar o HTML como texto puro mantém a requisição
na categoria "simples" do CORS — sem preflight, sem precisar afrouxar a política de
origens da API para aceitar requisições vindas do domínio da SEFAZ. O atalho não lê a
resposta: ele redireciona o navegador para a lista de notas do app, onde o resultado
aparece.
"""

from __future__ import annotations

import gzip
import logging

from fastapi import APIRouter, Body, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import ParseFalhou
from app.adapters.layout_padrao import parsear_pagina
from app.core.chave_nfce import ChaveInvalida, extrair_chave_do_qrcode, ler_chave
from app.core.db import get_session
from app.core.erros import ChaveAcessoInvalida, OperacaoInvalida
from app.models.enums import OrigemEntrada, StatusNota
from app.models.item_nota import ItemNota
from app.models.nota_fiscal import NotaFiscal
from app.services.ingestao import garantir_estabelecimento
from app.services.normalizacao import autovincular_itens

logger = logging.getLogger(__name__)

router = APIRouter(tags=["importar"])

TAMANHO_MAXIMO_HTML = 4 * 1024 * 1024  # 4 MB; a página de uma nota tem ~50-200 KB


@router.post("/notas/importar-html")
async def importar_html(
    resposta: Response,
    html: str = Body(..., media_type="text/plain"),
    url: str | None = Query(
        None, description="URL da página de onde o HTML foi capturado"
    ),
    chave: str | None = Query(None, description="Chave de acesso, se já conhecida"),
    sessao: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """Recebe o HTML de uma nota aberta no navegador e importa os itens.

    A chave de acesso é procurada, em ordem: no parâmetro `chave`, na URL de origem
    (o `?p=` do QR Code a carrega), e por último em qualquer sequência de 44 dígitos
    dentro do próprio HTML — a página da nota sempre mostra a chave.
    """
    if len(html) > TAMANHO_MAXIMO_HTML:
        raise OperacaoInvalida("HTML muito grande para ser uma nota fiscal.")

    chave_encontrada = None
    for candidato in (chave, url, html):
        if not candidato:
            continue
        try:
            chave_encontrada = extrair_chave_do_qrcode(candidato)
            break
        except ChaveInvalida:
            continue

    if not chave_encontrada:
        raise ChaveAcessoInvalida(
            "Não encontrei uma chave de acesso válida nesta página. "
            "Confirme que a nota está aberta na tela."
        )

    dados = ler_chave(chave_encontrada)

    try:
        bruta = parsear_pagina(html)
    except ParseFalhou as exc:
        raise OperacaoInvalida(
            "A página enviada não tem a tabela de itens da nota. Abra a nota completa "
            "(a tela que lista os produtos) antes de usar o atalho.",
            {"motivo": exc.motivo.value},
        ) from exc

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
        await garantir_estabelecimento(
            sessao, cnpj=dados.cnpj_emitente, uf=dados.uf
        )
        sessao.add(nota)
        await sessao.flush()
    elif nota.itens:
        # Não sobrescrever itens já existentes: podem ter vínculos de produto feitos à
        # mão, que é o dado mais caro de reproduzir aqui.
        return {
            "nota_id": nota.id,
            "importados": 0,
            "mensagem": (
                f"Esta nota já estava importada com {len(nota.itens)} itens. "
                "Nada foi alterado."
            ),
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

    resposta.status_code = 201
    return {
        "nota_id": nota.id,
        "importados": len(itens),
        "vinculados_automaticamente": vinculados,
        "pendentes_de_produto": len(itens) - vinculados,
        "estabelecimento": bruta.nome_estabelecimento,
        "mensagem": f"{len(itens)} itens importados.",
    }
