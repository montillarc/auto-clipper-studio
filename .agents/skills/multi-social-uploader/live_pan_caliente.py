"""
CreadorStudio Live Clipper Engine — Modo 'Pan Caliente' (live_pan_caliente.py)

Soporta tanto directos activos en tiempo real (HLS m3u8 itag 312 1080p60 .ts + itag 234 audio .ts)
como directos en DVR/DASH (itag 299 + 140):
1. Descarga primero SOLO el audio (.ts / .m4a) del bloque de 25-30 minutos (toma ~3 segundos).
2. Transcribe en GPU con faster-whisper (int8_float16 ligero) y aplica el Radar de Emoción + Contexto Completo
   con ventana deslizante (Sliding Window) para jamás cortar una conversación o reacción a la mitad.
3. Descarga los fragmentos de video 1080p60 ÚNICAMENTE de los minutos exactos de cada Short seleccionado (toma ~2s por clip).
4. Auto-detecta el layout (fullscreen / split_streamer / ometv) y la categoría (general / gaming / ometv),
   renderiza en 1080x1920 @ 60 FPS (Lanczos + AMD FidelityFX CAS + h264_nvenc + subtítulos .ass) y
   publica AL INSTANTE ('Como Pan Caliente', sin esperar horarios ni aprobación) en:
   - YouTube (CreadorStudio) -> PUBLIC inmediato
   - Instagram (Graph API) -> Publicación directa inmediata
   - TikTok (Content Posting API v2) -> Publicación directa inmediata
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import site
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    for _sp in site.getsitepackages():
        for _sub in ("cublas", "cudnn"):
            _dll_dir = os.path.join(_sp, "nvidia", _sub, "bin")
            if os.path.isdir(_dll_dir):
                if hasattr(os, "add_dll_directory"):
                    os.add_dll_directory(_dll_dir)
                if _dll_dir not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = _dll_dir + os.pathsep + os.environ.get("PATH", "")
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BASE_DIR / ".agents" / "skills" / "video-transcriber-analyzer"))
sys.path.insert(0, str(BASE_DIR / ".agents" / "skills" / "vertical-crop-renderer"))
sys.path.insert(0, str(BASE_DIR / ".agents" / "skills" / "strategic-time-calculator"))
sys.path.insert(0, str(BASE_DIR / ".agents" / "skills" / "youtube-shorts-uploader"))
sys.path.insert(0, str(BASE_DIR / ".agents" / "skills" / "multi-social-uploader"))

import imageio_ffmpeg
import yt_dlp
from calculator import get_and_reserve_next_slot, update_slot_youtube_id
from faster_whisper import WhisperModel
from instagram_api_uploader import (
    IG_ACCOUNTS,
    load_config,
    publish_reel_via_url,
    stage_video_url,
)
from instagram_scheduler import enqueue_instagram_reel, prepare_ig_staging_file
from renderer import detect_video_layout_and_regions, render_vertical_short
from tiktok_api_uploader import publish_tiktok_video
from tiktok_scheduler import enqueue_tiktok_video
from uploader import upload_scheduled_short
from virality_scorer import evaluate_virality_10_points, select_and_order_shorts_by_virality_rules

FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()
PROCESSING_DIR = BASE_DIR / "processing"
OUTPUT_BASE_DIR = BASE_DIR / "output_shorts"
LOGS_DIR = BASE_DIR / "logs"

PROCESSING_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_BASE_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("live_pan_caliente")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _fh = logging.FileHandler(LOGS_DIR / "live_pan_caliente.log", encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(_fh)
    _sh = logging.StreamHandler(sys.stdout)
    _sh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(_sh)

CATEGORY_ROUTING = {
    "gaming": {
        "ig": ["creador_gaming"],
        "tt": ["creador.gaming"],
    },
    "ometv": {
        "ig": ["creador_ometv"],
        "tt": ["creador_ometv"],
    },
    "general": {
        "ig": ["creador_short", "creador_fans", "creador_videos"],
        "tt": ["creador.clips", "creador.short", "creador.fans", "creador.videos"],
    },
}


def fetch_bytes(url: str) -> bytes:
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                return resp.read()
        except Exception:
            if attempt == 3:
                return b""
            time.sleep(0.8)
    return b""


def fetch_live_manifests(video_url: str) -> Tuple[Dict[str, Any], List[str], List[str], str]:
    """
    Extrae las listas de URLs por fragmento (sq=0..N) tanto para un directo activo (HLS m3u8 312+234)
    como para un directo finalizado en DASH (299+140).
    Devuelve: (info_dict, video_sq_urls, audio_sq_urls, container_type ['ts' | 'mp4'])
    """
    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        info = ydl.extract_info(video_url, download=False)

    formats = info.get("formats") or []
    fmt_map = {str(f.get("format_id")): f for f in formats}

    # Caso 1: Directo activo con playlists HLS m3u8 (312 = 1080p60, 234 = audio)
    if "312" in fmt_map and "234" in fmt_map:
        v_m3u8 = urllib.request.urlopen(fmt_map["312"]["url"], timeout=20).read().decode("utf-8")
        a_m3u8 = urllib.request.urlopen(fmt_map["234"]["url"], timeout=20).read().decode("utf-8")
        v_lines = [l.strip() for l in v_m3u8.splitlines() if l.strip().startswith("http")]
        a_lines = [l.strip() for l in a_m3u8.splitlines() if l.strip().startswith("http")]
        if v_lines and a_lines:
            v_template = v_lines[-1]
            a_template = a_lines[-1]
            m_last = re.search(r"/sq/(\d+)/", v_template)
            last_sq = int(m_last.group(1)) if m_last else len(v_lines)
            v_urls = [re.sub(r"/sq/\d+/", f"/sq/{i}/", v_template) for i in range(last_sq + 1)]
            a_urls = [re.sub(r"/sq/\d+/", f"/sq/{i}/", a_template) for i in range(last_sq + 1)]
            return info, v_urls, a_urls, "ts"

    # Caso 2: Directo con fragmentos DASH (299 + 140)
    with yt_dlp.YoutubeDL({"quiet": True, "format": "299/303/bestvideo[height>=1080]"}) as ydl:
        info_v = ydl.extract_info(video_url, download=False)
        frags_v = [f["url"] for f in (info_v.get("fragments") or [])]
    with yt_dlp.YoutubeDL({"quiet": True, "format": "140/bestaudio"}) as ydl:
        info_a = ydl.extract_info(video_url, download=False)
        frags_a = [f["url"] for f in (info_a.get("fragments") or [])]
    return info_v, frags_v, frags_a, "mp4"


def download_audio_window(
    audio_urls: List[str],
    sq_start: int,
    sq_end: int,
    container_type: str,
    out_audio_path: Path,
) -> Path:
    """Descarga en paralelo SOLO el audio del bloque de 30 minutos (en ~3 segundos)."""
    tmp_raw = PROCESSING_DIR / f"live_aud_raw_{sq_start}_{sq_end}.{container_type}"
    with ThreadPoolExecutor(max_workers=16) as ex:
        parts = list(ex.map(fetch_bytes, [audio_urls[i] for i in range(sq_start, sq_end + 1)]))
    with open(tmp_raw, "wb") as f:
        for b in parts:
            if b:
                f.write(b)

    subprocess.run(
        [
            FFMPEG_BIN,
            "-y",
            "-i",
            str(tmp_raw),
            "-vn",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            str(out_audio_path),
        ],
        check=True,
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0,
    )
    tmp_raw.unlink(missing_ok=True)
    return out_audio_path


def download_clip_av_slice(
    video_urls: List[str],
    audio_urls: List[str],
    sq_start: int,
    sq_end: int,
    container_type: str,
    out_mp4_path: Path,
) -> Path:
    """Descarga en paralelo el video 1080p60 + audio únicamente de los fragmentos sq del Short elegido."""
    tmp_v = PROCESSING_DIR / f"live_clip_v_{sq_start}_{sq_end}.{container_type}"
    tmp_a = PROCESSING_DIR / f"live_clip_a_{sq_start}_{sq_end}.{container_type}"

    with ThreadPoolExecutor(max_workers=16) as ex:
        v_parts = list(ex.map(fetch_bytes, [video_urls[i] for i in range(sq_start, sq_end + 1)]))
        a_parts = list(ex.map(fetch_bytes, [audio_urls[i] for i in range(sq_start, sq_end + 1)]))

    with open(tmp_v, "wb") as f:
        for b in v_parts:
            if b:
                f.write(b)
    with open(tmp_a, "wb") as f:
        for b in a_parts:
            if b:
                f.write(b)

    subprocess.run(
        [
            FFMPEG_BIN,
            "-y",
            "-i",
            str(tmp_v),
            "-i",
            str(tmp_a),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(out_mp4_path),
        ],
        check=True,
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0,
    )
    tmp_v.unlink(missing_ok=True)
    tmp_a.unlink(missing_ok=True)
    return out_mp4_path


def detect_clip_category_and_layout(
    video_path: Path,
    rel_start: float,
    rel_end: float,
    stream_title: str,
    clip_text: str,
) -> Tuple[Literal["gaming", "ometv", "general"], Literal["ometv", "split_streamer", "fullscreen"]]:
    """Clasifica automáticamente el clip en ometv, gaming o general y elige su layout 9:16."""
    title_low = stream_title.lower()
    text_low = clip_text.lower()

    if "ometv" in title_low or "ome tv" in title_low or "ometv" in text_low:
        return "ometv", "ometv"

    # Si el directo es un programa de radio/entrevista/debate (Podcast Debate, Yailin, etc.), es General Fullscreen
    general_show_keywords = {"tertulia", "yailin", "lil nay", "kevin wai", "conchinchineo", "entrevista", "radio"}
    if any(k in title_low for k in general_show_keywords):
        return "general", "fullscreen"

    layout_info = detect_video_layout_and_regions(
        video_path=video_path,
        start_time=rel_start,
        end_time=rel_end,
        layout_mode="auto",
    )
    detected_mode = layout_info.get("mode", "fullscreen")

    gaming_keywords = {
        "juego", "jugando", "gameplay", "boss", "jefe", "parry", "machetazo",
        "dlss", "fps", "enemigo", "espada", "caminante", "partida", "gamer",
        "zelda", "ocarina", "remake", "link", "nintendo", "live", "vamo al game",
    }
    if any(k in title_low or k in text_low for k in gaming_keywords) or detected_mode == "split_streamer":
        return "gaming", "split_streamer"

    return "general", "fullscreen"


def extract_viral_candidates_from_window(
    segments: List[Dict[str, Any]],
    window_dur: float,
    is_still_live: bool,
    max_clips: int = 8,
    stream_title: str = "",
    video_url: str = "",
    category: str = "general",
) -> Tuple[List[Dict[str, Any]], float]:
    """
    Encuentra los mejores momentos virales de 50s a 135s dentro del bloque de 30 minutos
    respetando el inicio y fin natural de la idea (sin cortar conversaciones a la mitad).
    """
    if not segments:
        return [], window_dur

    blocks: List[Dict[str, Any]] = []
    curr_segs: List[Dict[str, Any]] = []

    for seg in segments:
        if curr_segs and (seg["start"] - curr_segs[-1]["end"]) >= 1.8:
            blocks.append(
                {
                    "start": curr_segs[0]["start"],
                    "end": curr_segs[-1]["end"],
                    "text": " ".join(s["text"] for s in curr_segs).strip(),
                    "segs": list(curr_segs),
                }
            )
            curr_segs = []
        curr_segs.append(seg)

    if curr_segs:
        blocks.append(
            {
                "start": curr_segs[0]["start"],
                "end": curr_segs[-1]["end"],
                "text": " ".join(s["text"] for s in curr_segs).strip(),
                "segs": list(curr_segs),
            }
        )

    safe_cutoff_sec = window_dur
    if is_still_live and len(blocks) > 1 and (window_dur - blocks[-1]["end"]) < 75.0:
        safe_cutoff_sec = max(300.0, blocks[-1]["start"] - 2.0)
        blocks = [b for b in blocks if b["end"] <= safe_cutoff_sec]

    excitement_words = {
        "diablo", "mierda", "coño", "loco", "fuera", "mira", "increíble", "mentira",
        "duro", "bárbaro", "barbaro", "hermano", "chacho", "muchacho", "yailin",
        "lil nay", "kevin", "arrogancia", "millones", "dinero", "problema", "verdad",
        "nadie", "calle", "música", "musica", "fuego", "bomba", "exclusiva",
    }

    candidates: List[Dict[str, Any]] = []
    n = len(blocks)
    for i in range(n):
        c_start = blocks[i]["start"]
        c_end = blocks[i]["end"]
        c_texts = [blocks[i]["text"]]
        c_words = []
        for s in blocks[i]["segs"]:
            c_words.extend(s.get("words") or [])

        j = i + 1
        while j < n and (blocks[j]["end"] - c_start) <= 125.0:
            c_end = blocks[j]["end"]
            c_texts.append(blocks[j]["text"])
            for s in blocks[j]["segs"]:
                c_words.extend(s.get("words") or [])
            if (c_end - c_start) >= 62.0:
                break
            j += 1

        dur = c_end - c_start
        full_text = " ".join(c_texts).strip()
        if 40.0 <= dur <= 145.0 and len(c_words) >= 25:
            low_t = full_text.lower()
            ex_hits = sum(low_t.count(w) for w in excitement_words)
            exclamations = full_text.count("!") + full_text.count("¡") + full_text.count("?")
            wps = len(c_words) / max(1.0, dur)
            raw_score = (ex_hits * 3.5) + (exclamations * 1.5) + (wps * 4.0)
            cand_title, _, _ = build_live_viral_metadata(
                clip_text=full_text,
                stream_title=stream_title,
                video_url=video_url,
                category=category,
            )
            v_breakdown = evaluate_virality_10_points(
                text=full_text,
                duration=dur,
                words=c_words,
                title=cand_title,
            )
            candidates.append(
                {
                    "start": round(c_start, 2),
                    "end": round(c_end, 2),
                    "duration": round(dur, 1),
                    "text": full_text,
                    "words": c_words,
                    "title": cand_title,
                    "score": round(raw_score, 2),
                    "virality_score": v_breakdown.total_points,
                    "virality_grade": v_breakdown.final_grade,
                    "virality_classification": v_breakdown.classification,
                    "virality_breakdown": v_breakdown.to_dict(),
                }
            )

    candidates.sort(key=lambda x: (x["virality_score"], x["score"]), reverse=True)
    non_overlapping: List[Dict[str, Any]] = []
    for cand in candidates:
        if len(non_overlapping) >= max_clips:
            break
        # Evitar solapamiento entre los clips elegidos
        if all(abs(cand["start"] - s["start"]) > 90.0 for s in non_overlapping):
            non_overlapping.append(cand)

    ordered_all, yt_list, other_only = select_and_order_shorts_by_virality_rules(
        candidates=non_overlapping,
        max_total_shorts=min(8, max_clips),
        youtube_min_score=85,
        max_youtube_shorts=6,
        min_acceptable_score=50,
    )
    if non_overlapping:
        safe_cutoff_sec = max(safe_cutoff_sec, max(c["end"] for c in non_overlapping))
    return ordered_all, safe_cutoff_sec


def build_live_viral_metadata(clip_text: str, stream_title: str, video_url: str, category: str) -> Tuple[str, str, List[str]]:
    """Genera Título Viral con Emojis + #Shorts, Descripción con link al directo en vivo y 3 Hashtags + #Viral."""
    low_t = clip_text.lower()
    low_title = stream_title.lower()

    # Detectar el tema central real del fragmento para armar un título limpio y magnético
    if "yailin" in low_t:
        hook_topic = "¡SE PRENDIÓ EL DEBATE CON YAILIN EN VIVO!"
        tags = ["#YailinLaMasViral", "#Podcast Debate", "#RD", "#Viral", "#Shorts"]
    elif "kevin" in low_t or "arrogancia" in low_t:
        hook_topic = "¡LE CANTAN LA VERDAD SIN FILTRO SOBRE LA ARROGANCIA!"
        tags = ["#KevinWai", "#DebateUrbano", "#RD", "#Viral", "#Shorts"]
    elif "lil nay" in low_t:
        hook_topic = "¡LA VERDAD SOBRE LIL NAY Y LA MÚSICA URBANA EN RD!"
        tags = ["#LilNay", "#MusicaUrbana", "#RD", "#Viral", "#Shorts"]
    else:
        # Extraer una frase limpia e impactante del propio clip
        sentences = [s.strip() for s in re.split(r"[.!?¡¿]+", clip_text) if 14 <= len(s.strip()) <= 58]
        if sentences:
            best_phrase = sentences[0].upper()
        else:
            w_list = clip_text.split()
            if len(w_list) >= 4:
                best_phrase = " ".join(w_list[:7]).upper()
            else:
                clean_title = re.sub(r"[^\w\s]", "", stream_title).strip()
                best_phrase = clean_title[:40].upper() if clean_title else "MOMENTO ÉPICO EN VIVO"
        hook_topic = f"\"{best_phrase}\""
        if "zelda" in low_title or "ocarina" in low_title:
            tags = ["#Zelda", "#OcarinaOfTime", "#Gaming", "#Viral", "#Shorts"]
            hook_topic = f"{hook_topic} 🗡️ ZELDA OCARINA OF TIME"
        elif "tertulia" in low_title or "rd" in low_title:
            tags = ["#Podcast Debate", "#DebateRD", "#Viral", "#Viral", "#Shorts"]
        elif category == "gaming":
            tags = ["#Gaming", "#Gameplay", "#EnVivo", "#Viral", "#Shorts"]
        elif category == "ometv":
            tags = ["#OmeTV", "#Reaccion", "#EnVivo", "#Viral", "#Shorts"]
        else:
            tags = ["#Viral", "#Debate", "#RD", "#Viral", "#Shorts"]

    title = f"🔥 {hook_topic} 😱🎮 #Shorts"
    if len(title) > 98:
        title = f"🔥 {hook_topic[:75].rstrip()}... 😱🎮 #Shorts"

    description = (
        f"🔴 ¡ESTAMOS EN VIVO AHORA MISMO! {clip_text[:145].strip()}... 🔥🎮\n\n"
        f"🎥 Entra al directo completo aquí 👉 {video_url}\n\n"
        f"{' '.join(tags)}"
    )
    return title, description, tags


