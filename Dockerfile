FROM python:3.13-slim

WORKDIR /app

# Install uv (pinned to match build-system constraint)
RUN pip install uv==0.9.21

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src/ ./src/
# Copy only non-secret config artefacts; env files are injected at runtime via docker-compose
COPY config/denylist.yaml ./config/
COPY config/policies/ ./config/policies/

ENTRYPOINT ["uv", "run", "python", "-m", "aiops_triage_pipeline"]
CMD ["--mode", "hot-path"]
