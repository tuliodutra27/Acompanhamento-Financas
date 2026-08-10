"""Testes das regras de classificação.

As descrições aqui são **inventadas no formato dos cupons** (truncadas em ~20 caracteres,
abreviadas), não copiadas de compras de ninguém. O que se testa são as decisões de
desenho: agrupar marcas, separar o que muda o preço, e a ordem entre regras que são
prefixo uma da outra.
"""

from __future__ import annotations

import pytest

from app.services.classificacao import (
    REGRAS,
    Classificacao,
    classificar,
    extrair_tamanho,
)


def classificado(descricao: str) -> Classificacao:
    achado = classificar(descricao)
    assert achado is not None, f"nenhuma regra casou com {descricao!r}"
    return achado


class TestAgrupaMarcas:
    """O pedido central: comparar o mesmo produto ao longo do tempo, ignorando marca."""

    def test_hamburguer_de_marcas_diferentes_cai_no_mesmo_produto(self):
        nomes = {
            classificado("HAMBURG BOV FRIBOI M").nome,
            classificado("HAMBURG BOV SEARA 15").nome,
            classificado("HAMBURG BOV GRA FI").nome,
        }
        assert nomes == {"Hambúrguer bovino"}

    def test_refrigerantes_do_mesmo_tamanho_agrupam(self):
        assert (
            classificado("REFRI COCA-COLA 600").nome
            == classificado("REFRIG FANTA 600ML").nome
        )

    def test_grafias_diferentes_do_mesmo_produto_agrupam(self):
        """O portal escreve o mesmo item de formas diferentes entre notas."""
        nomes = {
            classificado("REF GUARAV 300ML FR").nome,
            classificado("REF GUARAVITA 300ML").nome,
            classificado("REFR GUARAVITA 300ML").nome,
        }
        assert nomes == {"Guaraná 300ml"}

    def test_sanduiche_congelado_agrupa_com_e_sem_gramatura(self):
        """Parte das descrições traz a gramatura e parte não — não pode dividir.

        Se a regra usasse `com_tamanho`, "SAND HOT H MARCA 145" e "SAND HOT HIT MARCA"
        virariam dois produtos, e o histórico de preço de um item só ficaria partido.
        """
        nomes = {
            classificado("HOT POCKET MARCA 145").nome,
            classificado("SAND HOT H MARCA 145").nome,
            classificado("SAND HOT HIT MARCA").nome,
        }
        assert nomes == {"Sanduíche congelado"}


class TestSeparaOQueMudaOPreco:
    """Agrupar tamanho ou variedade diferente tornaria a série de preço enganosa."""

    def test_tamanhos_diferentes_sao_produtos_diferentes(self):
        um_litro = classificado("LAVA R MARCA 1L VERD").nome
        tres_litros = classificado("LAVA ROUPA MARCA 3L M").nome
        assert um_litro != tres_litros
        assert "1L" in um_litro and "3L" in tres_litros

    def test_variedades_de_feijao_nao_se_misturam(self):
        carioca = classificado("FEIJAO MARCA 1kg C").nome
        preto = classificado("FEIJAO MARCA 1kg P").nome
        assert carioca != preto

    def test_cortes_de_carne_sao_produtos_diferentes(self):
        assert classificado("C RSF BV ACEM kg PED").nome == "Acém"
        assert classificado("C RSF BV ALCAT kg CR").nome == "Alcatra"
        assert classificado("C RSF BV ALC MAM kg").nome == "Maminha"

    def test_mini_hamburguer_nao_e_hamburguer_comum(self):
        assert classificado("MINI HAMBURG MARCA 3").nome == "Mini hambúrguer"


