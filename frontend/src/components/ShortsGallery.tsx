import { CheckSquare, Clock, Download, Eye, EyeOff, Loader2, Square, Trash2, Upload } from 'lucide-react';
import type {
  AccountCategoryKey,
  PipelineStatus,
  QueuesResponse,
  RenderedShortItem,
} from '../types';
import { ShortCard } from './ShortCard';
import {
  type ActiveOperation,
  type CategoryOptionMeta,
  type GalleryFilter,
  getHubCategoryOptions,
  getShortSelectionKey,
} from './studioHelpers';

export function ShortsGallery({
  renderedShorts,
  galleryFilter,
  onGalleryFilterChange,
  queues,
  pipelineStatus,
  rerenderVersions,
  isBusy,
  activeOperation = 'none',
  showSocialDetails = false,
  onToggleSocialDetails,
  selectedShortKeys = [],
  onToggleSelectShort,
  onToggleSelectAllVisible,
  onDownloadShorts,
  categoryOptions,
  getShortScheduleValue,
  onScheduleValueChange,
  onScheduleSingle,
  onToggleShortCategory,
  onOpenLayoutEditor,
  onCancelSingle,
  onDoubleClickVideo,
  onOpenScheduleModal,
  onCancelAllShorts,
  pendingTikTokCount = 0,
  onDispatchTikTokStudio,
}: {
  renderedShorts: RenderedShortItem[];
  galleryFilter: GalleryFilter;
  onGalleryFilterChange: (next: GalleryFilter) => void;
  queues: QueuesResponse;
  pipelineStatus: PipelineStatus | null;
  rerenderVersions: Record<string, number>;
  isBusy: boolean;
  activeOperation?: ActiveOperation;
  showSocialDetails?: boolean;
  onToggleSocialDetails?: () => void;
  selectedShortKeys?: string[];
  onToggleSelectShort?: (item: RenderedShortItem) => void;
  onToggleSelectAllVisible?: (visibleItems: RenderedShortItem[]) => void;
  onDownloadShorts?: (targetItems: RenderedShortItem[], mode: 'all' | 'selected') => void;
  categoryOptions?: CategoryOptionMeta[];
  getShortScheduleValue: (item: RenderedShortItem, idx: number) => string;
  onScheduleValueChange: (item: RenderedShortItem, val: string) => void;
  onScheduleSingle: (item: RenderedShortItem, idx: number) => void;
  onToggleShortCategory?: (item: RenderedShortItem, nextCategories: AccountCategoryKey[]) => void;
  onOpenLayoutEditor: (item: RenderedShortItem) => void;
  onCancelSingle: (item: RenderedShortItem) => void;
  onDoubleClickVideo: (item: RenderedShortItem) => void;
  onOpenScheduleModal: () => void;
  onCancelAllShorts: () => void;
  pendingTikTokCount?: number;
  onDispatchTikTokStudio?: () => void;
}) {
  const effectiveCategories =
    categoryOptions && categoryOptions.length > 0 ? categoryOptions : getHubCategoryOptions();

  const getItemCategories = (item: RenderedShortItem): AccountCategoryKey[] =>
    item.account_categories && item.account_categories.length > 0
      ? item.account_categories
      : ['clipping'];

  const categoryCounts: Record<string, number> = {};
  for (const catMeta of effectiveCategories) {
    categoryCounts[catMeta.key] = renderedShorts.filter((s) =>
      getItemCategories(s).includes(catMeta.key)
    ).length;
  }

  const filteredShorts = renderedShorts.filter((item) => {
    if (galleryFilter === 'all') return true;
    return getItemCategories(item).includes(galleryFilter);
  });

  const selectedVisibleShorts = filteredShorts.filter((item) =>
    selectedShortKeys.includes(getShortSelectionKey(item))
  );
  const allVisibleSelected =
    filteredShorts.length > 0 && selectedVisibleShorts.length === filteredShorts.length;

  return (
    <section className="bg-white dark:bg-[#11151F]/90 backdrop-blur-md rounded-2xl border border-zinc-200/80 dark:border-white/[0.08] shadow-sm p-6">
      <div className="mb-5 flex flex-col gap-4 text-left">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
              Shorts Renderizados ({renderedShorts.length})
            </h2>
          </div>

          {renderedShorts.length > 0 && (
            <div className="flex flex-wrap items-center gap-2.5 self-start md:self-auto shrink-0">
              {onToggleSelectAllVisible && (
                <button
                  type="button"
                  onClick={() => onToggleSelectAllVisible(filteredShorts)}
                  disabled={filteredShorts.length === 0}
                  aria-label="Seleccionar o deseleccionar todos los Shorts visibles"
                  aria-pressed={allVisibleSelected}
                  className={`h-10 px-3 rounded-lg border inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium tracking-normal gap-1.5 transition-colors disabled:opacity-50 ${
                    allVisibleSelected
                      ? 'border-cyan-500/40 bg-cyan-500/10 text-cyan-700 dark:text-cyan-300'
                      : 'border-zinc-200/80 dark:border-white/[0.08] bg-zinc-100 dark:bg-[#090B10] hover:bg-zinc-200/70 dark:hover:bg-[#171C29] text-zinc-700 dark:text-zinc-300'
                  }`}
                >
                  {allVisibleSelected ? (
                    <CheckSquare className="w-3.5 h-3.5 text-cyan-500" />
                  ) : (
                    <Square className="w-3.5 h-3.5 text-zinc-500 dark:text-zinc-400" />
                  )}
                  {allVisibleSelected ? 'Limpiar selección' : 'Seleccionar todos'}
                </button>
              )}
              {onDownloadShorts && (
                <button
                  type="button"
                  onClick={() =>
                    onDownloadShorts(
                      selectedVisibleShorts.length > 0 ? selectedVisibleShorts : filteredShorts,
                      selectedVisibleShorts.length > 0 ? 'selected' : 'all'
                    )
                  }
                  disabled={isBusy || filteredShorts.length === 0}
                  aria-label="Descargar Shorts"
                  className="h-10 px-3.5 rounded-lg border border-emerald-500/35 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-semibold tracking-normal gap-1.5 transition-colors tabular-nums disabled:opacity-50"
                >
                  {activeOperation === 'download_shorts' ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Download className="w-3.5 h-3.5" />
                  )}
                  {selectedVisibleShorts.length > 0
                    ? `Descargar Seleccionados (${selectedVisibleShorts.length})`
                    : `Descargar Todos (${filteredShorts.length})`}
                </button>
              )}
              {onToggleSocialDetails && (
                <button
                  type="button"
                  onClick={onToggleSocialDetails}
                  aria-label="Mostrar u ocultar categorías y estado de redes"
                  aria-pressed={showSocialDetails}
                  className={`h-10 px-3 rounded-lg border inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium tracking-normal gap-1.5 transition-colors ${
                    showSocialDetails
                      ? 'border-cyan-500/40 bg-cyan-500/10 text-cyan-700 dark:text-cyan-300'
                      : 'border-zinc-200/80 dark:border-white/[0.08] bg-zinc-100 dark:bg-[#090B10] hover:bg-zinc-200/70 dark:hover:bg-[#171C29] text-zinc-700 dark:text-zinc-300'
                  }`}
                >
                  {showSocialDetails ? (
                    <EyeOff className="w-3.5 h-3.5 text-cyan-500" />
                  ) : (
                    <Eye className="w-3.5 h-3.5 text-zinc-500 dark:text-zinc-400" />
                  )}
                  {showSocialDetails ? 'Ocultar categorías y redes' : 'Categorías y redes'}
                </button>
              )}
              {onDispatchTikTokStudio && pendingTikTokCount > 0 && (
                <button
                  type="button"
                  onClick={onDispatchTikTokStudio}
                  disabled={isBusy}
                  aria-label={`Subir TikToks en PC (${pendingTikTokCount})`}
                  className="h-10 px-3.5 rounded-lg border border-pink-500/40 bg-pink-500/10 hover:bg-pink-500/20 text-pink-700 dark:text-pink-300 inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-semibold tracking-normal gap-1.5 transition-colors tabular-nums disabled:opacity-50"
                >
                  {activeOperation === 'dispatch_tiktok_studio' ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Upload className="w-3.5 h-3.5" />
                  )}
                  Subir TikToks en PC ({pendingTikTokCount})
                </button>
              )}
              <button
                type="button"
                onClick={onOpenScheduleModal}
                disabled={isBusy}
                aria-label="Abrir Programación de Fecha y Hora"
                className="h-10 px-4 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white shadow-lg shadow-cyan-500/15 inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium tracking-normal gap-2 transition-all disabled:opacity-50"
              >
                <Clock className="w-3.5 h-3.5" />
                Programar Fecha y Hora
              </button>
              <button
                type="button"
                onClick={onCancelAllShorts}
                disabled={isBusy}
                aria-label="Cancelar Todos los Shorts"
                className="h-10 px-4 rounded-lg border border-red-200 dark:border-red-900/70 bg-red-50 dark:bg-red-950/60 hover:bg-red-100 dark:hover:bg-red-900/60 text-red-700 dark:text-red-300 inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium tracking-normal gap-2 transition-colors disabled:opacity-50"
              >
                <Trash2 className="w-3.5 h-3.5" />
                Cancelar Todos los Shorts
              </button>
            </div>
          )}
        </div>

        {renderedShorts.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <button
              type="button"
              onClick={() => onGalleryFilterChange('all')}
              aria-pressed={galleryFilter === 'all'}
              className={`h-10 px-3.5 rounded-lg border text-xs font-medium inline-flex items-center justify-center whitespace-nowrap transition-colors tabular-nums ${
                galleryFilter === 'all'
                  ? 'bg-gradient-to-r from-cyan-500 to-blue-600 border-transparent text-white shadow-sm shadow-cyan-500/20'
                  : 'border-zinc-200/80 dark:border-white/[0.08] bg-zinc-100 dark:bg-[#090B10] text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200/70 dark:hover:bg-[#171C29]'
              }`}
            >
              Todos ({renderedShorts.length})
            </button>
            {effectiveCategories.map((catMeta) => {
              const active = galleryFilter === catMeta.key;
              return (
                <button
                  key={catMeta.key}
                  type="button"
                  onClick={() => onGalleryFilterChange(catMeta.key)}
                  aria-pressed={active}
                  className={`h-10 px-3.5 rounded-lg border text-xs font-medium inline-flex items-center justify-center whitespace-nowrap transition-colors tabular-nums ${
                    active
                      ? 'bg-emerald-600 border-emerald-500 text-white shadow-sm'
                      : 'border-zinc-200/80 dark:border-white/[0.08] bg-zinc-100 dark:bg-[#090B10] text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200/70 dark:hover:bg-[#171C29]'
                  }`}
                >
                  {catMeta.shortLabel} ({categoryCounts[catMeta.key] ?? 0})
                </button>
              );
            })}
          </div>
        )}
      </div>

      {filteredShorts.length === 0 ? (
        <div
          data-testid="shorts-grid-4col"
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5"
        >
          <div className="sm:col-span-2 lg:col-span-4 py-8 px-4 rounded-xl border border-dashed border-zinc-200 dark:border-white/[0.1] text-sm text-zinc-500 dark:text-zinc-400 text-left">
            {renderedShorts.length === 0
              ? 'No hay Shorts renderizados actualmente en ./output_shorts/.'
              : 'Ningún Short coincide con el filtro de plataforma seleccionado.'}
          </div>
        </div>
      ) : (
        <div
          data-testid="shorts-grid-4col"
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 text-left"
        >
          {filteredShorts.map((item, idx) => {
            const cacheKey = item.relative_path || item.filename;
            const cacheVersion = rerenderVersions[cacheKey] || rerenderVersions[item.filename];
            return (
              <ShortCard
                key={`${item.folder}/${item.filename}`}
                item={item}
                index={idx}
                cacheVersion={cacheVersion}
                scheduleValue={getShortScheduleValue(item, idx)}
                queues={queues}
                pipelineStatus={pipelineStatus}
                isBusy={isBusy}
                isSelected={selectedShortKeys.includes(getShortSelectionKey(item))}
                onToggleSelect={
                  onToggleSelectShort ? () => onToggleSelectShort(item) : undefined
                }
                showSocialDetails={showSocialDetails}
                categoryOptions={effectiveCategories}
                onScheduleValueChange={(val) => onScheduleValueChange(item, val)}
                onScheduleSingle={() => onScheduleSingle(item, idx)}
                onToggleShortCategory={onToggleShortCategory}
                onOpenLayoutEditor={() => onOpenLayoutEditor(item)}
                onCancelSingle={() => onCancelSingle(item)}
                onDoubleClickVideo={() => onDoubleClickVideo(item)}
              />
            );
          })}
        </div>
      )}
    </section>
  );
}
