"""Classificação de itens em produto e categoria por padrões de texto.

O portal da SEFAZ entrega a descrição **truncada em ~20 caracteres e abreviada pelo
lojista** — `C MOID RSF BV ACEM k`, `HAMBURG BOV FRIBOI M`, `S +C DOVE 350+150ML`. Não
há campo de categoria, nem nome canônico: só esse texto.

Estas regras traduzem esse texto em (produto, categoria). Duas decisões de desenho
sustentam o resto do arquivo:

**1. Agrupar marcas, separar o que muda o preço.** O objetivo do app é comparar o preço
do mesmo produto ao longo do tempo, então `HAMBURG BOV FRIBOI`, `HAMBURG BOV SEARA` e
`HAMBURG BOV GRA FI` devem cair no mesmo produto. Mas tamanho de embalagem, variedade e
corte **não** podem ser agrupados: juntar lava-roupas de 1 L com o de 3 L faria o gráfico
mostrar "alta de 125%" quando na verdade se comprou o galão maior. Daí a flag
``com_tamanho``, que anexa ao nome o tamanho encontrado na descrição.

**2. A ordem das regras é significativa.** A primeira que casar vence, e várias regras
são prefixo de outras. `AGUA SANITARIA` tem de vir antes de `AGUA`, `SABONETE LIQ` antes
de `SABON`, `MINI HAMBURG` antes de `HAMBURG`, `BOLO … CHOC` antes de `CHOC`. Trocar a
ordem quebra a classificação de forma silenciosa — os testes em
``tests/test_classificacao.py`` existem para travar exatamente esses pares.

As regras foram derivadas de cupons reais de supermercado brasileiro, mas expressam
abreviações do domínio (`FGO` = frango, `QJ` = queijo, `MOID` = moída), não a lista de
compras de ninguém.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# ------------------------------------------------------------------ categorias

CARNES = "Carnes"
CONGELADOS = "Congelados"
HORTIFRUTI = "Hortifruti"
PADARIA = "Padaria"
LATICINIOS = "Frios e laticínios"
MERCEARIA = "Mercearia"
DOCES = "Doces e snacks"
BEBIDAS = "Bebidas"
ALCOOLICAS = "Bebidas alcoólicas"
LIMPEZA = "Limpeza"
HIGIENE = "Higiene"
DESCARTAVEIS = "Descartáveis"
PET = "Pet"
OUTROS = "Outros"

# Tamanho de embalagem: primeiro número seguido de unidade de medida.
_TAMANHO = re.compile(r"(\d+(?:[.,]\d+)?)\s*(KG|G|ML|LT|L)\b")

# Número no fim da descrição, com a unidade ausente ou cortada pela metade. O portal
# trunca em ~20 caracteres e o corte cai no meio da medida com frequência: `...600` e
# `...750M` são "600ML" e "750ML" mutilados. Só é consultado quando a regra declara
# `unidade_provavel`, então os 0-2 caracteres soltos não podem virar unidade errada.
_TAMANHO_SEM_UNIDADE = re.compile(r"(?<!\d)(\d{1,4}(?:[.,]\d+)?)\s*[A-Z]{0,2}\s*$")

# Número no fim que NÃO é medida de embalagem. "ARROZ TIPO 1" é classificação do grão,
# não um pacote de 1 kg — e ler errado criaria um produto fantasma ("Arroz 1kg") que
# rouba compras do produto verdadeiro. "ALFACE 1UN" e "CX 6" são contagem.
_NAO_E_MEDIDA = re.compile(
    r"\b(TIPO|TP|N|NO|NUM|UN|UNID|CX|PC|PCT|FD|C\/)\s*\d{1,4}\s*[A-Z]{0,2}\s*$"
)

_SUFIXO_POR_UNIDADE = {"KG": "kg", "G": "g", "ML": "ml", "L": "L", "LT": "L"}

# Venda por peso solto. O "KG" precisa vir **sem número antes**: "BOMBOM DA CASA kg" é
# granel, enquanto "ARROZ 5kg" é um pacote de 5 kg — a diferença é justamente o número.
_E_GRANEL = re.compile(r"\bGRANEL\b|(?<![\d,.])\s*\bKG\b")


@dataclass(frozen=True)
class Regra:
    padrao: str
    nome: str
    categoria: str
    # Anexa o tamanho da embalagem ao nome. Usar quando o preço unitário só é
    # comparável dentro do mesmo tamanho (bebidas, produtos de limpeza, grãos).
    com_tamanho: bool = False
    # Unidade a assumir quando a descrição traz o número **sem** a unidade, porque o
    # portal cortou o texto: `REFRI COCA-COLA 600` (cortou o "ML") descreve o mesmo
    # produto que `REFRIG FANTA 600ML`, e sem isso viravam dois produtos, partindo a
    # série de preço em duas.
    #
    # É declarado por regra, e não inferido do número, porque a leitura correta depende
    # do produto: um "5" solto é 5 kg em arroz e 5 ml em nada — enquanto "600" é 600 ml
    # num refrigerante e não 600 kg.
    unidade_provavel: str | None = None
    # Acrescenta " a granel" ao nome quando a descrição indica venda por peso solto.
    # Usar nos produtos que a loja vende das duas formas — tempero, bombom, azeitona,
    # pizza: o preço por quilo do granel e o da embalagem não são a mesma série, e
    # juntá-los gerava "quedas de 90%" que eram só troca de formato.
    separar_granel: bool = False


# A ordem importa: a primeira regra que casar vence. Regras mais específicas primeiro.
REGRAS: tuple[Regra, ...] = (
    # ================================ tomate processado (antes do hortifruti)
    # `EXTRATO TOMATE` era classificado como tomate fresco: o guarda na regra do
    # hortifruti é um lookahead, e só olha o que vem **depois** de "TOMATE" — aqui a
    # palavra que desqualifica vem antes. Resolver por ordem é mais simples e mais
    # legível que um regex com lookbehind.
    Regra(r"EXTRATO.*TOMATE|\bEXT\s*TOM", "Extrato de tomate", MERCEARIA, True, "g"),
    Regra(r"MOL\s*TOM|MOLHO.*TOMATE", "Molho de tomate", MERCEARIA),
    Regra(r"TOMATE\s*SECO", "Tomate seco", MERCEARIA),
    # ================================================================= carnes
    Regra(r"\bMOID", "Carne moída", CARNES, separar_granel=True),
    Regra(r"\bALCAT", "Alcatra", CARNES),
    Regra(r"\bMAMINHA|\bMAM\b", "Maminha", CARNES),
    Regra(r"\bPICANHA", "Picanha", CARNES),
    Regra(r"\bCOXAO", "Coxão", CARNES),
    Regra(r"\bPATINHO", "Patinho", CARNES),
    Regra(r"\bPALETA", "Paleta", CARNES),
    Regra(r"\bANCHO|\bBIFE\s*ANCHO", "Ancho", CARNES),
    Regra(r"\bSALSICHAO|\bSALSICHA", "Salsicha", CARNES, separar_granel=True),
    Regra(r"\bCONTRA\s*FILE|\bCONTRAFILE", "Contrafilé", CARNES),
    Regra(r"\bCOSTELA", "Costela", CARNES),
    Regra(r"\bACEM\b", "Acém", CARNES),
    # Cortes de frango antes de qualquer regra genérica de frango.
    Regra(r"PEITO.*(FGO|FRANGO)|(FGO|FRANGO).*PEITO", "Peito de frango", CARNES),
    Regra(
        r"FILE.*(FGO|FRANGO)|(FGO|FRANGO).*FILE|^FILE\s*DE\s*PEITO",
        "Filé de frango",
        CARNES,
    ),
    Regra(r"COXA.*(FGO|FRANGO)|SOBRECOXA", "Coxa de frango", CARNES),
    Regra(r"\bASA.*(FGO|FRANGO)", "Asa de frango", CARNES),
    Regra(r"\bLINGUI", "Linguiça", CARNES),
    Regra(r"\bBACON", "Bacon", CARNES),
    # Separado por espécie: filé embalado (UN) e peixe a granel (KG) não compartilham
    # escala de preço, e "Peixe" juntando tudo gerava faixa de 28 a 40 sem significado.
    Regra(r"\bTILAP", "Tilápia", CARNES),
    Regra(r"\bPOLACA|\bMERLUZA|\bPX\b", "Polaca ou merluza", CARNES),
    Regra(r"\bSALMAO", "Salmão", CARNES),
    Regra(r"\bPEIXE|\bSARDINHA\s*FRESC", "Peixe", CARNES),
    # ============================================================= congelados
    # Pão de hambúrguer antes de QUALQUER regra de hambúrguer: "PAO MQP VENDA kg
    # HAMBURGUER" é pão de padaria e estava entrando na série do congelado.
    Regra(r"^PAO.*HAMBURG|^PAO.*BISNAG", "Pão de hambúrguer", PADARIA),
    # "MINI HAMBURG" antes de "HAMBURG", senão o mini vira hambúrguer comum e a
    # série de preço mistura produtos de tamanhos bem diferentes.
    Regra(r"MINI\s*HAMBURG", "Mini hambúrguer", CONGELADOS),
    Regra(r"HAMBURG.*(FGO|FRANGO)", "Hambúrguer de frango", CONGELADOS),
    Regra(r"HAMBURG", "Hambúrguer bovino", CONGELADOS),
    Regra(r"\bNUGGET", "Nuggets", CONGELADOS),
    Regra(r"\bEMPANADO|\bSTEAK\s*FGO", "Empanado de frango", CONGELADOS),
    # Sanduíche congelado recheado, vendido como porção individual. Sem `com_tamanho`
    # de propósito: parte das descrições traz o "145" e parte não (o portal corta), e
    # com sufixo o mesmo produto se dividiria em "Sanduíche congelado 145g" e
    # "Sanduíche congelado". Porção individual não varia o bastante para justificar.
    Regra(
        r"HOT\s*POCKET|\bSAND\s*HOT|SANDUICHE.*(HOT|CONG)",
        "Sanduíche congelado",
        CONGELADOS,
    ),
    Regra(r"\bLASANHA", "Lasanha congelada", CONGELADOS),
    Regra(r"PAO\s*DE\s*QUEIJO", "Pão de queijo", CONGELADOS),
    Regra(r"\bPIZZA", "Pizza congelada", CONGELADOS, separar_granel=True),
    Regra(r"\bPOLPA", "Polpa de fruta", CONGELADOS),
    Regra(r"BROCOLIS.*(DAUCY|CONG)", "Brócolis congelado", CONGELADOS),
    Regra(
        r"(MISTURA|SELETA|JARDINEIRA|SALADA).*(DAUCY|LEGUME|VEGETAL)|LEGUMES?.*CONG",
        "Legumes congelados",
        CONGELADOS,
    ),
    # As marcas aparecem sem a palavra "congelada"/"frita" na descrição, e sem isto
    # elas caíam na batata fresca — R$ 24 a unidade contra R$ 4 o quilo.
    Regra(
        r"BATATA.*(FRITA|CONG|PALITO|NOISETTE|ONDULADA|BEM\s*BRASIL|FROSTO|MCCAIN)",
        "Batata congelada",
        CONGELADOS,
    ),
    Regra(r"\bSORVETE|\bPICOLE", "Sorvete", DOCES),
    # ============================================================= hortifruti
    #
    # **Todas as regras daqui estão ancoradas em `^`**, e isso não é estilo: é a
    # correção de um erro que só apareceu quando notas com descrição **completa**
    # (não truncada em 20 caracteres) entraram no banco. Nome de fruta em descrição
    # longa quase sempre é **sabor**, não o produto:
    #
    #     AGUA SABORIZADA CRYSTAL 510ML LIMAO   -> era classificado como Limão
    #     GELATINA APTI 20G MORANGO             -> era classificado como Morango
    #     DETERGENTE LIMPOL 500ML MACA          -> era classificado como Maçã
    #     BOMBOM DA CASA kg MORANGO             -> era classificado como Morango
    #
    # O cupom nomeia o produto primeiro ("LIMAO kg GRANEL", "MORANGO SELECIONADO"),
    # então exigir a fruta no início separa o produto do sabor sem depender da ordem
    # das regras nem de uma lista de exceções que nunca estaria completa.
    Regra(
        r"^TEMPERO\s*VERDE|^CHEIRO\s*VERDE",
        "Tempero verde",
        HORTIFRUTI,
        separar_granel=True,
    ),
    Regra(r"^ALFACE", "Alface", HORTIFRUTI),
    Regra(r"^BANANA", "Banana", HORTIFRUTI),
    # "BATATA DOCE" antes da inglesa: a regra genérica capturava a doce.
    Regra(r"^BATATA\s*DOCE", "Batata doce", HORTIFRUTI),
    # Exige "INGLESA"/"kg": o genérico capturava batata congelada de marca, que vem
    # em pacote e custa por unidade.
    Regra(
        r"^BATATA\s*(INGLESA|ASTERIX|LAVADA)|^BATATA.*\bKG\b",
        "Batata inglesa",
        HORTIFRUTI,
        separar_granel=True,
    ),
    Regra(r"^CEBOLA", "Cebola", HORTIFRUTI),
    Regra(r"^TOMATE\b", "Tomate", HORTIFRUTI),
    Regra(r"^LARANJA", "Laranja", HORTIFRUTI),
    Regra(r"^MACA\b", "Maçã", HORTIFRUTI),
    Regra(r"^MANGA\b", "Manga", HORTIFRUTI),
    Regra(r"^MORANGO", "Morango", HORTIFRUTI),
    Regra(r"^KIWI", "Kiwi", HORTIFRUTI),
    Regra(r"^TANGERINA|^PONKAN|^MEXERICA", "Tangerina", HORTIFRUTI),
    Regra(r"^LIMAO", "Limão", HORTIFRUTI),
    Regra(r"^MAMAO", "Mamão", HORTIFRUTI),
    Regra(r"^ABACAXI", "Abacaxi", HORTIFRUTI),
    Regra(r"^MELANCIA", "Melancia", HORTIFRUTI),
    Regra(r"^MELAO", "Melão", HORTIFRUTI),
    Regra(r"^UVA\b", "Uva", HORTIFRUTI),
    Regra(r"^PERA\b", "Pera", HORTIFRUTI),
    Regra(r"^CENOURA", "Cenoura", HORTIFRUTI),
    Regra(r"^COENTRO", "Coentro", HORTIFRUTI),
    Regra(r"^SALSA\b|^SALSINHA", "Salsinha", HORTIFRUTI),
    Regra(r"^COUVE", "Couve", HORTIFRUTI),
    Regra(r"^REPOLHO", "Repolho", HORTIFRUTI),
    Regra(r"^PIMENTAO", "Pimentão", HORTIFRUTI),
    # Abóbora e abobrinha são hortaliças diferentes, com preços diferentes — a regra
    # antiga juntava as duas sob "Abobrinha". "ABOB" truncado é quase sempre abóbora.
    Regra(r"^ABOBRINHA", "Abobrinha", HORTIFRUTI),
    Regra(r"^ABOBORA|^ABOB\b|^MORANGA", "Abóbora", HORTIFRUTI),
    Regra(r"^CHUCHU", "Chuchu", HORTIFRUTI),
    Regra(r"^BETERRABA", "Beterraba", HORTIFRUTI),
    Regra(r"^PEPINO", "Pepino", HORTIFRUTI),
    Regra(r"^MANDIOCA|^AIPIM|^MACAXEIRA", "Mandioca", HORTIFRUTI, separar_granel=True),
    Regra(r"^INHAME", "Inhame", HORTIFRUTI),
    Regra(r"^ALHO\b", "Alho", HORTIFRUTI),
    Regra(r"^GENGIBRE", "Gengibre", HORTIFRUTI),
    Regra(r"^QUIABO", "Quiabo", HORTIFRUTI),
    Regra(r"^TOMATINHO|^TOMATE\s*CEREJA", "Tomate cereja", HORTIFRUTI),
    Regra(r"^BROCOLIS", "Brócolis", HORTIFRUTI),
    Regra(r"^OVO\b|^OVOS\b", "Ovos", HORTIFRUTI),
    # ================================================================ padaria
    # Ancoradas em `^` pelo mesmo motivo do hortifruti: "SALGADINHO ... PAO DE ALHO"
    # é salgadinho de sabor pão de alho, não pão.
    Regra(r"^BOLO\b", "Bolo", PADARIA),
    Regra(r"^BRIOCHE", "Brioche", PADARIA),
    # Pão de hambúrguer antes de qualquer regra de hambúrguer, senão "PAO ... HAMBURGUER"
    # entrava na série do hambúrguer bovino congelado.
    Regra(r"^PAO.*HAMBURG|^PAO.*BISNAG", "Pão de hambúrguer", PADARIA),
    Regra(r"^PAO\s*(BAGUETE|FRANCES)|^BAGUETE", "Pão baguete", PADARIA),
    Regra(r"^PAO\s*(FOR|DE\s*FORMA)", "Pão de forma", PADARIA),
    Regra(r"^PAO.*(GRANEL|MQP)|^PAO.*(?<![\d,.])\s*KG\b", "Pão a granel", PADARIA),
    # Farinha de rosca antes de rosca: é ingrediente, não pão doce.
    Regra(r"FARINHA\s*DE\s*ROSCA|^FAR.*ROSCA", "Farinha de rosca", MERCEARIA),
    Regra(r"^ROSQUINHA", "Rosquinha", MERCEARIA),
    Regra(r"^ROSCA\b", "Rosca", PADARIA),
    Regra(r"^SONHO\b", "Sonho", PADARIA),
    Regra(r"^CROISSANT", "Croissant", PADARIA),
    Regra(r"^TORTA\b", "Torta", PADARIA),
    Regra(r"^EMPADA|^EMPADINHA", "Empada", PADARIA),
    Regra(r"^PAO\b", "Pão", PADARIA),
    # ==================================================== frios e laticínios
    # "QJ RALADO/PARMEZ" antes de "QJ" genérico.
    # `QJ\s*LA` e não `\bLA\b`: a marca "LA PAULINA" casava com o LA solto e um
    # queijo muçarela em peça virava queijo ralado (R$ 43,99/kg contra R$ 4,29 o pote).
    Regra(r"(QJ|QUEIJO).*RALAD|PARMEZ|PARMES|\bQJ\s*LA\b", "Queijo ralado", LATICINIOS),
    Regra(r"(QJ|QUEIJO).*(MUCA|MUSSAR|MUCAR)|MUSSARELA", "Queijo muçarela", LATICINIOS),
    Regra(r"(QJ|QUEIJO).*(PRATO)", "Queijo prato", LATICINIOS),
    Regra(r"(QJ|QUEIJO).*(MINAS|FRESCAL)", "Queijo minas", LATICINIOS),
    Regra(r"\bREQUEIJAO", "Requeijão", LATICINIOS),
    Regra(r"CREME\s*DE\s*RICOTA|\bRICOTA", "Creme de ricota", LATICINIOS),
    Regra(r"CREME\s*CULINARIO", "Creme culinário", LATICINIOS),
    Regra(r"CREME\s*(DE\s*)?LEITE", "Creme de leite", LATICINIOS),
    # "IOG" é a abreviação que o cupom usa. Natural separado do resto: é outro produto,
    # não outra marca do mesmo.
    Regra(r"(IOG|IOGURTE)\s*NAT", "Iogurte natural", LATICINIOS),
    Regra(r"\bIOGURTE|\bYOGURT|\bIOG\b", "Iogurte", LATICINIOS, True, "g"),
    Regra(r"\bPT\s*PERU|PEITO.*PERU|\bBLANQUET", "Peito de peru", LATICINIOS),
    Regra(r"\bMANTEIGA", "Manteiga", LATICINIOS),
    Regra(r"\bMARGARINA", "Margarina", LATICINIOS),
    Regra(r"\bPRESUNTO", "Presunto", LATICINIOS),
    Regra(r"\bMORTADELA", "Mortadela", LATICINIOS),
    Regra(r"\bSALAME", "Salame", LATICINIOS),
    Regra(r"\bQJ\b|\bQUEIJO\b", "Queijo", LATICINIOS),
    # ============================================================== mercearia
    # "LEITE COND" antes de qualquer regra de leite.
    Regra(r"LEITE\s*COND", "Leite condensado", MERCEARIA),
    Regra(r"LEITE\s*(EM\s*)?PO\b", "Leite em pó", MERCEARIA),
    Regra(r"\bLEITE\b", "Leite", LATICINIOS, True, "L"),
    Regra(r"\bARROZ", "Arroz", MERCEARIA, True, "kg"),
    Regra(r"FEIJAO.*(CARIOCA|\bC\b)", "Feijão carioca", MERCEARIA, com_tamanho=True),
    Regra(r"FEIJAO.*(PRETO|\bP\b)", "Feijão preto", MERCEARIA, com_tamanho=True),
    Regra(r"FEIJAO.*(FRADIN|CAUPI|BRANCO)", "Feijão fradinho", MERCEARIA, com_tamanho=True),
    Regra(r"\bFEIJAO", "Feijão", MERCEARIA, com_tamanho=True),
    Regra(r"\bACUCAR", "Açúcar", MERCEARIA, True, "kg"),
    # Azeitona antes de azeite: são produtos distintos e o nome começa igual.
    Regra(r"\bAZEITONA", "Azeitona", MERCEARIA, separar_granel=True),
    Regra(r"\bAZEITE|\bAZE\b", "Azeite", MERCEARIA, True, "ml"),
    Regra(r"\bOLEO\b", "Óleo de cozinha", MERCEARIA, True, "ml"),
    # Ancorado: `\bSAL\b` casava "SAL.PEIX" no fim de "RACAO P/GATOS ... SAL.PEIX",
    # e com `com_tamanho` o "1kg" da ração virava "Sal 1kg".
    Regra(r"^SAL\b", "Sal", MERCEARIA, com_tamanho=True),
    Regra(
        r"CAPS.*(NESC|DOLCE|CAFE|CAPPUC|\bD\s*G\b)|CAPSULA.*CAFE",
        "Cápsulas de café",
        MERCEARIA,
    ),
    Regra(r"\bCAFE\b", "Café", MERCEARIA, com_tamanho=True),
    # "MACARRAO INST" antes de "MACARRAO".
    Regra(r"(MACARRAO|MAC)\s*INST|\bLAMEN\b", "Macarrão instantâneo", MERCEARIA),
    Regra(r"\bMACARRAO|\bMAC\s", "Macarrão", MERCEARIA, com_tamanho=True),
    # Massa fresca refrigerada: outro produto e outra faixa de preço que o macarrão seco.
    Regra(
        r"FETTUCCINE|TALHARIM|GNOCCHI|NHOQUE|RAVIOLI|CAPELETTI|MASSA\s*FRESC|MAS\s*P\/",
        "Massa fresca",
        MERCEARIA,
    ),
    Regra(r"MILHO.*(VER|CONSERVA)|MILHO\s*VERDE", "Milho verde em conserva", MERCEARIA),
    Regra(r"\bERVILHA", "Ervilha em conserva", MERCEARIA),
    Regra(r"\bMAIONESE|\bMAION", "Maionese", MERCEARIA, True, "g"),
    Regra(r"\bKETCHUP|CATCHUP", "Ketchup", MERCEARIA, True, "g"),
    Regra(r"\bMOSTARDA", "Mostarda", MERCEARIA),
    Regra(r"\bVINAGRE", "Vinagre", MERCEARIA, True, "ml"),
    Regra(
        r"GELATINA.*(S\/\s*SABOR|SEM\s*SABOR|INCOLOR)",
        "Gelatina sem sabor",
        MERCEARIA,
    ),
    Regra(r"\bGELATINA", "Gelatina em pó", MERCEARIA),
    Regra(r"\bFARINHA|\bFAR\s*(TRIG|DE\s*TRIG)", "Farinha", MERCEARIA, True, "kg"),
    Regra(r"\bGELEIA", "Geleia", MERCEARIA),
    # Refresco em pó antes do refresco líquido: são produtos e preços diferentes.
    Regra(r"REFRES.*PO\b|\bTANG\b|SUCO\s*EM\s*PO", "Refresco em pó", MERCEARIA),
    Regra(r"\bFUBA", "Fubá", MERCEARIA),
    Regra(r"\bATUM", "Atum em lata", MERCEARIA),
    Regra(r"\bSARDINHA", "Sardinha em lata", MERCEARIA),
    Regra(r"ACHOCOLAT|\bTODDY|\bNESCAU", "Achocolatado", MERCEARIA),
    Regra(r"\bAVEIA", "Aveia", MERCEARIA),
    Regra(r"\bCANJIQUINHA|\bCANJICA", "Canjiquinha", MERCEARIA),
    Regra(r"TRIGO\s*P\/?\s*KIBE|\bQUIBE", "Trigo para quibe", MERCEARIA),
    Regra(r"MILHO\s*DE\s*PIPOCA|\bPIPOCA", "Milho de pipoca", MERCEARIA),
    Regra(r"^MEL\b|\bMEL\s+BALDONI", "Mel", MERCEARIA),
    Regra(r"MOLHO\s*DE\s*ALHO|MOLHO.*(SHOYU|INGLES|BARBECUE)", "Molho pronto", MERCEARIA),
    Regra(r"MASSA\s*P\/?\s*PASTEL|MASSA.*PASTEL", "Massa para pastel", MERCEARIA),
    Regra(r"MASSA\s*C\/?\s*OVOS", "Macarrão", MERCEARIA, True, "g"),
    Regra(r"^TORRADA", "Torrada", MERCEARIA),
    Regra(r"\bLENTILHA", "Lentilha", MERCEARIA),
    Regra(r"\bGRAO\s*DE\s*BICO", "Grão de bico", MERCEARIA),
    Regra(
        r"\bLOURO\b|\bOREGANO|\bCOMINHO|\bCOLORIFICO|\bPIMENTA\s*DO\s*REINO"
        r"|\bTEMPERO|^TEM\b",
        "Tempero seco",
        MERCEARIA,
        separar_granel=True,
    ),
    Regra(r"\bCHIMICHURRI|\bPAPRICA|\bCONDIMENTAD", "Condimento", MERCEARIA, separar_granel=True),
    Regra(r"(BISC|BISCOITO|BOLACHA).*RECH", "Biscoito recheado", MERCEARIA),
    Regra(r"\bBISCOITO|\bBISC\b|\bBOLACHA", "Biscoito", MERCEARIA),
    # ========================================================= doces e snacks
    Regra(r"\bBOMBOM", "Bombom", DOCES, separar_granel=True),
    # Vendidos em muitos tamanhos (barra de 90 g a caixa de 400 g): sem o tamanho no
    # nome, a faixa de preço de um "Chocolate" só ia de 1,94 a 16,99 sem significar nada.
    Regra(r"\bCHOC|CHOCOLATE|FERRERO|\bBIS\b", "Chocolate", DOCES, True, "g"),
    Regra(r"^MARIOLA|\bGOIABADA|\bPACOQUINHA", "Doce em pasta", DOCES),
    Regra(r"^DOCE\b", "Doce", DOCES, True, "g"),
    # Salgadinho de festa vem em pacote de centenas de gramas e custa múltiplas
    # vezes um chips — produtos distintos, não marcas do mesmo.
    Regra(r"\bSALG\b|SALGADINHO\s*DE\s*FESTA", "Salgadinho de festa", CONGELADOS),
    Regra(
        r"\bCHIPS|SALGADIN|BATATA\s*PALHA|BATATA.*(LAYS|RUFFLES|PRINGLES|ELMA)",
        "Salgadinho",
        DOCES,
        True,
        "g",
    ),
    Regra(r"\bWAFER", "Wafer", DOCES),
    Regra(r"\bALFAJOR", "Alfajor", DOCES, True, "g"),
    Regra(
        r"\bPIRULITO|\bBALA\b|\bCHICLETE|\bJUJUBA|MARSHMALLOW|\bMAXMALL|\bFINI\b"
        r"|\bTUBES\b",
        "Bala e goma",
        DOCES,
    ),
    Regra(r"\bAMENDOIM", "Amendoim", DOCES),
    Regra(r"\bPACOCA|\bPE\s*DE\s*MOLEQUE", "Doce de amendoim", DOCES),
    # ================================================================ bebidas
    # "AGUA SANITARIA" é produto de limpeza: precisa vir antes de qualquer "AGUA".
    Regra(r"AGUA\s*SANITARIA|\bCANDIDA\b|\bQ-?BOA", "Água sanitária", LIMPEZA),
    Regra(r"AGUA\s*(SAB|COM\s*GAS|TONICA)", "Água saborizada", BEBIDAS, True, "ml"),
    Regra(r"\bAGUA\s*(M|MIN)", "Água mineral", BEBIDAS, True, "ml"),
    # Guaraná e bebida láctea vinham antes marcados como energético só porque a
    # descrição começa com "ENERG": R$ 1,94 e R$ 9,89 na mesma série de preço.
    Regra(r"BEBIDA\s*LAC|\bBEB\s*LAC", "Bebida láctea", LATICINIOS),
    Regra(r"GUARAV|GUARAN", "Guaraná", BEBIDAS, True, "ml"),
    Regra(r"\bENERG|\bMONSTER|RED\s*BULL", "Energético", BEBIDAS),
    Regra(
        r"\bREFRI|\bREFRIG|\bCOCA|\bFANTA|\bSPRITE|\bPEPSI|\bSUKITA",
        "Refrigerante",
        BEBIDAS,
        com_tamanho=True,
        unidade_provavel="ml",
    ),
    Regra(r"\bNECTAR", "Néctar de fruta", BEBIDAS, True, "L"),
    Regra(r"\bSUCO\b", "Suco", BEBIDAS, True, "L"),
    Regra(r"REF\s*SAB|\bREFRESCO|^RF\b|\bRF\s", "Refresco", BEBIDAS, True, "L"),
    Regra(r"\bCHA\b", "Chá", BEBIDAS),
    Regra(r"AGUA\s*DE\s*COCO", "Água de coco", BEBIDAS, True, "ml"),
    Regra(r"BEBIDA\s*DE\s*SOJA|\bADES\b", "Bebida de soja", BEBIDAS, True, "ml"),
    # ==================================================== bebidas alcoólicas
    Regra(
        r"\bCERVEJA|\bCHOPP|\bSKOL|\bBRAHMA|\bHEINEKEN|\bITAIPAVA|\bANTARCTICA",
        "Cerveja",
        ALCOOLICAS,
        com_tamanho=True,
    ),
    Regra(r"\bVINHO\b", "Vinho", ALCOOLICAS),
    Regra(r"\bVODKA|\bCACHACA|\bWHISKY|\bGIN\b|\bRUM\b", "Destilado", ALCOOLICAS),
    # ================================================================ limpeza
    Regra(r"\bDETERGENTE", "Detergente de louça", LIMPEZA),
    Regra(r"LAV\s*LO|LAVA\s*LOUCA", "Lava-louças", LIMPEZA, True, "ml"),
    Regra(
        r"LAVA\s*R|LAVA\s*ROUPA|SABAO\s*LIQ|\bOMO\b|\bURCA\b|\bARIEL\b",
        "Lava-roupas líquido",
        LIMPEZA,
        com_tamanho=True,
    ),
    Regra(r"SABAO\s*(EM\s*)?PO", "Sabão em pó", LIMPEZA, com_tamanho=True),
    Regra(r"SABAO\s*(BARRA|GLICERIN)", "Sabão em barra", LIMPEZA),
    Regra(r"\bAMACIANTE|\bDOWNY|\bCOMFORT", "Amaciante", LIMPEZA, com_tamanho=True),
    Regra(r"\bDESINFETANTE|\bPINHO\b", "Desinfetante", LIMPEZA, com_tamanho=True),
    Regra(r"\bALVEJANTE|\bVANISH", "Alvejante", LIMPEZA),
    # Pastilha costuma vir em cartela ("leve 5 pague 4"); a pedra é unitária. O preço
    # de uma cartela contra o de uma pedra não é a mesma série.
    Regra(r"PAST(ILHA)?\s*SANIT", "Pastilha sanitária", LIMPEZA),
    Regra(r"PEDRA\s*SAN|BLOCO\s*SANIT", "Pedra sanitária", LIMPEZA),
    Regra(r"\bESPONJA|ESP\s*ANT|\bBOMBRIL|\bPALHA\s*DE\s*ACO", "Esponja", LIMPEZA, True, "g"),
    Regra(r"\bINSETICIDA|\bSBP\b|\bBAYGON", "Inseticida", LIMPEZA),
    Regra(r"LIMPA\s*VIDRO|\bVIDREX", "Limpa-vidros", LIMPEZA, True, "ml"),
    Regra(r"ALCOOL\s*GEL", "Álcool em gel", HIGIENE),
    Regra(r"^ALCOOL\b", "Álcool", LIMPEZA, True, "L"),
    Regra(r"\bRODO\b|\bVASSOURA|\bBALDE\b|\bPANO\s*DE", "Utensílio de limpeza", LIMPEZA),
    Regra(r"\bRALO\b|\bRALINHO|\bRAL\b.*PIA", "Ralo de pia", LIMPEZA),
    Regra(r"^CARVAO", "Carvão", OUTROS),
    Regra(r"LIMP.*CREMOSO|\bSAPOLIO", "Limpador cremoso", LIMPEZA),
    Regra(r"LIMP.*(CASA|MULT|PERF)|\bMULTIUSO|\bVEJA\b", "Limpador multiuso", LIMPEZA),
    # ================================================================ higiene
    # "PAPEL TOALHA" e "PAPEL HIGIENICO" antes de qualquer "PAPEL".
    Regra(r"PAPEL\s*(TO|TOALHA)|\bPAP\s*TOA", "Papel toalha", DESCARTAVEIS),
    Regra(r"PAPEL\s*(HIG|HIGIENICO)|\bPA\s*HIG?\b", "Papel higiênico", HIGIENE),
    Regra(r"SABONETE\s*LIQ|SABON\s*LIQ", "Sabonete líquido", HIGIENE),
    Regra(r"\bSABONETE|\bSABON\b", "Sabonete em barra", HIGIENE, True, "g"),
    Regra(
        r"^S\s*\+\s*C|SHAMPOO.*CONDIC|CONDIC.*SHAMPOO|KIT\s*SH",
        "Shampoo e condicionador",
        HIGIENE,
    ),
    Regra(r"\bSHAMPOO|\bXAMPU", "Shampoo", HIGIENE),
    Regra(r"\bCONDICIONADOR", "Condicionador", HIGIENE),
    Regra(
        r"CREME\s*DENTAL|PASTA\s*DENTAL|GEL\s*DENT|\bCOLGATE|\bSORRISO|\bCLOSE\s*UP"
        r"|\bCLOSEUP",
        "Creme dental",
        HIGIENE,
    ),
    Regra(r"ESCOVA\s*DEN", "Escova de dente", HIGIENE),
    Regra(r"\bABSORVENTE|\bABS\b", "Absorvente", HIGIENE),
    Regra(r"\bDESODORANTE|\bDESOD|\bDESO\b", "Desodorante", HIGIENE),
    Regra(r"\bCOTON|\bCOTONETE|HASTE\s*FLEX", "Cotonete", HIGIENE),
    Regra(r"DISCO.*ALGO|ALGODAO", "Algodão", HIGIENE),
    Regra(r"\bTINTURA|\bCOLORACAO|\bKOLESTON", "Tintura de cabelo", HIGIENE),
    Regra(r"\bFRALDA", "Fralda", HIGIENE),
    Regra(r"\bLENCO", "Lenço de papel", HIGIENE),
    Regra(r"TOALHA.*UMED|LENCO.*UMED", "Lenço umedecido", HIGIENE),
    Regra(r"FIO\s*DENTAL", "Fio dental", HIGIENE),
    Regra(r"\bBARBEAR|\bGILLETTE|\bPRESTOBARBA", "Aparelho de barbear", HIGIENE),
    # =========================================================== descartáveis
    Regra(r"COPO\s*(PLAST|DESC)", "Copo plástico", DESCARTAVEIS),
    Regra(r"(COLHER|GARFO|PRATO|FACA)\s*(PLAST|DESC)", "Utensílio descartável", DESCARTAVEIS),
    Regra(r"\bGUARDANAPO", "Guardanapo", DESCARTAVEIS),
    Regra(r"SACO\s*(P\/?\s*ALI|ALIMENTO|FREEZER)", "Saco para alimentos", DESCARTAVEIS),
    Regra(r"SACO\s*(DE\s*)?LIXO", "Saco de lixo", DESCARTAVEIS),
    Regra(r"SACO.*(HOT\s*DOG|PAO|LANCHE)", "Saco para lanche", DESCARTAVEIS),
    Regra(r"\bSACOLA", "Sacola plástica", DESCARTAVEIS),
    Regra(r"FILME\s*(PVC|PLAST)|PAPEL\s*ALUM", "Filme e alumínio", DESCARTAVEIS),
    Regra(r"\bFOSFORO|\bVELA\b", "Fósforo e vela", DESCARTAVEIS),
    Regra(r"PALITO.*DENTE", "Palito de dente", DESCARTAVEIS),
    Regra(r"FORMA\s*DESCART|FORMA.*AIR\s*FRYER", "Forma descartável", DESCARTAVEIS),
    # ==================================================================== pet
    # Sachê e ração seca diferem em uma ordem de magnitude de preço por unidade.
    Regra(r"RACAO.*SACHE|SACHE.*(GATO|CAO)", "Ração em sachê", PET),
    Regra(r"AREIA.*GATO", "Areia para gato", PET),
    Regra(r"RACAO.*(GATO|WHISKAS|FELIN)", "Ração seca para gato", PET, True, "kg"),
    Regra(r"RACAO.*(CAO|CACHORRO|PEDIGREE|DOG)", "Ração para cão", PET),
    Regra(r"\bRACAO", "Ração", PET),
)

# Compilado uma vez: `classificar` roda por item de cada nota importada.
_REGRAS_COMPILADAS: tuple[tuple[re.Pattern[str], Regra], ...] = tuple(
    (re.compile(regra.padrao), regra) for regra in REGRAS
)


def _sem_acento_maiusculo(texto: str) -> str:
    """Forma de comparação: maiúsculas, sem acento. Os padrões assumem isso."""
    sem_acento = "".join(
        c
        for c in unicodedata.normalize("NFD", texto or "")
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sem_acento).strip().upper()


def _formatar_quantidade(bruto: str) -> str:
    quantidade = bruto.replace(",", ".")
    # Só corta zeros à direita quando há parte decimal: "41,50" -> "41.5". Aplicar
    # `rstrip("0")` em inteiro transformaria "500" em "5" — e "500ML" viraria "5ml".
    if "." in quantidade:
        quantidade = quantidade.rstrip("0").rstrip(".")
    return quantidade


def extrair_tamanho(descricao: str, unidade_provavel: str | None = None) -> str | None:
    """Tamanho da embalagem, normalizado — ``"5KG"`` vira ``"5kg"``.

    Com ``unidade_provavel``, aceita também o número solto no fim da descrição (caso do
    texto cortado pelo portal) e assume essa unidade. Sem ela, número sem unidade é
    ignorado — melhor nome sem sufixo do que sufixo errado.
    """
    alvo = _sem_acento_maiusculo(descricao)

    if achado := _TAMANHO.search(alvo):
        unidade = _SUFIXO_POR_UNIDADE[achado.group(2)]
        return f"{_formatar_quantidade(achado.group(1))}{unidade}"

    if (
        unidade_provavel
        and not _NAO_E_MEDIDA.search(alvo)
        and (achado := _TAMANHO_SEM_UNIDADE.search(alvo))
    ):
        return f"{_formatar_quantidade(achado.group(1))}{unidade_provavel}"

    return None


@dataclass(frozen=True)
class Classificacao:
    nome: str
    categoria: str
    padrao: str


def classificar(descricao: str) -> Classificacao | None:
    """Produto e categoria para uma descrição de cupom, ou ``None`` se nada casar.

    ``None`` é resposta legítima e importante: melhor deixar o item na fila de revisão
    do que atribuí-lo a um produto errado, porque um vínculo errado contamina a série
    de preço em silêncio — e a série é o motivo de o app existir.
    """
    alvo = _sem_acento_maiusculo(descricao)
    if not alvo:
        return None

    for compilado, regra in _REGRAS_COMPILADAS:
        if not compilado.search(alvo):
            continue

        nome = regra.nome
        if regra.com_tamanho and (
            tamanho := extrair_tamanho(alvo, regra.unidade_provavel)
        ):
            nome = f"{nome} {tamanho}"
        elif regra.separar_granel and _E_GRANEL.search(alvo):
            nome = f"{nome} a granel"
        return Classificacao(nome=nome, categoria=regra.categoria, padrao=regra.padrao)

    return None
