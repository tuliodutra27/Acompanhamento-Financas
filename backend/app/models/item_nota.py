"""Uma linha da nota fiscal: o que foi comprado, quanto e por qual preço."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.nota_fiscal import NotaFiscal
    from app.models.produto import Produto


class ItemNota(Base):
    __tablename__ = "item_nota"
    __table_args__ = (
        CheckConstraint("quantidade > 0", name="ck_item_quantidade_positiva"),
        CheckConstraint("valor_unitario >= 0", name="ck_item_valor_unitario_nao_negativo"),
        CheckConstraint("valor_total >= 0", name="ck_item_valor_total_nao_negativo"),
        Index("idx_item_nota_id", "nota_id"),
        Index("idx_item_produto", "produto_id"),
        # A fila de revisão é literalmente "itens sem produto vinculado" — este índice
        # parcial serve exatamente essa consulta.
        Index(
            "idx_item_pendentes",
            "produto_id",
            postgresql_where=text("produto_id IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    nota_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("nota_fiscal.id", ondelete="CASCADE"), nullable=False
    )
    # NULL = ainda pendente de revisão. É o próprio estado, sem flag redundante.
    produto_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("produto.id"), nullable=True
    )

    # A descrição exatamente como veio da nota (ou como o usuário digitou). Nunca é
    # sobrescrita pela normalização — é o dado de origem.
    descricao_origem: Mapped[str] = mapped_column(String, nullable=False)
    gtin: Mapped[str | None] = mapped_column(String(14), nullable=True)

    quantidade: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    unidade: Mapped[str | None] = mapped_column(String(10), nullable=True)
    valor_unitario: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    valor_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    nota: Mapped[NotaFiscal] = relationship(back_populates="itens")
    produto: Mapped[Produto | None] = relationship(back_populates="itens", lazy="joined")
