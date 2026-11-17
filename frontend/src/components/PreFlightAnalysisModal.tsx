import React from 'react';
import {
  AlertCircle,
  Bookmark,
  CheckCircle2,
  Layers,
  Loader2,
  Play,
  Plus,
  Scissors,
  Sliders,
  Sparkles,
  Trash2,
  Type,
  X,
} from 'lucide-react';
import type {
  AccountCategoryKey,
  CamOverlayPos,
  CategorySceneRule,
  ContentProfileItem,
  LayoutMode,
  PreAnalyzeResponse,
  SceneDetectResponse,
  SourceType,
  SubtitlePosition,
  SubtitlePresetItem,
} from '../types';
import { InteractiveSceneStudio, type StudioDragTarget } from './InteractiveSceneStudio';
import { LiveSceneCropPreview, LiveSubtitleOverlay } from './LiveSubtitlePreview';
import {
  type ActiveOperation,
  type CategoryOptionMeta,
  DUAL_BOX_LAYOUTS,
  getHubCategoryOptions,
  LAYOUT_MODE_LABELS,
  SUBTITLE_POSITION_LABELS,
  SUBTITLE_PRESET_LABELS,
} from './studioHelpers';

export interface PreFlightAnalysisModalProps {
  sourceType: SourceType;
  selectedVideo: string;
  youtubeUrl: string;
  preAnalyzeData: PreAnalyzeResponse | null;
  categoryRules: CategorySceneRule[];
  activeRuleIndex: number;
  onSelectRuleIndex: (index: number) => void;
  onUpdateActiveRule: (patch: Partial<CategorySceneRule>) => void;
  onAddRule: () => void;
  onRemoveRule: (index: number) => void;
  subtitlePresets: SubtitlePresetItem[];
  contentProfiles: ContentProfileItem[];
  selectedProfileId: string;
  onSelectProfile: (profileId: string) => void;
  profileNameInput: string;
  onProfileNameInputChange: (val: string) => void;
  profileKeywordsInput: string;
  onProfileKeywordsInputChange: (val: string) => void;
  autoCategorizeByTopic?: boolean;
  onChangeAutoCategorizeByTopic?: (val: boolean) => void;
  allowedAccountCategories?: AccountCategoryKey[];
  onToggleAllowedAccountCategory?: (cat: AccountCategoryKey) => void;
  categoryOptions?: CategoryOptionMeta[];
  onSaveProfile: () => void;
  onDeleteProfile: () => void;
  sceneData: SceneDetectResponse | null;
  studioCanvasRef: React.RefObject<HTMLDivElement>;
  onSetCustomBoxesManual: (manual: boolean) => void;
  onStartDragging: (target: StudioDragTarget) => void;
  onDetectScene: (timestampSec?: number, preserveManualBoxes?: boolean) => void;
  onDiscoverCandidates: () => void;
  onConfirmStart: () => void;
  onClose: () => void;
  isBusy: boolean;
  activeOperation: ActiveOperation;
  actionState: 'idle' | 'loading' | 'success' | 'error';
  feedbackMessage: string;
}

const LAYOUT_SELECT_OPTIONS: LayoutMode[] = [
  'auto',
  'fullscreen',
  'split_streamer',
  'gaming_hud',
  'split_50_50',
  'podcast_dynamic',
  'reaction_pip',
  'reality_multicam',
  'floating_cam_top',
  'floating_circle',
  'blur_16_9_cam',
  'ometv',
];

