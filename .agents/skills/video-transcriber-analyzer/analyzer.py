"""
Skill 1: video-transcriber-analyzer
Transcribes Spanish video with faster-whisper (large-v3, cuda, float16, word_timestamps=True)
on NVIDIA RTX GPU (auto-registering cuBLAS/cuDNN DLL paths) and uses Google Antigravity SDK + Pydantic
to identify the best N non-overlapping 35-58s viral segments, including smart multi-zone sampling
for marathon live streams (>25 min).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import re
import site
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Sequence, Tuple

import cv2
import numpy as np
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator

load_dotenv()

LAST_FULL_WORDS_BY_VIDEO: Dict[str, List[Dict[str, Any]]] = {}


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

# Ensure NVIDIA CUDA 12 DLLs (cublas64_12.dll, cudnn64_9.dll) in .venv are visible on Windows
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

try:
    import imageio_ffmpeg
    FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_BIN = "ffmpeg"

from faster_whisper import WhisperModel
from google.antigravity import Agent, CapabilitiesConfig, LocalAgentConfig

logger = logging.getLogger("video-transcriber-analyzer")

MoodLiteral = Literal["misterio", "comedia", "impacto", "reflexion", "urbano"]


class WordTimestamp(BaseModel):
    """Word-level timestamp from faster-whisper."""

    word: str = Field(..., description="The transcribed word.")
    start: float = Field(..., description="Start timestamp in seconds.")
    end: float = Field(..., description="End timestamp in seconds.")
    probability: float = Field(default=1.0, description="Confidence score.")


class ViralSegmentCandidate(BaseModel):
    """Pydantic schema required from the LLM / Antigravity Agent for each viral clip."""

    start_time: float = Field(
        ...,
        description="Start timestamp in seconds of the viral segment.",
    )
    end_time: float = Field(
        ...,
        description="End timestamp in seconds of the viral segment (duration must be between 35 and 58 seconds).",
    )
    hook_title: str = Field(
        ...,
        description="Strategic clickbait title (truthful, high curiosity/CTR) in Spanish.",
    )
    first_person_caption: str = Field(
        ...,
        description="First-person caption written in a warm, relatable Dominican Spanish tone, including #Shorts and #Viral.",
    )
    tags: List[str] = Field(
        ...,
        description="List of SEO tags for YouTube Shorts.",
    )
    bgm_mood: MoodLiteral = Field(
        default="impacto",
        description="Musical mood for ACE-Step background music: 'misterio', 'comedia', 'impacto', 'reflexion', or 'urbano'.",
    )
    hook_strength: float = Field(
        default=8.5,
        ge=0.0,
        le=10.0,
        description="LLM semantic evaluation of hook strength in the first 3 seconds (0.0 - 10.0).",
    )
    standalone_value: float = Field(
        default=8.5,
        ge=0.0,
        le=10.0,
        description="LLM semantic evaluation of standalone narrative coherence (0.0 - 10.0).",
    )
    virality_potential: float = Field(
        default=8.5,
        ge=0.0,
        le=10.0,
        description="LLM semantic evaluation of shareability/debate virality potential (0.0 - 10.0).",
    )
    acoustic_energy_score: float = Field(
        default=7.5,
        ge=0.0,
        le=10.0,
        description="Acoustic energy & decibel spike score computed from 16kHz audio signal (0.0 - 10.0).",
    )

    @field_validator("first_person_caption")
    @classmethod
    def ensure_required_hashtags(cls, v: str) -> str:
        caption = v.strip()
        if "#viral" not in caption.lower():
            caption = f"{caption} #Viral"
        return caption

    @field_validator("tags")
    @classmethod
    def ensure_non_empty_tags(cls, v: List[str]) -> List[str]:
        cleaned = [t.strip().lstrip("#") for t in v if t.strip()]
        for required in ("Viral", "Shorts"):
            if required.lower() not in {t.lower() for t in cleaned}:
                cleaned.append(required)
        return cleaned

    @model_validator(mode="after")
    def validate_duration(self) -> "ViralSegmentCandidate":
        duration = self.end_time - self.start_time
        if duration < 20.0 or duration > 180.0:
            raise ValueError(
                f"El segmento viral debe durar entre 20 y 180 segundos (actual: {duration:.2f}s)."
            )
        return self


class ViralSegmentBatch(BaseModel):
    """Wrapper schema when requesting multiple viral clips from a single video."""

    clips: List[ViralSegmentCandidate] = Field(
        ...,
        description="List of non-overlapping viral segments ranked from highest to lowest viral potential.",
    )


class ViralClipAnalysis(ViralSegmentCandidate):
    """Full output of Skill 1 including word-level timestamps and non-silent subsegments for Skill 2."""

    word_timestamps: List[WordTimestamp] = Field(
        default_factory=list,
        description="Word-level timestamps within [start_time, end_time] (adjusted for any jump-cuts).",
    )
    keep_intervals: List[Tuple[float, float]] = Field(
        default_factory=list,
        description="Sub-intervals (relative to clip start) kept after trimming dead silences (>0.95s).",
    )
    transcript_excerpt: str = Field(
        default="",
        description="Full text of the selected viral segment.",
    )


SYSTEM_PROMPT = """Eres un Productor Ejecutivo y Estratega Viral de YouTube Shorts en República Dominicana.
Analiza la transcripción con marcas de tiempo en segundos y selecciona LOS FRAGMENTOS MÁS VIRALES (sin que se solapen entre sí), donde cada fragmento tenga una duración estricta de entre 35.0 y 58.0 segundos.

Cada fragmento seleccionado DEBE cumplir con esta estructura narrativa de 4 partes:
1) Gancho o chiste inicial fuerte (atrapa la atención en los primeros 3 segundos).
2) Misterio o pregunta sobre el tema (abre un loop mental o intriga).
3) Desarrollo / hechos (explicación dinámica y directa al grano).
4) Conclusión o remate (punchline final o reflexión contundente).

Reglas de salida para cada clip:
- `start_time` y `end_time`: segundos exactos basados en la transcripción (`35 <= end_time - start_time <= 58`).
- `hook_title`: Título con clickbait estratégico sin mentir, súper atractivo y directo.
- `first_person_caption`: Escrito en primera persona ("Yo...", "Mi gente...", "Miren esto...") con tono cercano dominicano natural (ej. "Mi gente, miren qué locura...", "De verdad que uno ve cosas..."), e incluyendo obligatoriamente `#Shorts` y `#Viral`.
- `tags`: Lista de 6 a 12 etiquetas relevantes en español.
- `bgm_mood`: Elige uno entre `"misterio"`, `"comedia"`, `"impacto"`, `"reflexion"` o `"urbano"` según la vibra del clip para la música de fondo.

