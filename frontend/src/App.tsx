import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';
import type {
  AccountCategoryKey,
  ActiveStudioTab,
  CamOverlayPos,
  CandidatesResponse,
  CategorySceneRule,
  CleanupResponse,
  ContentProfileItem,
  ContentProfilesResponse,
  DiscoveredCandidateItem,
  DiskSpaceReport,
  InboxResponse,
  InboxVideoItem,
  LayoutMode,
  LiveMonitorStatus,
  LocalVideoPickResponse,
  PipelineStatus,
  PreAnalyzeResponse,
  ProcessStartResponse,
  QueuesResponse,
  RenameProjectResponse,
  RenderedShortItem,
  SceneDetectResponse,
  ShortSceneDetectResponse,
  ShortsBatchSummary,
  ShortsResponse,
  SocialHubConfigResponse,
  SocialPlatformKey,
  SocialPlatformVerifyResponse,
  SourceType,
  SubtitlePosition,
  SubtitlePresetItem,
  SubtitlePresetsResponse,
  ThemeMode,
  VideoInspectionReport,
} from './types';
import { StudioHeader } from './components/StudioHeader';
import { LiveStreamStudio } from './components/LiveStreamStudio';
import { SocialAccountsStudio } from './components/SocialAccountsStudio';
import { OmniboxConfigStudio } from './components/OmniboxConfigStudio';
import type { StudioDragTarget } from './components/InteractiveSceneStudio';
import { PreFlightAnalysisModal } from './components/PreFlightAnalysisModal';
import { DiscoveredCandidatesTray } from './components/DiscoveredCandidatesTray';
import { ProcessMonitorSection } from './components/ProcessMonitorSection';
import { ShortsGallery } from './components/ShortsGallery';
import {
  FloatingShortPlayer,
  type ReeditDragState,
  ScheduleBatchModal,
  ShortLayoutEditorModal,
} from './components/StudioModals';
import {
  type ActiveOperation,
  type GalleryFilter,
  DUAL_BOX_LAYOUTS,
  SHORT_REEDIT_PRESET_BOXES,
  buildFallbackSceneRules,
  buildVideoDateProjectSlug,
  getHubCategoryOptions,
  getShortSelectionKey,
  getVideoDisplayName,
  isPlaceholderProjectId,
  clampNorm01,
  createSceneRule,
  formatUtcToAstDateTimeLocal,
  getDefaultLocalDateTimeInput,
  pauseAllVideosExcept,
} from './components/studioHelpers';

const SAFE_PROJECT_ID_RE = /^[a-zA-Z0-9_-]{1,56}$/;

function resolveWindowProjectId(): string {
  try {
    const raw = new URLSearchParams(window.location.search).get('project')?.trim() ?? '';
    if (raw && SAFE_PROJECT_ID_RE.test(raw)) {
      return raw;
    }
  } catch {
    // Fallback al proyecto principal si window.location no está disponible
  }
  return 'default';
}

function buildProjectApiUrl(path: string, projectId: string): string {
  if (!projectId || projectId === 'default') {
    return path;
  }
  const sep = path.includes('?') ? '&' : '?';
  return `${path}${sep}project_id=${encodeURIComponent(projectId)}`;
}

function generateIndependentProjectId(): string {
  return buildVideoDateProjectSlug(null);
}

const DEFAULT_SOCIAL_HUB_CONFIG: SocialHubConfigResponse = {
  categories: {
    principales: {
      key: 'principales',
      label: 'Cuentas Principales',
      description: 'Canales oficiales de marca personal y contenido destacado principal.',
      topic_keywords: ['principal', 'exclusiva', 'anuncio', 'opinion'],
      accounts: [
        {
          id: 'yt_principales_creadorstudio',
          platform: 'youtube',
          handle: '@CreadorStudio',
          display_name: 'CreadorStudio (Principal)',
          external_id: '',
          enabled: true,
        },
      ],
    },
    gaming: {
      key: 'gaming',
      label: 'Cuentas Gaming',
      description: 'Gameplays, hardware, DLSS/RTX, OBS y streams jugando.',
      topic_keywords: ['gaming', 'gameplay', 'juego', 'rtx', 'dlss'],
      accounts: [
        {
          id: 'ig_gaming_creador_gaming',
          platform: 'instagram',
          handle: '@creador_gaming',
          display_name: 'Creador Gaming',
          external_id: '',
          enabled: true,
        },
        {
          id: 'yt_gaming_creadorstudio',
          platform: 'youtube',
          handle: '@creadorstudio',
          display_name: 'CreadorStudio YouTube',
          external_id: '',
          enabled: true,
        },
        {
          id: 'tt_gaming_creador_gaming',
          platform: 'tiktok',
          handle: '@creador.gaming',
          display_name: 'Creador Gaming TikTok',
          external_id: '',
          enabled: true,
        },
        {
          id: 'fb_gaming_creador_gaming',
          platform: 'facebook',
          handle: 'Creador Gaming',
          display_name: 'Creador Gaming Page',
          external_id: '',
          enabled: true,
        },
      ],
    },
    clipping: {
      key: 'clipping',
      label: 'Cuentas Clipping',
      description: 'Red de clipping viral: debates, reacciones, podcast y humor.',
      is_custom: false,
      topic_keywords: ['clip', 'clipeo', 'viral', 'reaccion', 'debate', 'podcast', 'humor'],
      accounts: [
        {
          id: 'ig_clip_short',
          platform: 'instagram',
          handle: '@creador_short',
          display_name: 'Creador Short',
          external_id: '',
          enabled: true,
        },
      ],
    },
    ometv: {
      key: 'ometv',
      label: 'Cuentas OMETV',
      description: 'Exclusivo para clips de OmeTV, charlas con desconocidos e interacciones random en vivo.',
      is_custom: false,
      topic_keywords: ['ometv', 'omegle', 'desconocidos', 'random', 'videochat'],
      accounts: [
        {
          id: 'ig_ometv_creador_ometv',
          platform: 'instagram',
          handle: '@creador_ometv',
          display_name: 'Creador OMETV',
          external_id: '',
          enabled: true,
        },
        {
          id: 'yt_ometv_creadorstudio',
          platform: 'youtube',
          handle: '@creadorstudio',
          display_name: 'CreadorStudio YouTube',
          external_id: '',
          enabled: true,
        },
        {
          id: 'tt_ometv_creador_ometv',
          platform: 'tiktok',
          handle: '@creador_ometv',
          display_name: 'Creador OMETV TikTok',
          external_id: '',
          enabled: true,
        },
        {
          id: 'fb_ometv_creador_ometv',
          platform: 'facebook',
          handle: 'Creador OMETV',
          display_name: 'Creador OMETV Page',
          external_id: '',
          enabled: true,
        },
      ],
    },
  },
  api_settings: {
    youtube: {
      client_id: '',
      client_secret: '',
      client_secret_json: '',
      default_category_id: '22',
    },
    instagram: {
      app_id: '',
      app_secret: '',
      access_token: '',
      business_id: '',
      graph_version: 'v21.0',
    },
    tiktok: {
      client_key: '',
      client_secret: '',
      access_token: '',
      redirect_uri: 'http://localhost:3456/callback/',
      publish_mode: 'DIRECT_POST',
    },
    facebook: {
      app_id: '',
      page_access_token: '',
      graph_version: 'v21.0',
    },
  },
};

