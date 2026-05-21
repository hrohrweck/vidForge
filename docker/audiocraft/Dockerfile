FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc g++ pkg-config \
    ffmpeg curl \
    libsndfile1-dev \
    libavformat-dev libavcodec-dev libavdevice-dev libavutil-dev \
    libavfilter-dev libswscale-dev libswresample-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install torch first (CPU-only), with matching torchvision
RUN pip install --no-cache-dir torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cpu

# Install audiocraft normally (will try to build av==11.0.0 which will fail)
# Then override av with a binary wheel version
RUN pip install --no-cache-dir --no-deps audiocraft && \
    pip install --no-cache-dir \
    av==13.0.0 \
    num2words spacy xformers einops \
    fancyimpute openunmix julius dora-search flashy docopt \
    encodec safetensors 'transformers>=4.31.0' huggingface-hub \
    datasets submitit torchmetrics tqdm blobfile colorama \
    packaging regex requests six pyyaml \
    antlr4-python3-runtime demucs larq stable-audio-tools \
    soundfile scipy sentencepiece tokenizers \
    protobuf sympy

COPY server.py .

ENV HF_HOME=/app/hf_cache
RUN mkdir -p /app/output /app/hf_cache

VOLUME /app/output
VOLUME /app/hf_cache

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

CMD ["python", "server.py"]
