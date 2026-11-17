# 🎬 Auto-Clipper Studio (Short YT) — Guía Completa (`LEEME.md`)

**Auto-Clipper Studio** es un estudio local con Inteligencia Artificial para **extraer, puntuar viralidad, encuadrar en vertical `9:16` (`1080×1920`) con seguimiento facial e interfaz multi-escena, añadir subtítulos `.ASS` animados estilo karaoke y descargar o programar Shorts/Reels** desde:
1. **Archivos de video locales** en tu computadora.
2. **Enlaces (URL)** de YouTube, Twitch o Kick (incluso eligiendo solo un fragmento con rango de horas `Inicio` / `Fin`).
3. **Transmisiones EN VIVO activas** en tiempo real (pestaña **Directo en Vivo**).

> **Versión limpia para compartir:** Este repositorio no incluye tokens, claves privadas, bases de datos ni cuentas sociales personales. Cada persona lo compila en su computadora y puede usarlo 100% en local desde el primer minuto (sin necesidad de conectar redes si solo desea descargar los Shorts en `.mp4` / `.zip`).

---

## 📋 1. Requisitos previos

Instala estas herramientas en tu computadora antes de empezar:

| Herramienta | Versión recomendada | Uso en el proyecto |
| :--- | :--- | :--- |
| **Sistema Operativo** | Windows 10 / 11 (o Linux/macOS) | Ejecución local de FastAPI, Playwright y FFmpeg |
| **Python** | `3.11` (64-bit) | Backend FastAPI, Whisper, MediaPipe, análisis IA y render |
| **Node.js + npm** | `20 LTS` o superior | Compilación del frontend React + TypeScript + Vite |
| **Git** | Última versión | Clonar el repositorio |
| **GPU NVIDIA (Opcional)** | CUDA + driver actual | Acelera la transcripción Whisper y codificación `h264_nvenc` *(si no tienes GPU NVIDIA funciona igual por CPU)* |

*(FFmpeg ya se descarga e integra automáticamente mediante `imageio-ffmpeg` al instalar `requirements.txt`.)*

---

## 🚀 2. Cómo compilar y configurar en Google Antigravity

### Opción A — Pedírselo directo a tu Antigravity (Recomendada)

1. Clona este repositorio en tu PC (o ábrelo con **Open Folder** en Antigravity).
2. Abre un chat nuevo en Antigravity dentro de la carpeta **`auto-clipper-studio`** y pégale exactamente esta instrucción:

> *"Lee `LEEME.md` y `AGENTS.md`. Verifica Python 3.11 y Node.js, crea el entorno virtual `.venv`, instala `requirements.txt`, instala dependencias en `frontend/` y ejecuta `npm run build`, corre las pruebas (`pytest` y `vitest`) y levanta `api_server.py` en `http://127.0.0.1:8001`."*

Antigravity dejará todo compilado, probado y listo para usar en tu navegador.

---

### Opción B — Instalación manual paso a paso (PowerShell en Windows)

Abre PowerShell dentro de la carpeta del repositorio (`auto-clipper-studio`) y ejecuta en orden:

#### Paso 1: Crear el entorno virtual e instalar dependencias Python
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

#### Paso 2: Instalar y compilar el Frontend (React + Vite)
```powershell
cd frontend
npm install
npm run build
cd ..
```

#### Paso 3: Iniciar la aplicación
Puedes hacerlo de cualquiera de estas dos formas:
- **Doble clic** en el lanzador portátil **`Iniciar Auto-Clipper Studio.bat`** en la raíz del proyecto.
- O desde terminal:
  ```powershell
  .\.venv\Scripts\python.exe api_server.py
  ```

El servidor arrancará en **`http://127.0.0.1:8001`** y abrirá automáticamente el estudio en tu navegador.

---

## 🎯 3. Cómo usar el sistema paso a paso (Los 3 Modos)

El flujo se basa en **Perfiles de Contenido**: guardas una vez cómo se ve tu cámara, pantalla/juego y estilo de subtítulos para reutilizarlo en futuros videos o directos con un clic.

---

### 📁 Modo 1: Sacar clips desde un Video Local en tu PC

Ideal si ya grabaste una partida, podcast o stream con OBS en tu disco duro:

1. En la pestaña principal **`Estudio de Shorts`**, pulsa **`Archivo Local`** en el selector de la derecha.
2. Haz clic en el campo **`Video Local en tu PC`** (**`Explorar`**) y selecciona tu archivo `.mp4`, `.mkv` o `.mov`.
   *(El sistema lee el video sin copiarlo ni moverlo de su carpeta original.)*
