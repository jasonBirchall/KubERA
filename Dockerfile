FROM python:3.9-slim

WORKDIR /app

# Copy application code
COPY app.py k8s_assistant_persona.py ./

# Install dependencies directly
RUN pip install --no-cache-dir streamlit pandas matplotlib kubernetes openai

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

# Entrypoint to run the Streamlit app
ENTRYPOINT ["streamlit", "run", "app.py", "--server.address=0.0.0.0"]
