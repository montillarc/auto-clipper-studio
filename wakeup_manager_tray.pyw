"""
CreadorStudio & CreadorSecundario — Wakeup & Scheduled Processes Manager (Windows 11 Fluent Dark UI)
Aplicación ultra-ligera con estética nativa de Windows 11 Dark Mode (#181818 / #222222 / #2D2D2D)
y barra de título oscura nativa (DWM). Vive minimizada junto al reloj de Windows (System Tray).
"""

from __future__ import annotations

import ctypes
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import messagebox
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import customtkinter as ctk
import pystray
from PIL import Image, ImageDraw

AST_TZ = ZoneInfo("America/Santo_Domingo")
UTC_TZ = timezone.utc

BASE_DIR = Path(__file__).resolve().parent
SHORT_YT_DB = BASE_DIR / "config" / "schedule_state.db"
SIGNAL_FILE = BASE_DIR / "config" / ".wakeup_tray_show.signal"
CREATE_NO_WINDOW = 0x08000000

RUN_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_REG_NAME = "AutoClipper_WakeupManagerTray"

# Paleta Oficial Windows 11 Dark Mode (Fluent Neutral Dark)
W11_BG = "#181818"          # Fondo principal de ventana (igual a Explorador W11 / Antigravity)
W11_SURFACE = "#212121"     # Superficie de tarjetas (Cards)
W11_SURFACE_ALT = "#262626" # Superficie secundaria / hover
W11_BORDER = "#303030"      # Borde sutil de 1px
W11_BTN = "#2D2D2D"         # Botón estándar Windows 11 Dark
W11_BTN_HOVER = "#383838"   # Hover de botón estándar
W11_BTN_BORDER = "#3B3B3B"  # Borde sutil de botón
W11_ACCENT = "#0067C0"      # Azul Fluent Windows 11
W11_ACCENT_HOVER = "#1975C5"
W11_CYAN = "#60CDFF"        # Acento claro Windows 11 Dark
W11_TEXT = "#F3F3F3"        # Texto primario
W11_SUBTEXT = "#9E9E9E"     # Texto secundario / metadatos
W11_GREEN = "#6CCB5F"       # Estado activo sutil W11
W11_AMBER = "#FCE100"       # Advertencia / Wake
W11_DANGER_HOVER = "#442222"
W11_DANGER_TEXT = "#FF99A4"

ctk.set_appearance_mode("dark")


def apply_win11_dark_titlebar(window: tk.Misc) -> None:
    """Aplica la barra de título oscura nativa de Windows 11 (#181818) y esquinas redondeadas DWM."""
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            hwnd = window.winfo_id()
        dwmapi = ctypes.windll.dwmapi
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        dark_mode = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))
        # DWMWA_CAPTION_COLOR = 35 (COLORREF 0x00BBGGRR -> 0x00181818)
        caption_color = ctypes.c_int(0x00181818)
        dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption_color), ctypes.sizeof(caption_color))
        # DWMWA_WINDOW_CORNER_PREFERENCE = 33 (DWMWCP_ROUND = 2)
        corner_pref = ctypes.c_int(2)
        dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner_pref), ctypes.sizeof(corner_pref))
    except Exception:
        pass


