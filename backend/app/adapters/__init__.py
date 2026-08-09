"""Adapters de consulta de NFC-e por UF."""

from app.adapters.base import (
    ItemBruto,
    NFCeAdapter,
    NotaBruta,
    ParseFalhou,
    normalizar_gtin,
    numero_br,
)
from app.adapters.registry import adapter_para, ufs_suportadas
from app.adapters.urls_uf import url_consulta_manual

__all__ = [
    "ItemBruto",
    "NFCeAdapter",
    "NotaBruta",
    "ParseFalhou",
    "adapter_para",
    "normalizar_gtin",
    "numero_br",
    "ufs_suportadas",
    "url_consulta_manual",
]
