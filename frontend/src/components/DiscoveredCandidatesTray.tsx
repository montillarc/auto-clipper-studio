import { Eye, Loader2, Play, Scissors } from 'lucide-react';
import type { DiscoveredCandidateItem } from '../types';
import type { ActiveOperation } from './studioHelpers';

export function DiscoveredCandidatesTray({
  discoveredCandidates,
  selectedCandidateIds,
  isBusy,
  activeOperation,
  onSelectAll,
  onSelectGoldOnly,
  onToggleCandidate,
  onRenderSelected,
  onPreviewCut,
}: {
  discoveredCandidates: DiscoveredCandidateItem[];
  selectedCandidateIds: string[];
  isBusy: boolean;
  activeOperation: ActiveOperation;
  onSelectAll: () => void;
  onSelectGoldOnly: () => void;
  onToggleCandidate: (candidateId: string, checked: boolean) => void;
  onRenderSelected: () => void;
  onPreviewCut: (startTimeSec: number) => void;
}) {
  return (
    <section className="bg-white dark:bg-[#11151F]/90 backdrop-blur-md rounded-2xl border border-zinc-200/80 dark:border-white/[0.08] shadow-sm p-6 flex flex-col gap-4 text-left">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50 flex items-center gap-2">
            <Scissors className="w-5 h-5 text-cyan-500" />
            Bandeja de Clips Descubiertos ({discoveredCandidates.length})
          </h2>
          <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5 tabular-nums">
            Seleccionados para renderizado 9:16: {selectedCandidateIds.length} / {discoveredCandidates.length}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={onSelectAll}
            disabled={isBusy}
            className="h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-zinc-100 dark:bg-[#090B10] hover:bg-zinc-200/70 dark:hover:bg-[#171C29] text-xs font-medium text-zinc-900 dark:text-zinc-100 inline-flex items-center justify-center whitespace-nowrap transition-colors"
          >
            Seleccionar Todos
          </button>
          <button
            type="button"
            onClick={onSelectGoldOnly}
            disabled={isBusy}
            className="h-10 px-3 rounded-lg border border-amber-400/35 bg-amber-500/15 hover:bg-amber-500/25 text-xs font-medium text-amber-800 dark:text-amber-300 inline-flex items-center justify-center whitespace-nowrap transition-colors"
          >
            Solo Oro (&ge;85)
          </button>
          <button
            type="button"
            onClick={onRenderSelected}
            disabled={isBusy || selectedCandidateIds.length === 0}
            className="h-10 px-4 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white shadow-lg shadow-cyan-500/15 inline-flex items-center justify-center whitespace-nowrap leading-none text-sm font-medium gap-2 transition-all disabled:opacity-50"
          >
            {activeOperation === 'render_selected' ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Play className="w-4 h-4 fill-current" />
            )}
            Renderizar Seleccionados ({selectedCandidateIds.length})
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {discoveredCandidates.map((cand) => {
          const isChecked = selectedCandidateIds.includes(cand.candidate_id);
          return (
            <div
              key={cand.candidate_id}
              className={`p-4 rounded-xl border transition-colors flex flex-col gap-2.5 ${
                isChecked
                  ? 'border-cyan-500/60 bg-cyan-500/10'
                  : 'border-zinc-200/80 dark:border-white/[0.08] bg-zinc-50 dark:bg-[#090B10]'
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <label className="flex items-center gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={(e) => onToggleCandidate(cand.candidate_id, e.target.checked)}
                    className="w-4 h-4 rounded accent-cyan-500"
                  />
                  <span className="text-sm font-semibold text-zinc-900 dark:text-zinc-50 line-clamp-1">
                    {cand.hook_title}
                  </span>
                </label>
                <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-zinc-900 text-white dark:bg-[#171C29] dark:text-cyan-300 dark:border dark:border-cyan-500/30 tabular-nums shrink-0">
                  {cand.virality_score} / 100 · {cand.virality_grade}
                </span>
              </div>

              <p className="text-xs text-zinc-600 dark:text-zinc-300 leading-relaxed line-clamp-2">
                {cand.transcript_excerpt}
              </p>

              <div className="flex items-center justify-between gap-2 pt-1">
                <span className="text-xs text-zinc-500 dark:text-zinc-400 tabular-nums">
                  {Math.floor(cand.start_time / 60)}m {Math.floor(cand.start_time % 60)}s &rarr;{' '}
                  {Math.floor(cand.end_time / 60)}m {Math.floor(cand.end_time % 60)}s ({cand.duration.toFixed(0)}s)
                </span>
                <button
                  type="button"
                  onClick={() => onPreviewCut(cand.start_time)}
                  className="h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#171C29] hover:bg-zinc-100 dark:hover:bg-white/[0.06] text-xs font-medium text-zinc-800 dark:text-zinc-200 inline-flex items-center gap-1.5"
                >
                  <Eye className="w-3.5 h-3.5 text-cyan-400" />
                  Previsualizar Corte
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