class TestOrdemDasRegras:
    """Cada caso aqui é um par onde uma regra é prefixo da outra.

    Trocar a ordem em ``REGRAS`` quebra estes casos — é o único jeito de perceber, já
    que o efeito de uma regra na ordem errada é silencioso.
    """

    @pytest.mark.parametrize(
        ("descricao", "nome_esperado", "categoria_esperada"),
        [
            # "AGUA SANITARIA" é limpeza, não bebida
            ("AGUA SANITARIA MARCA", "Água sanitária", "Limpeza"),
            ("AGUA M MARCA 500ML", "Água mineral 500ml", "Bebidas"),
            # "BOLO ... CHOC" é bolo, não chocolate
            ("BOLO 350G CHOC GRAN", "Bolo", "Padaria"),
            ("CHOC BARRA 90G AO L", "Chocolate", "Doces e snacks"),
            # "SABONETE LIQ" antes de sabonete em barra
            ("SABONETE LIQ MARCA", "Sabonete líquido", "Higiene"),
            ("SABON MARCA 85G ROSA", "Sabonete em barra 85g", "Higiene"),
            # "LEITE COND" antes de leite
            ("LEITE COND MARCA 395", "Leite condensado", "Mercearia"),
            # "PAPEL TOALHA" antes de papel higiênico e de qualquer papel
            ("PAPEL TO MARCA CLEA", "Papel toalha", "Descartáveis"),
            ("PAPEL HIG MARCA 4UN", "Papel higiênico", "Higiene"),
            # "MACARRAO INST" antes de macarrão
            ("MACARRAO INST MARCA", "Macarrão instantâneo", "Mercearia"),
            # "TEMPERO VERDE" é hortifruti; tempero seco é mercearia
            ("TEMPERO VERDE UN", "Tempero verde", "Hortifruti"),
            ("LOURO MARCA 7G", "Tempero seco", "Mercearia"),
            # queijo ralado antes de queijo
            ("QJ LA PARMEZON 40G R", "Queijo ralado", "Frios e laticínios"),
            ("QJ MUCA MARCA kg", "Queijo muçarela", "Frios e laticínios"),
            # abóbora e abobrinha são hortaliças diferentes; a regra antiga juntava
            ("ABOBRINHA kg GRANEL", "Abobrinha", "Hortifruti"),
            ("ABOB MADU kg PROCESS", "Abóbora", "Hortifruti"),
            # azeitona antes de azeite
            ("AZEITONA VERDE kg FA", "Azeitona", "Mercearia"),
            ("AZE MARCA 500ML", "Azeite 500ml", "Mercearia"),
            # refresco em pó antes do líquido
            ("REFRES PO TANG 18G L", "Refresco em pó", "Mercearia"),
            ("REF SAB MARCA 1L", "Refresco 1L", "Bebidas"),
            # iogurte natural antes do genérico
            ("IOG NAT MARCA 160G", "Iogurte natural", "Frios e laticínios"),
            ("IOG CHAMYTO MARCA", "Iogurte", "Frios e laticínios"),
            # massa fresca não é macarrão seco
            ("FETTUCCINE MEU MENU", "Massa fresca", "Mercearia"),
            ("MAC C/SEM MARCA 1kg", "Macarrão 1kg", "Mercearia"),
        ],
    )
    def test_par_ambiguo(self, descricao, nome_esperado, categoria_esperada):
        achado = classificado(descricao)
        assert achado.nome == nome_esperado
        assert achado.categoria == categoria_esperada

    @pytest.mark.parametrize(
        ("descricao", "nome_esperado"),
        [
            # O lojista abrevia de formas que não são óbvias; cada uma destas custou
            # uma nota inteira cair na fila de revisão.
            ("IOG CHAMYTO MARCA", "Iogurte"),
            ("PA HI F DU MARCA", "Papel higiênico"),
            ("PAP TOA MARCA 100", "Papel toalha"),
            ("DESO CREME MARCA 5", "Desodorante"),
            ("FAR TRIG MARCA 1kg", "Farinha 1kg"),
            ("ESCOVA DEN MARCA", "Escova de dente"),
            ("ABS GEL INT 8 N C/A", "Absorvente"),
            ("GEL DENT RH MARCA", "Creme dental"),
            ("PX POLACA B ALASCA k", "Polaca ou merluza"),
            ("PET TILAP MARCA 6", "Tilápia"),
            ("PT PERU MARCA kg DEF", "Peito de peru"),
            ("SALG MARICOTA 420G C", "Salgadinho de festa"),
            ("PAST SANIT MARCA L5", "Pastilha sanitária"),
            ("LIMP MULT CREMOSO CI", "Limpador cremoso"),
            ("CAPS CAPPUC D G 175G", "Cápsulas de café"),
        ],
    )
    def test_abreviacoes_do_cupom(self, descricao, nome_esperado):
        assert classificado(descricao).nome == nome_esperado

    @pytest.mark.parametrize(
        ("descricao", "nome_esperado", "categoria_esperada"),
        [
            # Cada um destes foi encontrado pelo diagnóstico de grupos suspeitos, depois
            # de já estar classificado errado no banco — misturando produtos cujo preço
            # não é comparável.
            ("EXTRATO TOMATE MARCA", "Extrato de tomate", "Mercearia"),
            ("TOMATE kg GRANEL", "Tomate", "Hortifruti"),
            ("BATATA BEM BRASIL 1,", "Batata congelada", "Congelados"),
            ("BATATA FROSTO 1kg CO", "Batata congelada", "Congelados"),
            ("BATATA INGLESA kg GR", "Batata inglesa", "Hortifruti"),
            ("ENERG GUARAVITON 300", "Guaraná 300ml", "Bebidas"),
            ("ENERG MONSTER 473ML", "Energético", "Bebidas"),
            ("BEBIDA LAC ENERGIA", "Bebida láctea", "Frios e laticínios"),
            ("PET TILAP MARCA 6", "Tilápia", "Carnes"),
            ("PX POLACA B ALASCA k", "Polaca ou merluza", "Carnes"),
            ("BISC RECH MARCA 16", "Biscoito recheado", "Mercearia"),
            ("BISC MAIZ MARCA", "Biscoito", "Mercearia"),
        ],
    )
    def test_grupos_que_nao_devem_se_misturar(
        self, descricao, nome_esperado, categoria_esperada
    ):
        achado = classificado(descricao)
        assert achado.nome == nome_esperado
        assert achado.categoria == categoria_esperada


