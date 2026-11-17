import type {
  AccountCategoryKey,
  CategorySceneRule,
  LayoutMode,
  PipelineStatus,
  QueuesResponse,
  RenderedShortItem,
  ShortSocialStatuses,
  SocialHubConfigResponse,
  SocialNetworkStatusItem,
  SourceType,
  SubtitlePosition,
} from '../types';

export type ActiveOperation =
  | 'none'
  | 'inspect'
  | 'pick_local_video'
  | 'pre_analyze'
  | 'process'
  | 'cleanup'
  | 'cancel_short'
  | 'cancel_all'
  | 'cancel_pipeline'
  | 'schedule_batch'
  | 'detect_scene'
  | 'save_profile'
  | 'delete_profile'
  | 'discover'
  | 'render_selected'
  | 'schedule_single'
  | 'load_short_editor'
  | 'rerender_short'
  | 'save_social_hub'
  | 'verify_social_platform'
  | 'authorize_youtube_oauth'
  | 'dispatch_tiktok_studio'
  | 'update_short_categories'
  | 'create_social_category'
  | 'delete_social_category'
  | 'download_shorts'
  | 'start_live'
  | 'stop_live'
  | 'new_project';

export type GalleryFilter = 'all' | AccountCategoryKey;

export const ACCOUNT_CATEGORY_ORDER: readonly AccountCategoryKey[] = [
  'principales',
  'gaming',
  'clipping',
  'ometv',
] as const;

export const ACCOUNT_CATEGORY_META: Record<
  string,
  { label: string; shortLabel: string }
> = {
  principales: { label: 'Cuentas Principales', shortLabel: 'Principales' },
  gaming: { label: 'Cuentas Gaming', shortLabel: 'Gaming' },
  clipping: { label: 'Cuentas Clipping', shortLabel: 'Clipping' },
  ometv: { label: 'Cuentas OMETV', shortLabel: 'OMETV' },
};

export interface CategoryOptionMeta {
  key: string;
  label: string;
  shortLabel: string;
  isCustom: boolean;
}

export function getHubCategoryOptions(
  hubConfig?: SocialHubConfigResponse | null
): CategoryOptionMeta[] {
  const cats = hubConfig?.categories;
  if (!cats || Object.keys(cats).length === 0) {
    return ACCOUNT_CATEGORY_ORDER.map((k) => ({
      key: k,
      label: ACCOUNT_CATEGORY_META[k]?.label || k,
      shortLabel: ACCOUNT_CATEGORY_META[k]?.shortLabel || k,
      isCustom: false,
    }));
  }

  return Object.entries(cats).map(([rawKey, cat]) => {
    const key = (cat?.key || rawKey).trim();
    const label = (cat?.label || ACCOUNT_CATEGORY_META[key]?.label || key).trim();
    const knownShort = ACCOUNT_CATEGORY_META[key]?.shortLabel;
    const derivedShort = label.replace(/^cuentas\s+/i, '').trim() || label;
    return {
      key,
      label,
      shortLabel: knownShort || derivedShort,
      isCustom: Boolean(cat?.is_custom),
    };
  });
}

export const PREVIEW_SAMPLE_WORDS = ['¡MIRA', 'ESTE', 'CLIP', '100%!'] as const;

export function formatSecondsToTimestamp(totalSec: number): string {
  const safe = Math.max(0, Math.floor(Number.isFinite(totalSec) ? totalSec : 0));
  const hrs = Math.floor(safe / 3600);
  const mins = Math.floor((safe % 3600) / 60);
  const secs = safe % 60;
  const pad = (n: number) => String(n).padStart(2, '0');
  return hrs > 0 ? `${hrs}:${pad(mins)}:${pad(secs)}` : `${pad(mins)}:${pad(secs)}`;
}