export default function App() {
  const [projectId, setProjectId] = useState<string>(() => resolveWindowProjectId());
  const [projectDisplayName, setProjectDisplayName] = useState<string | null>(() => {
    const initialPid = resolveWindowProjectId();
    return initialPid !== 'default' ? initialPid : null;
  });
  const [showSocialDetails, setShowSocialDetails] = useState<boolean>(false);

  // Datos reales del backend
  const [inboxVideos, setInboxVideos] = useState<InboxVideoItem[]>([]);
  const [diskSpace, setDiskSpace] = useState<DiskSpaceReport | null>(null);
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus | null>(null);
  const [renderedShorts, setRenderedShorts] = useState<RenderedShortItem[]>([]);
  const [queues, setQueues] = useState<QueuesResponse>({
    youtube_slots: [],
    instagram_queue: [],
    tiktok_queue: [],
  });

  // Apariencia Light / Dark persistida en backend y DOM (Dark Studio por defecto en servidor vía settings.json)
  const [themeMode, setThemeMode] = useState<ThemeMode>(() => {
    try {
      const saved = window.localStorage.getItem('short_yt_theme_mode');
      return saved === 'dark' ? 'dark' : 'light';
    } catch {
      return 'light';
    }
  });

  // Entradas Reales del Panel Principal + Modal Flotante Pre-Análisis Multi-Categoría
  const [sourceType, setSourceType] = useState<SourceType>('inbox');
  const [selectedVideo, setSelectedVideo] = useState<string>('');
  const [pickedVideoMeta, setPickedVideoMeta] = useState<LocalVideoPickResponse | null>(null);
  const [youtubeUrl, setYoutubeUrl] = useState<string>('');
  const [downloadSectionStart, setDownloadSectionStart] = useState<string>('');
  const [downloadSectionEnd, setDownloadSectionEnd] = useState<string>('');
  const [shortsPerVideo, setShortsPerVideo] = useState<number>(8);
  const hasAutoSelectedInboxRef = useRef<boolean>(projectId !== 'default');

  useEffect(() => {
    const label = projectDisplayName || (projectId !== 'default' ? projectId : null);
    document.title = label
      ? `Auto-Clipper Studio · ${label}`
      : 'Auto-Clipper Studio';
  }, [projectId, projectDisplayName]);

  const [isPreAnalyzeModalOpen, setIsPreAnalyzeModalOpen] = useState<boolean>(false);
  const [preAnalyzeData, setPreAnalyzeData] = useState<PreAnalyzeResponse | null>(null);
  const [categoryRules, setCategoryRules] = useState<CategorySceneRule[]>(() =>
    buildFallbackSceneRules('inbox', '', '')
  );
  const [activeRuleIndex, setActiveRuleIndex] = useState<number>(0);
  const preAnalyzeAbortRef = useRef<AbortController | null>(null);

  const [subtitlePresets, setSubtitlePresets] = useState<SubtitlePresetItem[]>([]);
  const [contentProfiles, setContentProfiles] = useState<ContentProfileItem[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<string>('');
  const [profileNameInput, setProfileNameInput] = useState<string>('');
  const [profileKeywordsInput, setProfileKeywordsInput] = useState<string>('');
  const [autoCategorizeByTopic, setAutoCategorizeByTopic] = useState<boolean>(true);
  const [allowedAccountCategories, setAllowedAccountCategories] = useState<AccountCategoryKey[]>([
    'principales',
    'gaming',
    'clipping',
    'ometv',
  ]);
  const [sceneDataByRuleId, setSceneDataByRuleId] = useState<Record<string, SceneDetectResponse>>({});
  const [isStudioOpen, setIsStudioOpen] = useState<boolean>(false);
  const [discoveredCandidates, setDiscoveredCandidates] = useState<DiscoveredCandidateItem[]>([]);
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<string[]>([]);
  const [draggingTarget, setDraggingTarget] = useState<StudioDragTarget | null>(null);
  const studioCanvasRef = useRef<HTMLDivElement | null>(null);
  const sourceVideoRef = useRef<HTMLVideoElement | null>(null);

  // Pestaña activa, En Vivo y Hub de Cuentas Sociales + APIs
  const [activeTab, setActiveTab] = useState<ActiveStudioTab>('studio');
  const [liveStatus, setLiveStatus] = useState<LiveMonitorStatus | null>(null);
  const [liveStreamUrl, setLiveStreamUrl] = useState<string>('');
  const [liveProfileId, setLiveProfileId] = useState<number | null>(null);
  const [liveChunkDurationSec, setLiveChunkDurationSec] = useState<number>(90);
  const [liveMinScore, setLiveMinScore] = useState<number>(70);
  const [liveMaxShorts, setLiveMaxShorts] = useState<number>(12);
  const [socialHubConfig, setSocialHubConfig] = useState<SocialHubConfigResponse>(
    DEFAULT_SOCIAL_HUB_CONFIG
  );
  const [verifyResults, setVerifyResults] = useState<
    Partial<Record<SocialPlatformKey, SocialPlatformVerifyResponse>>
  >({});
  const [verifyingPlatform, setVerifyingPlatform] = useState<SocialPlatformKey | null>(null);
  const [pendingYouTubeAuthUrl, setPendingYouTubeAuthUrl] = useState<string | null>(null);

  // Filtro visual de galería y cache-busting tras re-render
  const [galleryFilter, setGalleryFilter] = useState<GalleryFilter>('all');
  const [rerenderVersions, setRerenderVersions] = useState<Record<string, number>>({});

  // Estados de ciclo completo (Idle / Loading / Success / Error)
  const [actionState, setActionState] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [activeOperation, setActiveOperation] = useState<ActiveOperation>('none');
  const [feedbackMessage, setFeedbackMessage] = useState<string>('Sistema listo para procesar.');
  const [inspectionReport, setInspectionReport] = useState<VideoInspectionReport | null>(null);
  const [activeShortPlayer, setActiveShortPlayer] = useState<RenderedShortItem | null>(null);
  const [selectedShortKeys, setSelectedShortKeys] = useState<string[]>([]);

  // Programación individual por Short, Reproductor Flotante y Editor Post-Previsualización
  const [shortScheduleTimes, setShortScheduleTimes] = useState<Record<string, string>>({});
  const [reeditShort, setReeditShort] = useState<RenderedShortItem | null>(null);
  const [reeditScene, setReeditScene] = useState<ShortSceneDetectResponse | null>(null);
  const [reeditLayoutMode, setReeditLayoutMode] = useState<LayoutMode>('split_streamer');
  const [reeditCamPos, setReeditCamPos] = useState<CamOverlayPos>('top_right');
  const [reeditSubPreset, setReeditSubPreset] = useState<string>('hormozi_pop');
  const [reeditSubPos, setReeditSubPos] = useState<SubtitlePosition>('auto');
  const [reeditCamBox, setReeditCamBox] = useState<[number, number, number, number]>([0.65, 0.05, 0.3, 0.4]);
  const [reeditContentBox, setReeditContentBox] = useState<[number, number, number, number]>([0.0, 0.0, 1.0, 1.0]);
  const [reeditTrimStart, setReeditTrimStart] = useState<number>(0);
  const [reeditTrimEnd, setReeditTrimEnd] = useState<number>(30);
  const [reeditMinTrim, setReeditMinTrim] = useState<number>(0);
  const [reeditMaxTrim, setReeditMaxTrim] = useState<number>(60);
  const [reeditMediaUrl, setReeditMediaUrl] = useState<string | null>(null);
  const [reeditDragging, setReeditDragging] = useState<ReeditDragState | null>(null);
  const reeditCanvasRef = useRef<HTMLDivElement | null>(null);
  const [floatingOffset, setFloatingOffset] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const floatingDragRef = useRef<{ startX: number; startY: number; origX: number; origY: number } | null>(null);

  // Estado del Modal Flotante de Finalización y Programación por Plataforma
  const [shortsSummary, setShortsSummary] = useState<ShortsBatchSummary | null>(null);
  const [isScheduleModalOpen, setIsScheduleModalOpen] = useState<boolean>(false);
  const [dismissedModalJobId, setDismissedModalJobId] = useState<string | null>(null);
  const [youtubeScheduleTime, setYoutubeScheduleTime] = useState<string>(() => getDefaultLocalDateTimeInput(1));
  const [instagramScheduleTime, setInstagramScheduleTime] = useState<string>(() => getDefaultLocalDateTimeInput(1));
  const [tiktokScheduleTime, setTiktokScheduleTime] = useState<string>(() => getDefaultLocalDateTimeInput(1));
  const [scheduleIntervalMinutes, setScheduleIntervalMinutes] = useState<number>(60);

  useEffect(() => {
    const validSet = new Set(renderedShorts.map(getShortSelectionKey));
    setSelectedShortKeys((prev) => prev.filter((k) => validSet.has(k)));
  }, [renderedShorts]);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', themeMode === 'dark');
    try {
      window.localStorage.setItem('short_yt_theme_mode', themeMode);
    } catch {
      // Silenciar en entornos sin almacenamiento local
    }
  }, [themeMode]);

  const fetchAllData = useCallback(async () => {
    try {
      const [inboxRes, shortsRes, queuesRes, subRes, profilesRes, candsRes, socialHubRes, liveRes] = await Promise.all([
        fetch(buildProjectApiUrl('/api/inbox', projectId)),
        fetch(buildProjectApiUrl('/api/shorts', projectId)),
        fetch('/api/queues'),
        fetch('/api/subtitles/presets').catch(() => null),
        fetch('/api/content-profiles').catch(() => null),
        fetch(buildProjectApiUrl('/api/pipeline/candidates', projectId)).catch(() => null),
        fetch('/api/social-accounts').catch(() => null),
        fetch(buildProjectApiUrl('/api/live/status', projectId)).catch(() => null),
      ]);

      if (inboxRes.ok) {
        const inboxData: InboxResponse = await inboxRes.json();
        setInboxVideos(inboxData.videos);
        setDiskSpace(inboxData.disk_space);
        setPipelineStatus(inboxData.pipeline_status);
        const serverProjName = inboxData.project_name || inboxData.pipeline_status?.project_name || null;
        if (projectId !== 'default') {
          setProjectDisplayName(serverProjName || projectId);
        } else if (inboxData.pipeline_status?.current_video) {
          setProjectDisplayName(
            serverProjName || buildVideoDateProjectSlug(inboxData.pipeline_status.current_video)
          );
        }
        if (inboxData.settings?.theme_mode === 'dark' || inboxData.settings?.theme_mode === 'light') {
          setThemeMode(inboxData.settings.theme_mode);
        }

        setSelectedVideo((prev) => {
          if (prev && (prev.includes('\\') || prev.includes('/'))) {
            hasAutoSelectedInboxRef.current = true;
            return prev;
          }
          if (prev && inboxData.videos.some((v) => v.file_name === prev)) {
            hasAutoSelectedInboxRef.current = true;
            return prev;
          }
          if (!hasAutoSelectedInboxRef.current && inboxData.videos.length > 0) {
            hasAutoSelectedInboxRef.current = true;
            return inboxData.videos[0].file_name;
          }
          return '';
        });
      }

      if (shortsRes.ok) {
        const shortsData: ShortsResponse = await shortsRes.json();
        setRenderedShorts(shortsData.shorts);
        if (shortsData.summary) {
          setShortsSummary(shortsData.summary);
        }
      }

      if (queuesRes.ok) {
        const queuesData: QueuesResponse = await queuesRes.json();
        setQueues(queuesData);
      }

      if (subRes && subRes.ok) {
        const subData: SubtitlePresetsResponse = await subRes.json();
        setSubtitlePresets(subData.presets);
      }

      if (profilesRes && profilesRes.ok) {
        const profilesData: ContentProfilesResponse = await profilesRes.json();
        setContentProfiles(Array.isArray(profilesData.profiles) ? profilesData.profiles : []);
      }

      if (candsRes && candsRes.ok) {
        const candsData: CandidatesResponse = await candsRes.json();
        setDiscoveredCandidates(candsData.candidates);
        if (candsData.candidates.length > 0) {
          setSelectedCandidateIds((prev) =>
            prev.length > 0 ? prev : candsData.candidates.map((c) => c.candidate_id)
          );
        }
      }

      if (socialHubRes && socialHubRes.ok) {
        const hubData: SocialHubConfigResponse = await socialHubRes.json();
        if (hubData?.categories && hubData?.api_settings) {
          setSocialHubConfig(hubData);
        }
      }
      if (liveRes && liveRes.ok) {
        const liveData: LiveMonitorStatus = await liveRes.json();
        setLiveStatus(liveData);
        if (liveData.stream_url) {
          setLiveStreamUrl((prev) => prev || liveData.stream_url);
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error de conexión con el servidor backend.';
      setActionState('error');
      setFeedbackMessage(msg);
    }
  }, [projectId]);

  useEffect(() => {
    void fetchAllData();
  }, [fetchAllData]);

  useEffect(() => {
    if (pipelineStatus?.status !== 'RUNNING' && pipelineStatus?.status !== 'STARTED') {
      return;
    }
    const timer = window.setInterval(async () => {
      try {
        const [stRes, shRes] = await Promise.all([
          fetch(buildProjectApiUrl('/api/pipeline/status', projectId)),
          fetch(buildProjectApiUrl('/api/shorts', projectId)),
        ]);
        if (stRes.ok) {
          const stData: PipelineStatus = await stRes.json();
          setPipelineStatus(stData);
        }
        if (shRes.ok) {
          const shData: ShortsResponse = await shRes.json();
          setRenderedShorts(shData.shorts);
          if (shData.summary) {
            setShortsSummary(shData.summary);
          }
        }
      } catch {
        // Silenciar errores transitorios de polling
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [pipelineStatus?.status, projectId]);

  const isLiveMonitoring =
    liveStatus?.status === 'STARTING' ||
    liveStatus?.status === 'MONITORING' ||
    liveStatus?.status === 'ANALYZING_CHUNK';

  useEffect(() => {
    if (!isLiveMonitoring) return;
    const timer = window.setInterval(async () => {
      try {
        const [liveRes, shRes] = await Promise.all([
          fetch(buildProjectApiUrl('/api/live/status', projectId)),
          fetch(buildProjectApiUrl('/api/shorts', projectId)),
        ]);
        if (liveRes.ok) {
          setLiveStatus((await liveRes.json()) as LiveMonitorStatus);
        }
        if (shRes.ok) {
          const shData: ShortsResponse = await shRes.json();
          setRenderedShorts(shData.shorts);
          if (shData.summary) {
            setShortsSummary(shData.summary);
          }
        }
      } catch {
        // Silenciar errores transitorios de polling en vivo
      }
    }, 2500);
    return () => window.clearInterval(timer);
  }, [isLiveMonitoring, projectId]);

  // Refresco en vivo de estado social cuando el panel de redes está desplegado (ignorado en tests)
  useEffect(() => {
    const isTestEnv =
      (import.meta as unknown as { env?: { MODE?: string } }).env?.MODE === 'test';
    if (isTestEnv || !showSocialDetails) return;
    const timer = window.setInterval(async () => {
      try {
        const [shRes, qRes] = await Promise.all([
          fetch(buildProjectApiUrl('/api/shorts', projectId)),
          fetch('/api/queues'),
        ]);
        if (shRes.ok) {
          const shData: ShortsResponse = await shRes.json();
          setRenderedShorts(shData.shorts);
          if (shData.summary) {
            setShortsSummary(shData.summary);
          }
        }
        if (qRes.ok) {
          setQueues((await qRes.json()) as QueuesResponse);
        }
      } catch {
        // Silenciar errores transitorios de polling social
      }
    }, 8000);
    return () => window.clearInterval(timer);
  }, [showSocialDetails, projectId]);

  const applyCompletedYouTubeOAuth = useCallback(
    async (data: SocialPlatformVerifyResponse) => {
      setPendingYouTubeAuthUrl(null);
      setVerifyResults((prev) => ({ ...prev, youtube: data }));
      setActionState(data.connected ? 'success' : 'error');
      const retryCount = Number(data.retried_youtube_slots || 0);
      setFeedbackMessage(
        data.connected && retryCount > 0
          ? `YOUTUBE: ${data.status_label} · ${data.detail} Se está reintentando ${retryCount} subida(s) pendiente(s) en segundo plano.`
          : data.error
          ? String(data.error)
          : `YOUTUBE: ${data.status_label} · ${data.detail}`
      );
      if (data.connected) {
        if (retryCount > 0) {
          setShowSocialDetails(true);
        }
        await fetchAllData();
      }
    },
    [fetchAllData]
  );

  // Espera no bloqueante tras abrir Google OAuth en el navegador del usuario (postMessage + polling cada 2s)
  useEffect(() => {
    if (!pendingYouTubeAuthUrl) return;
    let cancelled = false;
    let inFlight = false;

    const checkOAuthStatus = async () => {
      if (cancelled || inFlight) return;
      inFlight = true;
      try {
        const res = await fetch('/api/social-accounts/youtube/oauth/status');
        if (!res.ok) return;
        const stData: SocialPlatformVerifyResponse = await res.json();
        if (cancelled) return;
        if (stData.oauth_state === 'completed') {
          await applyCompletedYouTubeOAuth(stData);
        } else if (stData.oauth_state === 'error') {
          setPendingYouTubeAuthUrl(null);
          setActionState('error');
          setFeedbackMessage(
            stData.error || stData.detail || 'No se completó la autorización OAuth de YouTube.'
          );
        }
      } catch {
        // Silenciar errores transitorios al verificar estado OAuth
      } finally {
        inFlight = false;
      }
    };

    const onWindowMessage = (evt: MessageEvent) => {
      if (evt?.data && (evt.data as { type?: string }).type === 'SHORTYT_YOUTUBE_OAUTH_DONE') {
        void checkOAuthStatus();
      }
    };

    window.addEventListener('message', onWindowMessage);
    const pollTimer = window.setInterval(() => {
      void checkOAuthStatus();
    }, 2000);

    return () => {
      cancelled = true;
      window.removeEventListener('message', onWindowMessage);
      window.clearInterval(pollTimer);
    };
  }, [pendingYouTubeAuthUrl, applyCompletedYouTubeOAuth]);

  // Abrir automáticamente el modal flotante cuando la generación de Shorts termina
  useEffect(() => {
    const currentJobKey = pipelineStatus?.job_id || 'completed_batch';
    const needsConfirm = Boolean(shortsSummary?.requires_schedule_confirmation);
    if (
      pipelineStatus?.status === 'COMPLETED' &&
      renderedShorts.length > 0 &&
      needsConfirm &&
      dismissedModalJobId !== currentJobKey
    ) {
      setIsScheduleModalOpen(true);
    }
  }, [
    pipelineStatus?.status,
    pipelineStatus?.job_id,
    renderedShorts.length,
    shortsSummary?.requires_schedule_confirmation,
    dismissedModalJobId,
  ]);

  // Acción 0: Cambiar apariencia Light / Dark (POST /api/settings/theme)
  const handleToggleTheme = async () => {
    const nextTheme: ThemeMode = themeMode === 'dark' ? 'light' : 'dark';
    setThemeMode(nextTheme);
    try {
      await fetch('/api/settings/theme', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme_mode: nextTheme }),
      });
    } catch {
      // Mantiene el cambio local incluso si falla la petición
    }
  };

  const syncProjectNameWithVideo = useCallback(
    async (rawVideoName: string): Promise<string> => {
      const candidateLabel = rawVideoName.trim();
      if (!candidateLabel) return projectId;

      if (projectId === 'default') {
        setProjectDisplayName(buildVideoDateProjectSlug(candidateLabel));
        return 'default';
      }

      const isActive =
        pipelineStatus?.status === 'RUNNING' ||
        pipelineStatus?.status === 'STARTED' ||
        pipelineStatus?.status === 'DISCOVERING';
      if (isActive || !isPlaceholderProjectId(projectId)) {
        return projectId;
      }

      try {
        const renameRes = await fetch('/api/project/rename', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            from_project_id: projectId,
            video_filename: candidateLabel,
          }),
        });
        if (renameRes.ok) {
          const renameData = (await renameRes.json()) as RenameProjectResponse;
          if (renameData.project_id) {
            setProjectId(renameData.project_id);
            setProjectDisplayName(renameData.project_name || renameData.project_id);
            try {
              const targetUrl = `${window.location.pathname}?project=${encodeURIComponent(renameData.project_id)}`;
              window.history.replaceState({}, '', targetUrl);
            } catch {
              // Silenciar si history.replaceState no está disponible
            }
            return renameData.project_id;
          }
        }
      } catch {
        // Conservar proyecto actual ante error de red no crítico
      }
      return projectId;
    },
    [pipelineStatus?.status, projectId]
  );

  // Carga directa desde el Explorador nativo del navegador por streaming local (POST /api/local-video/upload)
  const handleSelectLocalVideoFile = async (file: File) => {
    if (actionState === 'loading') return;
    if (!/\.(mp4|mov|mkv|avi|webm)$/i.test(file.name)) {
      setActionState('error');
      setFeedbackMessage(
        `Formato no soportado (${file.name}). Usa un archivo MP4, MOV, MKV, AVI o WEBM.`
      );
      return;
    }

    setSourceType('inbox');
    setActionState('loading');
    setActiveOperation('pick_local_video');
    setFeedbackMessage(`Cargando video local «${file.name}»...`);

    try {
      const res = await fetch('/api/local-video/upload', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/octet-stream',
          'X-File-Name': encodeURIComponent(file.name),
        },
        body: file,
      });
      if (!res.ok) {
        const errBody = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }
      const data: LocalVideoPickResponse = await res.json();
      if (data.cancelled || !data.file_path) {
        setActionState('idle');
        setFeedbackMessage(
          selectedVideo
            ? `Selección cancelada. Se mantiene el archivo: ${getVideoDisplayName(selectedVideo)}.`
            : 'Selección cancelada. Pulsa «Archivo Local» para elegir un video de tu PC.'
        );
        return;
      }

      hasAutoSelectedInboxRef.current = true;
      setSelectedVideo(data.file_path);
      setPickedVideoMeta(data);
      setSceneDataByRuleId({});
      setIsStudioOpen(false);
      setPreAnalyzeData(null);
      setInspectionReport(null);
      await syncProjectNameWithVideo(data.file_name || data.file_path);
      setActionState('success');
      setFeedbackMessage(
        `Video local cargado: ${data.file_name || getVideoDisplayName(data.file_path)} (${data.size_mb ?? 0} MB).`
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'No se pudo cargar el video local.';
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      setActiveOperation('none');
    }
  };

  // Acción 1: Inspeccionar Video (POST /api/inspect)
  const handleInspectVideo = async () => {
    if (!selectedVideo) {
      setActionState('error');
      setFeedbackMessage('Selecciona primero un archivo de video local mediante el botón Archivo Local.');
      return;
    }

    setActionState('loading');
    setActiveOperation('inspect');
    setFeedbackMessage(`Analizando potencial de ${getVideoDisplayName(selectedVideo)}...`);

    try {
      const res = await fetch('/api/inspect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ video_filename: selectedVideo }),
      });

      if (!res.ok) {
        const errBody = (await res.json()) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }

      const report: VideoInspectionReport = await res.json();
      setInspectionReport(report);
      setShortsPerVideo(Math.min(24, Math.max(1, report.recommended_shorts)));
      setActionState('success');
      setFeedbackMessage(
        `Inspección completada: ${report.resolution} a ${report.fps} FPS (${report.duration_formatted}). Se recomiendan ${report.recommended_shorts} Shorts.`
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Fallo al inspeccionar el video.';
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      setActiveOperation('none');
    }
  };

  const sanitizeCategoryRules = (rules: CategorySceneRule[]): CategorySceneRule[] =>
    rules.map((rule) => {
      const allowDual = rule.custom_boxes_manual && DUAL_BOX_LAYOUTS.includes(rule.layout_mode);
      const allowSingleCam = rule.custom_boxes_manual && rule.layout_mode === 'fullscreen';
      return {
        ...rule,
        custom_cam_box_norm: allowDual || allowSingleCam ? rule.custom_cam_box_norm : null,
        custom_content_box_norm: allowDual ? rule.custom_content_box_norm : null,
      };
    });

  const getSafeActiveRule = (rules: CategorySceneRule[], idx: number): CategorySceneRule => {
    const safeIdx = Math.min(Math.max(0, idx), Math.max(0, rules.length - 1));
    return rules[safeIdx] || buildFallbackSceneRules(sourceType, selectedVideo, youtubeUrl)[0];
  };

  const activeSceneRule = getSafeActiveRule(categoryRules, activeRuleIndex);
  const firstDetectedScene = Object.values(sceneDataByRuleId)[0] || null;
  const activeSceneData: SceneDetectResponse | null = isStudioOpen
    ? sceneDataByRuleId[activeSceneRule.rule_id] ||
      (activeSceneRule.frame_url
        ? {
            video_filename: activeSceneRule.scene_label || 'escena',
            resolution: firstDetectedScene?.resolution || '1280x720',
            width: firstDetectedScene?.width || 1280,
            height: firstDetectedScene?.height || 720,
            detected_layout: activeSceneRule.layout_mode,
            faces_detected: firstDetectedScene?.faces_detected ?? 1,
            cam_box_norm:
              activeSceneRule.custom_cam_box_norm ||
              (activeSceneRule.layout_mode === 'fullscreen'
                ? [0.28, 0.05, 0.44, 0.9]
                : [0.02, 0.35, 0.26, 0.35]),
            content_box_norm: activeSceneRule.custom_content_box_norm || [0.28, 0.05, 0.7, 0.9],
            frame_url: activeSceneRule.frame_url,
            timestamp_sec: activeSceneRule.sample_timestamp_sec ?? 0,
            duration_sec: preAnalyzeData?.duration_sec ?? firstDetectedScene?.duration_sec ?? null,
            frame_source: firstDetectedScene?.frame_source,
          }
        : firstDetectedScene)
    : null;

  const handleUpdateActiveRule = (patch: Partial<CategorySceneRule>) => {
    setCategoryRules((prev) => {
      const safeIdx = Math.min(Math.max(0, activeRuleIndex), Math.max(0, prev.length - 1));
      return prev.map((rule, idx) => (idx === safeIdx ? { ...rule, ...patch } : rule));
    });
  };

  const handleAddCategoryRule = () => {
    if (categoryRules.length >= 4) return;
    const existingNums = categoryRules
      .map((r) => Number(r.rule_id.replace(/^(?:rule_|scene_)/, '')))
      .filter((n) => Number.isFinite(n));
    const nextNum = (existingNums.length ? Math.max(...existingNums) : categoryRules.length) + 1;
    const newRule = createSceneRule(`scene_${nextNum}`, categoryRules.length, 25);
    setCategoryRules((prev) => [...prev, newRule]);
    setActiveRuleIndex(categoryRules.length);
  };

  const handleRemoveCategoryRule = (idxToRemove: number) => {
    if (categoryRules.length <= 1) return;
    const nextLen = categoryRules.length - 1;
    setCategoryRules((prev) => prev.filter((_, idx) => idx !== idxToRemove));
    setActiveRuleIndex((cur) => Math.min(cur, Math.max(0, nextLen - 1)));
  };

  // Drag & resize interactivo en Canvas Studio 16:9 sobre la regla activa
  useEffect(() => {
    if (!draggingTarget) return;
    const handlePointerMove = (ev: PointerEvent) => {
      const el = studioCanvasRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return;
      const dx = (ev.clientX - draggingTarget.startX) / rect.width;
      const dy = (ev.clientY - draggingTarget.startY) / rect.height;
      const [ox, oy, ow, oh] = draggingTarget.origBox;
      const minSize = 0.08;
      let nx = ox;
      let ny = oy;
      let nw = ow;
      let nh = oh;
      if (draggingTarget.mode === 'move') {
        nx = Math.max(0, Math.min(1 - ow, ox + dx));
        ny = Math.max(0, Math.min(1 - oh, oy + dy));
      } else if (draggingTarget.mode === 'resize_nw') {
        nx = Math.max(0, Math.min(ox + ow - minSize, ox + dx));
        ny = Math.max(0, Math.min(oy + oh - minSize, oy + dy));
        nw = ox + ow - nx;
        nh = oy + oh - ny;
      } else if (draggingTarget.mode === 'resize_ne') {
        ny = Math.max(0, Math.min(oy + oh - minSize, oy + dy));
        nw = Math.max(minSize, Math.min(1 - ox, ow + dx));
        nh = oy + oh - ny;
      } else if (draggingTarget.mode === 'resize_sw') {
        nx = Math.max(0, Math.min(ox + ow - minSize, ox + dx));
        nw = ox + ow - nx;
        nh = Math.max(minSize, Math.min(1 - oy, oh + dy));
      } else {
        nw = Math.max(minSize, Math.min(1 - ox, ow + dx));
        nh = Math.max(minSize, Math.min(1 - oy, oh + dy));
      }
      const nextBox: [number, number, number, number] = [
        Number(nx.toFixed(4)),
        Number(ny.toFixed(4)),
        Number(nw.toFixed(4)),
        Number(nh.toFixed(4)),
      ];
      setCategoryRules((prev) => {
        const safeIdx = Math.min(Math.max(0, activeRuleIndex), Math.max(0, prev.length - 1));
        return prev.map((rule, idx) => {
          if (idx !== safeIdx) return rule;
          const sceneDet = sceneDataByRuleId[rule.rule_id];
          const promotedLayout: LayoutMode =
            rule.layout_mode === 'auto'
              ? ((sceneDet?.detected_layout && sceneDet.detected_layout !== 'auto'
                  ? sceneDet.detected_layout
                  : 'split_streamer') as LayoutMode)
              : rule.layout_mode;
          const fallbackCam: [number, number, number, number] =
            rule.custom_cam_box_norm ||
            sceneDet?.cam_box_norm ||
            (promotedLayout === 'fullscreen' ? [0.28, 0.05, 0.44, 0.9] : [0.02, 0.68, 0.24, 0.28]);
          const fallbackContent: [number, number, number, number] =
            rule.custom_content_box_norm || sceneDet?.content_box_norm || [0.26, 0.02, 0.72, 0.96];
          return {
            ...rule,
            layout_mode: promotedLayout,
            custom_boxes_manual: true,
            custom_cam_box_norm: draggingTarget.box === 'cam' ? nextBox : fallbackCam,
            custom_content_box_norm:
              promotedLayout === 'fullscreen'
                ? null
                : draggingTarget.box === 'content'
                ? nextBox
                : fallbackContent,
          };
        });
      });
    };
    const handlePointerUp = () => setDraggingTarget(null);
    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
    };
  }, [draggingTarget, activeRuleIndex, sceneDataByRuleId]);

  const handleSetCustomBoxesManual = (manual: boolean) => {
    setCategoryRules((prev) => {
      const safeIdx = Math.min(Math.max(0, activeRuleIndex), Math.max(0, prev.length - 1));
      return prev.map((rule, idx) => {
        if (idx !== safeIdx) return rule;
        const sceneDet = sceneDataByRuleId[rule.rule_id];
        if (!manual) {
          return { ...rule, custom_boxes_manual: false };
        }
        const promotedLayout: LayoutMode =
          rule.layout_mode === 'auto'
            ? ((sceneDet?.detected_layout && sceneDet.detected_layout !== 'auto'
                ? sceneDet.detected_layout
                : 'split_streamer') as LayoutMode)
            : rule.layout_mode;
        return {
          ...rule,
          layout_mode: promotedLayout,
          custom_boxes_manual: true,
          custom_cam_box_norm:
            rule.custom_cam_box_norm ||
            sceneDet?.cam_box_norm ||
            (promotedLayout === 'fullscreen' ? [0.28, 0.05, 0.44, 0.9] : [0.02, 0.68, 0.24, 0.28]),
          custom_content_box_norm:
            promotedLayout === 'fullscreen'
              ? null
              : rule.custom_content_box_norm || sceneDet?.content_box_norm || [0.26, 0.02, 0.72, 0.96],
        };
      });
    });
  };

  // Studio: Detectar escena 16:9 (cámara + juego/contenido) en cualquier fotograma del video local o remoto
  const handleDetectScene = async (overrideTimestampSec?: number, preserveManualBoxes = false) => {
    if (sourceType === 'inbox' && !selectedVideo) {
      setActionState('error');
      setFeedbackMessage('Selecciona primero un video local en Archivo Local para abrir el Estudio 16:9.');
      return;
    }
    if (sourceType === 'youtube_url' && !youtubeUrl.trim()) {
      setActionState('error');
      setFeedbackMessage('Ingresa una URL de YouTube/Twitch válida para capturar un fotograma en el Estudio 16:9.');
      return;
    }
    const targetRule = getSafeActiveRule(categoryRules, activeRuleIndex);
    const targetRuleId = targetRule.rule_id;
    const requestedTs =
      typeof overrideTimestampSec === 'number' && Number.isFinite(overrideTimestampSec)
        ? Math.max(0, overrideTimestampSec)
        : typeof targetRule.sample_timestamp_sec === 'number'
        ? targetRule.sample_timestamp_sec
        : undefined;

    setActionState('loading');
    setActiveOperation('detect_scene');
    setFeedbackMessage(
      requestedTs !== undefined
        ? `Extrayendo fotograma real en ${Math.floor(requestedTs / 60)}:${String(Math.floor(requestedTs % 60)).padStart(2, '0')} para calibrar el Estudio 16:9...`
        : sourceType === 'inbox'
        ? `Detectando rostro y contenido en ${selectedVideo}...`
        : 'Extrayendo fotograma del video remoto para calibrar el Estudio 16:9...'
    );
    try {
      const res = await fetch('/api/scene/detect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_type: sourceType,
          video_filename: sourceType === 'inbox' ? selectedVideo : null,
          youtube_url: sourceType === 'youtube_url' ? youtubeUrl.trim() : null,
          ...(requestedTs !== undefined ? { timestamp_sec: requestedTs } : {}),
        }),
      });
      if (!res.ok) {
        const errBody = (await res.json()) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }
      const data: SceneDetectResponse = await res.json();
      setSceneDataByRuleId((prev) => ({ ...prev, [targetRuleId]: data }));
      setIsStudioOpen(true);
      const keepManual = preserveManualBoxes && targetRule.custom_boxes_manual;
      setCategoryRules((prev) =>
        prev.map((rule) =>
          rule.rule_id === targetRuleId
            ? {
                ...rule,
                frame_url: data.frame_url,
                sample_timestamp_sec: data.timestamp_sec ?? requestedTs ?? rule.sample_timestamp_sec,
                ...(keepManual
                  ? {}
                  : {
                      custom_cam_box_norm: data.cam_box_norm,
                      custom_content_box_norm: data.content_box_norm,
                      custom_boxes_manual: false,
                    }),
              }
            : rule
        )
      );
      setActionState('success');
      setFeedbackMessage(
        data.frame_source === 'thumbnail_fallback'
          ? `Portada cargada (${data.resolution}): ${data.faces_detected} rostro(s). Si es posible usa la línea de tiempo para elegir otro momento.`
          : `Fotograma capturado (${data.resolution}): ${data.faces_detected} rostro(s). Ajusta cajas libremente en el Estudio 16:9.`
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Fallo al detectar la escena.';
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      setActiveOperation('none');
    }
  };

  const handleToggleAllowedAccountCategory = (catKey: AccountCategoryKey) => {
    setAllowedAccountCategories((prev) => {
      if (prev.includes(catKey)) {
        return prev.length > 1 ? prev.filter((c) => c !== catKey) : prev;
      }
      return [...prev, catKey];
    });
  };

  // Perfil de Contenido: Guardar nuevo o actualizar perfil multi-escena existente
  const handleSaveContentProfile = async () => {
    const cleanName = profileNameInput.trim();
    if (!cleanName) {
      setActionState('error');
      setFeedbackMessage('Escribe un nombre para guardar el Perfil de Contenido (ej. CreadorStudio Live, Podcast Debate).');
      return;
    }
    const parsedKeywords = profileKeywordsInput
      .split(',')
      .map((kw) => kw.trim())
      .filter(Boolean);
    const scenesToSave = sanitizeCategoryRules(categoryRules).map((rule) => ({
      ...rule,
      category: rule.category || 'auto',
    }));
    const isUpdating = Boolean(selectedProfileId);

    setActionState('loading');
    setActiveOperation('save_profile');
    try {
      const endpoint = isUpdating ? `/api/content-profiles/${selectedProfileId}` : '/api/content-profiles';
      const method = isUpdating ? 'PUT' : 'POST';
      const res = await fetch(endpoint, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: cleanName,
          match_keywords: parsedKeywords,
          scenes: scenesToSave,
          auto_categorize_by_topic: autoCategorizeByTopic,
          allowed_account_categories: allowedAccountCategories,
        }),
      });
      if (!res.ok) {
        const errBody = (await res.json()) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }
      const saved: ContentProfileItem = await res.json();
      setContentProfiles((prev) => [saved, ...prev.filter((p) => p.id !== saved.id)]);
      setSelectedProfileId(String(saved.id));
      setProfileNameInput(saved.name);
      setProfileKeywordsInput(saved.match_keywords.join(', '));
      if (typeof saved.auto_categorize_by_topic === 'boolean') {
        setAutoCategorizeByTopic(saved.auto_categorize_by_topic);
      }
      if (Array.isArray(saved.allowed_account_categories) && saved.allowed_account_categories.length > 0) {
        setAllowedAccountCategories(saved.allowed_account_categories);
      }
      if (Array.isArray(saved.scenes) && saved.scenes.length > 0) {
        setCategoryRules(saved.scenes);
        setActiveRuleIndex(0);
      }
      setActionState('success');
      setFeedbackMessage(
        isUpdating
          ? `Perfil "${saved.name}" actualizado (${saved.scenes.length} escena(s)).`
          : `Perfil "${saved.name}" guardado para futuras detecciones automáticas.`
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al guardar el perfil de contenido.';
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      setActiveOperation('none');
    }
  };

  const handleSelectContentProfile = (profileIdValue: string) => {
    setSelectedProfileId(profileIdValue);
    if (!profileIdValue) {
      setProfileNameInput('');
      setProfileKeywordsInput('');
      setAutoCategorizeByTopic(true);
      setAllowedAccountCategories(Object.keys(socialHubConfig.categories));
      setActionState('idle');
      setFeedbackMessage('Modo Perfil Nuevo: asigna un nombre y guarda tus escenas cuando estén listas.');
      return;
    }
    const found = contentProfiles.find((p) => String(p.id) === profileIdValue);
    if (!found) return;
    setProfileNameInput(found.name);
    setProfileKeywordsInput(found.match_keywords.join(', '));
    setAutoCategorizeByTopic(
      typeof found.auto_categorize_by_topic === 'boolean' ? found.auto_categorize_by_topic : true
    );
      setAllowedAccountCategories(
      Array.isArray(found.allowed_account_categories) && found.allowed_account_categories.length > 0
        ? found.allowed_account_categories
        : Object.keys(socialHubConfig.categories)
    );
    if (Array.isArray(found.scenes) && found.scenes.length > 0) {
      setCategoryRules(found.scenes);
      setActiveRuleIndex(0);
    }
    setActionState('success');
    setFeedbackMessage(`Perfil "${found.name}" cargado (${found.scenes.length} escena(s)).`);
  };

  const handleDeleteContentProfile = async () => {
    if (!selectedProfileId) return;
    setActionState('loading');
    setActiveOperation('delete_profile');
    try {
      const res = await fetch(`/api/content-profiles/${selectedProfileId}`, { method: 'DELETE' });
      if (!res.ok) {
        const errBody = (await res.json()) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }
      setContentProfiles((prev) => prev.filter((p) => String(p.id) !== selectedProfileId));
      setSelectedProfileId('');
      setProfileNameInput(preAnalyzeData?.suggested_profile_name || '');
      setProfileKeywordsInput((preAnalyzeData?.suggested_keywords || []).join(', '));
      setActionState('success');
      setFeedbackMessage('Perfil de contenido eliminado correctamente.');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al eliminar perfil de contenido.';
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      setActiveOperation('none');
    }
  };

  const resolveTargetVideoLabel = () => {
    if (sourceType === 'youtube_url') {
      return (preAnalyzeData?.video_title || youtubeUrl).trim();
    }
    return (pickedVideoMeta?.file_name || selectedVideo).trim();
  };

  // Pre-Render Discovery: Escanear hasta 24 candidatos IA con contexto completo y reglas
  const handleDiscoverCandidates = async () => {
    const rulesToSend = sanitizeCategoryRules(categoryRules).map((rule) => ({
      ...rule,
      category: rule.category || 'auto',
    }));

    setActionState('loading');
    setActiveOperation('discover');
    setFeedbackMessage(`Escaneando el 100% del audio y contexto para extraer hasta ${shortsPerVideo} clips...`);
    try {
      const activeProjectId = await syncProjectNameWithVideo(resolveTargetVideoLabel());
      const res = await fetch('/api/pipeline/discover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_type: sourceType,
          video_filename: sourceType === 'inbox' ? selectedVideo : null,
          youtube_url: sourceType === 'youtube_url' ? youtubeUrl : null,
          download_section_start:
            sourceType === 'youtube_url' && downloadSectionStart.trim() ? downloadSectionStart.trim() : null,
          download_section_end:
            sourceType === 'youtube_url' && downloadSectionEnd.trim() ? downloadSectionEnd.trim() : null,
          shorts_per_video: shortsPerVideo,
          content_category: 'auto',
          auto_categorize_by_topic: autoCategorizeByTopic,
          allowed_account_categories: allowedAccountCategories,
          category_rules: rulesToSend,
          ...(activeProjectId !== 'default' ? { project_id: activeProjectId } : {}),
        }),
      });
      if (!res.ok) {
        const errBody = (await res.json()) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }
      const data: CandidatesResponse = await res.json();
      setDiscoveredCandidates(data.candidates);
      setSelectedCandidateIds(data.candidates.map((c) => c.candidate_id));
      setIsPreAnalyzeModalOpen(false);
      setActionState('success');
      setFeedbackMessage(`Descubrimiento completo: ${data.candidates.length} clips con contexto listos para elegir.`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al escanear clips IA.';
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      setActiveOperation('none');
    }
  };

  const handleRenderSelectedCandidates = async () => {
    if (selectedCandidateIds.length === 0) {
      setActionState('error');
      setFeedbackMessage('Marca al menos un clip candidato para renderizar.');
      return;
    }
    const rulesToSend = sanitizeCategoryRules(categoryRules);
    const leadRule = getSafeActiveRule(rulesToSend, activeRuleIndex);

    setActionState('loading');
    setActiveOperation('render_selected');
    setFeedbackMessage(`Renderizando ${selectedCandidateIds.length} clips seleccionados con estilo ${leadRule.subtitle_preset}...`);
    try {
      const res = await fetch('/api/pipeline/render-selected', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          candidate_ids: selectedCandidateIds,
          layout_mode: leadRule.layout_mode,
          cam_overlay_pos: leadRule.cam_overlay_pos,
          custom_cam_box_norm: leadRule.custom_cam_box_norm,
          custom_content_box_norm: leadRule.custom_content_box_norm,
          subtitle_preset: leadRule.subtitle_preset,
          subtitle_position: leadRule.subtitle_position,
          bgm_mood: 'desactivada',
          auto_categorize_by_topic: autoCategorizeByTopic,
          allowed_account_categories: allowedAccountCategories,
          category_rules: rulesToSend,
          ...(projectId !== 'default' ? { project_id: projectId } : {}),
        }),
      });
      if (!res.ok) {
        const errBody = (await res.json()) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }
      const data = (await res.json()) as { job_id: string; selected_count: number; message: string };
      setActionState('success');
      setFeedbackMessage(`Job #${data.job_id}: ${data.message}`);
      await fetchAllData();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al renderizar clips seleccionados.';
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      setActiveOperation('none');
    }
  };

  const handlePreviewCandidateCut = (startSec: number) => {
    if (sourceVideoRef.current) {
      sourceVideoRef.current.currentTime = startSec;
      void sourceVideoRef.current.play().catch(() => undefined);
    }
    setActionState('success');
    setFeedbackMessage(`Previsualizando origen en ${Math.floor(startSec / 60)}m ${Math.floor(startSec % 60)}s.`);
  };

  // Paso 1 al pulsar Generar: Pre-Análisis Multi-Categoría antes de editar Shorts
  const handleRequestPreAnalyze = async (e: React.FormEvent) => {
    e.preventDefault();
    if (actionState === 'loading') return;

    preAnalyzeAbortRef.current?.abort();
    const controller = new AbortController();
    preAnalyzeAbortRef.current = controller;

    setActionState('loading');
    setActiveOperation('pre_analyze');
    setFeedbackMessage('Analizando escenas y categorías del video para sugerir layouts y subtítulos...');

    try {
      const res = await fetch('/api/pipeline/pre-analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          source_type: sourceType,
          video_filename: sourceType === 'inbox' ? selectedVideo : null,
          youtube_url: sourceType === 'youtube_url' ? youtubeUrl : null,
          download_section_start:
            sourceType === 'youtube_url' && downloadSectionStart.trim() ? downloadSectionStart.trim() : null,
          download_section_end:
            sourceType === 'youtube_url' && downloadSectionEnd.trim() ? downloadSectionEnd.trim() : null,
          ...(projectId !== 'default' ? { project_id: projectId } : {}),
        }),
      });

      if (res.ok) {
        const data: PreAnalyzeResponse = await res.json();
        const nextRules =
          Array.isArray(data.category_rules) && data.category_rules.length > 0
            ? data.category_rules.map((rule) => ({ ...rule, category: rule.category || 'auto' }))
            : buildFallbackSceneRules(sourceType, selectedVideo, youtubeUrl);
        setPreAnalyzeData(data);
        setCategoryRules(nextRules);
        setActiveRuleIndex(0);
        setSceneDataByRuleId({});
        setIsStudioOpen(false);
        if (data.matched_profile_id != null) {
          const matched = contentProfiles.find((p) => p.id === data.matched_profile_id);
          setSelectedProfileId(String(data.matched_profile_id));
          setProfileNameInput(data.matched_profile_name || matched?.name || '');
          setProfileKeywordsInput(
            (matched?.match_keywords || data.suggested_keywords || []).join(', ')
          );
          setAutoCategorizeByTopic(
            typeof data.auto_categorize_by_topic === 'boolean'
              ? data.auto_categorize_by_topic
              : typeof matched?.auto_categorize_by_topic === 'boolean'
              ? matched.auto_categorize_by_topic
              : true
          );
          const resolvedCats =
            data.allowed_account_categories && data.allowed_account_categories.length > 0
              ? data.allowed_account_categories
              : matched?.allowed_account_categories && matched.allowed_account_categories.length > 0
              ? matched.allowed_account_categories
              : (['principales', 'gaming', 'clipping'] as AccountCategoryKey[]);
          setAllowedAccountCategories(resolvedCats);
        } else {
          setSelectedProfileId('');
          setProfileNameInput(data.suggested_profile_name || '');
          setProfileKeywordsInput((data.suggested_keywords || []).join(', '));
          setAutoCategorizeByTopic(
            typeof data.auto_categorize_by_topic === 'boolean' ? data.auto_categorize_by_topic : true
          );
          setAllowedAccountCategories(
            data.allowed_account_categories && data.allowed_account_categories.length > 0
              ? data.allowed_account_categories
              : ['principales', 'gaming', 'clipping']
          );
        }
        setIsPreAnalyzeModalOpen(true);
        setActionState('idle');
        setFeedbackMessage(
          data.matched_profile_name
            ? `Perfil reconocido: "${data.matched_profile_name}". Confirma las escenas y encuadres antes de generar.`
            : 'Pre-análisis listo: configura tu Perfil de Contenido multi-escena antes de generar.'
        );
        return;
      }

      const errBody = (await res.json().catch(() => ({}))) as { detail?: string };
      if (res.status === 404 && (!errBody.detail || errBody.detail === 'Not found')) {
        const fallbackRules = buildFallbackSceneRules(sourceType, selectedVideo, youtubeUrl);
        setPreAnalyzeData({
          source_type: sourceType,
          target: sourceType === 'inbox' ? selectedVideo : youtubeUrl,
          video_title: null,
          duration_sec: null,
          thumbnail_url: null,
          matched_profile_id: null,
          matched_profile_name: null,
          suggested_profile_name: '',
          suggested_keywords: [],
          is_hybrid_multicategory: fallbackRules.length > 1,
          analysis_mode: 'client_fallback',
          analysis_summary: 'Configura las escenas, encuadres 9:16 y subtítulos sugeridos antes de generar los Shorts.',
          category_rules: fallbackRules,
        });
        setCategoryRules(fallbackRules);
        setActiveRuleIndex(0);
        setSceneDataByRuleId({});
        setIsStudioOpen(false);
        setSelectedProfileId('');
        setProfileNameInput('');
        setProfileKeywordsInput('');
        setIsPreAnalyzeModalOpen(true);
        setActionState('idle');
        setFeedbackMessage('Revisa y confirma la configuración antes de iniciar la generación.');
        return;
      }

      throw new Error(errBody.detail || `Error HTTP ${res.status}`);
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        return;
      }
      const msg = err instanceof Error ? err.message : 'Error al pre-analizar el video.';
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      setActiveOperation('none');
    }
  };

  const handleClosePreAnalyzeModal = () => {
    preAnalyzeAbortRef.current?.abort();
    setIsPreAnalyzeModalOpen(false);
    setSceneDataByRuleId({});
    setIsStudioOpen(false);
  };

  // Paso 2 Confirmar desde Modal: Generar Shorts con perfil multi-escena (POST /api/pipeline/process)
  const handleConfirmStartPipeline = async () => {
    const rulesToSend = sanitizeCategoryRules(categoryRules).map((rule) => ({
      ...rule,
      category: rule.category || 'auto',
    }));
    const leadRule = getSafeActiveRule(rulesToSend, activeRuleIndex);

    setActionState('loading');
    setActiveOperation('process');
    setFeedbackMessage('Iniciando pipeline de transcripción, detección de escenas y renderizado 9:16...');

    try {
      const activeProjectId = await syncProjectNameWithVideo(resolveTargetVideoLabel());
      const payload = {
        source_type: sourceType,
        video_filename: sourceType === 'inbox' ? selectedVideo : null,
        youtube_url: sourceType === 'youtube_url' ? youtubeUrl : null,
        download_section_start:
          sourceType === 'youtube_url' && downloadSectionStart.trim() ? downloadSectionStart.trim() : null,
        download_section_end:
          sourceType === 'youtube_url' && downloadSectionEnd.trim() ? downloadSectionEnd.trim() : null,
        content_category: 'auto',
        shorts_per_video: shortsPerVideo,
        layout_mode: leadRule.layout_mode,
        bgm_mood: 'desactivada',
        subtitle_preset: leadRule.subtitle_preset,
        subtitle_position: leadRule.subtitle_position,
        cam_overlay_pos: leadRule.cam_overlay_pos,
        custom_cam_box_norm: leadRule.custom_cam_box_norm,
        custom_content_box_norm: leadRule.custom_content_box_norm,
        auto_categorize_by_topic: autoCategorizeByTopic,
        allowed_account_categories: allowedAccountCategories,
        category_rules: rulesToSend,
        ...(activeProjectId !== 'default' ? { project_id: activeProjectId } : {}),
      };

      const res = await fetch('/api/pipeline/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errBody = (await res.json()) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }

      const startData: ProcessStartResponse = await res.json();
      setIsPreAnalyzeModalOpen(false);
      setActionState('success');
      setFeedbackMessage(
        `Job #${startData.job_id} iniciado (${startData.status}) para ${startData.target || 'video seleccionado'}.`
      );
      await fetchAllData();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al iniciar el procesamiento.';
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      setActiveOperation('none');
    }
  };

  // Acción 3: Limpiar Temporales (POST /api/cleanup)
  const handleDiskCleanup = async () => {
    setActionState('loading');
    setActiveOperation('cleanup');
    setFeedbackMessage('Limpiando archivos temporales en ./processing/ e ig_ready_8m...');

    try {
      const res = await fetch(buildProjectApiUrl('/api/cleanup', projectId), { method: 'POST' });
      if (!res.ok) {
        const errBody = (await res.json()) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }

      const data: CleanupResponse = await res.json();
      setDiskSpace(data.disk_space);
      setActionState('success');
      setFeedbackMessage(
        `Mantenimiento completado: ${data.deleted_files} archivos temporales eliminados (${data.mb_freed} MB liberados).`
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al limpiar archivos temporales.';
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      setActiveOperation('none');
    }
  };

  // Acción 4: Cancelar Proceso en Curso (POST /api/pipeline/cancel)
  const handleCancelPipeline = async () => {
    setActionState('loading');
    setActiveOperation('cancel_pipeline');
    setFeedbackMessage('Cancelando proceso activo de generación de Shorts...');

    try {
      const res = await fetch(buildProjectApiUrl('/api/pipeline/cancel', projectId), { method: 'POST' });
      if (!res.ok) {
        const errBody = (await res.json()) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }
      const data = (await res.json()) as { status: string; pipeline_status?: PipelineStatus };
      if (data.pipeline_status) {
        setPipelineStatus(data.pipeline_status);
      }
      setActionState('success');
      setFeedbackMessage('Proceso de generación cancelado correctamente.');
      await fetchAllData();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al cancelar el proceso.';
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      setActiveOperation('none');
    }
  };

  // Acción 5: Cancelar un Short Individual (DELETE /api/shorts/{short_rel_path})
  const handleCancelSingleShort = async (item: RenderedShortItem) => {
    const relPath =
      item.relative_path || (item.folder ? `${item.folder}/${item.filename}` : item.filename);
    const encodedPath = relPath
      .split('/')
      .map((part) => encodeURIComponent(part))
      .join('/');

    setActionState('loading');
    setActiveOperation('cancel_short');
    setFeedbackMessage(`Cancelando Short ${item.filename}...`);

    try {
      const res = await fetch(`/api/shorts/${encodedPath}`, { method: 'DELETE' });
      if (!res.ok) {
        const errBody = (await res.json()) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }
      if (activeShortPlayer?.filename === item.filename) {
        setActiveShortPlayer(null);
      }
      setRenderedShorts((prev) => prev.filter((s) => s.filename !== item.filename));
      setActionState('success');
      setFeedbackMessage(`Short ${item.filename} cancelado y eliminado de las colas.`);
      await fetchAllData();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al cancelar el Short.';
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      setActiveOperation('none');
    }
  };

  // Acción 6: Cancelar Todos los Shorts (DELETE /api/shorts)
  const handleCancelAllShorts = async () => {
    setActionState('loading');
    setActiveOperation('cancel_all');
    setFeedbackMessage('Cancelando todos los Shorts renderizados y limpiando colas...');

    try {
      const res = await fetch(buildProjectApiUrl('/api/shorts', projectId), { method: 'DELETE' });
      if (!res.ok) {
        const errBody = (await res.json()) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }
      const data = (await res.json()) as { canceled_count: number };
      setActiveShortPlayer(null);
      setRenderedShorts([]);
      setActionState('success');
      setFeedbackMessage(`${data.canceled_count} Shorts cancelados correctamente.`);
      await fetchAllData();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al cancelar los Shorts.';
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      setActiveOperation('none');
    }
  };

  // Acción 6B: Abrir Nuevo Proyecto en Ventana Independiente (POST /api/project/new)
  const handleNewProject = async () => {
    const newProjectId = generateIndependentProjectId();
    const targetUrl = `${window.location.origin}${window.location.pathname}?project=${encodeURIComponent(newProjectId)}`;
    const openedWin = typeof window.open === 'function' ? window.open(targetUrl, '_blank') : null;

    setActionState('loading');
    setActiveOperation('new_project');
    setFeedbackMessage('Abriendo nuevo proyecto en ventana independiente...');

    try {
      const res = await fetch('/api/project/new', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: 'independent',
          project_id: newProjectId,
          from_project_id: projectId,
        }),
      });
      if (!res.ok) {
        const errBody = (await res.json()) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }

      setActionState('success');
      setFeedbackMessage(
        openedWin
          ? 'Nuevo proyecto abierto en una ventana independiente. Este proyecto sigue intacto.'
          : `Proyecto ${newProjectId} creado. Ábrelo en ${targetUrl}`
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al abrir un nuevo proyecto independiente.';
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      setActiveOperation('none');
    }
  };

  // Acción 7: Programar lote por plataforma y distribuir en YouTube, Instagram, TikTok y Facebook
  const handleScheduleBatch = async (e: React.FormEvent) => {
    e.preventDefault();
    setActionState('loading');
    setActiveOperation('schedule_batch');
    setFeedbackMessage('Programando Shorts en YouTube, Instagram Reels, TikTok y Facebook...');

    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 45000);

    try {
      const res = await fetch('/api/shorts/schedule', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          youtube_start_time: youtubeScheduleTime,
          instagram_start_time: instagramScheduleTime,
          tiktok_start_time: tiktokScheduleTime,
          interval_minutes: scheduleIntervalMinutes,
          auto_upload_positive_to_youtube: true,
          ...(projectId !== 'default' ? { project_id: projectId } : {}),
        }),
      });
      if (!res.ok) {
        const errBody = (await res.json()) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }
      const data = (await res.json()) as {
        scheduled_count: number;
        youtube_uploaded_count: number;
        youtube_error?: string | null;
        summary?: ShortsBatchSummary;
        shorts?: RenderedShortItem[];
      };
      if (data.shorts) {
        setRenderedShorts(data.shorts);
      }
      if (data.summary) {
        setShortsSummary(data.summary);
      }
      setDismissedModalJobId(pipelineStatus?.job_id || 'completed_batch');
      setIsScheduleModalOpen(false);
      if (data.youtube_error) {
        setShowSocialDetails(true);
        setActionState('error');
        setFeedbackMessage(
          `Programación confirmada para ${data.scheduled_count} Shorts. Atención YouTube: ${data.youtube_error}`
        );
      } else {
        setActionState('success');
        setFeedbackMessage(
          `Programación confirmada para ${data.scheduled_count} Shorts (${data.youtube_uploaded_count} subidos automáticamente a YouTube).`
        );
      }
      await fetchAllData();
    } catch (err) {
      const msg =
        err instanceof DOMException && err.name === 'AbortError'
          ? 'La programación tardó demasiado; revisa Cuentas & APIs y vuelve a intentar.'
          : err instanceof Error
          ? err.message
          : 'Error al programar los Shorts.';
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      window.clearTimeout(timeoutId);
      setActiveOperation('none');
    }
  };

  // Exclusión mutua global de reproducción
  useEffect(() => {
    const onGlobalPlay = (evt: Event) => {
      const target = evt.target;
      if (target instanceof HTMLVideoElement) {
        pauseAllVideosExcept(target);
      }
    };
    document.addEventListener('play', onGlobalPlay, true);
    return () => {
      document.removeEventListener('play', onGlobalPlay, true);
    };
  }, []);

  // Arrastrar / redimensionar cajas del Editor Post-Previsualización sobre el canvas 16:9
  useEffect(() => {
    if (!reeditDragging) return;
    const handleMove = (evt: PointerEvent | MouseEvent) => {
      const canvasEl = reeditCanvasRef.current;
      if (!canvasEl) return;
      const rect = canvasEl.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return;
      const dx = (evt.clientX - reeditDragging.startX) / rect.width;
      const dy = (evt.clientY - reeditDragging.startY) / rect.height;
      const [ox, oy, ow, oh] = reeditDragging.origBox;
      let nextBox: [number, number, number, number];
      if (reeditDragging.mode === 'move') {
        const nx = clampNorm01(ox + dx, 0, Math.max(0, 1 - ow));
        const ny = clampNorm01(oy + dy, 0, Math.max(0, 1 - oh));
        nextBox = [nx, ny, ow, oh];
      } else {
        const nw = clampNorm01(ow + dx, 0.1, 1 - ox);
        const nh = clampNorm01(oh + dy, 0.1, 1 - oy);
        nextBox = [ox, oy, nw, nh];
      }
      if (reeditDragging.target === 'cam') {
        setReeditCamBox(nextBox);
      } else {
        setReeditContentBox(nextBox);
      }
    };
    const handleUp = () => {
      setReeditDragging(null);
    };
    window.addEventListener('pointermove', handleMove);
    window.addEventListener('pointerup', handleUp);
    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleUp);
    return () => {
      window.removeEventListener('pointermove', handleMove);
      window.removeEventListener('pointerup', handleUp);
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
    };
  }, [reeditDragging]);

  const startFloatingDrag = (clientX: number, clientY: number) => {
    floatingDragRef.current = {
      startX: clientX,
      startY: clientY,
      origX: floatingOffset.x,
      origY: floatingOffset.y,
    };
    const onMove = (ev: PointerEvent | MouseEvent) => {
      const ref = floatingDragRef.current;
      if (!ref) return;
      setFloatingOffset({
        x: ref.origX + (ev.clientX - ref.startX),
        y: ref.origY + (ev.clientY - ref.startY),
      });
    };
    const onUp = () => {
      floatingDragRef.current = null;
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  const openFloatingPlayer = (item: RenderedShortItem) => {
    pauseAllVideosExcept(null);
    setFloatingOffset({ x: 0, y: 0 });
    setActiveShortPlayer(item);
  };

  const getShortScheduleValue = (item: RenderedShortItem, idx = 0): string => {
    const key = item.relative_path || item.filename;
    if (shortScheduleTimes[key]) {
      return shortScheduleTimes[key];
    }
    return formatUtcToAstDateTimeLocal(item.publish_at_utc, idx + 1);
  };

  const updateShortScheduleValue = (item: RenderedShortItem, val: string) => {
    const k = item.relative_path || item.filename;
    setShortScheduleTimes((prev) => ({ ...prev, [k]: val }));
  };

  const handleApplyReeditPreset = (modeValue: LayoutMode) => {
    setReeditLayoutMode(modeValue);
    const presetBoxes = SHORT_REEDIT_PRESET_BOXES[modeValue] || SHORT_REEDIT_PRESET_BOXES.split_streamer;
    setReeditCamBox([...presetBoxes.cam]);
    setReeditContentBox([...presetBoxes.content]);
  };

  const handleOpenShortLayoutEditor = async (item: RenderedShortItem) => {
    const relPath = item.relative_path || item.filename;
    const baseDuration = Number(item.duration_sec || 30);
    pauseAllVideosExcept(null);
    setActionState('loading');
    setActiveOperation('load_short_editor');
    setReeditShort(item);
    setReeditScene(null);
    setReeditLayoutMode((item.layout_used as LayoutMode) || 'split_streamer');
    setReeditCamPos(item.cam_overlay_pos || 'top_right');
    setReeditSubPreset(item.subtitle_preset || 'hormozi_pop');
    setReeditSubPos(item.subtitle_position || 'auto');
    setReeditTrimStart(0);
    setReeditTrimEnd(baseDuration);
    setReeditMinTrim(0);
    setReeditMaxTrim(baseDuration + 30);
    setReeditMediaUrl(item.video_url || null);
    if (item.custom_cam_box_norm && item.custom_cam_box_norm.length === 4) {
      setReeditCamBox(item.custom_cam_box_norm);
    }
    if (item.custom_content_box_norm && item.custom_content_box_norm.length === 4) {
      setReeditContentBox(item.custom_content_box_norm);
    }
    setFeedbackMessage(`Cargando fotograma y zonas de ${item.filename}...`);

    try {
      const res = await fetch('/api/shorts/scene-detect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ short_rel_path: relPath }),
      });
      if (!res.ok) {
        const errBody = (await res.json()) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }
      const data = (await res.json()) as ShortSceneDetectResponse;
      setReeditScene(data);
      setReeditLayoutMode(
        (data.current_layout as LayoutMode) || (data.detected_layout as LayoutMode) || 'split_streamer'
      );
      setReeditCamPos(data.cam_overlay_pos || 'top_right');
      setReeditSubPreset(data.subtitle_preset || 'hormozi_pop');
      setReeditSubPos(data.subtitle_position || 'auto');
      setReeditCamBox(data.cam_box_norm);
      setReeditContentBox(data.content_box_norm);
      const nextStart = typeof data.trim_start_sec === 'number' ? data.trim_start_sec : 0;
      const nextEnd =
        typeof data.trim_end_sec === 'number'
          ? data.trim_end_sec
          : typeof data.duration_sec === 'number'
          ? data.duration_sec
          : baseDuration;
      setReeditTrimStart(nextStart);
      setReeditTrimEnd(nextEnd);
      setReeditMinTrim(typeof data.min_trim_sec === 'number' ? data.min_trim_sec : 0);
      setReeditMaxTrim(typeof data.max_trim_sec === 'number' ? data.max_trim_sec : nextEnd);
      setReeditMediaUrl(data.edit_media_url || item.video_url || null);
      setActionState('success');
      setFeedbackMessage(`Editor de layout y duración abierto para ${item.filename}.`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al analizar escena del Short.';
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      setActiveOperation('none');
    }
  };

  const handleRerenderShort = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!reeditShort) return;
    const relPath = reeditShort.relative_path || reeditShort.filename;
    const editedFilename = reeditShort.filename;
    setActionState('loading');
    setActiveOperation('rerender_short');
    setFeedbackMessage(`Re-renderizando ${editedFilename} con layout "${reeditLayoutMode}"...`);

    try {
      const res = await fetch('/api/shorts/rerender', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          short_rel_path: relPath,
          layout_mode: reeditLayoutMode,
          cam_overlay_pos: reeditCamPos,
          custom_cam_box_norm: reeditCamBox,
          custom_content_box_norm: reeditContentBox,
          subtitle_preset: reeditSubPreset,
          subtitle_position: reeditSubPos,
          trim_start_sec: reeditTrimStart,
          trim_end_sec: reeditTrimEnd,
        }),
      });
      if (!res.ok) {
        const errBody = (await res.json()) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }
      const data = (await res.json()) as {
        rerendered: boolean;
        short?: RenderedShortItem | null;
        shorts?: RenderedShortItem[];
      };
      const cacheStamp = Date.now();
      setRerenderVersions((prev) => ({
        ...prev,
        [relPath]: cacheStamp,
        [editedFilename]: cacheStamp,
      }));
      if (data.shorts) {
        setRenderedShorts(data.shorts);
      }
      if (data.short && activeShortPlayer && activeShortPlayer.filename === data.short.filename) {
        setActiveShortPlayer(data.short);
      }
      setReeditShort(null);
      setActionState('success');
      setFeedbackMessage(`Short ${editedFilename} actualizado con el nuevo layout (sin música de fondo).`);
      await fetchAllData();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al re-renderizar el Short.';
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      setActiveOperation('none');
    }
  };

  const handleScheduleSingleShort = async (item: RenderedShortItem, idx = 0) => {
    const relPath = item.relative_path || item.filename;
    const chosenTime = getShortScheduleValue(item, idx);
    setActionState('loading');
    setActiveOperation('schedule_single');
    setFeedbackMessage(`Programando ${item.filename} para ${chosenTime}...`);

    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 45000);

    try {
      const res = await fetch('/api/shorts/schedule-single', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          short_rel_path: relPath,
          scheduled_time: chosenTime,
          upload_to_youtube: true,
        }),
      });
      if (!res.ok) {
        const errBody = (await res.json()) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }
      const data = (await res.json()) as {
        scheduled: boolean;
        filename: string;
        scheduled_ast: string;
        youtube_error?: string | null;
        short?: RenderedShortItem | null;
        shorts?: RenderedShortItem[];
        summary?: ShortsBatchSummary;
      };
      if (data.shorts) {
        setRenderedShorts(data.shorts);
      }
      if (data.summary) {
        setShortsSummary(data.summary);
      }
      if (data.short && activeShortPlayer && activeShortPlayer.filename === data.short.filename) {
        setActiveShortPlayer(data.short);
      }
      if (data.youtube_error) {
        setShowSocialDetails(true);
        setActionState('error');
        setFeedbackMessage(
          `Short ${data.filename} programado para ${data.scheduled_ast}. Atención YouTube: ${data.youtube_error}`
        );
      } else {
        setActionState('success');
        setFeedbackMessage(`Short ${data.filename} programado para ${data.scheduled_ast}.`);
      }
      await fetchAllData();
    } catch (err) {
      const msg =
        err instanceof DOMException && err.name === 'AbortError'
          ? 'La programación tardó demasiado; revisa Cuentas & APIs y vuelve a intentar.'
          : err instanceof Error
          ? err.message
          : 'Error al programar fecha y hora del Short.';
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      window.clearTimeout(timeoutId);
      setActiveOperation('none');
    }
  };

  const handleToggleShortCategory = async (
    item: RenderedShortItem,
    nextCategories: AccountCategoryKey[]
  ) => {
    const relPath = item.relative_path || item.filename;
    setActionState('loading');
    setActiveOperation('update_short_categories');
    setFeedbackMessage(`Actualizando categorías de ${item.filename}...`);

    try {
      const res = await fetch('/api/shorts/categories', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          short_rel_path: relPath,
          account_categories: nextCategories,
        }),
      });
      if (!res.ok) {
        const errBody = (await res.json()) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }
      const data = (await res.json()) as {
        updated: boolean;
        account_categories: AccountCategoryKey[];
        short?: RenderedShortItem | null;
        shorts?: RenderedShortItem[];
      };
      if (data.shorts) {
        setRenderedShorts(data.shorts);
      } else {
        setRenderedShorts((prev) =>
          prev.map((s) =>
            (s.relative_path || s.filename) === relPath
              ? { ...s, account_categories: data.account_categories }
              : s
          )
        );
      }
      if (data.short && activeShortPlayer && activeShortPlayer.filename === data.short.filename) {
        setActiveShortPlayer(data.short);
      }
      setActionState('success');
      setFeedbackMessage(
        `Short ${item.filename} redirigido a: ${data.account_categories.join(', ')}.`
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al actualizar categorías del Short.';
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      setActiveOperation('none');
    }
  };

  const handleSaveSocialHubConfig = async () => {
    setActionState('loading');
    setActiveOperation('save_social_hub');
    setFeedbackMessage('Guardando cuentas por categoría y credenciales de APIs...');

    try {
      const res = await fetch('/api/social-accounts', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(socialHubConfig),
      });
      if (!res.ok) {
        const errBody = (await res.json()) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }
      const saved: SocialHubConfigResponse = await res.json();
      setSocialHubConfig(saved);
      setActionState('success');
      setFeedbackMessage('Hub de Cuentas y credenciales de APIs guardado correctamente.');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al guardar configuración del Hub Social.';
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      setActiveOperation('none');
    }
  };

  const handleVerifySocialPlatform = async (platform: SocialPlatformKey) => {
    setActionState('loading');
    setActiveOperation('verify_social_platform');
    setVerifyingPlatform(platform);
    setFeedbackMessage(`Verificando conexión de API para ${platform}...`);

    try {
      const res = await fetch('/api/social-accounts/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ platform }),
      });
      if (!res.ok) {
        const errBody = (await res.json()) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }
      const data: SocialPlatformVerifyResponse = await res.json();
      setVerifyResults((prev) => ({ ...prev, [platform]: data }));
      setActionState(data.connected ? 'success' : 'idle');
      setFeedbackMessage(`${platform.toUpperCase()}: ${data.status_label} · ${data.detail}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : `Error al probar API de ${platform}.`;
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      setVerifyingPlatform(null);
      setActiveOperation('none');
    }
  };

  const handleAuthorizeYouTubeOAuth = async () => {
    setActionState('loading');
    setActiveOperation('authorize_youtube_oauth');
    setFeedbackMessage('Preparando acceso de Google OAuth 2.0 en tu navegador...');

    try {
      let res = await fetch('/api/social-accounts/youtube/oauth/start', {
        method: 'POST',
      });
      if (res.status === 404) {
        res = await fetch('/api/social-accounts/youtube/authorize', {
          method: 'POST',
        });
      }
      if (!res.ok) {
        const errBody = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }
      const data: SocialPlatformVerifyResponse = await res.json();
      if (data.oauth_state === 'pending' && data.auth_url) {
        setPendingYouTubeAuthUrl(data.auth_url);
        setActionState('idle');
        if (typeof window !== 'undefined' && typeof window.open === 'function') {
          try {
            window.open(data.auth_url, '_blank');
          } catch {
            // Si el navegador bloquea popup, el usuario dispone del enlace directo Abrir Google OAuth ↗
          }
        }
        return;
      }
      await applyCompletedYouTubeOAuth(data);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'No se pudo autorizar YouTube OAuth.';
      setPendingYouTubeAuthUrl(null);
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      setActiveOperation('none');
    }
  };

  const handleCancelYouTubeOAuth = async () => {
    setPendingYouTubeAuthUrl(null);
    try {
      await fetch('/api/social-accounts/youtube/oauth/cancel', { method: 'POST' });
    } catch {
      // Silenciar errores de red al cancelar espera OAuth
    }
  };

  const renderedFileSet = new Set(renderedShorts.map((s) => s.filename));
  const pendingTikTokRowIds = queues.tiktok_queue
    .filter((entry) => {
      const st = String(entry.status || '').toUpperCase();
      if (st !== 'PENDING' && st !== 'INBOX_DRAFT' && st !== 'FAILED') return false;
      const bname = String(entry.video_path || '')
        .replace(/\\/g, '/')
        .split('/')
        .pop();
      return Boolean(bname && renderedFileSet.has(bname));
    })
    .map((entry) => entry.id);

  const handleDispatchTikTokStudio = async () => {
    if (pendingTikTokRowIds.length === 0) return;
    const confirmed =
      typeof window !== 'undefined' && typeof window.confirm === 'function'
        ? window.confirm(
            `Hay ${pendingTikTokRowIds.length} entrega(s) pendientes o en borrador de TikTok.\n\n¿Estás desocupado ahora para dar permiso a Short YT de usar Brave y subirlas/programarlas en TikTok Studio Web?`
          )
        : false;
    if (!confirmed) return;

    setActionState('loading');
    setActiveOperation('dispatch_tiktok_studio');
    setFeedbackMessage(
      `Abriendo TikTok Studio en Brave para despachar ${pendingTikTokRowIds.length} entrega(s)...`
    );
    try {
      const res = await fetch('/api/social-accounts/tiktok/studio-dispatch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_permission_granted: true,
          row_ids: pendingTikTokRowIds,
        }),
      });
      if (!res.ok) {
        const errBody = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }
      const data = (await res.json()) as { dispatched?: boolean; count?: number; detail?: string };
      setShowSocialDetails(true);
      setActionState('success');
      setFeedbackMessage(
        data.detail || `Despacho en Brave para TikTok Studio iniciado (${data.count || 0} entrega(s)).`
      );
      await fetchAllData();
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : 'No se pudo iniciar el despacho de TikTok Studio.';
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      setActiveOperation('none');
    }
  };

  const handleCreateSocialCategory = async (payload: {
    label: string;
    description: string;
    topic_keywords: string[];
  }): Promise<string | null> => {
    setActionState('loading');
    setActiveOperation('create_social_category');
    setFeedbackMessage(`Creando categoría "${payload.label}"...`);

    try {
      const res = await fetch('/api/social-accounts/categories', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const errBody = (await res.json()) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }
      const data = (await res.json()) as SocialHubConfigResponse & {
        created?: { key?: string; label?: string };
      };
      if (data.categories && data.api_settings) {
        setSocialHubConfig({ categories: data.categories, api_settings: data.api_settings });
      }
      const createdKey = data.created?.key || null;
      if (createdKey) {
        setAllowedAccountCategories((prev) =>
          prev.includes(createdKey) ? prev : [...prev, createdKey]
        );
      }
      setActionState('success');
      setFeedbackMessage(`Categoría "${data.created?.label || payload.label}" creada correctamente.`);
      return createdKey;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al crear categoría de cuentas.';
      setActionState('error');
      setFeedbackMessage(msg);
      return null;
    } finally {
      setActiveOperation('none');
    }
  };

  const handleDeleteSocialCategory = async (catKey: string) => {
    setActionState('loading');
    setActiveOperation('delete_social_category');
    setFeedbackMessage(`Eliminando categoría "${catKey}"...`);

    try {
      const res = await fetch(`/api/social-accounts/categories/${encodeURIComponent(catKey)}`, {
        method: 'DELETE',
      });
      if (!res.ok) {
        const errBody = (await res.json()) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }
      const data = (await res.json()) as SocialHubConfigResponse;
      if (data.categories && data.api_settings) {
        setSocialHubConfig({ categories: data.categories, api_settings: data.api_settings });
      }
      if (galleryFilter === catKey) {
        setGalleryFilter('all');
      }
      setAllowedAccountCategories((prev) => {
        const next = prev.filter((c) => c !== catKey);
        return next.length > 0 ? next : Object.keys(data.categories || {});
      });
      setActionState('success');
      setFeedbackMessage(`Categoría "${catKey}" eliminada correctamente.`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al eliminar categoría de cuentas.';
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      setActiveOperation('none');
    }
  };

  const categoryOptions = getHubCategoryOptions(socialHubConfig);

  const computedOroCount =
    shortsSummary?.oro_count ?? renderedShorts.filter((s) => s.tier === 'Oro').length;
  const computedPlataCount =
    shortsSummary?.plata_count ?? renderedShorts.filter((s) => s.tier === 'Plata').length;
  const computedMehCount =
    shortsSummary?.meh_count ?? renderedShorts.filter((s) => s.tier === 'Meh').length;
  const computedYoutubeEligibleCount =
    shortsSummary?.youtube_eligible_count ??
    renderedShorts.filter((s) => s.eligible_for_youtube).length;

  const isBusy = actionState === 'loading';

  const activePlayerKey = activeShortPlayer
    ? activeShortPlayer.relative_path || activeShortPlayer.filename
    : '';
  const activePlayerVersion = activeShortPlayer
    ? rerenderVersions[activePlayerKey] || rerenderVersions[activeShortPlayer.filename]
    : undefined;

  const handleToggleSelectShort = (item: RenderedShortItem) => {
    const key = getShortSelectionKey(item);
    setSelectedShortKeys((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
  };

  const handleToggleSelectAllVisible = (visibleItems: RenderedShortItem[]) => {
    const visibleKeys = visibleItems.map(getShortSelectionKey);
    if (visibleKeys.length === 0) return;
    const allSelected = visibleKeys.every((k) => selectedShortKeys.includes(k));
    if (allSelected) {
      setSelectedShortKeys((prev) => prev.filter((k) => !visibleKeys.includes(k)));
    } else {
      setSelectedShortKeys((prev) => Array.from(new Set([...prev, ...visibleKeys])));
    }
  };

  const handleDownloadShorts = async (
    targetItems: RenderedShortItem[],
    mode: 'all' | 'selected'
  ) => {
    if (targetItems.length === 0) return;
    const relPaths = targetItems.map(getShortSelectionKey);
    setActionState('loading');
    setActiveOperation('download_shorts');
    setFeedbackMessage(
      mode === 'selected'
        ? `Preparando descarga de ${targetItems.length} Short(s) seleccionado(s)...`
        : `Preparando descarga de los ${targetItems.length} Short(s)...`
    );

    try {
      const res = await fetch('/api/shorts/download-bundle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...(projectId !== 'default' ? { project_id: projectId } : {}),
          short_rel_paths: relPaths,
        }),
      });
      if (!res.ok) {
        const errBody = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }
      const disp = res.headers.get('Content-Disposition') || '';
      const fnMatch = disp.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
      const downloadName = fnMatch?.[1]
        ? decodeURIComponent(fnMatch[1])
        : targetItems.length === 1
        ? targetItems[0].filename
        : 'Shorts.zip';

      const blob = await res.blob();
      if (typeof URL.createObjectURL === 'function') {
        const blobUrl = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = blobUrl;
        anchor.download = downloadName;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        setTimeout(() => {
          if (typeof URL.revokeObjectURL === 'function') {
            URL.revokeObjectURL(blobUrl);
          }
        }, 1000);
      }

      setActionState('success');
      setFeedbackMessage(`Descarga iniciada: ${downloadName}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Error al descargar Shorts.';
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      setActiveOperation('none');
    }
  };

  const handleStartLiveMonitor = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanedUrl = liveStreamUrl.trim();
    if (!cleanedUrl) {
      setActionState('error');
      setFeedbackMessage('Ingresa una URL válida de transmisión en vivo.');
      return;
    }
    setActionState('loading');
    setActiveOperation('start_live');
    setFeedbackMessage('Conectando con la transmisión en vivo...');

    try {
      const activeProjectId = await syncProjectNameWithVideo(cleanedUrl);
      const res = await fetch('/api/live/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          stream_url: cleanedUrl,
          profile_id: liveProfileId,
          chunk_duration_sec: liveChunkDurationSec,
          overlap_sec: 20,
          min_virality_score: liveMinScore,
          max_shorts_total: liveMaxShorts,
          ...(activeProjectId !== 'default' ? { project_id: activeProjectId } : {}),
        }),
      });
      if (!res.ok) {
        const errBody = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }
      const data = (await res.json()) as LiveMonitorStatus;
      setLiveStatus(data);
      setActionState('success');
      setFeedbackMessage('Monitoreo en vivo activo. Extrayendo momentos virales...');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'No se pudo iniciar la captura en vivo.';
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      setActiveOperation('none');
    }
  };

  const handleStopLiveMonitor = async () => {
    setActionState('loading');
    setActiveOperation('stop_live');
    setFeedbackMessage('Deteniendo monitoreo en vivo...');
    try {
      const res = await fetch(buildProjectApiUrl('/api/live/stop', projectId), {
        method: 'POST',
      });
      if (!res.ok) {
        const errBody = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(errBody.detail || `Error HTTP ${res.status}`);
      }
      const data = (await res.json()) as LiveMonitorStatus;
      setLiveStatus(data);
      setActionState('success');
      setFeedbackMessage('Monitoreo en vivo detenido.');
      await fetchAllData();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'No se pudo detener el monitoreo en vivo.';
      setActionState('error');
      setFeedbackMessage(msg);
    } finally {
      setActiveOperation('none');
    }
  };

  return (
    <div className={themeMode === 'dark' ? 'dark' : ''}>
      <div
        data-testid="dark-studio-shell"
        className="relative min-h-screen bg-zinc-50 dark:bg-[#090B10] text-zinc-900 dark:text-zinc-50 font-sans antialiased tracking-tight p-4 sm:p-6 md:p-8 transition-colors duration-200 overflow-x-clip"
      >
        {/* Sutil resplandor radial superior Dark Studio (cian/índigo al 6%) */}
        <div
          aria-hidden="true"
          className="pointer-events-none fixed inset-x-0 top-0 h-[420px] opacity-0 dark:opacity-100"
          style={{
            background:
              'radial-gradient(ellipse 80% 60% at 50% 0%, rgba(6, 182, 212, 0.08), rgba(79, 70, 229, 0.05) 45%, transparent 75%)',
          }}
        />

        <div className="relative z-10 max-w-7xl mx-auto flex flex-col gap-6">
          <StudioHeader
            projectId={projectId}
            projectDisplayName={projectDisplayName}
            themeMode={themeMode}
            onToggleTheme={() => void handleToggleTheme()}
            diskSpace={diskSpace}
            pipelineStatus={pipelineStatus}
            isBusy={isBusy}
            activeOperation={activeOperation}
            onNewProject={() => void handleNewProject()}
            onDiskCleanup={() => void handleDiskCleanup()}
            activeTab={activeTab}
            onSelectTab={setActiveTab}
            isLiveMonitoring={isLiveMonitoring}
          />

          {/* Barra de Estado en Tiempo Real (carga, éxito, error o alerta automática de OAuth YouTube) */}
          {(() => {
            const shortsHaveYouTubeOAuthError = renderedShorts.some(
              (s) =>
                s.social_statuses?.youtube?.state === 'error' &&
                /oauth|invalid_grant|token|expirad|autorizar/i.test(
                  String(s.social_statuses?.youtube?.detail || '')
                )
            );
            const feedbackHasYouTubeOAuthError =
              actionState === 'error' &&
              /youtube/i.test(feedbackMessage) &&
              /oauth|invalid_grant|token|expirad|autorizar/i.test(feedbackMessage);
            const showQuickYtOAuthBtn =
              !pendingYouTubeAuthUrl &&
              activeTab !== 'accounts' &&
              (feedbackHasYouTubeOAuthError ||
                (actionState === 'idle' && shortsHaveYouTubeOAuthError));
            const isBannerVisible =
              !isPreAnalyzeModalOpen &&
              (Boolean(pendingYouTubeAuthUrl) || actionState !== 'idle' || showQuickYtOAuthBtn);
            if (!isBannerVisible) return null;
            const effectiveState = pendingYouTubeAuthUrl
              ? 'loading'
              : actionState === 'idle' && showQuickYtOAuthBtn
              ? 'error'
              : actionState;
            const effectiveMessage = pendingYouTubeAuthUrl
              ? 'Se abrió el acceso de Google en una nueva pestaña. Autoriza tu canal para continuar (si no se abrió sola, pulsa Abrir Google OAuth ↗).'
              : actionState === 'idle' && showQuickYtOAuthBtn
              ? 'Sesión OAuth de YouTube expirada o sin autorizar. Conecta tu cuenta para reintentar automáticamente tus Shorts pendientes.'
              : feedbackMessage;
            return (
              <section
                aria-live="polite"
                className={`rounded-2xl border p-4 flex flex-wrap items-center justify-between gap-4 shadow-sm backdrop-blur-md ${
                  effectiveState === 'error'
                    ? 'bg-red-50/90 dark:bg-red-950/50 border-red-200 dark:border-red-900/60 text-red-900 dark:text-red-200'
                    : effectiveState === 'success'
                    ? 'bg-emerald-50/90 dark:bg-emerald-950/50 border-emerald-200 dark:border-emerald-900/60 text-emerald-900 dark:text-emerald-200'
                    : 'bg-cyan-50/90 dark:bg-cyan-950/40 border-cyan-200 dark:border-cyan-500/35 text-cyan-900 dark:text-cyan-100'
                }`}
              >
                <div className="flex items-center gap-3 text-left min-w-0 flex-1">
                  {effectiveState === 'loading' && (
                    <Loader2 className="w-4 h-4 animate-spin text-cyan-500 shrink-0" />
                  )}
                  {effectiveState === 'success' && (
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
                  )}
                  {effectiveState === 'error' && (
                    <AlertCircle className="w-4 h-4 text-red-600 dark:text-red-400 shrink-0" />
                  )}
                  <span className="text-sm font-medium leading-relaxed">{effectiveMessage}</span>
                </div>
                {pendingYouTubeAuthUrl ? (
                  <div className="flex flex-wrap items-center gap-2 shrink-0">
                    <a
                      href={pendingYouTubeAuthUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="h-10 px-4 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold inline-flex items-center justify-center whitespace-nowrap leading-none gap-2 shadow-sm transition-colors"
                    >
                      Abrir Google OAuth ↗
                    </a>
                    <button
                      type="button"
                      onClick={() => void handleCancelYouTubeOAuth()}
                      className="h-10 px-3.5 rounded-xl border border-cyan-300 dark:border-white/15 bg-white/80 dark:bg-zinc-900/70 hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-800 dark:text-zinc-200 text-xs font-semibold inline-flex items-center justify-center whitespace-nowrap leading-none transition-colors"
                    >
                      Cancelar
                    </button>
                  </div>
                ) : (
                  showQuickYtOAuthBtn && (
                    <button
                      type="button"
                      onClick={() => void handleAuthorizeYouTubeOAuth()}
                      disabled={isBusy}
                      className="h-10 px-4 rounded-xl bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white text-xs font-semibold inline-flex items-center justify-center whitespace-nowrap leading-none gap-2 shadow-sm transition-colors shrink-0"
                    >
                      {activeOperation === 'authorize_youtube_oauth' && (
                        <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
                      )}
                      <span>
                        {activeOperation === 'authorize_youtube_oauth'
                          ? 'Autorizando OAuth...'
                          : 'Conectar YouTube OAuth'}
                      </span>
                    </button>
                  )
                )}
              </section>
            );
          })()}

          {activeTab === 'accounts' ? (
            <SocialAccountsStudio
              hubConfig={socialHubConfig}
              verifyResults={verifyResults}
              activeOp={activeOperation}
              verifyingPlatform={verifyingPlatform}
              pendingYouTubeAuthUrl={pendingYouTubeAuthUrl}
              onChangeHubConfig={setSocialHubConfig}
              onSaveHubConfig={() => void handleSaveSocialHubConfig()}
              onVerifyPlatform={(plat) => void handleVerifySocialPlatform(plat)}
              onAuthorizeYouTube={() => void handleAuthorizeYouTubeOAuth()}
              onCancelYouTubeOAuth={() => void handleCancelYouTubeOAuth()}
              onCreateCategory={(payload) => handleCreateSocialCategory(payload)}
              onDeleteCategory={(catKey) => void handleDeleteSocialCategory(catKey)}
            />
          ) : (
            <>
              {activeTab === 'live' ? (
                <LiveStreamStudio
                  streamUrl={liveStreamUrl}
                  onStreamUrlChange={setLiveStreamUrl}
                  profileId={liveProfileId}
                  onProfileIdChange={setLiveProfileId}
                  chunkDurationSec={liveChunkDurationSec}
                  onChunkDurationSecChange={setLiveChunkDurationSec}
                  minViralityScore={liveMinScore}
                  onMinViralityScoreChange={setLiveMinScore}
                  maxShortsTotal={liveMaxShorts}
                  onMaxShortsTotalChange={setLiveMaxShorts}
                  contentProfiles={contentProfiles}
                  liveStatus={liveStatus}
                  isBusy={isBusy}
                  activeOperation={activeOperation}
                  onStartLive={(e) => void handleStartLiveMonitor(e)}
                  onStopLive={() => void handleStopLiveMonitor()}
                />
              ) : (
                <>
                  <OmniboxConfigStudio
                sourceType={sourceType}
                onSourceTypeChange={(next) => {
                  setSourceType(next);
                  setSceneDataByRuleId({});
                  setIsStudioOpen(false);
                  setPreAnalyzeData(null);
                }}
                inboxVideos={inboxVideos}
                selectedVideo={selectedVideo}
                pickedVideoMeta={pickedVideoMeta}
                onSelectLocalVideoFile={(file) => void handleSelectLocalVideoFile(file)}
                youtubeUrl={youtubeUrl}
                onYoutubeUrlChange={setYoutubeUrl}
                downloadSectionStart={downloadSectionStart}
                onDownloadSectionStartChange={setDownloadSectionStart}
                downloadSectionEnd={downloadSectionEnd}
                onDownloadSectionEndChange={setDownloadSectionEnd}
                shortsPerVideo={shortsPerVideo}
                onShortsPerVideoChange={setShortsPerVideo}
                inspectionReport={inspectionReport}
                isBusy={isBusy}
                activeOperation={activeOperation}
                onInspectVideo={() => void handleInspectVideo()}
                onSubmitPipeline={(e) => void handleRequestPreAnalyze(e)}
              />

              {isPreAnalyzeModalOpen && (
                <PreFlightAnalysisModal
                  sourceType={sourceType}
                  selectedVideo={selectedVideo}
                  youtubeUrl={youtubeUrl}
                  preAnalyzeData={preAnalyzeData}
                  categoryRules={categoryRules}
                  activeRuleIndex={activeRuleIndex}
                  onSelectRuleIndex={setActiveRuleIndex}
                  onUpdateActiveRule={handleUpdateActiveRule}
                  onAddRule={handleAddCategoryRule}
                  onRemoveRule={handleRemoveCategoryRule}
                  subtitlePresets={subtitlePresets}
                  contentProfiles={contentProfiles}
                  selectedProfileId={selectedProfileId}
                  onSelectProfile={handleSelectContentProfile}
                  profileNameInput={profileNameInput}
                  onProfileNameInputChange={setProfileNameInput}
                  profileKeywordsInput={profileKeywordsInput}
                  onProfileKeywordsInputChange={setProfileKeywordsInput}
                  autoCategorizeByTopic={autoCategorizeByTopic}
                  onChangeAutoCategorizeByTopic={setAutoCategorizeByTopic}
                  allowedAccountCategories={allowedAccountCategories}
                  onToggleAllowedAccountCategory={handleToggleAllowedAccountCategory}
                  categoryOptions={categoryOptions}
                  onSaveProfile={() => void handleSaveContentProfile()}
                  onDeleteProfile={() => void handleDeleteContentProfile()}
                  sceneData={activeSceneData}
                  studioCanvasRef={studioCanvasRef}
                  onSetCustomBoxesManual={handleSetCustomBoxesManual}
                  onStartDragging={setDraggingTarget}
                  onDetectScene={(ts, preserve) => void handleDetectScene(ts, preserve)}
                  onDiscoverCandidates={() => void handleDiscoverCandidates()}
                  onConfirmStart={() => void handleConfirmStartPipeline()}
                  onClose={handleClosePreAnalyzeModal}
                  isBusy={isBusy}
                  activeOperation={activeOperation}
                  actionState={actionState}
                  feedbackMessage={feedbackMessage}
                />
              )}

              {discoveredCandidates.length > 0 && (
                <DiscoveredCandidatesTray
                  discoveredCandidates={discoveredCandidates}
                  selectedCandidateIds={selectedCandidateIds}
                  isBusy={isBusy}
                  activeOperation={activeOperation}
                  onSelectAll={() =>
                    setSelectedCandidateIds(discoveredCandidates.map((c) => c.candidate_id))
                  }
                  onSelectGoldOnly={() =>
                    setSelectedCandidateIds(
                      discoveredCandidates
                        .filter((c) => c.virality_score >= 85)
                        .map((c) => c.candidate_id)
                    )
                  }
                  onToggleCandidate={(id, checked) => {
                    if (checked) {
                      setSelectedCandidateIds((prev) => [...prev, id]);
                    } else {
                      setSelectedCandidateIds((prev) => prev.filter((item) => item !== id));
                    }
                  }}
                  onRenderSelected={() => void handleRenderSelectedCandidates()}
                  onPreviewCut={handlePreviewCandidateCut}
                />
              )}

              <ProcessMonitorSection
                pipelineStatus={pipelineStatus}
                sourceType={sourceType}
                selectedVideo={selectedVideo}
                youtubeUrl={youtubeUrl}
                isBusy={isBusy}
                sourceVideoRef={sourceVideoRef}
                onCancelPipeline={() => void handleCancelPipeline()}
              />
                </>
              )}

              <ShortsGallery
                renderedShorts={renderedShorts}
                galleryFilter={galleryFilter}
                onGalleryFilterChange={setGalleryFilter}
                queues={queues}
                pipelineStatus={pipelineStatus}
                rerenderVersions={rerenderVersions}
                isBusy={isBusy}
                activeOperation={activeOperation}
                showSocialDetails={showSocialDetails}
                onToggleSocialDetails={() => setShowSocialDetails((prev) => !prev)}
                selectedShortKeys={selectedShortKeys}
                onToggleSelectShort={handleToggleSelectShort}
                onToggleSelectAllVisible={handleToggleSelectAllVisible}
                onDownloadShorts={(items, mode) => void handleDownloadShorts(items, mode)}
                categoryOptions={categoryOptions}
                getShortScheduleValue={getShortScheduleValue}
                onScheduleValueChange={updateShortScheduleValue}
                onScheduleSingle={(item, idx) => void handleScheduleSingleShort(item, idx)}
                onToggleShortCategory={(item, cats) => void handleToggleShortCategory(item, cats)}
                onOpenLayoutEditor={(item) => void handleOpenShortLayoutEditor(item)}
                onCancelSingle={(item) => void handleCancelSingleShort(item)}
                onDoubleClickVideo={openFloatingPlayer}
                onOpenScheduleModal={() => setIsScheduleModalOpen(true)}
                onCancelAllShorts={() => void handleCancelAllShorts()}
                pendingTikTokCount={pendingTikTokRowIds.length}
                onDispatchTikTokStudio={() => void handleDispatchTikTokStudio()}
              />
            </>
          )}

          {isScheduleModalOpen && renderedShorts.length > 0 && (
            <ScheduleBatchModal
              computedOroCount={computedOroCount}
              computedPlataCount={computedPlataCount}
              computedMehCount={computedMehCount}
              computedYoutubeEligibleCount={computedYoutubeEligibleCount}
              youtubeScheduleTime={youtubeScheduleTime}
              instagramScheduleTime={instagramScheduleTime}
              tiktokScheduleTime={tiktokScheduleTime}
              scheduleIntervalMinutes={scheduleIntervalMinutes}
              isBusy={isBusy}
              activeOperation={activeOperation}
              onYoutubeScheduleTimeChange={setYoutubeScheduleTime}
              onInstagramScheduleTimeChange={setInstagramScheduleTime}
              onTiktokScheduleTimeChange={setTiktokScheduleTime}
              onScheduleIntervalMinutesChange={setScheduleIntervalMinutes}
              onClose={() => {
                setDismissedModalJobId(pipelineStatus?.job_id || 'completed_batch');
                setIsScheduleModalOpen(false);
              }}
              onSubmit={(e) => void handleScheduleBatch(e)}
            />
          )}

          {activeShortPlayer && (
            <FloatingShortPlayer
              activeShortPlayer={activeShortPlayer}
              floatingOffset={floatingOffset}
              scheduleValue={getShortScheduleValue(activeShortPlayer, 0)}
              queues={queues}
              pipelineStatus={pipelineStatus}
              cacheVersion={activePlayerVersion}
              isBusy={isBusy}
              showSocialDetails={showSocialDetails}
              onStartDrag={startFloatingDrag}
              onClose={() => setActiveShortPlayer(null)}
              onScheduleValueChange={(val) => updateShortScheduleValue(activeShortPlayer, val)}
              onScheduleSingle={() => void handleScheduleSingleShort(activeShortPlayer, 0)}
              onOpenLayoutEditor={() => void handleOpenShortLayoutEditor(activeShortPlayer)}
              onExclusivePlay={(videoEl) => pauseAllVideosExcept(videoEl)}
            />
          )}

          {reeditShort && (
            <ShortLayoutEditorModal
              reeditShort={reeditShort}
              reeditScene={reeditScene}
              reeditLayoutMode={reeditLayoutMode}
              reeditCamPos={reeditCamPos}
              reeditSubPreset={reeditSubPreset}
              reeditSubPos={reeditSubPos}
              reeditCamBox={reeditCamBox}
              reeditContentBox={reeditContentBox}
              reeditCanvasRef={reeditCanvasRef}
              reeditTrimStart={reeditTrimStart}
              reeditTrimEnd={reeditTrimEnd}
              reeditMinTrim={reeditMinTrim}
              reeditMaxTrim={reeditMaxTrim}
              reeditMediaUrl={reeditMediaUrl}
              activeOperation={activeOperation}
              isBusy={isBusy}
              onClose={() => setReeditShort(null)}
              onApplyPreset={handleApplyReeditPreset}
              onCamPosChange={setReeditCamPos}
              onSubPresetChange={setReeditSubPreset}
              onSubPosChange={setReeditSubPos}
              onChangeTrimRange={(s, e) => {
                setReeditTrimStart(s);
                setReeditTrimEnd(e);
              }}
              onStartDragging={setReeditDragging}
              onSubmitRerender={(e) => void handleRerenderShort(e)}
            />
          )}
        </div>
      </div>
    </div>
  );
}
