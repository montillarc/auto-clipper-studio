"""
Skill 3: strategic-time-calculator
Manages strategic publishing slots in America/Santo_Domingo (AST) backed by SQLite
(./config/schedule_state.db) and returns UTC ISO 8601 timestamps (YYYY-MM-DDTHH:MM:SSZ).
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

import pytz

logger = logging.getLogger("strategic-time-calculator")

SANTO_DOMINGO_TZ = pytz.timezone("America/Santo_Domingo")
UTC_TZ = pytz.UTC

# Strategic hourly windows in America/Santo_Domingo (AST) — 1 hour between each Short:
# From 09:00 AM to 11:00 PM AST (every 1 hour)
DAILY_SLOTS: List[Tuple[int, int]] = [
    (9, 0),
    (10, 0),
    (11, 0),
    (12, 0),
    (13, 0),
    (14, 0),
    (15, 0),
    (16, 0),
    (17, 0),
    (18, 0),
    (19, 0),
    (20, 0),
    (21, 0),
    (22, 0),
    (23, 0),
]
WEEKDAY_SLOTS: List[Tuple[int, int]] = DAILY_SLOTS
WEEKEND_SLOTS: List[Tuple[int, int]] = DAILY_SLOTS

DEFAULT_DB_PATH = Path("./config/schedule_state.db")


def init_db(db_path: str | Path = DEFAULT_DB_PATH) -> Path:
    """Initializes the SQLite database and schema if not already present."""
    db_file = Path(db_path).resolve()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduled_slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_name TEXT NOT NULL,
                slot_ast TEXT NOT NULL,
                publish_at_utc TEXT NOT NULL UNIQUE,
                youtube_video_id TEXT,
                created_at_utc TEXT NOT NULL
            )
            """
        )
        conn.commit()
    return db_file


def _slots_for_date_ast(target_date: datetime.date) -> List[datetime]:
    """Returns localized America/Santo_Domingo datetimes for all strategic windows on target_date."""
    is_weekend = target_date.weekday() in (5, 6)  # 5 = Saturday, 6 = Sunday
    hm_list = WEEKEND_SLOTS if is_weekend else WEEKDAY_SLOTS

    localized_slots: List[datetime] = []
    for hour, minute in hm_list:
        naive_dt = datetime.combine(target_date, time(hour=hour, minute=minute, second=0))
        localized_slots.append(SANTO_DOMINGO_TZ.localize(naive_dt))
    return localized_slots