def create_tray_icon_image(size: int = 64) -> Image.Image:
    """Ícono minimalista estilo Windows 11 Fluent para la bandeja del sistema."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((4, 4, size - 4, size - 4), radius=14, fill=(32, 32, 32, 255), outline=(96, 205, 255, 255), width=3)
    cx, cy = size // 2, size // 2
    bolt = [
        (cx + 3, 12),
        (cx - 11, cy + 2),
        (cx - 1, cy + 2),
        (cx - 4, size - 12),
        (cx + 11, cy - 3),
        (cx + 1, cy - 3),
    ]
    d.polygon(bolt, fill=(96, 205, 255, 255))
    return img


def run_ps(cmd: str, timeout: int = 20) -> str:
    full_cmd = f"[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; {cmd}"
    res = subprocess.run(
        ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", full_cmd],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
    )
    return (res.stdout or "").strip()


def suspend_pc_now() -> None:
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-WindowStyle",
            "Hidden",
            "-Command",
            "Start-Sleep -Milliseconds 600; Add-Type -AssemblyName System.Windows.Forms; "
            "[System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)",
        ],
        creationflags=0x00000008 | CREATE_NO_WINDOW,
    )


def is_autostart_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_REG_KEY, 0, winreg.KEY_READ) as k:
            val, _ = winreg.QueryValueEx(k, RUN_REG_NAME)
            return bool(val)
    except Exception:
        return False


def set_autostart_enabled(enable: bool) -> None:
    import winreg
    pythonw_exe = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw_exe.exists():
        pythonw_exe = Path(sys.executable)
    script_path = Path(__file__).resolve()
    cmd_str = f'"{pythonw_exe}" "{script_path}" --minimized'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_REG_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enable:
            winreg.SetValueEx(k, RUN_REG_NAME, 0, winreg.REG_SZ, cmd_str)
        else:
            try:
                winreg.DeleteValue(k, RUN_REG_NAME)
            except FileNotFoundError:
                pass


class ModernInputDialog(ctk.CTkToplevel):
    """Diálogo modal con estética Windows 11 Dark para editar horarios o fechas."""

    def __init__(self, parent: ctk.CTk, title: str, subtitle: str, initial_value: str = "") -> None:
        super().__init__(parent)
        self.title(title)
        self.geometry("520x230")
        self.resizable(False, False)
        self.configure(fg_color=W11_BG)
        self.result: Optional[str] = None

        self.transient(parent)
        self.grab_set()
        self.after(20, lambda: apply_win11_dark_titlebar(self))

        # Centrar sobre la ventana principal
        px = parent.winfo_rootx() + (parent.winfo_width() - 520) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - 230) // 2
        self.geometry(f"+{max(px, 100)}+{max(py, 100)}")

        card = ctk.CTkFrame(self, fg_color=W11_SURFACE, corner_radius=10, border_width=1, border_color=W11_BORDER)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            card,
            text=subtitle,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=W11_TEXT,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=18, pady=(16, 10))

        self.entry = ctk.CTkEntry(
            card,
            height=36,
            fg_color="#161616",
            border_color="#3D3D3D",
            text_color=W11_TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=13),
        )
        self.entry.pack(fill="x", padx=18, pady=(0, 16))
        self.entry.insert(0, initial_value)
        self.entry.focus_set()
        self.entry.bind("<Return>", lambda e: self._on_ok())
        self.entry.bind("<Escape>", lambda e: self.destroy())

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=18, pady=(0, 14))

        ctk.CTkButton(
            btn_row,
            text="Cancelar",
            width=100,
            height=32,
            corner_radius=6,
            fg_color=W11_BTN,
            hover_color=W11_BTN_HOVER,
            border_width=1,
            border_color=W11_BTN_BORDER,
            text_color=W11_TEXT,
            command=self.destroy,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            btn_row,
            text="Guardar cambios",
            width=130,
            height=32,
            corner_radius=6,
            fg_color=W11_ACCENT,
            hover_color=W11_ACCENT_HOVER,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=12),
            command=self._on_ok,
        ).pack(side="right")

        self.wait_window(self)

    def _on_ok(self) -> None:
        self.result = self.entry.get().strip()
        self.destroy()


class WakeupManagerApp:
    def __init__(self, start_minimized: bool = False) -> None:
        self.root = ctk.CTk()
        self.root.title("CreadorStudio — Control de Wakeups y Procesos")
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        win_w, win_h = 1120, 680
        pos_x = max(50, (screen_w - win_w) // 2)
        pos_y = max(50, (screen_h - win_h) // 2)
        self.root.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
        self.root.minsize(980, 560)
        self.root.configure(fg_color=W11_BG)

        self.icon_pil = create_tray_icon_image(64)
        try:
            from PIL import ImageTk
            self.tk_icon = ImageTk.PhotoImage(self.icon_pil)
            self.root.iconphoto(True, self.tk_icon)
        except Exception:
            pass

        self.root.after(30, lambda: apply_win11_dark_titlebar(self.root))
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        if not start_minimized:
            self.root.attributes("-topmost", True)
            self.root.after(600, lambda: self.root.attributes("-topmost", False))

        self._tasks_cache: List[Dict[str, Any]] = []
        self._queue_cache: Dict[str, Dict[str, Any]] = {}
        self.current_queue_filter = "PENDING"

        self._build_ui()

        self.tray_icon: Optional[pystray.Icon] = None
        self._start_tray_icon()

        self._running = True
        threading.Thread(target=self._signal_watcher_loop, daemon=True).start()

        self.root.after(150, self.refresh_all_async)
        if start_minimized:
            self.root.withdraw()

    # ------------------------------------------------------------------
    # CONSTRUCCIÓN DE INTERFAZ WINDOWS 11 FLUENT DARK
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        # Header superior minimalista estilo Configuración de Windows 11
        header = ctk.CTkFrame(self.root, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(18, 12))

        title_col = ctk.CTkFrame(header, fg_color="transparent")
        title_col.pack(side="left")

        ctk.CTkLabel(
            title_col,
            text="Control de Wakeups y Procesos",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=22),
            text_color=W11_TEXT,
            anchor="w",
        ).pack(anchor="w")

        self.status_lbl = ctk.CTkLabel(
            title_col,
            text="Sincronizando estado del sistema...",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=W11_SUBTEXT,
            anchor="w",
        )
        self.status_lbl.pack(anchor="w", pady=(2, 0))

        actions_col = ctk.CTkFrame(header, fg_color="transparent")
        actions_col.pack(side="right")

        ctk.CTkButton(
            actions_col,
            text="Actualizar",
            width=105,
            height=34,
            corner_radius=6,
            fg_color=W11_BTN,
            hover_color=W11_BTN_HOVER,
            border_width=1,
            border_color=W11_BTN_BORDER,
            text_color=W11_TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            command=self.refresh_all_async,
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            actions_col,
            text="Minimizar al reloj",
            width=130,
            height=34,
            corner_radius=6,
            fg_color=W11_BTN,
            hover_color=W11_BTN_HOVER,
            border_width=1,
            border_color=W11_BTN_BORDER,
            text_color=W11_TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            command=self.hide_to_tray,
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            actions_col,
            text="🌙  Suspender PC",
            width=145,
            height=34,
            corner_radius=6,
            fg_color=W11_ACCENT,
            hover_color=W11_ACCENT_HOVER,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=12),
            command=self.on_suspend_clicked,
        ).pack(side="left", padx=(5, 0))

        # Barra de navegación segmentada estilo Windows 11
        nav_row = ctk.CTkFrame(self.root, fg_color="transparent")
        nav_row.pack(fill="x", padx=24, pady=(0, 12))

        self.seg_nav = ctk.CTkSegmentedButton(
            nav_row,
            values=[
                "  ⏰  Wakeups y Tareas Programadas  ",
                "  📋  Cola de Publicaciones por Hora  ",
                "  🔋  Historial de Energía y Sistema  ",
            ],
            height=36,
            corner_radius=8,
            fg_color="#212121",
            selected_color="#323232",
            selected_hover_color="#3A3A3A",
            unselected_color="#212121",
            unselected_hover_color="#292929",
            text_color=W11_TEXT,
            font=ctk.CTkFont(family="Segoe UI Semibold", size=12),
            command=self._on_tab_changed,
        )
        self.seg_nav.pack(side="left")
        self.seg_nav.set("  ⏰  Wakeups y Tareas Programadas  ")

        # Contenedor de vistas
        self.body = ctk.CTkFrame(self.root, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=24, pady=(0, 18))

        self.view_tasks = ctk.CTkFrame(self.body, fg_color="transparent")
        self.view_queue = ctk.CTkFrame(self.body, fg_color="transparent")
        self.view_power = ctk.CTkFrame(self.body, fg_color="transparent")

        self._build_view_tasks()
        self._build_view_queue()
        self._build_view_power()

        self.view_tasks.pack(fill="both", expand=True)

    def _on_tab_changed(self, value: str) -> None:
        self.view_tasks.pack_forget()
        self.view_queue.pack_forget()
        self.view_power.pack_forget()
        if "Wakeups" in value:
            self.view_tasks.pack(fill="both", expand=True)
        elif "Cola" in value:
            self.view_queue.pack(fill="both", expand=True)
        else:
            self.view_power.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # VISTA 1: TARJETAS FLUENT DE WAKEUPS Y TAREAS
    # ------------------------------------------------------------------
    def _build_view_tasks(self) -> None:
        top_bar = ctk.CTkFrame(self.view_tasks, fg_color="transparent")
        top_bar.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            top_bar,
            text="Administra qué procesos tienen permiso para encender la PC desde suspensión (WakeToRun) y edita sus horarios con 1 clic.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=W11_SUBTEXT,
        ).pack(side="left")

        ctk.CTkButton(
            top_bar,
            text="+ Nueva tarea wakeup",
            width=155,
            height=30,
            corner_radius=6,
            fg_color=W11_BTN,
            hover_color=W11_BTN_HOVER,
            border_width=1,
            border_color=W11_BTN_BORDER,
            text_color=W11_TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            command=self.create_new_wakeup_task,
        ).pack(side="right")

        self.tasks_scroll = ctk.CTkScrollableFrame(
            self.view_tasks,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color="#333333",
            scrollbar_button_hover_color="#454545",
        )
        self.tasks_scroll.pack(fill="both", expand=True)

    def _render_task_cards(self, tasks_data: List[Dict[str, Any]]) -> None:
        for child in self.tasks_scroll.winfo_children():
            child.destroy()

        if not tasks_data:
            ctk.CTkLabel(
                self.tasks_scroll,
                text="No se encontraron tareas programadas.",
                text_color=W11_SUBTEXT,
            ).pack(pady=30)
            return

        for t in tasks_data:
            tname = t["TaskName"]
            is_wake = bool(t.get("WakeToRun"))
            state_raw = str(t.get("State", "Ready"))
            is_enabled = state_raw != "Disabled"
            next_run = t.get("NextRunTime") or "Sin programar"
            last_run = t.get("LastRunTime") or "—"
            last_res = t.get("LastTaskResult", "0")
            triggers = t.get("TriggersSummary") or "Sin disparadores"
            action_str = t.get("ActionSummary") or ""

            card = ctk.CTkFrame(
                self.tasks_scroll,
                fg_color=W11_SURFACE,
                corner_radius=8,
                border_width=1,
                border_color=W11_BORDER,
            )
            card.pack(fill="x", pady=5, padx=2)

            # Columna izquierda: información de la tarea
            left = ctk.CTkFrame(card, fg_color="transparent")
            left.pack(side="left", fill="both", expand=True, padx=16, pady=12)

            title_row = ctk.CTkFrame(left, fg_color="transparent")
            title_row.pack(fill="x")

            dot_color = W11_GREEN if is_enabled else "#757575"
            ctk.CTkLabel(
                title_row,
                text="●",
                font=ctk.CTkFont(size=12),
                text_color=dot_color,
            ).pack(side="left", padx=(0, 8))

            ctk.CTkLabel(
                title_row,
                text=tname,
                font=ctk.CTkFont(family="Segoe UI Semibold", size=14),
                text_color=W11_TEXT,
            ).pack(side="left")

            badge_bg = "#1E3A2F" if (is_wake and is_enabled) else "#2B2B2B"
            badge_fg = "#6CCB5F" if (is_wake and is_enabled) else W11_SUBTEXT
            badge_txt = "⚡ Despierta la PC" if is_wake else "💤 No despierta la PC"
            badge = ctk.CTkLabel(
                title_row,
                text=f"  {badge_txt}  ",
                fg_color=badge_bg,
                text_color=badge_fg,
                corner_radius=4,
                font=ctk.CTkFont(family="Segoe UI Semibold", size=11),
            )
            badge.pack(side="left", padx=12)

            ctk.CTkLabel(
                left,
                text=f"🕒 Horarios: {triggers}",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color="#D0D0D0",
                anchor="w",
            ).pack(fill="x", pady=(4, 1))

            ctk.CTkLabel(
                left,
                text=f"⏭ Próxima ejecución: {next_run}    •    ⏮ Última: {last_run} (Código {last_res})",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=W11_SUBTEXT,
                anchor="w",
            ).pack(fill="x")

            short_act = action_str if len(action_str) <= 105 else action_str[:102] + "..."
            ctk.CTkLabel(
                left,
                text=f"⚙️ Proceso: {short_act}",
                font=ctk.CTkFont(family="Consolas", size=11),
                text_color="#808080",
                anchor="w",
            ).pack(fill="x", pady=(2, 0))

            # Columna derecha: Switches estilo Windows 11 y botones de acción
            right = ctk.CTkFrame(card, fg_color="transparent")
            right.pack(side="right", padx=16, pady=12)

            switches_row = ctk.CTkFrame(right, fg_color="transparent")
            switches_row.pack(anchor="e", pady=(0, 8))

            sw_wake = ctk.CTkSwitch(
                switches_row,
                text="WakeToRun",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=W11_TEXT,
                progress_color=W11_ACCENT,
                button_color="#FFFFFF",
                fg_color="#3A3A3A",
                width=42,
            )
            if is_wake:
                sw_wake.select()
            sw_wake.configure(command=lambda name=tname, cur=is_wake: self.toggle_task_wake(name, cur))
            sw_wake.pack(side="left", padx=(0, 14))

            sw_en = ctk.CTkSwitch(
                switches_row,
                text="Activa",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=W11_TEXT,
                progress_color=W11_ACCENT,
                button_color="#FFFFFF",
                fg_color="#3A3A3A",
                width=42,
            )
            if is_enabled:
                sw_en.select()
            sw_en.configure(command=lambda name=tname, en=is_enabled: self.toggle_task_enabled(name, en))
            sw_en.pack(side="left")

            btns_row = ctk.CTkFrame(right, fg_color="transparent")
            btns_row.pack(anchor="e")

            ctk.CTkButton(
                btns_row,
                text="Horarios",
                width=82,
                height=28,
                corner_radius=6,
                fg_color=W11_BTN,
                hover_color=W11_BTN_HOVER,
                border_width=1,
                border_color=W11_BTN_BORDER,
                text_color=W11_TEXT,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                command=lambda name=tname, tr=triggers: self.edit_task_triggers(name, tr),
            ).pack(side="left", padx=3)

            ctk.CTkButton(
                btns_row,
                text="Ejecutar ahora",
                width=105,
                height=28,
                corner_radius=6,
                fg_color=W11_BTN,
                hover_color=W11_BTN_HOVER,
                border_width=1,
                border_color=W11_BTN_BORDER,
                text_color=W11_TEXT,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                command=lambda name=tname: self.run_selected_task_now(name),
            ).pack(side="left", padx=3)

            ctk.CTkButton(
                btns_row,
                text="Eliminar",
                width=74,
                height=28,
                corner_radius=6,
                fg_color=W11_BTN,
                hover_color=W11_DANGER_HOVER,
                border_width=1,
                border_color=W11_BTN_BORDER,
                text_color=W11_DANGER_TEXT,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                command=lambda name=tname: self.delete_selected_task(name),
            ).pack(side="left", padx=(3, 0))

    # ------------------------------------------------------------------
    # VISTA 2: COLA DE PUBLICACIONES Y PROCESOS POR HORA
    # ------------------------------------------------------------------
    def _build_view_queue(self) -> None:
        top_bar = ctk.CTkFrame(self.view_queue, fg_color="transparent")
        top_bar.pack(fill="x", pady=(0, 10))

        self.seg_filter = ctk.CTkSegmentedButton(
            top_bar,
            values=["Pendientes", "Todos", "Publicados", "Pausados / Fallidos"],
            height=32,
            corner_radius=6,
            fg_color="#212121",
            selected_color="#323232",
            selected_hover_color="#3A3A3A",
            unselected_color="#212121",
            unselected_hover_color="#292929",
            text_color=W11_TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            command=self._on_queue_filter_changed,
        )
        self.seg_filter.pack(side="left")
        self.seg_filter.set("Pendientes")

        self.queue_count_lbl = ctk.CTkLabel(
            top_bar,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=W11_SUBTEXT,
        )
        self.queue_count_lbl.pack(side="right")

        self.queue_scroll = ctk.CTkScrollableFrame(
            self.view_queue,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color="#333333",
            scrollbar_button_hover_color="#454545",
        )
        self.queue_scroll.pack(fill="both", expand=True)

    def _on_queue_filter_changed(self, val: str) -> None:
        mapping = {
            "Pendientes": "PENDING",
            "Todos": "ALL",
            "Publicados": "PUBLISHED",
            "Pausados / Fallidos": "OTHER",
        }
        self.current_queue_filter = mapping.get(val, "PENDING")
        self.refresh_queue_table()

    def refresh_queue_table(self) -> None:
        all_rows = self._load_all_queues()
        self._queue_cache = {r["uid"]: r for r in all_rows}
        flt = self.current_queue_filter

        for child in self.queue_scroll.winfo_children():
            child.destroy()

        filtered: List[Dict[str, Any]] = []
        for r in all_rows:
            st = r["status"]
            if flt == "PENDING" and st != "PENDING":
                continue
            if flt == "PUBLISHED" and st != "PUBLISHED":
                continue
            if flt == "OTHER" and st in ("PENDING", "PUBLISHED"):
                continue
            filtered.append(r)

        pending_total = sum(1 for r in all_rows if r["status"] == "PENDING")
        self.queue_count_lbl.configure(
            text=f"Mostrando {len(filtered)} elementos   •   Total pendientes en cola: {pending_total}"
        )

        if not filtered:
            ctk.CTkLabel(
                self.queue_scroll,
                text="No hay procesos en esta vista.",
                text_color=W11_SUBTEXT,
                font=ctk.CTkFont(family="Segoe UI", size=13),
            ).pack(pady=40)
            return

        for r in filtered:
            uid = r["uid"]
            st = r["status"]
            card = ctk.CTkFrame(
                self.queue_scroll,
                fg_color=W11_SURFACE,
                corner_radius=8,
                border_width=1,
                border_color=W11_BORDER,
            )
            card.pack(fill="x", pady=4, padx=2)

            left = ctk.CTkFrame(card, fg_color="transparent")
            left.pack(side="left", fill="both", expand=True, padx=14, pady=10)

            top_line = ctk.CTkFrame(left, fg_color="transparent")
            top_line.pack(fill="x")

            # Badge de Horario RD
            ctk.CTkLabel(
                top_line,
                text=f"  🕒 {r['sched_ast']}  ",
                fg_color="#2B2B2B",
                text_color=W11_CYAN,
                corner_radius=4,
                font=ctk.CTkFont(family="Segoe UI Semibold", size=12),
            ).pack(side="left", padx=(0, 8))

            # Badge Plataforma + Cuenta
            ctk.CTkLabel(
                top_line,
                text=f"{r['platform']}  •  {r['account']}",
                font=ctk.CTkFont(family="Segoe UI Semibold", size=13),
                text_color=W11_TEXT,
            ).pack(side="left", padx=(0, 10))

            st_color = W11_GREEN if st == "PUBLISHED" else ("#60CDFF" if st == "PENDING" else "#FCE100")
            ctk.CTkLabel(
                top_line,
                text=f"● {st}",
                font=ctk.CTkFont(family="Segoe UI Semibold", size=11),
                text_color=st_color,
            ).pack(side="left")

            ctk.CTkLabel(
                left,
                text=f"🎬 {r['video_name']}   ({r['project']})",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=W11_SUBTEXT,
                anchor="w",
            ).pack(fill="x", pady=(4, 0))

            right = ctk.CTkFrame(card, fg_color="transparent")
            right.pack(side="right", padx=14, pady=10)

            ctk.CTkButton(
                right,
                text="Cambiar hora",
                width=96,
                height=28,
                corner_radius=6,
                fg_color=W11_BTN,
                hover_color=W11_BTN_HOVER,
                border_width=1,
                border_color=W11_BTN_BORDER,
                text_color=W11_TEXT,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                command=lambda u=uid: self.edit_queue_item_time(u),
            ).pack(side="left", padx=3)

            pause_lbl = "Pausar" if st == "PENDING" else "Reactivar"
            ctk.CTkButton(
                right,
                text=pause_lbl,
                width=78,
                height=28,
                corner_radius=6,
                fg_color=W11_BTN,
                hover_color=W11_BTN_HOVER,
                border_width=1,
                border_color=W11_BTN_BORDER,
                text_color=W11_TEXT,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                command=lambda u=uid: self.toggle_queue_item_pause(u),
            ).pack(side="left", padx=3)

            ctk.CTkButton(
                right,
                text="Ver video",
                width=78,
                height=28,
                corner_radius=6,
                fg_color=W11_BTN,
                hover_color=W11_BTN_HOVER,
                border_width=1,
                border_color=W11_BTN_BORDER,
                text_color=W11_TEXT,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                command=lambda u=uid: self.open_selected_video(u),
            ).pack(side="left", padx=3)

            ctk.CTkButton(
                right,
                text="Eliminar",
                width=72,
                height=28,
                corner_radius=6,
                fg_color=W11_BTN,
                hover_color=W11_DANGER_HOVER,
                border_width=1,
                border_color=W11_BTN_BORDER,
                text_color=W11_DANGER_TEXT,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                command=lambda u=uid: self.delete_selected_queue_items(u),
            ).pack(side="left", padx=(3, 0))

    # ------------------------------------------------------------------
    # VISTA 3: HISTORIAL DE ENERGÍA Y CONFIGURACIÓN
    # ------------------------------------------------------------------
    def _build_view_power(self) -> None:
        cfg_card = ctk.CTkFrame(
            self.view_power,
            fg_color=W11_SURFACE,
            corner_radius=8,
            border_width=1,
            border_color=W11_BORDER,
        )
        cfg_card.pack(fill="x", pady=(0, 12))

        row1 = ctk.CTkFrame(cfg_card, fg_color="transparent")
        row1.pack(fill="x", padx=16, pady=(12, 6))

        ctk.CTkLabel(
            row1,
            text="Iniciar automáticamente al encender Windows (minimizada junto al reloj)",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=13),
            text_color=W11_TEXT,
        ).pack(side="left")

        self.sw_autostart = ctk.CTkSwitch(
            row1,
            text="",
            progress_color=W11_ACCENT,
            button_color="#FFFFFF",
            fg_color="#3A3A3A",
            width=44,
            command=self.on_toggle_autostart,
        )
        if is_autostart_enabled():
            self.sw_autostart.select()
        self.sw_autostart.pack(side="right")

        self.power_state_lbl = ctk.CTkLabel(
            cfg_card,
            text="Verificando banderas de energía de Windows...",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=W11_SUBTEXT,
            anchor="w",
        )
        self.power_state_lbl.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkLabel(
            self.view_power,
            text="Historial reciente de suspensiones y despertares (Windows Event Log)",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=13),
            text_color=W11_TEXT,
            anchor="w",
        ).pack(fill="x", pady=(0, 6))

        self.events_scroll = ctk.CTkScrollableFrame(
            self.view_power,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color="#333333",
            scrollbar_button_hover_color="#454545",
        )
        self.events_scroll.pack(fill="both", expand=True)

    def _render_power_events(self, events_data: List[Dict[str, str]]) -> None:
        for child in self.events_scroll.winfo_children():
            child.destroy()

        for ev in events_data:
            row = ctk.CTkFrame(
                self.events_scroll,
                fg_color=W11_SURFACE,
                corner_radius=6,
                border_width=1,
                border_color=W11_BORDER,
            )
            row.pack(fill="x", pady=3, padx=2)

            ctk.CTkLabel(
                row,
                text=ev["time"],
                width=165,
                font=ctk.CTkFont(family="Consolas", size=12),
                text_color=W11_SUBTEXT,
                anchor="w",
            ).pack(side="left", padx=(12, 8), pady=8)

            t_color = W11_CYAN if "Despertar" in ev["type"] else (W11_AMBER if "Suspensión" in ev["type"] else W11_TEXT)
            ctk.CTkLabel(
                row,
                text=ev["type"],
                width=190,
                font=ctk.CTkFont(family="Segoe UI Semibold", size=12),
                text_color=t_color,
                anchor="w",
            ).pack(side="left", padx=8, pady=8)

            ctk.CTkLabel(
                row,
                text=ev["details"],
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=W11_TEXT,
                anchor="w",
                justify="left",
            ).pack(side="left", fill="x", expand=True, padx=8, pady=8)

    # ------------------------------------------------------------------
    # SYSTEM TRAY (JUNTO AL RELOJ)
    # ------------------------------------------------------------------
    def _start_tray_icon(self) -> None:
        menu = pystray.Menu(
            pystray.MenuItem("🖥️ Abrir Panel de Control", self.show_from_tray, default=True),
            pystray.MenuItem("🔄 Actualizar Estado", lambda icon, item: self.root.after(0, self.refresh_all_async)),
            pystray.MenuItem("🌙 Suspender PC Ahora (Wake Activo)", lambda icon, item: suspend_pc_now()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌ Cerrar por completo", self.quit_app),
        )
        self.tray_icon = pystray.Icon(
            "AutoClipper_Wakeup_Tray",
            self.icon_pil,
            "CreadorStudio — Control de Wakeups y Procesos",
            menu,
        )
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def hide_to_tray(self) -> None:
        self.root.withdraw()

    def show_from_tray(self, icon: Any = None, item: Any = None) -> None:
        self.root.after(0, self._restore_window)

    def _restore_window(self) -> None:
        self.root.deiconify()
        self.root.state("normal")
        self.root.attributes("-topmost", True)
        self.root.lift()
        self.root.focus_force()
        self.root.after(20, lambda: apply_win11_dark_titlebar(self.root))
        self.root.after(500, lambda: self.root.attributes("-topmost", False))
        self.refresh_all_async()

    def quit_app(self, icon: Any = None, item: Any = None) -> None:
        self._running = False
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.root.after(0, self.root.destroy)

    def _ensure_chrome_migrated_profiles(self) -> None:
        try:
            cache_file = BASE_DIR / "processing" / "chrome_migrated_info_cache.json"
            local_app = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
            local_state_file = local_app / "Google" / "Chrome" / "User Data" / "Local State"
            if not cache_file.exists() or not local_state_file.exists():
                return
            ls = json.loads(local_state_file.read_text(encoding="utf-8"))
            prof = ls.setdefault("profile", {})
            ic = prof.setdefault("info_cache", {})
            migrated = json.loads(cache_file.read_text(encoding="utf-8"))
            changed = False
            for k, v in migrated.items():
                if k not in ic:
                    ic[k] = v
                    changed = True
            order = prof.setdefault("profiles_order", ["Default", "Profile 3"])
            for k in migrated:
                if k not in order:
                    order.append(k)
                    changed = True
            if changed:
                local_state_file.write_text(json.dumps(ls, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _signal_watcher_loop(self) -> None:
        while self._running:
            try:
                if SIGNAL_FILE.exists():
                    cmd = SIGNAL_FILE.read_text(encoding="utf-8").strip()
                    SIGNAL_FILE.unlink(missing_ok=True)
                    if cmd == "REFRESH":
                        self.root.after(0, self.refresh_all_async)
                    else:
                        self.root.after(0, self._restore_window)
            except Exception:
                pass
            time.sleep(0.8)

    # ------------------------------------------------------------------
    # LÓGICA DE DATOS Y ACCIONES
    # ------------------------------------------------------------------
    def refresh_all_async(self) -> None:
        self.status_lbl.configure(text="Actualizando tareas programadas, colas y eventos de energía...")
        threading.Thread(target=self._refresh_worker, daemon=True).start()

    def _refresh_worker(self) -> None:
        tasks_data = self._fetch_scheduled_tasks()
        events_data, pwr_summary = self._fetch_power_events()
        self.root.after(0, lambda: self._apply_refreshed_data(tasks_data, events_data, pwr_summary))

    def _apply_refreshed_data(
        self,
        tasks_data: List[Dict[str, Any]],
        events_data: List[Dict[str, str]],
        pwr_summary: str,
    ) -> None:
        self._tasks_cache = tasks_data
        self._render_task_cards(tasks_data)
        self.refresh_queue_table()
        self.power_state_lbl.configure(text=pwr_summary)
        self._render_power_events(events_data)

        wake_active_count = sum(1 for t in tasks_data if t.get("WakeToRun") and t.get("State") != "Disabled")
        now_str = datetime.now(AST_TZ).strftime("%I:%M:%S %p")
        self.status_lbl.configure(
            text=f"Actualizado a las {now_str}   •   Tareas con WakeToRun activo: {wake_active_count}   •   Al cerrar con [X] permanece junto al reloj"
        )

    def _fetch_scheduled_tasks(self) -> List[Dict[str, Any]]:
        ps_script = r"""
