"""Schemas do catálogo pessoal de produtos."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProdutoCriar(BaseModel):
    nome: str = Field(..., min_length=1, max_length=200)
    categoria: str | None = Field(None, max_length=100)


class ProdutoAtualizar(BaseModel):
    nome: str | None = Field(None, min_length=1, max_length=200)
    categoria: str | None = Field(None, max_length=100)


class ProdutoLeitura(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    categoria: str | None


class ProdutoComEstatisticas(ProdutoLeitura):
    n_compras: int = 0
    total_gasto: float = 0.0
    preco_medio: float = 0.0
    ultimo_preco: float | None = None


class ProdutoMerge(BaseModel):
    """Junta dois produtos que na verdade são o mesmo.

    Os itens e aliases de ``origem_id`` passam para ``destino_id``, e ``origem_id`` é
    apagado. Serve para corrigir a duplicata que aparece quando o mesmo produto foi
    cadastrado com dois nomes ("Arroz 5kg" e "Arroz Tio João").
    """

    origem_id: int
    destino_id: int


class SugestaoProduto(BaseModel):
    produto_id: int
    nome: str
    similaridade: float


class ItemPendente(BaseModel):
    """Item aguardando vínculo, já com as sugestões calculadas."""

    item_id: int
    nota_id: int
    descricao_origem: str
    gtin: str | None
    valor_unitario: float
    sugestoes: list[SugestaoProduto] = []
