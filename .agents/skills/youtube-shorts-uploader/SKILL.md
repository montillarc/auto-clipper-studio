---
name: youtube-shorts-uploader
description: >-
  Authenticates with YouTube Data API v3 via OAuth 2.0 using ./config/client_secret.json and
  auto-refreshing ./config/token.json (scope https://www.googleapis.com/auth/youtube.upload),
  and uploads vertical videos using videos().insert with resumable MediaFileUpload, scheduling
  them via status.publishAt (privacyStatus='private', selfDeclaredMadeForKids=False) and ensuring
  #Shorts in title and #Viral + #Shorts in description.
---

# YouTube Shorts Uploader (`youtube-shorts-uploader`)

Esta Skill sube el Short renderizado al canal de YouTube mediante la API oficial (`google-api-python-client`) y lo deja programado en la fecha y hora exacta calculada por `strategic-time-calculator`.

## Autenticación OAuth 2.0
- Lee las credenciales OAuth de cliente de escritorio desde `./config/client_secret.json`.
- Guarda y refresca automáticamente el token en `./config/token.json` con el scope:
  `https://www.googleapis.com/auth/youtube.upload`

## Configuración del Payload (`videos().insert`)
- **Carga resumible**: `MediaFileUpload(video_path, mimetype="video/mp4", chunksize=4*1024*1024, resumable=True)`
- **`snippet`**:
  - `title`: Asegura sufijo `#Shorts` (respetando el límite de 100 caracteres de YouTube).
  - `description`: Incluye el caption en primera persona junto con `#Viral` y `#Shorts`.
  - `tags`: Lista de etiquetas generadas.
  - `categoryId`: `"22"` (Personas y blogs) o `"24"` (Entretenimiento).
- **`status`**:
  - `privacyStatus`: `"private"` (obligatorio para usar `publishAt`).
  - `publishAt`: `<ISO_TIMESTAMP_DEL_CALCULADOR>` en formato `YYYY-MM-DDTHH:MM:SSZ`.
  - `selfDeclaredMadeForKids`: `False`.

## Uso

### CLI
```bash
.\.venv\Scripts\python.exe .agents/skills/youtube-shorts-uploader/uploader.py \
  --video "./output_shorts/video_short.mp4" \
  --title "¡No vas a creer esto! #Shorts" \
  --description "Mi gente, miren qué locura #Viral #Shorts" \
  --tags "Shorts,CreadorStudio,Viral" \
  --publish-at "2026-10-22T22:00:00Z"
```
