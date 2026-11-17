"""
Automatización en navegador real (Brave) para TikTok Studio Web.

Se usa ÚNICAMENTE cuando el usuario otorga permiso explícito o dispara
el despacho manual desde Short YT mientras la app de TikTok esté en Sandbox
sin Content Posting API pública aprobada.

Regla de seguridad obligatoria:
- Jamás intenta resolver, evadir ni hacer clic sobre CAPTCHAs, puzzles o
  verificaciones humanas; si aparece uno o falta sesión, se detiene de inmediato.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger("tiktok_studio_browser")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

BASE_DIR = Path(__file__).resolve().parents[3]
CONFIG_DIR = BASE_DIR / "config"
DB_PATH = CONFIG_DIR / "schedule_state.db"
SOCIAL_ACCOUNTS_PATH = CONFIG_DIR / "social_accounts.json"
CLONE_USER_DATA_DIR = CONFIG_DIR / "tiktok_studio_profiles" / "brave_clone"
DEBUG_SHOTS_DIR = BASE_DIR / "logs" / "tiktok_studio_debug"
AST_TZ = ZoneInfo("America/Santo_Domingo")

DEFAULT_BRAVE_EXE_CANDIDATES = (
    Path(r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"),
    Path(r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe"),
    Path(os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe")),
)
BRAVE_USER_DATA_DIR = Path(
    os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data")
)

FALLBACK_ACCOUNT_PROFILES: Dict[str, str] = {
    "creador.clips": "Default",
    "creador.fans": "Profile 1",
    "creador.videos": "Profile 2",
    "creador.short": "Profile 3",
    "creador_ometv": "Profile 4",
    "creador.gaming": "Profile 5",
}


def find_brave_executable() -> Path:
    for candidate in DEFAULT_BRAVE_EXE_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("No se encontró brave.exe instalado en el sistema.")


def is_process_running(image_name: str) -> bool:
    if os.name != "nt":
        return False
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/NH"],
            text=True,
            errors="ignore",
        )
        return image_name.lower() in out.lower()
    except Exception:
        return False


def resolve_brave_profile_map(
    social_accounts_path: Path = SOCIAL_ACCOUNTS_PATH,
) -> Dict[str, str]:
    """Devuelve {account_key_lower: brave_profile_dir} validado con Brave Local State si existe."""
    mapping: Dict[str, str] = dict(FALLBACK_ACCOUNT_PROFILES)
    if social_accounts_path.exists():
        try:
            raw = json.loads(social_accounts_path.read_text(encoding="utf-8"))
            for item in raw.get("tiktok_studio_accounts") or []:
                uname = str(item.get("username") or "").lstrip("@").strip().lower()
                bdir = str(item.get("brave_profile_dir") or "").strip()
                if uname and bdir:
                    mapping[uname] = bdir
        except Exception as exc:
            logger.warning("No se pudo leer social_accounts.json (%s); usando fallback.", exc)

    local_state = BRAVE_USER_DATA_DIR / "Local State"
    if local_state.exists():
        try:
            ls_data = json.loads(local_state.read_text(encoding="utf-8"))
            info_cache = (ls_data.get("profile") or {}).get("info_cache") or {}
            name_to_dir = {
                str(v.get("name") or "").strip().lower(): str(k)
                for k, v in info_cache.items()
                if str(v.get("name") or "").strip()
            }
            for uname, prof_dir in list(mapping.items()):
                if prof_dir not in info_cache:
                    # Resuelve por username o nombre conocido si movieron carpetas
                    for label_key, actual_dir in name_to_dir.items():
                        if uname.replace(".", " ") in label_key or uname.split(".")[-1] in label_key:
                            mapping[uname] = actual_dir
                            break
        except Exception:
            pass
    return mapping


def clean_tiktok_caption(raw_caption: str) -> str:
    """Normaliza la descripción evitando #Shorts duplicado y limitando longitud segura."""
    txt = " ".join(str(raw_caption or "").replace("\r", " ").replace("\n", " ").split())
    seen_tags: set[str] = set()
    tokens: List[str] = []
    for tok in txt.split(" "):
        low = tok.lower()
        if low.startswith("#"):
            if low in seen_tags:
                continue
            seen_tags.add(low)
        tokens.append(tok)
    out = " ".join(tokens).strip()
    return out[:2100] if len(out) > 2100 else out


