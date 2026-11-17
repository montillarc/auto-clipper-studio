---
trigger: always_on
description: Reglas permanentes e inalterables del flujo de trabajo de YouTube Shorts para CreadorStudio
---

# Reglas Permanentes del Proyecto YouTube Shorts (CreadorStudio)

Sigue siempre y sin excepción los parámetros definidos en `WORKFLOW_RULES.md`:

1. **Calidad `1080p60` Nativa**: Siempre extrae los fragmentos desde el stream original `1920x1080` a `60 FPS` (o superior) vía `yt-dlp` cuando el usuario pase un link de YouTube o cuando el archivo local esté en `720p30`. Aplica `Lanczos` + `AMD FidelityFX CAS` (`cas=strength=0.60`) + `unsharp` + `h264_nvenc` (`16 Mbps`, `-cq 16`).
2. **Límite de Generación y Guía Definitiva de Puntuación de Viralidad (10 Puntos Clave — `virality_scorer.py`)**:
   - **Tope de Generación**:
     - **Videos Grabados / VOD**: Máximo **8 Shorts por video**.
     - **Directos En Vivo (LIVE)**: Máximo **8 Shorts por hora de LIVE**.
   - **Los 10 Puntos Clave de Evaluación (Total: 100 puntos / Nota del 1.0 al 10.0 = Suma ÷ 10)**:
     1. **El Gancho Hipnótico (Primeros 3 segundos) [Valor: 15 pts]**: `15 pts` (atrapa por el cuello sin piedad: duda insoportable, frase polémica, locura o imagen chocante) | `7 pts` (pasable pero genérico) | `0 pts` (empieza con "Hola, ¿cómo están?").
     2. **El Ritmo y la Cero-Fricción Visual [Valor: 10 pts]**: `10 pts` (ritmo impecable, cero silencios incómodos, cero relleno) | `5 pts` (tiene baches/momentos lentos) | `0 pts` (lento/muerto).
     3. **El Factor "Un Pana Mío" (Identificación y Cercanía) [Valor: 10 pts]**: `10 pts` (conecta con códigos culturales reales, calle, vivencias comunes) | `5 pts` (medianamente relatable) | `0 pts` (discurso corporativo).
     4. **La Tensión del Misterio o la Pregunta Irresuelta [Valor: 10 pts]**: `10 pts` (intriga en la garganta hasta el último segundo) | `5 pts` (se adivina a mitad de camino) | `0 pts` (predecible desde el inicio).
     5. **Activación Emocional Visceral (Ira, Risa o Asombro) [Valor: 10 pts]**: `10 pts` (indigna, asombra o da un ataque de risa) | `5 pts` (sonrisa floja/indiferente) | `0 pts` (plano).
     6. **El Contenido "Carne de Comentarios" (Polarización y Debate) [Valor: 10 pts]**: `10 pts` (garantiza debate intenso o guerra en comentarios) | `5 pts` (solo dicen "buen video") | `0 pts` (tibio).
     7. **Valor Agregado o Dato Perturbador/Curioso [Valor: 10 pts]**: `10 pts` (perspectiva única, dato oculto o narrativa magistral) | `5 pts` (repetido) | `0 pts` (genérico).
     8. **El Clickbait Estratégico (Sin Engaño Descarado) [Valor: 10 pts]**: `10 pts` (imán de clics perfecto y honrado con el contenido) | `5 pts` (exagera de más) | `0 pts` (aburrido/estafa).
     9. **Potencial de "Remix" o Compartir en Privado [Valor: 10 pts]**: `10 pts` (ADN nativo para enviarse por DM/WhatsApp con "mira este soy yo") | `5 pts` (da igual) | `0 pts` (nadie lo comparte).
     10. **El Factor de Cierre o "Efecto Loop" [Valor: 5 pts]**: `5 pts` (cierra con broche de oro o bucle perfecto con el inicio) | `2 pts` (termina de golpe extraño) | `0 pts` (se apaga de la nada).
   - **Escala de Calificación**:
     - `90 - 100 pts (9.0 - 10.0)`: Oro en las manos 🔥
     - `75 - 89 pts (7.5 - 8.9)`: Buen video ⚡
     - `50 - 74 pts (5.0 - 7.4)`: Meh 😐
     - `< 50 pts (< 5.0)`: Bodrio total ❌ (Descartar siempre)
   - **Filtro de Publicación por Puntuación**:
     - **YouTube (`CreadorStudio`)**: **SOLO se publican los Shorts con puntuación igual o mayor a 85 puntos (`>= 85`)**, con un **máximo de 6 videos en YouTube**.
     - **Demás Redes (Instagram + TikTok + Facebook de la categoría correspondiente)**: Se publican **los 8 Shorts en total generados**.
   - **Orden de Subida e Intervalo ("1 Hora de por medio")**:
     - Primero se suben/programan los Shorts que cumplan la regla de la puntuación (**`>= 85 puntos`**, de mayor a menor nota) con **1 hora de por medio** entre cada uno.
     - Luego son seguidos por **los demás Shorts (`< 85 puntos`)** en las demás redes con el **mismo tiempo de por medio (1 hora entre cada uno)**.
3. **Contexto Completo de Principio a Fin (Hasta `2:30 - 3:00 min`) y Carpeta por Video**:
   - **Nunca cortes una conversación o idea por la mitad**: Cada Short debe empezar exactamente donde inicia el planteamiento del tema o el saludo/pregunta inicial en OmeTV y terminar cuando concluye naturalmente la conversación o reacción completa.
   - **Carpeta exclusiva por video**: Cada vez que se trabaje un video nuevo, crea una subcarpeta dedicada dentro de `./output_shorts/<Nombre_del_Video>/` para que todo quede limpio y organizado.
