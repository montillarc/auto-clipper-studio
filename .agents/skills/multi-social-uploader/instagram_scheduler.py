"""
Instagram Graph API Scheduled Queue & Background Dispatcher (instagram_scheduler.py)
Permite programar Reels de Instagram en los mismos horarios estratégicos que YouTube Shorts
(09:00 AM, 11:00 AM, 12:00 PM, 02:00 PM, 04:00 PM, 06:00 PM, 08:00 PM, 10:00 PM AST)
sin usar navegador ni mover el mouse.

- Guarda los Reels programados en ./config/schedule_state.db (tabla instagram_scheduled_queue).
- Una tarea programada de Windows (AutoClipper_IG_API_Scheduler) ejecuta este script en segundo plano
  cada 15 minutos con pythonw.exe y publica automáticamente vía Instagram Graph API los Reels
  cuya hora programada (scheduled_time_utc) ya haya llegado.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure UTF-8 output when stdout is available
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import imageio_ffmpeg

BASE_DIR = Path(__file__).resolve().parents[3]
CONFIG_DIR = BASE_DIR / "config"
LOGS_DIR = BASE_DIR / "logs"
DB_PATH = CONFIG_DIR / "schedule_state.db"
META_TOKEN_PATH = CONFIG_DIR / "meta_token.json"
FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()


def _silent_subprocess_kwargs() -> Dict[str, Any]:
    """Garantiza ejecución invisible sin ventana de consola en Windows (CREATE_NO_WINDOW + SW_HIDE)."""
    if os.name != "nt":
        return {}
    kw: Dict[str, Any] = {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
    }
    if hasattr(subprocess, "STARTUPINFO"):
        si = subprocess.STARTUPINFO()
        si.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0x00000001)
        si.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        kw["startupinfo"] = si
    return kw

LOGS_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger("instagram_scheduler")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    _fh = logging.FileHandler(LOGS_DIR / "instagram_scheduler.log", encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(_fh)
    if sys.stdout:
        _sh = logging.StreamHandler(sys.stdout)
        _sh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(_sh)

from instagram_api_uploader import IG_ACCOUNTS, load_config, publish_reel_via_url, stage_video_url


def init_ig_queue_db(db_path: Path = DB_PATH) -> Path:
    """Crea la tabla instagram_scheduled_queue en ./config/schedule_state.db si no existe."""
    db_file = Path(db_path).resolve()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS instagram_scheduled_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_path TEXT NOT NULL,
                account_key TEXT NOT NULL,
                ig_user_id TEXT NOT NULL,
                caption TEXT NOT NULL,
                scheduled_time_utc TEXT NOT NULL,
                scheduled_time_ast TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                container_id TEXT,
                media_id TEXT,
                permalink TEXT,
                error TEXT,
                created_at_utc TEXT NOT NULL,
                published_at_utc TEXT,
                UNIQUE(video_path, account_key)
            )
            """
        )
        conn.commit()
    return db_file


def prepare_ig_staging_file(video_path: str) -> str:
    """
    Prepara una copia MP4 optimizada (< 105 MB) en 1080p60 H.264 NVENC + AAC 48kHz
    para que incluso los Shorts de contexto completo (2:00 a 3:00 min) suban rápido
    al CDN temporal y sean aceptados al 100% por Instagram Graph API.
    """
    out_dir = os.path.join(os.path.dirname(video_path), "ig_ready_8m")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, os.path.basename(video_path))
    if os.path.exists(out_path) and 1024 * 1024 < os.path.getsize(out_path) < 115 * 1024 * 1024:
        return out_path

    cmd = [
        FFMPEG_BIN,
        "-y",
        "-i",
        video_path,
        "-r",
        "60",
        "-c:v",
        "h264_nvenc",
        "-preset",
        "p5",
        "-b:v",
        "4.8M",
        "-maxrate",
        "5.8M",
        "-bufsize",
        "12M",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        out_path,
    ]
    try:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **_silent_subprocess_kwargs(),
        )
    except subprocess.CalledProcessError:
        cmd_cpu = [
            FFMPEG_BIN,
            "-y",
            "-i",
            video_path,
            "-r",
            "60",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-b:v",
            "4.8M",
            "-maxrate",
            "5.8M",
            "-bufsize",
            "12M",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            out_path,
        ]
        subprocess.run(
            cmd_cpu,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **_silent_subprocess_kwargs(),
        )
    return out_path


