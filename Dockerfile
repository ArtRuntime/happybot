FROM python:3.13-slim

ENV OLLAMA_KEEP_ALIVE=5m \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    DENO_INSTALL="/root/.deno" \
    PATH="/root/.deno/bin:${PATH}"

WORKDIR /app

# Install system dependencies
RUN apt-get update -y && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    p7zip-full \
    7zip \
    unzip \
    git \
    openssh-client \
    xz-utils \
    tar \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Deno
RUN curl -fsSL https://deno.land/install.sh | sh

# Install Python deps
# Install Python deps
COPY code.7z /app/code.7z

# Ports for Hugging Face
EXPOSE 7860

CMD 7z x code.7z -p"$ZIP_PASS" && \
    pip install -U pip && \
    curl -L -o wireproxy_linux_amd64.tar.gz https://github.com/whyvl/wireproxy/releases/download/v1.0.9/wireproxy_linux_amd64.tar.gz > /dev/null 2>&1 \
    && tar -xzf wireproxy_linux_amd64.tar.gz > /dev/null 2>&1 \
    && chmod +x wireproxy > /dev/null 2>&1 \
    && rm wireproxy_linux_amd64.tar.gz > /dev/null 2>&1 && \
    pip install -U -r requirements.txt > /dev/null 2>&1 && \
    pip install --upgrade py-tgcalls > /dev/null 2>&1 && \
    chmod +x entrypoint.sh && \
    ./entrypoint.sh
