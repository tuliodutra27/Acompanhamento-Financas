"""Rotas da API v1."""

from fastapi import APIRouter

from app.api.v1 import analytics, health, importar, notas, produtos

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
# Antes de `notas`: a rota fixa /notas/importar-html não pode ser capturada por
# /notas/{nota_id}, que casaria "importar-html" como id.
router.include_router(importar.router)
router.include_router(notas.router)
router.include_router(produtos.router)
router.include_router(analytics.router)

__all__ = ["router"]
