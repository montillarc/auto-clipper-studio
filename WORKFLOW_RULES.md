# 🎬 CreadorStudio — Manual Maestro y Reglas Permanentes de Flujo de Trabajo (YouTube Shorts)

> **Propósito de este documento**: Este archivo (`WORKFLOW_RULES.md`) y su espejo de carga automática (`.agents/rules/shorts-workflow.md`) definen los **parámetros obligatorios e inalterables** que el sistema autónomo y el agente siempre deben seguir al procesar cualquier video o directo del canal **CreadorStudio**.

---

## 1. Regla de Entrada y Calidad Máxima (`1080p60+`)
1. **Entrada por Link de YouTube o Carpeta Local (`./inbox_videos/`)**:
   - Cuando el usuario pase un **link de YouTube** (o deposite un archivo en `./inbox_videos/`), el sistema siempre debe priorizar el stream original **DASH `1920x1080` a `60 FPS` (o `1440p60`/`4K60`)** mediante `yt-dlp` (`format="299/312/137/bestvideo[height>=1080]"`).
   - Si el archivo local en `./inbox_videos/` está en `720p30`, `renderer.py` extrae cada fragmento desde el stream `1080p60` nativo y aplica **escalado Lanczos Full-Chroma + AMD FidelityFX CAS (`cas=strength=0.60`) + `unsharp` + NVENC `16 Mbps` (`-cq 16`)**.

---

## 2. Límite de Generación y Guía Definitiva de Puntuación de Viralidad (10 Puntos Clave)
### 2.1 Tope Estricto de Generación
- **Videos Grabados / VOD**: Máximo **8 Shorts por video**.
- **Directos En Vivo (LIVE)**: Máximo **8 Shorts por hora de LIVE**.

### 2.2 Los 10 Puntos Clave de Evaluación (Total Perfecto: 100 puntos | Calificación Final: Suma ÷ 10)
1. **El Gancho Hipnótico (Primeros 3 segundos) — [Valor: 15 puntos]**
   - **Criterio**: ¿Planta una duda insoportable, una frase polémica, una estupidez monumental o una imagen chocante de inmediato?
   - `15 pts`: Sí, te atrapa por el cuello sin piedad.
   - `7 pts`: Es pasable pero genérico.
   - `0 pts`: Empieza con "Hola, ¿cómo están?". Vete a dormir.
2. **El Ritmo y la Cero-Fricción Visual — [Valor: 10 puntos]**
   - **Criterio**: ¿La edición visual y los estímulos van al compás de la ansiedad moderna (cero silencios incómodos y cero relleno)?
   - `10 pts`: Ritmo impecable, cada segundo aporta algo.
   - `5 pts`: Tiene baches y momentos lentos.
   - `0 pts`: Parece un tutorial de YouTube del 2012 grabado con un microondas.
3. **El Factor "Un Pana Mío" (Identificación y Cercanía) — [Valor: 10 puntos]**
   - **Criterio**: ¿Conecta con códigos culturales reales, vivencias comunes o referencias locales de golpe?
   - `10 pts`: Literalmente es la vida de cualquiera en el concho o en el barrio.
   - `5 pts`: Es medianamente relatable pero le falta calle.
   - `0 pts`: Parece un discurso corporativo de LinkedIn.
4. **La Tensión del Misterio o la Pregunta Irresuelta — [Valor: 10 puntos]**
   - **Criterio**: ¿Deja un cabo suelto o genera una incógnita que obliga a ver el video hasta el final para entender el desenlace?
   - `10 pts`: Te deja con la intriga en la garganta hasta el último segundo.
   - `5 pts`: Se adivina el final a mitad de camino.
   - `0 pts`: Aburrido y predecible desde el inicio.
5. **Activación Emocional Visceral (Ira, Risa o Asombro) — [Valor: 10 puntos]**
   - **Criterio**: ¿Provoca una sacudida emocional inmediata que obligue a reaccionar?
   - `10 pts`: O te indigna o te da un ataque de risa.
   - `5 pts`: Te deja indiferente o con una sonrisa floja.
   - `0 pts`: Más plano que un vaso de agua.
6. **El Contenido "Carne de Comentarios" (Polarización y Debate) — [Valor: 10 puntos]**
   - **Criterio**: ¿Invita a la polémica, al debate intenso o a la contradicción?
   - `10 pts`: Garantiza una guerra campal en los comentarios en menos de una hora.
   - `5 pts`: La gente dice "buen video" y ya.
   - `0 pts`: Un mensaje tan tibio que no ofendería ni a una monja.
