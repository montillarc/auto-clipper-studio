"""
Pilar 3: disk_cleanup.py — Mantenimiento Autónomo de Disco e Infraestructura
para Auto-Clipper Shorts Engine.

Funciones:
1. `clean_processing_dir()`: Elimina fragmentos DASH temporales (.ts, .m4a),
   archivos de subtítulos .ass usados y clips intermedios en ./processing/.
2. `clean_ig_staging_cache()`: Elimina videos en caché de ig_ready_8m mayores a 24 horas.
3. `get_disk_space_report()`: Devuelve GB libres, usados y porcentaje de salud del disco.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple


def _win_long_path(path: Path) -> Path:
    """Devuelve Path con prefijo \\\\?\\ en Windows cuando la ruta se acerca o supera MAX_PATH."""
    if sys.platform != "win32":
        return path
    abs_str = os.path.abspath(str(path))
    if abs_str.startswith("\\\\?\\") or len(abs_str) < 240:
        return path
    if abs_str.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + abs_str.lstrip("\\"))
    return Path("\\\\?\\" + abs_str)

logger = logging.getLogger("disk-cleanup")

BASE_DIR = Path(__file__).resolve().parents[3]
PROCESSING_DIR = BASE_DIR / "processing"
OUTPUT_DIR = BASE_DIR / "output_shorts"
PUBLISHED_ARCHIVE_DIR = BASE_DIR / "published_archive"


def get_disk_space_report(path: Path = BASE_DIR) -> Dict[str, float]:
    """Obtiene el estado de almacenamiento del disco donde reside el proyecto."""
    total, used, free = shutil.disk_usage(str(path))
    gb = 1024 ** 3
    return {
        "total_gb": round(total / gb, 2),
        "used_gb": round(used / gb, 2),
        "free_gb": round(free / gb, 2),
        "free_percentage": round((free / total) * 100, 1),
    }


def clean_processing_dir(max_age_seconds: int = 0) -> Tuple[int, float]:
    """
    Elimina archivos temporales e innecesarios de ./processing/ y ./published_archive/
    (subtítulos .ass, análisis JSON, cachés de transcripción, audios .m4a/.wav,
    clips de corte intermedios, fragmentos de stream y videos fuente ya procesados).
    """
    now = time.time()
    deleted_count = 0
    bytes_freed = 0

    patterns = [
        "*.ass",
        "*.m4a",
        "*.wav",
        "*.part",
        "*.ytdl",
        "*.jpg",
        "*.png",
        "*_analysis.json",
        "*_captions.json",
        "*_info.json",
        "*_batch_summary.json",
        "*_transcript_minutes.txt",
        ".transcript_cache_*.json",
        ".yt_hd_url_cache.json",
        "*_raw_clip_*.mp4",
        "*_aud_*.m4a",
        ".*hd1080p60_slice*",
        "*_slice*.mp4",
        "*_1080p60.mp4",
        "*_1080p.mp4",
        "*_720p*.mp4",
        "live_*",
        "temp_*",
        "*.ts",
        "*.mp4",
        "*.mov",
        "*.mkv",
        "*.webm",
    ]

    if PROCESSING_DIR.exists():
        for pat in patterns:
            for f in PROCESSING_DIR.glob(pat):
                try:
                    lp = _win_long_path(f)
                    if not lp.is_file():
                        continue
                    st = lp.stat()
                    file_age = now - st.st_mtime
                    if max_age_seconds <= 0 or file_age >= max_age_seconds:
                        lp.unlink(missing_ok=True)
                        deleted_count += 1
                        bytes_freed += st.st_size
                except OSError as exc:
                    logger.warning("No se pudo eliminar %s: %s", f.name, exc)

        # Limpiar subcarpetas temporales de slices
        for sub in PROCESSING_DIR.glob("slices_*"):
            try:
                lp_sub = _win_long_path(sub)
                if lp_sub.is_dir():
                    shutil.rmtree(lp_sub, ignore_errors=True)
                    deleted_count += 1
            except OSError as exc:
                logger.warning("No se pudo eliminar subdirectorio %s: %s", sub.name, exc)

    if PUBLISHED_ARCHIVE_DIR.exists():
        for pat in ("*.mp4", "*.mov", "*.mkv", "*.webm", "*.ass", "*.json", "*.part"):
            for f in PUBLISHED_ARCHIVE_DIR.glob(pat):
                try:
                    lp = _win_long_path(f)
                    if not lp.is_file():
                        continue
                    st = lp.stat()
                    file_age = now - st.st_mtime
                    if max_age_seconds <= 0 or file_age >= max_age_seconds:
                        lp.unlink(missing_ok=True)
                        deleted_count += 1
                        bytes_freed += st.st_size
                except OSError as exc:
                    logger.warning("No se pudo eliminar %s de published_archive: %s", f.name, exc)

    mb_freed = round(bytes_freed / (1024 * 1024), 2)
    logger.info("🧹 Limpieza de ./processing/ y ./published_archive/: %d archivos eliminados (%.2f MB liberados).", deleted_count, mb_freed)
    return deleted_count, mb_freed


def clean_ig_staging_cache(max_age_hours: int = 12) -> Tuple[int, float]:
    """Limpia las copias intermedias de ig_ready_8m más viejas de max_age_hours horas."""
    if not OUTPUT_DIR.exists():
        return 0, 0.0

    now = time.time()
    deleted_count = 0
    bytes_freed = 0
    max_age_seconds = max_age_hours * 3600

    for ig_folder in OUTPUT_DIR.glob("**/ig_ready_8m"):
        if not ig_folder.is_dir():
            continue
        for f in ig_folder.glob("*.mp4"):
            if max_age_seconds <= 0 or (now - f.stat().st_mtime >= max_age_seconds):
                try:
                    size = f.stat().st_size
                    f.unlink(missing_ok=True)
                    deleted_count += 1
                    bytes_freed += size
                except Exception as exc:
                    logger.warning("No se pudo eliminar %s: %s", f.name, exc)

    mb_freed = round(bytes_freed / (1024 * 1024), 2)
    logger.info("🧹 Limpieza de ig_ready_8m: %d archivos eliminados (%.2f MB liberados).", deleted_count, mb_freed)
    return deleted_count, mb_freed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Limpiador Autónomo de Disco CreadorStudio")
    parser.add_argument("--all", action="store_true", help="Limpiar temporales y caché de IG")
    args = parser.parse_args()

    report = get_disk_space_report()
    print(f"💾 Espacio en Disco: {report['free_gb']} GB libres ({report['free_percentage']}% disponible)")
    clean_processing_dir()
    if args.all:
        clean_ig_staging_cache(max_age_hours=0)
