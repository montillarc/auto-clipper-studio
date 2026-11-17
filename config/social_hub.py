"""
Gestor centralizado del Hub de Cuentas Sociales, APIs y Enrutamiento Multi-Categoría.
Soporta las 3 categorías oficiales:
- principales (Cuentas Principales)
- gaming (Cuentas Gaming)
- clipping (Cuentas Clipping)
para YouTube, Instagram, TikTok y Facebook Reels sin bloqueo por puntaje.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import sqlite3
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests

logger = logging.getLogger("social_hub")

BUILTIN_CATEGORY_KEYS: Tuple[str, ...] = ("principales", "gaming", "clipping", "ometv")
ACCOUNT_CATEGORY_KEYS: Tuple[str, ...] = BUILTIN_CATEGORY_KEYS
SOCIAL_PLATFORMS: Tuple[str, ...] = ("youtube", "instagram", "tiktok", "facebook")

HUB_CONFIG_FILENAME = "social_hub_config.json"
_CUSTOM_CATEGORY_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")


def _strip_accents(text: str) -> str:
    norm = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in norm if not unicodedata.combining(ch)).lower()


def slugify_category_key(raw_text: str) -> str:
    """Convierte un nombre de categoría (ej. 'Cuentas Podcast') en identificador slug válido ('podcast')."""
    base = _strip_accents(raw_text).strip()
    if base.startswith("cuentas "):
        candidate_rest = base[len("cuentas ") :].strip()
        if len(re.sub(r"[^a-z0-9]+", "", candidate_rest)) >= 2:
            base = candidate_rest
    slug = re.sub(r"[^a-z0-9]+", "_", base).strip("_")[:32].strip("_")
    if len(re.sub(r"[^a-z0-9]", "", slug)) < 2:
        raise ValueError("El nombre de la categoría debe contener al menos 2 caracteres alfanuméricos.")
    return slug


def normalize_account_categories(
    raw_categories: Optional[Iterable[str]],
    fallback: Sequence[str] = ("clipping",),
    valid_keys: Optional[Sequence[str]] = None,
) -> List[str]:
    """Normaliza una lista de categorías conservando orden sin duplicados."""
    allowed_set = (
        {str(k or "").strip().lower() for k in valid_keys if str(k or "").strip()}
        if valid_keys is not None
        else None
    )

    def _is_valid(k: str) -> bool:
        if not k:
            return False
        if allowed_set is not None:
            return k in allowed_set
        return k in BUILTIN_CATEGORY_KEYS or bool(_CUSTOM_CATEGORY_KEY_RE.match(k))

    seen: List[str] = []
    for raw in raw_categories or []:
        key = str(raw or "").strip().lower()
        if _is_valid(key) and key not in seen:
            seen.append(key)
    if not seen and fallback:
        for fb in fallback:
            fb_key = str(fb or "").strip().lower()
            if _is_valid(fb_key) and fb_key not in seen:
                seen.append(fb_key)
    return seen


def mask_secret(raw_value: Optional[str]) -> str:
    """Devuelve versión enmascarada segura ('••••XXXX') o cadena vacía."""
    cleaned = str(raw_value or "").strip()
    if not cleaned:
        return ""
    if cleaned.startswith("••••"):
        return cleaned
    if len(cleaned) <= 4:
        return "••••"
    return f"••••{cleaned[-4:]}"


def is_masked_secret(raw_value: Optional[str]) -> bool:
    """Detecta si el frontend reenvió un valor previamente enmascarado sin editar."""
    return str(raw_value or "").strip().startswith("••••")


def _default_hub_config() -> Dict[str, Any]:
    return {
        "categories": {
            "principales": {
                "key": "principales",
                "label": "Cuentas Principales",
                "description": "Canales oficiales de marca personal y contenido destacado principal.",
                "topic_keywords": [
                    "principal",
                    "exclusiva",
                    "anuncio",
                    "destacado",
                    "opinion",
                    "historia",
                    "personal",
                ],
                "accounts": [
                    {
                        "id": "yt_principales_creadorstudio",
                        "platform": "youtube",
                        "handle": "@CreadorStudio",
                        "display_name": "CreadorStudio (Principal)",
                        "external_id": "",
                        "enabled": True,
                    },
                    {
                        "id": "ig_principales_creadorstudio",
                        "platform": "instagram",
                        "handle": "@creadorstudio",
                        "display_name": "CreadorStudio Instagram",
                        "external_id": "",
                        "enabled": False,
                    },
                    {
                        "id": "tt_principales_creadorstudio",
                        "platform": "tiktok",
                        "handle": "@creadorstudio",
                        "display_name": "CreadorStudio TikTok",
                        "external_id": "",
                        "enabled": False,
                    },
                    {
                        "id": "fb_principales_creadorstudio",
                        "platform": "facebook",
                        "handle": "CreadorStudio",
                        "display_name": "CreadorStudio Facebook",
                        "external_id": "",
                        "enabled": False,
                    },
                ],
            },
            "gaming": {
                "key": "gaming",
                "label": "Cuentas Gaming",
                "description": "Gameplays, hardware, DLSS/RTX, OBS, lanzamientos y streams jugando.",
                "topic_keywords": [
                    "juego",
                    "gaming",
                    "gameplay",
                    "gamer",
                    "partida",
                    "fps",
                    "rtx",
                    "dlss",
                    "nvidia",
                    "obs",
                    "ps5",
                    "pc",
                    "zelda",
                    "gta",
                    "fortnite",
                    "minecraft",
                    "warzone",
                    "xbox",
                    "nintendo",
                ],
                "accounts": [
                    {
                        "id": "ig_gaming_creador_gaming",
                        "platform": "instagram",
                        "handle": "@creador_gaming",
                        "display_name": "Creador Gaming",
                        "external_id": "",
                        "enabled": True,
                    },
                    {
                        "id": "yt_gaming_creadorstudio",
                        "platform": "youtube",
                        "handle": "@creadorstudio",
                        "display_name": "CreadorStudio YouTube",
                        "external_id": "",
                        "enabled": True,
                    },
                    {
                        "id": "tt_gaming_creador_gaming",
                        "platform": "tiktok",
                        "handle": "@creador.gaming",
                        "display_name": "Creador Gaming TikTok",
                        "external_id": "",
                        "enabled": True,
                    },
                    {
                        "id": "fb_gaming_creador_gaming",
                        "platform": "facebook",
                        "handle": "Creador Gaming",
                        "display_name": "Creador Gaming Page",
                        "external_id": "",
                        "enabled": True,
                    },
                ],
            },
            "clipping": {
                "key": "clipping",
                "label": "Cuentas Clipping",
                "description": "Red de clipping viral: debates, reacciones, podcast y humor.",
                "is_custom": False,
                "topic_keywords": [
                    "clip",
                    "clipeo",
                    "viral",
                    "reaccion",
                    "debate",
                    "polemica",
                    "humor",
                    "charla",
                    "podcast",
                    "entrevista",
                    "chisme",
                ],
                "accounts": [
                    {
                        "id": "ig_clip_short",
                        "platform": "instagram",
                        "handle": "@creador_short",
                        "display_name": "Creador Short",
                        "external_id": "",
                        "enabled": True,
                    },
                    {
                        "id": "ig_clip_fans",
                        "platform": "instagram",
                        "handle": "@creador_fans",
                        "display_name": "CreadorStudio Fans",
                        "external_id": "",
                        "enabled": True,
                    },
                    {
                        "id": "yt_clip_creadorstudio",
                        "platform": "youtube",
                        "handle": "@creadorstudio",
                        "display_name": "CreadorStudio YouTube",
                        "external_id": "",
                        "enabled": True,
                    },
                    {
                        "id": "tt_clip_clips",
                        "platform": "tiktok",
                        "handle": "@creador.clips",
                        "display_name": "Creador Clips",
                        "external_id": "",
                        "enabled": True,
                    },
                    {
                        "id": "tt_clip_short",
                        "platform": "tiktok",
                        "handle": "@creador.short",
                        "display_name": "Creador Short TikTok",
                        "external_id": "",
                        "enabled": True,
                    },
                    {
                        "id": "fb_clip_short",
                        "platform": "facebook",
                        "handle": "Creador Short",
                        "display_name": "Creador Short Page",
                        "external_id": "",
                        "enabled": True,
                    },
                    {
                        "id": "fb_clip_clips",
                        "platform": "facebook",
                        "handle": "Creador Clips",
                        "display_name": "Creador Clips Page",
                        "external_id": "",
                        "enabled": True,
                    },
                ],
            },
            "ometv": {
                "key": "ometv",
                "label": "Cuentas OMETV",
                "description": "Exclusivo para clips de OmeTV, charlas con desconocidos e interacciones random en vivo.",
                "is_custom": False,
                "topic_keywords": [
                    "ometv",
                    "omegle",
                    "desconocidos",
                    "desconocido",
                    "random",
                    "videochat",
                    "extranjeros",
                ],
                "accounts": [
                    {
                        "id": "ig_ometv_creador_ometv",
                        "platform": "instagram",
                        "handle": "@creador_ometv",
                        "display_name": "Creador OMETV",
                        "external_id": "",
                        "enabled": True,
                    },
                    {
                        "id": "yt_ometv_creadorstudio",
                        "platform": "youtube",
                        "handle": "@creadorstudio",
                        "display_name": "CreadorStudio YouTube",
                        "external_id": "",
                        "enabled": True,
                    },
                    {
                        "id": "tt_ometv_creador_ometv",
                        "platform": "tiktok",
                        "handle": "@creador_ometv",
                        "display_name": "Creador OMETV TikTok",
                        "external_id": "",
                        "enabled": True,
                    },
                    {
                        "id": "fb_ometv_creador_ometv",
                        "platform": "facebook",
                        "handle": "Creador OMETV",
                        "display_name": "Creador OMETV Page",
                        "external_id": "",
                        "enabled": True,
                    },
                ],
            },
        },
        "api_settings": {
            "youtube": {
                "client_id": "",
                "client_secret": "",
                "client_secret_json": "",
                "default_category_id": "22",
            },
            "instagram": {
                "app_id": "",
                "app_secret": "",
                "access_token": "",
                "business_id": "",
                "graph_version": "v21.0",
            },
            "tiktok": {
                "client_key": "",
                "client_secret": "",
                "access_token": "",
                "redirect_uri": "http://localhost:3456/callback/",
                "publish_mode": "DIRECT_POST",
            },
            "facebook": {
                "app_id": "",
                "page_access_token": "",
                "graph_version": "v21.0",
            },
        },
    }


def _read_json_safe(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _hydrate_api_secrets_from_legacy_files(config_dir: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Completa campos faltantes desde client_secret.json, meta_token.json y tiktok_client.json locales."""
    api = cfg.setdefault("api_settings", {})
    yt = api.setdefault("youtube", {})
    ig = api.setdefault("instagram", {})
    tt = api.setdefault("tiktok", {})
    fb = api.setdefault("facebook", {})

    cs_data = _read_json_safe(config_dir / "client_secret.json")
    cs_web = cs_data.get("installed") or cs_data.get("web") or {}
    if isinstance(cs_web, dict):
        if not yt.get("client_id") and cs_web.get("client_id"):
            yt["client_id"] = str(cs_web["client_id"])
        if not yt.get("client_secret") and cs_web.get("client_secret"):
            yt["client_secret"] = str(cs_web["client_secret"])

    meta_data = _read_json_safe(config_dir / "meta_token.json")
    if meta_data:
        meta_tok = str(meta_data.get("access_token") or meta_data.get("system_user_token") or "")
        if not ig.get("access_token") and meta_tok:
            ig["access_token"] = meta_tok
        if not fb.get("page_access_token") and meta_tok:
            fb["page_access_token"] = meta_tok
        if not ig.get("app_id") and meta_data.get("app_id"):
            ig["app_id"] = str(meta_data["app_id"])
        if not fb.get("app_id") and meta_data.get("app_id"):
            fb["app_id"] = str(meta_data["app_id"])

    tt_client = _read_json_safe(config_dir / "tiktok_client.json")
    if tt_client:
        if not tt.get("client_key") and tt_client.get("client_key"):
            tt["client_key"] = str(tt_client["client_key"])
        if not tt.get("client_secret") and tt_client.get("client_secret"):
            tt["client_secret"] = str(tt_client["client_secret"])
        if not tt.get("redirect_uri") and tt_client.get("redirect_uri"):
            tt["redirect_uri"] = str(tt_client["redirect_uri"])

    return cfg