$tasks = Get-ScheduledTask | Where-Object {
    $_.TaskName -like '*AutoClipper*' -or
    $_.TaskName -like '*ShortYT*' -or
    ($_.Settings.WakeToRun -eq $true -and $_.State -ne 'Disabled')
}
$out = @()
foreach ($t in $tasks) {
    $info = $t | Get-ScheduledTaskInfo -ErrorAction SilentlyContinue
    $trigList = @()
    foreach ($tr in $t.Triggers) {
        if ($tr.Enabled -eq $false) { continue }
        $sb = [string]$tr.StartBoundary
        $timePart = if ($sb -match 'T(\d{2}:\d{2})') { $matches[1] } else { $sb }
        if ($tr.Repetition -and $tr.Repetition.Interval) {
            $trigList += "$timePart (Cada $($tr.Repetition.Interval))"
        } else {
            $trigList += $timePart
        }
    }
    $act = ($t.Actions | ForEach-Object { "$($_.Execute) $($_.Arguments)" }) -join '; '
    $out += [PSCustomObject]@{
        TaskName = $t.TaskName
        TaskPath = $t.TaskPath
        State = [string]$t.State
        WakeToRun = [bool]$t.Settings.WakeToRun
        NextRunTime = if ($info.NextRunTime) { $info.NextRunTime.ToString('dd/MM/yyyy hh:mm tt') } else { '' }
        LastRunTime = if ($info.LastRunTime) { $info.LastRunTime.ToString('dd/MM/yyyy hh:mm tt') } else { '' }
        LastTaskResult = [string]$info.LastTaskResult
        TriggersSummary = ($trigList -join ', ')
        ActionSummary = $act
    }
}
$out | ConvertTo-Json -Depth 3 -Compress
"""
        raw = run_ps(ps_script)
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            return [parsed] if isinstance(parsed, dict) else parsed
        except Exception:
            return []

    def _fetch_power_events(self) -> tuple[List[Dict[str, str]], str]:
        es_flag = 0
        try:
            from ctypes import wintypes
            state = wintypes.ULONG()
            ctypes.windll.powrprof.CallNtPowerInformation(16, None, 0, ctypes.byref(state), ctypes.sizeof(state))
            es_flag = state.value
        except Exception:
            pass

        if es_flag & 0x1:
            pwr_summary = (
                "⚡ Bandera de sistema: Hay una aplicación en 2do plano con ES_SYSTEM_REQUIRED (0x1). "
                "Nuestro Auto-Sleep inteligente volverá a suspender la PC automáticamente cuando despierte sola."
            )
        else:
            pwr_summary = "🟢 Bandera de sistema: Libre de bloqueos de energía (0x0). Reposo automático operando con normalidad."

        ps_ev = r"""
