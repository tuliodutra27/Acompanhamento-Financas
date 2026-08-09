"""Extração da chave de acesso de dentro do HTML de uma página de nota.

Regressão de um bug real: a primeira versão apagava todos os não-dígitos da página e
procurava 44 dígitos seguidos na sopa de números resultante. Isso concatena números
vizinhos (códigos de produto, valores, IDs de componente JSF) e produz candidatos falsos
— a importação falhava com 400 mesmo tendo recebido a página certa.
"""

from __future__ import annotations

import pytest

from app.core.chave_nfce import (
    ChaveInvalida,
    calcular_digito_verificador,
    candidatos_de_chave,
    extrair_chave_de_html,
)

BASE_43 = "3326081234567800019565001000000123112345678"
CHAVE = BASE_43 + "9"


def test_acha_chave_em_corrida_de_44_digitos():
    html = f"<div>Chave de acesso: <span>{CHAVE}</span></div>"
    assert extrair_chave_de_html(html) == CHAVE


def test_acha_chave_formatada_em_blocos_de_quatro():
    """É assim que os portais exibem a chave na tela."""
    formatada = " ".join(CHAVE[i : i + 4] for i in range(0, 44, 4))
    assert extrair_chave_de_html(f"<p>{formatada}</p>") == CHAVE


def test_ignora_numeros_vizinhos_e_nao_concatena():
    """O caso que quebrava: muitos números curtos na mesma página.

    Uma página de nota tem dezenas de códigos de produto, quantidades e valores. Se o
    extrator juntar os dígitos de todos eles, forma corridas de 44 que não são chave.
    """
    html = f"""
    <table id="tabResult">
      <tr><td>(Código: 60722) Qtde.:1 UN: UN Vl. Unit.: 16,98 Total 16,98</td></tr>
      <tr><td>(Código: 35503) Qtde.:4 UN: UN Vl. Unit.: 3,69 Total 14,76</td></tr>
      <tr><td>(Código: 96625) Qtde.:2 UN: UN Vl. Unit.: 4,50 Total 9,00</td></tr>
    </table>
    <div>Numero: 409113 Serie: 606 Protocolo: 133260812345 12/08/2026 18:22:41</div>
    <div>Chave: {CHAVE}</div>
    """
    assert extrair_chave_de_html(html) == CHAVE


def test_pagina_sem_chave_falha_em_vez_de_inventar():
    html = """
    <table id="tabResult">
      <tr><td>(Código: 60722) Qtde.:1 Vl. Unit.: 16,98</td></tr>
    </table>
    <div>Numero: 409113 Serie: 606 Emissao: 12/08/2026 18:22:41</div>
    """
    with pytest.raises(ChaveInvalida):
        extrair_chave_de_html(html)


def test_candidato_com_digito_verificador_errado_e_descartado():
    """44 dígitos não bastam: é o dígito verificador que identifica a chave."""
    falsa = BASE_43 + "0"  # DV correto é 9
    html = f"<div>{falsa}</div><div>{CHAVE}</div>"
    assert extrair_chave_de_html(html) == CHAVE


def test_prefere_parametro_de_url_quando_presente():
    html = f'<a href="https://portal.sefaz/x?p={CHAVE}|2|1|1|abc">consultar</a>'
    assert extrair_chave_de_html(html) == CHAVE


def test_candidatos_nao_repete():
    html = f"{CHAVE} {CHAVE} <span>{CHAVE}</span>"
    assert candidatos_de_chave(html).count(CHAVE) == 1


def test_chave_de_outro_modelo_ainda_e_reconhecida():
    """NF-e (modelo 55) também deve ser encontrada; o filtro de modelo é de quem usa."""
    base = BASE_43[:20] + "55" + BASE_43[22:]
    chave_nfe = base + calcular_digito_verificador(base)
    assert extrair_chave_de_html(f"<p>{chave_nfe}</p>") == chave_nfe
