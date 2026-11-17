"""
Servidor Backend FastAPI para Short YT (Auto-Clipper Shorts Engine).
Expone endpoints REST reales conectados directamente a las funciones core del proyecto.
"""

from __future__ import annotations

import gc
import hashlib
import importlib.util
import json
import logging
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
import uuid
import wsgiref.simple_server
import wsgiref.util
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Literal, Optional, Tuple
from urllib.parse import parse_qs, quote, unquote

import cv2
import numpy as np
from fastapi import BackgroundTasks, Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import inbox_inspector
import live_stream_monitor
import main_daemon as _main_daemon_bootstrap
from config import social_hub

_main_daemon_bootstrap.enable_silent_windows_subprocesses()

BASE_DIR = Path(__file__).resolve().parent
INBOX_DIR = BASE_DIR / "inbox_videos"
PROCESSING_DIR = BASE_DIR / "processing"
OUTPUT_SHORTS_DIR = BASE_DIR / "output_shorts"
PUBLISHED_ARCHIVE_DIR = BASE_DIR / "published_archive"
CONFIG_DIR = BASE_DIR / "config"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
DB_PATH = CONFIG_DIR / "schedule_state.db"
SKILLS_DIR = BASE_DIR / ".agents" / "skills"

# Garantizar flujos válidos en pythonw.exe / procesos sin consola antes de configurar logging
_LOG_DIR = BASE_DIR / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
if sys.stdout is None or sys.stderr is None or sys.__stdout__ is None or sys.__stderr__ is None:
    _silent_log_fp = open(_LOG_DIR / "api_server.log", "a", encoding="utf-8", buffering=1)
    try:
        os.dup2(_silent_log_fp.fileno(), 1)
        os.dup2(_silent_log_fp.fileno(), 2)
    except Exception:
        pass
    if sys.stdout is None:
        sys.stdout = _silent_log_fp  # type: ignore[assignment]
    if sys.stderr is None:
        sys.stderr = _silent_log_fp  # type: ignore[assignment]
    if sys.__stdout__ is None:
        sys.__stdout__ = sys.stdout  # type: ignore[misc]
    if sys.__stderr__ is None:
        sys.__stderr__ = sys.stderr  # type: ignore[misc]

win_long_path = _main_daemon_bootstrap.win_long_path

logger = logging.getLogger("short_yt_api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

VIDEO_EXTENSIONS = inbox_inspector.VIDEO_EXTENSIONS
REGISTERED_LOCAL_VIDEOS: Dict[str, Path] = {}
_LAST_PICKED_VIDEO_DIR: Optional[Path] = None


def _get_local_picks_dir() -> Path:
    """Subcarpeta temporal bajo ./processing/ para videos locales cargados desde el navegador."""
    return PROCESSING_DIR / "local_picks"


def _prune_local_picks_dir(
    keep_latest: int = 4,
    protected_paths: Optional[set[Path]] = None,
) -> None:
    """Conserva únicamente los últimos N videos elegidos localmente sin borrar trabajos activos."""
    picks_dir = _get_local_picks_dir()
    if not picks_dir.exists():
        return
    protected_resolved: set[Path] = set()
    if protected_paths:
        for p in protected_paths:
            try:
                protected_resolved.add(p.resolve())
            except OSError:
                pass
    for st in PROJECT_STATES.values():
        if st.get("status") in {"STARTED", "RUNNING", "DISCOVERING"} and st.get("current_video"):
            try:
                protected_resolved.add((picks_dir / Path(str(st["current_video"])).name).resolve())
            except OSError:
                pass

    now = time.time()
    staged_videos: List[Path] = []
    for item in picks_dir.iterdir():
        try:
            lp_item = win_long_path(item)
            if not lp_item.is_file():
                continue
            if item.name.startswith(".tmp_"):
                if now - lp_item.stat().st_mtime > 3600:
                    lp_item.unlink(missing_ok=True)
                continue
            staged_videos.append(item)
        except OSError:
            continue

    staged_videos.sort(key=lambda p: win_long_path(p).stat().st_mtime, reverse=True)
    for old_item in staged_videos[max(0, keep_latest) :]:
        try:
            if old_item.resolve() in protected_resolved:
                continue
            win_long_path(old_item).unlink(missing_ok=True)
        except OSError:
            pass


def register_local_video_path(video_path: Path) -> Path:
    """Registra una ruta local elegida explícitamente por el usuario mediante el Explorador."""
    resolved = video_path.resolve()
    lp = win_long_path(resolved)
    if not lp.exists() or not lp.is_file():
        raise FileNotFoundError(f"El video seleccionado no existe en disco: {resolved}")
    if resolved.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError(
            f"Formato no soportado ({resolved.suffix or 'sin extensión'}). Usa MP4, MOV, MKV, AVI o WEBM."
        )
    REGISTERED_LOCAL_VIDEOS[str(resolved)] = resolved
    REGISTERED_LOCAL_VIDEOS[resolved.name] = resolved
    return resolved


def _resolve_local_video_path(raw_video_ref: str, *, allow_processing: bool = True) -> Path:
    """
    Resuelve un video local desde la lista blanca del Explorador (REGISTERED_LOCAL_VIDEOS)
    o desde ./inbox_videos/ (y ./processing/ si allow_processing=True).
    Nunca acepta rutas externas arbitrarias no seleccionadas por el usuario.
    """
    cleaned = str(raw_video_ref or "").strip()
    if not cleaned:
        raise HTTPException(
            status_code=400,
            detail="Debes seleccionar un archivo de video local mediante el botón Archivo Local.",
        )

    is_bare_name = Path(cleaned).name == cleaned
    matched: Optional[Path] = None

    if cleaned in REGISTERED_LOCAL_VIDEOS:
        matched = REGISTERED_LOCAL_VIDEOS[cleaned]
    elif is_bare_name:
        if cleaned in REGISTERED_LOCAL_VIDEOS:
            matched = REGISTERED_LOCAL_VIDEOS[cleaned]
    else:
        try:
            resolved_key = str(Path(cleaned).resolve())
        except OSError:
            resolved_key = ""
        if resolved_key and resolved_key in REGISTERED_LOCAL_VIDEOS:
            matched = REGISTERED_LOCAL_VIDEOS[resolved_key]

    if matched is not None:
        lp = win_long_path(matched)
        if lp.exists() and lp.is_file():
            return matched
        raise HTTPException(
            status_code=404,
            detail=f"El video seleccionado '{matched.name}' ya no existe en disco.",
        )

    inbox_root = INBOX_DIR.resolve()
    local_picks_dir = _get_local_picks_dir()
    picks_root = local_picks_dir.resolve()
    proc_root = PROCESSING_DIR.resolve()
    if is_bare_name:
        search_dirs = (
            (INBOX_DIR, local_picks_dir, PROCESSING_DIR)
            if allow_processing
            else (INBOX_DIR, local_picks_dir)
        )
        for base_dir in search_dirs:
            cand = (base_dir / cleaned).resolve()
            if win_long_path(cand).exists() and win_long_path(cand).is_file():
                return cand
    else:
        try:
            cand = Path(cleaned).resolve()
        except OSError:
            cand = Path("")
        allowed_roots = (
            (inbox_root, picks_root, proc_root) if allow_processing else (inbox_root, picks_root)
        )
        if str(cand) and cand.parent in allowed_roots and win_long_path(cand).exists() and win_long_path(cand).is_file():
            return cand

    display_name = Path(cleaned).name or cleaned
    raise HTTPException(
        status_code=404,
        detail=f"El archivo '{display_name}' no fue encontrado.",
    )

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
    "theme_mode": "light",
}


