---
name: multi-social-uploader
description: Distributes and schedules rendered 1080p60 vertical Shorts from ./output_shorts/ in Hybrid Mode (Auto-Categorization + User Confirmation). ALL Shorts always go to YouTube (CreadorStudio), @creadorstudio on IG/TikTok is excluded from automation (kept in Meta Business Suite for manual reposts only), and secondary TikTok/Instagram accounts are routed by category (Gaming, OmeTV, General) after user confirmation.
---

# Skill 5: Multi-Social Uploader (Modo Híbrido: Categorización + Confirmación Previa)

## Reglas de Oro de Distribución (`./config/social_accounts.json`)

1. **YouTube Shorts (`CreadorStudio` — Canal Principal)**:
   - **TODOS los Shorts (100%) van SIEMPRE para YouTube**, sin importar su categoría (`Gaming`, `OmeTV` o `General`).
2. **Cuenta Principal `@creadorstudio` en Instagram, Facebook y TikTok (Excluida de Automatización)**:
   - Permanece conectada dentro de **Meta Business Suite**, pero **NUNCA se sube contenido automáticamente a `@creadorstudio`** en Instagram/Facebook ni TikTok.
   - Está reservada exclusivamente para que el propietario haga **repost manual** del contenido de las cuentas secundarias.
3. **Modo Híbrido (Pre-Categorización por Nicho + Pregunta Obligatoria al Usuario)**:
   - Antes de procesar y subir un lote, en la tabla de **Estimación Previa**, el agente clasifica cada clip y sugiere las cuentas secundarias correspondientes según su categoría, preguntando siempre al usuario:
     > *"En YouTube van todos para `CreadorStudio`. Para TikTok e Instagram, según la categoría detectada (`[Categoría]`), propongo subirlos a `[Cuentas]`. ¿Confirmas estas cuentas o quieres cambiar alguna?"*

---

## Tabla Oficial de Categorías y Cuentas Secundarias

| Categoría | YouTube (Fijo) | TikTok Studio (Brave) | Instagram Reels (Chrome `Creador`) | Contenido |
| :--- | :--- | :--- | :--- | :--- |
| 🎮 **`gaming`** | ✅ `CreadorStudio` | • `@creador.gaming` (`Profile 5`) | • `@creador_gaming` *(Suite)* | Exclusivo para gameplays, pruebas de juegos, PC/GPU, DLSS, OBS o reacciones jugando. *(Nota: `@creador_secundario` permanece vinculada en Meta pero excluida para otro proyecto).* |
| 🌍 **`ometv`** | ✅ `CreadorStudio` | • `@creador_ometv` (`Profile 4`) | • `@creador_ometv` *(Suite)* | Exclusivo para clips de OmeTV, charlas con desconocidos e interacciones en vivo. |
| 🔥 **`general`** | ✅ `CreadorStudio` | • `@creador.clips` (`Default`)<br>• `@creador.short` (`Profile 3`)<br>• `@creador.fans` (`Profile 1`)<br>• `@creador.videos` (`Profile 2`) | • `@creador_short` *(Suite)*<br>• `@creador_fans` *(Suite)*<br>• `@creador_videos` *(Suite)*<br>• `@creador.clips` *(Selector IG Chrome)* | Reacciones, noticias, debates, humor, polémicas y mejores momentos generales del stream. |
| 🚫 **Manual** | — | • `@creadorstudio` *(Fuera de automatización)* | • `@creadorstudio` / `CreadorStudio` *(Permanece en Meta Suite, fuera de automatización)* | Solo para reposteo manual por parte del usuario. |
