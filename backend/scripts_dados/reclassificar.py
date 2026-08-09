"""Aplica as regras de ``services/classificacao`` aos itens já no banco.

Quando usar:

- depois de ajustar as regras, para que as notas antigas passem a refletir o ajuste;
- para classificar de uma vez itens importados antes de as regras existirem.

Não contém nenhum dado de compra: lê as descrições do banco e decide por padrão. É o que
permite versionar este arquivo num repositório público — a versão anterior era uma tabela
com a lista literal de produtos comprados, o que publicaria o histórico de quem usa.

    # mostra o que faria, sem gravar nada
    docker compose run --rm --no-deps --entrypoint python backend \\
        scripts_dados/reclassificar.py --simular

    # classifica só os itens que estão sem produto (não toca no que já existe)
    docker compose run --rm --no-deps --entrypoint python backend \\
        scripts_dados/reclassificar.py

    # DESTRUTIVO: descarta a classificação atual e refaz tudo pelas regras
    docker compose run --rm --no-deps --entrypoint python backend \\
        scripts_dados/reclassificar.py --refazer
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

# Executado como script (`python scripts_dados/reclassificar.py`), o Python coloca a
# pasta do script em sys.path — não a raiz do projeto — e `import app` falha. Inserir a
# raiz aqui deixa o comando funcionar sem exigir PYTHONPATH na linha de invocação.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, func, select, text, update

from app.core.db import SessionLocal
from app.models.item_nota import ItemNota
from app.models.produto import Produto, ProdutoAlias
from app.services.classificacao import classificar
from app.services.normalizacao import (
    normalizar_descricao,
    obter_ou_criar_produto,
    registrar_alias,
)


async def simular() -> None:
    """Mostra como cada descrição distinta seria classificada, sem gravar nada."""
    async with SessionLocal() as sessao:
        descricoes = sorted(
            set((await sessao.scalars(select(ItemNota.descricao_origem))).all())
        )

    por_categoria: Counter[str] = Counter()
    sem_regra: list[str] = []

    for descricao in descricoes:
        achado = classificar(descricao)
        if achado is None:
            sem_regra.append(descricao)
            continue
        por_categoria[achado.categoria] += 1
        print(f"  {descricao[:24]:24} -> {achado.nome}  [{achado.categoria}]")

    print(f"\n{len(descricoes) - len(sem_regra)}/{len(descricoes)} descrições cobertas")
    for categoria, quantidade in por_categoria.most_common():
        print(f"  {categoria:22} {quantidade}")

    if sem_regra:
        print(f"\nSEM REGRA ({len(sem_regra)}) — ficariam na fila de revisão:")
        for descricao in sem_regra:
            print(f"  {descricao}")


async def aplicar(*, refazer: bool) -> None:
    async with SessionLocal() as sessao:
        if refazer:
            # Descarta a classificação atual inteira — inclusive ajustes manuais.
            # É o modo destrutivo; por isso exige a flag explícita.
            print("=== refazendo: descartando produtos e aliases atuais ===")
            await sessao.execute(update(ItemNota).values(produto_id=None))
            await sessao.execute(delete(ProdutoAlias))
            await sessao.execute(delete(Produto))
            await sessao.execute(text("ALTER SEQUENCE produto_id_seq RESTART WITH 1"))
            await sessao.flush()

        pendentes = (
            await sessao.scalars(
                select(ItemNota).where(ItemNota.produto_id.is_(None))
            )
        ).all()
        print(f"itens a classificar: {len(pendentes)}")

        vinculados = 0
        sem_regra: Counter[str] = Counter()

        for item in pendentes:
            achado = classificar(item.descricao_origem)
            if achado is None:
                sem_regra[item.descricao_origem] += 1
                continue

            produto = await obter_ou_criar_produto(
                sessao, achado.nome, achado.categoria
            )
            item.produto_id = produto.id
            if normalizar_descricao(item.descricao_origem):
                await registrar_alias(
                    sessao,
                    produto_id=produto.id,
                    gtin=item.gtin,
                    descricao=item.descricao_origem,
                )
            vinculados += 1

        await sessao.commit()

        total_produtos = await sessao.scalar(select(func.count(Produto.id)))
        total_categorias = await sessao.scalar(
            select(func.count(func.distinct(Produto.categoria)))
        )
        restantes = await sessao.scalar(
            select(func.count(ItemNota.id)).where(ItemNota.produto_id.is_(None))
        )

        print(f"itens vinculados: {vinculados}")
        print(f"produtos: {total_produtos} em {total_categorias} categorias")
        print(f"itens ainda sem produto: {restantes}")

        if sem_regra:
            print("\ndescrições sem regra (revisar na tela de Produtos):")
            for descricao, quantidade in sem_regra.most_common():
                print(f"  {quantidade}x  {descricao}")


def main() -> None:
    analisador = argparse.ArgumentParser(description=__doc__)
    analisador.add_argument(
        "--simular",
        action="store_true",
        help="mostra a classificação que seria aplicada, sem gravar",
    )
    analisador.add_argument(
        "--refazer",
        action="store_true",
        help="APAGA produtos e aliases atuais antes de reclassificar tudo",
    )
    argumentos = analisador.parse_args()

    if argumentos.simular:
        asyncio.run(simular())
    else:
        asyncio.run(aplicar(refazer=argumentos.refazer))


if __name__ == "__main__":
    main()
