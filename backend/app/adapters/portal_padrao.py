"""Adapter que consulta a nota pela URL do QR Code e lê o layout de referência.

Um adapter só, servindo qualquer UF. Isso é possível porque:

1. O **conteúdo do QR Code é padronizado nacionalmente** — a URL já vem apontando para
   o portal correto daquele estado, com o hash assinado da nota. Não precisamos saber
   qual é o endereço da SEFAZ de cada UF: o cupom nos diz.
2. A **página de resposta** segue, na maioria dos estados, a implementação de
   referência do ENCAT/SVRS, que ``layout_padrao.py`` sabe ler.

Onde uma dessas duas premissas não valer, o parse falha com um motivo registrado e a
nota cai no preenchimento manual — que é o caminho desenhado, não um acidente.
"""

from __future__ import annotations

import gzip

import httpx

from app.adapters.base import (
    NFCeAdapter,
    NotaBruta,
    ParseFalhou,
    detectar_bloqueio,
)
from app.adapters.layout_padrao import parsear_pagina
from app.core.config import get_settings
from app.models.enums import MotivoFalha


class PortalPadraoAdapter(NFCeAdapter):
    """Consulta via URL do QR Code + parse do layout de referência."""

    nome = "portal_padrao"

    def __init__(self, uf: str) -> None:
        self.uf = uf.upper()
        self._settings = get_settings()

    async def buscar(self, chave: str, url_consulta: str | None = None) -> NotaBruta:
        if not url_consulta:
            # Sem a URL do QR Code, o único caminho seria o formulário de consulta por
            # chave — protegido por reCAPTCHA. Falhar aqui é instantâneo e honesto:
            # melhor mandar o usuário para o preenchimento manual do que gastar 10s
            # numa requisição que vai ser barrada.
            raise ParseFalhou(
                MotivoFalha.sem_url_qrcode,
                "chave digitada não permite consulta automática (só a URL do QR Code)",
            )

        cabecalhos = {
            "User-Agent": self._settings.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9",
        }

        try:
            async with httpx.AsyncClient(
                timeout=self._settings.timeout_adapter_segundos,
                follow_redirects=True,
                headers=cabecalhos,
            ) as cliente:
                resposta = await cliente.get(url_consulta)
        except httpx.TimeoutException as exc:
            raise ParseFalhou(MotivoFalha.timeout, str(exc)) from exc
        except httpx.HTTPError as exc:
            raise ParseFalhou(MotivoFalha.bloqueio, str(exc)) from exc

        corpo = resposta.text

        if motivo := detectar_bloqueio(resposta.status_code, corpo):
            raise ParseFalhou(
                motivo, f"HTTP {resposta.status_code} ao consultar portal de {self.uf}"
            )

        nota = parsear_pagina(corpo)

        # Guardar o HTML cru (comprimido) é o que permite descobrir *o que* mudou no
        # portal quando um parse quebrar, sem ter que reproduzir a falha.
        nota.payload_bruto = gzip.compress(corpo.encode("utf-8", errors="replace"))
        nota.uf = nota.uf or self.uf
        return nota