def _load_skill_module(skill_folder: str, module_filename: str) -> ModuleType:
    """Carga dinámicamente un módulo real desde .agents/skills/<skill_folder>/<module_filename>."""
    module_path = SKILLS_DIR / skill_folder / module_filename
    if not module_path.exists():
        raise FileNotFoundError(f"No se encontró el módulo en: {module_path}")

    skill_dir_str = str(module_path.parent)
    if skill_dir_str not in sys.path:
        sys.path.insert(0, skill_dir_str)

    module_name = f"shortyt_skill_{skill_folder.replace('-', '_')}_{module_filename.replace('.', '_')}"
    if module_name in sys.modules:
        return sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, str(module_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"No se pudo cargar especificación para: {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


skill_virality = _load_skill_module("video-transcriber-analyzer", "virality_scorer.py")
skill_scheduler = _load_skill_module("strategic-time-calculator", "calculator.py")
skill_uploader = _load_skill_module("youtube-shorts-uploader", "uploader.py")
skill_ig_scheduler = _load_skill_module("multi-social-uploader", "instagram_scheduler.py")
skill_tt_scheduler = _load_skill_module("multi-social-uploader", "tiktok_scheduler.py")
skill_tt_wa = _load_skill_module("multi-social-uploader", "tiktok_whatsapp_coordinator.py")
skill_cleanup = _load_skill_module("multi-social-uploader", "disk_cleanup.py")
skill_renderer = _load_skill_module("vertical-crop-renderer", "renderer.py")
skill_analyzer = _load_skill_module("video-transcriber-analyzer", "analyzer.py")


PIPELINE_STATE_PATH = CONFIG_DIR / "pipeline_state.json"

PIPELINE_STATE: Dict[str, Any] = {
    "job_id": None,
    "status": "IDLE",
    "current_video": None,
    "source_type": "inbox",
    "source_preview_url": None,
    "progress_percent": 0,
    "phase_label": "En espera",
    "step_detail": "Sistema listo para procesar un nuevo video.",
    "message": "Sistema listo para procesar.",
    "short_uploads": {},
    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
}

PROJECT_STATES: Dict[str, Dict[str, Any]] = {"default": PIPELINE_STATE}
PROJECT_STATE_DIRS: Dict[str, Path] = {}
PROJECT_CANCEL_EVENTS: Dict[str, threading.Event] = {}


def _normalize_project_id(project_id: Optional[str]) -> str:
    """Normaliza un identificador de proyecto/ventana; devuelve 'default' si se omite."""
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", str(project_id or "").strip())[:56]
    return cleaned or "default"


def _make_initial_pipeline_state(
    phase_label: str = "En espera",
    detail: str = "Sistema listo para procesar un nuevo video.",
) -> Dict[str, Any]:
    return {
        "job_id": None,
        "status": "IDLE",
        "current_video": None,
        "project_name": None,
        "source_type": "inbox",
        "source_preview_url": None,
        "progress_percent": 0,
        "phase_label": phase_label,
        "step_detail": detail,
        "message": detail,
        "short_uploads": {},
        "requires_schedule_confirmation": False,
        "completion_summary": None,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _project_state_file(pid: str) -> Path:
    if pid == "default":
        return CONFIG_DIR / "pipeline_state.json"
    return CONFIG_DIR / "projects" / f"{pid}_state.json"


def _find_source_media_path(raw_filename: str) -> Optional[Path]:
    """Localiza el archivo fuente en REGISTERED_LOCAL_VIDEOS, inbox_videos, local_picks, processing o archive."""
    clean_name = Path(unquote(raw_filename)).name
    if not clean_name:
        return None
    raw_path = Path(clean_name)
    sanitized_name = (
        f"{_main_daemon_bootstrap.sanitize_media_stem(raw_path.stem, max_len=56)}"
        f"{raw_path.suffix.lower()}"
    )
    candidate_names = [clean_name] if sanitized_name == clean_name else [clean_name, sanitized_name]
    search_dirs = (INBOX_DIR, _get_local_picks_dir(), PROCESSING_DIR, PUBLISHED_ARCHIVE_DIR)
    for cand_name in candidate_names:
        reg_path = REGISTERED_LOCAL_VIDEOS.get(cand_name)
        if reg_path is not None:
            try:
                lp_reg = win_long_path(reg_path.resolve())
                if lp_reg.exists() and lp_reg.is_file():
                    return lp_reg
            except OSError:
                pass
        for search_dir in search_dirs:
            try:
                lp = win_long_path((search_dir / cand_name).resolve())
                if lp.exists() and lp.is_file():
                    return lp
            except OSError:
                continue
    return None


def _source_media_file_exists(raw_preview_url: Optional[str]) -> bool:
    """Verifica si el archivo backing de una URL /api/media/source/<archivo> aún existe en disco."""
    if not raw_preview_url:
        return True
    preview_str = str(raw_preview_url)
    prefix = "/api/media/source/"
    if not preview_str.startswith(prefix):
        return True
    return _find_source_media_path(preview_str[len(prefix) :]) is not None


def _resolve_project_display_name(pid: str, state: Dict[str, Any]) -> str:
    """Calcula un nombre legible '<Video>_<YYYY-MM-DD>' o conserva el identificador de proyecto."""
    if state.get("current_video"):
        return _main_daemon_bootstrap.build_video_date_project_id(str(state["current_video"]))
    if state.get("project_name"):
        return str(state["project_name"])
    if pid != "default":
        return pid
    return _main_daemon_bootstrap.build_video_date_project_id(None)


def _get_project_state(project_id: Optional[str] = None) -> Dict[str, Any]:
    """Devuelve el diccionario de estado mutable para el proyecto indicado (retrocompatible con PIPELINE_STATE)."""
    pid = _normalize_project_id(project_id)
    if pid == "default":
        PROJECT_STATES["default"] = PIPELINE_STATE
        if PIPELINE_STATE.get("source_preview_url") and not _source_media_file_exists(
            PIPELINE_STATE.get("source_preview_url")
        ):
            PIPELINE_STATE["source_preview_url"] = None
        PIPELINE_STATE["project_id"] = "default"
        PIPELINE_STATE["project_name"] = _resolve_project_display_name("default", PIPELINE_STATE)
        return PIPELINE_STATE

    state = PROJECT_STATES.get(pid)
    tracked_dir = PROJECT_STATE_DIRS.get(pid)
    if state is None or tracked_dir != CONFIG_DIR:
        state = _make_initial_pipeline_state()
        st_file = _project_state_file(pid)
        if st_file.exists():
            try:
                loaded = json.loads(st_file.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    state.update(loaded)
            except Exception:
                pass
        PROJECT_STATES[pid] = state
        PROJECT_STATE_DIRS[pid] = CONFIG_DIR
    if state.get("source_preview_url") and not _source_media_file_exists(
        state.get("source_preview_url")
    ):
        state["source_preview_url"] = None
    state["project_id"] = pid
    state["project_name"] = _resolve_project_display_name(pid, state)
    return state


def _persist_pipeline_state(project_id: Optional[str] = None) -> None:
    """Guarda el estado actual del pipeline del proyecto indicado en disco."""
    try:
        pid = _normalize_project_id(project_id)
        state = _get_project_state(pid)
        target_file = _project_state_file(pid)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(
            json.dumps(state, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def _get_project_cancel_event(project_id: Optional[str] = None) -> threading.Event:
    """Devuelve el threading.Event de cancelación aislado por proyecto."""
    pid = _normalize_project_id(project_id)
    if pid == "default":
        return _main_daemon_bootstrap.PIPELINE_CANCEL_EVENT
    ev = PROJECT_CANCEL_EVENTS.get(pid)
    if ev is None:
        ev = threading.Event()
        PROJECT_CANCEL_EVENTS[pid] = ev
    return ev


def _get_project_output_dir(project_id: Optional[str] = None) -> Path:
    """Devuelve la carpeta raíz donde se guardan los Shorts del proyecto."""
    pid = _normalize_project_id(project_id)
    if pid == "default":
        return OUTPUT_SHORTS_DIR
    return OUTPUT_SHORTS_DIR / "_projects" / pid


def _infer_project_id_from_rel_path(short_rel_path: str) -> str:
    """Infiere el project_id desde una ruta relativa dentro de ./output_shorts/."""
    parts = [p for p in unquote(short_rel_path).replace("\\", "/").strip("/").split("/") if p]
    if len(parts) >= 2 and parts[0] == "_projects":
        return _normalize_project_id(parts[1])
    return "default"


def _has_other_active_projects(exclude_project_id: Optional[str] = None) -> bool:
    """Retorna True si otro proyecto distinto se encuentra ejecutando descarga o render."""
    excl = _normalize_project_id(exclude_project_id) if exclude_project_id else None
    snapshot: Dict[str, Dict[str, Any]] = {"default": PIPELINE_STATE}
    for pid, st in PROJECT_STATES.items():
        if pid != "default" and PROJECT_STATE_DIRS.get(pid) == CONFIG_DIR:
            snapshot[pid] = st
    for pid, st in snapshot.items():
        if excl is not None and pid == excl:
            continue
        if st.get("status") in ("STARTED", "RUNNING", "DISCOVERING"):
            return True
    return False


if PIPELINE_STATE_PATH.exists():
    try:
        _saved_state = json.loads(PIPELINE_STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(_saved_state, dict):
            PIPELINE_STATE.update(_saved_state)
    except Exception:
        pass


def load_settings(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Lee y actualiza ./config/settings.json."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    settings = dict(DEFAULT_SETTINGS)
    if SETTINGS_PATH.exists():
        try:
            loaded = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                settings.update(loaded)
        except Exception as exc:
            logger.warning("Error leyendo settings.json: %s", exc)
    else:
        SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")

    if overrides:
        for k, v in overrides.items():
            if v is not None or k in _main_daemon_bootstrap._NULLABLE_OVERRIDE_KEYS:
                settings[k] = v
        SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")

    return settings


class InspectRequest(BaseModel):
    video_filename: str = Field(..., description="Nombre del archivo de video en inbox_videos")


class ThemeSettingsRequest(BaseModel):
    theme_mode: Literal["light", "dark"] = Field(
        ...,
        description="Modo de apariencia visual: light o dark",
    )


LayoutModeLiteral = Literal[
    "auto",
    "fullscreen",
    "split_streamer",
    "split_50_50",
    "ometv",
    "podcast_dynamic",
    "gaming_hud",
    "reaction_pip",
    "reality_multicam",
    "floating_cam_top",
    "floating_circle",
    "blur_16_9_cam",
]

ContentCategoryLiteral = Literal[
    "auto",
    "opinion_monologo",
    "reacciones",
    "videojuegos",
    "podcast",
    "realitys",
    "storytime_anecdota",
    "tutorial_curiosidad",
]


class CategorySceneRule(BaseModel):
    rule_id: str = Field(default="rule_1", min_length=1, max_length=60)
    category: ContentCategoryLiteral = Field(default="auto")
    scene_label: str = Field(default="Escena Principal", min_length=1, max_length=120)
    detected_share_pct: int = Field(default=100, ge=0, le=100)
    layout_mode: LayoutModeLiteral = Field(default="auto")
    subtitle_preset: str = Field(default="hormozi_pop")
    subtitle_position: Literal["auto", "top", "center", "bottom"] = Field(default="auto")
    cam_overlay_pos: Literal["top_left", "top_right", "bottom_left", "bottom_right"] = Field(
        default="top_right"
    )
    custom_cam_box_norm: Optional[List[float]] = Field(default=None)
    custom_content_box_norm: Optional[List[float]] = Field(default=None)
    custom_boxes_manual: bool = Field(default=False)
    frame_url: Optional[str] = Field(default=None)
    sample_timestamp_sec: Optional[float] = Field(default=None, ge=0.0)


class PreAnalyzeRequest(BaseModel):
    source_type: Literal["inbox", "youtube_url"] = Field(default="inbox")
    video_filename: Optional[str] = Field(default=None)
    youtube_url: Optional[str] = Field(default=None)
    download_section_start: Optional[str] = Field(default=None)
    download_section_end: Optional[str] = Field(default=None)
    project_id: Optional[str] = Field(default=None)


class ContentProfilePayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    match_keywords: List[str] = Field(default_factory=list)
    scenes: List[CategorySceneRule] = Field(..., min_length=1, max_length=4)
    auto_categorize_by_topic: bool = Field(default=True)
    allowed_account_categories: List[str] = Field(
        default_factory=lambda: ["principales", "gaming", "clipping"]
    )


class PipelineProcessRequest(BaseModel):
    source_type: Literal["inbox", "youtube_url"] = Field(
        default="inbox",
        description="Origen del video: archivo en inbox_videos o enlace de YouTube",
    )
    video_filename: Optional[str] = Field(
        default=None,
        description="Nombre del video dentro de inbox_videos",
    )
    youtube_url: Optional[str] = Field(
        default=None,
        description="URL del video o directo (YouTube, Twitch o Kick)",
    )
    download_section_start: Optional[str] = Field(
        default=None,
        description="Tiempo inicial opcional para descarga parcial (--download-sections), ej. 00:05:00",
    )
    download_section_end: Optional[str] = Field(
        default=None,
        description="Tiempo final opcional para descarga parcial (--download-sections), ej. 00:25:00",
    )
    content_category: Literal[
        "auto",
        "opinion_monologo",
        "reacciones",
        "videojuegos",
        "podcast",
        "realitys",
        "storytime_anecdota",
        "tutorial_curiosidad",
    ] = Field(
        default="auto",
        description="Categoría de analítica viral para evaluar y puntuar los fragmentos",
    )
    shorts_per_video: int = Field(
        default=8,
        ge=1,
        le=24,
        description="Cantidad de Shorts a extraer (1 a 24)",
    )
    layout_mode: LayoutModeLiteral = Field(
        default="auto",
        description="Modo de recorte y composición vertical",
    )
    bgm_mood: Literal["auto", "desactivada", "misterio", "comedia", "impacto", "reflexion", "urbano"] = Field(
        default="desactivada",
        description="Ambiente musical de fondo desactivado (audio 100% limpio)",
    )
    auto_upload_to_youtube: bool = Field(
        default=False,
        description="Si es True, sube automáticamente a YouTube todos los Shorts configurados",
    )
    enable_social_distribution: bool = Field(
        default=False,
        description="Si es True, reserva slots y encola distribución en IG/TikTok/Facebook al finalizar",
    )
    auto_categorize_by_topic: bool = Field(
        default=True,
        description="Si es True, clasifica cada Short según tema en las categorías permitidas",
    )
    allowed_account_categories: Optional[List[str]] = Field(
        default=None,
        description="Categorías permitidas del Hub Social (principales, gaming, clipping)",
    )
    subtitle_preset: str = Field(
        default="hormozi_pop",
        description="Estilo de animación de subtítulos",
    )
    subtitle_position: Literal["auto", "top", "center", "bottom"] = Field(
        default="auto",
        description="Posición vertical de subtítulos",
    )
    cam_overlay_pos: Literal["top_left", "top_right", "bottom_left", "bottom_right"] = Field(
        default="top_right",
        description="Esquina de la cámara flotante para layouts overlay/círculo",
    )
    custom_cam_box_norm: Optional[List[float]] = Field(
        default=None,
        description="Coordenadas normalizadas [x,y,w,h] seleccionadas en el Studio para la cámara",
    )
    custom_content_box_norm: Optional[List[float]] = Field(
        default=None,
        description="Coordenadas normalizadas [x,y,w,h] seleccionadas en el Studio para el juego/contenido",
    )
    category_rules: Optional[List[CategorySceneRule]] = Field(
        default=None,
        description="Reglas multi-categoría amarradas por escena (categoría -> layout + subtítulos)",
    )
    project_id: Optional[str] = Field(
        default=None,
        description="Identificador de ventana/proyecto independiente",
    )


class NewProjectRequest(BaseModel):
    mode: Literal["reset", "independent"] = Field(
        default="reset",
        description="independent crea una ventana nueva aislada sin detener la actual; reset reinicia el proyecto indicado",
    )
    project_id: Optional[str] = Field(
        default=None,
        description="Identificador del proyecto destino",
    )
    from_project_id: Optional[str] = Field(
        default=None,
        description="Identificador del proyecto origen desde el que se abre la nueva ventana",
    )


class RenameProjectRequest(BaseModel):
    from_project_id: str = Field(..., description="Identificador actual del proyecto en espera")
    video_filename: Optional[str] = Field(
        default=None,
        description="Nombre del video para generar el slug '<Video>_<YYYY-MM-DD>'",
    )
    new_project_id: Optional[str] = Field(
        default=None,
        description="Identificador explícito opcional del proyecto destino",
    )


class SceneDetectRequest(BaseModel):
    source_type: Literal["inbox", "processing", "youtube_url"] = Field(default="inbox")
    video_filename: Optional[str] = Field(default=None, description="Nombre del archivo de video a inspeccionar")
    youtube_url: Optional[str] = Field(default=None, description="Enlace remoto para calibración visual 16:9")
    timestamp_sec: Optional[float] = Field(default=None, ge=0.0)


class LayoutPresetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    layout_mode: str = Field(default="split_streamer")
    cam_box_norm: List[float] = Field(..., min_length=4, max_length=4)
    content_box_norm: List[float] = Field(..., min_length=4, max_length=4)
    cam_overlay_pos: Literal["top_left", "top_right", "bottom_left", "bottom_right"] = "top_right"
    subtitle_preset: str = Field(default="hormozi_pop")
    subtitle_position: Literal["auto", "top", "center", "bottom"] = "auto"


class DiscoverPipelineRequest(BaseModel):
    source_type: Literal["inbox", "youtube_url"] = "inbox"
    video_filename: Optional[str] = None
    youtube_url: Optional[str] = None
    download_section_start: Optional[str] = None
    download_section_end: Optional[str] = None
    shorts_per_video: int = Field(default=12, ge=1, le=24)
    content_category: str = Field(default="auto")
    category_rules: Optional[List[CategorySceneRule]] = Field(default=None)
    auto_categorize_by_topic: bool = Field(default=True)
    allowed_account_categories: Optional[List[str]] = Field(default=None)
    project_id: Optional[str] = Field(default=None)


class RenderSelectedRequest(BaseModel):
    candidate_ids: List[str] = Field(..., min_length=1)
    layout_mode: str = Field(default="auto")
    cam_overlay_pos: Literal["top_left", "top_right", "bottom_left", "bottom_right"] = "top_right"
    custom_cam_box_norm: Optional[List[float]] = None
    custom_content_box_norm: Optional[List[float]] = None
    subtitle_preset: str = Field(default="hormozi_pop")
    subtitle_position: Literal["auto", "top", "center", "bottom"] = "auto"
    bgm_mood: str = Field(default="desactivada")
    auto_upload_to_youtube: bool = Field(default=False)
    category_rules: Optional[List[CategorySceneRule]] = Field(default=None)
    auto_categorize_by_topic: bool = Field(default=True)
    allowed_account_categories: Optional[List[str]] = Field(default=None)
    project_id: Optional[str] = Field(default=None)


class ScheduleBatchRequest(BaseModel):
    youtube_start_time: str = Field(
        ...,
        description="Fecha y hora de programación inicial para YouTube Shorts (YYYY-MM-DDTHH:MM)",
    )
    instagram_start_time: str = Field(
        ...,
        description="Fecha y hora de programación inicial para Instagram Reels (YYYY-MM-DDTHH:MM)",
    )
    tiktok_start_time: str = Field(
        ...,
        description="Fecha y hora de programación inicial para TikTok (YYYY-MM-DDTHH:MM)",
    )
    facebook_start_time: Optional[str] = Field(
        default=None,
        description="Fecha y hora opcional para Facebook Reels (usa Instagram si se omite)",
    )
    interval_minutes: int = Field(
        default=60,
        ge=0,
        le=1440,
        description="Minutos de separación entre cada Short consecutivo",
    )
    auto_upload_positive_to_youtube: bool = Field(
        default=True,
        description="Si es True, sube automáticamente a YouTube los Shorts que aún no tengan ID",
    )
    project_id: Optional[str] = Field(default=None)


class ShortSceneDetectRequest(BaseModel):
    short_rel_path: str = Field(..., min_length=1, description="Ruta relativa del Short dentro de output_shorts")
    timestamp_sec: Optional[float] = Field(default=None, ge=0.0)


class RerenderShortRequest(BaseModel):
    short_rel_path: str = Field(..., min_length=1, description="Ruta relativa del Short dentro de output_shorts")
    layout_mode: LayoutModeLiteral = Field(default="split_streamer")
    cam_overlay_pos: Literal["top_left", "top_right", "bottom_left", "bottom_right"] = Field(
        default="top_right"
    )
    custom_cam_box_norm: Optional[List[float]] = Field(default=None)
    custom_content_box_norm: Optional[List[float]] = Field(default=None)
    subtitle_preset: str = Field(default="hormozi_pop")
    subtitle_position: Literal["auto", "top", "center", "bottom"] = Field(default="auto")
    trim_start_sec: Optional[float] = Field(default=None, ge=0.0)
    trim_end_sec: Optional[float] = Field(default=None, gt=0.0)


class ScheduleSingleShortRequest(BaseModel):
    short_rel_path: str = Field(..., min_length=1, description="Ruta relativa del Short dentro de output_shorts")
    scheduled_time: str = Field(
        ...,
        min_length=10,
        description="Fecha y hora de programación en AST (YYYY-MM-DDTHH:MM o ISO)",
    )
    upload_to_youtube: bool = Field(
        default=True,
        description="Si es True, sube y programa automáticamente en YouTube sin filtro de puntaje",
    )


class UpdateShortCategoriesRequest(BaseModel):
    short_rel_path: str = Field(..., min_length=1)
    account_categories: List[str] = Field(..., min_length=1)


class LiveMonitorStartRequest(BaseModel):
    stream_url: str = Field(..., min_length=1, description="Enlace del directo activo en YouTube, Twitch o Kick")
    profile_id: Optional[int] = Field(default=None, description="ID del Perfil de Contenido a aplicar")
    layout_mode: str = Field(default="auto")
    subtitle_preset: str = Field(default="hormozi_pop")
    chunk_duration_sec: int = Field(default=90, ge=30, le=300)
    overlap_sec: int = Field(default=20, ge=0, le=45)
    min_virality_score: int = Field(default=70, ge=40, le=95)
    max_shorts_total: int = Field(default=12, ge=1, le=50)
    project_id: Optional[str] = Field(default=None)


class VerifyPlatformRequest(BaseModel):
    platform: Literal["youtube", "instagram", "tiktok", "facebook"]


class CreateSocialCategoryRequest(BaseModel):
    label: str = Field(..., min_length=2, max_length=80)
    key: Optional[str] = Field(default=None, max_length=32)
    description: str = Field(default="", max_length=240)
    topic_keywords: List[str] = Field(default_factory=list)


def _get_hub_category_keys() -> List[str]:
    cfg = social_hub.get_raw_social_hub_config(CONFIG_DIR)
    keys = list((cfg.get("categories") or {}).keys())
    return keys or list(social_hub.BUILTIN_CATEGORY_KEYS)


@asynccontextmanager
async def _app_lifespan(_app: FastAPI):
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        _start_social_scheduler_daemon()
    yield


app = FastAPI(
    title="Short YT API — Auto-Clipper Shorts Engine",
    version="1.0.0",
    lifespan=_app_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _schedule_deferred_processing_cleanup(delay_sec: float = 3.0, project_id: str = "default") -> None:
    """Programa una limpieza diferida en segundo plano cuando el visor <video> cierre su conexión HTTP 206."""
    pid = _normalize_project_id(project_id)
    proc_dir = PROCESSING_DIR
    out_dir = _get_project_output_dir(pid)
    arch_dir = PUBLISHED_ARCHIVE_DIR

    def _deferred_run() -> None:
        try:
            state = _get_project_state(pid)
            if state.get("status") in ("STARTED", "RUNNING", "DISCOVERING") or _has_other_active_projects(exclude_project_id=pid):
                return
            if not proc_dir.exists():
                return
            gc.collect()
            skill_cleanup.PROCESSING_DIR = proc_dir
            skill_cleanup.OUTPUT_DIR = out_dir
            skill_cleanup.PUBLISHED_ARCHIVE_DIR = arch_dir
            skill_cleanup.clean_processing_dir(max_age_seconds=0)
        except Exception as deferred_err:
            logger.debug("Aviso en limpieza diferida de processing/: %s", deferred_err)

    timer = threading.Timer(delay_sec, _deferred_run)
    timer.daemon = True
    timer.start()


def _update_pipeline_progress(
    pct: int,
    phase: str,
    detail: str,
    short_update: Optional[Dict[str, Any]] = None,
    project_id: str = "default",
) -> None:
    pid = _normalize_project_id(project_id)
    state = _get_project_state(pid)
    state["progress_percent"] = max(0, min(100, int(pct)))
    state["phase_label"] = phase
    state["step_detail"] = detail
    state["message"] = detail
    state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if short_update:
        if short_update.get("release_source_preview"):
            state["source_preview_url"] = None
        if "filename" in short_update:
            uploads = dict(state.get("short_uploads") or {})
            uploads[short_update["filename"]] = {
                "percent": int(short_update.get("percent", 50)),
                "detail": str(short_update.get("detail", "Procesando subida...")),
            }
            state["short_uploads"] = uploads
    _persist_pipeline_state(pid)


def _run_pipeline_background(
    video_path: Optional[Path],
    overrides: Dict[str, Any],
    youtube_url: Optional[str] = None,
    project_id: str = "default",
) -> None:
    """Ejecuta el pipeline real en un hilo de trabajo actualizando el estado aislado del proyecto."""
    pid = _normalize_project_id(project_id)
    state = _get_project_state(pid)
    cancel_ev = _get_project_cancel_event(pid)
    out_root = _get_project_output_dir(pid)

    def _progress_cb(
        pct: int,
        phase: str,
        detail: str,
        short_update: Optional[Dict[str, Any]] = None,
    ) -> None:
        _update_pipeline_progress(pct, phase, detail, short_update, project_id=pid)

    try:
        import main_daemon

        state["status"] = "RUNNING"
        state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _persist_pipeline_state(pid)

        target_path = video_path
        if youtube_url:
            _progress_cb(
                5,
                "Fase 1/4 · Descarga Stream DASH",
                f"Descargando stream en máxima calidad desde enlace: {youtube_url}",
            )
            if pid == "default":
                target_path = main_daemon.download_youtube_url_max_quality(
                    youtube_url,
                    progress_callback=_progress_cb,
                    download_section_start=overrides.get("download_section_start"),
                    download_section_end=overrides.get("download_section_end"),
                )
            else:
                target_path = main_daemon.download_youtube_url_max_quality(
                    youtube_url,
                    progress_callback=_progress_cb,
                    download_section_start=overrides.get("download_section_start"),
                    download_section_end=overrides.get("download_section_end"),
                    cancel_event=cancel_ev,
                )

        if target_path is None or not target_path.exists():
            raise FileNotFoundError("No se encontró el archivo de video para procesar.")

        state["current_video"] = target_path.name
        state["project_name"] = _main_daemon_bootstrap.build_video_date_project_id(target_path.name)
        state["source_preview_url"] = f"/api/media/source/{quote(target_path.name)}"
        _progress_cb(
            18,
            "Fase 1/4 · Preparación",
            f"Iniciando motor de IA para {target_path.name}...",
        )

        is_external_local = (not bool(youtube_url)) and (
            target_path.parent.resolve() not in (INBOX_DIR.resolve(), PROCESSING_DIR.resolve())
        )
        if (
            pid == "default"
            and not _has_other_active_projects(exclude_project_id="default")
            and not is_external_local
        ):
            main_daemon.process_video_pipeline(
                target_path,
                cli_overrides=overrides,
                progress_callback=_progress_cb,
            )
        else:
            main_daemon.process_video_pipeline(
                target_path,
                cli_overrides=overrides,
                progress_callback=_progress_cb,
                cancel_event=cancel_ev,
                output_shorts_root=out_root,
                allow_global_temp_cleanup=not _has_other_active_projects(exclude_project_id=pid),
                keep_inbox_source=(is_external_local or (pid != "default" and not bool(youtube_url))),
            )

        state["status"] = "COMPLETED"
        state["source_preview_url"] = None
        needs_confirm = bool(overrides.get("enable_social_distribution", False))
        state["requires_schedule_confirmation"] = needs_confirm
        if not needs_confirm:
            state["short_uploads"] = {}
        _progress_cb(
            100,
            "Completado (100%)",
            f"Procesamiento finalizado con éxito para {target_path.name}.",
        )
        _schedule_deferred_processing_cleanup(delay_sec=3.0, project_id=pid)
    except Exception as exc:
        state["source_preview_url"] = None
        if exc.__class__.__name__ == "PipelineCanceledError":
            logger.info("Pipeline [%s] cancelado por el usuario: %s", pid, exc)
            state["status"] = "CANCELED"
            state["phase_label"] = "Proceso Cancelado"
            state["step_detail"] = "Generación de Shorts cancelada por el usuario."
            state["message"] = "Generación de Shorts cancelada por el usuario."
            state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _persist_pipeline_state(pid)
            return
        logger.exception("Error en ejecución de pipeline [%s]: %s", pid, exc)
        state["status"] = "ERROR"
        state["phase_label"] = "Error en el Proceso"
        state["step_detail"] = f"Error en el pipeline: {exc}"
        state["message"] = f"Error en el pipeline: {exc}"
        state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _persist_pipeline_state(pid)


@app.get("/api/inbox")
def get_inbox(project_id: Optional[str] = None) -> Dict[str, Any]:
    """Devuelve los videos en ./inbox_videos/, el espacio en disco y la configuración actual."""
    pid = _normalize_project_id(project_id)
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    videos: List[Dict[str, Any]] = []

    for item in sorted(INBOX_DIR.iterdir()):
        if item.is_file() and item.suffix.lower() in VIDEO_EXTENSIONS:
            stat = item.stat()
            videos.append(
                {
                    "file_name": item.name,
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

    disk_report = skill_cleanup.get_disk_space_report(BASE_DIR)
    settings = load_settings()
    st = dict(_get_project_state(pid))

    return {
        "project_id": pid,
        "project_name": st.get("project_name") or pid,
        "videos": videos,
        "disk_space": disk_report,
        "settings": settings,
        "pipeline_status": st,
    }


@app.post("/api/settings/theme")
def update_theme_mode(req: ThemeSettingsRequest) -> Dict[str, Any]:
    """Persiste el modo de apariencia (light / dark) en ./config/settings.json."""
    updated = load_settings(overrides={"theme_mode": req.theme_mode})
    return {
        "theme_mode": updated.get("theme_mode", req.theme_mode),
        "settings": updated,
    }


def _open_native_video_file_dialog() -> Optional[str]:
    """Abre el selector nativo de archivos de Windows Explorer para elegir un video local."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class _OPENFILENAMEW(ctypes.Structure):
        _fields_ = [
            ("lStructSize", wintypes.DWORD),
            ("hwndOwner", wintypes.HWND),
            ("hInstance", wintypes.HINSTANCE),
            ("lpstrFilter", ctypes.c_void_p),
            ("lpstrCustomFilter", wintypes.LPWSTR),
            ("nMaxCustFilter", wintypes.DWORD),
            ("nFilterIndex", wintypes.DWORD),
            ("lpstrFile", ctypes.c_void_p),
            ("nMaxFile", wintypes.DWORD),
            ("lpstrFileTitle", wintypes.LPWSTR),
            ("nMaxFileTitle", wintypes.DWORD),
            ("lpstrInitialDir", wintypes.LPCWSTR),
            ("lpstrTitle", wintypes.LPCWSTR),
            ("Flags", wintypes.DWORD),
            ("nFileOffset", wintypes.WORD),
            ("nFileExtension", wintypes.WORD),
            ("lpstrDefExt", wintypes.LPCWSTR),
            ("lCustData", wintypes.LPARAM),
            ("lpfnHook", ctypes.c_void_p),
            ("lpTemplateName", wintypes.LPCWSTR),
            ("pvReserved", ctypes.c_void_p),
            ("dwReserved", wintypes.DWORD),
            ("FlagsEx", wintypes.DWORD),
        ]

    filter_spec = (
        "Videos (*.mp4;*.mov;*.mkv;*.avi;*.webm)\0*.mp4;*.mov;*.mkv;*.avi;*.webm\0"
        "Todos los archivos (*.*)\0*.*\0\0"
    )
    filter_buf = ctypes.create_unicode_buffer(filter_spec)
    buf = ctypes.create_unicode_buffer(4096)
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = wintypes.HWND

    ofn = _OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(_OPENFILENAMEW)
    try:
        ofn.hwndOwner = user32.GetForegroundWindow()
    except Exception:
        ofn.hwndOwner = None
    ofn.lpstrFilter = ctypes.addressof(filter_buf)
    ofn.nFilterIndex = 1
    ofn.lpstrFile = ctypes.addressof(buf)
    ofn.nMaxFile = 4096
    ofn.lpstrTitle = "Seleccionar video local — Auto-Clipper Studio"
    initial_dir = (
        _LAST_PICKED_VIDEO_DIR
        if _LAST_PICKED_VIDEO_DIR is not None and _LAST_PICKED_VIDEO_DIR.exists()
        else None
    )
    if initial_dir is not None:
        ofn.lpstrInitialDir = str(initial_dir)
    # OFN_NOCHANGEDIR | OFN_PATHMUSTEXIST | OFN_FILEMUSTEXIST | OFN_EXPLORER
    ofn.Flags = 0x00081808

    com_inited = False
    try:
        try:
            hr = ctypes.windll.ole32.CoInitializeEx(None, 0x2 | 0x4)
            com_inited = hr in (0, 1)
        except Exception:
            com_inited = False
        ok = bool(ctypes.windll.comdlg32.GetOpenFileNameW(ctypes.byref(ofn)))
        return buf.value.strip() if ok and buf.value.strip() else None
    finally:
        if com_inited:
            try:
                ctypes.windll.ole32.CoUninitialize()
            except Exception:
                pass


@app.post("/api/local-video/pick")
def pick_local_video() -> Dict[str, Any]:
    """Abre el Explorador de Windows para elegir cualquier video local y lo registra de forma segura."""
    global _LAST_PICKED_VIDEO_DIR
    selected_raw = _open_native_video_file_dialog()
    if not selected_raw:
        return {
            "cancelled": True,
            "file_path": None,
            "file_name": None,
            "size_mb": None,
        }

    try:
        resolved = register_local_video_path(Path(selected_raw))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _LAST_PICKED_VIDEO_DIR = resolved.parent
    size_mb = round(win_long_path(resolved).stat().st_size / (1024 * 1024), 2)
    return {
        "cancelled": False,
        "file_path": str(resolved),
        "file_name": resolved.name,
        "size_mb": size_mb,
    }


@app.post("/api/local-video/upload")
async def upload_local_video(request: Request) -> Dict[str, Any]:
    """Recibe un video local elegido desde el Explorador nativo del navegador por streaming sin saturar RAM."""
    raw_name = unquote(
        request.headers.get("x-file-name") or request.query_params.get("filename") or ""
    ).strip()
    orig_name = Path(raw_name.replace("\\", "/")).name.strip()
    if not orig_name:
        raise HTTPException(status_code=400, detail="Debes indicar el nombre del archivo de video.")

    ext = Path(orig_name).suffix.lower()
    if ext not in VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato no soportado ({ext or 'sin extensión'}). Usa MP4, MOV, MKV, AVI o WEBM.",
        )

    safe_stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", Path(orig_name).stem).strip(" ._")[:80]
    if not safe_stem:
        safe_stem = "video_local"
    dest_name = f"{safe_stem}{ext}"

    picks_dir = _get_local_picks_dir()
    picks_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = picks_dir / f".tmp_{uuid.uuid4().hex[:8]}_{dest_name}"
    dest_path = picks_dir / dest_name

    bytes_written = 0
    try:
        with win_long_path(tmp_path).open("wb") as out_fp:
            async for chunk in request.stream():
                if chunk:
                    out_fp.write(chunk)
                    bytes_written += len(chunk)
    except Exception as exc:
        try:
            win_long_path(tmp_path).unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(
            status_code=500,
            detail=f"Error al guardar el video seleccionado: {exc}",
        ) from exc

    if bytes_written == 0:
        try:
            win_long_path(tmp_path).unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(status_code=400, detail="El archivo de video seleccionado está vacío.")

    final_path = dest_path
    try:
        os.replace(str(win_long_path(tmp_path)), str(win_long_path(dest_path)))
    except OSError:
        final_path = picks_dir / f"{safe_stem}_{uuid.uuid4().hex[:6]}{ext}"
        os.replace(str(win_long_path(tmp_path)), str(win_long_path(final_path)))

    _prune_local_picks_dir(keep_latest=4, protected_paths={final_path.resolve()})
    resolved = register_local_video_path(final_path)
    return {
        "cancelled": False,
        "file_path": str(resolved),
        "file_name": resolved.name,
        "size_mb": round(bytes_written / (1024 * 1024), 2),
    }


@app.post("/api/inspect")
def inspect_video(req: InspectRequest) -> Dict[str, Any]:
    """Ejecuta estimate_video_potential sobre el video local seleccionado (inbox o Explorador)."""
    candidate_path = _resolve_local_video_path(req.video_filename, allow_processing=False)

    if candidate_path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato no soportado ({candidate_path.suffix}). Usa MP4, MOV, MKV, AVI o WEBM.",
        )

    try:
        report = inbox_inspector.estimate_video_potential(candidate_path)
        return report
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo inspeccionar el video: {exc}") from exc


_REMOTE_VIDEO_URL_RE = re.compile(
    r"^https?://(www\.|m\.|clips\.)?(youtube\.com|youtu\.be|twitch\.tv|kick\.com)/.+",
    re.IGNORECASE,
)


_REMOTE_METADATA_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_REMOTE_METADATA_CACHE_TTL_SEC = 600.0


def _pick_best_seekable_stream_url(info: Dict[str, Any]) -> Tuple[Optional[str], Dict[str, str]]:
    """Selecciona la mejor URL de stream MP4/WebM directa compatible con seek rápido por rango HTTP (-ss)."""
    raw_formats = info.get("formats") or []
    candidates: List[Tuple[int, str, Dict[str, str]]] = []
    if isinstance(raw_formats, list):
        for fmt in raw_formats:
            if not isinstance(fmt, dict):
                continue
            url = str(fmt.get("url") or "").strip()
            if not url.startswith(("http://", "https://")):
                continue
            proto = str(fmt.get("protocol") or "").lower()
            vcodec = str(fmt.get("vcodec") or "").lower()
            if not vcodec or vcodec == "none":
                continue
            if "m3u8" in proto or ".m3u8" in url.lower() or "dash_segments" in proto:
                continue
            height = int(fmt.get("height") or 0)
            ext = str(fmt.get("ext") or "").lower()
            if height <= 0:
                score = 50
            elif 360 <= height <= 720:
                score = 1000 + height
            elif height <= 1080:
                score = 700 + (1080 - height) // 10
            else:
                score = 200
            if ext == "mp4" or vcodec.startswith("avc"):
                score += 300
            hdrs_raw = fmt.get("http_headers") or info.get("http_headers") or {}
            hdrs = (
                {str(k): str(v) for k, v in hdrs_raw.items() if v is not None}
                if isinstance(hdrs_raw, dict)
                else {}
            )
            candidates.append((score, url, hdrs))

    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        _, best_url, best_hdrs = candidates[0]
        return best_url, best_hdrs

    req_fmts = info.get("requested_formats")
    if isinstance(req_fmts, list):
        for fmt in req_fmts:
            if isinstance(fmt, dict) and str(fmt.get("vcodec") or "").lower() != "none":
                url = str(fmt.get("url") or "").strip()
                if url.startswith(("http://", "https://")):
                    hdrs_raw = fmt.get("http_headers") or info.get("http_headers") or {}
                    hdrs = (
                        {str(k): str(v) for k, v in hdrs_raw.items() if v is not None}
                        if isinstance(hdrs_raw, dict)
                        else {}
                    )
                    return url, hdrs

    direct_url = str(info.get("url") or "").strip()
    if direct_url.startswith(("http://", "https://")):
        hdrs_raw = info.get("http_headers") or {}
        hdrs = (
            {str(k): str(v) for k, v in hdrs_raw.items() if v is not None}
            if isinstance(hdrs_raw, dict)
            else {}
        )
        return direct_url, hdrs
    return None, {}


def _fetch_remote_url_metadata(raw_url: str) -> Dict[str, Any]:
    """Obtiene metadatos rápidos (título, tags, categoría, live, duración, stream_url) sin descargar video."""
    now = time.time()
    cached = _REMOTE_METADATA_CACHE.get(raw_url)
    if cached is not None and (now - cached[0]) < _REMOTE_METADATA_CACHE_TTL_SEC:
        return dict(cached[1])

    try:
        import yt_dlp

        ydl_opts = {
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 6,
            "extract_flat": "in_playlist",
            "js_runtimes": {"node": {}},
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(raw_url, download=False)
        if isinstance(info, dict):
            stream_url, http_headers = _pick_best_seekable_stream_url(info)
            result = {
                "title": str(info.get("title") or ""),
                "description": str(info.get("description") or "")[:600],
                "tags": [str(t) for t in (info.get("tags") or [])[:15]],
                "categories": [str(c) for c in (info.get("categories") or [])[:5]],
                "duration": info.get("duration"),
                "is_live": bool(info.get("is_live") or info.get("was_live")),
                "thumbnail": info.get("thumbnail"),
                "uploader": str(info.get("uploader") or info.get("channel") or ""),
                "stream_url": stream_url,
                "http_headers": http_headers,
            }
            _REMOTE_METADATA_CACHE[raw_url] = (now, dict(result))
            return result
    except Exception as exc:
        logger.info("Pre-análisis metadata fallback para %s: %s", raw_url, exc)
    return {
        "title": "",
        "description": "",
        "tags": [],
        "categories": [],
        "duration": None,
        "is_live": False,
        "thumbnail": None,
        "uploader": "",
        "stream_url": None,
        "http_headers": {},
    }


def _make_category_rule(
    rule_id: str,
    category: str,
    share_pct: int,
    *,
    scene_label: Optional[str] = None,
    layout_mode: Optional[str] = None,
    subtitle_preset: Optional[str] = None,
    subtitle_position: Optional[str] = None,
    cam_overlay_pos: str = "top_right",
    cam_box_norm: Optional[List[float]] = None,
    content_box_norm: Optional[List[float]] = None,
    frame_url: Optional[str] = None,
    sample_timestamp_sec: Optional[float] = None,
) -> Dict[str, Any]:
    defaults = _main_daemon_bootstrap.CATEGORY_SCENE_DEFAULTS.get(
        category,
        {
            "scene_label": "Escena Principal",
            "layout_mode": "fullscreen",
            "subtitle_preset": "hormozi_pop",
            "subtitle_position": "bottom",
        },
    )
    return {
        "rule_id": rule_id,
        "category": category,
        "scene_label": scene_label or defaults["scene_label"],
        "detected_share_pct": max(0, min(100, int(share_pct))),
        "layout_mode": layout_mode or defaults["layout_mode"],
        "subtitle_preset": subtitle_preset or defaults["subtitle_preset"],
        "subtitle_position": subtitle_position or defaults["subtitle_position"],
        "cam_overlay_pos": cam_overlay_pos,
        "custom_cam_box_norm": list(cam_box_norm) if cam_box_norm is not None else None,
        "custom_content_box_norm": list(content_box_norm) if content_box_norm is not None else None,
        "custom_boxes_manual": False,
        "frame_url": frame_url,
        "sample_timestamp_sec": sample_timestamp_sec,
    }


_STOP_KEYWORDS = {
    "live",
    "directo",
    "stream",
    "video",
    "videos",
    "oficial",
    "official",
    "completo",
    "full",
    "cap",
    "capitulo",
    "mp4",
    "mov",
    "mkv",
    "webm",
    "avi",
    "1080p",
    "720p",
    "60fps",
    "en",
    "el",
    "la",
    "los",
    "las",
    "de",
    "del",
    "con",
    "para",
    "por",
    "and",
    "the",
}


def _normalize_match_text(raw: str) -> Tuple[str, str]:
    """Normaliza un texto sin tildes ni mayúsculas: retorna (espaciado, compacto_alfanum)."""
    decomposed = unicodedata.normalize("NFKD", str(raw or ""))
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()
    spaced = re.sub(r"[^a-z0-9]+", " ", ascii_only).strip()
    compact = re.sub(r"[^a-z0-9]+", "", ascii_only)
    return spaced, compact


def _init_content_profiles_db() -> None:
    """Inicializa la tabla de perfiles de contenido reutilizables en SQLite (limpia, sin mock data)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS content_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                match_keywords TEXT NOT NULL,
                scenes_json TEXT NOT NULL,
                routing_config_json TEXT NOT NULL DEFAULT '{}',
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            )
            """
        )
        cols = {
            str(r[1])
            for r in conn.execute("PRAGMA table_info(content_profiles)").fetchall()
        }
        if "routing_config_json" not in cols:
            conn.execute(
                "ALTER TABLE content_profiles ADD COLUMN routing_config_json TEXT NOT NULL DEFAULT '{}'"
            )
        conn.commit()


def _sanitize_profile_keywords(keywords: List[str], name: str) -> List[str]:
    """Limpia y deduplica pistas de auto-detección; si llegan vacías, las deriva del nombre."""
    cleaned: List[str] = []
    seen: set[str] = set()
    for raw_kw in keywords:
        spaced, compact = _normalize_match_text(raw_kw)
        if len(compact) < 2:
            continue
        if spaced not in seen:
            seen.add(spaced)
            cleaned.append(spaced)

    if not cleaned:
        name_spaced, name_compact = _normalize_match_text(name)
        if len(name_compact) >= 2 and name_spaced not in seen:
            seen.add(name_spaced)
            cleaned.append(name_spaced)
        for tok in name_spaced.split():
            if len(tok) >= 3 and tok not in _STOP_KEYWORDS and tok not in seen:
                seen.add(tok)
                cleaned.append(tok)
    return cleaned[:10]


def _sanitize_profile_scenes_for_storage(scenes: List[CategorySceneRule]) -> List[Dict[str, Any]]:
    """Prepara escenas reutilizables eliminando URLs temporales y preservando cajas manuales válidas."""
    cleaned: List[Dict[str, Any]] = []
    for idx, sc in enumerate(scenes[:4], start=1):
        d = sc.model_dump()
        layout_mode = str(d.get("layout_mode") or "auto").strip().lower()
        manual_boxes = bool(d.get("custom_boxes_manual", False))
        keep_boxes = manual_boxes and (layout_mode in _main_daemon_bootstrap.DUAL_BOX_LAYOUTS)
        cleaned.append(
            {
                "rule_id": str(d.get("rule_id") or f"scene_{idx}"),
                "category": str(d.get("category") or "auto"),
                "scene_label": str(d.get("scene_label") or f"Escena {idx}").strip()[:120],
                "detected_share_pct": max(0, min(100, int(d.get("detected_share_pct", 50)))),
                "layout_mode": layout_mode,
                "subtitle_preset": str(d.get("subtitle_preset") or "hormozi_pop"),
                "subtitle_position": str(d.get("subtitle_position") or "auto"),
                "cam_overlay_pos": str(d.get("cam_overlay_pos") or "top_right"),
                "custom_cam_box_norm": (
                    list(d["custom_cam_box_norm"])
                    if keep_boxes and d.get("custom_cam_box_norm") is not None
                    else None
                ),
                "custom_content_box_norm": (
                    list(d["custom_content_box_norm"])
                    if keep_boxes and d.get("custom_content_box_norm") is not None
                    else None
                ),
                "custom_boxes_manual": keep_boxes,
                "frame_url": None,
                "sample_timestamp_sec": None,
            }
        )
    return cleaned


def _row_to_content_profile(row: sqlite3.Row) -> Dict[str, Any]:
    raw_routing = {}
    if "routing_config_json" in row.keys() and row["routing_config_json"]:
        try:
            raw_routing = json.loads(row["routing_config_json"])
        except Exception:
            raw_routing = {}
    valid_keys = _get_hub_category_keys()
    allowed_cats = social_hub.normalize_account_categories(
        raw_routing.get("allowed_account_categories"),
        fallback=valid_keys,
        valid_keys=valid_keys,
    )
    return {
        "id": int(row["id"]),
        "name": str(row["name"]),
        "match_keywords": json.loads(row["match_keywords"] or "[]"),
        "scenes": json.loads(row["scenes_json"] or "[]"),
        "auto_categorize_by_topic": bool(raw_routing.get("auto_categorize_by_topic", True)),
        "allowed_account_categories": allowed_cats,
        "created_at_utc": str(row["created_at_utc"]),
        "updated_at_utc": str(row["updated_at_utc"]),
    }


def _list_content_profiles_from_db() -> List[Dict[str, Any]]:
    _init_content_profiles_db()
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM content_profiles ORDER BY updated_at_utc DESC, id DESC"
        ).fetchall()
    return [_row_to_content_profile(r) for r in rows]


def _match_content_profile(text_parts: List[str]) -> Optional[Dict[str, Any]]:
    """Busca el perfil guardado que mejor coincide con canal, título o archivo normalizados."""
    hay_spaced, hay_compact = _normalize_match_text(" ".join(text_parts))
    if not hay_spaced:
        return None

    best_profile: Optional[Dict[str, Any]] = None
    best_score = 0
    for profile in _list_content_profiles_from_db():
        keywords = profile.get("match_keywords") or []
        hits = 0
        score = 0
        for raw_kw in keywords:
            kw_spaced, kw_compact = _normalize_match_text(str(raw_kw))
            if len(kw_compact) < 2:
                continue
            word_hit = bool(re.search(rf"(?<!\w){re.escape(kw_spaced)}(?!\w)", hay_spaced))
            compact_hit = len(kw_compact) >= 4 and kw_compact in hay_compact
            if word_hit or compact_hit:
                hits += 1
                score += 30 + len(kw_compact)

        name_spaced, name_compact = _normalize_match_text(str(profile.get("name") or ""))
        if len(name_compact) >= 4:
            name_hit = bool(re.search(rf"(?<!\w){re.escape(name_spaced)}(?!\w)", hay_spaced)) or (
                name_compact in hay_compact
            )
            if name_hit:
                hits += 1
                score += 50 + len(name_compact)

        if hits > 0:
            if keywords and hits >= len(keywords):
                score += 25
            if score > best_score:
                best_score = score
                best_profile = profile
    return best_profile


def _suggest_profile_identity(uploader: str, title_or_stem: str) -> Tuple[str, List[str]]:
    """Propone nombre y pistas iniciales cuando entra un contenido sin perfil guardado."""
    clean_uploader = str(uploader or "").strip()
    clean_title = re.sub(r"[_\-]+", " ", str(title_or_stem or "")).strip()
    suggested_name = (clean_uploader or clean_title or "Nuevo Contenido")[:80]
    seed_spaced, seed_compact = _normalize_match_text(clean_uploader or clean_title)
    kw_list: List[str] = []
    if len(seed_compact) >= 4:
        if " " in seed_spaced and len(seed_compact) <= 24:
            kw_list.append(seed_compact)
        elif seed_spaced:
            kw_list.append(seed_spaced)
    for tok in seed_spaced.split():
        if len(tok) >= 3 and tok not in _STOP_KEYWORDS and tok not in kw_list:
            kw_list.append(tok)
        if len(kw_list) >= 4:
            break
    if not kw_list and seed_spaced:
        kw_list.append(seed_spaced)
    return suggested_name, kw_list


def _infer_category_from_text_blob(blob: str) -> str:
    txt = (blob or "").lower()
    if any(k in txt for k in ("reality", "gran hermano", "tertulia", "convivencia", "confesionario", "la casa")):
        return "realitys"
    if any(
        k in txt
        for k in (
            "gaming",
            "videojuego",
            "gameplay",
            "zelda",
            "warzone",
            "fortnite",
            "valorant",
            "minecraft",
            "gta",
            "fifa",
            "elden",
            "jugando",
            "twitch.tv",
            "kick.com",
        )
    ):
        return "videojuegos"
    if any(k in txt for k in ("podcast", "entrevista", "episodio", "mesa redonda", "charlando con")):
        return "podcast"
    if any(k in txt for k in ("reaccion", "reacción", "react", "reaccionando")):
        return "reacciones"
    if any(k in txt for k in ("tutorial", "como hacer", "cómo ", "curso", "aprende", "curiosidad")):
        return "tutorial_curiosidad"
    if any(k in txt for k in ("storytime", "anécdota", "anecdota", "lo que me pasó")):
        return "storytime_anecdota"
    return "opinion_monologo"


def _pre_analyze_remote_url(raw_url: str) -> Dict[str, Any]:
    meta = _fetch_remote_url_metadata(raw_url)
    title = str(meta.get("title") or "")
    uploader = str(meta.get("uploader") or "")
    suggested_name, suggested_kw = _suggest_profile_identity(uploader, title or raw_url)
    matched_profile = _match_content_profile(
        [uploader, title, raw_url, " ".join(meta.get("tags") or [])]
    )

    display_title = title.strip() or raw_url
    if matched_profile is not None:
        hydrated_rules: List[Dict[str, Any]] = []
        for idx, raw_scene in enumerate(matched_profile.get("scenes") or [], start=1):
            sc = dict(raw_scene)
            sc.setdefault("rule_id", f"scene_{idx}")
            sc.setdefault("category", "auto")
            if not sc.get("frame_url") and meta.get("thumbnail"):
                sc["frame_url"] = meta.get("thumbnail")
            hydrated_rules.append(sc)
        return {
            "source_type": "youtube_url",
            "target": display_title,
            "video_title": title.strip() or None,
            "duration_sec": float(meta["duration"]) if meta.get("duration") else None,
            "thumbnail_url": meta.get("thumbnail"),
            "matched_profile_id": matched_profile["id"],
            "matched_profile_name": matched_profile["name"],
            "suggested_profile_name": matched_profile["name"],
            "suggested_keywords": matched_profile["match_keywords"],
            "auto_categorize_by_topic": bool(matched_profile.get("auto_categorize_by_topic", True)),
            "allowed_account_categories": list(
                matched_profile.get("allowed_account_categories")
                or _get_hub_category_keys()
            ),
            "is_hybrid_multicategory": len(hydrated_rules) >= 2,
            "analysis_mode": "matched_profile",
            "analysis_summary": (
                f"Perfil reconocido automáticamente: '{matched_profile['name']}' "
                f"({len(hydrated_rules)} escena(s) guardada(s))."
            ),
            "category_rules": hydrated_rules,
        }

    blob = " ".join(
        [
            raw_url,
            title,
            str(meta.get("description") or ""),
            " ".join(meta.get("tags") or []),
            " ".join(meta.get("categories") or []),
            uploader,
        ]
    ).lower()
    inferred = _infer_category_from_text_blob(blob)
    is_live_stream = bool(meta.get("is_live")) or any(
        k in blob for k in ("live", "directo", "stream", "twitch.tv", "kick.com")
    )

    rules: List[Dict[str, Any]] = []
    if inferred == "videojuegos" or is_live_stream:
        rules.append(_make_category_rule("rule_1", "videojuegos", 65, scene_label="Gameplay + Cámara"))
        rules.append(
            _make_category_rule(
                "rule_2",
                "opinion_monologo",
                35,
                scene_label="Charla Full Cam / Chat",
                layout_mode="fullscreen",
                subtitle_preset="hormozi_pop",
                subtitle_position="bottom",
            )
        )
    elif inferred == "realitys":
        rules.append(_make_category_rule("rule_1", "realitys", 65, scene_label="Sala Multicam / Reality"))
        rules.append(
            _make_category_rule(
                "rule_2",
                "opinion_monologo",
                35,
                scene_label="Confesionario / Plano Individual",
                layout_mode="fullscreen",
                subtitle_preset="hormozi_pop",
                subtitle_position="bottom",
            )
        )
    elif inferred == "podcast":
        rules.append(_make_category_rule("rule_1", "podcast", 70, scene_label="Podcast / 2 Hablantes"))
        rules.append(
            _make_category_rule(
                "rule_2",
                "opinion_monologo",
                30,
                scene_label="Close-Up Individual Full Cam",
                layout_mode="fullscreen",
                subtitle_preset="hormozi_pop",
                subtitle_position="bottom",
            )
        )
    elif inferred == "reacciones":
        rules.append(_make_category_rule("rule_1", "reacciones", 70, scene_label="Reacción Picture-in-Picture"))
        rules.append(
            _make_category_rule(
                "rule_2",
                "opinion_monologo",
                30,
                scene_label="Comentario Full Cam",
                layout_mode="fullscreen",
                subtitle_preset="hormozi_pop",
                subtitle_position="bottom",
            )
        )
    elif inferred == "tutorial_curiosidad":
        rules.append(_make_category_rule("rule_1", "tutorial_curiosidad", 65, scene_label="Tutorial / Explicación Visual"))
        rules.append(
            _make_category_rule(
                "rule_2",
                "opinion_monologo",
                35,
                scene_label="Gancho / Conclusión Full Cam",
                layout_mode="fullscreen",
                subtitle_preset="hormozi_pop",
                subtitle_position="bottom",
            )
        )
    else:
        primary_cat = inferred if inferred != "auto" else "opinion_monologo"
        rules.append(_make_category_rule("rule_1", primary_cat, 75, scene_label="Monólogo / Cámara Principal"))
        rules.append(
            _make_category_rule(
                "rule_2",
                "reacciones",
                25,
                scene_label="Corte Complementario PiP",
                layout_mode="reaction_pip",
                subtitle_preset="hormozi_pop",
                subtitle_position="center",
            )
        )

    raw_dur = meta.get("duration")
    dur_val = float(raw_dur) if isinstance(raw_dur, (int, float)) and raw_dur > 0 else 0.0
    if dur_val > 10.0:
        sample_ts_1 = round(min(max(30.0, dur_val * 0.22), max(0.0, dur_val - 5.0)), 1)
        sample_ts_2 = round(min(max(60.0, dur_val * 0.58), max(0.0, dur_val - 5.0)), 1)
        if len(rules) >= 1 and rules[0].get("sample_timestamp_sec") is None:
            rules[0]["sample_timestamp_sec"] = sample_ts_1
        if len(rules) >= 2 and rules[1].get("sample_timestamp_sec") is None:
            rules[1]["sample_timestamp_sec"] = sample_ts_2

    return {
        "source_type": "youtube_url",
        "target": display_title,
        "video_title": title.strip() or None,
        "duration_sec": dur_val if dur_val > 0 else None,
        "thumbnail_url": meta.get("thumbnail"),
        "matched_profile_id": None,
        "matched_profile_name": None,
        "suggested_profile_name": suggested_name,
        "suggested_keywords": suggested_kw,
        "auto_categorize_by_topic": True,
        "allowed_account_categories": _get_hub_category_keys(),
        "is_hybrid_multicategory": len(rules) >= 2,
        "analysis_mode": "remote_metadata",
        "analysis_summary": (
            f"Contenido nuevo ({' + '.join(r['scene_label'] for r in rules)}). "
            "Ajusta sus escenas y guárdalo como Perfil de Contenido para futuros videos."
        ),
        "category_rules": rules,
    }


def _pre_analyze_local_video(video_path: Path) -> Dict[str, Any]:
    cap = cv2.VideoCapture(str(video_path))
    duration_sec = 0.0
    if cap.isOpened():
        try:
            fps = float(cap.get(cv2.CAP_PROP_FPS)) or 30.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
            duration_sec = float(total_frames) / max(1.0, fps)
        finally:
            cap.release()

    suggested_name, suggested_kw = _suggest_profile_identity("", video_path.stem)
    matched_profile = _match_content_profile([video_path.stem.replace("_", " "), video_path.name])
    if matched_profile is not None:
        sample_ts = round(duration_sec * 0.25, 2) if duration_sec >= 2.0 else 0.0
        sample_det = _extract_scene_frame_and_boxes(video_path, timestamp_sec=sample_ts, frame_tag="pre_0")
        sample_frame_url = sample_det.get("frame_url")
        hydrated_rules: List[Dict[str, Any]] = []
        for idx, raw_scene in enumerate(matched_profile.get("scenes") or [], start=1):
            sc = dict(raw_scene)
            sc.setdefault("rule_id", f"scene_{idx}")
            sc.setdefault("category", "auto")
            sc["frame_url"] = sample_frame_url
            sc["sample_timestamp_sec"] = sample_ts
            hydrated_rules.append(sc)
        return {
            "source_type": "inbox",
            "target": video_path.name,
            "video_title": video_path.name,
            "duration_sec": round(duration_sec, 2) if duration_sec > 0 else None,
            "thumbnail_url": sample_frame_url,
            "matched_profile_id": matched_profile["id"],
            "matched_profile_name": matched_profile["name"],
            "suggested_profile_name": matched_profile["name"],
            "suggested_keywords": matched_profile["match_keywords"],
            "auto_categorize_by_topic": bool(matched_profile.get("auto_categorize_by_topic", True)),
            "allowed_account_categories": list(
                matched_profile.get("allowed_account_categories")
                or _get_hub_category_keys()
            ),
            "is_hybrid_multicategory": len(hydrated_rules) >= 2,
            "analysis_mode": "matched_profile",
            "analysis_summary": (
                f"Perfil reconocido automáticamente para '{video_path.name}': "
                f"'{matched_profile['name']}' ({len(hydrated_rules)} escena(s))."
            ),
            "category_rules": hydrated_rules,
        }

    if duration_sec >= 8.0:
        sample_times = [round(duration_sec * r, 2) for r in (0.15, 0.42, 0.68, 0.86)]
    else:
        sample_times = [max(0.0, round(duration_sec * 0.25, 2))]

    stem_cat_hint = _infer_category_from_text_blob(video_path.stem.replace("_", " "))
    name_is_hybrid = any(
        k in video_path.stem.lower()
        for k in ("live", "stream", "directo", "gameplay", "twitch", "kick", "zelda", "warzone", "podcast", "reality")
    )

    bucket_samples: Dict[str, List[Dict[str, Any]]] = {}
    for idx, ts in enumerate(sample_times):
        det = _extract_scene_frame_and_boxes(video_path, timestamp_sec=ts, frame_tag=f"pre_{idx}")
        det_layout = str(det.get("detected_layout") or "fullscreen").lower()
        if det_layout in _main_daemon_bootstrap.DUAL_SPEAKER_LAYOUTS:
            bucket = "podcast"
        elif det_layout == "reality_multicam":
            bucket = "realitys"
        elif det_layout == "reaction_pip":
            bucket = "reacciones"
        elif det_layout in _main_daemon_bootstrap.PIP_GAMEPLAY_LAYOUTS:
            bucket = "videojuegos" if stem_cat_hint not in ("reacciones", "tutorial_curiosidad") else stem_cat_hint
        else:
            bucket = "storytime_anecdota" if stem_cat_hint == "storytime_anecdota" else "opinion_monologo"

        det["sample_timestamp_sec"] = ts
        bucket_samples.setdefault(bucket, []).append(det)

    total_samples = max(1, len(sample_times))
    rules: List[Dict[str, Any]] = []
    ordered_buckets = sorted(bucket_samples.items(), key=lambda kv: len(kv[1]), reverse=True)
    for idx, (cat_key, items) in enumerate(ordered_buckets):
        rep = items[0]
        share = max(10, int(round((len(items) / total_samples) * 100)))
        det_layout = str(rep.get("detected_layout") or "")
        default_layout = _main_daemon_bootstrap.CATEGORY_SCENE_DEFAULTS.get(cat_key, {}).get("layout_mode", "fullscreen")
        chosen_layout = (
            det_layout
            if (cat_key in ("videojuegos", "podcast", "realitys", "reacciones") and det_layout not in ("", "auto"))
            else default_layout
        )
        rules.append(
            _make_category_rule(
                f"rule_{idx + 1}",
                cat_key,
                share,
                layout_mode=chosen_layout,
                cam_box_norm=rep.get("cam_box_norm"),
                content_box_norm=rep.get("content_box_norm"),
                frame_url=rep.get("frame_url"),
                sample_timestamp_sec=rep.get("sample_timestamp_sec"),
            )
        )

    if len(rules) == 1 and (name_is_hybrid or stem_cat_hint in ("videojuegos", "realitys", "podcast", "reacciones")):
        sole_cat = rules[0]["category"]
        if sole_cat == "opinion_monologo" and stem_cat_hint != "opinion_monologo":
            rules[0]["detected_share_pct"] = 40
            rules.insert(
                0,
                _make_category_rule(
                    "rule_hybrid",
                    stem_cat_hint,
                    60,
                    cam_box_norm=rules[0].get("custom_cam_box_norm"),
                    content_box_norm=rules[0].get("custom_content_box_norm"),
                    frame_url=rules[0].get("frame_url"),
                    sample_timestamp_sec=rules[0].get("sample_timestamp_sec"),
                ),
            )
        elif sole_cat in ("videojuegos", "realitys", "podcast", "reacciones"):
            rules[0]["detected_share_pct"] = 70
            rules.append(
                _make_category_rule(
                    "rule_cam",
                    "opinion_monologo",
                    30,
                    scene_label="Charla Full Cam / Primer Plano",
                    layout_mode="fullscreen",
                    subtitle_preset="hormozi_pop",
                    subtitle_position="bottom",
                    frame_url=rules[0].get("frame_url"),
                    sample_timestamp_sec=rules[0].get("sample_timestamp_sec"),
                )
            )

    for i, r in enumerate(rules, start=1):
        r["rule_id"] = f"rule_{i}"

    return {
        "source_type": "inbox",
        "target": video_path.name,
        "video_title": video_path.name,
        "duration_sec": round(duration_sec, 2) if duration_sec > 0 else None,
        "thumbnail_url": rules[0].get("frame_url") if rules else None,
        "matched_profile_id": None,
        "matched_profile_name": None,
        "suggested_profile_name": suggested_name,
        "suggested_keywords": suggested_kw,
        "auto_categorize_by_topic": True,
        "allowed_account_categories": _get_hub_category_keys(),
        "is_hybrid_multicategory": len(rules) >= 2,
        "analysis_mode": "local_multiframe",
        "analysis_summary": (
            f"Muestreo visual en {len(sample_times)} puntos de '{video_path.name}': "
            f"{' + '.join(r['scene_label'] for r in rules)}."
        ),
        "category_rules": rules,
    }


@app.post("/api/pipeline/pre-analyze")
def pre_analyze_pipeline(req: PreAnalyzeRequest) -> Dict[str, Any]:
    """
    Pre-análisis rápido (< 5s) previo al modal flotante: detecta múltiples categorías
    y propone reglas amarradas Categoría -> Layout + Subtítulos antes de editar Shorts.
    """
    if req.source_type == "youtube_url":
        raw_url = (req.youtube_url or "").strip()
        if not raw_url or not _REMOTE_VIDEO_URL_RE.match(raw_url):
            raise HTTPException(
                status_code=400,
                detail="Debes proporcionar un enlace válido de YouTube (youtube.com o youtu.be), Twitch o Kick.",
            )
        return _pre_analyze_remote_url(raw_url)

    raw_file = (req.video_filename or "").strip()
    if not raw_file:
        raise HTTPException(
            status_code=400,
            detail="Debes seleccionar un archivo de video local mediante el botón Archivo Local.",
        )
    candidate = _resolve_local_video_path(raw_file, allow_processing=False)
    return _pre_analyze_local_video(candidate)


@app.post("/api/pipeline/process")
def start_pipeline_process(req: PipelineProcessRequest) -> Dict[str, Any]:
    """Valida los parámetros de entrada, actualiza settings.json y lanza el procesamiento real."""
    pid = _normalize_project_id(req.project_id)
    state = _get_project_state(pid)
    cancel_ev = _get_project_cancel_event(pid)

    target_video_path: Optional[Path] = None
    yt_url: Optional[str] = None

    if req.source_type == "youtube_url":
        raw_url = (req.youtube_url or "").strip()
        if not raw_url or not _REMOTE_VIDEO_URL_RE.match(raw_url):
            raise HTTPException(
                status_code=400,
                detail="Debes proporcionar un enlace válido de YouTube (youtube.com o youtu.be), Twitch o Kick.",
            )
        yt_url = raw_url
    else:
        raw_file = (req.video_filename or "").strip()
        if not raw_file:
            raise HTTPException(
                status_code=400,
                detail="Debes seleccionar un archivo de video local mediante el botón Archivo Local.",
            )
        target_video_path = _resolve_local_video_path(raw_file, allow_processing=False)

    enable_bgm = False
    effective_mood = req.bgm_mood

    serialized_rules = [r.model_dump() for r in req.category_rules] if req.category_rules else None

    overrides = {
        "shorts_per_video": req.shorts_per_video,
        "content_category": req.content_category,
        "layout_mode": req.layout_mode,
        "enable_bgm": enable_bgm,
        "default_bgm_mood": effective_mood,
        "auto_upload_to_youtube": False,
        "enable_social_distribution": req.enable_social_distribution,
        "download_section_start": (req.download_section_start or "").strip() or None,
        "download_section_end": (req.download_section_end or "").strip() or None,
        "subtitle_preset": req.subtitle_preset,
        "subtitle_position": req.subtitle_position,
        "cam_overlay_pos": req.cam_overlay_pos,
        "custom_cam_box_norm": req.custom_cam_box_norm,
        "custom_content_box_norm": req.custom_content_box_norm,
        "category_rules": serialized_rules,
        "auto_categorize_by_topic": req.auto_categorize_by_topic,
        "allowed_account_categories": (
            social_hub.normalize_account_categories(
                req.allowed_account_categories,
                fallback=_get_hub_category_keys(),
                valid_keys=_get_hub_category_keys(),
            )
            if req.allowed_account_categories
            else _get_hub_category_keys()
        ),
    }
    applied_settings = load_settings(overrides)

    try:
        cancel_ev.clear()
    except Exception:
        pass

    # Limpiar Shorts anteriores del proyecto activo y temporales si no hay otro proyecto trabajando
    preserved_caches: Dict[Path, str] = {}
    other_active = _has_other_active_projects(exclude_project_id=pid)
    if not other_active and INBOX_DIR.exists() and PROCESSING_DIR.exists():
        active_sizes = {
            p.stat().st_size
            for p in INBOX_DIR.iterdir()
            if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
        }
        for sz in active_sizes:
            cache_f = PROCESSING_DIR / f".transcript_cache_{sz}.json"
            if cache_f.exists() and cache_f.is_file():
                try:
                    preserved_caches[cache_f] = cache_f.read_text(encoding="utf-8")
                except Exception:
                    pass

    cancel_all_rendered_shorts(project_id=pid)
    if not other_active:
        run_disk_cleanup()

    if preserved_caches:
        PROCESSING_DIR.mkdir(parents=True, exist_ok=True)
        for cache_f, raw_content in preserved_caches.items():
            try:
                cache_f.write_text(raw_content, encoding="utf-8")
            except Exception:
                pass

    job_id = str(uuid.uuid4())[:8]
    state["job_id"] = job_id
    state["status"] = "STARTED"
    state["current_video"] = target_video_path.name if target_video_path else yt_url
    state["source_type"] = req.source_type
    state["source_preview_url"] = (
        f"/api/media/source/{quote(target_video_path.name)}"
        if target_video_path is not None
        else yt_url
    )
    state["progress_percent"] = 5
    state["phase_label"] = "Fase 1/4 · Preparación"
    state["step_detail"] = (
        f"Preparando video local '{target_video_path.name}' para transcripción y recorte 9:16..."
        if target_video_path is not None
        else f"Conectando con YouTube para descargar stream en máxima calidad: {yt_url}"
    )
    state["message"] = state["step_detail"]
    state["short_uploads"] = {}
    state["completion_summary"] = None
    state["requires_schedule_confirmation"] = False
    state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _persist_pipeline_state(pid)

    thread_args = (target_video_path, overrides) if (yt_url is None and target_video_path is not None) else (None, overrides, yt_url)
    thread_kwargs = {"project_id": pid} if pid != "default" else {}
    thread = threading.Thread(
        target=_run_pipeline_background,
        args=thread_args,
        kwargs=thread_kwargs,
        daemon=True,
    )
    thread.start()

    return {
        "project_id": pid,
        "job_id": job_id,
        "status": "STARTED",
        "target": state["current_video"],
        "settings_applied": applied_settings,
    }


@app.get("/api/pipeline/status")
def get_pipeline_status(project_id: Optional[str] = None) -> Dict[str, Any]:
    """Devuelve el estado en tiempo real del proceso de extracción y renderizado para el proyecto."""
    return dict(_get_project_state(project_id))


@app.post("/api/pipeline/cancel")
def cancel_pipeline_process(project_id: Optional[str] = None) -> Dict[str, Any]:
    """Cancela únicamente la ejecución activa del proyecto indicado."""
    pid = _normalize_project_id(project_id)
    try:
        _get_project_cancel_event(pid).set()
    except Exception:
        pass

    state = _get_project_state(pid)
    state["status"] = "CANCELED"
    state["source_preview_url"] = None
    state["phase_label"] = "Proceso Cancelado"
    state["step_detail"] = "Generación de Shorts cancelada por el usuario."
    state["message"] = "Generación de Shorts cancelada por el usuario."
    state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _persist_pipeline_state(pid)
    return {
        "project_id": pid,
        "status": "CANCELED",
        "pipeline_status": dict(state),
    }


def _remove_short_from_sqlite_queues(short_filename: str) -> None:
    """Elimina las reservas y colas pendientes en SQLite asociadas a un Short cancelado."""
    if not DB_PATH.exists():
        return
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute("DELETE FROM scheduled_slots WHERE video_name = ?", (short_filename,))
            for table_name in (
                "instagram_scheduled_queue",
                "tiktok_scheduled_queue",
                "facebook_scheduled_queue",
            ):
                has_tbl = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,),
                ).fetchone()
                if has_tbl:
                    conn.execute(
                        f"DELETE FROM {table_name} WHERE video_path LIKE ?",
                        (f"%{short_filename}",),
                    )
            conn.commit()
    except Exception as db_err:
        logger.warning("No se pudo limpiar %s de las colas SQLite: %s", short_filename, db_err)


@app.delete("/api/shorts")
def cancel_all_rendered_shorts(project_id: Optional[str] = None) -> Dict[str, Any]:
    """Cancela los Shorts renderizados del proyecto indicado y limpia sus colas en SQLite."""
    pid = _normalize_project_id(project_id)
    scan_root = _get_project_output_dir(pid)
    scan_root.mkdir(parents=True, exist_ok=True)
    canceled_count = 0

    for mp4_file in list(scan_root.rglob("*.mp4")):
        if "ig_ready_8m" in mp4_file.parts:
            continue
        if pid == "default" and "_projects" in mp4_file.parts:
            continue
        fname = mp4_file.name
        try:
            win_long_path(mp4_file).unlink(missing_ok=True)
            win_long_path(mp4_file.with_name(f"{mp4_file.stem}_meta.json")).unlink(missing_ok=True)
            win_long_path(mp4_file.with_name(f"{mp4_file.stem}_opencut_timeline.json")).unlink(missing_ok=True)
            win_long_path(mp4_file.with_name(f"{mp4_file.stem}.srcclip")).unlink(missing_ok=True)
            win_long_path(mp4_file.with_name(f"{mp4_file.stem}_0_subs.ass")).unlink(missing_ok=True)
            _remove_short_from_sqlite_queues(fname)
            canceled_count += 1
        except Exception as exc:
            logger.warning("Error eliminando Short %s: %s", fname, exc)

    # Limpiar también sidecars huérfanos dentro del alcance del proyecto
    for pattern in ("*.srcclip", "*_subs.ass", "*_meta.json", "*_opencut_timeline.json"):
        for sidecar in list(scan_root.rglob(pattern)):
            if "ig_ready_8m" in sidecar.parts:
                continue
            if pid == "default" and "_projects" in sidecar.parts:
                continue
            try:
                win_long_path(sidecar).unlink(missing_ok=True)
            except Exception:
                pass

    sf_dir = CONFIG_DIR / "scene_frames"
    if sf_dir.exists():
        if pid == "default":
            jpg_iter = [j for j in sf_dir.glob("short_*.jpg") if not j.name.startswith("short__projects_")]
        else:
            jpg_iter = list(sf_dir.glob(f"short__projects_{pid}_*.jpg"))
        for jpg in jpg_iter:
            try:
                jpg.unlink(missing_ok=True)
            except Exception:
                pass

    # Limpiar subcarpetas vacías dentro del alcance del proyecto
    for sub in sorted(scan_root.rglob("*"), reverse=True):
        lp_sub = win_long_path(sub)
        if lp_sub.is_dir() and sub.name not in ("ig_ready_8m", "_projects"):
            if pid == "default" and "_projects" in sub.parts:
                continue
            try:
                if not any(lp_sub.iterdir()):
                    lp_sub.rmdir()
            except Exception:
                pass

    state = _get_project_state(pid)
    state["short_uploads"] = {}
    _persist_pipeline_state(pid)
    return {
        "canceled": True,
        "project_id": pid,
        "canceled_count": canceled_count,
    }


@app.post("/api/project/rename")
def rename_project(req: RenameProjectRequest) -> Dict[str, Any]:
    """Renombra un proyecto en espera vinculándolo al nombre del video + fecha ('<Video>_<YYYY-MM-DD>')."""
    from_pid = _normalize_project_id(req.from_project_id)
    if from_pid == "default":
        raise HTTPException(status_code=400, detail="El proyecto principal ('default') no puede renombrarse.")

    old_state = _get_project_state(from_pid)
    if old_state.get("status") in ("STARTED", "RUNNING", "DISCOVERING"):
        raise HTTPException(status_code=409, detail="No se puede renombrar un proyecto mientras está en ejecución.")

    if req.new_project_id:
        base_target = _normalize_project_id(req.new_project_id)
    else:
        base_target = _main_daemon_bootstrap.build_video_date_project_id(req.video_filename)
    if base_target == "default":
        raise HTTPException(status_code=400, detail="Nombre de proyecto destino inválido.")

    target_pid = base_target
    suffix_num = 2
    while (
        target_pid != from_pid
        and (
            target_pid in PROJECT_STATES
            or _get_project_output_dir(target_pid).exists()
            or _project_state_file(target_pid).exists()
        )
    ):
        target_pid = _normalize_project_id(f"{base_target[:48]}_{suffix_num}")
        suffix_num += 1

    if target_pid != from_pid:
        old_out = _get_project_output_dir(from_pid)
        new_out = _get_project_output_dir(target_pid)
        new_out.parent.mkdir(parents=True, exist_ok=True)
        if old_out.exists():
            shutil.move(str(old_out), str(new_out))
        else:
            new_out.mkdir(parents=True, exist_ok=True)

        old_cand = _candidates_file(from_pid)
        new_cand = _candidates_file(target_pid)
        if old_cand.exists():
            new_cand.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old_cand), str(new_cand))

        old_state_file = _project_state_file(from_pid)
        try:
            old_state_file.unlink(missing_ok=True)
        except Exception:
            pass

        PROJECT_STATES.pop(from_pid, None)
        PROJECT_STATE_DIRS.pop(from_pid, None)
        cancel_ev = PROJECT_CANCEL_EVENTS.pop(from_pid, None) or threading.Event()
        PROJECT_CANCEL_EVENTS[target_pid] = cancel_ev
        PROJECT_STATES[target_pid] = old_state
        PROJECT_STATE_DIRS[target_pid] = CONFIG_DIR

    old_state["project_id"] = target_pid
    old_state["project_name"] = target_pid
    old_state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _persist_pipeline_state(target_pid)

    return {
        "renamed": target_pid != from_pid,
        "old_project_id": from_pid,
        "project_id": target_pid,
        "project_name": target_pid,
        "project_url": f"/?project={target_pid}",
        "pipeline_status": dict(_get_project_state(target_pid)),
    }


@app.post("/api/project/new")
def reset_new_project(req: Optional[NewProjectRequest] = Body(default=None)) -> Dict[str, Any]:
    """
    Si mode=='independent', registra una nueva sesión/ventana aislada sin interrumpir ni borrar el trabajo actual.
    Si mode=='reset' (por defecto para compatibilidad), limpia únicamente el proyecto objetivo.
    """
    if req is not None and req.mode == "independent":
        requested_pid = _normalize_project_id(req.project_id) if req.project_id else "default"
        if requested_pid != "default":
            new_pid = requested_pid
        else:
            base_pid = _main_daemon_bootstrap.build_video_date_project_id(None)
            candidate = base_pid
            suffix_num = 2
            while (
                candidate in PROJECT_STATES
                or _get_project_output_dir(candidate).exists()
                or _project_state_file(candidate).exists()
            ):
                candidate = _normalize_project_id(f"{base_pid}_{suffix_num}")
                suffix_num += 1
            new_pid = candidate
        new_state = _make_initial_pipeline_state(
            phase_label="Nuevo Proyecto",
            detail="Ventana independiente lista. Selecciona un video o pega un enlace para comenzar.",
        )
        new_state["project_id"] = new_pid
        new_state["project_name"] = new_pid
        new_state["message"] = f"Proyecto {new_pid} iniciado en nueva ventana."
        PROJECT_STATES[new_pid] = new_state
        PROJECT_STATE_DIRS[new_pid] = CONFIG_DIR
        PROJECT_CANCEL_EVENTS[new_pid] = threading.Event()
        _get_project_output_dir(new_pid).mkdir(parents=True, exist_ok=True)

        new_cand_file = _candidates_file(new_pid)
        if new_cand_file.exists():
            try:
                new_cand_file.unlink(missing_ok=True)
            except Exception:
                pass

        _persist_pipeline_state(new_pid)
        return {
            "created": True,
            "reset": False,
            "mode": "independent",
            "project_id": new_pid,
            "project_name": new_pid,
            "project_url": f"/?project={new_pid}",
            "canceled_shorts": 0,
            "deleted_temp_files": 0,
            "pipeline_status": dict(new_state),
            "videos": get_inbox(project_id=new_pid)["videos"],
            "disk_space": skill_cleanup.get_disk_space_report(BASE_DIR),
        }

    pid = _normalize_project_id(req.project_id if req is not None else None)
    state = _get_project_state(pid)
    cancel_ev = _get_project_cancel_event(pid)
    try:
        if state.get("status") in ("RUNNING", "STARTED", "DISCOVERING"):
            cancel_ev.set()
            time.sleep(0.05)
        cancel_ev.clear()
    except Exception:
        pass

    canceled_res = cancel_all_rendered_shorts(project_id=pid)

    cand_file = _candidates_file(pid)
    if cand_file.exists():
        try:
            cand_file.unlink(missing_ok=True)
        except Exception:
            pass

    proc_deleted = 0
    if not _has_other_active_projects(exclude_project_id=pid) and pid == "default":
        sf_dir = CONFIG_DIR / "scene_frames"
        if sf_dir.exists():
            for jpg in sf_dir.glob("*.jpg"):
                if not jpg.name.startswith("short__projects_"):
                    try:
                        jpg.unlink(missing_ok=True)
                    except Exception:
                        pass

        skill_cleanup.PROCESSING_DIR = PROCESSING_DIR
        skill_cleanup.OUTPUT_DIR = OUTPUT_SHORTS_DIR
        skill_cleanup.PUBLISHED_ARCHIVE_DIR = PUBLISHED_ARCHIVE_DIR
        proc_deleted, _ = skill_cleanup.clean_processing_dir(max_age_seconds=0)
        try:
            skill_cleanup.clean_ig_staging_cache(max_age_hours=0)
        except Exception:
            pass

    clean_payload = _make_initial_pipeline_state(
        phase_label="Nuevo Proyecto",
        detail="Proyecto limpio. Selecciona un video o pega un enlace para comenzar.",
    )
    clean_payload["message"] = "Nuevo proyecto iniciado. Todo limpio para agregar otro video."
    state.update(clean_payload)
    _persist_pipeline_state(pid)

    return {
        "reset": True,
        "mode": "reset",
        "project_id": pid,
        "canceled_shorts": canceled_res["canceled_count"],
        "deleted_temp_files": proc_deleted,
        "pipeline_status": dict(state),
        "videos": get_inbox(project_id=pid)["videos"],
        "disk_space": skill_cleanup.get_disk_space_report(BASE_DIR),
    }


@app.delete("/api/shorts/{short_rel_path:path}")
def cancel_single_rendered_short(short_rel_path: str) -> Dict[str, Any]:
    """Cancela un Short individual eliminando su archivo MP4 de ./output_shorts/ y sus colas en SQLite."""
    decoded = unquote(short_rel_path)
    pid = _infer_project_id_from_rel_path(decoded)
    out_root = OUTPUT_SHORTS_DIR.resolve()
    target = (out_root / decoded).resolve()
    if out_root not in target.parents and target != out_root:
        raise HTTPException(status_code=400, detail="Ruta de Short inválida.")
    lp_target = win_long_path(target)
    if not lp_target.exists() or not lp_target.is_file():
        raise HTTPException(status_code=404, detail="Short no encontrado en ./output_shorts/.")

    fname = target.name
    parent_dir = target.parent
    lp_target.unlink(missing_ok=True)
    win_long_path(target.with_name(f"{target.stem}_meta.json")).unlink(missing_ok=True)
    win_long_path(target.with_name(f"{target.stem}_opencut_timeline.json")).unlink(missing_ok=True)
    win_long_path(target.with_name(f"{target.stem}.srcclip")).unlink(missing_ok=True)
    _remove_short_from_sqlite_queues(fname)

    lp_parent = win_long_path(parent_dir)
    if parent_dir != out_root and lp_parent.exists():
        try:
            if not any(lp_parent.iterdir()):
                lp_parent.rmdir()
        except Exception:
            pass

    state = _get_project_state(pid)
    uploads = dict(state.get("short_uploads") or {})
    if fname in uploads:
        uploads.pop(fname, None)
        state["short_uploads"] = uploads
        _persist_pipeline_state(pid)

    return {
        "canceled": True,
        "filename": fname,
        "relative_path": decoded,
    }


def _ensure_youtube_slots_columns(db_path: Path) -> None:
    """Asegura las columnas de estado/error en scheduled_slots y corrige borradores TikTok v_inbox_file."""
    skill_scheduler.init_db(db_path)
    skill_tt_scheduler.init_tiktok_queue_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(scheduled_slots)").fetchall()}
        if "status" not in cols:
            conn.execute("ALTER TABLE scheduled_slots ADD COLUMN status TEXT DEFAULT 'PENDING'")
        if "error" not in cols:
            conn.execute("ALTER TABLE scheduled_slots ADD COLUMN error TEXT")
        tt_cols = {
            str(r[1]) for r in conn.execute("PRAGMA table_info(tiktok_scheduled_queue)").fetchall()
        }
        if "publish_id" in tt_cols and "post_id" in tt_cols:
            conn.execute(
                """
                UPDATE tiktok_scheduled_queue
                SET status = 'INBOX_DRAFT'
                WHERE status = 'PUBLISHED'
                  AND publish_id LIKE 'v_inbox_file%'
                  AND (post_id IS NULL OR TRIM(post_id) = '')
                """
            )
        conn.commit()


def _extract_row_permalink(net_key: str, row: Dict[str, Any]) -> Optional[str]:
    """Construye la URL pública verificable de un post/reel publicado en cada red social."""
    st = str(row.get("status") or "").strip().upper()
    if st in ("INBOX_DRAFT", "SEND_TO_USER_INBOX"):
        return None
    if net_key == "youtube":
        vid = str(row.get("youtube_video_id") or "").strip()
        return f"https://www.youtube.com/shorts/{vid}" if vid else None
    raw_perm = str(row.get("permalink") or "").strip()
    if raw_perm.startswith(("http://", "https://")):
        return raw_perm
    if st not in ("PUBLISHED", "COMPLETED", "UPLOADED"):
        return None
    post_id = str(row.get("post_id") or "").strip()
    if net_key == "facebook" and post_id:
        return f"https://www.facebook.com/reel/{post_id}/"
    if net_key == "tiktok" and post_id:
        acct = str(row.get("account_key") or "").strip().lstrip("@")
        if acct:
            return f"https://www.tiktok.com/@{acct}/video/{post_id}"
    return None


def _build_short_social_statuses(
    score_val: int,
    slot_ast_val: Optional[str],
    yt_id_val: Optional[str],
    live_upload: Optional[Dict[str, Any]],
    ig_rows: List[Dict[str, Any]],
    tt_rows: List[Dict[str, Any]],
    fb_rows: Optional[List[Dict[str, Any]]] = None,
    resolved_targets: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    yt_slot_status: Optional[str] = None,
    yt_slot_error: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Construye el estado por red social (YouTube, Instagram, TikTok y Facebook) sin filtro < 85 pts."""
    live_pct = int(live_upload.get("percent", 100)) if live_upload else None
    live_detail = str(live_upload.get("detail", "En proceso...")) if live_upload else ""
    targets = resolved_targets or {}

    def _target_handles_str(net_key: str, fallback_acct: Optional[str] = None) -> Optional[str]:
        rows_t = targets.get(net_key) or []
        handles = [str(a.get("handle") or "").strip() for a in rows_t if str(a.get("handle") or "").strip()]
        if handles:
            return ", ".join(handles)
        return fallback_acct

    yt_account_label = _target_handles_str("youtube", "CreadorStudio")
    yt_slot_st_upper = str(yt_slot_status or "").strip().upper()
    if yt_id_val:
        yt_status: Dict[str, Any] = {
            "network": "youtube",
            "state": "uploaded",
            "status_label": "Subido",
            "detail": f"Subido ({yt_id_val})" + (f" · {slot_ast_val}" if slot_ast_val else ""),
            "percent": 100,
            "account": yt_account_label,
            "permalink": f"https://www.youtube.com/shorts/{yt_id_val}",
        }
    elif yt_slot_st_upper in ("PROCESSING", "UPLOADING", "IN_PROGRESS"):
        yt_status = {
            "network": "youtube",
            "state": "processing",
            "status_label": "En proceso",
            "detail": "Reintentando subida a YouTube..." + (f" · {slot_ast_val}" if slot_ast_val else ""),
            "percent": 55,
            "account": yt_account_label,
            "permalink": None,
        }
    elif yt_slot_st_upper in ("FAILED", "ERROR") or yt_slot_error:
        err_snippet = str(yt_slot_error or "Error al subir a YouTube")[:160]
        yt_status = {
            "network": "youtube",
            "state": "error",
            "status_label": "Error",
            "detail": err_snippet,
            "percent": 100,
            "account": yt_account_label,
            "permalink": None,
        }
    elif live_upload and live_pct is not None and live_pct < 100:
        yt_status = {
            "network": "youtube",
            "state": "processing",
            "status_label": "En proceso",
            "detail": live_detail,
            "percent": max(20, live_pct),
            "account": yt_account_label,
        }
    elif slot_ast_val:
        yt_status = {
            "network": "youtube",
            "state": "pending",
            "status_label": "Pendiente",
            "detail": f"Pendiente · {slot_ast_val}",
            "percent": 45,
            "account": yt_account_label,
        }
    else:
        yt_status = {
            "network": "youtube",
            "state": "local",
            "status_label": "Listo en local",
            "detail": "Listo en local (Sin programar)",
            "percent": 0,
            "account": yt_account_label,
        }

    def _summarize_queue_network(net_key: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        configured_accts = _target_handles_str(net_key)
        if rows:
            prefix = "" if net_key == "facebook" else "@"
            accts_list = list(
                dict.fromkeys(
                    f"{prefix}{str(r['account_key']).lstrip('@')}"
                    for r in rows
                    if r.get("account_key")
                )
            )
            accts = ", ".join(accts_list)
            account_val = accts or configured_accts
            statuses = [str(r.get("status") or "PENDING").upper() for r in rows]
            if all(st in ("PUBLISHED", "COMPLETED", "UPLOADED") for st in statuses):
                first_perm = next(
                    (perm for r in rows if (perm := _extract_row_permalink(net_key, r))),
                    None,
                )
                return {
                    "network": net_key,
                    "state": "uploaded",
                    "status_label": "Subido",
                    "detail": f"{account_val} · Subido" if account_val else "Subido",
                    "percent": 100,
                    "account": account_val,
                    "permalink": first_perm,
                }
            if any(st in ("PROCESSING", "UPLOADING", "IN_PROGRESS", "STAGING") for st in statuses):
                return {
                    "network": net_key,
                    "state": "processing",
                    "status_label": "En proceso",
                    "detail": f"{account_val} · En proceso" if account_val else "En proceso",
                    "percent": 65,
                    "account": account_val,
                    "permalink": None,
                }
            if any(st in ("FAILED", "ERROR") for st in statuses):
                err_txt = next((str(r.get("error") or "") for r in rows if r.get("error")), "Error de API")[:42]
                return {
                    "network": net_key,
                    "state": "error",
                    "status_label": "Error",
                    "detail": f"{account_val} · {err_txt}" if account_val else err_txt,
                    "percent": 100,
                    "account": account_val,
                    "permalink": None,
                }
            if any(st in ("INBOX_DRAFT", "SEND_TO_USER_INBOX") for st in statuses):
                return {
                    "network": net_key,
                    "state": "draft",
                    "status_label": "En Borrador (App)",
                    "detail": (
                        f"{account_val} · Enviado a Bandeja TikTok (App) — falta publicar en la app"
                        if account_val
                        else "Enviado a Bandeja TikTok (App) — falta publicar en la app"
                    ),
                    "percent": 85,
                    "account": account_val,
                    "permalink": None,
                }
            when_txt = str(rows[0].get("scheduled_time_ast") or slot_ast_val or "En cola")
            return {
                "network": net_key,
                "state": "pending",
                "status_label": "Pendiente",
                "detail": f"{account_val} · {when_txt}" if account_val else f"Pendiente · {when_txt}",
                "percent": 40,
                "account": account_val,
            }
        if live_upload and live_pct is not None and live_pct < 100:
            return {
                "network": net_key,
                "state": "processing",
                "status_label": "En proceso",
                "detail": live_detail,
                "percent": max(20, live_pct),
                "account": configured_accts,
            }
        if slot_ast_val:
            return {
                "network": net_key,
                "state": "pending",
                "status_label": "Pendiente",
                "detail": f"Pendiente · {slot_ast_val}",
                "percent": 40,
                "account": configured_accts,
            }
        return {
            "network": net_key,
            "state": "local",
            "status_label": "Listo en local",
            "detail": "Listo en local (Sin programar)",
            "percent": 0,
            "account": configured_accts,
        }

    return {
        "youtube": yt_status,
        "instagram": _summarize_queue_network("instagram", ig_rows),
        "tiktok": _summarize_queue_network("tiktok", tt_rows),
        "facebook": _summarize_queue_network("facebook", fb_rows or []),
    }


@app.get("/api/shorts")
def get_rendered_shorts(project_id: Optional[str] = None) -> Dict[str, Any]:
    """Escanea ./output_shorts/ (aislado por proyecto) y cruza metadatos de viralidad y slots en SQLite."""
    pid = _normalize_project_id(project_id)
    state = _get_project_state(pid)
    scan_root = _get_project_output_dir(pid)
    scan_root.mkdir(parents=True, exist_ok=True)
    _ensure_youtube_slots_columns(DB_PATH)
    hub_cfg = social_hub.get_raw_social_hub_config(CONFIG_DIR)

    slot_map: Dict[str, Dict[str, Any]] = {}
    ig_map: Dict[str, List[Dict[str, Any]]] = {}
    tt_map: Dict[str, List[Dict[str, Any]]] = {}
    fb_map: Dict[str, List[Dict[str, Any]]] = {}
    if DB_PATH.exists():
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT video_name, slot_ast, publish_at_utc, youtube_video_id, status, error FROM scheduled_slots"
            ).fetchall()
            for r in rows:
                slot_map[r["video_name"]] = dict(r)

            for table_name, dst_map in (
                ("instagram_scheduled_queue", ig_map),
                ("tiktok_scheduled_queue", tt_map),
                ("facebook_scheduled_queue", fb_map),
            ):
                if conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,),
                ).fetchone():
                    q_rows = conn.execute(
                        f"SELECT * FROM {table_name} ORDER BY id ASC"
                    ).fetchall()
                    for qr in q_rows:
                        row_d = dict(qr)
                        bname = str(row_d.get("video_path") or "").replace("\\", "/").rstrip("/").split("/")[-1]
                        if bname:
                            dst_map.setdefault(bname, []).append(row_d)

    shorts_list: List[Dict[str, Any]] = []
    score_pattern = re.compile(r"_(?:(Oro|Plata|Meh)|[\d.]+)_(\d+)pts\.mp4$", re.IGNORECASE)

    for mp4_file in sorted(scan_root.rglob("*.mp4")):
        if "ig_ready_8m" in mp4_file.parts:
            continue
        if pid == "default" and "_projects" in mp4_file.parts:
            continue
        fname = mp4_file.name
        if fname.startswith(("_rendering_", "_tmp_")) or fname.endswith(".tmp.mp4"):
            continue

        lp_mp4 = win_long_path(mp4_file)
        try:
            stat = lp_mp4.stat()
        except OSError as stat_err:
            logger.warning("No se pudo leer stat de Short %s: %s", mp4_file.name, stat_err)
            continue
        fname = mp4_file.name
        folder_name = mp4_file.parent.name if mp4_file.parent != scan_root else ""

        match = score_pattern.search(fname)
        if match:
            score_val = int(match.group(2))
            if match.group(1):
                tier_raw = match.group(1).capitalize()
            else:
                tier_raw = "Oro" if score_val >= 90 else ("Plata" if score_val >= 75 else "Meh")
        else:
            v_eval = skill_virality.evaluate_virality_10_points(
                text=fname.replace("_", " "),
                duration=48.0,
                words=[],
                title=fname.stem if hasattr(fname, "stem") else mp4_file.stem,
            )
            score_val = v_eval.total_points
            tier_raw = "Oro" if score_val >= 90 else ("Plata" if score_val >= 75 else "Meh")

        slot_info = slot_map.get(fname, {})
        rel_path_str = mp4_file.relative_to(OUTPUT_SHORTS_DIR).as_posix()
        encoded_rel = "/".join(quote(part) for part in rel_path_str.split("/"))

        live_upload = (state.get("short_uploads") or {}).get(fname)
        yt_id_val = slot_info.get("youtube_video_id")
        slot_ast_val = slot_info.get("slot_ast")

        if live_upload:
            upload_pct = int(live_upload.get("percent", 50))
            upload_detail = str(live_upload.get("detail", "Subiendo a redes sociales..."))
        elif yt_id_val:
            upload_pct = 100
            upload_detail = f"Publicado en YouTube Shorts ({yt_id_val}) + Redes Sociales"
        elif slot_ast_val:
            upload_pct = 80
            upload_detail = f"Programado en YouTube, IG, TikTok y Facebook ({slot_ast_val})"
        else:
            upload_pct = 100
            upload_detail = "Listo en local (./output_shorts/) · Sin subida automática"

        # Leer metadata sidecar (*_meta.json / *_opencut_timeline.json) si existe
        hook_title_val: Optional[str] = None
        category_val: Optional[str] = None
        account_categories_val: Optional[List[str]] = None
        layout_used_val: Optional[str] = None
        duration_sec_val: Optional[float] = None
        subtitle_preset_val: str = "hormozi_pop"
        subtitle_position_val: str = "auto"
        cam_overlay_pos_val: str = "top_right"
        custom_cam_box_norm_val: Optional[List[float]] = None
        custom_content_box_norm_val: Optional[List[float]] = None
        publish_at_utc_val: Optional[str] = slot_info.get("publish_at_utc")
        has_source_16_9 = win_long_path(mp4_file.with_name(f"{mp4_file.stem}.srcclip")).exists()

        lp_meta = win_long_path(mp4_file.with_name(f"{mp4_file.stem}_meta.json"))
        if lp_meta.exists():
            try:
                meta_obj = json.loads(lp_meta.read_text(encoding="utf-8"))
                hook_title_val = meta_obj.get("hook_title") or None
                category_val = meta_obj.get("category") or None
                if isinstance(meta_obj.get("account_categories"), list):
                    valid_keys = _get_hub_category_keys()
                    account_categories_val = social_hub.normalize_account_categories(
                        meta_obj["account_categories"],
                        fallback=(),
                        valid_keys=valid_keys,
                    )
                layout_used_val = meta_obj.get("layout_used") or None
                if meta_obj.get("duration_sec") is not None:
                    duration_sec_val = float(meta_obj["duration_sec"])
                if meta_obj.get("subtitle_preset"):
                    subtitle_preset_val = str(meta_obj["subtitle_preset"])
                if meta_obj.get("subtitle_position"):
                    subtitle_position_val = str(meta_obj["subtitle_position"])
                if meta_obj.get("cam_overlay_pos"):
                    cam_overlay_pos_val = str(meta_obj["cam_overlay_pos"])
                if isinstance(meta_obj.get("custom_cam_box_norm"), list):
                    custom_cam_box_norm_val = [float(x) for x in meta_obj["custom_cam_box_norm"]]
                if isinstance(meta_obj.get("custom_content_box_norm"), list):
                    custom_content_box_norm_val = [float(x) for x in meta_obj["custom_content_box_norm"]]
                if not slot_ast_val and meta_obj.get("scheduled_ast"):
                    slot_ast_val = str(meta_obj["scheduled_ast"])
                if not publish_at_utc_val and meta_obj.get("publish_at_utc"):
                    publish_at_utc_val = str(meta_obj["publish_at_utc"])
            except Exception:
                pass

        lp_tl = win_long_path(mp4_file.with_name(f"{mp4_file.stem}_opencut_timeline.json"))
        if lp_tl.exists():
            try:
                tl_obj = json.loads(lp_tl.read_text(encoding="utf-8"))
                if layout_used_val is None:
                    kfs = tl_obj.get("tracks", [{}])[0].get("effects", [{}])[0].get("keyframes", [{}])
                    layout_used_val = tl_obj.get("layout_mode") or (kfs[0].get("mode") if kfs else None)
                if duration_sec_val is None and tl_obj.get("source", {}).get("duration") is not None:
                    duration_sec_val = float(tl_obj["source"]["duration"])
                re_cfg = tl_obj.get("reedit_settings") or {}
                if subtitle_preset_val == "hormozi_pop" and re_cfg.get("subtitle_preset"):
                    subtitle_preset_val = str(re_cfg["subtitle_preset"])
                if subtitle_position_val == "auto" and re_cfg.get("subtitle_position"):
                    subtitle_position_val = str(re_cfg["subtitle_position"])
                if cam_overlay_pos_val == "top_right" and re_cfg.get("cam_overlay_pos"):
                    cam_overlay_pos_val = str(re_cfg["cam_overlay_pos"])
                if custom_cam_box_norm_val is None and isinstance(re_cfg.get("custom_cam_box_norm"), list):
                    custom_cam_box_norm_val = [float(x) for x in re_cfg["custom_cam_box_norm"]]
                if custom_content_box_norm_val is None and isinstance(re_cfg.get("custom_content_box_norm"), list):
                    custom_content_box_norm_val = [float(x) for x in re_cfg["custom_content_box_norm"]]
                src_raw = tl_obj.get("source", {}).get("slice") or tl_obj.get("source", {}).get("file")
                if src_raw and Path(str(src_raw)).exists():
                    has_source_16_9 = True
            except Exception:
                pass

        if not account_categories_val:
            account_categories_val = social_hub.classify_short_account_categories(
                text="" if hook_title_val else fname.replace("_", " "),
                title=str(hook_title_val or fname),
                tags=[],
                scene_category=str(category_val or "auto"),
                scene_label=str(layout_used_val or ""),
                hub_cfg=hub_cfg,
                auto_by_topic=True,
            )
        resolved_targets_raw = social_hub.resolve_target_accounts_for_categories(
            account_categories_val, hub_cfg
        )
        social_statuses = _build_short_social_statuses(
            score_val=score_val,
            slot_ast_val=slot_ast_val,
            yt_id_val=yt_id_val,
            live_upload=live_upload,
            ig_rows=ig_map.get(fname, []),
            tt_rows=tt_map.get(fname, []),
            fb_rows=fb_map.get(fname, []),
            resolved_targets=resolved_targets_raw,
            yt_slot_status=slot_info.get("status"),
            yt_slot_error=slot_info.get("error"),
        )

        cache_ver = int(stat.st_mtime * 1000) + (int(stat.st_size) % 1000)
        shorts_list.append(
            {
                "filename": fname,
                "folder": folder_name,
                "relative_path": rel_path_str,
                "video_url": f"/api/media/short/{encoded_rel}?v={cache_ver}",
                "thumbnail_url": f"/api/media/thumbnail/{encoded_rel}?v={cache_ver}",
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "virality_score": score_val,
                "virality_grade": round(score_val / 10.0, 1),
                "tier": tier_raw,
                "hook_title": hook_title_val,
                "category": category_val,
                "account_categories": account_categories_val,
                "resolved_targets": {
                    plat: [str(acc.get("handle") or "") for acc in accs]
                    for plat, accs in resolved_targets_raw.items()
                },
                "layout_used": layout_used_val,
                "subtitle_preset": subtitle_preset_val,
                "subtitle_position": subtitle_position_val,
                "cam_overlay_pos": cam_overlay_pos_val,
                "custom_cam_box_norm": custom_cam_box_norm_val,
                "custom_content_box_norm": custom_content_box_norm_val,
                "has_source_16_9": bool(has_source_16_9),
                "duration_sec": duration_sec_val,
                "eligible_for_youtube": True,
                "scheduled_ast": slot_ast_val,
                "publish_at_utc": publish_at_utc_val,
                "youtube_video_id": yt_id_val,
                "upload_progress_percent": upload_pct,
                "upload_status_detail": upload_detail,
                "social_statuses": social_statuses,
            }
        )

    shorts_list.sort(key=lambda x: (x["virality_score"], x["created_at"]), reverse=True)

    oro_count = sum(1 for s in shorts_list if s["tier"] == "Oro")
    plata_count = sum(1 for s in shorts_list if s["tier"] == "Plata")
    meh_count = sum(1 for s in shorts_list if s["tier"] == "Meh")
    yt_eligible_count = sum(1 for s in shorts_list if s["eligible_for_youtube"])
    yt_uploaded_count = sum(1 for s in shorts_list if s.get("youtube_video_id"))

    summary = {
        "total_shorts": len(shorts_list),
        "oro_count": oro_count,
        "plata_count": plata_count,
        "meh_count": meh_count,
        "youtube_eligible_count": yt_eligible_count,
        "youtube_uploaded_count": yt_uploaded_count,
        "requires_schedule_confirmation": bool(
            state.get("requires_schedule_confirmation", False)
        ),
    }
    state["completion_summary"] = summary

    return {
        "total": len(shorts_list),
        "shorts": shorts_list,
        "summary": summary,
        "project_id": pid,
    }


class DownloadShortsBundleRequest(BaseModel):
    project_id: Optional[str] = Field(default=None)
    short_rel_paths: Optional[List[str]] = Field(
        default=None,
        description="Lista opcional de rutas relativas de Shorts a descargar; si se omite, empaqueta todos los del proyecto.",
    )


@app.post("/api/shorts/download-bundle")
def download_shorts_bundle(
    req: DownloadShortsBundleRequest,
    background_tasks: BackgroundTasks,
) -> FileResponse:
    """Descarga uno (MP4 directo) o múltiples Shorts (ZIP) de los seleccionados o de todo el proyecto."""
    pid = _normalize_project_id(req.project_id)
    out_base = OUTPUT_SHORTS_DIR.resolve()
    scan_root = _get_project_output_dir(pid)

    def _is_valid_short_mp4(p: Path) -> bool:
        if p.suffix.lower() != ".mp4":
            return False
        if "ig_ready_8m" in p.parts:
            return False
        if pid == "default" and "_projects" in p.parts:
            return False
        if p.name.startswith(("_rendering_", "_tmp_")) or p.name.endswith(".tmp.mp4"):
            return False
        return win_long_path(p).is_file()

    files: List[Path] = []
    seen: set[Path] = set()
    if req.short_rel_paths is not None:
        for raw_rel in req.short_rel_paths:
            clean_rel = unquote(str(raw_rel or "")).replace("\\", "/").strip("/")
            parts = [part for part in clean_rel.split("/") if part]
            if not clean_rel or ".." in parts:
                raise HTTPException(status_code=400, detail="Ruta de Short inválida.")
            candidates = [(OUTPUT_SHORTS_DIR / clean_rel).resolve()]
            if pid != "default":
                candidates.append((scan_root / clean_rel).resolve())
            matched_file: Optional[Path] = None
            for cand in candidates:
                if not cand.is_relative_to(out_base):
                    raise HTTPException(status_code=400, detail="Ruta fuera de output_shorts.")
                if _is_valid_short_mp4(cand):
                    matched_file = cand
                    break
            if matched_file is not None and matched_file not in seen:
                seen.add(matched_file)
                files.append(matched_file)
    else:
        if scan_root.exists():
            for mp4_path in sorted(scan_root.rglob("*.mp4")):
                resolved = mp4_path.resolve()
                if _is_valid_short_mp4(resolved) and resolved not in seen:
                    seen.add(resolved)
                    files.append(resolved)

    if not files:
        raise HTTPException(status_code=404, detail="No hay Shorts disponibles para descargar.")

    if len(files) == 1:
        single_path = files[0]
        return FileResponse(
            path=str(win_long_path(single_path)),
            media_type="video/mp4",
            filename=single_path.name,
        )

    tmp_dir = CONFIG_DIR / "downloads_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_zip = tmp_dir / f"shorts_{uuid.uuid4().hex[:10]}.zip"
    used_names: set[str] = set()
    with zipfile.ZipFile(win_long_path(tmp_zip), "w", compression=zipfile.ZIP_STORED) as zf:
        for fpath in files:
            arcname = fpath.name
            if arcname in used_names:
                arcname = f"{fpath.stem}_{len(used_names) + 1}{fpath.suffix}"
            used_names.add(arcname)
            zf.write(str(win_long_path(fpath)), arcname=arcname)

    background_tasks.add_task(lambda zp=tmp_zip: zp.unlink(missing_ok=True))
    proj_slug = _resolve_project_display_name(pid, _get_project_state(pid))
    return FileResponse(
        path=str(win_long_path(tmp_zip)),
        media_type="application/zip",
        filename=f"{proj_slug}_Shorts_{len(files)}.zip",
    )


def _parse_schedule_datetime_ast(raw_dt: str) -> datetime:
    """Convierte un string ISO o YYYY-MM-DDTHH:MM a datetime en zona AST (UTC-4)."""
    ast_tz = timezone(timedelta(hours=-4))
    cleaned = raw_dt.strip()
    if cleaned.endswith("Z"):
        dt_utc = datetime.fromisoformat(cleaned[:-1]).replace(tzinfo=timezone.utc)
        return dt_utc.astimezone(ast_tz)
    parsed = datetime.fromisoformat(cleaned)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=ast_tz)
    return parsed.astimezone(ast_tz)


def _enqueue_targets_for_short(
    *,
    mp4_path: Path,
    hook_title: str,
    caption_txt: str,
    account_categories: List[str],
    hub_cfg: Dict[str, Any],
    ig_utc_iso: str,
    ig_ast_str: str,
    tt_utc_iso: str,
    tt_ast_str: str,
    fb_utc_iso: str,
    fb_ast_str: str,
    force_new: bool = False,
) -> None:
    """Encola o actualiza en SQLite las colas de Instagram, TikTok y Facebook para un Short según sus categorías."""
    targets = social_hub.resolve_target_accounts_for_categories(account_categories, hub_cfg)
    fname = mp4_path.name
    social_hub.init_facebook_queue_db(DB_PATH)

    with sqlite3.connect(str(DB_PATH)) as conn:
        for table_name, utc_val, ast_val in (
            ("instagram_scheduled_queue", ig_utc_iso, ig_ast_str),
            ("tiktok_scheduled_queue", tt_utc_iso, tt_ast_str),
            ("facebook_scheduled_queue", fb_utc_iso, fb_ast_str),
        ):
            conn.execute(
                f"""
                UPDATE {table_name}
                SET scheduled_time_utc = ?, scheduled_time_ast = ?,
                    status = CASE WHEN status IN ('PUBLISHED', 'INBOX_DRAFT') THEN status ELSE 'PENDING' END,
                    error = CASE WHEN status IN ('PUBLISHED', 'INBOX_DRAFT') THEN error ELSE NULL END
                WHERE video_path LIKE ?
                """,
                (utc_val, ast_val, f"%{fname}"),
            )
        conn.commit()

    for acc in targets.get("instagram") or []:
        try:
            skill_ig_scheduler.enqueue_instagram_reel(
                video_path=str(mp4_path),
                account_key=str(acc.get("handle") or ""),
                caption=caption_txt,
                scheduled_time_utc=ig_utc_iso,
                scheduled_time_ast=ig_ast_str,
                db_path=DB_PATH,
                ig_user_id=str(acc.get("external_id") or ""),
            )
        except Exception as ig_err:
            logger.warning("Aviso encolando IG para %s: %s", fname, ig_err)

    for acc in targets.get("tiktok") or []:
        try:
            skill_tt_scheduler.enqueue_tiktok_video(
                video_path=str(mp4_path),
                account_key=str(acc.get("handle") or ""),
                caption=f"{hook_title} #Viral #Shorts",
                scheduled_time_utc=tt_utc_iso,
                scheduled_time_ast=tt_ast_str,
                db_path=DB_PATH,
            )
        except Exception as tt_err:
            logger.warning("Aviso encolando TikTok para %s: %s", fname, tt_err)

    for acc in targets.get("facebook") or []:
        try:
            social_hub.enqueue_facebook_reel(
                video_path=str(mp4_path),
                account_key=str(acc.get("handle") or ""),
                fb_page_id=str(acc.get("external_id") or ""),
                caption=caption_txt,
                scheduled_time_utc=fb_utc_iso,
                scheduled_time_ast=fb_ast_str,
                db_path=DB_PATH,
            )
        except Exception as fb_err:
            logger.warning("Aviso encolando Facebook para %s: %s", fname, fb_err)


@app.post("/api/shorts/schedule")
def schedule_rendered_shorts_batch(req: ScheduleBatchRequest) -> Dict[str, Any]:
    """
    Programa todos los Shorts actuales en YouTube, Instagram Reels, TikTok y Facebook
    sin filtro de puntaje < 85 pts, según las cuentas configuradas por categoría.
    """
    try:
        yt_base_ast = _parse_schedule_datetime_ast(req.youtube_start_time)
        ig_base_ast = _parse_schedule_datetime_ast(req.instagram_start_time)
        tt_base_ast = _parse_schedule_datetime_ast(req.tiktok_start_time)
        fb_base_ast = _parse_schedule_datetime_ast(req.facebook_start_time or req.instagram_start_time)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Formato de fecha y hora inválido: {exc}",
        ) from exc

    pid = _normalize_project_id(req.project_id)
    state = _get_project_state(pid)
    current_data = get_rendered_shorts(project_id=pid)
    shorts_items: List[Dict[str, Any]] = current_data["shorts"]
    hub_cfg = social_hub.get_raw_social_hub_config(CONFIG_DIR)

    _ensure_youtube_slots_columns(DB_PATH)
    skill_ig_scheduler.init_ig_queue_db(DB_PATH)
    skill_tt_scheduler.init_tiktok_queue_db(DB_PATH)
    social_hub.init_facebook_queue_db(DB_PATH)

    uploads_state = dict(state.get("short_uploads") or {})
    scheduled_count = 0
    youtube_uploaded_count = 0
    youtube_errors: List[str] = []

    for idx, item in enumerate(shorts_items):
        fname = item["filename"]
        rel_path = item["relative_path"]
        mp4_path = (OUTPUT_SHORTS_DIR / rel_path).resolve()
        existing_yt_id = item.get("youtube_video_id")
        item_cats = list(item.get("account_categories") or ["clipping"])
        item_targets = social_hub.resolve_target_accounts_for_categories(item_cats, hub_cfg)
        has_active_yt = bool(item_targets.get("youtube"))

        offset_delta = timedelta(minutes=idx * req.interval_minutes)
        yt_dt_ast = yt_base_ast + offset_delta
        ig_dt_ast = ig_base_ast + offset_delta
        tt_dt_ast = tt_base_ast + offset_delta
        fb_dt_ast = fb_base_ast + offset_delta
        yt_ast_str = yt_dt_ast.strftime("%Y-%m-%d %I:%M %p AST")
        ig_ast_str = ig_dt_ast.strftime("%Y-%m-%d %I:%M %p AST")
        tt_ast_str = tt_dt_ast.strftime("%Y-%m-%d %I:%M %p AST")
        fb_ast_str = fb_dt_ast.strftime("%Y-%m-%d %I:%M %p AST")
        yt_utc_iso = yt_dt_ast.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ig_utc_iso = ig_dt_ast.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        tt_utc_iso = tt_dt_ast.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        fb_utc_iso = fb_dt_ast.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute("DELETE FROM scheduled_slots WHERE video_name = ?", (fname,))
            conn.execute(
                """
                INSERT INTO scheduled_slots (
                    video_name, slot_ast, publish_at_utc, youtube_video_id, status, error, created_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fname,
                    yt_ast_str,
                    yt_utc_iso,
                    existing_yt_id,
                    "PUBLISHED" if existing_yt_id else "PENDING",
                    None,
                    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                ),
            )
            conn.commit()

        clean_title = str(item.get("hook_title") or Path(fname).stem.replace("_", " "))
        hook_title = clean_title if "#Shorts" in clean_title else f"{clean_title[:75]} #Shorts"
        caption_txt = f"🔥 {clean_title} 👇\n\n#Viral #Shorts"
        _enqueue_targets_for_short(
            mp4_path=mp4_path,
            hook_title=hook_title,
            caption_txt=caption_txt,
            account_categories=item_cats,
            hub_cfg=hub_cfg,
            ig_utc_iso=ig_utc_iso,
            ig_ast_str=ig_ast_str,
            tt_utc_iso=tt_utc_iso,
            tt_ast_str=tt_ast_str,
            fb_utc_iso=fb_utc_iso,
            fb_ast_str=fb_ast_str,
        )

        # Subir automáticamente a YouTube sin filtro < 85 pts ni bloqueo OAuth interactivo
        final_yt_id = existing_yt_id
        yt_item_err: Optional[str] = None
        if req.auto_upload_positive_to_youtube and has_active_yt and not final_yt_id and mp4_path.exists():
            try:
                up_resp = skill_uploader.upload_scheduled_short(
                    video_path=mp4_path,
                    title=hook_title[:95],
                    description=caption_txt,
                    tags=["CreadorStudio", "Shorts", "Viral"],
                    publish_at_iso=yt_utc_iso,
                    category_id=str(
                        hub_cfg.get("api_settings", {}).get("youtube", {}).get("default_category_id") or "22"
                    ),
                    client_secret_path=CONFIG_DIR / "client_secret.json",
                    token_path=CONFIG_DIR / "token.json",
                    allow_interactive=False,
                )
                final_yt_id = up_resp.get("id")
                if final_yt_id:
                    with sqlite3.connect(str(DB_PATH)) as conn:
                        conn.execute(
                            "UPDATE scheduled_slots SET youtube_video_id = ?, status = 'PUBLISHED', error = NULL WHERE video_name = ?",
                            (final_yt_id, fname),
                        )
                        conn.commit()
                    youtube_uploaded_count += 1
            except Exception as up_err:
                yt_item_err = str(up_err).strip() or "Error al subir Short a YouTube."
                logger.warning("Aviso al subir Short %s a YouTube: %s", fname, yt_item_err)
                if yt_item_err not in youtube_errors:
                    youtube_errors.append(yt_item_err)
                with sqlite3.connect(str(DB_PATH)) as conn:
                    conn.execute(
                        "UPDATE scheduled_slots SET status = 'FAILED', error = ? WHERE video_name = ?",
                        (yt_item_err[:300], fname),
                    )
                    conn.commit()

        yt_badge = (
            f"YouTube Error ({yt_item_err[:60]})"
            if yt_item_err
            else (f"YouTube ({final_yt_id} · {yt_ast_str})" if final_yt_id else f"YouTube ({yt_ast_str})")
        )
        uploads_state[fname] = {
            "percent": 100,
            "detail": f"100% Programado: {yt_badge} · IG ({ig_ast_str}) · TikTok ({tt_ast_str}) · Facebook ({fb_ast_str})",
        }
        scheduled_count += 1

    state["short_uploads"] = uploads_state
    state["requires_schedule_confirmation"] = False
    _persist_pipeline_state(pid)

    if not os.environ.get("PYTEST_CURRENT_TEST"):
        threading.Thread(target=run_due_social_queues, daemon=True).start()

    refreshed = get_rendered_shorts(project_id=pid)
    yt_error_summary = youtube_errors[0] if youtube_errors else None
    return {
        "scheduled": True,
        "scheduled_count": scheduled_count,
        "youtube_uploaded_count": youtube_uploaded_count,
        "youtube_error": yt_error_summary,
        "summary": refreshed["summary"],
        "shorts": refreshed["shorts"],
        "project_id": pid,
    }


def _safe_short_scene_frame_path(short_rel_path: str) -> Path:
    safe_key = re.sub(r"[^a-zA-Z0-9_-]", "_", short_rel_path)[:80] or "short"
    frames_dir = CONFIG_DIR / "scene_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    return frames_dir / f"short_{safe_key}.jpg"


def _resolve_short_and_reedit_context(short_rel_path: str) -> Dict[str, Any]:
    decoded = unquote(short_rel_path).replace("\\", "/").lstrip("/")
    out_root = OUTPUT_SHORTS_DIR.resolve()
    target_mp4 = (out_root / decoded).resolve()
    if out_root not in target_mp4.parents and target_mp4 != out_root:
        raise HTTPException(status_code=400, detail="Ruta de Short inválida.")
    lp_target = win_long_path(target_mp4)
    if not lp_target.exists() or not lp_target.is_file():
        raise HTTPException(status_code=404, detail="Short no encontrado en ./output_shorts/.")

    meta_path = target_mp4.with_name(f"{target_mp4.stem}_meta.json")
    meta_obj: Dict[str, Any] = {}
    lp_meta = win_long_path(meta_path)
    if lp_meta.exists():
        try:
            meta_obj = json.loads(lp_meta.read_text(encoding="utf-8"))
        except Exception:
            meta_obj = {}

    tl_path = target_mp4.with_name(f"{target_mp4.stem}_opencut_timeline.json")
    tl_obj: Dict[str, Any] = {}
    lp_tl = win_long_path(tl_path)
    if lp_tl.exists():
        try:
            tl_obj = json.loads(lp_tl.read_text(encoding="utf-8"))
        except Exception:
            tl_obj = {}

    clip_dur = float(tl_obj.get("source", {}).get("duration") or meta_obj.get("duration_sec") or 0.0)
    if clip_dur <= 0.0:
        cap = cv2.VideoCapture(str(lp_target))
        if cap.isOpened():
            try:
                fps = float(cap.get(cv2.CAP_PROP_FPS)) or 30.0
                total_f = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
                if total_f > 0:
                    clip_dur = round(total_f / max(1.0, fps), 3)
            finally:
                cap.release()
    if clip_dur <= 0.0:
        clip_dur = 2.0

    srcclip_path = target_mp4.with_name(f"{target_mp4.stem}.srcclip")
    tl_src_file_raw = tl_obj.get("source", {}).get("file")
    tl_src_slice_raw = tl_obj.get("reedit_settings", {}).get("source_slice") or tl_obj.get("source", {}).get("slice")

    has_source_16_9 = False
    using_srcclip = False
    source_video_path = target_mp4
    start_time = 0.0
    end_time = clip_dur
    src_node = tl_obj.get("source") or {}

    if win_long_path(srcclip_path).exists() and win_long_path(srcclip_path).stat().st_size > 1024:
        source_video_path = srcclip_path
        has_source_16_9 = True
        using_srcclip = True
    elif tl_src_slice_raw and Path(str(tl_src_slice_raw)).exists():
        source_video_path = Path(str(tl_src_slice_raw))
        has_source_16_9 = True
        using_srcclip = True
    elif tl_src_file_raw and Path(str(tl_src_file_raw)).exists():
        source_video_path = Path(str(tl_src_file_raw))
        start_time = float(src_node.get("trimStart") or 0.0)
        end_time = float(src_node.get("trimEnd") or (start_time + clip_dur))
        has_source_16_9 = True

    probed_src_dur = skill_renderer._probe_media_duration_sec(source_video_path)
    if using_srcclip:
        slice_total_dur = max(float(src_node.get("slice_total_duration") or 0.0), probed_src_dur, clip_dur)
        start_time = float(src_node.get("slice_trim_start") or 0.0)
        raw_slice_end = src_node.get("slice_trim_end")
        end_time = float(raw_slice_end) if raw_slice_end is not None else min(slice_total_dur, start_time + clip_dur)
        if end_time <= start_time:
            end_time = min(slice_total_dur, start_time + clip_dur)
        max_trim_sec = slice_total_dur
    else:
        max_trim_sec = max(probed_src_dur, end_time, clip_dur)

    rel_norm = target_mp4.relative_to(out_root).as_posix()
    word_timestamps = list(tl_obj.get("word_timestamps") or [])
    context_word_timestamps = list(tl_obj.get("context_word_timestamps") or [])
    raw_keep = tl_obj.get("keep_intervals")
    keep_intervals = [tuple(iv) for iv in raw_keep] if isinstance(raw_keep, list) and len(raw_keep) > 0 else None

    return {
        "rel_path": rel_norm,
        "target_mp4": target_mp4,
        "meta_path": meta_path,
        "meta_obj": meta_obj,
        "tl_path": tl_path,
        "tl_obj": tl_obj,
        "srcclip_path": srcclip_path,
        "source_video_path": source_video_path,
        "using_srcclip": using_srcclip,
        "start_time": float(round(start_time, 3)),
        "end_time": float(round(max(start_time + 0.2, end_time), 3)),
        "min_trim_sec": 0.0,
        "max_trim_sec": float(round(max(clip_dur, max_trim_sec), 3)),
        "slice_origin_sec": float(src_node.get("slice_origin_sec") or 0.0),
        "clip_duration": float(clip_dur),
        "has_source_16_9": bool(has_source_16_9),
        "word_timestamps": word_timestamps,
        "context_word_timestamps": context_word_timestamps,
        "keep_intervals": keep_intervals,
    }


@app.get("/api/media/short-edit-source/{short_rel_path:path}")
def get_short_edit_source_stream(short_rel_path: str) -> FileResponse:
    """Sirve la fuente editable (.srcclip ±30s o video del Short) para previsualizar el recorte en vivo."""
    ctx = _resolve_short_and_reedit_context(short_rel_path)
    src_path = win_long_path(ctx["source_video_path"])
    if not src_path.exists():
        raise HTTPException(status_code=404, detail="Fuente editable del Short no disponible.")
    return FileResponse(str(src_path), media_type="video/mp4")


@app.post("/api/shorts/scene-detect")
def detect_rendered_short_scene(req: ShortSceneDetectRequest) -> Dict[str, Any]:
    """Extrae el fotograma, rango editable (±30s) y cajas IA de un Short ya renderizado."""
    ctx = _resolve_short_and_reedit_context(req.short_rel_path)
    src_path: Path = ctx["source_video_path"]
    target_ts = req.timestamp_sec
    if target_ts is None and ctx["has_source_16_9"]:
        span = max(0.5, float(ctx["end_time"]) - float(ctx["start_time"]))
        target_ts = float(ctx["start_time"]) + min(5.0, span * 0.2)

    det = _extract_scene_frame_and_boxes(src_path, timestamp_sec=target_ts)
    safe_src_stem = re.sub(r"[^a-zA-Z0-9_-]", "_", src_path.stem)[:60] or "scene"
    det_tag_m = re.search(r"scene_tag=([^&]+)", str(det.get("frame_url") or ""))
    det_tag = unquote(det_tag_m.group(1)) if det_tag_m else ""
    src_jpg = (
        CONFIG_DIR / "scene_frames" / f"{safe_src_stem}__{det_tag}.jpg"
        if det_tag
        else CONFIG_DIR / "scene_frames" / f"{safe_src_stem}.jpg"
    )
    if not src_jpg.exists():
        src_jpg = CONFIG_DIR / "scene_frames" / f"{safe_src_stem}.jpg"
    short_jpg = _safe_short_scene_frame_path(ctx["rel_path"])
    if src_jpg.exists():
        shutil.copy2(str(src_jpg), str(short_jpg))

    meta_obj = ctx["meta_obj"]
    re_cfg = ctx["tl_obj"].get("reedit_settings") or {}
    saved_cam = meta_obj.get("custom_cam_box_norm") or re_cfg.get("custom_cam_box_norm")
    saved_content = meta_obj.get("custom_content_box_norm") or re_cfg.get("custom_content_box_norm")

    cam_box = [float(x) for x in saved_cam] if isinstance(saved_cam, list) and len(saved_cam) == 4 else det["cam_box_norm"]
    content_box = (
        [float(x) for x in saved_content]
        if isinstance(saved_content, list) and len(saved_content) == 4
        else det["content_box_norm"]
    )
    current_layout = str(
        meta_obj.get("layout_used") or re_cfg.get("layout_mode") or det["detected_layout"] or "fullscreen"
    )
    subtitle_preset = str(meta_obj.get("subtitle_preset") or re_cfg.get("subtitle_preset") or "hormozi_pop")
    subtitle_position = str(meta_obj.get("subtitle_position") or re_cfg.get("subtitle_position") or "auto")
    cam_overlay_pos = str(meta_obj.get("cam_overlay_pos") or re_cfg.get("cam_overlay_pos") or "top_right")
    encoded_rel = "/".join(quote(part) for part in str(ctx["rel_path"]).split("/"))

    return {
        "short_rel_path": ctx["rel_path"],
        "filename": ctx["target_mp4"].name,
        "resolution": det["resolution"],
        "width": det["width"],
        "height": det["height"],
        "detected_layout": det["detected_layout"],
        "current_layout": current_layout,
        "faces_detected": det["faces_detected"],
        "cam_box_norm": cam_box,
        "content_box_norm": content_box,
        "subtitle_preset": subtitle_preset,
        "subtitle_position": subtitle_position,
        "cam_overlay_pos": cam_overlay_pos,
        "has_source_16_9": ctx["has_source_16_9"],
        "trim_start_sec": ctx["start_time"],
        "trim_end_sec": ctx["end_time"],
        "min_trim_sec": ctx["min_trim_sec"],
        "max_trim_sec": ctx["max_trim_sec"],
        "edit_media_url": f"/api/media/short-edit-source/{encoded_rel}?t={int(time.time() * 1000)}",
        "frame_url": f"/api/media/short-scene-frame?short_rel_path={quote(ctx['rel_path'])}&t={int(time.time() * 1000)}",
    }


@app.get("/api/media/short-scene-frame")
def get_rendered_short_scene_frame(short_rel_path: str) -> Response:
    """Sirve el fotograma JPEG del editor de layout de un Short ya renderizado."""
    ctx = _resolve_short_and_reedit_context(short_rel_path)
    short_jpg = _safe_short_scene_frame_path(ctx["rel_path"])
    if not short_jpg.exists():
        detect_rendered_short_scene(ShortSceneDetectRequest(short_rel_path=ctx["rel_path"]))
    if not short_jpg.exists():
        raise HTTPException(status_code=404, detail="Fotograma del Short no disponible.")
    return Response(content=short_jpg.read_bytes(), media_type="image/jpeg")


@app.post("/api/shorts/rerender")
def rerender_rendered_short(req: RerenderShortRequest) -> Dict[str, Any]:
    """Re-renderiza un Short existente cambiando layout, subtítulos y/o duración (acortar o alargar ±30s)."""
    ctx = _resolve_short_and_reedit_context(req.short_rel_path)
    target_mp4: Path = ctx["target_mp4"]
    srcclip_path: Path = ctx["srcclip_path"]

    if not ctx["has_source_16_9"]:
        shutil.copy2(str(win_long_path(target_mp4)), str(win_long_path(srcclip_path)))
        render_src = srcclip_path
        render_start = 0.0
        render_end = ctx["clip_duration"]
        allow_subtitles = False
        max_bound = ctx["clip_duration"]
    else:
        render_src = ctx["source_video_path"]
        render_start = float(ctx["start_time"])
        render_end = float(ctx["end_time"])
        allow_subtitles = req.subtitle_preset != "none"
        max_bound = float(ctx.get("max_trim_sec") or render_end)

    trim_requested = req.trim_start_sec is not None or req.trim_end_sec is not None
    if trim_requested:
        req_s = float(req.trim_start_sec) if req.trim_start_sec is not None else render_start
        req_e = float(req.trim_end_sec) if req.trim_end_sec is not None else render_end
        if req_s < 0.0 or req_e <= req_s or req_e > max_bound + 0.5:
            raise HTTPException(
                status_code=400,
                detail=f"El rango [{req_s:.1f}s - {req_e:.1f}s] excede el colchón disponible (0.0s - {max_bound:.1f}s).",
            )
        if (req_e - req_s) < 3.0:
            raise HTTPException(
                status_code=400,
                detail="La duración mínima del Short tras recortar debe ser al menos 3 segundos.",
            )
        old_s = render_start
        old_e = render_end
        render_start = round(req_s, 3)
        render_end = round(min(max_bound, req_e), 3)
    else:
        old_s = render_start
        old_e = render_end

    words_for_render = list(ctx["word_timestamps"])
    context_words = list(ctx.get("context_word_timestamps") or [])
    if trim_requested and context_words:
        sliced_words: List[Dict[str, Any]] = []
        for w in context_words:
            ws = float(w.get("start", 0.0))
            we = float(w.get("end", ws + 0.2))
            if we >= render_start and ws <= render_end:
                rs = max(0.0, round(ws - render_start, 4))
                re_ = max(rs + 0.05, min(round(render_end - render_start, 4), round(we - render_start, 4)))
                sliced_words.append(
                    {
                        "word": str(w.get("word", "")),
                        "start": rs,
                        "end": re_,
                        "probability": float(w.get("probability", 1.0)),
                    }
                )
        words_for_render = sliced_words
    elif trim_requested and (abs(render_start - old_s) > 0.25 or abs(render_end - old_e) > 0.25):
        offset_delta = old_s - render_start
        shifted_fallback: List[Dict[str, Any]] = []
        span = render_end - render_start
        for w in words_for_render:
            wd = dict(w) if isinstance(w, dict) else {"word": getattr(w, "word", ""), "start": getattr(w, "start", 0.0), "end": getattr(w, "end", 0.2)}
            ns = round(float(wd.get("start", 0.0)) + offset_delta, 4)
            ne = round(float(wd.get("end", ns + 0.2)) + offset_delta, 4)
            if ne >= 0.0 and ns <= span:
                shifted_fallback.append(
                    {
                        "word": str(wd.get("word", "")),
                        "start": max(0.0, ns),
                        "end": max(max(0.0, ns) + 0.05, min(span, ne)),
                        "probability": float(wd.get("probability", 1.0)),
                    }
                )
        words_for_render = shifted_fallback

    tmp_name = f"_tmp_rerender_{target_mp4.name}"
    tmp_mp4 = target_mp4.parent / tmp_name
    tmp_tl = target_mp4.parent / f"{tmp_mp4.stem}_opencut_timeline.json"
    tmp_mp4.unlink(missing_ok=True)
    tmp_tl.unlink(missing_ok=True)

    cat_hint = str(ctx["meta_obj"].get("category") or "auto")
    rendered_tmp = skill_renderer.render_vertical_short(
        video_path=render_src,
        start_time=render_start,
        end_time=render_end,
        word_timestamps=words_for_render,
        output_dir=target_mp4.parent,
        output_filename=tmp_name,
        bgm_mood="desactivada",
        keep_intervals=None if trim_requested else ctx["keep_intervals"],
        enable_bgm=False,
        layout_mode=req.layout_mode,
        custom_cam_box_norm=req.custom_cam_box_norm,
        custom_content_box_norm=req.custom_content_box_norm,
        cam_overlay_pos=req.cam_overlay_pos,
        subtitle_preset=req.subtitle_preset,
        subtitle_position=req.subtitle_position,
        enable_subtitles=allow_subtitles,
        category_hint=cat_hint,
    )
    os.replace(str(win_long_path(rendered_tmp)), str(win_long_path(target_mp4)))

    final_tl_layout = str(req.layout_mode)
    new_duration_sec = round(max(0.2, render_end - render_start), 2)
    if tmp_tl.exists():
        try:
            tl_data = json.loads(tmp_tl.read_text(encoding="utf-8"))
            tl_data["output"] = str(target_mp4.resolve())
            if context_words:
                tl_data["context_word_timestamps"] = context_words
            if isinstance(tl_data.get("source"), dict):
                tl_data["source"]["file"] = str(render_src.resolve())
                if srcclip_path.exists():
                    tl_data["source"]["slice"] = str(srcclip_path.resolve())
                tl_data["source"]["slice_origin_sec"] = ctx.get("slice_origin_sec", 0.0)
                tl_data["source"]["slice_trim_start"] = render_start
                tl_data["source"]["slice_trim_end"] = render_end
                tl_data["source"]["slice_total_duration"] = max_bound
                tl_data["source"]["duration"] = round(render_end - render_start, 3)
            final_tl_layout = str(tl_data.get("layout_mode") or final_tl_layout)
            ctx["tl_path"].write_text(json.dumps(tl_data, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp_tl.unlink(missing_ok=True)
        except Exception:
            if tmp_tl.exists():
                os.replace(str(tmp_tl), str(ctx["tl_path"]))

    updated_meta = dict(ctx["meta_obj"])
    updated_meta.update(
        {
            "short_filename": target_mp4.name,
            "layout_used": final_tl_layout,
            "duration_sec": new_duration_sec,
            "subtitle_preset": req.subtitle_preset,
            "subtitle_position": req.subtitle_position,
            "cam_overlay_pos": req.cam_overlay_pos,
            "custom_cam_box_norm": list(req.custom_cam_box_norm) if req.custom_cam_box_norm is not None else None,
            "custom_content_box_norm": (
                list(req.custom_content_box_norm) if req.custom_content_box_norm is not None else None
            ),
            "bgm_mood": "desactivada",
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    ctx["meta_path"].write_text(json.dumps(updated_meta, indent=2, ensure_ascii=False), encoding="utf-8")

    short_jpg = _safe_short_scene_frame_path(ctx["rel_path"])
    if short_jpg.exists():
        short_jpg.unlink(missing_ok=True)

    pid = _infer_project_id_from_rel_path(ctx["rel_path"])
    refreshed = get_rendered_shorts(project_id=pid)
    matched = next((s for s in refreshed["shorts"] if s["relative_path"] == ctx["rel_path"]), None)
    return {
        "rerendered": True,
        "short": matched,
        "shorts": refreshed["shorts"],
    }


@app.post("/api/shorts/categories")
def update_short_account_categories(req: UpdateShortCategoriesRequest) -> Dict[str, Any]:
    """Cambia o elimina las categorías de distribución asignadas a un Short específico."""
    ctx = _resolve_short_and_reedit_context(req.short_rel_path)
    valid_keys = _get_hub_category_keys()
    raw_in = [str(c or "").strip().lower() for c in req.account_categories]
    invalid = [c for c in raw_in if c not in valid_keys]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Categoría(s) inválida(s): {invalid}. Permitidas: {valid_keys}",
        )
    normalized = social_hub.normalize_account_categories(
        raw_in, fallback=(), valid_keys=valid_keys
    )
    if not normalized:
        raise HTTPException(
            status_code=400,
            detail="El Short debe conservar al menos una categoría de destino.",
        )

    updated_meta = dict(ctx["meta_obj"])
    updated_meta.update(
        {
            "short_filename": ctx["target_mp4"].name,
            "account_categories": normalized,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    ctx["meta_path"].write_text(json.dumps(updated_meta, indent=2, ensure_ascii=False), encoding="utf-8")

    pid = _infer_project_id_from_rel_path(ctx["rel_path"])
    refreshed = get_rendered_shorts(project_id=pid)
    matched = next((s for s in refreshed["shorts"] if s["relative_path"] == ctx["rel_path"]), None)
    return {
        "updated": True,
        "account_categories": normalized,
        "short": matched,
        "shorts": refreshed["shorts"],
    }


@app.post("/api/shorts/schedule-single")
def schedule_single_rendered_short(req: ScheduleSingleShortRequest) -> Dict[str, Any]:
    """Programa fecha y hora individualmente para un Short en YouTube, Instagram, TikTok y Facebook."""
    ctx = _resolve_short_and_reedit_context(req.short_rel_path)
    pid = _infer_project_id_from_rel_path(ctx["rel_path"])
    state = _get_project_state(pid)
    target_mp4: Path = ctx["target_mp4"]
    fname = target_mp4.name

    try:
        dt_ast = _parse_schedule_datetime_ast(req.scheduled_time)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Formato de fecha y hora inválido: {exc}",
        ) from exc

    ast_str = dt_ast.strftime("%Y-%m-%d %I:%M %p AST")
    utc_iso = dt_ast.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    _ensure_youtube_slots_columns(DB_PATH)
    skill_ig_scheduler.init_ig_queue_db(DB_PATH)
    skill_tt_scheduler.init_tiktok_queue_db(DB_PATH)
    social_hub.init_facebook_queue_db(DB_PATH)

    refreshed_before = get_rendered_shorts(project_id=pid)
    current_item = next((s for s in refreshed_before["shorts"] if s["relative_path"] == ctx["rel_path"]), None)
    existing_yt_id = current_item.get("youtube_video_id") if current_item else None
    item_cats = list(
        (current_item.get("account_categories") if current_item else None)
        or ctx["meta_obj"].get("account_categories")
        or ["clipping"]
    )
    hub_cfg = social_hub.get_raw_social_hub_config(CONFIG_DIR)
    item_targets = social_hub.resolve_target_accounts_for_categories(item_cats, hub_cfg)
    has_active_yt = bool(item_targets.get("youtube"))

    meta_obj = ctx["meta_obj"]
    hook_title = str(meta_obj.get("hook_title") or f"🔥 {target_mp4.stem.replace('_', ' ')} #Shorts")
    if "#Shorts" not in hook_title:
        hook_title = f"{hook_title} #Shorts"
    caption_txt = str(
        meta_obj.get("caption")
        or f"🔥 {target_mp4.stem.replace('_', ' ')} 👇\n\n#Viral #Shorts"
    )
    tags_list = list(meta_obj.get("tags") or ["CreadorStudio", "Shorts", "Viral"])

    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("DELETE FROM scheduled_slots WHERE video_name = ?", (fname,))
        conn.execute(
            """
            INSERT INTO scheduled_slots (
                video_name, slot_ast, publish_at_utc, youtube_video_id, status, error, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fname,
                ast_str,
                utc_iso,
                existing_yt_id,
                "PUBLISHED" if existing_yt_id else "PENDING",
                None,
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            ),
        )
        conn.commit()

    _enqueue_targets_for_short(
        mp4_path=target_mp4,
        hook_title=hook_title,
        caption_txt=caption_txt,
        account_categories=item_cats,
        hub_cfg=hub_cfg,
        ig_utc_iso=utc_iso,
        ig_ast_str=ast_str,
        tt_utc_iso=utc_iso,
        tt_ast_str=ast_str,
        fb_utc_iso=utc_iso,
        fb_ast_str=ast_str,
    )

    final_yt_id = existing_yt_id
    yt_error_msg: Optional[str] = None
    if req.upload_to_youtube and has_active_yt and not final_yt_id and target_mp4.exists():
        try:
            up_resp = skill_uploader.upload_scheduled_short(
                video_path=target_mp4,
                title=hook_title[:95],
                description=caption_txt,
                tags=tags_list,
                publish_at_iso=utc_iso,
                category_id=str(
                    hub_cfg.get("api_settings", {}).get("youtube", {}).get("default_category_id") or "22"
                ),
                client_secret_path=CONFIG_DIR / "client_secret.json",
                token_path=CONFIG_DIR / "token.json",
                allow_interactive=False,
            )
            final_yt_id = up_resp.get("id")
            if final_yt_id:
                with sqlite3.connect(str(DB_PATH)) as conn:
                    conn.execute(
                        "UPDATE scheduled_slots SET youtube_video_id = ?, status = 'PUBLISHED', error = NULL WHERE video_name = ?",
                        (final_yt_id, fname),
                    )
                    conn.commit()
        except Exception as up_err:
            yt_error_msg = str(up_err).strip() or "Error al subir Short a YouTube."
            logger.warning("Aviso al programar subida individual de %s a YouTube: %s", fname, yt_error_msg)
            with sqlite3.connect(str(DB_PATH)) as conn:
                conn.execute(
                    "UPDATE scheduled_slots SET status = 'FAILED', error = ? WHERE video_name = ?",
                    (yt_error_msg[:300], fname),
                )
                conn.commit()

    updated_meta = dict(meta_obj)
    updated_meta.update(
        {
            "short_filename": fname,
            "account_categories": item_cats,
            "scheduled_ast": ast_str,
            "publish_at_utc": utc_iso,
            "bgm_mood": "desactivada",
        }
    )
    ctx["meta_path"].write_text(json.dumps(updated_meta, indent=2, ensure_ascii=False), encoding="utf-8")

    uploads_state = dict(state.get("short_uploads") or {})
    yt_badge = (
        f"YouTube Error ({yt_error_msg[:60]})"
        if yt_error_msg
        else (f"YouTube ({final_yt_id} · {ast_str})" if final_yt_id else f"YouTube ({ast_str})")
    )
    uploads_state[fname] = {
        "percent": 100,
        "detail": f"100% Programado: {yt_badge} · IG ({ast_str}) · TikTok ({ast_str}) · Facebook ({ast_str})",
    }
    state["short_uploads"] = uploads_state
    _persist_pipeline_state(pid)

    if not os.environ.get("PYTEST_CURRENT_TEST"):
        threading.Thread(target=run_due_social_queues, daemon=True).start()

    refreshed = get_rendered_shorts(project_id=pid)
    matched = next((s for s in refreshed["shorts"] if s["relative_path"] == ctx["rel_path"]), None)
    return {
        "scheduled": True,
        "filename": fname,
        "scheduled_ast": ast_str,
        "publish_at_utc": utc_iso,
        "youtube_video_id": final_yt_id,
        "youtube_error": yt_error_msg,
        "short": matched,
        "shorts": refreshed["shorts"],
        "summary": refreshed["summary"],
    }


@app.get("/api/media/source/{filename:path}")
def get_source_video_stream(filename: str) -> FileResponse:
    """Sirve el archivo de video fuente activo desde inbox_videos, local_picks, processing o published_archive."""
    clean_name = Path(unquote(filename)).name
    if not clean_name:
        raise HTTPException(status_code=400, detail="Nombre de video inválido.")

    matched_path = _find_source_media_path(filename)
    if matched_path is not None:
        return FileResponse(str(matched_path), media_type="video/mp4")

    raise HTTPException(status_code=404, detail=f"No se encontró el video fuente '{clean_name}'.")


@app.get("/api/media/short/{short_rel_path:path}")
def get_short_video_stream(short_rel_path: str) -> FileResponse:
    """Sirve el archivo MP4 de un Short renderizado dentro de ./output_shorts/ para darle Play."""
    decoded = unquote(short_rel_path)
    out_root = OUTPUT_SHORTS_DIR.resolve()
    target = (out_root / decoded).resolve()
    if out_root not in target.parents and target != out_root:
        raise HTTPException(status_code=400, detail="Ruta de Short inválida.")
    lp_target = win_long_path(target)
    if not lp_target.exists() or not lp_target.is_file():
        raise HTTPException(status_code=404, detail="Short no encontrado en ./output_shorts/.")
    return FileResponse(str(lp_target), media_type="video/mp4")


@app.get("/api/media/thumbnail/{short_rel_path:path}")
def get_short_thumbnail(short_rel_path: str) -> Response:
    """Extrae con OpenCV una miniatura JPEG real del Short renderizado."""
    decoded = unquote(short_rel_path)
    out_root = OUTPUT_SHORTS_DIR.resolve()
    target = (out_root / decoded).resolve()
    if out_root not in target.parents and target != out_root:
        raise HTTPException(status_code=400, detail="Ruta de Short inválida.")
    lp_target = win_long_path(target)
    if not lp_target.exists() or not lp_target.is_file():
        raise HTTPException(status_code=404, detail="Short no encontrado para miniatura.")

    cap = cv2.VideoCapture(str(lp_target))
    frame = None
    if cap.isOpened():
        try:
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
            candidates = [
                min(45, max(0, total_frames // 5)),
                min(90, max(0, total_frames // 3)),
                max(0, total_frames // 2),
                min(15, max(0, total_frames // 4)),
                0,
            ]
            for cand_f in candidates:
                if cand_f > 0:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, cand_f)
                ok, read_frame = cap.read()
                if ok and read_frame is not None:
                    frame = read_frame
                    if float(read_frame.mean()) >= 18.0:
                        break
        finally:
            cap.release()

    if frame is None:
        # Fallback frame de respaldo limpio 9:16 si el contenedor es sintético vacío en un test
        frame = np.zeros((320, 180, 3), dtype=np.uint8)
        frame[:] = (28, 28, 32)

    ok_enc, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 86])
    if not ok_enc:
        raise HTTPException(status_code=500, detail="No se pudo codificar la miniatura JPEG.")
    return Response(content=buf.tobytes(), media_type="image/jpeg")


@app.get("/api/queues")
def get_distribution_queues() -> Dict[str, Any]:
    """Devuelve las colas programadas en SQLite para YouTube, Instagram y TikTok."""
    _ensure_youtube_slots_columns(DB_PATH)
    skill_ig_scheduler.init_ig_queue_db(DB_PATH)
    skill_tt_scheduler.init_tiktok_queue_db(DB_PATH)

    youtube_slots: List[Dict[str, Any]] = []
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, video_name, slot_ast, publish_at_utc, youtube_video_id, status, error, created_at_utc
            FROM scheduled_slots
            ORDER BY publish_at_utc ASC, id ASC
            """
        ).fetchall()
        youtube_slots = [dict(r) for r in rows]

    ig_queue = skill_ig_scheduler.list_queue(db_path=DB_PATH)
    tt_queue = skill_tt_scheduler.list_queue(db_path=DB_PATH)
    fb_queue = social_hub.list_facebook_queue(db_path=DB_PATH)

    for row in youtube_slots:
        row["permalink"] = _extract_row_permalink("youtube", row)
    for row in ig_queue:
        row["permalink"] = _extract_row_permalink("instagram", row)
    for row in tt_queue:
        row["permalink"] = _extract_row_permalink("tiktok", row)
    for row in fb_queue:
        row["permalink"] = _extract_row_permalink("facebook", row)

    return {
        "youtube_slots": youtube_slots,
        "instagram_queue": ig_queue,
        "tiktok_queue": tt_queue,
        "facebook_queue": fb_queue,
    }


_SOCIAL_DISPATCH_LOCK = threading.Lock()
_SOCIAL_DAEMON_STARTED = False


def run_due_social_queues() -> Dict[str, Any]:
    """Ejecuta de forma serializada el despacho de publicaciones vencidas en Instagram, TikTok y Facebook."""
    with _SOCIAL_DISPATCH_LOCK:
        try:
            ig_res = skill_ig_scheduler.process_due_instagram_queue(db_path=DB_PATH, force_all=False)
        except Exception as exc:
            logger.warning("Aviso despachando cola de Instagram: %s", exc)
            ig_res = {"processed": 0, "published": 0, "failed": 0, "error": str(exc)}

        try:
            tt_res = skill_tt_scheduler.process_due_tiktok_queue(db_path=DB_PATH, force_all=False)
        except Exception as exc:
            logger.warning("Aviso despachando cola de TikTok: %s", exc)
            tt_res = {"processed": 0, "published": 0, "failed": 0, "error": str(exc)}

        try:
            fb_res = social_hub.process_due_facebook_queue(
                db_path=DB_PATH,
                config_dir=CONFIG_DIR,
                force_all=False,
            )
        except Exception as exc:
            logger.warning("Aviso despachando cola de Facebook: %s", exc)
            fb_res = {"processed": 0, "published": 0, "failed": 0, "error": str(exc)}

        try:
            tt_wa_res = skill_tt_wa.tick_tiktok_whatsapp_workflow(
                db_path=DB_PATH,
                config_dir=CONFIG_DIR,
            )
        except Exception as exc:
            logger.warning("Aviso coordinando WhatsApp TikTok Studio: %s", exc)
            tt_wa_res = {"action": "error", "error": str(exc)}

    return {
        "instagram": ig_res,
        "tiktok": tt_res,
        "facebook": fb_res,
        "tiktok_whatsapp": tt_wa_res,
    }


def _start_social_scheduler_daemon() -> None:
    """Inicia el bucle en segundo plano cada 30s para publicar colas sociales programadas al vencer."""
    global _SOCIAL_DAEMON_STARTED
    if _SOCIAL_DAEMON_STARTED or os.environ.get("PYTEST_CURRENT_TEST"):
        return
    _SOCIAL_DAEMON_STARTED = True

    def _loop() -> None:
        time.sleep(8)
        while True:
            try:
                run_due_social_queues()
            except Exception as exc:
                logger.warning("Aviso en ciclo scheduler social: %s", exc)
            time.sleep(30)

    threading.Thread(target=_loop, daemon=True, name="short_yt_social_scheduler").start()


@app.get("/api/social-accounts")
def get_social_accounts_hub() -> Dict[str, Any]:
    """Devuelve las categorías de cuentas (Principales, Gaming, Clipping, OMETV y personalizadas) y sus APIs enmascaradas."""
    return social_hub.get_public_social_hub_config(CONFIG_DIR)


@app.put("/api/social-accounts")
def update_social_accounts_hub(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Guarda cuentas por categoría, palabras clave de tema y credenciales API preservando secretos enmascarados."""
    try:
        return social_hub.save_social_hub_config(CONFIG_DIR, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/social-accounts/categories")
def create_social_account_category(req: CreateSocialCategoryRequest) -> Dict[str, Any]:
    """Crea una nueva categoría editorial para distribuir cuentas y Shorts."""
    try:
        created_cat, public_hub = social_hub.create_social_category(
            CONFIG_DIR,
            label=req.label,
            key=req.key,
            description=req.description,
            topic_keywords=req.topic_keywords,
        )
        return {"created": created_cat, **public_hub}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/social-accounts/categories/{category_key}")
def delete_social_account_category(category_key: str) -> Dict[str, Any]:
    """Elimina una categoría personalizada (protege las categorías base del sistema)."""
    try:
        public_hub = social_hub.delete_social_category(CONFIG_DIR, category_key)
        return {"deleted": category_key, **public_hub}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/social-accounts/verify")
def verify_social_platform_endpoint(req: VerifyPlatformRequest) -> Dict[str, Any]:
    """Comprueba la configuración y tokens activos de la plataforma indicada."""
    try:
        return social_hub.verify_platform_connection(CONFIG_DIR, req.platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


_youtube_retry_thread: Optional[threading.Thread] = None
_YOUTUBE_RETRY_LOCK = threading.Lock()


def _find_short_mp4_by_name(video_name: str) -> Optional[Path]:
    """Busca el archivo MP4 renderizado correspondiente a un slot por filename dentro de OUTPUT_SHORTS_DIR."""
    if not video_name or not OUTPUT_SHORTS_DIR.exists():
        return None
    for candidate in sorted(OUTPUT_SHORTS_DIR.rglob(video_name)):
        if candidate.is_file() and not candidate.name.startswith(("_rendering_", "_tmp_")):
            return candidate
    return None


def _run_youtube_retry_batch(eligible: List[Dict[str, Any]]) -> int:
    """Ejecuta la subida a YouTube Shorts para una lista de slots pendientes/fallidos respetando publish_at_utc."""
    hub_cfg = social_hub.get_raw_social_hub_config(CONFIG_DIR)
    category_id = str(
        hub_cfg.get("api_settings", {}).get("youtube", {}).get("default_category_id") or "22"
    )
    uploaded = 0
    with _YOUTUBE_RETRY_LOCK:
        for item in eligible:
            slot_id = int(item["id"])
            fname = str(item["video_name"])
            mp4_path = Path(item["mp4_path"])
            publish_at_utc = str(item.get("publish_at_utc") or "").strip()
            if not mp4_path.exists():
                continue
            hook_title_val = None
            meta_lp = win_long_path(mp4_path.with_name(f"{mp4_path.stem}_meta.json"))
            if meta_lp.exists():
                try:
                    meta_obj = json.loads(meta_lp.read_text(encoding="utf-8"))
                    hook_title_val = meta_obj.get("hook_title")
                except Exception:
                    pass
            clean_title = str(hook_title_val or mp4_path.stem.replace("_", " "))
            hook_title = clean_title if "#Shorts" in clean_title else f"{clean_title[:75]} #Shorts"
            caption_txt = f"🔥 {clean_title} 👇\n\n#Viral #Shorts"
            try:
                up_resp = skill_uploader.upload_scheduled_short(
                    video_path=mp4_path,
                    title=hook_title[:95],
                    description=caption_txt,
                    tags=["CreadorStudio", "Shorts", "Viral"],
                    publish_at_iso=publish_at_utc,
                    category_id=category_id,
                    client_secret_path=CONFIG_DIR / "client_secret.json",
                    token_path=CONFIG_DIR / "token.json",
                    allow_interactive=False,
                )
                final_yt_id = up_resp.get("id")
                with sqlite3.connect(str(DB_PATH)) as conn:
                    if final_yt_id:
                        conn.execute(
                            "UPDATE scheduled_slots SET youtube_video_id = ?, status = 'PUBLISHED', error = NULL WHERE id = ?",
                            (final_yt_id, slot_id),
                        )
                        uploaded += 1
                    else:
                        conn.execute(
                            "UPDATE scheduled_slots SET status = 'FAILED', error = ? WHERE id = ?",
                            ("YouTube no devolvió video_id tras reintentar OAuth.", slot_id),
                        )
                    conn.commit()
            except Exception as exc:
                err_txt = str(exc).strip() or "Error al reintentar subida a YouTube."
                logger.warning("Aviso reintentando slot YouTube %s (%s): %s", slot_id, fname, err_txt)
                with sqlite3.connect(str(DB_PATH)) as conn:
                    conn.execute(
                        "UPDATE scheduled_slots SET status = 'FAILED', error = ? WHERE id = ?",
                        (err_txt, slot_id),
                    )
                    conn.commit()
    return uploaded


def _retry_pending_youtube_slots(sync_mode: bool = False) -> int:
    """Reintenta subir en YouTube los scheduled_slots sin youtube_video_id (FAILED o PENDING)."""
    global _youtube_retry_thread
    if not DB_PATH.exists():
        return 0
    _ensure_youtube_slots_columns(DB_PATH)
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT id, video_name, publish_at_utc, status
                FROM scheduled_slots
                WHERE (youtube_video_id IS NULL OR TRIM(youtube_video_id) = '')
                  AND UPPER(COALESCE(status, 'PENDING')) IN ('FAILED', 'PENDING')
                ORDER BY publish_at_utc ASC, id ASC
                """
            ).fetchall()
        ]

    eligible: List[Dict[str, Any]] = []
    for r in rows:
        mp4_path = _find_short_mp4_by_name(str(r.get("video_name") or ""))
        if mp4_path is not None:
            eligible.append({**r, "mp4_path": mp4_path})

    if not eligible:
        return 0

    if not sync_mode:
        slot_ids = [(int(item["id"]),) for item in eligible]
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.executemany(
                "UPDATE scheduled_slots SET status = 'PROCESSING', error = NULL WHERE id = ?",
                slot_ids,
            )
            conn.commit()
        t = threading.Thread(
            target=_run_youtube_retry_batch,
            args=(eligible,),
            daemon=True,
            name="youtube-oauth-retry",
        )
        _youtube_retry_thread = t
        t.start()
        return len(eligible)

    return _run_youtube_retry_batch(eligible)


@app.post("/api/social-accounts/youtube/authorize")
def authorize_youtube_oauth_endpoint() -> Dict[str, Any]:
    """Abre el flujo OAuth 2.0 local de YouTube bajo demanda (máx. 120s), guarda token.json y reintenta slots pendientes."""
    try:
        skill_uploader.get_authenticated_youtube_service(
            client_secret_path=CONFIG_DIR / "client_secret.json",
            token_path=CONFIG_DIR / "token.json",
            allow_interactive=True,
            oauth_timeout_sec=120,
        )
        verify_res = social_hub.verify_platform_connection(CONFIG_DIR, "youtube")
        retried_count = 0
        if verify_res.get("connected"):
            retried_count = _retry_pending_youtube_slots(sync_mode=False)
        return {**verify_res, "retried_youtube_slots": retried_count}
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo autorizar YouTube OAuth: {exc}") from exc


try:
    from google_auth_oauthlib.flow import (
        _ExclusiveWSGIServer as _OAuthWSGIServer,
        _WSGIRequestHandler as _OAuthWSGIHandler,
    )
except ImportError:  # pragma: no cover - fallback a WSGIServer estándar
    _OAuthWSGIServer = wsgiref.simple_server.WSGIServer  # type: ignore[misc, assignment]
    _OAuthWSGIHandler = wsgiref.simple_server.WSGIRequestHandler  # type: ignore[misc, assignment]


_YOUTUBE_OAUTH_LOCK = threading.Lock()
_youtube_oauth_waiter_thread: Optional[threading.Thread] = None
_YOUTUBE_OAUTH_SESSION: Dict[str, Any] = {
    "oauth_state": "idle",
    "platform": "youtube",
    "connected": False,
    "status_label": "Sin autorizar",
    "detail": "",
    "auth_url": None,
    "error": None,
    "retried_youtube_slots": 0,
    "cancel_event": None,
}


def _public_youtube_oauth_status() -> Dict[str, Any]:
    with _YOUTUBE_OAUTH_LOCK:
        return {
            "oauth_state": str(_YOUTUBE_OAUTH_SESSION.get("oauth_state") or "idle"),
            "platform": "youtube",
            "connected": bool(_YOUTUBE_OAUTH_SESSION.get("connected", False)),
            "status_label": str(_YOUTUBE_OAUTH_SESSION.get("status_label") or "Sin autorizar"),
            "detail": str(_YOUTUBE_OAUTH_SESSION.get("detail") or ""),
            "auth_url": _YOUTUBE_OAUTH_SESSION.get("auth_url"),
            "error": _YOUTUBE_OAUTH_SESSION.get("error"),
            "retried_youtube_slots": int(_YOUTUBE_OAUTH_SESSION.get("retried_youtube_slots") or 0),
        }


def _close_active_youtube_oauth_server() -> None:
    """Cancela cualquier servidor callback OAuth activo de YouTube y espera su cierre ordenado."""
    global _youtube_oauth_waiter_thread
    waiter: Optional[threading.Thread] = None
    with _YOUTUBE_OAUTH_LOCK:
        cancel_evt = _YOUTUBE_OAUTH_SESSION.get("cancel_event")
        if isinstance(cancel_evt, threading.Event):
            cancel_evt.set()
        waiter = _youtube_oauth_waiter_thread
        _YOUTUBE_OAUTH_SESSION["cancel_event"] = None
        _youtube_oauth_waiter_thread = None
    if waiter is not None and waiter.is_alive() and waiter is not threading.current_thread():
        waiter.join(timeout=1.5)


class _YouTubeOAuthCallbackApp:
    """WSGI mínimo para capturar la redirección OAuth de Google ignorando favicon/precargas."""

    def __init__(self) -> None:
        self.callback_uri: Optional[str] = None

    def __call__(self, environ: Dict[str, Any], start_response: Any) -> List[bytes]:
        qs = parse_qs(str(environ.get("QUERY_STRING") or ""))
        if "code" not in qs and "error" not in qs:
            start_response("204 No Content", [("Content-Length", "0")])
            return [b""]

        self.callback_uri = wsgiref.util.request_uri(environ)
        has_error = "error" in qs and "code" not in qs
        title_txt = (
            "Autorización de YouTube no completada"
            if has_error
            else "YouTube conectado correctamente"
        )
        body_txt = (
            f"Google devolvió: {qs['error'][0]}. Vuelve a Auto-Clipper Studio e inténtalo de nuevo."
            if has_error
            else "Ya guardamos tus credenciales y estamos reintentando tus Shorts pendientes. Puedes cerrar esta pestaña."
        )
        html_doc = f"""<!doctype html>
<html lang="es">
<head><meta charset="utf-8"><title>{title_txt}</title></head>
<body style="margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#090B10;color:#F4F4F5;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;text-align:center;padding:24px;">
  <div style="max-width:440px;background:#11151F;border:1px solid rgba(255,255,255,0.12);border-radius:16px;padding:28px;">
    <h1 style="font-size:18px;margin:0 0 10px 0;">{title_txt}</h1>
    <p style="font-size:14px;color:#A1A1AA;line-height:1.5;margin:0;">{body_txt}</p>
  </div>
  <script>
    try {{
      if (window.opener && typeof window.opener.postMessage === 'function') {{
        window.opener.postMessage({{ type: 'SHORTYT_YOUTUBE_OAUTH_DONE' }}, '*');
      }}
    }} catch (e) {{}}
    setTimeout(function() {{ try {{ window.close(); }} catch (e) {{}} }}, 1200);
  </script>
</body>
</html>"""
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [html_doc.encode("utf-8")]


@app.post("/api/social-accounts/youtube/oauth/start")
def start_youtube_oauth_browser_flow() -> Dict[str, Any]:
    """
    Inicia OAuth 2.0 de YouTube sin bloquear el servidor HTTP ni depender de webbrowser.open() en daemon:
    devuelve de inmediato auth_url para abrirlo en el navegador del usuario y espera el callback en segundo plano.
    """
    global _youtube_oauth_waiter_thread

    secret_path = CONFIG_DIR / "client_secret.json"
    token_path = CONFIG_DIR / "token.json"

    # 1) Si el token ya es válido o refresca silenciosamente, completar al instante
    try:
        skill_uploader.get_authenticated_youtube_service(
            client_secret_path=secret_path,
            token_path=token_path,
            allow_interactive=False,
        )
        _close_active_youtube_oauth_server()
        verify_res = social_hub.verify_platform_connection(CONFIG_DIR, "youtube")
        retried_count = (
            _retry_pending_youtube_slots(sync_mode=False) if verify_res.get("connected") else 0
        )
        with _YOUTUBE_OAUTH_LOCK:
            _YOUTUBE_OAUTH_SESSION.update(
                {
                    "oauth_state": "completed",
                    "connected": bool(verify_res.get("connected")),
                    "status_label": str(verify_res.get("status_label") or "Conectado"),
                    "detail": str(verify_res.get("detail") or ""),
                    "auth_url": None,
                    "error": None,
                    "retried_youtube_slots": retried_count,
                    "cancel_event": None,
                }
            )
        return _public_youtube_oauth_status()
    except Exception:
        pass

    if not secret_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"No se encontró './config/client_secret.json' en {secret_path}. Configúralo en Cuentas & APIs.",
        )

    _close_active_youtube_oauth_server()

    try:
        flow = skill_uploader.InstalledAppFlow.from_client_secrets_file(
            str(secret_path), skill_uploader.SCOPES
        )
        wsgi_app = _YouTubeOAuthCallbackApp()
        local_server = wsgiref.simple_server.make_server(
            "localhost",
            0,
            wsgi_app,
            server_class=_OAuthWSGIServer,
            handler_class=_OAuthWSGIHandler,
        )
        local_server.timeout = 0.25
        port = int(local_server.server_port)
        flow.redirect_uri = f"http://localhost:{port}/"
        auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"No se pudo iniciar la URL OAuth 2.0 de YouTube: {exc}",
        ) from exc

    cancel_evt = threading.Event()
    with _YOUTUBE_OAUTH_LOCK:
        _YOUTUBE_OAUTH_SESSION.update(
            {
                "oauth_state": "pending",
                "connected": False,
                "status_label": "Esperando confirmación en Google",
                "detail": "Autoriza tu canal en la pestaña de Google que acabamos de abrir.",
                "auth_url": auth_url,
                "error": None,
                "retried_youtube_slots": 0,
                "cancel_event": cancel_evt,
            }
        )

    def _wait_for_google_callback() -> None:
        deadline = time.monotonic() + 180.0
        try:
            while (
                time.monotonic() < deadline
                and not cancel_evt.is_set()
                and wsgi_app.callback_uri is None
            ):
                local_server.handle_request()

            if cancel_evt.is_set():
                return

            if not wsgi_app.callback_uri:
                with _YOUTUBE_OAUTH_LOCK:
                    if _YOUTUBE_OAUTH_SESSION.get("cancel_event") is cancel_evt:
                        _YOUTUBE_OAUTH_SESSION.update(
                            {
                                "oauth_state": "error",
                                "connected": False,
                                "status_label": "Tiempo agotado",
                                "detail": "Tiempo agotado (180s) esperando confirmación de Google.",
                                "error": "Tiempo agotado (180s) esperando confirmación en Google. Pulsa 'Conectar YouTube OAuth' para intentarlo de nuevo.",
                                "auth_url": None,
                                "cancel_event": None,
                            }
                        )
                return

            cb_qs = parse_qs(urllib.parse.urlparse(wsgi_app.callback_uri).query)
            if "error" in cb_qs and "code" not in cb_qs:
                err_code = str(cb_qs["error"][0])
                with _YOUTUBE_OAUTH_LOCK:
                    if _YOUTUBE_OAUTH_SESSION.get("cancel_event") is cancel_evt:
                        _YOUTUBE_OAUTH_SESSION.update(
                            {
                                "oauth_state": "error",
                                "connected": False,
                                "status_label": "Autorización denegada",
                                "detail": f"Google rechazó o canceló el acceso ({err_code}).",
                                "error": f"Google rechazó o canceló la autorización OAuth ({err_code}).",
                                "auth_url": None,
                                "cancel_event": None,
                            }
                        )
                return

            auth_resp = wsgi_app.callback_uri.replace("http://", "https://", 1)
            flow.fetch_token(authorization_response=auth_resp)
            creds = flow.credentials
            if not creds or not creds.valid:
                raise RuntimeError("No se obtuvieron credenciales OAuth 2.0 válidas tras autorizar.")
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json(), encoding="utf-8")

            verify_res = social_hub.verify_platform_connection(CONFIG_DIR, "youtube")
            retried_count = (
                _retry_pending_youtube_slots(sync_mode=False) if verify_res.get("connected") else 0
            )
            with _YOUTUBE_OAUTH_LOCK:
                if _YOUTUBE_OAUTH_SESSION.get("cancel_event") is cancel_evt:
                    _YOUTUBE_OAUTH_SESSION.update(
                        {
                            "oauth_state": "completed",
                            "connected": bool(verify_res.get("connected")),
                            "status_label": str(verify_res.get("status_label") or "Conectado"),
                            "detail": str(verify_res.get("detail") or ""),
                            "auth_url": None,
                            "error": None,
                            "retried_youtube_slots": retried_count,
                            "cancel_event": None,
                        }
                    )
        except Exception as exc:
            logger.warning("Fallo completando callback OAuth de YouTube: %s", exc)
            with _YOUTUBE_OAUTH_LOCK:
                if _YOUTUBE_OAUTH_SESSION.get("cancel_event") is cancel_evt:
                    _YOUTUBE_OAUTH_SESSION.update(
                        {
                            "oauth_state": "error",
                            "connected": False,
                            "status_label": "Error OAuth",
                            "detail": str(exc),
                            "error": f"No se pudo completar OAuth de YouTube: {exc}",
                            "auth_url": None,
                            "cancel_event": None,
                        }
                    )
        finally:
            try:
                local_server.server_close()
            except Exception:
                pass

    waiter = threading.Thread(
        target=_wait_for_google_callback,
        daemon=True,
        name="youtube-oauth-callback-waiter",
    )
    _youtube_oauth_waiter_thread = waiter
    waiter.start()
    return _public_youtube_oauth_status()


@app.get("/api/social-accounts/youtube/oauth/status")
def get_youtube_oauth_browser_status() -> Dict[str, Any]:
    """Consulta el estado actual del flujo OAuth en navegador sin bloquear."""
    return _public_youtube_oauth_status()


@app.post("/api/social-accounts/youtube/oauth/cancel")
def cancel_youtube_oauth_browser_flow() -> Dict[str, Any]:
    """Cancela la espera OAuth de YouTube en curso y cierra el puerto temporal."""
    _close_active_youtube_oauth_server()
    with _YOUTUBE_OAUTH_LOCK:
        _YOUTUBE_OAUTH_SESSION.update(
            {
                "oauth_state": "idle",
                "connected": False,
                "status_label": "Cancelado",
                "detail": "Autorización OAuth cancelada.",
                "auth_url": None,
                "error": None,
                "retried_youtube_slots": 0,
                "cancel_event": None,
            }
        )
    return _public_youtube_oauth_status()


class TikTokStudioDispatchRequest(BaseModel):
    user_permission_granted: bool = False
    row_ids: Optional[List[int]] = None


_TIKTOK_STUDIO_LOCK = threading.Lock()
_tiktok_studio_proc: Any = None
_tiktok_studio_last: Dict[str, Any] = {"dispatched_at": None, "row_ids": []}


def _resolve_playwright_python() -> str:
    """Devuelve el intérprete Python del sistema que dispone de Playwright para Brave."""
    local_app = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    for py_dir in sorted(local_app.glob("Programs/Python/Python3*"), reverse=True):
        cand = py_dir / "python.exe"
        if cand.exists():
            return str(cand)
    found = shutil.which("python")
    return found or sys.executable


@app.post("/api/social-accounts/tiktok/studio-dispatch")
def dispatch_tiktok_studio_browser(
    req: TikTokStudioDispatchRequest = Body(default_factory=TikTokStudioDispatchRequest),
) -> Dict[str, Any]:
    """
    Lanza la subida/programación en TikTok Studio Web vía Brave únicamente cuando el usuario
    confirma explícitamente permiso de uso de su navegador (`user_permission_granted=True`).
    """
    global _tiktok_studio_proc
    if not req.user_permission_granted:
        raise HTTPException(
            status_code=400,
            detail="Permiso explícito del usuario requerido antes de abrir Brave y publicar en TikTok Studio.",
        )

    skill_tt_scheduler.init_tiktok_queue_db(DB_PATH)
    script_path = SKILLS_DIR / "multi-social-uploader" / "tiktok_studio_browser.py"
    if not script_path.exists():
        raise HTTPException(status_code=500, detail=f"Falta script {script_path}")

    with sqlite3.connect(str(DB_PATH)) as conn:
        if req.row_ids:
            ph = ",".join("?" for _ in req.row_ids)
            eligible = [
                int(r[0])
                for r in conn.execute(
                    f"SELECT id FROM tiktok_scheduled_queue WHERE id IN ({ph}) ORDER BY scheduled_time_utc ASC, id ASC",
                    tuple(int(x) for x in req.row_ids),
                ).fetchall()
            ]
        else:
            eligible = [
                int(r[0])
                for r in conn.execute(
                    "SELECT id FROM tiktok_scheduled_queue WHERE UPPER(COALESCE(status, 'PENDING')) IN ('PENDING', 'INBOX_DRAFT', 'FAILED') ORDER BY scheduled_time_utc ASC, id ASC"
                ).fetchall()
            ]

    if not eligible:
        return {
            "dispatched": False,
            "count": 0,
            "row_ids": [],
            "detail": "No hay entregas de TikTok pendientes ni en borrador para subir.",
        }

    with _TIKTOK_STUDIO_LOCK:
        if _tiktok_studio_proc is not None and _tiktok_studio_proc.poll() is None:
            raise HTTPException(
                status_code=409,
                detail="Ya hay una automatización de TikTok Studio en curso en Brave.",
            )
        cmd = [
            _resolve_playwright_python(),
            str(script_path),
            "--db-path",
            str(DB_PATH),
            "--row-ids",
            ",".join(str(x) for x in eligible),
        ]
        _tiktok_studio_proc = subprocess.Popen(cmd, cwd=str(BASE_DIR))
        _tiktok_studio_last["dispatched_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _tiktok_studio_last["row_ids"] = eligible

    return {
        "dispatched": True,
        "count": len(eligible),
        "row_ids": eligible,
        "detail": f"Despachando {len(eligible)} entrega(s) en TikTok Studio Web vía Brave.",
    }


@app.get("/api/social-accounts/tiktok/studio-status")
def get_tiktok_studio_browser_status() -> Dict[str, Any]:
    """Consulta si el proceso de automatización en navegador de TikTok Studio sigue ejecutándose."""
    with _TIKTOK_STUDIO_LOCK:
        running = bool(_tiktok_studio_proc is not None and _tiktok_studio_proc.poll() is None)
        return {
            "running": running,
            "last_dispatched_at": _tiktok_studio_last.get("dispatched_at"),
            "row_ids": list(_tiktok_studio_last.get("row_ids") or []),
        }


class TikTokWhatsAppReplyRequest(BaseModel):
    text: str
    msg_id: str = ""


@app.post("/api/social-accounts/tiktok/whatsapp-reply")
def receive_tiktok_whatsapp_permission_reply(req: TikTokWhatsAppReplyRequest) -> Dict[str, Any]:
    """Recibe una respuesta aprobada/declinada reenviada desde el puente WhatsApp."""
    return skill_tt_wa.apply_whatsapp_permission_decision(
        text=req.text,
        msg_id=req.msg_id,
        db_path=DB_PATH,
        config_dir=CONFIG_DIR,
    )


@app.get("/api/social-accounts/tiktok/whatsapp-status")
def get_tiktok_whatsapp_approval_status() -> Dict[str, Any]:
    """Consulta el estado del coordinador de autorización por WhatsApp para TikTok Studio."""
    return skill_tt_wa.get_whatsapp_approval_public_status(config_dir=CONFIG_DIR)


def _init_layout_presets_db() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS layout_presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                layout_mode TEXT NOT NULL,
                cam_box_norm TEXT NOT NULL,
                content_box_norm TEXT NOT NULL,
                cam_overlay_pos TEXT NOT NULL,
                subtitle_preset TEXT NOT NULL,
                subtitle_position TEXT NOT NULL,
                created_at_utc TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _resolve_studio_video_path(video_filename: str) -> Path:
    return _resolve_local_video_path(video_filename, allow_processing=True)


def _extract_scene_frame_and_boxes(
    video_path: Path,
    timestamp_sec: Optional[float] = None,
    frame_tag: Optional[str] = None,
) -> Dict[str, Any]:
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(str(video_path))
    w, h = 1920, 1080
    frame = None
    fps = 30.0
    total_frames = 0
    target_sec = float(timestamp_sec or 0.0)
    duration_sec: Optional[float] = None
    if cap.isOpened():
        try:
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
            fps = float(cap.get(cv2.CAP_PROP_FPS)) or 30.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
            if total_frames > 0:
                duration_sec = round(float(total_frames) / max(1.0, fps), 2)
            target_f = (
                max(0, min(max(0, total_frames - 1), int(round(timestamp_sec * fps))))
                if timestamp_sec is not None
                else min(max(0, total_frames // 5), int(fps * 15))
            )
            target_sec = float(target_f) / max(1.0, fps)
            if target_f > 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, target_f)
            ok, read_f = cap.read()
            if not ok or read_f is None:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, read_f = cap.read()
            if ok and read_f is not None:
                frame = read_f
        finally:
            cap.release()

    if frame is None:
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame[:] = (24, 24, 28)
        w, h = 1280, 720

    frames_dir = CONFIG_DIR / "scene_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = re.sub(r"[^a-zA-Z0-9_-]", "_", video_path.stem)[:60] or "scene"
    raw_tag = frame_tag if frame_tag is not None else f"t{int(round(max(0.0, target_sec) * 10))}"
    safe_tag = re.sub(r"[^a-zA-Z0-9_-]", "_", str(raw_tag))[:24] or "t0"
    out_jpg = frames_dir / f"{safe_stem}__{safe_tag}.jpg"
    cv2.imwrite(str(out_jpg), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])

    return _analyze_scene_image_frame(
        frame=frame,
        video_filename=video_path.name,
        frame_url=f"/api/media/scene-frame?video_filename={quote(video_path.name)}&scene_tag={quote(safe_tag)}",
        video_path=video_path,
        target_sec=target_sec,
        duration_sec=duration_sec,
        frame_source="local_video",
    )


def _analyze_scene_image_frame(
    *,
    frame: np.ndarray,
    video_filename: str,
    frame_url: str,
    video_path: Optional[Path] = None,
    target_sec: float = 0.0,
    duration_sec: Optional[float] = None,
    frame_source: str = "local_video",
) -> Dict[str, Any]:
    """Detecta rostros y propone cajas normalizadas de cámara y contenido sobre cualquier fotograma 16:9."""
    h, w = frame.shape[:2] if frame is not None and frame.size > 0 else (720, 1280)
    faces_count = 0
    cam_box = (int(w * 0.02), int(h * 0.35), int(w * 0.26), int(h * 0.35))
    content_box = (int(w * 0.28), int(h * 0.05), int(w * 0.70), int(h * 0.90))
    detected_layout = "fullscreen"

    try:
        tracker = skill_renderer.SpeakerFaceTracker()
        try:
            faces = tracker.extract_bboxes_px(frame, allow_profile=False)
            if not faces and w >= 480:
                left_slice = frame[:, : int(w * 0.35)]
                right_slice = frame[:, int(w * 0.65) :]
                faces_l = tracker.extract_bboxes_px(left_slice, allow_profile=False)
                faces_r = [
                    (int(w * 0.65) + bx, by, bw, bh)
                    for (bx, by, bw, bh) in tracker.extract_bboxes_px(right_slice, allow_profile=False)
                ]
                faces = faces_l + faces_r
        finally:
            tracker.close()

        faces_count = len(faces)
        auto_info: Dict[str, Any] = {}
        if video_path is not None:
            auto_info = skill_renderer.detect_video_layout_and_regions(
                video_path=video_path,
                start_time=max(0.0, float(target_sec) - 1.5),
                end_time=float(target_sec) + 2.5,
                layout_mode="auto",
            )
            detected_layout = str(auto_info.get("mode", "fullscreen"))
        elif len(faces) >= 2:
            detected_layout = "split_50_50"
        elif len(faces) == 1:
            fx, _, fw, _ = faces[0]
            cx_ratio = (fx + fw / 2.0) / max(1.0, float(w))
            detected_layout = "split_streamer" if (cx_ratio < 0.34 or cx_ratio > 0.66) else "fullscreen"

        single_face_veto = len(faces) == 1 and detected_layout in ("podcast_dynamic", "split_50_50")
        if single_face_veto:
            detected_layout = "fullscreen"

        if detected_layout == "podcast_dynamic":
            if auto_info.get("split_left_box"):
                cam_box = tuple(int(v) for v in auto_info["split_left_box"])
            if auto_info.get("split_right_box"):
                content_box = tuple(int(v) for v in auto_info["split_right_box"])
        elif not single_face_veto:
            if auto_info.get("cam_box"):
                cam_box = tuple(int(v) for v in auto_info["cam_box"])
            if auto_info.get("content_box"):
                content_box = tuple(int(v) for v in auto_info["content_box"])
            elif auto_info.get("crop_box"):
                content_box = tuple(int(v) for v in auto_info["crop_box"])

        if faces and (single_face_veto or not auto_info.get("cam_box")) and detected_layout not in ("podcast_dynamic",):
            fx, fy, fw, fh = max(faces, key=lambda b: b[2] * b[3])
            face_cx = fx + fw / 2.0
            pad_x = int(fw * 1.15)
            pad_y = int(fh * 0.95)
            cx = max(0, fx - pad_x)
            cy = max(0, fy - int(fh * 0.65))
            cw = min(w - cx, fw + pad_x * 2)
            ch = min(h - cy, fh + pad_y * 2)
            cam_box = (cx, cy, max(64, cw), max(64, ch))
            if len(faces) == 1 and (face_cx < w * 0.32 or face_cx > w * 0.68):
                detected_layout = "gaming_hud" if cw < w * 0.45 else "split_streamer"
                if cx < w * 0.35:
                    x0 = min(w // 3, cx + cw)
                    content_box = (x0, 0, max(64, w - x0), h)
                else:
                    content_box = (0, 0, max(64, int(w * 0.72)), h)
    except Exception as exc:
        logger.warning("Detección de escena fallback (%s)", exc)

    cam_norm = [
        round(cam_box[0] / w, 4),
        round(cam_box[1] / h, 4),
        round(cam_box[2] / w, 4),
        round(cam_box[3] / h, 4),
    ]
    content_norm = [
        round(content_box[0] / w, 4),
        round(content_box[1] / h, 4),
        round(content_box[2] / w, 4),
        round(content_box[3] / h, 4),
    ]
    return {
        "video_filename": video_filename,
        "resolution": f"{w}x{h}",
        "width": w,
        "height": h,
        "detected_layout": detected_layout,
        "faces_detected": faces_count,
        "cam_box_norm": cam_norm,
        "content_box_norm": content_norm,
        "frame_url": frame_url,
        "timestamp_sec": round(float(target_sec), 2),
        "duration_sec": round(float(duration_sec), 2) if isinstance(duration_sec, (int, float)) and duration_sec > 0 else None,
        "frame_source": frame_source,
    }


def _extract_frame_via_ffmpeg(
    stream_url: str,
    target_sec: float,
    http_headers: Optional[Dict[str, str]] = None,
) -> Optional[np.ndarray]:
    """Extrae un único fotograma real en target_sec desde un stream HTTP/archivo local usando ffmpeg."""
    ffmpeg_bin = str(getattr(skill_renderer, "FFMPEG_BIN", "ffmpeg") or "ffmpeg")
    cmd: List[str] = [ffmpeg_bin, "-hide_banner", "-loglevel", "error"]
    if str(stream_url).lower().startswith(("http://", "https://")):
        cmd.extend(["-rw_timeout", "8000000"])
        if http_headers:
            header_blob = "".join(
                f"{str(k).strip()}: {str(v).strip()}\r\n"
                for k, v in http_headers.items()
                if k and v is not None
            )
            if header_blob:
                cmd.extend(["-headers", header_blob])
    cmd.extend(
        [
            "-ss",
            f"{max(0.0, float(target_sec)):.3f}",
            "-i",
            str(stream_url),
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "-q:v",
            "2",
            "pipe:1",
        ]
    )
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=14,
            check=False,
            **skill_renderer._silent_subprocess_kwargs(),
        )
        if proc.returncode == 0 and proc.stdout:
            arr = np.frombuffer(proc.stdout, dtype=np.uint8)
            decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if decoded is not None and decoded.size > 0:
                return decoded
    except Exception as exc:
        logger.info("ffmpeg frame extract fallback en %ss: %s", target_sec, exc)
    return None


def _extract_remote_scene_frame_and_boxes(
    raw_url: str,
    timestamp_sec: Optional[float] = None,
) -> Dict[str, Any]:
    """Extrae un fotograma real en cualquier segundo del stream remoto (o thumbnail fallback) para el Studio."""
    was_cached = raw_url in _REMOTE_METADATA_CACHE
    meta = _fetch_remote_url_metadata(raw_url)
    raw_dur = meta.get("duration")
    duration_sec: Optional[float] = (
        round(float(raw_dur), 2) if isinstance(raw_dur, (int, float)) and raw_dur > 0 else None
    )

    if timestamp_sec is not None:
        target_sec = max(0.0, float(timestamp_sec))
        if duration_sec is not None and duration_sec > 1.0:
            target_sec = min(target_sec, max(0.0, duration_sec - 0.5))
    elif duration_sec is not None and duration_sec > 10.0:
        target_sec = min(max(30.0, duration_sec * 0.22), max(0.0, duration_sec - 3.0))
    else:
        target_sec = min(15.0, max(0.0, (duration_sec or 15.0) * 0.35))

    frame: Optional[np.ndarray] = None
    frame_source = "synthetic_fallback"
    stream_url = str(meta.get("stream_url") or "").strip()
    http_headers = meta.get("http_headers") if isinstance(meta.get("http_headers"), dict) else None

    if stream_url:
        frame = _extract_frame_via_ffmpeg(stream_url, target_sec, http_headers)
        if frame is None and was_cached:
            _REMOTE_METADATA_CACHE.pop(raw_url, None)
            meta = _fetch_remote_url_metadata(raw_url)
            stream_url = str(meta.get("stream_url") or "").strip()
            http_headers = meta.get("http_headers") if isinstance(meta.get("http_headers"), dict) else None
            if stream_url:
                frame = _extract_frame_via_ffmpeg(stream_url, target_sec, http_headers)
        if frame is not None:
            frame_source = "video_stream"

    if frame is None:
        thumb_url = str(meta.get("thumbnail") or "").strip()
        if thumb_url.startswith(("http://", "https://")):
            try:
                req_thumb = urllib.request.Request(thumb_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req_thumb, timeout=4) as resp:
                    img_bytes = resp.read(8 * 1024 * 1024)
                arr = np.frombuffer(img_bytes, dtype=np.uint8)
                decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if decoded is not None and decoded.size > 0:
                    frame = decoded
                    frame_source = "thumbnail_fallback"
            except Exception as exc:
                logger.info("Miniatura remota fallback para %s: %s", raw_url, exc)

    if frame is None:
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame[:] = (24, 24, 28)
        frame_source = "synthetic_fallback"

    frames_dir = CONFIG_DIR / "scene_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    url_hash = hashlib.sha1(raw_url.encode("utf-8")).hexdigest()[:12]
    ts_tenths = int(round(max(0.0, target_sec) * 10))
    frame_name = f"__yt_{url_hash}_t{ts_tenths}.jpg"
    out_jpg = frames_dir / frame_name
    cv2.imwrite(str(out_jpg), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    return _analyze_scene_image_frame(
        frame=frame,
        video_filename=frame_name,
        frame_url=f"/api/media/scene-frame?video_filename={quote(frame_name)}",
        target_sec=target_sec,
        duration_sec=duration_sec,
        frame_source=frame_source,
    )


@app.get("/api/subtitles/presets")
def get_subtitle_presets() -> Dict[str, Any]:
    """Devuelve los presets de animación y estilo de subtítulos disponibles."""
    return {"presets": list(skill_renderer.SUBTITLE_STYLE_PRESETS.values())}


@app.post("/api/scene/detect")
def detect_scene_regions(req: SceneDetectRequest) -> Dict[str, Any]:
    """Extrae un fotograma 16:9 del video local o enlace remoto en el instante pedido y detecta cámara y contenido."""
    if req.source_type == "youtube_url":
        raw_url = (req.youtube_url or "").strip()
        if not raw_url or not _REMOTE_VIDEO_URL_RE.match(raw_url):
            raise HTTPException(
                status_code=400,
                detail="Debes proporcionar un enlace válido de YouTube, Twitch o Kick para calibrar el Estudio 16:9.",
            )
        return _extract_remote_scene_frame_and_boxes(raw_url, timestamp_sec=req.timestamp_sec)

    raw_file = (req.video_filename or "").strip()
    if not raw_file:
        raise HTTPException(
            status_code=400,
            detail="Debes indicar video_filename para detectar la escena.",
        )
    video_path = _resolve_studio_video_path(raw_file)
    return _extract_scene_frame_and_boxes(video_path, timestamp_sec=req.timestamp_sec)


@app.get("/api/media/scene-frame")
def get_scene_frame(video_filename: str, scene_tag: Optional[str] = None) -> Response:
    """Sirve el fotograma 16:9 JPEG para el Estudio Interactivo o pre-análisis multi-escena."""
    clean_name = Path(video_filename).name
    if clean_name.startswith("__yt_"):
        frames_base = (CONFIG_DIR / "scene_frames").resolve()
        remote_jpg = (frames_base / clean_name).resolve()
        if frames_base not in remote_jpg.parents or not remote_jpg.exists():
            raise HTTPException(status_code=404, detail="Fotograma de escena remota no disponible.")
        return Response(content=remote_jpg.read_bytes(), media_type="image/jpeg")

    video_path = _resolve_studio_video_path(video_filename)
    safe_stem = re.sub(r"[^a-zA-Z0-9_-]", "_", video_path.stem)[:60] or "scene"
    if scene_tag:
        safe_tag = re.sub(r"[^a-zA-Z0-9_-]", "_", scene_tag)[:24]
        jpg_path = CONFIG_DIR / "scene_frames" / f"{safe_stem}__{safe_tag}.jpg"
        if not jpg_path.exists():
            ts_match = re.match(r"^t(\d+)$", safe_tag)
            if ts_match:
                _extract_scene_frame_and_boxes(
                    video_path,
                    timestamp_sec=int(ts_match.group(1)) / 10.0,
                    frame_tag=safe_tag,
                )
            else:
                legacy_jpg = CONFIG_DIR / "scene_frames" / f"{safe_stem}.jpg"
                if legacy_jpg.exists():
                    jpg_path = legacy_jpg
    else:
        jpg_path = CONFIG_DIR / "scene_frames" / f"{safe_stem}.jpg"
    if not jpg_path.exists():
        det = _extract_scene_frame_and_boxes(video_path)
        det_tag = "t0"
        if "scene_tag=" in str(det.get("frame_url") or ""):
            det_tag = str(det["frame_url"]).split("scene_tag=")[-1].split("&")[0]
        alt_jpg = CONFIG_DIR / "scene_frames" / f"{safe_stem}__{det_tag}.jpg"
        if alt_jpg.exists():
            jpg_path = alt_jpg
    if not jpg_path.exists():
        raise HTTPException(status_code=404, detail="Fotograma de escena no disponible.")
    return Response(content=jpg_path.read_bytes(), media_type="image/jpeg")


@app.get("/api/content-profiles")
def list_content_profiles() -> Dict[str, Any]:
    """Lista todos los Perfiles de Contenido reutilizables guardados en SQLite."""
    return {"profiles": _list_content_profiles_from_db()}


@app.post("/api/content-profiles")
def create_content_profile(req: ContentProfilePayload) -> Dict[str, Any]:
    """Guarda un nuevo Perfil de Contenido multi-escena reutilizable en SQLite."""
    _init_content_profiles_db()
    clean_name = req.name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="El nombre del perfil no puede estar vacío.")
    keywords = _sanitize_profile_keywords(req.match_keywords, clean_name)
    scenes = _sanitize_profile_scenes_for_storage(req.scenes)
    valid_keys = _get_hub_category_keys()
    allowed_cats = social_hub.normalize_account_categories(
        req.allowed_account_categories, fallback=valid_keys, valid_keys=valid_keys
    )
    routing_cfg = {
        "auto_categorize_by_topic": bool(req.auto_categorize_by_topic),
        "allowed_account_categories": allowed_cats,
    }
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.execute(
            """
            INSERT INTO content_profiles (
                name, match_keywords, scenes_json, routing_config_json, created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                clean_name,
                json.dumps(keywords, ensure_ascii=False),
                json.dumps(scenes, ensure_ascii=False),
                json.dumps(routing_cfg, ensure_ascii=False),
                now_utc,
                now_utc,
            ),
        )
        conn.commit()
        new_id = int(cur.lastrowid)

    return {
        "id": new_id,
        "name": clean_name,
        "match_keywords": keywords,
        "scenes": scenes,
        "auto_categorize_by_topic": routing_cfg["auto_categorize_by_topic"],
        "allowed_account_categories": allowed_cats,
        "created_at_utc": now_utc,
        "updated_at_utc": now_utc,
    }


@app.put("/api/content-profiles/{profile_id}")
def update_content_profile(profile_id: int, req: ContentProfilePayload) -> Dict[str, Any]:
    """Actualiza un Perfil de Contenido existente (nombre, pistas, escenas y enrutamiento temático)."""
    _init_content_profiles_db()
    clean_name = req.name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="El nombre del perfil no puede estar vacío.")
    keywords = _sanitize_profile_keywords(req.match_keywords, clean_name)
    scenes = _sanitize_profile_scenes_for_storage(req.scenes)
    valid_keys = _get_hub_category_keys()
    allowed_cats = social_hub.normalize_account_categories(
        req.allowed_account_categories, fallback=valid_keys, valid_keys=valid_keys
    )
    routing_cfg = {
        "auto_categorize_by_topic": bool(req.auto_categorize_by_topic),
        "allowed_account_categories": allowed_cats,
    }
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        existing = conn.execute(
            "SELECT created_at_utc FROM content_profiles WHERE id = ?",
            (profile_id,),
        ).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Perfil de contenido no encontrado.")
        conn.execute(
            """
            UPDATE content_profiles
            SET name = ?, match_keywords = ?, scenes_json = ?, routing_config_json = ?, updated_at_utc = ?
            WHERE id = ?
            """,
            (
                clean_name,
                json.dumps(keywords, ensure_ascii=False),
                json.dumps(scenes, ensure_ascii=False),
                json.dumps(routing_cfg, ensure_ascii=False),
                now_utc,
                profile_id,
            ),
        )
        conn.commit()
        created_utc = str(existing["created_at_utc"])

    return {
        "id": profile_id,
        "name": clean_name,
        "match_keywords": keywords,
        "scenes": scenes,
        "auto_categorize_by_topic": routing_cfg["auto_categorize_by_topic"],
        "allowed_account_categories": allowed_cats,
        "created_at_utc": created_utc,
        "updated_at_utc": now_utc,
    }


@app.delete("/api/content-profiles/{profile_id}")
def delete_content_profile(profile_id: int) -> Dict[str, Any]:
    """Elimina un Perfil de Contenido de SQLite."""
    _init_content_profiles_db()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.execute("DELETE FROM content_profiles WHERE id = ?", (profile_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Perfil de contenido no encontrado.")
    return {"deleted": profile_id}


@app.get("/api/layout-presets")
def list_layout_presets() -> Dict[str, Any]:
    """Lista los presets de layout guardados en SQLite."""
    _init_layout_presets_db()
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM layout_presets ORDER BY id DESC"
        ).fetchall()
    presets = []
    for r in rows:
        presets.append(
            {
                "id": r["id"],
                "name": r["name"],
                "layout_mode": r["layout_mode"],
                "cam_box_norm": json.loads(r["cam_box_norm"]),
                "content_box_norm": json.loads(r["content_box_norm"]),
                "cam_overlay_pos": r["cam_overlay_pos"],
                "subtitle_preset": r["subtitle_preset"],
                "subtitle_position": r["subtitle_position"],
                "created_at_utc": r["created_at_utc"],
            }
        )
    return {"presets": presets}


@app.post("/api/layout-presets")
def create_layout_preset(req: LayoutPresetCreate) -> Dict[str, Any]:
    """Guarda un preset de encuadre + subtítulos reutilizable en SQLite."""
    _init_layout_presets_db()
    created = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.execute(
            """
            INSERT INTO layout_presets (
                name, layout_mode, cam_box_norm, content_box_norm,
                cam_overlay_pos, subtitle_preset, subtitle_position, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                req.name.strip(),
                req.layout_mode,
                json.dumps(req.cam_box_norm),
                json.dumps(req.content_box_norm),
                req.cam_overlay_pos,
                req.subtitle_preset,
                req.subtitle_position,
                created,
            ),
        )
        conn.commit()
        new_id = int(cur.lastrowid)
    return {
        "id": new_id,
        "name": req.name.strip(),
        "layout_mode": req.layout_mode,
        "cam_box_norm": req.cam_box_norm,
        "content_box_norm": req.content_box_norm,
        "cam_overlay_pos": req.cam_overlay_pos,
        "subtitle_preset": req.subtitle_preset,
        "subtitle_position": req.subtitle_position,
        "created_at_utc": created,
    }


@app.delete("/api/layout-presets/{preset_id}")
def delete_layout_preset(preset_id: int) -> Dict[str, Any]:
    """Elimina un preset guardado de SQLite."""
    _init_layout_presets_db()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cur = conn.execute("DELETE FROM layout_presets WHERE id = ?", (preset_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Preset no encontrado.")
    return {"deleted": preset_id}


def _candidates_file(project_id: Optional[str] = None) -> Path:
    pid = _normalize_project_id(project_id)
    if pid == "default":
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        return CONFIG_DIR / "candidates.json"
    p_dir = CONFIG_DIR / "projects"
    p_dir.mkdir(parents=True, exist_ok=True)
    return p_dir / f"{pid}_candidates.json"


def _render_selected_background(
    job_id: str,
    selected_candidates: List[Dict[str, Any]],
    source_video_path: Path,
    req_cfg: Dict[str, Any],
    project_id: str = "default",
) -> None:
    """Renderiza en segundo plano únicamente los candidatos seleccionados en la Bandeja Pre-Render."""
    pid = _normalize_project_id(project_id)
    state = _get_project_state(pid)
    cancel_ev = _get_project_cancel_event(pid)
    out_root = _get_project_output_dir(pid)

    state["job_id"] = job_id
    state["status"] = "RUNNING"
    state["current_video"] = source_video_path.name
    state["progress_percent"] = 10
    state["phase_label"] = "Renderizando Clips Seleccionados"
    state["step_detail"] = f"Preparando {len(selected_candidates)} clips del Studio..."
    state["short_uploads"] = {}
    _persist_pipeline_state(pid)

    clean_stem = _main_daemon_bootstrap.build_video_date_project_id(source_video_path.stem, max_len=44)
    out_dir = out_root / clean_stem
    out_dir.mkdir(parents=True, exist_ok=True)
    enable_bgm = False
    total = max(1, len(selected_candidates))
    rendered_ok_count = 0
    last_render_err: Optional[Exception] = None
    hub_cfg = social_hub.get_raw_social_hub_config(CONFIG_DIR)
    auto_by_topic = bool(req_cfg.get("auto_categorize_by_topic", True))
    allowed_cats = req_cfg.get("allowed_account_categories")
    full_video_words = getattr(skill_analyzer, "LAST_FULL_WORDS_BY_VIDEO", {}).get(
        str(source_video_path.resolve())
    )

    for idx, cand in enumerate(selected_candidates, start=1):
        if cancel_ev.is_set():
            state["status"] = "CANCELLED"
            state["source_preview_url"] = None
            state["phase_label"] = "Cancelado por el usuario"
            _persist_pipeline_state(pid)
            return

        score = int(cand.get("virality_score", 75))
        tier_tag = "Oro" if score >= 90 else ("Plata" if score >= 75 else "Meh")
        short_filename = f"{clean_stem}_{idx:02d}_{tier_tag}_{score}pts.mp4"
        state["progress_percent"] = int(15 + ((idx - 1) / total) * 75)
        state["step_detail"] = f"Renderizando Short {idx}/{total}: {cand.get('hook_title', short_filename)[:55]}"
        _persist_pipeline_state(pid)

        chosen_mood = "desactivada"
        raw_rules = req_cfg.get("category_rules")
        rules_list = raw_rules if isinstance(raw_rules, list) and len(raw_rules) > 0 else None
        cand_text = f"{cand.get('transcript_excerpt', '')} {cand.get('first_person_caption', '')}".strip()
        if rules_list:
            resolved_rule = _main_daemon_bootstrap.resolve_clip_category_rule(
                video_path=source_video_path,
                start_time=float(cand["start_time"]),
                end_time=float(cand["end_time"]),
                text=cand_text,
                title=str(cand.get("hook_title", "")),
                category_rules=rules_list,
                fallback_settings=req_cfg,
            )
            rule_cat = str(resolved_rule.get("category") or "").strip()
            cand_cat = (
                rule_cat
                if rule_cat and rule_cat != "auto"
                else str(cand.get("category", req_cfg.get("content_category", "auto")))
            )
            eff_layout = str(resolved_rule.get("layout_mode") or req_cfg.get("layout_mode", "auto"))
            eff_cam_box = resolved_rule.get("custom_cam_box_norm")
            eff_content_box = resolved_rule.get("custom_content_box_norm")
            eff_cam_pos = str(resolved_rule.get("cam_overlay_pos") or req_cfg.get("cam_overlay_pos", "top_right"))
            eff_sub_preset = str(resolved_rule.get("subtitle_preset") or req_cfg.get("subtitle_preset", "hormozi_pop"))
            eff_sub_pos = str(resolved_rule.get("subtitle_position") or req_cfg.get("subtitle_position", "auto"))
        else:
            cand_cat = str(cand.get("category", req_cfg.get("content_category", "auto")))
            eff_layout = str(req_cfg.get("layout_mode", "auto"))
            eff_cam_box = req_cfg.get("custom_cam_box_norm")
            eff_content_box = req_cfg.get("custom_content_box_norm")
            eff_cam_pos = str(req_cfg.get("cam_overlay_pos", "top_right"))
            eff_sub_preset = str(req_cfg.get("subtitle_preset", "hormozi_pop"))
            eff_sub_pos = str(req_cfg.get("subtitle_position", "auto"))

        cand_words = cand.get("word_timestamps", [])
        cand_keep = [tuple(iv) for iv in cand.get("keep_intervals", [])] or None
        refine_fn = getattr(skill_analyzer, "refine_clip_words_high_precision", None)
        if (
            callable(refine_fn)
            and (not cand_keep or len(cand_keep) <= 1)
            and source_video_path.exists()
            and source_video_path.stat().st_size >= 8192
        ):
            cand_words = refine_fn(
                video_path=source_video_path,
                start_time=float(cand["start_time"]),
                end_time=float(cand["end_time"]),
                fallback_words=cand_words,
            )
        try:
            out_mp4 = skill_renderer.render_vertical_short(
                video_path=source_video_path,
                start_time=float(cand["start_time"]),
                end_time=float(cand["end_time"]),
                word_timestamps=cand_words,
                output_dir=out_dir,
                output_filename=short_filename,
                bgm_mood=chosen_mood,
                keep_intervals=cand_keep,
                enable_bgm=enable_bgm,
                layout_mode=eff_layout,
                custom_cam_box_norm=eff_cam_box,
                custom_content_box_norm=eff_content_box,
                cam_overlay_pos=eff_cam_pos,
                subtitle_preset=eff_sub_preset,
                subtitle_position=eff_sub_pos,
                category_hint=cand_cat,
                context_word_timestamps=full_video_words,
            )
            rendered_ok_count += 1
        except RuntimeError as render_err:
            last_render_err = render_err
            logger.warning("Se omitió candidato %s porque no generó video válido: %s", short_filename, render_err)
            continue
        layout_used = eff_layout
        tl_path = out_dir / f"{out_mp4.stem}_opencut_timeline.json"
        if tl_path.exists():
            try:
                tl_obj = json.loads(tl_path.read_text(encoding="utf-8"))
                kfs = tl_obj.get("tracks", [{}])[0].get("effects", [{}])[0].get("keyframes", [{}])
                layout_used = str(tl_obj.get("layout_mode") or (kfs[0].get("mode") if kfs else None) or layout_used)
            except Exception:
                pass
        account_cats = cand.get("account_categories")
        if not isinstance(account_cats, list) or not account_cats:
            account_cats = social_hub.classify_short_account_categories(
                text=cand_text,
                title=str(cand.get("hook_title", "")),
                tags=list(cand.get("tags") or []),
                scene_category=str(cand_cat),
                scene_label=str(layout_used),
                hub_cfg=hub_cfg,
                allowed_categories=allowed_cats,
                auto_by_topic=auto_by_topic,
            )
        # Guardar sidecar metadata para la cuadrícula de Shorts
        meta = {
            "short_filename": out_mp4.name,
            "virality_score": score,
            "virality_grade": str(cand.get("virality_grade", round(score / 10.0, 1))),
            "tier": tier_tag,
            "category": cand_cat,
            "account_categories": account_cats,
            "layout_used": layout_used,
            "subtitle_preset": eff_sub_preset,
            "subtitle_position": eff_sub_pos,
            "cam_overlay_pos": eff_cam_pos,
            "custom_cam_box_norm": eff_cam_box,
            "custom_content_box_norm": eff_content_box,
            "duration_sec": round(float(cand["end_time"]) - float(cand["start_time"]), 2),
            "hook_title": cand.get("hook_title", ""),
            "caption": cand.get("first_person_caption", ""),
            "tags": cand.get("tags", []),
            "bgm_mood": "desactivada",
            "youtube_eligible": True,
            "youtube_uploaded": False,
        }
        (out_dir / f"{out_mp4.stem}_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    if rendered_ok_count == 0:
        state["status"] = "ERROR"
        state["source_preview_url"] = None
        state["phase_label"] = "Error al renderizar"
        state["step_detail"] = str(last_render_err or "Ningún clip generó fotogramas de video válidos.")
        state["message"] = state["step_detail"]
        _persist_pipeline_state(pid)
        return

    state["status"] = "COMPLETED"
    state["source_preview_url"] = None
    state["progress_percent"] = 100
    state["phase_label"] = "Completado"
    state["step_detail"] = f"{rendered_ok_count} Shorts renderizados correctamente."
    state["requires_schedule_confirmation"] = False
    state["short_uploads"] = {}
    _persist_pipeline_state(pid)


@app.post("/api/pipeline/discover")
def discover_pipeline_candidates(req: DiscoverPipelineRequest) -> Dict[str, Any]:
    """Transcribe al 100% y extrae hasta 24 candidatos con puntaje IA antes de renderizar MP4s."""
    pid = _normalize_project_id(req.project_id)
    state = _get_project_state(pid)
    cancel_ev = _get_project_cancel_event(pid)
    cancel_ev.clear()

    def _disc_progress(pct: int, phase: str, detail: str, _short_upd: Optional[Dict[str, Any]] = None) -> None:
        state["progress_percent"] = pct
        state["phase_label"] = phase
        state["step_detail"] = detail
        _persist_pipeline_state(pid)

    if req.source_type == "youtube_url":
        raw_url = (req.youtube_url or "").strip()
        if not raw_url:
            raise HTTPException(status_code=400, detail="Debes indicar youtube_url.")
        if pid == "default":
            video_path = _main_daemon_bootstrap.download_youtube_url_max_quality(
                raw_url,
                progress_callback=_disc_progress,
                download_section_start=req.download_section_start,
                download_section_end=req.download_section_end,
            )
        else:
            video_path = _main_daemon_bootstrap.download_youtube_url_max_quality(
                raw_url,
                progress_callback=_disc_progress,
                download_section_start=req.download_section_start,
                download_section_end=req.download_section_end,
                cancel_event=cancel_ev,
            )
    else:
        raw_file = (req.video_filename or "").strip()
        if not raw_file:
            raise HTTPException(status_code=400, detail="Debes seleccionar video_filename.")
        video_path = _resolve_studio_video_path(raw_file)

    state["status"] = "DISCOVERING"
    state["current_video"] = video_path.name
    state["project_name"] = _main_daemon_bootstrap.build_video_date_project_id(video_path.name)
    state["progress_percent"] = 20
    state["phase_label"] = "Escaneo Contextual IA (Pre-Render)"
    state["step_detail"] = f"Analizando el 100% de {video_path.name} para descubrir hasta {req.shorts_per_video} clips..."
    _persist_pipeline_state(pid)

    analyses = skill_analyzer.transcribe_and_analyze_multiple(
        video_path=video_path,
        max_shorts=req.shorts_per_video,
        enable_jumpcuts=True,
        progress_callback=_disc_progress,
    )

    serialized_rules = [r.model_dump() for r in req.category_rules] if req.category_rules else None
    hub_cfg = social_hub.get_raw_social_hub_config(CONFIG_DIR)
    candidates_payload: List[Dict[str, Any]] = []
    for idx, a in enumerate(analyses, start=1):
        dur = round(float(a.end_time) - float(a.start_time), 2)
        eval_text = a.transcript_excerpt.strip() or a.first_person_caption
        resolved_rule = (
            _main_daemon_bootstrap.resolve_clip_category_rule(
                video_path=video_path,
                start_time=float(a.start_time),
                end_time=float(a.end_time),
                text=eval_text,
                title=a.hook_title,
                category_rules=serialized_rules,
                fallback_settings={"content_category": req.content_category},
            )
            if serialized_rules
            else None
        )
        eff_cat = str(resolved_rule.get("category") or req.content_category) if resolved_rule else req.content_category
        v_eval = skill_virality.evaluate_virality_10_points(
            text=eval_text,
            duration=dur,
            words=a.word_timestamps,
            title=a.hook_title,
            llm_scores={
                "hook_strength": float(getattr(a, "hook_strength", 8.5)),
                "standalone_value": float(getattr(a, "standalone_value", 8.5)),
                "virality_potential": float(getattr(a, "virality_potential", 8.5)),
            },
            category=eff_cat,
            acoustic_score=float(getattr(a, "acoustic_energy_score", 7.5)),
        )
        cand_account_cats = social_hub.classify_short_account_categories(
            text=eval_text,
            title=str(a.hook_title),
            tags=list(a.tags),
            scene_category=str(eff_cat),
            scene_label=str(resolved_rule.get("scene_label") or "") if resolved_rule else "",
            hub_cfg=hub_cfg,
            allowed_categories=req.allowed_account_categories,
            auto_by_topic=req.auto_categorize_by_topic,
        )
        candidates_payload.append(
            {
                "candidate_id": f"cand_{idx:02d}",
                "start_time": float(a.start_time),
                "end_time": float(a.end_time),
                "duration": dur,
                "hook_title": a.hook_title,
                "first_person_caption": a.first_person_caption,
                "transcript_excerpt": a.transcript_excerpt,
                "tags": list(a.tags),
                "bgm_mood": a.bgm_mood,
                "category": str(getattr(v_eval, "category", eff_cat) if eff_cat == "auto" else eff_cat),
                "account_categories": cand_account_cats,
                "layout_mode": str(resolved_rule.get("layout_mode")) if resolved_rule else "auto",
                "subtitle_preset": str(resolved_rule.get("subtitle_preset")) if resolved_rule else "hormozi_pop",
                "virality_score": int(v_eval.total_points),
                "virality_grade": str(v_eval.final_grade),
                "tier": (
                    "Oro"
                    if int(v_eval.total_points) >= 90
                    else ("Plata" if int(v_eval.total_points) >= 75 else "Meh")
                ),
                "youtube_eligible": True,
                "word_timestamps": [
                    w.model_dump() if hasattr(w, "model_dump") else dict(w)
                    for w in a.word_timestamps
                ],
                "keep_intervals": [list(iv) for iv in getattr(a, "keep_intervals", [])],
            }
        )

    candidates_payload.sort(key=lambda c: c["virality_score"], reverse=True)
    record = {
        "project_id": pid,
        "video_filename": video_path.name,
        "video_path": str(video_path),
        "discovered_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "candidates": candidates_payload,
    }
    _candidates_file(pid).write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")

    state["status"] = "CANDIDATES_READY"
    state["progress_percent"] = 100
    state["phase_label"] = "Candidatos Listos para Selección"
    state["step_detail"] = f"Se detectaron {len(candidates_payload)} clips con contexto completo."
    _persist_pipeline_state(pid)

    return {
        "project_id": pid,
        "video_filename": video_path.name,
        "total_candidates": len(candidates_payload),
        "candidates": candidates_payload,
    }


@app.get("/api/pipeline/candidates")
def list_discovered_candidates(project_id: Optional[str] = None) -> Dict[str, Any]:
    """Devuelve los candidatos descubiertos en la bandeja pre-render del proyecto."""
    pid = _normalize_project_id(project_id)
    c_file = _candidates_file(pid)
    if not c_file.exists():
        return {"project_id": pid, "video_filename": None, "candidates": []}
    try:
        data = json.loads(c_file.read_text(encoding="utf-8"))
        return {
            "project_id": pid,
            "video_filename": data.get("video_filename"),
            "discovered_at": data.get("discovered_at"),
            "candidates": data.get("candidates", []),
        }
    except Exception:
        return {"project_id": pid, "video_filename": None, "candidates": []}


@app.post("/api/pipeline/render-selected", status_code=202)
def render_selected_candidates(
    req: RenderSelectedRequest,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    """Lanza el renderizado 9:16 solo para los candidatos elegidos con el encuadre y subtítulos del Studio."""
    pid = _normalize_project_id(req.project_id)
    c_file = _candidates_file(pid)
    if not c_file.exists():
        raise HTTPException(status_code=404, detail="No hay candidatos descubiertos todavía.")
    data = json.loads(c_file.read_text(encoding="utf-8"))
    all_cands = data.get("candidates", [])
    wanted = set(req.candidate_ids)
    selected = [c for c in all_cands if c.get("candidate_id") in wanted]
    if not selected:
        raise HTTPException(status_code=400, detail="Ningún candidate_id válido fue seleccionado.")

    raw_vid = data.get("video_path") or data.get("video_filename")
    if not raw_vid:
        raise HTTPException(status_code=404, detail="Video origen de candidatos no encontrado.")
    source_path = Path(raw_vid)
    if not source_path.exists():
        source_path = _resolve_studio_video_path(Path(raw_vid).name)

    try:
        _get_project_cancel_event(pid).clear()
    except Exception:
        pass
    cancel_all_rendered_shorts(project_id=pid)
    job_id = str(uuid.uuid4())[:8]
    if pid == "default":
        background_tasks.add_task(
            _render_selected_background,
            job_id,
            selected,
            source_path,
            req.model_dump(),
        )
    else:
        background_tasks.add_task(
            _render_selected_background,
            job_id,
            selected,
            source_path,
            req.model_dump(),
            project_id=pid,
        )
    return {
        "project_id": pid,
        "job_id": job_id,
        "selected_count": len(selected),
        "message": f"Renderizando {len(selected)} clips seleccionados con layout {req.layout_mode}.",
    }


@app.post("/api/cleanup")
def run_disk_cleanup(project_id: Optional[str] = None) -> Dict[str, Any]:
    """Ejecuta la limpieza real de archivos temporales en ./processing/, ./published_archive/ e ig_ready_8m."""
    pid = _normalize_project_id(project_id)
    skill_cleanup.PROCESSING_DIR = PROCESSING_DIR
    skill_cleanup.OUTPUT_DIR = OUTPUT_SHORTS_DIR
    skill_cleanup.PUBLISHED_ARCHIVE_DIR = PUBLISHED_ARCHIVE_DIR

    # Evitar borrar temporales recién descargados si alguna otra ventana independiente sigue activa.
    max_age_sec = 7200 if _has_other_active_projects(exclude_project_id=pid) else 0
    proc_deleted, proc_mb = skill_cleanup.clean_processing_dir(max_age_seconds=max_age_sec)
    ig_deleted, ig_mb = skill_cleanup.clean_ig_staging_cache(max_age_hours=0)
    disk_report = skill_cleanup.get_disk_space_report(BASE_DIR)

    return {
        "deleted_files": proc_deleted + ig_deleted,
        "mb_freed": round(proc_mb + ig_mb, 2),
        "disk_space": disk_report,
    }


ENGINE_IDENTITY = "Auto-Clipper Shorts Engine"


@app.get("/api/health")
def get_health() -> Dict[str, str]:
    """Endpoint de verificación de salud del motor."""
    return {
        "status": "ok",
        "engine": ENGINE_IDENTITY,
    }


def _is_port_free(port: int, host: str = "127.0.0.1") -> bool:
    """Comprueba mediante bind real si el puerto loopback está libre para iniciar Short YT."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, int(port)))
            return True
        except OSError:
            return False


def _is_short_yt_running_on_port(
    port: int,
    host: str = "127.0.0.1",
    timeout: float = 0.8,
) -> bool:
    """Verifica que /api/health responda 200 con la identidad exacta de Auto-Clipper Shorts Engine."""
    try:
        with urllib.request.urlopen(
            f"http://{host}:{int(port)}/api/health",
            timeout=timeout,
        ) as resp:
            if getattr(resp, "status", 200) != 200:
                return False
            payload = json.loads(resp.read().decode("utf-8"))
            return (
                isinstance(payload, dict)
                and payload.get("status") == "ok"
                and payload.get("engine") == ENGINE_IDENTITY
            )
    except Exception:
        return False


def resolve_startup_port(
    preferred_port: int = 8000,
    explicit_port: bool = False,
    max_scan: int = 20,
    host: str = "127.0.0.1",
) -> Tuple[int, bool]:
    """Resuelve el puerto de arranque reutilizando una instancia activa o saltando colisiones externas."""
    base = int(preferred_port)
    if explicit_port:
        if _is_port_free(base, host=host):
            return base, False
        if _is_short_yt_running_on_port(base, host=host):
            return base, True
        raise RuntimeError(
            f"El puerto explícito {base} está ocupado por otro servicio que no es {ENGINE_IDENTITY}."
        )

    first_free: Optional[int] = None
    for candidate in range(base, base + max(0, int(max_scan)) + 1):
        if _is_port_free(candidate, host=host):
            if first_free is None:
                first_free = candidate
        elif _is_short_yt_running_on_port(candidate, host=host):
            return candidate, True

    if first_free is not None:
        return first_free, False
    raise RuntimeError(
        f"No se encontró ningún puerto libre entre {base} y {base + max(0, int(max_scan))}."
    )


def _open_browser_when_ready(
    url: str,
    port: int,
    host: str = "127.0.0.1",
    timeout_sec: float = 15.0,
) -> bool:
    """Espera a que Short YT responda /api/health antes de abrir el navegador."""
    import webbrowser

    deadline = time.time() + max(0.5, float(timeout_sec))
    while time.time() < deadline:
        if _is_short_yt_running_on_port(port, host=host, timeout=0.8):
            webbrowser.open(url)
            return True
        time.sleep(0.2)
    return False


@app.get("/api/analytics/categories")
def get_analytics_categories() -> Dict[str, Any]:
    """Devuelve la matriz de evaluación y pesos sobre 100 puntos de cada categoría de contenido."""
    return {
        "categories": skill_virality.get_category_analytics_profiles(),
    }


LIVE_SESSIONS: Dict[str, live_stream_monitor.LiveMonitorSession] = {}


@app.get("/api/live/status")
def get_live_monitor_status(project_id: Optional[str] = None) -> Dict[str, Any]:
    """Devuelve el estado de monitoreo en tiempo real para la pestaña Directo en Vivo."""
    pid = _normalize_project_id(project_id)
    sess = LIVE_SESSIONS.get(pid)
    if sess is None:
        return live_stream_monitor.build_idle_live_status(pid)
    return sess.to_dict()


@app.post("/api/live/start")
def start_live_monitor(req: LiveMonitorStartRequest) -> Dict[str, Any]:
    """Inicia la captura continua por bloques rodantes de un directo activo."""
    pid = _normalize_project_id(req.project_id)
    raw_url = req.stream_url.strip()
    if not raw_url or not _REMOTE_VIDEO_URL_RE.match(raw_url):
        raise HTTPException(
            status_code=400,
            detail="Debes proporcionar un enlace válido de YouTube, Twitch o Kick en directo.",
        )

    existing = LIVE_SESSIONS.get(pid)
    if existing is not None:
        st = existing.to_dict().get("status")
        if st in ("STARTING", "MONITORING", "ANALYZING_CHUNK"):
            raise HTTPException(
                status_code=409,
                detail="Ya hay una transmisión en vivo siendo monitoreada en este proyecto.",
            )

    profile_cfg: Optional[Dict[str, Any]] = None
    profile_name = "Automático"
    if req.profile_id is not None:
        profiles = _list_content_profiles_from_db()
        profile_cfg = next((p for p in profiles if int(p["id"]) == int(req.profile_id)), None)
        if profile_cfg is None:
            raise HTTPException(status_code=404, detail="Perfil de Contenido no encontrado.")
        profile_name = str(profile_cfg.get("name") or f"Perfil #{req.profile_id}")

    session = live_stream_monitor.LiveMonitorSession(
        project_id=pid,
        stream_url=raw_url,
        profile_id=req.profile_id,
        profile_name=profile_name,
        layout_mode=req.layout_mode,
        subtitle_preset=req.subtitle_preset,
        chunk_duration_sec=req.chunk_duration_sec,
        overlap_sec=req.overlap_sec,
        min_virality_score=req.min_virality_score,
        max_shorts_total=req.max_shorts_total,
    )
    LIVE_SESSIONS[pid] = session

    out_root = _get_project_output_dir(pid)
    out_root.mkdir(parents=True, exist_ok=True)
    hub_keys = _get_hub_category_keys()

    worker = threading.Thread(
        target=live_stream_monitor.run_live_monitor_loop,
        args=(session,),
        kwargs={
            "config_dir": CONFIG_DIR,
            "processing_dir": PROCESSING_DIR,
            "output_root": out_root,
            "skill_analyzer": skill_analyzer,
            "skill_virality": skill_virality,
            "skill_renderer": skill_renderer,
            "hub_category_keys": hub_keys,
            "profile_cfg": profile_cfg,
        },
        daemon=True,
    )
    worker.start()
    return session.to_dict()


@app.post("/api/live/stop")
def stop_live_monitor(project_id: Optional[str] = None) -> Dict[str, Any]:
    """Detiene limpiamente la captura del directo en curso para el proyecto indicado."""
    pid = _normalize_project_id(project_id)
    sess = LIVE_SESSIONS.get(pid)
    if sess is None:
        return live_stream_monitor.build_idle_live_status(pid)
    sess.stop()
    return sess.to_dict()


FRONTEND_DIST_DIR = Path(__file__).resolve().parent / "frontend" / "dist"
if (FRONTEND_DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST_DIR / "assets")), name="assets")


_FAVICON_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
    "<rect width='32' height='32' rx='8' fill='#090B10'/>"
    "<path d='M12 9l11 7-11 7V9z' fill='#06B6D4'/>"
    "</svg>"
)


@app.get("/favicon.ico", include_in_schema=False)
def serve_favicon() -> Response:
    """Devuelve el ícono SVG del Studio para evitar errores 404 en consola del navegador."""
    return Response(
        content=_FAVICON_SVG,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/", response_model=None)
def serve_frontend_root() -> FileResponse | HTMLResponse:
    """Sirve la interfaz web compilada de Short YT sin caché HTML para cargar siempre el bundle vigente."""
    index_file = FRONTEND_DIST_DIR / "index.html"
    if index_file.exists():
        return FileResponse(
            str(index_file),
            media_type="text/html",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )
    return HTMLResponse(
        "<html><body><h1>Short YT</h1></body></html>",
        status_code=200,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


if __name__ == "__main__":
    import argparse
    import webbrowser
    import uvicorn

    LOGS_DIR = BASE_DIR / "logs"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None or sys.stderr is None:
        log_fh = open(LOGS_DIR / "api_server.log", "a", encoding="utf-8")
        sys.stdout = log_fh
        sys.stderr = log_fh

    ap = argparse.ArgumentParser(description="Short YT — Auto-Clipper Shorts Engine")
    ap.add_argument("--no-browser", action="store_true", help="No abrir el navegador automaticamente al iniciar")
    ap.add_argument(
        "--port",
        type=int,
        default=None,
        help="Puerto local fijo (por defecto busca el primer libre desde 8000)",
    )
    args = ap.parse_args()

    explicit_port = args.port is not None
    preferred_port = int(args.port) if explicit_port else 8000
    chosen_port, already_running = resolve_startup_port(
        preferred_port=preferred_port,
        explicit_port=explicit_port,
    )
    url = f"http://127.0.0.1:{chosen_port}"

    if already_running:
        print("==================================================================")
        print(f"SHORT YT YA SE ENCUENTRA ACTIVO EN SEGUNDO PLANO: {url}")
        print("==================================================================")
        if not args.no_browser:
            webbrowser.open(url)
    else:
        print("==================================================================")
        print(f"AUTO-CLIPPER SHORTS ENGINE (SHORT YT) ACTIVO EN: {url}")
        print("==================================================================")
        if not args.no_browser:
            threading.Thread(
                target=_open_browser_when_ready,
                args=(url, chosen_port),
                daemon=True,
            ).start()
        uvicorn.run(app, host="127.0.0.1", port=chosen_port, reload=False)


