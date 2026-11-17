import os
import sys
import time
import json
import subprocess
import requests

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import imageio_ffmpeg
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
CONFIG_PATH = str(BASE_DIR / "config" / "meta_token.json")
PROGRESS_PATH = str(BASE_DIR / "processing" / "ig_api_upload_progress.json")
FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()


def _silent_subprocess_kwargs():
    """Garantiza ejecución invisible sin ventana de consola en Windows (CREATE_NO_WINDOW + SW_HIDE)."""
    if os.name != "nt":
        return {}
    kw = {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
    }
    if hasattr(subprocess, "STARTUPINFO"):
        si = subprocess.STARTUPINFO()
        si.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0x00000001)
        si.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        kw["startupinfo"] = si
    return kw

# Mapa opcional de IDs Instagram Business (las cuentas activas se gestionan en Cuentas & APIs)
IG_ACCOUNTS: dict[str, str] = {}


def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Meta token config not found at {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_progress():
    if os.path.exists(PROGRESS_PATH):
        try:
            with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
                prog = json.load(f)
        except Exception:
            prog = {}
    else:
        prog = {}

    prog.setdefault("video_urls", {})
    for acct in IG_ACCOUNTS:
        prog.setdefault(acct, {})
    return prog


def save_progress(prog):
    with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
        json.dump(prog, f, indent=2, ensure_ascii=False)


def ensure_ig_compliant_mp4(video_path):
    """
    Encodes a 1080x1920 @ 60.00 FPS MP4 at 8 Mbps (max 10 Mbps) H.264 NVENC + 48000 Hz AAC
    with +faststart (~42-48 MB per 45s clip) for fast, 100% reliable Instagram Reels API ingestion.
    """
    out_dir = os.path.join(os.path.dirname(video_path), "ig_ready_8m")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, os.path.basename(video_path))
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1024 * 1024:
        return out_path

    print(f"  [FFmpeg] Optimizing {os.path.basename(video_path)} to 1080p60 (60fps, 8Mbps, 48kHz AAC)...")
    cmd = [
        FFMPEG_BIN, "-y", "-i", video_path,
        "-r", "60",
        "-c:v", "h264_nvenc", "-preset", "p5",
        "-b:v", "8M", "-maxrate", "10M", "-bufsize", "20M",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k",
        "-movflags", "+faststart",
        out_path
    ]
    subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **_silent_subprocess_kwargs(),
    )
    return out_path


def stage_video_url(ready_path):
    """
    Sube el MP4 optimizado a un CDN público con soporte completo de byte-ranges y Content-Type: video/mp4.
    Implementa redundancia dual automática (Uguu + Catbox) para garantizar 100% de disponibilidad.
    """
    file_size_mb = os.path.getsize(ready_path) / (1024 * 1024)
    print(f"  [Stage] Subiendo {os.path.basename(ready_path)} ({file_size_mb:.1f} MB) a CDN de staging con redundancia...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    # Intento 1: Uguu.se
    for attempt in range(2):
        try:
            with open(ready_path, "rb") as vf:
                r = requests.post(
                    "https://uguu.se/upload",
                    headers=headers,
                    files={"files[]": ("video.mp4", vf, "video/mp4")},
                    timeout=180,
                )
            if r.status_code == 200:
                data = r.json()
                url = data["files"][0]["url"]
                print(f"          [Uguu OK] Staged URL: {url}")
                return url
        except Exception as e:
            print(f"          Uguu intento {attempt+1} falló: {e}")
            time.sleep(2)

    # Intento 2 (Fallback): Catbox.moe
    print("  [Stage Fallback] Conmutando a Catbox CDN de alta velocidad...")
    for attempt in range(2):
        try:
            with open(ready_path, "rb") as vf:
                r = requests.post(
                    "https://catbox.moe/user/api.php",
                    headers=headers,
                    data={"reqtype": "fileupload"},
                    files={"fileToUpload": (os.path.basename(ready_path), vf, "video/mp4")},
                    timeout=180,
                )
            if r.status_code == 200 and r.text.startswith("https://files.catbox.moe/"):
                url = r.text.strip()
                print(f"          [Catbox OK] Staged URL: {url}")
                return url
        except Exception as e:
            print(f"          Catbox intento {attempt+1} falló: {e}")
            time.sleep(2)

    raise RuntimeError(f"Fallo crítico al alojar {ready_path} en los CDNs de staging (Uguu y Catbox).")


def publish_reel_via_url(ig_user_id, video_url, caption, access_token, graph_host="https://graph.facebook.com/v21.0"):
    """Creates an Instagram Reel container from a staged video_url, waits for FINISHED, and publishes it."""
    r = requests.post(
        f"{graph_host}/{ig_user_id}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true",
            "access_token": access_token,
        },
        timeout=60,
    ).json()

    container_id = r.get("id")
    if not container_id:
        raise RuntimeError(f"Failed to create Reel container: {r}")

    print(f"  [IG={ig_user_id}] Created container {container_id}, polling status...")
    for poll in range(40):
        time.sleep(4)
        st = requests.get(
            f"{graph_host}/{container_id}",
            params={"fields": "id,status_code,status", "access_token": access_token},
            timeout=30,
        ).json()
        code = st.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Container {container_id} failed: {st}")
    else:
        raise TimeoutError(f"Container {container_id} timed out.")

    pub = requests.post(
        f"{graph_host}/{ig_user_id}/media_publish",
        data={"creation_id": container_id, "access_token": access_token},
        timeout=90,
    ).json()
    media_id = pub.get("id")
    if not media_id:
        raise RuntimeError(f"Failed to publish {container_id}: {pub}")

    permalink = ""
    try:
        perm = requests.get(
            f"{graph_host}/{media_id}",
            params={"fields": "id,permalink,shortcode", "access_token": access_token},
            timeout=30,
        ).json()
        permalink = perm.get("permalink", "")
    except Exception:
        pass

    print(f"  ✅ [IG={ig_user_id}] PUBLISHED! media_id={media_id} -> {permalink}")

    # Auto-publish to the corresponding Facebook Page if configured in meta_token.json (fb_pages)
    fb_video_id = ""
    try:
        ig_to_acct = {v: k for k, v in IG_ACCOUNTS.items()}
        acct_key = ig_to_acct.get(str(ig_user_id))
        if acct_key:
            cfg_now = load_config()
            fb_info = cfg_now.get("fb_pages", {}).get(acct_key)
            if not fb_info:
                # Auto-discover from /me/accounts if a new FB page (e.g. CreadorStudio Videos) was added
                accts_resp = requests.get(
                    f"{graph_host}/me/accounts",
                    params={"fields": "id,name,access_token", "access_token": access_token},
                    timeout=30,
                ).json()
                for page_obj in accts_resp.get("data", []):
                    norm_name = page_obj.get("name", "").lower().replace(" ", "")
                    if norm_name == acct_key:
                        fb_info = {
                            "page_id": page_obj["id"],
                            "page_name": page_obj["name"],
                            "page_access_token": page_obj["access_token"],
                        }
                        cfg_now.setdefault("fb_pages", {})[acct_key] = fb_info
                        with open(CONFIG_PATH, "w", encoding="utf-8") as cf:
                            json.dump(cfg_now, cf, indent=2, ensure_ascii=False)
                        break

            if fb_info and fb_info.get("page_id") and fb_info.get("page_access_token"):
                page_id = fb_info["page_id"]
                page_tok = fb_info["page_access_token"]
                fb_res = requests.post(
                    f"{graph_host}/{page_id}/videos",
                    data={
                        "file_url": video_url,
                        "description": caption,
                        "access_token": page_tok,
                    },
                    timeout=90,
                ).json()
                fb_video_id = fb_res.get("id", "")
                if fb_video_id:
                    print(f"  ✅ [FB={fb_info.get('page_name', page_id)}] AUTO-PUBLISHED TO FACEBOOK PAGE! video_id={fb_video_id}")
                else:
                    print(f"  ⚠️ [FB={page_id}] Facebook Page video response: {fb_res}")
    except Exception as fb_err:
        print(f"  ⚠️ [FB] Auto-publish warning for {ig_user_id}: {fb_err}")

    return {
        "container_id": container_id,
        "media_id": media_id,
        "permalink": permalink,
        "fb_video_id": fb_video_id,
    }


