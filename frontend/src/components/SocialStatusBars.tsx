import type {
  PipelineStatus,
  QueuesResponse,
  RenderedShortItem,
  SocialNetworkStatusItem,
} from '../types';
import { resolveShortSocialStatuses } from './studioHelpers';

function getBarClasses(state: SocialNetworkStatusItem['state']): { bar: string; text: string } {
  switch (state) {
    case 'uploaded':
      return { bar: 'bg-emerald-500', text: 'text-emerald-600 dark:text-emerald-400' };
    case 'processing':
      return { bar: 'bg-cyan-500 animate-pulse', text: 'text-cyan-600 dark:text-cyan-400' };
    case 'draft':
      return { bar: 'bg-amber-400', text: 'text-amber-600 dark:text-amber-300' };
    case 'pending':
      return { bar: 'bg-amber-500', text: 'text-amber-600 dark:text-amber-300' };
    case 'error':
      return { bar: 'bg-red-500', text: 'text-red-600 dark:text-red-400' };
    case 'not_applicable':
      return { bar: 'bg-zinc-300 dark:bg-zinc-700', text: 'text-zinc-500 dark:text-zinc-400' };
    case 'local':
    default:
      return { bar: 'bg-zinc-400 dark:bg-zinc-600', text: 'text-zinc-700 dark:text-zinc-300' };
  }
}

export function SocialStatusBars({
  item,
  queues,
  pipelineStatus,
  compact = false,
}: {
  item: RenderedShortItem;
  queues: QueuesResponse;
  pipelineStatus: PipelineStatus | null;
  compact?: boolean;
}) {
  const statuses = resolveShortSocialStatuses(item, queues, pipelineStatus);
  const ordered: Array<{ label: string; info: SocialNetworkStatusItem }> = [
    { label: 'YouTube', info: statuses.youtube },
    { label: 'Instagram', info: statuses.instagram },
    { label: 'TikTok', info: statuses.tiktok },
    ...(statuses.facebook ? [{ label: 'Facebook', info: statuses.facebook }] : []),
  ];

  return (
    <div
      data-testid={`social-bars-${item.filename}`}
      className="flex flex-col gap-1.5 rounded-xl border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#090B10]/85 p-2.5"
    >
      {ordered.map(({ label, info }) => {
        const colors = getBarClasses(info.state);
        const showDetail =
          !compact &&
          Boolean(info.detail) &&
          info.detail !== 'Listo en local (Sin programar)' &&
          info.detail !== info.status_label;
        return (
          <div
            key={info.network}
            data-testid={`social-status-${info.network}-${item.filename}`}
            className="flex flex-col gap-0.5"
          >
            <div className="flex items-center justify-between gap-2 text-[11px]">
              <span className="inline-flex items-center gap-1 min-w-0 font-medium text-zinc-700 dark:text-zinc-200">
                <span>{label}</span>
                {info.account && (
                  <span className="text-[10px] text-zinc-500 dark:text-zinc-400 truncate">
                    {info.account}
                  </span>
                )}
              </span>
              <span className="inline-flex items-center gap-1.5 shrink-0">
                {info.permalink && (
                  <a
                    href={info.permalink}
                    target="_blank"
                    rel="noopener noreferrer"
                    title={`Abrir publicación en ${label}`}
                    className="text-[10px] font-semibold text-cyan-600 dark:text-cyan-400 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/40 rounded"
                  >
                    Ver ↗
                  </a>
                )}
                <span className={`font-semibold tabular-nums ${colors.text}`}>
                  {info.status_label}
                </span>
              </span>
            </div>
            <div className="w-full h-1.5 rounded-full bg-zinc-200/80 dark:bg-zinc-800 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-300 ${colors.bar}`}
                style={{ width: `${Math.min(100, Math.max(0, info.percent))}%` }}
              />
            </div>
            {showDetail && (
              <span className="text-[10px] text-zinc-500 dark:text-zinc-400 truncate" title={info.detail}>
                {info.detail}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
