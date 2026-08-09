"""Endpoints do catálogo pessoal de produtos e da fila de itens pendentes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.erros import NaoEncontrado, OperacaoInvalida
from app.models.item_nota import ItemNota
from app.models.nota_fiscal import NotaFiscal
from app.models.produto import Produto, ProdutoAlias
from app.schemas.produtos import (
    ItemPendente,
    ProdutoAtualizar,
    ProdutoComEstatisticas,
    ProdutoCriar,
    ProdutoLeitura,
    ProdutoMerge,
    SugestaoProduto,
)
from app.services.normalizacao import sugerir_produtos

router = APIRouter(tags=["produtos"])


@router.get("/produtos", response_model=list[ProdutoComEstatisticas])
async def listar_produtos(
    sessao: AsyncSession = Depends(get_session),
    q: str | None = Query(None, description="Busca por nome (parcial)"),
    limite: int = Query(100, ge=1, le=500),
) -> list[ProdutoComEstatisticas]:
    """Catálogo com estatísticas de uso — alimenta o autocomplete e a tela de gestão."""
    consulta = (
        select(
            Produto.id,
            Produto.nome,
            Produto.categoria,
            func.count(ItemNota.id).label("n_compras"),
            func.coalesce(func.sum(ItemNota.valor_total), 0).label("total_gasto"),
            func.coalesce(func.avg(ItemNota.valor_unitario), 0).label("preco_medio"),
        )
        .outerjoin(ItemNota, ItemNota.produto_id == Produto.id)
        .group_by(Produto.id, Produto.nome, Produto.categoria)
        .order_by(Produto.nome)
        .limit(limite)
    )
    if q:
        consulta = consulta.where(Produto.nome.ilike(f"%{q}%"))

    resultado = await sessao.execute(consulta)
    return [
        ProdutoComEstatisticas(
            id=linha.id,
            nome=linha.nome,
            categoria=linha.categoria,
            n_compras=int(linha.n_compras or 0),
            total_gasto=float(linha.total_gasto or 0),
            preco_medio=float(linha.preco_medio or 0),
        )
        for linha in resultado
    ]


@router.post("/produtos", response_model=ProdutoLeitura, status_code=201)
async def criar_produto(
    payload: ProdutoCriar, sessao: AsyncSession = Depends(get_session)
) -> ProdutoLeitura:
    produto = Produto(nome=payload.nome.strip(), categoria=payload.categoria)
    sessao.add(produto)
    await sessao.commit()
    await sessao.refresh(produto)
    return ProdutoLeitura.model_validate(produto)


@router.get("/produtos/sugestoes", response_model=list[SugestaoProduto])
async def sugestoes_para_descricao(
    descricao: str = Query(..., min_length=2),
    sessao: AsyncSession = Depends(get_session),
) -> list[SugestaoProduto]:
    """Produtos parecidos com uma descrição — usado antes de criar um produto novo.

    Evita a duplicata na origem: em vez de bloquear nomes repetidos (frágil em texto
    livre), a interface mostra "já existe algo parecido" e deixa o usuário decidir.
    """
    return [SugestaoProduto(**s) for s in await sugerir_produtos(sessao, descricao)]


@router.put("/produtos/{produto_id}", response_model=ProdutoLeitura)
async def atualizar_produto(
    produto_id: int,
    payload: ProdutoAtualizar,
    sessao: AsyncSession = Depends(get_session),
) -> ProdutoLeitura:
    produto = await sessao.get(Produto, produto_id)
    if produto is None:
        raise NaoEncontrado(f"Produto {produto_id} não encontrado.")

    if payload.nome is not None:
        produto.nome = payload.nome.strip()
    if payload.categoria is not None:
        produto.categoria = payload.categoria

    await sessao.commit()
    await sessao.refresh(produto)
    return ProdutoLeitura.model_validate(produto)


@router.post("/produtos/merge", response_model=ProdutoLeitura)
async def merge_produtos(
    payload: ProdutoMerge, sessao: AsyncSession = Depends(get_session)
) -> ProdutoLeitura:
    """Junta dois produtos que são o mesmo: itens e aliases migram, a origem é apagada.

    Sem isso, uma duplicata ("Arroz" e "Arroz 5kg" criados em momentos diferentes)
    quebraria o histórico de preço em duas séries pela metade.
    """
    if payload.origem_id == payload.destino_id:
        raise OperacaoInvalida("Origem e destino são o mesmo produto.")

    origem = await sessao.get(Produto, payload.origem_id)
    destino = await sessao.get(Produto, payload.destino_id)
    if origem is None:
        raise NaoEncontrado(f"Produto {payload.origem_id} não encontrado.")
    if destino is None:
        raise NaoEncontrado(f"Produto {payload.destino_id} não encontrado.")

    await sessao.execute(
        update(ItemNota)
        .where(ItemNota.produto_id == payload.origem_id)
        .values(produto_id=payload.destino_id)
    )

    # Aliases do destino que já existem venceriam o índice único; migrar só os que não
    # conflitam e descartar o resto (o vínculo já está representado no destino).
    aliases_origem = (
        await sessao.scalars(
            select(ProdutoAlias).where(ProdutoAlias.produto_id == payload.origem_id)
        )
    ).all()

    for alias in aliases_origem:
        conflito = None
        if alias.gtin:
            conflito = await sessao.scalar(
                select(ProdutoAlias.id).where(
                    ProdutoAlias.gtin == alias.gtin,
                    ProdutoAlias.produto_id == payload.destino_id,
                )
            )
        elif alias.descricao_normalizada:
            conflito = await sessao.scalar(
                select(ProdutoAlias.id).where(
                    ProdutoAlias.descricao_normalizada == alias.descricao_normalizada,
                    ProdutoAlias.produto_id == payload.destino_id,
                )
            )

        if conflito is None:
            alias.produto_id = payload.destino_id
        else:
            await sessao.delete(alias)

    await sessao.flush()
    await sessao.execute(delete(Produto).where(Produto.id == payload.origem_id))
    await sessao.commit()
    await sessao.refresh(destino)
    return ProdutoLeitura.model_validate(destino)


@router.get("/itens/pendentes", response_model=list[ItemPendente])
async def listar_itens_pendentes(
    sessao: AsyncSession = Depends(get_session),
    limite: int = Query(50, ge=1, le=200),
) -> list[ItemPendente]:
    """Itens sem produto vinculado, já com sugestões — a fila de revisão.

    Ordena pelos itens mais recentes: são os que o usuário lembra da compra e
    consegue classificar com menos esforço.
    """
    itens = (
        await sessao.scalars(
            select(ItemNota)
            .join(NotaFiscal, NotaFiscal.id == ItemNota.nota_id)
            .where(ItemNota.produto_id.is_(None))
            .order_by(
                func.coalesce(NotaFiscal.emitida_em, NotaFiscal.criado_em).desc(),
                ItemNota.id.desc(),
            )
            .limit(limite)
        )
    ).all()

    pendentes = []
    for item in itens:
        sugestoes = await sugerir_produtos(sessao, item.descricao_origem)
        pendentes.append(
            ItemPendente(
                item_id=item.id,
                nota_id=item.nota_id,
                descricao_origem=item.descricao_origem,
                gtin=item.gtin,
                valor_unitario=float(item.valor_unitario),
                sugestoes=[SugestaoProduto(**s) for s in sugestoes],
            )
        )
    return pendentes
