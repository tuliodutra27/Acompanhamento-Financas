"""Enums persistidos no banco (tipos ENUM do Postgres)."""

from __future__ import annotations

import enum


class StatusNota(str, enum.Enum):
    """Em que ponto do ciclo de ingestão a nota está.

    - ``pendente``: registrada, parse automático ainda não concluído.
    - ``ok``: itens vieram do parse automático do portal da SEFAZ.
    - ``falhou_parse``: o portal bloqueou/mudou/não respondeu — aguardando o usuário
      preencher os itens à mão.
    - ``manual``: os itens foram informados (ou corrigidos) pelo usuário.
    """

    pendente = "pendente"
    ok = "ok"
    falhou_parse = "falhou_parse"
    manual = "manual"


class OrigemEntrada(str, enum.Enum):
    """Como a chave de acesso entrou no app."""

    qrcode = "qrcode"
    chave_manual = "chave_manual"


class MotivoFalha(str, enum.Enum):
    """Por que o parse automático não funcionou.

    Gravado em ``nota_fiscal.erro_detalhe``. Vale distinguir os motivos porque eles
    levam a decisões diferentes: ``captcha`` significa "não insista, esse estado não
    é automatizável"; ``layout_mudou`` significa "o adapter precisa de manutenção".
    """

    captcha = "captcha"
    bloqueio = "bloqueio"
    layout_mudou = "layout_mudou"
    timeout = "timeout"
    uf_nao_suportada = "uf_nao_suportada"
    erro_inesperado = "erro_inesperado"
    # A chave foi digitada em vez de escaneada. A consulta por chave nos portais da
    # SEFAZ passa por um formulário com reCAPTCHA — não é automatizável. Só a URL do
    # QR Code carrega o hash assinado que abre a nota direto. Ver adapters/README.
    sem_url_qrcode = "sem_url_qrcode"
