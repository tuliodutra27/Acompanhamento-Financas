"""A nota fiscal (uma compra), identificada pela chave de acesso."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    LargeBinary,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.enums import OrigemEntrada, StatusNota

if TYPE_CHECKING:
    from app.models.estabelecimento import Estabelecimento
    from app.models.item_nota import ItemNota


class NotaFiscal(Base):
    __tablename__ = "nota_fiscal"
    __table_args__ = (
        CheckConstraint(r"chave_acesso ~ '^\d{44}$'", name="ck_nota_chave_44_digitos"),
        Index("idx_nota_status", "status"),
        Index("idx_nota_emitida", "emitida_em"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chave_acesso: Mapped[str] = mapped_column(String(44), unique=True, nullable=False)

    # Os três campos abaixo saem da própria chave, sem consulta de rede — é o que
    # garante que uma nota tenha dado útil mesmo quando o parse automático falha.
    uf: Mapped[str] = mapped_column(String(2), nullable=False)
    cnpj_emitente: Mapped[str | None] = mapped_column(
        String(14), ForeignKey("estabelecimento.cnpj"), nullable=True
    )
    ano_mes_chave: Mapped[str] = mapped_column(String(4), nullable=False)

    # Data completa: vem do parser ou é digitada pelo usuário no preenchimento manual.
    emitida_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    valor_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    status: Mapped[StatusNota] = mapped_column(
        Enum(StatusNota, name="status_nota"),
        nullable=False,
        default=StatusNota.pendente,
    )
    origem_entrada: Mapped[OrigemEntrada] = mapped_column(
        Enum(OrigemEntrada, name="origem_entrada"), nullable=False
    )

    # A URL completa lida do QR Code, quando a nota entrou por scan. É ela que carrega
    # o hash assinado que abre a nota sem passar pelo formulário com reCAPTCHA — ou
    # seja, é o que torna o parse automático possível. NULL quando a chave foi digitada.
    url_consulta: Mapped[str | None] = mapped_column(String, nullable=True)

    adapter_usado: Mapped[str | None] = mapped_column(String, nullable=True)
    erro_detalhe: Mapped[str | None] = mapped_column(String, nullable=True)

    # HTML/JSON cru da consulta, comprimido. Sem isso, depurar mudança de layout do
    # portal é adivinhação. Expurgado por retencao_payload_bruto_dias.
    payload_bruto: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    itens: Mapped[list[ItemNota]] = relationship(
        back_populates="nota",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ItemNota.id",
    )
    estabelecimento: Mapped[Estabelecimento | None] = relationship(lazy="joined")

    @property
    def preenchida(self) -> bool:
        """A nota já tem itens (independente de terem vindo do parser ou da mão)."""
        return bool(self.itens)
