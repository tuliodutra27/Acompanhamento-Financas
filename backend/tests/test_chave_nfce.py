"""Testes da leitura da chave de acesso.

A chave usada aqui é **sintética, não é de uma nota real**: foi montada campo a campo e
o dígito verificador foi calculado à mão pelo módulo 11, para servir de âncora
independente do código — um teste que usasse a própria função para gerar a entrada não
provaria que o algoritmo está certo.

    cUF     33            RJ
    AAMM    2608          agosto/2026
    CNPJ    12345678000195
    mod     65            NFC-e
    série   001
    nNF     000000123
    tpEmis  1
    cNF     12345678
    cDV     9             calculado: soma ponderada 684, 684 % 11 = 2, 11 - 2 = 9
"""

from __future__ import annotations

import pytest

from app.core.chave_nfce import (
    ChaveInvalida,
    calcular_digito_verificador,
    extrair_chave_do_qrcode,
    ler_chave,
    validar_chave,
)

CHAVE_BASE_43 = "3326081234567800019565001000000123112345678"
CHAVE_VALIDA = CHAVE_BASE_43 + "9"


def test_digito_verificador_confere_com_calculo_manual():
    assert calcular_digito_verificador(CHAVE_BASE_43) == "9"


def test_chave_valida_passa():
    assert validar_chave(CHAVE_VALIDA) == CHAVE_VALIDA


def test_aceita_chave_com_separadores():
    """O usuário cola a chave do jeito que o portal mostra, em blocos de 4."""
    formatada = " ".join(CHAVE_VALIDA[i : i + 4] for i in range(0, 44, 4))
    assert validar_chave(formatada) == CHAVE_VALIDA


def test_extrai_uf_cnpj_e_mes_sem_rede():
    dados = ler_chave(CHAVE_VALIDA)
    assert dados.uf == "RJ"
    assert dados.cnpj_emitente == "12345678000195"
    assert dados.ano_mes == "2608"
    assert dados.modelo == "65"
    assert dados.numero == "000000123"


def test_digito_verificador_errado_e_rejeitado():
    """Um dígito trocado tem que ser pego aqui, antes de gastar requisição."""
    with pytest.raises(ChaveInvalida) as erro:
        validar_chave(CHAVE_BASE_43 + "0")
    assert erro.value.motivo == "digito_verificador"


@pytest.mark.parametrize(
    ("entrada", "motivo"),
    [
        ("123", "formato"),
        ("", "formato"),
        ("9" * 44, "uf_desconhecida"),
    ],
)
def test_chaves_invalidas(entrada: str, motivo: str):
    with pytest.raises(ChaveInvalida) as erro:
        validar_chave(entrada)
    assert erro.value.motivo == motivo


def test_modelo_diferente_de_nfce_rejeitado_quando_exigido():
    """Modelo 55 é NF-e (não é cupom de consumidor)."""
    base_nfe = CHAVE_BASE_43[:20] + "55" + CHAVE_BASE_43[22:]
    chave_nfe = base_nfe + calcular_digito_verificador(base_nfe)

    assert validar_chave(chave_nfe) == chave_nfe  # aceita por padrão
    with pytest.raises(ChaveInvalida) as erro:
        validar_chave(chave_nfe, exigir_nfce=True)
    assert erro.value.motivo == "modelo_nao_e_nfce"


class TestExtracaoDoQRCode:
    """O conteúdo do QR Code é padronizado nacionalmente; só a URL-base muda por UF."""

    def test_qrcode_versao_2_com_pipe(self):
        conteudo = (
            "https://www.fazenda.rj.gov.br/nfce/qrcode"
            f"?p={CHAVE_VALIDA}|2|1|1|A1B2C3D4E5F6"
        )
        assert extrair_chave_do_qrcode(conteudo) == CHAVE_VALIDA

    def test_qrcode_versao_1_com_parametro_nomeado(self):
        conteudo = (
            f"https://nfce.fazenda.sp.gov.br/consulta?chNFe={CHAVE_VALIDA}"
            "&nVersao=100&tpAmb=1&cHashQRCode=abc"
        )
        assert extrair_chave_do_qrcode(conteudo) == CHAVE_VALIDA

    def test_chave_crua_digitada(self):
        assert extrair_chave_do_qrcode(CHAVE_VALIDA) == CHAVE_VALIDA

    def test_url_de_outro_estado_funciona_igual(self):
        """Nenhum parser por UF é necessário para achar a chave — só um regex."""
        conteudo = f"http://www.sefaz.rs.gov.br/NFCE/NFCE-COM.aspx?p={CHAVE_VALIDA}|2|1|"
        assert extrair_chave_do_qrcode(conteudo) == CHAVE_VALIDA

    def test_conteudo_sem_chave_falha(self):
        with pytest.raises(ChaveInvalida):
            extrair_chave_do_qrcode("https://exemplo.com/pagina-qualquer")
