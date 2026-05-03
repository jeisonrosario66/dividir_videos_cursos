FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

LABEL org.opencontainers.image.title="srt-translator-openai" \
      org.opencontainers.image.description="Traductor de subtitulos SRT al espanol con contexto BJJ, OpenAI API y modo Batch para optimizar costo." \
      org.opencontainers.image.version="0.1"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       nano \
       curl \
       ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY translator ./translator
COPY run_translator.py .
COPY translate_srt.py .
COPY entrypoint.sh .
COPY .env.container ./.env
COPY glossary_bjj.txt .

RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