3. *(Opcional)* Pulsa **`Inspeccionar Video`** para ver duración, resolución, FPS y estimación recomendada de Shorts.
4. En **`Shorts`**, indica cuántos clips quieres generar (rango de **`1`** a **`24`**) y pulsa el botón azul **`Generar`**.
5. Se abrirá el **Modal de Pre-Análisis y Escenas (`9:16`)**:
   - **Perfil de Contenido:** Selecciona un perfil ya guardado o crea uno nuevo (ej. *Podcast Estudio*, *Gameplay OBS*) con sus palabras clave y categorías permitidas.
   - **Calibrar Escena (`16:9` -> `9:16`):** Pulsa **`Detectar Escena & Studio`** para abrir el fotograma real del video. Ahí puedes elegir línea de tiempo, arrastrar las cajas de cámara/contenido (modos `Pantalla Completa`, `Split 50/50`, `Gameplay + Cámara` o `Podcast Dual`) y revisar en vivo cómo quedarán los subtítulos.
   - **Agregar más escenas (1 a 4):** Si el video alterna entre conversación y gameplay, puedes crear hasta 4 escenas distintas por perfil.
6. Elige cómo generar:
   - **`Escanear Clips IA`**: analiza el video, te muestra los mejores momentos puntuados con su título y transcripción para que elijas manualmente cuáles renderizar.
   - **`Confirmar y Generar Shorts`**: renderiza automáticamente en vertical `1080×1920` con subtítulos `.ASS`.
7. Al terminar, verás la **Galería de Shorts Renderizados**:
   - Pulsa **`Editar`** en cualquier tarjeta para cambiar el encuadre o acortar/alargar el clip (`±30s`) sin volver a analizar todo el video.
   - Usa **`Elegir`** / **`Seleccionar todos`** y pulsa **`Descargar Todos`** o **`Descargar Seleccionados`** (descarga `.mp4` directo si es 1 clip, o `.zip` si son varios).

---

### 🌐 Modo 2: Sacar clips desde una URL (YouTube, Twitch o Kick)

Ideal para videos publicados o VODs/directos largos ya terminados:

1. En **`Estudio de Shorts`**, selecciona **`Pegar URL de YouTube / LIVE`**.
2. Pega la URL del video o VOD de **YouTube**, **Twitch** o **Kick**.
3. *(Opcional — Muy recomendado para streams largos)* Rellena **`Inicio (Opcional)`** y **`Fin (Opcional)`** en formato `HH:MM:SS` (por ejemplo `01:10:00` y `01:55:00`) para descargar **únicamente esa parte del video** sin esperar a bajar 4 horas completas.
4. Indica la cantidad de **`Shorts`** (`1` a `24`) y pulsa **`Generar`**.
5. En el modal, pulsa **`Detectar Escena & Studio`** (también funciona en modo URL), ajusta o selecciona tu **Perfil de Contenido** y pulsa **`Confirmar y Generar Shorts`** (o **`Escanear Clips IA`**).
6. Descarga tus Shorts en `.mp4` / `.zip` o prográmalos desde la galería.

---

### 🔴 Modo 3: Sacar clips de una Transmisión EN VIVO en tiempo real (`Directo en Vivo`)

Ideal mientras alguien está transmitiendo en directo en **YouTube Live**, **Twitch** o **Kick** en ese preciso instante:

1. *(Recomendación previa)* Asegúrate de haber guardado antes al menos un **Perfil de Contenido** (desde Modo 1 o Modo 2) con tu encuadre `9:16` y estilo de subtítulos configurados.
2. Haz clic en la pestaña superior **`Directo en Vivo`**.
3. Completa los campos de la barra de control:
   - **`URL del Directo en Vivo`**: pega el enlace del stream que está en emisión ahora mismo.
   - **`Perfil de Contenido en Vivo`**: elige qué perfil visual aplicará a todos los clips que salgan del directo.
   - **`Intervalo de Escaneo`**: cada cuántos segundos analizar ventanas del stream (`60s`, `90s`, `120s`, `180s`).
   - **`Puntaje Mínimo`**: filtro mínimo de viralidad IA (`40` a `95`) para evitar clips flojos.
   - **`Máx. Shorts`**: límite máximo de Shorts a extraer en la sesión (`1` a `50`).