def resolve_tiktok_schedule_action(
    scheduled_dt_ast: Optional[datetime],
    now_ast: Optional[datetime] = None,
) -> Tuple[str, Optional[datetime]]:
    """
    Decide si un video debe publicarse ahora o programarse en TikTok Studio Web.
    TikTok Studio exige al menos ~20 min en el futuro en múltiplos de 5 min.
    """
    current = now_ast or datetime.now(AST_TZ)
    if scheduled_dt_ast is None:
        return ("POST_NOW", None)
    target = (
        scheduled_dt_ast.replace(tzinfo=AST_TZ)
        if scheduled_dt_ast.tzinfo is None
        else scheduled_dt_ast.astimezone(AST_TZ)
    )
    if target <= current + timedelta(minutes=5):
        return ("POST_NOW", None)

    min_valid = current + timedelta(minutes=22)
    eff = target if target >= min_valid else min_valid
    # Redondeo al múltiplo de 5 minutos igual o superior
    rem = eff.minute % 5
    if rem != 0 or eff.second > 0:
        add_min = (5 - rem) if rem != 0 else 5
        eff = eff.replace(second=0, microsecond=0) + timedelta(minutes=add_min)
    else:
        eff = eff.replace(second=0, microsecond=0)
    return ("SCHEDULE", eff)


def sync_brave_profile_to_clone(
    profile_dir: str,
    src_user_data: Path = BRAVE_USER_DATA_DIR,
    clone_user_data: Path = CLONE_USER_DATA_DIR,
) -> Path:
    """
    Sincroniza Local State + estado de sesión del perfil de Brave hacia un user-data-dir dedicado
    para evitar restricciones de debugging pipe sobre el directorio por defecto en Chromium moderno.
    """
    clone_user_data.mkdir(parents=True, exist_ok=True)
    local_state_src = src_user_data / "Local State"
    if local_state_src.exists():
        shutil.copy2(local_state_src, clone_user_data / "Local State")

    src_prof = src_user_data / profile_dir
    dst_prof = clone_user_data / profile_dir
    dst_prof.mkdir(parents=True, exist_ok=True)

    for rel_file in ("Preferences", "Secure Preferences", "Web Data"):
        f_src = src_prof / rel_file
        if f_src.exists():
            try:
                shutil.copy2(f_src, dst_prof / rel_file)
            except OSError:
                pass

    for rel_dir in ("Network", "Local Storage", "Session Storage", "IndexedDB", "Extension State"):
        d_src = src_prof / rel_dir
        d_dst = dst_prof / rel_dir
        if d_src.exists():
            try:
                shutil.copytree(d_src, d_dst, dirs_exist_ok=True)
            except Exception as exc:
                logger.warning("Aviso copiando %s (%s): %s", rel_dir, profile_dir, exc)

    return clone_user_data