def get_and_reserve_next_slot(
    video_name: str = "unnamed_short.mp4",
    db_path: str | Path = DEFAULT_DB_PATH,
    reference_now_utc: Optional[datetime] = None,
) -> str:
    """
    Queries ./config/schedule_state.db for the last assigned schedule slot,
    computes the next free strategic window in America/Santo_Domingo (AST),
    records the slot in SQLite to avoid duplicate schedules, and returns
    the UTC ISO 8601 timestamp ('YYYY-MM-DDTHH:MM:SSZ').
    """
    db_file = init_db(db_path)

    if reference_now_utc is None:
        now_utc = datetime.now(UTC_TZ)
    elif reference_now_utc.tzinfo is None:
        now_utc = UTC_TZ.localize(reference_now_utc)
    else:
        now_utc = reference_now_utc.astimezone(UTC_TZ)

    # Require at least 15 minutes buffer in the future so YouTube accepts publishAt
    min_valid_utc = now_utc + timedelta(minutes=15)

    with sqlite3.connect(str(db_file)) as conn:
        cursor = conn.cursor()

        # Evitar reservas duplicadas si el mismo video reintenta y ya tiene un slot futuro no usado
        cursor.execute(
            "SELECT publish_at_utc FROM scheduled_slots WHERE video_name = ? AND youtube_video_id IS NULL ORDER BY id DESC LIMIT 1",
            (video_name,),
        )
        existing_res = cursor.fetchone()
        if existing_res and existing_res[0]:
            ex_iso = existing_res[0]
            ex_clean = ex_iso[:-1] + "+00:00" if ex_iso.endswith("Z") else ex_iso
            try:
                ex_dt = datetime.fromisoformat(ex_clean).astimezone(UTC_TZ)
                if ex_dt > min_valid_utc:
                    logger.info(
                        "Reutilizando slot estratégico previamente reservado para '%s': %s (UTC)",
                        video_name,
                        ex_iso,
                    )
                    return ex_iso
            except Exception:
                pass

        cursor.execute(
            "SELECT publish_at_utc FROM scheduled_slots ORDER BY publish_at_utc DESC LIMIT 1"
        )
        row = cursor.fetchone()
        last_assigned_utc: Optional[datetime] = None
        if row and row[0]:
            last_str = row[0]
            if last_str.endswith("Z"):
                last_str = last_str[:-1] + "+00:00"
            last_assigned_utc = datetime.fromisoformat(last_str).astimezone(UTC_TZ)

        cursor.execute("SELECT publish_at_utc FROM scheduled_slots")
        reserved_utc_strings = {r[0] for r in cursor.fetchall()}

        # Determine search starting point in America/Santo_Domingo
        baseline_utc = min_valid_utc
        if last_assigned_utc and last_assigned_utc > baseline_utc:
            baseline_utc = last_assigned_utc

        baseline_ast = baseline_utc.astimezone(SANTO_DOMINGO_TZ)
        search_date = baseline_ast.date()

        chosen_slot_ast: Optional[datetime] = None
        chosen_utc_iso: Optional[str] = None

        # Search day by day until we find the next strictly free strategic window
        for day_offset in range(0, 365):
            candidate_date = search_date + timedelta(days=day_offset)
            for slot_ast in _slots_for_date_ast(candidate_date):
                slot_utc = slot_ast.astimezone(UTC_TZ)
                if slot_utc <= min_valid_utc:
                    continue
                if last_assigned_utc is not None and slot_utc <= last_assigned_utc:
                    continue
                iso_utc = slot_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
                if iso_utc not in reserved_utc_strings:
                    chosen_slot_ast = slot_ast
                    chosen_utc_iso = iso_utc
                    break
            if chosen_utc_iso:
                break

        if not chosen_utc_iso or not chosen_slot_ast:
            raise RuntimeError("No se encontró un slot estratégico disponible.")

        created_at_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        slot_ast_str = chosen_slot_ast.strftime("%Y-%m-%d %H:%M:%S %Z")

        cursor.execute(
            """
            INSERT INTO scheduled_slots (video_name, slot_ast, publish_at_utc, created_at_utc)
            VALUES (?, ?, ?, ?)
            """,
            (video_name, slot_ast_str, chosen_utc_iso, created_at_iso),
        )
        conn.commit()

    logger.info(
        "Slot estratégico reservado para '%s': %s (AST) -> %s (UTC)",
        video_name,
        slot_ast_str,
        chosen_utc_iso,
    )
    return chosen_utc_iso


def update_slot_youtube_id(
    publish_at_utc: str,
    youtube_video_id: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> None:
    """Updates the SQLite record with the uploaded YouTube video ID."""
    db_file = init_db(db_path)
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute(
            "UPDATE scheduled_slots SET youtube_video_id = ? WHERE publish_at_utc = ?",
            (youtube_video_id, publish_at_utc),
        )
        conn.commit()


def cancel_slot_reservation(
    publish_at_utc: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> None:
    """Libera una reserva de slot no utilizada si la subida o programación falló."""
    db_file = init_db(db_path)
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute(
            "DELETE FROM scheduled_slots WHERE publish_at_utc = ? AND youtube_video_id IS NULL",
            (publish_at_utc,),
        )
        conn.commit()
    logger.info("Reserva de slot liberada: %s", publish_at_utc)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Skill 3: Strategic Time Calculator")
    parser.add_argument("--video-name", default="cli_short.mp4", help="Nombre del video a programar")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="Ruta a schedule_state.db")
    args = parser.parse_args()

    utc_slot = get_and_reserve_next_slot(video_name=args.video_name, db_path=args.db_path)
    print(utc_slot)
