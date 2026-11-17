"""
Monitor de Transmisiones En Vivo en Tiempo Real (live_stream_monitor.py).
Captura bloques rodantes (HLS/DASH vía yt-dlp + FFmpeg) con solapamiento configurable
sin esperar a que finalice la transmisión, puntúa momentos virales, deduplica cruces de
ventana y renderiza Shorts 9:16 automáticamente en la galería del proyecto.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import main_daemon
from config import social_hub

main_daemon.enable_silent_windows_subprocesses()

logger = logging.getLogger("live_stream_monitor")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")


def _tokenize_moment_text(text: str) -> Set[str]:
    ascii_txt = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii").lower()
    words = re.findall(r"[a-z0-9]{3,}", ascii_txt)
    if len(words) < 3:
        words = re.findall(r"[a-z0-9]+", ascii_txt)
    return set(words)


def is_duplicate_live_moment(
    text: str,
    seen_token_sets: List[Set[str]],
    threshold: float = 0.58,
) -> bool:
    """Detecta si un clip candidato repite el mismo momento capturado en el solapamiento anterior."""
    tokens = _tokenize_moment_text(text)
    if not tokens:
        return False

    for prev in seen_token_sets:
        if not prev:
            continue
        if len(tokens) < 3 or len(prev) < 3:
            if tokens == prev:
                return True
            continue
        overlap_ratio = len(tokens & prev) / max(1, min(len(tokens), len(prev)))
        if overlap_ratio >= threshold:
            return True

    seen_token_sets.append(tokens)
    if len(seen_token_sets) > 15:
        del seen_token_sets[:-15]
    return False


def build_idle_live_status(project_id: str = "default") -> Dict[str, Any]:
    """Devuelve el diccionario de estado inicial en espera para /api/live/status."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {
        "project_id": project_id,
        "session_id": None,
        "status": "IDLE",
        "stream_url": "",
        "stream_title": "",
        "is_live_detected": False,
        "profile_id": None,
        "profile_name": "Automático",
        "layout_mode": "auto",
        "subtitle_preset": "hormozi_pop",
        "chunk_duration_sec": 90,
        "overlap_sec": 20,
        "min_virality_score": 70,
        "max_shorts_total": 12,
        "segments_captured": 0,
        "segments_analyzed": 0,
        "shorts_generated": 0,
        "phase_label": "En espera",
        "step_detail": "Pega el enlace de un directo activo para extraer Shorts en tiempo real.",
        "started_at": None,
        "updated_at": now_str,
        "recent_clips": [],
    }


