"""Schema inicial: notas, itens, produtos, aliases e estabelecimentos.

Revision ID: 0001
Revises:
Create Date: 2026-08-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # pg_trgm alimenta a sugestão de produto por similaridade de texto — é o que evita
    # ter que reclassificar "ARROZ TIO JOAO 5KG" do zero em cada nota nova.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    status_nota = sa.Enum(
        "pendente", "ok", "falhou_parse", "manual", name="status_nota"
    )
    origem_entrada = sa.Enum("qrcode", "chave_manual", name="origem_entrada")
    status_nota.create(op.get_bind(), checkfirst=True)
    origem_entrada.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "estabelecimento",
        sa.Column("cnpj", sa.String(14), primary_key=True),
        sa.Column("razao_social", sa.String(), nullable=True),
        sa.Column("nome_fantasia", sa.String(), nullable=True),
        sa.Column("municipio", sa.String(), nullable=True),
        sa.Column("uf", sa.String(2), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "produto",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("nome", sa.String(), nullable=False),
        sa.Column("categoria", sa.String(), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.execute(
        "CREATE INDEX idx_produto_nome_trgm ON produto USING gin (nome gin_trgm_ops)"
    )

    op.create_table(
        "produto_alias",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "produto_id",
            sa.BigInteger(),
            sa.ForeignKey("produto.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("gtin", sa.String(14), nullable=True),
        sa.Column("descricao_normalizada", sa.String(), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "gtin IS NOT NULL OR descricao_normalizada IS NOT NULL",
            name="ck_alias_tem_gtin_ou_descricao",
        ),
    )
    # Índices únicos parciais: um GTIN (ou uma descrição exata) só pode apontar para um
    # produto. É isso que torna o vínculo "memória" e não palpite repetido.
    op.execute(
        "CREATE UNIQUE INDEX uq_alias_gtin ON produto_alias (gtin) "
        "WHERE gtin IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_alias_descricao ON produto_alias "
        "(descricao_normalizada) WHERE descricao_normalizada IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX idx_alias_descricao_trgm ON produto_alias "
        "USING gin (descricao_normalizada gin_trgm_ops)"
    )

    op.create_table(
        "nota_fiscal",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("chave_acesso", sa.String(44), nullable=False, unique=True),
        sa.Column("uf", sa.String(2), nullable=False),
        sa.Column(
            "cnpj_emitente",
            sa.String(14),
            sa.ForeignKey("estabelecimento.cnpj"),
            nullable=True,
        ),
        sa.Column("ano_mes_chave", sa.String(4), nullable=False),
        sa.Column("emitida_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valor_total", sa.Numeric(12, 2), nullable=True),
        sa.Column("status", status_nota, nullable=False, server_default="pendente"),
        sa.Column("origem_entrada", origem_entrada, nullable=False),
        sa.Column("url_consulta", sa.String(), nullable=True),
        sa.Column("adapter_usado", sa.String(), nullable=True),
        sa.Column("erro_detalhe", sa.String(), nullable=True),
        sa.Column("payload_bruto", sa.LargeBinary(), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            r"chave_acesso ~ '^\d{44}$'", name="ck_nota_chave_44_digitos"
        ),
    )
    op.create_index("idx_nota_status", "nota_fiscal", ["status"])
    op.create_index("idx_nota_emitida", "nota_fiscal", ["emitida_em"])

    op.create_table(
        "item_nota",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "nota_id",
            sa.BigInteger(),
            sa.ForeignKey("nota_fiscal.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "produto_id", sa.BigInteger(), sa.ForeignKey("produto.id"), nullable=True
        ),
        sa.Column("descricao_origem", sa.String(), nullable=False),
        sa.Column("gtin", sa.String(14), nullable=True),
        sa.Column("quantidade", sa.Numeric(12, 4), nullable=False),
        sa.Column("unidade", sa.String(10), nullable=True),
        sa.Column("valor_unitario", sa.Numeric(12, 4), nullable=False),
        sa.Column("valor_total", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("quantidade > 0", name="ck_item_quantidade_positiva"),
        sa.CheckConstraint(
            "valor_unitario >= 0", name="ck_item_valor_unitario_nao_negativo"
        ),
        sa.CheckConstraint("valor_total >= 0", name="ck_item_valor_total_nao_negativo"),
    )
    op.create_index("idx_item_nota_id", "item_nota", ["nota_id"])
    op.create_index("idx_item_produto", "item_nota", ["produto_id"])
    # A fila de revisão é "itens sem produto": índice parcial serve exatamente ela.
    op.execute(
        "CREATE INDEX idx_item_pendentes ON item_nota (produto_id) "
        "WHERE produto_id IS NULL"
    )


def downgrade() -> None:
    op.drop_table("item_nota")
    op.drop_table("nota_fiscal")
    op.drop_table("produto_alias")
    op.drop_table("produto")
    op.drop_table("estabelecimento")
    sa.Enum(name="origem_entrada").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="status_nota").drop(op.get_bind(), checkfirst=True)
