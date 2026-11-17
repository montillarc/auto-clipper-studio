"""
TDD Suite (Red -> Green -> Refactor) para el Backend de Short YT (api_server.py).
Prueba todos los endpoints reales y las funciones core sin mocks de la lógica de negocio.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

# Importación del servidor backend (Fallará en fase RED antes de crear api_server.py)
import api_server


@pytest.fixture()
def temp_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Configura un directorio de trabajo real aislado con un video MP4 real y SQLite real."""
    inbox_dir = tmp_path / "inbox_videos"
    processing_dir = tmp_path / "processing"
    output_dir = tmp_path / "output_shorts"
    archive_dir = tmp_path / "published_archive"
    config_dir = tmp_path / "config"

    for d in (inbox_dir, processing_dir, output_dir, archive_dir, config_dir):
        d.mkdir(parents=True, exist_ok=True)

    # Crear un video MP4 válido real con OpenCV (60 frames a 30 fps = 2.0 segundos, 640x360)
    sample_video = inbox_dir / "test_stream_x3.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(sample_video), fourcc, 30.0, (640, 360))
    for i in range(60):
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        frame[:, :] = (i * 3 % 255, 100, 180)
        writer.write(frame)
    writer.release()

    # Crear un Short renderizado real en output_shorts/test_stream/
    short_folder = output_dir / "test_stream"
    short_folder.mkdir(parents=True, exist_ok=True)
    rendered_short = short_folder / "test_stream_01_Oro_92pts.mp4"
    rendered_short.write_bytes(sample_video.read_bytes())

    rendered_short_2 = short_folder / "test_stream_02_Plata_80pts.mp4"
    rendered_short_2.write_bytes(sample_video.read_bytes())

    # Crear archivo temporal en processing para probar cleanup real
    temp_ass = processing_dir / "temp_subtitles.ass"
    temp_ass.write_text("ScriptInfo", encoding="utf-8")

    # Configurar rutas en api_server y módulos subyacentes
    monkeypatch.setattr(api_server, "BASE_DIR", tmp_path)
    monkeypatch.setattr(api_server, "INBOX_DIR", inbox_dir)
    monkeypatch.setattr(api_server, "PROCESSING_DIR", processing_dir)
    monkeypatch.setattr(api_server, "OUTPUT_SHORTS_DIR", output_dir)
    monkeypatch.setattr(api_server, "PUBLISHED_ARCHIVE_DIR", archive_dir)
    monkeypatch.setattr(api_server, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(api_server, "SETTINGS_PATH", config_dir / "settings.json")
    monkeypatch.setattr(api_server, "DB_PATH", config_dir / "schedule_state.db")
    monkeypatch.setattr(api_server.skill_tt_scheduler, "CONFIG_DIR", config_dir)
    if getattr(api_server, "skill_tt_wa", None) is not None:
        monkeypatch.setattr(api_server.skill_tt_wa, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(api_server.skill_tt_wa, "DB_PATH", config_dir / "schedule_state.db")

    # Inicializar base SQLite real
    db_file = config_dir / "schedule_state.db"
    api_server.skill_scheduler.init_db(db_file)
    api_server.skill_ig_scheduler.init_ig_queue_db(db_file)
    api_server.skill_tt_scheduler.init_tiktok_queue_db(db_file)

    # Reservar un slot real para test_stream_01_Oro_92pts.mp4
    api_server.skill_scheduler.get_and_reserve_next_slot(
        video_name="test_stream_01_Oro_92pts.mp4",
        db_path=db_file,
    )

    return tmp_path


@pytest.fixture()
def client(temp_workspace: Path) -> TestClient:
    return TestClient(api_server.app)


def test_get_inbox_returns_videos_disk_and_settings(client: TestClient) -> None:
    """GET /api/inbox devuelve status 200, lista real de videos en inbox_videos, reporte de disco y settings."""
    response = client.get("/api/inbox")
    assert response.status_code == 200
    data = response.json()

    assert "videos" in data
    assert len(data["videos"]) == 1
    assert data["videos"][0]["file_name"] == "test_stream_x3.mp4"
    assert data["videos"][0]["size_mb"] >= 0.0

    assert "disk_space" in data
    assert data["disk_space"]["total_gb"] > 0
    assert data["disk_space"]["free_gb"] > 0

    assert "settings" in data
    assert data["settings"]["shorts_per_video"] == 8


def test_post_inspect_valid_video_returns_metrics(client: TestClient) -> None:
    """POST /api/inspect analiza un video real con OpenCV y devuelve resolución, FPS y shorts recomendados."""
    response = client.post("/api/inspect", json={"video_filename": "test_stream_x3.mp4"})
    assert response.status_code == 200
    data = response.json()

    assert data["file_name"] == "test_stream_x3.mp4"
    assert data["resolution"] == "640x360"
    assert data["fps"] == 30.0
    assert data["duration_sec"] == pytest.approx(2.0, abs=0.2)
    assert data["recommended_shorts"] >= 1
    assert data["max_possible_shorts"] >= 1


def test_post_inspect_missing_video_returns_404(client: TestClient) -> None:
    """POST /api/inspect con archivo inexistente devuelve 404."""
    response = client.post("/api/inspect", json={"video_filename": "no_existe.mp4"})
    assert response.status_code == 404
    assert "detail" in response.json()


def test_post_inspect_empty_filename_returns_400(client: TestClient) -> None:
    """POST /api/inspect con nombre vacío devuelve 400."""
    response = client.post("/api/inspect", json={"video_filename": "   "})
    assert response.status_code == 400
    assert "detail" in response.json()


def test_post_pipeline_process_invalid_shorts_count_returns_422(client: TestClient) -> None:
    """POST /api/pipeline/process valida que shorts_per_video esté entre 1 y 24."""
    response = client.post(
        "/api/pipeline/process",
        json={
            "source_type": "inbox",
            "video_filename": "test_stream_x3.mp4",
            "shorts_per_video": 25,
            "layout_mode": "auto",
            "bgm_mood": "auto",
            "auto_upload_to_youtube": False,
        },
    )
    assert response.status_code == 422


def test_post_pipeline_process_invalid_youtube_url_returns_400(client: TestClient) -> None:
    """POST /api/pipeline/process con source_type=youtube_url y URL inválida devuelve 400."""
    response = client.post(
        "/api/pipeline/process",
        json={
            "source_type": "youtube_url",
            "youtube_url": "https://example.com/not-youtube",
            "shorts_per_video": 4,
            "layout_mode": "auto",
            "bgm_mood": "auto",
            "auto_upload_to_youtube": False,
        },
    )
    assert response.status_code == 400
    assert "YouTube" in response.json()["detail"]


def test_post_pipeline_process_valid_saves_settings_and_starts_job(
    client: TestClient, temp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /api/pipeline/process con parámetros válidos persiste settings.json y lanza el job."""
    executed_calls = []

    def fake_runner(video_path: Path, overrides: dict) -> None:
        executed_calls.append((video_path.name, overrides))

    monkeypatch.setattr(api_server, "_run_pipeline_background", fake_runner)

    response = client.post(
        "/api/pipeline/process",
        json={
            "source_type": "inbox",
            "video_filename": "test_stream_x3.mp4",
            "shorts_per_video": 5,
            "layout_mode": "split_streamer",
            "bgm_mood": "impacto",
            "auto_upload_to_youtube": False,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("STARTED", "COMPLETED")
    assert data["settings_applied"]["shorts_per_video"] == 5
    assert data["settings_applied"]["layout_mode"] == "split_streamer"
    assert data["settings_applied"]["default_bgm_mood"] == "impacto"

    saved_cfg = json.loads((temp_workspace / "config" / "settings.json").read_text(encoding="utf-8"))
    assert saved_cfg["shorts_per_video"] == 5
    assert saved_cfg["layout_mode"] == "split_streamer"


def test_get_shorts_returns_rendered_shorts_and_virality_metadata(client: TestClient) -> None:
    """GET /api/shorts lista los MP4 en output_shorts con su puntaje viral, tier, elegibilidad YT y slot AST."""
    response = client.get("/api/shorts")
    assert response.status_code == 200
    data = response.json()

    assert "shorts" in data
    assert len(data["shorts"]) == 2

    by_name = {s["filename"]: s for s in data["shorts"]}
    s1 = by_name["test_stream_01_Oro_92pts.mp4"]
    assert s1["virality_score"] == 92
    assert s1["tier"] == "Oro"
    assert s1["eligible_for_youtube"] is True
    assert s1["scheduled_ast"] is not None

    s2 = by_name["test_stream_02_Plata_80pts.mp4"]
    assert s2["virality_score"] == 80
    assert s2["tier"] == "Plata"
    assert s2["eligible_for_youtube"] is True


def test_get_queues_returns_sqlite_schedules(client: TestClient) -> None:
    """GET /api/queues devuelve las colas reales de YouTube, Instagram y TikTok desde SQLite."""
    response = client.get("/api/queues")
    assert response.status_code == 200
    data = response.json()

    assert "youtube_slots" in data
    assert "instagram_queue" in data
    assert "tiktok_queue" in data
    assert len(data["youtube_slots"]) == 1
    assert data["youtube_slots"][0]["video_name"] == "test_stream_01_Oro_92pts.mp4"


def test_post_cleanup_removes_temp_files_and_returns_disk_report(
    client: TestClient, temp_workspace: Path
) -> None:
    """POST /api/cleanup ejecuta clean_processing_dir real y elimina archivos temporales .ass."""
    temp_ass = temp_workspace / "processing" / "temp_subtitles.ass"
    assert temp_ass.exists()

    response = client.post("/api/cleanup")
    assert response.status_code == 200
    data = response.json()

    assert data["deleted_files"] >= 1
    assert not temp_ass.exists()
    assert "disk_space" in data
    assert data["disk_space"]["free_gb"] > 0


def test_get_health_and_pipeline_status(client: TestClient) -> None:
    """GET /api/health y GET /api/pipeline/status devuelven estado operativo real del motor."""
    health_res = client.get("/api/health")
    assert health_res.status_code == 200
    h_data = health_res.json()
    assert h_data["status"] == "ok"
    assert h_data["engine"] == "Auto-Clipper Shorts Engine"

    status_res = client.get("/api/pipeline/status")
    assert status_res.status_code == 200
    s_data = status_res.json()
    assert "status" in s_data
    assert "message" in s_data
    assert "updated_at" in s_data


def test_post_pipeline_process_missing_inbox_file_returns_404(client: TestClient) -> None:
    """POST /api/pipeline/process con source_type=inbox y archivo inexistente devuelve 404."""
    response = client.post(
        "/api/pipeline/process",
        json={
            "source_type": "inbox",
            "video_filename": "fantasma.mp4",
            "shorts_per_video": 4,
            "layout_mode": "auto",
            "bgm_mood": "auto",
            "auto_upload_to_youtube": False,
        },
    )
    assert response.status_code == 404


def test_root_serves_frontend_ui(client: TestClient) -> None:
    """GET / sirve la interfaz web compilada de Short YT (status 200 HTML)."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "Short YT" in response.text


def test_zero_clipxtudio_references_in_codebase() -> None:
    """Verifica que no existan referencias residuales a clipXtudio en los archivos del proyecto."""
    root = Path(__file__).resolve().parent.parent
    files_to_check = [
        root / "api_server.py",
        root / "startup_sentinel.py",
        root / "frontend" / "src" / "App.tsx",
        root / ".agents" / "skills" / "video-transcriber-analyzer" / "analyzer.py",
        root / ".agents" / "skills" / "youtube-shorts-uploader" / "uploader.py",
    ]
    for fpath in files_to_check:
        content = fpath.read_text(encoding="utf-8")
        assert "clipxtudio" not in content.lower(), f"Referencia a clipXtudio encontrada en {fpath.name}"


def test_category_analytics_profiles_and_endpoint(client: TestClient) -> None:
    """GET /api/analytics/categories devuelve las categorías especializadas con pesos que suman 100 pts."""
    response = client.get("/api/analytics/categories")
    assert response.status_code == 200
    data = response.json()

    assert "categories" in data
    cats = {c["key"]: c for c in data["categories"]}
    required_keys = {
        "opinion_monologo",
        "reacciones",
        "videojuegos",
        "podcast",
        "realitys",
        "storytime_anecdota",
        "tutorial_curiosidad",
    }
    assert required_keys.issubset(set(cats.keys()))

    for key in required_keys:
        cat_info = cats[key]
        assert sum(cat_info["weights"].values()) == 100, f"Los pesos de {key} deben sumar 100"
        assert len(cat_info["key_signals"]) >= 3


def test_category_specific_virality_scoring() -> None:
    """Verifica que evaluate_virality_10_points mida distinto según la categoría del contenido."""
    gaming_text = (
        "¡Mira este clutch épico en la final! ¡No puede ser, qué locura de jugada, "
        "ganamos la partida en el último segundo con 1 de vida! ¡Increíble bug del jefe final!"
    )
    podcast_text = (
        "Todo lo que te enseñaron sobre el dinero es mentira. Cuando entiendes la psicología "
        "detrás del éxito y por qué el 99 por ciento fracasa en su mentalidad, tu vida cambia para siempre."
    )

    res_gaming_in_gaming = api_server.skill_virality.evaluate_virality_10_points(
        text=gaming_text,
        duration=45.0,
        title="CLUTCH IMPOSIBLE EN LA FINAL CON 1 HP",
        category="videojuegos",
    )
    res_gaming_in_podcast = api_server.skill_virality.evaluate_virality_10_points(
        text=gaming_text,
        duration=45.0,
        title="CLUTCH IMPOSIBLE EN LA FINAL CON 1 HP",
        category="podcast",
    )
    assert res_gaming_in_gaming.category == "videojuegos"
    assert res_gaming_in_gaming.total_points > res_gaming_in_podcast.total_points

    res_pod_in_podcast = api_server.skill_virality.evaluate_virality_10_points(
        text=podcast_text,
        duration=45.0,
        title="LA VERDAD OCULTA QUE NADIE TE DICE EN EL PODCAST",
        category="podcast",
    )
    res_pod_in_gaming = api_server.skill_virality.evaluate_virality_10_points(
        text=podcast_text,
        duration=45.0,
        title="LA VERDAD OCULTA QUE NADIE TE DICE EN EL PODCAST",
        category="videojuegos",
    )
    assert res_pod_in_podcast.category == "podcast"
    assert res_pod_in_podcast.total_points > res_pod_in_gaming.total_points


def test_podcast_dynamic_layout_detection_single_and_dual_speakers(tmp_path: Path) -> None:
    """
    Verifica que el layout 'podcast_dynamic' detecte quién habla en cada momento:
    - Solo Persona 1 (izquierda) -> 'speaker_1' (recorte completo 9:16 de Persona 1)
    - Solo Persona 2 (derecha) -> 'speaker_2' (recorte completo 9:16 de Persona 2)
    - Ambos hablando al mismo tiempo -> 'both_split' (pantalla dividida mitad y mitad 50/50)
    """
    renderer_mod = api_server._load_skill_module("vertical-crop-renderer", "renderer.py")
    podcast_video = tmp_path / "podcast_2_speakers.mp4"

    fps = 10.0
    width, height = 1280, 720
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(podcast_video), fourcc, fps, (width, height))

    # 30 frames (3.0s):
    # - 0.0s a 1.0s (frames 0..9): Habla Persona Izquierda (movimiento en zona izquierda x=320, y=360)
    # - 1.0s a 2.0s (frames 10..19): Habla Persona Derecha (movimiento en zona derecha x=960, y=360)
    # - 2.0s a 3.0s (frames 20..29): Hablan AMBOS al mismo tiempo (movimiento en ambas zonas)
    for f_idx in range(30):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        # Dibujar siluetas base de ambos hablantes
        cv2.circle(frame, (320, 300), 60, (180, 180, 180), -1)
        cv2.circle(frame, (960, 300), 60, (180, 180, 180), -1)

        toggle = (f_idx % 2) * 255
        if f_idx < 10:
            # Solo habla izquierda
            cv2.rectangle(frame, (290, 330), (350, 370), (toggle, toggle, 255), -1)
        elif f_idx < 20:
            # Solo habla derecha
            cv2.rectangle(frame, (930, 330), (990, 370), (toggle, 255, toggle), -1)
        else:
            # Hablan ambos al mismo tiempo
            cv2.rectangle(frame, (290, 330), (350, 370), (toggle, toggle, 255), -1)
            cv2.rectangle(frame, (930, 330), (990, 370), (toggle, 255, toggle), -1)

        writer.write(frame)
    writer.release()

    layout_info = renderer_mod.detect_video_layout_and_regions(
        video_path=podcast_video,
        start_time=0.0,
        end_time=3.0,
        layout_mode="podcast_dynamic",
    )

    assert layout_info["mode"] == "podcast_dynamic"
    assert "speaker_left_crop" in layout_info
    assert "speaker_right_crop" in layout_info
    assert "split_left_box" in layout_info
    assert "split_right_box" in layout_info
    assert "timeline_segments" in layout_info

    states = [seg["state"] for seg in layout_info["timeline_segments"]]
    assert "speaker_1" in states
    assert "speaker_2" in states
    assert "both_split" in states

    filter_graph = renderer_mod.build_podcast_dynamic_filter_graph(
        layout_info=layout_info,
        jumpcut_v_prefix="",
        hq_flags="lanczos",
        hook_punch_filter="",
        ass_filter="",
        speed_factor=1.0,
    )
    assert "scale=1080:960" in filter_graph
    assert "vstack=inputs=2" in filter_graph
    assert "scale=1080:1920" in filter_graph


def test_pipeline_process_accepts_podcast_dynamic_and_content_category(
    client: TestClient, temp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /api/pipeline/process acepta content_category='podcast' y layout_mode='podcast_dynamic'."""
    monkeypatch.setattr(api_server, "_run_pipeline_background", lambda *a, **kw: None)

    response = client.post(
        "/api/pipeline/process",
        json={
            "source_type": "inbox",
            "video_filename": "test_stream_x3.mp4",
            "content_category": "podcast",
            "shorts_per_video": 6,
            "layout_mode": "podcast_dynamic",
            "bgm_mood": "desactivada",
            "auto_upload_to_youtube": False,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["settings_applied"]["content_category"] == "podcast"
    assert data["settings_applied"]["layout_mode"] == "podcast_dynamic"


def test_gaming_hud_layout_detection_and_filter_graph(tmp_path: Path) -> None:
    """
    Verifica el layout 'gaming_hud' (25% Facecam 1080x480 arriba + 75% Gameplay/HUD 1080x1440 abajo
    con tracking del centro de acción óptica).
    """
    renderer_mod = api_server._load_skill_module("vertical-crop-renderer", "renderer.py")
    gaming_video = tmp_path / "gaming_clutch.mp4"

    fps = 10.0
    width, height = 1280, 720
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(gaming_video), fourcc, fps, (width, height))

    for f_idx in range(20):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        # Acción intensa en el lado derecho del gameplay (x=820..980, y=300..500)
        toggle = (f_idx % 2) * 255
        cv2.rectangle(frame, (820, 300), (980, 500), (0, toggle, 255), -1)
        writer.write(frame)
    writer.release()

    layout_info = renderer_mod.detect_video_layout_and_regions(
        video_path=gaming_video,
        start_time=0.0,
        end_time=2.0,
        layout_mode="gaming_hud",
    )

    assert layout_info["mode"] == "gaming_hud"
    assert "cam_box" in layout_info
    assert "content_box" in layout_info

    fg = renderer_mod.build_gaming_hud_filter_graph(
        layout_info=layout_info,
        jumpcut_v_prefix="",
        hq_flags="lanczos",
        hook_punch_filter="",
        ass_filter="",
    )
    assert "scale=1080:480" in fg
    assert "scale=1080:1440" in fg
    assert "vstack=inputs=2" in fg


def test_reaction_pip_layout_detection_and_filter_graph(tmp_path: Path) -> None:
    """
    Verifica el layout 'reaction_pip' (Video original 16:9 íntegro sin recortar bordes laterales
    sobre canvas blur + bloque de reacción del creador 1080x780 abajo).
    """
    renderer_mod = api_server._load_skill_module("vertical-crop-renderer", "renderer.py")
    reaction_video = tmp_path / "reaction_clip.mp4"

    fps = 10.0
    width, height = 1280, 720
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(reaction_video), fourcc, fps, (width, height))

    for f_idx in range(15):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        cv2.rectangle(frame, (100, 100), (1180, 620), (120, 80, 200), -1)
        writer.write(frame)
    writer.release()

    layout_info = renderer_mod.detect_video_layout_and_regions(
        video_path=reaction_video,
        start_time=0.0,
        end_time=1.5,
        layout_mode="reaction_pip",
    )

    assert layout_info["mode"] == "reaction_pip"
    assert "cam_box" in layout_info
    assert "content_box" in layout_info

    fg = renderer_mod.build_reaction_pip_filter_graph(
        layout_info=layout_info,
        jumpcut_v_prefix="",
        hq_flags="lanczos",
        hook_punch_filter="",
        ass_filter="",
    )
    # Verifica que mantiene el video 16:9 a ancho completo 1080 y el panel del creador
    assert "scale=1080:" in fg
    assert "gblur=" in fg or "boxblur=" in fg
    assert "vstack=inputs=2" in fg or "overlay=" in fg


def test_reality_multicam_layout_detection_and_filter_graph(tmp_path: Path) -> None:
    """
    Verifica el layout 'reality_multicam' para grupos de 3+ personas (Reality / IRL):
    - Arriba: Plano general panorámico 1080x640 de toda la sala.
    - Abajo: Zoom dinámico 1080x1280 que sigue la zona activa (zone_left, zone_center, zone_right).
    """
    renderer_mod = api_server._load_skill_module("vertical-crop-renderer", "renderer.py")
    reality_video = tmp_path / "reality_3_people.mp4"

    fps = 10.0
    width, height = 1280, 720
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(reality_video), fourcc, fps, (width, height))

    # 30 frames (3.0s):
    # - 0..1s: Habla/grita persona en IZQUIERDA (x=200)
    # - 1..2s: Habla/grita persona en CENTRO (x=640)
    # - 2..3s: Habla/grita persona en DERECHA (x=1080)
    for f_idx in range(30):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        toggle = (f_idx % 2) * 255
        if f_idx < 10:
            cv2.rectangle(frame, (160, 280), (240, 420), (toggle, 100, 255), -1)
        elif f_idx < 20:
            cv2.rectangle(frame, (600, 280), (680, 420), (100, toggle, 255), -1)
        else:
            cv2.rectangle(frame, (1040, 280), (1120, 420), (255, 100, toggle), -1)
        writer.write(frame)
    writer.release()

    layout_info = renderer_mod.detect_video_layout_and_regions(
        video_path=reality_video,
        start_time=0.0,
        end_time=3.0,
        layout_mode="reality_multicam",
    )

    assert layout_info["mode"] == "reality_multicam"
    assert "panoramic_box" in layout_info
    assert "zone_crops" in layout_info
    assert "timeline_segments" in layout_info

    zones = [seg["state"] for seg in layout_info["timeline_segments"]]
    assert "zone_left" in zones
    assert "zone_center" in zones
    assert "zone_right" in zones

    fg = renderer_mod.build_reality_multicam_filter_graph(
        layout_info=layout_info,
        jumpcut_v_prefix="",
        hq_flags="lanczos",
        hook_punch_filter="",
        ass_filter="",
        speed_factor=1.0,
    )
    assert "scale=1080:640" in fg
    assert "scale=1080:1280" in fg
    assert "vstack=inputs=2" in fg


def test_auto_category_to_layout_mapping_and_pipeline_acceptance(
    client: TestClient, temp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Verifica que cada categoría tenga su layout 9:16 óptimo en modo 'auto' y que
    POST /api/pipeline/process acepte los 3 nuevos layouts: gaming_hud, reaction_pip, reality_multicam.
    """
    renderer_mod = api_server._load_skill_module("vertical-crop-renderer", "renderer.py")
    assert renderer_mod.resolve_optimal_layout_for_category("videojuegos", "auto") == "gaming_hud"
    assert renderer_mod.resolve_optimal_layout_for_category("reacciones", "auto") == "reaction_pip"
    assert renderer_mod.resolve_optimal_layout_for_category("tutorial_curiosidad", "auto") == "reaction_pip"
    assert renderer_mod.resolve_optimal_layout_for_category("podcast", "auto") == "podcast_dynamic"
    assert renderer_mod.resolve_optimal_layout_for_category("realitys", "auto") == "reality_multicam"
    assert renderer_mod.resolve_optimal_layout_for_category("opinion_monologo", "auto") == "fullscreen"
    assert renderer_mod.resolve_optimal_layout_for_category("storytime_anecdota", "auto") == "fullscreen"

    monkeypatch.setattr(api_server, "_run_pipeline_background", lambda *a, **kw: None)

    for new_layout in ("gaming_hud", "reaction_pip", "reality_multicam"):
        res = client.post(
            "/api/pipeline/process",
            json={
                "source_type": "inbox",
                "video_filename": "test_stream_x3.mp4",
                "content_category": "auto",
                "shorts_per_video": 6,
                "layout_mode": new_layout,
                "bgm_mood": "auto",
                "auto_upload_to_youtube": False,
            },
        )
        assert res.status_code == 200, f"Fallo al enviar layout_mode={new_layout}: {res.text}"
        assert res.json()["settings_applied"]["layout_mode"] == new_layout


def test_pipeline_status_includes_progress_bar_and_source_preview(
    client: TestClient, temp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Verifica que:
    1) POST /api/pipeline/process inicialice progress_percent, phase_label, step_detail y source_preview_url.
    2) GET /api/pipeline/status devuelva estos campos para el Modal de Proceso del Video.
    3) GET /api/media/source/{filename} sirva el archivo de video fuente real para visualizarlo en el modal.
    """
    monkeypatch.setattr(api_server, "_run_pipeline_background", lambda *a, **kw: None)

    start_res = client.post(
        "/api/pipeline/process",
        json={
            "source_type": "inbox",
            "video_filename": "test_stream_x3.mp4",
            "content_category": "videojuegos",
            "shorts_per_video": 4,
            "layout_mode": "gaming_hud",
            "bgm_mood": "impacto",
            "auto_upload_to_youtube": True,
        },
    )
    assert start_res.status_code == 200

    status_res = client.get("/api/pipeline/status")
    assert status_res.status_code == 200
    st = status_res.json()

    assert "progress_percent" in st
    assert isinstance(st["progress_percent"], (int, float))
    assert 0 <= st["progress_percent"] <= 100
    assert "phase_label" in st and st["phase_label"]
    assert "step_detail" in st and st["step_detail"]
    assert st["source_preview_url"] == "/api/media/source/test_stream_x3.mp4"

    # Verificar que el endpoint de video fuente sirve el MP4 real
    media_res = client.get(st["source_preview_url"])
    assert media_res.status_code == 200
    assert "video/" in media_res.headers.get("content-type", "")
    assert len(media_res.content) > 100


def test_shorts_endpoint_includes_thumbnail_video_url_and_social_upload_progress(
    client: TestClient, temp_workspace: Path
) -> None:
    """
    Verifica que:
    1) GET /api/shorts incluya thumbnail_url, video_url, upload_progress_percent y upload_status_detail.
    2) GET /api/media/thumbnail/{path} extraiga con OpenCV una miniatura JPEG real del Short.
    3) GET /api/media/short/{path} permita reproducir el video MP4 del Short.
    """
    out_dir = temp_workspace / "output_shorts" / "CreadorStudio_Stream"
    out_dir.mkdir(parents=True, exist_ok=True)
    short_mp4 = out_dir / "CreadorStudio_Stream_01_Oro_95pts.mp4"

    # Crear un MP4 real con cuadros de color usando OpenCV para extraer su miniatura real
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(short_mp4), fourcc, 15.0, (360, 640))
    for i in range(15):
        frame = np.zeros((640, 360, 3), dtype=np.uint8)
        cv2.rectangle(frame, (40, 80), (320, 560), (40, 140, 255), -1)
        writer.write(frame)
    writer.release()

    # Registrar en SQLite como subido a YouTube para verificar progreso de subida en redes
    db_path = temp_workspace / "config" / "schedule_state.db"
    api_server.skill_scheduler.init_db(db_path)
    slot_utc = api_server.skill_scheduler.get_and_reserve_next_slot(
        video_name=short_mp4.name, db_path=db_path
    )
    api_server.skill_scheduler.update_slot_youtube_id(
        publish_at_utc=slot_utc,
        youtube_video_id="yt_live_999",
        db_path=db_path,
    )

    res = client.get("/api/shorts")
    assert res.status_code == 200
    items = res.json()["shorts"]
    target = next((s for s in items if s["filename"] == "CreadorStudio_Stream_01_Oro_95pts.mp4"), None)
    assert target is not None

    assert "thumbnail_url" in target and target["thumbnail_url"].startswith("/api/media/thumbnail/")
    assert "video_url" in target and target["video_url"].startswith("/api/media/short/")
    assert "upload_progress_percent" in target
    assert target["upload_progress_percent"] == 100
    assert "upload_status_detail" in target and "YouTube" in target["upload_status_detail"]

    # Verificar que la miniatura JPEG se genera y sirve correctamente
    thumb_res = client.get(target["thumbnail_url"])
    assert thumb_res.status_code == 200
    assert thumb_res.headers.get("content-type") == "image/jpeg"
    assert thumb_res.content[:3] == b"\xff\xd8\xff"

    # Verificar que el stream del Short MP4 funciona al darle Play
    play_res = client.get(target["video_url"])
    assert play_res.status_code == 200
    assert "video/" in play_res.headers.get("content-type", "")
    assert len(play_res.content) > 100


def test_youtube_download_progress_hook_updates_pipeline_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    Verifica que download_youtube_url_max_quality conecte progress_hooks de yt-dlp
    con el callback de progreso en tiempo real (MB descargados, velocidad, fragmentos)
    y active concurrent_fragment_downloads=8 + continuedl=True.
    """
    import main_daemon
    import yt_dlp

    captured_opts: Dict[str, Any] = {}
    progress_events: List[Tuple[int, str, str]] = []

    class DummyYDL:
        def __init__(self, opts: Dict[str, Any]) -> None:
            captured_opts.update(opts)

        def __enter__(self) -> "DummyYDL":
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def extract_info(self, url: str, download: bool = True) -> Dict[str, Any]:
            for hook in captured_opts.get("progress_hooks", []):
                hook(
                    {
                        "status": "downloading",
                        "downloaded_bytes": 2400 * 1024 * 1024,
                        "total_bytes_estimate": 4250 * 1024 * 1024,
                        "speed": 6.5 * 1024 * 1024,
                        "fragment_index": 1430,
                        "fragment_count": 2710,
                    }
                )
            return {"title": "Zelda_Live"}

        def prepare_filename(self, info: Dict[str, Any]) -> str:
            out_file = tmp_path / "Zelda_Live.mp4"
            out_file.write_bytes(b"\x00\x00\x00\x18ftypmp42")
            return str(out_file)

    monkeypatch.setattr(yt_dlp, "YoutubeDL", DummyYDL)

    def _cb(pct: int, phase: str, detail: str, short_update: Optional[Dict[str, Any]] = None) -> None:
        progress_events.append((pct, phase, detail))

    out_path = main_daemon.download_youtube_url_max_quality(
        "https://youtube.com/live/9No2bIIno_w?feature=share",
        progress_callback=_cb,
    )
    assert out_path.exists()
    assert captured_opts.get("concurrent_fragment_downloads") == 8
    assert captured_opts.get("continuedl") is True
    assert len(progress_events) >= 1
    pct, phase, detail = progress_events[-1]
    assert 1 <= pct <= 25
    assert "Descarga YouTube" in phase
    assert "1430/2710" in detail


def test_theme_mode_persistence_endpoint(client: TestClient) -> None:
    """
    Verifica que POST /api/settings/theme persista theme_mode ('light' | 'dark')
    en settings.json y que GET /api/inbox devuelva theme_mode actualizado.
    """
    res_dark = client.post("/api/settings/theme", json={"theme_mode": "dark"})
    assert res_dark.status_code == 200
    assert res_dark.json()["theme_mode"] == "dark"

    inbox_res = client.get("/api/inbox")
    assert inbox_res.status_code == 200
    assert inbox_res.json()["settings"]["theme_mode"] == "dark"

    res_invalid = client.post("/api/settings/theme", json={"theme_mode": "neon"})
    assert res_invalid.status_code == 422


