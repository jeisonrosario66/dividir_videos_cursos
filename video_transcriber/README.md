# Transcriptor de Videos a SRT

Este mini proyecto toma videos desde una carpeta, recorre subcarpetas y genera subtitulos `.srt` respetando la misma estructura relativa.

## Idea general

- `profile=local`: pensado para tu PC con 4 GB de RAM.
- `profile=vast`: pensado para una instancia con GPU en Vast.ai.
- El cambio normal entre entornos es solo el modelo o el perfil.

## Modelos disponibles

### Modelos oficiales de Whisper

Segun el repositorio oficial de OpenAI, los tamaños base disponibles son:

| Modelo | Variante ingles | Variante multilenguaje | VRAM aprox. | Comentario |
| --- | --- | --- | --- | --- |
| `tiny` | `tiny.en` | `tiny` | ~1 GB | El mas liviano. Buen punto de partida para 4 GB de RAM. |
| `base` | `base.en` | `base` | ~1 GB | Mejor calidad que `tiny`, aun razonable para CPU. |
| `small` | `small.en` | `small` | ~2 GB | Mas calidad, pero ya exige bastante mas tiempo y RAM. |
| `medium` | `medium.en` | `medium` | ~5 GB | Mejor precision, poco realista para tu PC. |
| `large` | no | `large` | ~10 GB | Pesado. Mas pensado para GPU. |
| `turbo` | no | `turbo` | ~6 GB | Version optimizada para transcripcion rapida. |

Notas:

- Las variantes `.en` son solo para audio en ingles.
- Para BJJ en espanol, portugues o cursos mixtos, usa normalmente los multilenguaje.
- En esta herramienta, para tu PC de 4 GB conviene empezar con `tiny` o `base`.

### Modelos comunes compatibles con `faster-whisper`

Como este proyecto usa `faster-whisper`, tambien puedes cargar checkpoints compatibles por nombre, por ejemplo:

- `large-v2`
- `large-v3`
- `distil-large-v3`

En la practica:

- `tiny` o `base`: recomendados en local.
- `large-v3` o `distil-large-v3`: mejores candidatos para Vast.ai con GPU.

## Estructura

- `transcriber/`: paquete principal
- `transtribir.py`: punto de entrada CLI
- `run_transcriber.py`: runner corto que lee rutas y opciones desde `.env`
- `.env.example`: plantilla para apuntar a videos de prueba
- `requirements.txt`: dependencias de transcripcion
- `Dockerfile`: contenedor para correrlo igual en local o en servidor
- `.gitignore`: exclusiones propias para que luego puedas mover esta carpeta sola

## Requisitos fuera de Docker

- Python 3.10+
- `ffmpeg`

## Instalacion local

