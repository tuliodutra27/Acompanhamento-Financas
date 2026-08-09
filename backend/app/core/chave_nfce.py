"""Leitura da chave de acesso de 44 dígitos da NFC-e/NF-e.

Tudo aqui é offline: a própria chave carrega UF, CNPJ do emitente e mês de emissão.
Isso é o que permite registrar a nota (e mostrar "UF detectada: RJ") mesmo quando o
parse automático falha e o usuário vai preencher os itens à mão.

Layout da chave (posições 1-indexadas, como na documentação da SEFAZ):

    01-02  cUF     código IBGE da UF emissora
    03-06  AAMM    ano (2 dígitos) e mês de emissão
    07-20  CNPJ    emitente
    21-22  mod     modelo do documento (55 = NF-e, 65 = NFC-e)
    23-25  série
    26-34  nNF     número da nota
    35     tpEmis  tipo de emissão
    36-43  cNF     código numérico
    44     cDV     dígito verificador (módulo 11)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MODELO_NFCE = "65"
MODELO_NFE = "55"

# Código IBGE da UF (2 primeiros dígitos da chave) -> sigla.
UF_POR_CODIGO_IBGE: dict[str, str] = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA",
    "31": "MG", "32": "ES", "33": "RJ", "35": "SP",
    "41": "PR", "42": "SC", "43": "RS",
    "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}

_SO_DIGITOS = re.compile(r"\D")
_SEQUENCIA_44_DIGITOS = re.compile(r"\d{44}")


class ChaveInvalida(ValueError):
    """A chave não passou na validação de formato, modelo ou dígito verificador."""

    def __init__(self, motivo: str) -> None:
        self.motivo = motivo
        super().__init__(motivo)


@dataclass(frozen=True)
class DadosChave:
    """O que a chave revela sem nenhuma consulta de rede."""

    chave: str
    uf: str
    codigo_ibge_uf: str
    cnpj_emitente: str
    ano_mes: str  # AAMM, como vem na chave
    modelo: str
    serie: str
    numero: str
    tipo_emissao: str


def limpar(entrada: str) -> str:
    """Remove tudo que não é dígito (espaços, pontos, o que o usuário colar)."""
    return _SO_DIGITOS.sub("", entrada or "")


def calcular_digito_verificador(chave_sem_dv: str) -> str:
    """Dígito verificador da chave: módulo 11 com pesos 2..9 da direita para a esquerda."""
    if len(chave_sem_dv) != 43 or not chave_sem_dv.isdigit():
        raise ChaveInvalida("formato")

    soma = 0
    peso = 2
    for digito in reversed(chave_sem_dv):
        soma += int(digito) * peso
        peso = 2 if peso == 9 else peso + 1

    resto = soma % 11
    return "0" if resto in (0, 1) else str(11 - resto)


def validar_chave(entrada: str, *, exigir_nfce: bool = False) -> str:
    """Valida a chave e devolve os 44 dígitos limpos.

    Levanta ``ChaveInvalida`` com um ``motivo`` estável, para a API traduzir em
    mensagem de erro: ``formato``, ``digito_verificador``, ``uf_desconhecida``,
    ``modelo_nao_suportado``, ``modelo_nao_e_nfce``.
    """
    chave = limpar(entrada)

    if len(chave) != 44:
        raise ChaveInvalida("formato")

    if chave[0:2] not in UF_POR_CODIGO_IBGE:
        raise ChaveInvalida("uf_desconhecida")

    modelo = chave[20:22]
    if modelo not in (MODELO_NFCE, MODELO_NFE):
        raise ChaveInvalida("modelo_nao_suportado")
    if exigir_nfce and modelo != MODELO_NFCE:
        raise ChaveInvalida("modelo_nao_e_nfce")

    if chave[43] != calcular_digito_verificador(chave[:43]):
        raise ChaveInvalida("digito_verificador")

    return chave


def ler_chave(entrada: str, *, exigir_nfce: bool = False) -> DadosChave:
    """Valida e decompõe a chave nos dados que ela carrega."""
    chave = validar_chave(entrada, exigir_nfce=exigir_nfce)
    codigo_ibge = chave[0:2]

    return DadosChave(
        chave=chave,
        uf=UF_POR_CODIGO_IBGE[codigo_ibge],
        codigo_ibge_uf=codigo_ibge,
        cnpj_emitente=chave[6:20],
        ano_mes=chave[2:6],
        modelo=chave[20:22],
        serie=chave[22:25],
        numero=chave[25:34],
        tipo_emissao=chave[34],
    )


def extrair_chave_do_qrcode(conteudo: str) -> str:
    """Extrai a chave de acesso do conteúdo lido de um QR Code de NFC-e.

    O QR Code da NFC-e é padronizado nacionalmente: só a URL-base antes dos parâmetros
    muda por UF. As três formas que aparecem na prática:

    1. QR Code 2.0 — ``https://<portal-da-uf>/...?p=<chave>|<versao>|<ambiente>|<hash>``
    2. QR Code 1.0 — ``https://<portal-da-uf>/...?chNFe=<chave>&nVersao=...``
    3. A chave crua, quando o usuário digita/cola em vez de escanear.

    Como fallback, aceita qualquer sequência de 44 dígitos encontrada no texto — alguns
    portais montam a URL de forma ligeiramente diferente do previsto nas notas técnicas.
    """
    texto = (conteudo or "").strip()
    if not texto:
        raise ChaveInvalida("formato")

    # 1. QR Code 2.0: parâmetro `p`, campos separados por "|", chave é o primeiro.
    if match := re.search(r"[?&]p=([^&#]+)", texto, re.IGNORECASE):
        candidato = limpar(match.group(1).split("|")[0])
        if len(candidato) == 44:
            return validar_chave(candidato)

    # 2. QR Code 1.0: parâmetro nomeado `chNFe`.
    if match := re.search(r"chNFe=(\d{44})", texto, re.IGNORECASE):
        return validar_chave(match.group(1))

    # 3. Chave crua (aceitando separadores que o usuário possa ter colado).
    somente_digitos = limpar(texto)
    if len(somente_digitos) == 44:
        return validar_chave(somente_digitos)

    # 4. Último recurso: qualquer corrida de 44 dígitos dentro do texto.
    if match := _SEQUENCIA_44_DIGITOS.search(somente_digitos or texto):
        return validar_chave(match.group(0))

    raise ChaveInvalida("formato")
