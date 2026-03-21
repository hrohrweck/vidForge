FROM ollama/ollama:rocm

USER root

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY scripts/ollama-entrypoint.sh /usr/local/bin/ollama-entrypoint.sh
RUN chmod +x /usr/local/bin/ollama-entrypoint.sh

USER ollama

ENTRYPOINT ["/usr/local/bin/ollama-entrypoint.sh"]
