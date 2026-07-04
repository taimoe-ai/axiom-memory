# Cloud Run image. Build: docker build -t axiom .
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_NO_CACHE=1

# Dependency layer first so code changes don't bust it.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# Cloud Run injects PORT; the CLI picks it up automatically.
CMD ["axiom", "serve", "--transport", "http", "--host", "0.0.0.0"]
