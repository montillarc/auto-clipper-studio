---
name: strategic-time-calculator
description: >-
  Connects to ./config/schedule_state.db (SQLite), defines strategic publishing windows in
  America/Santo_Domingo (AST) timezone (Mon-Fri: 12:30, 18:00, 21:00; Sat-Sun: 11:00, 16:00, 20:00),
  queries the last assigned slot, reserves the next available slot in SQLite to prevent duplicates,
  and returns the UTC ISO 8601 timestamp (YYYY-MM-DDTHH:MM:SSZ) required by YouTube API.
---

# Strategic Time Calculator (`strategic-time-calculator`)

Esta Skill gestiona la cola de programación de YouTube Shorts persistiendo cada ventana reservada en `./config/schedule_state.db` (SQLite).

## Ventanas Estratégicas (`America/Santo_Domingo` - AST, UTC-4)
- **Lunes a Viernes**: `12:30`, `18:00`, `21:00`
- **Sábados y Domingos**: `11:00`, `16:00`, `20:00`

## Lógica de Asignación
1. Conecta a `./config/schedule_state.db` y crea la tabla `scheduled_slots` si no existe (con restricción `UNIQUE` sobre `publish_at_utc` para evitar colisiones).
2. Consulta el último slot reservado y lo compara con la hora actual en `America/Santo_Domingo` (con margen mínimo de seguridad de 15 minutos hacia el futuro).
3. Encuentra el siguiente slot estratégico libre, lo registra en la base de datos y devuelve el timestamp en formato UTC ISO 8601 estricto (`YYYY-MM-DDTHH:MM:SSZ`) requerido por `status.publishAt` de YouTube Data API v3.

## Uso

### CLI
```bash
.\.venv\Scripts\python.exe .agents/skills/strategic-time-calculator/calculator.py --video-name "mi_short.mp4"
```

### Python
```python
from calculator import get_and_reserve_next_slot

publish_at_utc = get_and_reserve_next_slot(video_name="mi_short.mp4")
# Ejemplo: "2026-10-22T22:00:00Z"
```
