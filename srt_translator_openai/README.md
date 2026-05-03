# Traductor de SRT a Espanol con OpenAI

Este microproyecto traduce carpetas de subtitulos `.srt` al espanol con un contexto claro de BJJ y con foco fuerte en **eficiencia de costo**.

## Objetivo

- tomar una carpeta de `.srt`
- recorrer subcarpetas
- generar una carpeta espejo traducida al espanol
- minimizar costo en OpenAI

## Estrategia de eficiencia

La herramienta intenta ahorrar dinero de varias formas:

- **Batch API** como flujo recomendado
  - OpenAI documenta que Batch ofrece **50% de descuento** frente a llamadas sincronas y un pool separado de rate limits:
    - https://platform.openai.com/docs/guides/batch
    - https://platform.openai.com/docs/pricing/
- **Chunking por segmentos**
  - no manda un request por subtitulo
  - agrupa muchos segmentos en un solo request
- **Deduplicacion**
  - si dos chunks tienen exactamente el mismo contenido/prompt, solo prepara una solicitud
- **Cache local**
  - guarda respuestas por hash para no retraducir lo mismo
- **Timestamps locales**
  - no gasta tokens mandando tiempos; solo traduce texto e indices
- **Structured Outputs**
  - usa salida estructurada JSON para evitar retries por formato invalido:
    - https://platform.openai.com/docs/guides/structured-outputs?api-mode=responses&lang=python
- **Prompt corto**
  - el prompt base se compacta para no repetir instrucciones largas innecesarias
- **Glosario filtrado por chunk**
  - ya no manda las mas de 500 lineas del glosario en cada request
  - manda solo las entradas relevantes al texto actual, con un maximo configurable
- **Mejor deduplicacion**
  - ya no incluye `relative_path` ni `chunk_id` dentro del payload enviado al modelo
  - si dos chunks tienen el mismo texto, pueden reutilizar cache aunque vengan de archivos distintos

## Recomendacion de modelo

Por defecto usa:

- `gpt-4o-mini`

Lo elegi porque:

- soporta Structured Outputs segun la documentacion oficial
- es mucho mas barato que modelos grandes
- para traduccion de subtitulos suele dar una relacion calidad/costo muy buena

Si quieres mas calidad y aceptas mas costo, puedes cambiar `OPENAI_MODEL`.

## Estructura

- `translator/`: logica principal
- `translate_srt.py`: CLI directa
- `run_translator.py`: runner que usa `.env`
- `glossary_bjj.txt`: glosario base BJJ
- `Dockerfile`: contenedor

## Instalacion local

```bash
cd srt_translator_openai
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Variables importantes

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
INPUT_DIR=/ruta/a/srt_original
OUTPUT_DIR=/ruta/a/srt_es
WORK_DIR=
TRANSLATION_MODE=batch
OVERWRITE=false
CHUNK_MAX_CHARS=4500
MAX_SEGMENTS_PER_CHUNK=80
MAX_GLOSSARY_LINES_PER_CHUNK=60
TARGET_LANGUAGE=es
GLOSSARY_PATH=/app/glossary_bjj.txt
COURSE_CONTEXT=BJJ instructional subtitles. Preserve technique names and translate naturally to Latin American Spanish.
```

Si dejas vacio `WORK_DIR`, el proyecto usa `./work` dentro de `srt_translator_openai/`.

Si dejas vacios:

- `BATCH_REQUESTS_PATH`
- `BATCH_RESULTS_PATH`
- `BATCH_MANIFEST_PATH`

entonces usa automaticamente archivos dentro de `WORK_DIR`.

## Flujo simple de uso

### Opcion 1: traduccion inmediata

Si quieres traducir y obtener salida enseguida:

```bash
cd srt_translator_openai
TRANSLATION_MODE=sync python3 run_translator.py
```

Esto:

- recorre `INPUT_DIR` de forma recursiva
- traduce todo lo pendiente
- escribe directamente en `OUTPUT_DIR`

Si quieres el modo mas eficiente hoy, esta es mi recomendacion:

- `TRANSLATION_MODE=sync`
- `OPENAI_MODEL=gpt-4o-mini`
- `MAX_GLOSSARY_LINES_PER_CHUNK=40` o `60`
- deja `OVERWRITE=false`

En la practica, `sync` mas cache y glosario filtrado suele ser mucho mas estable para ti ahora mismo que `batch`, y sigue siendo barato.

### Opcion 2: traduccion mas barata

Si quieres menor costo:

```bash
cd srt_translator_openai
TRANSLATION_MODE=batch python3 run_translator.py
```

En este modo, el mismo comando avanza por etapas:

1. prepara el JSONL y el manifest
2. envia el batch a OpenAI
3. si vuelves a ejecutar despues, consulta el estado
4. cuando el batch termina, descarga resultados y escribe los `.srt`

Si falla, intenta descargar `work/batch_error.jsonl`.

## Flujo detallado: Batch API

### 1. Preparar solicitudes

```bash
cd srt_translator_openai
python3 run_translator.py prepare-batch
```

Esto genera:

- manifest
- `openai_batch_requests.jsonl`
- referencias de cache

### 2. Enviar batch

```bash
cd srt_translator_openai
python3 run_translator.py submit-batch
```

Guarda el `batch_id` que devuelve.

### 3. Consultar estado

```bash
cd srt_translator_openai
python3 run_translator.py batch-status --batch-id batch_123
```

### 4. Recolectar resultados y escribir `.srt`

```bash
cd srt_translator_openai
BATCH_ID=batch_123 python3 run_translator.py collect-batch
```

## Flujo rapido: sync

Para pruebas pequenas:

```bash
cd srt_translator_openai
TRANSLATION_MODE=sync python3 run_translator.py translate-sync
```

Esto es mas simple, pero normalmente mas caro que Batch.

## Docker

Construir:

```bash
cd srt_translator_openai
docker build -t jeisonrosario66/srt-translator-openai:0.1 .
```

Ejemplo de corrida local:

```bash
docker run --rm \
  --env-file .env \
  -v /ruta/a/srt_original:/data/input \
  -v /ruta/a/srt_es:/data/output \
  -v /ruta/a/work:/data/work \
  jeisonrosario66/srt-translator-openai:0.1 translate-sync
```

## Reglas de traduccion BJJ

La herramienta ya trae un glosario base, pero puedes editar `glossary_bjj.txt`.

La idea es:

- traducir natural al espanol
- mantener terminos que en BJJ se suelen conservar
- evitar traducciones literales feas
- mantener consistencia entre `guard`, `half guard`, `underhook`, `frame`, `saddle`, `ashi`, etc.

## Notas practicas

- si ya existe el `.srt` de salida y `OVERWRITE=false`, lo omite
- replica la estructura interna de la carpeta origen
- Batch es lo mejor para volumen alto
- Sync es mejor para validar calidad rapida en pocos archivos
