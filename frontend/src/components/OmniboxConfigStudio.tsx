import React, { useRef } from 'react';
import {
  FileVideo,
  FolderOpen,
  Link2,
  Loader2,
  Play,
  Search,
} from 'lucide-react';
import type {
  InboxVideoItem,
  LocalVideoPickResponse,
  SourceType,
  VideoInspectionReport,
} from '../types';
import { getVideoDisplayName, type ActiveOperation } from './studioHelpers';

export interface OmniboxConfigStudioProps {
  sourceType: SourceType;
  onSourceTypeChange: (next: SourceType) => void;
  inboxVideos: InboxVideoItem[];
  selectedVideo: string;
  pickedVideoMeta: LocalVideoPickResponse | null;
  onSelectLocalVideoFile: (file: File) => void;
  youtubeUrl: string;
  onYoutubeUrlChange: (url: string) => void;
  downloadSectionStart: string;
  onDownloadSectionStartChange: (val: string) => void;
  downloadSectionEnd: string;
  onDownloadSectionEndChange: (val: string) => void;
  shortsPerVideo: number;
  onShortsPerVideoChange: (count: number) => void;
  inspectionReport: VideoInspectionReport | null;
  isBusy: boolean;
  activeOperation: ActiveOperation;
  onInspectVideo: () => void;
  onSubmitPipeline: (e: React.FormEvent) => void;
}