def publish_pan_caliente(
    rendered_mp4: Path,
    title: str,
    description: str,
    hashtags: List[str],
    category: Literal["gaming", "ometv", "general"],
    publish_to_youtube: bool = True,
    publish_at_iso: str = "NOW",
) -> Dict[str, Any]:
    """
    Sube o programa el Short según las reglas de puntuación de viralidad (10 Puntos):
    - YouTube (CreadorStudio): SOLO si publish_to_youtube=True (puntuación >= 85, máx 6 videos).
    - Demás redes (Instagram y TikTok de la categoría): Se publican los 8 en total,
      primero los >= 85 con 1 hora de por medio y luego los demás con 1 hora de por medio.
    """
    results: Dict[str, Any] = {"youtube": None, "instagram": {}, "tiktok": {}, "publish_at_utc": publish_at_iso}
    tags_clean = [h.lstrip("#") for h in hashtags]

    # 1. YouTube (Solo si obtuvo >= 85 puntos, máximo 6 videos)
    if publish_to_youtube:
        try:
            yt_res = upload_scheduled_short(
                video_path=rendered_mp4,
                title=title,
                description=description,
                tags=tags_clean,
                publish_at_iso=publish_at_iso,
                category_id="22",
            )
            yt_id = yt_res.get("id", "")
            results["youtube"] = f"https://youtu.be/{yt_id}"
            logger.info("🔥 [PAN CALIENTE - YOUTUBE (%s)] -> https://youtu.be/%s", publish_at_iso, yt_id)
            if yt_id and publish_at_iso != "NOW":
                try:
                    update_slot_youtube_id(publish_at_utc=publish_at_iso, youtube_video_id=yt_id)
                except Exception as db_err:
                    logger.debug("No se pudo actualizar youtube_id en scheduled_slots: %s", db_err)
        except Exception as exc:
            logger.error("Error publicando en YouTube: %s", exc)
            results["youtube"] = f"ERROR: {exc}"
    else:
        results["youtube"] = "SKIPPED (< 85 pts o límite de 6 alcanzado)"
        logger.info("⏭️ [YOUTUBE] Omitido por regla de puntuación (< 85 pts); va para las demás redes.")

    # 2. Instagram Graph API (Los 8 Shorts en total, espaciados 1 hora)
    ig_targets = CATEGORY_ROUTING[category]["ig"]
    ig_caption = f"{title}\n\n{description}"
    try:
        if publish_at_iso == "NOW":
            cfg = load_config()
            access_token = cfg["access_token"]
            staged_local = prepare_ig_staging_file(str(rendered_mp4))
            public_video_url = stage_video_url(staged_local)
            for acct in ig_targets:
                ig_id = IG_ACCOUNTS.get(acct)
                if not ig_id:
                    continue
                info = publish_reel_via_url(ig_id, public_video_url, ig_caption, access_token)
                results["instagram"][acct] = info
                logger.info("🔥 [PAN CALIENTE - INSTAGRAM @%s] OK -> %s", acct, info)
        else:
            for acct in ig_targets:
                enqueue_instagram_reel(
                    video_path=str(rendered_mp4),
                    account_key=acct,
                    caption=ig_caption,
                    scheduled_time_utc=publish_at_iso,
                )
                results["instagram"][acct] = f"SCHEDULED ({publish_at_iso})"
    except Exception as exc:
        logger.error("Error en Instagram: %s", exc)

    # 3. TikTok Content Posting API v2 (Los 8 Shorts en total, espaciados 1 hora)
    tt_targets = CATEGORY_ROUTING[category]["tt"]
    tt_caption = f"{title} {' '.join(hashtags)}"
    for acct in tt_targets:
        try:
            if publish_at_iso == "NOW":
                info = publish_tiktok_video(
                    account_username=acct,
                    video_path=str(rendered_mp4),
                    caption=tt_caption,
                    mode="auto",
                )
                results["tiktok"][acct] = info
                logger.info("🔥 [PAN CALIENTE - TIKTOK @%s] OK -> %s", acct, info)
            else:
                enqueue_tiktok_video(
                    video_path=str(rendered_mp4),
                    account_key=acct,
                    caption=tt_caption,
                    scheduled_time_utc=publish_at_iso,
                )
                results["tiktok"][acct] = f"SCHEDULED ({publish_at_iso})"
        except Exception as exc:
            logger.error("Error en TikTok @%s: %s", acct, exc)
            results["tiktok"][acct] = f"ERROR: {exc}"

    return results