export function PreFlightAnalysisModal({
  sourceType,
  selectedVideo,
  youtubeUrl,
  preAnalyzeData,
  categoryRules,
  activeRuleIndex,
  onSelectRuleIndex,
  onUpdateActiveRule,
  onAddRule,
  onRemoveRule,
  subtitlePresets,
  contentProfiles,
  selectedProfileId,
  onSelectProfile,
  profileNameInput,
  onProfileNameInputChange,
  profileKeywordsInput,
  onProfileKeywordsInputChange,
  autoCategorizeByTopic = true,
  onChangeAutoCategorizeByTopic,
  allowedAccountCategories = ['principales', 'gaming', 'clipping', 'ometv'],
  onToggleAllowedAccountCategory,
  categoryOptions,
  onSaveProfile,
  onDeleteProfile,
  sceneData,
  studioCanvasRef,
  onSetCustomBoxesManual,
  onStartDragging,
  onDetectScene,
  onDiscoverCandidates,
  onConfirmStart,
  onClose,
  isBusy,
  activeOperation,
  actionState,
  feedbackMessage,
}: PreFlightAnalysisModalProps) {
  const safeIdx = Math.min(Math.max(0, activeRuleIndex), Math.max(0, categoryRules.length - 1));
  const activeRule: CategorySceneRule = categoryRules[safeIdx] || {
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
    sample_timestamp_sec: null,
  };

  const isPipOrFloatingCam =
    activeRule.layout_mode === 'floating_circle' ||
    activeRule.layout_mode === 'floating_cam_top' ||
    activeRule.layout_mode === 'reaction_pip' ||
    activeRule.layout_mode === 'gaming_hud' ||
    activeRule.layout_mode === 'split_streamer' ||
    activeRule.layout_mode === 'auto';

  const canDetectScene =
    sourceType === 'inbox' ? Boolean(selectedVideo.trim()) : Boolean(youtubeUrl.trim());

  const handleLayoutChange = (nextLayout: LayoutMode) => {
    if (nextLayout === 'fullscreen') {
      if (activeRule.custom_boxes_manual) {
        onUpdateActiveRule({
          layout_mode: nextLayout,
          custom_content_box_norm: null,
        });
      } else {
        onUpdateActiveRule({
          layout_mode: nextLayout,
          custom_boxes_manual: false,
          custom_cam_box_norm: null,
          custom_content_box_norm: null,
        });
      }
      return;
    }
    if (!DUAL_BOX_LAYOUTS.includes(nextLayout)) {
      onUpdateActiveRule({
        layout_mode: nextLayout,
        custom_boxes_manual: false,
        custom_cam_box_norm: null,
        custom_content_box_norm: null,
      });
      return;
    }
    onUpdateActiveRule({
      layout_mode: nextLayout,
    });
  };

  const displayCamBox: [number, number, number, number] =
    activeRule.custom_cam_box_norm ||
    sceneData?.cam_box_norm ||
    (activeRule.layout_mode === 'fullscreen' ? [0.28, 0.05, 0.44, 0.9] : [0.02, 0.68, 0.24, 0.28]);
  const displayContentBox: [number, number, number, number] =
    activeRule.custom_content_box_norm ||
    sceneData?.content_box_norm ||
    [0.26, 0.02, 0.72, 0.96];

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Configuración por Contenido y Escenas 9:16"
      data-testid="preflight-analysis-modal"
      className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4"
    >
      <div className="bg-white dark:bg-[#11151F] rounded-2xl border border-zinc-200/80 dark:border-white/[0.08] max-w-6xl w-full max-h-[92vh] overflow-y-auto shadow-2xl flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-zinc-200/80 dark:border-white/[0.08] flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 text-left">
          <div className="flex flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <Sparkles className="w-4 h-4 text-cyan-500 shrink-0" />
              <h3 className="text-lg font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
                Perfil de Contenido y Escenas 9:16
              </h3>
              {preAnalyzeData?.matched_profile_id ? (
                <span className="px-2.5 py-0.5 rounded-md bg-emerald-500/15 border border-emerald-500/35 text-[11px] font-semibold text-emerald-700 dark:text-emerald-300">
                  Perfil Auto-Reconocido: {preAnalyzeData.matched_profile_name}
                </span>
              ) : (
                <span className="px-2.5 py-0.5 rounded-md bg-cyan-500/15 border border-cyan-500/35 text-[11px] font-semibold text-cyan-700 dark:text-cyan-300 tabular-nums">
                  {categoryRules.length} {categoryRules.length === 1 ? 'escena' : 'escenas'} detectadas
                </span>
              )}
            </div>
            <p className="text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed">
              {preAnalyzeData?.analysis_summary ||
                'Define o guarda un Perfil de Contenido reutilizable (encuadres, subtítulos y cajas 16:9) para que futuros videos iguales se configuren solos.'}
            </p>
            {(preAnalyzeData?.video_title || preAnalyzeData?.target) && (
              <span className="text-[11px] font-medium text-zinc-500 dark:text-zinc-400 truncate max-w-2xl">
                Origen: {preAnalyzeData.video_title || preAnalyzeData.target}
              </span>
            )}
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar análisis previo"
            className="h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-zinc-50 dark:bg-[#090B10] hover:bg-zinc-200/70 dark:hover:bg-[#171C29] text-zinc-700 dark:text-zinc-200 inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium gap-1.5 shrink-0"
          >
            <X className="w-4 h-4" />
            Cerrar
          </button>
        </div>

        {/* Feedback Inline de Estado dentro del Modal (preserva inputs en error) */}
        {(actionState === 'error' || actionState === 'success') && feedbackMessage && (
          <div
            aria-live="polite"
            className={`mx-6 mt-4 p-3 rounded-xl border flex items-center gap-2.5 text-xs font-medium text-left ${
              actionState === 'error'
                ? 'bg-red-50 dark:bg-red-950/60 border-red-200 dark:border-red-900/70 text-red-800 dark:text-red-200'
                : 'bg-emerald-50 dark:bg-emerald-950/50 border-emerald-200 dark:border-emerald-900/60 text-emerald-800 dark:text-emerald-200'
            }`}
          >
            {actionState === 'error' ? (
              <AlertCircle className="w-4 h-4 text-red-600 dark:text-red-400 shrink-0" />
            ) : (
              <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
            )}
            <span>{feedbackMessage}</span>
          </div>
        )}

        {/* Body: Columna Izquierda Master-Detail + Columna Derecha Preview 9:16 */}
        <div className="p-6 grid grid-cols-1 lg:grid-cols-12 gap-6 text-left">
          {/* Columna Izquierda: Perfil Reutilizable + Escenas + Editor */}
          <div className="lg:col-span-7 flex flex-col gap-5">
            {/* Gestor de Perfiles de Contenido Reutilizables */}
            <div className="p-4 rounded-xl bg-zinc-50 dark:bg-[#090B10] border border-zinc-200/80 dark:border-white/[0.08] flex flex-col gap-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Bookmark className="w-4 h-4 text-cyan-500" />
                  <span className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                    Perfil de Contenido Guardado ({contentProfiles.length})
                  </span>
                </div>
                <span className="text-[11px] text-zinc-500 dark:text-zinc-400">
                  {selectedProfileId ? 'Editando perfil existente' : 'Nuevo perfil listo para guardar'}
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
                <div className="md:col-span-6">
                  <label
                    htmlFor="content-profile-select"
                    className="text-xs font-medium text-zinc-700 dark:text-zinc-300 mb-1.5 block"
                  >
                    Perfil de Contenido
                  </label>
                  <select
                    id="content-profile-select"
                    value={selectedProfileId}
                    onChange={(e) => onSelectProfile(e.target.value)}
                    className="w-full h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#11151F] text-sm text-zinc-900 dark:text-zinc-50 focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  >
                    <option value="">+ Nuevo perfil para este contenido ({contentProfiles.length} guardados)</option>
                    {contentProfiles.map((cp) => (
                      <option key={cp.id} value={String(cp.id)}>
                        {cp.name} ({cp.scenes.length} {cp.scenes.length === 1 ? 'escena' : 'escenas'})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="md:col-span-6">
                  <label
                    htmlFor="profile-name-input"
                    className="text-xs font-medium text-zinc-700 dark:text-zinc-300 mb-1.5 block"
                  >
                    Nombre del Contenido / Show
                  </label>
                  <input
                    id="profile-name-input"
                    type="text"
                    value={profileNameInput}
                    onChange={(e) => onProfileNameInputChange(e.target.value)}
                    placeholder="Ej. CreadorStudio Live, Podcast Debate"
                    className="w-full h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#11151F] text-sm text-zinc-900 dark:text-zinc-50 focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
                <div className="md:col-span-6">
                  <label
                    htmlFor="profile-keywords-input"
                    className="text-xs font-medium text-zinc-700 dark:text-zinc-300 mb-1.5 block"
                  >
                    Pistas de Auto-Detección (Canal / Palabras)
                  </label>
                  <input
                    id="profile-keywords-input"
                    type="text"
                    value={profileKeywordsInput}
                    onChange={(e) => onProfileKeywordsInputChange(e.target.value)}
                    placeholder="Ej. creadorstudio, live o tertulia"
                    className="w-full h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#11151F] text-sm text-zinc-900 dark:text-zinc-50 focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  />
                </div>

                <div className="md:col-span-3">
                  <button
                    type="button"
                    onClick={onSaveProfile}
                    disabled={isBusy || !profileNameInput.trim()}
                    className="w-full h-10 px-3 rounded-lg bg-zinc-900 dark:bg-indigo-500 hover:opacity-95 dark:hover:bg-indigo-400 text-white inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium gap-1.5 transition-all disabled:opacity-50"
                  >
                    {activeOperation === 'save_profile' ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Bookmark className="w-3.5 h-3.5" />
                    )}
                    {selectedProfileId ? 'Actualizar Perfil' : 'Guardar Perfil'}
                  </button>
                </div>

                <div className="md:col-span-3">
                  <button
                    type="button"
                    onClick={onDeleteProfile}
                    disabled={isBusy || !selectedProfileId}
                    className="w-full h-10 px-3 rounded-lg border border-red-200 dark:border-red-900/70 bg-red-50 dark:bg-red-950/60 hover:bg-red-100 dark:hover:bg-red-900/60 text-red-700 dark:text-red-300 inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium gap-1.5 transition-colors disabled:opacity-50"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    Eliminar Perfil
                  </button>
                </div>
              </div>

              <div className="pt-2 border-t border-zinc-200/70 dark:border-white/[0.06] flex flex-col lg:flex-row lg:items-center justify-between gap-2.5">
                <button
                  type="button"
                  onClick={() => onChangeAutoCategorizeByTopic?.(!autoCategorizeByTopic)}
                  aria-pressed={autoCategorizeByTopic}
                  className={`h-10 px-3.5 rounded-lg border text-xs font-medium inline-flex items-center justify-center gap-2 whitespace-nowrap leading-none transition-colors ${
                    autoCategorizeByTopic
                      ? 'border-emerald-500/40 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
                      : 'border-zinc-200 dark:border-zinc-700 bg-white dark:bg-[#11151F] text-zinc-600 dark:text-zinc-300'
                  }`}
                >
                  <Sparkles className="w-3.5 h-3.5 shrink-0" />
                  Auto-categorizar Shorts por tema: {autoCategorizeByTopic ? 'Activo' : 'Fijo'}
                </button>

                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[11px] font-medium text-zinc-500 dark:text-zinc-400">
                    Categorías permitidas:
                  </span>
                  {(categoryOptions && categoryOptions.length > 0
                    ? categoryOptions
                    : getHubCategoryOptions()
                  ).map((catMeta) => {
                    const active = allowedAccountCategories.includes(catMeta.key);
                    return (
                      <button
                        key={catMeta.key}
                        type="button"
                        aria-pressed={active}
                        onClick={() => onToggleAllowedAccountCategory?.(catMeta.key)}
                        className={`h-10 px-3 rounded-lg border text-xs font-semibold inline-flex items-center justify-center whitespace-nowrap leading-none transition-colors ${
                          active
                            ? 'bg-cyan-600 text-white border-cyan-600 dark:bg-cyan-500/25 dark:text-cyan-200 dark:border-cyan-400/50'
                            : 'bg-white dark:bg-[#11151F] text-zinc-600 dark:text-zinc-400 border-zinc-200 dark:border-white/[0.08]'
                        }`}
                      >
                        {catMeta.shortLabel}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Lista de Escenas del Contenido */}
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Layers className="w-4 h-4 text-cyan-500" />
                  <span className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                    Escenas de este Contenido ({categoryRules.length}/4)
                  </span>
                </div>
                <button
                  type="button"
                  onClick={onAddRule}
                  disabled={isBusy || categoryRules.length >= 4}
                  className="h-10 px-3 rounded-lg border border-cyan-500/40 bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-700 dark:text-cyan-300 inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium gap-1.5 transition-colors disabled:opacity-50"
                >
                  <Plus className="w-3.5 h-3.5" />
                  Agregar Escena
                </button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {categoryRules.map((rule, idx) => {
                  const isActive = idx === safeIdx;
                  const layoutLabel = LAYOUT_MODE_LABELS[rule.layout_mode] || rule.layout_mode;
                  return (
                    <div
                      key={rule.rule_id}
                      data-testid={`category-rule-card-${rule.rule_id}`}
                      className={`p-3 rounded-xl border transition-all flex flex-col gap-2.5 ${
                        isActive
                          ? 'bg-cyan-50/70 dark:bg-cyan-950/30 border-cyan-500/60 shadow-sm'
                          : 'bg-zinc-50 dark:bg-[#090B10] border-zinc-200/80 dark:border-white/[0.08]'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2.5 min-w-0">
                          {rule.frame_url && (
                            <img
                              src={rule.frame_url}
                              alt={rule.scene_label}
                              className="w-12 h-8 rounded object-cover border border-white/10 shrink-0"
                            />
                          )}
                          <div className="min-w-0">
                            <div className="text-xs font-semibold text-zinc-900 dark:text-zinc-50 truncate">
                              {rule.scene_label}
                            </div>
                            <div className="text-[11px] text-zinc-600 dark:text-zinc-400 truncate">
                              {layoutLabel}
                            </div>
                          </div>
                        </div>
                        <span className="px-2 py-0.5 rounded-md bg-white dark:bg-[#171C29] border border-zinc-200/80 dark:border-white/[0.08] text-[11px] font-semibold text-cyan-600 dark:text-cyan-300 tabular-nums shrink-0">
                          {rule.detected_share_pct}%
                        </span>
                      </div>

                      <div className="flex flex-wrap gap-1.5 text-[11px] text-zinc-600 dark:text-zinc-300">
                        <span className="px-2 py-0.5 rounded bg-white dark:bg-[#171C29] border border-zinc-200/80 dark:border-white/[0.08]">
                          Encuadre: {rule.layout_mode}
                        </span>
                        <span className="px-2 py-0.5 rounded bg-white dark:bg-[#171C29] border border-zinc-200/80 dark:border-white/[0.08]">
                          Subs: {rule.subtitle_preset}
                        </span>
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => onSelectRuleIndex(idx)}
                          aria-pressed={isActive}
                          className={`flex-1 h-10 px-3 rounded-lg inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium transition-colors ${
                            isActive
                              ? 'bg-gradient-to-r from-cyan-500 to-blue-600 text-white'
                              : 'border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#171C29] text-zinc-800 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-[#1E2436]'
                          }`}
                        >
                          {isActive ? 'Editando Escena' : `Configurar Escena ${idx + 1}`}
                        </button>
                        {categoryRules.length > 1 && (
                          <button
                            type="button"
                            onClick={() => onRemoveRule(idx)}
                            aria-label={`Quitar escena ${idx + 1}`}
                            disabled={isBusy}
                            className="h-10 px-3 rounded-lg border border-red-200 dark:border-red-900/70 bg-red-50 dark:bg-red-950/60 hover:bg-red-100 dark:hover:bg-red-900/60 text-red-700 dark:text-red-300 inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium gap-1 transition-colors disabled:opacity-50"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                            Quitar
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Editor Detallado de la Escena Activa */}
            <div className="p-4 rounded-xl bg-zinc-50 dark:bg-[#090B10] border border-zinc-200/80 dark:border-white/[0.08] flex flex-col gap-4">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-cyan-600 dark:text-cyan-400">
                  Ajustando: {activeRule.scene_label}
                </span>
                <span className="text-xs text-zinc-500 dark:text-zinc-400 tabular-nums">
                  {activeRule.custom_boxes_manual ? 'Cajas 16:9 fijadas manualmente' : 'Detección automática activa'}
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label
                    htmlFor="scene-label-input"
                    className="text-xs font-medium text-zinc-700 dark:text-zinc-300 mb-1.5 block"
                  >
                    Nombre de la Escena
                  </label>
                  <input
                    id="scene-label-input"
                    type="text"
                    value={activeRule.scene_label}
                    onChange={(e) => onUpdateActiveRule({ scene_label: e.target.value })}
                    placeholder="Ej. Cabina Mesa, Gameplay + Cámara"
                    className="w-full h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#11151F] text-sm text-zinc-900 dark:text-zinc-50 focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  />
                </div>

                <div>
                  <label
                    htmlFor="layout-mode-select"
                    className="text-xs font-medium text-zinc-700 dark:text-zinc-300 mb-1.5 block"
                  >
                    Formato de Encuadre 9:16
                  </label>
                  <select
                    id="layout-mode-select"
                    value={activeRule.layout_mode}
                    onChange={(e) => handleLayoutChange(e.target.value as LayoutMode)}
                    className="w-full h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#11151F] text-sm text-zinc-900 dark:text-zinc-50 focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  >
                    {LAYOUT_SELECT_OPTIONS.map((mode) => (
                      <option key={mode} value={mode}>
                        {LAYOUT_MODE_LABELS[mode]}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label
                    htmlFor="subtitle-preset-select"
                    className="text-xs font-medium text-zinc-700 dark:text-zinc-300 mb-1.5 flex items-center gap-1.5"
                  >
                    <Type className="w-3.5 h-3.5 text-cyan-500" />
                    Estilo de Subtítulos
                  </label>
                  <select
                    id="subtitle-preset-select"
                    value={activeRule.subtitle_preset}
                    onChange={(e) =>
                      onUpdateActiveRule({ subtitle_preset: e.target.value })
                    }
                    className="w-full h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#11151F] text-sm text-zinc-900 dark:text-zinc-50 focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  >
                    {subtitlePresets.length > 0 ? (
                      subtitlePresets.map((sp) => (
                        <option key={sp.id} value={sp.id}>
                          {sp.name}
                        </option>
                      ))
                    ) : (
                      <>
                        <option value="hormozi_pop">Hormozi Pop</option>
                        <option value="nexus_cyber_glow">Nexus Cyber Glow</option>
                        <option value="one_word_punch">One-Word Punch</option>
                        <option value="clean_apple_box">Clean Apple Box</option>
                        <option value="karaoke_duo">Karaoke Dúo</option>
                        <option value="none">Sin Subtítulos</option>
                      </>
                    )}
                  </select>
                </div>

                <div>
                  <label
                    htmlFor="subtitle-position-select"
                    className="text-xs font-medium text-zinc-700 dark:text-zinc-300 mb-1.5 block"
                  >
                    Posición Subtítulos
                  </label>
                  <select
                    id="subtitle-position-select"
                    value={activeRule.subtitle_position}
                    onChange={(e) =>
                      onUpdateActiveRule({
                        subtitle_position: e.target.value as SubtitlePosition,
                      })
                    }
                    className="w-full h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#11151F] text-sm text-zinc-900 dark:text-zinc-50 focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  >
                    <option value="auto">Automática</option>
                    <option value="top">Arriba (Top)</option>
                    <option value="center">Centro</option>
                    <option value="bottom">Abajo (Bottom)</option>
                  </select>
                </div>

                <div>
                  <label
                    htmlFor="cam-overlay-pos-select"
                    className="text-xs font-medium text-zinc-700 dark:text-zinc-300 mb-1.5 block"
                  >
                    Esquina Cámara
                  </label>
                  <select
                    id="cam-overlay-pos-select"
                    value={activeRule.cam_overlay_pos}
                    disabled={!isPipOrFloatingCam}
                    onChange={(e) =>
                      onUpdateActiveRule({
                        cam_overlay_pos: e.target.value as CamOverlayPos,
                      })
                    }
                    className="w-full h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#11151F] text-sm text-zinc-900 dark:text-zinc-50 focus:outline-none focus:ring-2 focus:ring-cyan-500 disabled:opacity-50"
                  >
                    <option value="top_right">Superior Derecha</option>
                    <option value="top_left">Superior Izquierda</option>
                    <option value="bottom_left">Inferior Izquierda</option>
                    <option value="bottom_right">Inferior Derecha</option>
                  </select>
                </div>
              </div>

              {/* Calibración Visual Studio 16:9 (Local + URL) */}
              <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
                <span className="text-[11px] text-zinc-500 dark:text-zinc-400">
                  Calibra las cajas 16:9 exactas de Cámara y Contenido en cualquier fotograma del video.
                </span>
                <button
                  type="button"
                  onClick={() => onDetectScene()}
                  disabled={isBusy || !canDetectScene}
                  className="h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#171C29] hover:bg-zinc-100 dark:hover:bg-[#1F2638] text-zinc-900 dark:text-zinc-100 inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium gap-1.5 transition-colors disabled:opacity-50 shrink-0"
                >
                  {activeOperation === 'detect_scene' ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-cyan-400" />
                  ) : (
                    <Sliders className="w-3.5 h-3.5 text-cyan-500" />
                  )}
                  Detectar Escena &amp; Studio
                </button>
              </div>
            </div>

            {sceneData && (
              <InteractiveSceneStudio
                sceneData={sceneData}
                layoutMode={activeRule.layout_mode}
                camOverlayPos={activeRule.cam_overlay_pos}
                subtitlePreset={activeRule.subtitle_preset}
                subtitlePosition={activeRule.subtitle_position}
                customCamBox={displayCamBox}
                customContentBox={displayContentBox}
                customBoxesManual={activeRule.custom_boxes_manual}
                videoDurationSec={sceneData.duration_sec ?? preAnalyzeData?.duration_sec ?? null}
                sampleTimestampSec={activeRule.sample_timestamp_sec}
                isDetectingFrame={activeOperation === 'detect_scene'}
                studioCanvasRef={studioCanvasRef}
                onSetCustomBoxesManual={onSetCustomBoxesManual}
                onStartDragging={onStartDragging}
                onSeekTimestamp={(sec) => onDetectScene(sec, true)}
              />
            )}
          </div>

          {/* Columna Derecha: Previsualización en Tiempo Real 9:16 + Resumen de Escenas */}
          <div className="lg:col-span-5 flex flex-col gap-4">
            <div className="p-5 rounded-xl bg-zinc-50 dark:bg-[#090B10] border border-zinc-200/80 dark:border-white/[0.08] flex flex-col items-center gap-4">
              <div className="w-full flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Type className="w-4 h-4 text-cyan-500" />
                  <span className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                    Previsualización en Vivo 9:16
                  </span>
                </div>
                <span className="text-[11px] font-medium text-zinc-500 dark:text-zinc-400 truncate max-w-[160px]">
                  {activeRule.scene_label}
                </span>
              </div>

              <div
                data-testid="live-subtitle-preview"
                data-subtitle-preset={activeRule.subtitle_preset}
                data-subtitle-position={activeRule.subtitle_position}
                data-layout-mode={activeRule.layout_mode}
                className="relative w-44 aspect-[9/16] rounded-2xl overflow-hidden border-2 border-zinc-300 dark:border-white/[0.14] bg-zinc-950 shadow-lg flex flex-col p-2"
              >
                <LiveSceneCropPreview
                  frameUrl={sceneData?.frame_url ?? activeRule.frame_url ?? null}
                  layoutMode={activeRule.layout_mode}
                  camOverlayPos={activeRule.cam_overlay_pos}
                  customCamBox={displayCamBox}
                  customContentBox={displayContentBox}
                />
                <LiveSubtitleOverlay
                  subtitlePreset={activeRule.subtitle_preset}
                  subtitlePosition={activeRule.subtitle_position}
                  layoutMode={activeRule.layout_mode}
                  showNoneBadge={true}
                />
              </div>

              <div className="w-full flex flex-wrap gap-1.5 text-[11px]">
                <span className="px-2 py-1 rounded-lg bg-white dark:bg-[#171C29] border border-zinc-200/80 dark:border-white/[0.08] font-medium text-zinc-800 dark:text-zinc-200">
                  Preset: {SUBTITLE_PRESET_LABELS[activeRule.subtitle_preset] || activeRule.subtitle_preset}
                </span>
                <span className="px-2 py-1 rounded-lg bg-white dark:bg-[#171C29] border border-zinc-200/80 dark:border-white/[0.08] font-medium text-zinc-800 dark:text-zinc-200">
                  Posición: {SUBTITLE_POSITION_LABELS[activeRule.subtitle_position]}
                </span>
                <span className="px-2 py-1 rounded-lg bg-white dark:bg-[#171C29] border border-zinc-200/80 dark:border-white/[0.08] font-medium text-zinc-800 dark:text-zinc-200">
                  Encuadre: {activeRule.layout_mode}
                </span>
              </div>
            </div>

            {/* Resumen de Escenas del Perfil */}
            <div className="p-4 rounded-xl bg-zinc-50 dark:bg-[#090B10] border border-zinc-200/80 dark:border-white/[0.08] flex flex-col gap-2">
              <span className="text-xs font-semibold text-zinc-900 dark:text-zinc-100 tabular-nums">
                Escenas configuradas ({categoryRules.length}):
              </span>
              <ul className="flex flex-col gap-1.5 text-xs text-zinc-600 dark:text-zinc-300">
                {categoryRules.map((rule) => (
                  <li
                    key={rule.rule_id}
                    className="flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg bg-white dark:bg-[#11151F] border border-zinc-200/70 dark:border-white/[0.06]"
                  >
                    <span className="font-medium truncate">
                      {rule.scene_label}
                    </span>
                    <span className="text-[11px] text-cyan-600 dark:text-cyan-400 shrink-0">
                      {rule.layout_mode} · {rule.subtitle_preset}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>

        {/* Footer Acciones (100% h-10) */}
        <div className="p-6 border-t border-zinc-200/80 dark:border-white/[0.08] flex flex-wrap items-center justify-between gap-3">
          <button
            type="button"
            onClick={onClose}
            className="h-10 px-4 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-zinc-100 dark:bg-[#090B10] hover:bg-zinc-200/70 dark:hover:bg-[#171C29] text-zinc-800 dark:text-zinc-200 inline-flex items-center justify-center whitespace-nowrap leading-none text-sm font-medium transition-colors"
          >
            Cancelar
          </button>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={onDiscoverCandidates}
              disabled={isBusy}
              className="h-10 px-4 rounded-lg border border-cyan-500/40 bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-700 dark:text-cyan-300 inline-flex items-center justify-center whitespace-nowrap leading-none text-sm font-medium gap-2 transition-colors disabled:opacity-50"
            >
              {activeOperation === 'discover' ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Scissors className="w-4 h-4" />
              )}
              Escanear Clips IA
            </button>

            <button
              type="button"
              onClick={onConfirmStart}
              disabled={isBusy}
              className="h-10 px-5 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white shadow-lg shadow-cyan-500/15 inline-flex items-center justify-center whitespace-nowrap leading-none text-sm font-semibold gap-2 transition-all disabled:opacity-50"
            >
              {activeOperation === 'process' ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Play className="w-4 h-4 fill-current" />
              )}
              Confirmar y Generar Shorts
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
