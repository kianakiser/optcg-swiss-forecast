# Build with --platform linux/amd64; Hopsworks' Delta client has no Linux ARM64 wheel.
FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.12.16 /uv /usr/local/bin/uv
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY src/ src/
COPY config/ config/

RUN useradd --create-home --uid 10001 app \
    && mkdir data \
    && chown app:app data
USER app

ENTRYPOINT ["python", "src/optcg/features/run.py"]
CMD ["--help"]
