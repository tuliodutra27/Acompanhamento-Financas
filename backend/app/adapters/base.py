"""Contrato dos adapters de consulta de NFC-e por UF.

Não existe API JSON nacional única de consulta de nota fiscal: cada estado publica seu
próprio portal HTML de consulta por chave de acesso. Então cada UF é um adapter, com a
mesma interface — adicionar um estado é escrever um arquivo e registrá-lo, sem tocar em
mais nada.

Regras que todo adapter deve seguir:

1. Timeout explícito por requisição (``Settings.timeout_adapter_segundos``).
2. **Nunca deixar exceção estranha vazar**: qualquer falha vira ``ParseFalhou`` com um
   ``motivo`` da enum ``MotivoFalha``. Quem chama trata um caso só.
3. Guardar o HTML bruto em ``NotaBruta.payload_bruto`` — é o que permite depurar
   mudança de layout do portal depois.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import MotivoFalha

# Marcadores de anti-bot/captcha no corpo da resposta. Quando aparecem, o portal não
# está com problema — está barrando automação, e insistir não resolve.
_MARCADORES_CAPTCHA = (
    "recaptcha",
    "g-recaptcha",
    "hcaptcha",
    "imperva",
    "incapsula",
    "_incap_",
    "captcha",
)


class ParseFalhou(Exception):
    """O parse automático não funcionou. ``motivo`` diz o que fazer a respeito."""

    def __init__(self, motivo: MotivoFalha, detalhe: str | None = None) -> None:
        self.motivo = motivo
        self.detalhe = detalhe
        super().__init__(f"{motivo.value}: {detalhe}" if detalhe else motivo.value)


class ItemBruto(BaseModel):
    """Um item como veio do portal, antes de qualquer normalização nossa."""

    descricao: str
    gtin: str | None = None
    quantidade: Decimal
    unidade: str | None = None
    valor_unitario: Decimal
    valor_total: Decimal


class NotaBruta(BaseModel):
    """Resultado de um parse bem-sucedido."""

    cnpj_emitente: str | None = None
    nome_estabelecimento: str | None = None
    municipio: str | None = None
    uf: str | None = None
    emitida_em: datetime | None = None
    valor_total: Decimal | None = None
    itens: list[ItemBruto] = Field(default_factory=list)
    payload_bruto: bytes | None = None


class NFCeAdapter(ABC):
    """Consulta a nota de uma UF a partir da chave de acesso."""

    uf: str
    nome: str

    @abstractmethod
    async def buscar(self, chave: str, url_consulta: str | None = None) -> NotaBruta:
        """Consulta a nota e devolve os itens.

        ``url_consulta`` é a URL completa lida do QR Code, quando existe. Ela é o
        caminho que de fato funciona: carrega o hash assinado da nota e abre direto,
        sem passar pelo formulário de consulta por chave (que tem reCAPTCHA). Com
        apenas a chave digitada, o adapter deve levantar ``sem_url_qrcode``.

        Levanta ``ParseFalhou`` — e somente ``ParseFalhou`` — quando não conseguir.
        """
        raise NotImplementedError


def detectar_bloqueio(status_http: int, corpo: str) -> MotivoFalha | None:
    """Classifica uma resposta que não é a nota esperada.

    Distinguir captcha de layout quebrado importa: captcha significa "esse estado não
    é automatizável, não insista"; layout quebrado significa "o adapter precisa de
    manutenção".
    """
    if status_http in (403, 429):
        return MotivoFalha.bloqueio
    if status_http >= 500:
        return MotivoFalha.bloqueio

    corpo_minusculo = corpo.lower()
    if any(marcador in corpo_minusculo for marcador in _MARCADORES_CAPTCHA):
        return MotivoFalha.captcha
    return None


def numero_br(texto: str | None) -> Decimal:
    """Converte número no formato brasileiro ("1.234,56") para Decimal.

    Os portais da SEFAZ renderizam valores já formatados para leitura humana; é sempre
    daí que os números saem.
    """
    if not texto:
        return Decimal("0")

    limpo = re.sub(r"[^\d,.\-]", "", texto).strip()
    if not limpo:
        return Decimal("0")

    # Formato brasileiro: ponto é separador de milhar, vírgula é decimal.
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")

    try:
        return Decimal(limpo)
    except Exception:  # noqa: BLE001 - entrada vem de HTML, qualquer coisa pode chegar
        return Decimal("0")


def normalizar_gtin(valor: str | None) -> str | None:
    """Zero-pad até 14 dígitos, para que "7896..." e "07896..." sejam o mesmo GTIN.

    Devolve ``None`` para os placeholders que as notas usam quando o produto não tem
    código de barras cadastrado ("SEM GTIN", zeros, etc.).
    """
    if not valor:
        return None

    digitos = re.sub(r"\D", "", valor)
    if not digitos or len(digitos) > 14:
        return None
    if int(digitos) == 0:
        return None
    if len(digitos) not in (8, 12, 13, 14):
        return None

    return digitos.zfill(14)
