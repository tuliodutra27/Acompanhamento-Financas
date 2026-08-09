"""Parser do portal de consulta de NFC-e no layout de referência (SVRS/ENCAT).

A maioria dos estados não escreveu um portal próprio: usa a implementação de
referência distribuída pelo ENCAT/SVRS. Isso é uma boa notícia para nós — um único
parser cobre muitas UFs, e adicionar um estado costuma ser só cadastrar a URL em
``urls_uf.py``. Onde o layout for diferente, o parse falha com ``layout_mudou`` e a
nota cai no preenchimento manual, que é o comportamento desenhado.

Estrutura que este parser espera (classes CSS do layout de referência):

    div.txtTopo                 nome do estabelecimento
    div.text                    "CNPJ: 12.345.678/0001-99" e o endereço
    table#tabResult > tr        uma linha por item, com:
        span.txtTit                 descrição
        span.RCod                   "(Código: 7891234567895)"
        span.Rqtd                   "Qtde.:2"
        span.RUN                    "UN: UN"
        span.RvlUnit                "Vl. Unit.: 5,99"
        span.valor                  valor total da linha
    div#totalNota               totais
    div#infos                   número, série, data de emissão, chave
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from bs4 import BeautifulSoup, Tag

from app.adapters.base import ItemBruto, NotaBruta, ParseFalhou, normalizar_gtin, numero_br
from app.models.enums import MotivoFalha

_RE_CNPJ = re.compile(r"CNPJ[:\s]*([\d./-]{14,20})", re.IGNORECASE)
_RE_EMISSAO = re.compile(
    r"Emiss[ãa]o[:\s]*(\d{2}/\d{2}/\d{4})(?:\s+(\d{2}:\d{2}:\d{2}))?", re.IGNORECASE
)
_RE_QUANTIDADE = re.compile(r"([\d.,]+)")
_RE_UNIDADE = re.compile(r"UN[:\s]*([A-Za-z]+)", re.IGNORECASE)


_SEM_ACENTO = str.maketrans("áàâãéêíóôõúüç", "aaaaeeiooouuc")


def _texto(elemento: Tag | None) -> str:
    """Texto limpo de um elemento, com espaços colapsados."""
    if elemento is None:
        return ""
    return re.sub(r"\s+", " ", elemento.get_text(" ", strip=True)).strip()


def _comparavel(texto: str) -> str:
    """Minúsculas sem acento, para casar rótulos do portal de forma tolerante."""
    return texto.lower().translate(_SEM_ACENTO)


def _primeiro(bloco: Tag, *seletores: str) -> Tag | None:
    """Primeiro elemento que casar com algum dos seletores, em ordem de preferência."""
    for seletor in seletores:
        if achado := bloco.select_one(seletor):
            return achado
    return None


def _extrair_item(linha: Tag) -> ItemBruto | None:
    """Converte uma ``<tr>`` do #tabResult em item. Devolve None se não for item."""
    descricao = _texto(_primeiro(linha, "span.txtTit", "span.txtTit2", ".txtTit"))
    if not descricao:
        return None

    quantidade = Decimal("0")
    if bruto_qtd := _texto(_primeiro(linha, "span.Rqtd", ".Rqtd")):
        if achado := _RE_QUANTIDADE.search(bruto_qtd.split(":")[-1]):
            quantidade = numero_br(achado.group(1))

    unidade = None
    if bruto_un := _texto(_primeiro(linha, "span.RUN", ".RUN")):
        if achado := _RE_UNIDADE.search(bruto_un):
            unidade = achado.group(1).upper()[:10]

    valor_unitario = Decimal("0")
    if bruto_unit := _texto(_primeiro(linha, "span.RvlUnit", ".RvlUnit")):
        valor_unitario = numero_br(bruto_unit.split(":")[-1])

    valor_total = numero_br(_texto(_primeiro(linha, "span.valor", ".valor")))

    # O portal mostra "(Código: xxx)", que é o cProd — o código interno do lojista.
    # No varejo de supermercado ele frequentemente *é* o GTIN, mas não sempre; por isso
    # passa por normalizar_gtin(), que só aceita comprimentos válidos de GTIN e
    # descarta o resto. Código interno curto simplesmente não vira GTIN.
    gtin = None
    if bruto_cod := _texto(_primeiro(linha, "span.RCod", ".RCod")):
        gtin = normalizar_gtin(bruto_cod.split(":")[-1])

    # Quantidade zerada quebraria o CHECK do banco; a nota sempre tem quantidade, então
    # isso indica linha de layout inesperado (subtotal, cabeçalho) — descartar.
    if quantidade <= 0:
        return None

    # Alguns portais omitem o valor unitário e só mostram o total da linha.
    if valor_unitario <= 0 and valor_total > 0:
        valor_unitario = (valor_total / quantidade).quantize(Decimal("0.0001"))
    if valor_total <= 0:
        valor_total = (valor_unitario * quantidade).quantize(Decimal("0.01"))

    return ItemBruto(
        descricao=descricao[:500],
        gtin=gtin,
        quantidade=quantidade,
        unidade=unidade,
        valor_unitario=valor_unitario,
        valor_total=valor_total,
    )


