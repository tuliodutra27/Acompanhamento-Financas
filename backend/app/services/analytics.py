"""As perguntas que o app existe para responder.

"Quanto eu paguei no arroz em cada mês do ano?", "quais são meus maiores gastos?",
"estou gastando mais este mês do que no passado?".
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Numeric, cast, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.item_nota import ItemNota
from app.models.nota_fiscal import NotaFiscal
from app.models.produto import Produto


def _data_da_compra() -> ColumnElement[date]:
    """Data a usar nas agregações.

    Prefere a data real de emissão (do parse ou digitada). Quando ela não existe —
    nota registrada, itens ainda não preenchidos — cai para o mês que está codificado
    na própria chave de acesso. Assim uma nota nunca fica fora dos relatórios por
    falta de data.
    """
    return func.coalesce(
        func.date_trunc("month", NotaFiscal.emitida_em),
        func.to_date(NotaFiscal.ano_mes_chave, "YYMM"),
    )


def _filtro_periodo(consulta, desde: date | None, ate: date | None):
    if desde is not None:
        consulta = consulta.where(_data_da_compra() >= desde)
    if ate is not None:
        consulta = consulta.where(_data_da_compra() <= ate)
    return consulta


async def serie_precos(
    sessao: AsyncSession,
    produto_id: int,
    *,
    desde: date | None = None,
    ate: date | None = None,
) -> list[dict[str, object]]:
    """Preço unitário do produto mês a mês — o gráfico principal do app.

    Devolve média, mínimo e máximo por mês, mais quantas compras entraram no cálculo.
    Mostrar o ``n_compras`` importa: uma média de uma única compra não é tendência, e
    a interface precisa poder dizer isso.
    """
    mes = _data_da_compra().label("mes")
    consulta = (
        select(
            mes,
            func.avg(ItemNota.valor_unitario).label("preco_medio"),
            func.min(ItemNota.valor_unitario).label("preco_min"),
            func.max(ItemNota.valor_unitario).label("preco_max"),
            func.sum(ItemNota.valor_total).label("total_gasto"),
            func.sum(ItemNota.quantidade).label("quantidade_total"),
            func.count().label("n_compras"),
        )
        .join(NotaFiscal, NotaFiscal.id == ItemNota.nota_id)
        .where(ItemNota.produto_id == produto_id)
        .group_by(mes)
        .order_by(mes)
    )

    resultado = await sessao.execute(_filtro_periodo(consulta, desde, ate))
    return [
        {
            "mes": linha.mes.date().isoformat() if hasattr(linha.mes, "date") else str(linha.mes),
            "preco_medio": float(linha.preco_medio or 0),
            "preco_min": float(linha.preco_min or 0),
            "preco_max": float(linha.preco_max or 0),
            "total_gasto": float(linha.total_gasto or 0),
            "quantidade_total": float(linha.quantidade_total or 0),
            "n_compras": int(linha.n_compras or 0),
        }
        for linha in resultado
    ]


async def ranking_gastos(
    sessao: AsyncSession,
    *,
    desde: date | None = None,
    ate: date | None = None,
    limite: int = 20,
) -> list[dict[str, object]]:
    """Maiores gastos por produto no período — "onde meu dinheiro está indo"."""
    consulta = (
        select(
            Produto.id.label("produto_id"),
            Produto.nome.label("nome"),
            func.sum(ItemNota.valor_total).label("total_gasto"),
            func.sum(ItemNota.quantidade).label("quantidade_total"),
            func.avg(ItemNota.valor_unitario).label("preco_medio"),
            func.count().label("n_compras"),
        )
        .join(ItemNota, ItemNota.produto_id == Produto.id)
        .join(NotaFiscal, NotaFiscal.id == ItemNota.nota_id)
        .group_by(Produto.id, Produto.nome)
        .order_by(func.sum(ItemNota.valor_total).desc())
        .limit(limite)
    )

    resultado = await sessao.execute(_filtro_periodo(consulta, desde, ate))
    return [
        {
            "produto_id": linha.produto_id,
            "nome": linha.nome,
            "total_gasto": float(linha.total_gasto or 0),
            "quantidade_total": float(linha.quantidade_total or 0),
            "preco_medio": float(linha.preco_medio or 0),
            "n_compras": int(linha.n_compras or 0),
        }
        for linha in resultado
    ]


async def resumo_mensal(
    sessao: AsyncSession, *, desde: date | None = None, ate: date | None = None
) -> list[dict[str, object]]:
    """Total gasto por mês, para comparar um mês com o outro."""
    mes = _data_da_compra().label("mes")
    consulta = (
        select(
            mes,
            func.sum(ItemNota.valor_total).label("total_gasto"),
            func.count(func.distinct(NotaFiscal.id)).label("n_notas"),
            func.count().label("n_itens"),
        )
        .join(NotaFiscal, NotaFiscal.id == ItemNota.nota_id)
        .group_by(mes)
        .order_by(mes)
    )

    resultado = await sessao.execute(_filtro_periodo(consulta, desde, ate))
    return [
        {
            "mes": linha.mes.date().isoformat() if hasattr(linha.mes, "date") else str(linha.mes),
            "total_gasto": float(linha.total_gasto or 0),
            "n_notas": int(linha.n_notas or 0),
            "n_itens": int(linha.n_itens or 0),
        }
        for linha in resultado
    ]


async def variacao_preco(
    sessao: AsyncSession, produto_id: int
) -> dict[str, object] | None:
    """Primeiro preço, último preço e variação percentual do produto.

    É o número que responde "o arroz subiu quanto?" sem o usuário ter que ler o
    gráfico. Devolve ``None`` quando há menos de duas compras — com um ponto só não
    existe variação, e inventar um número aqui seria pior que não mostrar nada.
    """
    serie = await serie_precos(sessao, produto_id)
    if len(serie) < 2:
        return None

    primeiro = serie[0]
    ultimo = serie[-1]
    preco_inicial = Decimal(str(primeiro["preco_medio"]))
    preco_final = Decimal(str(ultimo["preco_medio"]))

    if preco_inicial == 0:
        return None

    variacao = (preco_final - preco_inicial) / preco_inicial * 100
    return {
        "mes_inicial": primeiro["mes"],
        "preco_inicial": float(preco_inicial),
        "mes_final": ultimo["mes"],
        "preco_final": float(preco_final),
        "variacao_percentual": round(float(variacao), 2),
        "meses_com_dados": len(serie),
    }


async def gasto_por_categoria(
    sessao: AsyncSession, *, desde: date | None = None, ate: date | None = None
) -> list[dict[str, object]]:
    """Gasto por categoria — "onde vai meu dinheiro" em nível de grupo.

    Itens sem produto vinculado ficam fora: não têm categoria, e somá-los num
    "sem categoria" competindo com Carnes daria a impressão de que existe uma despesa
    com esse nome. Eles aparecem como pendência no painel, que é o lugar certo.
    """
    # A expressão é construída UMA vez e reusada no SELECT e no GROUP BY. Escrevê-la
    # duas vezes gera dois bind params distintos ($1 e $2), e o Postgres então trata as
    # duas como expressões diferentes e recusa com "must appear in the GROUP BY clause".
    categoria = func.coalesce(Produto.categoria, "Sem categoria")

    consulta = (
        select(
            categoria.label("categoria"),
            func.sum(ItemNota.valor_total).label("total_gasto"),
            func.count(ItemNota.id).label("n_itens"),
            func.count(func.distinct(Produto.id)).label("n_produtos"),
        )
        .select_from(ItemNota)
        .join(Produto, Produto.id == ItemNota.produto_id)
        .join(NotaFiscal, NotaFiscal.id == ItemNota.nota_id)
        .group_by(categoria)
        .order_by(func.sum(ItemNota.valor_total).desc())
    )

    resultado = await sessao.execute(_filtro_periodo(consulta, desde, ate))
    linhas = [
        {
            "categoria": linha.categoria,
            "total_gasto": float(linha.total_gasto or 0),
            "n_itens": int(linha.n_itens or 0),
            "n_produtos": int(linha.n_produtos or 0),
        }
        for linha in resultado
    ]

    # A fatia percentual é calculada aqui, e não no cliente, para que todas as telas
    # concordem sobre o denominador.
    total = sum(linha["total_gasto"] for linha in linhas) or 1.0
    for linha in linhas:
        linha["fatia"] = round(linha["total_gasto"] / total * 100, 1)

    return linhas


async def evolucao_por_categoria(
    sessao: AsyncSession,
    *,
    desde: date | None = None,
    ate: date | None = None,
    limite_categorias: int = 7,
) -> dict[str, object]:
    """Gasto por categoria, mês a mês, em formato pronto para barra empilhada.

    As categorias além de ``limite_categorias`` são somadas em "Outras". Isso não é
    economia de espaço: uma paleta categórica legível tem cerca de 8 cores, e gerar
    mais tons produz pares que ninguém distingue — muito menos quem tem daltonismo.
    Dobrar a cauda numa fatia só é o que mantém o gráfico honesto.
    """
    mes = _data_da_compra().label("mes")
    categoria = func.coalesce(Produto.categoria, "Sem categoria").label("categoria")

    consulta = (
        select(mes, categoria, func.sum(ItemNota.valor_total).label("total"))
        .select_from(ItemNota)
        .join(Produto, Produto.id == ItemNota.produto_id)
        .join(NotaFiscal, NotaFiscal.id == ItemNota.nota_id)
        .group_by(mes, categoria)
        .order_by(mes)
    )

    resultado = (await sessao.execute(_filtro_periodo(consulta, desde, ate))).all()

    def rotulo_mes(valor) -> str:
        return valor.date().isoformat() if hasattr(valor, "date") else str(valor)

    meses = sorted({rotulo_mes(linha.mes) for linha in resultado})

    total_por_categoria: dict[str, float] = {}
    for linha in resultado:
        total_por_categoria[linha.categoria] = total_por_categoria.get(
            linha.categoria, 0.0
        ) + float(linha.total or 0)

    ordenadas = sorted(total_por_categoria, key=total_por_categoria.get, reverse=True)
    principais = ordenadas[:limite_categorias]
    agrupar_em_outras = set(ordenadas[limite_categorias:])

    nomes = principais + (["Outras"] if agrupar_em_outras else [])
    valores: dict[str, dict[str, float]] = {nome: dict.fromkeys(meses, 0.0) for nome in nomes}

    for linha in resultado:
        nome = "Outras" if linha.categoria in agrupar_em_outras else linha.categoria
        valores[nome][rotulo_mes(linha.mes)] += float(linha.total or 0)

    return {
        "meses": meses,
        "categorias": [
            {
                "categoria": nome,
                "total": round(sum(valores[nome].values()), 2),
                "valores": [round(valores[nome][m], 2) for m in meses],
            }
            for nome in nomes
        ],
        "agrupadas_em_outras": sorted(agrupar_em_outras),
    }


async def produtos_da_categoria(
    sessao: AsyncSession,
    categoria: str,
    *,
    desde: date | None = None,
    ate: date | None = None,
) -> list[dict[str, object]]:
    """Produtos de uma categoria, do maior gasto para o menor — o detalhamento."""
    consulta = (
        select(
            Produto.id,
            Produto.nome,
            func.sum(ItemNota.valor_total).label("total_gasto"),
            func.count(ItemNota.id).label("n_compras"),
            func.avg(ItemNota.valor_unitario).label("preco_medio"),
        )
        .select_from(ItemNota)
        .join(Produto, Produto.id == ItemNota.produto_id)
        .join(NotaFiscal, NotaFiscal.id == ItemNota.nota_id)
        .where(func.coalesce(Produto.categoria, "Sem categoria") == categoria)
        .group_by(Produto.id, Produto.nome)
        .order_by(func.sum(ItemNota.valor_total).desc())
    )

    resultado = await sessao.execute(_filtro_periodo(consulta, desde, ate))
    return [
        {
            "produto_id": linha.id,
            "nome": linha.nome,
            "total_gasto": float(linha.total_gasto or 0),
            "n_compras": int(linha.n_compras or 0),
            "preco_medio": float(linha.preco_medio or 0),
        }
        for linha in resultado
    ]


async def _preco_e_quantidade_por_mes(
    sessao: AsyncSession,
) -> dict[str, dict[int, dict[str, float]]]:
    """``{mes: {produto_id: {nome, quantidade, preco, gasto}}}`` — base dos índices.

    O preço aqui é o **preço médio ponderado pelo volume** (gasto ÷ quantidade), não a
    média das linhas: comprar 0,2 kg a R$ 60 e 2 kg a R$ 40 tem preço médio de R$ 41,8
    e não R$ 50. Para um índice de preços a ponderação certa é a primeira.
    """
    mes = _data_da_compra().label("mes")
    consulta = (
        select(
            mes,
            Produto.id.label("produto_id"),
            Produto.nome.label("nome"),
            func.sum(ItemNota.quantidade).label("quantidade"),
            func.sum(ItemNota.valor_total).label("gasto"),
        )
        .select_from(ItemNota)
        .join(Produto, Produto.id == ItemNota.produto_id)
        .join(NotaFiscal, NotaFiscal.id == ItemNota.nota_id)
        .group_by(mes, Produto.id, Produto.nome)
    )

    por_mes: dict[str, dict[int, dict[str, float]]] = {}
    for linha in await sessao.execute(consulta):
        chave = (
            linha.mes.date().isoformat()
            if hasattr(linha.mes, "date")
            else str(linha.mes)
        )
        quantidade = float(linha.quantidade or 0)
        gasto = float(linha.gasto or 0)
        if quantidade <= 0:
            continue
        por_mes.setdefault(chave, {})[linha.produto_id] = {
            "nome": linha.nome,
            "quantidade": quantidade,
            "gasto": gasto,
            "preco": gasto / quantidade,
        }
    return por_mes


async def inflacao_cesta(sessao: AsyncSession) -> list[dict[str, object]]:
    """Índice de preços da **sua** cesta, de um mês para o outro.

    Por que não basta comparar o total gasto: o total mistura duas coisas diferentes —
    mudança de preço e mudança do que (e de quanto) você comprou. Gastar 10% mais pode
    ser inflação ou pode ser que você levou mais carne naquele mês.

    Este cálculo isola o preço. É um índice de Laspeyres: pega a cesta do mês-base
    (as quantidades que você realmente comprou) e a reavalia aos preços do mês seguinte.

        índice = Σ(quantidade_base × preço_novo) / Σ(quantidade_base × preço_base)

    Só entram produtos presentes nos **dois** meses — não há preço novo para comparar
    nos demais. Por isso vem acompanhado de ``cobertura``: a fatia do gasto do mês-base
    que o índice de fato representa. Um índice com 30% de cobertura diz pouco, e omitir
    esse número deixaria o resultado parecer mais sólido do que é.
    """
    por_mes = await _preco_e_quantidade_por_mes(sessao)
    meses = sorted(por_mes)
    resultado: list[dict[str, object]] = []

    for base, seguinte in zip(meses, meses[1:], strict=False):
        cesta_base = por_mes[base]
        cesta_nova = por_mes[seguinte]
        comuns = set(cesta_base) & set(cesta_nova)

        gasto_base_total = sum(p["gasto"] for p in cesta_base.values())
        if not comuns or gasto_base_total <= 0:
            continue

        custo_antigo = sum(
            cesta_base[i]["quantidade"] * cesta_base[i]["preco"] for i in comuns
        )
        custo_novo = sum(
            cesta_base[i]["quantidade"] * cesta_nova[i]["preco"] for i in comuns
        )
        if custo_antigo <= 0:
            continue

        variacao = (custo_novo / custo_antigo - 1) * 100

        # Contribuição de cada produto para a variação total, em pontos percentuais.
        # É o que responde "o que puxou o índice", em vez de só dar o número final.
        contribuicoes = sorted(
            (
                {
                    "produto_id": i,
                    "nome": cesta_base[i]["nome"],
                    "preco_base": round(cesta_base[i]["preco"], 2),
                    "preco_novo": round(cesta_nova[i]["preco"], 2),
                    "pontos_percentuais": round(
                        cesta_base[i]["quantidade"]
                        * (cesta_nova[i]["preco"] - cesta_base[i]["preco"])
                        / custo_antigo
                        * 100,
                        2,
                    ),
                }
                for i in comuns
            ),
            key=lambda c: abs(c["pontos_percentuais"]),
            reverse=True,
        )

        cobertura = custo_antigo / gasto_base_total * 100

        # A confiança vem da cobertura e do número de produtos comparados, e existe
        # para o número não ser lido com mais firmeza do que merece. Um mês em que
        # faltam notas produz cobertura baixa e poucos produtos em comum — o índice
        # então mede o acaso de quais notas existem, não o preço.
        if cobertura >= 60 and len(comuns) >= 25:
            confianca = "alta"
        elif cobertura >= 40 and len(comuns) >= 15:
            confianca = "media"
        else:
            confianca = "baixa"

        resultado.append(
            {
                "mes_base": base,
                "mes": seguinte,
                "variacao_percentual": round(variacao, 2),
                "cobertura": round(cobertura, 1),
                "confianca": confianca,
                "produtos_comparados": len(comuns),
                "produtos_no_mes_base": len(cesta_base),
                "maiores_altas": [
                    c for c in contribuicoes if c["pontos_percentuais"] > 0
                ][:5],
                "maiores_quedas": [
                    c for c in contribuicoes if c["pontos_percentuais"] < 0
                ][:5],
            }
        )

    return resultado


async def alertas_preco(
    sessao: AsyncSession, *, limite_percentual: float = 15.0, minimo_compras: int = 3
) -> list[dict[str, object]]:
    """Itens comprados acima do preço que você costuma pagar naquele produto.

    Compara o preço de cada item com a **mediana** das outras compras do mesmo produto
    — mediana e não média porque uma única compra atípica distorce a média e geraria
    alerta sobre si mesma.

    ``minimo_compras`` existe porque "o preço usual" não significa nada com uma ou duas
    observações: abaixo disso o alerta seria ruído com aparência de informação.
    """
    consulta = (
        select(
            ItemNota.id,
            ItemNota.produto_id,
            Produto.nome,
            ItemNota.descricao_origem,
            ItemNota.valor_unitario,
            ItemNota.unidade,
            NotaFiscal.id.label("nota_id"),
            _data_da_compra().label("mes"),
            func.coalesce(NotaFiscal.emitida_em, NotaFiscal.criado_em).label("data"),
        )
        .select_from(ItemNota)
        .join(Produto, Produto.id == ItemNota.produto_id)
        .join(NotaFiscal, NotaFiscal.id == ItemNota.nota_id)
    )

    linhas = (await sessao.execute(consulta)).all()

    por_produto: dict[int, list] = {}
    for linha in linhas:
        por_produto.setdefault(linha.produto_id, []).append(linha)

    alertas = []
    for itens in por_produto.values():
        if len(itens) < minimo_compras:
            continue

        for item in itens:
            # Mediana das OUTRAS compras: incluir a própria faria o item puxar o
            # referencial na direção dele e amortecer o próprio desvio.
            outros = sorted(
                float(o.valor_unitario) for o in itens if o.id != item.id
            )
            if len(outros) < 2:
                continue
            meio = len(outros) // 2
            usual = (
                outros[meio]
                if len(outros) % 2
                else (outros[meio - 1] + outros[meio]) / 2
            )
            if usual <= 0:
                continue

            atual = float(item.valor_unitario)
            desvio = (atual / usual - 1) * 100
            if desvio < limite_percentual:
                continue

            alertas.append(
                {
                    "item_id": item.id,
                    "nota_id": item.nota_id,
                    "produto_id": item.produto_id,
                    "nome": item.nome,
                    "descricao_origem": item.descricao_origem,
                    "unidade": item.unidade,
                    "preco_pago": round(atual, 2),
                    "preco_usual": round(usual, 2),
                    "acima_percentual": round(desvio, 1),
                    "data": item.data.date().isoformat() if item.data else None,
                    "n_compras": len(itens),
                }
            )

    return sorted(alertas, key=lambda a: a["acima_percentual"], reverse=True)


async def recorrencia_produtos(sessao: AsyncSession) -> dict[str, object]:
    """Separa o que você compra sempre do que foi compra de uma vez.

    Útil por dois motivos: os recorrentes são onde a variação de preço realmente pesa no
    orçamento, e os eventuais explicam picos de gasto que não são inflação.
    """
    mes = _data_da_compra().label("mes")
    consulta = (
        select(
            Produto.id,
            Produto.nome,
            Produto.categoria,
            func.count(func.distinct(mes)).label("meses"),
            func.count(ItemNota.id).label("compras"),
            func.sum(ItemNota.valor_total).label("gasto"),
        )
        .select_from(ItemNota)
        .join(Produto, Produto.id == ItemNota.produto_id)
        .join(NotaFiscal, NotaFiscal.id == ItemNota.nota_id)
        .group_by(Produto.id, Produto.nome, Produto.categoria)
    )

    total_meses = await sessao.scalar(
        select(func.count(func.distinct(_data_da_compra()))).select_from(NotaFiscal)
    )
    total_meses = int(total_meses or 0)

    recorrentes, frequentes, eventuais = [], [], []
    for linha in await sessao.execute(consulta):
        registro = {
            "produto_id": linha.id,
            "nome": linha.nome,
            "categoria": linha.categoria,
            "meses": int(linha.meses or 0),
            "compras": int(linha.compras or 0),
            "gasto": float(linha.gasto or 0),
        }
        if total_meses and registro["meses"] == total_meses:
            recorrentes.append(registro)
        elif total_meses and registro["meses"] >= max(2, total_meses / 2):
            frequentes.append(registro)
        else:
            eventuais.append(registro)

    ordenar = lambda lista: sorted(lista, key=lambda r: r["gasto"], reverse=True)  # noqa: E731

    return {
        "total_meses": total_meses,
        "recorrentes": ordenar(recorrentes),
        "frequentes": ordenar(frequentes),
        "eventuais": ordenar(eventuais)[:20],
        "gasto_recorrente": round(sum(r["gasto"] for r in recorrentes), 2),
        "gasto_eventual": round(sum(r["gasto"] for r in eventuais), 2),
    }


async def grupos_suspeitos(
    sessao: AsyncSession, *, fator_preco: float = 3.0
) -> list[dict[str, object]]:
    """Produtos que provavelmente agrupam coisas diferentes.

    Existe porque o erro mais custoso deste app é silencioso: agrupar dois produtos
    distintos sob o mesmo nome produz uma "variação de preço" que parece um insight e
    é só troca de formato. Aconteceu de verdade — chimichurri a granel somado a sachê
    de louro virou "queda de 90%".

    Dois sinais, ambos baratos de calcular:

    - **Unidades misturadas** (KG e UN no mesmo produto): venda por peso e por unidade
      não compartilham escala de preço. É o sinal mais forte, quase sempre um erro.
    - **Faixa de preço larga** (máximo ≥ ``fator_preco`` × mínimo): pode ser variação
      real — hortifruti oscila muito —, então isto é suspeita, não veredito.

    O que fazer com o resultado é decisão humana: separar a regra em
    ``services/classificacao.py``, ou aceitar que aquele produto varia mesmo.
    """
    consulta = (
        select(
            Produto.id,
            Produto.nome,
            Produto.categoria,
            func.count(ItemNota.id).label("n_itens"),
            func.count(func.distinct(ItemNota.unidade)).label("n_unidades"),
            func.string_agg(
                func.distinct(func.coalesce(ItemNota.unidade, "?")), literal("/")
            ).label("unidades"),
            func.min(ItemNota.valor_unitario).label("menor"),
            func.max(ItemNota.valor_unitario).label("maior"),
            func.count(func.distinct(ItemNota.descricao_origem)).label("n_descricoes"),
        )
        .select_from(ItemNota)
        .join(Produto, Produto.id == ItemNota.produto_id)
        .group_by(Produto.id, Produto.nome, Produto.categoria)
        .having(
            or_(
                func.count(func.distinct(ItemNota.unidade)) > 1,
                func.max(ItemNota.valor_unitario)
                >= func.min(ItemNota.valor_unitario) * fator_preco,
            )
        )
    )

    resultado = await sessao.execute(consulta)
    suspeitos = []
    for linha in resultado:
        menor = float(linha.menor or 0)
        maior = float(linha.maior or 0)
        motivos = []
        if (linha.n_unidades or 0) > 1:
            motivos.append(f"unidades misturadas ({linha.unidades})")
        if menor > 0 and maior / menor >= fator_preco:
            motivos.append(f"preço varia {maior / menor:.1f}×")

        suspeitos.append(
            {
                "produto_id": linha.id,
                "nome": linha.nome,
                "categoria": linha.categoria,
                "n_itens": int(linha.n_itens or 0),
                "n_descricoes": int(linha.n_descricoes or 0),
                "menor_preco": menor,
                "maior_preco": maior,
                "motivos": motivos,
                # Unidade misturada é quase sempre erro; faixa larga pode ser real.
                "gravidade": "alta" if (linha.n_unidades or 0) > 1 else "media",
            }
        )

    return sorted(
        suspeitos,
        key=lambda s: (s["gravidade"] != "alta", -(s["maior_preco"] / max(s["menor_preco"], 0.01))),
    )


async def totais_gerais(sessao: AsyncSession) -> dict[str, object]:
    """Números do topo do dashboard."""
    total_gasto = await sessao.scalar(
        select(func.coalesce(func.sum(ItemNota.valor_total), cast(literal(0), Numeric)))
    )
    n_notas = await sessao.scalar(select(func.count(NotaFiscal.id)))
    n_itens = await sessao.scalar(select(func.count(ItemNota.id)))
    n_produtos = await sessao.scalar(select(func.count(Produto.id)))
    itens_pendentes = await sessao.scalar(
        select(func.count(ItemNota.id)).where(ItemNota.produto_id.is_(None))
    )

    return {
        "total_gasto": float(total_gasto or 0),
        "n_notas": int(n_notas or 0),
        "n_itens": int(n_itens or 0),
        "n_produtos": int(n_produtos or 0),
        "itens_pendentes": int(itens_pendentes or 0),
    }
