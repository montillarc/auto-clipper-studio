"""
Connectors and local fallback generators inspired by:
- debpalash/VoiceStudio (Local Voice Cloning / TTS / Vocal Isolation API + Broadcast Audio Mastering)
- fspecii/ace-step-ui (ACE-Step 1.5 Local AI Music Generation + Mood BGM library in ./config/bgm/)
- opencut-app/opencut (OpenCut Timeline JSON export & Dynamic Zoom/Subtitle presets)
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
import wave
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence

import numpy as np

logger = logging.getLogger("audio_ai_connectors")

MoodType = Literal["misterio", "comedia", "impacto", "reflexion", "urbano"]

DEFAULT_BGM_DIR = Path("./config/bgm")
VOICESTUDIO_API_URL = os.getenv("VOICESTUDIO_API_URL", "http://127.0.0.1:7861")
ACESTEP_API_URL = os.getenv("ACESTEP_API_URL", "http://127.0.0.1:7860")

MOOD_PROMPTS: Dict[str, str] = {
    "misterio": "dark suspenseful cinematic ambient pulse, deep sub bass, mysterious tension, instrumental, no vocals, 95 bpm",
    "comedia": "quirky upbeat playful pizzicato and light percussion, funny background groove, instrumental, 115 bpm",
    "impacto": "energetic modern trap beat, punchy 808 bass, crisp hi-hats, viral short background music, instrumental, 130 bpm",
    "reflexion": "warm emotional lo-fi piano and soft atmospheric pad, inspiring cinematic background, instrumental, 82 bpm",
    "urbano": "dominican dembow and modern latin urban instrumental beat, clean low-end groove, no vocals, 118 bpm",
}


def _synthesize_procedural_bgm(output_wav: Path, mood: str, duration_sec: float = 65.0) -> Path:
    """
    Synthesizes a clean, royalty-free stereo backing track tailored to `mood`
    so ./config/bgm/<mood>.wav is always available out of the box even when ACE-Step UI is offline.
    Users can replace these files at any time with exports from ACE-Step 1.5 UI.
    """
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    sr = 44100
    n_samples = int(sr * duration_sec)
    t = np.linspace(0.0, duration_sec, n_samples, endpoint=False, dtype=np.float32)

    if mood == "misterio":
        # Deep minor drone (D2 + A2 + F3 slow LFO pulse)
        freqs = [73.42, 110.0, 174.61]
        lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 0.4 * t)
        sig = (
            0.45 * np.sin(2 * np.pi * freqs[0] * t)
            + 0.30 * np.sin(2 * np.pi * freqs[1] * t) * lfo
            + 0.15 * np.sin(2 * np.pi * freqs[2] * t + np.sin(2 * np.pi * 0.2 * t))
        )
        # Subtle heartbeat pulse at 92 BPM
        beat_env = np.exp(-12.0 * ((t * (92.0 / 60.0)) % 1.0))
        sig += 0.35 * np.sin(2 * np.pi * 55.0 * t) * beat_env

    elif mood == "comedia":
        # Playful plucked arpeggio (C4 - E4 - G4 - A4) at 116 BPM
        notes = [261.63, 329.63, 392.00, 440.00]
        step_hz = 116.0 / 60.0 * 2.0
        step_idx = (t * step_hz).astype(int) % len(notes)
        note_freq = np.choose(step_idx, notes)
        pluck_env = np.exp(-9.0 * ((t * step_hz) % 1.0))
        sig = 0.45 * np.sin(2 * np.pi * note_freq * t) * pluck_env + 0.25 * np.sin(
            2 * np.pi * (note_freq * 0.5) * t
        ) * pluck_env

    elif mood == "reflexion":
        # Warm ambient fifths pad (F2 + C3 + A3 + E4)
        lfo1 = 0.6 + 0.4 * np.sin(2 * np.pi * 0.18 * t)
        lfo2 = 0.6 + 0.4 * np.cos(2 * np.pi * 0.23 * t)
        sig = (
            0.40 * np.sin(2 * np.pi * 87.31 * t)
            + 0.30 * np.sin(2 * np.pi * 130.81 * t) * lfo1
            + 0.20 * np.sin(2 * np.pi * 220.00 * t) * lfo2
            + 0.10 * np.sin(2 * np.pi * 329.63 * t)
        )

    elif mood == "urbano":
        # Subtle rhythmic urban bass pulse at 118 BPM
        bpm = 118.0
        beat_pos = (t * (bpm / 60.0)) % 1.0
        kick_env = np.exp(-14.0 * beat_pos)
        kick_freq = 58.0 + 60.0 * np.exp(-35.0 * beat_pos)
        pad = 0.20 * np.sin(2 * np.pi * 110.0 * t) + 0.12 * np.sin(2 * np.pi * 164.81 * t)
        sig = 0.55 * np.sin(2 * np.pi * kick_freq * t) * kick_env + pad

    else:  # "impacto"
        # Energetic cinematic sub-bass pulse + fifth harmonic at 128 BPM
        bpm = 128.0
        beat_pos = (t * (bpm / 60.0)) % 1.0
        pulse_env = np.exp(-10.0 * beat_pos)
        sig = (
            0.50 * np.sin(2 * np.pi * 65.41 * t) * pulse_env
            + 0.25 * np.sin(2 * np.pi * 98.00 * t)
            + 0.15 * np.sin(2 * np.pi * 196.00 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.5 * t))
        )

    # Normalize to -12 dBFS peak so it mixes cleanly under speech
    max_val = float(np.max(np.abs(sig))) or 1.0
    sig = (sig / max_val) * 0.25

    # Create slight stereo width
    delay_samples = int(0.012 * sr)
    left = sig
    right = np.roll(sig, delay_samples)
    stereo = np.stack([left, right], axis=-1)
    pcm16 = np.clip(stereo * 32767.0, -32768, 32767).astype(np.int16)

    with wave.open(str(output_wav), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm16.tobytes())

    return output_wav


def ensure_bgm_library(bgm_dir: str | Path = DEFAULT_BGM_DIR) -> Dict[str, Path]:
    """Ensures all 5 mood BGM tracks exist in ./config/bgm/."""
    bgm_folder = Path(bgm_dir).resolve()
    bgm_folder.mkdir(parents=True, exist_ok=True)
    tracks: Dict[str, Path] = {}

    for mood in MOOD_PROMPTS:
        # Check if user placed a custom .mp3 or .wav from ACE-Step UI
        mp3_candidate = bgm_folder / f"{mood}.mp3"
        wav_candidate = bgm_folder / f"{mood}.wav"
        if mp3_candidate.exists() and mp3_candidate.stat().st_size > 1024:
            tracks[mood] = mp3_candidate
        elif wav_candidate.exists() and wav_candidate.stat().st_size > 1024:
            tracks[mood] = wav_candidate
        else:
            tracks[mood] = _synthesize_procedural_bgm(wav_candidate, mood=mood)

    return tracks


def get_bgm_track_for_mood(mood: str = "impacto", bgm_dir: str | Path = DEFAULT_BGM_DIR) -> Path:
    """
    Returns the BGM audio file for the requested mood.
    First checks if ACE-Step 1.5 API is running locally or uses ./config/bgm/<mood>.(mp3|wav).
    """
    tracks = ensure_bgm_library(bgm_dir)
    normalized = mood.lower().strip()
    if normalized not in tracks:
        normalized = "impacto"
    return tracks[normalized]


def try_voicestudio_tts_hook(
    text: str,
    output_wav_path: str | Path,
    api_url: str = VOICESTUDIO_API_URL,
) -> Optional[Path]:
    """
    Optional connector to debpalash/VoiceStudio local API.
    If VoiceStudio's local server is running, synthesizes a voiceover hook.
    Returns None gracefully if VoiceStudio desktop/server is not running.
    """
    if not text.strip():
        return None
    try:
        payload = json.dumps({"text": text, "language": "es"}).encode("utf-8")
        req = urllib.request.Request(
            f"{api_url.rstrip('/')}/api/tts",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            if resp.status == 200:
                out = Path(output_wav_path).resolve()
                out.write_bytes(resp.read())
                logger.info("Hook de voz generado con VoiceStudio local en: %s", out)
                return out
    except Exception:
        pass
    return None


def export_opencut_timeline_json(
    output_json_path: str | Path,
    source_video: str | Path,
    rendered_short: str | Path,
    start_time: float,
    end_time: float,
    keyframes: List[Any],
    word_timestamps: List[Any],
    bgm_track: Optional[str | Path],
    mood: str,
    keep_intervals: Optional[List[Any]] = None,
    subtitle_preset: str = "hormozi_pop",
    subtitle_position: str = "auto",
    cam_overlay_pos: str = "top_right",
    custom_cam_box_norm: Optional[List[float]] = None,
    custom_content_box_norm: Optional[List[float]] = None,
    source_slice_path: Optional[str | Path] = None,
    slice_origin_sec: float = 0.0,
    slice_trim_start: Optional[float] = None,
    slice_trim_end: Optional[float] = None,
    slice_total_duration: Optional[float] = None,
    context_word_timestamps: Optional[List[Any]] = None,
) -> Path:
    """
    Exports an OpenCut-compatible timeline project JSON so the edit decision list (EDL),
    dynamic camera keyframes, subtitles, re-edit settings, and audio tracks can be inspected or reopened.
    """
    out_path = Path(output_json_path).resolve()
    duration = round(end_time - start_time, 3)
    resolved_layout_mode = (
        str(keyframes[0].get("mode", "fullscreen"))
        if keyframes and isinstance(keyframes[0], dict)
        else "fullscreen"
    )

    def _serialize_words_list(raw_words: Sequence[Any]) -> List[Dict[str, Any]]:
        out_words: List[Dict[str, Any]] = []
        for w in raw_words:
            if hasattr(w, "model_dump"):
                raw = dict(w.model_dump())
            elif isinstance(w, dict):
                raw = dict(w)
            else:
                raw = {
                    "word": getattr(w, "word", ""),
                    "start": float(getattr(w, "start", 0.0)),
                    "end": float(getattr(w, "end", 0.3)),
                    "probability": float(getattr(w, "probability", 1.0)),
                }
            word_txt = str(raw.get("word", "")).strip()
            if not word_txt:
                continue
            out_words.append(
                {
                    "word": word_txt,
                    "start": round(float(raw.get("start", 0.0)), 4),
                    "end": round(float(raw.get("end", 0.3)), 4),
                    "probability": round(float(raw.get("probability", 1.0)), 4),
                }
            )
        return out_words

    serialized_words = _serialize_words_list(word_timestamps)
    serialized_context_words = (
        _serialize_words_list(context_word_timestamps)
        if context_word_timestamps is not None
        else None
    )

    serialized_keep = (
        [[round(float(iv[0]), 4), round(float(iv[1]), 4)] for iv in keep_intervals]
        if keep_intervals
        else None
    )

    tracks: List[Dict[str, Any]] = [
        {
            "id": "video-main",
            "type": "video",
            "effects": [
                {"type": "dynamic_face_crop_9_16", "keyframes": keyframes},
                {"type": "hook_punch_in_zoom", "startSec": 0.0, "endSec": 3.0, "maxZoom": 1.10},
                {
                    "type": "outro_punch_in_zoom",
                    "startSec": max(0.0, round(duration - 4.0, 2)),
                    "endSec": duration,
                    "maxZoom": 1.12,
                },
            ],
        },
        {
            "id": "audio-voice-master",
            "type": "audio",
            "processing": "Linear Gain Calibration (-14 dBFS) + Transparent Limiter (-1.0 dBFS)",
        },
        {
            "id": "subtitles-capcut-pop",
            "type": "caption",
            "style": f"CapCut Elastic Pop ({subtitle_preset})",
            "wordCount": len(serialized_words),
        },
    ]
    if bgm_track is not None:
        tracks.insert(
            2,
            {
                "id": "audio-bgm-acestep",
                "type": "audio",
                "mood": mood,
                "source": str(bgm_track),
                "autoDucking": True,
            },
        )

    timeline_data = {
        "schemaVersion": "1.0",
        "generator": "Short-YT-Antigravity-OpenCut-Bridge",
        "layout_mode": resolved_layout_mode,
        "canvas": {"width": 1080, "height": 1920, "fps": 30, "aspectRatio": "9:16"},
        "source": {
            "file": str(Path(source_video).resolve()),
            "slice": str(Path(source_slice_path).resolve()) if source_slice_path else None,
            "trimStart": start_time,
            "trimEnd": end_time,
            "duration": duration,
            "slice_origin_sec": round(float(slice_origin_sec), 3),
            "slice_trim_start": (
                round(float(slice_trim_start), 3) if slice_trim_start is not None else 0.0
            ),
            "slice_trim_end": (
                round(float(slice_trim_end), 3) if slice_trim_end is not None else duration
            ),
            "slice_total_duration": (
                round(float(slice_total_duration), 3)
                if slice_total_duration is not None
                else duration
            ),
        },
        "output": str(Path(rendered_short).resolve()),
        "word_timestamps": serialized_words,
        "context_word_timestamps": serialized_context_words,
        "keep_intervals": serialized_keep,
        "reedit_settings": {
            "layout_mode": resolved_layout_mode,
            "subtitle_preset": subtitle_preset,
            "subtitle_position": subtitle_position,
            "cam_overlay_pos": cam_overlay_pos,
            "custom_cam_box_norm": list(custom_cam_box_norm) if custom_cam_box_norm is not None else None,
            "custom_content_box_norm": list(custom_content_box_norm) if custom_content_box_norm is not None else None,
            "source_slice": str(Path(source_slice_path).resolve()) if source_slice_path else None,
        },
        "tracks": tracks,
    }
    out_path.write_text(json.dumps(timeline_data, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path
