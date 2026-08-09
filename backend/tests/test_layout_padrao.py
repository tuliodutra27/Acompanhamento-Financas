"""Testes do parser do layout de referência.

O parser recebe HTML já baixado, então roda sem rede e sem depender do portal estar de
pé — a página de exemplo abaixo reproduz a estrutura da implementação de referência
(ENCAT/SVRS) que a maioria das UFs usa.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.adapters.base import ParseFalhou, normalizar_gtin, numero_br
from app.adapters.layout_padrao import parsear_pagina
from app.models.enums import MotivoFalha

PAGINA_EXEMPLO = """
<html><body>
<div id="conteudo">
  <div class="txtCenter">
    <div id="u20" class="txtTopo">SUPERMERCADO EXEMPLO LTDA</div>
    <div class="text">CNPJ: 12.345.678/0001-95</div>
    <div class="text">Rua das Flores, 100, Centro, Sao Joao da Barra, RJ</div>
  </div>
  <table id="tabResult">
    <tr id="Item + 1">
      <td class="txtTit">
        <span class="txtTit">ARROZ BRANCO TIPO 1 5KG</span>
        <span class="RCod">(Codigo: 7896006711056)</span>
        <span class="Rqtd">Qtde.:2</span>
        <span class="RUN">UN: UN</span>
        <span class="RvlUnit">Vl. Unit.:&nbsp;&nbsp;24,90</span>
      </td>
      <td class="txtTit noWrap"><span class="valor">49,80</span></td>
    </tr>
    <tr id="Item + 2">
      <td class="txtTit">
        <span class="txtTit">FEIJAO CARIOCA 1KG</span>
        <span class="RCod">(Codigo: 123)</span>
        <span class="Rqtd">Qtde.:1</span>
        <span class="RUN">UN: UN</span>
        <span class="RvlUnit">Vl. Unit.:&nbsp;&nbsp;8,49</span>
      </td>
      <td class="txtTit noWrap"><span class="valor">8,49</span></td>
    </tr>
    <tr id="Item + 3">
      <td class="txtTit">
        <span class="txtTit">PICANHA BOVINA KG</span>
        <span class="RCod">(Codigo: 000002)</span>
        <span class="Rqtd">Qtde.:1,235</span>
        <span class="RUN">UN: KG</span>
        <span class="RvlUnit">Vl. Unit.:&nbsp;&nbsp;79,90</span>
      </td>
      <td class="txtTit noWrap"><span class="valor">98,68</span></td>
    </tr>
  </table>
  <div id="totalNota">
    <div id="linhaTotal">Valor a pagar R$:
      <span class="totalNumb txtMax">156,97</span>
    </div>
  </div>
  <div id="infos">
    <div>Numero: 123 Serie: 1 Emissao: 05/08/2026 19:42:11</div>
  </div>
</div>
</body></html>
"""


class TestParsearPagina:
    def test_le_todos_os_itens(self):
        nota = parsear_pagina(PAGINA_EXEMPLO)
        assert len(nota.itens) == 3
        assert [item.descricao for item in nota.itens] == [
            "ARROZ BRANCO TIPO 1 5KG",
            "FEIJAO CARIOCA 1KG",
            "PICANHA BOVINA KG",
        ]

    def test_le_dados_do_estabelecimento(self):
        nota = parsear_pagina(PAGINA_EXEMPLO)
        assert nota.nome_estabelecimento == "SUPERMERCADO EXEMPLO LTDA"
        assert nota.cnpj_emitente == "12345678000195"

    def test_le_data_de_emissao(self):
        nota = parsear_pagina(PAGINA_EXEMPLO)
        assert nota.emitida_em is not None
        assert nota.emitida_em.strftime("%d/%m/%Y %H:%M") == "05/08/2026 19:42"

    def test_le_valor_total_a_pagar(self):
        nota = parsear_pagina(PAGINA_EXEMPLO)
        assert nota.valor_total == Decimal("156.97")

    def test_valores_e_quantidade_fracionaria(self):
        """Produto por peso: quantidade com vírgula e preço por kg."""
        picanha = parsear_pagina(PAGINA_EXEMPLO).itens[2]
        assert picanha.quantidade == Decimal("1.235")
        assert picanha.unidade == "KG"
        assert picanha.valor_unitario == Decimal("79.90")
        assert picanha.valor_total == Decimal("98.68")

    def test_codigo_interno_curto_nao_vira_gtin(self):
        """O portal mostra o cProd do lojista, que só às vezes é o código de barras.

        "123" e "000002" são códigos internos — tratá-los como GTIN faria dois produtos
        diferentes de lojas diferentes colidirem no mesmo alias.
        """
        itens = parsear_pagina(PAGINA_EXEMPLO).itens
        assert itens[0].gtin == "07896006711056"  # EAN-13 real, com zero-pad para 14
        assert itens[1].gtin is None
        assert itens[2].gtin is None

    def test_pagina_sem_tabela_de_itens_falha_como_layout_mudou(self):
        with pytest.raises(ParseFalhou) as erro:
            parsear_pagina("<html><body><p>Nada por aqui</p></body></html>")
        assert erro.value.motivo == MotivoFalha.layout_mudou


class TestHelpers:
    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [
            ("1.234,56", Decimal("1234.56")),
            ("24,90", Decimal("24.90")),
            ("R$ 8,49", Decimal("8.49")),
            ("", Decimal("0")),
            (None, Decimal("0")),
        ],
    )
    def test_numero_br(self, entrada, esperado):
        assert numero_br(entrada) == esperado

    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [
            ("7896006711056", "07896006711056"),  # EAN-13 -> 14 com zero-pad
            ("78960067", "00000078960067"),  # EAN-8
            ("00000000000000", None),  # placeholder de "sem GTIN"
            ("123", None),  # código interno, não é comprimento de GTIN
            ("SEM GTIN", None),
            (None, None),
        ],
    )
    def test_normalizar_gtin(self, entrada, esperado):
        assert normalizar_gtin(entrada) == esperado