class TestTamanho:
    @pytest.mark.parametrize(
        ("descricao", "esperado"),
        [
            ("ARROZ MARCA 5kg TIPO", "5kg"),
            ("AZEITE MARCA 500ML", "500ml"),
            ("LAVA ROUPA MARCA 3L", "3L"),
            ("SABON MARCA 85G", "85g"),
            ("CHOC MARCA 41,5G P", "41.5g"),
            ("MISTURA MARCA LEGUME", None),
        ],
    )
    def test_extrair_tamanho(self, descricao, esperado):
        assert extrair_tamanho(descricao) == esperado

    def test_produto_sem_medida_nao_ganha_sufixo_inventado(self):
        assert classificado("ARROZ MARCA TIPO 1").nome == "Arroz"

    @pytest.mark.parametrize(
        "descricao",
        [
            "ARROZ MARCA TIPO 1",  # classificação do grão, não 1 kg
            "ARROZ MARCA TP 2",
            "REFRI MARCA CX 6",  # contagem de caixa
            "AGUA M MARCA UN 12",  # contagem de unidades
        ],
    )
    def test_numero_que_nao_e_medida_nao_vira_tamanho(self, descricao):
        """Ler "tipo 1" como "1kg" criaria um produto fantasma que rouba compras do real."""
        nome = classificado(descricao).nome
        assert not any(c.isdigit() for c in nome), f"ganhou tamanho indevido: {nome}"

    @pytest.mark.parametrize(
        ("descricao", "esperado"),
        [
            # O portal corta em ~20 caracteres e o corte cai no meio da medida.
            ("REFRI COCA-COLA 600", "Refrigerante 600ml"),
            ("VINAGRE MARCA 750M", "Vinagre 750ml"),
            ("SABON MARCA 85", "Sabonete em barra 85g"),
        ],
    )
    def test_unidade_cortada_pelo_portal_e_reconstruida(self, descricao, esperado):
        """Sem isto, `...600` e `...600ML` seriam dois produtos e a série se partiria."""
        assert classificado(descricao).nome == esperado


class TestNaoAdivinha:
    def test_descricao_desconhecida_devolve_none(self):
        """Melhor pendente do que num produto errado: vínculo errado suja a série."""
        assert classificar("XPTO ZZZ 999 QQQ") is None

    @pytest.mark.parametrize("entrada", ["", "   ", None])
    def test_entrada_vazia(self, entrada):
        assert classificar(entrada) is None


def test_toda_regra_tem_padrao_valido():
    """Uma regra com regex inválida derrubaria a importação de notas."""
    import re

    for regra in REGRAS:
        re.compile(regra.padrao)
        assert regra.nome.strip(), f"regra sem nome: {regra.padrao}"
        assert regra.categoria.strip(), f"regra sem categoria: {regra.padrao}"


def test_acentos_e_caixa_nao_atrapalham():
    assert classificado("açúcar cristal marca").nome.startswith("Açúcar")