class LiveMonitorSession:
    """Estado mutable y control de cancelación de una sesión activa de captura en vivo."""

    def __init__(
        self,
        *,
        project_id: str,
        stream_url: str,
        profile_id: Optional[int],
        profile_name: str,
        layout_mode: str,
        subtitle_preset: str,
        chunk_duration_sec: int,
        overlap_sec: int,
        min_virality_score: int,
        max_shorts_total: int,
    ) -> None:
        self.session_id = uuid.uuid4().hex[:8]
        self.project_id = project_id
        self.stream_url = stream_url
        self.profile_id = profile_id
        self.profile_name = profile_name
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.active_proc: Optional[subprocess.Popen[Any]] = None
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._state: Dict[str, Any] = {
            **build_idle_live_status(project_id),
            "session_id": self.session_id,
            "status": "STARTING",
            "stream_url": stream_url,
            "profile_id": profile_id,
            "profile_name": profile_name,
            "layout_mode": layout_mode,
            "subtitle_preset": subtitle_preset,
            "chunk_duration_sec": chunk_duration_sec,
            "overlap_sec": overlap_sec,
            "min_virality_score": min_virality_score,
            "max_shorts_total": max_shorts_total,
            "phase_label": "Conectando al directo...",
            "step_detail": f"Resolviendo stream en vivo desde {stream_url}",
            "started_at": now_str,
            "updated_at": now_str,
        }

    def update(self, **fields: Any) -> None:
        with self.lock:
            self._state.update(fields)
            self._state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def append_clip(self, clip_meta: Dict[str, Any]) -> None:
        with self.lock:
            clips = list(self._state.get("recent_clips") or [])
            clips.insert(0, clip_meta)
            self._state["recent_clips"] = clips[:20]
            self._state["shorts_generated"] = int(self._state.get("shorts_generated", 0)) + 1
            self._state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> Dict[str, Any]:
        with self.lock:
            copied = dict(self._state)
            copied["recent_clips"] = list(self._state.get("recent_clips") or [])
            return copied

    def stop(self) -> None:
        self.stop_event.set()
        proc = self.active_proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        with self.lock:
            if self._state.get("status") in ("STARTING", "MONITORING", "ANALYZING_CHUNK", "IDLE"):
                self._state["status"] = "STOPPED"
            self._state["phase_label"] = "Directo detenido"
            self._state["step_detail"] = "Monitoreo en vivo detenido por el usuario."
            self._state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def resolve_live_stream_inputs(stream_url: str) -> Dict[str, Any]:
    """Resuelve la(s) URL(s) HLS/DASH reproducibles de un directo activo mediante yt-dlp (skip_download=True)."""
    import yt_dlp  # type: ignore

    ydl_opts: Dict[str, Any] = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 8,
        "format": "bestvideo[height<=1080][fps<=60]+bestaudio/best[height<=1080]/best",
    }
    if shutil.which("node") is not None:
        ydl_opts["js_runtimes"] = {"node": {}}

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(stream_url, download=False)

    if not isinstance(info, dict):
        raise RuntimeError("No se pudieron obtener metadatos de la transmisión.")

    if str(info.get("live_status") or "").lower() == "is_upcoming":
        raise ValueError("La transmisión en vivo aún no ha iniciado (evento programado).")

    title = str(info.get("title") or "").strip() or "Directo_Vivo"
    is_live = bool(info.get("is_live") or str(info.get("live_status") or "").lower() == "is_live")

    def _to_headers(raw: Any) -> Dict[str, str]:
        if isinstance(raw, dict):
            return {str(k): str(v) for k, v in raw.items() if v is not None}
        return {}

    video_url: Optional[str] = None
    audio_url: Optional[str] = None
    headers: Dict[str, str] = _to_headers(info.get("http_headers"))

    req_fmts = info.get("requested_formats")
    if isinstance(req_fmts, list) and req_fmts:
        for fmt in req_fmts:
            if not isinstance(fmt, dict):
                continue
            u = str(fmt.get("url") or "").strip()
            if not u.startswith(("http://", "https://")):
                continue
            vc = str(fmt.get("vcodec") or "none").lower()
            ac = str(fmt.get("acodec") or "none").lower()
            if vc != "none" and video_url is None:
                video_url = u
                headers = _to_headers(fmt.get("http_headers")) or headers
            elif ac != "none" and audio_url is None:
                audio_url = u
        if video_url and not audio_url and len(req_fmts) == 1:
            audio_url = None

    if not video_url:
        raw_formats = info.get("formats") or []
        combined: List[Tuple[int, str, Dict[str, str]]] = []
        v_only: List[Tuple[int, str, Dict[str, str]]] = []
        a_only: List[Tuple[int, str]] = []
        for fmt in raw_formats if isinstance(raw_formats, list) else []:
            if not isinstance(fmt, dict):
                continue
            u = str(fmt.get("url") or "").strip()
            if not u.startswith(("http://", "https://")):
                continue
            vc = str(fmt.get("vcodec") or "none").lower()
            ac = str(fmt.get("acodec") or "none").lower()
            h = int(fmt.get("height") or 0)
            score = (1000 + h) if h <= 1080 else max(100, 1080 - (h - 1080))
            if vc != "none" and ac != "none":
                combined.append((score, u, _to_headers(fmt.get("http_headers")) or headers))
            elif vc != "none":
                v_only.append((score, u, _to_headers(fmt.get("http_headers")) or headers))
            elif ac != "none":
                a_only.append((int(fmt.get("abr") or 0), u))
        if combined:
            combined.sort(key=lambda x: x[0], reverse=True)
            _, video_url, headers = combined[0]
        elif v_only:
            v_only.sort(key=lambda x: x[0], reverse=True)
            _, video_url, headers = v_only[0]
            if a_only:
                a_only.sort(key=lambda x: x[0], reverse=True)
                audio_url = a_only[0][1]

    if not video_url:
        fallback_u = str(info.get("url") or info.get("manifest_url") or "").strip()
        if fallback_u.startswith(("http://", "https://")):
            video_url = fallback_u

    if not video_url:
        raise RuntimeError("No se encontró un flujo de video reproducible para este directo.")

    return {
        "video_url": video_url,
        "audio_url": audio_url,
        "http_headers": headers,
        "title": title,
        "is_live": is_live,
    }


