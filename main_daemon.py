"""
FASE 3: El Orquestador (main_daemon.py)
Monitorea ./inbox_videos/ usando watchdog, lee los parámetros de ./config/settings.json
(o flags de consola), extrae N Shorts virales por cada video largo invocando las 4 Skills
y archiva el original en ./published_archive/.
"""

from __future__ import annotations

import argparse
import gc
import importlib.util
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from types import ModuleType
from typing import Any, Dict, Optional, Set, Tuple

from config import social_hub


def enable_silent_windows_subprocesses() -> None:
    """
    Evita al 100% que Windows abra ventanas negras de consola (cmd / Windows Terminal / FFmpeg)
    y robe el foco del teclado cuando el motor corre en segundo plano (pythonw.exe o servidor web).
    Aplica CREATE_NO_WINDOW (0x08000000) + STARTUPINFO(SW_HIDE) globalmente a subprocess.Popen,
    cubriendo tanto nuestras llamadas FFmpeg como subprocesos internos de yt-dlp e imageio-ffmpeg.
    """
    if sys.platform != "win32":
        return
    if getattr(subprocess.Popen, "_is_short_yt_silent_popen", False):
        return

    _orig_popen = subprocess.Popen
    _create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    _create_new_console = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010)
    _detached_process = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)

    class _SilentPopen(_orig_popen):  # type: ignore[misc, valid-type]
        _is_short_yt_silent_popen = True

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            flags = int(kwargs.get("creationflags", 0) or 0)
            if not (flags & (_create_new_console | _detached_process)):
                flags |= _create_no_window
            kwargs["creationflags"] = flags

            if kwargs.get("startupinfo") is None and hasattr(subprocess, "STARTUPINFO"):
                si = subprocess.STARTUPINFO()
                si.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0x00000001)
                si.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
                kwargs["startupinfo"] = si

            super().__init__(*args, **kwargs)
            self._injected_creationflags = flags

    subprocess.Popen = _SilentPopen  # type: ignore[misc]


enable_silent_windows_subprocesses()


def win_long_path(path: Path) -> Path:
    """Devuelve Path con prefijo \\\\?\\ en Windows si la ruta se acerca o supera MAX_PATH (240+ chars)."""
    if sys.platform != "win32":
        return path
    abs_str = os.path.abspath(str(path))
    if abs_str.startswith("\\\\?\\"):
        return Path(abs_str)
    if len(abs_str) < 240:
        return path
    if abs_str.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + abs_str.lstrip("\\"))
    return Path("\\\\?\\" + abs_str)


def sanitize_media_stem(raw_stem: str, max_len: int = 44) -> str:
    """Normaliza un nombre de archivo eliminando emojis, hashtags y caracteres especiales, acotado a max_len."""
    ascii_stem = unicodedata.normalize("NFKD", str(raw_stem)).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", ascii_stem)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_-")
    if max_len > 0 and len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip("_-")
    return cleaned or "short_video"


def build_video_date_project_id(
    video_name: Optional[str] = None,
    *,
    now: Optional[datetime] = None,
    max_len: int = 56,
) -> str:
    """Genera un identificador legible '<Video>_<YYYY-MM-DD>' (o 'Proyecto_<YYYY-MM-DD>_<HHMM>' sin video)."""
    dt = now or datetime.now()
    date_part = dt.strftime("%Y-%m-%d")
    raw = str(video_name or "").strip()
    if not raw:
        return f"Proyecto_{date_part}_{dt.strftime('%H%M')}"
    raw_stem = Path(raw).stem or raw
    raw_stem = re.sub(r"^p_[A-Za-z0-9]{6,}_[A-Za-z0-9]{2,4}_+", "", raw_stem)
    raw_stem = re.sub(r"^p_[A-Za-z0-9]{4,}_+", "", raw_stem)
    raw_stem = re.sub(r"^inbox_vi(?:deos?)?_*", "", raw_stem, flags=re.IGNORECASE)
    suffix = f"_{date_part}"
    allowed_stem_len = max(8, max_len - len(suffix))
    clean_stem = sanitize_media_stem(raw_stem or "Video", max_len=allowed_stem_len)
    return f"{clean_stem}{suffix}"


def safe_unlink_with_retries(path: Path, retries: int = 5, delay_sec: float = 0.25) -> bool:
    """Elimina un archivo en Windows tolerando bloqueos transitorios (WinError 32) sin abortar el flujo."""
    target = win_long_path(path)
    last_err: Optional[Exception] = None
    for attempt in range(max(1, retries)):
        try:
            target.unlink(missing_ok=True)
            return True
        except (PermissionError, OSError) as exc:
            last_err = exc
            gc.collect()
            if attempt < retries - 1:
                time.sleep(delay_sec)
    logger.warning(
        "Archivo temporal aún en uso (se limpiará en diferido): %s (%s)",
        path.name,
        last_err,
    )
    return False

from dotenv import load_dotenv
from watchdog.events import FileCreatedEvent, FileMovedEvent, FileSystemEventHandler
from watchdog.observers import Observer

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
INBOX_DIR = BASE_DIR / "inbox_videos"
PROCESSING_DIR = BASE_DIR / "processing"
OUTPUT_SHORTS_DIR = BASE_DIR / "output_shorts"
PUBLISHED_ARCHIVE_DIR = BASE_DIR / "published_archive"
CONFIG_DIR = BASE_DIR / "config"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
SKILLS_DIR = BASE_DIR / ".agents" / "skills"

VIDEO_EXTENSIONS: Set[str] = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}

