FROM rocm/dev-ubuntu-22.04:7.1.1-complete

USER root

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y software-properties-common && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y wget curl git python3.12 python3.12-venv python3.12-dev python3-pip && \
    rm -rf /var/lib/apt/lists/*

# Create venv
RUN python3.12 -m venv /opt/venv
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

# Install ComfyUI-LTXVideo custom nodes
RUN cd /workspace/ComfyUI/custom_nodes && \
    git clone https://github.com/Lightricks/ComfyUI-LTXVideo.git && \
    cd ComfyUI-LTXVideo && \
    pip install -r requirements.txt

COPY comfyui-entrypoint.sh /usr/local/bin/comfyui-entrypoint.sh
RUN chmod +x /usr/local/bin/comfyui-entrypoint.sh

RUN groupadd -r vidforge -g 1001 && \
    groupadd -g 992 hostrender 2>/dev/null || true && \
    useradd -r -u 1001 -g vidforge -G video,render,hostrender vidforge && \
    chown -R vidforge:vidforge /workspace

USER vidforge

WORKDIR /workspace/ComfyUI

ENTRYPOINT ["/usr/local/bin/comfyui-entrypoint.sh"]
