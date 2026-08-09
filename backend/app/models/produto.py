"""O produto: o agrupamento que o usuário controla.

O ponto central do app é responder "quanto eu paguei no arroz ao longo do ano". Para
isso, "ARROZ TIO JOAO T1 5KG" e "ARROZ BRANCO TIPO 1 5KG" — descrições diferentes, de
lojas diferentes — precisam apontar para o mesmo *produto*. Quem decide essa
granularidade é o usuário (ele pode querer "Arroz" genérico ou "Arroz Tio João 5kg"
específico), e ``ProdutoAlias`` é a memória que evita ter que decidir de novo na
próxima nota.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.item_nota import ItemNota


class Produto(Base):
    __tablename__ = "produto"
    __table_args__ = (
        # Índice trigram: alimenta a sugestão "já existe algo parecido?" na hora de
        # vincular um item ou criar um produto novo.
        Index(
            "idx_produto_nome_trgm",
            text("nome gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Sem UNIQUE de propósito: unicidade em texto livre é frágil (acento, espaço,
    # maiúscula). A UI sugere reaproveitar um parecido em vez de bloquear, e
    # POST /produtos/merge corrige as duplicatas que passarem.
    nome: Mapped[str] = mapped_column(String, nullable=False)
    categoria: Mapped[str | None] = mapped_column(String, nullable=True)

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    aliases: Mapped[list[ProdutoAlias]] = relationship(
        back_populates="produto", cascade="all, delete-orphan", lazy="selectin"
    )
    itens: Mapped[list[ItemNota]] = relationship(back_populates="produto")


class ProdutoAlias(Base):
    """Como um produto aparece nas notas — a memória dos vínculos já feitos.

    Duas formas de reconhecer o mesmo produto na próxima nota:

    - ``gtin``: o código de barras. Confiável, mas nem toda nota traz.
    - ``descricao_normalizada``: o texto do cupom, normalizado (maiúsculas, sem
      acento). Casa exatamente quando a mesma loja repete a mesma descrição.
    """

    __tablename__ = "produto_alias"
    __table_args__ = (
        CheckConstraint(
            "gtin IS NOT NULL OR descricao_normalizada IS NOT NULL",
            name="ck_alias_tem_gtin_ou_descricao",
        ),
        Index("uq_alias_gtin", "gtin", unique=True, postgresql_where=text("gtin IS NOT NULL")),
        Index(
            "uq_alias_descricao",
            "descricao_normalizada",
            unique=True,
            postgresql_where=text("descricao_normalizada IS NOT NULL"),
        ),
        Index(
            "idx_alias_descricao_trgm",
            text("descricao_normalizada gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    produto_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("produto.id", ondelete="CASCADE"), nullable=False
    )
    # Sempre normalizado com zero-pad até 14 dígitos: GTIN chega com 8/12/13/14
    # dígitos, e sem padding "7896..." e "07896..." não colidem.
    gtin: Mapped[str | None] = mapped_column(String(14), nullable=True)
    descricao_normalizada: Mapped[str | None] = mapped_column(String, nullable=True)

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    produto: Mapped[Produto] = relationship(back_populates="aliases")
