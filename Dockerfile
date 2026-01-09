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
COPY requirements.txt ./
RUN pip install -U pip && pip install -U -r requirements.txt

COPY . /app
RUN chmod +x entrypoint.sh

# Ports for Hugging Face
EXPOSE 7860

CMD ["./entrypoint.sh"]