def parsear_pagina(html: str) -> NotaBruta:
    """Extrai a nota da página de consulta. Levanta ``ParseFalhou`` se não reconhecer.

    Não faz nenhuma requisição — recebe o HTML já baixado. Isso deixa o parser
    testável com uma página salva em disco, sem depender do portal estar de pé.
    """
    sopa = BeautifulSoup(html, "lxml")

    tabela = sopa.select_one("#tabResult") or sopa.select_one("table.tabResult")
    if tabela is None:
        raise ParseFalhou(
            MotivoFalha.layout_mudou, "tabela de itens (#tabResult) não encontrada"
        )

    itens = [
        item for linha in tabela.select("tr") if (item := _extrair_item(linha)) is not None
    ]
    if not itens:
        raise ParseFalhou(
            MotivoFalha.layout_mudou, "tabela de itens encontrada, mas sem itens legíveis"
        )

    nome_estabelecimento = _texto(_primeiro(sopa, ".txtTopo", "#u20", "div.txtTopo")) or None

    texto_completo = _texto(sopa.select_one("body") or sopa)

    cnpj = None
    if achado := _RE_CNPJ.search(texto_completo):
        cnpj_digitos = re.sub(r"\D", "", achado.group(1))
        cnpj = cnpj_digitos if len(cnpj_digitos) == 14 else None

    emitida_em = None
    if achado := _RE_EMISSAO.search(texto_completo):
        data, hora = achado.group(1), achado.group(2) or "00:00:00"
        try:
            emitida_em = datetime.strptime(f"{data} {hora}", "%d/%m/%Y %H:%M:%S")
        except ValueError:
            emitida_em = None

    valor_total = None
    if bloco_total := sopa.select_one("#totalNota"):
        # "Valor a pagar" é o que interessa (já com descontos), não o valor bruto.
        for linha in bloco_total.select("div, span"):
            texto_linha = _texto(linha)
            if "pagar" in _comparavel(texto_linha):
                if numeros := re.findall(r"[\d.]+,\d{2}", texto_linha):
                    valor_total = numero_br(numeros[-1])
                    break
        if valor_total is None and (numb := bloco_total.select_one(".totalNumb")):
            valor_total = numero_br(_texto(numb))

    # Se nem o total nem o estabelecimento apareceram, é provável que a página não seja
    # a nota (ex.: página de erro que por acaso tem uma tabela) — melhor falhar ruidoso.
    if valor_total is None and nome_estabelecimento is None:
        soma_itens = sum((item.valor_total for item in itens), Decimal("0"))
        valor_total = soma_itens or None

    municipio = None
    if bloco_endereco := sopa.select("div.text"):
        # O endereço é a última linha .text do bloco do emitente: "..., Cidade, UF".
        partes = [p.strip() for p in _texto(bloco_endereco[-1]).split(",") if p.strip()]
        if len(partes) >= 2:
            municipio = partes[-2][:120] if len(partes[-1]) <= 3 else partes[-1][:120]

    return NotaBruta(
        cnpj_emitente=cnpj,
        nome_estabelecimento=nome_estabelecimento,
        municipio=municipio,
        emitida_em=emitida_em,
        valor_total=valor_total,
        itens=itens,
    )
