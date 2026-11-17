"""
Servicio silencioso de inicio con Windows (Startup Sentinel).
Corre automáticamente al encender la PC, vigila ./inbox_videos/, calcula la estimación
de Shorts de cualquier video nuevo, actualiza ./config/pending_job.json y muestra
una notificación nativa en Windows avisando cuántos Shorts pueden salir.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Set

from inbox_inspector import (
    CONFIG_DIR,
    INBOX_DIR,
    PENDING_JOB_FILE,
    VIDEO_EXTENSIONS,
    estimate_video_potential,
    wait_until_file_ready,
)


def _send_windows_toast(title: str, message: str) -> None:
    """Envía una notificación nativa de escritorio en Windows."""
    ps_script = f"""
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
    $template = @"
    <toast>
        <visual>
            <binding template="ToastGeneric">
                <text>{title}</text>
                <text>{message}</text>
            </binding>
        </visual>
    </toast>
"@
    $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $xml.LoadXml($template)
    $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Auto-Clipper Studio").Show($toast)
    """
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
            capture_output=True,
            timeout=6,
            creationflags=0x08000000,
        )
    except Exception:
        pass


def run_startup_sentinel() -> None:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    notified_files: Set[str] = set()

    while True:
        try:
            current_files = {
                p.name
                for p in INBOX_DIR.iterdir()
                if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
            }
            # Limpiar archivos que ya fueron procesados o movidos
            notified_files.intersection_update(current_files)

            for item in sorted(INBOX_DIR.iterdir()):
                if (
                    item.is_file()
                    and item.suffix.lower() in VIDEO_EXTENSIONS
                    and item.name not in notified_files
                ):
                    if wait_until_file_ready(item):
                        report = estimate_video_potential(item)
                        PENDING_JOB_FILE.write_text(
                            json.dumps(report, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
                        notified_files.add(item.name)
                        _send_windows_toast(
                            title=f"🎬 Nuevo video detectado: {report['file_name']}",
                            message=(
                                f"Duración: {report['duration_formatted']} | "
                                f"Puedo sacarte {report['recommended_shorts']} Shorts (máx {report['max_possible_shorts']}). "
                                "Confírmame en el chat de Antigravity para procesarlo."
                            ),
                        )
        except Exception:
            pass
        time.sleep(3.0)


if __name__ == "__main__":
    run_startup_sentinel()
