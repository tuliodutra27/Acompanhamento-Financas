"""Testes de autenticação.

O foco é o que de fato protege dado: rota de dados sem sessão responde 401, e o atalho
de importação — que não pode usar cookie por vir de outro site — só passa com o token
certo.

Os testes não tocam o banco: as rotas escolhidas ou falham antes de consultar
(autenticação), ou falham logo depois por outro motivo (chave inválida). O `TestClient`
sobe com `raise_server_exceptions=False` para que uma falha de conexão vire status 500 e
não uma exceção que mascare o que se está medindo.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core import auth
from app.core.config import Settings

SENHA = "senha-de-teste"


def _cliente_com(monkeypatch, **campos) -> TestClient:
    """A configuração é `lru_cache`: trocar a variável de ambiente depois da primeira
    leitura não teria efeito. O que se substitui é a função `get_settings` inteira,
    dentro do módulo que a usa."""
    config = Settings(secret_key="chave-de-teste", **campos)
    monkeypatch.setattr("app.core.auth.get_settings", lambda: config)

    from app.main import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def cliente(monkeypatch):
    """App com senha configurada."""
    with _cliente_com(monkeypatch, auth_senha=SENHA) as cliente:
        yield cliente


@pytest.fixture
def cliente_aberto(monkeypatch):
    """App sem senha — o comportamento anterior à autenticação, que segue suportado."""
    with _cliente_com(monkeypatch, auth_senha="") as cliente:
        yield cliente


class TestPortaFechada:
    def test_rota_de_dados_sem_sessao_responde_401(self, cliente):
        resposta = cliente.get("/api/v1/analytics/totais")
        assert resposta.status_code == 401
        assert resposta.json()["erro"]["codigo"] == "NAO_AUTENTICADO"

    def test_health_continua_aberto(self, cliente):
        """A sonda do container não faz login — se exigisse, o Docker mataria o app."""
        assert cliente.get("/api/v1/health").status_code == 200

    def test_senha_errada_nao_cria_sessao(self, cliente):
        resposta = cliente.post("/api/v1/auth/login", json={"senha": "errada"})
        assert resposta.status_code == 401
        assert cliente.get("/api/v1/auth/sessao").json()["autenticado"] is False

    def test_login_correto_abre_as_rotas(self, cliente):
        assert cliente.post("/api/v1/auth/login", json={"senha": SENHA}).status_code == 200
        assert cliente.get("/api/v1/auth/sessao").json()["autenticado"] is True
        # Passou da autenticação: o que vier agora é problema de banco, não de sessão.
        assert cliente.get("/api/v1/analytics/totais").status_code != 401

    def test_logout_encerra_a_sessao(self, cliente):
        cliente.post("/api/v1/auth/login", json={"senha": SENHA})
        cliente.post("/api/v1/auth/logout")
        assert cliente.get("/api/v1/analytics/totais").status_code == 401


class TestAppSemSenha:
    def test_sem_senha_configurada_o_app_segue_aberto(self, cliente_aberto):
        estado = cliente_aberto.get("/api/v1/auth/sessao").json()
        assert estado == {"autenticado": True, "autenticacao_ativa": False}
        assert cliente_aberto.get("/api/v1/analytics/totais").status_code != 401

    def test_senha_vazia_nunca_autentica(self, monkeypatch):
        """Sem esta guarda, `auth_senha=""` casaria com uma senha vazia vinda de fora."""
        monkeypatch.setattr(
            "app.core.auth.get_settings", lambda: Settings(auth_senha="")
        )
        assert auth.senha_correta("") is False


class TestTokenDeImportacao:
    def test_atalho_sem_token_e_recusado(self, cliente):
        resposta = cliente.post("/api/v1/notas/importar-html", content="<html></html>")
        assert resposta.status_code == 401
        assert resposta.json()["erro"]["codigo"] == "NAO_AUTENTICADO"

    def test_token_errado_e_recusado(self, cliente):
        resposta = cliente.post(
            "/api/v1/notas/importar-html?token=" + "0" * 32, content="<html></html>"
        )
        assert resposta.status_code == 401

    def test_token_certo_passa_da_autorizacao(self, cliente):
        """Passa da porta: o 400 seguinte é sobre a página enviada, não a credencial."""
        resposta = cliente.post(
            f"/api/v1/notas/importar-html?token={auth.token_importacao()}",
            content="<html></html>",
        )
        assert resposta.status_code == 400
        assert resposta.json()["erro"]["codigo"] == "CHAVE_INVALIDA"

    def test_sessao_tambem_autoriza_a_importacao(self, cliente):
        """Importar de dentro do app, sem token — o cookie já basta na mesma origem."""
        cliente.post("/api/v1/auth/login", json={"senha": SENHA})
        resposta = cliente.post("/api/v1/notas/importar-html", content="<html></html>")
        assert resposta.status_code == 400

    def test_token_e_estavel_entre_chamadas(self, cliente):
        """Determinístico de propósito: o atalho instalado sobrevive a reinícios."""
        assert auth.token_importacao() == auth.token_importacao()

    def test_chave_secreta_diferente_gera_token_diferente(self, monkeypatch):
        """É assim que se revoga um atalho vazado: trocando a SECRET_KEY."""
        monkeypatch.setattr(
            "app.core.auth.get_settings", lambda: Settings(secret_key="uma")
        )
        primeiro = auth.token_importacao()
        monkeypatch.setattr(
            "app.core.auth.get_settings", lambda: Settings(secret_key="outra")
        )
        assert auth.token_importacao() != primeiro

    def test_token_de_importacao_exige_sessao(self, cliente):
        """Sem isto, qualquer um pegaria a credencial e passaria a inserir notas."""
        assert cliente.get("/api/v1/auth/token-importacao").status_code == 401
        cliente.post("/api/v1/auth/login", json={"senha": SENHA})
        resposta = cliente.get("/api/v1/auth/token-importacao")
        assert resposta.status_code == 200
        assert len(resposta.json()["token"]) == 32

    def test_atalho_recusado_por_formulario_tambem_responde_401(self, cliente):
        """O ramo de formulário devolve página legível, mas com o status certo — um 200
        numa falha some de qualquer log e de qualquer verificação automática."""
        resposta = cliente.post(
            "/api/v1/notas/importar-html",
            content="html=%3Chtml%3E%3C%2Fhtml%3E",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resposta.status_code == 401
        assert "Atalho não autorizado" in resposta.text
