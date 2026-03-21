FROM corundex/comfyui-rocm:latest

USER root

RUN apt-get update && apt-get install -y wget curl && rm -rf /var/lib/apt/lists/*

COPY scripts/comfyui-entrypoint.sh /usr/local/bin/comfyui-entrypoint.sh
RUN chmod +x /usr/local/bin/comfyui-entrypoint.sh

USER runner

ENTRYPOINT ["/usr/local/bin/comfyui-entrypoint.sh"]
