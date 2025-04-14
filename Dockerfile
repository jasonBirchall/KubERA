FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

# Copy just the dependency files first for better caching
COPY pyproject.toml uv.lock ./

# Install dependencies only (without installing the project)
# This creates a separate layer for dependencies which changes less frequently
RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --frozen --no-install-project

# Copy application code
COPY app.py k8s_assistant_persona.py ./

# Sync the project (install the project itself)
RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --frozen

# Install kubectl
RUN apt-get update && \
  apt-get install -y curl && \
  curl -LO "https://dl.k8s.io/release/stable.txt" && \
  curl -LO "https://dl.k8s.io/release/$(cat stable.txt)/bin/linux/amd64/kubectl" && \
  chmod +x kubectl && \
  mv kubectl /usr/local/bin/ && \
  rm stable.txt && \
  apt-get clean && \
  rm -rf /var/lib/apt/lists/*

# Expose the Streamlit port
EXPOSE 8501

# Start the Streamlit app using uv run
ENTRYPOINT ["uv", "run", "streamlit", "run", "app.py", "--server.address=0.0.0.0"]
