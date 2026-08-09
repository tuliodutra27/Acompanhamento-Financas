"""Schemas Pydantic da API."""

from app.schemas.notas import (
    EstabelecimentoAtualizar,
    EstabelecimentoLeitura,
    ItemAtualizar,
    ItemCriar,
    ItemLeitura,
    NotaAtualizar,
    NotaCriar,
    NotaDetalhe,
    NotaResumo,
    VincularProduto,
)
from app.schemas.produtos import (
    ItemPendente,
    ProdutoAtualizar,
    ProdutoComEstatisticas,
    ProdutoCriar,
    ProdutoLeitura,
    ProdutoMerge,
    SugestaoProduto,
)

__all__ = [
    "EstabelecimentoAtualizar",
    "EstabelecimentoLeitura",
    "ItemAtualizar",
    "ItemCriar",
    "ItemLeitura",
    "ItemPendente",
    "NotaAtualizar",
    "NotaCriar",
    "NotaDetalhe",
    "NotaResumo",
    "ProdutoAtualizar",
    "ProdutoComEstatisticas",
    "ProdutoCriar",
    "ProdutoLeitura",
    "ProdutoMerge",
    "SugestaoProduto",
    "VincularProduto",
]