def get_raw_social_hub_config(config_dir: Path) -> Dict[str, Any]:
    """Carga (o inicializa desde plantilla por defecto) la configuración completa con secretos reales."""
    config_dir.mkdir(parents=True, exist_ok=True)
    hub_path = config_dir / HUB_CONFIG_FILENAME
    default_cfg = _default_hub_config()
    stored = _read_json_safe(hub_path)

    merged_cats: Dict[str, Any] = {}
    stored_cats = stored.get("categories") if isinstance(stored.get("categories"), dict) else {}
    for cat_key in BUILTIN_CATEGORY_KEYS:
        base_cat = dict(default_cfg["categories"][cat_key])
        base_cat["is_custom"] = False
        ov = stored_cats.get(cat_key)
        if isinstance(ov, dict):
            if ov.get("label"):
                base_cat["label"] = str(ov["label"]).strip()
            if ov.get("description") is not None:
                base_cat["description"] = str(ov["description"])
            if isinstance(ov.get("topic_keywords"), list):
                base_cat["topic_keywords"] = [
                    str(k).strip() for k in ov["topic_keywords"] if str(k).strip()
                ]
            if isinstance(ov.get("accounts"), list):
                base_cat["accounts"] = _sanitize_accounts_list(ov["accounts"])
        merged_cats[cat_key] = base_cat

    for extra_key, ov in stored_cats.items():
        clean_k = str(extra_key or "").strip().lower()
        if clean_k in merged_cats or not isinstance(ov, dict):
            continue
        if not _CUSTOM_CATEGORY_KEY_RE.match(clean_k):
            continue
        merged_cats[clean_k] = {
            "key": clean_k,
            "label": str(ov.get("label") or clean_k.replace("_", " ").title()).strip()[:80],
            "description": str(ov.get("description") or "").strip()[:240],
            "is_custom": True,
            "topic_keywords": [
                str(k).strip().lower() for k in (ov.get("topic_keywords") or []) if str(k).strip()
            ][:30],
            "accounts": _sanitize_accounts_list(ov.get("accounts") or []),
        }

    merged_api: Dict[str, Any] = {}
    stored_api = stored.get("api_settings") if isinstance(stored.get("api_settings"), dict) else {}
    for net_key in SOCIAL_PLATFORMS:
        net_def = dict(default_cfg["api_settings"][net_key])
        ov_net = stored_api.get(net_key)
        if isinstance(ov_net, dict):
            for k, v in ov_net.items():
                if v is not None:
                    net_def[k] = str(v) if isinstance(v, str) else v
        merged_api[net_key] = net_def

    cfg = {"categories": merged_cats, "api_settings": merged_api}
    return _hydrate_api_secrets_from_legacy_files(config_dir, cfg)


