FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-editable

COPY src/ src/
COPY router_registry/ router_registry/

FROM python:3.12-slim

RUN useradd --create-home appuser
WORKDIR /app

COPY --from=builder /app/.venv .venv
COPY --from=builder /app/src src/
COPY --from=builder /app/router_registry router_registry/
COPY alembic/ alembic/
COPY alembic.ini .

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD [".venv/bin/uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
