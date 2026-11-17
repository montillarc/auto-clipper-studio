"""
TikTok Content Posting API v2 — Scheduled Queue & Background Dispatcher (tiktok_scheduler.py)
Permite programar Shorts en las 6 cuentas secundarias de TikTok en los mismos 8 horarios estratégicos
que YouTube e Instagram (09:00 AM, 11:00 AM, 12:00 PM, 02:00 PM, 04:00 PM, 06:00 PM, 08:00 PM, 10:00 PM AST)
100% en segundo plano mediante la API oficial de TikTok.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parents[3]
CONFIG_DIR = BASE_DIR / "config"
LOGS_DIR = BASE_DIR / "logs"
DB_PATH = CONFIG_DIR / "schedule_state.db"

LOGS_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / "tiktok_scheduler.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout) if sys.stdout else logging.NullHandler(),
    ],
)
logger = logging.getLogger("tiktok_scheduler")

from tiktok_api_uploader import TIKTOK_ACCOUNTS, publish_tiktok_video


def init_tiktok_queue_db(db_path: Path = DB_PATH) -> Path:
    """Crea la tabla tiktok_scheduled_queue en ./config/schedule_state.db si no existe."""
    db_file = Path(db_path).resolve()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tiktok_scheduled_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_path TEXT NOT NULL,
                account_key TEXT NOT NULL,
                caption TEXT NOT NULL,
                scheduled_time_utc TEXT NOT NULL,
                scheduled_time_ast TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                publish_id TEXT,
                post_id TEXT,
                error TEXT,
                created_at_utc TEXT NOT NULL,
                published_at_utc TEXT,
                UNIQUE(video_path, account_key)
            )
            """
        )
        conn.commit()
    return db_file