Devuelve ÚNICAMENTE un objeto JSON válido que cumpla con el esquema solicitado."""


def _get_video_duration_sec(video_path: Path) -> float:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return 0.0
    fps = float(cap.get(cv2.CAP_PROP_FPS)) or 30.0
    frames = float(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0.0
    cap.release()
    return frames / fps if fps > 0 else 0.0


def analyze_audio_energy_profile(
    media_path: str | Path,
    window_sec: float = 1.0,
) -> List[Dict[str, float]]:
    """
    Stage 3.1 — Acoustic Energy & Decibel Spike Analysis (16kHz PCM):
    Extracts or reads 16kHz mono PCM audio and computes RMS energy, peak amplitude,
    decibels (dBFS), and a normalized 0.0-10.0 acoustic energy score per window_sec.
    """
    path_obj = Path(media_path).resolve()
    if not path_obj.exists():
        return []

    temp_wav: Optional[Path] = None
    target_wav = path_obj
    try:
        if path_obj.suffix.lower() != ".wav":
            fd, tmp_name = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            temp_wav = Path(tmp_name)
            cmd = [
                FFMPEG_BIN,
                "-y",
                "-i",
                str(path_obj),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                str(temp_wav),
            ]
            subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                **_silent_subprocess_kwargs(),
            )
            if not temp_wav.exists() or temp_wav.stat().st_size < 1000:
                return []
            target_wav = temp_wav

        with wave.open(str(target_wav), "rb") as wf:
            sr = wf.getframerate() or 16000
            n_channels = wf.getnchannels() or 1
            n_frames = wf.getnframes()
            raw_bytes = wf.readframes(n_frames)

        if not raw_bytes:
            return []

        samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if n_channels > 1:
            samples = samples.reshape(-1, n_channels).mean(axis=1)

        win_samples = max(1, int(round(sr * max(0.25, window_sec))))
        total_samples = len(samples)
        profile: List[Dict[str, float]] = []

        for idx, start_sample in enumerate(range(0, total_samples, win_samples)):
            chunk = samples[start_sample : start_sample + win_samples]
            if len(chunk) == 0:
                continue
            rms = float(np.sqrt(np.mean(np.square(chunk))))
            peak = float(np.max(np.abs(chunk)))
            dbfs = float(20.0 * np.log10(max(rms, 1e-5)))
            # Map dBFS from [-48 dB .. -3 dB] -> [0.0 .. 10.0]
            norm_db = (dbfs + 48.0) / 45.0
            spike_boost = 1.25 if peak >= 0.65 else (0.6 if peak >= 0.35 else 0.0)
            score_10 = round(min(10.0, max(0.0, norm_db * 9.0 + spike_boost)), 2)

            t_start = round(idx * window_sec, 2)
            t_end = round(min(total_samples / float(sr), (idx + 1) * window_sec), 2)
            profile.append(
                {
                    "start": t_start,
                    "end": t_end,
                    "rms": round(rms, 5),
                    "peak": round(peak, 5),
                    "dbfs": round(dbfs, 2),
                    "energy_score": score_10,
                }
            )
        return profile
    except Exception as exc:
        logger.warning("No se pudo calcular perfil acústico para %s: %s", path_obj.name, exc)
        return []
    finally:
        if temp_wav is not None:
            try:
                temp_wav.unlink(missing_ok=True)
            except Exception:
                pass


def compute_segment_acoustic_score(
    energy_profile: List[Dict[str, float]],
    start_time: float,
    end_time: float,
) -> float:
    """
    Computes the 0.0-10.0 acoustic excitement score of a segment [start_time, end_time]
    by combining mean energy (45%) and top 25% decibel spike intensity (55%).
    """
    if not energy_profile:
        return 7.5
    matching = [
        float(w["energy_score"])
        for w in energy_profile
        if float(w["end"]) > start_time and float(w["start"]) < end_time
    ]
    if not matching:
        return 7.5
    arr = np.array(matching, dtype=np.float32)
    mean_val = float(np.mean(arr))
    top_k = max(1, int(np.ceil(len(arr) * 0.25)))
    top_spikes_mean = float(np.mean(np.sort(arr)[-top_k:]))
    combined = 0.45 * mean_val + 0.55 * top_spikes_mean
    return round(min(10.0, max(0.0, combined)), 2)


def select_peak_guided_zones(
    energy_profile: List[Dict[str, float]],
    duration_sec: float,
    num_zones: int,
    window_len: float = 85.0,
) -> List[float]:
    """
    Selects `num_zones` non-overlapping start timestamps of length `window_len`
    guided by real acoustic energy spikes across the broadcast.
    """
    num_zones = max(1, int(num_zones))
    if duration_sec <= window_len:
        return [0.0]

    usable_start = min(180.0, duration_sec * 0.03) if duration_sec > 600.0 else 0.0
    usable_end = max(usable_start + window_len, duration_sec - min(120.0, duration_sec * 0.02))

    if not energy_profile:
        step = (usable_end - usable_start - window_len) / max(1, num_zones - 1)
        return [round(usable_start + i * max(1.0, step), 2) for i in range(num_zones)]

    stride = max(2.0, min(15.0, (usable_end - usable_start) / max(10.0, num_zones * 6.0)))
    candidates: List[Tuple[float, float]] = []
    cur = usable_start
    while cur + window_len <= usable_end + 0.5:
        score = compute_segment_acoustic_score(energy_profile, cur, cur + window_len)
        candidates.append((score, round(cur, 2)))
        cur += stride

    candidates.sort(key=lambda x: x[0], reverse=True)
    chosen: List[float] = []
    min_gap = window_len * 0.65
    for _, start_t in candidates:
        if len(chosen) >= num_zones:
            break
        if all(abs(start_t - c) >= min_gap for c in chosen):
            chosen.append(start_t)

    if len(chosen) < num_zones:
        step = (usable_end - usable_start - window_len) / max(1, num_zones - 1)
        for i in range(num_zones):
            if len(chosen) >= num_zones:
                break
            fallback_t = round(usable_start + i * max(1.0, step), 2)
            if all(abs(fallback_t - c) >= window_len * 0.35 for c in chosen):
                chosen.append(fallback_t)

    chosen.sort()
    return chosen


def _setup_nvidia_dll_paths() -> None:
    """Configura las rutas de DLLs de NVIDIA en Windows para CUDA/cuDNN/cuBLAS."""
    if sys.platform != "win32":
        return
    venv_nvidia = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    if venv_nvidia.exists():
        for bin_dir in venv_nvidia.glob("*/bin"):
            if bin_dir.is_dir():
                os.environ["PATH"] = str(bin_dir.resolve()) + os.pathsep + os.environ.get("PATH", "")
                try:
                    os.add_dll_directory(str(bin_dir.resolve()))
                except Exception:
                    pass


_WHISPER_MODEL_CACHE: Dict[Tuple[str, str, str], WhisperModel] = {}

_BASE_DOMAIN_HOTWORDS: Tuple[str, ...] = (
    "CreadorStudio",
    "Outlook",
    "Anthropic",
    "Claude",
    "ChatGPT",
    "OpenAI",
    "Gemini",
    "NVIDIA",
    "RTX",
    "DLSS",
    "PlayStation",
    "PS5",
    "Nintendo Switch",
    "Zelda",
    "Link",
    "Sheik",
    "Twitch",
    "Kick",
    "YouTube",
    "OmeTV",
    "Donald Trump",
    "República Dominicana",
    "Santo Domingo",
    "klk",
    "tigueraje",
    "vaina",
    "coro",
)

_PHONETIC_WORD_REPLACEMENTS: Dict[str, str] = {
    "aulut": "Outlook",
    "aulook": "Outlook",
    "autluk": "Outlook",
    "outluk": "Outlook",
    "outlook": "Outlook",
    "antropic": "Anthropic",
    "antrópic": "Anthropic",
    "antropik": "Anthropic",
    "anthropic": "Anthropic",
    "chadgpt": "ChatGPT",
    "chatgbt": "ChatGPT",
    "chatgepete": "ChatGPT",
    "chatgpt": "ChatGPT",
    "openai": "OpenAI",
    "dlss": "DLSS",
    "rtx": "RTX",
    "nvidia": "NVIDIA",
    "ps5": "PS5",
    "ometv": "OmeTV",
    "creadorstudio": "CreadorStudio",
}

_HALLUCINATION_PHRASES: Tuple[str, ...] = (
    "subtítulos realizados por",
    "subtitulos realizados por",
    "amara.org",
    "suscríbete al canal",
    "suscribete al canal",
    "gracias por ver el video",
    "transcripción por",
    "transcripcion por",
)

_HALLUCINATION_SEQUENCES: Tuple[Tuple[str, ...], ...] = (
    ("subtítulos", "realizados", "por"),
    ("subtitulos", "realizados", "por"),
    ("suscríbete", "al", "canal"),
    ("suscribete", "al", "canal"),
    ("gracias", "por", "ver", "el", "video"),
)

_TOKEN_AFFINITY_RE = re.compile(r"^([^\wáéíóúÁÉÍÓÚñÑüÜ]*)(.+?)([^\wáéíóúÁÉÍÓÚñÑüÜ]*)$")


def _extract_whisper_ready_wav(
    source_path: Path,
    out_wav: Path,
    start_sec: Optional[float] = None,
    duration_sec: Optional[float] = None,
) -> bool:
    """
    Extrae audio mono 16kHz PCM pre-acondicionado exclusivamente para Whisper
    (highpass 65Hz + lowpass 7.8kHz + dynaudnorm suave para voces bajas).
    No altera el audio del MP4 final.
    """
    if not source_path.exists() or source_path.stat().st_size < 4096:
        return False
    cmd: List[str] = [FFMPEG_BIN, "-y"]
    if start_sec is not None and start_sec > 0:
        cmd.extend(["-ss", f"{float(start_sec):.3f}"])
    if duration_sec is not None and duration_sec > 0:
        cmd.extend(["-t", f"{float(duration_sec):.3f}"])
    cmd.extend(
        [
            "-i",
            str(source_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-af",
            "highpass=f=65,lowpass=f=7800,dynaudnorm=f=150:g=13:p=0.92:m=15.0",
            "-c:a",
            "pcm_s16le",
            str(out_wav),
        ]
    )
    subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        **_silent_subprocess_kwargs(),
    )
    return out_wav.exists() and out_wav.stat().st_size >= 4000


def _build_spanish_domain_prompt(video_path: Path) -> Tuple[str, str]:
    """Genera (initial_prompt, hotwords) adaptado al español dominicano, tech y título del video."""
    raw_stem = re.sub(r"[#]\S+", " ", video_path.stem)
    stem_tokens = [
        tok
        for tok in re.findall(r"[A-Za-z0-9áéíóúÁÉÍÓÚñÑüÜ]{3,}", raw_stem.replace("_", " ").replace("-", " "))
        if not tok.isdigit()
    ]
    unique_stem = list(dict.fromkeys(stem_tokens))[:8]
    topic_hint = f" Tema del directo: {' '.join(unique_stem)}." if unique_stem else ""

    hotwords_list = list(_BASE_DOMAIN_HOTWORDS)
    existing_lower = {w.lower() for w in hotwords_list}
    for tok in unique_stem:
        if len(tok) >= 4 and tok.lower() not in existing_lower:
            hotwords_list.append(tok)
            existing_lower.add(tok.lower())

    prompt = (
        "Transcripción fiel en español natural (República Dominicana). "
        "Respeta signos de interrogación, exclamación y nombres propios reales como "
        "CreadorStudio, Outlook, Anthropic, Claude, ChatGPT, OpenAI, Gemini, NVIDIA RTX DLSS, "
        "PS5, Nintendo Switch, Zelda, Link, Sheik, Twitch, Kick, YouTube, OmeTV y Donald Trump."
        f"{topic_hint} ¿Qué es lo que está pasando, mi gente?"
    )
    return prompt, ", ".join(hotwords_list)


def _replace_single_token_phonetics(token: str) -> str:
    match = _TOKEN_AFFINITY_RE.match(token.strip())
    if not match:
        return token.strip()
    lead, core, trail = match.groups()
    replacement = _PHONETIC_WORD_REPLACEMENTS.get(core.lower())
    if replacement is not None:
        return f"{lead}{replacement}{trail}"
    return f"{lead}{core}{trail}"


def polish_spanish_transcript_text(text: str) -> str:
    """Corrige confusiones fonéticas frecuentes de Whisper en español y descarta alucinaciones."""
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    lower_full = cleaned.lower()
    if any(phrase in lower_full for phrase in _HALLUCINATION_PHRASES):
        stripped = cleaned
        for phrase in _HALLUCINATION_PHRASES:
            stripped = re.sub(re.escape(phrase), "", stripped, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s{2,}", " ", stripped).strip(" .,-:;")
        if not cleaned:
            return ""

    # Frases multi-palabra específicas antes de corrección token por token
    cleaned = re.sub(r"\bdonald\s+trum+\b", "Donald Trump", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bcreador\s+rc\b", "CreadorStudio", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bome\s+tv\b", "OmeTV", cleaned, flags=re.IGNORECASE)

    tokens = cleaned.split()
    polished_tokens = [_replace_single_token_phonetics(tok) for tok in tokens]
    return " ".join(tok for tok in polished_tokens if tok)


def _strip_hallucination_runs(items: List[WordTimestamp]) -> List[WordTimestamp]:
    """Elimina secuencias completas conocidas de alucinaciones de silencio de Whisper."""
    n = len(items)
    skip = [False] * n
    cores = [
        re.sub(r"[^\wáéíóúÁÉÍÓÚñÑüÜ.]", "", it.word.lower())
        for it in items
    ]
    for i in range(n):
        if "amara.org" in cores[i]:
            start_rm = max(0, i - 3) if i >= 2 and any("subt" in cores[k] for k in range(max(0, i - 3), i)) else i
            for k in range(start_rm, i + 1):
                skip[k] = True
            continue
        for seq in _HALLUCINATION_SEQUENCES:
            seq_len = len(seq)
            if i + seq_len <= n and tuple(cores[i : i + seq_len]) == seq:
                for k in range(i, i + seq_len):
                    skip[k] = True
    return [it for idx, it in enumerate(items) if not skip[idx]]


def clean_and_polish_word_timestamps(
    words: Sequence[Any],
    clip_duration: Optional[float] = None,
) -> List[WordTimestamp]:
    """
    Normaliza, pule fonéticamente y alinea tiempos monótonos [start, end] para subtítulos ASS,
    eliminando tokens basura de silencio y duraciones congeladas mayores a 1.40s.
    """
    raw_items: List[WordTimestamp] = []
    for w in words:
        if hasattr(w, "model_dump"):
            d = dict(w.model_dump())
        elif isinstance(w, dict):
            d = dict(w)
        else:
            d = {
                "word": getattr(w, "word", ""),
                "start": getattr(w, "start", 0.0),
                "end": getattr(w, "end", 0.2),
                "probability": getattr(w, "probability", 1.0),
            }
        w_text = str(d.get("word", "")).strip()
        if not w_text:
            continue
        prob = float(d.get("probability", 1.0))
        alnum = re.findall(r"[A-Za-z0-9áéíóúÁÉÍÓÚñÑüÜ]", w_text)
        if prob < 0.16 and len(alnum) <= 1:
            continue
        if not alnum:
            continue
        raw_items.append(
            WordTimestamp(
                word=w_text,
                start=float(d.get("start", 0.0)),
                end=float(d.get("end", 0.2)),
                probability=prob,
            )
        )

    if not raw_items:
        return []

    filtered = _strip_hallucination_runs(raw_items)
    if not filtered:
        return []

    # Corrección de bigramas partidos (ej. "Donald" + "Trum" -> "Donald" + "Trump") y tokens individuales
    polished_words: List[WordTimestamp] = []
    for idx, item in enumerate(filtered):
        tok = _replace_single_token_phonetics(item.word)
        if idx > 0:
            prev_core = re.sub(r"[^\wáéíóúÁÉÍÓÚñÑüÜ]", "", polished_words[-1].word.lower())
            cur_match = _TOKEN_AFFINITY_RE.match(tok)
            if prev_core == "donald" and cur_match:
                lead, core, trail = cur_match.groups()
                if core.lower() in ("trum", "trump", "trun"):
                    polished_words[-1] = WordTimestamp(
                        word="Donald",
                        start=polished_words[-1].start,
                        end=polished_words[-1].end,
                        probability=polished_words[-1].probability,
                    )
                    tok = f"{lead}Trump{trail}"
        polished_words.append(
            WordTimestamp(
                word=tok,
                start=item.start,
                end=item.end,
                probability=item.probability,
            )
        )

    # Normalización temporal monótona [0.08s .. 1.40s] sin solapamientos
    normalized: List[WordTimestamp] = []
    prev_end = 0.0
    max_dur_cap = float(clip_duration) if (clip_duration is not None and clip_duration > 0) else None
    for item in polished_words:
        s_val = max(prev_end, max(0.0, round(float(item.start), 3)))
        if max_dur_cap is not None and s_val >= max_dur_cap - 0.02:
            break
        raw_end = max(s_val + 0.08, round(float(item.end), 3))
        e_val = min(raw_end, round(s_val + 1.40, 3))
        if max_dur_cap is not None:
            e_val = min(round(max_dur_cap, 3), e_val)
            if e_val <= s_val + 0.04:
                continue
        prev_end = e_val
        normalized.append(
            WordTimestamp(
                word=item.word,
                start=s_val,
                end=e_val,
                probability=round(float(item.probability), 3),
            )
        )
    return normalized


def _load_whisper_model(
    model_size: str = "large-v3",
    device: str = "cuda",
    compute_type: str = "float16",
) -> WhisperModel:
    cache_key = (model_size, device, compute_type)
    if cache_key in _WHISPER_MODEL_CACHE:
        return _WHISPER_MODEL_CACHE[cache_key]

    _setup_nvidia_dll_paths()
    logger.info(
        "Cargando modelo faster-whisper '%s' (device=%s, compute_type=%s)...",
        model_size,
        device,
        compute_type,
    )
    try:
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
    except Exception as cuda_err:
        logger.warning(
            "No se pudo inicializar CUDA (%s). Usando fallback en CPU (int8)...",
            cuda_err,
        )
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
    _WHISPER_MODEL_CACHE[cache_key] = model
    return model


def _collect_whisper_segments_and_words(
    segs_gen: Any,
    total_dur: float,
    segment_list: list[dict],
    all_words: list[WordTimestamp],
    progress_callback: Optional[Callable[[int, str, str], None]] = None,
) -> None:
    last_pct_reported = -1
    for seg in segs_gen:
        seg_text = polish_spanish_transcript_text(str(seg.text))
        if not seg_text:
            continue
        seg_s = round(float(seg.start), 2)
        seg_e = round(float(seg.end), 2)
        segment_list.append({"start": seg_s, "end": seg_e, "text": seg_text})
        if getattr(seg, "words", None):
            for w in seg.words:
                w_text = str(w.word).strip()
                if w_text:
                    all_words.append(
                        WordTimestamp(
                            word=w_text,
                            start=round(float(w.start), 3),
                            end=round(float(w.end), 3),
                            probability=round(float(getattr(w, "probability", 1.0)), 3),
                        )
                    )
        if callable(progress_callback):
            cur_pct = int(22 + min(1.0, max(0.0, seg_e / max(1.0, total_dur))) * 16)
            if cur_pct >= last_pct_reported + 2:
                last_pct_reported = cur_pct
                try:
                    progress_callback(
                        cur_pct,
                        "Fase 2/4 · Transcripción GPU Completa",
                        f"Transcribiendo 100% ({seg_e / 60.0:.1f} / {total_dur / 60.0:.1f} min) · {len(segment_list)} segmentos...",
                    )
                except Exception:
                    pass


def transcribe_video(
    video_path: str | Path,
    model_size: str = "large-v3",
    device: str = "cuda",
    compute_type: str = "float16",
    max_shorts_hint: int = 12,
    progress_callback: Optional[Callable[[int, str, str], None]] = None,
) -> tuple[list[dict], list[WordTimestamp]]:
    """
    Transcribes the video in Spanish using faster-whisper with pre-conditioned 16kHz audio,
    domain prompt/hotwords, phonetic polishing, and word_timestamps=True.
    """
    video_path = Path(video_path).resolve()
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    cache_dir = video_path.parent.parent / "processing"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f".transcript_cache_{video_path.stat().st_size}.json"
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if cached.get("cache_version") == 2:
                segs = cached.get("segments", [])
                words = clean_and_polish_word_timestamps(
                    [WordTimestamp(**w) for w in cached.get("words", [])]
                )
                if segs and words:
                    logger.info(
                        "Transcripción v2 cargada desde caché rápido (%d segmentos, %d palabras).",
                        len(segs),
                        len(words),
                    )
                    return segs, words
        except Exception:
            pass

    duration_sec = _get_video_duration_sec(video_path)
    model = _load_whisper_model(model_size=model_size, device=device, compute_type=compute_type)
    domain_prompt, domain_hotwords = _build_spanish_domain_prompt(video_path)

    segment_list: list[dict] = []
    all_words: list[WordTimestamp] = []

    logger.info(
        "Transcribiendo stream completo al 100%% (duración=%.1f min) en %s con BatchedInferencePipeline...",
        duration_sec / 60.0 if duration_sec > 0 else 0.0,
        device,
    )
    if callable(progress_callback):
        try:
            progress_callback(
                22,
                "Fase 2/4 · Transcripción GPU Completa",
                f"Pre-acondicionando audio y transcribiendo el 100% ({duration_sec / 60.0:.1f} min)...",
            )
        except Exception:
            pass

    common_whisper_kwargs: Dict[str, Any] = {
        "language": "es",
        "word_timestamps": True,
        "beam_size": 5,
        "best_of": 5,
        "initial_prompt": domain_prompt,
        "hotwords": domain_hotwords,
        "repetition_penalty": 1.08,
        "no_repeat_ngram_size": 3,
        "compression_ratio_threshold": 2.2,
        "hallucination_silence_threshold": 1.5,
        "vad_filter": True,
        "vad_parameters": {
            "threshold": 0.35,
            "min_speech_duration_ms": 180,
            "min_silence_duration_ms": 450,
            "speech_pad_ms": 280,
        },
    }

    def _run_whisper_on_source(audio_source: str) -> None:
        try:
            from faster_whisper import BatchedInferencePipeline  # type: ignore

            batched = BatchedInferencePipeline(model=model)
            segs_gen, info = batched.transcribe(
                audio_source,
                batch_size=8 if device == "cuda" else 4,
                **common_whisper_kwargs,
            )
        except Exception as batch_exc:
            logger.info("BatchedInferencePipeline fallback a model.transcribe estándar (%s)", batch_exc)
            segs_gen, info = model.transcribe(
                audio_source,
                **common_whisper_kwargs,
            )

        total_dur = max(1.0, float(getattr(info, "duration", 0.0) or duration_sec or 1.0))
        logger.info(
            "Idioma detectado/forzado: %s (prob=%.2f, duración=%.1fs)",
            getattr(info, "language", "es"),
            float(getattr(info, "language_probability", 1.0)),
            total_dur,
        )
        _collect_whisper_segments_and_words(
            segs_gen, total_dur, segment_list, all_words, progress_callback=progress_callback
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        full_wav = Path(tmpdir) / "full_audio_16k_whisper.wav"
        if _extract_whisper_ready_wav(video_path, full_wav):
            _run_whisper_on_source(str(full_wav))
        else:
            _run_whisper_on_source(str(video_path))

    all_words = clean_and_polish_word_timestamps(all_words)

    logger.info(
        "Transcripción completada: %d segmentos, %d palabras con timestamp.",
        len(segment_list),
        len(all_words),
    )
    try:
        cache_file.write_text(
            json.dumps(
                {
                    "cache_version": 2,
                    "segments": segment_list,
                    "words": [w.model_dump() for w in all_words],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass
    return segment_list, all_words


def refine_clip_words_high_precision(
    video_path: str | Path,
    start_time: float,
    end_time: float,
    fallback_words: Sequence[Any] = (),
    model_size: str = "large-v3",
    device: str = "cuda",
    compute_type: str = "float16",
) -> List[WordTimestamp]:
    """
    Segunda pasada de alta precisión (model.transcribe secuencial con condition_on_previous_text=True)
    sobre el recorte exacto del Short y su audio 16kHz pre-acondicionado para eliminar errores de subtítulos.
    """
    clip_duration = max(0.0, float(end_time) - float(start_time))
    cleaned_fallback = clean_and_polish_word_timestamps(
        fallback_words,
        clip_duration=clip_duration if clip_duration > 0 else None,
    )
    src_path = Path(video_path).resolve()
    if not src_path.exists() or src_path.stat().st_size < 8192 or clip_duration <= 0.5:
        return cleaned_fallback

    actual_extract_start = max(0.0, float(start_time) - 0.15)
    lead_pad = float(start_time) - actual_extract_start
    extract_dur = clip_duration + lead_pad + 0.15

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            clip_wav = Path(tmpdir) / "clip_whisper_16k.wav"
            if not _extract_whisper_ready_wav(
                src_path,
                clip_wav,
                start_sec=actual_extract_start,
                duration_sec=extract_dur,
            ):
                return cleaned_fallback

            model = _load_whisper_model(model_size=model_size, device=device, compute_type=compute_type)
            domain_prompt, domain_hotwords = _build_spanish_domain_prompt(src_path)
            segs_gen, _ = model.transcribe(
                str(clip_wav),
                language="es",
                word_timestamps=True,
                beam_size=5,
                best_of=5,
                temperature=[0.0, 0.2, 0.4],
                condition_on_previous_text=True,
                initial_prompt=domain_prompt,
                hotwords=domain_hotwords,
                repetition_penalty=1.08,
                no_repeat_ngram_size=3,
                compression_ratio_threshold=2.2,
                hallucination_silence_threshold=1.2,
                vad_filter=True,
                vad_parameters={
                    "threshold": 0.32,
                    "min_speech_duration_ms": 150,
                    "min_silence_duration_ms": 400,
                    "speech_pad_ms": 260,
                },
            )
            raw_clip_words: List[WordTimestamp] = []
            for seg in segs_gen:
                if not getattr(seg, "words", None):
                    continue
                for w in seg.words:
                    w_txt = str(w.word).strip()
                    if not w_txt:
                        continue
                    rel_s = float(w.start) - lead_pad
                    rel_e = float(w.end) - lead_pad
                    if rel_e <= 0.0 or rel_s >= clip_duration:
                        continue
                    raw_clip_words.append(
                        WordTimestamp(
                            word=w_txt,
                            start=max(0.0, round(rel_s, 3)),
                            end=min(clip_duration, max(max(0.0, rel_s) + 0.08, round(rel_e, 3))),
                            probability=round(float(getattr(w, "probability", 1.0)), 3),
                        )
                    )

        refined = clean_and_polish_word_timestamps(raw_clip_words, clip_duration=clip_duration)
        min_acceptable = max(2, int(len(cleaned_fallback) * 0.60)) if cleaned_fallback else 1
        if len(refined) >= min_acceptable:
            logger.info(
                "Subtítulos refinados por clip [%.1fs-%.1fs]: %d palabras pulidas.",
                start_time,
                end_time,
                len(refined),
            )
            return refined
    except Exception as exc:
        logger.debug("Refinamiento por clip omitido (%s). Usando transcripción base pulida.", exc)

    return cleaned_fallback


async def _analyze_multiple_with_antigravity_agent(
    segments: list[dict],
    max_shorts: int = 1,
) -> List[ViralSegmentCandidate]:
    """Uses the Google Antigravity SDK Agent to extract up to `max_shorts` non-overlapping viral clips."""
    formatted_transcript = "\n".join(
        f"[{s['start']:.2f}s - {s['end']:.2f}s] {s['text']}" for s in segments
    )
    prompt = (
        "Aquí tienes la transcripción con marcas de tiempo en segundos:\n\n"
        f"{formatted_transcript}\n\n"
        f"Selecciona hasta {max_shorts} fragmentos virales (que NO se solapen en tiempo) "
        "de entre 35 y 58 segundos cada uno que cumplan con la estructura "
        "(1. Gancho/chiste fuerte, 2. Misterio/pregunta, 3. Desarrollo/hechos, 4. Conclusión/remate) "
        "y devuelve el JSON validado con la lista `clips`."
    )

    config = LocalAgentConfig(
        system_instructions=SYSTEM_PROMPT,
        response_schema=ViralSegmentBatch,
        capabilities=CapabilitiesConfig(),
    )

    chunks: list[str] = []
    async with Agent(config) as agent:
        response = await agent.chat(prompt)
        async for token in response:
            chunks.append(token)

    raw_output = "".join(chunks).strip()
    if "```" in raw_output:
        for part in raw_output.split("```"):
            part_clean = part.strip()
            if part_clean.startswith("json"):
                part_clean = part_clean[4:].strip()
            if part_clean.startswith("{") and part_clean.endswith("}"):
                raw_output = part_clean
                break

    batch = ViralSegmentBatch.model_validate_json(raw_output)
    return batch.clips[:max_shorts]


def _infer_mood_from_text(text: str) -> MoodLiteral:
    lower = text.lower()
    if any(w in lower for w in ("secreto", "misterio", "oculto", "nadie sabe", "miedo", "oscuro")):
        return "misterio"
    if any(w in lower for w in ("jaja", "risa", "chiste", "loco", "broma", "gracioso", "diablo")):
        return "comedia"
    if any(w in lower for w in ("vida", "consejo", "aprender", "paz", "familia", "corazón")):
        return "reflexion"
    if any(w in lower for w in ("calle", "dembow", "tigueraje", "coro", "vaina", "klk")):
        return "urbano"
    return "impacto"


def _heuristic_viral_fallback_multiple(
    segments: list[dict],
    max_shorts: int = 1,
    min_dur: float = 35.0,
    max_dur: float = 58.0,
    video_stem_hint: str = "",
) -> List[ViralSegmentCandidate]:
    """
    Deterministic narrative scorer fallback that extracts up to `max_shorts`
    non-overlapping viral windows of [35s, 58s] ranked by viral score.
    """
    if not segments:
        raise ValueError("La transcripción está vacía; no se puede extraer ningún Short.")

    scored_windows: List[Tuple[float, float, float, str, str]] = []
    for i, start_seg in enumerate(segments):
        s_time = start_seg["start"]
        for j in range(i, len(segments)):
            e_time = segments[j]["end"]
            dur = e_time - s_time
            if min_dur <= dur <= max_dur:
                window_segs = segments[i : j + 1]
                # Skip windows that bridge across two distant sampling zones
                if any(
                    window_segs[k + 1]["start"] - window_segs[k]["end"] > 15.0
                    for k in range(len(window_segs) - 1)
                ):
                    continue
                window_text = " ".join(seg["text"] for seg in window_segs)
                word_count = len(window_text.split())
                # Require active commentary (at least ~45 words in 35-58s so we never pick silent gameplay)
                if word_count < 42:
                    continue
                score = 0.0
                first_txt = start_seg["text"].lower()
                if any(
                    k in first_txt
                    for k in (
                        "¿", "!", "mira", "sabías", "increíble", "secreto", "oye",
                        "imagínate", "dlss", "obs", "ps5", "switch", "latencia", "fps", "juego",
                    )
                ):
                    score += 3.5
                if "?" in window_text or "¿" in window_text or "por qué" in window_text.lower():
                    score += 2.5
                # High weight on continuous energetic commentary
                score += (word_count / max(1.0, dur)) * 3.0
                score += max(0.0, 2.0 - abs(dur - 46.0) * 0.1)
                scored_windows.append((score, s_time, e_time, start_seg["text"], window_text))

    scored_windows.sort(key=lambda item: item[0], reverse=True)

    selected: List[ViralSegmentCandidate] = []
    used_intervals: List[Tuple[float, float]] = []

    for score, s_time, e_time, first_seg_text, window_text in scored_windows:
        if len(selected) >= max_shorts:
            break
        overlaps = any(not (e_time <= us - 5.0 or s_time >= ue + 5.0) for us, ue in used_intervals)
        if overlaps:
            continue

        used_intervals.append((s_time, e_time))

        # Extraer dinámicamente la frase gancho real del texto del video
        sentences = [s.strip() for s in re.split(r"[.!?¡¿\n]+", window_text) if 14 <= len(s.strip()) <= 60]
        if sentences:
            best_phrase = sentences[0]
        else:
            words = window_text.split()
            best_phrase = " ".join(words[:6]) if len(words) >= 4 else "MOMENTO ÉPICO"

        clean_hook = re.sub(r"[^\w\s¿¡!?áéíóúÁÉÍÓÚñÑ]", "", best_phrase).strip()
        hook_title = f"🔥 \"{clean_hook.upper()}\" 😱 #Shorts"
        if len(hook_title) > 95:
            hook_title = f"🔥 {clean_hook[:75].upper()}... 😱 #Shorts"

        # Extraer palabras clave reales del fragmento para tags dinámicos
        stop_words = {"para", "como", "pero", "este", "esta", "estos", "estoy", "todo", "todos", "bien", "aqui", "aquí", "porque", "entonces", "cuando", "donde", "dónde", "mira", "vamos"}
        raw_words = re.findall(r"\b[a-zA-ZáéíóúÁÉÍÓÚñÑ]{5,15}\b", window_text.lower())
        top_topic_words = [w.capitalize() for w in raw_words if w not in stop_words][:3]
        if not top_topic_words:
            top_topic_words = ["Viral", "Trending", "Gaming"]

        tags_list = ["CreadorStudio", "Shorts"] + top_topic_words
        top_3_hashtags = " ".join(f"#{t}" for t in top_topic_words)
        brief_desc = f"😱 {window_text[:140].strip()}... 🔥"

        caption = (
            f"{brief_desc}\n\n"
            f""
            f"{top_3_hashtags} #Viral #Shorts"
        )
        selected.append(
            ViralSegmentCandidate(
                start_time=round(s_time, 2),
                end_time=round(e_time, 2),
                hook_title=hook_title[:95],
                first_person_caption=caption,
                tags=tags_list,
                bgm_mood=_infer_mood_from_text(window_text),
            )
        )

    # If some zones were shorter than 35s, pad from distinct segments so we still fulfill requested count
    if len(selected) < max_shorts and segments:
        for seg in segments:
            if len(selected) >= max_shorts:
                break
            s_time = seg["start"]
            e_time = round(s_time + 42.0, 2)
            overlaps = any(not (e_time <= us - 5.0 or s_time >= ue + 5.0) for us, ue in used_intervals)
            if overlaps:
                continue
            used_intervals.append((s_time, e_time))
            idx_num = len(selected)
            raw_seg_text = str(seg.get("text", "")).strip() or f"Momento destacado #{idx_num + 1}"
            clean_seg_hook = re.sub(r"[^\w\s¿¡!?áéíóúÁÉÍÓÚñÑ]", "", raw_seg_text).strip()
            base_hook = f"🔥 \"{clean_seg_hook[:65].upper()}\" 😱 #Shorts"
            selected.append(
                ViralSegmentCandidate(
                    start_time=round(s_time, 2),
                    end_time=e_time,
                    hook_title=base_hook[:90],
                    first_person_caption=(
                        f"😱 {raw_seg_text[:135]}... 👇🔥\n\n"
                        ""
                        "#Viral #Shorts"
                    ),
                    tags=["Shorts", "CreadorStudio", "Viral", "Gaming", "Stream"],
                    bgm_mood=_infer_mood_from_text(raw_seg_text),
                )
            )

    return selected


def snap_clip_boundaries_to_context(
    words: List[WordTimestamp],
    proposed_start: float,
    proposed_end: float,
    min_duration: float = 20.0,
    max_duration: float = 180.0,
) -> Tuple[float, float]:
    """
    Ajusta los bordes de un clip a fronteras naturales de oración o pausas >= 0.55s
    para que nunca empiece ni termine a mitad de una frase.
    """
    if not words:
        s_f = max(0.0, float(proposed_start))
        e_f = max(s_f + min_duration, float(proposed_end))
        return round(s_f, 2), round(e_f, 2)

    start_anchors: List[float] = [words[0].start]
    end_anchors: List[float] = []
    n = len(words)
    for i, w in enumerate(words):
        txt = w.word.strip()
        is_terminal = txt.endswith((".", "?", "!"))
        if i + 1 < n:
            gap = words[i + 1].start - w.end
            if is_terminal or gap >= 0.55:
                end_anchors.append(w.end)
                start_anchors.append(words[i + 1].start)
        else:
            end_anchors.append(w.end)

    if not end_anchors:
        end_anchors.append(words[-1].end)

    # Elegir anchor de inicio más cercano dentro de [-8.0s, +6.0s] respecto a proposed_start
    best_start = proposed_start
    best_start_dist = 1e9
    for anc in start_anchors:
        delta = anc - proposed_start
        if -8.5 <= delta <= 6.0:
            # Pequeña preferencia por expandir ligeramente hacia atrás si está cerca (evitar cortar gancho)
            penalty = abs(delta) + (0.4 if delta > 0 else 0.0)
            if penalty < best_start_dist:
                best_start_dist = penalty
                best_start = anc

    if best_start_dist >= 1e8:
        best_start = min(start_anchors, key=lambda a: abs(a - proposed_start))

    # Elegir anchor de fin válido que cumpla [min_duration, max_duration]
    valid_ends = [
        e for e in end_anchors if (e - best_start) >= min_duration and (e - best_start) <= max_duration
    ]
    if valid_ends:
        best_end = min(valid_ends, key=lambda e: abs(e - proposed_end))
    else:
        # Si ningún anchor cumple exactamente el rango tras ajustar start, buscar combinación válida
        best_pair: Optional[Tuple[float, float]] = None
        best_err = 1e9
        for anc_s in start_anchors:
            if abs(anc_s - proposed_start) > 15.0:
                continue
            for anc_e in end_anchors:
                dur = anc_e - anc_s
                if min_duration <= dur <= max_duration:
                    err = abs(anc_s - proposed_start) + abs(anc_e - proposed_end)
                    if err < best_err:
                        best_err = err
                        best_pair = (anc_s, anc_e)
        if best_pair is not None:
            best_start, best_end = best_pair
        else:
            best_end = max(best_start + min_duration, min(best_start + max_duration, proposed_end))

    s_out = round(max(0.0, best_start), 2)
    e_out = round(min(s_out + max_duration, max(s_out + min_duration, best_end)), 2)
    return s_out, e_out


def extract_contextual_narrative_arcs(
    word_timestamps: List[WordTimestamp],
    target_count: int = 12,
    energy_profile: Optional[List[Tuple[float, float]]] = None,
    min_dur: float = 20.0,
    max_dur: float = 180.0,
) -> List[ViralSegmentCandidate]:
    """
    Construye arcos narrativos completos agrupando oraciones enteras y pausas naturales
    sin cortar ideas a la mitad, priorizando ganchos, energía acústica y cierre narrativo.
    """
    if not word_timestamps:
        return []

    target_count = max(1, min(24, int(target_count)))

    # 1. Agrupar palabras en oraciones / turnos coherentes
    utterances: List[dict[str, Any]] = []
    cur_words: List[WordTimestamp] = []
    n = len(word_timestamps)
    for i, w in enumerate(word_timestamps):
        cur_words.append(w)
        txt = w.word.strip()
        is_end_punct = txt.endswith((".", "?", "!"))
        next_gap = (word_timestamps[i + 1].start - w.end) if (i + 1 < n) else 999.0
        cur_span = cur_words[-1].end - cur_words[0].start
        if is_end_punct or next_gap >= 0.70 or cur_span >= 22.0 or i == n - 1:
            utt_text = " ".join(cw.word.strip() for cw in cur_words).strip()
            if utt_text:
                utterances.append(
                    {
                        "start": float(cur_words[0].start),
                        "end": float(cur_words[-1].end),
                        "text": utt_text,
                        "word_count": len(cur_words),
                    }
                )
            cur_words = []

    if not utterances:
        return []

    hook_triggers = re.compile(
        r"\b(escucha|mira|secreto|nunca|nadie|por qué|como|increíble|brutal|loco|problema|verdad|error|cuidado|atención|hermano|locura|pasó|historia|épica)\b|[¿?!¡]",
        re.IGNORECASE,
    )
    closure_triggers = re.compile(
        r"\b(al final|por eso|en conclusión|ganamos|victoria|así fue|moraleja|literal|increíble)\b|[.!]$",
        re.IGNORECASE,
    )

    energy_map = energy_profile or []
    scored_windows: List[Tuple[float, float, float, str]] = []

    for i in range(len(utterances)):
        s_t = utterances[i]["start"]
        acc_texts: List[str] = []
        acc_words = 0
        for j in range(i, len(utterances)):
            if j > i and (utterances[j]["start"] - utterances[j - 1]["end"]) > 12.0:
                break
            acc_texts.append(utterances[j]["text"])
            acc_words += int(utterances[j]["word_count"])
            e_t = utterances[j]["end"]
            dur = e_t - s_t
            if dur > max_dur:
                break
            if dur < min_dur:
                continue

            full_text = " ".join(acc_texts)
            wps = acc_words / max(1.0, dur)
            hook_hits = len(hook_triggers.findall(utterances[i]["text"])) + 0.5 * len(hook_triggers.findall(full_text))
            closure_bonus = 2.0 if closure_triggers.search(utterances[j]["text"]) else 0.0
            ac_score = compute_segment_acoustic_score(energy_map, s_t, e_t) if energy_map else 6.0
            # Ventana dulce entre 28s y 85s recibe ligera bonificación de retención
            dur_bonus = 1.5 if 28.0 <= dur <= 85.0 else (0.7 if dur <= 125.0 else 0.0)
            score = (hook_hits * 2.4) + (min(wps, 3.8) * 1.8) + (ac_score * 0.9) + closure_bonus + dur_bonus
            scored_windows.append((score, round(s_t, 2), round(e_t, 2), full_text))

            # Evitar explorar demasiadas combinaciones largas si ya pasamos 110s
            if dur >= 110.0 and len(acc_texts) >= 4:
                break

    if not scored_windows:
        # Fallback elástico si el audio completo dura poco (>= 20s)
        total_s = utterances[0]["start"]
        total_e = utterances[-1]["end"]
        if (total_e - total_s) >= min_dur:
            scored_windows.append((5.0, round(total_s, 2), round(min(total_e, total_s + max_dur), 2), " ".join(u["text"] for u in utterances)))

    scored_windows.sort(key=lambda item: item[0], reverse=True)

    selected: List[ViralSegmentCandidate] = []
    used_ranges: List[Tuple[float, float]] = []

    for sc, s_t, e_t, text in scored_windows:
        if len(selected) >= target_count:
            break
        overlaps = any(not (e_t <= us - 3.0 or s_t >= ue + 3.0) for us, ue in used_ranges)
        if overlaps:
            continue
        snapped_s, snapped_e = snap_clip_boundaries_to_context(
            word_timestamps,
            s_t,
            e_t,
            min_duration=min_dur,
            max_duration=max_dur,
        )
        if any(not (snapped_e <= us - 2.0 or snapped_s >= ue + 2.0) for us, ue in used_ranges):
            continue
        used_ranges.append((snapped_s, snapped_e))

        first_sentence = re.split(r"[.!?]+", text.strip())[0].strip() or text[:65]
        clean_hook = re.sub(r"[^\w\s¿¡!?áéíóúÁÉÍÓÚñÑ]", "", first_sentence).strip()
        hook_title = f"🔥 \"{clean_hook[:68].upper()}\" 😱 #Shorts"
        words_clean = [re.sub(r"[^\wáéíóúñ]", "", w.lower()) for w in text.split()]
        top_tags = [w for w in dict.fromkeys(words_clean) if len(w) > 4][:4]
        tags_list = list(dict.fromkeys(["Shorts", "CreadorStudio", "Viral", *[t.capitalize() for t in top_tags]]))[:6]
        top_hashtags = " ".join(f"#{t}" for t in tags_list[:3])

        selected.append(
            ViralSegmentCandidate(
                start_time=snapped_s,
                end_time=snapped_e,
                hook_title=hook_title[:95],
                first_person_caption=(
                    f"😱 {text[:150].strip()}... 🔥\n\n"
                    f""
                    f"{top_hashtags} #Viral #Shorts"
                ),
                tags=tags_list,
                bgm_mood=_infer_mood_from_text(text),
                hook_strength=round(min(10.0, max(6.5, sc / 2.2)), 1),
                standalone_value=8.6,
                virality_potential=round(min(10.0, max(6.8, sc / 2.1)), 1),
            )
        )

    selected.sort(key=lambda c: c.start_time)
    return selected


def _analyze_with_local_ollama(
    segments: list[dict],
    max_shorts: int,
) -> List[ViralSegmentCandidate]:
    """
    Intenta descubrir capítulos y momentos con contexto completo usando Ollama local
    (qwen2.5:7b -> llama3.1:8b) sin ventanas ni costos de API. Falla rápido si no está activo.
    """
    import urllib.request
    import urllib.error

    if not segments:
        return []

    # Dividir transcripción en capítulos de ~12 minutos para nunca saturar contexto local
    total_end = float(segments[-1]["end"])
    chapter_len = 720.0
    overlap = 60.0
    chapters: List[list[dict]] = []
    cursor = float(segments[0]["start"])
    while cursor < total_end or not chapters:
        ch_end = cursor + chapter_len
        ch_segs = [s for s in segments if s["end"] >= cursor and s["start"] <= ch_end]
        if ch_segs:
            chapters.append(ch_segs)
        if ch_end >= total_end:
            break
        cursor = ch_end - overlap

    per_chapter_goal = max(2, min(6, math.ceil(max_shorts / max(1, len(chapters))) + 1))
    all_candidates: List[ViralSegmentCandidate] = []

    models_to_try = ("qwen2.5:7b", "llama3.1:8b", "qwen2.5:3b")
    active_model: Optional[str] = None
    try:
        req_tags = urllib.request.Request("http://127.0.0.1:11434/api/tags", method="GET")
        with urllib.request.urlopen(req_tags, timeout=1.5) as resp:
            tags_data = json.loads(resp.read().decode("utf-8"))
            installed = {m.get("name", "") for m in tags_data.get("models", [])}
            for cand_m in models_to_try:
                if cand_m in installed:
                    active_model = cand_m
                    break
            if not active_model and installed:
                active_model = sorted(installed)[0]
    except Exception:
        return []

    if not active_model:
        return []

    for ch_segs in chapters:
        if len(all_candidates) >= max_shorts + 4:
            break
        compact_lines = [
            f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in ch_segs[:140]
        ]
        prompt = (
            "Eres un editor experto de clips virales (tipo NexusClips). Analiza este capítulo y devuelve EXCLUSIVAMENTE un JSON válido "
            "con la clave `clips`: lista de objetos con `start_time` (float segundos exactos), `end_time` (float segundos exactos, duración entre 22 y 120s), "
            "`hook_title` (string corto viral en español), `first_person_caption` (string con emojis), `tags` (lista de 4 strings), "
            "`bgm_mood` (uno de: misterio, comedia, impacto, reflexion, urbano). "
            f"Regla crítica: NO cortes ninguna oración a la mitad ni cortes una explicación sin su remate. Extrae hasta {per_chapter_goal} clips.\n\n"
            + "\n".join(compact_lines)
        )
        payload = json.dumps(
            {
                "model": active_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "format": "json",
            }
        ).encode("utf-8")
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=28.0) as resp:
                raw_resp = json.loads(resp.read().decode("utf-8"))
            content = str(raw_resp.get("message", {}).get("content", "")).strip()
            parsed = json.loads(content)
            raw_clips = (
                parsed.get("clips", [])
                if isinstance(parsed, dict)
                else (parsed if isinstance(parsed, list) else [])
            )
            for item in raw_clips:
                try:
                    cand = ViralSegmentCandidate.model_validate(item)
                    if not any(
                        not (cand.end_time <= u.start_time - 2.0 or cand.start_time >= u.end_time + 2.0)
                        for u in all_candidates
                    ):
                        all_candidates.append(cand)
                except Exception:
                    continue
        except Exception:
            continue

    return all_candidates[:max_shorts]


def compute_jumpcut_intervals_and_remap_words(
    clip_words: List[WordTimestamp],
    clip_duration: float,
    max_silence_gap: float = 0.95,
    padding_sec: float = 0.12,
    enable_jumpcuts: bool = True,
) -> Tuple[List[Tuple[float, float]], List[WordTimestamp]]:
    """
    OpenCut-inspired Jump-Cut Silence Trimmer:
    Detects dead silences longer than `max_silence_gap` seconds inside the clip,
    builds the list of sub-intervals `[start, end]` to keep, and remaps `word_timestamps`.
    """
    if not clip_words or not enable_jumpcuts:
        return [(0.0, round(clip_duration, 3))], clip_words

    intervals: List[List[float]] = []
    for w in clip_words:
        w_s = max(0.0, w.start - padding_sec)
        w_e = min(clip_duration, w.end + padding_sec)
        if not intervals:
            intervals.append([w_s, w_e])
        else:
            prev_s, prev_e = intervals[-1]
            if (w_s - prev_e) <= max_silence_gap:
                intervals[-1][1] = max(prev_e, w_e)
            else:
                intervals.append([w_s, w_e])

    if intervals[0][0] < 0.8:
        intervals[0][0] = 0.0
    if (clip_duration - intervals[-1][1]) < 0.8:
        intervals[-1][1] = round(clip_duration, 3)

    total_kept = sum(e - s for s, e in intervals)
    if total_kept < min(20.0, clip_duration * 0.65) or len(intervals) == 1:
        return [(0.0, round(clip_duration, 3))], clip_words

    remapped_words: List[WordTimestamp] = []
    accumulated_offset = 0.0
    keep_tuples: List[Tuple[float, float]] = []

    for seg_s, seg_e in intervals:
        seg_s_r = round(seg_s, 3)
        seg_e_r = round(seg_e, 3)
        keep_tuples.append((seg_s_r, seg_e_r))
        for w in clip_words:
            if w.start >= seg_s - 0.05 and w.end <= seg_e + 0.05:
                new_start = max(0.0, round((w.start - seg_s) + accumulated_offset, 3))
                new_end = max(new_start + 0.05, round((w.end - seg_s) + accumulated_offset, 3))
                remapped_words.append(
                    WordTimestamp(
                        word=w.word,
                        start=new_start,
                        end=new_end,
                        probability=w.probability,
                    )
                )
        accumulated_offset += seg_e_r - seg_s_r

    logger.info(
        "Jump-Cuts calculados: %d intervalos activos (ahorro de %.2fs de silencio muerto)",
        len(keep_tuples),
        clip_duration - accumulated_offset,
    )
    return keep_tuples, remapped_words


def _build_clip_analysis(
    candidate: ViralSegmentCandidate,
    segments: list[dict],
    all_words: list[WordTimestamp],
    enable_jumpcuts: bool = True,
) -> ViralClipAnalysis:
    clip_words: list[WordTimestamp] = []
    for w in all_words:
        if w.end >= candidate.start_time and w.start <= candidate.end_time:
            rel_start = max(0.0, round(w.start - candidate.start_time, 3))
            rel_end = max(rel_start + 0.05, round(w.end - candidate.start_time, 3))
            clip_words.append(
                WordTimestamp(
                    word=w.word,
                    start=rel_start,
                    end=rel_end,
                    probability=w.probability,
                )
            )

    clip_duration = round(candidate.end_time - candidate.start_time, 3)
    keep_intervals, remapped_words = compute_jumpcut_intervals_and_remap_words(
        clip_words=clip_words,
        clip_duration=clip_duration,
        enable_jumpcuts=enable_jumpcuts,
    )

    excerpt = " ".join(
        s["text"]
        for s in segments
        if s["end"] >= candidate.start_time and s["start"] <= candidate.end_time
    )

    return ViralClipAnalysis(
        start_time=candidate.start_time,
        end_time=candidate.end_time,
        hook_title=candidate.hook_title,
        first_person_caption=candidate.first_person_caption,
        tags=candidate.tags,
        bgm_mood=candidate.bgm_mood,
        hook_strength=candidate.hook_strength,
        standalone_value=candidate.standalone_value,
        virality_potential=candidate.virality_potential,
        acoustic_energy_score=candidate.acoustic_energy_score,
        word_timestamps=remapped_words,
        keep_intervals=keep_intervals,
        transcript_excerpt=excerpt,
    )


def transcribe_and_analyze_multiple(
    video_path: str | Path,
    max_shorts: int = 1,
    enable_jumpcuts: bool = True,
    output_json_path: Optional[str | Path] = None,
    progress_callback: Optional[Callable[[int, str, str], None]] = None,
) -> List[ViralClipAnalysis]:
    """
    Transcribes the full stream once and returns up to `max_shorts` contextual
    ViralClipAnalysis objects discovered via 3-tier pipeline:
      1) Gemini API (if GEMINI_API_KEY / GOOGLE_API_KEY is configured)
      2) Local Ollama LLM (qwen2.5:7b / llama3.1:8b) chapter discovery
      3) Contextual Narrative Arc Extractor + boundary snapping (never cuts mid-sentence)
    """
    max_shorts = max(1, min(24, int(max_shorts)))
    energy_profile = analyze_audio_energy_profile(video_path, window_sec=1.0)
    segments, all_words = transcribe_video(
        video_path=video_path,
        model_size="large-v3",
        device="cuda",
        compute_type="float16",
        max_shorts_hint=max_shorts,
        progress_callback=progress_callback,
    )

    candidates: List[ViralSegmentCandidate] = []
    has_gemini_key = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))

    if has_gemini_key:
        try:
            logger.info(
                "Tier 1: Analizando transcripción con Gemini Antigravity Agent (buscando %d Shorts)...",
                max_shorts,
            )
            candidates = asyncio.run(
                _analyze_multiple_with_antigravity_agent(segments, max_shorts=max_shorts)
            )
        except Exception as exc:
            logger.warning("Tier 1 Gemini falló (%s). Probando Tier 2 Ollama local...", exc)

    if len(candidates) < max_shorts:
        try:
            ollama_cands = _analyze_with_local_ollama(segments, max_shorts=max_shorts)
            used = [(c.start_time, c.end_time) for c in candidates]
            for oc in ollama_cands:
                if len(candidates) >= max_shorts:
                    break
                if not any(not (oc.end_time <= u0 - 2.0 or oc.start_time >= u1 + 2.0) for u0, u1 in used):
                    candidates.append(oc)
                    used.append((oc.start_time, oc.end_time))
        except Exception as exc:
            logger.warning("Tier 2 Ollama local falló (%s). Continuando con Tier 3 narrativo...", exc)

    if len(candidates) < max_shorts and all_words:
        try:
            logger.info(
                "Tier 3: Extrayendo arcos narrativos contextuales para completar hasta %d clips...",
                max_shorts,
            )
            narrative_cands = extract_contextual_narrative_arcs(
                word_timestamps=all_words,
                target_count=max_shorts,
                energy_profile=energy_profile,
            )
            used = [(c.start_time, c.end_time) for c in candidates]
            for nc in narrative_cands:
                if len(candidates) >= max_shorts:
                    break
                if not any(not (nc.end_time <= u0 - 2.0 or nc.start_time >= u1 + 2.0) for u0, u1 in used):
                    candidates.append(nc)
                    used.append((nc.start_time, nc.end_time))
        except Exception as exc:
            logger.warning("Tier 3 arcos narrativos falló (%s). Continuando con heurística...", exc)

    if len(candidates) < max_shorts and segments:
        extra = _heuristic_viral_fallback_multiple(segments, max_shorts=max_shorts, min_dur=20.0, max_dur=150.0)
        used = [(c.start_time, c.end_time) for c in candidates]
        for ex in extra:
            if len(candidates) >= max_shorts:
                break
            if not any(not (ex.end_time <= u0 - 2.0 or ex.start_time >= u1 + 2.0) for u0, u1 in used):
                candidates.append(ex)
                used.append((ex.start_time, ex.end_time))

    # Asegurar que TODOS los clips queden alineados a pausas / finales de oración completos
    if all_words:
        for c in candidates:
            s_snap, e_snap = snap_clip_boundaries_to_context(
                all_words,
                c.start_time,
                c.end_time,
                min_duration=20.0,
                max_duration=180.0,
            )
            c.start_time = s_snap
            c.end_time = e_snap

    for c in candidates:
        c.acoustic_energy_score = compute_segment_acoustic_score(
            energy_profile, c.start_time, c.end_time
        )

    results = [
        _build_clip_analysis(c, segments, all_words, enable_jumpcuts=enable_jumpcuts)
        for c in candidates[:max_shorts]
    ]
    try:
        cache_key = str(Path(video_path).resolve())
        LAST_FULL_WORDS_BY_VIDEO[cache_key] = [
            {
                "word": w.word,
                "start": float(w.start),
                "end": float(w.end),
                "probability": float(w.probability),
            }
            for w in all_words
        ]
    except Exception:
        pass

    if output_json_path:
        out_path = Path(output_json_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [r.model_dump() for r in results] if len(results) > 1 else results[0].model_dump()
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Resultado de análisis (%d Shorts) guardado en: %s", len(results), out_path)

    return results


def transcribe_and_analyze(
    video_path: str | Path,
    output_json_path: Optional[str | Path] = None,
) -> ViralClipAnalysis:
    """Single-clip entrypoint for backwards compatibility."""
    return transcribe_and_analyze_multiple(
        video_path=video_path,
        max_shorts=1,
        output_json_path=output_json_path,
    )[0]


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Skill 1: Video Transcriber & Viral Analyzer")
    parser.add_argument("--video", required=True, help="Ruta al archivo de video de entrada")
    parser.add_argument("--max-shorts", type=int, default=1, help="Cantidad de Shorts a extraer del video")
    parser.add_argument("--output", required=False, help="Ruta opcional para guardar el JSON")
    args = parser.parse_args()

    analyses = transcribe_and_analyze_multiple(
        args.video, max_shorts=args.max_shorts, output_json_path=args.output
    )
    print(json.dumps([a.model_dump() for a in analyses], indent=2, ensure_ascii=False))
