FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ffmpeg \
       nano \
       openssh-client \
       openssh-server \
       tmux \
       git \
       wget \
       curl \
       less \
       sudo \
       rsync \
       software-properties-common \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY transcriber ./transcriber
COPY transtribir.py .
COPY run_transcriber.py .
COPY entrypoint.sh .
COPY .env.container ./.env

RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
