"""Endpoints de análise: é aqui que o app entrega o valor que motivou construí-lo."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.erros import NaoEncontrado
from app.models.produto import Produto
from app.services import analytics

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/produtos/{produto_id}/serie-precos")
async def serie_precos(
    produto_id: int,
    desde: date | None = None,
    ate: date | None = None,
    sessao: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """Preço do produto mês a mês — "quanto paguei no arroz ao longo do ano"."""
    produto = await sessao.get(Produto, produto_id)
    if produto is None:
        raise NaoEncontrado(f"Produto {produto_id} não encontrado.")

    serie = await analytics.serie_precos(sessao, produto_id, desde=desde, ate=ate)
    return {
        "produto": {"id": produto.id, "nome": produto.nome},
        "serie": serie,
        "variacao": await analytics.variacao_preco(sessao, produto_id),
    }


@router.get("/gastos/ranking")
async def ranking_gastos(
    desde: date | None = None,
    ate: date | None = None,
    limite: int = Query(20, ge=1, le=100),
    sessao: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    """Maiores gastos por produto no período."""
    return await analytics.ranking_gastos(sessao, desde=desde, ate=ate, limite=limite)


@router.get("/gastos/resumo")
async def resumo_gastos(
    desde: date | None = None,
    ate: date | None = None,
    sessao: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    """Total gasto por mês, para comparar um mês com o outro."""
    return await analytics.resumo_mensal(sessao, desde=desde, ate=ate)


@router.get("/totais")
async def totais(sessao: AsyncSession = Depends(get_session)) -> dict[str, object]:
    """Números do topo do dashboard, incluindo quantos itens aguardam revisão."""
    return await analytics.totais_gerais(sessao)