```bash
cd video_transcriber
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Apuntar a una carpeta de prueba

La forma mas simple es usar un archivo `.env`.

```bash
cd video_transcriber
cp .env.example .env
```

Luego edita `.env` y cambia solo esta linea:

```env
INPUT_DIR=/ruta/absoluta/a/tus/videos/de/prueba
```

Si quieres fijar tambien la salida:

```env
OUTPUT_DIR=/ruta/absoluta/a/tus/subtitulos
```

Despues ejecutas:

```bash
python3 run_transcriber.py
```

Si quieres controlar el paralelismo desde `.env`, agrega por ejemplo:

```env
PARALLEL_FILES=1
```

## Uso local directo

Para una maquina modesta conviene empezar con `tiny` o `base`.

```bash
cd video_transcriber
python3 transtribir.py /ruta/a/videos --profile local --model tiny -o /ruta/a/subtitulos
```

Si quieres deteccion automatica de idioma:

```bash
cd video_transcriber
python3 transtribir.py /ruta/a/videos --profile local --model tiny --language auto
```

En local con 4 GB de RAM, mi recomendacion sigue siendo:

- `--parallel-files 1`
- `tiny` o `base`

## Uso en Vast.ai

Con GPU puedes usar un modelo mas pesado:

```bash
cd video_transcriber
python3 transtribir.py /workspace/videos --profile vast --model large-v3 --parallel-files 2 -o /workspace/subtitulos
```

Si montas exactamente el mismo proyecto, normalmente el cambio principal sera:

- `--profile local --model tiny`
- por
- `--profile vast --model large-v3`

Si quieres probar otra opcion en GPU:

- `--profile vast --model distil-large-v3`

Suele ser una buena opcion cuando quieres muy buena velocidad con calidad alta.

## Paralelismo

Esta herramienta ya puede transcribir varios archivos a la vez.

- Usa `--parallel-files N` para definir cuantos videos procesar en paralelo.
- Internamente se apoya en `num_workers` de `faster-whisper`, pensado para llamadas concurrentes desde varios threads.
- Mas paralelismo mejora el throughput total, pero aumenta el consumo de VRAM y RAM.

Ejemplos:

```bash
cd video_transcriber
python3 transtribir.py /ruta/a/videos --profile local --model tiny --parallel-files 1
```

```bash
cd video_transcriber
python3 transtribir.py /workspace/videos --profile vast --model large-v3 --parallel-files 2 -o /workspace/subtitulos
```

```bash
cd video_transcriber
python3 transtribir.py /workspace/videos --profile vast --model distil-large-v3 --parallel-files 3 -o /workspace/subtitulos
```

Punto de partida recomendado:

- PC local 4 GB RAM: `parallel-files=1`
- GPU 24 GB: empieza con `parallel-files=2`
- GPU 48 GB: prueba `parallel-files=3` o `4`

Si ves errores de memoria o la GPU se vuelve inestable, baja `--parallel-files`.

## Docker

Construir la imagen:

```bash
cd video_transcriber
docker build -t curso-transcriber .
```

Si la vas a subir a Docker Hub para Vast.ai:

```bash
docker build -t jeisonrosario66/curso-transcriber:0.2 .
docker push jeisonrosario66/curso-transcriber:0.2
```

La version `0.2` cambia la base a `python:3.11-slim-bookworm` e incluye paquetes que Vast espera cuando levanta una instancia en modo `Interactive shell server, SSH`.

Si quieres una version pensada especificamente para evitar errores de `libcublas.so.12` y `cudnn` en Vast:

```bash
docker build -t jeisonrosario66/curso-transcriber:0.3 .
docker push jeisonrosario66/curso-transcriber:0.3
```

La version `0.3` ademas:

- instala `nvidia-cublas-cu12`
- instala `nvidia-cudnn-cu12`
- exporta `LD_LIBRARY_PATH` automaticamente en el arranque

Si quieres una version mas liviana para Vast, pero que siga autocorrigiendo el runtime CUDA al arrancar:

```bash
docker build -t jeisonrosario66/curso-transcriber:0.4 .
docker push jeisonrosario66/curso-transcriber:0.4
```

La version `0.4`:

- no mete `cublas/cudnn` dentro de la imagen final
- instala esas librerias solo al arrancar si `PROFILE=vast`
- sigue exportando `LD_LIBRARY_PATH` automaticamente
- deberia subir y bajar mucho mas rapido que `0.3`

Si quieres una version mas robusta para trabajar por SSH dentro de Vast y que ya tenga un `.env` basico dentro de `/app/.env`, usa:

```bash
docker build -t jeisonrosario66/curso-transcriber:0.5 .
docker push jeisonrosario66/curso-transcriber:0.5
```

La version `0.5`:

- incluye `nano`
- copia un `.env` base dentro de `/app/.env`
- toma variables de entorno de Vast por encima del archivo
- instala `cublas/cudnn` bajo demanda tambien cuando ejecutas `python run_transcriber.py` manualmente por SSH

Si quieres la version recomendada final para Vast, ligera pero mas robusta y con progreso visible durante la transcripcion, usa:

```bash
docker build -t jeisonrosario66/curso-transcriber:0.6 .
docker push jeisonrosario66/curso-transcriber:0.6
```

La version `0.6`:

- mantiene la imagen liviana como `0.5`
- resuelve CUDA tambien cuando ejecutas CLI manual (`python run_transcriber.py` o `python transtribir.py`)
- trae `.env` base en `/app/.env`
- incluye `nano`
- muestra progreso por archivo con porcentaje, conteos `ok/fail/skip`, duracion y tiempo transcurrido

Correrla montando carpetas locales:

```bash
cd video_transcriber
docker run --rm \
  -v /ruta/a/videos:/data/input \
  -v /ruta/a/subtitulos:/data/output \
  curso-transcriber /data/input --profile local --model tiny --parallel-files 1 -o /data/output
```

En Vast.ai la idea es la misma, pero cambiando el perfil y modelo:

```bash
cd video_transcriber
docker run --rm \
  -v /workspace/videos:/data/input \
  -v /workspace/subtitulos:/data/output \
  curso-transcriber /data/input --profile vast --model large-v3 --parallel-files 2 -o /data/output