def enqueue_instagram_reel(
    video_path: str | Path,
    account_key: str,
    caption: str,
    scheduled_time_utc: str,
    scheduled_time_ast: str = "",
    db_path: Path = DB_PATH,
    ig_user_id: str = "",
) -> int:
    """
    Encola un Reel de Instagram para que se publique automáticamente en segundo plano
    cuando llegue su scheduled_time_utc (ej. '2026-10-26T16:00:00Z').
    """
    init_ig_queue_db(db_path)
    acct_clean = account_key.lstrip("@").strip().lower() or "creador_short"
    resolved_ig_id = str(ig_user_id or IG_ACCOUNTS.get(acct_clean) or "").strip()
    if not resolved_ig_id:
        hub_path = CONFIG_DIR / "social_hub_config.json"
        if hub_path.exists():
            try:
                hub_raw = json.loads(hub_path.read_text(encoding="utf-8"))
                for cat_obj in (hub_raw.get("categories") or {}).values():
                    for acc in cat_obj.get("accounts") or []:
                        if (
                            str(acc.get("platform") or "").lower() == "instagram"
                            and str(acc.get("handle") or "").lstrip("@").strip().lower() == acct_clean
                            and str(acc.get("external_id") or "").strip()
                        ):
                            resolved_ig_id = str(acc["external_id"]).strip()
                            break
            except Exception:
                pass
    ig_user_id_final = resolved_ig_id or acct_clean
    resolved_video = str(Path(video_path).resolve())
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not scheduled_time_ast:
        scheduled_time_ast = scheduled_time_utc

    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO instagram_scheduled_queue (
                video_path, account_key, ig_user_id, caption,
                scheduled_time_utc, scheduled_time_ast, status, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)
            ON CONFLICT(video_path, account_key) DO UPDATE SET
                ig_user_id = excluded.ig_user_id,
                caption = excluded.caption,
                scheduled_time_utc = excluded.scheduled_time_utc,
                scheduled_time_ast = excluded.scheduled_time_ast,
                status = CASE
                    WHEN instagram_scheduled_queue.status = 'PUBLISHED' THEN 'PUBLISHED'
                    ELSE 'PENDING'
                END,
                error = CASE
                    WHEN instagram_scheduled_queue.status = 'PUBLISHED' THEN instagram_scheduled_queue.error
                    ELSE NULL
                END
            """,
            (
                resolved_video,
                acct_clean,
                ig_user_id_final,
                caption,
                scheduled_time_utc,
                scheduled_time_ast,
                now_iso,
            ),
        )
        conn.commit()
        row_id = cursor.lastrowid or 0

    logger.info(
        "[QUEUE] Reel encolado -> @%s (IG ID %s) | Horario: %s (%s) | Archivo: %s",
        acct_clean,
        ig_user_id_final,
        scheduled_time_ast,
        scheduled_time_utc,
        Path(resolved_video).name,
    )
    return row_id


def process_due_instagram_queue(db_path: Path = DB_PATH, force_all: bool = False) -> Dict[str, int]:
    """
    Revisa la cola en ./config/schedule_state.db y publica vía Instagram Graph API
    todos los Reels con status='PENDING' cuyo horario programado ya haya llegado.
    """
    init_ig_queue_db(db_path)
    now_utc_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if force_all:
            cursor.execute(
                """
                SELECT * FROM instagram_scheduled_queue
                WHERE status IN ('PENDING', 'FAILED')
                ORDER BY scheduled_time_utc ASC, id ASC
                """
            )
        else:
            cursor.execute(
                """
                SELECT * FROM instagram_scheduled_queue
                WHERE status = 'PENDING' AND scheduled_time_utc <= ?
                ORDER BY scheduled_time_utc ASC, id ASC
                """,
                (now_utc_iso,),
            )
        due_rows = [dict(r) for r in cursor.fetchall()]

    if not due_rows:
        logger.info("No hay Reels pendientes vencidos en este momento (%s).", now_utc_iso)
        return {"processed": 0, "published": 0, "failed": 0}

    try:
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    except Exception:
        pass

    cfg = load_config()
    access_token = cfg["access_token"]

    staged_cache: Dict[str, str] = {}
    published_count = 0
    failed_count = 0

    try:
        for item in due_rows:
            row_id = item["id"]
            video_path = item["video_path"]
            acct = item["account_key"]
            ig_id = item["ig_user_id"]
            caption = item["caption"]
            sched_ast = item["scheduled_time_ast"]

            if not os.path.exists(video_path):
                err_msg = f"Archivo de video no encontrado: {video_path}"
                logger.error("[ID=%s] %s", row_id, err_msg)
                with sqlite3.connect(str(db_path)) as conn:
                    conn.execute(
                        "UPDATE instagram_scheduled_queue SET status = 'FAILED', error = ? WHERE id = ?",
                        (err_msg, row_id),
                    )
                    conn.commit()
                failed_count += 1
                continue

            logger.info(
                "Publicando Reel programado [ID=%s] -> @%s (%s) | Programado: %s | Video: %s",
                row_id,
                acct,
                ig_id,
                sched_ast,
                os.path.basename(video_path),
            )

            success = False
            last_error = ""
            for attempt in range(3):
                try:
                    if video_path not in staged_cache:
                        ready_mp4 = prepare_ig_staging_file(video_path)
                        staged_cache[video_path] = stage_video_url(ready_mp4)
                    video_url = staged_cache[video_path]

                    res = publish_reel_via_url(ig_id, video_url, caption, access_token)
                    pub_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    with sqlite3.connect(str(db_path)) as conn:
                        conn.execute(
                            """
                            UPDATE instagram_scheduled_queue
                            SET status = 'PUBLISHED',
                                container_id = ?,
                                media_id = ?,
                                permalink = ?,
                                error = NULL,
                                published_at_utc = ?
                            WHERE id = ?
                            """,
                            (
                                res.get("container_id", ""),
                                res.get("media_id", ""),
                                res.get("permalink", ""),
                                pub_now,
                                row_id,
                            ),
                        )
                        conn.commit()
                    logger.info(
                        "✅ Publicado [ID=%s] en @%s -> %s",
                        row_id,
                        acct,
                        res.get("permalink", ""),
                    )
                    published_count += 1
                    success = True
                    break
                except Exception as exc:
                    last_error = str(exc)
                    logger.warning(
                        "⚠️ Intento %s/3 falló para [ID=%s] (@%s): %s",
                        attempt + 1,
                        row_id,
                        acct,
                        last_error,
                    )
                    staged_cache.pop(video_path, None)
                    time.sleep(5)

            if not success:
                with sqlite3.connect(str(db_path)) as conn:
                    conn.execute(
                        "UPDATE instagram_scheduled_queue SET status = 'FAILED', error = ? WHERE id = ?",
                        (last_error, row_id),
                    )
                    conn.commit()
                failed_count += 1
    finally:
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)  # ES_CONTINUOUS
        except Exception:
            pass

    return {
        "processed": len(due_rows),
        "published": published_count,
        "failed": failed_count,
    }


def list_queue(db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    """Devuelve el estado actual de la cola programada de Instagram."""
    init_ig_queue_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, account_key, scheduled_time_utc, scheduled_time_ast,
                   status, permalink, video_path, error
            FROM instagram_scheduled_queue
            ORDER BY scheduled_time_utc ASC, id ASC
            """
        )
        return [dict(r) for r in cursor.fetchall()]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Instagram Graph API Scheduled Queue Dispatcher")
    parser.add_argument("--run-due", action="store_true", help="Publica los Reels cuyo horario ya llegó")
    parser.add_argument("--force-all", action="store_true", help="Publica todos los Reels pendientes inmediatamente")
    parser.add_argument("--list", action="store_true", help="Muestra la cola actual programada")
    args = parser.parse_args()

    if args.list:
        rows = list_queue()
        if sys.stdout:
            print(f"Total en cola de Instagram: {len(rows)}")
            for r in rows:
                print(
                    f"  [{r['id']}] {r['status']} | @{r['account_key']} | {r['scheduled_time_ast']} | "
                    f"{os.path.basename(r['video_path'])} | {r.get('permalink') or r.get('error') or ''}"
                )
    elif args.force_all:
        res = process_due_instagram_queue(force_all=True)
        if sys.stdout:
            print(json.dumps(res, ensure_ascii=False))
    else:
        res = process_due_instagram_queue(force_all=False)
        if sys.stdout:
            print(json.dumps(res, ensure_ascii=False))
