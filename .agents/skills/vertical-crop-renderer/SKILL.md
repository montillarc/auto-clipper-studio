---
name: vertical-crop-renderer
description: >-
  Cuts and reframes horizontal videos into vertical 9:16 (1080x1920) YouTube Shorts using MediaPipe
  Face Detection and OpenCV to dynamically track the speaker's X position, generates dynamic 3-4 word
  .ass subtitles using pysubs2 (large yellow/white text with thick black outline in the lower-center),
  and renders the final video into ./output_shorts/ using FFmpeg with NVIDIA NVENC (h264_nvenc).
---

# Vertical Crop & Dynamic Subtitle Renderer (`vertical-crop-renderer`)

Esta Skill toma las marcas de tiempo (`start_time`, `end_time`, `word_timestamps`) generadas por `video-transcriber-analyzer`, rastrea el rostro del hablante con **MediaPipe + OpenCV**, genera subtítulos dinámicos `.ass` con **pysubs2** y renderiza el Short vertical (`1080x1920`) con aceleración por hardware **FFmpeg NVENC (`h264_nvenc`)**.

## Flujo Técnico
1. **Rastreo Facial Dinámico (`MediaPipe` + `OpenCV`)**:
   - Muestrea el segmento `[start_time, end_time]` detectando la caja delimitadora del rostro principal.
   - Calcula la coordenada `X` del recorte 9:16 aplicando un filtro de suavizado exponencial (EMA) con zona muerta (*deadzone*) para evitar saltos bruscos y garantizar que la cara nunca salga del encuadre.
2. **Subtítulos Dinámicos `.ass` (`pysubs2`)**:
   - Agrupa `word_timestamps` en bloques de **máximo 3 a 4 palabras** en pantalla.
   - Configura resolución `1080x1920`, fuente grande en negrita (Amarillo `#FFE600` / Blanco `#FFFFFF`), borde negro grueso (`Outline=5`, `Shadow=2`) y alineación central-baja (`Alignment=2`, `MarginV=280`).
3. **Renderizado con Aceleración GPU (`ffmpeg-python` + `h264_nvenc`)**:
   - Corta el segmento exacto, aplica el filtro `crop` dinámico 9:16, escala a `1080x1920`, quema los subtítulos `.ass` y codifica en `./output_shorts/` usando `h264_nvenc` (con fallback seguro a `libx264` si no se detecta GPU NVIDIA activa).

## Uso

### CLI
```bash
.\.venv\Scripts\python.exe .agents/skills/vertical-crop-renderer/renderer.py \
  --video "./processing/video.mp4" \
  --analysis "./processing/video_analysis.json" \
  --output-dir "./output_shorts"
```

### Python
```python
from renderer import render_vertical_short

output_video = render_vertical_short(
    video_path="./processing/video.mp4",
    analysis=analysis_obj,
    output_dir="./output_shorts",
)
```
