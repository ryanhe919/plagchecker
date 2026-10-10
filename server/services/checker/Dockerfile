FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY checker ./checker
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
ENV PATH="/app/.venv/bin:${PATH}" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_THREAD_LIMIT=2
WORKDIR /app
COPY --from=builder /app/.venv ./.venv
COPY --from=builder /app/checker ./checker
RUN groupadd --system app && useradd --system --gid app --home-dir /app app \
    && mkdir -p /data/jobs && chown app:app /data/jobs
USER app
EXPOSE 8000
CMD ["uvicorn", "checker.api:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
