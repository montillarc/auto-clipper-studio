"""
Skill 4: youtube-shorts-uploader
Handles OAuth 2.0 authentication (./config/client_secret.json -> ./config/token.json)
and uploads scheduled YouTube Shorts via YouTube Data API v3 (videos().insert, resumable=True).
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
try:
    from google_auth_oauthlib.flow import WSGITimeoutError
except ImportError:  # pragma: no cover - compatibilidad versiones previas
    WSGITimeoutError = TimeoutError  # type: ignore[misc, assignment]
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger("youtube-shorts-uploader")

SCOPES: List[str] = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]
DEFAULT_CLIENT_SECRET_PATH = Path("./config/client_secret.json")
DEFAULT_TOKEN_PATH = Path("./config/token.json")


def get_authenticated_youtube_service(
    client_secret_path: str | Path = DEFAULT_CLIENT_SECRET_PATH,
    token_path: str | Path = DEFAULT_TOKEN_PATH,
    *,
    allow_interactive: bool = True,
    oauth_timeout_sec: int = 120,
) -> Resource:
    """
    Authenticates via OAuth 2.0 reading ./config/client_secret.json and automatically
    saving/refreshing ./config/token.json with scope https://www.googleapis.com/auth/youtube.upload.
    When `allow_interactive=False`, fails fast instead of blocking HTTP workers waiting for a browser flow.
    """
    secret_file = Path(client_secret_path).resolve()
    tok_file = Path(token_path).resolve()
    tok_file.parent.mkdir(parents=True, exist_ok=True)

    creds: Credentials | None = None
    if tok_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(tok_file), SCOPES)
        except Exception as exc:
            logger.warning("Token existente inválido (%s). Se regenerará.", exc)
            creds = None

    if not creds or not creds.valid:
        refreshed = False
        refresh_error_msg = ""
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("Refrescando token OAuth 2.0 en %s...", tok_file)
                creds.refresh(Request())
                refreshed = True
            except Exception as exc:
                refresh_error_msg = str(exc)
                logger.warning("Refresh token expirado o revocado (%s). Solicitando nuevo login OAuth 2.0...", exc)
                creds = None

        if not refreshed:
            if not allow_interactive:
                detail = f" ({refresh_error_msg})" if refresh_error_msg else ""
                raise RuntimeError(
                    "Sesión OAuth de YouTube expirada o sin autorizar"
                    f"{detail}. Ve a Cuentas & APIs y pulsa 'Autorizar OAuth' en YouTube."
                )
            if not secret_file.exists():
                raise FileNotFoundError(
                    f"No se encontró el archivo de credenciales OAuth 2.0 en: {secret_file}. "
                    "Descárgalo desde Google Cloud Console y guárdalo como './config/client_secret.json'."
                )
            logger.info("Iniciando flujo OAuth 2.0 local desde %s...", secret_file)
            flow = InstalledAppFlow.from_client_secrets_file(str(secret_file), SCOPES)
            try:
                creds = flow.run_local_server(
                    port=0,
                    open_browser=True,
                    timeout_seconds=max(15, int(oauth_timeout_sec)),
                    access_type="offline",
                    prompt="consent",
                )
            except WSGITimeoutError as exc:
                raise TimeoutError(
                    f"Tiempo de espera agotado ({oauth_timeout_sec}s) esperando la autorización OAuth 2.0 de YouTube."
                ) from exc
            if not creds or not creds.valid:
                raise RuntimeError("No se obtuvieron credenciales OAuth 2.0 válidas tras autorizar YouTube.")

        tok_file.write_text(creds.to_json(), encoding="utf-8")
        logger.info("Token OAuth 2.0 guardado en: %s", tok_file)

    return build("youtube", "v3", credentials=creds)


def format_shorts_title(raw_title: str) -> str:
    """Ensures the title ends with `#Shorts` and fits within YouTube's 100-char limit."""
    clean = " ".join(raw_title.strip().split())
    # Strip trailing #shorts variations so we can append canonical #Shorts
    if clean.lower().endswith("#shorts"):
        clean = clean[: -len("#shorts")].strip()

    suffix = " #Shorts"
    max_base_len = 100 - len(suffix)
    if len(clean) > max_base_len:
        clean = clean[: max_base_len - 1].rstrip() + "…"
    return f"{clean}{suffix}"


def format_shorts_description(raw_description: str) -> str:
    """Ensures the description contains #Shorts cleanly."""
    desc = raw_description.strip()
    if "#Shorts" not in desc and "#shorts" not in desc:
        desc = f"{desc} #Shorts"
    elif "#shorts" in desc and "#Shorts" not in desc:
        desc = desc.replace("#shorts", "#Shorts")
    return desc.strip()


