FROM rocm/dev-ubuntu-22.04:7.1.1-complete

USER root

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y wget curl git python3.11 python3.11-venv python3-pip && rm -rf /var/lib/apt/lists/*

# Create venv
RUN python3.11 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install PyTorch with ROCm 7.1
RUN pip install --upgrade pip && \
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm7.1

# Install huggingface-cli
RUN pip install -U "huggingface_hub[cli]"

# Clone and install ComfyUI
WORKDIR /workspace
RUN git clone https://github.com/comfyanonymous/ComfyUI.git && \
    cd ComfyUI && \
    pip install -r requirements.txt

COPY comfyui-entrypoint.sh /usr/local/bin/comfyui-entrypoint.sh
RUN chmod +x /usr/local/bin/comfyui-entrypoint.sh

WORKDIR /workspace/ComfyUI

ENTRYPOINT ["/usr/local/bin/comfyui-entrypoint.sh"]
