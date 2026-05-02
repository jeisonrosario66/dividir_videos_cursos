# Herramientas para cursos en video

Este repo ahora tiene dos utilidades separadas:

- `split_course.py`: divide cursos largos en capitulos usando `content.txt` o `timing.txt`
- `video_transcriber/`: mini proyecto separado para transcribir videos y generar `.srt`

## Splitter

Ejemplo:

```bash
python3 split_course.py /ruta/base
```

## Transcriptor

La guia completa esta en [video_transcriber/README.md](/home/bigdev/github/dividir_videos_cursos/video_transcriber/README.md).

Ejemplo rapido para tu PC:

```bash
cd video_transcriber
python3 transtribir.py /ruta/a/videos --profile local --model tiny -o /ruta/a/subtitulos
```
