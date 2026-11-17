"""
SKILL 5: Multi-Social Uploader & Distributor (distributor.py)
Prepara y enruta los Shorts 1080p60 generados en ./output_shorts/ en Modo Híbrido
(Categorización Automática por Nicho + Confirmación Previa del Usuario):
- TODOS los Shorts van siempre al canal principal de YouTube (CreadorStudio) sin importar la categoría.
- La cuenta principal @creadorstudio (en Instagram, Facebook y TikTok) queda EXCLUIDA de la automatización
  (reservada para repost manual del propietario, permaneciendo intacta dentro de Meta Business Suite).
- Las cuentas secundarias se asignan por categoría (gaming, ometv, general) y se confirman con el usuario.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("multi_social_uploader")

BASE_DIR = Path(__file__).resolve().parents[3]
CONFIG_DIR = BASE_DIR / "config"
SOCIAL_ACCOUNTS_PATH = CONFIG_DIR / "social_accounts.json"
SOCIAL_QUEUE_PATH = CONFIG_DIR / "social_distribution_queue.json"
AST_TZ = ZoneInfo("America/Santo_Domingo")


def load_social_accounts(config_path: Path = SOCIAL_ACCOUNTS_PATH) -> Dict[str, Any]:
    """Carga el inventario y reglas de enrutamiento de Meta Business Suite y TikTok Studio."""
    if not config_path.exists():
        raise FileNotFoundError(f"No se encontró el archivo de cuentas sociales: {config_path}")
    return json.loads(config_path.read_text(encoding="utf-8"))


def format_social_caption(
    title: str,
    description: str,
    tags: List[str],
    platform: str = "tiktok",
) -> str:
    """
    Formatea el texto optimizado para TikTok Studio o Instagram/Facebook Reels
    respetando la regla de metadatos de CreadorStudio (Título con emojis + descripción + 3 hashtags + #Viral).
    """
    clean_title = re.sub(r"#shorts\b", "", title, flags=re.IGNORECASE).strip()
    clean_desc = re.sub(r"#shorts\b", "", description, flags=re.IGNORECASE).strip()

    clean_tags: List[str] = []
    for t in tags:
        slug = re.sub(r"[^\wáéíóúñÁÉÍÓÚÑ]", "", t).strip()
        if slug and slug.lower() not in {"shorts", "creadorstudio"}:
            if slug.lower() not in [x.lower() for x in clean_tags]:
                clean_tags.append(slug)
        if len(clean_tags) >= 3:
            break

    while len(clean_tags) < 3:
        fallback = ["Viral", "Tendencia", "Stream"][len(clean_tags)]
        if fallback.lower() not in [x.lower() for x in clean_tags]:
            clean_tags.append(fallback)

    hashtag_line = " ".join(f"#{t}" for t in clean_tags[:3]) + " #Viral"
    if platform.lower() == "tiktok":
        hashtag_line += " #FYP"
    else:
        hashtag_line += " #Reels"

    lines = [clean_title]
    if clean_desc and clean_desc.lower() != clean_title.lower():
        lines.append("")
        lines.append(clean_desc)
    lines.append("")
    lines.append(hashtag_line)
    return "\n".join(lines).strip()


def classify_clip_category(
    title: str,
    description: str,
    tags: List[str],
    layout_mode: str = "auto",
) -> str:
    """
    Clasifica automáticamente un clip en una de las 3 categorías oficiales:
    - 'ometv': Clips de OmeTV, Omegle, charlas random con desconocidos.
    - 'gaming': Gameplays, juegos, PC/GPU, DLSS, OBS, RTX.
    - 'general': Reacciones, noticias, debates, humor, clips generales del stream.
    """
    combined_text = f"{title} {description} {' '.join(tags)}".lower()
    if any(k in combined_text for k in ("ometv", "omegle", "desconocido", "charla random")):
        return "ometv"
    if any(
        k in combined_text
        for k in ("dlss", "obs", "fps", "juego", "gaming", "gameplay", "nvidia", "rtx", "gamer", "jugando")
    ):
        return "gaming"
    return "general"


def select_target_accounts(
    title: str,
    description: str,
    tags: List[str],
    clip_index: int = 1,
    layout_mode: str = "auto",
    explicit_category: Optional[str] = None,
    accounts_cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Selecciona las cuentas sugeridas según la categoría del clip ('gaming', 'ometv' o 'general'):
    1. YouTube: SIEMPRE recibe el 100% de los Shorts ('CreadorStudio').
    2. @creadorstudio (IG/FB/TikTok): SIEMPRE excluida de la automatización (repost manual del usuario).
    3. Cuentas secundarias de TikTok e Instagram: filtradas por categoría.
    """
    cfg = accounts_cfg or load_social_accounts()
    category = (explicit_category or classify_clip_category(title, description, tags, layout_mode)).lower()

    tiktok_all: List[Dict[str, Any]] = [
        acc for acc in cfg.get("tiktok_studio_accounts", []) if acc.get("auto_publish", True)
    ]
    ig_all: List[Dict[str, Any]] = [
        acc
        for acc in cfg.get("meta_business_suite", {}).get("network_instagram_accounts", [])
        if acc.get("auto_publish", True) and acc.get("username", "").lower() != "creadorstudio"
    ]

    tiktok_matched = [acc for acc in tiktok_all if acc.get("category") == category] or tiktok_all
    ig_matched = [acc for acc in ig_all if acc.get("category") == category] or ig_all

    # Para 'general', asignamos la cuenta principal de la rotación y también listamos todas las elegibles de la categoría
    primary_tiktok = tiktok_matched[(clip_index - 1) % len(tiktok_matched)] if tiktok_matched else {}
    primary_ig = ig_matched[(clip_index - 1) % len(ig_matched)] if ig_matched else {}

    return {
        "category": category,
        "youtube_channel": "CreadorStudio (SIEMPRE ACTIVO - Todas las categorías)",
        "excluded_manual_only": ["@creadorstudio (IG/FB/TikTok - Solo repost manual del propietario)"],
        "tiktok_primary": primary_tiktok,
        "instagram_primary": primary_ig,
        "tiktok_category_accounts": [f"@{a['username']}" for a in tiktok_matched],
        "instagram_category_accounts": [f"@{a['username']}" for a in ig_matched],
    }


def enqueue_social_distribution(
    video_path: Path,
    title: str,
    description: str,
    tags: List[str],
    publish_at_utc: str,
    clip_index: int = 1,
    layout_mode: str = "auto",
    explicit_category: Optional[str] = None,
    queue_path: Path = SOCIAL_QUEUE_PATH,
) -> Dict[str, Any]:
    """
    Registra un Short renderizado en la cola multi-plataforma (./config/social_distribution_queue.json)
    con su horario local en República Dominicana (America/Santo_Domingo), categoría detectada,
    cuentas sugeridas (excluyendo @creadorstudio en IG/TikTok) y estado de confirmación.
    """
    utc_dt = datetime.fromisoformat(publish_at_utc.replace("Z", "+00:00"))
    ast_dt = utc_dt.astimezone(AST_TZ)
    ast_formatted = ast_dt.strftime("%Y-%m-%d %I:%M %p AST")

    routing = select_target_accounts(
        title=title,
        description=description,
        tags=tags,
        clip_index=clip_index,
        layout_mode=layout_mode,
        explicit_category=explicit_category,
    )

    entry: Dict[str, Any] = {
        "video_file": str(video_path.resolve()),
        "video_name": video_path.name,
        "clip_index": clip_index,
        "category": routing["category"],
        "publish_at_utc": publish_at_utc,
        "publish_at_ast": ast_formatted,
        "tiktok_caption": format_social_caption(title, description, tags, platform="tiktok"),
        "reels_caption": format_social_caption(title, description, tags, platform="reels"),
        "routing": routing,
        "status": {
            "youtube_main": "scheduled_always",
            "meta_business_suite": "pending_user_confirmation",
            "tiktok_studio": "pending_user_confirmation",
        },
    }

    existing_queue: List[Dict[str, Any]] = []
    if queue_path.exists():
        try:
            loaded = json.loads(queue_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                existing_queue = loaded
        except Exception:
            existing_queue = []

    existing_queue = [item for item in existing_queue if item.get("video_name") != video_path.name]
    existing_queue.append(entry)

    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(json.dumps(existing_queue, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info(
        "[SKILL 5/5] [%s] (%s) -> YT: CreadorStudio (Fijo) | TikTok Sugerido: %s | IG Sugerido: %s",
        routing["category"].upper(),
        ast_formatted,
        ", ".join(routing["tiktok_category_accounts"]),
        ", ".join(routing["instagram_category_accounts"]),
    )
    return entry
