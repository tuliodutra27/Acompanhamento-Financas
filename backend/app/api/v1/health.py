"""Health check e metadados de suporte por UF."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.registry import ufs_suportadas
from app.core.config import get_settings
from app.core.db import get_session

router = APIRouter(tags=["sistema"])


@router.get("/health")
async def health(sessao: AsyncSession = Depends(get_session)) -> dict[str, object]:
    """Status do app e do banco. Usado pelo healthcheck do container."""
    try:
        await sessao.execute(text("SELECT 1"))
        banco_ok = True
    except Exception:  # noqa: BLE001 - health check nunca deve estourar
        banco_ok = False

    return {
        "status": "ok" if banco_ok else "degradado",
        "banco": "ok" if banco_ok else "indisponivel",
        "ambiente": get_settings().ambiente,
        "ufs_com_adapter": len(ufs_suportadas()),
    }


@router.get("/ufs-suportadas")
async def listar_ufs_suportadas() -> dict[str, object]:
    """Quais UFs têm adapter e sob qual condição o preenchimento automático funciona.

    A interface usa isso para dar expectativa honesta antes do usuário tentar: o
    preenchimento automático depende de escanear o QR Code, porque só a URL do QR
    carrega o hash que abre a nota sem passar pelo formulário com reCAPTCHA.
    """
    return {
        "ufs": ufs_suportadas(),
        "observacao": (
            "O preenchimento automático depende de escanear o QR Code do cupom. "
            "Chave digitada cai direto no preenchimento manual, porque a consulta por "
            "chave nos portais da SEFAZ é protegida por reCAPTCHA."
        ),
    }
