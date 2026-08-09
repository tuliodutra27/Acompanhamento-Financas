"""Configuração da aplicação, lida do ambiente (12-factor)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_nome: str = "Acompanhamento de Finanças"
    ambiente: str = "development"

    database_url: str = (
        "postgresql+asyncpg://financas:financas@localhost:5432/financas"
    )

    # Origens permitidas em dev (o Vite roda em porta separada). Em produção o
    # frontend é servido no mesmo host, então CORS não é necessário.
    cors_origens: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Tempo máximo esperando o portal da SEFAZ responder, por tentativa de parse.
    timeout_adapter_segundos: float = 10.0

    # Quantos dias guardar o HTML bruto da consulta — serve para depurar mudança de
    # layout do portal sem ter que reproduzir a falha.
    retencao_payload_bruto_dias: int = 30

    # User-Agent honesto e identificável nas consultas aos portais públicos.
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