def run_live_pan_caliente_loop(
    video_url: str,
    window_minutes: int = 60,
    max_clips_per_window: int = 8,
    start_from_recent: bool = True,
    once: bool = False,
) -> None:
    logger.info("🚀 Iniciando Motor En Vivo 'PAN CALIENTE' para: %s", video_url)
    whisper_model = WhisperModel("large-v3", device="cuda", compute_type="int8_float16")

    window_frags = int((window_minutes * 60) / 5.0)
    last_processed_sq: Optional[int] = None
    clip_counter = 0

    while True:
        info, v_urls, a_urls, container_type = fetch_live_manifests(video_url)
        video_id = info.get("id", "live_stream")
        stream_title = info.get("title", "Directo En Vivo")
        is_live = bool(info.get("is_live"))
        total_frags = min(len(v_urls), len(a_urls))

        out_dir = OUTPUT_BASE_DIR / f"{video_id}_Live_PanCaliente"
        out_dir.mkdir(parents=True, exist_ok=True)

        if last_processed_sq is None:
            if start_from_recent and total_frags > window_frags:
                # Arrancar con los últimos 30 minutos más calientes del directo actual
                last_processed_sq = max(1, total_frags - window_frags)
            else:
                last_processed_sq = 1

        available_new_frags = total_frags - last_processed_sq
        logger.info(
            "📡 Stream '%s' [is_live=%s | tipo=%s]: %d fragmentos totales (%d nuevos desde sq=%d)",
            stream_title,
            is_live,
            container_type,
            total_frags,
            available_new_frags,
            last_processed_sq,
        )

        min_required_frags = int(window_frags * 0.80)
        if available_new_frags < min_required_frags and is_live and not once:
            logger.info(
                "⏳ Esperando acumular el bloque de 1 hora de LIVE (%d/%d fragmentos, revisando en 180s)...",
                available_new_frags,
                min_required_frags,
            )
            time.sleep(180)
            continue

        if available_new_frags <= 10 and not is_live:
            logger.info("✅ El directo finalizó y todos los bloques fueron procesados.")
            break

        sq_start = last_processed_sq
        sq_end = min(total_frags - 1, sq_start + window_frags)
        aud_window_path = PROCESSING_DIR / f"{video_id}_aud_{sq_start}_{sq_end}.m4a"

        logger.info("⬇️ [Paso 1/4] Descargando audio del bloque sq=%d..%d (~%d min)...", sq_start, sq_end, (sq_end - sq_start) * 5 // 60)
        download_audio_window(a_urls, sq_start, sq_end, container_type, aud_window_path)

        logger.info("🎙️ [Paso 2/4] Transcribiendo bloque con GPU (faster-whisper int8_float16)...")
        raw_segments, _ = whisper_model.transcribe(
            str(aud_window_path),
            language="es",
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            word_timestamps=True,
        )

        rel_segments: List[Dict[str, Any]] = []
        for s in raw_segments:
            if "suscrib" in s.text.lower():
                continue
            words = [
                {"word": w.word, "start": round(w.start, 2), "end": round(w.end, 2)}
                for w in (s.words or [])
            ]
            rel_segments.append(
                {
                    "start": round(s.start, 2),
                    "end": round(s.end, 2),
                    "text": s.text.strip(),
                    "words": words,
                }
            )
        aud_window_path.unlink(missing_ok=True)

        window_dur = (sq_end - sq_start + 1) * 5.0
        selected_clips, safe_cutoff_rel = extract_viral_candidates_from_window(
            segments=rel_segments,
            window_dur=window_dur,
            is_still_live=is_live,
            max_clips=max_clips_per_window,
            stream_title=stream_title,
            video_url=video_url,
        )

        logger.info("🎯 Detectados %d Shorts Top Virales en este bloque de %d min.", len(selected_clips), int(window_dur // 60))

        for cand in selected_clips:
            clip_counter += 1
            c_start = cand["start"]
            c_end = cand["end"]

            # Calcular exactamente los fragmentos sq de video 1080p60 para este clip
            clip_sq_s = max(sq_start, sq_start + int(c_start // 5.0) - 1)
            clip_sq_e = min(sq_end, sq_start + int(c_end // 5.0) + 2)
            raw_clip_mp4 = PROCESSING_DIR / f"{video_id}_raw_clip_{clip_counter:02d}.mp4"

            logger.info("⬇️ [Paso 3/4] Descargando video 1080p60 sq=%d..%d para Short #%d...", clip_sq_s, clip_sq_e, clip_counter)
            download_clip_av_slice(v_urls, a_urls, clip_sq_s, clip_sq_e, container_type, raw_clip_mp4)

            slice_offset_sec = (clip_sq_s - sq_start) * 5.0
            local_start = max(0.0, round(c_start - slice_offset_sec, 3))
            local_end = max(local_start + 10.0, round(c_end - slice_offset_sec, 3))

            category, layout_mode = detect_clip_category_and_layout(
                video_path=raw_clip_mp4,
                rel_start=local_start,
                rel_end=local_end,
                stream_title=stream_title,
                clip_text=cand["text"],
            )
            title, description, hashtags = build_live_viral_metadata(
                clip_text=cand["text"],
                stream_title=stream_title,
                video_url=video_url,
                category=category,
            )

            out_filename = f"PanCaliente_{clip_counter:02d}_{category}_sq{clip_sq_s}.mp4"
            clip_words = [
                {
                    "word": w["word"],
                    "start": round(max(0.0, w["start"] - c_start), 3),
                    "end": round(max(0.08, w["end"] - c_start), 3),
                }
                for w in cand["words"]
            ]

            logger.info(
                "🎬 Renderizando Pan Caliente #%d [%s | %s | %.1fs]: %s",
                clip_counter,
                category,
                layout_mode,
                local_end - local_start,
                title,
            )
            rendered_mp4 = render_vertical_short(
                video_path=raw_clip_mp4,
                start_time=local_start,
                end_time=local_end,
                word_timestamps=clip_words,
                output_dir=out_dir,
                output_filename=out_filename,
                enable_bgm=False,
                layout_mode=layout_mode,
                playback_speed=1.0,
                custom_cam_box=(28, 224, 492, 328) if layout_mode == "split_streamer" else None,
                custom_content_box=(862, 152, 696, 772) if layout_mode == "split_streamer" else None,
                enable_subtitles=True,
            )
            raw_clip_mp4.unlink(missing_ok=True)

            v_score = int(cand.get("virality_score", 0))
            v_grade = float(cand.get("virality_grade", 0.0))
            pub_yt = bool(cand.get("publish_to_youtube", v_score >= 85))
            slot_iso = get_and_reserve_next_slot(video_name=out_filename)

            logger.info(
                "🚀 [Paso 4/4] Programando Short #%d [Nota: %d/100 (%.1f/10) | YT=%s | Horario=%s]...",
                clip_counter,
                v_score,
                v_grade,
                "SÍ (>=85)" if pub_yt else "NO (<85, solo IG/TikTok)",
                slot_iso,
            )
            pub_res = publish_pan_caliente(
                rendered_mp4=rendered_mp4,
                title=title,
                description=description,
                hashtags=hashtags,
                category=category,
                publish_to_youtube=pub_yt,
                publish_at_iso=slot_iso,
            )
            logger.info("✅ PROCESADO Pan Caliente #%d: %s", clip_counter, json.dumps(pub_res, ensure_ascii=False))

        if is_live:
            overlap_frags = 24  # 2 min overlap to avoid splitting a live conversation
            advanced_frags = max(overlap_frags, int(safe_cutoff_rel // 5.0))
            last_processed_sq = max(sq_end - overlap_frags, min(sq_end + 1, sq_start + advanced_frags))
        else:
            last_processed_sq = sq_end + 1

        if once:
            logger.info("🏁 Prueba de bloque completada (--once).")
            break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CreadorStudio Live Clipper Engine - Modo Pan Caliente")
    parser.add_argument("--url", required=True, help="URL del directo de YouTube")
    parser.add_argument("--window-minutes", type=int, default=60, help="Tamaño del bloque en minutos (default: 60 = 1 hora de LIVE)")
    parser.add_argument("--max-clips", type=int, default=8, help="Máximo de Shorts por hora de LIVE (default: 8)")
    parser.add_argument("--once", action="store_true", help="Procesar un bloque de prueba y terminar")
    args = parser.parse_args()

    run_live_pan_caliente_loop(
        video_url=args.url,
        window_minutes=args.window_minutes,
        max_clips_per_window=args.max_clips,
        once=args.once,
    )
