import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import type { PipelineStatus } from './types';
import { ShortCard } from './components/ShortCard';

const mockInboxPayload = {
  videos: [
    {
      file_name: 'CreadorStudio_LIVE_Demo.mp4',
      size_mb: 512.4,
      modified_at: '2026-11-07 12:00:00',
    },
  ],
  disk_space: {
    total_gb: 931.5,
    used_gb: 600.2,
    free_gb: 331.3,
    free_percentage: 35.6,
  },
  settings: {
    shorts_per_video: 8,
    min_short_duration_sec: 45.0,
    max_short_duration_sec: 120.0,
    playback_speed: 1.0,
    layout_mode: 'auto',
    enable_bgm: false,
    default_bgm_mood: 'auto',
    enable_dynamic_zoom: true,
    enable_hook_punchin: true,
    enable_jumpcuts: false,
    max_words_per_subtitle: 4,
    youtube_category_id: '22',
    auto_upload_to_youtube: false,
  },
  pipeline_status: {
    job_id: 'ab12cd34',
    status: 'IDLE',
    current_video: 'CreadorStudio_LIVE_Demo.mp4',
    source_type: 'inbox',
    source_preview_url: '/api/media/source/CreadorStudio_LIVE_Demo.mp4',
    progress_percent: 45,
    phase_label: 'Fase 3/4 · Renderizado 9:16 (2/6)',
    step_detail: 'Renderizando CreadorStudio_01_Oro_94pts.mp4 [Layout: gaming_hud]...',
    message: 'Sistema listo para procesar.',
    updated_at: '2026-11-07 12:00:00',
  },
};

const mockShortsPayload = {
  total: 2,
  shorts: [
    {
      filename: 'CreadorStudio_01_Oro_94pts.mp4',
      folder: 'CreadorStudio_LIVE_Demo',
      relative_path: 'CreadorStudio_LIVE_Demo/CreadorStudio_01_Oro_94pts.mp4',
      video_url: '/api/media/short/CreadorStudio_LIVE_Demo/CreadorStudio_01_Oro_94pts.mp4',
      thumbnail_url: '/api/media/thumbnail/CreadorStudio_LIVE_Demo/CreadorStudio_01_Oro_94pts.mp4',
      size_mb: 24.8,
      created_at: '2026-11-07 12:15:00',
      virality_score: 94,
      virality_grade: 9.4,
      tier: 'Oro',
      eligible_for_youtube: true,
      scheduled_ast: '2026-11-07 02:00 PM AST',
      publish_at_utc: '2026-11-07T18:00:00Z',
      youtube_video_id: 'yt_live_999',
      upload_progress_percent: 100,
      upload_status_detail: 'Publicado en YouTube Shorts (yt_live_999) + Redes Sociales',
    },
    {
      filename: 'CreadorStudio_02_Plata_78pts.mp4',
      folder: 'CreadorStudio_LIVE_Demo',
      relative_path: 'CreadorStudio_LIVE_Demo/CreadorStudio_02_Plata_78pts.mp4',
      video_url: '/api/media/short/CreadorStudio_LIVE_Demo/CreadorStudio_02_Plata_78pts.mp4',
      thumbnail_url: '/api/media/thumbnail/CreadorStudio_LIVE_Demo/CreadorStudio_02_Plata_78pts.mp4',
      size_mb: 19.2,
      created_at: '2026-11-07 12:16:00',
      virality_score: 78,
      virality_grade: 7.8,
      tier: 'Plata',
      eligible_for_youtube: false,
      scheduled_ast: '2026-11-07 03:00 PM AST',
      publish_at_utc: '2026-11-07T19:00:00Z',
      youtube_video_id: null,
      upload_progress_percent: 75,
      upload_status_detail: 'En cola para Instagram Reels y TikTok (2026-11-07 03:00 PM AST)',
    },
  ],
};

const mockQueuesPayload = {
  youtube_slots: [
    {
      id: 1,
      video_name: 'CreadorStudio_01_Oro_94pts.mp4',
      slot_ast: '2026-11-07 02:00 PM AST',
      publish_at_utc: '2026-11-07T18:00:00Z',
      youtube_video_id: null,
      created_at_utc: '2026-11-07T16:15:00Z',
    },
  ],
  instagram_queue: [
    {
      id: 10,
      account_key: 'creador_short',
      scheduled_time_utc: '2026-11-07T18:00:00Z',
      scheduled_time_ast: '2026-11-07 02:00 PM AST',
      status: 'PENDING',
      video_path: 'C:/Short YT/output_shorts/CreadorStudio_01_Oro_94pts.mp4',
    },
  ],
  tiktok_queue: [
    {
      id: 20,
      account_key: 'creador.clips',
      scheduled_time_utc: '2026-11-07T18:00:00Z',
      scheduled_time_ast: '2026-11-07 02:00 PM AST',
      status: 'PENDING',
      video_path: 'C:/Short YT/output_shorts/CreadorStudio_01_Oro_94pts.mp4',
    },
  ],
};

