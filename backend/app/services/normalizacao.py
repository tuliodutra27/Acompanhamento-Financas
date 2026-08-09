"""Vínculo entre a linha da nota e o produto do catálogo pessoal.

O problema que isto resolve: para responder "quanto paguei no arroz este ano", as
linhas "ARROZ TIO JOAO T1 5KG" (de uma loja) e "ARROZ BR TIPO1 5 KG" (de outra)
precisam apontar para o mesmo produto. Três níveis, do mais confiável ao menos:

1. **GTIN** — se o alias já tem esse código de barras, é o mesmo produto. Certeza.
2. **Descrição normalizada exata** — a mesma loja repete a mesma descrição; se já
   vinculamos aquele texto uma vez, vale para sempre.
3. **Similaridade de texto (trigram)** — só *sugere*. Quem decide é o usuário, porque
   "ARROZ 5KG" e "ARROZ 1KG" são parecidíssimos como texto e produtos diferentes na
   prática.

Os níveis 1 e 2 rodam sozinhos na importação. O nível 3 nunca vincula sem confirmação.
"""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item_nota import ItemNota
from app.models.produto import Produto, ProdutoAlias

# Abaixo disso a sugestão é ruído. pg_trgm devolve similaridade entre 0 e 1.
LIMITE_SIMILARIDADE = 0.35
MAX_SUGESTOES = 5


def normalizar_descricao(texto: str) -> str:
    """Maiúsculas, sem acento, espaços colapsados — a forma canônica de comparação.

    É só para *comparar*. A descrição original nunca é sobrescrita: fica em
    ``item_nota.descricao_origem``, que é o dado de origem.
    """
    if not texto:
        return ""

    sem_acento = "".join(
        caractere
        for caractere in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caractere) != "Mn"
    )
    return re.sub(r"\s+", " ", sem_acento).strip().upper()


async def encontrar_produto_por_alias(
    sessao: AsyncSession, *, gtin: str | None, descricao: str
) -> int | None:
    """Produto já conhecido para este GTIN ou esta descrição exata. Sem adivinhação."""
    if gtin:
        encontrado = await sessao.scalar(
            select(ProdutoAlias.produto_id).where(ProdutoAlias.gtin == gtin)
        )
        if encontrado:
            return encontrado

    descricao_normalizada = normalizar_descricao(descricao)
    if descricao_normalizada:
        encontrado = await sessao.scalar(
            select(ProdutoAlias.produto_id).where(
                ProdutoAlias.descricao_normalizada == descricao_normalizada
            )
        )
        if encontrado:
            return encontrado

    return None


async def sugerir_produtos(
    sessao: AsyncSession, descricao: str, *, limite: int = MAX_SUGESTOES
) -> list[dict[str, object]]:
    """Produtos parecidos com esta descrição, por similaridade trigram.

    Alimenta a tela de revisão: o usuário vê "é algum destes?" em vez de digitar o
    nome do produto de novo a cada nota.

    Duas medidas, e o maior valor entre elas — porque os dois lados da comparação têm
    comprimentos muito diferentes:

    - ``word_similarity(nome, alvo)`` para o **nome do produto**, que é curto ("Arroz")
      contra uma descrição longa ("ARROZ BRANCO T1 5 KG"). O ``similarity()`` comum
      afunda nesse caso: os trigramas sobrando na descrição contam como divergência, e
      um casamento óbvio fica abaixo de qualquer limite razoável. O ``word_similarity``
      procura o melhor trecho, que é exatamente a pergunta certa aqui.
    - ``similarity(alias, alvo)`` para as **descrições já vinculadas** ao produto, que
      têm o mesmo comprimento do alvo — aí o ``similarity()`` comum é a medida certa, e
      costuma ser a mais informativa: casa "ARROZ BR TIPO1 5KG" com "ARROZ BRANCO TIPO
      1 5KG" mesmo sem o nome do produto se parecer com nenhuma das duas.
    """
    alvo = normalizar_descricao(descricao)
    if not alvo:
        return []

    por_nome = func.word_similarity(func.upper(Produto.nome), alvo)
    por_alias = func.coalesce(
        func.max(func.similarity(ProdutoAlias.descricao_normalizada, alvo)), 0.0
    )
    similaridade = func.greatest(por_nome, por_alias)

    consulta = (
        select(Produto.id, Produto.nome, similaridade.label("similaridade"))
        .outerjoin(
            ProdutoAlias,
            (ProdutoAlias.produto_id == Produto.id)
            & ProdutoAlias.descricao_normalizada.is_not(None),
        )
        .group_by(Produto.id, Produto.nome)
        .having(similaridade > LIMITE_SIMILARIDADE)
        .order_by(similaridade.desc())
        .limit(limite)
    )

    resultado = await sessao.execute(consulta)
    return [
        {"produto_id": linha.id, "nome": linha.nome, "similaridade": float(linha.similaridade)}
        for linha in resultado
    ]


async def registrar_alias(
    sessao: AsyncSession, *, produto_id: int, gtin: str | None, descricao: str
) -> None:
    """Grava o vínculo aprendido, para não perguntar de novo na próxima nota.

    Idempotente: se o alias já existe (para qualquer produto), não faz nada — não
    sobrescreve uma decisão anterior do usuário silenciosamente.
    """
    descricao_normalizada = normalizar_descricao(descricao) or None

    if gtin:
        ja_existe = await sessao.scalar(
            select(ProdutoAlias.id).where(ProdutoAlias.gtin == gtin)
        )
        if not ja_existe:
            sessao.add(ProdutoAlias(produto_id=produto_id, gtin=gtin))

    if descricao_normalizada:
        ja_existe = await sessao.scalar(
            select(ProdutoAlias.id).where(
                ProdutoAlias.descricao_normalizada == descricao_normalizada
            )
        )
        if not ja_existe:
            sessao.add(
                ProdutoAlias(
                    produto_id=produto_id, descricao_normalizada=descricao_normalizada
                )
            )


async def autovincular_itens(sessao: AsyncSession, itens: list[ItemNota]) -> int:
    """Vincula os itens que dão para vincular com certeza. Devolve quantos vinculou.

    O resto fica com ``produto_id`` nulo — que é, por si só, a fila de revisão.
    """
    vinculados = 0
    for item in itens:
        if item.produto_id is not None:
            continue

        produto_id = await encontrar_produto_por_alias(
            sessao, gtin=item.gtin, descricao=item.descricao_origem
        )
        if produto_id is not None:
            item.produto_id = produto_id
            vinculados += 1

    return vinculados
