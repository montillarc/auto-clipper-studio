"""
Coordinador de Autorización por WhatsApp para Subidas en TikTok Studio Web.

Utiliza un puente local HTTP de WhatsApp (opcional, por defecto `http://127.0.0.1:3847`) para:
  1. Detectar cuándo hay TikToks vencidos o próximos a publicarse (`<= +35 min`)
     y el modo configurado es `TIKTOK_STUDIO`.
  2. Enviar un aviso claro por WhatsApp al propietario preguntando si puede usar
     la computadora (Brave) para subir/programar las entregas.
  3. Escuchar su respuesta (`aprobado`, `está bien`, `dale`, `sí`, etc. o
     `ocupado` / `luego` / `no`) sin spam ni bloqueos, lanzar `tiktok_studio_browser.py`
     al aprobar y reportar el resultado final por WhatsApp.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("tiktok_whatsapp_coordinator")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BASE_DIR = Path(__file__).resolve().parents[3]
CONFIG_DIR = BASE_DIR / "config"
DB_PATH = CONFIG_DIR / "schedule_state.db"
APPROVAL_STATE_FILENAME = "tiktok_whatsapp_approval.json"
WHATSAPP_BRIDGE_URL = os.environ.get("SHORTYT_WHATSAPP_BRIDGE_URL", "http://127.0.0.1:3847").rstrip("/")
AST_TZ = ZoneInfo("America/Santo_Domingo")
SHORTYT_WA_PROJECT_TAG = "AutoClipper_TikTok"

_APPROVAL_LOCK = threading.Lock()


def _strip_accents_lower(text: str) -> str:
    norm = unicodedata.normalize("NFKD", str(text or ""))
    no_accents = "".join(ch for ch in norm if not unicodedata.combining(ch))
    return " ".join(no_accents.lower().split())


_DECLINE_PATTERN = re.compile(
    r"\b(no|ocupado|ocupada|luego|despues|ahora no|espera|cancela|cancelar|para luego|mas tarde|todavia no)\b",
    re.IGNORECASE,
)
_APPROVE_PATTERN = re.compile(
    r"\b(aprobado|apruebo|esta bien|dale|ok|okey|okay|si|autorizado|autorizo|mete mano|rompe|sube|subelo|sube todo|adelante|hazlo|procede)\b",
    re.IGNORECASE,
)


def classify_whatsapp_permission_reply(text: str) -> Optional[str]:
    """Devuelve 'approved', 'declined' o None según la intención del mensaje en español."""
    clean = _strip_accents_lower(text)
    if not clean:
        return None
    if _DECLINE_PATTERN.search(clean):
        return "declined"
    if _APPROVE_PATTERN.search(clean):
        return "approved"
    return None


def _read_approval_state(config_dir: Path) -> Dict[str, Any]:
    path = Path(config_dir) / APPROVAL_STATE_FILENAME
    default_state: Dict[str, Any] = {
        "state": "idle",
        "batch_id": None,
        "sent_ts_ms": 0,
        "sent_message_ids": [],
        "row_ids": [],
        "cooldown_until_utc": None,
        "processed_msg_ids": [],
        "last_summary": None,
    }
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                default_state.update(loaded)
        except Exception:
            pass
    return default_state


def _write_approval_state(config_dir: Path, state: Dict[str, Any]) -> None:
    path = Path(config_dir) / APPROVAL_STATE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    # Acotar historial de mensajes ya procesados
    if isinstance(state.get("processed_msg_ids"), list) and len(state["processed_msg_ids"]) > 100:
        state["processed_msg_ids"] = state["processed_msg_ids"][-100:]
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def get_whatsapp_bridge_status(bridge_url: str = WHATSAPP_BRIDGE_URL) -> Dict[str, Any]:
    """Consulta de forma segura si el túnel de WhatsApp Bridge está activo y conectado."""
    try:
        with urllib.request.urlopen(f"{bridge_url.rstrip('/')}/status", timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "connected": bool(data.get("ok") and data.get("status") == "connected"),
                "status": str(data.get("status") or "unknown"),
                "owner_number": data.get("owner_number"),
            }
    except Exception as exc:
        return {"connected": False, "status": "unreachable", "error": str(exc)}


def send_whatsapp_bridge_message(
    text: str,
    *,
    etapa: str = "TIKTOK_STUDIO_APPROVAL",
    proyecto: str = SHORTYT_WA_PROJECT_TAG,
    bridge_url: str = WHATSAPP_BRIDGE_URL,
) -> Dict[str, Any]:
    """Envía un mensaje saliente por el túnel local de WhatsApp Bridge."""
    payload = json.dumps(
        {
            "text": text,
            "proyecto": proyecto,
            "etapa": etapa,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{bridge_url.rstrip('/')}/send",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_whatsapp_bridge_messages(
    since_ms: int,
    *,
    bridge_url: str = WHATSAPP_BRIDGE_URL,
) -> List[Dict[str, Any]]:
    """Lee mensajes entrantes recibidos desde `since_ms` en la bandeja del WhatsApp Bridge."""
    with urllib.request.urlopen(
        f"{bridge_url.rstrip('/')}/messages?since={int(since_ms)}",
        timeout=5,
    ) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        msgs = data.get("messages") or []
        return [m for m in msgs if isinstance(m, dict)]


def get_tiktok_publish_mode(config_dir: Path = CONFIG_DIR) -> str:
    hub_path = Path(config_dir) / "social_hub_config.json"
    if not hub_path.exists():
        return "DIRECT_POST"
    try:
        raw = json.loads(hub_path.read_text(encoding="utf-8"))
        return (
            str(((raw.get("api_settings") or {}).get("tiktok") or {}).get("publish_mode") or "DIRECT_POST")
            .strip()
            .upper()
        )
    except Exception:
        return "DIRECT_POST"


def find_due_or_upcoming_tiktok_rows(
    db_path: Path = DB_PATH,
    *,
    lead_minutes: int = 35,
    batch_horizon_hours: int = 12,
) -> List[Dict[str, Any]]:
    """
    Devuelve entregas activas (`PENDING` / `INBOX_DRAFT`) cuyo archivo MP4 exista en disco
    cuando al menos una entrega esté vencida o dentro de los próximos `lead_minutes` minutos.
    Incluye las entregas programadas hasta `batch_horizon_hours` para despachar todo el bloque de una sola vez.
    """
    if not Path(db_path).exists():
        return []
    now_utc = datetime.now(timezone.utc)
    trigger_cutoff = (now_utc + timedelta(minutes=lead_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    batch_cutoff = (now_utc + timedelta(hours=batch_horizon_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT id, account_key, scheduled_time_utc, scheduled_time_ast, status, video_path, caption
                FROM tiktok_scheduled_queue
                WHERE UPPER(COALESCE(status, 'PENDING')) IN ('PENDING', 'INBOX_DRAFT')
                  AND scheduled_time_utc <= ?
                ORDER BY scheduled_time_utc ASC, id ASC
                """,
                (batch_cutoff,),
            ).fetchall()
        ]

    valid_rows = [r for r in rows if r.get("video_path") and Path(str(r["video_path"])).exists()]
    if not valid_rows:
        return []

    has_urgent = any(str(r.get("scheduled_time_utc") or "") <= trigger_cutoff for r in valid_rows)
    return valid_rows if has_urgent else []