describe('Short YT Frontend — Apple HIG & Zero-Dead-UI Audit', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.history.pushState({}, '', '/');
    window.localStorage.removeItem('short_yt_theme_mode');
    document.documentElement.classList.remove('dark');
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url.endsWith('/api/inbox')) {
        return new Response(JSON.stringify(mockInboxPayload), { status: 200 });
      }
      if (url.endsWith('/api/shorts') && init?.method === 'DELETE') {
        return new Response(JSON.stringify({ canceled: true, canceled_count: 2 }), { status: 200 });
      }
      if (url.includes('/api/shorts/') && init?.method === 'DELETE') {
        return new Response(
          JSON.stringify({ canceled: true, filename: 'CreadorStudio_01_Oro_94pts.mp4' }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/shorts')) {
        return new Response(JSON.stringify(mockShortsPayload), { status: 200 });
      }
      if (url.endsWith('/api/queues')) {
        return new Response(JSON.stringify(mockQueuesPayload), { status: 200 });
      }
      if (url.endsWith('/api/pipeline/status')) {
        return new Response(JSON.stringify(mockInboxPayload.pipeline_status), { status: 200 });
      }
      if (url.endsWith('/api/content-profiles')) {
        return new Response(JSON.stringify({ profiles: [] }), { status: 200 });
      }
      if (url.endsWith('/api/analytics/categories')) {
        return new Response(
          JSON.stringify({
            categories: [
              {
                key: 'opinion_monologo',
                label: 'Video de Opinión (1 Persona)',
                description: 'Evalúa monólogos y comentarios en solitario.',
                key_signals: ['Gancho inquisitivo o denuncia en primeros 2s (20 pts)'],
                weights: { p1_gancho_hipnotico: 20, p6_carne_de_comentarios: 20 },
              },
              {
                key: 'podcast',
                label: 'Podcast / Entrevista',
                description: 'Prioriza el Índice Contrarian y densidad de epifanías.',
                key_signals: ['Índice Contrarian / Hot Take que genera debate profundo (25 pts)'],
                weights: { p6_carne_de_comentarios: 25, p7_valor_dato_curioso: 25 },
              },
            ],
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/inspect') && init?.method === 'POST') {
        return new Response(
          JSON.stringify({
            file_name: 'CreadorStudio_LIVE_Demo.mp4',
            file_path: 'C:/Short YT/inbox_videos/CreadorStudio_LIVE_Demo.mp4',
            file_size_mb: 512.4,
            duration_sec: 1840.0,
            duration_formatted: '30m 40s',
            resolution: '1920x1080',
            fps: 60.0,
            recommended_shorts: 8,
            max_possible_shorts: 12,
            detected_at: '2026-11-07 12:30:00',
            status: 'WAITING_USER_APPROVAL',
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/pipeline/pre-analyze') && init?.method === 'POST') {
        return new Response(
          JSON.stringify({
            source_type: 'inbox',
            target: 'CreadorStudio_LIVE_Demo.mp4',
            video_title: 'Stream Gameplay & Charla',
            duration_sec: 1840.0,
            thumbnail_url: null,
            is_hybrid_multicategory: true,
            analysis_mode: 'local_multiframe',
            analysis_summary: 'Detectado stream híbrido: 35% charla Full Cam + 65% Gameplay + Cámara.',
            category_rules: [
              {
                rule_id: 'rule_1',
                category: 'opinion_monologo',
                scene_label: 'Charla Full Cam / Just Chatting',
                detected_share_pct: 35,
                layout_mode: 'fullscreen',
                subtitle_preset: 'hormozi_pop',
                subtitle_position: 'bottom',
                cam_overlay_pos: 'top_right',
                custom_cam_box_norm: null,
                custom_content_box_norm: null,
                custom_boxes_manual: false,
                frame_url: null,
                sample_timestamp_sec: 120.0,
              },
              {
                rule_id: 'rule_2',
                category: 'videojuegos',
                scene_label: 'Gameplay + Cámara',
                detected_share_pct: 65,
                layout_mode: 'gaming_hud',
                subtitle_preset: 'nexus_cyber_glow',
                subtitle_position: 'center',
                cam_overlay_pos: 'top_right',
                custom_cam_box_norm: [0.02, 0.35, 0.26, 0.35],
                custom_content_box_norm: [0.28, 0.05, 0.7, 0.9],
                custom_boxes_manual: false,
                frame_url: null,
                sample_timestamp_sec: 900.0,
              },
            ],
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/pipeline/process') && init?.method === 'POST') {
        return new Response(
          JSON.stringify({
            job_id: 'ab12cd34',
            status: 'STARTED',
            target: 'CreadorStudio_LIVE_Demo.mp4',
            settings_applied: mockInboxPayload.settings,
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/cleanup') && init?.method === 'POST') {
        return new Response(
          JSON.stringify({
            deleted_files: 4,
            mb_freed: 128.5,
            disk_space: {
              total_gb: 931.5,
              used_gb: 599.0,
              free_gb: 332.5,
              free_percentage: 35.7,
            },
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/settings/theme') && init?.method === 'POST') {
        const body = init.body ? (JSON.parse(init.body as string) as { theme_mode: 'light' | 'dark' }) : { theme_mode: 'dark' };
        return new Response(
          JSON.stringify({
            theme_mode: body.theme_mode,
            settings: { ...mockInboxPayload.settings, theme_mode: body.theme_mode },
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/pipeline/cancel') && init?.method === 'POST') {
        return new Response(
          JSON.stringify({
            status: 'CANCELED',
            pipeline_status: { ...mockInboxPayload.pipeline_status, status: 'CANCELED' },
          }),
          { status: 200 }
        );
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
    });
  });

  it('renderiza videos de inbox, cuadrícula de shorts virales y barras de estado por red social', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByTitle('CreadorStudio_01_Oro_94pts.mp4')).toBeInTheDocument();
    });

    expect(screen.queryByRole('columnheader', { name: /Archivo Short/i })).not.toBeInTheDocument();
    expect(screen.getByText('94 / 100')).toBeInTheDocument();
    expect(screen.getByText('78 / 100')).toBeInTheDocument();
    expect(screen.queryByText(/\/10\)/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Mostrar u ocultar categorías y estado de redes/i }));
    expect(screen.getByText('@creador_short')).toBeInTheDocument();
    expect(screen.getByText('@creador.clips')).toBeInTheDocument();
    expect(screen.queryByText(/Slots YouTube/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Cola Instagram/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Cola TikTok/i)).not.toBeInTheDocument();
    expect(screen.getByText(/331\.3 GB libres/i)).toBeInTheDocument();
    expect(screen.queryByText(/clipXtudio/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText(
        /Extracción autónoma 1080p60, analítica adaptativa por categoría sobre 100 puntos, recorte 9:16 y colas SQLite\./i
      )
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/Tabla SQLite: scheduled_slots/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Tabla SQLite: instagram_scheduled_queue/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Tabla SQLite: tiktok_scheduled_queue/i)).not.toBeInTheDocument();
  });

  it('ejecuta POST /api/inspect al pulsar Inspeccionar Video y muestra métricas reales', async () => {
    const user = userEvent.setup();
    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Inspeccionar Video/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /Inspeccionar Video/i }));

    await waitFor(() => {
      expect(screen.getByText('1920x1080')).toBeInTheDocument();
      expect(screen.getByText('30m 40s')).toBeInTheDocument();
    });
  });

  it('ejecuta pre-análisis y luego POST /api/pipeline/process al confirmar en el modal', async () => {
    const user = userEvent.setup();
    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^Generar$/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /^Generar$/i }));

    await waitFor(() => {
      expect(screen.getByTestId('preflight-analysis-modal')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /Confirmar y Generar Shorts/i }));

    await waitFor(() => {
      expect(screen.getByText(/ab12cd34/i)).toBeInTheDocument();
    });
  });

  it('ejecuta POST /api/cleanup al pulsar Limpiar Temporales y actualiza el espacio libre', async () => {
    const user = userEvent.setup();
    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Limpiar Temporales/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /Limpiar Temporales/i }));

    await waitFor(() => {
      expect(screen.getByText(/332\.5 GB libres/i)).toBeInTheDocument();
      expect(screen.getByText(/128\.5 MB liberados/i)).toBeInTheDocument();
    });
  });

  it('verifica que todos los botones e inputs interactivos tengan altura h-10 (Apple HIG)', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^Generar$/i })).toBeInTheDocument();
    });

    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThanOrEqual(4);
    for (const btn of buttons) {
      expect(btn.className).toContain('h-10');
    }
  });

  it('muestra alerta de error limpia cuando el backend devuelve HTTP 400', async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url.endsWith('/api/inbox')) {
        return new Response(JSON.stringify(mockInboxPayload), { status: 200 });
      }
      if (url.endsWith('/api/shorts') && init?.method === 'DELETE') {
        return new Response(JSON.stringify({ canceled: true, canceled_count: 2 }), { status: 200 });
      }
      if (url.includes('/api/shorts/') && init?.method === 'DELETE') {
        return new Response(
          JSON.stringify({ canceled: true, filename: 'CreadorStudio_01_Oro_94pts.mp4' }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/shorts')) {
        return new Response(JSON.stringify(mockShortsPayload), { status: 200 });
      }
      if (url.endsWith('/api/queues')) {
        return new Response(JSON.stringify(mockQueuesPayload), { status: 200 });
      }
      if (url.endsWith('/api/pipeline/status')) {
        return new Response(JSON.stringify(mockInboxPayload.pipeline_status), { status: 200 });
      }
      if (url.endsWith('/api/content-profiles')) {
        return new Response(JSON.stringify({ profiles: [] }), { status: 200 });
      }
      if (url.endsWith('/api/analytics/categories')) {
        return new Response(
          JSON.stringify({
            categories: [
              {
                key: 'opinion_monologo',
                label: 'Video de Opinión (1 Persona)',
                description: 'Evalúa monólogos y comentarios en solitario.',
                key_signals: ['Gancho inquisitivo o denuncia en primeros 2s (20 pts)'],
                weights: { p1_gancho_hipnotico: 20, p6_carne_de_comentarios: 20 },
              },
              {
                key: 'podcast',
                label: 'Podcast / Entrevista',
                description: 'Prioriza el Índice Contrarian y densidad de epifanías.',
                key_signals: ['Índice Contrarian / Hot Take que genera debate profundo (25 pts)'],
                weights: { p6_carne_de_comentarios: 25, p7_valor_dato_curioso: 25 },
              },
            ],
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/pipeline/pre-analyze') && init?.method === 'POST') {
        return new Response(
          JSON.stringify({
            source_type: 'inbox',
            target: 'CreadorStudio_LIVE_Demo.mp4',
            video_title: 'Stream Gameplay & Charla',
            duration_sec: 1840.0,
            thumbnail_url: null,
            is_hybrid_multicategory: true,
            analysis_mode: 'local_multiframe',
            analysis_summary: 'Detectado stream híbrido: 35% charla Full Cam + 65% Gameplay + Cámara.',
            category_rules: [
              {
                rule_id: 'rule_1',
                category: 'opinion_monologo',
                scene_label: 'Charla Full Cam / Just Chatting',
                detected_share_pct: 35,
                layout_mode: 'fullscreen',
                subtitle_preset: 'hormozi_pop',
                subtitle_position: 'bottom',
                cam_overlay_pos: 'top_right',
                custom_cam_box_norm: null,
                custom_content_box_norm: null,
                custom_boxes_manual: false,
                frame_url: null,
                sample_timestamp_sec: 120.0,
              },
              {
                rule_id: 'rule_2',
                category: 'videojuegos',
                scene_label: 'Gameplay + Cámara',
                detected_share_pct: 65,
                layout_mode: 'gaming_hud',
                subtitle_preset: 'nexus_cyber_glow',
                subtitle_position: 'center',
                cam_overlay_pos: 'top_right',
                custom_cam_box_norm: [0.02, 0.35, 0.26, 0.35],
                custom_content_box_norm: [0.28, 0.05, 0.7, 0.9],
                custom_boxes_manual: false,
                frame_url: null,
                sample_timestamp_sec: 900.0,
              },
            ],
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/pipeline/process') && init?.method === 'POST') {
        return new Response(
          JSON.stringify({ detail: 'Debes proporcionar un enlace válido de YouTube (youtube.com o youtu.be).' }),
          { status: 400 }
        );
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^Generar$/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /^Generar$/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Confirmar y Generar Shorts/i })).toBeInTheDocument();
    });

    const profileNameInput = screen.getByLabelText(/Nombre del Contenido \/ Show/i) as HTMLInputElement;
    await user.type(profileNameInput, 'Mi Show Guardado');

    await user.click(screen.getByRole('button', { name: /Confirmar y Generar Shorts/i }));

    await waitFor(() => {
      expect(screen.getByTestId('preflight-analysis-modal')).toBeInTheDocument();
      expect(
        screen.getByText(/Debes proporcionar un enlace válido de YouTube/i)
      ).toBeInTheDocument();
      expect((screen.getByLabelText(/Nombre del Contenido \/ Show/i) as HTMLInputElement).value).toBe('Mi Show Guardado');
    });
  });

  it('elimina selectores de categoría/vara viral y permite seleccionar Formato de Encuadre Podcast Dinámico (9:16 + 50/50)', async () => {
    const user = userEvent.setup();
    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^Generar$/i })).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /^Generar$/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/Perfil de Contenido/i)).toBeInTheDocument();
    });

    expect(screen.queryByLabelText(/Categoría de Analítica Viral/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Vara de Medición Activa/i)).not.toBeInTheDocument();

    const profileSelect = screen.getByLabelText(/Perfil de Contenido/i) as HTMLSelectElement;
    expect(profileSelect.className).toContain('h-10');

    const layoutSelect = screen.getByLabelText(/Formato de Encuadre 9:16/i) as HTMLSelectElement;
    expect(layoutSelect.className).toContain('h-10');
    await user.selectOptions(layoutSelect, 'podcast_dynamic');
    expect(layoutSelect.value).toBe('podcast_dynamic');
  });

  it('permite seleccionar los nuevos layouts Gaming HUD (25/75), Reaction PiP (16:9 Íntegro) y Reality Multicam (Sala + Zoom)', async () => {
    const user = userEvent.setup();
    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^Generar$/i })).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /^Generar$/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/Formato de Encuadre 9:16/i)).toBeInTheDocument();
    });

    const layoutSelect = screen.getByLabelText(/Formato de Encuadre 9:16/i) as HTMLSelectElement;

    await user.selectOptions(layoutSelect, 'gaming_hud');
    expect(layoutSelect.value).toBe('gaming_hud');

    await user.selectOptions(layoutSelect, 'reaction_pip');
    expect(layoutSelect.value).toBe('reaction_pip');

    await user.selectOptions(layoutSelect, 'reality_multicam');
    expect(layoutSelect.value).toBe('reality_multicam');
  });

  it('muestra directamente el Monitor de Proceso del Video debajo de la configuración con el video en grande encima de la barra de carga', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Monitor de Proceso del Video/i })).toBeInTheDocument();
    });

    expect(screen.queryByRole('button', { name: /Ver Monitor de Proceso/i })).not.toBeInTheDocument();
    const progressBar = screen.getByTestId('pipeline-progress-bar');
    const videoPlayer = screen.getByTestId('source-video-player');
    expect(progressBar).toBeInTheDocument();
    expect(videoPlayer).toBeInTheDocument();
    expect(screen.getByText(/Fase 3\/4 · Renderizado 9:16/i)).toBeInTheDocument();
    // El video debe ir en grande encima de la barra de carga (preceder en orden del DOM)
    expect(videoPlayer.compareDocumentPosition(progressBar) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('permite alternar el switch de apariencia entre Light y Dark en el top de la interfaz y persiste en /api/settings/theme', async () => {
    const user = userEvent.setup();
    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('switch', { name: /Cambiar apariencia Light \/ Dark/i })).toBeInTheDocument();
    });

    const themeSwitch = screen.getByRole('switch', { name: /Cambiar apariencia Light \/ Dark/i });
    expect(themeSwitch.className).toContain('h-10');
    expect(themeSwitch).toHaveAttribute('aria-checked', 'false');

    await user.click(themeSwitch);

    await waitFor(() => {
      expect(themeSwitch).toHaveAttribute('aria-checked', 'true');
      expect(document.documentElement.classList.contains('dark')).toBe(true);
    });
  });

  it('muestra miniatura real, barras de estado por red social sin colas sueltas y abre flotante con doble clic', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByAltText(/Miniatura de CreadorStudio_01_Oro_94pts\.mp4/i)).toBeInTheDocument();
    });

    // Por defecto las categorías por Short y barras de redes inician ocultas
    expect(screen.queryByTestId('social-status-youtube-CreadorStudio_01_Oro_94pts.mp4')).not.toBeInTheDocument();

    const toggleSocialBtn = screen.getByRole('button', {
      name: /Mostrar u ocultar categorías y estado de redes/i,
    });
    expect(toggleSocialBtn).toHaveAttribute('aria-pressed', 'false');
    expect(toggleSocialBtn.className).toContain('h-10');
    fireEvent.click(toggleSocialBtn);
    expect(toggleSocialBtn).toHaveAttribute('aria-pressed', 'true');

    // Barras por red social (YouTube / Instagram / TikTok / Facebook) en cada tarjeta sin bloqueo < 85 pts
    const ytBar01 = screen.getByTestId('social-status-youtube-CreadorStudio_01_Oro_94pts.mp4');
    const igBar01 = screen.getByTestId('social-status-instagram-CreadorStudio_01_Oro_94pts.mp4');
    const ttBar01 = screen.getByTestId('social-status-tiktok-CreadorStudio_01_Oro_94pts.mp4');
    const fbBar01 = screen.getByTestId('social-status-facebook-CreadorStudio_01_Oro_94pts.mp4');
    expect(ytBar01).toHaveTextContent(/Subido/i);
    expect(igBar01).toHaveTextContent(/Pendiente/i);
    expect(ttBar01).toHaveTextContent(/Pendiente/i);
    expect(fbBar01).toHaveTextContent(/Pendiente/i);

    const ytBar02 = screen.getByTestId('social-status-youtube-CreadorStudio_02_Plata_78pts.mp4');
    expect(ytBar02).toHaveTextContent(/Pendiente/i);
    expect(screen.queryByText(/Solo IG \/ TikTok/i)).not.toBeInTheDocument();

    // La sección independiente de colas SQLite y el botón Flotante ya no deben existir
    expect(screen.queryByText(/Slots YouTube/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Cola Instagram/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Cola TikTok/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Flotante/i })).not.toBeInTheDocument();

    const cardVideos = Array.from(
      document.querySelectorAll('[data-testid="shorts-grid-4col"] video')
    ) as HTMLVideoElement[];
    expect(cardVideos.length).toBeGreaterThanOrEqual(1);
    fireEvent.doubleClick(cardVideos[0]);

    await waitFor(() => {
      expect(screen.getByTestId('floating-short-player')).toBeInTheDocument();
      expect(screen.getByTestId('short-video-player')).toBeInTheDocument();
    });
  });

  it('permite cancelar un Short individual y cancelar todos los Shorts o el proceso activo', async () => {
    const user = userEvent.setup();
    render(<App />);

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /Cancelar Short CreadorStudio_01_Oro_94pts\.mp4/i })
      ).toBeInTheDocument();
    });

    const cancelSingleBtn = screen.getByRole('button', {
      name: /Cancelar Short CreadorStudio_01_Oro_94pts\.mp4/i,
    });
    expect(cancelSingleBtn.className).toContain('h-10');
    await user.click(cancelSingleBtn);

    await waitFor(() => {
      expect(screen.getByText(/Short CreadorStudio_01_Oro_94pts\.mp4 cancelado/i)).toBeInTheDocument();
    });

    const cancelAllBtn = screen.getByRole('button', { name: /Cancelar Todos los Shorts/i });
    expect(cancelAllBtn.className).toContain('h-10');
    await user.click(cancelAllBtn);

    await waitFor(() => {
      expect(screen.getByText(/Shorts cancelados correctamente/i)).toBeInTheDocument();
    });
  });

  it('muestra el modal flotante al terminar la generación con el conteo Oro, Plata y Meh y permite programar fecha y hora por plataforma', async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url.endsWith('/api/inbox')) {
        return new Response(
          JSON.stringify({
            ...mockInboxPayload,
            pipeline_status: {
              ...mockInboxPayload.pipeline_status,
              status: 'COMPLETED',
              progress_percent: 100,
              phase_label: 'Completado (100%)',
            },
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/shorts/schedule') && init?.method === 'POST') {
        return new Response(
          JSON.stringify({
            scheduled: true,
            scheduled_count: 2,
            youtube_uploaded_count: 1,
            summary: {
              total_shorts: 2,
              oro_count: 1,
              plata_count: 1,
              meh_count: 0,
              youtube_eligible_count: 1,
              youtube_uploaded_count: 1,
              requires_schedule_confirmation: false,
            },
            shorts: mockShortsPayload.shorts,
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/shorts')) {
        return new Response(
          JSON.stringify({
            ...mockShortsPayload,
            summary: {
              total_shorts: 2,
              oro_count: 1,
              plata_count: 1,
              meh_count: 0,
              youtube_eligible_count: 1,
              youtube_uploaded_count: 1,
              requires_schedule_confirmation: true,
            },
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/queues')) {
        return new Response(JSON.stringify(mockQueuesPayload), { status: 200 });
      }
      if (url.endsWith('/api/content-profiles')) {
        return new Response(JSON.stringify({ profiles: [] }), { status: 200 });
      }
      if (url.endsWith('/api/analytics/categories')) {
        return new Response(JSON.stringify({ categories: [] }), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
    });

    render(<App />);

    await waitFor(() => {
      expect(
        screen.getByRole('dialog', { name: /Resumen de Generación y Programación de Shorts/i })
      ).toBeInTheDocument();
    });

    expect(
      screen.getByText(/La generación de Shorts terminó: tenemos 1 cantidad Oro, 1 cantidad de Plata y 0 cantidad Meh/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Favor seleccionar la fecha y hora de programación de los Shorts en sus respectivas plataformas/i)
    ).toBeInTheDocument();

    const ytInput = screen.getByLabelText(/Fecha y Hora YouTube Shorts/i) as HTMLInputElement;
    const igInput = screen.getByLabelText(/Fecha y Hora Instagram Reels/i) as HTMLInputElement;
    const ttInput = screen.getByLabelText(/Fecha y Hora TikTok/i) as HTMLInputElement;
    expect(ytInput.className).toContain('h-10');
    expect(igInput.className).toContain('h-10');
    expect(ttInput.className).toContain('h-10');

    const confirmBtn = screen.getByRole('button', {
      name: /Confirmar Fecha y Hora y Subir a Redes/i,
    });
    expect(confirmBtn.className).toContain('h-10');
    await user.click(confirmBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/Programación confirmada para 2 Shorts/i)
      ).toBeInTheDocument();
    });
  });

  it('permite ingresar URL de YouTube, Twitch o Kick y rango opcional Inicio/Fin (--download-sections)', async () => {
    const user = userEvent.setup();
    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Pegar URL de YouTube \/ LIVE/i })).toBeInTheDocument();
    });

    expect(document.getElementById('source-type-select')).toBeNull();
    expect(document.getElementById('inbox-video-select')).toBeNull();

    await user.click(screen.getByRole('button', { name: /Pegar URL de YouTube \/ LIVE/i }));

    const urlInput = screen.getByLabelText(/URL de YouTube, Twitch o Kick/i) as HTMLInputElement;
    const startInput = screen.getByLabelText(/Inicio \(Opcional\)/i) as HTMLInputElement;
    const endInput = screen.getByLabelText(/Fin \(Opcional\)/i) as HTMLInputElement;

    expect(urlInput.className).toContain('h-10');
    expect(startInput.className).toContain('h-10');
    expect(endInput.className).toContain('h-10');

    await user.type(urlInput, 'https://www.twitch.tv/videos/2199887766');
    await user.type(startInput, '00:05:00');
    await user.type(endInput, '00:15:00');

    await user.click(screen.getByRole('button', { name: /^Generar$/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Confirmar y Generar Shorts/i })).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /Confirmar y Generar Shorts/i }));

    await waitFor(() => {
      expect(screen.getByText(/ab12cd34/i)).toBeInTheDocument();
    });
  });

  it('permite detectar escena 16:9, ajustar Studio 9:16 en vivo, elegir preset de subtítulos y guardar/actualizar Perfil de Contenido', async () => {
    const user = userEvent.setup();
    let savedProfiles: Array<Record<string, unknown>> = [];

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method || 'GET').toUpperCase();
      if (url.endsWith('/api/inbox')) {
        return new Response(JSON.stringify(mockInboxPayload), { status: 200 });
      }
      if (url.endsWith('/api/shorts')) {
        return new Response(JSON.stringify({ total: 0, shorts: [] }), { status: 200 });
      }
      if (url.endsWith('/api/queues')) {
        return new Response(JSON.stringify(mockQueuesPayload), { status: 200 });
      }
      if (url.endsWith('/api/content-profiles') && method === 'GET') {
        return new Response(JSON.stringify({ profiles: savedProfiles }), { status: 200 });
      }
      if (url.endsWith('/api/content-profiles') && method === 'POST') {
        const body = JSON.parse(String(init?.body || '{}')) as Record<string, unknown>;
        const created = { id: 101, ...body };
        savedProfiles = [created];
        return new Response(JSON.stringify(created), { status: 200 });
      }
      if (url.endsWith('/api/content-profiles/101') && method === 'PUT') {
        const body = JSON.parse(String(init?.body || '{}')) as Record<string, unknown>;
        const updated = { id: 101, ...body };
        savedProfiles = [updated];
        return new Response(JSON.stringify(updated), { status: 200 });
      }
      if (url.endsWith('/api/subtitles/presets')) {
        return new Response(
          JSON.stringify({
            presets: [
              { id: 'hormozi_pop', name: 'Hormozi Pop', description: 'Rebote amarillo.' },
              { id: 'nexus_cyber_glow', name: 'Nexus Cyber Glow', description: 'Cian neón vibrante.' },
              { id: 'one_word_punch', name: 'One-Word Punch', description: 'Palabra gigante.' },
            ],
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/scene/detect') && method === 'POST') {
        return new Response(
          JSON.stringify({
            video_filename: 'stream_ep01_x4.mp4',
            resolution: '1920x1080',
            width: 1920,
            height: 1080,
            detected_layout: 'gaming_hud',
            faces_detected: 1,
            cam_box_norm: [0.02, 0.68, 0.24, 0.28],
            content_box_norm: [0.28, 0.02, 0.7, 0.96],
            frame_url: '/api/media/scene-frame?video_filename=stream_ep01_x4.mp4',
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/pipeline/candidates')) {
        return new Response(JSON.stringify({ video_filename: null, candidates: [] }), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^Generar$/i })).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /^Generar$/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Detectar Escena & Studio/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /Detectar Escena & Studio/i }));

    await waitFor(() => {
      expect(screen.getByTestId('studio-preview-9-16')).toBeInTheDocument();
    });

    const manualToggleBtn = screen.getByRole('button', { name: /Fijar Encuadre Manual/i });
    expect(manualToggleBtn.className).toContain('h-10');
    await user.click(manualToggleBtn);
    expect(screen.getByRole('button', { name: /Usar Detección Automática/i })).toBeInTheDocument();

    const layoutSelect = screen.getByLabelText(/Formato de Encuadre 9:16/i) as HTMLSelectElement;
    await user.selectOptions(layoutSelect, 'floating_circle');

    const subPresetSelect = screen.getByLabelText(/Estilo de Subtítulos/i) as HTMLSelectElement;
    await user.selectOptions(subPresetSelect, 'nexus_cyber_glow');

    const profileNameInput = screen.getByLabelText(/Nombre del Contenido \/ Show/i) as HTMLInputElement;
    expect(profileNameInput.className).toContain('h-10');
    await user.type(profileNameInput, 'CreadorStudio Setup');

    const keywordsInput = screen.getByLabelText(/Pistas de Auto-Detección \(Canal \/ Palabras\)/i) as HTMLInputElement;
    expect(keywordsInput.className).toContain('h-10');
    await user.type(keywordsInput, 'creadorstudio, setup');

    const saveProfileBtn = screen.getByRole('button', { name: /Guardar Perfil/i });
    expect(saveProfileBtn.className).toContain('h-10');
    await user.click(saveProfileBtn);

    await waitFor(() => {
      expect(screen.getByText(/Perfil "CreadorStudio Setup" guardado/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Actualizar Perfil/i })).toBeInTheDocument();
    });

    await user.type(keywordsInput, ', live');
    const updateProfileBtn = screen.getByRole('button', { name: /Actualizar Perfil/i });
    expect(updateProfileBtn.className).toContain('h-10');
    await user.click(updateProfileBtn);

    await waitFor(() => {
      expect(screen.getByText(/Perfil "CreadorStudio Setup" actualizado/i)).toBeInTheDocument();
    });

    const allButtons = document.querySelectorAll('button');
    allButtons.forEach((btn) => {
      expect(btn.className).toContain('h-10');
    });
  });

  it('permite escanear hasta 24 candidatos IA pre-render y renderizar solo los seleccionados', async () => {
    const user = userEvent.setup();
    const capturedPayloads: Array<Record<string, unknown>> = [];

    const fakeCandidates = [
      {
        candidate_id: 'cand_01',
        start_time: 12.5,
        end_time: 54.0,
        duration: 41.5,
        hook_title: 'CLUTCH ÉPICO EN LA FINAL',
        first_person_caption: 'Caption 1',
        transcript_excerpt: 'No van a creer lo que pasó en esta última ronda del torneo.',
        tags: ['Gaming', 'Clutch'],
        bgm_mood: 'impacto',
        virality_score: 93,
        virality_grade: 'Oro',
        youtube_eligible: true,
      },
      {
        candidate_id: 'cand_02',
        start_time: 210.0,
        end_time: 255.0,
        duration: 45.0,
        hook_title: 'RISA CONTAGIOSA EN VIVO',
        first_person_caption: 'Caption 2',
        transcript_excerpt: 'Se cayó la silla en medio de la transmisión y nadie paraba de reír.',
        tags: ['Comedia'],
        bgm_mood: 'comedia',
        virality_score: 76,
        virality_grade: 'Plata',
        youtube_eligible: false,
      },
    ];

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/api/inbox')) {
        return new Response(JSON.stringify(mockInboxPayload), { status: 200 });
      }
      if (url.endsWith('/api/shorts')) {
        return new Response(JSON.stringify({ total: 0, shorts: [] }), { status: 200 });
      }
      if (url.endsWith('/api/queues')) {
        return new Response(JSON.stringify(mockQueuesPayload), { status: 200 });
      }
      if (url.endsWith('/api/content-profiles')) {
        return new Response(JSON.stringify({ profiles: [] }), { status: 200 });
      }
      if (url.endsWith('/api/analytics/categories')) {
        return new Response(JSON.stringify({ categories: [] }), { status: 200 });
      }
      if (url.endsWith('/api/subtitles/presets')) {
        return new Response(
          JSON.stringify({
            presets: [{ id: 'hormozi_pop', name: 'Hormozi Pop', description: 'Default' }],
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/layout-presets')) {
        return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      }
      if (url.endsWith('/api/pipeline/candidates')) {
        return new Response(JSON.stringify({ video_filename: null, candidates: [] }), { status: 200 });
      }
      if (url.endsWith('/api/pipeline/discover') && init?.method === 'POST') {
        return new Response(
          JSON.stringify({
            video_filename: 'stream_ep01_x4.mp4',
            total_candidates: 2,
            candidates: fakeCandidates,
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/pipeline/render-selected') && init?.method === 'POST') {
        capturedPayloads.push(JSON.parse(String(init.body || '{}')) as Record<string, unknown>);
        return new Response(
          JSON.stringify({ job_id: 'sel99', selected_count: 1, message: 'Renderizando 1 clip' }),
          { status: 202 }
        );
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
    });

    render(<App />);

    const countInput = await screen.findByLabelText(/^Shorts$/i) as HTMLInputElement;
    expect(countInput.max).toBe('24');
    await user.clear(countInput);
    await user.type(countInput, '16');

    await user.click(screen.getByRole('button', { name: /^Generar$/i }));
    const discoverBtn = await screen.findByRole('button', { name: /Escanear Clips IA/i });
    expect(discoverBtn.className).toContain('h-10');
    await user.click(discoverBtn);

    await waitFor(() => {
      expect(screen.getByText(/No van a creer lo que pasó en esta última ronda del torneo/i)).toBeInTheDocument();
      expect(screen.getByText(/93 \/ 100/i)).toBeInTheDocument();
    });

    // Dejar solo cand_01 marcado usando botón Solo Oro (>=85)
    const goldOnlyBtn = screen.getByRole('button', { name: /Solo Oro/i });
    expect(goldOnlyBtn.className).toContain('h-10');
    await user.click(goldOnlyBtn);

    const renderSelectedBtn = screen.getByRole('button', { name: /Renderizar Seleccionados/i });
    expect(renderSelectedBtn.className).toContain('h-10');
    await user.click(renderSelectedBtn);

    await waitFor(() => {
      expect(capturedPayloads.length).toBeGreaterThan(0);
    });
    const lastPayload = capturedPayloads[0];
    expect(lastPayload.candidate_ids).toEqual(['cand_01']);
    expect(lastPayload).toHaveProperty('layout_mode');
    expect(lastPayload).toHaveProperty('subtitle_preset');
    expect(lastPayload).toHaveProperty('subtitle_position');
  });

  it('deja los Shorts en modo Listo en local sin activar subida automática ni abrir modal al terminar', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url.includes('/api/inbox')) {
        return {
          ok: true,
          json: async () => ({
            ...mockInboxPayload,
            pipeline_status: {
              status: 'COMPLETED',
              current_video: 'stream.mp4',
              last_completed_at: '2026-11-13T10:00:00',
              job_id: 'job_local_ready_01',
            },
            settings: {
              ...mockInboxPayload.settings,
              auto_upload_to_youtube: false,
            },
          }),
        } as Response;
      }
      if (url.includes('/api/shorts')) {
        return {
          ok: true,
          json: async () => ({
            total: 1,
            shorts: [
              {
                filename: 'Local_Ready_01_Oro_91pts.mp4',
                folder: 'stream',
                relative_path: 'stream/Local_Ready_01_Oro_91pts.mp4',
                video_url: '/api/media/short/stream/Local_Ready_01_Oro_91pts.mp4',
                thumbnail_url: '/api/media/thumbnail/stream/Local_Ready_01_Oro_91pts.mp4',
                size_mb: 18.5,
                created_at: '2026-11-13 10:00:00',
                virality_score: 91,
                virality_grade: 9.1,
                tier: 'Oro',
                category: 'videojuegos',
                eligible_for_youtube: true,
                scheduled_ast: null,
                publish_at_utc: null,
                youtube_video_id: null,
                upload_progress_percent: 100,
                upload_status_detail: 'Listo en local (./output_shorts/) · Sin subida automática',
              },
            ],
            summary: {
              total: 1,
              oro: 1,
              plata: 0,
              meh: 0,
              youtube_eligible: 1,
              requires_schedule_confirmation: false,
            },
          }),
        } as Response;
      }
      if (url.includes('/api/queues')) {
        return { ok: true, json: async () => ({ youtube_slots: [], instagram_queue: [], tiktok_queue: [] }) } as Response;
      }
      if (url.includes('/api/analytics/categories')) {
        return { ok: true, json: async () => ({ categories: [], total_shorts: 1 }) } as Response;
      }
      return { ok: true, json: async () => ({ presets: [], candidates: [] }) } as Response;
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/Listo en local \(Sin programar\)/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Mostrar u ocultar categorías y estado de redes/i }));
    expect(screen.getByText(/Listo en local \(\.\/output_shorts\/\) · Sin subida automática/i)).toBeInTheDocument();
    expect(document.getElementById('auto-upload-switch')).toBeNull();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('muestra el preview en vivo de subtítulos animándose dentro del modal pre-análisis y reacciona al preset y posición elegidos', async () => {
    const user = userEvent.setup();
    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^Generar$/i })).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /^Generar$/i }));

    const livePreview = await screen.findByTestId('live-subtitle-preview');
    expect(livePreview).toBeInTheDocument();
    expect(livePreview).toHaveAttribute('data-subtitle-preset', 'hormozi_pop');

    const subPresetSelect = screen.getByLabelText(/Estilo de Subtítulos/i) as HTMLSelectElement;
    const subPosSelect = screen.getByLabelText(/Posición Subtítulos/i) as HTMLSelectElement;

    await user.selectOptions(subPresetSelect, 'nexus_cyber_glow');
    expect(livePreview).toHaveAttribute('data-subtitle-preset', 'nexus_cyber_glow');

    await user.selectOptions(subPosSelect, 'top');
    expect(livePreview).toHaveAttribute('data-subtitle-position', 'top');

    await user.selectOptions(subPresetSelect, 'one_word_punch');
    expect(livePreview).toHaveAttribute('data-subtitle-preset', 'one_word_punch');

    await user.selectOptions(subPresetSelect, 'none');
    expect(screen.getByText(/Sin subtítulos activos/i)).toBeInTheDocument();
  });

  it('organiza los Shorts en cuadrícula de 4 columnas con descarga grupal y sin modal x4', async () => {
    render(<App />);

    const grid4Col = await screen.findByTestId('shorts-grid-4col');
    expect(grid4Col.className).toContain('lg:grid-cols-4');

    const inlineVideos = grid4Col.querySelectorAll('video');
    expect(inlineVideos.length).toBe(2);
    expect(screen.getByText('94 / 100')).toBeInTheDocument();
    expect(screen.getByText('78 / 100')).toBeInTheDocument();

    expect(
      screen.queryByRole('button', { name: /Ver en Modal|Abrir Modal de Shorts en Cuadrícula/i })
    ).not.toBeInTheDocument();
    const downloadBtn = screen.getByRole('button', { name: /Descargar Shorts/i });
    expect(downloadBtn.className).toContain('h-10');
    expect(downloadBtn).toHaveTextContent(/Descargar Todos \(2\)/i);

    const allButtons = document.querySelectorAll('button');
    allButtons.forEach((btn) => {
      expect(btn.className).toContain('h-10');
    });
  });

  it('muestra Split 50/50 Limpio sin OmeTV Banner y conserva layout_mode=auto al editar el nombre de la escena', async () => {
    const user = userEvent.setup();
    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^Generar$/i })).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /^Generar$/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/Formato de Encuadre 9:16/i)).toBeInTheDocument();
    });

    const layoutSelect = screen.getByLabelText(/Formato de Encuadre 9:16/i) as HTMLSelectElement;
    await user.selectOptions(layoutSelect, 'split_50_50');

    const livePreview = screen.getByTestId('live-subtitle-preview');
    expect(livePreview).toHaveAttribute('data-layout-mode', 'split_50_50');
    expect(screen.getByText('Panel 1 · 50%')).toBeInTheDocument();
    expect(screen.getByText('Panel 2 · 50%')).toBeInTheDocument();
    expect(screen.queryByText(/OmeTV Banner/i)).not.toBeInTheDocument();

    await user.selectOptions(layoutSelect, 'auto');
    const sceneLabelInput = screen.getByLabelText(/Nombre de la Escena/i) as HTMLInputElement;
    expect(sceneLabelInput.className).toContain('h-10');
    await user.clear(sceneLabelInput);
    await user.type(sceneLabelInput, 'Cabina Podcast Debate');
    expect(layoutSelect.value).toBe('auto');

    const allButtons = document.querySelectorAll('button');
    allButtons.forEach((btn) => {
      expect(btn.className).toContain('h-10');
    });
  });

  it('envía custom_cam_box_norm=null en fullscreen tras detectar escena y envía cajas del Perfil de Contenido al seleccionarlo con split_50_50', async () => {
    const user = userEvent.setup();
    const postedPayloads: Array<Record<string, unknown>> = [];
    const presetCamBox = [0.05, 0.1, 0.4, 0.8];
    const presetContentBox = [0.55, 0.1, 0.4, 0.8];

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/api/inbox')) {
        return new Response(JSON.stringify(mockInboxPayload), { status: 200 });
      }
      if (url.endsWith('/api/shorts')) {
        return new Response(JSON.stringify({ total: 0, shorts: [] }), { status: 200 });
      }
      if (url.endsWith('/api/queues')) {
        return new Response(JSON.stringify(mockQueuesPayload), { status: 200 });
      }
      if (url.endsWith('/api/subtitles/presets')) {
        return new Response(
          JSON.stringify({
            presets: [{ id: 'hormozi_pop', name: 'Hormozi Pop', description: 'Rebote amarillo.' }],
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/content-profiles')) {
        return new Response(
          JSON.stringify({
            profiles: [
              {
                id: 202,
                name: 'Podcast Debate Cabina 50/50',
                match_keywords: ['tertulia'],
                scenes: [
                  {
                    rule_id: 'scene_1',
                    category: 'auto',
                    scene_label: 'Debate Cabina',
                    detected_share_pct: 100,
                    layout_mode: 'split_50_50',
                    subtitle_preset: 'hormozi_pop',
                    subtitle_position: 'auto',
                    cam_overlay_pos: 'top_right',
                    custom_cam_box_norm: presetCamBox,
                    custom_content_box_norm: presetContentBox,
                    custom_boxes_manual: true,
                  },
                ],
              },
            ],
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/pipeline/candidates')) {
        return new Response(JSON.stringify({ video_filename: null, candidates: [] }), { status: 200 });
      }
      if (url.endsWith('/api/scene/detect') && init?.method === 'POST') {
        return new Response(
          JSON.stringify({
            video_filename: 'CreadorStudio_LIVE_Demo.mp4',
            resolution: '1920x1080',
            width: 1920,
            height: 1080,
            detected_layout: 'fullscreen',
            faces_detected: 1,
            cam_box_norm: [0.3, 0.1, 0.4, 0.8],
            content_box_norm: [0.22, 0.0, 0.56, 1.0],
            frame_url: '/api/media/scene-frame?video_filename=CreadorStudio_LIVE_Demo.mp4',
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/pipeline/pre-analyze') && init?.method === 'POST') {
        return new Response(
          JSON.stringify({
            source_type: 'inbox',
            target: 'CreadorStudio_LIVE_Demo.mp4',
            video_title: 'Stream Gameplay & Charla',
            duration_sec: 1840.0,
            thumbnail_url: null,
            matched_profile_id: null,
            matched_profile_name: null,
            is_hybrid_multicategory: true,
            analysis_mode: 'local_multiframe',
            analysis_summary: 'Detectadas 2 escenas en el video.',
            category_rules: [
              {
                rule_id: 'scene_1',
                category: 'auto',
                scene_label: 'Charla Full Cam',
                detected_share_pct: 35,
                layout_mode: 'fullscreen',
                subtitle_preset: 'hormozi_pop',
                subtitle_position: 'bottom',
                cam_overlay_pos: 'top_right',
                custom_cam_box_norm: null,
                custom_content_box_norm: null,
                custom_boxes_manual: false,
                frame_url: null,
                sample_timestamp_sec: 120.0,
              },
              {
                rule_id: 'scene_2',
                category: 'auto',
                scene_label: 'Gameplay + Cámara',
                detected_share_pct: 65,
                layout_mode: 'gaming_hud',
                subtitle_preset: 'nexus_cyber_glow',
                subtitle_position: 'center',
                cam_overlay_pos: 'top_right',
                custom_cam_box_norm: [0.02, 0.35, 0.26, 0.35],
                custom_content_box_norm: [0.28, 0.05, 0.7, 0.9],
                custom_boxes_manual: false,
                frame_url: null,
                sample_timestamp_sec: 900.0,
              },
            ],
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/pipeline/process') && init?.method === 'POST') {
        const parsed = JSON.parse(String(init.body || '{}')) as Record<string, unknown>;
        postedPayloads.push(parsed);
        return new Response(
          JSON.stringify({
            job_id: 'job_test_5050',
            status: 'STARTED',
            target: 'CreadorStudio_LIVE_Demo.mp4',
            settings_applied: { ...mockInboxPayload.settings, layout_mode: parsed.layout_mode },
          }),
          { status: 200 }
        );
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^Generar$/i })).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /^Generar$/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Detectar Escena & Studio/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /Detectar Escena & Studio/i }));
    await waitFor(() => {
      expect(screen.getByTestId('studio-preview-9-16')).toBeInTheDocument();
    });

    const layoutSelect = screen.getByLabelText(/Formato de Encuadre 9:16/i) as HTMLSelectElement;
    await user.selectOptions(layoutSelect, 'fullscreen');
    await user.click(screen.getByRole('button', { name: /Confirmar y Generar Shorts/i }));

    await waitFor(() => {
      expect(postedPayloads.length).toBe(1);
    });
    expect(postedPayloads[0].layout_mode).toBe('fullscreen');
    expect(postedPayloads[0].custom_cam_box_norm).toBeNull();
    expect(postedPayloads[0].custom_content_box_norm).toBeNull();
    expect(postedPayloads[0].content_category).toBe('auto');

    await user.click(screen.getByRole('button', { name: /^Generar$/i }));
    const profileSelect = (await screen.findByLabelText(/Perfil de Contenido/i)) as HTMLSelectElement;
    const layoutSelectAfterReopen = screen.getByLabelText(/Formato de Encuadre 9:16/i) as HTMLSelectElement;
    await user.selectOptions(profileSelect, '202');
    expect(layoutSelectAfterReopen.value).toBe('split_50_50');

    await user.click(screen.getByRole('button', { name: /Confirmar y Generar Shorts/i }));
    await waitFor(() => {
      expect(postedPayloads.length).toBe(2);
    });
    expect(postedPayloads[1].layout_mode).toBe('split_50_50');
    expect(postedPayloads[1].custom_cam_box_norm).toEqual(presetCamBox);
    expect(postedPayloads[1].custom_content_box_norm).toEqual(presetContentBox);
    expect(postedPayloads[1].content_category).toBe('auto');

    const allButtons = document.querySelectorAll('button');
    allButtons.forEach((btn) => {
      expect(btn.className).toContain('h-10');
    });
  });

  it('oculta el selector de Música de Fondo (BGM) y envía bgm_mood="desactivada" al generar', async () => {
    const user = userEvent.setup();
    const postedPayloads: Array<Record<string, unknown>> = [];

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/api/inbox')) {
        return new Response(JSON.stringify(mockInboxPayload), { status: 200 });
      }
      if (url.endsWith('/api/shorts')) {
        return new Response(JSON.stringify({ total: 0, shorts: [] }), { status: 200 });
      }
      if (url.endsWith('/api/queues')) {
        return new Response(JSON.stringify(mockQueuesPayload), { status: 200 });
      }
      if (url.endsWith('/api/content-profiles')) {
        return new Response(JSON.stringify({ profiles: [] }), { status: 200 });
      }
      if (url.endsWith('/api/analytics/categories')) {
        return new Response(JSON.stringify({ categories: [] }), { status: 200 });
      }
      if (url.endsWith('/api/subtitles/presets')) {
        return new Response(
          JSON.stringify({
            presets: [{ id: 'hormozi_pop', name: 'Hormozi Pop', description: 'Rebote amarillo.' }],
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/layout-presets')) {
        return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      }
      if (url.endsWith('/api/pipeline/candidates')) {
        return new Response(JSON.stringify({ video_filename: null, candidates: [] }), { status: 200 });
      }
      if (url.endsWith('/api/pipeline/pre-analyze') && init?.method === 'POST') {
        return new Response(
          JSON.stringify({
            source_type: 'inbox',
            target: 'CreadorStudio_LIVE_Demo.mp4',
            video_title: 'Stream Gameplay & Charla',
            duration_sec: 1840.0,
            thumbnail_url: null,
            is_hybrid_multicategory: true,
            analysis_mode: 'local_multiframe',
            analysis_summary: 'Detectado stream híbrido: 35% charla Full Cam + 65% Gameplay + Cámara.',
            category_rules: [
              {
                rule_id: 'rule_1',
                category: 'opinion_monologo',
                scene_label: 'Charla Full Cam / Just Chatting',
                detected_share_pct: 35,
                layout_mode: 'fullscreen',
                subtitle_preset: 'hormozi_pop',
                subtitle_position: 'bottom',
                cam_overlay_pos: 'top_right',
                custom_cam_box_norm: null,
                custom_content_box_norm: null,
                custom_boxes_manual: false,
                frame_url: null,
                sample_timestamp_sec: 120.0,
              },
              {
                rule_id: 'rule_2',
                category: 'videojuegos',
                scene_label: 'Gameplay + Cámara',
                detected_share_pct: 65,
                layout_mode: 'gaming_hud',
                subtitle_preset: 'nexus_cyber_glow',
                subtitle_position: 'center',
                cam_overlay_pos: 'top_right',
                custom_cam_box_norm: [0.02, 0.35, 0.26, 0.35],
                custom_content_box_norm: [0.28, 0.05, 0.7, 0.9],
                custom_boxes_manual: false,
                frame_url: null,
                sample_timestamp_sec: 900.0,
              },
            ],
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/pipeline/process') && init?.method === 'POST') {
        const parsed = JSON.parse(String(init.body || '{}')) as Record<string, unknown>;
        postedPayloads.push(parsed);
        return new Response(
          JSON.stringify({
            job_id: 'job_no_bgm',
            status: 'STARTED',
            target: 'CreadorStudio_LIVE_Demo.mp4',
            settings_applied: { ...mockInboxPayload.settings, enable_bgm: false, default_bgm_mood: 'desactivada' },
          }),
          { status: 200 }
        );
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^Generar$/i })).toBeInTheDocument();
    });

    expect(screen.queryByLabelText(/Música de Fondo/i)).not.toBeInTheDocument();
    expect(document.querySelector('#bgm-mood-select')).toBeNull();

    await user.click(screen.getByRole('button', { name: /^Generar$/i }));

    await waitFor(() => {
      expect(screen.getByTestId('preflight-analysis-modal')).toBeInTheDocument();
    });
    expect(document.querySelector('#bgm-mood-select')).toBeNull();

    await user.click(screen.getByRole('button', { name: /Confirmar y Generar Shorts/i }));

    await waitFor(() => {
      expect(postedPayloads.length).toBe(1);
    });
    expect(postedPayloads[0].bgm_mood).toBe('desactivada');

    const allButtons = document.querySelectorAll('button');
    allButtons.forEach((btn) => {
      expect(btn.className).toContain('h-10');
    });
  });

  it('pausa automáticamente los otros videos al reproducir un Short y abre el Reproductor Flotante sin pantalla completa', async () => {
    const pauseSpy = vi
      .spyOn(HTMLMediaElement.prototype, 'pause')
      .mockImplementation(function (this: HTMLMediaElement) {
        Object.defineProperty(this, 'paused', { value: true, configurable: true });
      });

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/inbox')) {
        return new Response(JSON.stringify(mockInboxPayload), { status: 200 });
      }
      if (url.endsWith('/api/shorts')) {
        return new Response(JSON.stringify(mockShortsPayload), { status: 200 });
      }
      if (url.endsWith('/api/queues')) {
        return new Response(JSON.stringify(mockQueuesPayload), { status: 200 });
      }
      if (url.endsWith('/api/content-profiles')) {
        return new Response(JSON.stringify({ profiles: [] }), { status: 200 });
      }
      if (url.endsWith('/api/analytics/categories')) {
        return new Response(JSON.stringify({ categories: [] }), { status: 200 });
      }
      if (url.endsWith('/api/subtitles/presets')) {
        return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      }
      if (url.endsWith('/api/layout-presets')) {
        return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      }
      if (url.endsWith('/api/pipeline/candidates')) {
        return new Response(JSON.stringify({ video_filename: null, candidates: [] }), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTitle('CreadorStudio_01_Oro_94pts.mp4')).toBeInTheDocument();
      expect(screen.getByTitle('CreadorStudio_02_Plata_78pts.mp4')).toBeInTheDocument();
    });

    const cardVideos = Array.from(
      document.querySelectorAll('[data-testid="shorts-grid-4col"] video')
    ) as HTMLVideoElement[];
    expect(cardVideos.length).toBe(2);

    // Ningún reproductor debe permitir pantalla completa
    cardVideos.forEach((vid) => {
      expect(vid.getAttribute('controlsList')).toBe('nofullscreen');
    });

    // Simular vid0 reproduciéndose y luego darle play a vid1: vid0 debe pausarse automáticamente
    Object.defineProperty(cardVideos[0], 'paused', { value: false, configurable: true });
    Object.defineProperty(cardVideos[1], 'paused', { value: true, configurable: true });
    fireEvent.play(cardVideos[1]);

    expect(pauseSpy).toHaveBeenCalledTimes(1);
    expect(pauseSpy.mock.instances[0]).toBe(cardVideos[0]);

    // Con doble clic sobre el video del Short se abre el Reproductor Flotante NO bloqueante delante de la UI
    expect(screen.queryByRole('button', { name: /Flotante/i })).not.toBeInTheDocument();
    fireEvent.doubleClick(cardVideos[0]);
    const floatingDialog = await screen.findByTestId('floating-short-player');
    expect(floatingDialog).toHaveAttribute('aria-modal', 'false');
    const floatingVideo = screen.getByTestId('short-video-player') as HTMLVideoElement;
    expect(floatingVideo.getAttribute('controlsList')).toBe('nofullscreen');

    const allButtons = document.querySelectorAll('button');
    allButtons.forEach((btn) => {
      expect(btn.className).toContain('h-10');
    });
  });

  it('permite editar el layout después de previsualizar y programar fecha/hora individual por Short', async () => {
    const user = userEvent.setup();
    const rerenderBodies: Array<Record<string, unknown>> = [];
    const scheduleSingleBodies: Array<Record<string, unknown>> = [];

    let shortsState = structuredClone(mockShortsPayload);

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/api/inbox')) {
        return new Response(JSON.stringify(mockInboxPayload), { status: 200 });
      }
      if (url.endsWith('/api/shorts')) {
        return new Response(JSON.stringify(shortsState), { status: 200 });
      }
      if (url.endsWith('/api/queues')) {
        return new Response(JSON.stringify(mockQueuesPayload), { status: 200 });
      }
      if (url.endsWith('/api/content-profiles')) {
        return new Response(JSON.stringify({ profiles: [] }), { status: 200 });
      }
      if (url.endsWith('/api/analytics/categories')) {
        return new Response(JSON.stringify({ categories: [] }), { status: 200 });
      }
      if (url.endsWith('/api/subtitles/presets')) {
        return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      }
      if (url.endsWith('/api/layout-presets')) {
        return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      }
      if (url.endsWith('/api/pipeline/candidates')) {
        return new Response(JSON.stringify({ video_filename: null, candidates: [] }), { status: 200 });
      }
      if (url.endsWith('/api/shorts/scene-detect') && init?.method === 'POST') {
        return new Response(
          JSON.stringify({
            short_rel_path: 'CreadorStudio_LIVE_Demo/CreadorStudio_01_Oro_94pts.mp4',
            filename: 'CreadorStudio_01_Oro_94pts.mp4',
            resolution: '1920x1080',
            width: 1920,
            height: 1080,
            detected_layout: 'fullscreen',
            current_layout: 'fullscreen',
            faces_detected: 1,
            cam_box_norm: [0.68, 0.06, 0.28, 0.38],
            content_box_norm: [0.0, 0.0, 1.0, 1.0],
            subtitle_preset: 'hormozi_pop',
            subtitle_position: 'auto',
            cam_overlay_pos: 'top_right',
            has_source_16_9: true,
            frame_url: '/api/media/short-scene-frame?short_rel_path=CreadorStudio_LIVE_Demo/CreadorStudio_01_Oro_94pts.mp4',
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/shorts/rerender') && init?.method === 'POST') {
        const body = JSON.parse(String(init.body || '{}')) as Record<string, unknown>;
        rerenderBodies.push(body);
        const updatedFirst = {
          ...shortsState.shorts[0],
          layout_used: String(body.layout_mode || 'split_50_50'),
        };
        shortsState = {
          ...shortsState,
          shorts: [updatedFirst, shortsState.shorts[1]],
        };
        return new Response(
          JSON.stringify({ rerendered: true, short: updatedFirst, shorts: shortsState.shorts }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/shorts/schedule-single') && init?.method === 'POST') {
        const body = JSON.parse(String(init.body || '{}')) as Record<string, unknown>;
        scheduleSingleBodies.push(body);
        const updatedFirst = {
          ...shortsState.shorts[0],
          scheduled_ast: '2026-12-20 06:30 PM AST',
          publish_at_utc: '2026-12-20T22:30:00Z',
        };
        shortsState = {
          ...shortsState,
          shorts: [updatedFirst, shortsState.shorts[1]],
        };
        return new Response(
          JSON.stringify({
            scheduled: true,
            filename: 'CreadorStudio_01_Oro_94pts.mp4',
            scheduled_ast: '2026-12-20 06:30 PM AST',
            publish_at_utc: '2026-12-20T22:30:00Z',
            youtube_video_id: 'yt_single_1',
            short: updatedFirst,
            shorts: shortsState.shorts,
          }),
          { status: 200 }
        );
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTitle('CreadorStudio_01_Oro_94pts.mp4')).toBeInTheDocument();
    });

    // 1) Abrir Editor Post-Previsualización unificado para el Short 01
    expect(screen.queryByRole('button', { name: /^(Recortar|Editar Layout)$/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Editar Short CreadorStudio_01_Oro_94pts\.mp4/i }));
    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: /Editor de Layout del Short/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /^50\/50 Limpio$/i }));
    const subPresetSelect = screen.getByLabelText(/Estilo de Subtítulos del Short/i) as HTMLSelectElement;
    await user.selectOptions(subPresetSelect, 'minimal_white');

    const allEditorButtons = document.querySelectorAll('button');
    allEditorButtons.forEach((btn) => {
      expect(btn.className).toContain('h-10');
    });

    await user.click(screen.getByRole('button', { name: /Guardar y Re-renderizar Short/i }));
    await waitFor(() => {
      expect(rerenderBodies.length).toBe(1);
    });
    expect(rerenderBodies[0].layout_mode).toBe('split_50_50');
    expect(rerenderBodies[0].subtitle_preset).toBe('minimal_white');

    // 2) Programar Fecha y Hora individualmente en el Short 01
    const dateInput = screen.getByLabelText(/Fecha y hora de CreadorStudio_01_Oro_94pts\.mp4/i) as HTMLInputElement;
    fireEvent.change(dateInput, { target: { value: '2026-12-20T18:30' } });
    await user.click(screen.getByRole('button', { name: /Programar Short CreadorStudio_01_Oro_94pts\.mp4/i }));

    await waitFor(() => {
      expect(scheduleSingleBodies.length).toBe(1);
    });
    expect(scheduleSingleBodies[0].short_rel_path).toBe('CreadorStudio_LIVE_Demo/CreadorStudio_01_Oro_94pts.mp4');
    expect(scheduleSingleBodies[0].scheduled_time).toBe('2026-12-20T18:30');
    expect(scheduleSingleBodies[0].upload_to_youtube).toBe(true);
    await waitFor(() => {
      expect(screen.getAllByText(/2026-12-20 06:30 PM AST/i).length).toBeGreaterThanOrEqual(2);
    });

    const finalButtons = document.querySelectorAll('button');
    finalButtons.forEach((btn) => {
      expect(btn.className).toContain('h-10');
    });
  });

  it('abre un Nuevo Proyecto en ventana independiente via POST /api/project/new sin detener ni borrar el proyecto activo', async () => {
    const user = userEvent.setup();
    const capturedBodies: Record<string, unknown>[] = [];
    const openSpy = vi
      .spyOn(window, 'open')
      .mockImplementation(() => ({ closed: false } as unknown as Window));

    const runningInboxPayload = {
      ...mockInboxPayload,
      pipeline_status: {
        ...mockInboxPayload.pipeline_status,
        status: 'RUNNING',
      },
    };

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : input.toString();
      const method = (init?.method || 'GET').toUpperCase();

      if (url.endsWith('/api/project/new') && method === 'POST') {
        const bodyObj = JSON.parse(String(init?.body || '{}')) as Record<string, unknown>;
        capturedBodies.push(bodyObj);
        return new Response(
          JSON.stringify({
            created: true,
            reset: false,
            mode: 'independent',
            project_id: bodyObj.project_id,
            project_url: `/?project=${String(bodyObj.project_id)}`,
            pipeline_status: {
              ...mockInboxPayload.pipeline_status,
              project_id: bodyObj.project_id,
              job_id: null,
              status: 'IDLE',
              current_video: null,
              progress_percent: 0,
              phase_label: 'Nuevo Proyecto',
              step_detail: 'Ventana independiente lista.',
              message: 'Nuevo proyecto independiente listo para seleccionar o pegar otro video.',
            },
            videos: mockInboxPayload.videos,
            disk_space: mockInboxPayload.disk_space,
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/inbox')) {
        return new Response(JSON.stringify(runningInboxPayload), { status: 200 });
      }
      if (url.endsWith('/api/pipeline/status')) {
        return new Response(JSON.stringify(runningInboxPayload.pipeline_status), { status: 200 });
      }
      if (url.endsWith('/api/shorts')) {
        return new Response(JSON.stringify(mockShortsPayload), { status: 200 });
      }
      if (url.endsWith('/api/queues')) {
        return new Response(JSON.stringify(mockQueuesPayload), { status: 200 });
      }
      if (url.endsWith('/api/content-profiles')) {
        return new Response(JSON.stringify({ profiles: [] }), { status: 200 });
      }
      if (url.endsWith('/api/analytics/categories')) {
        return new Response(JSON.stringify({ categories: [] }), { status: 200 });
      }
      if (url.endsWith('/api/subtitles/presets')) {
        return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      }
      if (url.endsWith('/api/layout-presets')) {
        return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      }
      if (url.endsWith('/api/pipeline/candidates')) {
        return new Response(JSON.stringify({ video_filename: null, candidates: [] }), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTitle('CreadorStudio_01_Oro_94pts.mp4')).toBeInTheDocument();
    });

    const newProjectBtn = screen.getByRole('button', { name: /Iniciar Nuevo Proyecto/i });
    expect(newProjectBtn.className).toContain('h-10');
    expect(newProjectBtn).not.toBeDisabled();
    await user.click(newProjectBtn);

    await waitFor(() => {
      expect(capturedBodies.length).toBe(1);
      expect(screen.getByText(/Nuevo proyecto abierto en una ventana independiente/i)).toBeInTheDocument();
    });

    const sentBody = capturedBodies[0];
    expect(sentBody.mode).toBe('independent');
    expect(String(sentBody.project_id || '')).toMatch(/^Proyecto_\d{4}-\d{2}-\d{2}/);
    expect(openSpy).toHaveBeenCalledTimes(1);
    const [openedUrl, openedTarget] = openSpy.mock.calls[0];
    expect(String(openedUrl)).toContain(`?project=${String(sentBody.project_id)}`);
    expect(openedTarget).toBe('_blank');

    // El proyecto actual conserva sus Shorts y su ejecución intacta.
    expect(screen.getByTitle('CreadorStudio_01_Oro_94pts.mp4')).toBeInTheDocument();

    const allButtons = document.querySelectorAll('button');
    allButtons.forEach((btn) => {
      expect(btn.className).toContain('h-10');
    });
  });

  it('aisla las peticiones con ?project=p_est_02 en ventanas independientes y omite autoselección de inbox', async () => {
    window.history.pushState({}, '', '/?project=p_est_02');
    const requestedUrls: string[] = [];

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = typeof input === 'string' ? input : input.toString();
      requestedUrls.push(url);

      if (url.includes('/api/inbox')) {
        return new Response(
          JSON.stringify({
            ...mockInboxPayload,
            project_id: 'p_est_02',
            pipeline_status: {
              ...mockInboxPayload.pipeline_status,
              project_id: 'p_est_02',
              job_id: null,
              status: 'IDLE',
              current_video: null,
              progress_percent: 0,
            },
          }),
          { status: 200 }
        );
      }
      if (url.includes('/api/shorts')) {
        return new Response(JSON.stringify({ project_id: 'p_est_02', total: 0, shorts: [] }), { status: 200 });
      }
      if (url.endsWith('/api/queues')) {
        return new Response(JSON.stringify(mockQueuesPayload), { status: 200 });
      }
      if (url.endsWith('/api/content-profiles')) {
        return new Response(JSON.stringify({ profiles: [] }), { status: 200 });
      }
      if (url.endsWith('/api/analytics/categories')) {
        return new Response(JSON.stringify({ categories: [] }), { status: 200 });
      }
      if (url.endsWith('/api/subtitles/presets')) {
        return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      }
      if (url.endsWith('/api/layout-presets')) {
        return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      }
      if (url.includes('/api/pipeline/candidates')) {
        return new Response(
          JSON.stringify({ project_id: 'p_est_02', video_filename: null, candidates: [] }),
          { status: 200 }
        );
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('active-project-badge')).toHaveTextContent(/Proyecto:\s*p_est_02/i);
    });

    expect(requestedUrls).toContain('/api/inbox?project_id=p_est_02');
    expect(requestedUrls).toContain('/api/shorts?project_id=p_est_02');
    expect(requestedUrls).toContain('/api/pipeline/candidates?project_id=p_est_02');

    expect(document.getElementById('source-type-select')).toBeNull();
    expect(document.getElementById('inbox-video-select')).toBeNull();
    expect(screen.getByTestId('selected-local-video-display')).toHaveTextContent(/Ningún archivo elegido/i);

    const allButtons = document.querySelectorAll('button');
    allButtons.forEach((btn) => {
      expect(btn.className).toContain('h-10');
    });
  });

  it('conmuta la ingesta Omnibox entre URL y Archivo Local vía selector nativo del navegador sin desplegables y muestra Modo Local-Ready', async () => {
    const user = userEvent.setup();
    let uploadCalls = 0;
    let uploadedHeaderName = '';
    const preAnalyzeBodies: Array<Record<string, unknown>> = [];

    const origInputClick = HTMLInputElement.prototype.click;
    let fileInputClicks = 0;
    const inputClickSpy = vi
      .spyOn(HTMLInputElement.prototype, 'click')
      .mockImplementation(function (this: HTMLInputElement) {
        if (this.getAttribute('data-testid') === 'local-video-file-input') {
          fileInputClicks += 1;
          return;
        }
        origInputClick.call(this);
      });

    try {
      const fetchSpy = vi.mocked(globalThis.fetch);
      const prevImpl = fetchSpy.getMockImplementation();
      fetchSpy.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input.toString();
        if (url.endsWith('/api/local-video/upload') && init?.method === 'POST') {
          uploadCalls += 1;
          const headersObj = (init.headers || {}) as Record<string, string>;
          uploadedHeaderName = decodeURIComponent(
            headersObj['X-File-Name'] || headersObj['x-file-name'] || ''
          );
          return new Response(
            JSON.stringify({
              cancelled: false,
              file_path: 'D:/Clips/Partida_Epica.mp4',
              file_name: 'Partida_Epica.mp4',
              size_mb: 312.4,
            }),
            { status: 200 }
          );
        }
        if (url.endsWith('/api/pipeline/pre-analyze') && init?.method === 'POST') {
          if (typeof init.body === 'string') {
            preAnalyzeBodies.push(JSON.parse(init.body) as Record<string, unknown>);
          }
        }
        return prevImpl
          ? prevImpl(input, init)
          : new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
      });

      render(<App />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Pegar URL de YouTube \/ LIVE/i })).toBeInTheDocument();
      });
      expect(screen.queryByText(/Modo Local-Ready/i)).not.toBeInTheDocument();
      expect(document.getElementById('auto-upload-switch')).toBeNull();

      expect(document.getElementById('source-type-select')).toBeNull();
      expect(document.getElementById('inbox-video-select')).toBeNull();

      const urlSwitchBtn = screen.getByRole('button', { name: /Pegar URL de YouTube \/ LIVE/i });
      const localPickBtn = screen.getByRole('button', { name: /^Archivo Local$/i });
      expect(urlSwitchBtn.className).toContain('h-10');
      expect(localPickBtn.className).toContain('h-10');

      await user.click(urlSwitchBtn);
      expect(screen.getByLabelText(/URL de YouTube, Twitch o Kick/i)).toBeInTheDocument();

      // Al pulsar Archivo Local se cambia a modo local y se dispara el selector nativo del navegador
      await user.click(localPickBtn);
      expect(fileInputClicks).toBe(1);
      const fileInput = screen.getByTestId('local-video-file-input') as HTMLInputElement;
      const sampleFile = new File([new Uint8Array(1024)], 'Partida_Epica.mp4', {
        type: 'video/mp4',
      });
      fireEvent.change(fileInput, { target: { files: [sampleFile] } });

      await waitFor(() => {
        expect(uploadCalls).toBe(1);
        expect(screen.getByTestId('selected-local-video-display')).toHaveTextContent('Partida_Epica.mp4');
      });
      expect(uploadedHeaderName).toBe('Partida_Epica.mp4');
      expect(screen.getByTestId('selected-local-video-display')).toHaveTextContent('312.4 MB');

      // También el botón/caja de archivo dispara el selector nativo y cancelar preserva el archivo anterior
      await user.click(screen.getByTestId('selected-local-video-display'));
      expect(fileInputClicks).toBe(2);
      fireEvent.change(fileInput, { target: { files: [] } });
      expect(uploadCalls).toBe(1);
      expect(screen.getByTestId('selected-local-video-display')).toHaveTextContent('Partida_Epica.mp4');

      await user.click(screen.getByRole('button', { name: /^Generar$/i }));
      await waitFor(() => {
        expect(screen.getByTestId('preflight-analysis-modal')).toBeInTheDocument();
      });
      expect(preAnalyzeBodies.length).toBeGreaterThanOrEqual(1);
      expect(preAnalyzeBodies[0]).toMatchObject({
        source_type: 'inbox',
        video_filename: 'D:/Clips/Partida_Epica.mp4',
      });

      document.querySelectorAll('button').forEach((btn) => {
        expect(btn.className).toContain('h-10');
      });
    } finally {
      inputClickSpy.mockRestore();
    }
  });

  it('filtra galería por categoría de cuentas, muestra 4 barras sin regla <85 y abre editor Layout + Duración', async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : input.toString();
      const method = (init?.method || 'GET').toUpperCase();

      if (url.endsWith('/api/inbox')) {
        return new Response(JSON.stringify(mockInboxPayload), { status: 200 });
      }
      if (url.endsWith('/api/shorts')) {
        return new Response(
          JSON.stringify({
            total: 2,
            shorts: [
              { ...mockShortsPayload.shorts[0], eligible_for_youtube: true, account_categories: ['gaming', 'clipping'] },
              { ...mockShortsPayload.shorts[1], eligible_for_youtube: true, account_categories: ['principales'] },
            ],
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/queues')) {
        return new Response(JSON.stringify(mockQueuesPayload), { status: 200 });
      }
      if (url.endsWith('/api/content-profiles')) {
        return new Response(JSON.stringify({ profiles: [] }), { status: 200 });
      }
      if (url.endsWith('/api/analytics/categories')) {
        return new Response(JSON.stringify({ categories: [] }), { status: 200 });
      }
      if (url.endsWith('/api/subtitles/presets')) {
        return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      }
      if (url.endsWith('/api/layout-presets')) {
        return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      }
      if (url.endsWith('/api/pipeline/candidates')) {
        return new Response(JSON.stringify({ video_filename: null, candidates: [] }), { status: 200 });
      }
      if (url.endsWith('/api/shorts/scene-detect') && method === 'POST') {
        return new Response(
          JSON.stringify({
            short_rel_path: 'CreadorStudio_LIVE_Demo/CreadorStudio_01_Oro_94pts.mp4',
            frame_url: '/api/media/short-scene-frame?short_rel_path=test',
            edit_media_url: '/api/media/short-edit-source/CreadorStudio_LIVE_Demo/CreadorStudio_01_Oro_94pts.mp4',
            resolution: '1920x1080',
            faces_detected: 1,
            has_source_16_9: true,
            detected_layout: 'split_50_50',
            current_layout: 'split_streamer',
            cam_box_norm: [0.65, 0.05, 0.3, 0.4],
            content_box_norm: [0.0, 0.0, 1.0, 1.0],
            subtitle_preset: 'hormozi_pop',
            subtitle_position: 'auto',
            cam_overlay_pos: 'top_right',
            trim_start_sec: 10,
            trim_end_sec: 55,
            min_trim_sec: 0,
            max_trim_sec: 85,
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/shorts/rerender') && method === 'POST') {
        return new Response(
          JSON.stringify({
            rerendered: true,
            short: { ...mockShortsPayload.shorts[0], eligible_for_youtube: true, layout_used: 'split_50_50', duration_sec: 50 },
            shorts: [
              { ...mockShortsPayload.shorts[0], eligible_for_youtube: true, layout_used: 'split_50_50', duration_sec: 50 },
              { ...mockShortsPayload.shorts[1], eligible_for_youtube: true },
            ],
          }),
          { status: 200 }
        );
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
    });

    render(<App />);

    const grid = await screen.findByTestId('shorts-grid-4col');
    expect(screen.getByText(/ORO 🔥/i)).toBeInTheDocument();
    expect(screen.getByText(/PLATA ⚡/i)).toBeInTheDocument();
    expect(screen.queryByText(/Solo IG \/ TikTok/i)).not.toBeInTheDocument();

    const downloadLink = screen.getByRole('link', {
      name: /Descargar Short CreadorStudio_01_Oro_94pts\.mp4/i,
    }) as HTMLAnchorElement;
    expect(downloadLink).toHaveAttribute('download', 'CreadorStudio_01_Oro_94pts.mp4');

    const gamingFilterBtn = screen.getByRole('button', { name: /^Gaming \(1\)/i });
    const principalesFilterBtn = screen.getByRole('button', { name: /^Principales \(1\)/i });
    const allFilterBtn = screen.getByRole('button', { name: /^Todos \(2\)/i });

    await user.click(gamingFilterBtn);
    expect(grid.querySelectorAll('video').length).toBe(1);
    expect(screen.getByTitle('CreadorStudio_01_Oro_94pts.mp4')).toBeInTheDocument();
    expect(screen.queryByTitle('CreadorStudio_02_Plata_78pts.mp4')).not.toBeInTheDocument();

    await user.click(principalesFilterBtn);
    expect(grid.querySelectorAll('video').length).toBe(1);
    expect(screen.getByTitle('CreadorStudio_02_Plata_78pts.mp4')).toBeInTheDocument();

    await user.click(allFilterBtn);
    expect(grid.querySelectorAll('video').length).toBe(2);

    const editBtn = screen.getByRole('button', {
      name: /Editar Short CreadorStudio_01_Oro_94pts\.mp4/i,
    });
    await user.click(editBtn);

    const saveRerenderBtn = await screen.findByRole('button', {
      name: /Guardar y Re-renderizar Short/i,
    });
    await user.click(saveRerenderBtn);

    await waitFor(() => {
      const firstVideo = grid.querySelector('video') as HTMLVideoElement;
      expect(firstVideo.getAttribute('src')).toMatch(/\?v=\d+/);
    });
  });

  it('hidrata Dark Studio (#090B10 / #11151F) desde settings.theme_mode y mantiene h-10 en todos los botones', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url.endsWith('/api/inbox')) {
        return new Response(
          JSON.stringify({
            ...mockInboxPayload,
            settings: { ...mockInboxPayload.settings, theme_mode: 'dark' },
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/shorts')) {
        return new Response(JSON.stringify({ total: 0, shorts: [] }), { status: 200 });
      }
      if (url.endsWith('/api/queues')) {
        return new Response(JSON.stringify(mockQueuesPayload), { status: 200 });
      }
      if (url.endsWith('/api/content-profiles')) {
        return new Response(JSON.stringify({ profiles: [] }), { status: 200 });
      }
      if (url.endsWith('/api/analytics/categories')) {
        return new Response(JSON.stringify({ categories: [] }), { status: 200 });
      }
      if (url.endsWith('/api/subtitles/presets')) {
        return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      }
      if (url.endsWith('/api/layout-presets')) {
        return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      }
      if (url.endsWith('/api/pipeline/candidates')) {
        return new Response(JSON.stringify({ video_filename: null, candidates: [] }), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
    });

    render(<App />);

    await waitFor(() => {
      expect(document.documentElement.classList.contains('dark')).toBe(true);
    });

    const studioSurface = document.querySelector('[data-testid="dark-studio-shell"]');
    expect(studioSurface).toBeInTheDocument();
    expect(studioSurface?.className).toContain('dark:bg-[#090B10]');

    const studioPanel = document.querySelector('header');
    expect(studioPanel?.className).toContain('dark:bg-[#11151F]/90');

    const allButtons = document.querySelectorAll('button');
    allButtons.forEach((btn) => {
      expect(btn.className).toContain('h-10');
    });
  });

  it('elimina selectores manuales del panel principal, auto-reconoce Perfil de Contenido multi-escena y permite editar/agregar escenas antes de generar', async () => {
    const user = userEvent.setup();
    const processPayloads: Array<Record<string, unknown>> = [];

    const savedCreadorProfile = {
      id: 77,
      name: 'CreadorStudio Live',
      match_keywords: ['creadorstudio', 'live'],
      scenes: [
        {
          rule_id: 'rule_1',
          category: 'auto',
          scene_label: 'Charla Full Cam / Opinión',
          detected_share_pct: 35,
          layout_mode: 'fullscreen',
          subtitle_preset: 'hormozi_pop',
          subtitle_position: 'bottom',
          cam_overlay_pos: 'top_right',
          custom_cam_box_norm: null,
          custom_content_box_norm: null,
          custom_boxes_manual: false,
          frame_url: null,
          sample_timestamp_sec: 90.0,
        },
        {
          rule_id: 'rule_2',
          category: 'auto',
          scene_label: 'Gameplay + Cámara',
          detected_share_pct: 65,
          layout_mode: 'gaming_hud',
          subtitle_preset: 'nexus_cyber_glow',
          subtitle_position: 'center',
          cam_overlay_pos: 'top_right',
          custom_cam_box_norm: [0.02, 0.35, 0.26, 0.35],
          custom_content_box_norm: [0.28, 0.05, 0.7, 0.9],
          custom_boxes_manual: false,
          frame_url: null,
          sample_timestamp_sec: 820.0,
        },
      ],
    };

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method || 'GET').toUpperCase();

      if (url.endsWith('/api/inbox')) {
        return new Response(JSON.stringify(mockInboxPayload), { status: 200 });
      }
      if (url.endsWith('/api/shorts')) {
        return new Response(JSON.stringify({ total: 0, shorts: [] }), { status: 200 });
      }
      if (url.endsWith('/api/queues')) {
        return new Response(JSON.stringify(mockQueuesPayload), { status: 200 });
      }
      if (url.endsWith('/api/content-profiles')) {
        return new Response(JSON.stringify({ profiles: [savedCreadorProfile] }), { status: 200 });
      }
      if (url.endsWith('/api/subtitles/presets')) {
        return new Response(
          JSON.stringify({
            presets: [
              { id: 'hormozi_pop', name: 'Hormozi Pop', description: 'Pop amarillo.' },
              { id: 'nexus_cyber_glow', name: 'Nexus Cyber Glow', description: 'Cian neón.' },
              { id: 'karaoke_duo', name: 'Karaoke Dúo', description: 'Barrido verde.' },
            ],
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/pipeline/candidates')) {
        return new Response(JSON.stringify({ video_filename: null, candidates: [] }), { status: 200 });
      }
      if (url.endsWith('/api/pipeline/pre-analyze') && method === 'POST') {
        return new Response(
          JSON.stringify({
            source_type: 'inbox',
            target: 'CreadorStudio_LIVE_Demo.mp4',
            video_title: 'CreadorStudio Live Gameplay & Charla',
            duration_sec: 1840.0,
            thumbnail_url: null,
            matched_profile_id: 77,
            matched_profile_name: 'CreadorStudio Live',
            suggested_profile_name: 'CreadorStudio Live',
            suggested_keywords: ['creadorstudio', 'live'],
            is_hybrid_multicategory: true,
            analysis_mode: 'profile_matched',
            analysis_summary: 'Perfil auto-reconocido: CreadorStudio Live (2 escenas configuradas).',
            category_rules: savedCreadorProfile.scenes,
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/pipeline/process') && method === 'POST') {
        const parsed = JSON.parse(String(init?.body || '{}')) as Record<string, unknown>;
        processPayloads.push(parsed);
        return new Response(
          JSON.stringify({
            job_id: 'job_multicat_01',
            status: 'STARTED',
            target: 'CreadorStudio_LIVE_Demo.mp4',
            settings_applied: mockInboxPayload.settings,
          }),
          { status: 200 }
        );
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^Generar$/i })).toBeInTheDocument();
    });

    // Panel principal limpio sin ruido de edición pre-análisis
    expect(screen.queryByLabelText(/Categoría de Analítica Viral/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Vara de Medición Activa/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Formato de Encuadre 9:16/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Estilo de Subtítulos/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Detectar Escena & Studio/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Escanear Clips IA/i })).not.toBeInTheDocument();
    expect(screen.queryByTestId('live-subtitle-preview')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /^Generar$/i }));

    const modal = await screen.findByTestId('preflight-analysis-modal');
    expect(modal).toBeInTheDocument();
    expect(screen.getByText(/^Perfil Auto-Reconocido:\s*CreadorStudio Live$/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Categoría de Analítica Viral/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Vara de Medición Activa/i)).not.toBeInTheDocument();
    expect(screen.getByTestId('category-rule-card-rule_1')).toBeInTheDocument();
    expect(screen.getByTestId('category-rule-card-rule_2')).toBeInTheDocument();
    expect(processPayloads.length).toBe(0);

    // Editar Escena 2 a split_streamer y agregar Escena 3 sin sobrescribir Escena 1
    await user.click(screen.getByRole('button', { name: /Configurar Escena 2/i }));
    const modalLayoutSelect = screen.getByLabelText(/Formato de Encuadre 9:16/i) as HTMLSelectElement;
    await user.selectOptions(modalLayoutSelect, 'split_streamer');

    await user.click(screen.getByRole('button', { name: /Agregar Escena/i }));
    expect(screen.getByTestId('category-rule-card-scene_3')).toBeInTheDocument();

    const modalButtons = modal.querySelectorAll('button');
    modalButtons.forEach((btn) => {
      expect(btn.className).toContain('h-10');
    });

    await user.click(screen.getByRole('button', { name: /Confirmar y Generar Shorts/i }));

    await waitFor(() => {
      expect(processPayloads.length).toBe(1);
    });

    expect(processPayloads[0].content_category).toBe('auto');
    const sentRules = processPayloads[0].category_rules as Array<Record<string, unknown>>;
    expect(Array.isArray(sentRules)).toBe(true);
    expect(sentRules.length).toBe(3);
    expect(sentRules[0]).toMatchObject({
      rule_id: 'rule_1',
      category: 'auto',
      layout_mode: 'fullscreen',
      subtitle_preset: 'hormozi_pop',
    });
    expect(sentRules[1]).toMatchObject({
      rule_id: 'rule_2',
      category: 'auto',
      layout_mode: 'split_streamer',
    });
    expect(sentRules[2]).toMatchObject({
      rule_id: 'scene_3',
      category: 'auto',
    });
  });

  it('habilita y ejecuta Detectar Escena & Studio en modo URL Directa con botones h-10', async () => {
    const user = userEvent.setup();
    const sceneDetectPayloads: Array<Record<string, unknown>> = [];

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method || 'GET').toUpperCase();

      if (url.endsWith('/api/inbox')) {
        return new Response(JSON.stringify(mockInboxPayload), { status: 200 });
      }
      if (url.endsWith('/api/shorts')) {
        return new Response(JSON.stringify({ total: 0, shorts: [] }), { status: 200 });
      }
      if (url.endsWith('/api/queues')) {
        return new Response(JSON.stringify(mockQueuesPayload), { status: 200 });
      }
      if (url.endsWith('/api/content-profiles')) {
        return new Response(JSON.stringify({ profiles: [] }), { status: 200 });
      }
      if (url.endsWith('/api/subtitles/presets')) {
        return new Response(
          JSON.stringify({
            presets: [{ id: 'hormozi_pop', name: 'Hormozi Pop', description: 'Pop amarillo.' }],
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/pipeline/candidates')) {
        return new Response(JSON.stringify({ video_filename: null, candidates: [] }), { status: 200 });
      }
      if (url.endsWith('/api/pipeline/pre-analyze') && method === 'POST') {
        return new Response(
          JSON.stringify({
            source_type: 'youtube_url',
            target: 'https://www.youtube.com/watch?v=P0sOl8K4jq0',
            video_title: 'Reality Show Vivo',
            duration_sec: 1200.0,
            thumbnail_url: null,
            matched_profile_id: null,
            matched_profile_name: null,
            suggested_profile_name: 'Reality Show Vivo',
            suggested_keywords: ['reality', 'show'],
            is_hybrid_multicategory: false,
            analysis_mode: 'remote_metadata',
            analysis_summary: 'Configura la escena base para este enlace remoto.',
            category_rules: [
              {
                rule_id: 'scene_1',
                category: 'auto',
                scene_label: 'Escena Principal',
                detected_share_pct: 100,
                layout_mode: 'auto',
                subtitle_preset: 'hormozi_pop',
                subtitle_position: 'auto',
                cam_overlay_pos: 'top_right',
                custom_cam_box_norm: null,
                custom_content_box_norm: null,
                custom_boxes_manual: false,
                frame_url: null,
                sample_timestamp_sec: 30.0,
              },
            ],
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/scene/detect') && method === 'POST') {
        const body = JSON.parse(String(init?.body || '{}')) as Record<string, unknown>;
        sceneDetectPayloads.push(body);
        return new Response(
          JSON.stringify({
            video_filename: '__yt_demo.mp4',
            resolution: '1280x720',
            width: 1280,
            height: 720,
            detected_layout: 'reality_multicam',
            faces_detected: 2,
            cam_box_norm: [0.08, 0.12, 0.35, 0.72],
            content_box_norm: [0.1, 0.05, 0.8, 0.9],
            frame_url: '/api/media/scene-frame?video_filename=__yt_demo.mp4',
          }),
          { status: 200 }
        );
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Pegar URL de YouTube \/ LIVE/i })).toBeInTheDocument();
    });

    expect(document.getElementById('source-type-select')).toBeNull();
    expect(document.getElementById('inbox-video-select')).toBeNull();

    await user.click(screen.getByRole('button', { name: /Pegar URL de YouTube \/ LIVE/i }));

    const urlInput = screen.getByLabelText(/URL de YouTube, Twitch o Kick/i) as HTMLInputElement;
    await user.type(urlInput, 'https://www.youtube.com/watch?v=P0sOl8K4jq0');

    await user.click(screen.getByRole('button', { name: /^Generar$/i }));

    const modal = await screen.findByTestId('preflight-analysis-modal');
    const detectBtn = screen.getByRole('button', { name: /Detectar Escena & Studio/i }) as HTMLButtonElement;
    expect(detectBtn).not.toBeDisabled();
    expect(detectBtn.className).toContain('h-10');

    await user.click(detectBtn);

    await waitFor(() => {
      expect(screen.getByTestId('studio-preview-9-16')).toBeInTheDocument();
    });

    expect(sceneDetectPayloads.length).toBe(1);
    expect(sceneDetectPayloads[0]).toMatchObject({
      source_type: 'youtube_url',
      video_filename: null,
      youtube_url: 'https://www.youtube.com/watch?v=P0sOl8K4jq0',
      timestamp_sec: 30.0,
    });

    const modalButtons = modal.querySelectorAll('button');
    modalButtons.forEach((btn) => {
      expect(btn.className).toContain('h-10');
    });
  });

  it('permite elegir cualquier punto de la línea de tiempo en el Estudio Interactivo, ver el recorte 9:16 real por escena y conservar encuadre manual en fullscreen o gameplay', async () => {
    const user = userEvent.setup();
    const sceneDetectCalls: Array<Record<string, unknown>> = [];
    const processCalls: Array<Record<string, unknown>> = [];

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method || 'GET').toUpperCase();

      if (url.endsWith('/api/inbox')) {
        return new Response(JSON.stringify(mockInboxPayload), { status: 200 });
      }
      if (url.endsWith('/api/shorts')) {
        return new Response(JSON.stringify({ total: 0, shorts: [] }), { status: 200 });
      }
      if (url.endsWith('/api/queues')) {
        return new Response(JSON.stringify(mockQueuesPayload), { status: 200 });
      }
      if (url.endsWith('/api/content-profiles')) {
        return new Response(JSON.stringify({ profiles: [] }), { status: 200 });
      }
      if (url.endsWith('/api/subtitles/presets')) {
        return new Response(
          JSON.stringify({
            presets: [{ id: 'hormozi_pop', name: 'Hormozi Pop', description: 'Pop amarillo.' }],
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/pipeline/candidates')) {
        return new Response(JSON.stringify({ video_filename: null, candidates: [] }), { status: 200 });
      }
      if (url.endsWith('/api/pipeline/pre-analyze') && method === 'POST') {
        return new Response(
          JSON.stringify({
            source_type: 'youtube_url',
            target: 'https://www.youtube.com/watch?v=TimelineFree916',
            video_title: 'Directo Largo Multi Escena',
            duration_sec: 1800.0,
            thumbnail_url: null,
            matched_profile_id: null,
            matched_profile_name: null,
            suggested_profile_name: 'Directo Largo',
            suggested_keywords: ['directo', 'largo'],
            is_hybrid_multicategory: true,
            analysis_mode: 'remote_metadata',
            analysis_summary: '2 escenas detectadas.',
            category_rules: [
              {
                rule_id: 'scene_1',
                category: 'auto',
                scene_label: 'Charla Full Cam',
                detected_share_pct: 40,
                layout_mode: 'fullscreen',
                subtitle_preset: 'hormozi_pop',
                subtitle_position: 'bottom',
                cam_overlay_pos: 'top_right',
                custom_cam_box_norm: null,
                custom_content_box_norm: null,
                custom_boxes_manual: false,
                frame_url: null,
                sample_timestamp_sec: 120.0,
              },
              {
                rule_id: 'scene_2',
                category: 'auto',
                scene_label: 'Gameplay + Cámara',
                detected_share_pct: 60,
                layout_mode: 'gaming_hud',
                subtitle_preset: 'hormozi_pop',
                subtitle_position: 'center',
                cam_overlay_pos: 'top_right',
                custom_cam_box_norm: null,
                custom_content_box_norm: null,
                custom_boxes_manual: false,
                frame_url: null,
                sample_timestamp_sec: 900.0,
              },
            ],
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/scene/detect') && method === 'POST') {
        const body = JSON.parse(String(init?.body || '{}')) as Record<string, unknown>;
        sceneDetectCalls.push(body);
        const ts = Number(body.timestamp_sec ?? 120);
        const tag = `t${Math.round(ts * 10)}`;
        return new Response(
          JSON.stringify({
            video_filename: `__yt_tl_${tag}.jpg`,
            resolution: '1280x720',
            width: 1280,
            height: 720,
            detected_layout: ts >= 850 ? 'gaming_hud' : 'fullscreen',
            faces_detected: 1,
            cam_box_norm: ts >= 850 ? [0.04, 0.62, 0.24, 0.32] : [0.3, 0.1, 0.4, 0.8],
            content_box_norm: ts >= 850 ? [0.28, 0.04, 0.7, 0.92] : [0.22, 0.0, 0.56, 1.0],
            frame_url: `/api/media/scene-frame?video_filename=__yt_tl_${tag}.jpg`,
            timestamp_sec: ts,
            duration_sec: 1800.0,
            frame_source: 'video_stream',
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/pipeline/process') && method === 'POST') {
        const body = JSON.parse(String(init?.body || '{}')) as Record<string, unknown>;
        processCalls.push(body);
        return new Response(
          JSON.stringify({
            job_id: 'job_timeline_ok',
            status: 'STARTED',
            target: 'Directo Largo Multi Escena',
            settings_applied: mockInboxPayload.settings,
          }),
          { status: 200 }
        );
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Pegar URL de YouTube \/ LIVE/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /Pegar URL de YouTube \/ LIVE/i }));
    await user.type(
      screen.getByLabelText(/URL de YouTube, Twitch o Kick/i),
      'https://www.youtube.com/watch?v=TimelineFree916'
    );
    await user.click(screen.getByRole('button', { name: /^Generar$/i }));

    const modal = await screen.findByTestId('preflight-analysis-modal');
    await user.click(screen.getByRole('button', { name: /Detectar Escena & Studio/i }));

    const studioPreview = await screen.findByTestId('studio-preview-9-16');
    expect(studioPreview).toBeInTheDocument();
    expect(screen.getByLabelText(/Línea de tiempo del video/i)).toBeInTheDocument();

    const tsInput = screen.getByLabelText(/Minuto o segundo del video/i) as HTMLInputElement;
    await user.clear(tsInput);
    await user.type(tsInput, '12:30');
    await user.click(screen.getByRole('button', { name: /Capturar Fotograma/i }));

    await waitFor(() => {
      expect(sceneDetectCalls.length).toBe(2);
    });
    expect(sceneDetectCalls[1].timestamp_sec).toBe(750);

    await waitFor(() => {
      const liveCam = studioPreview.querySelector('[data-testid="live-crop-cam"]') as HTMLImageElement | null;
      expect(liveCam).not.toBeNull();
      expect(liveCam?.getAttribute('src')).toContain('__yt_tl_t7500.jpg');
    });

    await user.click(screen.getByRole('button', { name: /Fijar Encuadre Manual/i }));

    // Pasar a escena 2 y detectar su propio fotograma en el minuto 15:00 (900s)
    await user.click(screen.getByRole('button', { name: /Configurar Escena 2/i }));
    await user.click(screen.getByRole('button', { name: /Detectar Escena & Studio/i }));

    await waitFor(() => {
      expect(sceneDetectCalls.length).toBe(3);
      const studioImg = screen.getByAltText(/Fotograma 16:9/i) as HTMLImageElement;
      expect(studioImg.getAttribute('src')).toContain('__yt_tl_t9000.jpg');
    });
    const studioPreviewDual = screen.getByTestId('studio-preview-9-16');
    expect(studioPreviewDual.querySelector('[data-testid="live-crop-cam"]')).not.toBeNull();
    expect(studioPreviewDual.querySelector('[data-testid="live-crop-content"]')).not.toBeNull();

    // Regresar a escena 1: debe conservar su propio fotograma (t7500) y encuadre manual
    await user.click(screen.getByRole('button', { name: /Configurar Escena 1/i }));
    await waitFor(() => {
      const studioImgBack = screen.getByAltText(/Fotograma 16:9/i) as HTMLImageElement;
      expect(studioImgBack.getAttribute('src')).toContain('__yt_tl_t7500.jpg');
    });

    const modalButtons = modal.querySelectorAll('button');
    modalButtons.forEach((btn) => {
      expect(btn.className).toContain('h-10');
    });

    await user.click(screen.getByRole('button', { name: /Confirmar y Generar Shorts/i }));
    await waitFor(() => {
      expect(processCalls.length).toBe(1);
    });
    const sentRules = processCalls[0].category_rules as Array<Record<string, unknown>>;
    expect(sentRules[0].layout_mode).toBe('fullscreen');
    expect(sentRules[0].custom_boxes_manual).toBe(true);
    expect(sentRules[0].custom_cam_box_norm).toEqual([0.3, 0.1, 0.4, 0.8]);
    expect(sentRules[0].sample_timestamp_sec).toBe(750);
  });

  it('ShortCard renderiza <video> con playsInline + preload metadata y remonta al cambiar video_url o cacheVersion', () => {
    const baseItem = {
      ...mockShortsPayload.shorts[0],
      tier: 'Oro' as const,
      social_statuses: undefined,
    };
    const typedPipelineStatus: PipelineStatus = {
      ...mockInboxPayload.pipeline_status,
      status: 'IDLE',
      source_type: 'inbox',
    };

    const { container, rerender } = render(
      <ShortCard
        item={baseItem}
        index={0}
        cacheVersion={1}
        scheduleValue="2026-11-15T14:00"
        queues={mockQueuesPayload}
        pipelineStatus={typedPipelineStatus}
        isBusy={false}
        onScheduleValueChange={vi.fn()}
        onScheduleSingle={vi.fn()}
        onOpenLayoutEditor={vi.fn()}
        onCancelSingle={vi.fn()}
        onDoubleClickVideo={vi.fn()}
      />
    );

    const firstVideo = container.querySelector('video') as HTMLVideoElement | null;
    expect(firstVideo).not.toBeNull();
    expect(firstVideo?.getAttribute('preload')).toBe('metadata');
    expect(firstVideo?.hasAttribute('playsinline')).toBe(true);
    expect(firstVideo?.getAttribute('src')).toContain('?v=1');

    rerender(
      <ShortCard
        item={baseItem}
        index={0}
        cacheVersion={2}
        scheduleValue="2026-11-15T14:00"
        queues={mockQueuesPayload}
        pipelineStatus={typedPipelineStatus}
        isBusy={false}
        onScheduleValueChange={vi.fn()}
        onScheduleSingle={vi.fn()}
        onOpenLayoutEditor={vi.fn()}
        onCancelSingle={vi.fn()}
        onDoubleClickVideo={vi.fn()}
      />
    );

    const secondVideo = container.querySelector('video') as HTMLVideoElement | null;
    expect(secondVideo).not.toBeNull();
    expect(secondVideo).not.toBe(firstVideo);
    expect(secondVideo?.getAttribute('src')).toContain('?v=2');
  });

  it('gestiona pestaña Cuentas & APIs por categoría, cambia categorías por Short y recorta/alarga duración en Studio', async () => {
    const user = userEvent.setup();
    const putSocialPayloads: Array<Record<string, unknown>> = [];
    const categoryPatchPayloads: Array<Record<string, unknown>> = [];
    const rerenderPayloads: Array<Record<string, unknown>> = [];
    const verifyPlatforms: string[] = [];

    const mockSocialHub = {
      categories: {
        principales: {
          key: 'principales',
          label: 'Cuentas Principales',
          description: 'Cuentas marca principal',
          topic_keywords: ['exclusiva', 'principal'],
          accounts: [
            {
              id: 'yt_main',
              platform: 'youtube',
              handle: '@CreadorStudio',
              display_name: 'CreadorStudio YT',
              external_id: '',
              enabled: true,
            },
          ],
        },
        gaming: {
          key: 'gaming',
          label: 'Cuentas Gaming',
          description: 'Canal Gaming',
          topic_keywords: ['juego', 'gaming'],
          accounts: [
            {
              id: 'ig_gaming',
              platform: 'instagram',
              handle: '@creador_gaming',
              display_name: 'Creador Gaming IG',
              external_id: '900000000000001',
              enabled: true,
            },
            {
              id: 'tt_gaming',
              platform: 'tiktok',
              handle: '@CreadorStudiogaming',
              display_name: 'Creador Gaming TT',
              external_id: '',
              enabled: true,
            },
          ],
        },
        clipping: {
          key: 'clipping',
          label: 'Cuentas Clipping',
          description: 'Red de clips virales',
          topic_keywords: ['clip', 'debate'],
          accounts: [
            {
              id: 'fb_clip',
              platform: 'facebook',
              handle: 'Creador Short',
              display_name: 'FB Short',
              external_id: '900000000000012',
              enabled: true,
            },
          ],
        },
      },
      api_settings: {
        youtube: { client_id: 'yt-client', client_secret: '••••1234', default_category_id: '22', has_token: true },
        instagram: { app_id: 'meta-app', app_secret: '', access_token: '••••5678', business_id: '818', graph_version: 'v21.0' },
        tiktok: { client_key: 'tk-key', client_secret: '••••9012', access_token: '', redirect_uri: 'http://localhost:3456/callback/', publish_mode: 'DIRECT_POST' },
        facebook: { app_id: 'meta-app', page_access_token: '••••5678', graph_version: 'v21.0' },
      },
    };

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : input.toString();
      const method = (init?.method || 'GET').toUpperCase();

      if (url.endsWith('/api/inbox')) {
        return new Response(JSON.stringify(mockInboxPayload), { status: 200 });
      }
      if (url.endsWith('/api/shorts')) {
        return new Response(
          JSON.stringify({
            total: 1,
            shorts: [
              {
                ...mockShortsPayload.shorts[0],
                eligible_for_youtube: true,
                duration_sec: 45,
                account_categories: ['gaming'],
              },
            ],
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/queues')) {
        return new Response(JSON.stringify({ ...mockQueuesPayload, facebook_queue: [] }), { status: 200 });
      }
      if (url.endsWith('/api/content-profiles')) {
        return new Response(JSON.stringify({ profiles: [] }), { status: 200 });
      }
      if (url.endsWith('/api/analytics/categories')) {
        return new Response(JSON.stringify({ categories: [] }), { status: 200 });
      }
      if (url.endsWith('/api/subtitles/presets')) {
        return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      }
      if (url.endsWith('/api/layout-presets')) {
        return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      }
      if (url.endsWith('/api/pipeline/candidates')) {
        return new Response(JSON.stringify({ video_filename: null, candidates: [] }), { status: 200 });
      }
      if (url.endsWith('/api/social-accounts') && method === 'GET') {
        return new Response(JSON.stringify(mockSocialHub), { status: 200 });
      }
      if (url.endsWith('/api/social-accounts') && method === 'PUT') {
        const body = JSON.parse(String(init?.body || '{}')) as Record<string, unknown>;
        putSocialPayloads.push(body);
        return new Response(JSON.stringify(body), { status: 200 });
      }
      if (url.endsWith('/api/social-accounts/verify') && method === 'POST') {
        const body = JSON.parse(String(init?.body || '{}')) as { platform: string };
        verifyPlatforms.push(body.platform);
        return new Response(
          JSON.stringify({ platform: body.platform, connected: true, status_label: 'Conectado', detail: 'Token OK' }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/shorts/categories') && method === 'POST') {
        const body = JSON.parse(String(init?.body || '{}')) as Record<string, unknown>;
        categoryPatchPayloads.push(body);
        return new Response(
          JSON.stringify({
            updated: true,
            short: {
              ...mockShortsPayload.shorts[0],
              eligible_for_youtube: true,
              account_categories: body.account_categories,
            },
            shorts: [
              {
                ...mockShortsPayload.shorts[0],
                eligible_for_youtube: true,
                account_categories: body.account_categories,
              },
            ],
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/shorts/scene-detect') && method === 'POST') {
        return new Response(
          JSON.stringify({
            short_rel_path: 'CreadorStudio_LIVE_Demo/CreadorStudio_01_Oro_94pts.mp4',
            frame_url: '/api/media/short-scene-frame?short_rel_path=test',
            edit_media_url: '/api/media/short-edit-source/CreadorStudio_LIVE_Demo/CreadorStudio_01_Oro_94pts.mp4',
            resolution: '1920x1080',
            faces_detected: 1,
            has_source_16_9: true,
            detected_layout: 'fullscreen',
            current_layout: 'fullscreen',
            cam_box_norm: [0.25, 0.05, 0.5, 0.9],
            content_box_norm: [0.0, 0.0, 1.0, 1.0],
            subtitle_preset: 'hormozi_pop',
            subtitle_position: 'bottom',
            cam_overlay_pos: 'top_right',
            trim_start_sec: 20,
            trim_end_sec: 65,
            min_trim_sec: 0,
            max_trim_sec: 95,
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/shorts/rerender') && method === 'POST') {
        const body = JSON.parse(String(init?.body || '{}')) as Record<string, unknown>;
        rerenderPayloads.push(body);
        return new Response(
          JSON.stringify({
            rerendered: true,
            short: { ...mockShortsPayload.shorts[0], eligible_for_youtube: true, duration_sec: 55 },
            shorts: [{ ...mockShortsPayload.shorts[0], eligible_for_youtube: true, duration_sec: 55 }],
          }),
          { status: 200 }
        );
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
    });

    render(<App />);

    // 1) Abrir pestaña Cuentas & APIs y verificar secciones + probar conexión + guardar
    const accountsTab = await screen.findByRole('tab', { name: /Cuentas & APIs/i });
    await user.click(accountsTab);

    expect(await screen.findByRole('heading', { name: /Cuentas Principales/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Cuentas Gaming/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Cuentas Clipping/i })).toBeInTheDocument();

    const verifyBtns = screen.getAllByRole('button', { name: /Probar Conexión/i });
    expect(verifyBtns.length).toBeGreaterThanOrEqual(4);
    await user.click(verifyBtns[0]);
    await waitFor(() => {
      expect(verifyPlatforms.length).toBe(1);
    });

    await user.click(screen.getByRole('button', { name: /Guardar Configuración de Cuentas y APIs/i }));
    await waitFor(() => {
      expect(putSocialPayloads.length).toBe(1);
    });

    // 2) Volver a Estudio de Shorts, mostrar categorías/redes, cambiar categoría y alargar duración (+5s fin)
    await user.click(screen.getByRole('tab', { name: /Estudio de Shorts/i }));
    await user.click(
      await screen.findByRole('button', {
        name: /Mostrar u ocultar categorías y estado de redes/i,
      })
    );
    const clipChip = await screen.findByRole('button', {
      name: /Categoría Clipping para CreadorStudio_01_Oro_94pts\.mp4/i,
    });
    await user.click(clipChip);
    await waitFor(() => {
      expect(categoryPatchPayloads.length).toBe(1);
      expect(categoryPatchPayloads[0].account_categories).toEqual(['gaming', 'clipping']);
    });

    const editBtn = screen.getByRole('button', {
      name: /Editar Short CreadorStudio_01_Oro_94pts\.mp4/i,
    });
    await user.click(editBtn);

    const plus5EndBtn = await screen.findByRole('button', { name: /Alargar fin \+5s/i });
    await user.click(plus5EndBtn);
    await user.click(screen.getByRole('button', { name: /Guardar y Re-renderizar Short/i }));

    await waitFor(() => {
      expect(rerenderPayloads.length).toBe(1);
      expect(rerenderPayloads[0].trim_start_sec).toBe(20);
      expect(rerenderPayloads[0].trim_end_sec).toBe(70);
    });
  });

  it('incluye categoría OMETV precargada y permite crear nuevas categorías de cuentas con controles h-10', async () => {
    const user = userEvent.setup();
    const createdPayloads: Array<Record<string, unknown>> = [];
    const hubState = {
      categories: {
        principales: {
          key: 'principales',
          label: 'Cuentas Principales',
          description: 'Marca personal',
          topic_keywords: ['principal'],
          is_custom: false,
          accounts: [],
        },
        gaming: {
          key: 'gaming',
          label: 'Cuentas Gaming',
          description: 'Gameplays',
          topic_keywords: ['gaming'],
          is_custom: false,
          accounts: [],
        },
        clipping: {
          key: 'clipping',
          label: 'Cuentas Clipping',
          description: 'Clips virales',
          topic_keywords: ['clip'],
          is_custom: false,
          accounts: [],
        },
        ometv: {
          key: 'ometv',
          label: 'Cuentas OMETV',
          description: 'OmeTV clips',
          topic_keywords: ['ometv'],
          is_custom: false,
          accounts: [
            {
              id: 'ig_ometv',
              platform: 'instagram',
              handle: '@creador_ometv',
              display_name: 'Creador OMETV',
              external_id: '900000000000002',
              enabled: true,
            },
          ],
        },
      } as Record<string, unknown>,
      api_settings: {
        youtube: { client_id: '', client_secret: '', default_category_id: '22' },
        instagram: { app_id: '', app_secret: '', access_token: '', business_id: '', graph_version: 'v21.0' },
        tiktok: { client_key: '', client_secret: '', access_token: '', redirect_uri: '', publish_mode: 'DIRECT_POST' },
        facebook: { app_id: '', page_access_token: '', graph_version: 'v21.0' },
      },
    };

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : input.toString();
      const method = (init?.method || 'GET').toUpperCase();

      if (url.endsWith('/api/inbox')) return new Response(JSON.stringify(mockInboxPayload), { status: 200 });
      if (url.endsWith('/api/shorts')) return new Response(JSON.stringify(mockShortsPayload), { status: 200 });
      if (url.endsWith('/api/queues')) return new Response(JSON.stringify(mockQueuesPayload), { status: 200 });
      if (url.endsWith('/api/content-profiles')) return new Response(JSON.stringify({ profiles: [] }), { status: 200 });
      if (url.endsWith('/api/analytics/categories')) return new Response(JSON.stringify({ categories: [] }), { status: 200 });
      if (url.endsWith('/api/subtitles/presets')) return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      if (url.endsWith('/api/layout-presets')) return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      if (url.endsWith('/api/pipeline/candidates')) return new Response(JSON.stringify({ video_filename: null, candidates: [] }), { status: 200 });
      if (url.endsWith('/api/social-accounts') && method === 'GET') {
        return new Response(JSON.stringify(hubState), { status: 200 });
      }
      if (url.endsWith('/api/social-accounts/categories') && method === 'POST') {
        const body = JSON.parse(String(init?.body || '{}')) as {
          label: string;
          topic_keywords?: string[];
        };
        createdPayloads.push(body);
        const created = {
          key: 'podcast',
          label: body.label,
          description: '',
          topic_keywords: body.topic_keywords || [],
          accounts: [],
          is_custom: true,
        };
        hubState.categories.podcast = created;
        return new Response(JSON.stringify({ created, ...hubState }), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
    });

    render(<App />);

    // Verificar filtro OMETV y chip en galería tras activar vista de categorías y redes
    expect(await screen.findByRole('button', { name: /^OMETV \(/i })).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /Categoría OMETV para CreadorStudio_01_Oro_94pts\.mp4/i })
    ).not.toBeInTheDocument();
    await user.click(
      screen.getByRole('button', { name: /Mostrar u ocultar categorías y estado de redes/i })
    );
    expect(
      screen.getByRole('button', { name: /Categoría OMETV para CreadorStudio_01_Oro_94pts\.mp4/i })
    ).toBeInTheDocument();

    // Abrir Cuentas & APIs -> verificar OMETV y crear categoría nueva
    await user.click(screen.getByRole('tab', { name: /Cuentas & APIs/i }));
    const ometvTabBtn = await screen.findByRole('button', { name: /Cuentas OMETV/i });
    await user.click(ometvTabBtn);
    expect(screen.getByDisplayValue('@creador_ometv')).toBeInTheDocument();

    const newCatNameInput = screen.getByLabelText(/Nombre de nueva categoría/i);
    const newCatKeywordsInput = screen.getByLabelText(/Palabras clave de nueva categoría/i);
    await user.type(newCatNameInput, 'Cuentas Podcast');
    await user.type(newCatKeywordsInput, 'tertulia, invitado');
    await user.click(screen.getByRole('button', { name: /Crear Categoría/i }));

    await waitFor(() => {
      expect(createdPayloads.length).toBe(1);
      expect(screen.getByRole('button', { name: /Cuentas Podcast/i })).toBeInTheDocument();
    });

    document.querySelectorAll('button').forEach((btn) => {
      expect(btn.className).toContain('h-10');
    });

    // Regresar al estudio y confirmar que aparece el filtro dinámico de Podcast
    await user.click(screen.getByRole('tab', { name: /Estudio de Shorts/i }));
    expect(await screen.findByRole('button', { name: /^Podcast \(/i })).toBeInTheDocument();
  });

  it('inicia con categorías y estado de redes ocultos por defecto, permite alternarlos y nombra proyectos por video + fecha', async () => {
    const user = userEvent.setup();
    window.history.pushState({}, '', '/?project=Proyecto_2026-11-15_2230');
    const renamePayloads: Array<Record<string, unknown>> = [];
    const expectedSlug = 'Partida_Fortnite_2026-11-15';

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : input.toString();
      const method = (init?.method || 'GET').toUpperCase();

      if (url.includes('/api/inbox')) {
        return new Response(
          JSON.stringify({
            ...mockInboxPayload,
            project_id: url.includes(expectedSlug) ? expectedSlug : 'Proyecto_2026-11-15_2230',
            project_name: url.includes(expectedSlug) ? expectedSlug : 'Proyecto_2026-11-15_2230',
            pipeline_status: {
              ...mockInboxPayload.pipeline_status,
              project_id: url.includes(expectedSlug) ? expectedSlug : 'Proyecto_2026-11-15_2230',
              project_name: url.includes(expectedSlug) ? expectedSlug : 'Proyecto_2026-11-15_2230',
              status: 'IDLE',
              current_video: null,
            },
          }),
          { status: 200 }
        );
      }
      if (url.includes('/api/shorts')) {
        return new Response(JSON.stringify(mockShortsPayload), { status: 200 });
      }
      if (url.endsWith('/api/queues')) {
        return new Response(JSON.stringify(mockQueuesPayload), { status: 200 });
      }
      if (url.endsWith('/api/content-profiles')) {
        return new Response(JSON.stringify({ profiles: [] }), { status: 200 });
      }
      if (url.endsWith('/api/analytics/categories')) {
        return new Response(JSON.stringify({ categories: [] }), { status: 200 });
      }
      if (url.endsWith('/api/subtitles/presets')) {
        return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      }
      if (url.endsWith('/api/layout-presets')) {
        return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      }
      if (url.includes('/api/pipeline/candidates')) {
        return new Response(JSON.stringify({ video_filename: null, candidates: [] }), { status: 200 });
      }
      if (url.includes('/api/local-video/upload') && method === 'POST') {
        return new Response(
          JSON.stringify({
            cancelled: false,
            file_path: 'Partida_Fortnite.mp4',
            file_name: 'Partida Fortnite.mp4',
            size_mb: 12.5,
          }),
          { status: 200 }
        );
      }
      if (url.includes('/api/project/rename') && method === 'POST') {
        const body = JSON.parse(String(init?.body || '{}')) as Record<string, unknown>;
        renamePayloads.push(body);
        return new Response(
          JSON.stringify({
            renamed: true,
            old_project_id: 'Proyecto_2026-11-15_2230',
            project_id: expectedSlug,
            project_name: expectedSlug,
            project_url: `/?project=${expectedSlug}`,
            pipeline_status: {
              ...mockInboxPayload.pipeline_status,
              project_id: expectedSlug,
              project_name: expectedSlug,
              status: 'IDLE',
              current_video: null,
            },
          }),
          { status: 200 }
        );
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
    });

    render(<App />);

    // 1) Categorías y barras de estado por red social inician ocultas por defecto
    expect(
      await screen.findByAltText(/Miniatura de CreadorStudio_01_Oro_94pts\.mp4/i)
    ).toBeInTheDocument();
    expect(screen.queryByTestId('social-status-youtube-CreadorStudio_01_Oro_94pts.mp4')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /Categoría Gaming para CreadorStudio_01_Oro_94pts\.mp4/i })
    ).not.toBeInTheDocument();

    const toggleBtn = screen.getByRole('button', {
      name: /Mostrar u ocultar categorías y estado de redes/i,
    });
    expect(toggleBtn).toHaveAttribute('aria-pressed', 'false');
    expect(toggleBtn.className).toContain('h-10');

    await user.click(toggleBtn);
    expect(toggleBtn).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('social-status-youtube-CreadorStudio_01_Oro_94pts.mp4')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Categoría Gaming para CreadorStudio_01_Oro_94pts\.mp4/i })
    ).toBeInTheDocument();

    await user.click(toggleBtn);
    expect(toggleBtn).toHaveAttribute('aria-pressed', 'false');
    expect(screen.queryByTestId('social-status-youtube-CreadorStudio_01_Oro_94pts.mp4')).not.toBeInTheDocument();

    // 2) Al seleccionar un video local en proyecto nuevo sin video, se renombra a Video + Fecha
    expect(screen.getByTestId('active-project-badge')).toHaveTextContent(/Proyecto_2026-11-15_2230/);
    const localFileInput = screen.getByTestId('local-video-file-input') as HTMLInputElement;
    const videoFile = new File([new Uint8Array([0, 1, 2, 3])], 'Partida Fortnite.mp4', { type: 'video/mp4' });
    await user.upload(localFileInput, videoFile);

    await waitFor(() => {
      expect(renamePayloads.length).toBeGreaterThanOrEqual(1);
      expect(screen.getByTestId('active-project-badge')).toHaveTextContent(expectedSlug);
    });
    expect(window.location.search).toContain(`project=${expectedSlug}`);

    document.querySelectorAll('button').forEach((btn) => {
      expect(btn.className).toContain('h-10');
    });
  });

  it('remueve subida automática a YouTube, modal x4 y etiquetas innecesarias, y descarga todos o solo los Shorts seleccionados', async () => {
    const user = userEvent.setup();
    window.history.pushState({}, '', '/');
    const capturedDownloadBodies: Array<Record<string, unknown>> = [];

    const origCreateObjUrl = URL.createObjectURL;
    const origRevokeObjUrl = URL.revokeObjectURL;
    URL.createObjectURL = vi.fn(() => 'blob:http://localhost/shorts-bundle');
    URL.revokeObjectURL = vi.fn();

    try {
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
        const url = typeof input === 'string' ? input : input.toString();
        const method = (init?.method || 'GET').toUpperCase();

        if (url.includes('/api/inbox')) {
          return new Response(JSON.stringify(mockInboxPayload), { status: 200 });
        }
        if (url.includes('/api/shorts/download-bundle') && method === 'POST') {
          const body = JSON.parse(String(init?.body || '{}')) as Record<string, unknown>;
          capturedDownloadBodies.push(body);
          return new Response(new Uint8Array([80, 75, 3, 4]), {
            status: 200,
            headers: {
              'Content-Type': 'application/zip',
              'Content-Disposition': 'attachment; filename="Shorts.zip"',
            },
          });
        }
        if (url.includes('/api/shorts')) {
          return new Response(JSON.stringify(mockShortsPayload), { status: 200 });
        }
        if (url.endsWith('/api/queues')) {
          return new Response(JSON.stringify(mockQueuesPayload), { status: 200 });
        }
        if (url.endsWith('/api/content-profiles')) {
          return new Response(JSON.stringify({ profiles: [] }), { status: 200 });
        }
        if (url.endsWith('/api/analytics/categories')) {
          return new Response(JSON.stringify({ categories: [] }), { status: 200 });
        }
        if (url.endsWith('/api/subtitles/presets')) {
          return new Response(JSON.stringify({ presets: [] }), { status: 200 });
        }
        if (url.endsWith('/api/layout-presets')) {
          return new Response(JSON.stringify({ presets: [] }), { status: 200 });
        }
        if (url.includes('/api/pipeline/candidates')) {
          return new Response(JSON.stringify({ video_filename: null, candidates: [] }), { status: 200 });
        }
        if (url.endsWith('/api/social-accounts')) {
          return new Response(JSON.stringify({ categories: {}, api_settings: {} }), { status: 200 });
        }
        return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
      });

      render(<App />);
      await screen.findByTestId('shorts-grid-4col');

      // Subida automática a YouTube, modal x4 y etiquetas decorativas eliminadas
      expect(document.getElementById('auto-upload-switch')).toBeNull();
      expect(screen.queryByRole('button', { name: /Ver en Modal/i })).not.toBeInTheDocument();
      expect(screen.queryByText(/Modo Local-Ready/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/Auto-Subida Multi-Red/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/Multi-Red Activo/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/Daemon:/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/Estado:/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/Estudio Dark 9:16/i)).not.toBeInTheDocument();

      // Descargar todos cuando no hay selección manual
      const downloadBtn = screen.getByRole('button', { name: /Descargar Shorts/i });
      expect(downloadBtn).toHaveTextContent(/Descargar Todos \(2\)/i);
      await user.click(downloadBtn);

      await waitFor(() => {
        expect(capturedDownloadBodies.length).toBe(1);
      });
      expect((capturedDownloadBodies[0].short_rel_paths as string[]).length).toBe(2);

      // Seleccionar un Short -> el botón cambia a Descargar Seleccionados (1)
      const check2 = screen.getByRole('checkbox', {
        name: /Seleccionar Short CreadorStudio_02_Plata_78pts\.mp4/i,
      }) as HTMLInputElement;
      await user.click(check2);
      expect(check2.checked).toBe(true);
      expect(downloadBtn).toHaveTextContent(/Descargar Seleccionados \(1\)/i);

      await user.click(downloadBtn);
      await waitFor(() => {
        expect(capturedDownloadBodies.length).toBe(2);
      });
      expect(capturedDownloadBodies[1].short_rel_paths).toEqual([
        'CreadorStudio_LIVE_Demo/CreadorStudio_02_Plata_78pts.mp4',
      ]);

      // Botón Seleccionar todos / Limpiar selección
      const toggleAllBtn = screen.getByRole('button', {
        name: /Seleccionar o deseleccionar todos los Shorts visibles/i,
      });
      await user.click(toggleAllBtn);
      const check1 = screen.getByRole('checkbox', {
        name: /Seleccionar Short CreadorStudio_01_Oro_94pts\.mp4/i,
      }) as HTMLInputElement;
      expect(check1.checked).toBe(true);
      expect(check2.checked).toBe(true);
      expect(downloadBtn).toHaveTextContent(/Descargar Seleccionados \(2\)/i);

      await user.click(toggleAllBtn);
      expect(check1.checked).toBe(false);
      expect(check2.checked).toBe(false);
      expect(downloadBtn).toHaveTextContent(/Descargar Todos \(2\)/i);

      document.querySelectorAll('button').forEach((btn) => {
        expect(btn.className).toContain('h-10');
      });
    } finally {
      URL.createObjectURL = origCreateObjUrl;
      URL.revokeObjectURL = origRevokeObjUrl;
    }
  });

  it('opera la pestaña Directo en Vivo conectada a Perfiles de Contenido, telemetría en tiempo real y galería con controles h-10', async () => {
    const user = userEvent.setup();
    window.history.pushState({}, '', '/');
    const capturedStartBodies: Array<Record<string, unknown>> = [];
    let stopCalls = 0;
    let liveState: Record<string, unknown> = {
      project_id: 'default',
      status: 'IDLE',
      stream_url: '',
      stream_title: '',
      is_live_detected: false,
      profile_id: null,
      profile_name: 'Automático',
      chunk_duration_sec: 90,
      overlap_sec: 20,
      min_virality_score: 70,
      max_shorts_total: 12,
      segments_captured: 0,
      segments_analyzed: 0,
      shorts_generated: 0,
      phase_label: 'En espera',
      step_detail: 'Pega el enlace de un directo activo para extraer Shorts en tiempo real.',
      recent_clips: [],
    };

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : input.toString();
      const method = (init?.method || 'GET').toUpperCase();

      if (url.includes('/api/inbox')) return new Response(JSON.stringify(mockInboxPayload), { status: 200 });
      if (url.includes('/api/shorts')) return new Response(JSON.stringify(mockShortsPayload), { status: 200 });
      if (url.endsWith('/api/queues')) return new Response(JSON.stringify(mockQueuesPayload), { status: 200 });
      if (url.endsWith('/api/content-profiles')) {
        return new Response(
          JSON.stringify({
            profiles: [
              {
                id: 7,
                name: 'CreadorStudio Live Gaming',
                match_keywords: ['fortnite', 'twitch'],
                scenes: [],
              },
            ],
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/analytics/categories')) return new Response(JSON.stringify({ categories: [] }), { status: 200 });
      if (url.endsWith('/api/subtitles/presets')) return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      if (url.endsWith('/api/layout-presets')) return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      if (url.includes('/api/pipeline/candidates')) return new Response(JSON.stringify({ video_filename: null, candidates: [] }), { status: 200 });
      if (url.endsWith('/api/social-accounts')) return new Response(JSON.stringify({ categories: {}, api_settings: {} }), { status: 200 });
      if (url.includes('/api/live/status')) return new Response(JSON.stringify(liveState), { status: 200 });
      if (url.includes('/api/live/start') && method === 'POST') {
        const body = JSON.parse(String(init?.body || '{}')) as Record<string, unknown>;
        capturedStartBodies.push(body);
        liveState = {
          ...liveState,
          status: 'MONITORING',
          stream_url: body.stream_url,
          stream_title: 'DIRECTO FORTNITE FINAL',
          is_live_detected: true,
          profile_id: body.profile_id,
          profile_name: 'CreadorStudio Live Gaming',
          min_virality_score: body.min_virality_score,
          segments_captured: 3,
          segments_analyzed: 2,
          shorts_generated: 1,
          phase_label: 'Capturando bloque en vivo #4 (90s)',
          step_detail: 'Procesando stream activo en segundo plano...',
          recent_clips: [
            {
              filename: 'Live_01_Oro_91pts.mp4',
              hook_title: 'CLUTCH FINAL EN VIVO',
              virality_score: 91,
              tier: 'Oro',
              created_at: '01:05:00',
            },
          ],
        };
        return new Response(JSON.stringify(liveState), { status: 200 });
      }
      if (url.includes('/api/live/stop') && method === 'POST') {
        stopCalls += 1;
        liveState = {
          ...liveState,
          status: 'STOPPED',
          phase_label: 'Directo detenido',
          step_detail: 'Monitoreo en vivo finalizado.',
        };
        return new Response(JSON.stringify(liveState), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
    });

    render(<App />);
    await user.click(await screen.findByRole('tab', { name: /Directo en Vivo/i }));

    const urlInput = await screen.findByLabelText(/URL del Directo en Vivo/i);
    const profileSelect = screen.getByLabelText(/Perfil de Contenido en Vivo/i) as HTMLSelectElement;
    const minScoreInput = screen.getByLabelText(/Puntaje Mínimo/i) as HTMLInputElement;

    await user.type(urlInput, 'https://www.twitch.tv/creadorstudio');
    await user.selectOptions(profileSelect, '7');
    await user.clear(minScoreInput);
    await user.type(minScoreInput, '75');
    await user.click(screen.getByRole('button', { name: /Iniciar en Vivo/i }));

    await waitFor(() => {
      expect(capturedStartBodies.length).toBe(1);
      expect(screen.getByText('DIRECTO FORTNITE FINAL')).toBeInTheDocument();
      expect(screen.getByText('CLUTCH FINAL EN VIVO')).toBeInTheDocument();
    });

    expect(capturedStartBodies[0].stream_url).toBe('https://www.twitch.tv/creadorstudio');
    expect(capturedStartBodies[0].profile_id).toBe(7);
    expect(capturedStartBodies[0].min_virality_score).toBe(75);
    expect(screen.getByTestId('shorts-grid-4col')).toBeInTheDocument();

    const stopBtn = screen.getByRole('button', { name: /Detener Directo/i });
    await user.click(stopBtn);
    await waitFor(() => {
      expect(stopCalls).toBe(1);
      expect(screen.getByRole('button', { name: /Iniciar en Vivo/i })).toBeInTheDocument();
    });

    document.querySelectorAll('button').forEach((btn) => {
      expect(btn.className).toContain('h-10');
    });
  });

  it('muestra Autorizar OAuth en YouTube y reporta youtube_error sin bloquear Programar Fecha y Hora', async () => {
    const user = userEvent.setup();
    let ytAuthorizeCalls = 0;

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();
      const method = (init?.method || 'GET').toUpperCase();

      if (url.endsWith('/api/inbox')) {
        return new Response(JSON.stringify(mockInboxPayload), { status: 200 });
      }
      if (url.endsWith('/api/shorts')) {
        return new Response(JSON.stringify(mockShortsPayload), { status: 200 });
      }
      if (url.endsWith('/api/queues')) {
        return new Response(JSON.stringify(mockQueuesPayload), { status: 200 });
      }
      if (url.endsWith('/api/content-profiles')) {
        return new Response(JSON.stringify({ profiles: [] }), { status: 200 });
      }
      if (url.endsWith('/api/analytics/categories')) {
        return new Response(JSON.stringify({ categories: [] }), { status: 200 });
      }
      if (url.endsWith('/api/subtitles/presets')) {
        return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      }
      if (url.includes('/api/pipeline/candidates')) {
        return new Response(JSON.stringify({ video_filename: null, candidates: [] }), { status: 200 });
      }
      if (url.endsWith('/api/live/status')) {
        return new Response(JSON.stringify({ status: 'IDLE', recent_clips: [] }), { status: 200 });
      }
      if (url.endsWith('/api/social-accounts/youtube/authorize') && method === 'POST') {
        ytAuthorizeCalls += 1;
        return new Response(
          JSON.stringify({
            platform: 'youtube',
            connected: true,
            status_label: 'Conectado',
            detail: 'OAuth YouTube listo (token.json renovado).',
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/shorts/schedule') && method === 'POST') {
        return new Response(
          JSON.stringify({
            scheduled: true,
            scheduled_count: 2,
            youtube_uploaded_count: 0,
            youtube_error: 'Sesión OAuth de YouTube expirada. Pulsa Autorizar OAuth en Cuentas & APIs.',
            shorts: mockShortsPayload.shorts,
            summary: {
              total_shorts: 2,
              oro_count: 1,
              plata_count: 1,
              meh_count: 0,
              youtube_eligible_count: 2,
              youtube_uploaded_count: 0,
              requires_schedule_confirmation: false,
            },
          }),
          { status: 200 }
        );
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
    });

    render(<App />);

    // 1) Abrir modal de programación y confirmar con youtube_error: no bloquea botones, muestra aviso y expande barras
    const openSchedBtn = await screen.findByRole('button', {
      name: /Abrir Programación de Fecha y Hora/i,
    });
    await user.click(openSchedBtn);
    await user.click(
      await screen.findByRole('button', { name: /Confirmar Fecha y Hora y Subir a Redes/i })
    );

    await waitFor(() => {
      expect(screen.getByText(/Atención YouTube:.*Autorizar OAuth/i)).toBeInTheDocument();
      expect(screen.getByTestId('social-bars-CreadorStudio_01_Oro_94pts.mp4')).toBeInTheDocument();
    });
    expect(openSchedBtn).not.toBeDisabled();

    // 2) Ir a Cuentas & APIs y pulsar Autorizar OAuth en tarjeta de YouTube
    await user.click(screen.getByRole('tab', { name: /Cuentas & APIs/i }));
    const authBtn = await screen.findByRole('button', { name: /Autorizar OAuth/i });
    expect(authBtn.className).toContain('h-10');
    await user.click(authBtn);

    await waitFor(() => {
      expect(ytAuthorizeCalls).toBe(1);
      expect(
        screen.getAllByText(/OAuth YouTube listo \(token\.json renovado\)\./i).length
      ).toBeGreaterThanOrEqual(1);
    });

    document.querySelectorAll('button').forEach((btn) => {
      expect(btn.className).toContain('h-10');
    });
  });

  it('muestra En Borrador (App) para TikTok inbox, enlaces Ver ↗ en redes subidas y Conectar YouTube OAuth en alerta', async () => {
    const user = userEvent.setup();
    let ytAuthorizeCalls = 0;

    const shortWithStatuses = {
      ...mockShortsPayload.shorts[0],
      social_statuses: {
        youtube: {
          network: 'youtube' as const,
          state: 'error' as const,
          status_label: 'Error',
          detail: 'Sesión OAuth de YouTube expirada o sin autorizar (invalid_grant).',
          percent: 100,
          account: '@creadorstudio',
        },
        instagram: {
          network: 'instagram' as const,
          state: 'uploaded' as const,
          status_label: 'Subido',
          detail: '@creador_gaming · Subido',
          percent: 100,
          account: '@creador_gaming',
          permalink: 'https://www.instagram.com/reel/DfyPDgVAnAy/',
        },
        tiktok: {
          network: 'tiktok' as const,
          state: 'draft' as const,
          status_label: 'En Borrador (App)',
          detail: '@creador.gaming · Enviado a Bandeja TikTok (App) — falta publicar en la app',
          percent: 85,
          account: '@creador.gaming',
          permalink: null,
        },
        facebook: {
          network: 'facebook' as const,
          state: 'uploaded' as const,
          status_label: 'Subido',
          detail: 'Creador Gaming · Subido',
          percent: 100,
          account: 'Creador Gaming',
          permalink: 'https://www.facebook.com/reel/900000000000015/',
        },
      },
    };

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();
      const method = (init?.method || 'GET').toUpperCase();

      if (url.endsWith('/api/inbox')) {
        return new Response(JSON.stringify(mockInboxPayload), { status: 200 });
      }
      if (url.endsWith('/api/shorts')) {
        return new Response(
          JSON.stringify({
            total: 1,
            shorts: [shortWithStatuses],
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/queues')) {
        return new Response(JSON.stringify(mockQueuesPayload), { status: 200 });
      }
      if (url.endsWith('/api/content-profiles')) {
        return new Response(JSON.stringify({ profiles: [] }), { status: 200 });
      }
      if (url.endsWith('/api/analytics/categories')) {
        return new Response(JSON.stringify({ categories: [] }), { status: 200 });
      }
      if (url.endsWith('/api/subtitles/presets')) {
        return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      }
      if (url.includes('/api/pipeline/candidates')) {
        return new Response(JSON.stringify({ video_filename: null, candidates: [] }), { status: 200 });
      }
      if (url.endsWith('/api/live/status')) {
        return new Response(JSON.stringify({ status: 'IDLE', recent_clips: [] }), { status: 200 });
      }
      if (url.endsWith('/api/social-accounts/youtube/authorize') && method === 'POST') {
        ytAuthorizeCalls += 1;
        return new Response(
          JSON.stringify({
            platform: 'youtube',
            connected: true,
            status_label: 'Conectado',
            detail: 'OAuth YouTube listo (token.json renovado).',
            retried_youtube_slots: 1,
          }),
          { status: 200 }
        );
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
    });

    render(<App />);

    // Expandir barras de redes sociales y verificar banner automático por fallo OAuth de YouTube
    const toggleSocialBtn = await screen.findByRole('button', {
      name: /Mostrar u ocultar categorías y estado de redes/i,
    });
    await user.click(toggleSocialBtn);

    await waitFor(() => {
      expect(screen.getByText('En Borrador (App)')).toBeInTheDocument();
      const viewLinks = screen.getAllByRole('link', { name: /Ver ↗/i });
      expect(viewLinks).toHaveLength(2);
      expect(viewLinks.map((a) => a.getAttribute('href'))).toEqual([
        'https://www.instagram.com/reel/DfyPDgVAnAy/',
        'https://www.facebook.com/reel/900000000000015/',
      ]);
    });

    const connectYtBtn = await screen.findByRole('button', { name: /Conectar YouTube OAuth/i });
    expect(connectYtBtn.className).toContain('h-10');
    await user.click(connectYtBtn);

    await waitFor(() => {
      expect(ytAuthorizeCalls).toBe(1);
      expect(screen.getByText(/reintentando 1 subida\(s\)/i)).toBeInTheDocument();
    });

    document.querySelectorAll('button').forEach((btn) => {
      expect(btn.className).toContain('h-10');
    });
  });

  it('abre Google OAuth en el navegador sin bloquear la UI, muestra enlace directo de respaldo y completa auto-reintento al detectar oauth/status', async () => {
    const user = userEvent.setup();
    const expectedAuthUrl =
      'https://accounts.google.com/o/oauth2/auth?client_id=cid&redirect_uri=http%3A%2F%2Flocalhost%3A55555%2F';
    let oauthStatusCallCount = 0;

    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);

    const shortWithOAuthErr = {
      ...mockShortsPayload.shorts[0],
      social_statuses: {
        youtube: {
          network: 'youtube' as const,
          state: 'error' as const,
          status_label: 'Error',
          detail: 'Sesión OAuth de YouTube expirada o sin autorizar (invalid_grant).',
          percent: 100,
          account: '@creadorstudio',
        },
        instagram: {
          network: 'instagram' as const,
          state: 'pending' as const,
          status_label: 'Pendiente',
          detail: 'Pendiente',
          percent: 40,
          account: '@creador_gaming',
        },
        tiktok: {
          network: 'tiktok' as const,
          state: 'draft' as const,
          status_label: 'En Borrador (App)',
          detail: 'En bandeja',
          percent: 85,
          account: '@creador.gaming',
        },
        facebook: {
          network: 'facebook' as const,
          state: 'pending' as const,
          status_label: 'Pendiente',
          detail: 'Pendiente',
          percent: 40,
          account: 'Creador Gaming',
        },
      },
    };

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();
      const method = (init?.method || 'GET').toUpperCase();

      if (url.endsWith('/api/inbox')) {
        return new Response(JSON.stringify(mockInboxPayload), { status: 200 });
      }
      if (url.endsWith('/api/shorts')) {
        return new Response(
          JSON.stringify({
            total: 1,
            shorts: [shortWithOAuthErr],
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/queues')) {
        return new Response(JSON.stringify(mockQueuesPayload), { status: 200 });
      }
      if (url.endsWith('/api/content-profiles')) {
        return new Response(JSON.stringify({ profiles: [] }), { status: 200 });
      }
      if (url.endsWith('/api/analytics/categories')) {
        return new Response(JSON.stringify({ categories: [] }), { status: 200 });
      }
      if (url.endsWith('/api/subtitles/presets')) {
        return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      }
      if (url.includes('/api/pipeline/candidates')) {
        return new Response(JSON.stringify({ video_filename: null, candidates: [] }), { status: 200 });
      }
      if (url.endsWith('/api/live/status')) {
        return new Response(JSON.stringify({ status: 'IDLE', recent_clips: [] }), { status: 200 });
      }
      if (url.endsWith('/api/social-accounts/youtube/oauth/start') && method === 'POST') {
        return new Response(
          JSON.stringify({
            oauth_state: 'pending',
            platform: 'youtube',
            connected: false,
            status_label: 'Esperando confirmación en Google',
            detail: 'Completa el acceso en la pestaña de Google.',
            auth_url: expectedAuthUrl,
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/social-accounts/youtube/oauth/status')) {
        oauthStatusCallCount += 1;
        if (oauthStatusCallCount === 1) {
          return new Response(
            JSON.stringify({
              oauth_state: 'pending',
              platform: 'youtube',
              connected: false,
              status_label: 'Esperando confirmación en Google',
              detail: 'Completa el acceso en la pestaña de Google.',
              auth_url: expectedAuthUrl,
            }),
            { status: 200 }
          );
        }
        return new Response(
          JSON.stringify({
            oauth_state: 'completed',
            platform: 'youtube',
            connected: true,
            status_label: 'Conectado',
            detail: 'OAuth YouTube listo.',
            retried_youtube_slots: 2,
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/social-accounts/youtube/oauth/cancel') && method === 'POST') {
        return new Response(JSON.stringify({ oauth_state: 'idle' }), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
    });

    render(<App />);

    const connectYtBtn = await screen.findByRole('button', { name: /Conectar YouTube OAuth/i });
    await user.click(connectYtBtn);

    await waitFor(() => {
      expect(openSpy).toHaveBeenCalledWith(expectedAuthUrl, '_blank');
      const fallbackLink = screen.getByRole('link', { name: /Abrir Google OAuth ↗/i });
      expect(fallbackLink).toHaveAttribute('href', expectedAuthUrl);
      const cancelBtn = screen.getByRole('button', { name: /^Cancelar$/i });
      expect(cancelBtn.className).toContain('h-10');
    });

    // Disparar primera consulta pending y luego el postMessage del callback
    window.dispatchEvent(new MessageEvent('message', { data: { type: 'SHORTYT_YOUTUBE_OAUTH_DONE' } }));
    await waitFor(() => {
      expect(oauthStatusCallCount).toBeGreaterThanOrEqual(1);
    });
    window.dispatchEvent(new MessageEvent('message', { data: { type: 'SHORTYT_YOUTUBE_OAUTH_DONE' } }));

    await waitFor(() => {
      expect(screen.getByText(/reintentando 2 subida\(s\)/i)).toBeInTheDocument();
    });

    document.querySelectorAll('button').forEach((btn) => {
      expect(btn.className).toContain('h-10');
    });
    openSpy.mockRestore();
  });

  it('muestra Subir TikToks en PC cuando hay pendientes y pide permiso antes de despachar por TikTok Studio', async () => {
    const user = userEvent.setup();
    let dispatchCalls = 0;
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();
      const method = (init?.method || 'GET').toUpperCase();

      if (url.endsWith('/api/inbox')) {
        return new Response(JSON.stringify(mockInboxPayload), { status: 200 });
      }
      if (url.endsWith('/api/shorts')) {
        return new Response(JSON.stringify(mockShortsPayload), { status: 200 });
      }
      if (url.endsWith('/api/queues')) {
        return new Response(JSON.stringify(mockQueuesPayload), { status: 200 });
      }
      if (url.endsWith('/api/content-profiles')) {
        return new Response(JSON.stringify({ profiles: [] }), { status: 200 });
      }
      if (url.endsWith('/api/analytics/categories')) {
        return new Response(JSON.stringify({ categories: [] }), { status: 200 });
      }
      if (url.endsWith('/api/subtitles/presets')) {
        return new Response(JSON.stringify({ presets: [] }), { status: 200 });
      }
      if (url.includes('/api/pipeline/candidates')) {
        return new Response(JSON.stringify({ video_filename: null, candidates: [] }), { status: 200 });
      }
      if (url.endsWith('/api/live/status')) {
        return new Response(JSON.stringify({ status: 'IDLE', recent_clips: [] }), { status: 200 });
      }
      if (url.endsWith('/api/social-accounts')) {
        return new Response(
          JSON.stringify({
            categories: {},
            api_settings: {
              youtube: { client_id: '', client_secret: '', default_category_id: '22', default_privacy_status: 'private' },
              instagram: { app_id: '', app_secret: '', access_token: '', business_id: '', graph_version: 'v21.0' },
              tiktok: { client_key: '', client_secret: '', access_token: '', redirect_uri: '', publish_mode: 'TIKTOK_STUDIO' },
              facebook: { app_id: '', page_access_token: '', graph_version: 'v21.0' },
            },
          }),
          { status: 200 }
        );
      }
      if (url.endsWith('/api/social-accounts/tiktok/studio-dispatch') && method === 'POST') {
        const body = JSON.parse(String(init?.body || '{}'));
        expect(body.user_permission_granted).toBe(true);
        dispatchCalls += 1;
        return new Response(
          JSON.stringify({ dispatched: true, count: 1, detail: 'Despachando 1 TikTok vía Brave.' }),
          { status: 200 }
        );
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 });
    });

    render(<App />);

    const ttBtn = await screen.findByRole('button', { name: /Subir TikToks en PC \(1\)/i });
    expect(ttBtn.className).toContain('h-10');

    // 1) Si el usuario dice que NO (confirm=false), NO se ejecuta
    await user.click(ttBtn);
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(dispatchCalls).toBe(0);

    // 2) Si el usuario da permiso (confirm=true), SÍ se despacha
    await user.click(ttBtn);
    await waitFor(() => {
      expect(confirmSpy).toHaveBeenCalledTimes(2);
      expect(dispatchCalls).toBe(1);
      expect(screen.getByText(/Brave.*TikTok Studio|TikTok.*Brave/i)).toBeInTheDocument();
    });

    // Verificar opción TIKTOK_STUDIO en Cuentas & APIs
    await user.click(screen.getByRole('tab', { name: /Cuentas & APIs/i }));
    const modeSelect = await screen.findByLabelText(/Modo de Publicación/i);
    expect(modeSelect.innerHTML).toContain('TIKTOK_STUDIO');

    document.querySelectorAll('button').forEach((btn) => {
      expect(btn.className).toContain('h-10');
    });
    confirmSpy.mockRestore();
  });
});
