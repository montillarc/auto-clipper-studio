import { Clock, Download, Sliders, Trash2 } from 'lucide-react';
import type {
  AccountCategoryKey,
  PipelineStatus,
  QueuesResponse,
  RenderedShortItem,
} from '../types';
import { SocialStatusBars } from './SocialStatusBars';
import {
  type CategoryOptionMeta,
  formatShortCardTitle,
  getHubCategoryOptions,
  getTierVisualMeta,
  pauseAllVideosExcept,
  withCacheBust,
} from './studioHelpers';

export function ShortCard({
  item,
  index,
  cacheVersion,
  scheduleValue,
  queues,
  pipelineStatus,
  isBusy,
  isSelected = false,
  onToggleSelect,
  showSocialDetails = false,
  categoryOptions,
  onScheduleValueChange,
  onScheduleSingle,
  onToggleShortCategory,
  onOpenLayoutEditor,
  onCancelSingle,
  onDoubleClickVideo,
}: {
  item: RenderedShortItem;
  index: number;
  cacheVersion?: number;
  scheduleValue: string;
  queues: QueuesResponse;
  pipelineStatus: PipelineStatus | null;
  isBusy: boolean;
  isSelected?: boolean;
  onToggleSelect?: () => void;
  showSocialDetails?: boolean;
  categoryOptions?: CategoryOptionMeta[];
  onScheduleValueChange: (nextVal: string) => void;
  onScheduleSingle: () => void;
  onToggleShortCategory?: (item: RenderedShortItem, nextCategories: AccountCategoryKey[]) => void;
  onOpenLayoutEditor: () => void;
  onCancelSingle: () => void;
  onDoubleClickVideo: () => void;
}) {
  const tierMeta = getTierVisualMeta(item.tier);
  const effectiveVideoUrl = withCacheBust(item.video_url, cacheVersion);
  const effectiveThumbUrl = withCacheBust(item.thumbnail_url, cacheVersion);
  const currentCategories: AccountCategoryKey[] =
    item.account_categories && item.account_categories.length > 0
      ? item.account_categories
      : ['clipping'];

  const handleToggleCategory = (catKey: AccountCategoryKey) => {
    if (!onToggleShortCategory) return;
    const exists = currentCategories.includes(catKey);
    if (exists && currentCategories.length <= 1) {
      return;
    }
    const nextCats = exists
      ? currentCategories.filter((c) => c !== catKey)
      : [...currentCategories, catKey];
    onToggleShortCategory(item, nextCats);
  };

  return (
    <article
      className={`rounded-2xl border bg-zinc-50 dark:bg-[#090B10]/90 hover:dark:bg-[#171C29]/90 overflow-hidden flex flex-col shadow-sm transition-all duration-200 ${
        isSelected
          ? 'border-cyan-500 ring-2 ring-cyan-500/50 dark:border-cyan-400'
          : 'border-zinc-200/80 dark:border-white/[0.08] hover:dark:border-white/[0.14]'
      }`}
    >
      {/* Marco Monitor Vertical 9:16 */}
      <div className="relative aspect-[9/16] bg-zinc-950 border-b border-zinc-200/80 dark:border-white/[0.08] overflow-hidden">
        <video
          key={effectiveVideoUrl}
          src={effectiveVideoUrl}
          poster={effectiveThumbUrl}
          controls
          controlsList="nofullscreen"
          playsInline
          title="Doble clic para abrir en reproductor flotante"
          onDoubleClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onDoubleClickVideo();
          }}
          onPlay={(e) => pauseAllVideosExcept(e.currentTarget)}
          preload="metadata"
          className="w-full h-full object-cover cursor-pointer"
        />
        {effectiveThumbUrl && (
          <img
            src={effectiveThumbUrl}
            alt={`Miniatura de ${item.filename}`}
            className="sr-only"
          />
        )}
        <div className="pointer-events-none absolute top-2.5 left-2.5 right-2.5 flex items-center justify-between gap-1.5">
          <span
            className={`px-2 py-0.5 rounded-lg text-[11px] font-semibold tabular-nums shadow-sm ${tierMeta.badgeClass}`}
          >
            {tierMeta.label} · {item.virality_score} pts
          </span>
          {onToggleSelect && (
            <label
              onClick={(e) => e.stopPropagation()}
              className={`pointer-events-auto inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg backdrop-blur-md border text-[11px] font-medium cursor-pointer select-none shadow-sm transition-colors ${
                isSelected
                  ? 'bg-cyan-600/90 border-cyan-400 text-white'
                  : 'bg-zinc-950/80 hover:bg-zinc-900/90 border-white/15 text-zinc-100'
              }`}
            >
              <input
                type="checkbox"
                aria-label={`Seleccionar Short ${item.filename}`}
                checked={Boolean(isSelected)}
                onChange={() => onToggleSelect()}
                className="w-3.5 h-3.5 rounded accent-cyan-400 cursor-pointer"
              />
              <span>{isSelected ? 'Elegido' : 'Elegir'}</span>
            </label>
          )}
        </div>
      </div>

      {/* Detalles Clave del Short */}
      <div className="p-3.5 flex flex-col gap-2.5 flex-1 justify-between text-left">
        <div className="flex flex-col gap-1.5">
          <p
            className="text-xs font-semibold text-zinc-900 dark:text-zinc-50 line-clamp-2 leading-snug"
            title={item.filename}
          >
            {formatShortCardTitle(item)}
          </p>

          <div className="flex flex-wrap items-center gap-1.5 text-[11px] tabular-nums">
            <span className="font-semibold text-zinc-900 dark:text-zinc-100">
              {item.virality_score} / 100
            </span>
            <span className="text-zinc-400">·</span>
            <span className="text-zinc-500 dark:text-zinc-400">{item.size_mb} MB</span>
          </div>

          {/* Categorías editables por Short para dirigir redes (ocultas por defecto) */}
          {showSocialDetails && (
            <div className="flex flex-wrap items-center gap-1 pt-0.5">
              {(categoryOptions && categoryOptions.length > 0
                ? categoryOptions
                : getHubCategoryOptions()
              ).map((catMeta) => {
                const active = currentCategories.includes(catMeta.key);
                const isOnlyActive = active && currentCategories.length === 1;
                return (
                  <button
                    key={catMeta.key}
                    type="button"
                    disabled={isBusy || isOnlyActive}
                    aria-pressed={active}
                    aria-label={`Categoría ${catMeta.shortLabel} para ${item.filename}`}
                    onClick={() => handleToggleCategory(catMeta.key)}
                    className={`h-10 px-2.5 rounded-lg border text-[11px] font-semibold inline-flex items-center justify-center whitespace-nowrap leading-none transition-colors disabled:opacity-60 ${
                      active
                        ? 'bg-cyan-600 text-white border-cyan-600 dark:bg-cyan-500/25 dark:text-cyan-200 dark:border-cyan-400/50'
                        : 'bg-white dark:bg-[#171C29] text-zinc-600 dark:text-zinc-400 border-zinc-200/80 dark:border-white/[0.08] hover:bg-zinc-100 dark:hover:bg-white/[0.08]'
                    }`}
                  >
                    {catMeta.shortLabel}
                  </button>
                );
              })}
            </div>
          )}

          <p className="text-[11px] text-zinc-500 dark:text-zinc-400 tabular-nums truncate">
            {item.scheduled_ast || 'Listo en local (Sin programar)'}
          </p>
        </div>

        <div className="flex flex-col gap-2 pt-1">
          {showSocialDetails && (
            <SocialStatusBars
              item={item}
              queues={queues}
              pipelineStatus={pipelineStatus}
              compact={false}
            />
          )}

          {/* Programación individual de Fecha y Hora por Short (AST) */}
          <div className="flex flex-col gap-1.5 rounded-xl border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#090B10]/85 p-2">
            <span className="inline-flex items-center gap-1 text-[11px] font-medium text-zinc-600 dark:text-zinc-300">
              <Clock className="w-3 h-3 text-cyan-500" />
              Programar fecha y hora (AST) · #{index + 1}
            </span>
            <div className="flex items-center gap-1.5">
              <input
                type="datetime-local"
                aria-label={`Fecha y hora de ${item.filename}`}
                value={scheduleValue}
                onChange={(e) => onScheduleValueChange(e.target.value)}
                className="flex-1 min-w-0 h-10 px-2 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-zinc-50 dark:bg-[#171C29] text-zinc-900 dark:text-zinc-50 text-[11px] font-medium tabular-nums focus:outline-none focus:ring-2 focus:ring-cyan-500"
              />
              <button
                type="button"
                onClick={onScheduleSingle}
                disabled={isBusy}
                aria-label={`Programar Short ${item.filename}`}
                className="h-10 px-3 rounded-lg bg-zinc-900 dark:bg-indigo-500 hover:bg-zinc-800 dark:hover:bg-indigo-400 text-white inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium tracking-normal gap-1 transition-colors disabled:opacity-50 shrink-0"
              >
                Programar
              </button>
            </div>
          </div>

          <div className="grid grid-cols-12 gap-1.5">
            <button
              type="button"
              onClick={onOpenLayoutEditor}
              disabled={isBusy}
              aria-label={`Editar Short ${item.filename}`}
              className="col-span-5 h-10 px-2.5 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#171C29] hover:bg-zinc-100 dark:hover:bg-white/[0.08] text-zinc-900 dark:text-zinc-100 inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium tracking-normal gap-1.5 transition-colors disabled:opacity-50"
            >
              <Sliders className="w-3.5 h-3.5 text-cyan-500 shrink-0" />
              <span>Editar</span>
            </button>

            <a
              href={effectiveVideoUrl}
              download={item.filename}
              aria-label={`Descargar Short ${item.filename}`}
              className="col-span-4 h-10 px-2 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#171C29] hover:bg-zinc-100 dark:hover:bg-white/[0.08] text-zinc-800 dark:text-zinc-200 inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium gap-1 transition-colors"
            >
              <Download className="w-3.5 h-3.5 text-cyan-500 shrink-0" />
              <span>MP4</span>
            </a>

            <button
              type="button"
              onClick={onCancelSingle}
              disabled={isBusy}
              aria-label={`Cancelar Short ${item.filename}`}
              className="col-span-3 h-10 px-2 rounded-lg border border-red-200 dark:border-red-900/70 bg-red-50 dark:bg-red-950/60 hover:bg-red-100 dark:hover:bg-red-900/60 text-red-700 dark:text-red-300 inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium tracking-normal transition-colors disabled:opacity-50"
            >
              <Trash2 className="w-3.5 h-3.5 shrink-0" />
              <span className="sr-only">Cancelar</span>
            </button>
          </div>
        </div>
      </div>
    </article>
  );
}