def enqueue_tiktok_video(
    video_path: str | Path,
    account_key: str,
    caption: str,
    scheduled_time_utc: str,
    scheduled_time_ast: str = "",
    db_path: Path = DB_PATH,
) -> int:
    """Encola un Short de TikTok para publicarse vía API cuando llegue su scheduled_time_utc."""
    init_tiktok_queue_db(db_path)
    acct_clean = account_key.lstrip("@").strip().lower()
    if not acct_clean:
        raise ValueError("La cuenta de TikTok no puede estar vacía.")

    resolved_video = str(Path(video_path).resolve())
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not scheduled_time_ast:
        scheduled_time_ast = scheduled_time_utc

    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO tiktok_scheduled_queue (
                video_path, account_key, caption,
                scheduled_time_utc, scheduled_time_ast, status, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, 'PENDING', ?)
            ON CONFLICT(video_path, account_key) DO UPDATE SET
                caption = excluded.caption,
                scheduled_time_utc = excluded.scheduled_time_utc,
                scheduled_time_ast = excluded.scheduled_time_ast,
                status = CASE
                    WHEN tiktok_scheduled_queue.status IN ('PUBLISHED', 'INBOX_DRAFT') THEN tiktok_scheduled_queue.status
                    ELSE 'PENDING'
                END,
                error = CASE
                    WHEN tiktok_scheduled_queue.status IN ('PUBLISHED', 'INBOX_DRAFT') THEN tiktok_scheduled_queue.error
                    ELSE NULL
                END
            """,
            (resolved_video, acct_clean, caption, scheduled_time_utc, scheduled_time_ast, now_iso),
        )
        conn.commit()
        row_id = cursor.lastrowid or 0

    logger.info(
        "[TIKTOK QUEUE] Encolado -> @%s | Horario: %s (%s) | Archivo: %s",
        acct_clean,
        scheduled_time_ast,
        scheduled_time_utc,
        Path(resolved_video).name,
    )
    return row_id


def process_due_tiktok_queue(db_path: Path = DB_PATH, force_all: bool = False) -> Dict[str, int]:
    """Publica vía TikTok API todos los Shorts en cola cuya hora programada ya haya llegado."""
    init_tiktok_queue_db(db_path)
    now_utc_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if force_all:
            cursor.execute(
                """
                SELECT * FROM tiktok_scheduled_queue
                WHERE status IN ('PENDING', 'FAILED')
                ORDER BY scheduled_time_utc ASC, id ASC
                """
            )
        else:
            cursor.execute(
                """
                SELECT * FROM tiktok_scheduled_queue
                WHERE status = 'PENDING' AND scheduled_time_utc <= ?
                ORDER BY scheduled_time_utc ASC, id ASC
                """,
                (now_utc_iso,),
            )
        due_rows = [dict(r) for r in cursor.fetchall()]

    if not due_rows:
        logger.info("No hay Shorts pendientes vencidos en este momento (%s).", now_utc_iso)
        return {"processed": 0, "published": 0, "failed": 0}

    publish_mode = "DIRECT_POST"
    for cfg_cand in (Path(db_path).resolve().parent / "social_hub_config.json", CONFIG_DIR / "social_hub_config.json"):
        if cfg_cand.exists():
            try:
                hub_raw = json.loads(cfg_cand.read_text(encoding="utf-8"))
                publish_mode = str(
                    ((hub_raw.get("api_settings") or {}).get("tiktok") or {}).get("publish_mode")
                    or "DIRECT_POST"
                )
                break
            except Exception:
                pass

    if publish_mode.strip().upper() == "TIKTOK_STUDIO":
        logger.info(
            "TikTok configurado en modo TIKTOK_STUDIO (navegador PC con permiso): %s fila(s) conservadas en PENDING sin enviar a Sandbox Inbox.",
            len(due_rows),
        )
        return {
            "processed": 0,
            "published": 0,
            "failed": 0,
            "skipped_browser_mode": len(due_rows),
        }

    # Mantener el sistema despierto mientras dure la transferencia si despertó por WakeToRun,
    # sin forzar jamás la suspensión manual al terminar (Windows maneja UNATTENDSLEEP solo si no hay usuario).
    try:
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    except Exception:
        pass

    published_count = 0
    failed_count = 0

    try:
        for item in due_rows:
            row_id = item["id"]
            video_path = item["video_path"]
            acct = item["account_key"]
            caption = item["caption"]

            if not os.path.exists(video_path):
                err_msg = f"Archivo no encontrado: {video_path}"
                with sqlite3.connect(str(db_path)) as conn:
                    conn.execute(
                        "UPDATE tiktok_scheduled_queue SET status = 'FAILED', error = ? WHERE id = ?",
                        (err_msg, row_id),
                    )
                    conn.commit()
                failed_count += 1
                continue

            try:
                res = publish_tiktok_video(acct, video_path, caption, mode=publish_mode)
                pub_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                res_status = str(res.get("status") or "").strip().upper()
                publish_id = str(res.get("publish_id") or "").strip()
                post_id = str(res.get("post_id") or "").strip()
                # Solo PUBLISH_COMPLETE (o un post_id real) cuenta como publicado en el perfil;
                # SEND_TO_USER_INBOX / v_inbox_file solo envía un borrador a la bandeja de la app TikTok.
                if res_status == "SEND_TO_USER_INBOX" or (publish_id.startswith("v_inbox_file") and not post_id):
                    target_status = "INBOX_DRAFT"
                else:
                    target_status = "PUBLISHED"
                with sqlite3.connect(str(db_path)) as conn:
                    conn.execute(
                        """
                        UPDATE tiktok_scheduled_queue
                        SET status = ?,
                            publish_id = ?,
                            post_id = ?,
                            error = NULL,
                            published_at_utc = ?
                        WHERE id = ?
                        """,
                        (
                            target_status,
                            publish_id,
                            post_id,
                            pub_now,
                            row_id,
                        ),
                    )
                    conn.commit()
                published_count += 1
            except Exception as exc:
                err_str = str(exc)
                logger.error("Error publicando TikTok [ID=%s] (@%s): %s", row_id, acct, err_str)
                with sqlite3.connect(str(db_path)) as conn:
                    conn.execute(
                        "UPDATE tiktok_scheduled_queue SET status = 'FAILED', error = ? WHERE id = ?",
                        (err_str, row_id),
                    )
                    conn.commit()
                failed_count += 1
    finally:
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)  # ES_CONTINUOUS (libera bloqueo)
        except Exception:
            pass

    return {"processed": len(due_rows), "published": published_count, "failed": failed_count}


def list_queue(db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    init_tiktok_queue_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, account_key, scheduled_time_utc, scheduled_time_ast,
                   status, publish_id, post_id, video_path, error
            FROM tiktok_scheduled_queue
            ORDER BY scheduled_time_utc ASC, id ASC
            """
        )
        return [dict(r) for r in cursor.fetchall()]


