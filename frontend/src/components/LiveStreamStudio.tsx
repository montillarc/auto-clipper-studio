import type React from 'react';
import { Link2, Loader2, Radio, Square, Tv } from 'lucide-react';
import type { ContentProfileItem, LiveMonitorStatus } from '../types';
import { extractYouTubeEmbedUrl, type ActiveOperation } from './studioHelpers';

export interface LiveStreamStudioProps {
  streamUrl: string;
  onStreamUrlChange: (val: string) => void;
  profileId: number | null;
  onProfileIdChange: (val: number | null) => void;
  chunkDurationSec: number;
  onChunkDurationSecChange: (val: number) => void;
  minViralityScore: number;
  onMinViralityScoreChange: (val: number) => void;
  maxShortsTotal: number;
  onMaxShortsTotalChange: (val: number) => void;
  contentProfiles: ContentProfileItem[];
  liveStatus: LiveMonitorStatus | null;
  isBusy: boolean;
  activeOperation: ActiveOperation;
  onStartLive: (e: React.FormEvent) => void;
  onStopLive: () => void;
}

export function LiveStreamStudio({
  streamUrl,
  onStreamUrlChange,
  profileId,
  onProfileIdChange,
  chunkDurationSec,
  onChunkDurationSecChange,
  minViralityScore,
  onMinViralityScoreChange,
  maxShortsTotal,
  onMaxShortsTotalChange,
  contentProfiles,
  liveStatus,
  isBusy,
  activeOperation,
  onStartLive,
  onStopLive,
}: LiveStreamStudioProps) {
  const isLiveActive =
    liveStatus?.status === 'STARTING' ||
    liveStatus?.status === 'MONITORING' ||
    liveStatus?.status === 'ANALYZING_CHUNK';

  const activePreviewUrl = (liveStatus?.stream_url || streamUrl || '').trim();
  const ytEmbedUrl = extractYouTubeEmbedUrl(activePreviewUrl);
  const segCaptured = liveStatus?.segments_captured ?? 0;
  const segAnalyzed = liveStatus?.segments_analyzed ?? 0;
  const shortsGenerated = liveStatus?.shorts_generated ?? 0;
  const recentClips = liveStatus?.recent_clips ?? [];

  return (
    <section className="bg-white dark:bg-[#11151F]/90 backdrop-blur-md rounded-2xl border border-zinc-200/80 dark:border-white/[0.08] shadow-sm dark:shadow-black/30 p-6 flex flex-col gap-5 text-left antialiased">
      <div className="pb-4 border-b border-zinc-200/70 dark:border-white/[0.06] flex items-center justify-between gap-4">
        <div className="flex items-center gap-2.5 min-w-0">
          <Radio
            className={`w-5 h-5 shrink-0 ${
              isLiveActive ? 'text-emerald-500 animate-pulse' : 'text-cyan-500'
            }`}
          />
          <h2 className="text-lg font-semibold tracking-tight text-zinc-900 dark:text-zinc-50 truncate">
            Recorte en Vivo desde Transmisión Activa
          </h2>
        </div>
        {liveStatus?.stream_title && (
          <span className="text-xs font-medium text-cyan-600 dark:text-cyan-400 truncate max-w-md">
            {liveStatus.stream_title}
          </span>
        )}
      </div>

      <form
        onSubmit={onStartLive}
        className="p-4 rounded-xl bg-zinc-50/80 dark:bg-[#0B0E16]/90 border border-zinc-200/70 dark:border-white/[0.06]"
      >
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 items-end">
          <div className="lg:col-span-4 text-left">
            <label
              htmlFor="live-stream-url-input"
              className="h-4 text-[11px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 mb-1.5 flex items-center gap-1.5 truncate"
            >
              <Link2 className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
              URL del Directo en Vivo
            </label>
            <input
              id="live-stream-url-input"
              type="url"
              required
              disabled={isLiveActive}
              value={streamUrl}
              onChange={(e) => onStreamUrlChange(e.target.value)}
              placeholder="https://www.youtube.com/live/... o twitch.tv/..."
              className="w-full h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#090B10] text-sm text-zinc-900 dark:text-zinc-50 focus:outline-none focus:ring-2 focus:ring-cyan-500 disabled:opacity-60"
            />
          </div>

          <div className="lg:col-span-2 text-left">
            <label
              htmlFor="live-profile-select"
              className="h-4 text-[11px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 mb-1.5 block truncate"
            >
              Perfil de Contenido en Vivo
            </label>
            <select
              id="live-profile-select"
              disabled={isLiveActive}
              value={profileId !== null ? String(profileId) : ''}
              onChange={(e) => onProfileIdChange(e.target.value ? Number(e.target.value) : null)}
              className="w-full h-10 px-2.5 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#090B10] text-sm text-zinc-900 dark:text-zinc-50 focus:outline-none focus:ring-2 focus:ring-cyan-500 disabled:opacity-60"
            >
              <option value="">Automático</option>
              {contentProfiles.map((prof) => (
                <option key={prof.id} value={String(prof.id)}>
                  {prof.name}
                </option>
              ))}
            </select>
          </div>

          <div className="lg:col-span-2 text-left">
            <label
              htmlFor="live-chunk-duration-select"
              className="h-4 text-[11px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 mb-1.5 block truncate"
            >
              Intervalo de Escaneo
            </label>
            <select
              id="live-chunk-duration-select"
              disabled={isLiveActive}
              value={String(chunkDurationSec)}
              onChange={(e) => onChunkDurationSecChange(Number(e.target.value))}
              className="w-full h-10 px-2.5 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#090B10] text-sm text-zinc-900 dark:text-zinc-50 tabular-nums focus:outline-none focus:ring-2 focus:ring-cyan-500 disabled:opacity-60"
            >
              <option value="60">Cada 60s</option>
              <option value="90">Cada 90s</option>
              <option value="120">Cada 120s</option>
              <option value="180">Cada 180s</option>
            </select>
          </div>

          <div className="lg:col-span-1 text-left">
            <label
              htmlFor="live-min-score-input"
              className="h-4 text-[11px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 mb-1.5 block truncate"
            >
              Puntaje Mínimo
            </label>
            <input
              id="live-min-score-input"
              type="number"
              min={40}
              max={95}
              disabled={isLiveActive}
              value={minViralityScore}
              onChange={(e) => onMinViralityScoreChange(Number(e.target.value))}
              className="w-full h-10 px-2 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#090B10] text-sm text-center font-medium text-zinc-900 dark:text-zinc-50 tabular-nums focus:outline-none focus:ring-2 focus:ring-cyan-500 disabled:opacity-60"
            />
          </div>

          <div className="lg:col-span-1 text-left">
            <label
              htmlFor="live-max-shorts-input"
              className="h-4 text-[11px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 mb-1.5 block truncate"
            >
              Máx. Shorts
            </label>
            <input
              id="live-max-shorts-input"
              type="number"
              min={1}
              max={50}
              disabled={isLiveActive}
              value={maxShortsTotal}
              onChange={(e) => onMaxShortsTotalChange(Number(e.target.value))}
              className="w-full h-10 px-2 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#090B10] text-sm text-center font-medium text-zinc-900 dark:text-zinc-50 tabular-nums focus:outline-none focus:ring-2 focus:ring-cyan-500 disabled:opacity-60"
            />
          </div>

          <div className="lg:col-span-2 text-left">
            <span className="h-4 text-[11px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 mb-1.5 block truncate">
              Control
            </span>
            {isLiveActive ? (
              <button
                type="button"
                onClick={onStopLive}
                disabled={isBusy && activeOperation !== 'start_live'}
                className="w-full h-10 px-4 rounded-lg bg-red-600 hover:bg-red-500 text-white shadow-lg shadow-red-500/15 inline-flex items-center justify-center whitespace-nowrap leading-none text-sm font-semibold tracking-normal gap-2 transition-all disabled:opacity-50"
              >
                {activeOperation === 'stop_live' ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Square className="w-3.5 h-3.5 fill-current" />
                )}
                Detener Directo
              </button>
            ) : (
              <button
                type="submit"
                disabled={isBusy}
                className="w-full h-10 px-4 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white shadow-lg shadow-cyan-500/15 inline-flex items-center justify-center whitespace-nowrap leading-none text-sm font-semibold tracking-normal gap-2 transition-all disabled:opacity-50"
              >
                {activeOperation === 'start_live' ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Radio className="w-4 h-4" />
                )}
                Iniciar en Vivo
              </button>
            )}
          </div>
        </div>
      </form>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        <div className="lg:col-span-6 w-full rounded-xl overflow-hidden border border-zinc-200/80 dark:border-white/[0.08] bg-zinc-950 aspect-video flex items-center justify-center">
          {ytEmbedUrl ? (
            <iframe
              src={ytEmbedUrl}
              title="Vista previa del directo en vivo"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              className="w-full h-full border-0"
            />
          ) : (
            <div className="p-6 text-center flex flex-col items-center gap-2 text-zinc-400">
              <Tv className="w-8 h-8 text-zinc-600" />
              <span className="text-xs font-medium text-zinc-300 truncate max-w-sm">
                {activePreviewUrl || 'Esperando enlace de transmisión activa'}
              </span>
            </div>
          )}
        </div>

        <div className="lg:col-span-6 flex flex-col gap-3">
          <div className="p-4 rounded-xl bg-zinc-50 dark:bg-[#090B10] border border-zinc-200/80 dark:border-white/[0.08] flex flex-col gap-1.5">
            <span className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
              {liveStatus?.phase_label || 'En espera'}
            </span>
            <p className="text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed">
              {liveStatus?.step_detail || 'Pega el enlace de un directo activo para extraer Shorts en tiempo real.'}
            </p>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="p-3.5 rounded-xl bg-zinc-50 dark:bg-[#090B10] border border-zinc-200/80 dark:border-white/[0.08]">
              <span className="text-[11px] font-medium text-zinc-500 dark:text-zinc-400 block">
                Bloques Capturados
              </span>
              <span className="text-lg font-semibold text-zinc-900 dark:text-zinc-50 tabular-nums">
                {segCaptured}
              </span>
            </div>
            <div className="p-3.5 rounded-xl bg-zinc-50 dark:bg-[#090B10] border border-zinc-200/80 dark:border-white/[0.08]">
              <span className="text-[11px] font-medium text-zinc-500 dark:text-zinc-400 block">
                Bloques Analizados
              </span>
              <span className="text-lg font-semibold text-zinc-900 dark:text-zinc-50 tabular-nums">
                {segAnalyzed}
              </span>
            </div>
            <div className="p-3.5 rounded-xl bg-zinc-50 dark:bg-[#090B10] border border-zinc-200/80 dark:border-white/[0.08]">
              <span className="text-[11px] font-medium text-zinc-500 dark:text-zinc-400 block">
                Shorts Generados
              </span>
              <span className="text-lg font-semibold text-cyan-600 dark:text-cyan-400 tabular-nums">
                {shortsGenerated}
              </span>
            </div>
          </div>

          {recentClips.length > 0 && (
            <div className="p-3.5 rounded-xl bg-zinc-50 dark:bg-[#090B10] border border-zinc-200/80 dark:border-white/[0.08] flex flex-col gap-2 max-h-48 overflow-y-auto">
              <span className="text-xs font-semibold text-zinc-700 dark:text-zinc-200">
                Clips detectados en vivo
              </span>
              {recentClips.map((clip) => (
                <div
                  key={`${clip.filename}-${clip.created_at}`}
                  className="flex items-center justify-between gap-2 text-xs py-1.5 px-2.5 rounded-lg bg-white dark:bg-[#11151F] border border-zinc-200/70 dark:border-white/[0.06]"
                >
                  <span className="font-medium text-zinc-900 dark:text-zinc-100 truncate">
                    {clip.hook_title}
                  </span>
                  <span className="shrink-0 font-semibold text-cyan-600 dark:text-cyan-400 tabular-nums">
                    {clip.virality_score} pts
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
