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
    "tenacity>=9.0"

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

# Aplica as migrations antes de subir: é um app de um usuário, não há deploy
# coordenado nem janela de manutenção a respeitar.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
