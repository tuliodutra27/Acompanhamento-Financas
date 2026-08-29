"""Rotas da API v1."""

from fastapi import APIRouter, Depends

from app.api.v1 import analytics, auth, health, importar, notas, produtos
from app.core.auth import exigir_sessao

router = APIRouter(prefix="/api/v1")

# Abertas: `health` é sonda de container (o Docker não faz login) e `auth` é a porta de
# entrada — protegê-la seria trancar a chave dentro da casa.
router.include_router(health.router)
router.include_router(auth.router)

# `importar` tem autorização própria, por token, dentro da rota: o atalho roda no site da
# SEFAZ e o cookie de sessão não viaja entre sites. Ver app/core/auth.py.
# Antes de `notas`: a rota fixa /notas/importar-html não pode ser capturada por
# /notas/{nota_id}, que casaria "importar-html" como id.
router.include_router(importar.router)

# Todo o resto toca dados pessoais de compra e exige sessão. A dependência fica aqui, no
# ponto de montagem, e não espalhada rota a rota — assim uma rota nova nasce protegida
# por padrão, em vez de depender de alguém lembrar de anotá-la.
protegidas = [Depends(exigir_sessao)]
router.include_router(notas.router, dependencies=protegidas)
router.include_router(produtos.router, dependencies=protegidas)
router.include_router(analytics.router, dependencies=protegidas)

__all__ = ["router"]
