"""
TikTok Official Content Posting API v2 — OAuth 2.0 + Uploader (tiktok_api_uploader.py)
Permite autenticar las 6 cuentas secundarias de TikTok de CreadorStudio una sola vez,
auto-renovar sus tokens (access_token 24h / refresh_token 365 días) en ./config/tiktok_tokens.json,
y subir Shorts 1080p60 directamente en segundo plano sin abrir el navegador ni mover el mouse.

Soporta dos modos oficiales de TikTok Content Posting API v2:
1. DIRECT POST (/v2/post/publish/video/init/) -> Publica directamente en el perfil (scope: video.publish).
   - Nota de TikTok API: Si la App en TikTok Developers aún no ha pasado revisión ("Unaudited"),
     TikTok exige privacy_level="SELF_ONLY" en Direct Post, o bien usar el modo INBOX/DRAFT.
2. INBOX UPLOAD (/v2/post/publish/inbox/video/init/) -> Envía el video listo con título/hashtags
   a la bandeja de TikTok (scope: video.upload).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import math
import os
import secrets
import sys
import time
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional

import requests

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parents[3]
CONFIG_DIR = BASE_DIR / "config"
CLIENT_CONFIG_PATH = CONFIG_DIR / "tiktok_client.json"
TOKENS_PATH = CONFIG_DIR / "tiktok_tokens.json"

REDIRECT_PORT = 3456
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback/"

# Las 6 cuentas secundarias oficiales de TikTok (@creadorstudio principal queda excluida)
TIKTOK_ACCOUNTS = [
    "creador.clips",
    "creador.fans",
    "creador.videos",
    "creador.short",
    "creador_ometv",
    "creador.gaming",
    "creador_secundario",
]

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
DIRECT_POST_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
INBOX_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
STATUS_FETCH_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"


def load_client_config() -> Dict[str, str]:
    if not CLIENT_CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"No existe {CLIENT_CONFIG_PATH}. Guarda ahí tu client_key y client_secret de TikTok Developers."
        )
    return json.loads(CLIENT_CONFIG_PATH.read_text(encoding="utf-8"))


def save_client_config(client_key: str, client_secret: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "client_key": client_key.strip(),
        "client_secret": client_secret.strip(),
        "redirect_uri": REDIRECT_URI,
    }
    CLIENT_CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Configuración de cliente TikTok guardada en: {CLIENT_CONFIG_PATH}")


def load_tokens() -> Dict[str, Any]:
    if TOKENS_PATH.exists():
        try:
            return json.loads(TOKENS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_tokens(tokens: Dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TOKENS_PATH.write_text(json.dumps(tokens, indent=2, ensure_ascii=False), encoding="utf-8")


def _generate_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def authorize_account_interactive(account_username: str) -> Dict[str, Any]:
    """
    Inicia un servidor local temporal en http://localhost:3456/callback/ y abre la URL
    de autorización OAuth 2.0 de TikTok para vincular la cuenta indicada.
    """
    cfg = load_client_config()
    client_key = cfg["client_key"]
    client_secret = cfg["client_secret"]
    redirect_uri = cfg.get("redirect_uri", REDIRECT_URI)

    code_verifier, code_challenge = _generate_pkce()
    state = secrets.token_hex(16)

    params = {
        "client_key": client_key,
        "scope": "user.info.basic,video.publish,video.upload",
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    captured: Dict[str, Optional[str]] = {"code": None, "error": None}

    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            if "code" in qs:
                captured["code"] = qs["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                html = (
                    f"<html><body style='font-family:sans-serif;text-align:center;padding:40px;'>"
                    f"<h2>✅ Cuenta @{account_username} conectada con éxito a CreadorStudio</h2>"
                    f"<p>Ya puedes cerrar esta pestaña y volver a Antigravity.</p></body></html>"
                )
                self.wfile.write(html.encode("utf-8"))
            else:
                captured["error"] = qs.get("error_description", qs.get("error", ["unknown"]))[0]
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"Error: {captured['error']}".encode("utf-8"))

        def log_message(self, format, *args):
            return

    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), CallbackHandler)
    print(f"\n=======================================================")
    print(f"🔗 Autorizando cuenta TikTok: @{account_username}")
    print(f"👉 Abre este enlace en el perfil donde tengas @{account_username}:")
    print(f"   {url}")
    print(f"=======================================================\n")

    try:
        webbrowser.open(url)
    except Exception:
        pass

    server.handle_request()
    server.server_close()

    if not captured["code"]:
        raise RuntimeError(f"No se recibió código OAuth para @{account_username}: {captured['error']}")

    r = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": captured["code"],
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        },
        timeout=30,
    ).json()

    if "access_token" not in r:
        raise RuntimeError(f"Error al canjear token de TikTok: {r}")

    now = int(time.time())
    acct_clean = account_username.lstrip("@").strip().lower()
    tokens = load_tokens()
    tokens[acct_clean] = {
        "username": acct_clean,
        "open_id": r.get("open_id"),
        "access_token": r["access_token"],
        "refresh_token": r.get("refresh_token"),
        "expires_at": now + int(r.get("expires_in", 86400)) - 300,
        "refresh_expires_at": now + int(r.get("refresh_expires_in", 31536000)),
        "scope": r.get("scope", ""),
        "updated_at": now,
    }
    save_tokens(tokens)
    print(f"✅ Token guardado para @{acct_clean} (open_id={r.get('open_id')})")
    return tokens[acct_clean]


def get_valid_access_token(account_username: str) -> str:
    """Devuelve un access_token válido para la cuenta, renovándolo con refresh_token si expiró."""
    acct_clean = account_username.lstrip("@").strip().lower()
    tokens = load_tokens()
    if acct_clean not in tokens:
        raise KeyError(
            f"La cuenta @{acct_clean} aún no está autorizada en {TOKENS_PATH}. "
            f"Ejecuta: python tiktok_api_uploader.py --auth {acct_clean}"
        )

    entry = tokens[acct_clean]
    now = int(time.time())
    if now < int(entry.get("expires_at", 0)) and entry.get("access_token"):
        return entry["access_token"]

    cfg = load_client_config()
    r = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": cfg["client_key"],
            "client_secret": cfg["client_secret"],
            "grant_type": "refresh_token",
            "refresh_token": entry["refresh_token"],
        },
        timeout=30,
    ).json()

    if "access_token" not in r:
        raise RuntimeError(f"No se pudo refrescar el token de @{acct_clean}: {r}")

    entry["access_token"] = r["access_token"]
    entry["refresh_token"] = r.get("refresh_token", entry["refresh_token"])
    entry["expires_at"] = now + int(r.get("expires_in", 86400)) - 300
    entry["updated_at"] = now
    tokens[acct_clean] = entry
    save_tokens(tokens)
    return entry["access_token"]


def query_creator_info(access_token: str) -> Dict[str, Any]:
    """Consulta las opciones de privacidad permitidas para la cuenta en TikTok API."""
    r = requests.post(
        CREATOR_INFO_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        timeout=30,
    ).json()
    return r.get("data", {})


def compute_tiktok_chunk_plan(file_size: int) -> tuple[int, int]:
    """
    Calcula (chunk_size, total_chunk_count) siguiendo la especificación estricta de TikTok Content Posting API v2:
    - Archivos <= 64 MB se suben en 1 único bloque igual a `file_size`.
    - Archivos > 64 MB usan bloques de 10 MB y `total_chunk_count = floor(file_size / chunk_size)`,
      de modo que el último bloque absorba los bytes sobrantes (< 20 MB <= 128 MB máximo).
    """
    if file_size <= 0:
        raise ValueError("El archivo de video está vacío para subir a TikTok.")
    max_single_chunk = 64 * 1024 * 1024
    if file_size <= max_single_chunk:
        return file_size, 1
    chunk_size = 10 * 1024 * 1024
    total_chunks = max(1, file_size // chunk_size)
    return chunk_size, total_chunks


def upload_video_chunks(
    upload_url: str,
    video_path: str,
    chunk_size: int,
    total_chunk_count: Optional[int] = None,
) -> None:
    """Sube el archivo MP4 por bloques (Byte-Range) a los servidores de TikTok con reintentos."""
    file_size = os.path.getsize(video_path)
    effective_total = (
        max(1, int(total_chunk_count))
        if total_chunk_count is not None
        else max(1, file_size // max(1, chunk_size))
    )

    with open(video_path, "rb") as vf:
        for chunk_idx in range(effective_total):
            start_byte = chunk_idx * chunk_size
            data = vf.read() if chunk_idx == effective_total - 1 else vf.read(chunk_size)
            end_byte = start_byte + len(data) - 1

            headers = {
                "Content-Type": "video/mp4",
                "Content-Length": str(len(data)),
                "Content-Range": f"bytes {start_byte}-{end_byte}/{file_size}",
            }
            success = False
            last_err = ""
            for attempt in range(3):
                try:
                    resp = requests.put(upload_url, headers=headers, data=data, timeout=180)
                    if resp.status_code in (200, 201, 206):
                        success = True
                        break
                    last_err = f"HTTP {resp.status_code} - {resp.text}"
                except Exception as exc:
                    last_err = str(exc)
                time.sleep(2)

            if not success:
                raise RuntimeError(
                    f"Error subiendo bloque {chunk_idx+1}/{effective_total} a TikTok tras 3 intentos: {last_err}"
                )


def publish_tiktok_video(
    account_username: str,
    video_path: str,
    caption: str,
    mode: str = "auto",
) -> Dict[str, Any]:
    """
    Publica un Short en TikTok vía Content Posting API v2:
    - Si la app está auditada por TikTok, publica directo en PUBLIC_TO_EVERYONE.
    - Si mode es inbox/INBOX_UPLOAD/UPLOAD_TO_DRAFT o la app es Unaudited/Sandbox, envía al Inbox/Borrador oficial.
    """
    access_token = get_valid_access_token(account_username)
    file_size = os.path.getsize(video_path)
    chunk_size, total_chunk_count = compute_tiktok_chunk_plan(file_size)

    creator_info = query_creator_info(access_token)
    privacy_options = creator_info.get("privacy_level_options", ["SELF_ONLY"])
    norm_mode = str(mode or "auto").strip().lower()
    use_inbox = norm_mode in ("inbox", "inbox_upload", "upload_to_draft")

    if use_inbox:
        init_endpoint = INBOX_INIT_URL
        payload = {
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunk_count,
            }
        }
    else:
        init_endpoint = DIRECT_POST_INIT_URL
        privacy = "PUBLIC_TO_EVERYONE" if "PUBLIC_TO_EVERYONE" in privacy_options else "SELF_ONLY"
        payload = {
            "post_info": {
                "title": caption[:2200],
                "privacy_level": privacy,
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunk_count,
            },
        }

    init_resp = requests.post(
        init_endpoint,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json=payload,
        timeout=60,
    ).json()

    err = init_resp.get("error", {})
    if err.get("code") == "unaudited_client_can_only_post_to_private_accounts" and not use_inbox:
        print(
            f"  ℹ️ [TikTok @{account_username}] App aún no auditada para Direct Post en cuenta pública; "
            f"usando modo oficial INBOX UPLOAD (/v2/post/publish/inbox/video/init/)..."
        )
        init_resp = requests.post(
            INBOX_INIT_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": file_size,
                    "chunk_size": chunk_size,
                    "total_chunk_count": total_chunk_count,
                }
            },
            timeout=60,
        ).json()
        err = init_resp.get("error", {})

    if err.get("code") != "ok":
        raise RuntimeError(f"TikTok API init error (@{account_username}): {init_resp}")

    data = init_resp["data"]
    publish_id = data["publish_id"]
    upload_url = data["upload_url"]

    print(
        f"  [TikTok @{account_username}] Subiendo {os.path.basename(video_path)} "
        f"({file_size/(1024*1024):.1f} MB en {total_chunk_count} bloque(s))..."
    )
    upload_video_chunks(upload_url, video_path, chunk_size, total_chunk_count)

    for _ in range(30):
        time.sleep(4)
        st = requests.post(
            STATUS_FETCH_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={"publish_id": publish_id},
            timeout=30,
        ).json()
        status_val = st.get("data", {}).get("status")
        if status_val in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
            print(f"  ✅ [TikTok @{account_username}] ¡Completado! status={status_val} | publish_id={publish_id}")
            return {
                "status": status_val,
                "publish_id": publish_id,
                "post_id": st.get("data", {}).get("publicaly_available_post_id"),
            }
        if status_val == "FAILED":
            raise RuntimeError(f"TikTok publicación falló (@{account_username}): {st}")

    return {"status": "PROCESSING", "publish_id": publish_id}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TikTok Content Posting API v2 Manager")
    parser.add_argument("--set-credentials", nargs=2, metavar=("CLIENT_KEY", "CLIENT_SECRET"), help="Guarda Client Key y Client Secret")
    parser.add_argument("--auth", metavar="USERNAME", help="Autoriza una cuenta de TikTok (ej. creador.clips)")
    parser.add_argument("--list-accounts", action="store_true", help="Muestra las cuentas conectadas")
    args = parser.parse_args()

    if args.set_credentials:
        save_client_config(args.set_credentials[0], args.set_credentials[1])
    elif args.auth:
        authorize_account_interactive(args.auth)
    elif args.list_accounts:
        toks = load_tokens()
        print("Cuentas de TikTok en ./config/tiktok_tokens.json:")
        for acct in TIKTOK_ACCOUNTS:
            st = "✅ CONECTADA" if acct in toks else "⏳ PENDIENTE"
            print(f"  - @{acct}: {st}")
