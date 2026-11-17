export type SourceType = 'inbox' | 'youtube_url';

export type ThemeMode = 'light' | 'dark';

export type ContentCategory =
  | 'auto'
  | 'opinion_monologo'
  | 'reacciones'
  | 'videojuegos'
  | 'podcast'
  | 'realitys'
  | 'storytime_anecdota'
  | 'tutorial_curiosidad';

export type LayoutMode =
  | 'auto'
  | 'fullscreen'
  | 'split_streamer'
  | 'split_50_50'
  | 'ometv'
  | 'podcast_dynamic'
  | 'gaming_hud'
  | 'reaction_pip'
  | 'reality_multicam'
  | 'floating_cam_top'
  | 'floating_circle'
  | 'blur_16_9_cam';

export type SubtitlePosition = 'auto' | 'top' | 'center' | 'bottom';

export type CamOverlayPos = 'top_left' | 'top_right' | 'bottom_left' | 'bottom_right';

export type BgmMood =
  | 'auto'
  | 'desactivada'
  | 'misterio'
  | 'comedia'
  | 'impacto'
  | 'reflexion'
  | 'urbano';

export interface CategoryAnalyticsProfile {
  key: string;
  label: string;
  description: string;
  key_signals: string[];
  weights: Record<string, number>;
}

export interface AnalyticsCategoriesResponse {
  categories: CategoryAnalyticsProfile[];
}

export interface InboxVideoItem {
  file_name: string;
  size_mb: number;
  modified_at: string;
}

export interface DiskSpaceReport {
  total_gb: number;
  used_gb: number;
  free_gb: number;
  free_percentage: number;
}

export interface RuntimeSettings {
  shorts_per_video: number;
  content_category?: ContentCategory;
  min_short_duration_sec: number;
  max_short_duration_sec: number;
  playback_speed: number;
  layout_mode: LayoutMode;
  enable_bgm: boolean;
  default_bgm_mood: string;
  enable_dynamic_zoom: boolean;
  enable_hook_punchin: boolean;
  enable_jumpcuts: boolean;
  max_words_per_subtitle: number;
  youtube_category_id: string;
  auto_upload_to_youtube?: boolean;
  theme_mode?: ThemeMode;
}

export interface ShortsBatchSummary {
  total_shorts: number;
  oro_count: number;
  plata_count: number;
  meh_count: number;
  youtube_eligible_count: number;
  youtube_uploaded_count: number;
  requires_schedule_confirmation: boolean;
}

export interface PipelineStatus {
  project_id?: string;
  project_name?: string;
  job_id: string | null;
  status:
    | 'IDLE'
    | 'STARTED'
    | 'RUNNING'
    | 'DISCOVERING'
    | 'CANDIDATES_READY'
    | 'COMPLETED'
    | 'ERROR'
    | 'CANCELED'
    | 'CANCELLED';
  current_video: string | null;
  source_type?: SourceType;
  source_preview_url?: string | null;
  progress_percent?: number;
  phase_label?: string;
  step_detail?: string;
  message: string;
  updated_at: string;
  completion_summary?: ShortsBatchSummary;
}

export interface InboxResponse {
  project_id?: string;
  project_name?: string;
  videos: InboxVideoItem[];
  disk_space: DiskSpaceReport;
  settings: RuntimeSettings;
  pipeline_status: PipelineStatus;
}

export interface VideoInspectionReport {
  file_name: string;
  file_path: string;
  file_size_mb: number;
  duration_sec: number;
  duration_formatted: string;
  resolution: string;
  fps: number;
  recommended_shorts: number;
  max_possible_shorts: number;
  detected_at: string;
  status: string;
}

export type SocialNetworkState =
  | 'uploaded'
  | 'processing'
  | 'draft'
  | 'pending'
  | 'local'
  | 'not_applicable'
  | 'error';

export type AccountCategoryKey = string;

export type SocialPlatformKey = 'youtube' | 'instagram' | 'tiktok' | 'facebook';

export interface SocialNetworkStatusItem {
  network: SocialPlatformKey;
  state: SocialNetworkState;
  status_label: string;
  detail: string;
  percent: number;
  account?: string | null;
  permalink?: string | null;
  targets?: string[];
}

export interface ShortSocialStatuses {
  youtube: SocialNetworkStatusItem;
  instagram: SocialNetworkStatusItem;
  tiktok: SocialNetworkStatusItem;
  facebook?: SocialNetworkStatusItem;
}