4. **Detección Inteligente por Clip y Diseño Oficial de OmeTV**:
   - **Modo `ometv` (50/50 + Banner Central)**: En clips de OmeTV, recorta limpio por dentro el recuadro de CreadorStudio arriba (`1080x960`, sin bordes amarillos ni letreros del stream) + recuadro del invitado abajo (`1080x960`, sin bordes amarillos) y coloca siempre en el medio (`y=960`) el banner oficial `config/ometv_banner.png`.
   - **Modo `split_streamer` (Reacción / Gameplay)**: Cámara de CreadorStudio fija arriba (`1080x720`) + Contenido abajo (`1080x1200`) + Subtítulos en la línea divisoria (`y=720`).
   - **Modo `fullscreen` (Solo en pantalla)**: Corte vertical `1080x1920` centrado en su rostro + Subtítulos abajo (`y=1580`).
5. **Audio 100% Limpio y Original (`playback_speed=1.0`, `enable_bgm=False`)**:
   - Mantén el audio original del stream limpio y natural, sin música sintética de fondo (`enable_bgm=False`) y sin filtros destructivos (`rubberband`, `loudnorm` o `acompressor`) que distorsionen la voz.
6. **Formato Obligatorio de Metadatos en cada Short**:
   - 1️⃣ **TÍTULO VIRAL CORTO con Emojis** + `#Shorts`
   - 2️⃣ **DESCRIPCIÓN BREVE con Emojis + enlace del video original** (`🎥 Mira el directo completo aquí 👉 https://...`)
   - 3️⃣ **3 HASHTAGS más importantes del tema + `#Viral`** (`#Shorts`)
7. **Horarios de Publicación (`America/Santo_Domingo`) — 1 Hora de por medio (100% API en Segundo Plano)**:
   - Los Shorts se programan con **1 hora de separación (`1 hora de por medio`)**: primero todos los que cumplen la regla de puntuación (`>= 85 puntos`, máx 6 en YouTube + demás redes) con 1 hora de por medio, y luego seguidos por los demás Shorts (`< 85 puntos`, en las demás redes) con 1 hora de por medio.
   - **Programación en Instagram (`instagram_scheduler.py`)**: Los Reels de Instagram se encolan en `./config/schedule_state.db` (`instagram_scheduled_queue`) mediante `enqueue_instagram_reel()` con su horario `publish_at_utc` para que `AutoClipper_IG_API_Scheduler` los publique automáticamente vía Graph API a su hora exacta.
   - **Programación en TikTok (`tiktok_scheduler.py` + `tiktok_api_uploader.py`)**: Los Shorts de TikTok se encolan en `./config/schedule_state.db` (`tiktok_scheduled_queue`) mediante `enqueue_tiktok_video()` con su horario `publish_at_utc` para que `CreadorStudio_TikTok_API_Scheduler` los publique automáticamente vía TikTok Content Posting API v2 (`./config/tiktok_tokens.json`).
8. **Distribución Multi-Plataforma en Modo Híbrido (`multi-social-uploader`)**:
   - **YouTube (`CreadorStudio`)**: Solo reciben publicación los Shorts con **puntuación `>= 85 puntos` (máximo 6 videos)** sin importar la categoría.
   - **Demás Redes (IG/TikTok/FB)**: Reciben **los 8 Shorts generados en total**, enrutados por categoría:
     - **Categoría `gaming`**: TikTok `@creador.gaming` (`Profile 5`) + IG `@creador_gaming` (Meta Business Suite). *(Nota: `@creador_secundario` permanece vinculada en Meta pero queda excluida de este proyecto).*
     - **Categoría `ometv`**: TikTok `@creador_ometv` (`Profile 4`) + IG `@creador_ometv` (Meta Business Suite).
     - **Categoría `general`**: TikTok `@creador.clips` (`Default`), `@creador.short` (`Profile 3`), `@creador.fans` (`Profile 1`), `@creador.videos` (`Profile 2`) + IG `@creador_short`, `@creador_fans`, `@creador_videos` (Meta Business Suite) y `@creador.clips` (Selector IG Chrome).
   - **Excluida de Automatización (Solo Repost Manual del Usuario)**: `@creadorstudio` en Instagram, Facebook y TikTok.
9. **Revisión y Aprobación Local Obligatoria en Videos Grabados / VOD (Pre-Upload Preview)**:
   - En videos ya grabados o directos finalizados (modo VOD), renderiza primero hasta los **8 Shorts** localmente en `./output_shorts/<Nombre_del_Video>/`, presenta la tabla con la **Puntuación de Viralidad sobre 100 (y nota del 1 al 10)** de cada uno, indicando cuáles tienen `>= 85` (para YouTube, máx 6) y cuáles van al segundo bloque (`< 85`, solo demás redes), con enlaces locales clicables (`file:///...`) y espera aprobación antes de subir.
10. **Modo Transmisión En Vivo ("Pan Caliente" — `live_pan_caliente.py`)**:
    - En directos activos, captura bloques de **1 hora de LIVE**, extrae **máximo 8 Shorts por hora de LIVE** evaluados con la **Guía de Puntuación de Viralidad (10 Puntos)**, publica en YouTube (`CreadorStudio`) únicamente los que alcancen **`>= 85 puntos` (máximo 6)** y en las demás redes los **8 en total**, programados en orden estricto: primero los `>= 85` con **1 hora de por medio** y luego los demás (`< 85`) con **1 hora de por medio**.