```

## Vast.ai

### Modo recomendado si no quieres depender de SSH

Usa `Docker ENTRYPOINT` y asegurate de que Cloud Sync copie los videos a:

```text
/data/input
```

y que la salida quede en:

```text
/data/output
```

Variables recomendadas:

- `INPUT_DIR=/data/input`
- `OUTPUT_DIR=/data/output`
- `PROFILE=vast`
- `MODEL=large-v3`
- `LANGUAGE=auto`
- `OVERWRITE=false`
- `PARALLEL_FILES=2`

### Modo SSH en Vast

Si quieres usar `Interactive shell server, SSH`, usa la imagen nueva:

- `jeisonrosario66/curso-transcriber:0.2`

Esta version preinstala:

- `openssh-client`
- `openssh-server`
- `tmux`
- `sudo`
- `rsync`
- `software-properties-common`

Eso mejora la compatibilidad con la capa SSH que Vast construye por encima de tu contenedor.

Si vas a usar GPU real para transcribir dentro de Vast, usa mejor:

- `jeisonrosario66/curso-transcriber:0.3`

porque esa version deja resuelto el runtime de `cublas/cudnn` para `faster-whisper`.

Si quieres reducir mucho el tiempo de pull de la imagen, usa mejor:

- `jeisonrosario66/curso-transcriber:0.4`

porque esa version descarga `cublas/cudnn` al iniciar en vez de hornearlo dentro de la imagen.

Si quieres ademas un `.env` ya preparado dentro del contenedor y mejor experiencia por SSH, usa:

- `jeisonrosario66/curso-transcriber:0.5`

Si quieres la opcion mas completa y recomendada para tus pruebas actuales en Vast, usa:

- `jeisonrosario66/curso-transcriber:0.6`

### Nota importante sobre Cloud Sync

Si sincronizas Drive a `/data/`, el contenedor no encontrara archivos si `INPUT_DIR` apunta a `/data/input`.

Haz el sync asi:

- origen Drive: por ejemplo `/cursos_sin_datos/AOJ`
- destino en la instancia: `/data/input`

Y luego recupera resultados desde:

- `/data/output`

## Carpeta sugerida para pruebas

Si quieres tener un lugar fijo dentro del proyecto, puedes crear algo como:

```text
video_transcriber/
  test_data/
    videos/
    subtitulos/
```

Luego apuntas en `.env` a `test_data/videos`. Esa carpeta ya esta ignorada por git.

## Notas practicas

- `tiny` y `base` son los puntos de partida mas seguros para 4 GB de RAM.
- `large-v3` no es realista para tu PC, pero si para GPU.
- `distil-large-v3` puede ser muy atractivo en Vast.ai si priorizas velocidad.
- El perfil `vast` ahora viene preparado para empezar con paralelismo conservador.
- El script omite `.srt` ya existentes salvo que uses `--overwrite`.
- La salida replica la estructura interna de la carpeta origen.

## Traduccion a espanol

Si luego quieres una carpeta espejo con subtitulos traducidos al espanol, lo mejor no es traducir directamente el audio con otra herramienta de voz a texto. Para conservar mejor el contexto de BJJ, normalmente conviene este flujo:

1. Transcribir primero con esta herramienta en el idioma original.
2. Traducir despues los `.srt` como texto, manteniendo tiempos y contexto entre segmentos.
3. Guardar la traduccion en una carpeta paralela espejo.

Esto suele dar mejores resultados porque:

- Whisper es muy bueno para transcribir, pero su tarea de traduccion oficial esta orientada sobre todo a llevar audio no ingles hacia ingles, no a producir subtitulos finales de alta calidad en espanol.
- En BJJ necesitas consistencia terminologica: `guard`, `half guard`, `underhook`, `frames`, `inside position`, `saddle`, `ashi`, etc. Muchas veces no quieres traducir todo literal.
- Una IA de texto para traducir los `.srt` puede trabajar con glosario, tono, contexto tecnico y reglas de estilo.

Recomendacion practica:

- Usa esta herramienta para generar los `.srt` originales.
- Haz una segunda herramienta o script para traducir esos `.srt` a espanol con glosario propio de BJJ.
- Conserva una carpeta espejo, por ejemplo:

```text
curso/
  original_srt/
  es_srt/
```

Si quieres, en el siguiente paso puedo dejarte esa segunda fase armada dentro del mismo `video_transcriber/`, para que tome una carpeta de `.srt` y genere la version espanola en espejo.

## Fuentes

- OpenAI Whisper README: https://github.com/openai/whisper
- Faster-Whisper README: https://github.com/SYSTRAN/faster-whisper
