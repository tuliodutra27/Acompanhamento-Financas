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


# A ordem importa: a primeira regra que casar vence. Regras mais específicas primeiro.
REGRAS: tuple[Regra, ...] = (
    # ================================================================= carnes
    Regra(r"\bMOID", "Carne moída", CARNES),
    Regra(r"\bALCAT", "Alcatra", CARNES),
    Regra(r"\bMAMINHA|\bMAM\b", "Maminha", CARNES),
    Regra(r"\bPICANHA", "Picanha", CARNES),
    Regra(r"\bCOXAO", "Coxão", CARNES),
    Regra(r"\bPATINHO", "Patinho", CARNES),
    Regra(r"\bCONTRA\s*FILE|\bCONTRAFILE", "Contrafilé", CARNES),
    Regra(r"\bCOSTELA", "Costela", CARNES),
    Regra(r"\bACEM\b", "Acém", CARNES),
    # Cortes de frango antes de qualquer regra genérica de frango.
    Regra(r"PEITO.*(FGO|FRANGO)|(FGO|FRANGO).*PEITO", "Peito de frango", CARNES),
    Regra(r"FILE.*(FGO|FRANGO)|(FGO|FRANGO).*FILE", "Filé de frango", CARNES),
    Regra(r"COXA.*(FGO|FRANGO)|SOBRECOXA", "Coxa de frango", CARNES),
    Regra(r"\bASA.*(FGO|FRANGO)", "Asa de frango", CARNES),
    Regra(r"\bLINGUI", "Linguiça", CARNES),
    Regra(r"\bBACON", "Bacon", CARNES),
    Regra(r"\bPEIXE|\bTILAPIA|\bSALMAO|\bSARDINHA\s*FRESC", "Peixe", CARNES),
    # ============================================================= congelados
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
    Regra(r"\bPIZZA", "Pizza congelada", CONGELADOS),
    Regra(r"\bPOLPA", "Polpa de fruta", CONGELADOS),
    Regra(r"BROCOLIS.*(DAUCY|CONG)", "Brócolis congelado", CONGELADOS),
    Regra(
        r"(MISTURA|SELETA|JARDINEIRA).*(DAUCY|LEGUME|VEGETAL)|LEGUMES?.*CONG",
        "Legumes congelados",
        CONGELADOS,
    ),
    Regra(r"BATATA.*(FRITA|CONG|PALITO)", "Batata congelada", CONGELADOS),
    Regra(r"\bSORVETE|\bPICOLE", "Sorvete", DOCES),
    # ============================================================= hortifruti
    # "TEMPERO VERDE" antes de "TEMPERO" (que é tempero seco, de mercearia).
    Regra(r"TEMPERO\s*VERDE|CHEIRO\s*VERDE", "Tempero verde", HORTIFRUTI),
    Regra(r"\bALFACE", "Alface", HORTIFRUTI),
    Regra(r"\bBANANA", "Banana", HORTIFRUTI),
    Regra(r"BATATA\s*(INGLESA|ASTERIX|LAVADA)|^BATATA\b", "Batata inglesa", HORTIFRUTI),
    Regra(r"BATATA\s*DOCE", "Batata doce", HORTIFRUTI),
    Regra(r"\bCEBOLA", "Cebola", HORTIFRUTI),
    Regra(r"\bTOMATE\b(?!.*(MOL|EXTRA|SECO))", "Tomate", HORTIFRUTI),
    Regra(r"\bLARANJA", "Laranja", HORTIFRUTI),
    Regra(r"\bMACA\b|MACA\s*(kg|RED|FUJI|GALA)", "Maçã", HORTIFRUTI),
    Regra(r"\bMANGA\b", "Manga", HORTIFRUTI),
    Regra(r"\bMORANGO", "Morango", HORTIFRUTI),
    Regra(r"\bKIWI", "Kiwi", HORTIFRUTI),
    Regra(r"TANGERINA|PONKAN|MEXERICA", "Tangerina", HORTIFRUTI),
    Regra(r"\bLIMAO", "Limão", HORTIFRUTI),
    Regra(r"\bMAMAO", "Mamão", HORTIFRUTI),
    Regra(r"\bABACAXI", "Abacaxi", HORTIFRUTI),
    Regra(r"\bMELANCIA", "Melancia", HORTIFRUTI),
    Regra(r"\bMELAO", "Melão", HORTIFRUTI),
    Regra(r"\bUVA\b", "Uva", HORTIFRUTI),
    Regra(r"\bPERA\b", "Pera", HORTIFRUTI),
    Regra(r"\bCENOURA", "Cenoura", HORTIFRUTI),
    Regra(r"\bCOENTRO", "Coentro", HORTIFRUTI),
    Regra(r"\bSALSA\b|SALSINHA", "Salsinha", HORTIFRUTI),
    Regra(r"\bCOUVE", "Couve", HORTIFRUTI),
    Regra(r"\bREPOLHO", "Repolho", HORTIFRUTI),
    Regra(r"\bPIMENTAO", "Pimentão", HORTIFRUTI),
    Regra(r"\bABOBRINHA|\bABOBORA", "Abobrinha", HORTIFRUTI),
    Regra(r"\bCHUCHU", "Chuchu", HORTIFRUTI),
    Regra(r"\bBETERRABA", "Beterraba", HORTIFRUTI),
    Regra(r"\bPEPINO", "Pepino", HORTIFRUTI),
    Regra(r"\bMANDIOCA|\bAIPIM|\bMACAXEIRA", "Mandioca", HORTIFRUTI),
    Regra(r"\bINHAME", "Inhame", HORTIFRUTI),
    Regra(r"\bALHO\b", "Alho", HORTIFRUTI),
    Regra(r"\bGENGIBRE", "Gengibre", HORTIFRUTI),
    Regra(r"\bBROCOLIS", "Brócolis", HORTIFRUTI),
    Regra(r"\bOVO\b|\bOVOS\b", "Ovos", HORTIFRUTI),
    # ================================================================ padaria
    # "BOLO" antes de "CHOC": "BOLO 350G CHOC" é bolo, não chocolate.
    Regra(r"\bBOLO\b", "Bolo", PADARIA),
    Regra(r"\bBRIOCHE", "Brioche", PADARIA),
    Regra(r"PAO\s*(BAGUETE|FRANCES)|\bBAGUETE", "Pão baguete", PADARIA),
    Regra(r"PAO\s*(FOR|DE\s*FORMA)", "Pão de forma", PADARIA),
    Regra(r"PAO.*(kg|GRANEL|MQP)", "Pão a granel", PADARIA),
    Regra(r"\bROSCA\b", "Rosca", PADARIA),
    Regra(r"\bSONHO\b", "Sonho", PADARIA),
    Regra(r"\bCROISSANT", "Croissant", PADARIA),
    Regra(r"\bTORTA\b", "Torta", PADARIA),
    Regra(r"\bPAO\b", "Pão", PADARIA),
    # ==================================================== frios e laticínios
    # "QJ RALADO/PARMEZ" antes de "QJ" genérico.
    Regra(r"(QJ|QUEIJO).*(RALAD|\bLA\b)|PARMEZ|PARMES", "Queijo ralado", LATICINIOS),
    Regra(r"(QJ|QUEIJO).*(MUCA|MUSSAR|MUCAR)|MUSSARELA", "Queijo muçarela", LATICINIOS),
    Regra(r"(QJ|QUEIJO).*(PRATO)", "Queijo prato", LATICINIOS),
    Regra(r"(QJ|QUEIJO).*(MINAS|FRESCAL)", "Queijo minas", LATICINIOS),
    Regra(r"\bREQUEIJAO", "Requeijão", LATICINIOS),
    Regra(r"CREME\s*(DE\s*)?LEITE", "Creme de leite", LATICINIOS),
    Regra(r"\bIOGURTE|\bYOGURT", "Iogurte", LATICINIOS),
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
    Regra(r"\bAZEITE|\bAZE\b", "Azeite", MERCEARIA, True, "ml"),
    Regra(r"\bOLEO\b", "Óleo de cozinha", MERCEARIA, True, "ml"),
    Regra(r"\bSAL\b", "Sal", MERCEARIA, com_tamanho=True),
    Regra(r"CAPS.*(NESC|DOLCE|CAFE)|CAPSULA.*CAFE", "Cápsulas de café", MERCEARIA),
    Regra(r"\bCAFE\b", "Café", MERCEARIA, com_tamanho=True),
    # "MACARRAO INST" antes de "MACARRAO".
    Regra(r"(MACARRAO|MAC)\s*INST|\bLAMEN\b", "Macarrão instantâneo", MERCEARIA),
    Regra(r"\bMACARRAO|\bMAC\s", "Macarrão", MERCEARIA, com_tamanho=True),
    Regra(r"MOL\s*TOM|MOLHO.*TOMATE", "Molho de tomate", MERCEARIA),
    Regra(r"EXTRATO.*TOMATE", "Extrato de tomate", MERCEARIA),
    Regra(r"MILHO.*(VER|CONSERVA)|MILHO\s*VERDE", "Milho verde em conserva", MERCEARIA),
    Regra(r"\bERVILHA", "Ervilha em conserva", MERCEARIA),
    Regra(r"\bMAIONESE|\bMAION", "Maionese", MERCEARIA, True, "g"),
    Regra(r"\bKETCHUP|CATCHUP", "Ketchup", MERCEARIA),
    Regra(r"\bMOSTARDA", "Mostarda", MERCEARIA),
    Regra(r"\bVINAGRE", "Vinagre", MERCEARIA, True, "ml"),
    Regra(r"\bGELATINA", "Gelatina em pó", MERCEARIA),
    Regra(r"\bFARINHA", "Farinha", MERCEARIA, com_tamanho=True),
    Regra(r"\bFUBA", "Fubá", MERCEARIA),
    Regra(r"\bATUM", "Atum em lata", MERCEARIA),
    Regra(r"\bSARDINHA", "Sardinha em lata", MERCEARIA),
    Regra(r"ACHOCOLAT|\bTODDY|\bNESCAU", "Achocolatado", MERCEARIA),
    Regra(r"\bAVEIA", "Aveia", MERCEARIA),
    Regra(r"\bLENTILHA", "Lentilha", MERCEARIA),
    Regra(r"\bGRAO\s*DE\s*BICO", "Grão de bico", MERCEARIA),
    Regra(
        r"\bLOURO\b|\bOREGANO|\bCOMINHO|\bCOLORIFICO|\bPIMENTA\s*DO\s*REINO|\bTEMPERO",
        "Tempero seco",
        MERCEARIA,
    ),
    Regra(r"\bBISCOITO|\bBISC\b|\bBOLACHA", "Biscoito", MERCEARIA),
    # ========================================================= doces e snacks
    Regra(r"\bBOMBOM", "Bombom", DOCES),
    Regra(r"\bCHOC|CHOCOLATE", "Chocolate", DOCES),
    Regra(r"\bCHIPS|SALGADIN|BATATA\s*PALHA", "Salgadinho", DOCES),
    Regra(r"\bPIRULITO|\bBALA\b|\bCHICLETE", "Bala e pirulito", DOCES),
    Regra(r"\bAMENDOIM", "Amendoim", DOCES),
    Regra(r"\bPACOCA|\bPE\s*DE\s*MOLEQUE", "Doce de amendoim", DOCES),
    # ================================================================ bebidas
    # "AGUA SANITARIA" é produto de limpeza: precisa vir antes de qualquer "AGUA".
    Regra(r"AGUA\s*SANITARIA|\bCANDIDA\b|\bQ-?BOA", "Água sanitária", LIMPEZA),
    Regra(r"AGUA\s*(SAB|COM\s*GAS|TONICA)", "Água saborizada", BEBIDAS, True, "ml"),
    Regra(r"\bAGUA\s*(M|MIN)", "Água mineral", BEBIDAS, True, "ml"),
    Regra(r"\bENERG|\bMONSTER|RED\s*BULL", "Energético", BEBIDAS),
    Regra(r"GUARAV|GUARAN", "Guaraná", BEBIDAS, True, "ml"),
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
    Regra(r"PEDRA\s*SAN", "Pedra sanitária", LIMPEZA),
    Regra(r"\bESPONJA|ESP\s*ANT|\bBOMBRIL|\bPALHA\s*DE\s*ACO", "Esponja", LIMPEZA),
    Regra(r"\bINSETICIDA|\bSBP\b|\bBAYGON", "Inseticida", LIMPEZA),
    Regra(r"\bRODO\b|\bVASSOURA|\bBALDE\b|\bPANO\s*DE", "Utensílio de limpeza", LIMPEZA),
    Regra(r"\bRALO\b|\bRAL\b.*PIA", "Ralo de pia", LIMPEZA),
    Regra(r"LIMP.*(CASA|MULTI|PERF)|\bMULTIUSO|\bVEJA\b", "Limpador multiuso", LIMPEZA),
    # ================================================================ higiene
    # "PAPEL TOALHA" e "PAPEL HIGIENICO" antes de qualquer "PAPEL".
    Regra(r"PAPEL\s*(TO|TOALHA)", "Papel toalha", DESCARTAVEIS),
    Regra(r"PAPEL\s*(HIG|HIGIENICO)", "Papel higiênico", HIGIENE),
    Regra(r"SABONETE\s*LIQ|SABON\s*LIQ", "Sabonete líquido", HIGIENE),
    Regra(r"\bSABONETE|\bSABON\b", "Sabonete em barra", HIGIENE, True, "g"),
    Regra(r"^S\s*\+\s*C|SHAMPOO.*CONDIC|CONDIC.*SHAMPOO", "Shampoo e condicionador", HIGIENE),
    Regra(r"\bSHAMPOO|\bXAMPU", "Shampoo", HIGIENE),
    Regra(r"\bCONDICIONADOR", "Condicionador", HIGIENE),
    Regra(r"CREME\s*DENTAL|PASTA\s*DENTAL|\bCOLGATE|\bSORRISO", "Creme dental", HIGIENE),
    Regra(r"ESCOVA\s*DENT", "Escova de dente", HIGIENE),
    Regra(r"\bABSORVENTE", "Absorvente", HIGIENE),
    Regra(r"\bDESODORANTE|\bDESOD\b", "Desodorante", HIGIENE),
    Regra(r"\bCOTON|\bCOTONETE|HASTE\s*FLEX", "Cotonete", HIGIENE),
    Regra(r"DISCO.*ALGO|ALGODAO", "Algodão", HIGIENE),
    Regra(r"\bTINTURA|\bCOLORACAO|\bKOLESTON", "Tintura de cabelo", HIGIENE),
    Regra(r"\bFRALDA", "Fralda", HIGIENE),
    Regra(r"\bLENCO", "Lenço de papel", HIGIENE),
    Regra(r"\bBARBEAR|\bGILLETTE|\bPRESTOBARBA", "Aparelho de barbear", HIGIENE),
    # =========================================================== descartáveis
    Regra(r"COPO\s*(PLAST|DESC)", "Copo plástico", DESCARTAVEIS),
    Regra(r"(COLHER|GARFO|PRATO|FACA)\s*(PLAST|DESC)", "Utensílio descartável", DESCARTAVEIS),
    Regra(r"\bGUARDANAPO", "Guardanapo", DESCARTAVEIS),
    Regra(r"SACO\s*(P\/?\s*ALI|ALIMENTO|FREEZER)", "Saco para alimentos", DESCARTAVEIS),
    Regra(r"SACO\s*(DE\s*)?LIXO", "Saco de lixo", DESCARTAVEIS),
    Regra(r"\bSACOLA", "Sacola plástica", DESCARTAVEIS),
    Regra(r"FILME\s*(PVC|PLAST)|PAPEL\s*ALUM", "Filme e alumínio", DESCARTAVEIS),
    Regra(r"\bFOSFORO|\bVELA\b", "Fósforo e vela", DESCARTAVEIS),
    # ==================================================================== pet
    Regra(r"RACAO.*(GATO|WHISKAS|FELIN)|AREIA.*GATO", "Ração para gato", PET),
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
        return Classificacao(nome=nome, categoria=regra.categoria, padrao=regra.padrao)

    return None