7. **Valor Agregado o Dato Perturbador/Curioso — [Valor: 10 puntos]**
   - **Criterio**: ¿Aporta una perspectiva única, un dato oculto o una narrativa contada de forma magistral?
   - `10 pts`: Te vuela la cabeza con un dato que nadie tenía.
   - `5 pts`: Es lo mismo que repiten otros diez creadores.
   - `0 pts`: Información genérica de Wikipedia.
8. **El Clickbait Estratégico (Sin Engaño Descarado) — [Valor: 10 puntos]**
   - **Criterio**: ¿El empaque (miniatura y título) genera un pico brutal de morbo sin caer en la estafa barata?
   - `10 pts`: Es un imán de clics perfecto y honrado con el contenido.
   - `5 pts`: Exagera un poco pero se pasa de mentiroso.
   - `0 pts`: Aburrido o una estafa total que frustra al usuario.
9. **Potencial de "Remix" o Compartir en Privado — [Valor: 10 puntos]**
   - **Criterio**: ¿Tiene el ADN nativo para ser reenviado por mensaje privado (WhatsApp / DM) con la frase "mira este soy yo"?
   - `10 pts`: Dispara directito al DM de tus amigos con un "Jajaja tú".
   - `5 pts`: Da igual si lo ven solo o acompañado.
   - `0 pts`: Nadie en su sano juicio lo compartiría.
10. **El Factor de Cierre o "Efecto Loop" — [Valor: 5 puntos]**
    - **Criterio**: ¿Tiene un final memorable o un bucle perfecto que conecte con el inicio?
    - `5 pts`: Cierra con broche de oro o te deja queriendo verlo otra vez.
    - `2 pts`: Termina de golpe de manera extraña.
    - `0 pts`: Se apaga la música y se acaba de la nada.

### 2.3 Escala de Calificación y Regla de Filtrado por Plataforma
- **`90 - 100 puntos (9.0 - 10.0)`**: Tienes oro en las manos 🔥.
- **`75 - 89 puntos (7.5 - 8.9)`**: Buen video, va a funcionar bien ⚡.
- **`50 - 74 puntos (5.0 - 7.4)`**: Meh 😐.
- **`Menos de 50 puntos (< 5.0)`**: Bodrio total ❌ (Se descarta siempre).

> **Regla de Publicación por Puntuación**:
> - **YouTube (`CreadorStudio`)**: **SOLO se publican los Shorts con puntuación igual o mayor a 85 puntos (`>= 85`)**, con un **máximo de 6 videos en YouTube**.
> - **Demás Redes (Instagram + TikTok + Facebook según categoría)**: Se publican **los 8 Shorts en total generados**.
> - **Orden de Subida e Intervalo ("1 Hora de por medio")**:
>   1. **Primero** se suben los Shorts que cumplan la regla de la puntuación (**`>= 85 puntos`**) con **1 hora de por medio** entre cada uno.
>   2. **Luego** son seguidos de **los demás Shorts (`< 85 puntos`)** con el **mismo tiempo de por medio (1 hora entre cada uno)**.

---

## 3. Regla de Contexto Completo (Principio a Fin, hasta `2:30 - 3:00 min`) y Carpeta por Video
1. **Contexto Completo de Principio a Fin**: Prohibido cortar conversaciones o ideas por la mitad.
2. **Carpeta Exclusiva por Video dentro de `./output_shorts/`**: `./output_shorts/<Nombre_del_Video>/`.

---

## 4. Regla de Detección de Escena por Fragmento (`OmeTV 50/50`, `Split-Screen` y `Fullscreen`)
- **`ometv`**: Arriba (`1080x960`) CreadorStudio + Abajo (`1080x960`) Invitado + Banner `config/ometv_banner.png` en `y=960`.
- **`split_streamer`**: Arriba (`1080x720`) Cámara de CreadorStudio + Abajo (`1080x1200`) Contenido + Subtítulos en `y=720`.
- **`fullscreen`**: Corte vertical `1080x1920` centrado en el rostro + Subtítulos en `y=1580`.

---

## 5. Regla de Audio 100% Limpio y Metadatos
- Audio original intacto (`playback_speed=1.0`, `enable_bgm=False`).
- Metadatos: 1️⃣ **TÍTULO VIRAL CORTO con Emojis** + `#Shorts`, 2️⃣ **DESCRIPCIÓN BREVE con Emojis + enlace del video original**, 3️⃣ **3 HASHTAGS más importantes del tema + `#Viral`** (`#Shorts`).