def _sanitize_accounts_list(accounts: Sequence[Any]) -> List[Dict[str, Any]]:
    cleaned: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    for idx, raw in enumerate(accounts, start=1):
        if not isinstance(raw, dict):
            continue
        platform = str(raw.get("platform") or "").strip().lower()
        if platform not in SOCIAL_PLATFORMS:
            continue
        handle = str(raw.get("handle") or "").strip()
        if not handle:
            continue
        acc_id = str(raw.get("id") or "").strip() or f"{platform}_{idx}_{re.sub(r'[^a-zA-Z0-9_]+', '_', handle)[:24]}"
        while acc_id in seen_ids:
            acc_id = f"{acc_id}_{idx}"
        seen_ids.add(acc_id)
        cleaned.append(
            {
                "id": acc_id,
                "platform": platform,
                "handle": handle,
                "display_name": str(raw.get("display_name") or handle).strip(),
                "external_id": str(raw.get("external_id") or "").strip(),
                "enabled": bool(raw.get("enabled", True)),
            }
        )
    return cleaned


def get_public_social_hub_config(config_dir: Path) -> Dict[str, Any]:
    """Devuelve la configuración social sanitizada con secretos enmascarados para el frontend."""
    raw = get_raw_social_hub_config(config_dir)
    api = raw["api_settings"]
    yt = api["youtube"]
    ig = api["instagram"]
    tt = api["tiktok"]
    fb = api["facebook"]

    yt_token_file = (config_dir / "token.json").exists()
    yt_secret_file = (config_dir / "client_secret.json").exists()
    tt_tokens_data = _read_json_safe(config_dir / "tiktok_tokens.json")

    public_api = {
        "youtube": {
            "client_id": yt.get("client_id", ""),
            "client_secret": mask_secret(yt.get("client_secret")),
            "has_client_secret": bool(yt.get("client_secret") or yt_secret_file),
            "has_token": yt_token_file,
            "default_category_id": str(yt.get("default_category_id") or "22"),
        },
        "instagram": {
            "app_id": ig.get("app_id", ""),
            "app_secret": mask_secret(ig.get("app_secret")),
            "access_token": mask_secret(ig.get("access_token")),
            "has_app_secret": bool(ig.get("app_secret")),
            "has_access_token": bool(ig.get("access_token")),
            "business_id": ig.get("business_id", ""),
            "graph_version": ig.get("graph_version", "v21.0"),
        },
        "tiktok": {
            "client_key": tt.get("client_key", ""),
            "client_secret": mask_secret(tt.get("client_secret")),
            "access_token": mask_secret(tt.get("access_token")),
            "has_client_secret": bool(tt.get("client_secret")),
            "has_access_token": bool(tt.get("access_token") or tt_tokens_data),
            "redirect_uri": tt.get("redirect_uri", "http://localhost:3456/callback/"),
            "publish_mode": str(tt.get("publish_mode") or "DIRECT_POST"),
        },
        "facebook": {
            "app_id": fb.get("app_id", ""),
            "page_access_token": mask_secret(fb.get("page_access_token")),
            "has_page_access_token": bool(fb.get("page_access_token")),
            "graph_version": fb.get("graph_version", "v21.0"),
        },
    }
    return {
        "categories": raw["categories"],
        "api_settings": public_api,
    }


def _merge_secret_field(existing_val: str, incoming_val: Optional[str]) -> str:
    if incoming_val is None:
        return existing_val
    cleaned = str(incoming_val).strip()
    if not cleaned:
        return ""
    if is_masked_secret(cleaned):
        return existing_val
    return cleaned


