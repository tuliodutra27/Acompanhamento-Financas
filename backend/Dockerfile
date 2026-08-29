# Backend: FastAPI + uvicorn
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# lxml precisa de libxml2/libxslt em runtime; o resto é wheel puro.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libxml2 libxslt1.1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    "fastapi>=0.115" \
    "uvicorn[standard]>=0.32" \
    "sqlalchemy>=2.0.36" \
    "asyncpg>=0.30" \
    "alembic>=1.14" \
    "pydantic>=2.9" \
    "pydantic-settings>=2.6" \
    "httpx>=0.28" \
    "beautifulsoup4>=4.12" \
    "lxml>=5.3" \
    "tenacity>=9.0" \
    "itsdangerous>=2.2"

COPY . .

EXPOSE 8000

# `start-period` generoso de propósito. Num boot frio do homelab (2 núcleos, HDD) todos
# os containers sobem juntos, a carga passa de 9, e o `alembic upgrade head` que roda
# antes do uvicorn levou ~3 minutos em 29/08/2026 — só de contenção de I/O, sem migration
# nova para aplicar. Com os 20s anteriores o container era marcado `unhealthy` bem antes
# de ter chance de responder, e `web` (que espera por `service_healthy`) ficava travado
# atrás disso. Durante o start-period a falha não conta, então isto não esconde defeito:
# só evita alarme falso enquanto o disco engasga.
HEALTHCHECK --interval=30s --timeout=5s --start-period=300s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

# Aplica as migrations antes de subir: é um app de um usuário, não há deploy
# coordenado nem janela de manutenção a respeitar.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
