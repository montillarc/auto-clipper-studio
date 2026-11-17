import type React from 'react';
import { Activity, X } from 'lucide-react';
import type { PipelineStatus, SourceType } from '../types';
import { extractYouTubeEmbedUrl, pauseAllVideosExcept } from './studioHelpers';

export function ProcessMonitorSection({
  pipelineStatus,
  sourceType,
  selectedVideo,
  youtubeUrl,
  isBusy,
  sourceVideoRef,
  onCancelPipeline,
}: {
  pipelineStatus: PipelineStatus | null;
  sourceType: SourceType;
  selectedVideo: string;
  youtubeUrl: string;
  isBusy: boolean;
  sourceVideoRef: React.RefObject<HTMLVideoElement>;
  onCancelPipeline: () => void;
}) {
  const candidatePreview =
    pipelineStatus?.source_preview_url ||
    (sourceType === 'youtube_url' && youtubeUrl
      ? youtubeUrl
      : selectedVideo
      ? `/api/media/source/${encodeURIComponent(selectedVideo)}`
      : undefined);
  const ytEmbedUrl = extractYouTubeEmbedUrl(candidatePreview);
  const isDirectMediaStream = Boolean(
    candidatePreview &&
      (candidatePreview.startsWith('/api/media/') ||
        /\.(mp4|mov|mkv|webm)(\?|$)/i.test(candidatePreview))
  );
  const progress = Math.min(100, Math.max(0, pipelineStatus?.progress_percent ?? 0));

  return (
    <section
      id="process-monitor-section"
      className="bg-white dark:bg-[#11151F]/90 backdrop-blur-md rounded-2xl border border-zinc-200/80 dark:border-white/[0.08] shadow-sm p-6 flex flex-col gap-5 text-left"
    >
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2">
        <div>
          <h2 className="text-xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50 flex items-center gap-2">
            <Activity className="w-5 h-5 text-cyan-500" />
            Monitor de Proceso del Video
          </h2>
          {(pipelineStatus?.current_video || selectedVideo || youtubeUrl) && (
            <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5 tabular-nums">
              {pipelineStatus?.current_video || selectedVideo || youtubeUrl}
            </p>
          )}
        </div>

        {(pipelineStatus?.status === 'RUNNING' || pipelineStatus?.status === 'STARTED') && (
          <div className="flex items-center gap-3 self-start md:self-auto">
            <button
              type="button"
              onClick={onCancelPipeline}
              disabled={isBusy}
              aria-label="Cancelar Proceso de Generación"
              className="h-10 px-3 rounded-lg border border-red-200 dark:border-red-900/70 bg-red-50 dark:bg-red-950/60 hover:bg-red-100 dark:hover:bg-red-900/60 text-red-700 dark:text-red-300 inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium tracking-normal gap-1.5 transition-colors disabled:opacity-50"
            >
              <X className="w-3.5 h-3.5" />
              Cancelar Proceso
            </button>
          </div>
        )}
      </div>

      {/* 1. Visualización en Grande del Video en Trabajo (ENCIMA de la barra de carga) */}
      <div className="w-full flex flex-col gap-2">
        <div className="w-full rounded-xl overflow-hidden border border-zinc-200/80 dark:border-white/[0.08] bg-zinc-950 aspect-video max-h-[540px] flex items-center justify-center">
          {ytEmbedUrl ? (
            <iframe
              data-testid="source-video-player"
              src={ytEmbedUrl}
              title="Vista previa del video de YouTube en trabajo"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              className="w-full h-full border-0"
            />
          ) : (
            <video
              ref={sourceVideoRef}
              data-testid="source-video-player"
              src={isDirectMediaStream ? candidatePreview : undefined}
              controls
              controlsList="nofullscreen"
              onDoubleClick={(e) => e.preventDefault()}
              onPlay={(e) => pauseAllVideosExcept(e.currentTarget)}
              preload="metadata"
              className="w-full h-full object-contain"
            />
          )}
        </div>
      </div>

      {/* 2. Barra de Carga Porcentual y Detalle Breve de la Acción (DEBAJO del video) */}
      <div className="w-full p-4 rounded-xl bg-zinc-50 dark:bg-[#090B10] border border-zinc-200/80 dark:border-white/[0.08] flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
            {pipelineStatus?.phase_label || 'Preparando Pipeline'}
          </span>
          <span className="text-sm font-semibold text-cyan-600 dark:text-cyan-400 tabular-nums">
            {progress}%
          </span>
        </div>
        <div
          data-testid="pipeline-progress-bar"
          className="w-full h-3 rounded-full bg-zinc-200/80 dark:bg-zinc-800 overflow-hidden"
        >
          <div
            className={`h-full rounded-full transition-all duration-300 ${
              progress >= 100 ? 'bg-emerald-500' : 'bg-gradient-to-r from-cyan-500 to-blue-600'
            }`}
            style={{ width: `${progress}%` }}
          />
        </div>
        <p className="text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed">
          {pipelineStatus?.step_detail || pipelineStatus?.message || 'Listo para iniciar procesamiento.'}
        </p>
      </div>
    </section>
  );
}