def _sync_legacy_api_credential_files(config_dir: Path, raw_api: Dict[str, Any]) -> None:
    """Sincroniza credenciales editadas en la UI con los archivos JSON nativos de cada SDK."""
    config_dir.mkdir(parents=True, exist_ok=True)
    yt = raw_api.get("youtube") or {}
    ig = raw_api.get("instagram") or {}
    tt = raw_api.get("tiktok") or {}
    fb = raw_api.get("facebook") or {}

    cs_raw_json = str(yt.get("client_secret_json") or "").strip()
    if cs_raw_json and not is_masked_secret(cs_raw_json):
        try:
            parsed_cs = json.loads(cs_raw_json)
            if isinstance(parsed_cs, dict):
                (config_dir / "client_secret.json").write_text(
                    json.dumps(parsed_cs, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
        except Exception:
            pass

    meta_tok = str(ig.get("access_token") or fb.get("page_access_token") or "").strip()
    if meta_tok or ig.get("app_id"):
        meta_file = config_dir / "meta_token.json"
        existing_meta = _read_json_safe(meta_file)
        if meta_tok:
            existing_meta["access_token"] = meta_tok
        if ig.get("app_id"):
            existing_meta["app_id"] = str(ig["app_id"]).strip()
        if ig.get("business_id"):
            existing_meta["business_id"] = str(ig["business_id"]).strip()
        meta_file.write_text(json.dumps(existing_meta, indent=2, ensure_ascii=False), encoding="utf-8")

    if tt.get("client_key") or tt.get("client_secret"):
        tt_file = config_dir / "tiktok_client.json"
        existing_tt = _read_json_safe(tt_file)
        if tt.get("client_key"):
            existing_tt["client_key"] = str(tt["client_key"]).strip()
        if tt.get("client_secret"):
            existing_tt["client_secret"] = str(tt["client_secret"]).strip()
        existing_tt["redirect_uri"] = str(tt.get("redirect_uri") or "http://localhost:3456/callback/")
        tt_file.write_text(json.dumps(existing_tt, indent=2, ensure_ascii=False), encoding="utf-8")


def save_social_hub_config(config_dir: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Valida, persiste categorías base + personalizadas y APIs preservando secretos enmascarados."""
    current = get_raw_social_hub_config(config_dir)
    new_cats: Dict[str, Any] = {}
    in_cats = payload.get("categories") if isinstance(payload.get("categories"), dict) else {}

    def _merge_cat_entry(cat_key: str, base_cat: Dict[str, Any], cat_in: Any, is_custom: bool) -> Dict[str, Any]:
        cat_cur = dict(base_cat)
        cat_cur["key"] = cat_key
        cat_cur["is_custom"] = is_custom
        if isinstance(cat_in, dict):
            if cat_in.get("label"):
                cat_cur["label"] = str(cat_in["label"]).strip()[:80]
            if cat_in.get("description") is not None:
                cat_cur["description"] = str(cat_in["description"]).strip()[:240]
            if isinstance(cat_in.get("topic_keywords"), list):
                cat_cur["topic_keywords"] = list(
                    dict.fromkeys(
                        str(k).strip().lower() for k in cat_in["topic_keywords"] if str(k).strip()
                    )
                )[:30]
            if isinstance(cat_in.get("accounts"), list):
                cat_cur["accounts"] = _sanitize_accounts_list(cat_in["accounts"])
        return cat_cur

    for cat_key in BUILTIN_CATEGORY_KEYS:
        new_cats[cat_key] = _merge_cat_entry(
            cat_key, current["categories"][cat_key], in_cats.get(cat_key), is_custom=False
        )

    source_custom_cats = in_cats if in_cats else current["categories"]
    for raw_k, cat_in in source_custom_cats.items():
        clean_k = str(raw_k or "").strip().lower()
        if clean_k in new_cats or not isinstance(cat_in, dict):
            continue
        norm_k = slugify_category_key(clean_k)
        base_custom = current["categories"].get(
            norm_k,
            {
                "key": norm_k,
                "label": str(cat_in.get("label") or norm_k).strip()[:80],
                "description": "",
                "topic_keywords": [],
                "accounts": [],
                "is_custom": True,
            },
        )
        new_cats[norm_k] = _merge_cat_entry(norm_k, base_custom, cat_in, is_custom=True)

    cur_api = current["api_settings"]
    in_api = payload.get("api_settings") if isinstance(payload.get("api_settings"), dict) else {}

    yt_in = in_api.get("youtube") or {}
    ig_in = in_api.get("instagram") or {}
    tt_in = in_api.get("tiktok") or {}
    fb_in = in_api.get("facebook") or {}

    merged_api = {
        "youtube": {
            "client_id": str(yt_in.get("client_id", cur_api["youtube"].get("client_id", ""))).strip(),
            "client_secret": _merge_secret_field(
                str(cur_api["youtube"].get("client_secret", "")), yt_in.get("client_secret")
            ),
            "client_secret_json": _merge_secret_field(
                str(cur_api["youtube"].get("client_secret_json", "")), yt_in.get("client_secret_json")
            ),
            "default_category_id": str(
                yt_in.get("default_category_id", cur_api["youtube"].get("default_category_id", "22"))
            ).strip()
            or "22",
        },
        "instagram": {
            "app_id": str(ig_in.get("app_id", cur_api["instagram"].get("app_id", ""))).strip(),
            "app_secret": _merge_secret_field(
                str(cur_api["instagram"].get("app_secret", "")), ig_in.get("app_secret")
            ),
            "access_token": _merge_secret_field(
                str(cur_api["instagram"].get("access_token", "")), ig_in.get("access_token")
            ),
            "business_id": str(
                ig_in.get("business_id", cur_api["instagram"].get("business_id", ""))
            ).strip(),
            "graph_version": str(
                ig_in.get("graph_version", cur_api["instagram"].get("graph_version", "v21.0"))
            ).strip()
            or "v21.0",
        },
        "tiktok": {
            "client_key": str(tt_in.get("client_key", cur_api["tiktok"].get("client_key", ""))).strip(),
            "client_secret": _merge_secret_field(
                str(cur_api["tiktok"].get("client_secret", "")), tt_in.get("client_secret")
            ),
            "access_token": _merge_secret_field(
                str(cur_api["tiktok"].get("access_token", "")), tt_in.get("access_token")
            ),
            "redirect_uri": str(
                tt_in.get("redirect_uri", cur_api["tiktok"].get("redirect_uri", "http://localhost:3456/callback/"))
            ).strip(),
            "publish_mode": (
                "TIKTOK_STUDIO"
                if str(tt_in.get("publish_mode", cur_api["tiktok"].get("publish_mode", "DIRECT_POST")))
                .strip()
                .upper()
                == "TIKTOK_STUDIO"
                else (
                    "INBOX_UPLOAD"
                    if str(tt_in.get("publish_mode", cur_api["tiktok"].get("publish_mode", "DIRECT_POST")))
                    .strip()
                    .upper()
                    in ("INBOX_UPLOAD", "UPLOAD_TO_DRAFT")
                    else "DIRECT_POST"
                )
            ),
        },
        "facebook": {
            "app_id": str(fb_in.get("app_id", cur_api["facebook"].get("app_id", ""))).strip(),
            "page_access_token": _merge_secret_field(
                str(cur_api["facebook"].get("page_access_token", "")), fb_in.get("page_access_token")
            ),
            "graph_version": str(
                fb_in.get("graph_version", cur_api["facebook"].get("graph_version", "v21.0"))
            ).strip()
            or "v21.0",
        },
    }

    final_raw = {"categories": new_cats, "api_settings": merged_api}
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / HUB_CONFIG_FILENAME).write_text(
        json.dumps(final_raw, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _sync_legacy_api_credential_files(config_dir, merged_api)
    return get_public_social_hub_config(config_dir)


def create_social_category(
    config_dir: Path,
    *,
    label: str,
    key: Optional[str] = None,
    description: str = "",
    topic_keywords: Optional[Sequence[str]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Crea una nueva categoría de cuentas sociales personalizada."""
    clean_label = str(label or "").strip()[:80]
    if not clean_label:
        raise ValueError("El nombre de la categoría es obligatorio.")
    cat_key = slugify_category_key(key or clean_label)
    current = get_raw_social_hub_config(config_dir)
    if cat_key in current["categories"]:
        raise ValueError(f"Ya existe una categoría con clave '{cat_key}'.")

    kws = list(
        dict.fromkeys(str(k).strip().lower() for k in (topic_keywords or []) if str(k).strip())
    )[:30]
    created_entry: Dict[str, Any] = {
        "key": cat_key,
        "label": clean_label,
        "description": str(description or "").strip()[:240],
        "is_custom": True,
        "topic_keywords": kws,
        "accounts": [],
    }
    current["categories"][cat_key] = created_entry
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / HUB_CONFIG_FILENAME).write_text(
        json.dumps(current, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return created_entry, get_public_social_hub_config(config_dir)


def delete_social_category(config_dir: Path, category_key: str) -> Dict[str, Any]:
    """Elimina una categoría personalizada (protege las categorías base del sistema)."""
    clean_key = str(category_key or "").strip().lower()
    if clean_key in BUILTIN_CATEGORY_KEYS:
        raise ValueError(
            f"La categoría base '{clean_key}' no se puede eliminar; puedes editar o desactivar sus cuentas."
        )
    current = get_raw_social_hub_config(config_dir)
    if clean_key not in current["categories"]:
        raise KeyError(f"Categoría '{category_key}' no encontrada.")
    del current["categories"][clean_key]
    (config_dir / HUB_CONFIG_FILENAME).write_text(
        json.dumps(current, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return get_public_social_hub_config(config_dir)


def verify_platform_connection(config_dir: Path, platform: str) -> Dict[str, Any]:
    """Comprueba estado real de credenciales OAuth/Graph y cuentas activas para una plataforma."""
    net = str(platform or "").strip().lower()
    if net not in SOCIAL_PLATFORMS:
        raise ValueError(f"Plataforma no soportada: {platform}")

    raw = get_raw_social_hub_config(config_dir)
    api = raw["api_settings"][net]
    active_count = sum(
        1
        for cat in raw["categories"].values()
        for acc in cat.get("accounts", [])
        if acc.get("platform") == net and acc.get("enabled")
    )

    if net == "youtube":
        tok_file = config_dir / "token.json"
        has_secret = bool(api.get("client_secret") or (config_dir / "client_secret.json").exists())
        has_token = tok_file.exists()
        if has_secret and has_token:
            try:
                from google.auth.transport.requests import Request as GoogleAuthRequest
                from google.oauth2.credentials import Credentials as GoogleCredentials

                creds = GoogleCredentials.from_authorized_user_file(
                    str(tok_file),
                    [
                        "https://www.googleapis.com/auth/youtube.upload",
                        "https://www.googleapis.com/auth/youtube",
                    ],
                )
                if creds and not creds.valid:
                    if creds.expired and creds.refresh_token:
                        creds.refresh(GoogleAuthRequest())
                        if hasattr(creds, "to_json"):
                            tok_file.write_text(creds.to_json(), encoding="utf-8")
                    else:
                        return {
                            "platform": net,
                            "connected": False,
                            "status_label": "Sesión Expirada (Autorizar OAuth)",
                            "detail": "token.json expirado sin refresh_token válido. Pulsa 'Autorizar OAuth' para renovar.",
                        }
                if not creds or not creds.valid:
                    return {
                        "platform": net,
                        "connected": False,
                        "status_label": "Sesión Expirada (Autorizar OAuth)",
                        "detail": "Credenciales OAuth de YouTube inválidas. Pulsa 'Autorizar OAuth' para renovar.",
                    }
            except Exception as yt_exc:
                return {
                    "platform": net,
                    "connected": False,
                    "status_label": "Sesión Expirada (Autorizar OAuth)",
                    "detail": f"El token OAuth de YouTube expiró o fue revocado ({yt_exc}). Pulsa 'Autorizar OAuth' para renovar.",
                }
            return {
                "platform": net,
                "connected": True,
                "status_label": "Conectado",
                "detail": f"OAuth YouTube listo y validado (token.json activo) · {active_count} cuenta(s) activa(s).",
            }
        if has_secret:
            return {
                "platform": net,
                "connected": False,
                "status_label": "Falta Autorización OAuth",
                "detail": "client_secret configurado; pulsa 'Autorizar OAuth' para generar token.json.",
            }
        return {
            "platform": net,
            "connected": False,
            "status_label": "Sin Credenciales",
            "detail": "Configura Client ID/Secret o pega client_secret.json de Google Cloud.",
        }

    if net == "instagram":
        has_tok = bool(api.get("access_token") or _read_json_safe(config_dir / "meta_token.json").get("access_token"))
        if has_tok:
            return {
                "platform": net,
                "connected": True,
                "status_label": "Token Activo",
                "detail": f"Meta Graph {api.get('graph_version', 'v21.0')} configurado · {active_count} cuenta(s) activa(s).",
            }
        return {
            "platform": net,
            "connected": False,
            "status_label": "Token Pendiente",
            "detail": "Ingresa el Access Token de Meta Graph API (Instagram Business).",
        }

    if net == "tiktok":
        pub_mode_val = str(api.get("publish_mode", "DIRECT_POST")).strip().upper()
        if pub_mode_val == "TIKTOK_STUDIO":
            return {
                "platform": net,
                "connected": True,
                "status_label": "TikTok Studio Web (PC)",
                "detail": f"Automatización en navegador Brave con confirmación previa · {active_count} cuenta(s) activa(s).",
            }
        has_client = bool(api.get("client_key") and api.get("client_secret"))
        has_tok = bool(api.get("access_token") or _read_json_safe(config_dir / "tiktok_tokens.json"))
        if has_client and has_tok:
            return {
                "platform": net,
                "connected": True,
                "status_label": "Conectado",
                "detail": f"TikTok API v2 ({api.get('publish_mode', 'DIRECT_POST')}) lista · {active_count} cuenta(s) activa(s).",
            }
        if has_client:
            return {
                "platform": net,
                "connected": False,
                "status_label": "Client Key Listo",
                "detail": f"Falta Access Token OAuth · {active_count} cuenta(s) configurada(s).",
            }
        return {
            "platform": net,
            "connected": False,
            "status_label": "Sin Credenciales",
            "detail": "Configura Client Key y Client Secret de TikTok Developers.",
        }

    # facebook
    has_fb_tok = bool(
        api.get("page_access_token")
        or raw["api_settings"]["instagram"].get("access_token")
        or _read_json_safe(config_dir / "meta_token.json").get("access_token")
    )
    if has_fb_tok:
        return {
            "platform": "facebook",
            "connected": True,
            "status_label": "Token Activo",
            "detail": f"Facebook Graph {api.get('graph_version', 'v21.0')} configurado · {active_count} página(s) activa(s).",
        }
    return {
        "platform": "facebook",
        "connected": False,
        "status_label": "Token Pendiente",
        "detail": "Ingresa el Page Access Token de Meta Graph API para Facebook Reels.",
    }


def classify_short_account_categories(
    *,
    text: str,
    title: str,
    tags: Sequence[str],
    scene_category: str,
    scene_label: str,
    hub_cfg: Dict[str, Any],
    allowed_categories: Optional[Sequence[str]] = None,
    auto_by_topic: bool = True,
) -> List[str]:
    """
    Asigna 1 o varias categorías de cuenta según tema (principales, gaming, clipping, ometv o personalizadas),
    restringido a las categorías habilitadas en el Perfil de Contenido.
    """
    cats_cfg = hub_cfg.get("categories") or {}
    all_hub_keys = list(cats_cfg.keys()) or list(BUILTIN_CATEGORY_KEYS)
    allowed = normalize_account_categories(
        allowed_categories, fallback=all_hub_keys, valid_keys=all_hub_keys
    )
    if not auto_by_topic:
        return allowed

    haystack = _strip_accents(f"{title} {text} {' '.join(tags)} {scene_category} {scene_label}")
    matched: List[str] = []

    for cat_key in allowed:
        kws = (cats_cfg.get(cat_key) or {}).get("topic_keywords") or []
        hit = False
        for kw in kws:
            kw_norm = _strip_accents(str(kw)).strip()
            if len(kw_norm) < 2:
                continue
            if re.search(rf"(?<!\w){re.escape(kw_norm)}(?!\w)", haystack):
                hit = True
                break
        if not hit and cat_key == "gaming" and any(
            g in haystack for g in ("videojuegos", "gaming_hud", "gameplay")
        ):
            hit = True
        if not hit and cat_key == "ometv" and any(o in haystack for o in ("ometv", "omegle")):
            hit = True
        if not hit and cat_key == "clipping" and any(
            c in haystack for c in ("reacciones", "podcast", "realitys", "opinion_monologo", "debate")
        ):
            hit = True
        if hit:
            matched.append(cat_key)

    if matched:
        return matched
    return ["clipping"] if "clipping" in allowed else [allowed[0]]


def resolve_target_accounts_for_categories(
    categories: Sequence[str],
    hub_cfg: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    """Resuelve todas las cuentas activas por plataforma para un conjunto de categorías (sin duplicados)."""
    cats_cfg = hub_cfg.get("categories") or {}
    all_hub_keys = list(cats_cfg.keys()) or list(BUILTIN_CATEGORY_KEYS)
    norm_cats = normalize_account_categories(
        categories, fallback=("clipping",), valid_keys=all_hub_keys
    )
    targets: Dict[str, List[Dict[str, Any]]] = {p: [] for p in SOCIAL_PLATFORMS}
    seen_handles: Dict[str, set[str]] = {p: set() for p in SOCIAL_PLATFORMS}

    for cat_key in norm_cats:
        cat_obj = cats_cfg.get(cat_key) or {}
        for acc in cat_obj.get("accounts") or []:
            if not acc.get("enabled", True):
                continue
            plat = str(acc.get("platform") or "").strip().lower()
            handle = str(acc.get("handle") or "").strip()
            if plat not in SOCIAL_PLATFORMS or not handle:
                continue
            norm_handle = handle.lstrip("@").lower()
            if norm_handle in seen_handles[plat]:
                continue
            seen_handles[plat].add(norm_handle)
            targets[plat].append(dict(acc))

    return targets


def init_facebook_queue_db(db_path: Path) -> Path:
    """Crea la tabla facebook_scheduled_queue en SQLite si no existe."""
    db_file = Path(db_path).resolve()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS facebook_scheduled_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_path TEXT NOT NULL,
                account_key TEXT NOT NULL,
                fb_page_id TEXT NOT NULL,
                caption TEXT NOT NULL,
                scheduled_time_utc TEXT NOT NULL,
                scheduled_time_ast TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                post_id TEXT,
                error TEXT,
                created_at_utc TEXT NOT NULL,
                published_at_utc TEXT,
                UNIQUE(video_path, account_key)
            )
            """
        )
        conn.commit()
    return db_file


def enqueue_facebook_reel(
    *,
    video_path: str | Path,
    account_key: str,
    fb_page_id: str = "",
    caption: str,
    scheduled_time_utc: str,
    scheduled_time_ast: str = "",
    db_path: Path,
) -> int:
    """Encola un Reel en facebook_scheduled_queue para programación / publicación vía Meta Graph API."""
    init_facebook_queue_db(db_path)
    acct_clean = account_key.lstrip("@").strip().lower() or "creadorstudio_page"
    resolved_video = str(Path(video_path).resolve())
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ast_val = scheduled_time_ast or scheduled_time_utc

    with sqlite3.connect(str(db_file_path := Path(db_path).resolve())) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO facebook_scheduled_queue (
                video_path, account_key, fb_page_id, caption,
                scheduled_time_utc, scheduled_time_ast, status, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)
            ON CONFLICT(video_path, account_key) DO UPDATE SET
                fb_page_id = excluded.fb_page_id,
                caption = excluded.caption,
                scheduled_time_utc = excluded.scheduled_time_utc,
                scheduled_time_ast = excluded.scheduled_time_ast,
                status = CASE
                    WHEN facebook_scheduled_queue.status = 'PUBLISHED' THEN 'PUBLISHED'
                    ELSE 'PENDING'
                END,
                error = CASE
                    WHEN facebook_scheduled_queue.status = 'PUBLISHED' THEN facebook_scheduled_queue.error
                    ELSE NULL
                END
            """,
            (
                resolved_video,
                acct_clean,
                str(fb_page_id or ""),
                caption,
                scheduled_time_utc,
                ast_val,
                now_iso,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid or 0)


FB_RESUMABLE_THRESHOLD_BYTES = 50 * 1024 * 1024  # 50 MB


def _http_post_multipart(
    url: str,
    *,
    data: Dict[str, Any],
    files: Optional[Dict[str, Any]] = None,
    timeout: int = 180,
) -> Any:
    """Envía subida de video multipart/form-data o form-urlencoded a Facebook Graph Video API."""
    return requests.post(url, data=data, files=files if files else None, timeout=timeout)


def _parse_fb_graph_response(resp: Any, context: str) -> Dict[str, Any]:
    """Valida HTTP status y cuerpo JSON de Meta Graph API sin ocultar errores HTML/vacíos."""
    status_code = int(getattr(resp, "status_code", 200) or 200)
    try:
        body = resp.json()
    except Exception:
        raw_text = str(getattr(resp, "text", "") or "")
        clean_text = " ".join(re.sub(r"<[^>]+>", " ", raw_text).split())[:180]
        raise RuntimeError(
            f"Facebook HTTP {status_code} ({context}): respuesta no-JSON ({clean_text or 'vacía'})"
        )

    if isinstance(body, dict) and body.get("error"):
        err_obj = body["error"]
        if isinstance(err_obj, dict):
            code = err_obj.get("code")
            msg = err_obj.get("error_user_msg") or err_obj.get("message") or str(err_obj)
        else:
            code = None
            msg = str(err_obj)
        raise RuntimeError(f"Facebook Graph error ({context}, code={code}): {msg}")

    if status_code >= 400:
        raise RuntimeError(f"Facebook HTTP {status_code} ({context}): {body}")

    return body if isinstance(body, dict) else {}


def _upload_facebook_video_resumable(
    endpoint_url: str,
    *,
    video_path: str,
    file_size: int,
    caption: str,
    page_tok: str,
    page_id: str,
) -> str:
    """Ejecuta subida reanudable en 3 fases (start -> transfer chunks -> finish) contra graph-video.facebook.com."""
    start_resp = _http_post_multipart(
        endpoint_url,
        data={
            "upload_phase": "start",
            "file_size": str(file_size),
            "access_token": page_tok,
        },
        files=None,
        timeout=60,
    )
    start_body = _parse_fb_graph_response(start_resp, f"{page_id}/start")
    session_id = str(start_body.get("upload_session_id") or "").strip()
    video_id = str(start_body.get("video_id") or "").strip()
    start_offset = int(start_body.get("start_offset", 0))
    end_offset = int(start_body.get("end_offset", 0))
    if not session_id:
        raise RuntimeError(f"Facebook Graph error ({page_id}/start): falta upload_session_id ({start_body})")

    chunks_sent = 0
    max_chunks = 512
    with open(video_path, "rb") as vf:
        while start_offset < end_offset:
            chunks_sent += 1
            if chunks_sent > max_chunks:
                raise RuntimeError(f"Facebook resumable upload ({page_id}): excedió límite de {max_chunks} bloques.")
            vf.seek(start_offset)
            chunk_bytes = vf.read(end_offset - start_offset)
            if not chunk_bytes:
                raise RuntimeError(
                    f"Facebook resumable upload ({page_id}): lectura vacía en offset {start_offset}..{end_offset}."
                )

            tr_body: Dict[str, Any] = {}
            for attempt in range(1, 4):
                try:
                    tr_resp = _http_post_multipart(
                        endpoint_url,
                        data={
                            "upload_phase": "transfer",
                            "upload_session_id": session_id,
                            "start_offset": str(start_offset),
                            "access_token": page_tok,
                        },
                        files={"video_file_chunk": ("chunk.mp4", io.BytesIO(chunk_bytes), "application/octet-stream")},
                        timeout=240,
                    )
                    tr_body = _parse_fb_graph_response(tr_resp, f"{page_id}/transfer@{start_offset}")
                    break
                except Exception as exc:
                    is_transient = isinstance(exc, requests.RequestException) or "HTTP 5" in str(exc)
                    if attempt >= 3 or not is_transient:
                        raise
                    time.sleep(1.5 * attempt)

            new_start = int(tr_body.get("start_offset", end_offset))
            new_end = int(tr_body.get("end_offset", new_start))
            if new_start <= start_offset and new_start < new_end:
                raise RuntimeError(
                    f"Facebook resumable upload ({page_id}): offset estancado ({start_offset} -> {new_start})."
                )
            start_offset, end_offset = new_start, new_end

    fin_resp = _http_post_multipart(
        endpoint_url,
        data={
            "upload_phase": "finish",
            "upload_session_id": session_id,
            "description": caption,
            "access_token": page_tok,
        },
        files=None,
        timeout=120,
    )
    fin_body = _parse_fb_graph_response(fin_resp, f"{page_id}/finish")
    if fin_body.get("success") is False:
        raise RuntimeError(f"Facebook Graph error ({page_id}/finish): {fin_body}")

    post_id = str(fin_body.get("post_id") or fin_body.get("id") or video_id).strip()
    if not post_id:
        raise RuntimeError(f"Facebook Graph error ({page_id}/finish): sin post_id ni video_id ({fin_body})")
    return post_id


def upload_facebook_page_video(
    *,
    video_path: str,
    caption: str,
    page_id: str,
    page_tok: str,
    graph_version: str = "v21.0",
) -> str:
    """Sube un video a una Página de Facebook usando graph-video.facebook.com y carga reanudable >= 50 MB."""
    endpoint_url = f"https://graph-video.facebook.com/{graph_version}/{page_id}/videos"
    file_size = os.path.getsize(video_path)
    if file_size >= FB_RESUMABLE_THRESHOLD_BYTES:
        return _upload_facebook_video_resumable(
            endpoint_url,
            video_path=video_path,
            file_size=file_size,
            caption=caption,
            page_tok=page_tok,
            page_id=page_id,
        )

    try:
        with open(video_path, "rb") as vf:
            resp = _http_post_multipart(
                endpoint_url,
                data={"description": caption, "access_token": page_tok},
                files={"source": (Path(video_path).name, vf, "video/mp4")},
                timeout=240,
            )
        body = _parse_fb_graph_response(resp, f"{page_id}/videos")
        post_id = str(body.get("id") or body.get("post_id") or "").strip()
        if not post_id:
            raise RuntimeError(f"Facebook Graph error ({page_id}): {body}")
        return post_id
    except Exception as exc:
        err_txt = str(exc)
        if "HTTP 413" in err_txt or "no-JSON" in err_txt:
            return _upload_facebook_video_resumable(
                endpoint_url,
                video_path=video_path,
                file_size=file_size,
                caption=caption,
                page_tok=page_tok,
                page_id=page_id,
            )
        raise


def _resolve_fb_page_credentials(
    *,
    fb_page_id: str,
    account_key: str,
    meta_data: Dict[str, Any],
    raw_hub: Dict[str, Any],
    graph_version: str,
) -> Tuple[str, str]:
    """Resuelve (page_id, page_access_token) desde fb_pages de meta_token.json o api_settings.facebook."""
    norm_target = re.sub(r"[^a-z0-9]", "", str(account_key or "").lower())
    fb_pages = meta_data.get("fb_pages") if isinstance(meta_data.get("fb_pages"), dict) else {}

    for pg_key, pg_info in fb_pages.items():
        if not isinstance(pg_info, dict):
            continue
        pid = str(pg_info.get("page_id") or "").strip()
        pname = str(pg_info.get("page_name") or pg_key or "")
        norm_pg = re.sub(r"[^a-z0-9]", "", f"{pg_key} {pname}".lower())
        norm_key_only = re.sub(r"[^a-z0-9]", "", str(pg_key).lower())
        norm_name_only = re.sub(r"[^a-z0-9]", "", pname.lower())
        matched = bool(fb_page_id and pid == fb_page_id) or (
            bool(norm_target) and norm_target in (norm_key_only, norm_name_only, norm_pg)
        )
        if matched:
            ptok = str(pg_info.get("page_access_token") or "").strip()
            if pid and ptok:
                return pid, ptok

    fb_api = (raw_hub.get("api_settings") or {}).get("facebook") or {}
    ig_api = (raw_hub.get("api_settings") or {}).get("instagram") or {}
    fallback_tok = str(
        fb_api.get("page_access_token")
        or meta_data.get("access_token")
        or ig_api.get("access_token")
        or ""
    ).strip()

    user_tok = str(meta_data.get("access_token") or fallback_tok).strip()
    if user_tok and (not fb_page_id or not fb_pages):
        try:
            acct_resp = requests.get(
                f"https://graph.facebook.com/{graph_version}/me/accounts",
                params={"fields": "id,name,access_token", "access_token": user_tok},
                timeout=30,
            ).json()
            for page_obj in acct_resp.get("data", []):
                if not isinstance(page_obj, dict):
                    continue
                pid = str(page_obj.get("id") or "").strip()
                pname = str(page_obj.get("name") or "")
                norm_name = re.sub(r"[^a-z0-9]", "", pname.lower())
                if (fb_page_id and pid == fb_page_id) or (norm_target and norm_name == norm_target):
                    ptok = str(page_obj.get("access_token") or fallback_tok).strip()
                    if pid and ptok:
                        return pid, ptok
        except Exception:
            pass

    return str(fb_page_id or "").strip(), fallback_tok


def process_due_facebook_queue(
    db_path: Path,
    config_dir: Path,
    force_all: bool = False,
) -> Dict[str, int]:
    """
    Revisa facebook_scheduled_queue en SQLite y publica los videos PENDING cuyo scheduled_time_utc
    ya venció usando Meta Graph API /{page_id}/videos.
    """
    init_facebook_queue_db(db_path)
    now_utc_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with sqlite3.connect(str(Path(db_path).resolve())) as conn:
        conn.row_factory = sqlite3.Row
        if force_all:
            due_rows = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT * FROM facebook_scheduled_queue
                    WHERE status IN ('PENDING', 'FAILED')
                    ORDER BY scheduled_time_utc ASC, id ASC
                    """
                ).fetchall()
            ]
        else:
            due_rows = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT * FROM facebook_scheduled_queue
                    WHERE status = 'PENDING' AND scheduled_time_utc <= ?
                    ORDER BY scheduled_time_utc ASC, id ASC
                    """,
                    (now_utc_iso,),
                ).fetchall()
            ]

    if not due_rows:
        return {"processed": 0, "published": 0, "failed": 0}

    meta_data = _read_json_safe(Path(config_dir) / "meta_token.json")
    raw_hub = get_raw_social_hub_config(Path(config_dir))
    graph_version = str(
        ((raw_hub.get("api_settings") or {}).get("facebook") or {}).get("graph_version") or "v21.0"
    ).strip() or "v21.0"

    published_count = 0
    failed_count = 0

    for item in due_rows:
        row_id = int(item["id"])
        video_path = str(item.get("video_path") or "")
        account_key = str(item.get("account_key") or "")
        fb_page_id = str(item.get("fb_page_id") or "")
        caption = str(item.get("caption") or "")

        if not video_path or not os.path.exists(video_path):
            err_msg = f"Archivo de video no encontrado: {video_path}"
            with sqlite3.connect(str(Path(db_path).resolve())) as conn:
                conn.execute(
                    "UPDATE facebook_scheduled_queue SET status = 'FAILED', error = ? WHERE id = ?",
                    (err_msg, row_id),
                )
                conn.commit()
            failed_count += 1
            continue

        page_id, page_tok = _resolve_fb_page_credentials(
            fb_page_id=fb_page_id,
            account_key=account_key,
            meta_data=meta_data,
            raw_hub=raw_hub,
            graph_version=graph_version,
        )
        if not page_id or not page_tok:
            err_msg = f"Falta page_id o page_access_token para Facebook '{account_key}'."
            with sqlite3.connect(str(Path(db_path).resolve())) as conn:
                conn.execute(
                    "UPDATE facebook_scheduled_queue SET status = 'FAILED', error = ? WHERE id = ?",
                    (err_msg, row_id),
                )
                conn.commit()
            failed_count += 1
            continue

        try:
            post_id = upload_facebook_page_video(
                video_path=video_path,
                caption=caption,
                page_id=page_id,
                page_tok=page_tok,
                graph_version=graph_version,
            )

            pub_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            with sqlite3.connect(str(Path(db_path).resolve())) as conn:
                conn.execute(
                    """
                    UPDATE facebook_scheduled_queue
                    SET status = 'PUBLISHED',
                        fb_page_id = ?,
                        post_id = ?,
                        error = NULL,
                        published_at_utc = ?
                    WHERE id = ?
                    """,
                    (page_id, post_id, pub_now, row_id),
                )
                conn.commit()
            published_count += 1
        except Exception as exc:
            logger.warning("Error publicando video en Facebook [ID=%s]: %s", row_id, exc)
            with sqlite3.connect(str(Path(db_path).resolve())) as conn:
                conn.execute(
                    "UPDATE facebook_scheduled_queue SET status = 'FAILED', error = ? WHERE id = ?",
                    (str(exc)[:300], row_id),
                )
                conn.commit()
            failed_count += 1

    return {"processed": len(due_rows), "published": published_count, "failed": failed_count}


def list_facebook_queue(db_path: Path, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lista las entradas de facebook_scheduled_queue en SQLite."""
    init_facebook_queue_db(db_path)
    with sqlite3.connect(str(Path(db_path).resolve())) as conn:
        conn.row_factory = sqlite3.Row
        if status_filter:
            rows = conn.execute(
                "SELECT * FROM facebook_scheduled_queue WHERE status = ? ORDER BY scheduled_time_utc ASC, id ASC",
                (status_filter,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM facebook_scheduled_queue ORDER BY scheduled_time_utc ASC, id ASC"
            ).fetchall()
    return [dict(r) for r in rows]