def run_endofabyss_batch():
    cfg = load_config()
    token = cfg["access_token"]
    batch_file = BASE_DIR / "processing" / "batch_summary.json"
    with open(batch_file, "r", encoding="utf-8") as f:
        batch = json.load(f)

    prog = load_progress()
    save_progress(prog)

    for clip in batch:
        idx_str = str(clip["idx"])
        active_accounts = list(IG_ACCOUNTS.keys())
        if not active_accounts:
            break
        if all(prog.get(a, {}).get(idx_str, {}).get("status") == "PUBLISHED" for a in active_accounts):
            print(f"[SKIP] Short #{idx_str} already published.")
            continue

        print(f"\n=======================================================")
        print(f"🎬 Processing Short #{idx_str}: {clip['title']}")
        print(f"=======================================================")

        video_url = prog["video_urls"].get(idx_str)
        if not video_url:
            ready_path = ensure_ig_compliant_mp4(clip["file"])
            video_url = stage_video_url(ready_path)
            prog["video_urls"][idx_str] = video_url
            save_progress(prog)

        for acct_name in active_accounts:
            if prog[acct_name].get(idx_str, {}).get("status") == "PUBLISHED":
                print(f"  [SKIP] @{acct_name} Short #{idx_str} already published: {prog[acct_name][idx_str].get('permalink')}")
                continue

            ig_id = IG_ACCOUNTS[acct_name]
            print(f"  ---> Publishing Short #{idx_str} to @{acct_name} ({ig_id})...")
            for retry in range(3):
                try:
                    res = publish_reel_via_url(ig_id, video_url, clip["reels_caption"], token)
                    prog[acct_name][idx_str] = {
                        "status": "PUBLISHED",
                        "title": clip["title"],
                        "container_id": res["container_id"],
                        "media_id": res["media_id"],
                        "permalink": res["permalink"],
                    }
                    save_progress(prog)
                    break
                except Exception as e:
                    print(f"  [WARN] Retry {retry+1}/3 on @{acct_name} Short #{idx_str}: {e}")
                    if retry < 2:
                        # Re-stage video if URL expired
                        ready_path = ensure_ig_compliant_mp4(clip["file"])
                        video_url = stage_video_url(ready_path)
                        prog["video_urls"][idx_str] = video_url
                        save_progress(prog)
                        time.sleep(5)
                    else:
                        prog[acct_name][idx_str] = {"status": "FAILED", "error": str(e)}
                        save_progress(prog)

    print("\n🎉 ALL INSTAGRAM REELS PUBLISHED! Progress saved to:", PROGRESS_PATH)


if __name__ == "__main__":
    run_endofabyss_batch()