def suspend_if_unattended_wake() -> None:
    """
    Si la PC se despertó automáticamente de suspensión (Reason SxTransition en Kernel-Power 566)
    para ejecutar la tarea programada y el usuario NO ha tocado el mouse ni el teclado,
    vuelve a poner la PC en suspensión (Standby S3) al terminar, incluso si alguna app en
    segundo plano intenta mantener Windows despierto.
    """
    try:
        import ctypes
        import subprocess

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        def get_idle_seconds() -> float:
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
            tick = ctypes.windll.kernel32.GetTickCount()
            return ((tick - lii.dwTime) & 0xFFFFFFFF) / 1000.0

        # Esperar unos segundos para que instagram_scheduler.py también termine si arrancó a la vez
        time.sleep(10)

        # Si el usuario movió el mouse o presionó una tecla recientemente, NO suspender jamás
        if get_idle_seconds() < 15.0:
            logger.info("[AUTO-SLEEP] Usuario activo (idle < 15s). No se suspende la PC.")
            return

        # Consultar el último evento Kernel-Power 566 (estado de sesión/pantalla) y esperar si instagram_scheduler sigue subiendo
        ps_check = (
            "for ($i=0; $i -lt 36; $i++) { "
            "$ig = Get-CimInstance Win32_Process -Filter \"Name LIKE 'python%' AND CommandLine LIKE '%instagram_scheduler.py%'\" -ErrorAction SilentlyContinue; "
            "if (-not $ig) { break }; Start-Sleep -Seconds 5 "
            "}; "
            "$ev = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-Kernel-Power'; Id=566} "
            "-MaxEvents 1 -ErrorAction SilentlyContinue; "
            "if ($ev -and ((Get-Date) - $ev.TimeCreated).TotalMinutes -lt 30 -and $ev.Message -match 'Reason SxTransition') "
            "{ 'UNATTENDED_SX' } else { 'USER_ACTIVE' }"
        )
        res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_check],
            capture_output=True,
            text=True,
            timeout=200,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        mode = (res.stdout or "").strip()
        if mode == "UNATTENDED_SX" and get_idle_seconds() >= 15.0:
            logger.info("[AUTO-SLEEP] Despertar desatendido confirmado (Reason SxTransition). Volviendo a suspender la PC...")
            subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-WindowStyle",
                    "Hidden",
                    "-Command",
                    "Start-Sleep -Seconds 2; Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)",
                ],
                creationflags=0x00000008 | 0x08000000,  # DETACHED_PROCESS | CREATE_NO_WINDOW
            )
        else:
            logger.info("[AUTO-SLEEP] Sesión activa (%s). La PC permanece encendida.", mode)
    except Exception as exc:
        logger.warning("[AUTO-SLEEP] No se pudo verificar estado desatendido: %s", exc)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TikTok API Scheduled Queue Dispatcher")
    parser.add_argument("--run-due", action="store_true", help="Publica los Shorts cuyo horario ya llegó")
    parser.add_argument("--force-all", action="store_true", help="Publica todos los pendientes ahora")
    parser.add_argument("--list", action="store_true", help="Muestra la cola programada de TikTok")
    args = parser.parse_args()

    if args.list:
        rows = list_queue()
        if sys.stdout:
            print(f"Total en cola de TikTok: {len(rows)}")
            for r in rows:
                print(
                    f"  [{r['id']}] {r['status']} | @{r['account_key']} | {r['scheduled_time_ast']} | "
                    f"{os.path.basename(r['video_path'])}"
                )
    elif args.force_all:
        out = process_due_tiktok_queue(force_all=True)
        if sys.stdout:
            print(json.dumps(out, ensure_ascii=False))
    else:
        out = process_due_tiktok_queue(force_all=False)
        if sys.stdout:
            print(json.dumps(out, ensure_ascii=False))
        suspend_if_unattended_wake()