def capture_live_window_chunk(
    stream_url: str,
    output_chunk_path: Path,
    duration_sec: int,
    stop_event: threading.Event,
    session: Optional[LiveMonitorSession] = None,
) -> Dict[str, Any]:
    """Captura una ventana temporal acotada (-t duration_sec) del stream en vivo mediante FFmpeg."""
    import imageio_ffmpeg

    meta = resolve_live_stream_inputs(stream_url)
    video_url = str(meta["video_url"])
    audio_url = meta.get("audio_url")
    headers = meta.get("http_headers") or {}
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    output_chunk_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path = output_chunk_path.with_name(f"_staging_{output_chunk_path.name}")
    staging_path.unlink(missing_ok=True)

    header_blob = "".join(f"{k}: {v}\r\n" for k, v in headers.items() if k and v)
    cmd: List[str] = [ffmpeg_exe, "-y", "-loglevel", "error"]

    def _add_input(target_url: str) -> None:
        if target_url.startswith(("http://", "https://")):
            cmd.extend(["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"])
            if header_blob:
                cmd.extend(["-headers", header_blob])
        cmd.extend(["-i", target_url])

    _add_input(video_url)
    if audio_url:
        _add_input(str(audio_url))
        cmd.extend(["-map", "0:v:0", "-map", "1:a:0?"])

    cmd.extend(
        [
            "-t",
            str(max(10, int(duration_sec))),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(staging_path),
        ]
    )

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if session is not None:
        session.active_proc = proc

    timeout_at = time.monotonic() + float(duration_sec) + 45.0
    try:
        while proc.poll() is None:
            if stop_event.is_set():
                proc.terminate()
                try:
                    proc.wait(timeout=3.0)
                except Exception:
                    proc.kill()
                staging_path.unlink(missing_ok=True)
                return {"cancelled": True, "title": meta["title"], "is_live": meta["is_live"]}
            if time.monotonic() > timeout_at:
                proc.kill()
                staging_path.unlink(missing_ok=True)
                raise TimeoutError("Tiempo de captura de bloque en vivo excedido.")
            stop_event.wait(0.35)
    finally:
        if session is not None and session.active_proc is proc:
            session.active_proc = None

    if proc.returncode != 0:
        err_txt = (proc.stderr.read() or b"").decode("utf-8", errors="ignore").strip() if proc.stderr else ""
        staging_path.unlink(missing_ok=True)
        raise RuntimeError(f"FFmpeg falló capturando bloque en vivo (code={proc.returncode}): {err_txt[:240]}")

    ok, reason = main_daemon._validate_downloaded_video_integrity(staging_path, ffmpeg_exe)
    if not ok:
        staging_path.unlink(missing_ok=True)
        raise RuntimeError(f"Bloque en vivo inválido ({reason}).")

    if output_chunk_path.exists():
        output_chunk_path.unlink(missing_ok=True)
    os.replace(str(staging_path), str(output_chunk_path))
    return {
        "cancelled": False,
        "chunk_path": output_chunk_path,
        "title": meta["title"],
        "is_live": meta["is_live"],
    }


