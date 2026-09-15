FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN addgroup --system bot && adduser --system --ingroup bot bot

COPY pyproject.toml README.md alembic.ini ./
COPY app ./app
COPY admin ./admin
COPY config ./config
COPY scripts ./scripts
COPY deploy ./deploy

RUN pip install --no-cache-dir . && chown -R bot:bot /app

USER bot

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