4. Pulsa **`Iniciar en Vivo`**.
5. **Cómo trabaja por debajo:**
   - Resuelve el stream HLS con `yt-dlp` sin esperar a que termine la transmisión.
   - Captura bloques rodantes mediante FFmpeg con **`20s` de solapamiento** entre ventanas para no cortar frases ni jugadas por la mitad.
   - Transcribe y puntúa cada bloque con IA; si un momento ya se extrajo en el bloque anterior, lo descarta automáticamente para evitar duplicados.
   - Cada clip que supera tu **`Puntaje Mínimo`** se renderiza en `9:16` y aparece al instante en la galería inferior listo para reproducir o descargar mientras el directo sigue corriendo.
6. Cuando quieras terminar, pulsa **`Detener Directo`**.

---

## ⚙️ 4. Configuración Opcional de Redes Sociales y APIs (`Cuentas & APIs`)

Si además de descargar tus clips quieres **programarlos y subirlos** a tus canales, abre la pestaña **`Cuentas & APIs`** en la interfaz web. Toda tu configuración y tokens se guardan únicamente en archivos locales dentro de `config/` (ignorados por `.gitignore`):

1. **Categorías de Cuentas:** Puedes usar las 4 categorías base (`Principales`, `Gaming`, `Clipping`, `OMETV`) o crear las tuyas propias con **palabras clave temáticas** para que el sistema asigne cada Short automáticamente a las cuentas correctas. *(En la galería, el botón **`Categorías y redes`** viene oculto por defecto para mantener la vista limpia; púlsalo cuando quieras ver o ajustar categorías y barras de subida).*
2. **YouTube Data API v3:**
   - Crea un proyecto en Google Cloud Console, habilita **YouTube Data API v3** y genera credenciales OAuth 2.0 (`Desktop App`).
   - Pega tu `Client ID` y `Client Secret` (o tu JSON en **`Cuentas & APIs`**; plantilla en [`config/client_secret.example.json`](config/client_secret.example.json)), guarda y pulsa **`Autorizar OAuth`** para vincular tu canal en el navegador.
3. **Instagram Reels y Facebook Reels (Meta Graph API):**
   - Pega tu `Meta App ID`, `Long-Lived Access Token`, `Business ID` y tu `Page Access Token` de Facebook (ver plantilla [`config/meta_token.example.json`](config/meta_token.example.json)) junto al `external_id` de cada cuenta IG / Página FB.
   - Videos de Facebook mayores a `50 MB` utilizan subida reanudable en 3 fases contra `graph-video.facebook.com`.
4. **TikTok (`DIRECT_POST`, `INBOX_UPLOAD` o `TIKTOK_STUDIO`):**
   - Con app aprobada puedes usar **`DIRECT_POST`** (`Client Key`, `Client Secret` y OAuth).
   - Mientras tu app esté en Sandbox puedes elegir **`INBOX_UPLOAD`** (envía borradores a tu app móvil de TikTok) o **`TIKTOK_STUDIO`** (automatización asistida en tu navegador Brave local con tu permiso explícito).

*(También se incluyen plantillas limpias de referencia en `config/*.example.json`.)*

---

## 🧪 5. Verificar que todo compila y pasa pruebas (Tests)

Ejecuta las suites automatizadas en cualquier momento desde la raíz del proyecto:

```powershell
# Pruebas Backend (FastAPI + Pipeline + Redes Sociales)
.\.venv\Scripts\python.exe -m pytest tests/test_api.py -q

# Pruebas Frontend + Compilación TypeScript/Vite
cd frontend
npm run test -- --run
npm run build
```

---

## 📂 6. Estructura principal del proyecto

- `api_server.py`: Servidor FastAPI + endpoints REST + despachador en segundo plano de colas programadas + servidor estático de `frontend/dist/`.
- `main_daemon.py`: Pipeline principal de descarga segura (`yt-dlp`), transcripción Whisper, análisis de viralidad y orquestación de render.
- `live_stream_monitor.py`: Captura continua en vivo por ventanas rodantes HLS/FFmpeg y deduplicación.
- `.agents/skills/`: Habilidades modulares (`video-transcriber-analyzer`, `vertical-crop-renderer`, `strategic-time-calculator`, `youtube-shorts-uploader`, `multi-social-uploader`).
- `config/`: Conectores de IA/redes (`audio_ai_connectors.py`, `social_hub.py`), modelos/máscaras (`blaze_face_short_range.tflite`) y plantillas `*.example.json`.
- `frontend/`: Interfaz web React + TypeScript + Tailwind CSS (estilo minimalista `40px` / `h-10`).
- `tests/test_api.py` & `frontend/src/App.test.tsx`: Suites completas de verificación backend y frontend.

---

## 📄 Licencia

Distribuido bajo licencia **MIT**. Consulta [LICENSE](LICENSE).
