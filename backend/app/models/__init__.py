"""Models SQLAlchemy.

Importados aqui para que o metadata da Base fique completo — o Alembic depende disso
para gerar as migrations.
"""

from app.models.enums import MotivoFalha, OrigemEntrada, StatusNota
from app.models.estabelecimento import Estabelecimento
from app.models.item_nota import ItemNota
from app.models.nota_fiscal import NotaFiscal
from app.models.produto import Produto, ProdutoAlias

__all__ = [
    "Estabelecimento",
    "ItemNota",
    "MotivoFalha",
    "NotaFiscal",
    "OrigemEntrada",
    "Produto",
    "ProdutoAlias",
    "StatusNota",
]
