"""Rotas de sessão: entrar, sair e perguntar se está autenticado."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.core.auth import (
    CHAVE_SESSAO,
    NaoAutenticado,
    autenticacao_ativa,
    esta_autenticado,
    senha_correta,
    token_importacao,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class Credenciais(BaseModel):
    senha: str = Field(..., min_length=1)


@router.get("/sessao")
async def sessao(requisicao: Request) -> dict[str, object]:
    """Estado da sessão — o frontend consulta isto antes de desenhar qualquer tela."""
    return {
        "autenticado": esta_autenticado(requisicao),
        # Quando não há senha configurada o app segue aberto; a interface avisa em vez
        # de fingir que existe proteção.
        "autenticacao_ativa": autenticacao_ativa(),
    }


@router.post("/login")
async def login(credenciais: Credenciais, requisicao: Request) -> dict[str, object]:
    if not autenticacao_ativa():
        return {"autenticado": True, "autenticacao_ativa": False}

    if not senha_correta(credenciais.senha):
        # Atraso fixo em qualquer falha: sem ele, um atacante mede o tempo de resposta
        # para saber se errou a senha ou se bateu num limite. Um usuário só, então
        # meio segundo não incomoda ninguém.
        await asyncio.sleep(0.5)
        raise NaoAutenticado("Senha incorreta.")

    requisicao.session[CHAVE_SESSAO] = True
    return {"autenticado": True, "autenticacao_ativa": True}


@router.post("/logout")
async def logout(requisicao: Request) -> dict[str, bool]:
    requisicao.session.clear()
    return {"autenticado": False}


@router.get("/token-importacao")
async def obter_token_importacao(requisicao: Request) -> dict[str, str]:
    """Credencial que o atalho de importação carrega na URL.

    Exige sessão: é o que impede alguém de pegar o token sem estar autenticado e passar
    a inserir notas na conta.
    """
    if not esta_autenticado(requisicao):
        raise NaoAutenticado("Faça login para ver o atalho de importação.")
    return {"token": token_importacao()}
