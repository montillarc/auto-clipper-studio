"""
Inspector proactivo de ./inbox_videos/ (Modo Consultivo / Aprobación en Chat).
Vigila ./inbox_videos/, espera a que el video termine de copiarse, analiza su duración,
resolución y potencial de Shorts virales, guarda el reporte en ./config/pending_job.json
y despierta al agente en el chat para pedir confirmación al usuario antes de procesar.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any, Dict, Set

import cv2

BASE_DIR = Path(__file__).resolve().parent
INBOX_DIR = BASE_DIR / "inbox_videos"
CONFIG_DIR = BASE_DIR / "config"
PENDING_JOB_FILE = CONFIG_DIR / "pending_job.json"

VIDEO_EXTENSIONS: Set[str] = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


def wait_until_file_ready(
    file_path: Path,
    stability_seconds: float = 2.0,
    timeout_seconds: float = 600.0,
) -> bool:
    """Espera a que el archivo termine de copiarse en Windows sin bloqueo de escritura."""
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
    return False


def estimate_video_potential(video_path: Path) -> Dict[str, Any]:
    """
    Analiza la duración real, resolución, FPS y peso del video y estima cuántos
    Shorts virales (de 35 a 58 segundos) se recomiendan extraer sin perder calidad.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el video: {video_path}")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
    fps = float(cap.get(cv2.CAP_PROP_FPS)) or 30.0
    frame_count = float(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0.0
    cap.release()

    duration_sec = round(frame_count / fps, 2) if fps > 0 and frame_count > 0 else 0.0
    size_mb = round(video_path.stat().st_size / (1024 * 1024), 2)

    minutes = int(duration_sec // 60)
    seconds = int(round(duration_sec % 60))
    duration_formatted = f"{minutes}m {seconds:02d}s" if minutes > 0 else f"{seconds}s"

    # Estimación inteligente de Shorts virales:
    # - Un Short dura en promedio ~45s.
    # - En videos hablados/podcasts, suele haber 1 momento altamente viral cada ~3 a 3.5 minutos.
    # - El máximo teórico (sin repetir contenido y dejando respiro) es ~1 por cada 75 segundos.
    if duration_sec < 45:
        recommended = 1
        max_possible = 1
    elif duration_sec <= 180:  # Hasta 3 minutos
        recommended = 1
        max_possible = max(1, int(duration_sec // 50))
    else:
        recommended = max(2, int(round(duration_sec / 200.0)))  # ~1 Short top cada 3.3 min
        max_possible = max(recommended, int(math.floor(duration_sec / 75.0)))
        recommended = min(recommended, 16)
        max_possible = min(max_possible, 24)

    return {
        "file_name": video_path.name,
        "file_path": str(video_path.resolve()),
        "file_size_mb": size_mb,
        "duration_sec": duration_sec,
        "duration_formatted": duration_formatted,
        "resolution": f"{width}x{height}",
        "fps": round(fps, 2),
        "recommended_shorts": recommended,
        "max_possible_shorts": max_possible,
        "detected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "WAITING_USER_APPROVAL",
    }


def watch_until_next_video(poll_interval: float = 2.0) -> Dict[str, Any]:
    """
    Vigila ./inbox_videos/ de forma continua. En cuanto detecta un archivo de video
    nuevo terminado de copiar, calcula la estimación de Shorts, guarda el reporte
    en ./config/pending_job.json y termina para despertar al asistente en el chat.
    """
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        for item in sorted(INBOX_DIR.iterdir()):
            if item.is_file() and item.suffix.lower() in VIDEO_EXTENSIONS:
                if wait_until_file_ready(item):
                    report = estimate_video_potential(item)
                    PENDING_JOB_FILE.write_text(
                        json.dumps(report, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    return report
        time.sleep(poll_interval)


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Inspector consultivo de inbox_videos")
    parser.add_argument(
        "--file",
        default=None,
        help="Analiza un archivo específico inmediatamente en lugar de esperar",
    )
    args = parser.parse_args()

    if args.file:
        res = estimate_video_potential(Path(args.file))
    else:
        res = watch_until_next_video()

    print(json.dumps(res, indent=2, ensure_ascii=False))
