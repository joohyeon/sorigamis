FROM python:3.12-slim

WORKDIR /app

# Install system deps needed to build some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

# Install hermes-agent CLI from GitHub (PyPI only has <=0.15.2; we need 0.17.0+)
# Pin to a specific commit for reproducible builds. Bump this when upgrading Hermes.
RUN pip install --no-cache-dir \
    "git+https://github.com/NousResearch/hermes-agent.git@d40b5735a"

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install project deps (frozen, no dev, no project install yet)
RUN uv sync --frozen --no-dev --no-install-project

# Copy source
COPY . .

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
