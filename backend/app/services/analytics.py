"""As perguntas que o app existe para responder.

"Quanto eu paguei no arroz em cada mês do ano?", "quais são meus maiores gastos?",
"estou gastando mais este mês do que no passado?".
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Numeric, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.item_nota import ItemNota
from app.models.nota_fiscal import NotaFiscal
from app.models.produto import Produto


def _data_da_compra() -> ColumnElement[date]:
    """Data a usar nas agregações.

    Prefere a data real de emissão (do parse ou digitada). Quando ela não existe —
    nota registrada, itens ainda não preenchidos — cai para o mês que está codificado
    na própria chave de acesso. Assim uma nota nunca fica fora dos relatórios por
    falta de data.
    """
    return func.coalesce(
        func.date_trunc("month", NotaFiscal.emitida_em),
        func.to_date(NotaFiscal.ano_mes_chave, "YYMM"),
    )


def _filtro_periodo(consulta, desde: date | None, ate: date | None):
    if desde is not None:
        consulta = consulta.where(_data_da_compra() >= desde)
    if ate is not None:
        consulta = consulta.where(_data_da_compra() <= ate)
    return consulta


async def serie_precos(
    sessao: AsyncSession,
    produto_id: int,
    *,
    desde: date | None = None,
    ate: date | None = None,
) -> list[dict[str, object]]:
    """Preço unitário do produto mês a mês — o gráfico principal do app.

    Devolve média, mínimo e máximo por mês, mais quantas compras entraram no cálculo.
    Mostrar o ``n_compras`` importa: uma média de uma única compra não é tendência, e
    a interface precisa poder dizer isso.
    """
    mes = _data_da_compra().label("mes")
    consulta = (
        select(
            mes,
            func.avg(ItemNota.valor_unitario).label("preco_medio"),
            func.min(ItemNota.valor_unitario).label("preco_min"),
            func.max(ItemNota.valor_unitario).label("preco_max"),
            func.sum(ItemNota.valor_total).label("total_gasto"),
            func.sum(ItemNota.quantidade).label("quantidade_total"),
            func.count().label("n_compras"),
        )
        .join(NotaFiscal, NotaFiscal.id == ItemNota.nota_id)
        .where(ItemNota.produto_id == produto_id)
        .group_by(mes)
        .order_by(mes)
    )

    resultado = await sessao.execute(_filtro_periodo(consulta, desde, ate))
    return [
        {
            "mes": linha.mes.date().isoformat() if hasattr(linha.mes, "date") else str(linha.mes),
            "preco_medio": float(linha.preco_medio or 0),
            "preco_min": float(linha.preco_min or 0),
            "preco_max": float(linha.preco_max or 0),
            "total_gasto": float(linha.total_gasto or 0),
            "quantidade_total": float(linha.quantidade_total or 0),
            "n_compras": int(linha.n_compras or 0),
        }
        for linha in resultado
    ]


async def ranking_gastos(
    sessao: AsyncSession,
    *,
    desde: date | None = None,
    ate: date | None = None,
    limite: int = 20,
) -> list[dict[str, object]]:
    """Maiores gastos por produto no período — "onde meu dinheiro está indo"."""
    consulta = (
        select(
            Produto.id.label("produto_id"),
            Produto.nome.label("nome"),
            func.sum(ItemNota.valor_total).label("total_gasto"),
            func.sum(ItemNota.quantidade).label("quantidade_total"),
            func.avg(ItemNota.valor_unitario).label("preco_medio"),
            func.count().label("n_compras"),
        )
        .join(ItemNota, ItemNota.produto_id == Produto.id)
        .join(NotaFiscal, NotaFiscal.id == ItemNota.nota_id)
        .group_by(Produto.id, Produto.nome)
        .order_by(func.sum(ItemNota.valor_total).desc())
        .limit(limite)
    )

    resultado = await sessao.execute(_filtro_periodo(consulta, desde, ate))
    return [
        {
            "produto_id": linha.produto_id,
            "nome": linha.nome,
            "total_gasto": float(linha.total_gasto or 0),
            "quantidade_total": float(linha.quantidade_total or 0),
            "preco_medio": float(linha.preco_medio or 0),
            "n_compras": int(linha.n_compras or 0),
        }
        for linha in resultado
    ]


async def resumo_mensal(
    sessao: AsyncSession, *, desde: date | None = None, ate: date | None = None
) -> list[dict[str, object]]:
    """Total gasto por mês, para comparar um mês com o outro."""
    mes = _data_da_compra().label("mes")
    consulta = (
        select(
            mes,
            func.sum(ItemNota.valor_total).label("total_gasto"),
            func.count(func.distinct(NotaFiscal.id)).label("n_notas"),
            func.count().label("n_itens"),
        )
        .join(NotaFiscal, NotaFiscal.id == ItemNota.nota_id)
        .group_by(mes)
        .order_by(mes)
    )

    resultado = await sessao.execute(_filtro_periodo(consulta, desde, ate))
    return [
        {
            "mes": linha.mes.date().isoformat() if hasattr(linha.mes, "date") else str(linha.mes),
            "total_gasto": float(linha.total_gasto or 0),
            "n_notas": int(linha.n_notas or 0),
            "n_itens": int(linha.n_itens or 0),
        }
        for linha in resultado
    ]


async def variacao_preco(
    sessao: AsyncSession, produto_id: int
) -> dict[str, object] | None:
    """Primeiro preço, último preço e variação percentual do produto.

    É o número que responde "o arroz subiu quanto?" sem o usuário ter que ler o
    gráfico. Devolve ``None`` quando há menos de duas compras — com um ponto só não
    existe variação, e inventar um número aqui seria pior que não mostrar nada.
    """
    serie = await serie_precos(sessao, produto_id)
    if len(serie) < 2:
        return None

    primeiro = serie[0]
    ultimo = serie[-1]
    preco_inicial = Decimal(str(primeiro["preco_medio"]))
    preco_final = Decimal(str(ultimo["preco_medio"]))

    if preco_inicial == 0:
        return None

    variacao = (preco_final - preco_inicial) / preco_inicial * 100
    return {
        "mes_inicial": primeiro["mes"],
        "preco_inicial": float(preco_inicial),
        "mes_final": ultimo["mes"],
        "preco_final": float(preco_final),
        "variacao_percentual": round(float(variacao), 2),
        "meses_com_dados": len(serie),
    }


async def totais_gerais(sessao: AsyncSession) -> dict[str, object]:
    """Números do topo do dashboard."""
    total_gasto = await sessao.scalar(
        select(func.coalesce(func.sum(ItemNota.valor_total), cast(literal(0), Numeric)))
    )
    n_notas = await sessao.scalar(select(func.count(NotaFiscal.id)))
    n_itens = await sessao.scalar(select(func.count(ItemNota.id)))
    n_produtos = await sessao.scalar(select(func.count(Produto.id)))
    itens_pendentes = await sessao.scalar(
        select(func.count(ItemNota.id)).where(ItemNota.produto_id.is_(None))
    )

    return {
        "total_gasto": float(total_gasto or 0),
        "n_notas": int(n_notas or 0),
        "n_itens": int(n_itens or 0),
        "n_produtos": int(n_produtos or 0),
        "itens_pendentes": int(itens_pendentes or 0),
    }