$evs = @()
$wakes = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-Power-Troubleshooter'} -MaxEvents 8 -ErrorAction SilentlyContinue
foreach ($w in $wakes) {
    $msg = ($w.Message -replace '\r\n', ' ' -replace '\s+', ' ')
    $evs += [PSCustomObject]@{
        SortTime = $w.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
        time = $w.TimeCreated.ToString('dd/MM/yyyy hh:mm:ss tt')
        type = '☀️ Despertar (Wakeup)'
        details = $msg
    }
}
$sleeps = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-Kernel-Power'; Id=42,566} -MaxEvents 12 -ErrorAction SilentlyContinue
foreach ($s in $sleeps) {
    $msg = ($s.Message -replace '\r\n', ' ' -replace '\s+', ' ')
    $tLabel = if ($s.Id -eq 42) { '🌙 Suspensión iniciada' } else { '🔄 Transición de sesión' }
    $evs += [PSCustomObject]@{
        SortTime = $s.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
        time = $s.TimeCreated.ToString('dd/MM/yyyy hh:mm:ss tt')
        type = $tLabel
        details = $msg
    }
}
$evs | Sort-Object SortTime -Descending | Select-Object -First 18 | ConvertTo-Json -Compress
"""
        raw = run_ps(ps_ev)
        events_list: List[Dict[str, str]] = []
        if raw:
            try:
                parsed = json.loads(raw)
                events_list = [parsed] if isinstance(parsed, dict) else parsed
            except Exception:
                pass
        return events_list, pwr_summary

    def toggle_task_wake(self, task_name: str, currently_wake: bool) -> None:
        new_wake = "$false" if currently_wake else "$true"
        cmd = (
            f"$t = Get-ScheduledTask -TaskName '{task_name}'; "
            f"$t.Settings.WakeToRun = {new_wake}; "
            f"Set-ScheduledTask -InputObject $t | Out-Null"
        )
        run_ps(cmd)
        self.refresh_all_async()

    def toggle_task_enabled(self, task_name: str, currently_enabled: bool) -> None:
        action_cmd = "Disable-ScheduledTask" if currently_enabled else "Enable-ScheduledTask"
        run_ps(f"{action_cmd} -TaskName '{task_name}' | Out-Null")
        self.refresh_all_async()

    def run_selected_task_now(self, task_name: str) -> None:
        run_ps(f"Start-ScheduledTask -TaskName '{task_name}'")
        self.refresh_all_async()

    def edit_task_triggers(self, task_name: str, current_triggers: str) -> None:
        init_val = current_triggers if "Cada" not in current_triggers else "09:01, 12:01, 15:01, 18:01, 20:01, 22:01"
        dlg = ModernInputDialog(
            self.root,
            title=f"Horarios — {task_name}",
            subtitle=f"Ingresa las horas diarias (formato 24h HH:MM) separadas por coma para '{task_name}':",
            initial_value=init_val,
        )
        if not dlg.result:
            return
        valid_re = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
        raw_times = [h.strip() for h in dlg.result.split(",") if h.strip()]
        times = [h for h in raw_times if valid_re.match(h)]
        if not times:
            messagebox.showerror("Formato inválido", "Ingresa al menos una hora válida en formato 24h HH:MM (ej. 09:00, 14:00).")
            return
        trig_ps = "; ".join([f"New-ScheduledTaskTrigger -Daily -At '{t}'" for t in times])
        ps_cmd = (
            f"$trigs = @({trig_ps}); "
            f"Set-ScheduledTask -TaskName '{task_name}' -Trigger $trigs | Out-Null"
        )
        run_ps(ps_cmd)
        self.refresh_all_async()

    def create_new_wakeup_task(self) -> None:
        win = ctk.CTkToplevel(self.root)
        win.title("Nueva tarea de Wakeup")
        win.geometry("540x380")
        win.resizable(False, False)
        win.configure(fg_color=W11_BG)
        win.transient(self.root)
        win.grab_set()
        win.after(20, lambda: apply_win11_dark_titlebar(win))

        card = ctk.CTkFrame(win, fg_color=W11_SURFACE, corner_radius=10, border_width=1, border_color=W11_BORDER)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        def _add_field(label_txt: str, default_val: str = "") -> ctk.CTkEntry:
            ctk.CTkLabel(card, text=label_txt, font=ctk.CTkFont(family="Segoe UI", size=12), text_color=W11_TEXT).pack(
                anchor="w", padx=16, pady=(10, 2)
            )
            e = ctk.CTkEntry(card, height=32, fg_color="#161616", border_color="#3D3D3D", text_color=W11_TEXT)
            e.pack(fill="x", padx=16)
            if default_val:
                e.insert(0, default_val)
            return e

        ent_name = _add_field("Nombre de la tarea (sin espacios):", "MiTarea_Wakeup")
        ent_times = _add_field("Horarios diarios 24h separados por coma:", "09:01, 12:01, 18:01")
        default_pyw = str(Path(sys.executable).with_name("pythonw.exe") if Path(sys.executable).with_name("pythonw.exe").exists() else Path(sys.executable))
        ent_exe = _add_field("Ejecutable:", default_pyw)
        ent_args = _add_field("Argumentos / ruta del script:", "")

        sw_wake = ctk.CTkSwitch(
            card,
            text="Despertar la PC automáticamente (WakeToRun)",
            progress_color=W11_ACCENT,
            fg_color="#3A3A3A",
        )
        sw_wake.select()
        sw_wake.pack(anchor="w", padx=16, pady=12)

        def _save() -> None:
            tname = ent_name.get().strip().replace(" ", "_")
            valid_re = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
            raw_times = [x.strip() for x in ent_times.get().split(",") if x.strip()]
            times = [x for x in raw_times if valid_re.match(x)]
            exe = ent_exe.get().strip()
            args = ent_args.get().strip()
            if not tname or not times or not exe:
                messagebox.showerror("Error", "Completa el nombre, ejecutable y al menos una hora válida HH:MM.")
                return
            trig_ps = "; ".join([f"New-ScheduledTaskTrigger -Daily -At '{t}'" for t in times])
            wake_flag = "$true" if sw_wake.get() else "$false"
            arg_part = f"-Argument '{args}'" if args else ""
            ps_cmd = (
                f"$act = New-ScheduledTaskAction -Execute '{exe}' {arg_part}; "
                f"$trigs = @({trig_ps}); "
                f"$set = New-ScheduledTaskSettingsSet -WakeToRun:{wake_flag} -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries; "
                f"Register-ScheduledTask -TaskName '{tname}' -Action $act -Trigger $trigs -Settings $set -Force | Out-Null"
            )
            run_ps(ps_cmd)
            win.destroy()
            self.refresh_all_async()

        ctk.CTkButton(
            card,
            text="Crear tarea",
            height=32,
            corner_radius=6,
            fg_color=W11_ACCENT,
            hover_color=W11_ACCENT_HOVER,
            command=_save,
        ).pack(anchor="e", padx=16, pady=(4, 12))

    def delete_selected_task(self, task_name: str) -> None:
        if not messagebox.askyesno("Eliminar tarea", f"¿Seguro que deseas eliminar la tarea '{task_name}'?"):
            return
        run_ps(f"Unregister-ScheduledTask -TaskName '{task_name}' -Confirm:$false")
        self.refresh_all_async()

    # ------------------------------------------------------------------
    # COLA SQLITE
    # ------------------------------------------------------------------
    def _load_all_queues(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        dbs = [("Auto-Clipper", SHORT_YT_DB)]
        for proj_name, db_path in dbs:
            if not db_path.exists():
                continue
            try:
                with sqlite3.connect(str(db_path)) as conn:
                    conn.row_factory = sqlite3.Row
                    cur = conn.cursor()
                    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                    if "tiktok_scheduled_queue" in tables:
                        for r in cur.execute("SELECT * FROM tiktok_scheduled_queue ORDER BY scheduled_time_utc ASC, id ASC"):
                            d = dict(r)
                            rows.append(
                                {
                                    "uid": f"{proj_name}:TT:{d['id']}",
                                    "db_id": d["id"],
                                    "db_path": str(db_path),
                                    "table": "tiktok_scheduled_queue",
                                    "project": proj_name,
                                    "platform": "TikTok",
                                    "account": f"@{d['account_key']}",
                                    "sched_utc": d["scheduled_time_utc"],
                                    "sched_ast": self._format_ast(d["scheduled_time_utc"], d.get("scheduled_time_ast", "")),
                                    "status": d["status"],
                                    "video_name": os.path.basename(d["video_path"]),
                                    "video_path": d["video_path"],
                                }
                            )
                    if "instagram_scheduled_queue" in tables:
                        for r in cur.execute("SELECT * FROM instagram_scheduled_queue ORDER BY scheduled_time_utc ASC, id ASC"):
                            d = dict(r)
                            rows.append(
                                {
                                    "uid": f"{proj_name}:IG:{d['id']}",
                                    "db_id": d["id"],
                                    "db_path": str(db_path),
                                    "table": "instagram_scheduled_queue",
                                    "project": proj_name,
                                    "platform": "Instagram + FB",
                                    "account": f"@{d['account_key']}",
                                    "sched_utc": d["scheduled_time_utc"],
                                    "sched_ast": self._format_ast(d["scheduled_time_utc"], d.get("scheduled_time_ast", "")),
                                    "status": d["status"],
                                    "video_name": os.path.basename(d["video_path"]),
                                    "video_path": d["video_path"],
                                }
                            )
            except Exception:
                pass
        rows.sort(key=lambda x: (x["sched_utc"], x["uid"]))
        return rows

    @staticmethod
    def _format_ast(utc_iso: str, fallback_ast: str) -> str:
        try:
            dt_utc = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
            dt_ast = dt_utc.astimezone(AST_TZ)
            return dt_ast.strftime("%Y-%m-%d %I:%M %p")
        except Exception:
            return fallback_ast or utc_iso

    def edit_queue_item_time(self, uid: str) -> None:
        item = self._queue_cache.get(uid)
        if not item:
            return
        dlg = ModernInputDialog(
            self.root,
            title="Cambiar fecha y hora programada",
            subtitle=f"Nueva fecha y hora (RD) para {item['account']} — {item['video_name']}\n(Formato: YYYY-MM-DD HH:MM AM/PM o 24h):",
            initial_value=item["sched_ast"],
        )
        if not dlg.result:
            return
        dt_ast = None
        for fmt in ("%Y-%m-%d %I:%M %p", "%Y-%m-%d %H:%M", "%Y-%m-%d %I:%M:%S %p", "%Y-%m-%d %H:%M:%S"):
            try:
                dt_ast = datetime.strptime(dlg.result.strip(), fmt).replace(tzinfo=AST_TZ)
                break
            except ValueError:
                continue
        if not dt_ast:
            messagebox.showerror("Formato inválido", "Usa el formato YYYY-MM-DD HH:MM AM/PM (ej. 2026-10-26 02:00 PM).")
            return
        utc_iso = dt_ast.astimezone(UTC_TZ).strftime("%Y-%m-%dT%H:%M:%SZ")
        ast_label = dt_ast.strftime("%Y-%m-%d %I:%M %p AST")
        with sqlite3.connect(item["db_path"]) as conn:
            conn.execute(
                f"UPDATE {item['table']} SET scheduled_time_utc = ?, scheduled_time_ast = ? WHERE id = ?",
                (utc_iso, ast_label, item["db_id"]),
            )
            conn.commit()
        self.refresh_queue_table()

    def toggle_queue_item_pause(self, uid: str) -> None:
        item = self._queue_cache.get(uid)
        if not item:
            return
        new_st = "PAUSED" if item["status"] == "PENDING" else "PENDING"
        with sqlite3.connect(item["db_path"]) as conn:
            conn.execute(f"UPDATE {item['table']} SET status = ? WHERE id = ?", (new_st, item["db_id"]))
            conn.commit()
        self.refresh_queue_table()

    def open_selected_video(self, uid: str) -> None:
        item = self._queue_cache.get(uid)
        if item and os.path.exists(item["video_path"]):
            os.startfile(item["video_path"])
        else:
            messagebox.showerror("Archivo no encontrado", "No se encontró el archivo de video en disco.")

    def delete_selected_queue_items(self, uid: str) -> None:
        item = self._queue_cache.get(uid)
        if not item:
            return
        if not messagebox.askyesno("Eliminar de la cola", f"¿Eliminar '{item['video_name']}' ({item['account']}) de la cola?"):
            return
        with sqlite3.connect(item["db_path"]) as conn:
            conn.execute(f"DELETE FROM {item['table']} WHERE id = ?", (item["db_id"],))
            conn.commit()
        self.refresh_queue_table()

    def on_toggle_autostart(self) -> None:
        enable = bool(self.sw_autostart.get())
        set_autostart_enabled(enable)

    def on_suspend_clicked(self) -> None:
        if messagebox.askyesno(
            "Suspender PC",
            "¿Suspender la PC ahora mismo en Modo S3 con los Wake Timers activos?",
        ):
            suspend_pc_now()

    def run(self) -> None:
        self.root.mainloop()


_MUTEX_HANDLE = None


def main() -> None:
    global _MUTEX_HANDLE
    mutex_name = "Local\\AutoClipper_Wakeup_Tray_App_v2"
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _MUTEX_HANDLE = k32.CreateMutexW(None, False, mutex_name)
    if ctypes.get_last_error() == 183:
        try:
            SIGNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
            SIGNAL_FILE.write_text("SHOW", encoding="utf-8")
        except Exception:
            pass
        sys.exit(0)

    if not is_autostart_enabled():
        try:
            set_autostart_enabled(True)
        except Exception:
            pass

    start_min = "--minimized" in sys.argv
    app = WakeupManagerApp(start_minimized=start_min)
    app.run()


if __name__ == "__main__":
    main()