export function OmniboxConfigStudio({
  sourceType,
  onSourceTypeChange,
  inboxVideos,
  selectedVideo,
  pickedVideoMeta,
  onSelectLocalVideoFile,
  youtubeUrl,
  onYoutubeUrlChange,
  downloadSectionStart,
  onDownloadSectionStartChange,
  downloadSectionEnd,
  onDownloadSectionEndChange,
  shortsPerVideo,
  onShortsPerVideoChange,
  inspectionReport,
  isBusy,
  activeOperation,
  onInspectVideo,
  onSubmitPipeline,
}: OmniboxConfigStudioProps) {
  const localFileInputRef = useRef<HTMLInputElement | null>(null);
  const isAnalyzingOrStarting =
    activeOperation === 'pre_analyze' || activeOperation === 'process';
  const displayFileName = getVideoDisplayName(selectedVideo);
  const matchingInboxItem = inboxVideos.find((v) => v.file_name === displayFileName);
  const displayFileSizeMb =
    pickedVideoMeta &&
    pickedVideoMeta.size_mb !== null &&
    (pickedVideoMeta.file_path === selectedVideo || pickedVideoMeta.file_name === displayFileName)
      ? pickedVideoMeta.size_mb
      : matchingInboxItem?.size_mb;

  const triggerLocalPicker = () => {
    if (isBusy) return;
    onSourceTypeChange('inbox');
    if (localFileInputRef.current) {
      localFileInputRef.current.value = '';
      localFileInputRef.current.click();
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const picked = e.target.files?.[0];
    if (picked) {
      onSelectLocalVideoFile(picked);
    }
    e.target.value = '';
  };

  return (
    <section className="bg-white dark:bg-[#11151F]/90 backdrop-blur-md rounded-2xl border border-zinc-200/80 dark:border-white/[0.08] shadow-sm dark:shadow-black/30 p-6 antialiased">
      <input
        ref={localFileInputRef}
        data-testid="local-video-file-input"
        type="file"
        accept=".mp4,.mov,.mkv,.avi,.webm,video/*"
        tabIndex={-1}
        aria-hidden="true"
        className="sr-only"
        onChange={handleFileInputChange}
      />

      {/* Cabecera en una sola línea equilibrada: Título | Conmutador segmentado h-10 */}
      <div className="pb-4 mb-4 border-b border-zinc-200/70 dark:border-white/[0.06] flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 text-left">
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
            Configuración y Ejecución del Pipeline
          </h2>
        </div>

        <div className="shrink-0 self-start lg:self-center">
          <div className="inline-flex items-center p-1 rounded-xl bg-zinc-100 dark:bg-[#090B10] border border-zinc-200/80 dark:border-white/[0.08] gap-1">
            <button
              type="button"
              disabled={isBusy}
              onClick={() => onSourceTypeChange('youtube_url')}
              aria-pressed={sourceType === 'youtube_url'}
              className={`h-10 px-3.5 rounded-lg inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium tracking-tight gap-1.5 transition-all disabled:opacity-50 ${
                sourceType === 'youtube_url'
                  ? 'bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-sm shadow-cyan-500/20'
                  : 'text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200/60 dark:hover:bg-[#171C29]'
              }`}
            >
              <Link2 className="w-3.5 h-3.5" />
              Pegar URL de YouTube / LIVE
            </button>
            <button
              type="button"
              disabled={isBusy}
              onClick={triggerLocalPicker}
              aria-pressed={sourceType === 'inbox'}
              className={`h-10 px-3.5 rounded-lg inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium tracking-tight gap-1.5 transition-all disabled:opacity-50 ${
                sourceType === 'inbox'
                  ? 'bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-sm shadow-cyan-500/20'
                  : 'text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200/60 dark:hover:bg-[#171C29]'
              }`}
            >
              {activeOperation === 'pick_local_video' ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <FolderOpen className="w-3.5 h-3.5" />
              )}
              Archivo Local
            </button>
          </div>
        </div>
      </div>

      <form onSubmit={onSubmitPipeline} className="flex flex-col gap-4">
        {/* Barra de Control Simétrica contenida (12 cols, todas con etiqueta + h-10 exacto) */}
        <div className="p-4 rounded-xl bg-zinc-50/80 dark:bg-[#0B0E16]/90 border border-zinc-200/70 dark:border-white/[0.06]">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 items-end">
            {sourceType === 'inbox' ? (
              <>
                <div className="lg:col-span-7 text-left">
                  <span className="h-4 text-[11px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 mb-1.5 flex items-center gap-1.5 whitespace-nowrap">
                    <FileVideo className="w-3.5 h-3.5 text-cyan-500" />
                    Video Local en tu PC
                  </span>
                  <button
                    type="button"
                    data-testid="selected-local-video-display"
                    disabled={isBusy}
                    onClick={triggerLocalPicker}
                    title={selectedVideo || 'Haz clic para explorar un video local'}
                    className="w-full h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#090B10] hover:border-cyan-500/50 dark:hover:border-cyan-400/40 flex items-center justify-between gap-2.5 text-sm transition-colors disabled:opacity-50"
                  >
                    {displayFileName ? (
                      <>
                        <span className="flex items-center gap-2 min-w-0">
                          <FolderOpen className="w-4 h-4 text-cyan-500 shrink-0" />
                          <span className="truncate font-medium text-zinc-900 dark:text-zinc-50">
                            {displayFileName}
                          </span>
                        </span>
                        <span className="flex items-center gap-2 shrink-0">
                          {displayFileSizeMb !== undefined && (
                            <span className="text-xs text-zinc-500 dark:text-zinc-400 tabular-nums">
                              {displayFileSizeMb} MB
                            </span>
                          )}
                          <span className="px-2 py-0.5 rounded-md bg-cyan-500/10 text-cyan-700 dark:text-cyan-300 border border-cyan-500/25 text-[11px] font-medium whitespace-nowrap">
                            Cambiar
                          </span>
                        </span>
                      </>
                    ) : (
                      <>
                        <span className="flex items-center gap-2 min-w-0 text-zinc-500 dark:text-zinc-400">
                          <FolderOpen className="w-4 h-4 text-zinc-400 dark:text-zinc-500 shrink-0" />
                          <span className="truncate">
                            Ningún archivo elegido — haz clic para explorar
                          </span>
                        </span>
                        <span className="shrink-0 px-2 py-0.5 rounded-md bg-zinc-100 dark:bg-[#171C29] text-zinc-700 dark:text-zinc-300 border border-zinc-200/80 dark:border-white/[0.08] text-[11px] font-medium whitespace-nowrap">
                          Explorar
                        </span>
                      </>
                    )}
                  </button>
                </div>
                <div className="lg:col-span-2 text-left">
                  <span className="h-4 text-[11px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 mb-1.5 block truncate">
                    Diagnóstico
                  </span>
                  <button
                    type="button"
                    onClick={onInspectVideo}
                    disabled={isBusy || !selectedVideo}
                    className="w-full h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#090B10] hover:bg-zinc-100 dark:hover:bg-[#171C29] text-zinc-900 dark:text-zinc-100 inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium tracking-normal gap-1.5 transition-colors disabled:opacity-50"
                  >
                    {activeOperation === 'inspect' ? (
                      <Loader2 className="w-4 h-4 animate-spin text-cyan-400" />
                    ) : (
                      <Search className="w-4 h-4 text-zinc-700 dark:text-cyan-400" />
                    )}
                    Inspeccionar Video
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="lg:col-span-5 text-left">
                  <label
                    htmlFor="youtube-url-input"
                    className="h-4 text-[11px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 mb-1.5 flex items-center gap-1.5 truncate"
                  >
                    <Link2 className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
                    URL de YouTube, Twitch o Kick
                  </label>
                  <input
                    id="youtube-url-input"
                    type="url"
                    required={sourceType === 'youtube_url'}
                    value={youtubeUrl}
                    onChange={(e) => onYoutubeUrlChange(e.target.value)}
                    placeholder="https://www.youtube.com/watch?v=... o twitch.tv/..."
                    className="w-full h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#090B10] text-sm text-zinc-900 dark:text-zinc-50 focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  />
                </div>
                <div className="lg:col-span-2 text-left">
                  <label
                    htmlFor="section-start-input"
                    className="h-4 text-[11px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 mb-1.5 block truncate"
                  >
                    Inicio (Opcional)
                  </label>
                  <input
                    id="section-start-input"
                    type="text"
                    value={downloadSectionStart}
                    onChange={(e) => onDownloadSectionStartChange(e.target.value)}
                    placeholder="00:05:00"
                    className="w-full h-10 px-2.5 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#090B10] text-sm text-zinc-900 dark:text-zinc-50 tabular-nums focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  />
                </div>
                <div className="lg:col-span-2 text-left">
                  <label
                    htmlFor="section-end-input"
                    className="h-4 text-[11px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 mb-1.5 block truncate"
                  >
                    Fin (Opcional)
                  </label>
                  <input
                    id="section-end-input"
                    type="text"
                    value={downloadSectionEnd}
                    onChange={(e) => onDownloadSectionEndChange(e.target.value)}
                    placeholder="00:20:00"
                    className="w-full h-10 px-2.5 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#090B10] text-sm text-zinc-900 dark:text-zinc-50 tabular-nums focus:outline-none focus:ring-2 focus:ring-cyan-500"
                  />
                </div>
              </>
            )}

            <div className="lg:col-span-1 text-left">
              <label
                htmlFor="shorts-count-input"
                className="h-4 text-[11px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 mb-1.5 block truncate"
              >
                Shorts
              </label>
              <input
                id="shorts-count-input"
                type="number"
                min={1}
                max={24}
                value={shortsPerVideo}
                onChange={(e) => onShortsPerVideoChange(Number(e.target.value))}
                className="w-full h-10 px-2 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#090B10] text-sm text-center font-medium text-zinc-900 dark:text-zinc-50 tabular-nums focus:outline-none focus:ring-2 focus:ring-cyan-500"
              />
            </div>

            <div className="lg:col-span-2 text-left">
              <span className="h-4 text-[11px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 mb-1.5 block truncate">
                Ejecución
              </span>
              <button
                type="submit"
                disabled={isBusy}
                className="w-full h-10 px-4 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white shadow-lg shadow-cyan-500/15 inline-flex items-center justify-center whitespace-nowrap leading-none text-sm font-semibold tracking-normal gap-2 transition-all disabled:opacity-50"
              >
                {isAnalyzingOrStarting ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Play className="w-4 h-4 fill-current" />
                )}
                Generar
              </button>
            </div>
          </div>
        </div>

        {/* Tarjeta compacta de Inspección */}
        {inspectionReport && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-4 rounded-xl bg-zinc-50 dark:bg-[#090B10] border border-zinc-200/80 dark:border-white/[0.08] text-left">
            <div>
              <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400 block">
                Resolución Nativa
              </span>
              <span className="text-sm font-semibold text-zinc-900 dark:text-zinc-50 tabular-nums">
                {inspectionReport.resolution}
              </span>
            </div>
            <div>
              <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400 block">
                Cuadros por Segundo
              </span>
              <span className="text-sm font-semibold text-zinc-900 dark:text-zinc-50 tabular-nums">
                {inspectionReport.fps} FPS
              </span>
            </div>
            <div>
              <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400 block">
                Duración Real
              </span>
              <span className="text-sm font-semibold text-zinc-900 dark:text-zinc-50 tabular-nums">
                {inspectionReport.duration_formatted}
              </span>
            </div>
            <div>
              <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400 block">
                Potencial Estimado
              </span>
              <span className="text-sm font-semibold text-cyan-600 dark:text-cyan-400 tabular-nums">
                {inspectionReport.recommended_shorts} recomendados (máx. {inspectionReport.max_possible_shorts})
              </span>
            </div>
          </div>
        )}
      </form>
    </section>
  );
}
