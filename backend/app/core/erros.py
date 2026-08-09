"""Erros de domínio e o envelope de erro da API.

Mesmo formato usado no projeto irmão compara-precos:
``{"erro": {"codigo", "mensagem", "detalhes"}}``.
"""

from __future__ import annotations

from typing import Any


class ErroAplicacao(Exception):
    """Erro de domínio que a API sabe traduzir em resposta HTTP."""

    codigo = "ERRO_INTERNO"
    status_http = 500

    def __init__(
        self, mensagem: str, detalhes: dict[str, Any] | None = None
    ) -> None:
        self.mensagem = mensagem
        self.detalhes = detalhes or {}
        super().__init__(mensagem)

    def envelope(self) -> dict[str, Any]:
        return {
            "erro": {
                "codigo": self.codigo,
                "mensagem": self.mensagem,
                "detalhes": self.detalhes,
            }
        }


class ChaveAcessoInvalida(ErroAplicacao):
    codigo = "CHAVE_INVALIDA"
    status_http = 400


class NaoEncontrado(ErroAplicacao):
    codigo = "NAO_ENCONTRADO"
    status_http = 404


class OperacaoInvalida(ErroAplicacao):
    codigo = "OPERACAO_INVALIDA"
    status_http = 409
