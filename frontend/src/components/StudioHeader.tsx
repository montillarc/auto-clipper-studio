import { Activity, Film, FolderPlus, HardDrive, KeyRound, Loader2, Moon, Radio, Sun, Trash2 } from 'lucide-react';
import type { ActiveStudioTab, DiskSpaceReport, PipelineStatus, ThemeMode } from '../types';
import type { ActiveOperation } from './studioHelpers';

export function StudioHeader({
  projectId,
  projectDisplayName,
  themeMode,
  onToggleTheme,
  diskSpace,
  pipelineStatus,
  isBusy,
  activeOperation,
  onNewProject,
  onDiskCleanup,
  activeTab = 'studio',
  onSelectTab,
  isLiveMonitoring = false,
}: {
  projectId?: string;
  projectDisplayName?: string | null;
  themeMode: ThemeMode;
  onToggleTheme: () => void;
  diskSpace: DiskSpaceReport | null;
  pipelineStatus: PipelineStatus | null;
  isBusy: boolean;
  activeOperation: ActiveOperation;
  onNewProject: () => void;
  onDiskCleanup: () => void;
  activeTab?: ActiveStudioTab;
  onSelectTab?: (tab: ActiveStudioTab) => void;
  isLiveMonitoring?: boolean;
}) {
  const isPipelineActive =
    pipelineStatus?.status === 'RUNNING' ||
    pipelineStatus?.status === 'STARTED' ||
    pipelineStatus?.status === 'DISCOVERING';
  const isSecondaryWindow = Boolean(projectId && projectId !== 'default');

  const scrollToMonitor = () => {
    const el = document.getElementById('process-monitor-section');
    if (el && typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <header className="relative z-30 bg-white/95 dark:bg-[#11151F]/90 backdrop-blur-md rounded-2xl border border-zinc-200/80 dark:border-white/[0.08] shadow-sm dark:shadow-black/30 px-5 py-4 flex flex-col gap-3.5">
      <div className="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-3">
        <div className="flex items-center gap-3 text-left min-w-0">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 text-white flex items-center justify-center shadow-lg shadow-cyan-500/15 shrink-0">
            <Film className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-lg sm:text-xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50 whitespace-nowrap">
                Auto-Clipper Studio
              </h1>
              {isSecondaryWindow && (
                <span
                  data-testid="active-project-badge"
                  className="shrink-0 px-2 py-0.5 rounded-md bg-cyan-500/15 border border-cyan-500/30 text-[11px] font-medium text-cyan-600 dark:text-cyan-300 tabular-nums"
                >
                  Proyecto: {projectDisplayName || projectId}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            role="switch"
            aria-checked={themeMode === 'dark'}
            aria-label="Cambiar apariencia Light / Dark"
            onClick={onToggleTheme}
            className="h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-zinc-100 dark:bg-[#090B10] hover:bg-zinc-200/70 dark:hover:bg-[#171C29] text-zinc-900 dark:text-zinc-100 inline-flex items-center justify-center whitespace-nowrap leading-none text-sm font-medium tracking-normal gap-2 transition-colors"
          >
            <span
              className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-semibold transition-colors ${
                themeMode === 'light'
                  ? 'bg-white text-zinc-900 shadow-sm'
                  : 'text-zinc-500 dark:text-zinc-400'
              }`}
            >
              <Sun className="w-3.5 h-3.5 text-amber-500" />
              Light
            </span>
            <span
              className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-semibold transition-colors ${
                themeMode === 'dark'
                  ? 'bg-[#171C29] text-zinc-50 border border-white/[0.08] shadow-sm'
                  : 'text-zinc-500 dark:text-zinc-400'
              }`}
            >
              <Moon className="w-3.5 h-3.5 text-cyan-400" />
              Dark
            </span>
          </button>

          {diskSpace && (
            <div className="h-10 px-3.5 rounded-lg bg-zinc-100 dark:bg-[#090B10] border border-zinc-200/80 dark:border-white/[0.08] inline-flex items-center gap-2 text-xs font-medium text-zinc-700 dark:text-zinc-300 tabular-nums whitespace-nowrap">
              <HardDrive className="w-4 h-4 text-zinc-500 dark:text-cyan-400 shrink-0" />
              <span>
                {diskSpace.free_gb} GB libres / {diskSpace.total_gb} GB ({diskSpace.free_percentage}%)
              </span>
            </div>
          )}

          <button
            type="button"
            onClick={onNewProject}
            disabled={activeOperation === 'new_project'}
            title="Abrir un proyecto nuevo en una ventana independiente"
            aria-label="Iniciar Nuevo Proyecto"
            className="h-10 px-4 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white shadow-lg shadow-cyan-500/15 inline-flex items-center justify-center whitespace-nowrap leading-none text-sm font-medium tracking-normal gap-2 transition-all disabled:opacity-50"
          >
            {activeOperation === 'new_project' ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <FolderPlus className="w-4 h-4" />
            )}
            Nuevo Proyecto
          </button>

          <button
            type="button"
            onClick={onDiskCleanup}
            disabled={isBusy}
            className="h-10 px-4 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#090B10] hover:bg-zinc-100 dark:hover:bg-[#171C29] text-zinc-800 dark:text-zinc-200 inline-flex items-center justify-center whitespace-nowrap leading-none text-sm font-medium tracking-normal gap-2 transition-colors disabled:opacity-50"
          >
            {activeOperation === 'cleanup' ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Trash2 className="w-4 h-4 text-zinc-600 dark:text-zinc-400" />
            )}
            Limpiar Temporales
          </button>
        </div>
      </div>

      <div className="pt-2.5 border-t border-zinc-200/70 dark:border-white/[0.06] flex flex-wrap items-center justify-between gap-2.5">
        <div
          role="tablist"
          aria-label="Navegación principal del estudio"
          className="inline-flex items-center p-0.5 rounded-xl bg-zinc-100 dark:bg-[#090B10] border border-zinc-200/80 dark:border-white/[0.08]"
        >
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'studio'}
            onClick={() => onSelectTab?.('studio')}
            className={`h-10 px-4 rounded-lg inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-semibold gap-1.5 transition-all ${
              activeTab === 'studio'
                ? 'bg-white dark:bg-[#171C29] text-zinc-900 dark:text-white shadow-sm'
                : 'text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-200'
            }`}
          >
            <Film className="w-3.5 h-3.5" />
            Estudio de Shorts
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'live'}
            onClick={() => onSelectTab?.('live')}
            className={`h-10 px-4 rounded-lg inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-semibold gap-1.5 transition-all ${
              activeTab === 'live'
                ? 'bg-white dark:bg-[#171C29] text-zinc-900 dark:text-white shadow-sm'
                : 'text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-200'
            }`}
          >
            <Radio className={`w-3.5 h-3.5 ${isLiveMonitoring ? 'text-emerald-500 animate-pulse' : ''}`} />
            Directo en Vivo
            {isLiveMonitoring && (
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" aria-hidden="true" />
            )}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'accounts'}
            onClick={() => onSelectTab?.('accounts')}
            className={`h-10 px-4 rounded-lg inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-semibold gap-1.5 transition-all ${
              activeTab === 'accounts'
                ? 'bg-white dark:bg-[#171C29] text-zinc-900 dark:text-white shadow-sm'
                : 'text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-200'
            }`}
          >
            <KeyRound className="w-3.5 h-3.5" />
            Cuentas &amp; APIs
          </button>
        </div>

        {isPipelineActive && pipelineStatus && (
          <button
            type="button"
            onClick={scrollToMonitor}
            aria-label="Ir al Monitor Activo"
            className="h-10 px-3 rounded-lg border border-cyan-500/40 bg-cyan-500/15 hover:bg-cyan-500/25 text-cyan-700 dark:text-cyan-300 inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-semibold gap-2 transition-colors tabular-nums"
          >
            <Activity className="w-3.5 h-3.5 animate-pulse" />
            <span>
              {pipelineStatus.phase_label || 'Procesando'} · {pipelineStatus.progress_percent ?? 0}%
            </span>
          </button>
        )}
      </div>
    </header>
  );
}
