# Guía de Trabajo para Antigravity (`AGENTS.md`)

Este repositorio es **Auto-Clipper Studio** (`FastAPI + React + Vite + FFmpeg/Whisper/MediaPipe`).

## Reglas para el Agente al abrir este proyecto en Antigravity

1. **Lectura previa obligatoria:** Lee primero `FLOW.md` y `LEEME.md` para conocer los endpoints activos, el flujo de UI y los contratos reales del backend.
2. **Compilación y entorno inicial (si es primera vez en la PC del usuario):**
   - Backend Python (`3.11+`):
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\python.exe -m pip install -r requirements.txt
     ```
   - Frontend React/Vite (`Node.js 20+`):
     ```powershell
     cd frontend
     npm install
     npm run build
     cd ..
     ```
   - Arranque del servidor local: `.\.venv\Scripts\python.exe api_server.py` (sirve la interfaz compilada y la API en `http://127.0.0.1:8001`).
3. **Respetar privacidad y `.gitignore`:**
   - Jamás subas al repositorio archivos dentro de `config/` con credenciales reales (`client_secret.json`, `token.json`, `meta_token.json`, `tiktok_client.json`, `tiktok_tokens.json`, `social_hub_config.json`, `schedule_state.db`, `settings.json`).
   - Usa únicamente las plantillas `config/*.example.json` o la pestaña **`Cuentas & APIs`** de la interfaz para que cada usuario guarde sus propias claves de forma local.
4. **Verificación recomendada tras cualquier cambio:**
   - Backend: `.\.venv\Scripts\python.exe -m pytest tests/test_api.py -q`
   - Frontend: `cd frontend && npm run test -- --run && npm run build`