export interface RenderedShortItem {
  filename: string;
  folder: string;
  relative_path?: string;
  video_url?: string;
  thumbnail_url?: string;
  size_mb: number;
  created_at: string;
  virality_score: number;
  virality_grade: number;
  tier: 'Oro' | 'Plata' | 'Meh';
  hook_title?: string | null;
  category?: string | null;
  layout_used?: string | null;
  duration_sec?: number | null;
  eligible_for_youtube: boolean;
  scheduled_ast: string | null;
  publish_at_utc: string | null;
  youtube_video_id: string | null;
  upload_progress_percent?: number;
  upload_status_detail?: string;
  account_categories?: AccountCategoryKey[];
  resolved_targets?: Partial<Record<SocialPlatformKey, string[]>>;
  social_statuses?: ShortSocialStatuses;
  subtitle_preset?: string;
  subtitle_position?: SubtitlePosition;
  cam_overlay_pos?: CamOverlayPos;
  custom_cam_box_norm?: [number, number, number, number] | null;
  custom_content_box_norm?: [number, number, number, number] | null;
  has_source_16_9?: boolean;
}

export interface ShortsResponse {
  project_id?: string;
  total: number;
  shorts: RenderedShortItem[];
  summary?: ShortsBatchSummary;
}

export interface YouTubeScheduledSlot {
  id: number;
  video_name: string;
  slot_ast: string;
  publish_at_utc: string;
  youtube_video_id: string | null;
  created_at_utc: string;
}

export interface SocialQueueItem {
  id: number;
  account_key: string;
  scheduled_time_utc: string;
  scheduled_time_ast: string;
  status: string;
  video_path: string;
  permalink?: string | null;
  publish_id?: string | null;
  post_id?: string | null;
  error?: string | null;
}

export interface QueuesResponse {
  youtube_slots: YouTubeScheduledSlot[];
  instagram_queue: SocialQueueItem[];
  tiktok_queue: SocialQueueItem[];
  facebook_queue?: SocialQueueItem[];
}

export interface CleanupResponse {
  deleted_files: number;
  mb_freed: number;
  disk_space: DiskSpaceReport;
}

export interface ProcessStartResponse {
  job_id: string;
  status: string;
  target: string | null;
  settings_applied: RuntimeSettings;
}

export interface SubtitlePresetItem {
  id: string;
  name: string;
  description: string;
  fontname?: string;
  fontsize?: number;
  max_words?: number;
}

export interface SubtitlePresetsResponse {
  presets: SubtitlePresetItem[];
}

export interface SceneDetectResponse {
  video_filename: string;
  resolution: string;
  width: number;
  height: number;
  detected_layout: string;
  faces_detected: number;
  cam_box_norm: [number, number, number, number];
  content_box_norm: [number, number, number, number];
  frame_url: string;
  timestamp_sec?: number;
  duration_sec?: number | null;
  frame_source?: string;
}

export interface ShortSceneDetectResponse {
  short_rel_path: string;
  filename: string;
  resolution: string;
  width: number;
  height: number;
  detected_layout: string;
  current_layout: LayoutMode | string;
  faces_detected: number;
  cam_box_norm: [number, number, number, number];
  content_box_norm: [number, number, number, number];
  subtitle_preset: string;
  subtitle_position: SubtitlePosition;
  cam_overlay_pos: CamOverlayPos;
  has_source_16_9: boolean;
  frame_url: string;
  edit_media_url?: string;
  trim_start_sec?: number;
  trim_end_sec?: number;
  min_trim_sec?: number;
  max_trim_sec?: number;
  duration_sec?: number;
}

export interface DiscoveredCandidateItem {
  candidate_id: string;
  start_time: number;
  end_time: number;
  duration: number;
  hook_title: string;
  first_person_caption: string;
  transcript_excerpt: string;
  tags: string[];
  bgm_mood: string;
  virality_score: number;
  virality_grade: string;
  youtube_eligible: boolean;
  account_categories?: AccountCategoryKey[];
}

export interface CandidatesResponse {
  video_filename: string | null;
  discovered_at?: string;
  candidates: DiscoveredCandidateItem[];
}

export interface CategorySceneRule {
  rule_id: string;
  category?: ContentCategory;
  scene_label: string;
  detected_share_pct: number;
  layout_mode: LayoutMode;
  subtitle_preset: string;
  subtitle_position: SubtitlePosition;
  cam_overlay_pos: CamOverlayPos;
  custom_cam_box_norm: [number, number, number, number] | null;
  custom_content_box_norm: [number, number, number, number] | null;
  custom_boxes_manual: boolean;
  frame_url?: string | null;
  sample_timestamp_sec?: number | null;
}

