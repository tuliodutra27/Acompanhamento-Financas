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


@router.get("/categorias")
async def gasto_por_categoria(
    desde: date | None = None,
    ate: date | None = None,
    sessao: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    """Gasto por categoria, com a fatia percentual de cada uma."""
    return await analytics.gasto_por_categoria(sessao, desde=desde, ate=ate)


@router.get("/categorias/evolucao")
async def evolucao_por_categoria(
    desde: date | None = None,
    ate: date | None = None,
    limite: int = Query(
        7,
        ge=3,
        le=8,
        description=(
            "Quantas categorias manter separadas; o resto vira 'Outras'. O teto de 8 "
            "não é arbitrário: acima disso as cores deixam de ser distinguíveis."
        ),
    ),
    sessao: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """Gasto por categoria mês a mês, pronto para barra empilhada."""
    return await analytics.evolucao_por_categoria(
        sessao, desde=desde, ate=ate, limite_categorias=limite
    )


@router.get("/categorias/{categoria}/produtos")
async def produtos_da_categoria(
    categoria: str,
    desde: date | None = None,
    ate: date | None = None,
    sessao: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    """Detalhamento: os produtos de uma categoria, do maior gasto para o menor."""
    return await analytics.produtos_da_categoria(
        sessao, categoria, desde=desde, ate=ate
    )


@router.get("/inflacao-cesta")
async def inflacao_cesta(
    sessao: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    """Índice de preços da sua cesta, mês a mês (Laspeyres), com cobertura.

    Diferente de comparar o total gasto: isola a variação de **preço** da variação do
    que foi comprado. Ver a docstring do serviço para o cálculo e as limitações.
    """
    return await analytics.inflacao_cesta(sessao)


@router.get("/alertas-preco")
async def alertas_preco(
    limite: float = Query(
        15.0, ge=5.0, description="Quantos %% acima do usual para gerar alerta"
    ),
    minimo_compras: int = Query(
        3, ge=2, description="Mínimo de compras do produto para haver 'preço usual'"
    ),
    sessao: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    """Itens pagos acima da mediana histórica daquele produto."""
    return await analytics.alertas_preco(
        sessao, limite_percentual=limite, minimo_compras=minimo_compras
    )


@router.get("/recorrencia")
async def recorrencia(sessao: AsyncSession = Depends(get_session)) -> dict[str, object]:
    """Produtos recorrentes, frequentes e eventuais, com o gasto de cada grupo."""
    return await analytics.recorrencia_produtos(sessao)


@router.get("/grupos-suspeitos")
async def grupos_suspeitos(
    fator_preco: float = Query(
        3.0,
        ge=1.5,
        description="A partir de quantas vezes entre o menor e o maior preço suspeitar",
    ),
    sessao: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    """Produtos que provavelmente agrupam coisas diferentes.

    Serve para pegar o erro silencioso de classificação: dois produtos distintos sob o
    mesmo nome geram uma "variação de preço" que parece insight e é só troca de formato.
    """
    return await analytics.grupos_suspeitos(sessao, fator_preco=fator_preco)


@router.get("/totais")
async def totais(sessao: AsyncSession = Depends(get_session)) -> dict[str, object]:
    """Números do topo do dashboard, incluindo quantos itens aguardam revisão."""
    return await analytics.totais_gerais(sessao)
