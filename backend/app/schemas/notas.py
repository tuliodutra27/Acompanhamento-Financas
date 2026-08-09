"""Schemas de entrada e saída de notas e itens."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import OrigemEntrada, StatusNota


class NotaCriar(BaseModel):
    """O que o app envia depois de escanear o QR Code ou receber a chave digitada."""

    conteudo: str = Field(
        ...,
        min_length=8,
        description=(
            "URL completa lida do QR Code (preferido — é o que permite o preenchimento "
            "automático) ou a chave de acesso de 44 dígitos."
        ),
    )
    origem: OrigemEntrada = OrigemEntrada.qrcode


class ItemLeitura(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    produto_id: int | None
    produto_nome: str | None = None
    descricao_origem: str
    gtin: str | None
    quantidade: Decimal
    unidade: str | None
    valor_unitario: Decimal
    valor_total: Decimal


class ItemCriar(BaseModel):
    """Entrada manual de um item (o caminho quando o parse automático não passa)."""

    descricao_origem: str = Field(..., min_length=1, max_length=500)
    gtin: str | None = None
    quantidade: Decimal = Field(..., gt=0)
    unidade: str | None = Field(None, max_length=10)
    valor_unitario: Decimal | None = Field(None, ge=0)
    valor_total: Decimal | None = Field(None, ge=0)
    produto_id: int | None = None
    novo_produto_nome: str | None = Field(None, min_length=1, max_length=200)


class ItemAtualizar(BaseModel):
    descricao_origem: str | None = Field(None, min_length=1, max_length=500)
    gtin: str | None = None
    quantidade: Decimal | None = Field(None, gt=0)
    unidade: str | None = Field(None, max_length=10)
    valor_unitario: Decimal | None = Field(None, ge=0)
    valor_total: Decimal | None = Field(None, ge=0)


class VincularProduto(BaseModel):
    """Vincula um item a um produto existente ou cria um produto novo para ele."""

    produto_id: int | None = None
    novo_produto_nome: str | None = Field(None, min_length=1, max_length=200)


class EstabelecimentoLeitura(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cnpj: str
    razao_social: str | None
    nome_fantasia: str | None
    municipio: str | None
    uf: str | None


class EstabelecimentoAtualizar(BaseModel):
    razao_social: str | None = Field(None, max_length=200)
    nome_fantasia: str | None = Field(None, max_length=200)
    municipio: str | None = Field(None, max_length=120)


class NotaResumo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chave_acesso: str
    uf: str
    ano_mes_chave: str
    emitida_em: datetime | None
    valor_total: Decimal | None
    status: StatusNota
    origem_entrada: OrigemEntrada
    erro_detalhe: str | None
    n_itens: int = 0
    estabelecimento_nome: str | None = None


class NotaDetalhe(NotaResumo):
    cnpj_emitente: str | None
    adapter_usado: str | None
    url_consulta: str | None
    # Link do portal da SEFAZ para o usuário abrir a nota no próprio navegador e
    # conferir os itens enquanto preenche à mão.
    url_portal_uf: str | None = None
    itens: list[ItemLeitura] = []


class NotaAtualizar(BaseModel):
    """Dados que o usuário completa quando o parse não trouxe (data, valor total)."""

    emitida_em: datetime | None = None
    valor_total: Decimal | None = Field(None, ge=0)
