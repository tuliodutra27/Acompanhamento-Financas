"""Resolve qual adapter atende cada UF.

Como o ``PortalPadraoAdapter`` funciona a partir da URL do próprio QR Code (que é
padronizada nacionalmente), ele é registrado como padrão para **todas** as UFs. Não é
otimismo: é que o custo de tentar é uma requisição HTTP, e a falha já tem um caminho
definido (preenchimento manual, com o motivo registrado). Assumir de antemão que um
estado não funciona seria descartar dado que talvez viesse de graça.

Quando algum estado precisar de tratamento próprio (layout diferente, handshake de
cookie/CSRF como o de Preço da Hora BA), basta escrever a classe e registrá-la em
``ADAPTERS_ESPECIFICOS`` — nada mais no app muda.
"""

from __future__ import annotations

from app.adapters.base import NFCeAdapter
from app.adapters.portal_padrao import PortalPadraoAdapter
from app.core.chave_nfce import UF_POR_CODIGO_IBGE

# UF -> classe de adapter, para estados que não seguem o layout de referência.
ADAPTERS_ESPECIFICOS: dict[str, type[NFCeAdapter]] = {}

UFS_CONHECIDAS: frozenset[str] = frozenset(UF_POR_CODIGO_IBGE.values())


def adapter_para(uf: str) -> NFCeAdapter | None:
    """Adapter que atende a UF, ou ``None`` se a UF não existir."""
    uf = (uf or "").upper()
    if uf not in UFS_CONHECIDAS:
        return None

    if especifico := ADAPTERS_ESPECIFICOS.get(uf):
        return especifico()
    return PortalPadraoAdapter(uf=uf)


def ufs_suportadas() -> list[dict[str, str]]:
    """Quais UFs têm adapter, e por qual estratégia — alimenta GET /ufs-suportadas."""
    return [
        {
            "uf": uf,
            "adapter": (
                ADAPTERS_ESPECIFICOS[uf].nome
                if uf in ADAPTERS_ESPECIFICOS
                else PortalPadraoAdapter.nome
            ),
            # Deixa explícito na API o que o usuário precisa saber: escanear o QR Code
            # é o que habilita o preenchimento automático.
            "requer_qrcode": True,
        }
        for uf in sorted(UFS_CONHECIDAS)
    ]
