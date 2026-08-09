"""Da chave escaneada/digitada até os itens no banco.

Roda síncrono dentro do request: é um usuário só, e o caminho automático é uma
requisição HTTP de poucos segundos. ``GET /notas/{id}`` já existe para polling, então
migrar isso para uma fila depois não muda o contrato da API.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import NotaBruta, ParseFalhou
from app.adapters.registry import adapter_para
from app.core.chave_nfce import ChaveInvalida, extrair_chave_do_qrcode, ler_chave
from app.core.erros import ChaveAcessoInvalida
from app.models.enums import MotivoFalha, OrigemEntrada, StatusNota
from app.models.estabelecimento import Estabelecimento
from app.models.item_nota import ItemNota
from app.models.nota_fiscal import NotaFiscal
from app.services.normalizacao import autovincular_itens

logger = logging.getLogger(__name__)

_MENSAGEM_CHAVE = {
    "formato": "A chave precisa ter 44 dígitos. Confira se copiou tudo.",
    "digito_verificador": (
        "A chave tem 44 dígitos mas o dígito verificador não fecha — provavelmente há "
        "um número trocado."
    ),
    "uf_desconhecida": "Os dois primeiros dígitos da chave não correspondem a um estado.",
    "modelo_nao_suportado": (
        "Esta chave não é de nota fiscal eletrônica (modelo 55/65)."
    ),
    "modelo_nao_e_nfce": "Esta chave não é de NFC-e (cupom de consumidor).",
}


def _eh_url(conteudo: str) -> bool:
    return "://" in (conteudo or "") or "?p=" in (conteudo or "")


async def registrar_nota(
    sessao: AsyncSession, *, conteudo: str, origem: OrigemEntrada
) -> tuple[NotaFiscal, bool]:
    """Registra a nota e tenta preenchê-la automaticamente.

    ``conteudo`` é o que o app leu: a URL completa do QR Code, ou a chave digitada.

    Devolve ``(nota, criada)`` — ``criada=False`` quando a chave já estava no banco,
    para a API responder 200 em vez de 201. Reenviar a mesma nota nunca duplica dado.
    """
    try:
        chave = extrair_chave_do_qrcode(conteudo)
        dados = ler_chave(chave)
    except ChaveInvalida as exc:
        raise ChaveAcessoInvalida(
            _MENSAGEM_CHAVE.get(exc.motivo, "Chave de acesso inválida."),
            {"motivo": exc.motivo},
        ) from exc

    existente = await sessao.scalar(
        select(NotaFiscal).where(NotaFiscal.chave_acesso == chave)
    )
    if existente is not None:
        return existente, False

    # A URL do QR Code é o que habilita o parse automático — guardá-la permite tentar
    # de novo depois (POST /notas/{id}/reprocessar) sem pedir o cupom outra vez.
    url_consulta = conteudo.strip() if _eh_url(conteudo) else None

    nota = NotaFiscal(
        chave_acesso=chave,
        uf=dados.uf,
        cnpj_emitente=dados.cnpj_emitente,
        ano_mes_chave=dados.ano_mes,
        origem_entrada=origem,
        url_consulta=url_consulta,
        status=StatusNota.pendente,
    )

    # O estabelecimento existe a partir da chave, mesmo sem parse: o CNPJ está lá.
    await garantir_estabelecimento(
        sessao, cnpj=dados.cnpj_emitente, uf=dados.uf
    )

    sessao.add(nota)
    await sessao.flush()

    await tentar_preencher(sessao, nota)
    await sessao.commit()
    await sessao.refresh(nota)
    return nota, True


async def tentar_preencher(sessao: AsyncSession, nota: NotaFiscal) -> None:
    """Tenta o parse automático e aplica o resultado na nota (sem commit).

    Nunca levanta exceção por falha de parse: falha é um estado válido da nota
    (``falhou_parse`` + ``erro_detalhe``), porque o preenchimento manual é um caminho
    previsto, não um erro do sistema.
    """
    adapter = adapter_para(nota.uf)
    if adapter is None:
        nota.status = StatusNota.falhou_parse
        nota.erro_detalhe = MotivoFalha.uf_nao_suportada.value
        return

    nota.adapter_usado = f"{adapter.nome}:{adapter.uf}"

    try:
        bruta = await adapter.buscar(nota.chave_acesso, nota.url_consulta)
    except ParseFalhou as exc:
        nota.status = StatusNota.falhou_parse
        nota.erro_detalhe = exc.motivo.value
        logger.info(
            "parse automático não concluído: chave=%s uf=%s motivo=%s detalhe=%s",
            nota.chave_acesso,
            nota.uf,
            exc.motivo.value,
            exc.detalhe,
        )
        return
    except Exception:  # noqa: BLE001 - blindagem: adapter nunca derruba a ingestão
        nota.status = StatusNota.falhou_parse
        nota.erro_detalhe = MotivoFalha.erro_inesperado.value
        logger.exception("erro inesperado no adapter da UF %s", nota.uf)
        return

    await _aplicar_nota_bruta(sessao, nota, bruta)


async def _aplicar_nota_bruta(
    sessao: AsyncSession, nota: NotaFiscal, bruta: NotaBruta
) -> None:
    """Grava o resultado de um parse bem-sucedido."""
    nota.emitida_em = bruta.emitida_em or nota.emitida_em
    nota.valor_total = bruta.valor_total or nota.valor_total
    nota.payload_bruto = bruta.payload_bruto
    nota.erro_detalhe = None

    if bruta.cnpj_emitente:
        nota.cnpj_emitente = bruta.cnpj_emitente

    await garantir_estabelecimento(
        sessao,
        cnpj=nota.cnpj_emitente,
        uf=bruta.uf or nota.uf,
        razao_social=bruta.nome_estabelecimento,
        municipio=bruta.municipio,
    )

    itens = [
        ItemNota(
            nota_id=nota.id,
            descricao_origem=item.descricao,
            gtin=item.gtin,
            quantidade=item.quantidade,
            unidade=item.unidade,
            valor_unitario=item.valor_unitario,
            valor_total=item.valor_total,
        )
        for item in bruta.itens
    ]
    sessao.add_all(itens)
    await sessao.flush()

    await autovincular_itens(sessao, itens)
    nota.status = StatusNota.ok


async def garantir_estabelecimento(
    sessao: AsyncSession,
    *,
    cnpj: str | None,
    uf: str | None,
    razao_social: str | None = None,
    municipio: str | None = None,
) -> None:
    """Cria ou completa o estabelecimento, sem sobrescrever dado já bom por vazio."""
    if not cnpj:
        return

    estabelecimento = await sessao.get(Estabelecimento, cnpj)
    if estabelecimento is None:
        sessao.add(
            Estabelecimento(
                cnpj=cnpj, uf=uf, razao_social=razao_social, municipio=municipio
            )
        )
        await sessao.flush()
        return

    if razao_social and not estabelecimento.razao_social:
        estabelecimento.razao_social = razao_social
    if municipio and not estabelecimento.municipio:
        estabelecimento.municipio = municipio
    if uf and not estabelecimento.uf:
        estabelecimento.uf = uf