def _is_immediate_or_past_publish_time(publish_at_iso: str | None) -> bool:
    """Devuelve True si el horario es NOW, inválido/vacío o <= now + 5 min (YouTube rechaza publishAt pasado)."""
    if not publish_at_iso:
        return True
    cleaned = str(publish_at_iso).strip()
    if not cleaned or cleaned.upper() == "NOW":
        return True
    try:
        iso_norm = f"{cleaned[:-1]}+00:00" if cleaned.endswith("Z") else cleaned
        parsed = datetime.fromisoformat(iso_norm)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc) <= (datetime.now(timezone.utc) + timedelta(minutes=5))
    except Exception:
        return False


def build_upload_body(
    title: str,
    description: str,
    tags: Sequence[str],
    publish_at_iso: str | None = None,
    category_id: str = "22",
) -> Dict[str, Any]:
    """Constructs the exact YouTube Data API v3 videos().insert request body."""
    clean_cat = str(category_id or "22").strip()
    if not clean_cat.isdigit():
        clean_cat = "22"

    if _is_immediate_or_past_publish_time(publish_at_iso):
        status_dict: Dict[str, Any] = {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        }
    else:
        status_dict = {
            "privacyStatus": "private",
            "publishAt": publish_at_iso,
            "selfDeclaredMadeForKids": False,
        }

    return {
        "snippet": {
            "title": format_shorts_title(title),
            "description": format_shorts_description(description),
            "tags": list(tags),
            "categoryId": clean_cat,
        },
        "status": status_dict,
    }


def upload_scheduled_short(
    video_path: str | Path,
    title: str,
    description: str,
    tags: Sequence[str],
    publish_at_iso: str | None = None,
    category_id: str = "22",
    client_secret_path: str | Path = DEFAULT_CLIENT_SECRET_PATH,
    token_path: str | Path = DEFAULT_TOKEN_PATH,
    *,
    allow_interactive: bool = True,
    oauth_timeout_sec: int = 120,
) -> Dict[str, Any]:
    """
    Uploads the video file to YouTube using videos().insert with MediaFileUpload(resumable=True).
    If `publish_at_iso` is None, 'NOW' or <= now + 5m, publishes immediately as PUBLIC ('Pan Caliente' live mode).
    Otherwise schedules its publication at `publish_at_iso`.
    """
    video_file = Path(video_path).resolve()
    if not video_file.exists():
        raise FileNotFoundError(f"El archivo de video a subir no existe: {video_file}")

    youtube = get_authenticated_youtube_service(
        client_secret_path=client_secret_path,
        token_path=token_path,
        allow_interactive=allow_interactive,
        oauth_timeout_sec=oauth_timeout_sec,
    )

    body = build_upload_body(
        title=title,
        description=description,
        tags=tags,
        publish_at_iso=publish_at_iso,
        category_id=category_id,
    )

    media = MediaFileUpload(
        str(video_file),
        mimetype="video/mp4",
        chunksize=4 * 1024 * 1024,  # 4 MB chunks
        resumable=True,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    logger.info(
        "Iniciando subida resumible a YouTube: '%s' (Programado para %s)...",
        body["snippet"]["title"],
        publish_at_iso,
    )

    response: Dict[str, Any] | None = None
    retry_count = 0
    max_retries = 5

    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                progress_pct = int(status.progress() * 100)
                logger.info("Progreso de subida: %d%%", progress_pct)
        except HttpError as err:
            if err.resp.status in (500, 502, 503, 504) and retry_count < max_retries:
                retry_count += 1
                wait_sec = 2**retry_count
                logger.warning(
                    "Error HTTP %s temporal en subida. Reintentando en %ds (%d/%d)...",
                    err.resp.status,
                    wait_sec,
                    retry_count,
                    max_retries,
                )
                time.sleep(wait_sec)
            else:
                raise

    video_id = response.get("id", "UNKNOWN_ID")
    logger.info(
        "¡Short subido y programado exitosamente! YouTube Video ID: %s | publishAt: %s",
        video_id,
        publish_at_iso,
    )
    return response


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Skill 4: YouTube Shorts Uploader")
    parser.add_argument("--video", required=True, help="Ruta al Short .mp4 renderizado")
    parser.add_argument("--title", required=True, help="Título del Short")
    parser.add_argument("--description", required=True, help="Descripción en primera persona")
    parser.add_argument("--tags", default="Shorts,CreadorStudio", help="Tags separados por coma")
    parser.add_argument("--publish-at", required=True, help="Timestamp UTC ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)")
    parser.add_argument("--category-id", default="22", choices=["22", "24"], help="Categoría de YouTube")
    args = parser.parse_args()

    tag_list = [t.strip() for t in args.tags.split(",") if t.strip()]
    res = upload_scheduled_short(
        video_path=args.video,
        title=args.title,
        description=args.description,
        tags=tag_list,
        publish_at_iso=args.publish_at,
        category_id=args.category_id,
    )
    print(f"Uploaded YouTube ID: {res.get('id')}")