export interface ContentProfileItem {
  id: number;
  name: string;
  match_keywords: string[];
  scenes: CategorySceneRule[];
  auto_categorize_by_topic?: boolean;
  allowed_account_categories?: AccountCategoryKey[];
  created_at_utc?: string;
  updated_at_utc?: string;
}

export interface ContentProfilesResponse {
  profiles: ContentProfileItem[];
}

export interface PreAnalyzeResponse {
  source_type: SourceType;
  target: string;
  video_title: string | null;
  duration_sec: number | null;
  thumbnail_url: string | null;
  matched_profile_id?: number | null;
  matched_profile_name?: string | null;
  suggested_profile_name?: string | null;
  suggested_keywords?: string[];
  auto_categorize_by_topic?: boolean;
  allowed_account_categories?: AccountCategoryKey[];
  is_hybrid_multicategory: boolean;
  analysis_mode: string;
  analysis_summary: string;
  category_rules: CategorySceneRule[];
}

export interface LocalVideoPickResponse {
  cancelled: boolean;
  file_path: string | null;
  file_name: string | null;
  size_mb: number | null;
}

export interface SocialAccountEntry {
  id: string;
  platform: SocialPlatformKey;
  handle: string;
  display_name: string;
  external_id: string;
  enabled: boolean;
}

export interface SocialAccountCategoryConfig {
  key: AccountCategoryKey;
  label: string;
  description: string;
  topic_keywords: string[];
  accounts: SocialAccountEntry[];
  is_custom?: boolean;
}

export interface SocialHubApiSettings {
  youtube: {
    client_id: string;
    client_secret: string;
    client_secret_json?: string;
    has_client_secret?: boolean;
    has_token?: boolean;
    default_category_id: string;
  };
  instagram: {
    app_id: string;
    app_secret: string;
    access_token: string;
    has_app_secret?: boolean;
    has_access_token?: boolean;
    business_id: string;
    graph_version: string;
  };
  tiktok: {
    client_key: string;
    client_secret: string;
    access_token: string;
    has_client_secret?: boolean;
    has_access_token?: boolean;
    redirect_uri: string;
    publish_mode: string;
  };
  facebook: {
    app_id: string;
    page_access_token: string;
    has_page_access_token?: boolean;
    graph_version: string;
  };
}

export interface SocialHubConfigResponse {
  categories: Record<AccountCategoryKey, SocialAccountCategoryConfig>;
  api_settings: SocialHubApiSettings;
}

export interface SocialPlatformVerifyResponse {
  platform: SocialPlatformKey;
  connected: boolean;
  status_label: string;
  detail: string;
  retried_youtube_slots?: number;
  oauth_state?: 'idle' | 'pending' | 'completed' | 'error';
  auth_url?: string | null;
  error?: string | null;
}

export interface RenameProjectResponse {
  renamed: boolean;
  old_project_id: string;
  project_id: string;
  project_name: string;
  project_url: string;
  pipeline_status: PipelineStatus;
}

export type ActiveStudioTab = 'studio' | 'live' | 'accounts';

export interface LiveRecentClipItem {
  filename: string;
  folder?: string;
  hook_title: string;
  virality_score: number;
  tier: string;
  created_at: string;
}

export interface LiveMonitorStatus {
  project_id?: string;
  session_id?: string | null;
  status: 'IDLE' | 'STARTING' | 'MONITORING' | 'ANALYZING_CHUNK' | 'STOPPED' | 'COMPLETED' | 'ERROR';
  stream_url: string;
  stream_title?: string;
  is_live_detected?: boolean;
  profile_id?: number | null;
  profile_name?: string;
  layout_mode?: string;
  subtitle_preset?: string;
  chunk_duration_sec: number;
  overlap_sec: number;
  min_virality_score: number;
  max_shorts_total: number;
  segments_captured: number;
  segments_analyzed: number;
  shorts_generated: number;
  phase_label: string;
  step_detail: string;
  started_at?: string | null;
  updated_at?: string;
  recent_clips: LiveRecentClipItem[];
}

export interface LiveMonitorStartPayload {
  stream_url: string;
  profile_id: number | null;
  chunk_duration_sec: number;
  overlap_sec?: number;
  min_virality_score: number;
  max_shorts_total: number;
  project_id?: string;
}
