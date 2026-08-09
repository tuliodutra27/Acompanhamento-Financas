"""Onde a compra foi feita, identificado pelo CNPJ."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Estabelecimento(Base):
    __tablename__ = "estabelecimento"

    # O CNPJ vem da própria chave de acesso, então existe mesmo quando o parse falha —
    # por isso é a chave primária natural aqui.
    cnpj: Mapped[str] = mapped_column(String(14), primary_key=True)
    razao_social: Mapped[str | None] = mapped_column(String, nullable=True)
    nome_fantasia: Mapped[str | None] = mapped_column(String, nullable=True)
    municipio: Mapped[str | None] = mapped_column(String, nullable=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    @property
    def nome_exibicao(self) -> str:
        return self.nome_fantasia or self.razao_social or self.cnpj