def test_analyzer_imports_and_pipeline_error_propagation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    Verifica que:
    1) analyzer._setup_nvidia_dll_paths() y analyzer._heuristic_viral_fallback_multiple()
       ejecuten sin NameError (sys, re y padding dinámico de hooks).
    2) Si process_video_pipeline falla durante la transcripción, restaure el video desde
       processing/ hacia inbox_videos/ y propague la excepción para que PIPELINE_STATE
       quede en 'ERROR' (y nunca en un falso 'COMPLETED').
    """
    import main_daemon

    analyzer_mod = api_server._load_skill_module("video-transcriber-analyzer", "analyzer.py")
    # 1. No debe lanzar NameError: name 'sys' is not defined
    analyzer_mod._setup_nvidia_dll_paths()

    # 2. No debe lanzar NameError: name 're' is not defined ni 'hooks_templates' is not defined
    sample_segments = [
        {
            "start": 10.0,
            "end": 55.0,
            "text": (
                "¿Sabías qué pasa cuando entras al Templo del Tiempo en Zelda Ocarina of Time Remake? "
                "Mira cómo cambia toda la iluminación en tiempo real y la fluidez a sesenta cuadros por segundo "
                "mientras abrimos la puerta principal con la Espada Maestra en este directo épico."
            ),
        },
        {
            "start": 120.0,
            "end": 135.0,
            "text": "Segundo segmento corto para probar el relleno sin plantillas indefinidas.",
        },
    ]
    clips = analyzer_mod._heuristic_viral_fallback_multiple(sample_segments, max_shorts=2)
    assert len(clips) == 2
    assert clips[0].hook_title
    assert clips[1].hook_title

    # 3. Si ocurre un error en process_video_pipeline, el video debe regresar a inbox_videos y lanzar excepción
    fake_inbox = tmp_path / "inbox_videos"
    fake_proc = tmp_path / "processing"
    fake_out = tmp_path / "output_shorts"
    fake_arch = tmp_path / "published_archive"
    fake_cfg = tmp_path / "config"
    for d in (fake_inbox, fake_proc, fake_out, fake_arch, fake_cfg):
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(main_daemon, "INBOX_DIR", fake_inbox)
    monkeypatch.setattr(main_daemon, "PROCESSING_DIR", fake_proc)
    monkeypatch.setattr(main_daemon, "OUTPUT_SHORTS_DIR", fake_out)
    monkeypatch.setattr(main_daemon, "PUBLISHED_ARCHIVE_DIR", fake_arch)
    monkeypatch.setattr(main_daemon, "CONFIG_DIR", fake_cfg)
    monkeypatch.setattr(main_daemon, "wait_until_file_ready", lambda p, timeout=30.0: True)

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Fallo simulado en transcripción")

    monkeypatch.setattr(main_daemon.skill_transcriber, "transcribe_and_analyze_multiple", _boom)

    video_file = fake_inbox / "zelda_live.mp4"
    video_file.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    with pytest.raises(RuntimeError, match="Fallo simulado"):
        main_daemon.process_video_pipeline(video_file)

    assert (fake_inbox / "zelda_live.mp4").exists(), "El video debe restaurarse a inbox_videos tras un fallo"


def test_pipeline_renders_all_extracted_shorts_using_transcript_excerpt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    Verifica que main_daemon.process_video_pipeline evalúe transcript_excerpt completo
    y renderice todos los Shorts solicitados (nunca 0 Shorts cuando hay candidatos extraídos).
    """
    import main_daemon

    fake_inbox = tmp_path / "inbox_videos"
    fake_proc = tmp_path / "processing"
    fake_out = tmp_path / "output_shorts"
    fake_arch = tmp_path / "published_archive"
    fake_cfg = tmp_path / "config"
    for d in (fake_inbox, fake_proc, fake_out, fake_arch, fake_cfg):
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(main_daemon, "INBOX_DIR", fake_inbox)
    monkeypatch.setattr(main_daemon, "PROCESSING_DIR", fake_proc)
    monkeypatch.setattr(main_daemon, "OUTPUT_SHORTS_DIR", fake_out)
    monkeypatch.setattr(main_daemon, "PUBLISHED_ARCHIVE_DIR", fake_arch)
    monkeypatch.setattr(main_daemon, "CONFIG_DIR", fake_cfg)
    monkeypatch.setattr(main_daemon, "SETTINGS_PATH", fake_cfg / "settings.json")
    monkeypatch.setattr(main_daemon, "wait_until_file_ready", lambda p, timeout=30.0: True)
    main_daemon.PIPELINE_CANCEL_EVENT.clear()

    # Crear 2 clips con texto conversacional normal de gameplay (que antes daba <50 pts si solo miraba caption)
    fake_clips = [
        main_daemon.skill_transcriber.ViralClipAnalysis(
            start_time=100.0,
            end_time=145.0,
            hook_title='🔥 "COMO UN TAL UN POCO ARROGANTE" 😱 #Shorts',
            first_person_caption="😱 Como un tal Un poco arrogante... #Viral #Shorts",
            tags=["CreadorStudio", "Shorts", "Zelda"],
            bgm_mood="impacto",
            word_timestamps=[],
            keep_intervals=[(0.0, 45.0)],
            transcript_excerpt="Como un tal un poco arrogante ya siento que nos sentimos los de antes en este directo.",
        ),
        main_daemon.skill_transcriber.ViralClipAnalysis(
            start_time=300.0,
            end_time=345.0,
            hook_title='🔥 "ENTRANDO AL TEMPLO DEL TIEMPO" 😱 #Shorts',
            first_person_caption="😱 Entrando al templo... #Viral #Shorts",
            tags=["CreadorStudio", "Shorts", "Zelda"],
            bgm_mood="impacto",
            word_timestamps=[],
            keep_intervals=[(0.0, 45.0)],
            transcript_excerpt="Vamos entrando por la puerta principal para buscar la siguiente llave del templo.",
        ),
    ]
    monkeypatch.setattr(
        main_daemon.skill_transcriber,
        "transcribe_and_analyze_multiple",
        lambda *a, **kw: fake_clips,
    )

    rendered_files: List[Path] = []

    def _fake_render(**kwargs: Any) -> Path:
        out_dir = Path(kwargs["output_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / kwargs["output_filename"]
        out_file.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        rendered_files.append(out_file)
        return out_file

    monkeypatch.setattr(main_daemon.skill_renderer, "render_vertical_short", _fake_render)
    monkeypatch.setattr(main_daemon.skill_scheduler, "get_and_reserve_next_slot", lambda **kw: "2026-11-08T16:00:00Z")
    monkeypatch.setattr(main_daemon.skill_ig_scheduler, "enqueue_instagram_reel", lambda **kw: 1)
    monkeypatch.setattr(main_daemon.skill_tt_scheduler, "enqueue_tiktok_video", lambda **kw: 1)

    video_file = fake_inbox / "zelda_test.mp4"
    video_file.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    main_daemon.process_video_pipeline(
        video_file,
        cli_overrides={"shorts_per_video": 2, "content_category": "videojuegos", "auto_upload_to_youtube": False},
    )

    assert len(rendered_files) == 2, f"Se esperaban 2 Shorts renderizados, pero se generaron {len(rendered_files)}"


def test_cancel_individual_short_removes_file_and_sqlite_queues(
    client: TestClient, temp_workspace: Path
) -> None:
    """
    Verifica que DELETE /api/shorts/{short_rel_path} cancele un Short:
    1) Elimina el archivo MP4 de ./output_shorts/.
    2) Elimina su reserva en scheduled_slots y sus entradas en instagram_scheduled_queue y tiktok_scheduled_queue.
    """
    out_dir = temp_workspace / "output_shorts" / "Zelda_Run"
    out_dir.mkdir(parents=True, exist_ok=True)
    short_mp4 = out_dir / "Zelda_Run_01_Oro_92pts.mp4"
    short_mp4.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 512)

    db_path = temp_workspace / "config" / "schedule_state.db"
    api_server.skill_scheduler.init_db(db_path)
    api_server.skill_ig_scheduler.init_ig_queue_db(db_path)
    api_server.skill_tt_scheduler.init_tiktok_queue_db(db_path)

    slot_utc = api_server.skill_scheduler.get_and_reserve_next_slot(
        video_name=short_mp4.name, db_path=db_path
    )
    api_server.skill_ig_scheduler.enqueue_instagram_reel(
        video_path=str(short_mp4),
        account_key="creador_gaming",
        caption="Zelda test #Shorts",
        scheduled_time_utc=slot_utc,
        db_path=db_path,
    )
    api_server.skill_tt_scheduler.enqueue_tiktok_video(
        video_path=str(short_mp4),
        account_key="creador.gaming",
        caption="Zelda test #Shorts",
        scheduled_time_utc=slot_utc,
        db_path=db_path,
    )

    del_res = client.delete("/api/shorts/Zelda_Run/Zelda_Run_01_Oro_92pts.mp4")
    assert del_res.status_code == 200
    body = del_res.json()
    assert body["canceled"] is True
    assert body["filename"] == "Zelda_Run_01_Oro_92pts.mp4"
    assert not short_mp4.exists()

    shorts_after = client.get("/api/shorts").json()["shorts"]
    assert all(s["filename"] != "Zelda_Run_01_Oro_92pts.mp4" for s in shorts_after)

    queues_after = client.get("/api/queues").json()
    assert all(s["video_name"] != "Zelda_Run_01_Oro_92pts.mp4" for s in queues_after["youtube_slots"])
    assert all("Zelda_Run_01_Oro_92pts.mp4" not in q["video_path"] for q in queues_after["instagram_queue"])
    assert all("Zelda_Run_01_Oro_92pts.mp4" not in q["video_path"] for q in queues_after["tiktok_queue"])


def test_cancel_all_shorts_clears_output_shorts_and_pending_queues(
    client: TestClient, temp_workspace: Path
) -> None:
    """
    Verifica que DELETE /api/shorts cancele todos los Shorts renderizados en ./output_shorts/
    y limpie sus programaciones pendientes en SQLite.
    """
    out_dir = temp_workspace / "output_shorts" / "Batch_Zelda"
    out_dir.mkdir(parents=True, exist_ok=True)
    s1 = out_dir / "Batch_Zelda_01_Plata_80pts.mp4"
    s2 = out_dir / "Batch_Zelda_02_Meh_65pts.mp4"
    s1.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    s2.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    res = client.delete("/api/shorts")
    assert res.status_code == 200
    data = res.json()
    assert data["canceled_count"] >= 2
    assert client.get("/api/shorts").json()["total"] == 0


def test_cancel_running_pipeline_endpoint(client: TestClient) -> None:
    """
    Verifica que POST /api/pipeline/cancel detenga el estado activo del pipeline y marque status='CANCELED'.
    """
    api_server.PIPELINE_STATE["status"] = "RUNNING"
    api_server.PIPELINE_STATE["current_video"] = "zelda_live.mp4"

    res = client.post("/api/pipeline/cancel")
    assert res.status_code == 200
    assert res.json()["status"] == "CANCELED"

    st = client.get("/api/pipeline/status").json()
    assert st["status"] == "CANCELED"


def test_completion_summary_and_schedule_shorts_batch_with_auto_youtube_upload(
    client: TestClient, temp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Verifica que:
    1) GET /api/shorts y GET /api/pipeline/status incluyan completion_summary con el conteo
       exacto de Oro, Plata y Meh.
    2) POST /api/shorts/schedule programe la fecha y hora en YouTube (scheduled_slots),
       Instagram (instagram_scheduled_queue) y TikTok (tiktok_scheduled_queue),
       suba automáticamente a YouTube los Shorts positivos (>= 85 pts) y actualice el progreso al 100%.
    """
    client.delete("/api/shorts")
    out_dir = temp_workspace / "output_shorts" / "Hablando_Debate"
    out_dir.mkdir(parents=True, exist_ok=True)

    s_oro = out_dir / "Hablando_Debate_01_Oro_91pts.mp4"
    s_plata = out_dir / "Hablando_Debate_02_Plata_76pts.mp4"
    s_meh = out_dir / "Hablando_Debate_03_Meh_68pts.mp4"
    for f in (s_oro, s_plata, s_meh):
        f.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 512)

    shorts_res = client.get("/api/shorts")
    assert shorts_res.status_code == 200
    shorts_data = shorts_res.json()
    assert "summary" in shorts_data
    assert shorts_data["summary"]["oro_count"] == 1
    assert shorts_data["summary"]["plata_count"] == 1
    assert shorts_data["summary"]["meh_count"] == 1
    assert shorts_data["summary"]["youtube_eligible_count"] == 3

    uploaded_calls: List[Dict[str, Any]] = []

    def _mock_yt_upload(**kwargs: Any) -> Dict[str, Any]:
        uploaded_calls.append(kwargs)
        fname_up = Path(str(kwargs.get("video_path", ""))).name
        return {"id": f"yt_auto_{fname_up[:12]}"}

    monkeypatch.setattr(api_server.skill_uploader, "upload_scheduled_short", _mock_yt_upload)

    sched_res = client.post(
        "/api/shorts/schedule",
        json={
            "youtube_start_time": "2026-11-08T14:00",
            "instagram_start_time": "2026-11-08T15:00",
            "tiktok_start_time": "2026-11-08T16:00",
            "interval_minutes": 60,
            "auto_upload_positive_to_youtube": True,
        },
    )
    assert sched_res.status_code == 200
    sched_body = sched_res.json()
    assert sched_body["scheduled_count"] == 3
    assert sched_body["youtube_uploaded_count"] == 3
    assert len(uploaded_calls) == 3

    # Verificar que todos los Shorts ahora están al 100% y tienen su youtube_video_id sin filtro < 85 pts
    updated_shorts = client.get("/api/shorts").json()["shorts"]
    oro_item = next(s for s in updated_shorts if s["filename"] == "Hablando_Debate_01_Oro_91pts.mp4")
    plata_item = next(s for s in updated_shorts if s["filename"] == "Hablando_Debate_02_Plata_76pts.mp4")
    assert oro_item["youtube_video_id"] == "yt_auto_Hablando_Deb"
    assert plata_item["youtube_video_id"] == "yt_auto_Hablando_Deb"
    assert oro_item["upload_progress_percent"] == 100
    assert plata_item["upload_progress_percent"] == 100


def test_desktop_launcher_file_exists_and_starts_short_yt() -> None:
    """
    Verifica que exista el archivo iniciador portátil en la raíz del proyecto
    ('Iniciar Auto-Clipper Studio.bat') con saltos de línea Windows CRLF (\\r\\n)
    para arrancar api_server.py sin errores de ruta en cmd.exe.
    """
    repo_launcher = Path(__file__).resolve().parents[1] / "Iniciar Auto-Clipper Studio.bat"
    assert repo_launcher.exists(), f"No se encontró el lanzador portátil: {repo_launcher}"
    raw_bytes = repo_launcher.read_bytes()
    assert b"\r\n" in raw_bytes, "El archivo .bat debe tener saltos de línea CRLF (\\r\\n) para cmd.exe en Windows"
    content = raw_bytes.decode("utf-8")
    assert "api_server.py" in content


def test_auto_cleanup_on_video_finish_and_clean_state_on_new_video(
    client: TestClient, temp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Verifica que:
    1) Al terminar de procesar un video en process_video_pipeline, se eliminen automáticamente
       todos los archivos temporales e innecesarios (.ass, _analysis.json, .transcript_cache_*.json,
       y el video fuente pesado en processing/ y published_archive/).
    2) Al iniciar el trabajo de otro video (POST /api/pipeline/process), el sistema limpie
       los Shorts y estados residuales del video anterior para quedar limpio.
    """
    import main_daemon

    fake_inbox = temp_workspace / "inbox_videos"
    fake_proc = temp_workspace / "processing"
    fake_out = temp_workspace / "output_shorts"
    fake_arch = temp_workspace / "published_archive"
    fake_cfg = temp_workspace / "config"

    monkeypatch.setattr(main_daemon, "INBOX_DIR", fake_inbox)
    monkeypatch.setattr(main_daemon, "PROCESSING_DIR", fake_proc)
    monkeypatch.setattr(main_daemon, "OUTPUT_SHORTS_DIR", fake_out)
    monkeypatch.setattr(main_daemon, "PUBLISHED_ARCHIVE_DIR", fake_arch)
    monkeypatch.setattr(main_daemon, "CONFIG_DIR", fake_cfg)
    monkeypatch.setattr(main_daemon, "SETTINGS_PATH", fake_cfg / "settings.json")
    monkeypatch.setattr(main_daemon, "wait_until_file_ready", lambda p, timeout=30.0: True)
    main_daemon.PIPELINE_CANCEL_EVENT.clear()

    # Crear basura temporal en processing/ y published_archive/
    (fake_proc / "old_subs.ass").write_text("ScriptInfo", encoding="utf-8")
    (fake_proc / ".transcript_cache_999.json").write_text("{}", encoding="utf-8")
    (fake_proc / "video_viejo_analysis.json").write_text("[]", encoding="utf-8")
    (fake_arch / "video_pesado_anterior.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")

    fake_clips = [
        main_daemon.skill_transcriber.ViralClipAnalysis(
            start_time=10.0,
            end_time=55.0,
            hook_title='🔥 "MOMENTO VIRAL" 😱 #Shorts',
            first_person_caption="😱 Momento viral #Viral #Shorts",
            tags=["CreadorStudio", "Shorts"],
            bgm_mood="impacto",
            word_timestamps=[],
            keep_intervals=[(0.0, 45.0)],
            transcript_excerpt="Texto completo del momento viral para el Short.",
        )
    ]
    monkeypatch.setattr(
        main_daemon.skill_transcriber,
        "transcribe_and_analyze_multiple",
        lambda *a, **kw: fake_clips,
    )

    def _fake_render(**kwargs: Any) -> Path:
        out_dir = Path(kwargs["output_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        # Simular creación de subtítulo .ass temporal durante el render
        (fake_proc / "temp_render_subs.ass").write_text("AssContent", encoding="utf-8")
        out_file = out_dir / kwargs["output_filename"]
        out_file.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        return out_file

    monkeypatch.setattr(main_daemon.skill_renderer, "render_vertical_short", _fake_render)
    monkeypatch.setattr(main_daemon.skill_scheduler, "get_and_reserve_next_slot", lambda **kw: "2026-11-10T18:00:00Z")
    monkeypatch.setattr(main_daemon.skill_ig_scheduler, "enqueue_instagram_reel", lambda **kw: 1)
    monkeypatch.setattr(main_daemon.skill_tt_scheduler, "enqueue_tiktok_video", lambda **kw: 1)

    source_video = fake_inbox / "nuevo_directo.mp4"
    source_video.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    main_daemon.process_video_pipeline(
        source_video,
        cli_overrides={"shorts_per_video": 1, "auto_upload_to_youtube": False},
    )

    # 1) Al terminar el video, ni processing/ ni published_archive/ deben conservar temporales ni el MP4 pesado
    assert not list(fake_proc.glob("*.ass")), "Deben limpiarse todos los .ass al terminar el video"
    assert not list(fake_proc.glob("*_analysis.json")), "Deben limpiarse los _analysis.json al terminar el video"
    assert not list(fake_proc.glob(".transcript_cache_*.json")), "Deben limpiarse los cachés de transcripción"
    assert not list(fake_proc.glob("*.mp4")), "No debe quedar ningún MP4 en processing/"
    assert not list(fake_arch.glob("*.mp4")), "No deben acumularse videos pesados en published_archive/"

    # 2) Al iniciar un nuevo video en POST /api/pipeline/process, debe limpiar los Shorts previos para empezar limpio
    assert client.get("/api/shorts").json()["total"] > 0
    monkeypatch.setattr(api_server, "_run_pipeline_background", lambda *a, **kw: None)

    next_video = fake_inbox / "siguiente_video.mp4"
    next_video.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    start_res = client.post(
        "/api/pipeline/process",
        json={
            "source_type": "inbox",
            "video_filename": "siguiente_video.mp4",
            "content_category": "auto",
            "shorts_per_video": 4,
            "layout_mode": "auto",
            "bgm_mood": "desactivada",
            "auto_upload_to_youtube": True,
        },
    )
    assert start_res.status_code == 200
    assert client.get("/api/shorts").json()["total"] == 0, "Debe limpiar los Shorts anteriores al iniciar un nuevo video"


def test_acoustic_energy_peak_detection_and_segment_scoring(tmp_path: Path) -> None:
    """
    Mejora 1 (Stage 3.1): Verifica la detección de picos acústicos (RMS / dB spikes)
    sobre audio 16kHz, la selección de zonas guiadas por energía y la calificación
    acústica por segmento (0-10).
    """
    import wave
    import main_daemon

    analyzer = main_daemon.skill_transcriber
    wav_path = tmp_path / "stream_audio.wav"
    sr = 16000
    # 20 segundos: 0-10s silencio/bajo volumen, 10-18s grito/risa de alta energía, 18-20s bajo
    t = np.linspace(0, 20.0, sr * 20, endpoint=False)
    signal = np.zeros_like(t)
    signal[: sr * 10] = 0.015 * np.sin(2 * np.pi * 220 * t[: sr * 10])
    signal[sr * 10 : sr * 18] = 0.88 * np.sin(2 * np.pi * 440 * t[sr * 10 : sr * 18])
    signal[sr * 18 :] = 0.02 * np.sin(2 * np.pi * 220 * t[sr * 18 :])
    pcm16 = np.clip(signal * 32767, -32768, 32767).astype(np.int16)

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm16.tobytes())

    energy_profile = analyzer.analyze_audio_energy_profile(wav_path, window_sec=1.0)
    assert len(energy_profile) >= 18

    quiet_score = analyzer.compute_segment_acoustic_score(energy_profile, 0.0, 9.0)
    loud_score = analyzer.compute_segment_acoustic_score(energy_profile, 10.0, 18.0)
    assert loud_score >= 7.5, f"El tramo de alta energía debe puntuar >= 7.5 (obtuvo {loud_score})"
    assert quiet_score <= 3.5, f"El tramo silencioso debe puntuar <= 3.5 (obtuvo {quiet_score})"
    assert loud_score > quiet_score + 4.0

    # Verificar que select_peak_guided_zones priorice las ventanas con picos reales
    zones = analyzer.select_peak_guided_zones(
        energy_profile=energy_profile,
        duration_sec=20.0,
        num_zones=2,
        window_len=6.0,
    )
    assert len(zones) == 2
    assert any(z <= 12.0 and z + 6.0 >= 14.0 for z in zones)


def test_multiplatform_url_and_download_sections_support(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Mejora 2 (Stage 1): Verifica soporte de URLs de YouTube, Twitch y Kick +
    descarga de rangos específicos (--download-sections / download_ranges).
    """
    import main_daemon

    assert main_daemon.parse_timecode_to_seconds("00:10:30") == 630.0
    assert main_daemon.parse_timecode_to_seconds("05:15") == 315.0
    assert main_daemon.parse_timecode_to_seconds("90") == 90.0

    captured_calls: List[Dict[str, Any]] = []

    def _fake_bg(video_path: Any, overrides: Dict[str, Any], youtube_url: Optional[str] = None) -> None:
        captured_calls.append({"video_path": video_path, "overrides": overrides, "url": youtube_url})

    monkeypatch.setattr(api_server, "_run_pipeline_background", _fake_bg)

    for valid_url in (
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.twitch.tv/videos/2199887766",
        "https://kick.com/creadorstudio/videos/abcd-1234",
    ):
        res = client.post(
            "/api/pipeline/process",
            json={
                "source_type": "youtube_url",
                "youtube_url": valid_url,
                "download_section_start": "00:05:00",
                "download_section_end": "00:15:00",
                "content_category": "videojuegos",
                "shorts_per_video": 4,
                "layout_mode": "auto",
                "bgm_mood": "desactivada",
                "auto_upload_to_youtube": True,
            },
        )
        assert res.status_code == 200, f"Falló URL válida {valid_url}: {res.text}"

    assert len(captured_calls) == 3
    assert captured_calls[-1]["overrides"]["download_section_start"] == "00:05:00"
    assert captured_calls[-1]["overrides"]["download_section_end"] == "00:15:00"


def test_kalman_filter_smooth_face_tracking_and_dynamic_crop() -> None:
    """
    Mejora 3 (Stage 4): Verifica el Filtro de Kalman 1D para suavizar el seguimiento
    facial sin tirones (jitter) y la generación de expresión dinámica de recorte 9:16.
    """
    import main_daemon

    renderer = main_daemon.skill_renderer
    smoother = renderer.KalmanFaceSmoother1D(process_variance=1.5, measurement_variance=45.0)

    # Simular un hablante moviéndose de X=650 a X=1150 con ruido/jitter brusco
    raw_xs = [650, 790, 620, 710, 880, 740, 920, 1080, 950, 1140, 1160]
    smoothed_xs = [smoother.update(float(x)) for x in raw_xs]

    raw_deltas = np.abs(np.diff(raw_xs))
    smooth_deltas = np.abs(np.diff(smoothed_xs))
    assert float(np.max(smooth_deltas)) < float(np.max(raw_deltas)), "Kalman debe reducir los saltos bruscos (jitter)"

    keyframes = [
        (0.0, smoothed_xs[0]),
        (3.0, smoothed_xs[5]),
        (6.0, smoothed_xs[-1]),
    ]
    crop_expr = renderer.build_kalman_fullscreen_crop_expr(
        keyframes=keyframes,
        crop_w=608,
        frame_w=1920,
    )
    assert "if(lt(t," in crop_expr or crop_expr.isdigit()


def test_hybrid_virality_scoring_with_llm_axes_and_acoustic_energy() -> None:
    """
    Mejora 4 (Stage 3.2): Verifica la puntuación híbrida combinando los 3 ejes del LLM
    (hook_strength, standalone_value, virality_potential), la energía acústica (0-10)
    y la matriz de 10 puntos por categoría.
    """
    import main_daemon

    analyzer = main_daemon.skill_transcriber
    scorer = main_daemon.skill_virality

    cand = analyzer.ViralSegmentCandidate(
        start_time=10.0,
        end_time=52.0,
        hook_title='🔥 "EL SECRETO QUE NADIE CUENTA" 😱 #Shorts',
        first_person_caption="😱 Mira por qué esto cambió todo #Viral #Shorts",
        tags=["CreadorStudio", "Shorts"],
        bgm_mood="impacto",
        hook_strength=9.5,
        standalone_value=9.2,
        virality_potential=9.6,
        acoustic_energy_score=9.4,
    )
    assert cand.hook_strength == 9.5
    assert cand.acoustic_energy_score == 9.4

    base_eval = scorer.evaluate_virality_10_points(
        text="Mira este momento interesante donde hablamos del tema en directo con todos ustedes.",
        duration=45.0,
        words=[],
        title=cand.hook_title,
        category="reacciones",
        llm_scores={"hook_strength": 4.0, "standalone_value": 4.0, "virality_potential": 4.0},
        acoustic_score=2.0,
    )
    high_eval = scorer.evaluate_virality_10_points(
        text="Mira este momento interesante donde hablamos del tema en directo con todos ustedes.",
        duration=45.0,
        words=[],
        title=cand.hook_title,
        category="reacciones",
        llm_scores={"hook_strength": 9.6, "standalone_value": 9.4, "virality_potential": 9.8},
        acoustic_score=9.5,
    )
    assert high_eval.total_points > base_eval.total_points + 10
    assert 0 <= high_eval.total_points <= 100


def test_zero_popup_console_windows_on_subprocesses(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Verifica que:
    1) main_daemon.enable_silent_windows_subprocesses() inyecte automáticamente
       CREATE_NO_WINDOW (0x08000000) y SW_HIDE en cualquier subprocess.Popen / subprocess.run
       (incluyendo llamadas internas de yt-dlp, faster-whisper y FFmpeg) para jamás abrir
       pantallazos de consola ni robar el foco del teclado en Windows.
    2) Todos los módulos de skills (analyzer.py, renderer.py, instagram_scheduler.py,
       instagram_api_uploader.py) usen explícitamente flags silenciosos en sus llamadas FFmpeg.
    """
    import subprocess
    import main_daemon

    main_daemon.enable_silent_windows_subprocesses()

    # Verificar que subprocess.Popen ahora sea la clase envolvente silenciosa en Windows
    assert getattr(subprocess.Popen, "_is_short_yt_silent_popen", False) is True

    # Ejecutar un comando real inofensivo sin pasar creationflags y comprobar que el proceso hijo lleva CREATE_NO_WINDOW
    proc = subprocess.Popen(
        ["cmd.exe", "/c", "echo silent_ok"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    out, _ = proc.communicate(timeout=5)
    assert "silent_ok" in out
    assert getattr(proc, "_injected_creationflags", 0) & 0x08000000 != 0

    # Auditar código fuente de los 4 módulos de skills que invocan FFmpeg
    project_root = Path(__file__).resolve().parent.parent
    skill_files = [
        project_root / ".agents" / "skills" / "video-transcriber-analyzer" / "analyzer.py",
        project_root / ".agents" / "skills" / "vertical-crop-renderer" / "renderer.py",
        project_root / ".agents" / "skills" / "multi-social-uploader" / "instagram_scheduler.py",
        project_root / ".agents" / "skills" / "multi-social-uploader" / "instagram_api_uploader.py",
    ]
    for sf in skill_files:
        src = sf.read_text(encoding="utf-8")
        assert "CREATE_NO_WINDOW" in src or "0x08000000" in src, (
            f"El archivo {sf.name} debe usar CREATE_NO_WINDOW explícitamente en sus subprocesos FFmpeg"
        )


def test_boundary_snap_and_contextual_narrative_arcs_never_cut_mid_sentence() -> None:
    """snap_clip_boundaries_to_context y extract_contextual_narrative_arcs deben alinear cortes a pausas/oraciones y soportar hasta 24 arcos."""
    import sys

    skills_dir = Path(__file__).resolve().parent.parent / ".agents" / "skills" / "video-transcriber-analyzer"
    if str(skills_dir) not in sys.path:
        sys.path.insert(0, str(skills_dir))
    import analyzer

    # Construir palabras sintéticas formando oraciones completas con pausas claras de >0.7s
    words = []
    t = 0.5
    sentences = [
        ("Primero tenemos que entender por qué este torneo cambió todo el juego aquí.", 8.0),
        ("La primera ronda fue completamente brutal porque nadie esperaba ese ataque sorpresa.", 12.0),
        ("Y entonces cuando todos pensaban que estaba perdido pasó algo increíble.", 12.0),
        ("Escucha esto hermano porque aquí viene el secreto que nadie te cuenta.", 10.0),
        ("La verdad es que nosotros practicamos seis horas diarias para dominar esta jugada.", 14.0),
        ("Al final conseguimos la victoria épica que dejó al estadio entero gritando locura.", 14.0),
    ]
    for idx_s, (sent_text, _dur) in enumerate(sentences):
        tokens = sent_text.split()
        for tok in tokens:
            words.append(
                analyzer.WordTimestamp(
                    word=tok,
                    start=round(t, 2),
                    end=round(t + 0.45, 2),
                    probability=0.95,
                )
            )
            t += 0.55
        # Pausa entre oraciones
        t += 0.9 if idx_s % 2 == 0 else 1.2

    # Un límite propuesto a mitad de la oración 2 debe ajustarse hacia la frontera de oración más cercana
    mid_sentence_start = words[15].start
    mid_sentence_end = words[-8].end
    snapped_start, snapped_end = analyzer.snap_clip_boundaries_to_context(
        words=words,
        proposed_start=mid_sentence_start,
        proposed_end=mid_sentence_end,
        min_duration=20.0,
        max_duration=180.0,
    )
    assert snapped_end - snapped_start >= 20.0
    # El inicio ajustado debe coincidir con inicio de oración (palabra anterior terminó con puntuación o pausa >= 0.6s)
    start_idx = min(range(len(words)), key=lambda i: abs(words[i].start - snapped_start))
    if start_idx > 0:
        prev_w = words[start_idx - 1]
        gap = words[start_idx].start - prev_w.end
        assert prev_w.word.endswith((".", "?", "!")) or gap >= 0.6

    # Verificar que extract_contextual_narrative_arcs genere múltiples arcos contextuales sin cortar oraciones
    arcs = analyzer.extract_contextual_narrative_arcs(
        word_timestamps=words,
        target_count=3,
        energy_profile=[],
    )
    assert len(arcs) >= 1
    for arc in arcs:
        assert 20.0 <= (arc.end_time - arc.start_time) <= 180.0
        assert arc.hook_title.strip()
        assert arc.first_person_caption.strip()


def test_pipeline_accepts_up_to_24_shorts_for_long_streams(client: TestClient, temp_workspace: Path) -> None:
    """POST /api/pipeline/process debe aceptar shorts_per_video=24 sin 422 y respetar le=24."""
    from unittest.mock import patch

    with patch("api_server._run_pipeline_background") as mock_bg:
        response = client.post(
            "/api/pipeline/process",
            json={
                "source_type": "inbox",
                "video_filename": "test_stream_x3.mp4",
                "shorts_per_video": 24,
                "layout_mode": "auto",
                "bgm_mood": "auto",
                "auto_upload_to_youtube": False,
                "subtitle_preset": "nexus_cyber_glow",
                "subtitle_position": "auto",
            },
        )
    assert response.status_code in (200, 202), response.text
    mock_bg.assert_called_once()
    resp_invalid = client.post(
        "/api/pipeline/process",
        json={
            "source_type": "inbox",
            "video_filename": "test_stream_x3.mp4",
            "shorts_per_video": 25,
            "layout_mode": "auto",
            "bgm_mood": "auto",
            "auto_upload_to_youtube": False,
        },
    )
    assert resp_invalid.status_code == 422


def test_nexus_layouts_and_custom_normalized_boxes_in_renderer(tmp_path: Path) -> None:
    """norm_box_to_even_px y nuevos layouts (floating_cam_top, floating_circle, blur_16_9_cam) deben renderizar MP4 1080x1920 reales."""
    import sys
    import cv2
    import numpy as np

    skills_dir = Path(__file__).resolve().parent.parent / ".agents" / "skills" / "vertical-crop-renderer"
    analyzer_dir = Path(__file__).resolve().parent.parent / ".agents" / "skills" / "video-transcriber-analyzer"
    for d in (skills_dir, analyzer_dir):
        if str(d) not in sys.path:
            sys.path.insert(0, str(d))
    import renderer
    from analyzer import WordTimestamp

    px_box = renderer.norm_box_to_even_px((0.02, 0.72, 0.24, 0.25), 1920, 1080)
    assert len(px_box) == 4
    assert all(v % 2 == 0 for v in px_box)
    assert px_box[2] >= 64 and px_box[3] >= 64

    # Crear clip sintético 16:9 de 1.5s con audio silencioso real para FFmpeg [0:a]
    raw_vid = tmp_path / "raw_16_9.mp4"
    sample_vid = tmp_path / "sample_16_9.mp4"
    writer = cv2.VideoWriter(str(raw_vid), cv2.VideoWriter_fourcc(*"mp4v"), 15.0, (640, 360))
    for _ in range(24):
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        cv2.rectangle(frame, (20, 200), (180, 340), (40, 180, 240), -1)
        cv2.rectangle(frame, (190, 20), (620, 340), (30, 120, 60), -1)
        writer.write(frame)
    writer.release()
    import subprocess
    subprocess.run(
        [
            renderer.FFMPEG_BIN, "-y",
            "-i", str(raw_vid),
            "-f", "lavfi", "-t", "1.5", "-i", "anullsrc=r=48000:cl=stereo",
            "-c:v", "copy", "-c:a", "aac", "-shortest",
            str(sample_vid),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        **renderer._silent_subprocess_kwargs(),
    )

    words = [
        WordTimestamp(word="Hola", start=0.1, end=0.4, probability=0.98),
        WordTimestamp(word="equipo", start=0.45, end=0.8, probability=0.98),
    ]
    out_dir = tmp_path / "out"
    for mode in ("floating_cam_top", "floating_circle", "blur_16_9_cam"):
        out_mp4 = renderer.render_vertical_short(
            video_path=sample_vid,
            start_time=0.0,
            end_time=1.2,
            word_timestamps=words,
            output_dir=out_dir,
            output_filename=f"short_{mode}.mp4",
            layout_mode=mode,
            enable_bgm=False,
            enable_dynamic_zoom=False,
            enable_hook_punchin=False,
            custom_cam_box_norm=(0.03, 0.55, 0.25, 0.38),
            custom_content_box_norm=(0.30, 0.05, 0.67, 0.88),
            cam_overlay_pos="top_right",
            subtitle_preset="nexus_cyber_glow",
            subtitle_position="bottom",
        )
        assert out_mp4.exists()
        assert out_mp4.stat().st_size > 2000


def test_subtitle_style_presets_and_vertical_positions(tmp_path: Path) -> None:
    """SUBTITLE_STYLE_PRESETS y generate_dynamic_ass_subtitles deben soportar los 6 presets y posiciones top/center/bottom/auto."""
    import sys

    skills_dir = Path(__file__).resolve().parent.parent / ".agents" / "skills" / "vertical-crop-renderer"
    analyzer_dir = Path(__file__).resolve().parent.parent / ".agents" / "skills" / "video-transcriber-analyzer"
    for d in (skills_dir, analyzer_dir):
        if str(d) not in sys.path:
            sys.path.insert(0, str(d))
    import renderer
    from analyzer import WordTimestamp

    expected_keys = {
        "hormozi_pop",
        "nexus_cyber_glow",
        "one_word_punch",
        "clean_apple_box",
        "karaoke_duo",
        "none",
    }
    assert expected_keys.issubset(set(renderer.SUBTITLE_STYLE_PRESETS.keys()))

    words = [
        WordTimestamp(word="Primera", start=0.1, end=0.45, probability=0.99),
        WordTimestamp(word="palabra", start=0.5, end=0.9, probability=0.99),
        WordTimestamp(word="brutal", start=0.95, end=1.4, probability=0.99),
    ]
    ass_top = tmp_path / "top_punch.ass"
    renderer.generate_dynamic_ass_subtitles(
        word_timestamps=words,
        output_ass_path=ass_top,
        subtitle_preset="one_word_punch",
        subtitle_position="top",
    )
    txt_top = ass_top.read_text(encoding="utf-8")
    assert "Dialogue:" in txt_top
    assert "\\fscx" in txt_top or "\\t(" in txt_top

    ass_none = tmp_path / "none.ass"
    renderer.generate_dynamic_ass_subtitles(
        word_timestamps=words,
        output_ass_path=ass_none,
        subtitle_preset="none",
        subtitle_position="auto",
    )
    assert "Dialogue:" not in ass_none.read_text(encoding="utf-8")


def test_scene_detect_and_layout_presets_endpoints(client: TestClient, temp_workspace: Path) -> None:
    """GET /api/subtitles/presets, POST /api/scene/detect, GET /api/media/scene-frame y CRUD /api/layout-presets deben funcionar."""
    import cv2
    import numpy as np

    res_subs = client.get("/api/subtitles/presets")
    assert res_subs.status_code == 200
    sub_data = res_subs.json()
    assert len(sub_data["presets"]) >= 6
    assert any(p["id"] == "nexus_cyber_glow" for p in sub_data["presets"])

    inbox_vid = temp_workspace / "inbox_videos" / "studio_sample.mp4"
    writer = cv2.VideoWriter(str(inbox_vid), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (640, 360))
    for _ in range(15):
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        cv2.rectangle(frame, (15, 210), (160, 340), (60, 170, 220), -1)
        writer.write(frame)
    writer.release()

    res_detect = client.post(
        "/api/scene/detect",
        json={"source_type": "inbox", "video_filename": "studio_sample.mp4"},
    )
    assert res_detect.status_code == 200, res_detect.text
    det = res_detect.json()
    assert "cam_box_norm" in det and len(det["cam_box_norm"]) == 4
    assert "content_box_norm" in det and len(det["content_box_norm"]) == 4
    assert det["frame_url"].startswith("/api/media/scene-frame")

    res_frame = client.get(det["frame_url"])
    assert res_frame.status_code == 200
    assert res_frame.headers["content-type"].startswith("image/jpeg")

    res_create = client.post(
        "/api/layout-presets",
        json={
            "name": "Setup Warzone Cam",
            "layout_mode": "floating_circle",
            "cam_box_norm": [0.02, 0.70, 0.22, 0.26],
            "content_box_norm": [0.15, 0.0, 0.72, 1.0],
            "cam_overlay_pos": "top_right",
            "subtitle_preset": "nexus_cyber_glow",
            "subtitle_position": "bottom",
        },
    )
    assert res_create.status_code == 200, res_create.text
    preset_id = res_create.json()["id"]

    res_list = client.get("/api/layout-presets")
    assert res_list.status_code == 200
    assert any(p["id"] == preset_id and p["name"] == "Setup Warzone Cam" for p in res_list.json()["presets"])

    res_del = client.delete(f"/api/layout-presets/{preset_id}")
    assert res_del.status_code == 200
    res_list2 = client.get("/api/layout-presets")
    assert not any(p["id"] == preset_id for p in res_list2.json()["presets"])


def test_discover_candidates_and_render_selected_workflow(client: TestClient, temp_workspace: Path) -> None:
    """POST /api/pipeline/discover, GET /api/pipeline/candidates y POST /api/pipeline/render-selected deben permitir pre-selección de clips."""
    import sys
    from unittest.mock import patch

    analyzer_dir = Path(__file__).resolve().parent.parent / ".agents" / "skills" / "video-transcriber-analyzer"
    if str(analyzer_dir) not in sys.path:
        sys.path.insert(0, str(analyzer_dir))
    import analyzer

    # Crear video de muestra en inbox
    vid_path = temp_workspace / "inbox_videos" / "discovery_stream.mp4"
    vid_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    fake_analyses = [
        analyzer.ViralClipAnalysis(
            start_time=12.0,
            end_time=44.5,
            hook_title='🔥 "EL TRUCO QUE CAMBIÓ EL TORNEO" 😱 #Shorts',
            first_person_caption="Mira esta jugada épica #Shorts",
            tags=["Shorts", "Viral"],
            bgm_mood="impacto",
            hook_strength=9.2,
            standalone_value=9.0,
            virality_potential=9.4,
            acoustic_energy_score=8.5,
            word_timestamps=[
                analyzer.WordTimestamp(word="Mira", start=0.2, end=0.5, probability=0.95),
                analyzer.WordTimestamp(word="esto.", start=0.55, end=0.9, probability=0.95),
            ],
            keep_intervals=[(0.0, 32.5)],
            transcript_excerpt="Mira esto hermano porque nadie esperaba este giro en la final.",
        ),
        analyzer.ViralClipAnalysis(
            start_time=120.0,
            end_time=165.0,
            hook_title='🔥 "POR QUÉ CASI PERDEMOS TODO" 😱 #Shorts',
            first_person_caption="Historia real #Shorts",
            tags=["Shorts", "Gaming"],
            bgm_mood="misterio",
            hook_strength=8.1,
            standalone_value=8.4,
            virality_potential=8.0,
            acoustic_energy_score=7.8,
            word_timestamps=[
                analyzer.WordTimestamp(word="Escucha", start=0.1, end=0.4, probability=0.95),
                analyzer.WordTimestamp(word="bien.", start=0.45, end=0.85, probability=0.95),
            ],
            keep_intervals=[(0.0, 45.0)],
            transcript_excerpt="Escucha bien lo que pasó después de esa ronda tan tensa.",
        ),
    ]

    with patch("api_server.skill_analyzer.transcribe_and_analyze_multiple", return_value=fake_analyses):
        res_disc = client.post(
            "/api/pipeline/discover",
            json={
                "source_type": "inbox",
                "video_filename": "discovery_stream.mp4",
                "shorts_per_video": 12,
                "content_category": "auto",
            },
        )
    assert res_disc.status_code in (200, 202), res_disc.text
    disc_data = res_disc.json()
    assert len(disc_data["candidates"]) == 2

    res_list = client.get("/api/pipeline/candidates")
    assert res_list.status_code == 200
    cands = res_list.json()["candidates"]
    assert len(cands) == 2
    assert cands[0]["virality_score"] >= cands[1]["virality_score"]
    first_id = cands[0]["candidate_id"]

    with patch("api_server._render_selected_background") as mock_render_bg:
        res_sel = client.post(
            "/api/pipeline/render-selected",
            json={
                "candidate_ids": [first_id],
                "layout_mode": "floating_circle",
                "cam_overlay_pos": "top_right",
                "custom_cam_box_norm": [0.02, 0.70, 0.22, 0.25],
                "custom_content_box_norm": [0.25, 0.02, 0.72, 0.96],
                "subtitle_preset": "nexus_cyber_glow",
                "subtitle_position": "bottom",
                "bgm_mood": "auto",
                "auto_upload_to_youtube": False,
            },
        )
    assert res_sel.status_code in (200, 202), res_sel.text
    assert res_sel.json()["selected_count"] == 1
    mock_render_bg.assert_called_once()


def test_local_ready_mode_skips_auto_upload_and_leaves_shorts_ready_at_100_percent(client: TestClient, monkeypatch) -> None:
    """
    TDD:
    1) api_server.DEFAULT_SETTINGS, main_daemon.DEFAULT_SETTINGS y PipelineProcessRequest
       deben iniciar en modo local-ready (auto_upload_to_youtube=False, enable_social_distribution=False).
    2) Al ejecutar main_daemon.process_video_pipeline sin habilitar subida/distribución social,
       NO debe invocar get_and_reserve_next_slot, upload_scheduled_short, enqueue_instagram_reel ni enqueue_tiktok_video,
       incluso cuando el clip sea categoría Oro (>= 85 pts), y debe generar su _meta.json sidecar en ./output_shorts/.
    3) GET /api/shorts sobre ese Short local-ready debe devolver requires_schedule_confirmation=False,
       upload_progress_percent=100 y 'Listo en local' en upload_status_detail.
    """
    import main_daemon

    assert api_server.DEFAULT_SETTINGS["auto_upload_to_youtube"] is False
    assert api_server.DEFAULT_SETTINGS["enable_social_distribution"] is False
    assert main_daemon.DEFAULT_SETTINGS["auto_upload_to_youtube"] is False
    assert main_daemon.DEFAULT_SETTINGS["enable_social_distribution"] is False

    req_default = api_server.PipelineProcessRequest(
        source_type="inbox",
        video_filename="demo.mp4",
    )
    assert req_default.auto_upload_to_youtube is False
    assert req_default.enable_social_distribution is False

    monkeypatch.setattr(main_daemon, "INBOX_DIR", api_server.INBOX_DIR)
    monkeypatch.setattr(main_daemon, "PROCESSING_DIR", api_server.PROCESSING_DIR)
    monkeypatch.setattr(main_daemon, "OUTPUT_SHORTS_DIR", api_server.OUTPUT_SHORTS_DIR)
    monkeypatch.setattr(main_daemon, "PUBLISHED_ARCHIVE_DIR", api_server.PUBLISHED_ARCHIVE_DIR)
    monkeypatch.setattr(main_daemon, "CONFIG_DIR", api_server.CONFIG_DIR)
    monkeypatch.setattr(main_daemon, "SETTINGS_PATH", api_server.SETTINGS_PATH)
    monkeypatch.setattr(main_daemon, "wait_until_file_ready", lambda p, timeout=30.0: True)
    main_daemon.PIPELINE_CANCEL_EVENT.clear()

    video_path = api_server.INBOX_DIR / "local_ready_stream.mp4"
    video_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    fake_clip = main_daemon.skill_transcriber.ViralClipAnalysis(
        start_time=0.0,
        end_time=50.0,
        hook_title='🔥 "¡INCREÍBLE FINAL IMPOSIBLE EN TORNEO!" 😱 #Shorts',
        first_person_caption="😱 Increíble jugada final épica en directo #Viral #Shorts",
        tags=["CreadorStudio", "Shorts", "Gaming"],
        bgm_mood="impacto",
        word_timestamps=[],
        keep_intervals=[(0.0, 50.0)],
        transcript_excerpt=(
            "¡No puede ser hermano mira esa jugada increíble imposible en el último segundo "
            "del torneo ganamos la partida épica!"
        ),
    )

    monkeypatch.setattr(
        main_daemon.skill_transcriber,
        "transcribe_and_analyze_multiple",
        lambda *a, **kw: [fake_clip],
    )

    rendered_files: List[Path] = []

    def _fake_render_short(**kwargs: Any) -> Path:
        out_dir = Path(kwargs["output_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / kwargs["output_filename"]
        out_file.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        rendered_files.append(out_file)
        return out_file

    monkeypatch.setattr(main_daemon.skill_renderer, "render_vertical_short", _fake_render_short)

    forbidden_calls: List[str] = []
    monkeypatch.setattr(
        main_daemon.skill_scheduler,
        "get_and_reserve_next_slot",
        lambda *a, **kw: forbidden_calls.append("scheduler") or "2026-11-13T18:00:00Z",
    )
    monkeypatch.setattr(
        main_daemon.skill_uploader,
        "upload_scheduled_short",
        lambda *a, **kw: forbidden_calls.append("uploader") or {"id": "should_not_upload"},
    )
    monkeypatch.setattr(
        main_daemon.skill_ig_scheduler,
        "enqueue_instagram_reel",
        lambda *a, **kw: forbidden_calls.append("ig") or 1,
    )
    monkeypatch.setattr(
        main_daemon.skill_tt_scheduler,
        "enqueue_tiktok_video",
        lambda *a, **kw: forbidden_calls.append("tiktok") or 1,
    )

    main_daemon.process_video_pipeline(
        video_path,
        cli_overrides={"shorts_per_video": 1, "content_category": "videojuegos"},
    )

    assert forbidden_calls == [], f"No debía invocar subidas ni colas sociales: {forbidden_calls}"
    assert len(rendered_files) == 1
    created_mp4 = rendered_files[0]
    assert created_mp4.exists()
    meta_file = created_mp4.with_name(f"{created_mp4.stem}_meta.json")
    assert meta_file.exists(), "Debe guardar metadata _meta.json en modo Local-Ready"

    api_server.PIPELINE_STATE["status"] = "COMPLETED"
    api_server.PIPELINE_STATE["requires_schedule_confirmation"] = False

    res_shorts = client.get("/api/shorts")
    assert res_shorts.status_code == 200, res_shorts.text
    payload = res_shorts.json()
    assert payload["summary"]["requires_schedule_confirmation"] is False
    matching = [s for s in payload["shorts"] if s["filename"] == created_mp4.name]
    assert len(matching) == 1
    item = matching[0]
    assert item["upload_progress_percent"] == 100
    assert "Listo en local" in item["upload_status_detail"]


def test_analyzer_ollama_tier_symtable_and_discover_youtube_url_resilience(
    client: TestClient, monkeypatch
) -> None:
    """
    TDD RED -> GREEN:
    1) _analyze_with_local_ollama debe funcionar sin NameError (import math) tanto sin Ollama activo
       como con respuesta JSON válida de Ollama.
    2) Todos los .py del proyecto deben estar libres de referencias a símbolos globales indefinidos (symtable).
    3) POST /api/pipeline/discover con source_type="youtube_url" debe invocar download_youtube_url_max_quality
       con su firma real (url, progress_callback=..., download_section_start=..., download_section_end=...).
    4) POST /api/pipeline/process debe preservar .transcript_cache_<size>.json de videos aún en INBOX_DIR
       durante el pre-cleanup inicial, eliminando cachés huérfanos de otros tamaños.
    """
    import builtins
    import io
    import json
    import symtable
    import urllib.request
    import main_daemon

    analyzer = main_daemon.skill_transcriber
    sample_segments = [
        {
            "start": 0.0,
            "end": 42.0,
            "text": "Hermano mira esta jugada increíble imposible que acaba de pasar en el directo.",
        }
    ]

    # 1a. Sin Ollama activo -> retorna [] sin lanzar NameError: name 'math' is not defined
    def _fail_urlopen(*args, **kwargs):
        raise OSError("Ollama offline")

    monkeypatch.setattr(urllib.request, "urlopen", _fail_urlopen)
    assert analyzer._analyze_with_local_ollama(sample_segments, max_shorts=4) == []

    # 1b. Con Ollama activo -> parsea respuesta {"clips": [...]} correctamente
    class _FakeResp:
        def __init__(self, payload: bytes) -> None:
            self._buf = io.BytesIO(payload)

        def read(self) -> bytes:
            return self._buf.getvalue()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _fake_urlopen(req, timeout=2.0):
        full_url = getattr(req, "full_url", str(req))
        if "/api/tags" in full_url:
            return _FakeResp(json.dumps({"models": [{"name": "qwen2.5:7b"}]}).encode("utf-8"))
        return _FakeResp(
            json.dumps(
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "clips": [
                                    {
                                        "start_time": 0.0,
                                        "end_time": 40.0,
                                        "hook_title": "🔥 JUGADA IMPOSIBLE #Shorts",
                                        "first_person_caption": "😱 Increíble jugada #Viral #Shorts",
                                        "tags": ["Gaming", "Zelda", "CreadorStudio", "Shorts"],
                                        "bgm_mood": "impacto",
                                    }
                                ]
                            }
                        )
                    }
                }
            ).encode("utf-8")
        )

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    ollama_cands = analyzer._analyze_with_local_ollama(sample_segments, max_shorts=4)
    assert len(ollama_cands) == 1
    assert ollama_cands[0].end_time == 40.0

    # 2. Auditoría symtable en todo el repositorio Python (excluyendo .venv/node_modules/__pycache__)
    builtin_names = set(dir(builtins)) | {
        "__file__",
        "__name__",
        "__doc__",
        "__package__",
        "__annotations__",
    }
    project_root = Path(__file__).resolve().parent.parent
    symtable_issues = []

    def _walk_sym(st, globals_def, rel_path: str) -> None:
        for sym in st.get_symbols():
            if sym.is_global() and not sym.is_assigned() and not sym.is_imported():
                if sym.get_name() not in globals_def and sym.get_name() not in builtin_names:
                    symtable_issues.append(f"{rel_path}:{st.get_lineno()} ({st.get_name()}) -> {sym.get_name()}")
        for ch in st.get_children():
            _walk_sym(ch, globals_def, rel_path)

    for py_path in sorted(project_root.rglob("*.py")):
        if any(part in py_path.parts for part in (".venv", "node_modules", "__pycache__")):
            continue
        src = py_path.read_text(encoding="utf-8", errors="replace")
        top = symtable.symtable(src, str(py_path), "exec")
        gdef = {
            s.get_name()
            for s in top.get_symbols()
            if s.is_assigned() or s.is_imported() or s.is_namespace()
        }
        rel = str(py_path.relative_to(project_root))
        for sym in top.get_symbols():
            if sym.is_referenced() and not (sym.is_assigned() or sym.is_imported() or sym.is_namespace()):
                if sym.get_name() not in builtin_names:
                    symtable_issues.append(f"{rel}:1 (module) -> {sym.get_name()}")
        _walk_sym(top, gdef, rel)

    assert symtable_issues == [], f"Símbolos globales indefinidos detectados: {symtable_issues}"

    # 3. POST /api/pipeline/discover con youtube_url y firma real de download_youtube_url_max_quality
    downloaded_video = api_server.INBOX_DIR / "yt_discovered.mp4"
    downloaded_video.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    captured_dl: Dict[str, Any] = {}

    def _real_sig_download(
        url: str,
        progress_callback=None,
        download_section_start=None,
        download_section_end=None,
    ) -> Path:
        captured_dl["url"] = url
        captured_dl["start"] = download_section_start
        captured_dl["end"] = download_section_end
        return downloaded_video

    monkeypatch.setattr(
        api_server._main_daemon_bootstrap,
        "download_youtube_url_max_quality",
        _real_sig_download,
    )
    monkeypatch.setattr(
        api_server.skill_analyzer,
        "transcribe_and_analyze_multiple",
        lambda **kwargs: [
            analyzer.ViralClipAnalysis(
                start_time=0.0,
                end_time=40.0,
                hook_title="🔥 DESDE YOUTUBE #Shorts",
                first_person_caption="😱 Clip #Viral #Shorts",
                tags=["Gaming", "CreadorStudio", "Shorts"],
                bgm_mood="impacto",
                word_timestamps=[],
                keep_intervals=[(0.0, 40.0)],
                transcript_excerpt="Jugada increíble desde YouTube URL con sección.",
            )
        ],
    )
    res_disc = client.post(
        "/api/pipeline/discover",
        json={
            "source_type": "youtube_url",
            "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "shorts_per_video": 4,
            "content_category": "videojuegos",
            "download_section_start": "00:01:00",
            "download_section_end": "00:05:00",
        },
    )
    assert res_disc.status_code == 200, res_disc.text
    assert captured_dl == {
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "start": "00:01:00",
        "end": "00:05:00",
    }

    # 4. POST /api/pipeline/process preserva caché de videos en INBOX_DIR y borra cachés huérfanos
    active_video = api_server.INBOX_DIR / "active_inbox_video.mp4"
    active_video.write_bytes(b"ACTIVE_STREAM_BYTES_123456")
    active_cache = api_server.PROCESSING_DIR / f".transcript_cache_{active_video.stat().st_size}.json"
    active_cache.write_text('{"segments": [], "words": []}', encoding="utf-8")
    orphan_cache = api_server.PROCESSING_DIR / ".transcript_cache_999999999.json"
    orphan_cache.write_text('{"segments": [], "words": []}', encoding="utf-8")

    monkeypatch.setattr(api_server, "_run_pipeline_background", lambda *a, **kw: None)
    res_proc = client.post(
        "/api/pipeline/process",
        json={
            "source_type": "inbox",
            "video_filename": "active_inbox_video.mp4",
            "content_category": "videojuegos",
            "shorts_per_video": 4,
            "layout_mode": "auto",
            "bgm_mood": "desactivada",
        },
    )
    assert res_proc.status_code == 200, res_proc.text
    assert active_cache.exists(), "Debe preservar caché de transcripción del video activo en INBOX_DIR"
    assert not orphan_cache.exists(), "Debe limpiar cachés huérfanos que no correspondan a INBOX_DIR"


def test_per_clip_visual_auto_layout_solo_cam_vs_obs_side_by_side(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    RED->GREEN Punto 1:
    - Caso A (Solo Cámara): Incluso con category_hint='realitys', layout_mode='auto' debe resolver 'fullscreen'
      cuando hay rostro centrado dominante sin costura OBS (jamás reality_multicam duplicado).
    - Caso B (OBS Side-by-Side): Con panel izquierdo streamer + costura vertical + panel derecho gameplay,
      incluso con category_hint='opinion_monologo', layout_mode='auto' debe resolver 'split_streamer' sin cruzar la costura.
    - Caso C (gaming_hud explícito sobre OBS Side-by-Side): cam_box y content_box quedan confinados en sus paneles reales.
    """
    renderer_mod = api_server._load_skill_module("vertical-crop-renderer", "renderer.py")
    fps = 10.0
    width, height = 1280, 720
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")

    # Caso A: Solo en cámara (hablante centrado sin costura OBS)
    solo_video = tmp_path / "solo_talking_head.mp4"
    writer_a = cv2.VideoWriter(str(solo_video), fourcc, fps, (width, height))
    for i in range(16):
        frame = np.full((height, width, 3), (38, 22, 52), dtype=np.uint8)
        # Persona grande centrada
        cv2.ellipse(frame, (640, 290), (95, 115), 0, 0, 360, (145, 170, 210), -1)
        cv2.rectangle(frame, (440, 410), (840, 710), (30, 110, 240), -1)
        writer_a.write(frame)
    writer_a.release()

    orig_extract = renderer_mod.SpeakerFaceTracker.extract_bboxes_px

    def _mock_center_face(self, bgr_frame, **kwargs):
        # Si el slice tiene ancho ~563px (zona central 28%..72%), devolver rostro grande centrado
        if bgr_frame.shape[1] >= 480:
            return [(180, 160, 190, 190)]
        return []

    monkeypatch.setattr(renderer_mod.SpeakerFaceTracker, "extract_bboxes_px", _mock_center_face)
    layout_solo = renderer_mod.detect_video_layout_and_regions(
        video_path=solo_video,
        start_time=0.0,
        end_time=1.5,
        layout_mode="auto",
        category_hint="realitys",
    )
    assert layout_solo["mode"] == "fullscreen", f"Solo-cámara no debe usar reality_multicam: {layout_solo}"

    # Restaurar detector real para probar Caso B y C con costura OBS real en píxeles
    monkeypatch.setattr(renderer_mod.SpeakerFaceTracker, "extract_bboxes_px", orig_extract)

    obs_video = tmp_path / "obs_side_by_side.mp4"
    writer_b = cv2.VideoWriter(str(obs_video), fourcc, fps, (width, height))
    for i in range(18):
        frame = np.full((height, width, 3), (8, 8, 8), dtype=np.uint8)
        # Panel Izquierdo Streamer (x=18..342, y=38..680) con contenido y movimiento local
        cv2.rectangle(frame, (18, 38), (342, 680), (70, 32, 80), -1)
        shift = (i % 3) * 14
        cv2.ellipse(frame, (175 + shift, 280), (52, 68), 0, 0, 360, (140, 165, 205), -1)
        cv2.rectangle(frame, (60, 420), (300, 665), (25, 115, 245), -1)
        # Barra naranja estática inferior del overlay (y=684..718)
        cv2.rectangle(frame, (18, 684), (342, 716), (10, 130, 250), -1)
        # Costura oscura OBS entre x=343..361 (se mantiene en BGR=(8,8,8))
        # Panel Derecho Gameplay (x=362..1262, y=38..680) con textura + hearts HUD + acción intensa
        cv2.rectangle(frame, (362, 38), (1262, 680), (75, 92, 70), -1)
        for gx in range(390, 1240, 90):
            cv2.line(frame, (gx, 40), (gx, 678), (58, 72, 54), 2)
        for gy in range(70, 670, 90):
            cv2.line(frame, (364, gy), (1260, gy), (58, 72, 54), 2)
        # Corazones rojos HUD (arriba-izquierda del panel gameplay)
        for h_idx in range(6):
            cv2.circle(frame, (410 + h_idx * 28, 120), 10, (30, 40, 220), -1)
        # Acción de juego intensa en x=620..920
        act_col = (240, 220, 40) if (i % 2 == 0) else (40, 120, 230)
        cv2.rectangle(frame, (640, 260), (920, 520), act_col, -1)
        cv2.rectangle(frame, (362, 684), (1262, 716), (10, 130, 250), -1)
        writer_b.write(frame)
    writer_b.release()

    layout_obs_auto = renderer_mod.detect_video_layout_and_regions(
        video_path=obs_video,
        start_time=0.0,
        end_time=1.7,
        layout_mode="auto",
        category_hint="opinion_monologo",
    )
    assert layout_obs_auto["mode"] == "split_streamer", f"OBS side-by-side debe detectar split_streamer: {layout_obs_auto}"
    cx, cy, cw, ch = layout_obs_auto["cam_box"]
    gx, gy, gw, gh = layout_obs_auto["content_box"]
    assert cx + cw <= 355, f"cam_box cruza costura OBS hacia juego: cam_box={(cx, cy, cw, ch)}"
    assert gx >= 352, f"content_box cruza costura OBS hacia camara: content_box={(gx, gy, gw, gh)}"

    layout_hud = renderer_mod.detect_video_layout_and_regions(
        video_path=obs_video,
        start_time=0.0,
        end_time=1.7,
        layout_mode="gaming_hud",
        category_hint="videojuegos",
    )
    assert layout_hud["mode"] == "gaming_hud"
    hcx, hcy, hcw, hch = layout_hud["cam_box"]
    hgx, hgy, hgw, hgh = layout_hud["content_box"]
    assert hcx + hcw <= 355, f"gaming_hud cam_box cruza costura OBS: {layout_hud['cam_box']}"
    assert hgx >= 352, f"gaming_hud content_box cruza costura OBS: {layout_hud['content_box']}"
    assert hgy + hgh <= 696, f"gaming_hud content_box incluye barra estática inferior: {layout_hud['content_box']}"


def test_scene_detect_uses_extract_bboxes_px_and_shorts_expose_sidecar_metadata(
    client: TestClient, temp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    RED->GREEN Punto 1 + Punto 3:
    - /api/scene/detect debe detectar rostros reales sin AttributeError (sin .detect_faces).
    - /api/shorts debe incluir hook_title, category y layout_used desde sidecars *_meta.json / *_opencut_timeline.json.
    """
    inbox_vid = temp_workspace / "inbox_videos" / "obs_studio_check.mp4"
    writer = cv2.VideoWriter(str(inbox_vid), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (1280, 720))
    for _ in range(12):
        frame = np.full((720, 1280, 3), (35, 35, 35), dtype=np.uint8)
        writer.write(frame)
    writer.release()

    renderer_mod = api_server.skill_renderer
    called = {"extract_count": 0}

    def _fake_extract(self, bgr_frame, **kwargs):
        called["extract_count"] += 1
        h, w = bgr_frame.shape[:2]
        if w >= 900:
            return [(90, 210, 130, 140)]
        if w <= 500:
            return [(85, 210, 125, 135)]
        return []

    monkeypatch.setattr(renderer_mod.SpeakerFaceTracker, "extract_bboxes_px", _fake_extract)

    res_detect = client.post(
        "/api/scene/detect",
        json={"source_type": "inbox", "video_filename": "obs_studio_check.mp4"},
    )
    assert res_detect.status_code == 200, res_detect.text
    det = res_detect.json()
    assert called["extract_count"] >= 1
    assert det["faces_detected"] >= 1
    assert det["detected_layout"] in ("gaming_hud", "split_streamer")

    # Verificar enriquecimiento desde sidecars en GET /api/shorts
    out_folder = api_server.OUTPUT_SHORTS_DIR / "Zelda_Live"
    out_folder.mkdir(parents=True, exist_ok=True)
    mp4_file = out_folder / "Zelda_Live_01_Oro_95pts.mp4"
    mp4_file.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 512)
    mp4_file.with_name(f"{mp4_file.stem}_meta.json").write_text(
        json.dumps(
            {
                "short_filename": mp4_file.name,
                "virality_score": 95,
                "tier": "Oro",
                "category": "videojuegos",
                "hook_title": "EL SECRETO DEL TEMPLO DEL AGUA",
                "layout_used": "split_streamer",
                "duration_sec": 54.2,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    res_shorts = client.get("/api/shorts")
    assert res_shorts.status_code == 200
    items = res_shorts.json()["shorts"]
    target = next(s for s in items if s["filename"] == mp4_file.name)
    assert target["hook_title"] == "EL SECRETO DEL TEMPLO DEL AGUA"
    assert target["category"] == "videojuegos"
    assert target["layout_used"] == "split_streamer"
    assert target["duration_sec"] == 54.2


def test_post_completion_cleanup_ignores_winerror32_locked_file_and_completes_pipeline(
    client: TestClient, temp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Regresión WinError 32 al 96%: Si el archivo en processing/ sigue bloqueado por otro proceso
    (p. ej. streaming HTTP 206 o OneDrive) al terminar los renders, el pipeline debe completar a 100%,
    liberar source_preview_url, conservar los Shorts generados y NO restaurar el video ni marcar ERROR.
    """
    import main_daemon

    client.delete("/api/shorts")
    fake_inbox = temp_workspace / "inbox_videos"
    fake_proc = temp_workspace / "processing"
    fake_out = temp_workspace / "output_shorts"
    fake_arch = temp_workspace / "published_archive"
    fake_cfg = temp_workspace / "config"

    monkeypatch.setattr(main_daemon, "INBOX_DIR", fake_inbox)
    monkeypatch.setattr(main_daemon, "PROCESSING_DIR", fake_proc)
    monkeypatch.setattr(main_daemon, "OUTPUT_SHORTS_DIR", fake_out)
    monkeypatch.setattr(main_daemon, "PUBLISHED_ARCHIVE_DIR", fake_arch)
    monkeypatch.setattr(main_daemon, "CONFIG_DIR", fake_cfg)
    monkeypatch.setattr(main_daemon, "SETTINGS_PATH", fake_cfg / "settings.json")
    monkeypatch.setattr(main_daemon, "wait_until_file_ready", lambda p, timeout=30.0: True)
    main_daemon.PIPELINE_CANCEL_EVENT.clear()

    raw_name = "🟡 CreadorStudio LIVE - Zelda Cap 06 #ZeldaOcarinaOfTime.mp4"
    source_video = fake_inbox / raw_name
    source_video.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 512)

    fake_clips = [
        main_daemon.skill_transcriber.ViralClipAnalysis(
            start_time=10.0,
            end_time=60.0,
            hook_title='🔥 "MOMENTO ÉPICO EN ZELDA" 😱 #Shorts',
            first_person_caption="Momento épico jugando Zelda Cap 06 #Viral #Shorts",
            tags=["CreadorStudio", "Zelda", "Shorts"],
            bgm_mood="impacto",
            word_timestamps=[],
            keep_intervals=[(0.0, 50.0)],
            transcript_excerpt="No vas a creer lo que pasó en el Templo del Tiempo ahora mismo.",
        )
    ]
    monkeypatch.setattr(
        main_daemon.skill_transcriber,
        "transcribe_and_analyze_multiple",
        lambda *a, **kw: fake_clips,
    )

    def _fake_render(**kwargs: Any) -> Path:
        out_dir = Path(kwargs["output_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / kwargs["output_filename"]
        out_file.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 512)
        return out_file

    monkeypatch.setattr(main_daemon.skill_renderer, "render_vertical_short", _fake_render)
    monkeypatch.setattr(main_daemon.skill_cleanup, "clean_processing_dir", lambda **kw: (0, 0.0))
    monkeypatch.setattr(main_daemon.skill_cleanup, "clean_ig_staging_cache", lambda **kw: (0, 0.0))

    orig_unlink = Path.unlink

    def _locked_proc_unlink(self: Path, missing_ok: bool = False) -> None:
        if "processing" in self.parts and self.suffix.lower() == ".mp4":
            raise PermissionError(
                13,
                "[WinError 32] The process cannot access the file because it is being used by another process",
            )
        orig_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", _locked_proc_unlink)

    api_server.PIPELINE_STATE["source_preview_url"] = f"/api/media/source/{raw_name}"
    api_server._run_pipeline_background(
        source_video,
        {"shorts_per_video": 1, "auto_upload_to_youtube": False},
    )

    assert api_server.PIPELINE_STATE["status"] == "COMPLETED"
    assert api_server.PIPELINE_STATE["progress_percent"] == 100
    assert api_server.PIPELINE_STATE["source_preview_url"] is None
    assert not source_video.exists(), "No debe restaurar el video a inbox si los renders ya terminaron"

    shorts_res = client.get("/api/shorts")
    assert shorts_res.status_code == 200
    shorts_payload = shorts_res.json()
    assert shorts_payload["total"] == 1
    rel_path = shorts_payload["shorts"][0]["relative_path"]
    assert "🟡" not in rel_path and "#" not in rel_path
    assert len(str(fake_out / rel_path)) < 220


def test_long_emoji_titles_sanitize_in_studio_render_and_shorts_endpoint_handles_numeric_grade(
    client: TestClient, temp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Regresión MAX_PATH / WinError 3:
    1) sanitize_media_stem limpia emojis/hashtags y limita longitud a <= max_len.
    2) _render_selected_background genera carpeta y MP4 cortos con tier Oro/Plata/Meh.
    3) GET /api/shorts tolera y parsea correctamente archivos legados con nota numérica (ej. _EP_01_9.1_91pts.mp4).
    """
    import main_daemon

    client.delete("/api/shorts")
    raw_long = "🟡 CreadorStudio LIVE - The Legend of Zelda Ocarina of Time Remake - Cap 06 #ZeldaOcarinaOfTime"
    sanitized = main_daemon.sanitize_media_stem(raw_long, max_len=44)
    assert len(sanitized) <= 44
    assert "🟡" not in sanitized
    assert "#" not in sanitized
    assert sanitized.startswith("CreadorStudio_LIVE")

    fake_inbox = temp_workspace / "inbox_videos"
    src_video = fake_inbox / f"{raw_long}.mp4"
    src_video.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 512)

    def _fake_render_studio(**kwargs: Any) -> Path:
        out_dir = Path(kwargs["output_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / kwargs["output_filename"]
        out_file.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 512)
        return out_file

    monkeypatch.setattr(api_server.skill_renderer, "render_vertical_short", _fake_render_studio)

    api_server._render_selected_background(
        job_id="job_san_1",
        selected_candidates=[
            {
                "candidate_id": "cand_01",
                "start_time": 10.0,
                "end_time": 55.0,
                "hook_title": "JEFE FINAL SIN DAÑO",
                "first_person_caption": "Caption corto",
                "tags": ["Zelda"],
                "bgm_mood": "impacto",
                "virality_score": 91,
                "virality_grade": "9.1",
                "word_timestamps": [],
                "keep_intervals": [[0.0, 45.0]],
            }
        ],
        source_video_path=src_video,
        req_cfg={"layout_mode": "auto", "bgm_mood": "auto", "subtitle_preset": "hormozi_pop"},
    )

    assert api_server.PIPELINE_STATE["status"] == "COMPLETED"
    assert api_server.PIPELINE_STATE["source_preview_url"] is None

    rendered = list((temp_workspace / "output_shorts").rglob("*.mp4"))
    assert len(rendered) == 1
    assert len(str(rendered[0])) < 240
    assert "_Oro_91pts.mp4" in rendered[0].name
    assert "🟡" not in str(rendered[0]) and "#" not in str(rendered[0])

    # Archivo legado con formato _EP_01_9.1_91pts.mp4
    legacy_dir = temp_workspace / "output_shorts" / "Legacy_Test"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    legacy_mp4 = legacy_dir / "Legacy_Test_EP_01_9.1_91pts.mp4"
    legacy_mp4.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 512)

    res = client.get("/api/shorts")
    assert res.status_code == 200
    items = res.json()["shorts"]
    leg_item = next(s for s in items if s["filename"] == legacy_mp4.name)
    assert leg_item["virality_score"] == 91
    assert leg_item["tier"] == "Oro"


def test_split_50_50_layout_clean_no_ometv_banner_and_api_accepts(
    client: TestClient, temp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica split_50_50 limpio (1080x960 + 1080x960 sin ometv_banner.png) y aceptación en API."""
    video_file = temp_workspace / "inbox_videos" / "test_stream_x3.mp4"
    info = api_server.skill_renderer.detect_video_layout_and_regions(
        video_file, 0.0, 2.0, layout_mode="split_50_50"
    )
    assert info["mode"] == "split_50_50"
    for box_key in ("cam_box", "content_box"):
        bx, by, bw, bh = info[box_key]
        assert bw > 0 and bh > 0
        assert bx >= 0 and by >= 0
        assert bx + bw <= 640 and by + bh <= 360

    graph = api_server.skill_renderer.build_split_50_50_filter_graph(
        info, "", "flags=lanczos", "", ""
    )
    assert "scale=1080:960" in graph
    assert "vstack=inputs=2" in graph
    assert "ometv" not in graph.lower()

    monkeypatch.setattr(api_server, "_run_pipeline_background", lambda *args, **kwargs: None)
    res = client.post(
        "/api/pipeline/process",
        json={
            "source_type": "inbox",
            "video_filename": "test_stream_x3.mp4",
            "layout_mode": "split_50_50",
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["settings_applied"]["layout_mode"] == "split_50_50"


def test_custom_studio_boxes_never_hijack_non_split_streamer_modes_and_ometv_blur_geometry(
    temp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Cajas custom del Studio no deben secuestrar fullscreen/split_50_50/gaming_hud hacia split_streamer;
    ometv escala proporcionalmente en 1280x720 y blur_16_9_cam conserva panel 16:9 amplio.
    """
    import subprocess

    vid_720p = temp_workspace / "inbox_videos" / "stream_720p_layout.mp4"
    writer = cv2.VideoWriter(str(vid_720p), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (1280, 720))
    for i in range(60):
        frame = np.full((720, 1280, 3), (25, 45, 70), dtype=np.uint8)
        if i % 2 == 0:
            cv2.rectangle(frame, (120, 120), (1160, 600), (60, 110, 170), 3)
        writer.write(frame)
    writer.release()

    ometv_info = api_server.skill_renderer.detect_video_layout_and_regions(
        vid_720p, 0.0, 2.0, layout_mode="ometv"
    )
    assert ometv_info["mode"] == "ometv"
    cx, cy, cw, ch = ometv_info["cam_box"]
    gx, gy, gw, gh = ometv_info["content_box"]
    assert cx >= 0 and cy >= 0 and cx + cw <= 1280 and cy + ch <= 720
    assert gx >= 0 and gy >= 0 and gx + gw <= 1280 and gy + gh <= 720

    blur_info = api_server.skill_renderer.detect_video_layout_and_regions(
        vid_720p, 0.0, 2.0, layout_mode="blur_16_9_cam"
    )
    assert blur_info["mode"] == "blur_16_9_cam"
    assert blur_info["content_box"][2] >= int(1280 * 0.85)

    captured_filters: list[str] = []

    def _fake_subprocess_run(cmd, *args, **kwargs):
        if isinstance(cmd, (list, tuple)) and "-filter_complex" in cmd:
            idx = cmd.index("-filter_complex")
            captured_filters.append(str(cmd[idx + 1]))
            out_file = Path(str(cmd[-1]))
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 512)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(api_server.skill_renderer.subprocess, "run", _fake_subprocess_run)

    custom_cam = [0.02, 0.65, 0.25, 0.30]
    custom_content = [0.28, 0.02, 0.70, 0.94]
    out_dir = temp_workspace / "output_shorts" / "layout_checks"

    api_server.skill_renderer.render_vertical_short(
        video_path=vid_720p,
        start_time=0.0,
        end_time=2.0,
        word_timestamps=[],
        output_dir=out_dir,
        output_filename="check_fullscreen.mp4",
        layout_mode="fullscreen",
        enable_subtitles=False,
        custom_cam_box_norm=custom_cam,
        custom_content_box_norm=custom_content,
    )
    assert "vstack" not in captured_filters[-1]

    api_server.skill_renderer.render_vertical_short(
        video_path=vid_720p,
        start_time=0.0,
        end_time=2.0,
        word_timestamps=[],
        output_dir=out_dir,
        output_filename="check_split5050.mp4",
        layout_mode="split_50_50",
        enable_subtitles=False,
        custom_cam_box_norm=custom_cam,
        custom_content_box_norm=custom_content,
    )
    assert "scale=1080:960" in captured_filters[-1]
    assert "vstack=inputs=2" in captured_filters[-1]

    api_server.skill_renderer.render_vertical_short(
        video_path=vid_720p,
        start_time=0.0,
        end_time=2.0,
        word_timestamps=[],
        output_dir=out_dir,
        output_filename="check_gaming_hud.mp4",
        layout_mode="gaming_hud",
        enable_subtitles=False,
        custom_cam_box_norm=custom_cam,
        custom_content_box_norm=custom_content,
    )
    assert "scale=1080:480" in captured_filters[-1]
    assert "scale=1080:1440" in captured_filters[-1]


def test_timeline_hysteresis_and_scene_detect_centered_solo_fullscreen(
    client: TestClient, temp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica histéresis temporal (>=3s) en clips largos y /api/scene/detect solo-cámara centrado -> fullscreen."""
    smoothed = api_server.skill_renderer._smooth_timeline_states(
        [(0.0, 4.5, "left_full"), (4.5, 6.0, "both_split"), (6.0, 12.0, "left_full")],
        window_sec=1.5,
        total_duration=12.0,
    )
    assert smoothed == [{"start": 0.0, "end": 12.0, "state": "left_full"}]

    solo_vid = temp_workspace / "inbox_videos" / "solo_centered_speaker.mp4"
    writer = cv2.VideoWriter(str(solo_vid), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (1280, 720))
    for _ in range(15):
        frame = np.full((720, 1280, 3), (40, 42, 46), dtype=np.uint8)
        writer.write(frame)
    writer.release()

    def _fake_centered_extract(self, bgr_frame, **kwargs):
        h, w = bgr_frame.shape[:2]
        if w >= 600:
            return [(560, 200, 160, 180)]
        if 500 <= w < 600:
            return [(200, 200, 160, 180)]
        return []

    monkeypatch.setattr(
        api_server.skill_renderer.SpeakerFaceTracker, "extract_bboxes_px", _fake_centered_extract
    )

    res = client.post(
        "/api/scene/detect",
        json={"source_type": "inbox", "video_filename": "solo_centered_speaker.mp4"},
    )
    assert res.status_code == 200, res.text
    det = res.json()
    assert det["detected_layout"] == "fullscreen"


def test_bgm_disabled_everywhere_and_quiet_audio_boosted_cleanly(
    client: TestClient, temp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    BGM queda desactivada por defecto en backend/daemon/API y el audio bajo (-34 dB)
    recibe ganancia lineal limpia con volumedetect + alimiter sin loudnorm ni acompressor.
    """
    import re
    import subprocess
    import imageio_ffmpeg
    import main_daemon

    assert api_server.DEFAULT_SETTINGS["enable_bgm"] is False
    assert api_server.DEFAULT_SETTINGS["default_bgm_mood"] == "desactivada"
    assert main_daemon.DEFAULT_SETTINGS["enable_bgm"] is False
    assert main_daemon.DEFAULT_SETTINGS["default_bgm_mood"] == "desactivada"

    monkeypatch.setattr(api_server, "_run_pipeline_background", lambda *args, **kwargs: None)
    res = client.post(
        "/api/pipeline/process",
        json={
            "source_type": "inbox",
            "video_filename": "test_stream_x3.mp4",
            "bgm_mood": "impacto",
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["settings_applied"]["enable_bgm"] is False

    monkeypatch.setattr(
        api_server.skill_renderer, "_try_fetch_youtube_1080p60_slice", lambda *args, **kwargs: None
    )

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    quiet_src = temp_workspace / "inbox_videos" / "quiet_audio_src.mp4"
    gen_cmd = [
        ffmpeg_exe,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=640x360:rate=30:duration=2.0",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=2.0",
        "-af",
        "volume=-14dB",
        "-ac",
        "2",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(quiet_src),
    ]
    gen_proc = subprocess.run(gen_cmd, capture_output=True, text=True, check=False)
    assert gen_proc.returncode == 0, gen_proc.stderr

    out_dir = temp_workspace / "output_shorts" / "quiet_test"
    out_dir.mkdir(parents=True, exist_ok=True)
    rendered_path = api_server.skill_renderer.render_vertical_short(
        video_path=quiet_src,
        start_time=0.0,
        end_time=2.0,
        word_timestamps=[],
        output_dir=out_dir,
        output_filename="quiet_boost_test.mp4",
        layout_mode="fullscreen",
        enable_subtitles=False,
        enable_bgm=False,
        bgm_mood="desactivada",
    )
    assert rendered_path.exists()

    vol_proc = subprocess.run(
        [ffmpeg_exe, "-hide_banner", "-i", str(rendered_path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert vol_proc.returncode == 0, vol_proc.stderr
    vol_out = f"{vol_proc.stderr}\n{vol_proc.stdout}"
    mean_m = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", vol_out)
    max_m = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", vol_out)
    assert mean_m is not None and max_m is not None, vol_out
    assert float(mean_m.group(1)) >= -18.5
    assert float(max_m.group(1)) <= -0.3

    renderer_path = Path(api_server.skill_renderer.__file__).resolve()
    renderer_src = renderer_path.read_text(encoding="utf-8")
    assert "loudnorm(" not in renderer_src
    assert "loudnorm=" not in renderer_src
    assert "acompressor" not in renderer_src


def test_spanish_subtitle_polishing_fixes_phonetic_errors_and_hallucinations() -> None:
    """Corrige errores fonéticos conocidos en español, elimina alucinaciones Whisper y acota congelamientos."""
    sa = api_server.skill_analyzer

    polished = sa.polish_spanish_transcript_text(
        "Usa Aulut con Antropic y Donald Trum. Subtítulos realizados por Amara.org"
    )
    assert "Outlook" in polished
    assert "Anthropic" in polished
    assert "Donald Trump" in polished
    assert "Aulut" not in polished
    assert "Amara.org" not in polished

    words = [
        sa.WordTimestamp(word="Usa", start=0.0, end=0.3),
        sa.WordTimestamp(word="Aulut", start=0.3, end=0.6),
        sa.WordTimestamp(word="Antropic", start=0.6, end=0.9),
        sa.WordTimestamp(word="Donald", start=0.9, end=1.1),
        sa.WordTimestamp(word="Trum", start=1.1, end=6.1),
        sa.WordTimestamp(word="Subtítulos", start=6.2, end=6.4),
        sa.WordTimestamp(word="realizados", start=6.4, end=6.6),
        sa.WordTimestamp(word="por", start=6.6, end=6.8),
        sa.WordTimestamp(word="Amara.org", start=6.8, end=7.0),
    ]
    cleaned = sa.clean_and_polish_word_timestamps(words, clip_duration=8.0)
    assert [w.word for w in cleaned] == ["Usa", "Outlook", "Anthropic", "Donald", "Trump"]
    assert cleaned[-1].end - cleaned[-1].start <= 1.4001


def test_post_preview_short_layout_rerender_and_bgm_hard_lock(
    temp_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifica bloqueo estricto sin BGM (-14 dBFS), creación .srcclip y re-renderizado post-preview."""
    import re
    import subprocess
    from imageio_ffmpeg import get_ffmpeg_exe

    monkeypatch.setattr(api_server.skill_renderer, "_try_fetch_youtube_1080p60_slice", lambda *a, **kw: None)

    ffmpeg_exe = get_ffmpeg_exe()
    out_dir = temp_workspace / "output_shorts" / "test_stream"
    target_mp4 = out_dir / "test_stream_01_Oro_92pts.mp4"
    srcclip_path = out_dir / "test_stream_01_Oro_92pts.srcclip"

    # Generar fuente 16:9 limpia (1280x720) con audio tonal bajo para .srcclip
    cmd = [
        ffmpeg_exe,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=1280x720:rate=30:duration=1.5",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000:duration=1.5",
        "-af",
        "volume=-26dB",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-ac",
        "2",
        "-f",
        "mp4",
        str(srcclip_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr

    # 1) Probar que incluso pidiendo enable_bgm=True y bgm_mood="comedia", renderer lo bloquea y omite audio-bgm-acestep
    hard_lock_out = api_server.skill_renderer.render_vertical_short(
        video_path=srcclip_path,
        start_time=0.0,
        end_time=1.4,
        word_timestamps=[{"word": "Prueba", "start": 0.1, "end": 0.5}],
        output_dir=out_dir,
        output_filename="bgm_locked_check.mp4",
        layout_mode="fullscreen",
        enable_subtitles=False,
        enable_bgm=True,
        bgm_mood="comedia",
    )
    assert hard_lock_out.exists()
    tl_check = json.loads((out_dir / "bgm_locked_check_opencut_timeline.json").read_text(encoding="utf-8"))
    track_ids = [t["id"] for t in tl_check["tracks"]]
    assert "audio-bgm-acestep" not in track_ids
    assert tl_check["reedit_settings"]["layout_mode"] in ("fullscreen", "split_streamer")
    assert len(tl_check["word_timestamps"]) == 1

    vol_proc = subprocess.run(
        [ffmpeg_exe, "-hide_banner", "-i", str(hard_lock_out), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    vol_out = f"{vol_proc.stderr}\n{vol_proc.stdout}"
    mean_m = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", vol_out)
    assert mean_m is not None and float(mean_m.group(1)) >= -18.0
    hard_lock_out.unlink(missing_ok=True)
    (out_dir / "bgm_locked_check_opencut_timeline.json").unlink(missing_ok=True)
    (out_dir / "bgm_locked_check.srcclip").unlink(missing_ok=True)

    # 2) Preparar _meta.json + _opencut_timeline.json del Short 01 existente en temp_workspace
    meta_path = out_dir / "test_stream_01_Oro_92pts_meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "short_filename": target_mp4.name,
                "virality_score": 92,
                "layout_used": "fullscreen",
                "subtitle_preset": "hormozi_pop",
                "subtitle_position": "auto",
                "bgm_mood": "desactivada",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    tl_path = out_dir / "test_stream_01_Oro_92pts_opencut_timeline.json"
    tl_path.write_text(
        json.dumps(
            {
                "source": {"file": str(srcclip_path), "trimStart": 0.0, "trimEnd": 1.4, "duration": 1.4},
                "word_timestamps": [{"word": "Hola", "start": 0.1, "end": 0.4}],
                "reedit_settings": {"source_slice": str(srcclip_path)},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    client = TestClient(api_server.app)

    det_res = client.post(
        "/api/shorts/scene-detect",
        json={"short_rel_path": "test_stream/test_stream_01_Oro_92pts.mp4"},
    )
    assert det_res.status_code == 200, det_res.text
    det_body = det_res.json()
    assert det_body["has_source_16_9"] is True
    assert det_body["filename"] == "test_stream_01_Oro_92pts.mp4"

    frame_res = client.get(det_body["frame_url"])
    assert frame_res.status_code == 200
    assert frame_res.headers["content-type"].startswith("image/jpeg")

    rerender_res = client.post(
        "/api/shorts/rerender",
        json={
            "short_rel_path": "test_stream/test_stream_01_Oro_92pts.mp4",
            "layout_mode": "split_50_50",
            "cam_overlay_pos": "top_left",
            "custom_cam_box_norm": [0.55, 0.08, 0.40, 0.84],
            "custom_content_box_norm": [0.05, 0.08, 0.48, 0.84],
            "subtitle_preset": "minimal_white",
            "subtitle_position": "bottom",
        },
    )
    assert rerender_res.status_code == 200, rerender_res.text
    rr_body = rerender_res.json()
    assert rr_body["rerendered"] is True
    assert rr_body["short"]["layout_used"] == "split_50_50"
    assert rr_body["short"]["subtitle_preset"] == "minimal_white"
    assert rr_body["short"]["subtitle_position"] == "bottom"
    assert rr_body["short"]["has_source_16_9"] is True

    updated_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert updated_meta["layout_used"] == "split_50_50"
    assert updated_meta["bgm_mood"] == "desactivada"
    assert updated_meta["custom_cam_box_norm"] == [0.55, 0.08, 0.4, 0.84]

    updated_tl = json.loads(tl_path.read_text(encoding="utf-8"))
    assert "audio-bgm-acestep" not in [t["id"] for t in updated_tl["tracks"]]
    assert srcclip_path.exists()
    # La extensión .srcclip NO debe inflar el conteo de .mp4 en output_shorts
    assert len(list(out_dir.glob("*.mp4"))) == 2


def test_schedule_single_short_updates_sqlite_and_meta(
    temp_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Programa fecha y hora individualmente para un Short y actualiza SQLite y _meta.json sin duplicados."""
    out_dir = temp_workspace / "output_shorts" / "test_stream"
    meta_path = out_dir / "test_stream_01_Oro_92pts_meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "short_filename": "test_stream_01_Oro_92pts.mp4",
                "virality_score": 92,
                "category": "gaming",
                "hook_title": "🔥 Jugada épica en vivo #Shorts",
                "caption": "Mira el clip completo #Viral #Shorts",
                "tags": ["CreadorStudio", "Gaming", "Shorts"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    yt_calls = []

    def fake_upload_scheduled_short(**kwargs):
        yt_calls.append(kwargs)
        return {"id": "yt_single_999"}

    monkeypatch.setattr(api_server.skill_uploader, "upload_scheduled_short", fake_upload_scheduled_short)

    client = TestClient(api_server.app)
    resp1 = client.post(
        "/api/shorts/schedule-single",
        json={
            "short_rel_path": "test_stream/test_stream_01_Oro_92pts.mp4",
            "scheduled_time": "2026-12-20T18:30",
            "upload_to_youtube": True,
        },
    )
    assert resp1.status_code == 200, resp1.text
    b1 = resp1.json()
    assert b1["scheduled"] is True
    assert b1["scheduled_ast"] == "2026-12-20 06:30 PM AST"
    assert b1["publish_at_utc"] == "2026-12-20T22:30:00Z"
    assert b1["youtube_video_id"] == "yt_single_999"
    assert len(yt_calls) == 1

    # Reprogramar el mismo Short a otro horario debe actualizar las 3 colas SQLite sin duplicar filas ni re-subir a YT
    resp2 = client.post(
        "/api/shorts/schedule-single",
        json={
            "short_rel_path": "test_stream/test_stream_01_Oro_92pts.mp4",
            "scheduled_time": "2026-12-21T15:00",
            "upload_to_youtube": True,
        },
    )
    assert resp2.status_code == 200, resp2.text
    b2 = resp2.json()
    assert b2["scheduled_ast"] == "2026-12-21 03:00 PM AST"
    assert b2["publish_at_utc"] == "2026-12-21T19:00:00Z"
    assert b2["youtube_video_id"] == "yt_single_999"
    assert len(yt_calls) == 1

    db_path = temp_workspace / "config" / "schedule_state.db"
    with sqlite3.connect(str(db_path)) as conn:
        yt_rows = conn.execute(
            "SELECT slot_ast, publish_at_utc, youtube_video_id FROM scheduled_slots WHERE video_name = ?",
            ("test_stream_01_Oro_92pts.mp4",),
        ).fetchall()
        ig_rows = conn.execute(
            "SELECT scheduled_time_utc, account_key FROM instagram_scheduled_queue WHERE video_path LIKE ?",
            ("%test_stream_01_Oro_92pts.mp4",),
        ).fetchall()
        tt_rows = conn.execute(
            "SELECT scheduled_time_utc, account_key FROM tiktok_scheduled_queue WHERE video_path LIKE ?",
            ("%test_stream_01_Oro_92pts.mp4",),
        ).fetchall()

    assert len(yt_rows) == 1
    assert yt_rows[0] == ("2026-12-21 03:00 PM AST", "2026-12-21T19:00:00Z", "yt_single_999")
    assert len(ig_rows) == 1
    assert ig_rows[0] == ("2026-12-21T19:00:00Z", "creador_gaming")
    assert len(tt_rows) == 1
    assert tt_rows[0] == ("2026-12-21T19:00:00Z", "creador.gaming")

    updated_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert updated_meta["scheduled_ast"] == "2026-12-21 03:00 PM AST"
    assert updated_meta["publish_at_utc"] == "2026-12-21T19:00:00Z"


def test_new_project_resets_shorts_candidates_and_pipeline_state(temp_workspace: Path) -> None:
    """POST /api/project/new purga output_shorts, candidatos, temporales y resetea el estado sin tocar inbox_videos."""
    out_dir = temp_workspace / "output_shorts" / "test_stream"
    (out_dir / "test_stream_01_Oro_92pts.srcclip").write_bytes(b"srcclip-bytes")
    (out_dir / "test_stream_01_Oro_92pts_meta.json").write_text("{}", encoding="utf-8")
    (out_dir / "test_stream_01_Oro_92pts_subs.ass").write_text("[Script Info]", encoding="utf-8")

    cand_file = temp_workspace / "config" / "candidates.json"
    cand_file.write_text(json.dumps({"video_filename": "test_stream_x3.mp4", "candidates": []}), encoding="utf-8")

    sf_dir = temp_workspace / "config" / "scene_frames"
    sf_dir.mkdir(parents=True, exist_ok=True)
    (sf_dir / "short_test.jpg").write_bytes(b"jpg-bytes")

    (temp_workspace / "processing" / "leftover_tmp.wav").write_bytes(b"wav-bytes")
    keep_inbox = temp_workspace / "inbox_videos" / "keep_me.mp4"
    keep_inbox.write_bytes(b"keep-inbox-video")

    api_server.PIPELINE_STATE["status"] = "COMPLETED"
    api_server.PIPELINE_STATE["current_video"] = "test_stream_x3.mp4"

    client = TestClient(api_server.app)
    resp = client.post("/api/project/new")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["reset"] is True
    assert body["canceled_shorts"] >= 2
    assert body["pipeline_status"]["status"] == "IDLE"
    assert body["pipeline_status"]["current_video"] is None
    assert not any((temp_workspace / "output_shorts").rglob("*.mp4"))
    assert not any((temp_workspace / "output_shorts").rglob("*.srcclip"))
    assert not cand_file.exists()
    assert not (sf_dir / "short_test.jpg").exists()
    assert not (temp_workspace / "processing" / "leftover_tmp.wav").exists()
    assert keep_inbox.exists()
    assert any(v["file_name"] == "keep_me.mp4" for v in body["videos"])


def test_get_shorts_per_network_social_statuses_and_zero_amix_in_renderer(
    temp_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/shorts expone social_statuses por red (YT/IG/TikTok) y renderer.py carece de código amix/sidechaincompress."""
    out_dir = temp_workspace / "output_shorts" / "test_stream"
    meta_01 = out_dir / "test_stream_01_Oro_92pts_meta.json"
    meta_01.write_text(
        json.dumps(
            {
                "short_filename": "test_stream_01_Oro_92pts.mp4",
                "virality_score": 92,
                "category": "gaming",
                "hook_title": "🔥 Oro 92pts #Shorts",
                "caption": "Clip gaming #Viral #Shorts",
                "tags": ["CreadorStudio", "Gaming", "Shorts"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Desprogramar slot previo del fixture para test_stream_02 y programar test_stream_01 con upload YouTube mockeado
    monkeypatch.setattr(
        api_server.skill_uploader,
        "upload_scheduled_short",
        lambda **kwargs: {"id": "yt_123"},
    )
    client = TestClient(api_server.app)
    sched_resp = client.post(
        "/api/shorts/schedule-single",
        json={
            "short_rel_path": "test_stream/test_stream_01_Oro_92pts.mp4",
            "scheduled_time": "2026-12-22T14:00",
            "upload_to_youtube": True,
        },
    )
    assert sched_resp.status_code == 200, sched_resp.text

    db_path = temp_workspace / "config" / "schedule_state.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "UPDATE tiktok_scheduled_queue SET status = 'PUBLISHED' WHERE video_path LIKE ?",
            ("%test_stream_01_Oro_92pts.mp4",),
        )
        conn.commit()

    shorts_resp = client.get("/api/shorts")
    assert shorts_resp.status_code == 200, shorts_resp.text
    shorts = {s["filename"]: s for s in shorts_resp.json()["shorts"]}

    s_oro = shorts["test_stream_01_Oro_92pts.mp4"]
    assert s_oro["social_statuses"]["youtube"]["state"] == "uploaded"
    assert s_oro["social_statuses"]["youtube"]["status_label"] == "Subido"
    assert s_oro["social_statuses"]["instagram"]["state"] == "pending"
    assert s_oro["social_statuses"]["instagram"]["status_label"] == "Pendiente"
    assert s_oro["social_statuses"]["tiktok"]["state"] == "uploaded"
    assert s_oro["social_statuses"]["tiktok"]["status_label"] == "Subido"

    s_plata = shorts["test_stream_02_Plata_80pts.mp4"]
    assert s_plata["eligible_for_youtube"] is True
    assert s_plata["social_statuses"]["youtube"]["state"] == "local"
    assert s_plata["social_statuses"]["youtube"]["status_label"] == "Listo en local"
    assert s_plata["social_statuses"]["instagram"]["state"] == "local"
    assert s_plata["social_statuses"]["instagram"]["status_label"] == "Listo en local"
    assert s_plata["social_statuses"]["tiktok"]["state"] == "local"
    assert s_plata["social_statuses"]["facebook"]["state"] == "local"

    renderer_path = (
        Path(__file__).resolve().parent.parent
        / ".agents"
        / "skills"
        / "vertical-crop-renderer"
        / "renderer.py"
    )
    renderer_src = renderer_path.read_text(encoding="utf-8")
    assert "amix" not in renderer_src
    assert "sidechaincompress" not in renderer_src


def test_download_youtube_url_720p_reality_format_and_fallback(temp_workspace: Path, monkeypatch) -> None:
    """
    TDD:
    1) PRIMARY_YTDLP_FORMAT incluye ramas 720p y bv*+ba/b (soporta videos sin 1080p como P0sOl8K4jq0).
    2) Si yt-dlp reporta 'Requested format is not available', reintenta automáticamente con FALLBACK_YTDLP_FORMAT.
    """
    import main_daemon
    import yt_dlp

    assert "height>=720" in main_daemon.PRIMARY_YTDLP_FORMAT
    assert "bv*+ba/b" in main_daemon.PRIMARY_YTDLP_FORMAT

    proc_dir = temp_workspace / "processing"
    proc_dir.mkdir(parents=True, exist_ok=True)
    target_mp4 = proc_dir / "Reality_720p_Fallback.mp4"
    seen_formats: list[str] = []

    class _FallbackFakeYDL:
        def __init__(self, opts: dict) -> None:
            self.opts = opts
            seen_formats.append(str(opts.get("format", "")))

        def __enter__(self) -> "_FallbackFakeYDL":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def extract_info(self, url: str, download: bool = True) -> dict:
            if len(seen_formats) == 1:
                raise RuntimeError(
                    "ERROR: [youtube] P0sOl8K4jq0: Requested format is not available. Use --list-formats for a list of available formats"
                )
            target_mp4.write_bytes(b"fake-720p-mp4-stream")
            return {
                "title": "Reality Show Cap 1",
                "ext": "mp4",
                "height": 720,
                "requested_downloads": [{"filepath": str(target_mp4)}],
            }

        def prepare_filename(self, info: dict) -> str:
            return str(target_mp4)

    monkeypatch.setattr(main_daemon, "PROCESSING_DIR", proc_dir)
    monkeypatch.setattr(yt_dlp, "YoutubeDL", _FallbackFakeYDL)

    downloaded = main_daemon.download_youtube_url_max_quality(
        "https://www.youtube.com/watch?v=P0sOl8K4jq0",
    )

    assert downloaded == target_mp4
    assert downloaded.exists()
    assert len(seen_formats) == 2
    assert seen_formats[0] == main_daemon.PRIMARY_YTDLP_FORMAT
    assert seen_formats[1] == main_daemon.FALLBACK_YTDLP_FORMAT


def test_independent_new_project_keeps_running_job_and_shorts_isolated(
    client: TestClient,
    temp_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    TDD: POST /api/project/new con mode='independent' abre un nuevo espacio de proyecto aislado
    sin detener, limpiar ni mezclar el job RUNNING ni los Shorts del proyecto principal.
    """
    monkeypatch.setattr(api_server, "PIPELINE_STATE_PATH", temp_workspace / "config" / "pipeline_state.json")

    default_short_dir = temp_workspace / "output_shorts" / "stream_principal"
    default_short_dir.mkdir(parents=True, exist_ok=True)
    default_short_mp4 = default_short_dir / "stream_principal_01_Oro_92pts.mp4"
    default_short_mp4.write_bytes(b"default-short-bytes")

    monkeypatch.setitem(api_server.PIPELINE_STATE, "job_id", "job_main_99")
    monkeypatch.setitem(api_server.PIPELINE_STATE, "status", "RUNNING")
    monkeypatch.setitem(api_server.PIPELINE_STATE, "current_video", "stream_principal.mp4")
    monkeypatch.setitem(api_server.PIPELINE_STATE, "progress_percent", 45)
    monkeypatch.setitem(api_server.PIPELINE_STATE, "phase_label", "Renderizando Clip 2/8")
    monkeypatch.setitem(api_server.PIPELINE_STATE, "step_detail", "Procesando en ventana principal...")

    initial_total = client.get("/api/shorts").json()["total"]
    assert initial_total == 3  # 2 del fixture + 1 agregado

    resp_new = client.post(
        "/api/project/new",
        json={"mode": "independent", "from_project_id": "default"},
    )
    assert resp_new.status_code == 200, resp_new.text
    new_payload = resp_new.json()
    new_pid = new_payload["project_id"]
    assert new_payload["created"] is True
    assert new_payload["reset"] is False
    assert new_payload["mode"] == "independent"
    assert new_payload["project_url"] == f"/?project={new_pid}"
    assert new_pid != "default"
    assert new_payload["pipeline_status"]["status"] == "IDLE"
    assert new_payload["pipeline_status"]["progress_percent"] == 0

    try:
        # El proyecto principal debe seguir RUNNING y conservar sus Shorts intactos.
        st_default = client.get("/api/pipeline/status").json()
        assert st_default["status"] == "RUNNING"
        assert st_default["job_id"] == "job_main_99"
        assert st_default["progress_percent"] == 45

        sh_default = client.get("/api/shorts").json()
        assert sh_default["total"] == initial_total
        assert any(s["filename"] == "stream_principal_01_Oro_92pts.mp4" for s in sh_default["shorts"])

        # El proyecto independiente arranca limpio e aislado.
        st_new = client.get(f"/api/pipeline/status?project_id={new_pid}").json()
        assert st_new["status"] == "IDLE"
        assert st_new["job_id"] is None
        assert st_new["progress_percent"] == 0
        sh_new = client.get(f"/api/shorts?project_id={new_pid}").json()
        assert sh_new["project_id"] == new_pid
        assert sh_new["total"] == 0
        cands_new = client.get(f"/api/pipeline/candidates?project_id={new_pid}").json()
        assert cands_new["candidates"] == []

        # Cancelar o borrar Shorts en la ventana nueva no toca la ventana principal.
        cancel_new = client.post(f"/api/pipeline/cancel?project_id={new_pid}")
        assert cancel_new.status_code == 200
        assert cancel_new.json()["pipeline_status"]["status"] == "CANCELED"
        assert client.get("/api/pipeline/status").json()["status"] == "RUNNING"

        del_new = client.delete(f"/api/shorts?project_id={new_pid}")
        assert del_new.status_code == 200
        assert client.get("/api/shorts").json()["total"] == initial_total
    finally:
        api_server.PROJECT_STATES.pop(new_pid, None)
        api_server.PROJECT_STATE_DIRS.pop(new_pid, None)
        api_server.PROJECT_CANCEL_EVENTS.pop(new_pid, None)


def test_pre_analyze_endpoint_detects_multicategory_rules_for_stream_url_and_local_video(
    client: TestClient,
    temp_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    TDD:
    1) POST /api/pipeline/pre-analyze valida enlace remoto y responde 400 si es inválido.
    2) Para una URL de directo/gaming, detecta múltiples categorías amarradas a layouts distintos
       (ej. videojuegos->gaming_hud y opinion_monologo->fullscreen).
    3) Para un video local en inbox_videos, extrae fotograma y devuelve al menos una regla con frame_url válido.
    """
    import cv2
    import numpy as np

    res_bad = client.post(
        "/api/pipeline/pre-analyze",
        json={"source_type": "youtube_url", "youtube_url": "not-a-valid-url"},
    )
    assert res_bad.status_code == 400

    monkeypatch.setattr(
        api_server,
        "_fetch_remote_url_metadata",
        lambda _url: {
            "title": "CreadorStudio LIVE - Jugando Zelda y Charlando con el Chat",
            "description": "Directo jugando Legend of Zelda y hablando con el chat",
            "tags": ["gaming", "zelda", "live"],
            "categories": ["Gaming"],
            "duration": 7200,
            "is_live": True,
            "thumbnail": "https://i.ytimg.com/vi/demo/hqdefault.jpg",
        },
    )

    res_url = client.post(
        "/api/pipeline/pre-analyze",
        json={"source_type": "youtube_url", "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
    )
    assert res_url.status_code == 200, res_url.text
    url_data = res_url.json()
    assert url_data["is_hybrid_multicategory"] is True
    assert len(url_data["category_rules"]) >= 2
    by_cat = {r["category"]: r for r in url_data["category_rules"]}
    assert "videojuegos" in by_cat
    assert "opinion_monologo" in by_cat
    assert by_cat["videojuegos"]["layout_mode"] == "gaming_hud"
    assert by_cat["opinion_monologo"]["layout_mode"] == "fullscreen"

    inbox_vid = temp_workspace / "inbox_videos" / "hybrid_local_test.mp4"
    writer = cv2.VideoWriter(str(inbox_vid), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (640, 360))
    for _ in range(15):
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        cv2.rectangle(frame, (20, 200), (180, 340), (70, 180, 240), -1)
        writer.write(frame)
    writer.release()

    res_local = client.post(
        "/api/pipeline/pre-analyze",
        json={"source_type": "inbox", "video_filename": "hybrid_local_test.mp4"},
    )
    assert res_local.status_code == 200, res_local.text
    local_data = res_local.json()
    assert len(local_data["category_rules"]) >= 1
    first_frame_url = local_data["category_rules"][0].get("frame_url")
    assert first_frame_url and first_frame_url.startswith("/api/media/scene-frame")

    res_img = client.get(first_frame_url)
    assert res_img.status_code == 200
    assert res_img.headers["content-type"].startswith("image/jpeg")


def test_multicategory_pipeline_routes_each_clip_to_its_bound_layout_and_subtitles(
    temp_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    TDD: Cuando category_rules define múltiples categorías amarradas a distintos layouts/subtítulos,
    main_daemon.process_video_pipeline inspecciona cada clip individualmente y aplica la regla que coincide
    con su escena visual + contexto, guardando layout y subtítulos exactos por Short en _meta.json.
    """
    import main_daemon

    inbox_dir = temp_workspace / "inbox_videos"
    proc_dir = temp_workspace / "processing"
    out_dir = temp_workspace / "output_shorts"
    arch_dir = temp_workspace / "published_archive"
    cfg_dir = temp_workspace / "config"
    for d in (inbox_dir, proc_dir, out_dir, arch_dir, cfg_dir):
        d.mkdir(parents=True, exist_ok=True)

    src_vid = inbox_dir / "streamer_hybrid_stream.mp4"
    src_vid.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    monkeypatch.setattr(main_daemon, "INBOX_DIR", inbox_dir)
    monkeypatch.setattr(main_daemon, "PROCESSING_DIR", proc_dir)
    monkeypatch.setattr(main_daemon, "OUTPUT_SHORTS_DIR", out_dir)
    monkeypatch.setattr(main_daemon, "PUBLISHED_ARCHIVE_DIR", arch_dir)
    monkeypatch.setattr(main_daemon, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(main_daemon, "SETTINGS_PATH", cfg_dir / "settings.json")
    monkeypatch.setattr(main_daemon, "wait_until_file_ready", lambda p, timeout=30.0: True)
    main_daemon.PIPELINE_CANCEL_EVENT.clear()

    clip_chat = main_daemon.skill_transcriber.ViralClipAnalysis(
        start_time=10.0,
        end_time=55.0,
        hook_title="CHARLA SERIA CON EL CHAT",
        first_person_caption="Hablemos claro sobre lo que pasó ayer #Shorts",
        tags=["Opinion", "Chat"],
        bgm_mood="impacto",
        hook_strength=9.1,
        standalone_value=9.0,
        virality_potential=9.2,
        acoustic_energy_score=8.3,
        word_timestamps=[
            main_daemon.skill_transcriber.WordTimestamp(word="Hola", start=0.1, end=0.4, probability=0.95)
        ],
        keep_intervals=[(0.0, 45.0)],
        transcript_excerpt="Escúchenme bien porque hoy quiero hablarles directo a cámara sin filtros.",
    )
    clip_game = main_daemon.skill_transcriber.ViralClipAnalysis(
        start_time=120.0,
        end_time=175.0,
        hook_title="BOSS FINAL EPIC CLUTCH",
        first_person_caption="No puedo creer este clutch en la última ronda #Gaming #Shorts",
        tags=["Gaming", "Clutch"],
        bgm_mood="impacto",
        hook_strength=9.3,
        standalone_value=9.1,
        virality_potential=9.4,
        acoustic_energy_score=8.9,
        word_timestamps=[
            main_daemon.skill_transcriber.WordTimestamp(word="Vamos", start=0.1, end=0.4, probability=0.95)
        ],
        keep_intervals=[(0.0, 55.0)],
        transcript_excerpt="Cuidado con el boss final, increíble jugada ganamos el torneo ahora.",
    )

    monkeypatch.setattr(
        main_daemon.skill_transcriber,
        "transcribe_and_analyze_multiple",
        lambda **kwargs: [clip_chat, clip_game],
    )
    monkeypatch.setattr(
        main_daemon.skill_transcriber,
        "refine_clip_words_high_precision",
        lambda **kwargs: kwargs.get("fallback_words", []),
    )

    def _fake_detect_regions(**kwargs):
        st = float(kwargs.get("start_time", 0.0))
        if st < 80.0:
            return {"mode": "fullscreen"}
        return {"mode": "gaming_hud"}

    monkeypatch.setattr(main_daemon.skill_renderer, "detect_video_layout_and_regions", _fake_detect_regions)

    render_calls: list[dict] = []

    def _fake_render(**kwargs):
        render_calls.append(dict(kwargs))
        out_path = Path(kwargs["output_dir"]) / str(kwargs["output_filename"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"rendered-short")
        return out_path

    monkeypatch.setattr(main_daemon.skill_renderer, "render_vertical_short", _fake_render)

    rules = [
        {
            "rule_id": "r1",
            "category": "videojuegos",
            "scene_label": "Gameplay",
            "detected_share_pct": 65,
            "layout_mode": "split_streamer",
            "subtitle_preset": "nexus_cyber_glow",
            "subtitle_position": "center",
            "cam_overlay_pos": "top_right",
            "custom_boxes_manual": False,
        },
        {
            "rule_id": "r2",
            "category": "opinion_monologo",
            "scene_label": "Charla Full Cam",
            "detected_share_pct": 35,
            "layout_mode": "fullscreen",
            "subtitle_preset": "hormozi_pop",
            "subtitle_position": "bottom",
            "cam_overlay_pos": "top_right",
            "custom_boxes_manual": False,
        },
    ]

    main_daemon.process_video_pipeline(
        inbox_video_path=src_vid,
        cli_overrides={
            "shorts_per_video": 2,
            "category_rules": rules,
            "auto_upload_to_youtube": False,
            "enable_social_distribution": False,
        },
        allow_global_temp_cleanup=False,
    )

    assert len(render_calls) == 2
    calls_by_start = {round(float(c["start_time"]), 1): c for c in render_calls}
    assert calls_by_start[10.0]["layout_mode"] == "fullscreen"
    assert calls_by_start[10.0]["subtitle_preset"] == "hormozi_pop"
    assert calls_by_start[10.0]["subtitle_position"] == "bottom"
    assert calls_by_start[10.0]["category_hint"] == "opinion_monologo"

    assert calls_by_start[120.0]["layout_mode"] == "split_streamer"
    assert calls_by_start[120.0]["subtitle_preset"] == "nexus_cyber_glow"
    assert calls_by_start[120.0]["subtitle_position"] == "center"
    assert calls_by_start[120.0]["category_hint"] == "videojuegos"

    meta_files = list(out_dir.rglob("*_meta.json"))
    assert len(meta_files) == 2
    metas_by_cat = {}
    for mf in meta_files:
        payload = json.loads(mf.read_text(encoding="utf-8"))
        metas_by_cat[payload["category"]] = payload

    assert metas_by_cat["opinion_monologo"]["layout_used"] == "fullscreen"
    assert metas_by_cat["opinion_monologo"]["subtitle_preset"] == "hormozi_pop"
    assert metas_by_cat["videojuegos"]["layout_used"] == "split_streamer"
    assert metas_by_cat["videojuegos"]["subtitle_preset"] == "nexus_cyber_glow"


def test_content_profiles_crud_and_auto_recognition_in_pre_analyze(
    client: TestClient,
    temp_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    TDD:
    1) GET /api/content-profiles inicia vacío (sin perfiles mock).
    2) POST /api/content-profiles crea perfiles multi-escena ("CreadorStudio Live", "Podcast Debate") sin requerir categoría genérica.
    3) POST /api/pipeline/pre-analyze auto-reconoce el perfil por canal/título/archivo (normalización Unicode NFKD)
       y devuelve sus escenas guardadas con cajas manuales + frame_url válido para archivos locales.
    4) PUT y DELETE /api/content-profiles/{id} actualizan y eliminan correctamente (404 si ya no existe).
    """
    import cv2
    import numpy as np

    res_empty = client.get("/api/content-profiles")
    assert res_empty.status_code == 200, res_empty.text
    assert res_empty.json()["profiles"] == []

    res_p1 = client.post(
        "/api/content-profiles",
        json={
            "name": "CreadorStudio Live",
            "match_keywords": ["creadorstudio", "live"],
            "scenes": [
                {
                    "rule_id": "scene_1",
                    "scene_label": "Charla Cámara Completa",
                    "detected_share_pct": 40,
                    "layout_mode": "fullscreen",
                    "subtitle_preset": "hormozi_pop",
                    "subtitle_position": "bottom",
                    "cam_overlay_pos": "top_right",
                    "custom_boxes_manual": False,
                },
                {
                    "rule_id": "scene_2",
                    "scene_label": "Gameplay + Cámara",
                    "detected_share_pct": 60,
                    "layout_mode": "split_streamer",
                    "subtitle_preset": "nexus_cyber_glow",
                    "subtitle_position": "center",
                    "cam_overlay_pos": "top_right",
                    "custom_cam_box_norm": [0.03, 0.62, 0.25, 0.32],
                    "custom_content_box_norm": [0.28, 0.0, 0.72, 1.0],
                    "custom_boxes_manual": True,
                },
            ],
        },
    )
    assert res_p1.status_code == 200, res_p1.text
    p1 = res_p1.json()
    assert p1["name"] == "CreadorStudio Live"
    assert len(p1["scenes"]) == 2
    assert p1["scenes"][1]["custom_cam_box_norm"] == [0.03, 0.62, 0.25, 0.32]

    res_p2 = client.post(
        "/api/content-profiles",
        json={
            "name": "Podcast Debate",
            "match_keywords": ["tertulia"],
            "scenes": [
                {
                    "rule_id": "scene_1",
                    "scene_label": "Cabina Mesa",
                    "detected_share_pct": 70,
                    "layout_mode": "podcast_dynamic",
                    "subtitle_preset": "karaoke_duo",
                    "subtitle_position": "bottom",
                    "cam_overlay_pos": "top_right",
                    "custom_cam_box_norm": [0.05, 0.1, 0.4, 0.8],
                    "custom_content_box_norm": [0.55, 0.1, 0.4, 0.8],
                    "custom_boxes_manual": True,
                },
                {
                    "rule_id": "scene_2",
                    "scene_label": "Plano Individual",
                    "detected_share_pct": 30,
                    "layout_mode": "fullscreen",
                    "subtitle_preset": "hormozi_pop",
                    "subtitle_position": "bottom",
                    "cam_overlay_pos": "top_right",
                    "custom_boxes_manual": False,
                },
            ],
        },
    )
    assert res_p2.status_code == 200, res_p2.text
    p2 = res_p2.json()

    monkeypatch.setattr(
        api_server,
        "_fetch_remote_url_metadata",
        lambda _url: {
            "title": "Aló Foke Sin Filtro En Vivo",
            "description": "Programa en vivo",
            "tags": ["radio"],
            "categories": ["Entertainment"],
            "duration": 5400,
            "is_live": True,
            "thumbnail": "https://i.ytimg.com/vi/tertulia/hqdefault.jpg",
            "uploader": "Podcast Debate Radio Show",
        },
    )

    res_pre_url = client.post(
        "/api/pipeline/pre-analyze",
        json={"source_type": "youtube_url", "youtube_url": "https://www.youtube.com/watch?v=Podcast DebateDemo1"},
    )
    assert res_pre_url.status_code == 200, res_pre_url.text
    pre_url = res_pre_url.json()
    assert pre_url["matched_profile_id"] == p2["id"]
    assert pre_url["matched_profile_name"] == "Podcast Debate"
    assert pre_url["analysis_mode"] == "matched_profile"
    assert len(pre_url["category_rules"]) == 2
    assert pre_url["category_rules"][0]["scene_label"] == "Cabina Mesa"
    assert pre_url["category_rules"][0]["custom_cam_box_norm"] == [0.05, 0.1, 0.4, 0.8]

    inbox_vid = temp_workspace / "inbox_videos" / "CreadorStudio_LIVE_Zelda.mp4"
    writer = cv2.VideoWriter(str(inbox_vid), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (640, 360))
    for _ in range(12):
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        cv2.rectangle(frame, (20, 200), (180, 340), (70, 180, 240), -1)
        writer.write(frame)
    writer.release()

    res_pre_local = client.post(
        "/api/pipeline/pre-analyze",
        json={"source_type": "inbox", "video_filename": "CreadorStudio_LIVE_Zelda.mp4"},
    )
    assert res_pre_local.status_code == 200, res_pre_local.text
    pre_local = res_pre_local.json()
    assert pre_local["matched_profile_id"] == p1["id"]
    assert pre_local["matched_profile_name"] == "CreadorStudio Live"
    assert pre_local["analysis_mode"] == "matched_profile"
    assert pre_local["category_rules"][1]["custom_cam_box_norm"] == [0.03, 0.62, 0.25, 0.32]
    local_frame_url = pre_local["category_rules"][0].get("frame_url")
    assert local_frame_url and local_frame_url.startswith("/api/media/scene-frame")
    res_frame = client.get(local_frame_url)
    assert res_frame.status_code == 200
    assert res_frame.headers["content-type"].startswith("image/jpeg")

    res_upd = client.put(
        f"/api/content-profiles/{p1['id']}",
        json={
            "name": "CreadorStudio Live VIP",
            "match_keywords": ["creadorstudio", "zelda"],
            "scenes": p1["scenes"],
        },
    )
    assert res_upd.status_code == 200, res_upd.text
    assert res_upd.json()["name"] == "CreadorStudio Live VIP"
    assert "zelda" in res_upd.json()["match_keywords"]

    res_del = client.delete(f"/api/content-profiles/{p1['id']}")
    assert res_del.status_code == 200
    res_del_again = client.delete(f"/api/content-profiles/{p1['id']}")
    assert res_del_again.status_code == 404


def test_scene_detect_supports_youtube_url_for_studio_calibration(
    client: TestClient,
    temp_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    TDD: POST /api/scene/detect valida URLs remotas y genera fotograma 16:9 + cajas normalizadas
    para youtube_url, permitiendo usar Detectar Escena & Studio también desde enlace.
    """
    res_bad = client.post(
        "/api/scene/detect",
        json={"source_type": "youtube_url", "youtube_url": "notaurl"},
    )
    assert res_bad.status_code == 400

    monkeypatch.setattr(
        api_server,
        "_fetch_remote_url_metadata",
        lambda _url: {
            "title": "Demo Stream",
            "description": "",
            "tags": [],
            "categories": [],
            "duration": 1200,
            "is_live": False,
            "thumbnail": None,
            "uploader": "Demo",
        },
    )

    res_ok = client.post(
        "/api/scene/detect",
        json={"source_type": "youtube_url", "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
    )
    assert res_ok.status_code == 200, res_ok.text
    data = res_ok.json()
    assert len(data["cam_box_norm"]) == 4
    assert len(data["content_box_norm"]) == 4
    assert all(isinstance(v, (int, float)) for v in data["cam_box_norm"])
    assert all(isinstance(v, (int, float)) for v in data["content_box_norm"])
    assert data["frame_url"].startswith("/api/media/scene-frame")

    res_img = client.get(data["frame_url"])
    assert res_img.status_code == 200
    assert res_img.headers["content-type"].startswith("image/jpeg")


def test_stale_source_preview_url_is_cleared_when_backing_video_missing(
    client: TestClient,
    temp_workspace: Path,
) -> None:
    """Si un estado previo o cancelado apunta a un MP4 inexistente en disco, no debe devolver 404 en consola."""
    api_server.PIPELINE_STATE["status"] = "CANCELED"
    api_server.PIPELINE_STATE["source_preview_url"] = "/api/media/source/nonexistent_ghost.mp4"

    inbox_res = client.get("/api/inbox")
    assert inbox_res.status_code == 200
    assert inbox_res.json()["pipeline_status"]["source_preview_url"] is None

    status_res = client.get("/api/pipeline/status")
    assert status_res.status_code == 200
    assert status_res.json()["source_preview_url"] is None

    # Y si el archivo sí existe en inbox_videos, conserva source_preview_url y responde 200 al servirlo
    real_vid = api_server.INBOX_DIR / "present_stream.mp4"
    real_vid.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    api_server.PIPELINE_STATE["status"] = "RUNNING"
    api_server.PIPELINE_STATE["source_preview_url"] = "/api/media/source/present_stream.mp4"

    status_ok = client.get("/api/pipeline/status")
    assert status_ok.status_code == 200
    assert status_ok.json()["source_preview_url"] == "/api/media/source/present_stream.mp4"


def test_resolve_startup_port_skips_foreign_service_on_default_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si un servicio externo (ej. Laravel) ocupa 8000, debe elegir el primer puerto libre (8001)."""
    monkeypatch.setattr(api_server, "_is_port_free", lambda port, host="127.0.0.1": int(port) != 8000)
    monkeypatch.setattr(
        api_server,
        "_is_short_yt_running_on_port",
        lambda port, host="127.0.0.1", timeout=0.8: False,
    )

    port, already_running = api_server.resolve_startup_port(preferred_port=8000, explicit_port=False)
    assert port == 8001
    assert already_running is False


def test_resolve_startup_port_reuses_existing_short_yt_on_fallback_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si Short YT ya corre en un puerto alternativo (8001) y 8000 está ocupado, debe reutilizar 8001."""
    monkeypatch.setattr(
        api_server,
        "_is_port_free",
        lambda port, host="127.0.0.1": int(port) not in (8000, 8001),
    )
    monkeypatch.setattr(
        api_server,
        "_is_short_yt_running_on_port",
        lambda port, host="127.0.0.1", timeout=0.8: int(port) == 8001,
    )

    port, already_running = api_server.resolve_startup_port(preferred_port=8000, explicit_port=False)
    assert port == 8001
    assert already_running is True


def test_is_short_yt_running_on_port_rejects_foreign_200_and_explicit_busy_port_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rechaza respuestas 200 de otros servicios y falla si un puerto explícito está ocupado por otro servicio."""
    import json

    class _FakeResp:
        def __init__(self, payload: Dict[str, Any], status: int = 200) -> None:
            self.status = status
            self._body = json.dumps(payload).encode("utf-8")

        def read(self) -> bytes:
            return self._body

        def __enter__(self) -> "_FakeResp":
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
            return False

    monkeypatch.setattr(
        api_server.urllib.request,
        "urlopen",
        lambda url, timeout=0.8: _FakeResp({"status": "ok", "app": "laravel"}),
    )
    assert api_server._is_short_yt_running_on_port(8000) is False

    monkeypatch.setattr(
        api_server.urllib.request,
        "urlopen",
        lambda url, timeout=0.8: _FakeResp({"status": "ok", "engine": "Auto-Clipper Shorts Engine"}),
    )
    assert api_server._is_short_yt_running_on_port(8001) is True

    monkeypatch.setattr(api_server, "_is_port_free", lambda port, host="127.0.0.1": False)
    monkeypatch.setattr(
        api_server,
        "_is_short_yt_running_on_port",
        lambda port, host="127.0.0.1", timeout=0.8: False,
    )
    with pytest.raises(RuntimeError):
        api_server.resolve_startup_port(preferred_port=8000, explicit_port=True)


def test_local_video_pick_cancel_and_external_file_end_to_end(
    client: TestClient,
    temp_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    POST /api/local-video/pick:
    1) Cancelar el Explorador devuelve cancelled=True sin error.
    2) Rutas externas no registradas se rechazan (404).
    3) Al elegir un MP4 externo real, permite inspect, pre-analyze, scene/detect, streaming y process con keep_inbox_source=True.
    """
    import shutil
    import time

    monkeypatch.setattr(api_server, "REGISTERED_LOCAL_VIDEOS", {})
    monkeypatch.setattr(api_server, "_open_native_video_file_dialog", lambda: None)

    cancel_res = client.post("/api/local-video/pick")
    assert cancel_res.status_code == 200
    assert cancel_res.json() == {
        "cancelled": True,
        "file_path": None,
        "file_name": None,
        "size_mb": None,
    }

    ext_dir = temp_workspace / "mis_videos_pc"
    ext_dir.mkdir(parents=True, exist_ok=True)
    ext_mp4 = ext_dir / "clip_externo.mp4"
    shutil.copy2(temp_workspace / "inbox_videos" / "test_stream_x3.mp4", ext_mp4)

    # Gate de seguridad: antes de registrarlo mediante el selector, debe rechazarse con 404
    unreg_inspect = client.post("/api/inspect", json={"video_filename": str(ext_mp4)})
    assert unreg_inspect.status_code == 404

    monkeypatch.setattr(api_server, "_open_native_video_file_dialog", lambda: str(ext_mp4))
    pick_res = client.post("/api/local-video/pick")
    assert pick_res.status_code == 200
    picked = pick_res.json()
    assert picked["cancelled"] is False
    assert picked["file_name"] == "clip_externo.mp4"
    assert picked["file_path"] == str(ext_mp4.resolve())
    assert picked["size_mb"] >= 0

    inspect_res = client.post("/api/inspect", json={"video_filename": picked["file_path"]})
    assert inspect_res.status_code == 200
    assert inspect_res.json()["file_name"] == "clip_externo.mp4"

    pre_res = client.post(
        "/api/pipeline/pre-analyze",
        json={"source_type": "inbox", "video_filename": picked["file_path"]},
    )
    assert pre_res.status_code == 200
    assert pre_res.json()["target"] == "clip_externo.mp4"

    scene_res = client.post(
        "/api/scene/detect",
        json={"source_type": "inbox", "video_filename": picked["file_path"]},
    )
    assert scene_res.status_code == 200
    frame_url = scene_res.json()["frame_url"]
    assert frame_url
    assert client.get(frame_url).status_code == 200

    stream_res = client.get("/api/media/source/clip_externo.mp4")
    assert stream_res.status_code == 200

    captured_calls: list[dict[str, object]] = []

    def _fake_process_pipeline(video_path: Path, **kwargs: object) -> None:
        captured_calls.append({"video_path": Path(video_path), **kwargs})

    monkeypatch.setattr(api_server._main_daemon_bootstrap, "process_video_pipeline", _fake_process_pipeline)

    proc_res = client.post(
        "/api/pipeline/process",
        json={
            "source_type": "inbox",
            "video_filename": picked["file_path"],
            "shorts_per_video": 2,
            "layout_mode": "auto",
            "bgm_mood": "desactivada",
            "auto_upload_to_youtube": False,
        },
    )
    assert proc_res.status_code == 200

    deadline = time.time() + 3.0
    while not captured_calls and time.time() < deadline:
        time.sleep(0.05)

    assert len(captured_calls) == 1
    assert Path(str(captured_calls[0]["video_path"])).resolve() == ext_mp4.resolve()
    assert captured_calls[0].get("keep_inbox_source") is True
    assert ext_mp4.exists(), "El video externo original debe conservarse intacto en su carpeta"


def test_local_video_upload_stream_and_root_no_cache(
    client: TestClient,
    temp_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    POST /api/local-video/upload:
    1) Rechaza con 400 extensiones inválidas (.txt) o carga vacía.
    2) Recibe un MP4 real por streaming hacia processing/local_picks y lo registra.
    3) Permite inspect, scene/detect y GET /api/media/source incluso tras limpiar REGISTERED_LOCAL_VIDEOS.
    4) GET / incluye Cache-Control con no-store cuando existe frontend/dist/index.html.
    """
    monkeypatch.setattr(api_server, "REGISTERED_LOCAL_VIDEOS", {})

    bad_ext = client.post(
        "/api/local-video/upload",
        headers={"X-File-Name": "notas.txt", "Content-Type": "application/octet-stream"},
        content=b"hola",
    )
    assert bad_ext.status_code == 400

    empty_res = client.post(
        "/api/local-video/upload",
        headers={"X-File-Name": "vacio.mp4", "Content-Type": "application/octet-stream"},
        content=b"",
    )
    assert empty_res.status_code == 400

    mp4_bytes = (temp_workspace / "inbox_videos" / "test_stream_x3.mp4").read_bytes()
    upload_res = client.post(
        "/api/local-video/upload",
        headers={
            "X-File-Name": "Clip%20Prueba%20Local.mp4",
            "Content-Type": "application/octet-stream",
        },
        content=mp4_bytes,
    )
    assert upload_res.status_code == 200
    payload = upload_res.json()
    assert payload["cancelled"] is False
    assert payload["file_name"] == "Clip Prueba Local.mp4"
    assert payload["size_mb"] >= 0

    staged_path = Path(payload["file_path"]).resolve()
    expected_picks_dir = (temp_workspace / "processing" / "local_picks").resolve()
    assert staged_path.parent == expected_picks_dir
    assert staged_path.exists()
    assert staged_path.read_bytes() == mp4_bytes
    assert str(staged_path) in api_server.REGISTERED_LOCAL_VIDEOS

    # Simular reinicio de memoria borrando REGISTERED_LOCAL_VIDEOS para probar resolución persistente desde local_picks
    api_server.REGISTERED_LOCAL_VIDEOS.clear()

    inspect_res = client.post("/api/inspect", json={"video_filename": payload["file_path"]})
    assert inspect_res.status_code == 200
    assert inspect_res.json()["file_name"] == "Clip Prueba Local.mp4"

    scene_res = client.post(
        "/api/scene/detect",
        json={"source_type": "inbox", "video_filename": payload["file_path"]},
    )
    assert scene_res.status_code == 200
    assert scene_res.json()["frame_url"]

    stream_res = client.get("/api/media/source/Clip%20Prueba%20Local.mp4")
    assert stream_res.status_code == 200

    if (api_server.FRONTEND_DIST_DIR / "index.html").exists():
        root_res = client.get("/")
        assert root_res.status_code == 200
        assert "no-store" in root_res.headers.get("cache-control", "").lower()


def test_scene_detect_extracts_real_frame_at_timestamp_for_local_and_remote_stream(
    client: TestClient,
    temp_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    TDD: POST /api/scene/detect debe extraer fotogramas reales de cualquier segundo del video
    (sin limitarse a la portada ni colisionar caché) tanto en local como en stream remoto youtube_url.
    """
    mp4_path = temp_workspace / "inbox_videos" / "timeline_two_tone.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(mp4_path), fourcc, 30.0, (640, 360))
    for i in range(120):
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        if i < 60:
            frame[:, :] = (10, 10, 230)  # BGR -> Rojo dominante (0.0s .. 2.0s)
        else:
            frame[:, :] = (10, 230, 10)  # BGR -> Verde dominante (2.0s .. 4.0s)
        writer.write(frame)
    writer.release()

    # 1) Modo local: extraer 0.3s vs 3.0s debe devolver frames visualmente distintos y frame_source='local_video'
    res_local_early = client.post(
        "/api/scene/detect",
        json={
            "source_type": "inbox",
            "video_filename": "timeline_two_tone.mp4",
            "timestamp_sec": 0.3,
        },
    )
    assert res_local_early.status_code == 200, res_local_early.text
    early_data = res_local_early.json()
    assert early_data["frame_source"] == "local_video"
    assert early_data["duration_sec"] > 3.5
    assert abs(early_data["timestamp_sec"] - 0.3) <= 0.15

    res_local_late = client.post(
        "/api/scene/detect",
        json={
            "source_type": "inbox",
            "video_filename": "timeline_two_tone.mp4",
            "timestamp_sec": 3.0,
        },
    )
    assert res_local_late.status_code == 200, res_local_late.text
    late_data = res_local_late.json()
    assert late_data["frame_source"] == "local_video"
    assert late_data["frame_url"] != early_data["frame_url"]

    img_early = cv2.imdecode(
        np.frombuffer(client.get(early_data["frame_url"]).content, dtype=np.uint8),
        cv2.IMREAD_COLOR,
    )
    img_late = cv2.imdecode(
        np.frombuffer(client.get(late_data["frame_url"]).content, dtype=np.uint8),
        cv2.IMREAD_COLOR,
    )
    assert img_early is not None and img_late is not None
    assert float(img_early[:, :, 2].mean()) > float(img_early[:, :, 1].mean()) + 100.0
    assert float(img_late[:, :, 1].mean()) > float(img_late[:, :, 2].mean()) + 100.0

    # 2) Modo URL remota con stream directo: debe usar ffmpeg -ss (video_stream) y NO la portada estática
    monkeypatch.setattr(
        api_server,
        "_fetch_remote_url_metadata",
        lambda _url, **_kw: {
            "title": "Stream Largo Two Tone",
            "description": "",
            "tags": [],
            "categories": [],
            "duration": 4.0,
            "is_live": False,
            "thumbnail": "https://example.invalid/cover_should_not_be_used.jpg",
            "uploader": "CreadorStudio",
            "stream_url": str(mp4_path),
            "http_headers": {},
        },
    )

    res_remote_early = client.post(
        "/api/scene/detect",
        json={
            "source_type": "youtube_url",
            "youtube_url": "https://www.youtube.com/watch?v=timelineTest01",
            "timestamp_sec": 0.3,
        },
    )
    assert res_remote_early.status_code == 200, res_remote_early.text
    r_early = res_remote_early.json()
    assert r_early["frame_source"] == "video_stream"
    assert abs(r_early["timestamp_sec"] - 0.3) <= 0.2
    assert r_early["duration_sec"] == pytest.approx(4.0, abs=0.1)

    res_remote_late = client.post(
        "/api/scene/detect",
        json={
            "source_type": "youtube_url",
            "youtube_url": "https://www.youtube.com/watch?v=timelineTest01",
            "timestamp_sec": 3.0,
        },
    )
    assert res_remote_late.status_code == 200, res_remote_late.text
    r_late = res_remote_late.json()
    assert r_late["frame_source"] == "video_stream"
    assert r_late["frame_url"] != r_early["frame_url"]

    img_r_early = cv2.imdecode(
        np.frombuffer(client.get(r_early["frame_url"]).content, dtype=np.uint8),
        cv2.IMREAD_COLOR,
    )
    img_r_late = cv2.imdecode(
        np.frombuffer(client.get(r_late["frame_url"]).content, dtype=np.uint8),
        cv2.IMREAD_COLOR,
    )
    assert img_r_early is not None and img_r_late is not None
    assert float(img_r_early[:, :, 2].mean()) > float(img_r_early[:, :, 1].mean()) + 100.0
    assert float(img_r_late[:, :, 1].mean()) > float(img_r_late[:, :, 2].mean()) + 100.0


def test_fullscreen_manual_cam_box_preserved_in_resolve_clip_category_rule(
    temp_workspace: Path,
) -> None:
    """TDD: resolve_clip_category_rule debe conservar custom_cam_box_norm en fullscreen cuando custom_boxes_manual=True."""
    video_path = temp_workspace / "inbox_videos" / "test_stream_x3.mp4"
    res_manual = api_server._main_daemon_bootstrap.resolve_clip_category_rule(
        video_path=video_path,
        start_time=0.0,
        end_time=2.0,
        text="charla directa",
        title="Charla",
        category_rules=[
            {
                "rule_id": "scene_1",
                "category": "auto",
                "scene_label": "Charla Solo Cam",
                "layout_mode": "fullscreen",
                "subtitle_preset": "hormozi_pop",
                "subtitle_position": "bottom",
                "cam_overlay_pos": "top_right",
                "custom_cam_box_norm": [0.12, 0.08, 0.36, 0.84],
                "custom_content_box_norm": [0.4, 0.1, 0.5, 0.8],
                "custom_boxes_manual": True,
            }
        ],
    )
    assert res_manual["custom_cam_box_norm"] == [0.12, 0.08, 0.36, 0.84]
    assert res_manual["custom_content_box_norm"] is None

    res_auto = api_server._main_daemon_bootstrap.resolve_clip_category_rule(
        video_path=video_path,
        start_time=0.0,
        end_time=2.0,
        text="charla directa",
        title="Charla",
        category_rules=[
            {
                "rule_id": "scene_1",
                "category": "auto",
                "scene_label": "Charla Solo Cam",
                "layout_mode": "fullscreen",
                "subtitle_preset": "hormozi_pop",
                "subtitle_position": "bottom",
                "cam_overlay_pos": "top_right",
                "custom_cam_box_norm": [0.12, 0.08, 0.36, 0.84],
                "custom_content_box_norm": [0.4, 0.1, 0.5, 0.8],
                "custom_boxes_manual": False,
            }
        ],
    )
    assert res_auto["custom_cam_box_norm"] is None
    assert res_auto["custom_content_box_norm"] is None


def test_ytdlp_download_keeps_inbox_dir_with_video_id_and_recovers_corrupt_resume(
    temp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    1) Con rutas largas en Windows (> 65 chars), download_youtube_url_max_quality debe configurar
       paths={'home': str(INBOX_DIR)} y outtmpl relativo con %(id)s para no truncar a 'inbox_vi.mp4'.
    2) Si un .mp4 descargado por resume previo tiene video truncado respecto al audio (>= 8192 bytes),
       debe detectar la corrupción, limpiar artefactos previos y reintentar con continuedl=False.
    """
    import shutil
    import subprocess
    import imageio_ffmpeg
    import main_daemon
    import yt_dlp

    long_inbox = (
        temp_workspace
        / "carpeta_con_ruta_larga_para_superar_sesenta_y_cuatro_caracteres"
        / "inbox_videos"
    )
    long_inbox.mkdir(parents=True, exist_ok=True)
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    # Generar MP4 corrupto/truncado: 1.5s de video + 25.0s de audio (emula resume de otra descarga)
    corrupt_mp4 = temp_workspace / "corrupt_truncated_source.mp4"
    proc_bad = subprocess.run(
        [
            ffmpeg_exe,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x180:rate=15:duration=1.5",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=25.0",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(corrupt_mp4),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_bad.returncode == 0, proc_bad.stderr
    assert corrupt_mp4.stat().st_size >= 8192

    # Generar MP4 íntegro: 4.0s de video + 4.0s de audio sincronizados
    clean_mp4 = temp_workspace / "clean_valid_source.mp4"
    proc_good = subprocess.run(
        [
            ffmpeg_exe,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x180:rate=15:duration=4.0",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=4.0",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(clean_mp4),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_good.returncode == 0, proc_good.stderr

    # Verificar que Real yt_dlp con los opts del primer intento resuelve dentro de long_inbox con ID
    attempt_opts: List[Dict[str, Any]] = []
    attempt_paths: List[Path] = []
    real_ydl_cls = yt_dlp.YoutubeDL

    class _CorruptResumeThenCleanYDL:
        def __init__(self, opts: Dict[str, Any]) -> None:
            self.opts = dict(opts)
            attempt_opts.append(self.opts)
            self._real_ydl = real_ydl_cls(
                {
                    "paths": opts.get("paths") or {},
                    "outtmpl": opts.get("outtmpl"),
                    "trim_file_name": opts.get("trim_file_name"),
                    "quiet": True,
                }
            )

        def __enter__(self) -> "_CorruptResumeThenCleanYDL":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def prepare_filename(self, info: Dict[str, Any]) -> str:
            return self._real_ydl.prepare_filename(info)

        def extract_info(self, url: str, download: bool = True) -> Dict[str, Any]:
            info = {
                "id": "vf1gzPlYPY8",
                "title": "MI DIRECTO EPICO EN VIVO MUY LARGO PARA TRUNCAR NOMBRE SIN ID",
                "ext": "mp4",
            }
            target_file = Path(self.prepare_filename(info)).with_suffix(".mp4")
            target_file.parent.mkdir(parents=True, exist_ok=True)
            attempt_paths.append(target_file)
            if len(attempt_opts) == 1:
                shutil.copy2(str(corrupt_mp4), str(target_file))
                # Emular residuo .part previo junto a la descarga
                target_file.with_suffix(".mp4.part").write_bytes(b"stale-part")
            else:
                shutil.copy2(str(clean_mp4), str(target_file))
            info["requested_downloads"] = [{"filepath": str(target_file)}]
            return info

    monkeypatch.setattr(main_daemon, "INBOX_DIR", long_inbox)
    monkeypatch.setattr(yt_dlp, "YoutubeDL", _CorruptResumeThenCleanYDL)

    out_path = main_daemon.download_youtube_url_max_quality(
        "https://youtube.com/live/vf1gzPlYPY8?feature=share",
        filename_prefix="p_mwhvy78v_s2s",
    )

    assert len(attempt_opts) >= 2, f"Debió reintentar al detectar video truncado: {attempt_opts}"
    assert attempt_opts[0].get("paths", {}).get("home") == str(long_inbox)
    assert attempt_paths[0].parent.resolve() == long_inbox.resolve()
    assert "vf1gzPlYPY8" in attempt_paths[0].name
    assert attempt_opts[0].get("continuedl") is True
    assert attempt_opts[1].get("continuedl") is False
    assert not attempt_paths[0].with_suffix(".mp4.part").exists()
    assert out_path.parent.resolve() == long_inbox.resolve()
    assert "vf1gzPlYPY8" in out_path.name
    assert out_path.exists()


def test_renderer_rejects_audio_only_output_and_api_hides_staging_mp4(
    client: TestClient, temp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    1) Si FFmpeg recibe un rango donde no existen fotogramas de video (audio-only), render_vertical_short
       debe rechazar el archivo en staging y lanzar RuntimeError sin dejar MP4 negro ni temporales.
    2) GET /api/shorts debe ignorar archivos en staging (_rendering_* / _tmp_rerender_ / *.tmp.mp4).
    """
    import subprocess
    import imageio_ffmpeg

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    monkeypatch.setattr(
        api_server.skill_renderer, "_try_fetch_youtube_1080p60_slice", lambda *args, **kwargs: None
    )

    # Fuente desbalanceada: 2s de video + 7s de audio
    unbalanced_src = temp_workspace / "inbox_videos" / "video_ends_early.mp4"
    gen_proc = subprocess.run(
        [
            ffmpeg_exe,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=640x360:rate=30:duration=2.0",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=7.0",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(unbalanced_src),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert gen_proc.returncode == 0, gen_proc.stderr

    broken_dir = temp_workspace / "output_shorts" / "BrokenRun"
    broken_dir.mkdir(parents=True, exist_ok=True)
    with pytest.raises(RuntimeError):
        api_server.skill_renderer.render_vertical_short(
            video_path=unbalanced_src,
            start_time=4.0,
            end_time=6.5,
            word_timestamps=[],
            output_dir=broken_dir,
            output_filename="broken_clip.mp4",
            layout_mode="fullscreen",
            enable_subtitles=False,
            enable_bgm=False,
        )

    assert not (broken_dir / "broken_clip.mp4").exists()
    assert not (broken_dir / "broken_clip.srcclip").exists()
    assert list(broken_dir.glob("_rendering_*")) == []

    # Crear 1 Short visible + temporales de staging en output_shorts y verificar filtrado en GET /api/shorts
    client.delete("/api/shorts")
    vis_dir = temp_workspace / "output_shorts" / "StageCheck"
    vis_dir.mkdir(parents=True, exist_ok=True)
    (vis_dir / "StageCheck_01_Oro_91pts.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42valid")
    (vis_dir / "_rendering_1234_StageCheck_02_Oro_90pts.mp4").write_bytes(b"incomplete-render")
    (vis_dir / "_tmp_rerender_StageCheck_01_Oro_91pts.mp4").write_bytes(b"rerender-tmp")
    (vis_dir / "StageCheck_03_Plata_80pts.tmp.mp4").write_bytes(b"tmp-suffix")

    res = client.get("/api/shorts")
    assert res.status_code == 200
    names = [s["filename"] for s in res.json()["shorts"]]
    assert names == ["StageCheck_01_Oro_91pts.mp4"]


def test_social_accounts_hub_crud_masked_secrets_and_verify(client: TestClient) -> None:
    """
    TDD: GET/PUT /api/social-accounts gestiona Cuentas Principales, Gaming y Clipping
    enmascarando secretos API sin sobreescribirlos al reenviar '••••', y POST /api/social-accounts/verify valida conexión.
    """
    res_get = client.get("/api/social-accounts")
    assert res_get.status_code == 200, res_get.text
    hub = res_get.json()
    cats = hub["categories"]
    assert "principales" in cats and "gaming" in cats and "clipping" in cats

    gaming_handles = {acc["handle"].lower() for acc in cats["gaming"]["accounts"]}
    assert "@creador_gaming" in gaming_handles
    assert "@creadorstudio" in gaming_handles
    assert "@creador.gaming" in gaming_handles

    # Guardar cuenta nueva + secreto real de API y topic_keywords
    payload = dict(hub)
    payload["categories"]["gaming"]["topic_keywords"] = ["zelda", "rtx", "gameplay"]
    payload["categories"]["gaming"]["accounts"].append(
        {
            "id": "fb_gaming_custom",
            "platform": "facebook",
            "handle": "CreadorStudiogaming",
            "display_name": "CreadorStudiogaming Page",
            "external_id": "900000000000011",
            "enabled": True,
        }
    )
    payload["api_settings"]["instagram"]["access_token"] = "EAAG_real_super_secret_token_9876"
    payload["api_settings"]["tiktok"]["client_key"] = "tk_key_abc"
    payload["api_settings"]["tiktok"]["client_secret"] = "tk_secret_4321"

    res_put = client.put("/api/social-accounts", json=payload)
    assert res_put.status_code == 200, res_put.text
    saved = res_put.json()
    assert saved["api_settings"]["instagram"]["access_token"].startswith("••••")
    assert saved["api_settings"]["instagram"]["access_token"].endswith("9876")
    assert "EAAG_real_super_secret_token_9876" not in json.dumps(saved)
    assert saved["api_settings"]["instagram"]["has_access_token"] is True

    # Segundo PUT reenviando el valor enmascarado: debe preservar el secreto real intacto en disco
    saved["categories"]["clipping"]["topic_keywords"].append("highlight")
    res_put2 = client.put("/api/social-accounts", json=saved)
    assert res_put2.status_code == 200, res_put2.text
    raw_cfg = json.loads((api_server.CONFIG_DIR / "social_hub_config.json").read_text(encoding="utf-8"))
    assert raw_cfg["api_settings"]["instagram"]["access_token"] == "EAAG_real_super_secret_token_9876"
    assert raw_cfg["api_settings"]["tiktok"]["client_secret"] == "tk_secret_4321"
    assert "highlight" in raw_cfg["categories"]["clipping"]["topic_keywords"]

    res_verify = client.post("/api/social-accounts/verify", json={"platform": "tiktok"})
    assert res_verify.status_code == 200, res_verify.text
    v_data = res_verify.json()
    assert v_data["platform"] == "tiktok"
    assert "status_label" in v_data and "detail" in v_data


def test_profile_multi_category_topic_filtering_and_short_categories_override(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    TDD:
    1) Un Perfil de Contenido guarda auto_categorize_by_topic + allowed_account_categories.
    2) El clasificador temático puede asignar múltiples categorías a un Short según el tema.
    3) POST /api/shorts/categories permite cambiar/eliminar categorías en cada Short redirigiendo YouTube/IG/TikTok/FB.
    """
    prof_res = client.post(
        "/api/content-profiles",
        json={
            "name": "Creador Gaming Stream",
            "match_keywords": ["creadorstudio", "gameplay"],
            "auto_categorize_by_topic": True,
            "allowed_account_categories": ["gaming", "clipping"],
            "scenes": [
                {
                    "rule_id": "scene_1",
                    "category": "videojuegos",
                    "scene_label": "Gameplay + Debate",
                    "layout_mode": "split_streamer",
                    "subtitle_preset": "hormozi_pop",
                    "subtitle_position": "center",
                    "cam_overlay_pos": "top_right",
                }
            ],
        },
    )
    assert prof_res.status_code == 200, prof_res.text
    prof = prof_res.json()
    assert prof["auto_categorize_by_topic"] is True
    assert prof["allowed_account_categories"] == ["gaming", "clipping"]

    # Clasificación temática multi-etiqueta: clip menciona tanto gameplay (rtx/juego) como clip viral/debate
    hub_cfg = api_server.social_hub.get_raw_social_hub_config(api_server.CONFIG_DIR)
    multi_cats = api_server.social_hub.classify_short_account_categories(
        text="Probando RTX 5090 en este juego nuevo y reaccionando al debate viral del stream",
        title="Gameplay con RTX y debate viral",
        tags=["gaming", "clip"],
        scene_category="videojuegos",
        scene_label="Gameplay + Debate",
        hub_cfg=hub_cfg,
        allowed_categories=["gaming", "clipping"],
        auto_by_topic=True,
    )
    assert "gaming" in multi_cats
    assert "clipping" in multi_cats

    # Cambiar manualmente categorías del Short existente en gallery -> ["principales", "gaming"]
    cat_res = client.post(
        "/api/shorts/categories",
        json={
            "short_rel_path": "test_stream/test_stream_02_Plata_80pts.mp4",
            "account_categories": ["principales", "gaming"],
        },
    )
    assert cat_res.status_code == 200, cat_res.text
    updated_short = cat_res.json()["short"]
    assert updated_short["account_categories"] == ["principales", "gaming"]
    assert updated_short["eligible_for_youtube"] is True
    assert any("creador_gaming" in h.lower() for h in updated_short["resolved_targets"]["instagram"])
    assert "facebook" in updated_short["social_statuses"]

    # Programar individualmente y verificar colas incluyendo facebook_queue
    monkeypatch.setattr(
        api_server.skill_uploader, "upload_scheduled_short", lambda **kw: {"id": "yt_multi_cat"}
    )
    sched_res = client.post(
        "/api/shorts/schedule-single",
        json={
            "short_rel_path": "test_stream/test_stream_02_Plata_80pts.mp4",
            "scheduled_time": "2026-11-16T15:00",
            "upload_to_youtube": True,
        },
    )
    assert sched_res.status_code == 200, sched_res.text
    queues = client.get("/api/queues").json()
    assert "facebook_queue" in queues
    assert any(
        "test_stream_02_Plata_80pts.mp4" in str(row.get("video_path", ""))
        for row in queues["facebook_queue"]
    )


def test_short_trim_extend_with_padded_srcclip_rerenders_new_duration(
    client: TestClient, temp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    TDD:
    1) render_vertical_short guarda .srcclip con colchón ±30s (hasta toda la duración disponible) + slice_origin_sec.
    2) Tras eliminar el video fuente original, POST /api/shorts/scene-detect expone [min_trim_sec, max_trim_sec]
       y POST /api/shorts/rerender permite ALARGAR el Short de 4s a 9s sin perder audio ni video.
    """
    import subprocess
    import imageio_ffmpeg

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    monkeypatch.setattr(
        api_server.skill_renderer, "_try_fetch_youtube_1080p60_slice", lambda *args, **kwargs: None
    )

    long_src = temp_workspace / "inbox_videos" / "pad_trim_src_12s.mp4"
    gen = subprocess.run(
        [
            ffmpeg_exe,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=640x360:rate=15:duration=12.0",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=12.0",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(long_src),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert gen.returncode == 0, gen.stderr

    out_dir = temp_workspace / "output_shorts" / "TrimProject"
    out_dir.mkdir(parents=True, exist_ok=True)
    rendered_mp4 = api_server.skill_renderer.render_vertical_short(
        video_path=long_src,
        start_time=4.0,
        end_time=8.0,
        word_timestamps=[{"word": "Hola", "start": 0.5, "end": 1.0}],
        context_word_timestamps=[
            {"word": "Antes", "start": 2.0, "end": 2.4},
            {"word": "Hola", "start": 4.5, "end": 5.0},
            {"word": "Despues", "start": 9.0, "end": 9.5},
        ],
        output_dir=out_dir,
        output_filename="TrimProject_01_Plata_78pts.mp4",
        layout_mode="fullscreen",
        enable_subtitles=True,
        enable_bgm=False,
    )
    assert rendered_mp4.exists()
    srcclip = out_dir / "TrimProject_01_Plata_78pts.srcclip"
    assert srcclip.exists()

    # Simular limpieza automática borrando el video largo original
    long_src.unlink()

    det_res = client.post(
        "/api/shorts/scene-detect",
        json={"short_rel_path": "TrimProject/TrimProject_01_Plata_78pts.mp4"},
    )
    assert det_res.status_code == 200, det_res.text
    det = det_res.json()
    assert det["min_trim_sec"] == 0.0
    assert det["max_trim_sec"] >= 11.5
    assert det["trim_start_sec"] == pytest.approx(4.0, abs=0.2)
    assert det["trim_end_sec"] == pytest.approx(8.0, abs=0.2)
    assert det["edit_media_url"]

    # Alargar el Short de 4.0s a 9.0s usando trim_start_sec=1.5, trim_end_sec=10.5
    rerender_res = client.post(
        "/api/shorts/rerender",
        json={
            "short_rel_path": "TrimProject/TrimProject_01_Plata_78pts.mp4",
            "layout_mode": "fullscreen",
            "cam_overlay_pos": "top_right",
            "subtitle_preset": "hormozi_pop",
            "subtitle_position": "bottom",
            "trim_start_sec": 1.5,
            "trim_end_sec": 10.5,
        },
    )
    assert rerender_res.status_code == 200, rerender_res.text
    rr = rerender_res.json()
    assert rr["rerendered"] is True
    assert rr["short"]["duration_sec"] == pytest.approx(9.0, abs=0.5)
    real_dur = api_server.skill_renderer._probe_media_duration_sec(rendered_mp4)
    assert real_dur == pytest.approx(9.0, abs=0.5)


def test_social_hub_ometv_builtin_and_custom_category_crud_and_routing(
    client: TestClient,
) -> None:
    """
    TDD:
    1) GET /api/social-accounts incluye la categoría 'ometv' ('Cuentas OMETV') precargada con @creador_ometv y Creador OMETV.
    2) POST /api/social-accounts/categories crea categorías personalizadas, rechaza duplicados y permite agregar cuentas vía PUT.
    3) POST /api/shorts/categories acepta 'ometv' y categorías personalizadas, rechazando inexistentes (400).
    4) DELETE /api/social-accounts/categories/{key} elimina categorías personalizadas y protege las categorías base.
    """
    res_get = client.get("/api/social-accounts")
    assert res_get.status_code == 200, res_get.text
    cats = res_get.json()["categories"]
    assert "ometv" in cats
    assert cats["ometv"]["label"] == "Cuentas OMETV"
    ometv_handles = {a["handle"].lower() for a in cats["ometv"]["accounts"]}
    assert "@creador_ometv" in ometv_handles
    assert "@creadorstudio" in ometv_handles
    assert "creador ometv" in ometv_handles

    # Crear categoría personalizada "Cuentas Podcast"
    res_create = client.post(
        "/api/social-accounts/categories",
        json={
            "label": "Cuentas Podcast",
            "description": "Debates y charlas largas",
            "topic_keywords": ["tertulia", "invitado"],
        },
    )
    assert res_create.status_code == 200, res_create.text
    created_body = res_create.json()
    new_key = created_body["created"]["key"]
    assert new_key == "podcast"
    assert created_body["categories"][new_key]["is_custom"] is True

    # Duplicado debe fallar con 400
    res_dup = client.post(
        "/api/social-accounts/categories",
        json={"label": "Podcast", "topic_keywords": ["otra"]},
    )
    assert res_dup.status_code == 400

    # Agregar cuenta en categoría personalizada vía PUT /api/social-accounts y verificar persistencia
    hub_payload = client.get("/api/social-accounts").json()
    hub_payload["categories"]["podcast"]["accounts"].append(
        {
            "id": "ig_podcast_custom",
            "platform": "instagram",
            "handle": "@creador_podcast",
            "display_name": "CreadorStudio Podcast",
            "external_id": "900000000000999",
            "enabled": True,
        }
    )
    res_put = client.put("/api/social-accounts", json=hub_payload)
    assert res_put.status_code == 200, res_put.text
    assert len(res_put.json()["categories"]["podcast"]["accounts"]) == 1

    # Enrutar Short existente a ["ometv", "podcast"] y rechazar categoría inválida
    res_assign = client.post(
        "/api/shorts/categories",
        json={
            "short_rel_path": "test_stream/test_stream_02_Plata_80pts.mp4",
            "account_categories": ["ometv", "podcast"],
        },
    )
    assert res_assign.status_code == 200, res_assign.text
    short_out = res_assign.json()["short"]
    assert short_out["account_categories"] == ["ometv", "podcast"]
    assert "@creador_ometv" in short_out["resolved_targets"]["instagram"]
    assert "@creador_podcast" in short_out["resolved_targets"]["instagram"]

    res_bad_cat = client.post(
        "/api/shorts/categories",
        json={
            "short_rel_path": "test_stream/test_stream_02_Plata_80pts.mp4",
            "account_categories": ["no_existe_xyz"],
        },
    )
    assert res_bad_cat.status_code == 400

    # No debe permitir eliminar categorías base, pero sí la personalizada
    assert client.delete("/api/social-accounts/categories/ometv").status_code == 400
    assert client.delete("/api/social-accounts/categories/principales").status_code == 400
    res_del = client.delete("/api/social-accounts/categories/podcast")
    assert res_del.status_code == 200, res_del.text
    assert "podcast" not in res_del.json()["categories"]


def test_project_naming_linked_to_video_and_date_no_random_ids(
    client: TestClient, temp_workspace: Path
) -> None:
    """
    TDD:
    1) main_daemon.build_video_date_project_id genera slugs deterministas '<Video>_<YYYY-MM-DD>'
       (o 'Proyecto_<YYYY-MM-DD>_<HHMM>' sin video), sin hex/prefijos aleatorios.
    2) POST /api/project/new crea proyectos independientes con nombre basado en fecha ('Proyecto_YYYY-MM-DD_HHMM'),
       nunca 'p_<hex>'.
    3) POST /api/project/rename migra un proyecto en espera al nombre vinculado al video + fecha,
       moviendo estado JSON y carpetas de salida/config, y /api/inbox + /api/pipeline/status exponen project_name.
    """
    from datetime import datetime
    import main_daemon
    import re
    import shutil

    fixed_now = datetime(2026, 11, 15, 22, 30, 0)
    assert main_daemon.build_video_date_project_id(None, now=fixed_now) == "Proyecto_2026-11-15_2230"
    video_pid = main_daemon.build_video_date_project_id("Mi Gameplay Épico #1.mp4", now=fixed_now)
    assert video_pid.startswith("Mi_Gameplay_Epico_1")
    assert video_pid.endswith("_2026-11-15")
    assert len(video_pid) <= 56

    res_new = client.post(
        "/api/project/new",
        json={"mode": "independent", "from_project_id": "default"},
    )
    assert res_new.status_code == 200, res_new.text
    new_data = res_new.json()
    new_pid = new_data["project_id"]
    assert re.match(r"^Proyecto_\d{4}-\d{2}-\d{2}_\d{4}(?:_\d+)?$", new_pid), f"ID inesperado: {new_pid}"
    assert new_data["project_name"] == new_pid
    assert new_data["pipeline_status"]["project_name"] == new_pid

    # Sembrar carpeta de proyecto antes de renombrar para probar migración completa
    old_out_dir = temp_workspace / "output_shorts" / "_projects" / new_pid
    old_out_dir.mkdir(parents=True, exist_ok=True)
    (old_out_dir / "marker.txt").write_text("keep", encoding="utf-8")

    try:
        res_rename = client.post(
            "/api/project/rename",
            json={
                "from_project_id": new_pid,
                "video_filename": "Partida Roblox Epica.mp4",
            },
        )
        assert res_rename.status_code == 200, res_rename.text
        ren_data = res_rename.json()
        renamed_pid = ren_data["project_id"]
        assert renamed_pid.startswith("Partida_Roblox_Epica_")
        assert re.search(r"_\d{4}-\d{2}-\d{2}$", renamed_pid)
        assert ren_data["project_name"] == renamed_pid
        assert (temp_workspace / "output_shorts" / "_projects" / renamed_pid / "marker.txt").exists()
        assert not old_out_dir.exists()

        status_res = client.get(f"/api/pipeline/status?project_id={renamed_pid}")
        assert status_res.status_code == 200
        assert status_res.json()["project_name"] == renamed_pid

        inbox_res = client.get(f"/api/inbox?project_id={renamed_pid}")
        assert inbox_res.status_code == 200
        assert inbox_res.json()["project_name"] == renamed_pid
    finally:
        client.post(f"/api/pipeline/cancel?project_id={new_pid}")
        shutil.rmtree(old_out_dir, ignore_errors=True)
        for p_dir in (temp_workspace / "output_shorts" / "_projects").glob("Partida_Roblox_Epica_*"):
            pid_cleanup = p_dir.name
            client.post(f"/api/pipeline/cancel?project_id={pid_cleanup}")
            shutil.rmtree(p_dir, ignore_errors=True)


def test_shorts_download_bundle_all_or_selected_and_auto_upload_disabled(
    client: TestClient, temp_workspace: Path
) -> None:
    """
    TDD:
    1) main_daemon.build_video_date_project_id limpia prefijos aleatorios compuestos y 'inbox_vi'
       ('p_mwiib95o_xgj_inbox_vi.mp4' -> 'Video_2026-11-16').
    2) POST /api/shorts/download-bundle descarga todos los Shorts válidos del proyecto en ZIP
       (ignorando _rendering_*.mp4), o solo los seleccionados si 'short_rel_paths' >= 2,
       o MP4 directo si 'short_rel_paths' tiene 1 elemento, y rechaza path traversal con 400.
    """
    from datetime import datetime
    import io
    import shutil
    import zipfile
    import main_daemon

    cleaned = main_daemon.build_video_date_project_id(
        "p_mwiib95o_xgj_inbox_vi.mp4",
        now=datetime(2026, 11, 16, 0, 10, 0),
    )
    assert cleaned == "Video_2026-11-16"

    pid = "TestDownload_2026-11-16"
    proj_dir = temp_workspace / "output_shorts" / "_projects" / pid / pid
    proj_dir.mkdir(parents=True, exist_ok=True)
    f1 = proj_dir / "clip_01_Oro_92pts.mp4"
    f2 = proj_dir / "clip_02_Plata_80pts.mp4"
    f3 = proj_dir / "clip_03_Meh_65pts.mp4"
    staging = proj_dir / "_rendering_temp.mp4"
    f1.write_bytes(b"mp4-one")
    f2.write_bytes(b"mp4-two")
    f3.write_bytes(b"mp4-three")
    staging.write_bytes(b"mp4-ignore")

    try:
        # 1) Descargar todos en ZIP (ignorando _rendering_temp.mp4)
        res_all = client.post("/api/shorts/download-bundle", json={"project_id": pid})
        assert res_all.status_code == 200, res_all.text
        assert "application/zip" in res_all.headers.get("content-type", "")
        with zipfile.ZipFile(io.BytesIO(res_all.content), "r") as zf:
            names = sorted(zf.namelist())
        assert names == [
            "clip_01_Oro_92pts.mp4",
            "clip_02_Plata_80pts.mp4",
            "clip_03_Meh_65pts.mp4",
        ]

        # 2) Descargar solo 2 seleccionados en ZIP
        res_sel = client.post(
            "/api/shorts/download-bundle",
            json={
                "project_id": pid,
                "short_rel_paths": [
                    f"_projects/{pid}/{pid}/clip_01_Oro_92pts.mp4",
                    f"_projects/{pid}/{pid}/clip_03_Meh_65pts.mp4",
                ],
            },
        )
        assert res_sel.status_code == 200, res_sel.text
        assert "application/zip" in res_sel.headers.get("content-type", "")
        with zipfile.ZipFile(io.BytesIO(res_sel.content), "r") as zf:
            sel_names = sorted(zf.namelist())
        assert sel_names == ["clip_01_Oro_92pts.mp4", "clip_03_Meh_65pts.mp4"]

        # 3) Descargar exactamente 1 Short -> entrega MP4 directo
        res_one = client.post(
            "/api/shorts/download-bundle",
            json={
                "project_id": pid,
                "short_rel_paths": [f"_projects/{pid}/{pid}/clip_02_Plata_80pts.mp4"],
            },
        )
        assert res_one.status_code == 200, res_one.text
        assert "video/mp4" in res_one.headers.get("content-type", "")
        assert res_one.content == b"mp4-two"

        # 4) Rechazar path traversal
        res_bad = client.post(
            "/api/shorts/download-bundle",
            json={"short_rel_paths": ["../../secret.mp4"]},
        )
        assert res_bad.status_code == 400
    finally:
        shutil.rmtree(temp_workspace / "output_shorts" / "_projects" / pid, ignore_errors=True)


def test_live_stream_monitor_rolling_windows_dedup_profile_routing_and_api_lifecycle(
    client: TestClient, temp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    TDD (Pestaña Directo en Vivo):
    1) GET /api/live/status inicia en IDLE y POST /api/live/start valida URL remota (400) y perfil existente (404).
    2) live_stream_monitor.resolve_live_stream_inputs rechaza directos aún no iniciados (is_upcoming)
       y extrae streams HLS activos (m3u8); is_duplicate_live_moment filtra solapamientos.
    3) El ciclo de captura por bloques rodantes (capture -> solapamiento -> análisis IA -> filtro de puntaje ->
       render 9:16 + _meta.json con Perfil de Contenido -> dedup -> cleanup) produce Shorts reales
       visibles en /api/shorts y responde a /api/live/stop.
    """
    import subprocess
    import time
    import shutil
    from pathlib import Path
    import imageio_ffmpeg
    import yt_dlp
    import main_daemon
    import live_stream_monitor

    res_idle = client.get("/api/live/status")
    assert res_idle.status_code == 200, res_idle.text
    idle_data = res_idle.json()
    assert idle_data["status"] == "IDLE"
    assert idle_data["segments_captured"] == 0
    assert idle_data["shorts_generated"] == 0

    # Validación URL y perfil
    assert (
        client.post(
            "/api/live/start",
            json={"stream_url": "https://example.com/not-live"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/live/start",
            json={
                "stream_url": "https://www.youtube.com/live/vf1gzPlYPY8",
                "profile_id": 999999,
            },
        ).status_code
        == 404
    )

    # Pruebas unitarias de resolución HLS / rechazo is_upcoming y deduplicación
    class _FakeYdlUpcoming:
        def __init__(self, opts):
            self.opts = opts
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def extract_info(self, url, download=False):
            return {"id": "up1", "title": "Espera", "live_status": "is_upcoming", "is_live": False}

    monkeypatch.setattr(yt_dlp, "YoutubeDL", _FakeYdlUpcoming)
    with pytest.raises(ValueError, match="no ha iniciado"):
        live_stream_monitor.resolve_live_stream_inputs("https://www.youtube.com/live/vf1gzPlYPY8")

    class _FakeYdlLiveHls:
        def __init__(self, opts):
            self.opts = opts
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def extract_info(self, url, download=False):
            return {
                "id": "live123",
                "title": "Directo Real 1080p",
                "live_status": "is_live",
                "is_live": True,
                "formats": [
                    {
                        "url": "https://manifest.example.com/live/playlist.m3u8",
                        "protocol": "m3u8_native",
                        "vcodec": "avc1.640028",
                        "acodec": "mp4a.40.2",
                        "height": 1080,
                    }
                ],
            }

    monkeypatch.setattr(yt_dlp, "YoutubeDL", _FakeYdlLiveHls)
    resolved = live_stream_monitor.resolve_live_stream_inputs("https://www.youtube.com/live/vf1gzPlYPY8")
    assert resolved["is_live"] is True
    assert resolved["video_url"].endswith(".m3u8")

    seen_tokens: list = []
    t1 = "Increíble clutch en el torneo de Fortnite en vivo sin balas"
    assert live_stream_monitor.is_duplicate_live_moment(t1, seen_tokens) is False
    assert live_stream_monitor.is_duplicate_live_moment("clutch torneo Fortnite en vivo sin balas ahora", seen_tokens) is True
    assert live_stream_monitor.is_duplicate_live_moment("Ahora estamos reaccionando a otro video completamente distinto en OmeTV", seen_tokens) is False

    # Crear Perfil de Contenido real con categoría gaming
    prof_res = client.post(
        "/api/content-profiles",
        json={
            "name": "Live Gaming Test",
            "match_keywords": ["directo", "fortnite"],
            "auto_categorize_by_topic": False,
            "allowed_account_categories": ["gaming"],
            "scenes": [
                {
                    "rule_id": "r1",
                    "category": "videojuegos",
                    "scene_label": "Gameplay",
                    "detected_share_pct": 100,
                    "layout_mode": "fullscreen",
                    "subtitle_preset": "hormozi_pop",
                    "subtitle_position": "bottom",
                    "cam_overlay_pos": "top_right",
                    "custom_boxes_manual": False,
                }
            ],
        },
    )
    assert prof_res.status_code == 200, prof_res.text
    prof_id = prof_res.json()["id"]

    # Generar chunk MP4 1280x720 real (25s para cumplir mínimo 20s de ViralClipAnalysis)
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    live_src_mp4 = temp_workspace / "live_chunk_fixture.mp4"
    proc_gen = subprocess.run(
        [
            ffmpeg_exe, "-y",
            "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30:duration=25",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=25",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(live_src_mp4),
        ],
        capture_output=True, text=True, check=False,
    )
    assert proc_gen.returncode == 0, proc_gen.stderr

    chunk_calls = {"n": 0}

    def _fake_capture_chunk(stream_url, output_chunk_path, duration_sec, stop_event, session=None):
        chunk_calls["n"] += 1
        output_chunk_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(live_src_mp4), str(output_chunk_path))
        if chunk_calls["n"] >= 2:
            stop_event.set()
        return {
            "cancelled": False,
            "chunk_path": output_chunk_path,
            "title": "Directo Epico en Vivo",
            "is_live": True,
        }

    def _fake_analyze(video_path, max_shorts=3, enable_jumpcuts=True, **kwargs):
        idx = chunk_calls["n"]
        clip_strong_1 = main_daemon.skill_transcriber.ViralClipAnalysis(
            start_time=1.0,
            end_time=23.0,
            hook_title="🔥 ¡INCREÍBLE CLUTCH IMPOSIBLE EN TORNEO! #Shorts",
            first_person_caption="¡No puedo creer este último segundo brutal en directo!",
            tags=["Gaming", "Shorts"],
            bgm_mood="impacto",
            word_timestamps=[{"word": "Increíble", "start": 0.2, "end": 0.8}],
            transcript_excerpt="¡Increíble clutch imposible en torneo! No puedo creer lo que acaba de pasar en el último segundo.",
            hook_strength=9.8,
            standalone_value=9.6,
            virality_potential=9.7,
            acoustic_energy_score=9.4,
        )
        clip_weak = main_daemon.skill_transcriber.ViralClipAnalysis(
            start_time=0.5,
            end_time=21.5,
            hook_title="Saludos",
            first_person_caption="hola buenas como estan",
            tags=["Directo"],
            bgm_mood="reflexion",
            word_timestamps=[],
            transcript_excerpt="hola buenas como estan bienvenidos",
            hook_strength=1.5,
            standalone_value=1.5,
            virality_potential=1.5,
            acoustic_energy_score=1.5,
        )
        clip_strong_2 = main_daemon.skill_transcriber.ViralClipAnalysis(
            start_time=2.0,
            end_time=24.0,
            hook_title="😱 ¡EXPLOTÓ TODO EL MAPA EN DIRECTO! #Shorts",
            first_person_caption="¡Mira la trampa oculta que activó el jefe final!",
            tags=["Fortnite", "Clip"],
            bgm_mood="impacto",
            word_timestamps=[{"word": "Mentira", "start": 0.3, "end": 0.9}],
            transcript_excerpt="¡Mentira! Mira cómo explotó todo el mapa en directo cuando saltó la trampa oculta del servidor.",
            hook_strength=9.7,
            standalone_value=9.5,
            virality_potential=9.6,
            acoustic_energy_score=9.2,
        )
        if idx == 1:
            return [clip_strong_1, clip_weak]
        return [clip_strong_1, clip_strong_2]

    monkeypatch.setattr(live_stream_monitor, "capture_live_window_chunk", _fake_capture_chunk)
    monkeypatch.setattr(api_server.skill_analyzer, "transcribe_and_analyze_multiple", _fake_analyze)

    live_pid = "LiveTest_2026-11-16"
    try:
        start_res = client.post(
            "/api/live/start",
            json={
                "stream_url": "https://www.youtube.com/live/vf1gzPlYPY8",
                "profile_id": prof_id,
                "chunk_duration_sec": 60,
                "overlap_sec": 15,
                "min_virality_score": 70,
                "max_shorts_total": 5,
                "project_id": live_pid,
            },
        )
        assert start_res.status_code == 200, start_res.text

        final_st = None
        deadline = time.time() + 25.0
        while time.time() < deadline:
            st_res = client.get(f"/api/live/status?project_id={live_pid}")
            assert st_res.status_code == 200
            st_json = st_res.json()
            if st_json["status"] in ("STOPPED", "COMPLETED", "ERROR"):
                final_st = st_json
                break
            time.sleep(0.25)

        assert final_st is not None, "El monitor en vivo no terminó a tiempo"
        assert final_st["status"] in ("STOPPED", "COMPLETED"), final_st
        assert final_st["segments_captured"] == 2
        assert final_st["segments_analyzed"] == 2
        assert final_st["shorts_generated"] == 2
        assert len(final_st["recent_clips"]) == 2

        shorts_res = client.get(f"/api/shorts?project_id={live_pid}")
        assert shorts_res.status_code == 200
        shorts_body = shorts_res.json()
        assert shorts_body["total"] == 2
        assert all(s["account_categories"] == ["gaming"] for s in shorts_body["shorts"])

        stop_res = client.post(f"/api/live/stop?project_id={live_pid}")
        assert stop_res.status_code == 200
        assert stop_res.json()["status"] in ("STOPPED", "COMPLETED")
    finally:
        client.post(f"/api/live/stop?project_id={live_pid}")
        shutil.rmtree(temp_workspace / "output_shorts" / "_projects" / live_pid, ignore_errors=True)
        shutil.rmtree(temp_workspace / "processing" / "live_chunks", ignore_errors=True)


def test_social_scheduling_nonblocking_oauth_tiktok_chunk_floor_and_facebook_dispatcher(
    client: TestClient, temp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    TDD Red -> Green:
    1) YouTube OAuth no bloquea endpoints HTTP cuando refresh_token expiró (allow_interactive=False),
       registra FAILED/error en scheduled_slots y devuelve youtube_error sin colgar el flujo.
    2) build_upload_body publica inmediato ('public') cuando publish_at_iso es pasado o <= +5 min,
       mantiene 'private' + publishAt si es > 5 min futuro, y respeta category_id numérico ('20').
    3) tiktok_api_uploader.compute_tiktok_chunk_plan usa math.floor (100,648,585 bytes -> 9 bloques),
       upload_video_chunks envía 9 PUTs cubriendo hasta el byte 100648584 sin exceder total_chunk_count.
    4) verify_platform_connection('youtube') detecta token.json revocado (connected=False).
    5) social_hub.process_due_facebook_queue + api_server.run_due_social_queues publican filas PENDING vencidas
       y POST /api/social-accounts/youtube/authorize ejecuta flujo interactivo con timeout.
    """
    import importlib.util
    import json
    import sqlite3
    import sys
    from datetime import datetime, timedelta, timezone
    from config import social_hub

    cfg_dir = temp_workspace / "config"
    db_path = cfg_dir / "schedule_state.db"

    # Cargar tiktok_api_uploader directamente desde la skill
    tt_mod_path = api_server.SKILLS_DIR / "multi-social-uploader" / "tiktok_api_uploader.py"
    spec = importlib.util.spec_from_file_location("test_tt_uploader_mod", str(tt_mod_path))
    assert spec is not None and spec.loader is not None
    tt_uploader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tt_uploader)

    # 1) YouTube OAuth no interactivo cuando el refresh token expiró (invalid_grant)
    (cfg_dir / "client_secret.json").write_text(
        json.dumps({"installed": {"client_id": "cid", "client_secret": "csec"}}), encoding="utf-8"
    )
    (cfg_dir / "token.json").write_text(
        json.dumps(
            {
                "token": "expired",
                "refresh_token": "revoked_refresh",
                "client_id": "cid",
                "client_secret": "csec",
            }
        ),
        encoding="utf-8",
    )

    class _RevokedCreds:
        valid = False
        expired = True
        refresh_token = "revoked_refresh"

        def refresh(self, _req) -> None:
            raise Exception("invalid_grant: Token has been expired or revoked.")

        def to_json(self) -> str:
            return "{}"

    interactive_calls: List[Any] = []
    monkeypatch.setattr(
        api_server.skill_uploader.Credentials,
        "from_authorized_user_file",
        classmethod(lambda cls, *_a, **_kw: _RevokedCreds()),
    )
    monkeypatch.setattr(
        api_server.skill_uploader.InstalledAppFlow,
        "from_client_secrets_file",
        classmethod(lambda cls, *a, **kw: interactive_calls.append((a, kw))),
    )

    with pytest.raises(RuntimeError, match="Autorizar OAuth"):
        api_server.skill_uploader.get_authenticated_youtube_service(
            client_secret_path=cfg_dir / "client_secret.json",
            token_path=cfg_dir / "token.json",
            allow_interactive=False,
        )
    assert interactive_calls == []

    # 2) verify_platform_connection detecta token revocado
    yt_ver = social_hub.verify_platform_connection(cfg_dir, "youtube")
    assert yt_ver["connected"] is False
    assert "expirad" in (yt_ver["status_label"] + yt_ver["detail"]).lower()

    # 3) build_upload_body: pasado/inmediato vs futuro (>5m) y category_id numérico
    past_iso = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    near_iso = (datetime.now(timezone.utc) + timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    future_iso = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")

    body_past = api_server.skill_uploader.build_upload_body("Test", "Desc", ["Shorts"], past_iso, category_id="20")
    assert body_past["snippet"]["categoryId"] == "20"
    assert body_past["status"]["privacyStatus"] == "public"
    assert "publishAt" not in body_past["status"]

    body_near = api_server.skill_uploader.build_upload_body("Test", "Desc", ["Shorts"], near_iso, category_id="20")
    assert body_near["status"]["privacyStatus"] == "public"
    assert "publishAt" not in body_near["status"]

    body_future = api_server.skill_uploader.build_upload_body("Test", "Desc", ["Shorts"], future_iso, category_id="20")
    assert body_future["status"]["privacyStatus"] == "private"
    assert body_future["status"]["publishAt"] == future_iso

    # 4) TikTok chunk math (math.floor + resto absorbido en el último bloque)
    assert tt_uploader.compute_tiktok_chunk_plan(10 * 1024 * 1024) == (10 * 1024 * 1024, 1)
    assert tt_uploader.compute_tiktok_chunk_plan(60 * 1024 * 1024) == (60 * 1024 * 1024, 1)
    chunk_sz, total_chunks = tt_uploader.compute_tiktok_chunk_plan(100_648_585)
    assert chunk_sz == 10 * 1024 * 1024
    assert total_chunks == 9

    sparse_mp4 = temp_workspace / "processing" / "sparse_100mb.mp4"
    with sparse_mp4.open("wb") as fp:
        fp.seek(100_648_585 - 1)
        fp.write(b"\x00")

    put_ranges: List[str] = []

    class _FakePutResp:
        status_code = 206
        text = ""

    def _fake_put(_url: str, headers: Dict[str, str], data: bytes, timeout: int = 180):
        put_ranges.append(f"{headers['Content-Range']}|{len(data)}")
        return _FakePutResp()

    monkeypatch.setattr(tt_uploader.requests, "put", _fake_put)
    tt_uploader.upload_video_chunks("https://upload.tiktok.test/put", str(sparse_mp4), chunk_sz, total_chunks)
    assert len(put_ranges) == 9
    assert put_ranges[0].startswith(f"bytes 0-{chunk_sz - 1}/100648585|{chunk_sz}")
    assert put_ranges[-1] == f"bytes {8 * chunk_sz}-100648584/100648585|{100_648_585 - 8 * chunk_sz}"

    # 5) schedule-single y schedule batch con fallo YT no bloquean, limpian error previo en colas y reportan youtube_error
    short_rel = "test_stream/test_stream_02_Plata_80pts.mp4"
    short_mp4 = temp_workspace / "output_shorts" / "test_stream" / "test_stream_02_Plata_80pts.mp4"
    api_server.skill_ig_scheduler.enqueue_instagram_reel(
        video_path=str(short_mp4),
        account_key="creador_short",
        caption="prev",
        scheduled_time_utc=past_iso,
        scheduled_time_ast="prev AST",
        db_path=db_path,
    )
    api_server.skill_tt_scheduler.enqueue_tiktok_video(
        video_path=str(short_mp4),
        account_key="creador.clips",
        caption="prev",
        scheduled_time_utc=past_iso,
        scheduled_time_ast="prev AST",
        db_path=db_path,
    )
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "UPDATE instagram_scheduled_queue SET status='FAILED', error='old err' WHERE video_path LIKE ?",
            ("%test_stream_02_Plata_80pts.mp4",),
        )
        conn.execute(
            "UPDATE tiktok_scheduled_queue SET status='FAILED', error='total chunk count' WHERE video_path LIKE ?",
            ("%test_stream_02_Plata_80pts.mp4",),
        )
        conn.commit()

    def _fail_yt_no_hang(**kwargs: Any) -> Dict[str, Any]:
        assert kwargs.get("allow_interactive") is False
        raise RuntimeError("Sesión OAuth de YouTube expirada. Pulsa Autorizar OAuth.")

    monkeypatch.setattr(api_server.skill_uploader, "upload_scheduled_short", _fail_yt_no_hang)
    res_single = client.post(
        "/api/shorts/schedule-single",
        json={
            "short_rel_path": short_rel,
            "scheduled_time": "2026-12-20T18:30",
            "upload_to_youtube": True,
        },
    )
    assert res_single.status_code == 200, res_single.text
    b_single = res_single.json()
    assert b_single["scheduled"] is True
    assert "Autorizar OAuth" in (b_single.get("youtube_error") or "")

    with sqlite3.connect(str(db_path)) as conn:
        ig_errs = conn.execute(
            "SELECT status, error FROM instagram_scheduled_queue WHERE video_path LIKE ?",
            ("%test_stream_02_Plata_80pts.mp4",),
        ).fetchall()
        tt_errs = conn.execute(
            "SELECT status, error FROM tiktok_scheduled_queue WHERE video_path LIKE ?",
            ("%test_stream_02_Plata_80pts.mp4",),
        ).fetchall()
        assert ig_errs and all(r[0] == "PENDING" and r[1] is None for r in ig_errs)
        assert tt_errs and all(r[0] == "PENDING" and r[1] is None for r in tt_errs)

    shorts_after = client.get("/api/shorts").json()["shorts"]
    s02 = next(s for s in shorts_after if s["filename"] == "test_stream_02_Plata_80pts.mp4")
    assert s02["social_statuses"]["youtube"]["state"] == "error"

    res_batch = client.post(
        "/api/shorts/schedule",
        json={
            "youtube_start_time": "2026-12-21T14:00",
            "instagram_start_time": "2026-12-21T14:00",
            "tiktok_start_time": "2026-12-21T14:00",
            "interval_minutes": 60,
            "auto_upload_positive_to_youtube": True,
        },
    )
    assert res_batch.status_code == 200, res_batch.text
    assert "Autorizar OAuth" in (res_batch.json().get("youtube_error") or "")

    # 6) Facebook Dispatcher + run_due_social_queues
    (cfg_dir / "meta_token.json").write_text(
        json.dumps(
            {
                "access_token": "EAAG_USER",
                "fb_pages": {
                    "creadorstudio gaming": {
                        "page_id": "900000000000011",
                        "page_name": "Creador Gaming",
                        "page_access_token": "EAAG_PAGE_GAMING",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    social_hub.enqueue_facebook_reel(
        video_path=short_mp4,
        account_key="Creador Gaming",
        fb_page_id="900000000000011",
        caption="Clip FB",
        scheduled_time_utc=past_iso,
        scheduled_time_ast="pasado",
        db_path=db_path,
    )
    fb_posts: List[str] = []

    class _FakeFbResp:
        status_code = 200

        def json(self) -> Dict[str, Any]:
            return {"id": "fb_post_777"}

    def _fake_fb_post(url: str, data: Dict[str, Any], files: Dict[str, Any], timeout: int = 180):
        fb_posts.append(url)
        assert data["access_token"] == "EAAG_PAGE_GAMING"
        assert "source" in files
        return _FakeFbResp()

    monkeypatch.setattr(social_hub, "_http_post_multipart", _fake_fb_post)
    monkeypatch.setattr(
        api_server.skill_ig_scheduler,
        "process_due_instagram_queue",
        lambda **_kw: {"processed": 0, "published": 0, "failed": 0},
    )
    monkeypatch.setattr(
        api_server.skill_tt_scheduler,
        "process_due_tiktok_queue",
        lambda **_kw: {"processed": 0, "published": 0, "failed": 0},
    )

    dispatch_res = api_server.run_due_social_queues()
    assert dispatch_res["facebook"]["published"] == 1
    assert any("900000000000011/videos" in u for u in fb_posts)

    # 7) Endpoint POST /api/social-accounts/youtube/authorize
    auth_calls: List[Dict[str, Any]] = []

    class _FreshValidCreds:
        valid = True
        expired = False
        refresh_token = "new_refresh"

    monkeypatch.setattr(
        api_server.skill_uploader,
        "get_authenticated_youtube_service",
        lambda **kw: auth_calls.append(kw) or "yt_service",
    )
    monkeypatch.setattr(
        api_server.skill_uploader.Credentials,
        "from_authorized_user_file",
        classmethod(lambda cls, *_a, **_kw: _FreshValidCreds()),
    )

    auth_res = client.post("/api/social-accounts/youtube/authorize")
    assert auth_res.status_code == 200, auth_res.text
    assert auth_calls and auth_calls[0]["allow_interactive"] is True
    assert auth_res.json()["connected"] is True


def test_tiktok_inbox_draft_honest_status_permalinks_and_youtube_oauth_auto_retry(
    client: TestClient, temp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    TDD Red -> Green:
    1) TikTok SEND_TO_USER_INBOX / v_inbox_file% se guarda y reporta como 'INBOX_DRAFT' ('En Borrador (App)', 85%),
       nunca verde 'Subido', y migra filas heredadas v_inbox_file% sin post_id al consultar /api/shorts.
    2) Los social_statuses y /api/queues exponen enlaces directos permalink reales para YouTube, Instagram, Facebook
       y TikTok PUBLISH_COMPLETE (con post_id).
    3) POST /api/social-accounts/youtube/authorize reintenta en segundo plano slots de YouTube sin youtube_video_id
       respetando su publish_at_utc y actualiza la barra a 'Subido' con su permalink.
    """
    import json
    import sqlite3
    from datetime import datetime, timedelta, timezone
    from config import social_hub

    cfg_dir = temp_workspace / "config"
    db_path = cfg_dir / "schedule_state.db"
    out_dir = temp_workspace / "output_shorts" / "test_stream"
    out_dir.mkdir(parents=True, exist_ok=True)

    short_02 = out_dir / "test_stream_02_Plata_80pts.mp4"
    short_97 = out_dir / "test_stream_97_Plata_85pts.mp4"
    short_98 = out_dir / "test_stream_98_Plata_86pts.mp4"
    short_97.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32)
    short_98.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32)

    past_iso = (datetime.now(timezone.utc) - timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1) TikTok SEND_TO_USER_INBOX -> INBOX_DRAFT
    api_server.skill_tt_scheduler.enqueue_tiktok_video(
        video_path=str(short_02),
        account_key="creador.gaming",
        caption="Borrador inbox",
        scheduled_time_utc=past_iso,
        scheduled_time_ast="2026-11-16 10:00 AM AST",
        db_path=db_path,
    )
    api_server.skill_tt_scheduler.enqueue_tiktok_video(
        video_path=str(short_98),
        account_key="creador.short",
        caption="Publicado directo",
        scheduled_time_utc=past_iso,
        scheduled_time_ast="2026-11-16 10:00 AM AST",
        db_path=db_path,
    )

    def _fake_tt_publish(account_key: str, _vp: str, _cap: str, mode: str = "AUTO") -> Dict[str, Any]:
        if account_key == "creador.gaming":
            return {
                "status": "SEND_TO_USER_INBOX",
                "publish_id": "v_inbox_file~v2.7708778085709481990",
                "post_id": None,
                "mode": mode,
            }
        return {
            "status": "PUBLISH_COMPLETE",
            "publish_id": "v_pub_file~v2.999999",
            "post_id": "770999888",
            "mode": mode,
        }

    monkeypatch.setattr(api_server.skill_tt_scheduler, "publish_tiktok_video", _fake_tt_publish)
    tt_res = api_server.skill_tt_scheduler.process_due_tiktok_queue(db_path=db_path)
    assert tt_res["published"] == 2

    with sqlite3.connect(str(db_path)) as conn:
        st_02 = conn.execute(
            "SELECT status, publish_id, post_id FROM tiktok_scheduled_queue WHERE video_path LIKE ?",
            ("%test_stream_02_Plata_80pts.mp4",),
        ).fetchone()
        st_98 = conn.execute(
            "SELECT status, publish_id, post_id FROM tiktok_scheduled_queue WHERE video_path LIKE ?",
            ("%test_stream_98_Plata_86pts.mp4",),
        ).fetchone()
        assert st_02 == ("INBOX_DRAFT", "v_inbox_file~v2.7708778085709481990", "")
        assert st_98 == ("PUBLISHED", "v_pub_file~v2.999999", "770999888")

    # Re-encolar INBOX_DRAFT no lo regresa a PENDING
    api_server.skill_tt_scheduler.enqueue_tiktok_video(
        video_path=str(short_02),
        account_key="creador.gaming",
        caption="Borrador inbox v2",
        scheduled_time_utc=past_iso,
        scheduled_time_ast="2026-11-16 11:00 AM AST",
        db_path=db_path,
    )
    with sqlite3.connect(str(db_path)) as conn:
        assert conn.execute(
            "SELECT status FROM tiktok_scheduled_queue WHERE video_path LIKE ?",
            ("%test_stream_02_Plata_80pts.mp4",),
        ).fetchone()[0] == "INBOX_DRAFT"

    # Fila legacy mal marcada PUBLISHED con v_inbox_file% debe migrarse automáticamente a INBOX_DRAFT
    api_server.skill_tt_scheduler.enqueue_tiktok_video(
        video_path=str(short_97),
        account_key="creadorstudio.legacy",
        caption="Legacy inbox",
        scheduled_time_utc=past_iso,
        scheduled_time_ast="2026-11-16 09:00 AM AST",
        db_path=db_path,
    )
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "UPDATE tiktok_scheduled_queue SET status='PUBLISHED', publish_id='v_inbox_file~v2.legacy123', post_id='' WHERE video_path LIKE ?",
            ("%test_stream_97_Plata_85pts.mp4",),
        )
        conn.commit()

    # 2) Instagram PUBLISHED (con permalink), Facebook PUBLISHED (con post_id) y YouTube FAILED + PUBLISHED
    api_server.skill_ig_scheduler.enqueue_instagram_reel(
        video_path=str(short_02),
        account_key="creador_gaming",
        caption="IG clip",
        scheduled_time_utc=past_iso,
        scheduled_time_ast="2026-11-16 10:00 AM AST",
        db_path=db_path,
    )
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "UPDATE instagram_scheduled_queue SET status='PUBLISHED', permalink='https://www.instagram.com/reel/DfyPDgVAnAy/' WHERE video_path LIKE ?",
            ("%test_stream_02_Plata_80pts.mp4",),
        )
        conn.commit()

    social_hub.enqueue_facebook_reel(
        video_path=short_02,
        account_key="Creador Gaming",
        fb_page_id="900000000000011",
        caption="FB clip",
        scheduled_time_utc=past_iso,
        scheduled_time_ast="2026-11-16 10:00 AM AST",
        db_path=db_path,
    )
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "UPDATE facebook_scheduled_queue SET status='PUBLISHED', post_id='900000000000015' WHERE video_path LIKE ?",
            ("%test_stream_02_Plata_80pts.mp4",),
        )
        conn.commit()

    api_server._ensure_youtube_slots_columns(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO scheduled_slots (
                video_name, slot_ast, publish_at_utc, youtube_video_id, status, error, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "test_stream_02_Plata_80pts.mp4",
                "2026-12-20 06:30 PM AST",
                "2026-12-20T22:30:00Z",
                None,
                "FAILED",
                "Sesión OAuth de YouTube expirada o sin autorizar (invalid_grant).",
                past_iso,
            ),
        )
        conn.execute(
            """
            INSERT INTO scheduled_slots (
                video_name, slot_ast, publish_at_utc, youtube_video_id, status, error, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "test_stream_98_Plata_86pts.mp4",
                "2026-12-20 07:30 PM AST",
                "2026-12-20T23:30:00Z",
                "ytPub98abc",
                "PUBLISHED",
                None,
                past_iso,
            ),
        )
        conn.commit()

    shorts_res = client.get("/api/shorts")
    assert shorts_res.status_code == 200, shorts_res.text
    shorts = shorts_res.json()["shorts"]

    s02 = next(s for s in shorts if s["filename"] == "test_stream_02_Plata_80pts.mp4")
    s97 = next(s for s in shorts if s["filename"] == "test_stream_97_Plata_85pts.mp4")
    s98 = next(s for s in shorts if s["filename"] == "test_stream_98_Plata_86pts.mp4")

    # Migración automática en DB de legacy row
    with sqlite3.connect(str(db_path)) as conn:
        assert conn.execute(
            "SELECT status FROM tiktok_scheduled_queue WHERE video_path LIKE ?",
            ("%test_stream_97_Plata_85pts.mp4",),
        ).fetchone()[0] == "INBOX_DRAFT"

    assert s97["social_statuses"]["tiktok"]["status_label"] == "En Borrador (App)"
    assert s97["social_statuses"]["tiktok"]["percent"] == 85
    assert s97["social_statuses"]["tiktok"]["state"] != "uploaded"
    assert not s97["social_statuses"]["tiktok"].get("permalink")

    assert s02["social_statuses"]["tiktok"]["status_label"] == "En Borrador (App)"
    assert s02["social_statuses"]["tiktok"]["percent"] == 85
    assert s02["social_statuses"]["tiktok"]["state"] != "uploaded"
    assert not s02["social_statuses"]["tiktok"].get("permalink")
    assert s02["social_statuses"]["instagram"]["permalink"] == "https://www.instagram.com/reel/DfyPDgVAnAy/"
    assert s02["social_statuses"]["facebook"]["permalink"] == "https://www.facebook.com/reel/900000000000015/"

    assert s98["social_statuses"]["tiktok"]["status_label"] == "Subido"
    assert s98["social_statuses"]["tiktok"]["permalink"] == "https://www.tiktok.com/@creador.short/video/770999888"
    assert s98["social_statuses"]["youtube"]["permalink"] == "https://www.youtube.com/shorts/ytPub98abc"

    queues_res = client.get("/api/queues")
    assert queues_res.status_code == 200
    q_data = queues_res.json()
    assert q_data["instagram_queue"][0]["permalink"] == "https://www.instagram.com/reel/DfyPDgVAnAy/"
    assert q_data["facebook_queue"][0]["post_id"] == "900000000000015"
    assert q_data["facebook_queue"][0]["permalink"] == "https://www.facebook.com/reel/900000000000015/"
    tt_pub_q = next(item for item in q_data["tiktok_queue"] if item.get("post_id") == "770999888")
    assert tt_pub_q["permalink"] == "https://www.tiktok.com/@creador.short/video/770999888"

    # 3) Authorize OAuth reintenta automáticamente slots de YouTube pendientes/fallidos sin youtube_video_id
    (cfg_dir / "client_secret.json").write_text(
        json.dumps({"installed": {"client_id": "cid", "client_secret": "csec"}}), encoding="utf-8"
    )

    class _ValidCreds:
        valid = True
        expired = False
        refresh_token = "ok_refresh"

    retried_uploads: List[Dict[str, Any]] = []

    def _fake_upload_retry(**kw: Any) -> Dict[str, Any]:
        retried_uploads.append(kw)
        return {"id": "ytRetried02", "status": "uploaded"}

    def _fake_auth_service(**_kw: Any) -> str:
        (cfg_dir / "token.json").write_text(
            json.dumps(
                {
                    "token": "fresh_tok",
                    "refresh_token": "ok_refresh",
                    "client_id": "cid",
                    "client_secret": "csec",
                }
            ),
            encoding="utf-8",
        )
        return "yt_service_ok"

    monkeypatch.setattr(
        api_server.skill_uploader,
        "get_authenticated_youtube_service",
        _fake_auth_service,
    )
    monkeypatch.setattr(
        api_server.skill_uploader.Credentials,
        "from_authorized_user_file",
        classmethod(lambda cls, *_a, **_kw: _ValidCreds()),
    )
    monkeypatch.setattr(api_server.skill_uploader, "upload_scheduled_short", _fake_upload_retry)

    auth_res = client.post("/api/social-accounts/youtube/authorize")
    assert auth_res.status_code == 200, auth_res.text
    auth_body = auth_res.json()
    assert auth_body["connected"] is True
    # Retries BOTH the seeded PENDING slot (test_stream_01) and the FAILED slot (test_stream_02)
    assert auth_body.get("retried_youtube_slots") == 2

    retry_thread = getattr(api_server, "_youtube_retry_thread", None)
    if retry_thread is not None:
        retry_thread.join(timeout=3.0)

    assert len(retried_uploads) == 2
    assert all(call["allow_interactive"] is False for call in retried_uploads)
    retry_s02 = next(
        call for call in retried_uploads if call["video_path"].name == "test_stream_02_Plata_80pts.mp4"
    )
    assert retry_s02["publish_at_iso"] == "2026-12-20T22:30:00Z"

    s02_after = next(
        s for s in client.get("/api/shorts").json()["shorts"] if s["filename"] == "test_stream_02_Plata_80pts.mp4"
    )
    assert s02_after["social_statuses"]["youtube"]["state"] == "uploaded"
    assert s02_after["social_statuses"]["youtube"]["status_label"] == "Subido"
    assert s02_after["social_statuses"]["youtube"]["permalink"] == "https://www.youtube.com/shorts/ytRetried02"


def test_youtube_oauth_browser_nonblocking_start_callback_and_auto_retry(
    client: TestClient, temp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    TDD Red -> Green:
    1) POST /api/social-accounts/youtube/oauth/start NO bloquea esperando webbrowser.open() en background;
       devuelve de inmediato oauth_state='pending' + auth_url válida apuntando a http://localhost:<port>/.
    2) Ignora peticiones accesorias como /favicon.ico (204) manteniendo oauth_state='pending'.
    3) Cuando el navegador redirige con ?code=... al callback local, canjea el token, guarda token.json,
       marca oauth_state='completed', dispara _retry_pending_youtube_slots y actualiza Shorts a 'Subido'.
    4) POST /api/social-accounts/youtube/oauth/cancel detiene limpiamente un flujo pendiente.
    """
    import json
    import sqlite3
    import urllib.parse
    import urllib.request
    from datetime import datetime, timedelta, timezone

    cfg_dir = temp_workspace / "config"
    db_path = cfg_dir / "schedule_state.db"
    out_dir = temp_workspace / "output_shorts" / "test_stream"
    out_dir.mkdir(parents=True, exist_ok=True)
    short_02 = out_dir / "test_stream_02_Plata_80pts.mp4"
    past_iso = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")

    (cfg_dir / "client_secret.json").write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "cid_test",
                    "client_secret": "csec_test",
                    "project_id": "creadorstudio-web",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost"],
                }
            }
        ),
        encoding="utf-8",
    )
    (cfg_dir / "token.json").write_text(
        json.dumps({"token": "revoked", "refresh_token": "old_revoked"}), encoding="utf-8"
    )

    api_server._ensure_youtube_slots_columns(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO scheduled_slots (
                video_name, slot_ast, publish_at_utc, youtube_video_id, status, error, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                short_02.name,
                "2026-12-20 06:30 PM AST",
                "2026-12-20T22:30:00Z",
                None,
                "FAILED",
                "invalid_grant",
                past_iso,
            ),
        )
        conn.commit()

    class _ExpiredCreds:
        valid = False
        expired = True
        refresh_token = "old_revoked"

        def refresh(self, _req: Any) -> None:
            raise Exception("invalid_grant: Token has been expired or revoked.")

    class _FreshCreds:
        valid = True
        expired = False
        refresh_token = "fresh_refresh_tok"

        def to_json(self) -> str:
            return json.dumps(
                {
                    "token": "fresh_oauth_token",
                    "refresh_token": "fresh_refresh_tok",
                    "client_id": "cid_test",
                    "client_secret": "csec_test",
                }
            )

    def _from_user_file(tok_path: str, *_a: Any, **_kw: Any) -> Any:
        raw = Path(tok_path).read_text(encoding="utf-8") if Path(tok_path).exists() else ""
        if "fresh_oauth_token" in raw:
            return _FreshCreds()
        return _ExpiredCreds()

    monkeypatch.setattr(
        api_server.skill_uploader.Credentials,
        "from_authorized_user_file",
        staticmethod(_from_user_file),
    )

    real_from_secrets = api_server.skill_uploader.InstalledAppFlow.from_client_secrets_file
    fetched_urls: List[str] = []

    class _MockedFlow:
        def __init__(self, inner: Any) -> None:
            self._inner = inner

        @property
        def redirect_uri(self) -> Any:
            return self._inner.redirect_uri

        @redirect_uri.setter
        def redirect_uri(self, value: str) -> None:
            self._inner.redirect_uri = value

        def authorization_url(self, **kwargs: Any) -> Any:
            return self._inner.authorization_url(**kwargs)

        def fetch_token(self, authorization_response: str = "", **_kwargs: Any) -> None:
            fetched_urls.append(authorization_response)
            assert authorization_response.startswith("https://localhost:")
            assert "code=test_auth_code_123" in authorization_response

        @property
        def credentials(self) -> Any:
            return _FreshCreds()

    monkeypatch.setattr(
        api_server.skill_uploader.InstalledAppFlow,
        "from_client_secrets_file",
        staticmethod(lambda path, scopes, **kw: _MockedFlow(real_from_secrets(path, scopes, **kw))),
    )

    monkeypatch.setattr(
        api_server.skill_uploader,
        "upload_scheduled_short",
        lambda **_kw: {"id": "ytBrowserFlow99", "status": "uploaded"},
    )

    # 1) Start OAuth devuelve de inmediato pending + auth_url
    start_res = client.post("/api/social-accounts/youtube/oauth/start")
    assert start_res.status_code == 200, start_res.text
    start_body = start_res.json()
    assert start_body["oauth_state"] == "pending"
    auth_url = str(start_body.get("auth_url") or "")
    assert auth_url.startswith("https://accounts.google.com/o/oauth2/auth")
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(auth_url).query)
    redirect_uri = qs["redirect_uri"][0]
    assert redirect_uri.startswith("http://localhost:")

    # 2) Favicon no debe cerrar ni completar el flujo
    with urllib.request.urlopen(f"{redirect_uri}favicon.ico", timeout=3) as fav_resp:
        assert fav_resp.status in (200, 204)
    st_mid = client.get("/api/social-accounts/youtube/oauth/status").json()
    assert st_mid["oauth_state"] == "pending"

    # 3) Callback real con ?code=... completa OAuth, guarda token.json y reintenta Shorts
    with urllib.request.urlopen(f"{redirect_uri}?code=test_auth_code_123&state=ok", timeout=3) as cb_resp:
        assert cb_resp.status == 200
        cb_html = cb_resp.read().decode("utf-8")
        assert "SHORTYT_YOUTUBE_OAUTH_DONE" in cb_html

    waiter_t = getattr(api_server, "_youtube_oauth_waiter_thread", None)
    if waiter_t is not None:
        waiter_t.join(timeout=3.0)
    retry_t = getattr(api_server, "_youtube_retry_thread", None)
    if retry_t is not None:
        retry_t.join(timeout=3.0)

    assert len(fetched_urls) == 1
    assert "fresh_oauth_token" in (cfg_dir / "token.json").read_text(encoding="utf-8")

    st_done = client.get("/api/social-accounts/youtube/oauth/status").json()
    assert st_done["oauth_state"] == "completed"
    assert st_done["connected"] is True
    assert st_done["retried_youtube_slots"] >= 1

    s02 = next(
        s for s in client.get("/api/shorts").json()["shorts"] if s["filename"] == short_02.name
    )
    assert s02["social_statuses"]["youtube"]["status_label"] == "Subido"
    assert s02["social_statuses"]["youtube"]["permalink"] == "https://www.youtube.com/shorts/ytBrowserFlow99"

    # 4) Cancelar un flujo pendiente limpia el listener
    (cfg_dir / "token.json").write_text(
        json.dumps({"token": "revoked", "refresh_token": "old_revoked"}), encoding="utf-8"
    )
    start_res2 = client.post("/api/social-accounts/youtube/oauth/start")
    assert start_res2.json()["oauth_state"] == "pending"
    cancel_res = client.post("/api/social-accounts/youtube/oauth/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["oauth_state"] == "idle"
    assert client.get("/api/social-accounts/youtube/oauth/status").json()["oauth_state"] == "idle"


def test_tiktok_studio_mode_permission_dispatch_and_browser_helpers(
    client: TestClient, temp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    TDD Red -> Green:
    1) social_hub acepta publish_mode='TIKTOK_STUDIO' y verify('tiktok') devuelve conectado ('TikTok Studio Web (PC)').
    2) process_due_tiktok_queue NO convierte a Sandbox INBOX_DRAFT cuando publish_mode='TIKTOK_STUDIO'.
    3) tiktok_studio_browser.clean_tiktok_caption y resolve_tiktok_schedule_action limpian hashtags y validan ventana >= 22 min.
    4) POST /api/social-accounts/tiktok/studio-dispatch exige user_permission_granted=True (400 si False)
       y actualiza estado consultable en GET /api/social-accounts/tiktok/studio-status.
    """
    import importlib.util
    import json
    import sqlite3
    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo

    tt_browser_path = api_server.SKILLS_DIR / "multi-social-uploader" / "tiktok_studio_browser.py"
    spec = importlib.util.spec_from_file_location("test_tt_studio_browser", str(tt_browser_path))
    assert spec is not None and spec.loader is not None
    tt_browser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tt_browser)

    # Helpers de limpieza de caption y ventana horaria
    assert (
        tt_browser.clean_tiktok_caption('🔥 "¡QUÉ VERGÜENZA" 😱 #Shorts #Viral #Shorts')
        == '🔥 "¡QUÉ VERGÜENZA" 😱 #Shorts #Viral'
    )
    ast_tz = ZoneInfo("America/Santo_Domingo")
    fixed_now = datetime(2026, 11, 16, 12, 25, tzinfo=ast_tz)
    assert tt_browser.resolve_tiktok_schedule_action(fixed_now - timedelta(minutes=10), fixed_now) == ("POST_NOW", None)
    act, eff = tt_browser.resolve_tiktok_schedule_action(fixed_now + timedelta(minutes=10), fixed_now)
    assert act == "SCHEDULE" and eff is not None and eff >= fixed_now + timedelta(minutes=22)
    assert eff.minute % 5 == 0

    # Guardar TIKTOK_STUDIO en Hub Social
    cur_cfg = client.get("/api/social-accounts").json()
    cur_cfg["api_settings"]["tiktok"]["publish_mode"] = "TIKTOK_STUDIO"
    put_res = client.put("/api/social-accounts", json=cur_cfg)
    assert put_res.status_code == 200, put_res.text
    assert put_res.json()["api_settings"]["tiktok"]["publish_mode"] == "TIKTOK_STUDIO"

    ver_res = client.post("/api/social-accounts/verify", json={"platform": "tiktok"})
    assert ver_res.status_code == 200
    assert ver_res.json()["connected"] is True
    assert "TikTok Studio Web" in ver_res.json()["status_label"]

    # Encolar una fila vencida; process_due_tiktok_queue debe saltarla sin tocar API Sandbox
    db_path = temp_workspace / "config" / "schedule_state.db"
    short_mp4 = temp_workspace / "output_shorts" / "test_stream" / "test_stream_02_Plata_80pts.mp4"
    past_iso = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    api_server.skill_tt_scheduler.enqueue_tiktok_video(
        video_path=str(short_mp4),
        account_key="creador.gaming",
        caption="Test studio mode #Shorts",
        scheduled_time_utc=past_iso,
        scheduled_time_ast="2026-11-16 10:00 AM AST",
        db_path=db_path,
    )
    api_calls: List[str] = []
    monkeypatch.setattr(
        api_server.skill_tt_scheduler,
        "publish_tiktok_video",
        lambda *a, **_kw: api_calls.append(str(a)) or {},
    )
    due_res = api_server.skill_tt_scheduler.process_due_tiktok_queue(db_path=db_path)
    assert api_calls == []
    assert due_res.get("skipped_browser_mode", 0) >= 1

    # Rechazar despacho sin permiso explícito
    deny_res = client.post("/api/social-accounts/tiktok/studio-dispatch", json={"user_permission_granted": False})
    assert deny_res.status_code == 400

    # Despacho con permiso mockeando subproceso real
    launched_cmds: List[Any] = []

    class _FakeProc:
        def __init__(self, pid: int = 9999) -> None:
            self.pid = pid

        def poll(self) -> int:
            return 0

    def _fake_popen(cmd: List[str], **_kw: Any) -> _FakeProc:
        launched_cmds.append(cmd)
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("UPDATE tiktok_scheduled_queue SET status='PUBLISHED', error=NULL")
            conn.commit()
        return _FakeProc()

    monkeypatch.setattr(api_server.subprocess, "Popen", _fake_popen)
    ok_res = client.post("/api/social-accounts/tiktok/studio-dispatch", json={"user_permission_granted": True})
    assert ok_res.status_code == 200, ok_res.text
    assert ok_res.json()["dispatched"] is True
    assert len(launched_cmds) == 1

    st_res = client.get("/api/social-accounts/tiktok/studio-status")
    assert st_res.status_code == 200
    assert st_res.json()["running"] is False

    # 5) Flujo automático de permiso por WhatsApp Bridge (ask -> reply 'aprobado' -> launcher)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "UPDATE tiktok_scheduled_queue SET status='PENDING', scheduled_time_utc=? WHERE video_path LIKE ?",
            (past_iso, "%test_stream_02_Plata_80pts.mp4"),
        )
        conn.commit()

    assert api_server.skill_tt_wa.classify_whatsapp_permission_reply("aprobado dale") == "approved"
    assert api_server.skill_tt_wa.classify_whatsapp_permission_reply("está bien sube todo") == "approved"
    assert api_server.skill_tt_wa.classify_whatsapp_permission_reply("ahora no, ocupado") == "declined"

    sent_wa: List[Dict[str, Any]] = []
    wa_inbox: List[Dict[str, Any]] = []
    wa_launched_rows: List[List[int]] = []

    monkeypatch.setattr(
        api_server.skill_tt_wa,
        "get_whatsapp_bridge_status",
        lambda *_a, **_kw: {"connected": True, "status": "connected"},
    )
    monkeypatch.setattr(
        api_server.skill_tt_wa,
        "send_whatsapp_bridge_message",
        lambda text, **kw: sent_wa.append({"text": text, **kw}) or {"ok": True, "message_ids": ["WA_MSG_1"]},
    )
    monkeypatch.setattr(
        api_server.skill_tt_wa,
        "fetch_whatsapp_bridge_messages",
        lambda _since, **_kw: list(wa_inbox),
    )

    step1 = api_server.skill_tt_wa.tick_tiktok_whatsapp_workflow(
        db_path=db_path,
        config_dir=temp_workspace / "config",
        launcher=lambda rids: wa_launched_rows.append(rids),
    )
    assert step1["action"] == "asked_whatsapp"
    assert len(sent_wa) == 1
    assert "TikTok Studio" in sent_wa[0]["text"]
    assert step1["row_ids"]

    # Segundo tick mientras espera sin respuesta: NO vuelve a spamear
    step2 = api_server.skill_tt_wa.tick_tiktok_whatsapp_workflow(
        db_path=db_path,
        config_dir=temp_workspace / "config",
        launcher=lambda rids: wa_launched_rows.append(rids),
    )
    assert step2["action"] == "awaiting_approval"
    assert len(sent_wa) == 1

    # Llega respuesta "aprobado" por WhatsApp citando el mensaje
    wa_inbox.append(
        {
            "id": "IN_MSG_99",
            "texto": "Aprobado, dale para allá",
            "quoted_id": "WA_MSG_1",
            "timestamp_ms": 9999999999999,
        }
    )
    step3 = api_server.skill_tt_wa.tick_tiktok_whatsapp_workflow(
        db_path=db_path,
        config_dir=temp_workspace / "config",
        launcher=lambda rids: wa_launched_rows.append(rids),
    )
    assert step3["action"] == "wa_reply_approved"
    assert len(wa_launched_rows) == 1 and wa_launched_rows[0] == step1["row_ids"]

    wa_st_res = client.get("/api/social-accounts/tiktok/whatsapp-status")
    assert wa_st_res.status_code == 200
    assert wa_st_res.json()["publish_mode"] == "TIKTOK_STUDIO"
    assert wa_st_res.json()["whatsapp_connected"] is True

    # Endpoint /whatsapp-reply rechaza ("ocupado") y pone pausa 30m
    (temp_workspace / "config" / "tiktok_whatsapp_approval.json").unlink(missing_ok=True)
    rep_res = client.post(
        "/api/social-accounts/tiktok/whatsapp-reply",
        json={"text": "Estoy ocupado ahora, luego", "msg_id": "IN_DEC_1"},
    )
    assert rep_res.status_code == 200
    assert rep_res.json()["handled"] is True
    assert rep_res.json()["intent"] == "declined"
    assert client.get("/api/social-accounts/tiktok/whatsapp-status").json()["approval_state"] == "paused"


def test_facebook_large_video_resumable_upload_and_non_json_error_handling(
    temp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    TDD Red -> Green:
    1) Archivos >= FB_RESUMABLE_THRESHOLD_BYTES usan https://graph-video.facebook.com/.../{page_id}/videos
       con subida reanudable en 3 fases (start -> transfer chunks -> finish).
    2) Respuestas HTTP 413 HTML/vacías no-JSON nunca lanzan 'Expecting value: line 1 column 1 (char 0)',
       informan 'Facebook HTTP 413' y en subidas directas disparan respaldo reanudable automático.
    """
    import json
    import sqlite3
    from datetime import datetime, timedelta, timezone
    from config import social_hub

    cfg_dir = temp_workspace / "config"
    db_path = cfg_dir / "schedule_state.db"
    out_dir = temp_workspace / "output_shorts" / "fb_test"
    out_dir.mkdir(parents=True, exist_ok=True)

    (cfg_dir / "meta_token.json").write_text(
        json.dumps(
            {
                "access_token": "EAAG_USER_TOK",
                "fb_pages": {
                    "creadorstudio_gaming": {
                        "page_id": "900000000000011",
                        "page_name": "Creador Gaming",
                        "page_access_token": "EAAG_TEST_TOKEN",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    large_bytes = (b"MP4CHUNK_A_" * 190)[:2048] + (b"MP4CHUNK_B_" * 190)[:2048]
    assert len(large_bytes) == 4096
    large_mp4 = out_dir / "large_short.mp4"
    large_mp4.write_bytes(large_bytes)

    small_fail_mp4 = out_dir / "small_fail.mp4"
    small_fail_mp4.write_bytes(b"SMALL_FAIL" * 40)

    small_fallback_mp4 = out_dir / "small_fallback.mp4"
    small_fallback_mp4.write_bytes(b"SMALL_FALLBACK" * 40)

    monkeypatch.setattr(social_hub, "FB_RESUMABLE_THRESHOLD_BYTES", 1024)
    past_iso = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")

    class _FakeResp:
        def __init__(self, status_code: int, payload: Any = None, text: str = "") -> None:
            self.status_code = status_code
            self._payload = payload
            self.text = text

        def json(self) -> Any:
            if self._payload is None:
                raise ValueError("Expecting value: line 1 column 1 (char 0)")
            return self._payload

    calls: List[Dict[str, Any]] = []

    def _fake_resumable_http(url: str, *, data: Dict[str, Any], files: Any = None, timeout: int = 180):
        assert url == "https://graph-video.facebook.com/v21.0/900000000000011/videos"
        phase = data.get("upload_phase")
        calls.append({"url": url, "phase": phase, "data": dict(data), "files_keys": list((files or {}).keys())})
        if phase == "start":
            assert data["file_size"] == "4096"
            assert data["access_token"] == "EAAG_TEST_TOKEN"
            return _FakeResp(
                200,
                {
                    "upload_session_id": "sess_99",
                    "video_id": "vid_998877",
                    "start_offset": "0",
                    "end_offset": "2048",
                },
            )
        if phase == "transfer":
            assert data["upload_session_id"] == "sess_99"
            chunk_tuple = files["video_file_chunk"]
            raw = chunk_tuple[1].read()
            if data["start_offset"] == "0":
                assert raw == large_bytes[:2048]
                return _FakeResp(200, {"start_offset": "2048", "end_offset": "4096"})
            if data["start_offset"] == "2048":
                assert raw == large_bytes[2048:4096]
                return _FakeResp(200, {"start_offset": "4096", "end_offset": "4096"})
            raise AssertionError(f"Offset inesperado: {data['start_offset']}")
        if phase == "finish":
            assert data["upload_session_id"] == "sess_99"
            assert data["description"] == "Large clip FB"
            return _FakeResp(200, {"success": True})
        raise AssertionError(f"Fase inesperada: {phase}")

    # Caso 1: Archivo >= threshold sube en 4 llamadas (start, transfer x2, finish)
    row_large_id = social_hub.enqueue_facebook_reel(
        video_path=large_mp4,
        account_key="creadorstudio gaming",
        fb_page_id="900000000000011",
        caption="Large clip FB",
        scheduled_time_utc=past_iso,
        scheduled_time_ast="pasado",
        db_path=db_path,
    )
    monkeypatch.setattr(social_hub, "_http_post_multipart", _fake_resumable_http)
    res1 = social_hub.process_due_facebook_queue(db_path=db_path, config_dir=cfg_dir)
    assert res1["published"] == 1
    assert [c["phase"] for c in calls] == ["start", "transfer", "transfer", "finish"]

    with sqlite3.connect(str(db_path)) as conn:
        st_large = conn.execute(
            "SELECT status, post_id, error FROM facebook_scheduled_queue WHERE id = ?",
            (row_large_id,),
        ).fetchone()
    assert st_large == ("PUBLISHED", "vid_998877", None)

    # Caso 2: HTTP 413 HTML no-JSON persistente reporta 'Facebook HTTP 413' limpio (nunca JSONDecodeError crudo)
    row_fail_id = social_hub.enqueue_facebook_reel(
        video_path=small_fail_mp4,
        account_key="creadorstudio gaming",
        fb_page_id="900000000000011",
        caption="Fail 413 FB",
        scheduled_time_utc=past_iso,
        scheduled_time_ast="pasado",
        db_path=db_path,
    )
    monkeypatch.setattr(
        social_hub,
        "_http_post_multipart",
        lambda url, *, data, files=None, timeout=180: _FakeResp(
            413, None, "<html>413 Request Entity Too Large</html>"
        ),
    )
    res2 = social_hub.process_due_facebook_queue(db_path=db_path, config_dir=cfg_dir)
    assert res2["failed"] == 1
    with sqlite3.connect(str(db_path)) as conn:
        st_fail, err_fail = conn.execute(
            "SELECT status, error FROM facebook_scheduled_queue WHERE id = ?",
            (row_fail_id,),
        ).fetchone()
    assert st_fail == "FAILED"
    assert "Facebook HTTP 413" in (err_fail or "")
    assert "Expecting value: line 1 column 1" not in (err_fail or "")

    # Caso 3: Single-shot devuelve HTTP 413 no-JSON -> respaldo automático por upload_phase=start/transfer/finish
    fallback_phases: List[Optional[str]] = []

    def _fake_fallback_http(url: str, *, data: Dict[str, Any], files: Any = None, timeout: int = 180):
        phase = data.get("upload_phase")
        fallback_phases.append(phase)
        if phase is None:
            return _FakeResp(413, None, "<html>413 Request Entity Too Large</html>")
        if phase == "start":
            return _FakeResp(
                200,
                {
                    "upload_session_id": "sess_fb_ok",
                    "video_id": "vid_fallback_413",
                    "start_offset": "0",
                    "end_offset": str(len(small_fallback_mp4.read_bytes())),
                },
            )
        if phase == "transfer":
            end_s = str(len(small_fallback_mp4.read_bytes()))
            return _FakeResp(200, {"start_offset": end_s, "end_offset": end_s})
        if phase == "finish":
            return _FakeResp(200, {"success": True})
        raise AssertionError(f"Fase inesperada: {phase}")

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("UPDATE facebook_scheduled_queue SET status = 'PENDING' WHERE id = ?", (row_fail_id,))
        # Desactivamos row_fail para aislar row_fallback
        conn.execute("UPDATE facebook_scheduled_queue SET status = 'FAILED' WHERE id = ?", (row_fail_id,))
        conn.commit()

    row_fb_ok_id = social_hub.enqueue_facebook_reel(
        video_path=small_fallback_mp4,
        account_key="creadorstudio gaming",
        fb_page_id="900000000000011",
        caption="Fallback 413 FB",
        scheduled_time_utc=past_iso,
        scheduled_time_ast="pasado",
        db_path=db_path,
    )
    monkeypatch.setattr(social_hub, "_http_post_multipart", _fake_fallback_http)
    res3 = social_hub.process_due_facebook_queue(db_path=db_path, config_dir=cfg_dir)
    assert res3["published"] == 1
    assert fallback_phases == [None, "start", "transfer", "finish"]
    with sqlite3.connect(str(db_path)) as conn:
        st_fb_ok = conn.execute(
            "SELECT status, post_id, error FROM facebook_scheduled_queue WHERE id = ?",
            (row_fb_ok_id,),
        ).fetchone()
    assert st_fb_ok == ("PUBLISHED", "vid_fallback_413", None)



