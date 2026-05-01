# 🎬 Course Video Splitter (CLI)

Herramienta simple en Python para dividir cursos en video (.mp4) en capítulos usando un archivo `content.txt` con timestamps.

---

## 🚀 Características

- Divide videos automáticamente por volumen
- Usa timestamps definidos manualmente
- No pierde calidad (`ffmpeg -c copy`)
- Organiza salida en carpetas (`volume_X`)
- Funciona por línea de comandos

---

## 📦 Requisitos

- Python 3.8+
- ffmpeg

### Instalar ffmpeg (Linux)

```bash
sudo apt install ffmpeg