def _prepend_overlap_tail(
    prev_tail_path: Optional[Path],
    current_chunk: Path,
    overlap_sec: int,
    work_dir: Path,
    seg_idx: int,
    ffmpeg_exe: str,
) -> Tuple[Path, Optional[Path]]:
    """Prepara ventana de análisis concatenando el solapamiento previo y extrae nueva cola."""
    analysis_path = current_chunk
    if prev_tail_path is not None and prev_tail_path.exists() and overlap_sec > 0:
        concat_list = work_dir / f"concat_{seg_idx}.txt"
        merged_path = work_dir / f"window_{seg_idx}.mp4"
        concat_list.write_text(
            f"file '{prev_tail_path.resolve().as_posix()}'\nfile '{current_chunk.resolve().as_posix()}'\n",
            encoding="utf-8",
        )
        proc_m = subprocess.run(
            [
                ffmpeg_exe,
                "-y",
                "-loglevel",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list),
                "-c",
                "copy",
                str(merged_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        concat_list.unlink(missing_ok=True)
        if proc_m.returncode == 0 and merged_path.exists():
            ok, _ = main_daemon._validate_downloaded_video_integrity(merged_path, ffmpeg_exe)
            if ok:
                analysis_path = merged_path
            else:
                merged_path.unlink(missing_ok=True)
        else:
            merged_path.unlink(missing_ok=True)

    next_tail: Optional[Path] = None
    if overlap_sec > 0 and current_chunk.exists():
        candidate_tail = work_dir / f"tail_{seg_idx}.mp4"
        proc_t = subprocess.run(
            [
                ffmpeg_exe,
                "-y",
                "-loglevel",
                "error",
                "-sseof",
                f"-{int(overlap_sec)}",
                "-i",
                str(current_chunk),
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-avoid_negative_ts",
                "make_zero",
                str(candidate_tail),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc_t.returncode == 0 and candidate_tail.exists() and candidate_tail.stat().st_size > 1024:
            next_tail = candidate_tail
        else:
            candidate_tail.unlink(missing_ok=True)

    if prev_tail_path is not None:
        prev_tail_path.unlink(missing_ok=True)
    return analysis_path, next_tail


def run_live_monitor_loop(
    session: LiveMonitorSession,
    *,
    config_dir: Path,
    processing_dir: Path,
    output_root: Path,
    skill_analyzer: Any,
    skill_virality: Any,
    skill_renderer: Any,
    hub_category_keys: List[str],
    profile_cfg: Optional[Dict[str, Any]] = None,
) -> None:
    """Ciclo en segundo plano de captura rodante -> análisis IA -> filtrado -> render 9:16."""
    import imageio_ffmpeg

    work_dir = processing_dir / "live_chunks" / session.session_id
    work_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    seen_token_sets: List[Set[str]] = []
    prev_tail: Optional[Path] = None

    cfg_snap = session.to_dict()
    chunk_sec = int(cfg_snap["chunk_duration_sec"])
    overlap_sec = int(cfg_snap["overlap_sec"])
    min_score = int(cfg_snap["min_virality_score"])
    max_shorts_total = int(cfg_snap["max_shorts_total"])
    default_layout = str(cfg_snap.get("layout_mode") or "auto")
    default_sub_preset = str(cfg_snap.get("subtitle_preset") or "hormozi_pop")

    profile_scenes = (profile_cfg or {}).get("scenes") if isinstance(profile_cfg, dict) else None
    category_rules = profile_scenes if isinstance(profile_scenes, list) and profile_scenes else None
    auto_by_topic = bool((profile_cfg or {}).get("auto_categorize_by_topic", True)) if profile_cfg else True
    allowed_cats = (profile_cfg or {}).get("allowed_account_categories") if profile_cfg else None

    fallback_settings = {
        "content_category": "auto",
        "layout_mode": default_layout,
        "subtitle_preset": default_sub_preset,
        "subtitle_position": "auto",
        "cam_overlay_pos": "top_right",
        "custom_cam_box_norm": None,
        "custom_content_box_norm": None,
    }

    seg_idx = 0
    short_seq = 0
    dedicated_out_dir: Optional[Path] = None
    folder_slug = ""

    try:
        while not session.stop_event.is_set() and session.to_dict()["shorts_generated"] < max_shorts_total:
            seg_idx += 1
            session.update(
                status="MONITORING",
                phase_label=f"Capturando bloque en vivo #{seg_idx} ({chunk_sec}s)",
                step_detail=f"Grabando ventana rodante del directo para detectar momentos virales...",
            )
            chunk_path = work_dir / f"chunk_{seg_idx}.mp4"
            cap_res = capture_live_window_chunk(
                session.stream_url,
                chunk_path,
                chunk_sec,
                session.stop_event,
                session=session,
            )
            if cap_res.get("cancelled"):
                break

            stream_title = str(cap_res.get("title") or "Directo_Vivo")
            if dedicated_out_dir is None:
                folder_slug = main_daemon.build_video_date_project_id(stream_title, max_len=44)
                dedicated_out_dir = output_root / folder_slug
                dedicated_out_dir.mkdir(parents=True, exist_ok=True)

            cur_caps = int(session.to_dict()["segments_captured"]) + 1
            session.update(
                segments_captured=cur_caps,
                stream_title=stream_title,
                is_live_detected=bool(cap_res.get("is_live", False)),
                status="ANALYZING_CHUNK",
                phase_label=f"Analizando bloque #{seg_idx} con IA",
                step_detail=f"Transcribiendo audio y evaluando picos de viralidad en {stream_title}...",
            )

            analysis_path, next_tail = _prepend_overlap_tail(
                prev_tail,
                chunk_path,
                overlap_sec,
                work_dir,
                seg_idx,
                ffmpeg_exe,
            )
            prev_tail = next_tail

            try:
                analyses = skill_analyzer.transcribe_and_analyze_multiple(
                    video_path=analysis_path,
                    max_shorts=3,
                    enable_jumpcuts=True,
                )
            except Exception as ai_err:
                logger.warning("Error analizando bloque en vivo #%d: %s", seg_idx, ai_err)
                analyses = []

            hub_cfg = social_hub.get_raw_social_hub_config(config_dir)
            valid_keys = list(hub_category_keys or social_hub.get_category_keys(hub_cfg))
            full_words = getattr(skill_analyzer, "LAST_FULL_WORDS_BY_VIDEO", {}).get(
                str(analysis_path.resolve())
            )

            scored_clips: List[Tuple[int, Any, Optional[Dict[str, Any]]]] = []
            for a in analyses:
                eval_txt = f"{getattr(a, 'transcript_excerpt', '')} {getattr(a, 'first_person_caption', '')}".strip()
                resolved_rule = (
                    main_daemon.resolve_clip_category_rule(
                        video_path=analysis_path,
                        start_time=float(a.start_time),
                        end_time=float(a.end_time),
                        text=eval_txt,
                        title=str(getattr(a, "hook_title", "")),
                        category_rules=category_rules,
                        fallback_settings=fallback_settings,
                    )
                    if category_rules
                    else None
                )
                clip_cat = (
                    str(resolved_rule.get("category") or "auto")
                    if resolved_rule
                    else "auto"
                )
                llm_axes = {
                    "hook_strength": float(getattr(a, "hook_strength", 8.5)),
                    "standalone_value": float(getattr(a, "standalone_value", 8.5)),
                    "virality_potential": float(getattr(a, "virality_potential", 8.5)),
                }
                v_eval = skill_virality.evaluate_virality_10_points(
                    text=eval_txt,
                    duration=max(1.0, float(a.end_time) - float(a.start_time)),
                    words=getattr(a, "word_timestamps", []),
                    title=str(getattr(a, "hook_title", "")),
                    llm_scores=llm_axes,
                    category=clip_cat,
                    acoustic_score=float(getattr(a, "acoustic_energy_score", 7.5)),
                )
                scored_clips.append((int(v_eval.total_points), a, resolved_rule))

            scored_clips.sort(key=lambda item: item[0], reverse=True)

            for v_score, a, resolved_rule in scored_clips:
                if int(session.to_dict()["shorts_generated"]) >= max_shorts_total:
                    break
                if v_score < min_score:
                    continue
                moment_sig = f"{getattr(a, 'transcript_excerpt', '')} {getattr(a, 'first_person_caption', '')}".strip()
                if is_duplicate_live_moment(moment_sig, seen_token_sets):
                    continue

                short_seq += 1
                tier_tag = "Oro" if v_score >= 90 else ("Plata" if v_score >= 75 else "Meh")
                out_name = f"{folder_slug}_{short_seq:02d}_{tier_tag}_{v_score}pts.mp4"
                while (dedicated_out_dir / out_name).exists():
                    short_seq += 1
                    out_name = f"{folder_slug}_{short_seq:02d}_{tier_tag}_{v_score}pts.mp4"

                rule_layout = str((resolved_rule or {}).get("layout_mode") or default_layout)
                sub_preset = str((resolved_rule or {}).get("subtitle_preset") or default_sub_preset)
                sub_pos = str((resolved_rule or {}).get("subtitle_position") or "auto")
                cam_pos = str((resolved_rule or {}).get("cam_overlay_pos") or "top_right")
                cam_box = (resolved_rule or {}).get("custom_cam_box_norm")
                content_box = (resolved_rule or {}).get("custom_content_box_norm")
                clip_cat = str((resolved_rule or {}).get("category") or "auto")
                clip_scene_label = str((resolved_rule or {}).get("scene_label") or "")

                try:
                    rendered_path = skill_renderer.render_vertical_short(
                        video_path=analysis_path,
                        start_time=float(a.start_time),
                        end_time=float(a.end_time),
                        word_timestamps=list(getattr(a, "word_timestamps", [])),
                        output_dir=dedicated_out_dir,
                        output_filename=out_name,
                        bgm_mood="desactivada",
                        enable_bgm=False,
                        enable_dynamic_zoom=True,
                        enable_hook_punchin=True,
                        layout_mode=rule_layout,
                        playback_speed=1.20,
                        custom_cam_box_norm=cam_box,
                        custom_content_box_norm=content_box,
                        cam_overlay_pos=cam_pos,
                        subtitle_preset=sub_preset,
                        subtitle_position=sub_pos,
                        category_hint=clip_cat,
                        context_word_timestamps=full_words,
                    )
                except Exception as ren_err:
                    logger.warning("Se omitió clip en vivo %s por error al renderizar: %s", out_name, ren_err)
                    continue

                short_acct_cats = social_hub.classify_short_account_categories(
                    text=moment_sig,
                    title=str(getattr(a, "hook_title", "")),
                    tags=list(getattr(a, "tags", [])),
                    scene_category=clip_cat,
                    scene_label=clip_scene_label,
                    hub_cfg=hub_cfg,
                    allowed_categories=allowed_cats if allowed_cats else valid_keys,
                    auto_by_topic=auto_by_topic,
                )
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                meta_payload = {
                    "short_filename": rendered_path.name,
                    "virality_score": v_score,
                    "virality_grade": round(v_score / 10.0, 1),
                    "tier": tier_tag,
                    "category": clip_cat,
                    "account_categories": short_acct_cats,
                    "layout_used": rule_layout,
                    "subtitle_preset": sub_preset,
                    "subtitle_position": sub_pos,
                    "cam_overlay_pos": cam_pos,
                    "custom_cam_box_norm": list(cam_box) if cam_box is not None else None,
                    "custom_content_box_norm": list(content_box) if content_box is not None else None,
                    "duration_sec": round(float(a.end_time) - float(a.start_time), 2),
                    "hook_title": str(getattr(a, "hook_title", "")),
                    "caption": str(getattr(a, "first_person_caption", "")),
                    "tags": list(getattr(a, "tags", [])),
                    "bgm_mood": "desactivada",
                    "youtube_eligible": True,
                    "local_ready": True,
                    "live_stream_url": session.stream_url,
                    "created_at": now_str,
                }
                rendered_path.with_name(f"{rendered_path.stem}_meta.json").write_text(
                    json.dumps(meta_payload, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                session.append_clip(
                    {
                        "filename": rendered_path.name,
                        "folder": folder_slug,
                        "hook_title": meta_payload["hook_title"] or rendered_path.name,
                        "virality_score": v_score,
                        "tier": tier_tag,
                        "created_at": now_str,
                    }
                )

            cur_an = int(session.to_dict()["segments_analyzed"]) + 1
            session.update(
                segments_analyzed=cur_an,
                step_detail=f"Bloque #{seg_idx} analizado · Shorts acumulados: {session.to_dict()['shorts_generated']}.",
            )

            if analysis_path != chunk_path:
                analysis_path.unlink(missing_ok=True)
            chunk_path.unlink(missing_ok=True)

        if session.stop_event.is_set():
            session.update(
                status="STOPPED",
                phase_label="Directo detenido",
                step_detail=f"Monitoreo finalizado · {session.to_dict()['shorts_generated']} Short(s) generados.",
            )
        else:
            session.update(
                status="COMPLETED",
                phase_label="Cupo de Shorts alcanzado",
                step_detail=f"Se generaron {session.to_dict()['shorts_generated']} Short(s) del directo.",
            )
    except Exception as exc:
        logger.exception("Error en monitoreo de transmisión en vivo: %s", exc)
        session.update(
            status="ERROR",
            phase_label="Error en directo",
            step_detail=str(exc),
        )
    finally:
        if prev_tail is not None:
            prev_tail.unlink(missing_ok=True)
        shutil.rmtree(work_dir, ignore_errors=True)