export function parseTimestampInput(raw: string): number | null {
  const cleaned = raw.trim();
  if (!cleaned) return null;
  if (/^\d+(?:\.\d+)?$/.test(cleaned)) {
    const val = Number(cleaned);
    return Number.isFinite(val) && val >= 0 ? val : null;
  }
  const colonParts = cleaned.split(':').map((p) => p.trim());
  if ((colonParts.length === 2 || colonParts.length === 3) && colonParts.every((p) => /^\d+(?:\.\d+)?$/.test(p))) {
    const nums = colonParts.map(Number);
    if (colonParts.length === 2) {
      return nums[0] * 60 + nums[1];
    }
    return nums[0] * 3600 + nums[1] * 60 + nums[2];
  }
  const hmsMatch = cleaned.match(/^(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*(?:(\d+(?:\.\d+)?)\s*s?)?$/i);
  if (hmsMatch && (hmsMatch[1] || hmsMatch[2] || hmsMatch[3])) {
    const h = Number(hmsMatch[1] || 0);
    const m = Number(hmsMatch[2] || 0);
    const s = Number(hmsMatch[3] || 0);
    return h * 3600 + m * 60 + s;
  }
  return null;
}

export const SUBTITLE_PRESET_LABELS: Record<string, string> = {
  hormozi_pop: 'Hormozi Pop · Amarillo / Verde / Rojo',
  nexus_cyber_glow: 'Nexus Cyber Glow · Cian Neón Impact',
  one_word_punch: 'One-Word Punch · Palabra Gigante',
  clean_apple_box: 'Clean Apple Box · Pastilla Oscura',
  karaoke_duo: 'Karaoke Dúo · Barrido Verde Progresivo',
  none: 'Sin Subtítulos',
};

export const SUBTITLE_POSITION_LABELS: Record<SubtitlePosition, string> = {
  auto: 'Automática (Según Encuadre)',
  top: 'Arriba (Top)',
  center: 'Centro (Línea Divisoria)',
  bottom: 'Abajo (Bottom Safe)',
};

export const LAYOUT_MODE_LABELS: Record<LayoutMode, string> = {
  auto: 'Automático (Detección Visual IA)',
  fullscreen: 'Fullscreen (Cámara Completa 9:16)',
  split_streamer: 'Split Streamer (Cámara Arriba + Contenido Abajo)',
  gaming_hud: 'Gameplay + Cámara Flotante / Superior',
  split_50_50: 'Split 50/50 Limpio (Doble Plano)',
  podcast_dynamic: 'Mesa / Podcast Dinámico (1 Rostro / 2 en 50-50)',
  reaction_pip: 'Reacción PiP (16:9 Íntegro + Reacción Abajo)',
  reality_multicam: 'Sala Panorámica / Reality Multicam',
  floating_cam_top: 'Contenido 9:16 + Cámara En Esquina',
  floating_circle: 'Contenido 9:16 + Cámara Circular',
  blur_16_9_cam: '16:9 Blur Cine + Cámara Superior',
  ometv: 'Doble Cámara 50/50 (Cara a Cara)',
};

const SCENE_PRESET_TEMPLATES: Array<{
  scene_label: string;
  layout_mode: LayoutMode;
  subtitle_preset: string;
  subtitle_position: SubtitlePosition;
}> = [
  {
    scene_label: 'Escena Principal',
    layout_mode: 'fullscreen',
    subtitle_preset: 'hormozi_pop',
    subtitle_position: 'bottom',
  },
  {
    scene_label: 'Gameplay / Contenido + Cámara',
    layout_mode: 'split_streamer',
    subtitle_preset: 'nexus_cyber_glow',
    subtitle_position: 'center',
  },
  {
    scene_label: 'Mesa / Doble Plano 50-50',
    layout_mode: 'podcast_dynamic',
    subtitle_preset: 'karaoke_duo',
    subtitle_position: 'bottom',
  },
  {
    scene_label: 'Pantalla Completa + PiP',
    layout_mode: 'reaction_pip',
    subtitle_preset: 'hormozi_pop',
    subtitle_position: 'center',
  },
];

export function createSceneRule(
  ruleId: string,
  index = 0,
  sharePct = 50
): CategorySceneRule {
  const tpl = SCENE_PRESET_TEMPLATES[index % SCENE_PRESET_TEMPLATES.length];
  return {
    rule_id: ruleId,
    category: 'auto',
    scene_label: tpl.scene_label,
    detected_share_pct: sharePct,
    layout_mode: tpl.layout_mode,
    subtitle_preset: tpl.subtitle_preset,
    subtitle_position: tpl.subtitle_position,
    cam_overlay_pos: 'top_right',
    custom_cam_box_norm: null,
    custom_content_box_norm: null,
    custom_boxes_manual: false,
    frame_url: null,
    sample_timestamp_sec: null,
  };
}

export function buildFallbackSceneRules(
  sourceType: SourceType,
  selectedVideo: string,
  youtubeUrl: string
): CategorySceneRule[] {
  const hint = (sourceType === 'youtube_url' ? youtubeUrl : selectedVideo).toLowerCase();
  if (hint.includes('podcast') || hint.includes('entrevista') || hint.includes('tertulia')) {
    return [
      {
        ...createSceneRule('scene_1', 2, 70),
        scene_label: 'Cabina / Mesa Principal',
      },
      {
        ...createSceneRule('scene_2', 0, 30),
        scene_label: 'Plano Individual',
      },
    ];
  }
  if (hint.includes('twitch') || hint.includes('kick') || hint.includes('stream') || hint.includes('live')) {
    return [
      {
        ...createSceneRule('scene_1', 0, 35),
        scene_label: 'Charla Cámara Completa',
      },
      {
        ...createSceneRule('scene_2', 1, 65),
        scene_label: 'Gameplay + Cámara',
        layout_mode: 'gaming_hud',
      },
    ];
  }
  return [
    {
      ...createSceneRule('scene_1', 0, 100),
      scene_label: 'Escena Principal',
      layout_mode: 'auto',
      subtitle_preset: 'hormozi_pop',
      subtitle_position: 'auto',
    },
  ];
}

export const DUAL_BOX_LAYOUTS: LayoutMode[] = [
  'split_streamer',
  'split_50_50',
  'podcast_dynamic',
  'gaming_hud',
  'reaction_pip',
  'floating_cam_top',
  'floating_circle',
  'blur_16_9_cam',
  'ometv',
];

export const SHORT_REEDIT_LAYOUTS: Array<{ value: LayoutMode; label: string }> = [
  { value: 'split_50_50', label: '50/50 Limpio (Sin OmeTV)' },
  { value: 'split_streamer', label: 'Streamer Dividido (Cam + Contenido)' },
  { value: 'ometv', label: 'OmeTV 50/50 + Banner Central' },
  { value: 'fullscreen', label: 'Pantalla Completa Vertical' },
  { value: 'podcast_dynamic', label: 'Podcast Dinámico (Dual)' },
  { value: 'gaming_hud', label: 'Gaming HUD Completo' },
  { value: 'reaction_pip', label: 'Reacción PiP (Cámara Flotante)' },
  { value: 'reality_multicam', label: 'Reality Multicámara' },
  { value: 'floating_cam_top', label: 'Cámara Flotante Superior' },
  { value: 'floating_circle', label: 'Cámara Circular Flotante' },
  { value: 'blur_16_9_cam', label: '16:9 Centrado con Blur + Cámara' },
  { value: 'auto', label: 'Detección Automática IA' },
];

export const SHORT_REEDIT_SUBTITLE_PRESETS: Array<{ value: string; label: string }> = [
  { value: 'hormozi_pop', label: 'Hormozi Pop (Amarillo/Blanco)' },
  { value: 'nexus_cyber_glow', label: 'Nexus Cyber Glow (Cian Neón)' },
  { value: 'one_word_punch', label: 'One-Word Punch (Gigante)' },
  { value: 'clean_apple_box', label: 'Clean Apple Box (Oscura)' },
  { value: 'karaoke_duo', label: 'Karaoke Dúo (Barrido Verde)' },
  { value: 'mrbeast_clean', label: 'MrBeast Limpio' },
  { value: 'tiktok_karaoke', label: 'Karaoke Dinámico' },
  { value: 'minimal_white', label: 'Minimalista Blanco' },
  { value: 'none', label: 'Sin Subtítulos' },
];

export const SHORT_REEDIT_PRESET_BOXES: Record<
  LayoutMode,
  { cam: [number, number, number, number]; content: [number, number, number, number] }
> = {
  split_50_50: { cam: [0.55, 0.08, 0.4, 0.84], content: [0.05, 0.08, 0.48, 0.84] },
  split_streamer: { cam: [0.68, 0.06, 0.28, 0.38], content: [0.0, 0.0, 1.0, 1.0] },
  ometv: { cam: [0.0, 0.0, 0.5, 1.0], content: [0.5, 0.0, 0.5, 1.0] },
  fullscreen: { cam: [0.34, 0.0, 0.32, 1.0], content: [0.0, 0.0, 1.0, 1.0] },
  podcast_dynamic: { cam: [0.54, 0.1, 0.4, 0.8], content: [0.06, 0.1, 0.4, 0.8] },
  gaming_hud: { cam: [0.72, 0.04, 0.25, 0.32], content: [0.0, 0.0, 1.0, 1.0] },
  reaction_pip: { cam: [0.68, 0.05, 0.28, 0.36], content: [0.0, 0.0, 1.0, 1.0] },
  reality_multicam: { cam: [0.52, 0.08, 0.44, 0.84], content: [0.04, 0.08, 0.44, 0.84] },
  floating_cam_top: { cam: [0.66, 0.05, 0.3, 0.36], content: [0.0, 0.0, 1.0, 1.0] },
  floating_circle: { cam: [0.7, 0.05, 0.26, 0.34], content: [0.0, 0.0, 1.0, 1.0] },
  blur_16_9_cam: { cam: [0.68, 0.62, 0.28, 0.34], content: [0.0, 0.0, 1.0, 1.0] },
  auto: { cam: [0.68, 0.06, 0.28, 0.38], content: [0.0, 0.0, 1.0, 1.0] },
};

export function getDefaultLocalDateTimeInput(offsetHours: number): string {
  const d = new Date(Date.now() + offsetHours * 3600 * 1000);
  d.setMinutes(0, 0, 0);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function formatUtcToAstDateTimeLocal(utcIso?: string | null, fallbackOffsetHours = 1): string {
  if (utcIso) {
    const parsedMs = Date.parse(utcIso);
    if (Number.isFinite(parsedMs)) {
      const astDate = new Date(parsedMs - 4 * 3600 * 1000);
      const pad = (n: number) => String(n).padStart(2, '0');
      return `${astDate.getUTCFullYear()}-${pad(astDate.getUTCMonth() + 1)}-${pad(astDate.getUTCDate())}T${pad(
        astDate.getUTCHours()
      )}:${pad(astDate.getUTCMinutes())}`;
    }
  }
  return getDefaultLocalDateTimeInput(fallbackOffsetHours);
}

export function pauseAllVideosExcept(keep?: HTMLVideoElement | null): void {
  if (typeof document === 'undefined') return;
  const videos = document.querySelectorAll('video');
  videos.forEach((vid) => {
    if (vid !== keep && !vid.paused) {
      try {
        vid.pause();
      } catch {
        // Silenciar errores de reproducción en entornos de prueba sin decodificador
      }
    }
  });
}

export function clampNorm01(v: number, minVal = 0, maxVal = 1): number {
  return Math.min(maxVal, Math.max(minVal, Number.isFinite(v) ? v : minVal));
}

export function extractYouTubeEmbedUrl(rawUrl?: string | null): string | null {
  if (!rawUrl) return null;
  const trimmed = rawUrl.trim();
  if (!trimmed.startsWith('http://') && !trimmed.startsWith('https://')) {
    return null;
  }
  const match = trimmed.match(
    /(?:youtube\.com\/(?:watch\?v=|live\/|embed\/|shorts\/)|youtu\.be\/)([A-Za-z0-9_-]{11})/
  );
  if (match && match[1]) {
    return `https://www.youtube.com/embed/${match[1]}`;
  }
  return null;
}

export function formatShortCardTitle(item: RenderedShortItem): string {
  if (item.hook_title && item.hook_title.trim()) {
    return item.hook_title.trim();
  }
  return item.filename
    .replace(/_(Oro|Plata|Meh)_\d+pts\.mp4$/i, '')
    .replace(/\.mp4$/i, '')
    .replace(/_/g, ' ')
    .trim();
}

export function getTierVisualMeta(tier: RenderedShortItem['tier']): {
  label: string;
  badgeClass: string;
} {
  if (tier === 'Oro') {
    return {
      label: 'ORO 🔥',
      badgeClass:
        'bg-amber-500/20 text-amber-200 border border-amber-400/40 backdrop-blur-md',
    };
  }
  if (tier === 'Plata') {
    return {
      label: 'PLATA ⚡',
      badgeClass:
        'bg-cyan-500/20 text-cyan-200 border border-cyan-400/40 backdrop-blur-md',
    };
  }
  return {
    label: 'MEH 😐',
    badgeClass:
      'bg-zinc-600/35 text-zinc-200 border border-zinc-500/40 backdrop-blur-md',
  };
}

export function withCacheBust(url: string, version?: number): string;
export function withCacheBust(url: string | undefined, version?: number): string | undefined;
export function withCacheBust(url: string | undefined, version?: number): string | undefined {
  if (!url || !version) return url;
  return `${url}${url.includes('?') ? '&' : '?'}v=${version}`;
}

function mapQueueStatusToSocialItem(
  network: 'instagram' | 'tiktok' | 'facebook',
  entry: QueuesResponse['instagram_queue'][number] | undefined,
  fallbackScheduledAst: string | null,
  pipeline: PipelineStatus | null
): SocialNetworkStatusItem {
  const networkName =
    network === 'instagram' ? 'Instagram' : network === 'tiktok' ? 'TikTok' : 'Facebook';
  const isPipelineRunning =
    pipeline?.status === 'RUNNING' ||
    pipeline?.status === 'STARTED' ||
    pipeline?.status === 'DISCOVERING';
  const stageUpper = String(pipeline?.phase_label || pipeline?.status || '').toUpperCase();
  const detailLower = String(pipeline?.step_detail || '').toLowerCase();
  const isPipelineActiveForNet =
    isPipelineRunning &&
    (stageUpper.includes('UPLOAD') ||
      detailLower.includes(network) ||
      detailLower.includes('subiendo'));

  if (entry) {
    const st = String(entry.status || '').toUpperCase();
    const cleanAcct = entry.account_key ? entry.account_key.replace(/^@/, '') : '';
    const acct = cleanAcct ? `@${cleanAcct}` : null;
    if (st === 'PUBLISHED' || st === 'DONE' || st === 'UPLOADED') {
      const permalink =
        entry.permalink ||
        (network === 'facebook' && entry.post_id
          ? `https://www.facebook.com/reel/${entry.post_id}/`
          : network === 'tiktok' && entry.post_id && cleanAcct
          ? `https://www.tiktok.com/@${cleanAcct}/video/${entry.post_id}`
          : null);
      return {
        network,
        state: 'uploaded',
        status_label: 'Subido',
        detail: `${acct ? `${acct} · ` : ''}${entry.scheduled_time_ast || 'Publicado'}`,
        percent: 100,
        account: acct,
        permalink,
      };
    }
    if (st === 'INBOX_DRAFT' || st === 'SEND_TO_USER_INBOX') {
      return {
        network,
        state: 'draft',
        status_label: 'En Borrador (App)',
        detail: `${acct ? `${acct} · ` : ''}Enviado a Bandeja TikTok (App) — falta publicar en la app`,
        percent: 85,
        account: acct,
        permalink: null,
      };
    }
    if (st === 'PROCESSING' || st === 'UPLOADING' || st === 'IN_PROGRESS') {
      return {
        network,
        state: 'processing',
        status_label: 'En proceso',
        detail: `${acct ? `${acct} · ` : ''}Subiendo a ${networkName}...`,
        percent: 65,
        account: acct,
      };
    }
    if (st === 'FAILED' || st === 'ERROR') {
      return {
        network,
        state: 'error',
        status_label: 'Error',
        detail: entry.error || `Error al subir a ${networkName}`,
        percent: 100,
        account: acct,
      };
    }
    if (isPipelineActiveForNet) {
      return {
        network,
        state: 'processing',
        status_label: 'En proceso',
        detail: `${acct ? `${acct} · ` : ''}Subiendo a ${networkName}...`,
        percent: 65,
        account: acct,
      };
    }
    return {
      network,
      state: 'pending',
      status_label: 'Pendiente',
      detail: `${acct ? `${acct} · ` : ''}${entry.scheduled_time_ast || 'En cola'}`,
      percent: 50,
      account: acct,
    };
  }

  if (isPipelineActiveForNet) {
    return {
      network,
      state: 'processing',
      status_label: 'En proceso',
      detail: `Subiendo a ${networkName}...`,
      percent: 65,
      account: null,
    };
  }
  if (fallbackScheduledAst) {
    return {
      network,
      state: 'pending',
      status_label: 'Pendiente',
      detail: fallbackScheduledAst,
      percent: 50,
      account: null,
    };
  }
  return {
    network,
    state: 'local',
    status_label: 'Listo en local',
    detail: 'Listo en local (Sin programar)',
    percent: 25,
    account: null,
  };
}

export function resolveShortSocialStatuses(
  item: RenderedShortItem,
  queuesData: QueuesResponse,
  pipeline: PipelineStatus | null
): ShortSocialStatuses {
  const fnameLower = item.filename.toLowerCase();
  const stemLower = fnameLower.replace(/\.[^/.]+$/, '');
  const matchesShort = (videoPath?: string | null) => {
    const p = String(videoPath || '').toLowerCase();
    return Boolean(p && (p.includes(fnameLower) || (stemLower && p.includes(stemLower))));
  };

  const igMatch = queuesData.instagram_queue.find((q) => matchesShort(q.video_path));
  const ttMatch = queuesData.tiktok_queue.find((q) => matchesShort(q.video_path));
  const fbMatch = (queuesData.facebook_queue || []).find((q) => matchesShort(q.video_path));

  if (item.social_statuses) {
    return {
      youtube: item.social_statuses.youtube,
      instagram: item.social_statuses.instagram,
      tiktok: item.social_statuses.tiktok,
      facebook:
        item.social_statuses.facebook ||
        mapQueueStatusToSocialItem('facebook', fbMatch, item.scheduled_ast, pipeline),
    };
  }

  const isPipelineRunning =
    pipeline?.status === 'RUNNING' ||
    pipeline?.status === 'STARTED' ||
    pipeline?.status === 'DISCOVERING';
  const stageUpper = String(pipeline?.phase_label || pipeline?.status || '').toUpperCase();
  const detailLower = String(pipeline?.step_detail || '').toLowerCase();
  const isYtUploading =
    isPipelineRunning &&
    (detailLower.includes('youtube') || stageUpper.includes('UPLOAD'));

  const ytAccount =
    item.resolved_targets?.youtube?.[0] || '@CreadorStudio';

  let ytStatus: SocialNetworkStatusItem;
  if (item.youtube_video_id) {
    ytStatus = {
      network: 'youtube',
      state: 'uploaded',
      status_label: 'Subido',
      detail: `Subido (${item.youtube_video_id})`,
      percent: 100,
      account: ytAccount,
      permalink: `https://www.youtube.com/shorts/${item.youtube_video_id}`,
    };
  } else if (isYtUploading) {
    ytStatus = {
      network: 'youtube',
      state: 'processing',
      status_label: 'En proceso',
      detail: pipeline?.step_detail || 'Subiendo a YouTube Shorts...',
      percent: 65,
      account: ytAccount,
    };
  } else if (item.scheduled_ast) {
    ytStatus = {
      network: 'youtube',
      state: 'pending',
      status_label: 'Pendiente',
      detail: item.scheduled_ast,
      percent: 50,
      account: ytAccount,
    };
  } else {
    ytStatus = {
      network: 'youtube',
      state: 'local',
      status_label: 'Listo en local',
      detail: item.upload_status_detail || 'Listo en local (Sin programar)',
      percent: 25,
      account: ytAccount,
    };
  }

  return {
    youtube: ytStatus,
    instagram: mapQueueStatusToSocialItem('instagram', igMatch, item.scheduled_ast, pipeline),
    tiktok: mapQueueStatusToSocialItem('tiktok', ttMatch, item.scheduled_ast, pipeline),
    facebook: mapQueueStatusToSocialItem('facebook', fbMatch, item.scheduled_ast, pipeline),
  };
}

export function getVideoDisplayName(videoRef: string): string {
  const trimmed = (videoRef || '').trim();
  if (!trimmed) return '';
  return trimmed.split(/[\\/]/).pop() || trimmed;
}

export function buildVideoDateProjectSlug(
  videoName?: string | null,
  now: Date = new Date()
): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  const datePart = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  const raw = (videoName || '').trim();
  if (!raw) {
    return `Proyecto_${datePart}_${pad(now.getHours())}${pad(now.getMinutes())}`;
  }
  const baseName = getVideoDisplayName(raw).replace(/\.[^/.]+$/, '');
  const withoutRandom = baseName
    .replace(/^p_[a-zA-Z0-9]{6,}_[a-zA-Z0-9]{2,4}_+/g, '')
    .replace(/^p_[a-zA-Z0-9]{4,}_+/, '')
    .replace(/^inbox_vi(?:deos?)?_*/i, '');
  const ascii = withoutRandom.normalize('NFKD').replace(/[\u0300-\u036f]/g, '');
  let clean = ascii.replace(/[^A-Za-z0-9_-]+/g, '_').replace(/_+/g, '_').replace(/^[_-]+|[_-]+$/g, '');
  const maxStemLen = 45;
  if (clean.length > maxStemLen) {
    clean = clean.slice(0, maxStemLen).replace(/[_-]+$/g, '');
  }
  return `${clean || 'Video'}_${datePart}`;
}

export function getShortSelectionKey(item: RenderedShortItem): string {
  return item.relative_path || (item.folder ? `${item.folder}/${item.filename}` : item.filename);
}

export function isPlaceholderProjectId(pid: string): boolean {
  return /^Proyecto_\d{4}-\d{2}-\d{2}_\d{4}(?:_\d+)?$/i.test(pid) || /^p_[a-z0-9_]+$/i.test(pid);
}