@contextmanager
def open_brave_tiktok_context(
    playwright: Any,
    profile_dir: str,
    *,
    headless: bool = False,
) -> Iterator[Tuple[Any, bool]]:
    """
    Abre un contexto persistente de Brave con la sesión del perfil indicado.
    Intenta usar primero el User Data real de Brave (si no hay otro brave.exe abierto)
    y cae automáticamente a un directorio clonado si Chromium rechaza el default User Data.
    """
    brave_exe = find_brave_executable()
    launch_args = [
        f"--profile-directory={profile_dir}",
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    used_clone = False
    ctx = None

    if not is_process_running("brave.exe"):
        try:
            ctx = playwright.chromium.launch_persistent_context(
                user_data_dir=str(BRAVE_USER_DATA_DIR),
                executable_path=str(brave_exe),
                headless=headless,
                args=launch_args,
                ignore_default_args=["--enable-automation"],
                viewport={"width": 1366, "height": 900},
                timeout=20000,
            )
        except Exception as direct_exc:
            logger.info(
                "Brave rechazó User Data directo para debugging (%s); usando perfil sincronizado.",
                direct_exc,
            )

    if ctx is None:
        used_clone = True
        clone_root = sync_brave_profile_to_clone(profile_dir)
        ctx = playwright.chromium.launch_persistent_context(
            user_data_dir=str(clone_root),
            executable_path=str(brave_exe),
            headless=headless,
            args=launch_args,
            ignore_default_args=["--enable-automation"],
            viewport={"width": 1366, "height": 900},
            timeout=25000,
        )

    try:
        yield ctx, used_clone
    finally:
        try:
            ctx.close()
        except Exception:
            pass


def detect_challenge_or_login(page: Any) -> Optional[str]:
    """
    Detecta de forma pasiva si TikTok exige login o muestra un CAPTCHA.
    Nunca hace clic ni intenta resolver desafíos humanos.
    """
    url_low = str(page.url or "").lower()
    if "/login" in url_low or "passport" in url_low:
        return f"Redirigió a login ({page.url})."

    try:
        challenge = page.evaluate(
            """() => {
                const sels = [
                    'iframe[src*="captcha"]',
                    '[id*="captcha"]',
                    '[class*="secsdk-captcha"]',
                    '[class*="captcha_verify"]',
                    '.TUXModal:has-text("Verify to continue")',
                    '.TUXModal:has-text("Verifica")',
                ];
                for (const s of sels) {
                    const el = document.querySelector(s);
                    if (el) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 40 && r.height > 40) {
                            return s;
                        }
                    }
                }
                const txt = (document.body?.innerText || '').toLowerCase();
                if (txt.includes('drag the slider') || txt.includes('arrastra el deslizador') || txt.includes('log in to tiktok')) {
                    return 'challenge_text';
                }
                return null;
            }"""
        )
        if challenge:
            return f"Desafío/CAPTCHA o login detectado ({challenge})."
    except Exception:
        pass
    return None


def _try_pick_schedule_datetime(page: Any, target_dt: datetime) -> Dict[str, Any]:
    """
    Activa 'Programar' / 'Schedule' en TikTok Studio y selecciona fecha y hora (múltiplos de 5 min)
    usando los selectores exactos TUX/TimePicker de TikTok Studio.
    """
    def _click_schedule_option() -> Dict[str, Any]:
        return page.evaluate(
            """() => {
                const radios = Array.from(document.querySelectorAll('input[type="radio"][value*="schedule" i]'));
                for (const rad of radios) {
                    rad.scrollIntoView({ block: 'center' });
                    if (rad.checked) {
                        return { clicked: true, alreadyChecked: true, text: 'radio_value_schedule' };
                    }
                    const lbl = rad.closest('label');
                    if (lbl) lbl.click();
                    else rad.click();
                    return { clicked: true, alreadyChecked: !!rad.checked, text: 'radio_value_schedule' };
                }
                const labels = Array.from(document.querySelectorAll('label, span, div[role="radio"], button'));
                for (const el of labels) {
                    const t = (el.textContent || '').trim();
                    if (/^(Programar|Schedule)$/i.test(t)) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0) {
                            el.scrollIntoView({ block: 'center' });
                            el.click();
                            return { clicked: true, text: t };
                        }
                    }
                }
                return { clicked: false };
            }"""
        )

    schedule_clicked = _click_schedule_option()
    if not schedule_clicked.get("clicked"):
        raise RuntimeError("No se encontró la opción 'Programar' / 'Schedule' en TikTok Studio.")

    page.wait_for_timeout(800)
    # Cuentas nuevas muestran un aviso único "Allow your video to be saved for scheduled posting?"
    dismissed = _dismiss_benign_studio_modals(page)
    if dismissed:
        page.wait_for_timeout(700)
        _click_schedule_option()
        page.wait_for_timeout(800)
        _dismiss_benign_studio_modals(page)

    hh_str = f"{target_dt.hour:02d}"
    mm_val = (target_dt.minute // 5) * 5
    mm_str = f"{mm_val:02d}"
    target_time_label = f"{hh_str}:{mm_str}"
    target_date_iso = target_dt.strftime("%Y-%m-%d")

    # Localizar y abrir el selector de hora (.Picker__trigger clásico o TUXTextInputCore-input nuevo)
    time_re = re.compile(r"^\s*\d{1,2}:\d{2}(\s*[AP]M)?\s*$", re.IGNORECASE)
    time_trigger = page.locator(".Picker__trigger").filter(has_text=time_re).first
    trigger_is_input = False
    if time_trigger.count() == 0:
        cand_inputs = page.locator("input.TUXTextInputCore-input, input[readonly]")
        for idx in range(cand_inputs.count()):
            cand = cand_inputs.nth(idx)
            try:
                if cand.is_visible() and time_re.match((cand.input_value() or "").strip()):
                    time_trigger = cand
                    trigger_is_input = True
                    break
            except Exception:
                continue
    if time_trigger.count() == 0:
        raise RuntimeError("No se encontró el botón selector de hora HH:MM tras marcar Schedule.")

    time_trigger.scroll_into_view_if_needed()
    time_trigger.click()
    page.wait_for_timeout(600)

    # Seleccionar columnas TimePicker__column (UI clásica) o .tiktok-timepicker-time-scroll-container (TUX)
    cols = page.locator(".TimePicker__column")
    tux_cols = page.locator(".tiktok-timepicker-time-scroll-container")
    hh_picked = False
    mm_picked = False
    if cols.count() >= 2:
        h_btn = cols.nth(0).locator("button.TimePicker__item, button").filter(
            has_text=re.compile(rf"^\s*{hh_str}\s*$")
        ).first
        if h_btn.count() > 0:
            h_btn.scroll_into_view_if_needed()
            h_btn.click()
            hh_picked = True
        m_btn = cols.nth(1).locator("button.TimePicker__item, button").filter(
            has_text=re.compile(rf"^\s*{mm_str}\s*$")
        ).first
        if m_btn.count() > 0:
            m_btn.scroll_into_view_if_needed()
            m_btn.click()
            mm_picked = True
    elif tux_cols.count() >= 2:
        h_opt = tux_cols.nth(0).locator(".tiktok-timepicker-option-item").filter(
            has_text=re.compile(rf"^\s*{hh_str}\s*$")
        ).first
        if h_opt.count() > 0:
            h_opt.scroll_into_view_if_needed()
            h_opt.click()
            hh_picked = True
        page.wait_for_timeout(200)
        m_opt = tux_cols.nth(1).locator(".tiktok-timepicker-option-item").filter(
            has_text=re.compile(rf"^\s*{mm_str}\s*$")
        ).first
        if m_opt.count() > 0:
            m_opt.scroll_into_view_if_needed()
            m_opt.click()
            mm_picked = True
    else:
        picked = page.evaluate(
            """({ hh, mm }) => {
                const containers = Array.from(document.querySelectorAll(
                    '.tiktok-timepicker-time-scroll-container, [class*="timepicker"] ul, [role="listbox"]'
                ));
                const clickMatch = (nodes, wanted) => {
                    for (const item of nodes) {
                        if ((item.textContent || '').trim() === wanted) {
                            item.scrollIntoView({ block: 'center' });
                            item.click();
                            return true;
                        }
                    }
                    return false;
                };
                if (containers.length >= 2) {
                    return {
                        hhPicked: clickMatch(containers[0].querySelectorAll('.tiktok-timepicker-option-item, button, span, li'), hh),
                        mmPicked: clickMatch(containers[1].querySelectorAll('.tiktok-timepicker-option-item, button, span, li'), mm),
                    };
                }
                return { hhPicked: false, mmPicked: false };
            }""",
            {"hh": hh_str, "mm": mm_str},
        )
        hh_picked = bool(picked.get("hhPicked"))
        mm_picked = bool(picked.get("mmPicked"))

    # Cerrar popover haciendo clic sobre texto neutro ("When to post" / "Settings") para no tocar enlaces del header
    try:
        neutral = page.locator("span, div").filter(has_text=re.compile(r"^(When to post|Cuándo publicar|Settings|Configuración)$", re.IGNORECASE)).first
        if neutral.count() > 0:
            neutral.click()
        else:
            page.mouse.click(600, 770)
    except Exception:
        page.keyboard.press("Escape")
    page.wait_for_timeout(400)

    # Verificar hora resultante visible en el trigger
    observed_time = ""
    try:
        observed_time = (time_trigger.input_value() if trigger_is_input else time_trigger.inner_text() or "").strip()
    except Exception:
        observed_time = ""

    # Ajustar fecha si la fecha programada no es hoy
    today_ast = datetime.now(AST_TZ).date()
    if target_dt.date() != today_ast:
        date_re = re.compile(r"[A-Za-z]+\s+\d{1,2},\s+\d{4}|\d{4}-\d{2}-\d{2}")
        date_trigger = page.locator(".Picker__trigger").filter(has_text=date_re).first
        if date_trigger.count() == 0:
            cand_inputs = page.locator("input.TUXTextInputCore-input, input[readonly]")
            for idx in range(cand_inputs.count()):
                cand = cand_inputs.nth(idx)
                try:
                    if cand.is_visible() and date_re.match((cand.input_value() or "").strip()):
                        date_trigger = cand
                        break
                except Exception:
                    continue
        if date_trigger.count() > 0:
            date_trigger.click()
            page.wait_for_timeout(400)
            day_str = str(target_dt.day)
            day_btn = page.locator('[class*="Calendar"], [class*="DatePicker"], [role="dialog"], .TUXPopover').locator("button, span, div").filter(
                has_text=re.compile(rf"^\s*{day_str}\s*$")
            ).first
            if day_btn.count() > 0:
                day_btn.click()
                page.wait_for_timeout(300)
                try:
                    page.locator("span, div").filter(has_text=re.compile(r"^(When to post|Cuándo publicar)$", re.IGNORECASE)).first.click()
                except Exception:
                    pass

    if not (hh_picked and mm_picked):
        raise RuntimeError(
            f"No se pudo fijar hora {target_time_label} en TikTok Studio (hh={hh_picked}, mm={mm_picked}, cols={cols.count()}, obs={observed_time})."
        )

    return {
        "target_date": target_date_iso,
        "target_time": target_time_label,
        "observed_time": observed_time,
    }


def _dismiss_benign_studio_modals(page: Any) -> Optional[str]:
    """Cierra avisos benignos de onboarding de TikTok Studio (check automático o tour react-joyride), jamás CAPTCHAs."""
    try:
        clicked = page.evaluate(
            """() => {
                // Jamás actuar si existe algún elemento o texto de CAPTCHA / verificación humana
                const bodyTxt = (document.body?.innerText || '').toLowerCase();
                if (bodyTxt.includes('verify to continue') || bodyTxt.includes('drag the slider') || bodyTxt.includes('arrastra el deslizador')) {
                    return null;
                }
                const portals = Array.from(document.querySelectorAll(
                    '#react-joyride-portal, .react-joyride__tooltip, [class*="joyride"], .TUXModal, [role="dialog"], [role="alertdialog"], [data-floating-ui-portal]'
                ));
                for (const p of portals) {
                    const txt = (p.innerText || '').toLowerCase();
                    if (!txt) continue;
                    if (txt.includes('captcha') || txt.includes('slider') || txt.includes('verify to continue') || txt.includes('human')) {
                        return null;
                    }
                    if (
                        txt.includes('automatic content checks') ||
                        txt.includes('copyright') ||
                        txt.includes('content check') ||
                        txt.includes('verificación automática') ||
                        txt.includes('new editing features') ||
                        txt.includes('nuevas funciones de edición') ||
                        txt.includes('scheduled posting') ||
                        txt.includes('saved on our servers before it is posted') ||
                        txt.includes('se guarde para publicarlo') ||
                        txt.includes('se guarde en nuestros servidores')
                    ) {
                        const btns = Array.from(p.querySelectorAll('button')).filter(b => !b.disabled);
                        const preferred = [
                            /^(Allow|Permitir)$/i,
                            /^(Turn on|Activar|Got it|Entendido|Accept|Aceptar|OK|Done|Listo)$/i,
                            /^(Next|Siguiente|Skip|Omitir|Close|Cerrar|Cancel|Cancelar)$/i,
                        ];
                        for (const rx of preferred) {
                            for (const b of btns) {
                                const bt = (b.innerText || '').trim();
                                if (rx.test(bt)) {
                                    b.click();
                                    return bt;
                                }
                            }
                        }
                    }
                }
                return null;
            }"""
        )
        if not clicked:
            # Fallback para tooltips Joyride (p. ej. 'Got it' / 'Next' / 'Done') cuando existe el overlay joyride sin CAPTCHA
            has_joyride_overlay = page.locator('#react-joyride-portal [data-test-id="overlay"]').count() > 0
            if has_joyride_overlay:
                page_txt = (page.locator("body").inner_text() or "").lower()
                if "captcha" not in page_txt and "verify to continue" not in page_txt:
                    tour_btn = page.locator("button").filter(
                        has_text=re.compile(r"^\s*(Got it|Entendido|Skip|Omitir|Done|Listo)\s*$", re.IGNORECASE)
                    ).first
                    if tour_btn.count() > 0 and tour_btn.is_visible():
                        tour_btn.click()
                        clicked = "joyride_overlay_btn"
        if clicked:
            page.wait_for_timeout(450)
        return clicked
    except Exception:
        return None


def upload_or_schedule_in_tiktok_studio(
    page: Any,
    video_path: Path,
    caption: str,
    scheduled_dt_ast: Optional[datetime] = None,
    *,
    debug_dir: Path = DEBUG_SHOTS_DIR,
    upload_timeout_sec: int = 210,
) -> Dict[str, Any]:
    """
    Sube y publica/programa un MP4 en TikTok Studio Web dentro de la sesión Brave abierta.
    """
    debug_dir.mkdir(parents=True, exist_ok=True)
    ts_tag = datetime.now().strftime("%H%M%S")
    safe_stem = re.sub(r"[^A-Za-z0-9_-]", "_", video_path.stem)[:32]

    page.goto("https://www.tiktok.com/tiktokstudio/upload?lang=es", wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(3500)

    blocked_reason = detect_challenge_or_login(page)
    if blocked_reason:
        shot = debug_dir / f"{ts_tag}_{safe_stem}_blocked.png"
        page.screenshot(path=str(shot))
        return {
            "ok": False,
            "status": "BLOCKED_CHALLENGE_OR_LOGIN",
            "error": blocked_reason,
            "screenshot": str(shot),
        }

    file_input = page.locator('input[type="file"]').first
    file_input.wait_for(state="attached", timeout=30000)
    file_input.set_input_files(str(video_path.resolve()))

    # Esperar que el editor de descripción (contenteditable) sea visible e interactuable y la subida complete
    caption_editor = page.locator('div[contenteditable="true"]').first
    caption_editor.wait_for(state="visible", timeout=60000)

    deadline = time.monotonic() + float(upload_timeout_sec)
    upload_ready = False
    while time.monotonic() < deadline:
        blocked = detect_challenge_or_login(page)
        if blocked:
            shot = debug_dir / f"{ts_tag}_{safe_stem}_blocked_mid.png"
            page.screenshot(path=str(shot))
            return {
                "ok": False,
                "status": "BLOCKED_CHALLENGE_OR_LOGIN",
                "error": blocked,
                "screenshot": str(shot),
            }

        state_info = page.evaluate(
            """() => {
                const txt = (document.body?.innerText || '');
                const btns = Array.from(document.querySelectorAll('button'));
                let postBtn = null;
                for (const b of btns) {
                    const t = (b.innerText || '').trim();
                    const e2e = b.getAttribute('data-e2e') || '';
                    if (e2e === 'post_video_button' || /^(Publicar|Programar|Post|Schedule)$/i.test(t)) {
                        postBtn = {
                            text: t,
                            disabled: !!b.disabled || b.getAttribute('aria-disabled') === 'true',
                            e2e,
                        };
                    }
                }
                const hasPreview = !!document.querySelector('video[src], video source, [class*="phone-container"] video');
                // Ignorar "100%" (ya subido); solo considerar en progreso 0%..99% en la zona de carga
                const pctMatches = txt.match(/\\b(\\d{1,3})%/g) || [];
                const uploadingPct = pctMatches.some((m) => {
                    const n = parseInt(m.replace('%', ''), 10);
                    return n >= 0 && n < 100;
                });
                return { postBtn, hasPreview, uploadingPct };
            }"""
        )
        pb = state_info.get("postBtn")
        if pb and not pb.get("disabled") and not state_info.get("uploadingPct"):
            upload_ready = True
            break
        _dismiss_benign_studio_modals(page)
        page.wait_for_timeout(1500)

    if not upload_ready:
        shot = debug_dir / f"{ts_tag}_{safe_stem}_upload_timeout.png"
        page.screenshot(path=str(shot))
        return {
            "ok": False,
            "status": "UPLOAD_TIMEOUT",
            "error": "El archivo tardó demasiado en terminar de cargarse en TikTok Studio.",
            "screenshot": str(shot),
        }

    for _ in range(5):
        if not _dismiss_benign_studio_modals(page):
            break

    # Escribir descripción limpia
    clean_cap = clean_tiktok_caption(caption)
    caption_editor.scroll_into_view_if_needed()
    caption_editor.click()
    page.wait_for_timeout(200)
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.wait_for_timeout(150)
    page.keyboard.insert_text(clean_cap)
    page.wait_for_timeout(400)
    page.keyboard.press("Escape")
    page.wait_for_timeout(250)

    action, eff_dt = resolve_tiktok_schedule_action(scheduled_dt_ast)
    sched_meta: Dict[str, Any] = {}
    if action == "SCHEDULE" and eff_dt is not None:
        sched_meta = _try_pick_schedule_datetime(page, eff_dt)
        page.wait_for_timeout(400)

    pre_shot = debug_dir / f"{ts_tag}_{safe_stem}_before_submit.png"
    page.screenshot(path=str(pre_shot))

    # Pulsar el botón principal Publicar / Programar
    submit_btn = page.locator('button[data-e2e="post_video_button"]').first
    if submit_btn.count() == 0:
        submit_btn = page.locator("button").filter(
            has_text=re.compile(r"^(Publicar|Programar|Post|Schedule)$", re.IGNORECASE)
        ).last

    submit_btn.scroll_into_view_if_needed()
    is_disabled = submit_btn.is_disabled() or submit_btn.get_attribute("aria-disabled") == "true"
    if is_disabled:
        shot = debug_dir / f"{ts_tag}_{safe_stem}_submit_disabled.png"
        page.screenshot(path=str(shot))
        return {
            "ok": False,
            "status": "SUBMIT_DISABLED",
            "error": "El botón Publicar/Programar quedó deshabilitado tras configurar la publicación.",
            "screenshot": str(shot),
        }

    submit_btn.click()
    page.wait_for_timeout(2000)

    # Confirmar modales no-CAPTCHA ("Continuar", "Publicar ahora" o "Programar") si TikTok los muestra
    blocked_post = detect_challenge_or_login(page)
    if blocked_post:
        shot = debug_dir / f"{ts_tag}_{safe_stem}_post_blocked.png"
        page.screenshot(path=str(shot))
        return {
            "ok": False,
            "status": "BLOCKED_CHALLENGE_OR_LOGIN",
            "error": blocked_post,
            "screenshot": str(shot),
        }

    confirmed = False
    wait_end = time.monotonic() + 35.0
    while time.monotonic() < wait_end:
        blocked_loop = detect_challenge_or_login(page)
        if blocked_loop:
            shot = debug_dir / f"{ts_tag}_{safe_stem}_loop_blocked.png"
            page.screenshot(path=str(shot))
            return {
                "ok": False,
                "status": "BLOCKED_CHALLENGE_OR_LOGIN",
                "error": blocked_loop,
                "screenshot": str(shot),
            }

        check = page.evaluate(
            """() => {
                const url = window.location.href.toLowerCase();
                if (url.includes('/tiktokstudio/content') || url.includes('/creator-center/content')) {
                    return { done: true, reason: 'redirected_content' };
                }
                const txt = (document.body?.innerText || '').toLowerCase();
                if (
                    txt.includes('your video is being uploaded') ||
                    txt.includes('se ha programado') ||
                    txt.includes('has been scheduled') ||
                    txt.includes('published') ||
                    txt.includes('tu video se está subiendo') ||
                    txt.includes('se publicó') ||
                    txt.includes('gestionar tus publicaciones') ||
                    txt.includes('manage your posts')
                ) {
                    return { done: true, reason: 'success_banner' };
                }
                // Buscar botón de confirmación secundaria dentro de un modal benigno ("Publicar ahora" / "Post now")
                const modalBtns = Array.from(document.querySelectorAll('.TUXModal button, [role="dialog"] button'));
                for (const b of modalBtns) {
                    const bt = (b.innerText || '').trim();
                    if (/^(Publicar ahora|Post now|Confirm|Confirmar|Continuar|Continue to post)$/i.test(bt) && !b.disabled) {
                        b.click();
                        return { done: false, clickedConfirm: bt };
                    }
                }
                return { done: false };
            }"""
        )
        if check.get("done"):
            confirmed = True
            break
        page.wait_for_timeout(1200)

    done_shot = debug_dir / f"{ts_tag}_{safe_stem}_after_submit.png"
    page.screenshot(path=str(done_shot))

    if not confirmed:
        return {
            "ok": False,
            "status": "CONFIRM_TIMEOUT",
            "error": "No se observó confirmación explícita de publicación/programación en TikTok Studio.",
            "screenshot": str(done_shot),
        }

    return {
        "ok": True,
        "status": "PUBLISHED",
        "mode": "SCHEDULED_STUDIO" if action == "SCHEDULE" else "POSTED_NOW",
        "effective_ast": eff_dt.strftime("%Y-%m-%d %I:%M %p AST") if eff_dt else "INMEDIATO",
        "schedule_meta": sched_meta,
        "screenshot": str(done_shot),
    }


def process_queue_via_browser(
    *,
    db_path: Path = DB_PATH,
    row_ids: Optional[List[int]] = None,
    statuses: Tuple[str, ...] = ("PENDING", "INBOX_DRAFT", "FAILED"),
    headless: bool = False,
) -> Dict[str, Any]:
    """
    Procesa filas de tiktok_scheduled_queue usando Brave y marca como PUBLISHED únicamente
    aquellas confirmadas en TikTok Studio Web.
    """
    from playwright.sync_api import sync_playwright

    if not db_path.exists():
        return {"processed": 0, "published": 0, "blocked": 0, "failed": 0, "items": []}

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if row_ids:
            placeholders = ",".join("?" for _ in row_ids)
            rows = [
                dict(r)
                for r in conn.execute(
                    f"SELECT * FROM tiktok_scheduled_queue WHERE id IN ({placeholders}) ORDER BY scheduled_time_utc ASC, id ASC",
                    tuple(row_ids),
                ).fetchall()
            ]
        else:
            st_ph = ",".join("?" for _ in statuses)
            rows = [
                dict(r)
                for r in conn.execute(
                    f"SELECT * FROM tiktok_scheduled_queue WHERE UPPER(COALESCE(status, 'PENDING')) IN ({st_ph}) ORDER BY scheduled_time_utc ASC, id ASC",
                    tuple(s.upper() for s in statuses),
                ).fetchall()
            ]

    profile_map = resolve_brave_profile_map()
    by_profile: Dict[str, List[Dict[str, Any]]] = {}
    missing_rows: List[Dict[str, Any]] = []
    for r in rows:
        acct = str(r.get("account_key") or "").lstrip("@").strip().lower()
        pdir = profile_map.get(acct)
        if not pdir:
            missing_rows.append({**r, "reason": f"No hay perfil Brave mapeado para @{acct}"})
            continue
        by_profile.setdefault(pdir, []).append(r)

    results: List[Dict[str, Any]] = []
    published_cnt = 0
    blocked_cnt = 0
    failed_cnt = len(missing_rows)
    for mr in missing_rows:
        results.append(
            {
                "id": mr["id"],
                "account_key": mr["account_key"],
                "ok": False,
                "status": "FAILED",
                "error": mr["reason"],
            }
        )

    with sync_playwright() as p:
        for prof_dir, items in by_profile.items():
            with open_brave_tiktok_context(p, prof_dir, headless=headless) as (ctx, used_clone):
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                for row in items:
                    row_id = int(row["id"])
                    acct = str(row["account_key"])
                    vpath = Path(str(row["video_path"]))
                    if not vpath.exists():
                        err = f"Archivo no encontrado: {vpath}"
                        with sqlite3.connect(str(db_path)) as conn:
                            conn.execute(
                                "UPDATE tiktok_scheduled_queue SET status='FAILED', error=? WHERE id=?",
                                (err, row_id),
                            )
                            conn.commit()
                        failed_cnt += 1
                        results.append({"id": row_id, "account_key": acct, "ok": False, "status": "FAILED", "error": err})
                        continue

                    utc_str = str(row.get("scheduled_time_utc") or "").strip()
                    sched_dt_ast: Optional[datetime] = None
                    if utc_str:
                        try:
                            iso_u = f"{utc_str[:-1]}+00:00" if utc_str.endswith("Z") else utc_str
                            sched_dt_ast = datetime.fromisoformat(iso_u).astimezone(AST_TZ)
                        except Exception:
                            sched_dt_ast = None

                    try:
                        res = upload_or_schedule_in_tiktok_studio(
                            page,
                            vpath,
                            str(row.get("caption") or vpath.stem),
                            sched_dt_ast,
                        )
                    except Exception as exc:
                        res = {
                            "ok": False,
                            "status": "BROWSER_ERROR",
                            "error": str(exc),
                        }

                    pub_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    if res.get("ok"):
                        mode_tag = "tiktok_studio_scheduled" if res.get("mode") == "SCHEDULED_STUDIO" else "tiktok_studio_post"
                        eff_ast = str(res.get("effective_ast") or row.get("scheduled_time_ast") or "")
                        with sqlite3.connect(str(db_path)) as conn:
                            conn.execute(
                                """
                                UPDATE tiktok_scheduled_queue
                                SET status = 'PUBLISHED',
                                    publish_id = ?,
                                    scheduled_time_ast = ?,
                                    error = NULL,
                                    published_at_utc = ?
                                WHERE id = ?
                                """,
                                (mode_tag, eff_ast, pub_now, row_id),
                            )
                            conn.commit()
                        published_cnt += 1
                    elif res.get("status") == "BLOCKED_CHALLENGE_OR_LOGIN":
                        blocked_cnt += 1
                        with sqlite3.connect(str(db_path)) as conn:
                            conn.execute(
                                "UPDATE tiktok_scheduled_queue SET status = 'FAILED', error = ? WHERE id = ?",
                                (str(res.get("error") or "CAPTCHA o login requerido en Brave."), row_id),
                            )
                            conn.commit()
                        results.append({"id": row_id, "account_key": acct, "profile": prof_dir, "used_clone": used_clone, **res})
                        # No insistir sobre un perfil que mostró CAPTCHA o login
                        break
                    else:
                        failed_cnt += 1
                        with sqlite3.connect(str(db_path)) as conn:
                            conn.execute(
                                "UPDATE tiktok_scheduled_queue SET status = 'FAILED', error = ? WHERE id = ?",
                                (str(res.get("error") or res.get("status") or "Error TikTok Studio"), row_id),
                            )
                            conn.commit()

                    results.append({"id": row_id, "account_key": acct, "profile": prof_dir, "used_clone": used_clone, **res})

    return {
        "processed": len(results),
        "published": published_cnt,
        "blocked": blocked_cnt,
        "failed": failed_cnt,
        "items": results,
    }


def _parse_cli() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Sube/programa Shorts en TikTok Studio Web vía Brave.")
    ap.add_argument("--db-path", type=str, default=str(DB_PATH))
    ap.add_argument("--row-ids", type=str, default="", help="Lista separada por comas, ej. 116,120,121")
    ap.add_argument("--headless", action="store_true")
    return ap.parse_args()


if __name__ == "__main__":
    args = _parse_cli()
    ids = [int(x.strip()) for x in args.row_ids.split(",") if x.strip().isdigit()]
    summary = process_queue_via_browser(
        db_path=Path(args.db_path),
        row_ids=ids or None,
        headless=bool(args.headless),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
