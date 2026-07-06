FROM python:3.14-slim

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

# Install Wireproxy
RUN curl -L -o wireproxy_linux_amd64.tar.gz https://github.com/whyvl/wireproxy/releases/download/v1.1.2/wireproxy_linux_amd64.tar.gz \
    && tar -xzf wireproxy_linux_amd64.tar.gz \
    && chmod +x wireproxy \
    && rm wireproxy_linux_amd64.tar.gz


# Install Python deps
COPY requirements-freez.txt ./
RUN pip install -U pip && pip install -U -r requirements-freez.txt
COPY . /app
RUN chmod +x entrypoint.sh
CMD ["./entrypoint.sh"]
