"""Autenticação de usuário único.

O app é pessoal e tem **um** usuário, então não há cadastro, papéis nem recuperação de
senha — isso seria complexidade sem ninguém para usá-la. O que existe é uma senha
guardada fora do código (variável de ambiente) e uma sessão em cookie assinado.

**A parte que exige cuidado é o atalho de importação.** Ele envia a nota a partir do
domínio da SEFAZ, ou seja, de outra origem. Um cookie de sessão com ``SameSite=Lax``
— o padrão sensato, que é o que protege contra CSRF — **não é enviado** num POST
entre sites. Havia duas saídas:

1. afrouxar o cookie para ``SameSite=None``, o que reabriria CSRF em todas as rotas;
2. dar ao atalho uma credencial própria, restrita a uma rota só.

A segunda é a escolhida. O token de importação é derivado da chave secreta por HMAC,
então não precisa de configuração extra nem de armazenamento, e vale exclusivamente
para ``POST /notas/importar-html``. Se vazar, o estrago possível é alguém **inserir**
uma nota — não ler o histórico, não apagar nada.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from fastapi import Request

from app.core.config import get_settings
from app.core.erros import ErroAplicacao

CHAVE_SESSAO = "autenticado"


class NaoAutenticado(ErroAplicacao):
    codigo = "NAO_AUTENTICADO"
    status_http = 401


def autenticacao_ativa() -> bool:
    """Só exige login quando há senha configurada.

    Sem isso, subir o app pela primeira vez (ou rodar os testes) exigiria configurar
    senha antes de qualquer coisa funcionar. Com senha vazia o app segue aberto, que é
    o comportamento que já existia — a diferença é que agora é uma escolha explícita.
    """
    return bool(get_settings().auth_senha)


def senha_correta(senha: str) -> bool:
    """Compara em tempo constante, para o tempo de resposta não vazar o prefixo certo."""
    esperada = get_settings().auth_senha
    if not esperada:
        return False
    return secrets.compare_digest(senha.encode("utf-8"), esperada.encode("utf-8"))


def token_importacao() -> str:
    """Credencial do atalho, derivada da chave secreta.

    Determinística de propósito: o atalho instalado no navegador continua valendo entre
    reinícios do container, sem precisar de tabela nem de nova configuração. Trocar a
    ``secret_key`` invalida o token — que é o jeito de revogá-lo.
    """
    return hmac.new(
        get_settings().secret_key.encode("utf-8"),
        b"importar-html",
        hashlib.sha256,
    ).hexdigest()[:32]


def token_importacao_valido(token: str | None) -> bool:
    if not token:
        return False
    return secrets.compare_digest(token, token_importacao())


def esta_autenticado(requisicao: Request) -> bool:
    if not autenticacao_ativa():
        return True
    return bool(requisicao.session.get(CHAVE_SESSAO))


async def exigir_sessao(requisicao: Request) -> None:
    """Dependência das rotas protegidas."""
    if not esta_autenticado(requisicao):
        raise NaoAutenticado("Faça login para acessar seus dados.")
