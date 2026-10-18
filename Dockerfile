# Imagem de produção da Rede de Vendas: API FastAPI servindo também o frontend React compilado.
# Construir:  docker build -t rede-vendas .
# Rodar:      veja docker-compose.yml e docs/DEPLOY.md

# ---------- etapa 1: compila o frontend (Node só existe nesta etapa) ----------
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- etapa 2: imagem final, só com Python ----------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    REDE_VENDAS_DB=/dados/rede_vendas.db

WORKDIR /app

# Dependências primeiro (lidas do pyproject.toml): mudar só o código não refaz esta camada.
COPY pyproject.toml ./
RUN python -c "import tomllib; d = tomllib.load(open('pyproject.toml', 'rb')); \
print('\n'.join(d['project']['optional-dependencies']['api']))" > /tmp/requisitos.txt \
    && pip install -r /tmp/requisitos.txt

COPY rede_vendas/ rede_vendas/
COPY --from=frontend /app/frontend/dist frontend/dist

# Usuário sem privilégios; o banco fica num volume em /dados.
RUN useradd --system --uid 10001 --home /app rede \
    && mkdir -p /dados/backups \
    && chown -R rede:rede /dados
USER rede
VOLUME ["/dados"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/saude', timeout=4)"

# Um único worker: o SQLite e o limite de tentativas de login vivem num processo só.
# --proxy-headers: confia no Caddy para informar o IP real e o HTTPS.
CMD ["uvicorn", "rede_vendas.api:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
