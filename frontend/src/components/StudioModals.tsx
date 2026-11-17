import type React from 'react';
import { CheckCircle2, Loader2, Move, Scissors, Sliders, X } from 'lucide-react';
import type {
  CamOverlayPos,
  LayoutMode,
  PipelineStatus,
  QueuesResponse,
  RenderedShortItem,
  ShortSceneDetectResponse,
  SubtitlePosition,
} from '../types';
import { LiveSubtitleOverlay, SceneLayoutWireframe } from './LiveSubtitlePreview';
import { SocialStatusBars } from './SocialStatusBars';
import {
  type ActiveOperation,
  SHORT_REEDIT_LAYOUTS,
  SHORT_REEDIT_SUBTITLE_PRESETS,
  withCacheBust,
} from './studioHelpers';

export interface ReeditDragState {
  target: 'cam' | 'content';
  mode: 'move' | 'resize';
  startX: number;
  startY: number;
  origBox: [number, number, number, number];
}

export function ScheduleBatchModal({
  computedOroCount,
  computedPlataCount,
  computedMehCount,
  computedYoutubeEligibleCount,
  youtubeScheduleTime,
  instagramScheduleTime,
  tiktokScheduleTime,
  scheduleIntervalMinutes,
  isBusy,
  activeOperation,
  onYoutubeScheduleTimeChange,
  onInstagramScheduleTimeChange,
  onTiktokScheduleTimeChange,
  onScheduleIntervalMinutesChange,
  onClose,
  onSubmit,
}: {
  computedOroCount: number;
  computedPlataCount: number;
  computedMehCount: number;
  computedYoutubeEligibleCount: number;
  youtubeScheduleTime: string;
  instagramScheduleTime: string;
  tiktokScheduleTime: string;
  scheduleIntervalMinutes: number;
  isBusy: boolean;
  activeOperation: ActiveOperation;
  onYoutubeScheduleTimeChange: (v: string) => void;
  onInstagramScheduleTimeChange: (v: string) => void;
  onTiktokScheduleTimeChange: (v: string) => void;
  onScheduleIntervalMinutesChange: (v: number) => void;
  onClose: () => void;
  onSubmit: (e: React.FormEvent) => void;
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Resumen de Generación y Programación de Shorts"
      className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/70 backdrop-blur-sm p-4"
    >
      <div className="bg-white dark:bg-[#171C29] rounded-2xl border border-zinc-200/80 dark:border-white/[0.14] shadow-2xl w-full max-w-xl p-6 flex flex-col gap-6 text-left">
        <div className="flex items-start justify-between gap-4 border-b border-zinc-200/80 dark:border-white/[0.08] pb-4">
          <div className="flex flex-col gap-1">
            <h3 className="text-lg font-semibold tracking-tight text-zinc-900 dark:text-zinc-50 flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-emerald-500 shrink-0" />
              Generación de Shorts Terminada
            </h3>
            <p className="text-sm text-zinc-700 dark:text-zinc-300 leading-relaxed">
              La generación de Shorts terminó: tenemos {computedOroCount} cantidad Oro, {computedPlataCount} cantidad de Plata y {computedMehCount} cantidad Meh. Favor seleccionar la fecha y hora de programación de los Shorts en sus respectivas plataformas.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.1] bg-zinc-100 dark:bg-[#090B10] hover:bg-zinc-200/70 dark:hover:bg-[#11151F] text-zinc-900 dark:text-zinc-100 inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium tracking-normal gap-1 transition-colors shrink-0"
          >
            <X className="w-4 h-4" />
            Cerrar
          </button>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="p-3 rounded-xl bg-amber-500/15 border border-amber-400/30">
            <span className="text-xs font-medium text-amber-800 dark:text-amber-300 block">Oro (&ge; 90 pts)</span>
            <span className="text-lg font-semibold text-amber-900 dark:text-amber-200 tabular-nums">
              {computedOroCount}
            </span>
          </div>
          <div className="p-3 rounded-xl bg-cyan-500/15 border border-cyan-400/30">
            <span className="text-xs font-medium text-cyan-800 dark:text-cyan-300 block">Plata (75–89 pts)</span>
            <span className="text-lg font-semibold text-cyan-900 dark:text-cyan-200 tabular-nums">
              {computedPlataCount}
            </span>
          </div>
          <div className="p-3 rounded-xl bg-zinc-500/15 border border-zinc-500/30">
            <span className="text-xs font-medium text-zinc-600 dark:text-zinc-300 block">Meh (&lt; 75 pts)</span>
            <span className="text-lg font-semibold text-zinc-800 dark:text-zinc-200 tabular-nums">
              {computedMehCount}
            </span>
          </div>
          <div className="p-3 rounded-xl bg-emerald-500/15 border border-emerald-400/30">
            <span className="text-xs font-medium text-emerald-800 dark:text-emerald-300 block">Redes Activas (YT · IG · TT · FB)</span>
            <span className="text-lg font-semibold text-emerald-900 dark:text-emerald-200 tabular-nums">
              {computedYoutubeEligibleCount}
            </span>
          </div>
        </div>

        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label
                htmlFor="youtube-schedule-input"
                className="text-xs font-medium text-zinc-700 dark:text-zinc-300 mb-1.5 block"
              >
                Fecha y Hora YouTube Shorts (Todos los Shorts)
              </label>
              <input
                id="youtube-schedule-input"
                type="datetime-local"
                required
                value={youtubeScheduleTime}
                onChange={(e) => onYoutubeScheduleTimeChange(e.target.value)}
                className="w-full h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.1] bg-white dark:bg-[#090B10] text-sm text-zinc-900 dark:text-zinc-50 tabular-nums focus:outline-none focus:ring-2 focus:ring-cyan-500"
              />
            </div>

            <div>
              <label
                htmlFor="instagram-schedule-input"
                className="text-xs font-medium text-zinc-700 dark:text-zinc-300 mb-1.5 block"
              >
                Fecha y Hora Instagram Reels
              </label>
              <input
                id="instagram-schedule-input"
                type="datetime-local"
                required
                value={instagramScheduleTime}
                onChange={(e) => onInstagramScheduleTimeChange(e.target.value)}
                className="w-full h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.1] bg-white dark:bg-[#090B10] text-sm text-zinc-900 dark:text-zinc-50 tabular-nums focus:outline-none focus:ring-2 focus:ring-cyan-500"
              />
            </div>

            <div>
              <label
                htmlFor="tiktok-schedule-input"
                className="text-xs font-medium text-zinc-700 dark:text-zinc-300 mb-1.5 block"
              >
                Fecha y Hora TikTok
              </label>
              <input
                id="tiktok-schedule-input"
                type="datetime-local"
                required
                value={tiktokScheduleTime}
                onChange={(e) => onTiktokScheduleTimeChange(e.target.value)}
                className="w-full h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.1] bg-white dark:bg-[#090B10] text-sm text-zinc-900 dark:text-zinc-50 tabular-nums focus:outline-none focus:ring-2 focus:ring-cyan-500"
              />
            </div>

            <div>
              <label
                htmlFor="interval-minutes-select"
                className="text-xs font-medium text-zinc-700 dark:text-zinc-300 mb-1.5 block"
              >
                Intervalo entre Shorts Consecutivos
              </label>
              <select
                id="interval-minutes-select"
                value={scheduleIntervalMinutes}
                onChange={(e) => onScheduleIntervalMinutesChange(Number(e.target.value))}
                className="w-full h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.1] bg-white dark:bg-[#090B10] text-sm text-zinc-900 dark:text-zinc-50 tabular-nums focus:outline-none focus:ring-2 focus:ring-cyan-500"
              >
                <option value={60}>Cada 1 hora (60 min)</option>
                <option value={30}>Cada 30 minutos</option>
                <option value={120}>Cada 2 horas (120 min)</option>
                <option value={180}>Cada 3 horas (180 min)</option>
                <option value={0}>Misma hora simultánea</option>
              </select>
            </div>
          </div>

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="submit"
              disabled={isBusy}
              className="h-10 px-5 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white shadow-lg shadow-cyan-500/15 inline-flex items-center justify-center whitespace-nowrap leading-none text-sm font-medium tracking-normal gap-2 transition-all disabled:opacity-50"
            >
              {activeOperation === 'schedule_batch' ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <CheckCircle2 className="w-4 h-4" />
              )}
              Confirmar Fecha y Hora y Subir a Redes
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export function FloatingShortPlayer({
  activeShortPlayer,
  floatingOffset,
  scheduleValue,
  queues,
  pipelineStatus,
  cacheVersion,
  isBusy,
  showSocialDetails = false,
  onStartDrag,
  onClose,
  onScheduleValueChange,
  onScheduleSingle,
  onOpenLayoutEditor,
  onExclusivePlay,
}: {
  activeShortPlayer: RenderedShortItem;
  floatingOffset: { x: number; y: number };
  scheduleValue: string;
  queues: QueuesResponse;
  pipelineStatus: PipelineStatus | null;
  cacheVersion?: number;
  isBusy: boolean;
  showSocialDetails?: boolean;
  onStartDrag: (clientX: number, clientY: number) => void;
  onClose: () => void;
  onScheduleValueChange: (val: string) => void;
  onScheduleSingle: () => void;
  onOpenLayoutEditor: () => void;
  onExclusivePlay: (videoEl: HTMLVideoElement) => void;
}) {
  const effectiveVideoUrl = withCacheBust(activeShortPlayer.video_url, cacheVersion);
  const effectiveThumbUrl = withCacheBust(activeShortPlayer.thumbnail_url, cacheVersion);

  return (
    <div
      data-testid="floating-short-player"
      role="dialog"
      aria-modal="false"
      aria-label="Reproductor Flotante de Short"
      style={{ transform: `translate3d(${floatingOffset.x}px, ${floatingOffset.y}px, 0)` }}
      className="fixed bottom-6 right-6 z-50 w-[330px] sm:w-[370px] bg-white dark:bg-[#171C29] rounded-2xl border border-zinc-200/90 dark:border-white/[0.14] shadow-2xl overflow-hidden flex flex-col text-left"
    >
      <div
        onPointerDown={(e) => onStartDrag(e.clientX, e.clientY)}
        className="flex items-center justify-between gap-2 px-4 py-3 bg-zinc-50 dark:bg-[#11151F] border-b border-zinc-200/80 dark:border-white/[0.08] cursor-move select-none"
      >
        <div className="min-w-0 flex items-center gap-2">
          <Move className="w-4 h-4 text-cyan-500 shrink-0" />
          <div className="min-w-0">
            <h3 className="text-xs font-semibold tracking-tight text-zinc-900 dark:text-zinc-50 truncate">
              {activeShortPlayer.filename}
            </h3>
            <p className="text-[11px] text-zinc-500 dark:text-zinc-400 tabular-nums">
              Puntaje Viral: {activeShortPlayer.virality_score} pts ({activeShortPlayer.tier})
            </p>
          </div>
        </div>
        <button
          type="button"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={onClose}
          aria-label="Cerrar reproductor flotante"
          className="h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.1] bg-white dark:bg-[#090B10] hover:bg-zinc-200/70 dark:hover:bg-[#11151F] text-zinc-900 dark:text-zinc-100 inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium tracking-normal gap-1 transition-colors shrink-0"
        >
          <X className="w-4 h-4" />
          Cerrar
        </button>
      </div>

      <div className="bg-zinc-950 aspect-[9/16] max-h-[52vh] w-full flex items-center justify-center">
        <video
          key={effectiveVideoUrl}
          data-testid="short-video-player"
          src={effectiveVideoUrl}
          poster={effectiveThumbUrl}
          controls
          controlsList="nofullscreen"
          playsInline
          onDoubleClick={(e) => e.preventDefault()}
          onPlay={(e) => onExclusivePlay(e.currentTarget)}
          autoPlay
          className="w-full h-full object-contain"
        />
      </div>

      <div className="p-3 bg-zinc-50 dark:bg-[#11151F] border-t border-zinc-200/80 dark:border-white/[0.08] flex flex-col gap-2">
        <div className="flex items-center gap-1.5">
          <input
            type="datetime-local"
            aria-label={`Fecha y hora flotante de ${activeShortPlayer.filename}`}
            value={scheduleValue}
            onChange={(e) => onScheduleValueChange(e.target.value)}
            className="flex-1 min-w-0 h-10 px-2 rounded-lg border border-zinc-200/80 dark:border-white/[0.1] bg-white dark:bg-[#090B10] text-zinc-900 dark:text-zinc-50 text-[11px] font-medium tabular-nums focus:outline-none focus:ring-2 focus:ring-cyan-500"
          />
          <button
            type="button"
            onClick={onScheduleSingle}
            disabled={isBusy}
            aria-label={`Programar Short flotante ${activeShortPlayer.filename}`}
            className="h-10 px-3 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium tracking-normal transition-all disabled:opacity-50 shrink-0"
          >
            Programar
          </button>
        </div>

        {showSocialDetails && (
          <SocialStatusBars
            item={activeShortPlayer}
            queues={queues}
            pipelineStatus={pipelineStatus}
            compact={true}
          />
        )}

        <div className="flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={onOpenLayoutEditor}
            disabled={isBusy}
            aria-label={`Editar Short flotante ${activeShortPlayer.filename}`}
            className="h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.1] bg-white dark:bg-[#090B10] hover:bg-zinc-100 dark:hover:bg-[#171C29] text-zinc-900 dark:text-zinc-100 inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium tracking-normal gap-1.5 transition-colors disabled:opacity-50"
          >
            <Sliders className="w-3.5 h-3.5 text-cyan-500" />
            Editar
          </button>
          <span className="text-[11px] font-medium text-zinc-600 dark:text-zinc-300 truncate tabular-nums">
            {activeShortPlayer.scheduled_ast || 'Listo en local'}
          </span>
        </div>
      </div>
    </div>
  );
}

export function ShortLayoutEditorModal({
  reeditShort,
  reeditScene,
  reeditLayoutMode,
  reeditCamPos,
  reeditSubPreset,
  reeditSubPos,
  reeditCamBox,
  reeditContentBox,
  reeditCanvasRef,
  reeditTrimStart,
  reeditTrimEnd,
  reeditMinTrim,
  reeditMaxTrim,
  reeditMediaUrl,
  activeOperation,
  isBusy,
  onClose,
  onApplyPreset,
  onCamPosChange,
  onSubPresetChange,
  onSubPosChange,
  onChangeTrimRange,
  onStartDragging,
  onSubmitRerender,
}: {
  reeditShort: RenderedShortItem;
  reeditScene: ShortSceneDetectResponse | null;
  reeditLayoutMode: LayoutMode;
  reeditCamPos: CamOverlayPos;
  reeditSubPreset: string;
  reeditSubPos: SubtitlePosition;
  reeditCamBox: [number, number, number, number];
  reeditContentBox: [number, number, number, number];
  reeditCanvasRef: React.RefObject<HTMLDivElement>;
  reeditTrimStart?: number;
  reeditTrimEnd?: number;
  reeditMinTrim?: number;
  reeditMaxTrim?: number;
  reeditMediaUrl?: string | null;
  activeOperation: ActiveOperation;
  isBusy: boolean;
  onClose: () => void;
  onApplyPreset: (mode: LayoutMode) => void;
  onCamPosChange: (pos: CamOverlayPos) => void;
  onSubPresetChange: (preset: string) => void;
  onSubPosChange: (pos: SubtitlePosition) => void;
  onChangeTrimRange?: (startSec: number, endSec: number) => void;
  onStartDragging: (drag: ReeditDragState) => void;
  onSubmitRerender: (e?: React.FormEvent) => void;
}) {
  const minTrimVal = Number.isFinite(reeditMinTrim) ? Number(reeditMinTrim) : 0;
  const fallbackDur = Number(reeditShort.duration_sec || 30);
  const trimStartVal = Number.isFinite(reeditTrimStart) ? Number(reeditTrimStart) : 0;
  const trimEndVal = Number.isFinite(reeditTrimEnd) ? Number(reeditTrimEnd) : fallbackDur;
  const maxTrimVal = Number.isFinite(reeditMaxTrim)
    ? Math.max(trimEndVal, Number(reeditMaxTrim))
    : Math.max(trimEndVal, fallbackDur + 30);
  const minClipDuration = 3.0;
  const resultDuration = Math.max(0, Number((trimEndVal - trimStartVal).toFixed(1)));

  const handleAdjustStart = (delta: number) => {
    if (!onChangeTrimRange) return;
    const clampedStart = Math.max(
      minTrimVal,
      Math.min(trimEndVal - minClipDuration, Number((trimStartVal + delta).toFixed(1)))
    );
    onChangeTrimRange(clampedStart, trimEndVal);
  };

  const handleAdjustEnd = (delta: number) => {
    if (!onChangeTrimRange) return;
    const clampedEnd = Math.min(
      maxTrimVal,
      Math.max(trimStartVal + minClipDuration, Number((trimEndVal + delta).toFixed(1)))
    );
    onChangeTrimRange(trimStartVal, clampedEnd);
  };
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Editor de Layout del Short"
      className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/75 backdrop-blur-sm p-4"
    >
      <form
        onSubmit={(e) => onSubmitRerender(e)}
        className="bg-white dark:bg-[#171C29] rounded-2xl border border-zinc-200/80 dark:border-white/[0.14] shadow-2xl w-full max-w-5xl max-h-[92vh] flex flex-col overflow-hidden text-left"
      >
        <div className="px-6 py-4 border-b border-zinc-200/80 dark:border-white/[0.08] flex items-center justify-between gap-4">
          <div className="min-w-0">
            <h3 className="text-lg font-semibold tracking-tight text-zinc-900 dark:text-zinc-50 truncate">
              Editar Layout Post-Previsualización · {reeditShort.filename}
            </h3>
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              Ajusta las zonas de Cámara y Contenido o cambia el diseño y guarda para re-renderizar sin música de fondo.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.1] bg-zinc-100 dark:bg-[#090B10] hover:bg-zinc-200/70 dark:hover:bg-[#11151F] text-zinc-900 dark:text-zinc-100 inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium tracking-normal gap-1 transition-colors shrink-0"
          >
            <X className="w-4 h-4" />
            Cerrar
          </button>
        </div>

        <div className="p-6 overflow-y-auto grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Columna Izquierda: Presets rápidos + Canvas 16:9 Interactivo */}
          <div className="lg:col-span-7 flex flex-col gap-4">
            <div className="flex flex-wrap gap-2">
              {(
                [
                  { id: 'split_50_50', label: '50/50 Limpio' },
                  { id: 'split_streamer', label: 'Streamer Arriba' },
                  { id: 'ometv', label: 'OmeTV Banner' },
                  { id: 'fullscreen', label: 'Solo Rostro 9:16' },
                  { id: 'blur_16_9_cam', label: '16:9 Blur + Cam' },
                ] as Array<{ id: LayoutMode; label: string }>
              ).map((presetBtn) => (
                <button
                  key={presetBtn.id}
                  type="button"
                  onClick={() => onApplyPreset(presetBtn.id)}
                  className={`h-10 px-3 rounded-lg border text-xs font-medium inline-flex items-center justify-center whitespace-nowrap leading-none transition-colors ${
                    reeditLayoutMode === presetBtn.id
                      ? 'bg-gradient-to-r from-cyan-500 to-blue-600 border-transparent text-white shadow-sm'
                      : 'border-zinc-200/80 dark:border-white/[0.08] bg-zinc-50 dark:bg-[#090B10] text-zinc-800 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-[#11151F]'
                  }`}
                >
                  {presetBtn.label}
                </button>
              ))}
            </div>

            <div
              ref={reeditCanvasRef}
              data-testid="reedit-layout-canvas"
              className="relative aspect-video w-full rounded-xl overflow-hidden bg-zinc-950 border border-zinc-200/80 dark:border-white/[0.08] select-none"
            >
              {activeOperation === 'load_short_editor' && !reeditScene && (
                <div className="absolute inset-0 flex items-center justify-center bg-zinc-950/80 text-white gap-2 text-xs font-medium z-20">
                  <Loader2 className="w-4 h-4 animate-spin text-cyan-400" />
                  Analizando fotograma del clip...
                </div>
              )}
              {reeditScene?.frame_url && (
                <img
                  src={reeditScene.frame_url}
                  alt={`Fotograma de ${reeditShort.filename}`}
                  className="w-full h-full object-contain pointer-events-none"
                />
              )}

              {/* Caja Contenido (Verde) */}
              <div
                onPointerDown={(e) => {
                  e.stopPropagation();
                  onStartDragging({
                    target: 'content',
                    mode: 'move',
                    startX: e.clientX,
                    startY: e.clientY,
                    origBox: reeditContentBox,
                  });
                }}
                style={{
                  left: `${reeditContentBox[0] * 100}%`,
                  top: `${reeditContentBox[1] * 100}%`,
                  width: `${reeditContentBox[2] * 100}%`,
                  height: `${reeditContentBox[3] * 100}%`,
                }}
                className="absolute border-2 border-emerald-400 bg-emerald-500/15 cursor-move rounded"
              >
                <span className="px-1.5 py-0.5 text-[10px] font-semibold bg-emerald-500 text-zinc-950 rounded-br">
                  Contenido
                </span>
                <div
                  onPointerDown={(e) => {
                    e.stopPropagation();
                    onStartDragging({
                      target: 'content',
                      mode: 'resize',
                      startX: e.clientX,
                      startY: e.clientY,
                      origBox: reeditContentBox,
                    });
                  }}
                  className="absolute right-0 bottom-0 w-3.5 h-3.5 bg-emerald-400 cursor-se-resize rounded-tl"
                />
              </div>

              {/* Caja Cámara (Cian) */}
              <div
                onPointerDown={(e) => {
                  e.stopPropagation();
                  onStartDragging({
                    target: 'cam',
                    mode: 'move',
                    startX: e.clientX,
                    startY: e.clientY,
                    origBox: reeditCamBox,
                  });
                }}
                style={{
                  left: `${reeditCamBox[0] * 100}%`,
                  top: `${reeditCamBox[1] * 100}%`,
                  width: `${reeditCamBox[2] * 100}%`,
                  height: `${reeditCamBox[3] * 100}%`,
                }}
                className="absolute border-2 border-cyan-400 bg-cyan-500/20 cursor-move rounded"
              >
                <span className="px-1.5 py-0.5 text-[10px] font-semibold bg-cyan-500 text-zinc-950 rounded-br">
                  Cámara
                </span>
                <div
                  onPointerDown={(e) => {
                    e.stopPropagation();
                    onStartDragging({
                      target: 'cam',
                      mode: 'resize',
                      startX: e.clientX,
                      startY: e.clientY,
                      origBox: reeditCamBox,
                    });
                  }}
                  className="absolute right-0 bottom-0 w-3.5 h-3.5 bg-cyan-400 cursor-se-resize rounded-tl"
                />
              </div>
            </div>

            <p className="text-[11px] text-zinc-500 dark:text-zinc-400 tabular-nums">
              {reeditScene
                ? `Fuente: ${reeditScene.resolution} · Rostros: ${reeditScene.faces_detected} · ${
                    reeditScene.has_source_16_9
                      ? 'Recorte 16:9 original disponible'
                      : 'Clip vertical existente (se re-estiliza con el nuevo layout)'
                  }`
                : 'Arrastra o redimensiona los recuadros de Cámara (cian) y Contenido (verde).'}
            </p>
          </div>

          {/* Columna Derecha: Controles exactos + Previsualización 9:16 */}
          <div className="lg:col-span-5 flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-xs font-medium text-zinc-700 dark:text-zinc-300">
              Layout de Salida (9:16)
              <select
                aria-label="Layout del Short"
                value={reeditLayoutMode}
                onChange={(e) => onApplyPreset(e.target.value as LayoutMode)}
                className="h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.1] bg-zinc-50 dark:bg-[#090B10] text-zinc-900 dark:text-zinc-50 text-xs font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
              >
                {SHORT_REEDIT_LAYOUTS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>

            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1 text-xs font-medium text-zinc-700 dark:text-zinc-300">
                Esquina de Cámara
                <select
                  aria-label="Posición de Cámara del Short"
                  value={reeditCamPos}
                  onChange={(e) => onCamPosChange(e.target.value as CamOverlayPos)}
                  className="h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.1] bg-zinc-50 dark:bg-[#090B10] text-zinc-900 dark:text-zinc-50 text-xs font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
                >
                  <option value="top_right">Arriba Derecha</option>
                  <option value="top_left">Arriba Izquierda</option>
                  <option value="bottom_right">Abajo Derecha</option>
                  <option value="bottom_left">Abajo Izquierda</option>
                </select>
              </label>

              <label className="flex flex-col gap-1 text-xs font-medium text-zinc-700 dark:text-zinc-300">
                Posición Subtítulos
                <select
                  aria-label="Posición de Subtítulos del Short"
                  value={reeditSubPos}
                  onChange={(e) => onSubPosChange(e.target.value as SubtitlePosition)}
                  className="h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.1] bg-zinc-50 dark:bg-[#090B10] text-zinc-900 dark:text-zinc-50 text-xs font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
                >
                  <option value="auto">Automática</option>
                  <option value="top">Superior</option>
                  <option value="center">Centro</option>
                  <option value="bottom">Inferior</option>
                </select>
              </label>
            </div>

            <label className="flex flex-col gap-1 text-xs font-medium text-zinc-700 dark:text-zinc-300">
              Estilo de Subtítulos
              <select
                aria-label="Estilo de Subtítulos del Short"
                value={reeditSubPreset}
                onChange={(e) => onSubPresetChange(e.target.value)}
                className="h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.1] bg-zinc-50 dark:bg-[#090B10] text-zinc-900 dark:text-zinc-50 text-xs font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500"
              >
                {SHORT_REEDIT_SUBTITLE_PRESETS.map((sp) => (
                  <option key={sp.value} value={sp.value}>
                    {sp.label}
                  </option>
                ))}
              </select>
            </label>

            {/* Panel de Recorte y Extensión de Duración (±30s contexto) */}
            <div className="p-3.5 rounded-xl border border-amber-500/30 bg-amber-500/5 dark:bg-[#090B10] space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-zinc-900 dark:text-zinc-100">
                  <Scissors className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                  <span>Duración y Recorte del Short (±30s contexto)</span>
                </div>
                <span className="px-2 py-0.5 rounded-md bg-amber-500/15 border border-amber-500/30 text-[11px] font-semibold text-amber-700 dark:text-amber-300 tabular-nums">
                  {resultDuration.toFixed(1)}s ({trimStartVal.toFixed(1)}s → {trimEndVal.toFixed(1)}s)
                </span>
              </div>

              {reeditMediaUrl && (
                <video
                  key={reeditMediaUrl}
                  src={reeditMediaUrl}
                  controls
                  playsInline
                  preload="metadata"
                  className="w-full aspect-video rounded-lg bg-black border border-zinc-200/80 dark:border-white/[0.08]"
                />
              )}

              <div className="flex flex-col gap-3">
                <div className="space-y-1.5">
                  <span className="text-[11px] font-medium text-zinc-600 dark:text-zinc-400 block tabular-nums">
                    Inicio del Clip (mín {minTrimVal.toFixed(1)}s)
                  </span>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <button
                      type="button"
                      disabled={isBusy}
                      aria-label="Alargar inicio -5s"
                      onClick={() => handleAdjustStart(-5)}
                      className="h-10 px-2.5 rounded-lg border border-zinc-200 dark:border-white/[0.08] bg-white dark:bg-[#171C29] text-xs font-semibold text-zinc-800 dark:text-zinc-100 inline-flex items-center justify-center tabular-nums disabled:opacity-50"
                    >
                      -5s
                    </button>
                    <button
                      type="button"
                      disabled={isBusy}
                      aria-label="Alargar inicio -1s"
                      onClick={() => handleAdjustStart(-1)}
                      className="h-10 px-2.5 rounded-lg border border-zinc-200 dark:border-white/[0.08] bg-white dark:bg-[#171C29] text-xs font-semibold text-zinc-800 dark:text-zinc-100 inline-flex items-center justify-center tabular-nums disabled:opacity-50"
                    >
                      -1s
                    </button>
                    <input
                      type="number"
                      step="0.5"
                      aria-label="Segundo de inicio del Short"
                      value={trimStartVal}
                      onChange={(e) => {
                        const raw = Number(e.target.value);
                        if (!Number.isNaN(raw) && onChangeTrimRange) {
                          const clamped = Math.max(
                            minTrimVal,
                            Math.min(trimEndVal - minClipDuration, Number(raw.toFixed(1)))
                          );
                          onChangeTrimRange(clamped, trimEndVal);
                        }
                      }}
                      className="w-20 h-10 px-2 rounded-lg border border-zinc-200 dark:border-white/[0.1] bg-white dark:bg-[#11151F] text-xs font-semibold text-center text-zinc-900 dark:text-zinc-50 tabular-nums"
                    />
                    <button
                      type="button"
                      disabled={isBusy}
                      aria-label="Acortar inicio +1s"
                      onClick={() => handleAdjustStart(1)}
                      className="h-10 px-2.5 rounded-lg border border-zinc-200 dark:border-white/[0.08] bg-white dark:bg-[#171C29] text-xs font-semibold text-zinc-800 dark:text-zinc-100 inline-flex items-center justify-center tabular-nums disabled:opacity-50"
                    >
                      +1s
                    </button>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <span className="text-[11px] font-medium text-zinc-600 dark:text-zinc-400 block tabular-nums">
                    Fin del Clip (máx {maxTrimVal.toFixed(1)}s)
                  </span>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <button
                      type="button"
                      disabled={isBusy}
                      aria-label="Acortar fin -5s"
                      onClick={() => handleAdjustEnd(-5)}
                      className="h-10 px-2.5 rounded-lg border border-zinc-200 dark:border-white/[0.08] bg-white dark:bg-[#171C29] text-xs font-semibold text-zinc-800 dark:text-zinc-100 inline-flex items-center justify-center tabular-nums disabled:opacity-50"
                    >
                      -5s
                    </button>
                    <button
                      type="button"
                      disabled={isBusy}
                      aria-label="Acortar fin -1s"
                      onClick={() => handleAdjustEnd(-1)}
                      className="h-10 px-2.5 rounded-lg border border-zinc-200 dark:border-white/[0.08] bg-white dark:bg-[#171C29] text-xs font-semibold text-zinc-800 dark:text-zinc-100 inline-flex items-center justify-center tabular-nums disabled:opacity-50"
                    >
                      -1s
                    </button>
                    <input
                      type="number"
                      step="0.5"
                      aria-label="Segundo de fin del Short"
                      value={trimEndVal}
                      onChange={(e) => {
                        const raw = Number(e.target.value);
                        if (!Number.isNaN(raw) && onChangeTrimRange) {
                          const clamped = Math.min(
                            maxTrimVal,
                            Math.max(trimStartVal + minClipDuration, Number(raw.toFixed(1)))
                          );
                          onChangeTrimRange(trimStartVal, clamped);
                        }
                      }}
                      className="w-20 h-10 px-2 rounded-lg border border-zinc-200 dark:border-white/[0.1] bg-white dark:bg-[#11151F] text-xs font-semibold text-center text-zinc-900 dark:text-zinc-50 tabular-nums"
                    />
                    <button
                      type="button"
                      disabled={isBusy}
                      aria-label="Alargar fin +1s"
                      onClick={() => handleAdjustEnd(1)}
                      className="h-10 px-2.5 rounded-lg border border-zinc-200 dark:border-white/[0.08] bg-white dark:bg-[#171C29] text-xs font-semibold text-zinc-800 dark:text-zinc-100 inline-flex items-center justify-center tabular-nums disabled:opacity-50"
                    >
                      +1s
                    </button>
                    <button
                      type="button"
                      disabled={isBusy}
                      aria-label="Alargar fin +5s"
                      onClick={() => handleAdjustEnd(5)}
                      className="h-10 px-2.5 rounded-lg border border-cyan-500/40 bg-cyan-500/15 text-xs font-semibold text-cyan-800 dark:text-cyan-200 inline-flex items-center justify-center tabular-nums disabled:opacity-50"
                    >
                      +5s
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* Esquema visual 9:16 del resultado con Subtítulos en vivo */}
            <div className="p-3 rounded-xl border border-zinc-200/80 dark:border-white/[0.08] bg-zinc-50 dark:bg-[#090B10] flex items-center gap-4">
              <div className="w-24 aspect-[9/16] rounded-xl bg-zinc-950 border border-white/[0.14] overflow-hidden flex flex-col p-1.5 shrink-0 relative">
                <SceneLayoutWireframe
                  layoutMode={reeditLayoutMode}
                  camOverlayPos={reeditCamPos}
                  compact={true}
                />
                <LiveSubtitleOverlay
                  subtitlePreset={reeditSubPreset}
                  subtitlePosition={reeditSubPos}
                  layoutMode={reeditLayoutMode}
                  showNoneBadge={false}
                />
              </div>
              <div className="text-[11px] text-zinc-600 dark:text-zinc-300 flex flex-col gap-1 tabular-nums">
                <span className="font-semibold text-zinc-900 dark:text-zinc-100">
                  Vista 9:16 ({reeditLayoutMode})
                </span>
                <span>Cámara: [{reeditCamBox.map((n) => n.toFixed(2)).join(', ')}]</span>
                <span>Contenido: [{reeditContentBox.map((n) => n.toFixed(2)).join(', ')}]</span>
                <span className="text-emerald-600 dark:text-emerald-400 font-medium">
                  Audio: 100% limpio (sin música de fondo, -14 dBFS)
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="px-6 py-4 border-t border-zinc-200/80 dark:border-white/[0.08] bg-zinc-50 dark:bg-[#11151F] flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={() => onApplyPreset(reeditLayoutMode)}
            className="h-10 px-4 rounded-lg border border-zinc-200/80 dark:border-white/[0.1] bg-white dark:bg-[#090B10] hover:bg-zinc-100 dark:hover:bg-[#171C29] text-zinc-800 dark:text-zinc-200 inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium tracking-normal transition-colors"
          >
            Restablecer zonas
          </button>
          <button
            type="button"
            onClick={onClose}
            className="h-10 px-4 rounded-lg border border-zinc-200/80 dark:border-white/[0.1] bg-white dark:bg-[#090B10] hover:bg-zinc-100 dark:hover:bg-[#171C29] text-zinc-800 dark:text-zinc-200 inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium tracking-normal transition-colors"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={isBusy}
            aria-label="Guardar y Re-renderizar Short"
            className="h-10 px-5 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white shadow-lg shadow-cyan-500/15 inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium tracking-normal gap-2 transition-all disabled:opacity-50"
          >
            {activeOperation === 'rerender_short' ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Re-renderizando...
              </>
            ) : (
              'Guardar y Re-renderizar'
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
