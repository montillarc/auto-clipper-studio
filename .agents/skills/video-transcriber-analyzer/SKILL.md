---
name: video-transcriber-analyzer
description: >-
  Transcribes long-form Spanish videos using faster-whisper (large-v3, CUDA float16, word_timestamps=True)
  and analyzes the transcript with Google Antigravity SDK to find the most viral 35-58 second segment
  following a 4-part narrative structure (Hook, Mystery/Question, Development/Facts, Conclusion/Punchline).
  Returns a validated Pydantic schema with start_time, end_time, hook_title, first_person_caption (Dominican tone), and tags.
---

# Video Transcriber & Viral Segment Analyzer (`video-transcriber-analyzer`)

Esta Skill transcribe un video largo en español usando `faster-whisper` con aceleración GPU (`cuda`, `float16`) y extrae el fragmento más viral (entre **35 y 58 segundos**) aplicando criterios de retención para YouTube Shorts.

## Estructura Narrativa Requerida
El analizador selecciona únicamente segmentos que cumplan con:
1. **Gancho o chiste inicial fuerte** (primeros 3 segundos).
2. **Misterio o pregunta sobre el tema** (genera curiosidad y retención).
3. **Desarrollo / hechos** (cuerpo ágil y directo).
4. **Conclusión o remate** (cierre satisfactorio o loop).

## Esquema de Salida (Pydantic)
El módulo [analyzer.py](./analyzer.py) valida la respuesta con el modelo `ViralClipAnalysis`:
- `start_time` (`float`): Segundo exacto de inicio del corte.
- `end_time` (`float`): Segundo exacto de fin del corte (`35.0 <= end_time - start_time <= 58.0`).
- `hook_title` (`str`): Título con clickbait estratégico sin mentir, optimizado para CTR.
- `first_person_caption` (`str`): Descripción en primera persona con tono cercano dominicano, incluyendo obligatoriamente `#Shorts` y `#Viral`.
- `tags` (`list[str]`): Lista de etiquetas relevantes para el algoritmo de YouTube Shorts.
- `word_timestamps` (`list[WordTimestamp]`): Marcas de tiempo palabra por palabra para la generación de subtítulos dinámicos `.ass`.

## Uso desde Línea de Comandos o Python

### CLI
```bash
.\.venv\Scripts\python.exe .agents/skills/video-transcriber-analyzer/analyzer.py --video "./processing/video.mp4" --output "./processing/video_analysis.json"
```

### Python
```python
from analyzer import transcribe_and_analyze

result = transcribe_and_analyze("./processing/video.mp4")
print(result.model_dump_json(indent=2))
```