def _format_approval_prompt(rows: List[Dict[str, Any]], batch_id: str) -> str:
    lines = [
        f"🎬 *Short YT · Permiso para TikTok Studio* (`{batch_id}`)",
        f"Tengo *{len(rows)} entrega(s)* listas/pendientes para subir o programar en *Brave*:",
    ]
    for r in rows[:8]:
        ast_lbl = str(r.get("scheduled_time_ast") or "Ahora")
        acct = str(r.get("account_key") or "").lstrip("@")
        vname = Path(str(r.get("video_path") or "clip.mp4")).stem
        lines.append(f"• `{ast_lbl}` · *@{acct}* · _{vname[:36]}_")
    if len(rows) > 8:
        lines.append(f"• _...y {len(rows) - 8} entrega(s) más._")
    lines.extend(
        [
            "",
            "🖥️ ¿Puedo usar tu computadora ahora para publicarlas/programarlas en TikTok Studio?",
            "Responde *\"aprobado\"* (o *\"está bien\"* / *\"dale\"*) para arrancar, o *\"ocupado\"* / *\"luego\"* para esperar.",
        ]
    )
    return "\n".join(lines)


def _resolve_playwright_python() -> str:
    local_app = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    for py_dir in sorted(local_app.glob("Programs/Python/Python3*"), reverse=True):
        cand = py_dir / "python.exe"
        if cand.exists():
            return str(cand)
    return shutil.which("python") or sys.executable


