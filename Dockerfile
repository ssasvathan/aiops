FROM python:3.13-slim

WORKDIR /app

# Install uv (pinned to match build-system constraint)
RUN pip install uv==0.9.21

# Build deps for psycopg[c] C extension
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY README.md ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev
# Copy only non-secret config artefacts; env files are injected at runtime via docker-compose
COPY config/denylist.yaml ./config/
COPY config/policies/ ./config/policies/

ENTRYPOINT ["uv", "run", "python", "-m", "aiops_triage_pipeline"]
CMD ["--mode", "hot-path"]