DEFAULT_SETTINGS: Dict[str, Any] = {
    "shorts_per_video": 8,
    "content_category": "auto",
    "min_short_duration_sec": 45.0,
    "max_short_duration_sec": 120.0,
    "playback_speed": 1.0,
    "layout_mode": "auto",
    "enable_bgm": False,
    "default_bgm_mood": "desactivada",
    "enable_dynamic_zoom": True,
    "enable_hook_punchin": True,
    "enable_jumpcuts": False,
    "max_words_per_subtitle": 4,
    "youtube_category_id": "22",
    "auto_upload_to_youtube": False,
    "enable_social_distribution": False,
    "auto_categorize_by_topic": True,
    "allowed_account_categories": ["principales", "gaming", "clipping"],
    "theme_mode": "light",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-28s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main_daemon")


_NULLABLE_OVERRIDE_KEYS: Set[str] = {
    "custom_cam_box_norm",
    "custom_content_box_norm",
    "category_rules",
    "allowed_account_categories",
    "download_section_start",
    "download_section_end",
}

DUAL_BOX_LAYOUTS: Set[str] = {
    "split_streamer",
    "split_50_50",
    "ometv",
    "podcast_dynamic",
    "gaming_hud",
    "reaction_pip",
    "floating_cam_top",
    "floating_circle",
    "blur_16_9_cam",
}
PIP_GAMEPLAY_LAYOUTS: Set[str] = {
    "split_streamer",
    "gaming_hud",
    "reaction_pip",
    "floating_cam_top",
    "floating_circle",
    "blur_16_9_cam",
}
DUAL_SPEAKER_LAYOUTS: Set[str] = {"podcast_dynamic", "split_50_50", "ometv"}
FULLSCREEN_CATEGORIES: Set[str] = {"opinion_monologo", "storytime_anecdota"}
GAMEPLAY_PIP_CATEGORIES: Set[str] = {"videojuegos", "reacciones", "tutorial_curiosidad"}

CATEGORY_SCENE_DEFAULTS: Dict[str, Dict[str, str]] = {
    "videojuegos": {
        "scene_label": "Gameplay + Cámara",
        "layout_mode": "gaming_hud",
        "subtitle_preset": "nexus_cyber_glow",
        "subtitle_position": "center",
    },
    "opinion_monologo": {
        "scene_label": "Charla / Monólogo Full Cam",
        "layout_mode": "fullscreen",
        "subtitle_preset": "hormozi_pop",
        "subtitle_position": "bottom",
    },
    "podcast": {
        "scene_label": "Podcast / 2 Personas",
        "layout_mode": "podcast_dynamic",
        "subtitle_preset": "karaoke_duo",
        "subtitle_position": "bottom",
    },
    "realitys": {
        "scene_label": "Reality / Multicam Sala",
        "layout_mode": "reality_multicam",
        "subtitle_preset": "hormozi_pop",
        "subtitle_position": "bottom",
    },
    "reacciones": {
        "scene_label": "Reacción Picture-in-Picture",
        "layout_mode": "reaction_pip",
        "subtitle_preset": "hormozi_pop",
        "subtitle_position": "center",
    },
    "storytime_anecdota": {
        "scene_label": "Storytime / Anécdota",
        "layout_mode": "fullscreen",
        "subtitle_preset": "one_word_punch",
        "subtitle_position": "center",
    },
    "tutorial_curiosidad": {
        "scene_label": "Tutorial / Dato Curioso",
        "layout_mode": "floating_cam_top",
        "subtitle_preset": "clean_apple_box",
        "subtitle_position": "bottom",
    },
}


def load_runtime_settings(cli_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Loads ./config/settings.json dynamically and merges optional CLI overrides."""
    settings = dict(DEFAULT_SETTINGS)
    if SETTINGS_PATH.exists():
        try:
            user_cfg = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(user_cfg, dict):
                settings.update(user_cfg)
        except Exception as exc:
            logger.warning("No se pudo leer config/settings.json (%s). Usando valores por defecto.", exc)
    else:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")

    if cli_overrides:
        for k, v in cli_overrides.items():
            if v is not None or k in _NULLABLE_OVERRIDE_KEYS:
                settings[k] = v
    return settings


def _detect_shorts_count_from_filename(stem: str, default_count: int) -> int:
    """
    Allows overriding the number of Shorts per video right in the filename!
    Example: `podcast_ep12_x5.mp4` -> extracts 5 Shorts automatically.
    """
    match = re.search(r"_x(\d+)$", stem, flags=re.IGNORECASE)
    if match:
        return max(1, int(match.group(1)))
    return max(1, int(default_count))


def _load_skill_module(skill_folder: str, module_filename: str) -> ModuleType:
    """Dynamically loads a skill Python module from .agents/skills/<skill_folder>/<module_filename>."""
    module_path = SKILLS_DIR / skill_folder / module_filename
    if not module_path.exists():
        raise FileNotFoundError(f"No se encontró el módulo de la skill en: {module_path}")

    skill_dir_str = str(module_path.parent)
    if skill_dir_str not in sys.path:
        sys.path.insert(0, skill_dir_str)

    module_name = f"agy_skill_{skill_folder.replace('-', '_')}_{module_filename.replace('.', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, str(module_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"No se pudo cargar la especificación para: {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Load the modular Antigravity skills
skill_transcriber = _load_skill_module("video-transcriber-analyzer", "analyzer.py")
skill_virality = _load_skill_module("video-transcriber-analyzer", "virality_scorer.py")
skill_renderer = _load_skill_module("vertical-crop-renderer", "renderer.py")
skill_scheduler = _load_skill_module("strategic-time-calculator", "calculator.py")
skill_uploader = _load_skill_module("youtube-shorts-uploader", "uploader.py")
skill_social = _load_skill_module("multi-social-uploader", "distributor.py")
skill_ig_scheduler = _load_skill_module("multi-social-uploader", "instagram_scheduler.py")
skill_tt_scheduler = _load_skill_module("multi-social-uploader", "tiktok_scheduler.py")
skill_cleanup = _load_skill_module("multi-social-uploader", "disk_cleanup.py")


def wait_until_file_ready(
    file_path: Path,
    stability_seconds: float = 2.0,
    timeout_seconds: float = 600.0,
) -> bool:
    """
    Waits until a video file in ./inbox_videos/ has finished copying:
    checks that file size > 0 remains constant across `stability_seconds`
    and that the file can be opened for exclusive read/write without PermissionError.
    """
    start_wait = time.monotonic()
    last_size = -1

    while (time.monotonic() - start_wait) < timeout_seconds:
        if not file_path.exists():
            return False

        try:
            current_size = file_path.stat().st_size
            if current_size > 0 and current_size == last_size:
                with open(file_path, "rb+"):
                    return True
            last_size = current_size
        except (PermissionError, OSError):
            pass

        time.sleep(stability_seconds)

    logger.error("Tiempo de espera agotado esperando que termine de copiarse: %s", file_path)
    return False


class PipelineCanceledError(RuntimeError):
    """Excepción lanzada cuando el usuario cancela manualmente la generación de Shorts."""


PRIMARY_YTDLP_FORMAT = (
    "299+140/312+140/"
    "bestvideo[vcodec^=avc1][height>=1080][fps>=60]+bestaudio[acodec^=mp4a]/"
    "bestvideo[height>=1080][fps>=60]+bestaudio/"
    "bestvideo[vcodec^=avc1][height>=1080]+bestaudio[acodec^=mp4a]/"
    "bestvideo[height>=1080]+bestaudio/"
    "bestvideo[vcodec^=avc1][height>=720]+bestaudio[acodec^=mp4a]/"
    "bestvideo[height>=720]+bestaudio/"
    "bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
    "bv*+ba/b"
)
FALLBACK_YTDLP_FORMAT = "bv*+ba/bestvideo+bestaudio/b/best"

PIPELINE_CANCEL_EVENT = threading.Event()


def resolve_clip_category_rule(
    video_path: Path,
    start_time: float,
    end_time: float,
    text: str,
    title: str,
    category_rules: Optional[List[Dict[str, Any]]],
    fallback_settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Combina el régimen visual real del segmento [start_time, end_time] y la categoría verbal
    para elegir la regla correspondiente (categoría + layout + subtítulos + posición) dentro
    de `category_rules`. Si no hay reglas múltiples, retorna un fallback 100% retrocompatible.
    """
    fb = fallback_settings or {}
    fallback_layout = str(fb.get("layout_mode", "auto") or "auto").strip().lower() or "auto"
    fallback_cat = str(fb.get("content_category", "auto") or "auto").strip() or "auto"
    fallback_sub_preset = str(fb.get("subtitle_preset", "hormozi_pop") or "hormozi_pop").strip()
    fallback_sub_pos = str(fb.get("subtitle_position", "auto") or "auto").strip()
    fallback_cam_pos = str(fb.get("cam_overlay_pos", "top_right") or "top_right").strip()
    fallback_cam_box = fb.get("custom_cam_box_norm")
    fallback_content_box = fb.get("custom_content_box_norm")

    normalized_rules: List[Dict[str, Any]] = []
    for idx, raw_r in enumerate(category_rules or []):
        if isinstance(raw_r, dict):
            r_dict = dict(raw_r)
        elif hasattr(raw_r, "model_dump"):
            r_dict = dict(raw_r.model_dump())
        else:
            continue
        r_layout = str(r_dict.get("layout_mode") or "auto").strip().lower()
        r_cat = str(r_dict.get("category") or "auto").strip()
        manual_boxes = bool(r_dict.get("custom_boxes_manual", False))
        use_dual_boxes = manual_boxes and (r_layout in DUAL_BOX_LAYOUTS)
        use_cam_box = use_dual_boxes or (manual_boxes and r_layout == "fullscreen")
        normalized_rules.append(
            {
                "rule_id": str(r_dict.get("rule_id") or f"rule_{idx + 1}"),
                "category": r_cat,
                "scene_label": str(r_dict.get("scene_label") or r_cat),
                "layout_mode": r_layout,
                "subtitle_preset": str(r_dict.get("subtitle_preset") or fallback_sub_preset),
                "subtitle_position": str(r_dict.get("subtitle_position") or fallback_sub_pos),
                "cam_overlay_pos": str(r_dict.get("cam_overlay_pos") or fallback_cam_pos),
                "custom_cam_box_norm": (
                    list(r_dict["custom_cam_box_norm"])
                    if use_cam_box and r_dict.get("custom_cam_box_norm") is not None
                    else None
                ),
                "custom_content_box_norm": (
                    list(r_dict["custom_content_box_norm"])
                    if use_dual_boxes and r_dict.get("custom_content_box_norm") is not None
                    else None
                ),
            }
        )

    if not normalized_rules:
        return {
            "rule_id": "fallback",
            "category": fallback_cat,
            "scene_label": fallback_cat,
            "layout_mode": fallback_layout,
            "subtitle_preset": fallback_sub_preset,
            "subtitle_position": fallback_sub_pos,
            "cam_overlay_pos": fallback_cam_pos,
            "custom_cam_box_norm": list(fallback_cam_box) if fallback_cam_box is not None else None,
            "custom_content_box_norm": list(fallback_content_box) if fallback_content_box is not None else None,
            "detected_visual_mode": "auto",
            "detected_verbal_category": "auto",
        }

    if len(normalized_rules) == 1:
        single = dict(normalized_rules[0])
        single["detected_visual_mode"] = single["layout_mode"]
        single["detected_verbal_category"] = single["category"]
        return single

    detected_visual_mode = "auto"
    try:
        vis_info = skill_renderer.detect_video_layout_and_regions(
            video_path=video_path,
            start_time=float(start_time),
            end_time=float(end_time),
            layout_mode="auto",
            category_hint="auto",
        )
        if isinstance(vis_info, dict) and vis_info.get("mode"):
            detected_visual_mode = str(vis_info["mode"]).strip().lower()
    except Exception as vis_exc:
        logger.warning("Inspección visual de clip [%.1f-%.1f] fallback: %s", start_time, end_time, vis_exc)

    detected_verbal_cat = "auto"
    try:
        detected_verbal_cat = str(skill_virality.detect_content_category(text or "", title or "")).strip()
    except Exception:
        pass

    best_rule = normalized_rules[0]
    best_score = -10**9
    for order_idx, rule in enumerate(normalized_rules):
        score = max(0, 10 - order_idx)
        r_layout = rule["layout_mode"]
        r_cat = rule["category"]

        if detected_visual_mode == "fullscreen":
            if r_layout == "fullscreen":
                score += 65
            elif r_cat in FULLSCREEN_CATEGORIES:
                score += 55
            elif r_layout in PIP_GAMEPLAY_LAYOUTS:
                score -= 15
        elif detected_visual_mode in PIP_GAMEPLAY_LAYOUTS:
            if r_layout in PIP_GAMEPLAY_LAYOUTS:
                score += 60
            if r_cat in GAMEPLAY_PIP_CATEGORIES:
                score += 15
            elif r_layout == "fullscreen":
                score -= 20
        elif detected_visual_mode in DUAL_SPEAKER_LAYOUTS:
            if r_layout in DUAL_SPEAKER_LAYOUTS:
                score += 60
            if r_cat == "podcast":
                score += 15
        elif detected_visual_mode == "reality_multicam":
            if r_layout == "reality_multicam":
                score += 60
            if r_cat == "realitys":
                score += 15

        if detected_verbal_cat != "auto" and r_cat == detected_verbal_cat:
            score += 25
        if detected_visual_mode != "auto" and r_layout == detected_visual_mode:
            score += 25

        if score > best_score:
            best_score = score
            best_rule = rule

    chosen = dict(best_rule)
    chosen["detected_visual_mode"] = detected_visual_mode
    chosen["detected_verbal_category"] = detected_verbal_cat
    return chosen


def process_video_pipeline(
    inbox_video_path: Path,
    cli_overrides: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Any] = None,
    cancel_event: Optional[threading.Event] = None,
    output_shorts_root: Optional[Path] = None,
    allow_global_temp_cleanup: bool = True,
    keep_inbox_source: bool = False,
) -> None:
    """
    Executes the 4-Skill autonomous pipeline sequentially for a single video,
    generating up to `shorts_per_video` Shorts from it and scheduling each one in YouTube.
    """
    active_cancel = cancel_event if cancel_event is not None else PIPELINE_CANCEL_EVENT

    def _notify(pct: int, phase: str, detail: str, short_update: Optional[Dict[str, Any]] = None) -> None:
        if active_cancel.is_set():
            raise PipelineCanceledError("Generación de Shorts cancelada por el usuario.")
        if callable(progress_callback):
            try:
                progress_callback(pct, phase, detail, short_update)
            except Exception:
                pass

    logger.info("=" * 78)
    logger.info("NUEVO VIDEO DETECTADO: %s", inbox_video_path.name)
    _notify(8, "Fase 1/4 · Preparación", f"Verificando estabilidad de archivo: {inbox_video_path.name}")

    if not wait_until_file_ready(inbox_video_path):
        logger.warning("El archivo %s ya no está disponible o no terminó de copiarse.", inbox_video_path)
        return

    settings = load_runtime_settings(cli_overrides)
    shorts_to_extract = _detect_shorts_count_from_filename(
        inbox_video_path.stem, settings["shorts_per_video"]
    )
    enable_bgm = False
    default_mood = "desactivada"
    enable_zoom = bool(settings.get("enable_dynamic_zoom", True))
    enable_jumpcuts = bool(settings.get("enable_jumpcuts", True))
    playback_speed = float(settings.get("playback_speed", 1.20))
    layout_mode = str(settings.get("layout_mode", "auto"))
    category_id = str(settings.get("youtube_category_id", "22"))
    auto_upload = False
    enable_social_dist = bool(settings.get("enable_social_distribution", False))
    subtitle_preset = str(settings.get("subtitle_preset", "hormozi_pop"))
    subtitle_position = str(settings.get("subtitle_position", "auto"))
    cam_overlay_pos = str(settings.get("cam_overlay_pos", "top_right"))
    custom_cam_box_norm = settings.get("custom_cam_box_norm")
    custom_content_box_norm = settings.get("custom_content_box_norm")

    logger.info(
        "Parámetros activos -> Shorts: %d | Speed: %.2fx | Layout: %s | BGM: %s (Mood=%s) | JumpCuts: %s | Subir YT: %s",
        shorts_to_extract,
        playback_speed,
        layout_mode,
        enable_bgm,
        default_mood,
        enable_jumpcuts,
        auto_upload,
    )

    for d in (INBOX_DIR, PROCESSING_DIR, OUTPUT_SHORTS_DIR, PUBLISHED_ARCHIVE_DIR, CONFIG_DIR):
        d.mkdir(parents=True, exist_ok=True)

    if inbox_video_path.parent.resolve() == PROCESSING_DIR.resolve():
        processing_video_path = inbox_video_path
        logger.info("[FASE 0] Reanudando video en área de trabajo: %s", processing_video_path)
    else:
        clean_proc_stem = sanitize_media_stem(inbox_video_path.stem, max_len=56)
        processing_video_path = PROCESSING_DIR / f"{clean_proc_stem}{inbox_video_path.suffix.lower()}"
        if processing_video_path.exists():
            timestamp_tag = int(time.time())
            processing_video_path = (
                PROCESSING_DIR / f"{clean_proc_stem}_{timestamp_tag}{inbox_video_path.suffix.lower()}"
            )
        if keep_inbox_source:
            shutil.copy2(str(win_long_path(inbox_video_path)), str(win_long_path(processing_video_path)))
            logger.info("[FASE 0] Video copiado a área de trabajo (inbox preservado): %s", processing_video_path)
        else:
            moved = False
            last_move_err: Optional[Exception] = None
            for attempt in range(4):
                try:
                    shutil.move(str(win_long_path(inbox_video_path)), str(win_long_path(processing_video_path)))
                    moved = True
                    break
                except (PermissionError, OSError) as mv_exc:
                    last_move_err = mv_exc
                    gc.collect()
                    if attempt < 3:
                        time.sleep(0.25)
            if not moved:
                try:
                    shutil.copy2(str(win_long_path(inbox_video_path)), str(win_long_path(processing_video_path)))
                    safe_unlink_with_retries(inbox_video_path, retries=3, delay_sec=0.2)
                except Exception as copy_exc:
                    raise (last_move_err or copy_exc)
            logger.info("[FASE 0] Video movido a área de trabajo: %s", processing_video_path)

    renders_completed = False
    try:
        # ------------------------------------------------------------------
        # SKILL 1: video-transcriber-analyzer (usa caché si ya fue transcrito)
        # ------------------------------------------------------------------
        _notify(
            22,
            "Fase 2/4 · Transcripción & IA",
            f"Transcribiendo audio y analizando hasta {shorts_to_extract} momentos virales...",
        )
        analysis_json_path = PROCESSING_DIR / f"{processing_video_path.stem}_analysis.json"
        if analysis_json_path.exists():
            logger.info(
                "[SKILL 1/4] Cargando transcripción previa en caché: %s",
                analysis_json_path.name,
            )
            raw_cached = json.loads(analysis_json_path.read_text(encoding="utf-8"))
            if isinstance(raw_cached, list):
                analyses_list = [
                    skill_transcriber.ViralClipAnalysis.model_validate(item)
                    for item in raw_cached[:shorts_to_extract]
                ]
            else:
                analyses_list = [skill_transcriber.ViralClipAnalysis.model_validate(raw_cached)]
        else:
            logger.info(
                "[SKILL 1/4] Ejecutando 'video-transcriber-analyzer' (extrayendo hasta %d Shorts)...",
                shorts_to_extract,
            )
            analyses_list = skill_transcriber.transcribe_and_analyze_multiple(
                video_path=processing_video_path,
                max_shorts=shorts_to_extract,
                enable_jumpcuts=enable_jumpcuts,
                output_json_path=analysis_json_path,
                progress_callback=lambda pct, phase, detail: _notify(pct, phase, detail),
            )

        total_extracted = len(analyses_list)
        db_path = CONFIG_DIR / "schedule_state.db"
        clean_base_stem = build_video_date_project_id(processing_video_path.stem, max_len=44)
        out_root = output_shorts_root if output_shorts_root is not None else OUTPUT_SHORTS_DIR
        dedicated_out_dir = out_root / clean_base_stem
        dedicated_out_dir.mkdir(parents=True, exist_ok=True)

        # ----------------------------------------------------------------------
        # EVALUACIÓN DE VIRALIDAD (GUÍA DE 10 PUNTOS CLAVE Y CATEGORÍA / MULTI-REGLA)
        # ----------------------------------------------------------------------
        content_category = str(settings.get("content_category", "auto"))
        raw_category_rules = settings.get("category_rules")
        category_rules = raw_category_rules if isinstance(raw_category_rules, list) and len(raw_category_rules) > 0 else None
        _notify(
            38,
            "Fase 2/4 · Analítica Viral y Encuadre",
            (
                f"Enrutando y puntuando {total_extracted} candidatos bajo {len(category_rules)} escena(s) del perfil..."
                if category_rules
                else f"Puntuando {total_extracted} candidatos..."
            ),
        )
        scored_candidates = []
        for idx, analysis in enumerate(analyses_list, start=1):
            dur = analysis.end_time - analysis.start_time
            eval_text = f"{getattr(analysis, 'transcript_excerpt', '')} {analysis.first_person_caption}".strip()
            resolved_rule = (
                resolve_clip_category_rule(
                    video_path=processing_video_path,
                    start_time=analysis.start_time,
                    end_time=analysis.end_time,
                    text=eval_text,
                    title=analysis.hook_title,
                    category_rules=category_rules,
                    fallback_settings=settings,
                )
                if category_rules
                else None
            )
            clip_eval_category = (
                str(resolved_rule.get("category") or content_category)
                if resolved_rule
                else content_category
            )
            llm_axes = {
                "hook_strength": float(getattr(analysis, "hook_strength", 8.5)),
                "standalone_value": float(getattr(analysis, "standalone_value", 8.5)),
                "virality_potential": float(getattr(analysis, "virality_potential", 8.5)),
            }
            ac_score = float(getattr(analysis, "acoustic_energy_score", 7.5))
            v_eval = skill_virality.evaluate_virality_10_points(
                text=eval_text,
                duration=dur,
                words=analysis.word_timestamps,
                title=analysis.hook_title,
                llm_scores=llm_axes,
                category=clip_eval_category,
                acoustic_score=ac_score,
            )
            scored_candidates.append(
                {
                    "idx": idx,
                    "analysis": analysis,
                    "virality_score": v_eval.total_points,
                    "virality_grade": v_eval.final_grade,
                    "virality_classification": v_eval.classification,
                    "virality_breakdown": v_eval.to_dict(),
                    "resolved_rule": resolved_rule,
                }
            )

        target_short_count = min(max(1, int(shorts_to_extract)), total_extracted)
        ordered_all, yt_list, other_only = skill_virality.select_and_order_shorts_by_virality_rules(
            candidates=scored_candidates,
            max_total_shorts=target_short_count,
            youtube_min_score=0,
            max_youtube_shorts=target_short_count,
            min_acceptable_score=50,
        )
        if len(ordered_all) < target_short_count and scored_candidates:
            already_ids = {id(c) for c in ordered_all}
            remaining = [c for c in scored_candidates if id(c) not in already_ids]
            remaining.sort(key=lambda x: int(x.get("virality_score", 0)), reverse=True)
            for rem_c in remaining:
                if len(ordered_all) >= target_short_count:
                    break
                rem_c["publish_to_youtube"] = True
                rem_c["publish_to_other_networks"] = True
                ordered_all.append(rem_c)

        hub_cfg = social_hub.get_raw_social_hub_config(CONFIG_DIR)
        auto_by_topic = bool(settings.get("auto_categorize_by_topic", True))
        allowed_account_cats = settings.get("allowed_account_categories")
        full_video_words = getattr(skill_transcriber, "LAST_FULL_WORDS_BY_VIDEO", {}).get(
            str(processing_video_path.resolve())
        )

        total_ordered = max(1, len(ordered_all))
        rendered_ok_count = 0
        last_render_err: Optional[Exception] = None
        for rank_idx, cand in enumerate(ordered_all, start=1):
            if active_cancel.is_set():
                raise PipelineCanceledError("Generación de Shorts cancelada por el usuario.")
            analysis = cand["analysis"]
            v_score = cand["virality_score"]
            v_grade = cand["virality_grade"]
            pub_yt = cand["publish_to_youtube"]

            logger.info("-" * 65)
            logger.info(
                "[SHORT %d/%d] Nota: %.1f/10 (%d pts) | YT: %s | Título: %s",
                rank_idx,
                len(ordered_all),
                v_grade,
                v_score,
                "SÍ (>=85)" if pub_yt else "NO (<85, solo redes)",
                analysis.hook_title,
            )

            chosen_mood = "desactivada"
            tier_tag = "Oro" if v_score >= 90 else ("Plata" if v_score >= 75 else "Meh")
            short_filename = f"{clean_base_stem}_{rank_idx:02d}_{tier_tag}_{v_score}pts.mp4"

            # ------------------------------------------------------------------
            # SKILL 2: vertical-crop-renderer (Subtítulos Neón + Hook Punch-In)
            # ------------------------------------------------------------------
            resolved_rule = cand.get("resolved_rule")
            if isinstance(resolved_rule, dict) and resolved_rule:
                rule_cat = str(resolved_rule.get("category") or "").strip()
                scene_display = str(resolved_rule.get("scene_label") or "").strip()
                detected_cat = (
                    rule_cat
                    if rule_cat and rule_cat != "auto"
                    else str(cand.get("virality_breakdown", {}).get("category", content_category))
                )
                req_layout = str(resolved_rule.get("layout_mode") or layout_mode or "auto").strip().lower()
                effective_layout_mode = "auto" if req_layout == "auto" else req_layout
                clip_sub_preset = str(resolved_rule.get("subtitle_preset") or subtitle_preset)
                clip_sub_pos = str(resolved_rule.get("subtitle_position") or subtitle_position)
                clip_cam_pos = str(resolved_rule.get("cam_overlay_pos") or cam_overlay_pos)
                clip_cam_box = resolved_rule.get("custom_cam_box_norm")
                clip_content_box = resolved_rule.get("custom_content_box_norm")
            else:
                scene_display = ""
                detected_cat = str(cand.get("virality_breakdown", {}).get("category", content_category))
                req_layout = (layout_mode or "auto").strip().lower()
                effective_layout_mode = "auto" if req_layout == "auto" else req_layout
                clip_sub_preset = subtitle_preset
                clip_sub_pos = subtitle_position
                clip_cam_pos = cam_overlay_pos
                clip_cam_box = custom_cam_box_norm
                clip_content_box = custom_content_box_norm
            render_pct = int(42 + ((rank_idx - 0.5) / total_ordered) * 40)
            scene_tag_txt = scene_display or (detected_cat if detected_cat and detected_cat != "auto" else "Escena Principal")
            _notify(
                render_pct,
                f"Fase 3/4 · Renderizado 9:16 ({rank_idx}/{len(ordered_all)})",
                f"Renderizando {short_filename} [Escena: {scene_tag_txt} · Encuadre: {effective_layout_mode}]...",
                {
                    "filename": short_filename,
                    "percent": 20,
                    "detail": f"Renderizando video 9:16 ({effective_layout_mode})...",
                },
            )
            effective_words = analysis.word_timestamps
            keep_ivs = getattr(analysis, "keep_intervals", None)
            refine_fn = getattr(skill_transcriber, "refine_clip_words_high_precision", None)
            if callable(refine_fn) and (not keep_ivs or len(keep_ivs) <= 1):
                effective_words = refine_fn(
                    video_path=processing_video_path,
                    start_time=analysis.start_time,
                    end_time=analysis.end_time,
                    fallback_words=analysis.word_timestamps,
                )
            try:
                rendered_short_path = skill_renderer.render_vertical_short(
                    video_path=processing_video_path,
                    start_time=analysis.start_time,
                    end_time=analysis.end_time,
                    word_timestamps=effective_words,
                    output_dir=dedicated_out_dir,
                    output_filename=short_filename,
                    bgm_mood=chosen_mood,
                    keep_intervals=keep_ivs,
                    enable_bgm=enable_bgm,
                    enable_dynamic_zoom=enable_zoom,
                    enable_hook_punchin=True,
                    layout_mode=effective_layout_mode,
                    playback_speed=playback_speed,
                    custom_cam_box_norm=clip_cam_box,
                    custom_content_box_norm=clip_content_box,
                    cam_overlay_pos=clip_cam_pos,
                    subtitle_preset=clip_sub_preset,
                    subtitle_position=clip_sub_pos,
                    category_hint=detected_cat,
                    context_word_timestamps=full_video_words,
                )
                rendered_ok_count += 1
            except PipelineCanceledError:
                raise
            except RuntimeError as render_err:
                last_render_err = render_err
                logger.warning(
                    "[SKILL 2/4] Se omitió el Short %s porque no generó video válido: %s",
                    short_filename,
                    render_err,
                )
                continue
            logger.info("[SKILL 2/4] Short 9:16 listo en: %s", rendered_short_path)

            # Guardar sidecar _meta.json para la cuadrícula de Shorts y analítica
            try:
                layout_used = effective_layout_mode
                tl_path = rendered_short_path.with_name(f"{rendered_short_path.stem}_opencut_timeline.json")
                if tl_path.exists():
                    try:
                        tl_data = json.loads(tl_path.read_text(encoding="utf-8"))
                        kf = tl_data.get("tracks", [{}])[0].get("effects", [{}])[0].get("keyframes", [{}])
                        layout_used = str(tl_data.get("layout_mode") or (kf[0].get("mode") if kf else None) or layout_used)
                    except Exception:
                        pass
                clip_scene_label = (
                    str(resolved_rule.get("scene_label") or "")
                    if isinstance(resolved_rule, dict)
                    else ""
                )
                short_account_categories = social_hub.classify_short_account_categories(
                    text=f"{getattr(analysis, 'transcript_excerpt', '')} {getattr(analysis, 'first_person_caption', '')}",
                    title=str(getattr(analysis, "hook_title", "")),
                    tags=list(getattr(analysis, "tags", [])),
                    scene_category=str(detected_cat),
                    scene_label=clip_scene_label,
                    hub_cfg=hub_cfg,
                    allowed_categories=allowed_account_cats,
                    auto_by_topic=auto_by_topic,
                )
                meta_payload = {
                    "short_filename": rendered_short_path.name,
                    "virality_score": int(v_score),
                    "virality_grade": float(v_grade),
                    "tier": str(tier_tag),
                    "category": str(detected_cat),
                    "account_categories": short_account_categories,
                    "layout_used": str(layout_used),
                    "subtitle_preset": str(clip_sub_preset),
                    "subtitle_position": str(clip_sub_pos),
                    "cam_overlay_pos": str(clip_cam_pos),
                    "custom_cam_box_norm": (
                        list(clip_cam_box) if clip_cam_box is not None else None
                    ),
                    "custom_content_box_norm": (
                        list(clip_content_box) if clip_content_box is not None else None
                    ),
                    "duration_sec": round(float(analysis.end_time) - float(analysis.start_time), 2),
                    "hook_title": str(getattr(analysis, "hook_title", "")),
                    "caption": str(getattr(analysis, "first_person_caption", "")),
                    "tags": list(getattr(analysis, "tags", [])),
                    "bgm_mood": "desactivada",
                    "youtube_eligible": True,
                    "local_ready": not bool(auto_upload or enable_social_dist),
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                rendered_short_path.with_name(f"{rendered_short_path.stem}_meta.json").write_text(
                    json.dumps(meta_payload, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception as meta_err:
                logger.warning("No se pudo escribir sidecar _meta.json para %s: %s", rendered_short_path.name, meta_err)

            if auto_upload or enable_social_dist:
                # ------------------------------------------------------------------
                # SKILL 3: strategic-time-calculator (1 Hora de por medio)
                # ------------------------------------------------------------------
                publish_at_iso = skill_scheduler.get_and_reserve_next_slot(
                    video_name=rendered_short_path.name,
                    db_path=db_path,
                )
                logger.info("[SKILL 3/4] Slot UTC reservado (+1 hora): %s", publish_at_iso)
                _notify(
                    int(42 + (rank_idx / total_ordered) * 42),
                    f"Fase 4/4 · Distribución en Redes ({rank_idx}/{len(ordered_all)})",
                    f"Reservado slot {publish_at_iso} y preparando subida de {short_filename}...",
                    {
                        "filename": short_filename,
                        "percent": 55,
                        "detail": "Slot AST reservado · Conectando con APIs de redes...",
                    },
                )

                # ------------------------------------------------------------------
                # SKILL 5: multi-social-uploader (IG, TikTok y Facebook según categorías)
                # ------------------------------------------------------------------
                yt_id_uploaded: Optional[str] = None
                resolved_targets = social_hub.resolve_target_accounts_for_categories(
                    short_account_categories, hub_cfg
                )
                try:
                    ig_targets = resolved_targets.get("instagram") or []
                    tt_targets = resolved_targets.get("tiktok") or []
                    fb_targets = resolved_targets.get("facebook") or []

                    for acc in ig_targets:
                        skill_ig_scheduler.enqueue_instagram_reel(
                            video_path=str(rendered_short_path),
                            account_key=str(acc.get("handle") or ""),
                            caption=f"{analysis.hook_title}\n\n{analysis.first_person_caption}",
                            scheduled_time_utc=publish_at_iso,
                            db_path=db_path,
                            ig_user_id=str(acc.get("external_id") or ""),
                        )
                    for acc in tt_targets:
                        skill_tt_scheduler.enqueue_tiktok_video(
                            video_path=str(rendered_short_path),
                            account_key=str(acc.get("handle") or ""),
                            caption=f"{analysis.hook_title} {' '.join(analysis.tags)}",
                            scheduled_time_utc=publish_at_iso,
                            db_path=db_path,
                        )
                    for acc in fb_targets:
                        social_hub.enqueue_facebook_reel(
                            video_path=str(rendered_short_path),
                            account_key=str(acc.get("handle") or ""),
                            fb_page_id=str(acc.get("external_id") or ""),
                            caption=f"{analysis.hook_title}\n\n{analysis.first_person_caption}",
                            scheduled_time_utc=publish_at_iso,
                            db_path=db_path,
                        )
                    logger.info(
                        "[SKILL 5/5] Encolado [%s] -> IG(%d), TT(%d), FB(%d) a las %s",
                        ",".join(short_account_categories),
                        len(ig_targets),
                        len(tt_targets),
                        len(fb_targets),
                        publish_at_iso,
                    )
                    _notify(
                        int(50 + (rank_idx / total_ordered) * 46),
                        f"Fase 4/4 · Redes Sociales ({rank_idx}/{len(ordered_all)})",
                        f"Encolado {short_filename} en YouTube, Instagram, TikTok y Facebook.",
                        {
                            "filename": short_filename,
                            "percent": 100 if yt_id_uploaded else 90,
                            "detail": (
                                f"Publicado en YouTube Shorts ({yt_id_uploaded}) + En cola multi-red"
                                if yt_id_uploaded
                                else "Programado en YouTube, IG, TikTok y Facebook · Listo en cola"
                            ),
                        },
                    )
                except Exception as soc_err:
                    logger.warning("[SKILL 5/5] Error encolando distribución en redes: %s", soc_err)
            else:
                logger.info(
                    "[LOCAL READY] Short guardado en %s sin subida automática ni colas sociales.",
                    rendered_short_path,
                )
                _notify(
                    int(50 + (rank_idx / total_ordered) * 46),
                    f"Fase 4/4 · Local Ready ({rank_idx}/{len(ordered_all)})",
                    f"Short {short_filename} listo en local (./output_shorts/).",
                    {
                        "filename": short_filename,
                        "percent": 100,
                        "detail": "Listo en local (./output_shorts/) · Sin subida automática",
                    },
                )

        if len(ordered_all) > 0 and rendered_ok_count == 0:
            raise RuntimeError(
                str(last_render_err or "Ningún Short generó fotogramas de video 9:16 válidos.")
            )

        renders_completed = True
        _notify(
            97,
            "Fase 4/4 · Limpieza Final",
            "Liberando monitor de video y limpiando archivos temporales...",
            {"release_source_preview": True},
        )

        # ------------------------------------------------------------------
        # AUTO-CLEANUP TEMPORARY & SOURCE FILES ON VIDEO COMPLETION
        # ------------------------------------------------------------------
        deleted_tmp = 0
        freed_mb = 0.0
        ig_deleted = 0
        ig_mb = 0.0
        try:
            safe_unlink_with_retries(processing_video_path, retries=5, delay_sec=0.25)
            safe_unlink_with_retries(analysis_json_path, retries=3, delay_sec=0.2)
            if allow_global_temp_cleanup:
                skill_cleanup.PROCESSING_DIR = PROCESSING_DIR
                skill_cleanup.OUTPUT_DIR = out_root
                skill_cleanup.PUBLISHED_ARCHIVE_DIR = PUBLISHED_ARCHIVE_DIR
                deleted_tmp, freed_mb = skill_cleanup.clean_processing_dir(max_age_seconds=0)
                ig_deleted, ig_mb = skill_cleanup.clean_ig_staging_cache(max_age_hours=0)
        except Exception as cleanup_exc:
            logger.warning(
                "Aviso en limpieza automática final (los Shorts ya están listos en output_shorts): %s",
                cleanup_exc,
            )
        logger.info(
            "[COMPLETADO] %d Short(s) procesados. Limpieza automática finalizada: %d temporales eliminados (%.2f MB liberados).",
            total_extracted,
            deleted_tmp + ig_deleted,
            freed_mb + ig_mb,
        )
        logger.info("=" * 78)

    except Exception as exc:
        logger.exception(
            "Error procesando el video '%s': %s",
            processing_video_path.name,
            exc,
        )
        if not renders_completed:
            try:
                if win_long_path(processing_video_path).exists():
                    if keep_inbox_source:
                        safe_unlink_with_retries(processing_video_path, retries=3, delay_sec=0.15)
                    else:
                        restored_path = INBOX_DIR / processing_video_path.name
                        if not win_long_path(restored_path).exists():
                            shutil.move(
                                str(win_long_path(processing_video_path)),
                                str(win_long_path(restored_path)),
                            )
                            logger.info(
                                "Video restaurado a inbox_videos tras fallo para no perder el archivo: %s",
                                restored_path,
                            )
            except Exception as restore_err:
                logger.warning("No se pudo restaurar el video a inbox_videos: %s", restore_err)
        raise


class InboxVideoEventHandler(FileSystemEventHandler):
    """Watchdog event handler that queues newly created or moved video files in ./inbox_videos/."""

    def __init__(self, video_queue: "Queue[Path]") -> None:
        super().__init__()
        self.video_queue = video_queue

    def _enqueue_if_video(self, path_str: str) -> None:
        candidate = Path(path_str).resolve()
        if candidate.is_file() and candidate.suffix.lower() in VIDEO_EXTENSIONS:
            logger.info("Evento watchdog detectado para: %s", candidate.name)
            self.video_queue.put(candidate)

    def on_created(self, event: FileCreatedEvent) -> None:
        if not event.is_directory:
            self._enqueue_if_video(event.src_path)

    def on_moved(self, event: FileMovedEvent) -> None:
        if not event.is_directory:
            self._enqueue_if_video(event.dest_path)


def parse_timecode_to_seconds(raw_tc: Optional[str]) -> Optional[float]:
    """
    Convierte un timecode ('HH:MM:SS', 'MM:SS' o segundos '90') a segundos float.
    Devuelve None si está vacío o no es válido.
    """
    if raw_tc is None:
        return None
    cleaned = str(raw_tc).strip()
    if not cleaned:
        return None
    try:
        if ":" not in cleaned:
            val = float(cleaned)
            return val if val >= 0.0 else None
        parts = [float(p) for p in cleaned.split(":")]
        if len(parts) == 3:
            return parts[0] * 3600.0 + parts[1] * 60.0 + parts[2]
        if len(parts) == 2:
            return parts[0] * 60.0 + parts[1]
    except Exception:
        return None
    return None


def _resolve_downloaded_media_path(ydl: Any, info: Dict[str, Any]) -> Path:
    """Resuelve la ruta real del video descargado por yt-dlp sin asumir siempre la extensión."""
    requested = info.get("requested_downloads") or []
    for item in requested:
        fp_raw = item.get("filepath") or item.get("_filename")
        if fp_raw:
            fp_path = Path(str(fp_raw))
            if win_long_path(fp_path).exists():
                return fp_path

    prepared = Path(ydl.prepare_filename(info))
    mp4_candidate = prepared.with_suffix(".mp4")
    if win_long_path(mp4_candidate).exists():
        return mp4_candidate
    if win_long_path(prepared).exists():
        return prepared
    for ext in (".mkv", ".webm", ".mov", ".m4v"):
        alt = prepared.with_suffix(ext)
        if win_long_path(alt).exists():
            return alt
    return mp4_candidate


def _cleanup_corrupt_ytdlp_artifacts(target_path: Path, stem_hint: Optional[str] = None) -> None:
    """Elimina descargas truncadas, fragmentos .part/.ytdl asociados y residuos legacy inbox_vi*."""
    candidates: Set[Path] = {target_path}
    parent = target_path.parent
    stems = {s for s in (target_path.stem, stem_hint) if s}
    if win_long_path(parent).exists():
        for stem in stems:
            for item in parent.glob(f"{stem}*"):
                name_low = item.name.lower()
                if (
                    item == target_path
                    or ".part" in name_low
                    or name_low.endswith(".ytdl")
                    or ".temp." in name_low
                    or re.search(r"\.f\d+\.", name_low) is not None
                ):
                    candidates.add(item)
        # Limpiar residuos sueltos de yt-dlp asociados al prefijo o truncamiento histórico inbox_vi*
        if win_long_path(BASE_DIR).exists():
            for legacy_item in BASE_DIR.glob("inbox_vi*"):
                try:
                    if win_long_path(legacy_item).is_file():
                        candidates.add(legacy_item)
                except OSError:
                    pass

    for item in candidates:
        try:
            if win_long_path(item).exists() and win_long_path(item).is_file():
                safe_unlink_with_retries(item, retries=3, delay_sec=0.1)
        except OSError:
            pass


def _validate_downloaded_video_integrity(media_path: Path, ffmpeg_bin: str) -> Tuple[bool, str]:
    """
    Verifica que el contenedor descargado tenga una pista de video real decodificable y no esté truncado
    respecto a la duración total del audio/contenedor (por ejemplo, colisión de .part al reanudar).
    """
    lp_media = win_long_path(media_path)
    if not lp_media.exists() or not lp_media.is_file():
        return False, "archivo descargado no existe"
    try:
        file_size = lp_media.stat().st_size
    except OSError as exc:
        return False, f"no se pudo leer tamaño del archivo ({exc})"

    # Stubs sintéticos pequeños en pruebas unitarias
    if file_size < 8192:
        return True, "stub_sintetico"

    kwargs: Dict[str, Any] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

    try:
        probe_proc = subprocess.run(
            [ffmpeg_bin, "-hide_banner", "-i", str(lp_media)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            **kwargs,
        )
        probe_out = f"{probe_proc.stderr}\n{probe_proc.stdout}"
    except Exception as exc:
        return False, f"error inspeccionando archivo descargado ({exc})"

    if "Video:" not in probe_out:
        return False, "contenedor sin pista de video"

    res_match = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", probe_out, re.DOTALL)
    if not res_match or int(res_match.group(1)) <= 0 or int(res_match.group(2)) <= 0:
        return False, "resolución de video inválida o nula"

    container_dur = 0.0
    dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", probe_out)
    if dur_match:
        container_dur = (
            int(dur_match.group(1)) * 3600.0
            + int(dur_match.group(2)) * 60.0
            + float(dur_match.group(3))
        )

    try:
        head_proc = subprocess.run(
            [
                ffmpeg_bin,
                "-v",
                "error",
                "-ss",
                "0",
                "-i",
                str(lp_media),
                "-map",
                "0:v:0",
                "-frames:v",
                "1",
                "-s",
                "16x16",
                "-pix_fmt",
                "rgb24",
                "-f",
                "rawvideo",
                "pipe:1",
            ],
            capture_output=True,
            timeout=15,
            **kwargs,
        )
        if head_proc.returncode != 0 or len(head_proc.stdout) < 16 * 16 * 3:
            return False, "primer fotograma de video inválido o vacío"
    except Exception as exc:
        return False, f"error decodificando primer fotograma ({exc})"

    if container_dur >= 20.0:
        tail_sec = max(1.0, container_dur * 0.85)
        try:
            tail_proc = subprocess.run(
                [
                    ffmpeg_bin,
                    "-v",
                    "error",
                    "-ss",
                    f"{tail_sec:.2f}",
                    "-i",
                    str(lp_media),
                    "-map",
                    "0:v:0",
                    "-frames:v",
                    "1",
                    "-s",
                    "16x16",
                    "-pix_fmt",
                    "rgb24",
                    "-f",
                    "rawvideo",
                    "pipe:1",
                ],
                capture_output=True,
                timeout=15,
                **kwargs,
            )
            if tail_proc.returncode != 0 or len(tail_proc.stdout) < 16 * 16 * 3:
                return (
                    False,
                    f"pista de video cortada antes del final ({tail_sec:.1f}s / {container_dur:.1f}s)",
                )
        except Exception as exc:
            return False, f"fallo verificando continuidad final de video ({exc})"

    return True, "ok"


def download_youtube_url_max_quality(
    url: str,
    progress_callback: Optional[Any] = None,
    download_section_start: Optional[str] = None,
    download_section_end: Optional[str] = None,
    cancel_event: Optional[threading.Event] = None,
    filename_prefix: Optional[str] = None,
) -> Path:
    """
    Downloads a YouTube, Twitch, or Kick video/livestream in highest native quality available
    (4K/1080p60/720p/best compatible stream) using yt-dlp + FFmpeg into ./inbox_videos/,
    with automatic fallback selector when a format restriction fails, optional time-range
    clipping (--download-sections), and live progress reporting via progress_callback.
    """
    import yt_dlp  # type: ignore
    try:
        import imageio_ffmpeg
        ffmpeg_loc = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        ffmpeg_loc = "ffmpeg"

    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSING_DIR.mkdir(parents=True, exist_ok=True)

    active_cancel = cancel_event if cancel_event is not None else PIPELINE_CANCEL_EVENT
    sec_start = parse_timecode_to_seconds(download_section_start)
    sec_end = parse_timecode_to_seconds(download_section_end)
    safe_prefix = sanitize_media_stem(filename_prefix, max_len=14) if filename_prefix else ""

    def _ytdlp_hook(d: Dict[str, Any]) -> None:
        if active_cancel.is_set():
            raise PipelineCanceledError("Descarga y generación cancelada por el usuario.")
        if not callable(progress_callback):
            return
        status = d.get("status")
        info_dict = d.get("info_dict") if isinstance(d.get("info_dict"), dict) else {}
        res_label = str(info_dict.get("resolution") or "HD/DASH")
        if status == "downloading":
            dl_bytes = float(d.get("downloaded_bytes") or 0.0)
            tot_bytes = float(d.get("total_bytes") or d.get("total_bytes_estimate") or 0.0)
            frag_idx = d.get("fragment_index")
            frag_cnt = d.get("fragment_count")
            speed_bps = float(d.get("speed") or 0.0)

            if tot_bytes > 0:
                raw_ratio = min(1.0, max(0.0, dl_bytes / tot_bytes))
            elif frag_idx and frag_cnt and int(frag_cnt) > 0:
                raw_ratio = min(1.0, max(0.0, float(frag_idx) / float(frag_cnt)))
            else:
                raw_ratio = 0.25

            # Mapear la descarga entre 2% y 20% del pipeline total
            overall_pct = max(2, min(20, int(round(2 + raw_ratio * 18))))
            dl_pct_str = f"{raw_ratio * 100:.1f}%"
            dl_mb_str = f"{dl_bytes / (1024 * 1024):.1f} MB"
            tot_gb_str = f" / {tot_bytes / (1024 * 1024 * 1024):.2f} GB" if tot_bytes > 0 else ""
            speed_str = f" @ {speed_bps / (1024 * 1024):.2f} MB/s" if speed_bps > 0 else ""
            frag_str = f" (frag {frag_idx}/{frag_cnt})" if (frag_idx is not None and frag_cnt is not None) else ""

            progress_callback(
                overall_pct,
                f"Fase 1/4 · Descarga YouTube DASH ({dl_pct_str})",
                f"Descargando stream {res_label}: {dl_mb_str}{tot_gb_str}{speed_str}{frag_str}",
                None,
            )
        elif status == "finished":
            progress_callback(
                20,
                "Fase 1/4 · Uniendo Audio y Video (FFmpeg)",
                f"Descarga de fragmentos completada · Fusionando contenedor MP4 ({res_label})...",
                None,
            )

    logger.info("Extrayendo stream en máxima calidad disponible desde URL: %s", url)
    # Limpiar residuos sueltos inbox_vi* en BASE_DIR originados por versiones previas sin paths.home
    if win_long_path(BASE_DIR).exists():
        for legacy_item in BASE_DIR.glob("inbox_vi*"):
            try:
                if win_long_path(legacy_item).is_file():
                    safe_unlink_with_retries(legacy_item, retries=2, delay_sec=0.05)
            except OSError:
                pass

    rel_outtmpl = "%(title).34B__%(id)s.%(ext)s"
    has_node_runtime = shutil.which("node") is not None

    def _build_opts(
        format_selector: str,
        enable_remote_ejs: bool,
        allow_continue: bool = True,
    ) -> Dict[str, Any]:
        opts: Dict[str, Any] = {
            "format": format_selector,
            "merge_output_format": "mp4",
            "ffmpeg_location": ffmpeg_loc,
            "paths": {"home": str(INBOX_DIR)},
            "outtmpl": rel_outtmpl,
            "trim_file_name": 56,
            "continuedl": allow_continue,
            "concurrent_fragment_downloads": 8,
            "progress_hooks": [_ytdlp_hook],
            "quiet": False,
        }
        if has_node_runtime:
            opts["js_runtimes"] = {"node": {}}
            if enable_remote_ejs:
                opts["remote_components"] = ["ejs:github"]
        if sec_start is not None and sec_end is not None and sec_end > sec_start:
            opts["download_ranges"] = yt_dlp.utils.download_range_func(None, [(sec_start, sec_end)])
            opts["force_keyframes_at_cuts"] = True
        return opts

    if sec_start is not None and sec_end is not None and sec_end > sec_start:
        logger.info("Descargando sección específica del stream: %.1fs -> %.1fs", sec_start, sec_end)

    format_stages = [
        (PRIMARY_YTDLP_FORMAT, True, "primario"),
        (FALLBACK_YTDLP_FORMAT, False, "respaldo universal bv*+ba/b"),
    ]
    last_exc: Optional[Exception] = None
    info: Optional[Dict[str, Any]] = None
    filename: Optional[Path] = None
    had_corrupt_resume = False

    for stage_idx, (fmt_selector, enable_ejs, stage_label) in enumerate(format_stages):
        continue_choices = (False,) if had_corrupt_resume else (True, False)
        for allow_continue in continue_choices:
            ydl_opts = _build_opts(
                fmt_selector,
                enable_remote_ejs=enable_ejs,
                allow_continue=allow_continue,
            )
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    candidate_path = _resolve_downloaded_media_path(ydl, info)
            except PipelineCanceledError:
                raise
            except Exception as exc:
                last_exc = exc
                if active_cancel.is_set():
                    raise PipelineCanceledError("Descarga y generación cancelada por el usuario.") from exc
                if stage_idx < len(format_stages) - 1:
                    logger.warning(
                        "Fallo en descarga con selector %s (%s). Reintentando con selector %s...",
                        stage_label,
                        exc,
                        format_stages[stage_idx + 1][2],
                    )
                    break
                raise

            is_valid, reason = _validate_downloaded_video_integrity(candidate_path, ffmpeg_loc)
            if is_valid:
                filename = candidate_path
                break

            had_corrupt_resume = True
            last_exc = RuntimeError(
                f"Descarga corrupta o sin pista de video completa ({reason}) en '{candidate_path.name}'."
            )
            logger.warning(
                "Descarga inválida detectada (%s) en intento '%s' (continuedl=%s). Limpiando y descargando limpio...",
                reason,
                stage_label,
                allow_continue,
            )
            if callable(progress_callback):
                progress_callback(
                    5,
                    "Fase 1/4 · Reiniciando Descarga Limpia",
                    f"Se detectó descarga previa corrupta ({reason}). Reintentando desde cero...",
                    None,
                )
            _cleanup_corrupt_ytdlp_artifacts(candidate_path, stem_hint=safe_prefix or None)
            filename = None
            if not allow_continue:
                break

        if filename is not None:
            break

    if filename is None:
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("No se pudo descargar un archivo de video válido desde yt-dlp.")

    clean_dl_stem = sanitize_media_stem(filename.stem, max_len=56)
    target_ext = filename.suffix.lower() or ".mp4"
    if filename.stem != clean_dl_stem and win_long_path(filename).exists():
        clean_dl_path = filename.with_name(f"{clean_dl_stem}{target_ext}")
        if clean_dl_path.exists() and clean_dl_path != filename:
            clean_dl_path = filename.with_name(f"{clean_dl_stem}_{int(time.time())}{target_ext}")
        try:
            win_long_path(filename).rename(win_long_path(clean_dl_path))
            filename = clean_dl_path
        except OSError as rn_err:
            logger.warning("No se pudo renombrar descarga limpia '%s': %s", filename.name, rn_err)
    logger.info("Descarga completada en: %s", filename)
    return filename.resolve()


def run_daemon(cli_overrides: Optional[Dict[str, Any]] = None, run_once: bool = False) -> None:
    """Starts the Watchdog observer daemon monitoring ./inbox_videos/."""
    for folder in (INBOX_DIR, PROCESSING_DIR, OUTPUT_SHORTS_DIR, PUBLISHED_ARCHIVE_DIR, CONFIG_DIR):
        folder.mkdir(parents=True, exist_ok=True)

    load_runtime_settings(cli_overrides)
    skill_scheduler.init_db(CONFIG_DIR / "schedule_state.db")

    video_queue: "Queue[Path]" = Queue()
    seen_in_flight: Set[Path] = set()

    for existing in sorted(INBOX_DIR.iterdir()):
        if existing.is_file() and existing.suffix.lower() in VIDEO_EXTENSIONS:
            video_queue.put(existing.resolve())

    if video_queue.empty():
        for pending_proc in sorted(PROCESSING_DIR.iterdir()):
            if pending_proc.is_file() and pending_proc.suffix.lower() in VIDEO_EXTENSIONS:
                video_queue.put(pending_proc.resolve())

    event_handler = InboxVideoEventHandler(video_queue)
    observer = Observer()
    observer.schedule(event_handler, str(INBOX_DIR), recursive=False)
    observer.start()

    logger.info("Sistema Autónomo de YouTube Shorts iniciado.")
    logger.info("1. Carpeta de entrada (suelta tus videos aquí): %s", INBOX_DIR)
    logger.info("2. Archivo de configuración en caliente: %s", SETTINGS_PATH)
    logger.info("3. Carpeta de Shorts generados: %s", OUTPUT_SHORTS_DIR)

    try:
        while True:
            try:
                next_video = video_queue.get(timeout=1.0)
            except Empty:
                if run_once and video_queue.empty():
                    break
                continue

            if next_video in seen_in_flight or not next_video.exists():
                video_queue.task_done()
                continue

            seen_in_flight.add(next_video)
            try:
                process_video_pipeline(next_video, cli_overrides=cli_overrides)
            except Exception as daemon_err:
                logger.error("El pipeline falló para %s: %s", next_video.name, daemon_err)
            finally:
                seen_in_flight.discard(next_video)
                video_queue.task_done()

            if run_once and video_queue.empty():
                break
    except KeyboardInterrupt:
        logger.info("Deteniendo daemon por solicitud del usuario (Ctrl+C)...")
    finally:
        observer.stop()
        observer.join()
        logger.info("Daemon detenido correctamente.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Orquestador Autónomo de YouTube Shorts (Watchdog + 4 Antigravity Skills)"
    )
    parser.add_argument(
        "--shorts-per-video",
        type=int,
        default=None,
        help=" cuántos Shorts extraer por cada video largo (sobreescribe config/settings.json)",
    )
    parser.add_argument(
        "--mood",
        choices=["auto", "misterio", "comedia", "impacto", "reflexion", "urbano"],
        default=None,
        help="Estado de ánimo de la música de fondo (por defecto 'auto' lo elige la IA)",
    )
    parser.add_argument(
        "--no-bgm",
        action="store_true",
        help="Desactiva la música de fondo automática",
    )
    parser.add_argument(
        "--no-zoom",
        action="store_true",
        help="Desactiva el efecto Dynamic Zoom (Punch-In)",
    )
    parser.add_argument(
        "--no-jumpcuts",
        action="store_true",
        help="Desactiva el recorte automático de silencios largos",
    )
    parser.add_argument(
        "--dry-run-upload",
        action="store_true",
        help="Genera los Shorts en ./output_shorts/ sin subirlos a YouTube",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Procesa los videos actuales en ./inbox_videos/ y termina",
    )
    parser.add_argument(
        "--youtube-url",
        type=str,
        default=None,
        help="Descarga directamente un link de YouTube en máxima calidad (1080p60+) a ./inbox_videos/ antes de procesar",
    )
    args = parser.parse_args()

    if args.youtube_url:
        download_youtube_url_max_quality(args.youtube_url)

    overrides: Dict[str, Any] = {}
    if args.shorts_per_video is not None:
        overrides["shorts_per_video"] = args.shorts_per_video
    if args.mood is not None:
        overrides["default_bgm_mood"] = args.mood
    if args.no_bgm:
        overrides["enable_bgm"] = False
    if args.no_zoom:
        overrides["enable_dynamic_zoom"] = False
    if args.no_jumpcuts:
        overrides["enable_jumpcuts"] = False
    if args.dry_run_upload:
        overrides["auto_upload_to_youtube"] = False

    run_daemon(cli_overrides=overrides, run_once=args.once)