def _run_browser_batch_and_notify(
    *,
    row_ids: List[int],
    db_path: Path,
    config_dir: Path,
    bridge_url: str,
) -> None:
    script_path = Path(__file__).resolve().parent / "tiktok_studio_browser.py"
    summary_text = ""
    try:
        proc = subprocess.run(
            [
                _resolve_playwright_python(),
                str(script_path),
                "--db-path",
                str(db_path),
                "--row-ids",
                ",".join(str(x) for x in row_ids),
            ],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
        )
        out_raw = (proc.stdout or "").strip()
        parsed: Dict[str, Any] = {}
        if out_raw:
            try:
                parsed = json.loads(out_raw[out_raw.find("{") :])
            except Exception:
                parsed = {}
        pub = int(parsed.get("published") or 0)
        blk = int(parsed.get("blocked") or 0)
        fld = int(parsed.get("failed") or 0)
        if blk > 0:
            summary_text = (
                f"⚠️ *Short YT · TikTok Studio pausado por seguridad*\n"
                f"✅ Publicados/Programados: *{pub}* | 🛑 Bloqueados (CAPTCHA/Login): *{blk}* | ❌ Fallos: *{fld}*\n"
                f"Revisa Brave en tu PC para completar cualquier verificación pendiente."
            )
        else:
            summary_text = (
                f"📲 *Short YT · TikTok Studio completado*\n"
                f"✅ Publicados/Programados: *{pub}* de *{len(row_ids)}* entrega(s)"
                + (f" (⚠️ {fld} con error — revisa Short YT)" if fld > 0 else " 🎉")
            )
    except Exception as exc:
        summary_text = f"❌ *Short YT · Error ejecutando TikTok Studio en Brave:* {exc}"

    cooldown = (datetime.now(timezone.utc) + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _APPROVAL_LOCK:
        st = _read_approval_state(config_dir)
        st["state"] = "idle"
        st["cooldown_until_utc"] = cooldown
        st["last_summary"] = summary_text
        _write_approval_state(config_dir, st)

    if summary_text:
        try:
            send_whatsapp_bridge_message(
                summary_text,
                etapa="TIKTOK_STUDIO_REPORT",
                bridge_url=bridge_url,
            )
        except Exception as exc:
            logger.warning("No se pudo enviar resumen WhatsApp: %s", exc)


def default_spawn_browser_batch(
    row_ids: List[int],
    *,
    db_path: Path = DB_PATH,
    config_dir: Path = CONFIG_DIR,
    bridge_url: str = WHATSAPP_BRIDGE_URL,
) -> None:
    t = threading.Thread(
        target=_run_browser_batch_and_notify,
        kwargs={
            "row_ids": list(row_ids),
            "db_path": Path(db_path),
            "config_dir": Path(config_dir),
            "bridge_url": bridge_url,
        },
        daemon=True,
        name="tiktok-wa-studio-runner",
    )
    t.start()


def apply_whatsapp_permission_decision(
    *,
    text: str,
    msg_id: str = "",
    db_path: Path = DB_PATH,
    config_dir: Path = CONFIG_DIR,
    bridge_url: str = WHATSAPP_BRIDGE_URL,
    launcher: Optional[Callable[[List[int]], None]] = None,
) -> Dict[str, Any]:
    """
    Evalúa un texto recibido por WhatsApp (`aprobado`, `ocupado`, etc.) cuando hay una
    solicitud de TikTok Studio pendiente (o filas pendientes listas) y actúa de inmediato.
    """
    intent = classify_whatsapp_permission_reply(text)
    if intent is None:
        return {"handled": False, "intent": None, "detail": "Mensaje sin intención de aprobación/rechazo."}

    with _APPROVAL_LOCK:
        st = _read_approval_state(config_dir)
        if msg_id and msg_id in (st.get("processed_msg_ids") or []):
            return {"handled": False, "intent": intent, "detail": "Mensaje ya procesado."}

        if msg_id:
            st.setdefault("processed_msg_ids", []).append(msg_id)

        if intent == "declined":
            cooldown = (datetime.now(timezone.utc) + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
            st["state"] = "paused"
            st["cooldown_until_utc"] = cooldown
            _write_approval_state(config_dir, st)
            try:
                send_whatsapp_bridge_message(
                    "⏸️ *Entendido, jefe.* No usaré la computadora todavía; te vuelvo a preguntar en 30 min o cuando me escribas *aprobado*.",
                    etapa="TIKTOK_STUDIO_PAUSED",
                    bridge_url=bridge_url,
                )
            except Exception:
                pass
            return {"handled": True, "intent": "declined", "state": "paused"}

        # intent == "approved"
        if st.get("state") == "running":
            _write_approval_state(config_dir, st)
            return {"handled": True, "intent": "approved", "state": "already_running"}

        target_ids = [int(x) for x in (st.get("row_ids") or []) if str(x).isdigit()]
        if not target_ids:
            # Si el usuario aprobó proactivamente, recoger pendientes/borradores existentes
            due_now = find_due_or_upcoming_tiktok_rows(db_path, lead_minutes=720)
            target_ids = [int(r["id"]) for r in due_now]

        if not target_ids:
            st["state"] = "idle"
            _write_approval_state(config_dir, st)
            return {"handled": True, "intent": "approved", "state": "no_pending_rows", "count": 0}

        st["state"] = "running"
        st["row_ids"] = target_ids
        _write_approval_state(config_dir, st)

    try:
        send_whatsapp_bridge_message(
            f"✅ *¡Aprobado recibido!* Abriendo Brave para subir/programar *{len(target_ids)} entrega(s)* en TikTok Studio...",
            etapa="TIKTOK_STUDIO_RUNNING",
            bridge_url=bridge_url,
        )
    except Exception:
        pass

    runner = launcher or (
        lambda rids: default_spawn_browser_batch(
            rids,
            db_path=db_path,
            config_dir=config_dir,
            bridge_url=bridge_url,
        )
    )
    runner(target_ids)
    return {
        "handled": True,
        "intent": "approved",
        "state": "running",
        "row_ids": target_ids,
        "count": len(target_ids),
    }


def tick_tiktok_whatsapp_workflow(
    *,
    db_path: Path = DB_PATH,
    config_dir: Path = CONFIG_DIR,
    bridge_url: str = WHATSAPP_BRIDGE_URL,
    lead_minutes: int = 35,
    launcher: Optional[Callable[[List[int]], None]] = None,
) -> Dict[str, Any]:
    """
    Paso periódico (cada 30s desde api_server) que solicita permiso por WhatsApp antes de
    vencer la programación TikTok o ejecuta inmediatamente tras recibir aprobación por WhatsApp.
    """
    pub_mode = get_tiktok_publish_mode(config_dir)
    if pub_mode != "TIKTOK_STUDIO":
        return {"mode": pub_mode, "action": "noop_not_studio_mode"}

    now_utc = datetime.now(timezone.utc)
    with _APPROVAL_LOCK:
        st = _read_approval_state(config_dir)
        cur_state = str(st.get("state") or "idle")
        sent_ts_ms = int(st.get("sent_ts_ms") or 0)
        sent_ids = set(str(x) for x in (st.get("sent_message_ids") or []))
        processed_ids = set(str(x) for x in (st.get("processed_msg_ids") or []))
        cooldown_iso = st.get("cooldown_until_utc")

    if cur_state == "running":
        return {"mode": pub_mode, "action": "running"}

    if cur_state == "awaiting_approval":
        # Si han pasado > 4 horas sin respuesta, expirar y permitir re-consultar si aún hay pendientes
        if sent_ts_ms > 0 and (int(time.time() * 1000) - sent_ts_ms) > 4 * 3600 * 1000:
            with _APPROVAL_LOCK:
                st = _read_approval_state(config_dir)
                st["state"] = "idle"
                _write_approval_state(config_dir, st)
        else:
            try:
                msgs = fetch_whatsapp_bridge_messages(sent_ts_ms, bridge_url=bridge_url)
            except Exception:
                msgs = []

            for m in msgs:
                mid = str(m.get("id") or "")
                mts = int(m.get("timestamp_ms") or 0)
                if mid and mid in processed_ids:
                    continue
                if mts and sent_ts_ms and mts < sent_ts_ms:
                    continue
                mtxt = str(m.get("texto") or "").strip()
                quoted_id = str(m.get("quoted_id") or "")
                quoted_txt = str(m.get("quoted_text") or "")
                intent = classify_whatsapp_permission_reply(mtxt)
                if not intent:
                    continue
                is_our_reply = (
                    (quoted_id and quoted_id in sent_ids)
                    or "tiktok" in quoted_txt.lower()
                    or "short yt" in quoted_txt.lower()
                    or "tiktok" in mtxt.lower()
                    or not quoted_id
                )
                if is_our_reply:
                    res = apply_whatsapp_permission_decision(
                        text=mtxt,
                        msg_id=mid,
                        db_path=db_path,
                        config_dir=config_dir,
                        bridge_url=bridge_url,
                        launcher=launcher,
                    )
                    return {"mode": pub_mode, "action": f"wa_reply_{res.get('intent')}", **res}
            return {"mode": pub_mode, "action": "awaiting_approval"}

    # idle o paused: verificar si sigue en ventana de espera (cooldown)
    if cooldown_iso:
        try:
            cd_dt = datetime.fromisoformat(str(cooldown_iso).replace("Z", "+00:00"))
            if now_utc < cd_dt:
                return {"mode": pub_mode, "action": "cooldown"}
        except Exception:
            pass

    due_rows = find_due_or_upcoming_tiktok_rows(db_path, lead_minutes=lead_minutes)
    if not due_rows:
        return {"mode": pub_mode, "action": "no_due_rows"}

    bridge_st = get_whatsapp_bridge_status(bridge_url)
    if not bridge_st.get("connected"):
        return {"mode": pub_mode, "action": "whatsapp_disconnected"}

    batch_id = uuid.uuid4().hex[:8]
    prompt_txt = _format_approval_prompt(due_rows, batch_id)
    now_ms = int(time.time() * 1000)
    try:
        send_res = send_whatsapp_bridge_message(
            prompt_txt,
            etapa=f"TIKTOK_STUDIO_APPROVAL:{batch_id}",
            proyecto=SHORTYT_WA_PROJECT_TAG,
            bridge_url=bridge_url,
        )
    except Exception as exc:
        logger.warning("Fallo enviando solicitud de permiso WhatsApp: %s", exc)
        return {"mode": pub_mode, "action": "send_failed", "error": str(exc)}

    sent_msg_ids = [str(x) for x in (send_res.get("message_ids") or []) if x]
    row_ids = [int(r["id"]) for r in due_rows]
    with _APPROVAL_LOCK:
        st = _read_approval_state(config_dir)
        st.update(
            {
                "state": "awaiting_approval",
                "batch_id": batch_id,
                "sent_ts_ms": now_ms,
                "sent_message_ids": sent_msg_ids,
                "row_ids": row_ids,
                "cooldown_until_utc": None,
            }
        )
        _write_approval_state(config_dir, st)

    return {
        "mode": pub_mode,
        "action": "asked_whatsapp",
        "batch_id": batch_id,
        "row_ids": row_ids,
    }


def get_whatsapp_approval_public_status(
    config_dir: Path = CONFIG_DIR,
    bridge_url: str = WHATSAPP_BRIDGE_URL,
) -> Dict[str, Any]:
    """Estado resumido para endpoints HTTP y panel UI."""
    st = _read_approval_state(config_dir)
    bridge = get_whatsapp_bridge_status(bridge_url)
    return {
        "publish_mode": get_tiktok_publish_mode(config_dir),
        "whatsapp_connected": bool(bridge.get("connected")),
        "whatsapp_status": bridge.get("status"),
        "approval_state": st.get("state", "idle"),
        "batch_id": st.get("batch_id"),
        "row_ids": list(st.get("row_ids") or []),
        "cooldown_until_utc": st.get("cooldown_until_utc"),
        "last_summary": st.get("last_summary"),
    }
