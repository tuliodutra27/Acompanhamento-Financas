"""Ponto de entrada da API."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from app.api.v1 import router as router_v1
from app.core.config import get_settings
from app.core.erros import ErroAplicacao

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

settings = get_settings()

app = FastAPI(
    title=settings.app_nome,
    description=(
        "Acompanhamento de gastos de mercado a partir de notas fiscais eletrônicas "
        "(NFC-e). Uso pessoal."
    ),
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

# Em produção o frontend é servido no mesmo host (roteado pelo Nginx Proxy Manager),
# então CORS não entra em jogo. Isto existe para o dev, onde o Vite roda em outra porta.
if settings.ambiente == "development":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origens,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(router_v1)


@app.exception_handler(ErroAplicacao)
async def tratar_erro_aplicacao(_: Request, exc: ErroAplicacao) -> JSONResponse:
    """Erros de domínio saem no envelope padrão, com código estável."""
    return JSONResponse(status_code=exc.status_http, content=exc.envelope())


@app.exception_handler(RequestValidationError)
async def tratar_erro_validacao(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "erro": {
                "codigo": "VALIDACAO",
                "mensagem": "Os dados enviados não são válidos.",
                "detalhes": {"campos": exc.errors()},
            }
        },
    )
