"""Endpoints de notas fiscais e seus itens."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.urls_uf import url_consulta_manual
from app.core.db import get_session
from app.core.erros import NaoEncontrado, OperacaoInvalida
from app.models.enums import StatusNota
from app.models.item_nota import ItemNota
from app.models.nota_fiscal import NotaFiscal
from app.models.produto import Produto
from app.schemas.notas import (
    EstabelecimentoAtualizar,
    ItemAtualizar,
    ItemCriar,
    ItemLeitura,
    NotaAtualizar,
    NotaCriar,
    NotaDetalhe,
    NotaResumo,
    VincularProduto,
)
from app.services.ingestao import registrar_nota, tentar_preencher
from app.services.normalizacao import encontrar_produto_por_alias, registrar_alias

router = APIRouter(prefix="/notas", tags=["notas"])


def _para_item_leitura(item: ItemNota) -> ItemLeitura:
    return ItemLeitura(
        id=item.id,
        produto_id=item.produto_id,
        produto_nome=item.produto.nome if item.produto else None,
        descricao_origem=item.descricao_origem,
        gtin=item.gtin,
        quantidade=item.quantidade,
        unidade=item.unidade,
        valor_unitario=item.valor_unitario,
        valor_total=item.valor_total,
    )


def _para_detalhe(nota: NotaFiscal) -> NotaDetalhe:
    return NotaDetalhe(
        id=nota.id,
        chave_acesso=nota.chave_acesso,
        uf=nota.uf,
        ano_mes_chave=nota.ano_mes_chave,
        emitida_em=nota.emitida_em,
        valor_total=nota.valor_total,
        status=nota.status,
        origem_entrada=nota.origem_entrada,
        erro_detalhe=nota.erro_detalhe,
        cnpj_emitente=nota.cnpj_emitente,
        adapter_usado=nota.adapter_usado,
        url_consulta=nota.url_consulta,
        url_portal_uf=url_consulta_manual(nota.uf),
        n_itens=len(nota.itens),
        estabelecimento_nome=(
            nota.estabelecimento.nome_exibicao if nota.estabelecimento else None
        ),
        itens=[_para_item_leitura(item) for item in nota.itens],
    )


async def _buscar_nota(sessao: AsyncSession, nota_id: int) -> NotaFiscal:
    nota = await sessao.get(NotaFiscal, nota_id)
    if nota is None:
        raise NaoEncontrado(f"Nota {nota_id} não encontrada.")
    return nota


async def _buscar_item(sessao: AsyncSession, nota_id: int, item_id: int) -> ItemNota:
    item = await sessao.get(ItemNota, item_id)
    if item is None or item.nota_id != nota_id:
        raise NaoEncontrado(f"Item {item_id} não encontrado na nota {nota_id}.")
    return item


async def _resolver_produto(
    sessao: AsyncSession, produto_id: int | None, novo_nome: str | None
) -> Produto | None:
    """Produto existente pelo id, ou um novo criado a partir do nome."""
    if produto_id is not None:
        produto = await sessao.get(Produto, produto_id)
        if produto is None:
            raise NaoEncontrado(f"Produto {produto_id} não encontrado.")
        return produto

    if novo_nome:
        produto = Produto(nome=novo_nome.strip())
        sessao.add(produto)
        await sessao.flush()
        return produto

    return None


@router.post("", response_model=NotaDetalhe)
async def criar_nota(
    payload: NotaCriar, resposta: Response, sessao: AsyncSession = Depends(get_session)
) -> NotaDetalhe:
    """Registra uma nota a partir do QR Code ou da chave, e tenta preenchê-la.

    Idempotente por chave de acesso: reenviar o mesmo cupom devolve a nota que já
    existe (200) em vez de duplicar (201).
    """
    nota, criada = await registrar_nota(
        sessao, conteudo=payload.conteudo, origem=payload.origem
    )
    resposta.status_code = status.HTTP_201_CREATED if criada else status.HTTP_200_OK
    return _para_detalhe(nota)


@router.get("", response_model=list[NotaResumo])
async def listar_notas(
    sessao: AsyncSession = Depends(get_session),
    status_filtro: StatusNota | None = Query(None, alias="status"),
    uf: str | None = Query(None, min_length=2, max_length=2),
    desde: date | None = None,
    limite: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[NotaResumo]:
    contagem_itens = (
        select(ItemNota.nota_id, func.count().label("n"))
        .group_by(ItemNota.nota_id)
        .subquery()
    )

    consulta = (
        select(NotaFiscal, func.coalesce(contagem_itens.c.n, 0).label("n_itens"))
        .outerjoin(contagem_itens, contagem_itens.c.nota_id == NotaFiscal.id)
        .order_by(
            func.coalesce(NotaFiscal.emitida_em, NotaFiscal.criado_em).desc(),
            NotaFiscal.id.desc(),
        )
        .limit(limite)
        .offset(offset)
    )
    if status_filtro is not None:
        consulta = consulta.where(NotaFiscal.status == status_filtro)
    if uf:
        consulta = consulta.where(NotaFiscal.uf == uf.upper())
    if desde is not None:
        consulta = consulta.where(
            func.coalesce(NotaFiscal.emitida_em, NotaFiscal.criado_em) >= desde
        )

    resultado = await sessao.execute(consulta)
    return [
        NotaResumo(
            id=nota.id,
            chave_acesso=nota.chave_acesso,
            uf=nota.uf,
            ano_mes_chave=nota.ano_mes_chave,
            emitida_em=nota.emitida_em,
            valor_total=nota.valor_total,
            status=nota.status,
            origem_entrada=nota.origem_entrada,
            erro_detalhe=nota.erro_detalhe,
            n_itens=n_itens,
            estabelecimento_nome=(
                nota.estabelecimento.nome_exibicao if nota.estabelecimento else None
            ),
        )
        for nota, n_itens in resultado
    ]


@router.get("/{nota_id}", response_model=NotaDetalhe)
async def obter_nota(
    nota_id: int, sessao: AsyncSession = Depends(get_session)
) -> NotaDetalhe:
    return _para_detalhe(await _buscar_nota(sessao, nota_id))


@router.patch("/{nota_id}", response_model=NotaDetalhe)
async def atualizar_nota(
    nota_id: int, payload: NotaAtualizar, sessao: AsyncSession = Depends(get_session)
) -> NotaDetalhe:
    """Completa data de emissão e valor total no preenchimento manual."""
    nota = await _buscar_nota(sessao, nota_id)

    if payload.emitida_em is not None:
        nota.emitida_em = payload.emitida_em
    if payload.valor_total is not None:
        nota.valor_total = payload.valor_total

    await sessao.commit()
    await sessao.refresh(nota)
    return _para_detalhe(nota)


@router.post("/{nota_id}/reprocessar", response_model=NotaDetalhe)
async def reprocessar_nota(
    nota_id: int, sessao: AsyncSession = Depends(get_session)
) -> NotaDetalhe:
    """Tenta o parse automático de novo.

    Bloqueado quando a nota já tem itens: o parse sobrescreveria trabalho manual do
    usuário, que é justamente o dado mais caro de reproduzir aqui.
    """
    nota = await _buscar_nota(sessao, nota_id)

    if nota.itens:
        raise OperacaoInvalida(
            "Esta nota já tem itens. Reprocessar apagaria o que foi preenchido — "
            "remova os itens antes, se realmente quiser tentar de novo.",
            {"n_itens": len(nota.itens)},
        )

    await tentar_preencher(sessao, nota)
    await sessao.commit()
    await sessao.refresh(nota)
    return _para_detalhe(nota)


@router.put("/{nota_id}/estabelecimento", response_model=NotaDetalhe)
async def atualizar_estabelecimento(
    nota_id: int,
    payload: EstabelecimentoAtualizar,
    sessao: AsyncSession = Depends(get_session),
) -> NotaDetalhe:
    """Preenche/corrige o nome da loja (o CNPJ vem da chave, o nome não)."""
    nota = await _buscar_nota(sessao, nota_id)
    if nota.estabelecimento is None:
        raise OperacaoInvalida("Esta nota não tem CNPJ de emitente registrado.")

    if payload.razao_social is not None:
        nota.estabelecimento.razao_social = payload.razao_social
    if payload.nome_fantasia is not None:
        nota.estabelecimento.nome_fantasia = payload.nome_fantasia
    if payload.municipio is not None:
        nota.estabelecimento.municipio = payload.municipio

    await sessao.commit()
    await sessao.refresh(nota)
    return _para_detalhe(nota)


@router.post("/{nota_id}/itens", response_model=ItemLeitura, status_code=201)
async def adicionar_item(
    nota_id: int, payload: ItemCriar, sessao: AsyncSession = Depends(get_session)
) -> ItemLeitura:
    """Adiciona um item à mão — o caminho quando o parse automático não passou."""
    nota = await _buscar_nota(sessao, nota_id)

    if payload.valor_unitario is None and payload.valor_total is None:
        raise OperacaoInvalida("Informe o valor unitário ou o valor total do item.")

    valor_unitario = payload.valor_unitario
    valor_total = payload.valor_total
    if valor_unitario is None:
        assert valor_total is not None  # garantido pela validação acima
        valor_unitario = (valor_total / payload.quantidade).quantize(Decimal("0.0001"))
    if valor_total is None:
        valor_total = (valor_unitario * payload.quantidade).quantize(Decimal("0.01"))

    produto = await _resolver_produto(
        sessao, payload.produto_id, payload.novo_produto_nome
    )
    produto_id = produto.id if produto else None

    # Sem produto informado, tenta o vínculo por alias antes de deixar pendente.
    # Isto é essencial e não um detalhe: a entrada manual é o caminho mais comum do
    # app, e sem esta busca a "memória" dos aliases só serviria ao parse automático —
    # o usuário reclassificaria o mesmo arroz em cada nota.
    if produto_id is None:
        produto_id = await encontrar_produto_por_alias(
            sessao, gtin=payload.gtin, descricao=payload.descricao_origem
        )

    item = ItemNota(
        nota_id=nota.id,
        produto_id=produto_id,
        descricao_origem=payload.descricao_origem.strip(),
        gtin=payload.gtin,
        quantidade=payload.quantidade,
        unidade=payload.unidade,
        valor_unitario=valor_unitario,
        valor_total=valor_total,
    )
    sessao.add(item)

    if produto_id is not None:
        # Idempotente: se o vínculo veio da descrição e agora há GTIN, o alias de
        # GTIN é acrescentado — a próxima nota casa pelo caminho mais confiável.
        await registrar_alias(
            sessao,
            produto_id=produto_id,
            gtin=payload.gtin,
            descricao=payload.descricao_origem,
        )

    # A nota passa a "manual": os itens são responsabilidade do usuário agora.
    nota.status = StatusNota.manual
    await sessao.commit()
    await sessao.refresh(item)
    return _para_item_leitura(item)


@router.put("/{nota_id}/itens/{item_id}", response_model=ItemLeitura)
async def atualizar_item(
    nota_id: int,
    item_id: int,
    payload: ItemAtualizar,
    sessao: AsyncSession = Depends(get_session),
) -> ItemLeitura:
    item = await _buscar_item(sessao, nota_id, item_id)

    for campo, valor in payload.model_dump(exclude_unset=True).items():
        if valor is not None:
            setattr(item, campo, valor)

    # Recalcula o total se a quantidade ou o unitário mudaram e o total não veio.
    if payload.valor_total is None and (
        payload.quantidade is not None or payload.valor_unitario is not None
    ):
        item.valor_total = (item.valor_unitario * item.quantidade).quantize(
            Decimal("0.01")
        )

    await sessao.commit()
    await sessao.refresh(item)
    return _para_item_leitura(item)


@router.delete("/{nota_id}/itens/{item_id}", status_code=204)
async def remover_item(
    nota_id: int, item_id: int, sessao: AsyncSession = Depends(get_session)
) -> None:
    item = await _buscar_item(sessao, nota_id, item_id)
    await sessao.delete(item)
    await sessao.commit()


@router.post("/{nota_id}/itens/{item_id}/vincular", response_model=ItemLeitura)
async def vincular_item(
    nota_id: int,
    item_id: int,
    payload: VincularProduto,
    sessao: AsyncSession = Depends(get_session),
) -> ItemLeitura:
    """Vincula o item a um produto (existente ou novo) e memoriza o vínculo.

    O alias gravado é o que faz a próxima nota com esse mesmo item ser vinculada
    automaticamente, sem perguntar de novo.
    """
    item = await _buscar_item(sessao, nota_id, item_id)

    produto = await _resolver_produto(
        sessao, payload.produto_id, payload.novo_produto_nome
    )
    if produto is None:
        raise OperacaoInvalida(
            "Informe produto_id (produto existente) ou novo_produto_nome."
        )

    item.produto_id = produto.id
    await registrar_alias(
        sessao,
        produto_id=produto.id,
        gtin=item.gtin,
        descricao=item.descricao_origem,
    )

    await sessao.commit()
    await sessao.refresh(item)
    return _para_item_leitura(item)
