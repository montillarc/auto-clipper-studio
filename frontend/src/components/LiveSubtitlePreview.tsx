import { useEffect, useState } from 'react';
import type { CamOverlayPos, LayoutMode, SubtitlePosition } from '../types';
import { PREVIEW_SAMPLE_WORDS } from './studioHelpers';

export function SceneLayoutWireframe({
  layoutMode,
  camOverlayPos,
  compact = false,
}: {
  layoutMode: LayoutMode;
  camOverlayPos: CamOverlayPos;
  compact?: boolean;
}) {
  const txt = compact ? 'text-[9px]' : 'text-[10px]';
  if (layoutMode === 'floating_circle' || layoutMode === 'floating_cam_top') {
    return (
      <>
        <div
          className={`absolute inset-0 bg-gradient-to-br from-emerald-950 via-zinc-900 to-zinc-950 flex items-center justify-center font-medium text-emerald-300/80 ${
            compact ? 'text-[10px]' : 'text-[11px]'
          }`}
        >
          Gameplay 9:16
        </div>
        <div
          className={`relative z-10 flex ${
            camOverlayPos.includes('right') ? 'justify-end' : 'justify-start'
          } ${camOverlayPos.startsWith('bottom') ? 'mt-auto mb-9' : compact ? 'mt-1.5' : 'mt-2'}`}
        >
          <div
            className={`border-2 border-cyan-400 bg-blue-900/75 font-semibold text-white flex items-center justify-center ${txt} ${
              layoutMode === 'floating_circle'
                ? compact
                  ? 'w-11 h-11 rounded-full'
                  : 'w-14 h-14 rounded-full'
                : compact
                ? 'w-14 h-10 rounded-md'
                : 'w-20 h-14 rounded-lg'
            }`}
          >
            CAM
          </div>
        </div>
      </>
    );
  }
  if (layoutMode === 'blur_16_9_cam') {
    return (
      <div className="relative z-10 flex flex-col items-center justify-center h-full gap-2 my-auto">
        <div
          className={`${
            compact ? 'w-16 h-11' : 'w-24 h-16'
          } rounded-lg border border-cyan-400 bg-blue-900/70 text-white flex items-center justify-center font-semibold ${txt}`}
        >
          Cámara
        </div>
        <div
          className={`w-full aspect-video rounded-md border border-emerald-400 bg-emerald-900/60 text-emerald-200 flex items-center justify-center font-semibold text-center px-1 ${txt}`}
        >
          16:9 Nítido sobre Blur
        </div>
      </div>
    );
  }
  if (layoutMode === 'split_50_50') {
    return (
      <div className="relative z-10 flex flex-col h-full gap-0.5">
        <div
          className={`h-1/2 rounded-t-md border border-cyan-400/70 bg-blue-900/55 text-white flex items-center justify-center font-semibold ${txt}`}
        >
          Panel 1 · 50%
        </div>
        <div className="h-[2px] w-full bg-zinc-950" />
        <div
          className={`h-1/2 rounded-b-md border border-emerald-400/80 bg-emerald-900/45 text-emerald-200 flex items-center justify-center font-semibold ${txt}`}
        >
          Panel 2 · 50%
        </div>
      </div>
    );
  }
  if (layoutMode === 'ometv') {
    return (
      <div className="relative z-10 flex flex-col h-full gap-0.5">
        <div
          className={`h-[46%] rounded-t-md border border-cyan-400/70 bg-blue-900/50 text-white flex items-center justify-center font-semibold ${txt}`}
        >
          Host OmeTV 50%
        </div>
        <div className="h-4 rounded-sm bg-amber-500/90 text-zinc-950 text-[8px] font-black flex items-center justify-center tracking-wide uppercase">
          OmeTV Banner
        </div>
        <div
          className={`flex-1 rounded-b-md border border-emerald-400/80 bg-emerald-900/40 text-emerald-200 flex items-center justify-center font-semibold ${txt}`}
        >
          Invitado 50%
        </div>
      </div>
    );
  }
  if (layoutMode === 'gaming_hud') {
    return (
      <div className="relative z-10 flex flex-col h-full gap-1">
        <div
          className={`h-[25%] rounded-md border border-cyan-400/70 bg-blue-900/55 text-white flex items-center justify-center font-semibold ${txt}`}
        >
          Facecam 25%
        </div>
        <div
          className={`flex-1 rounded-md border border-emerald-400/80 bg-emerald-900/45 text-emerald-200 flex items-center justify-center font-semibold ${txt}`}
        >
          HUD / Acción 75%
        </div>
      </div>
    );
  }
  if (layoutMode === 'reaction_pip') {
    return (
      <div className="relative z-10 flex flex-col h-full gap-1">
        <div
          className={`h-[59%] rounded-md border border-emerald-400/80 bg-emerald-950/60 text-emerald-200 flex items-center justify-center font-semibold text-center px-1 ${txt}`}
        >
          Video 16:9 + Blur
        </div>
        <div
          className={`flex-1 rounded-md border border-cyan-400/70 bg-blue-900/55 text-white flex items-center justify-center font-semibold text-center px-1 ${txt}`}
        >
          Reacción Creador
        </div>
      </div>
    );
  }
  if (layoutMode === 'reality_multicam') {
    return (
      <div className="relative z-10 flex flex-col h-full gap-1">
        <div
          className={`h-[33%] rounded-md border border-amber-400/80 bg-amber-950/45 text-amber-200 flex items-center justify-center font-semibold text-center px-1 ${txt}`}
        >
          Sala Panorámica
        </div>
        <div
          className={`flex-1 rounded-md border border-cyan-400/70 bg-blue-900/50 text-white flex items-center justify-center font-semibold text-center px-1 ${txt}`}
        >
          Zoom Hablante
        </div>
      </div>
    );
  }
  if (layoutMode === 'podcast_dynamic') {
    return (
      <div className="relative z-10 flex flex-col h-full gap-1">
        <div
          className={`h-1/2 rounded-md border border-cyan-400/70 bg-blue-900/50 text-white flex items-center justify-center font-semibold text-center px-1 ${txt}`}
        >
          Hablante 1 / 9:16
        </div>
        <div
          className={`h-1/2 rounded-md border border-purple-400/80 bg-purple-950/50 text-purple-200 flex items-center justify-center font-semibold text-center px-1 ${txt}`}
        >
          Hablante 2 ↔ 50/50
        </div>
      </div>
    );
  }
  if (layoutMode === 'fullscreen') {
    return (
      <div
        className={`relative z-10 flex-1 rounded-lg border border-cyan-400/70 bg-gradient-to-b from-blue-950/70 to-zinc-900 flex items-center justify-center text-blue-200 font-semibold text-center px-1 ${txt}`}
      >
        Cámara Solo 9:16
      </div>
    );
  }
  if (layoutMode === 'auto') {
    return (
      <div className="relative z-10 flex flex-col h-full gap-1">
        <div className="px-1.5 py-0.5 rounded bg-cyan-500/20 border border-cyan-400/40 text-[8px] font-bold text-cyan-200 text-center uppercase tracking-wider">
          IA Auto · Por Clip
        </div>
        <div
          className={`flex-1 rounded-md border border-zinc-600/80 bg-gradient-to-b from-blue-950/50 via-zinc-900 to-emerald-950/40 text-zinc-200 flex items-center justify-center font-semibold text-center px-1 ${txt}`}
        >
          Solo 9:16 / Split OBS / Dúo
        </div>
      </div>
    );
  }
  return (
    <div className="relative z-10 flex flex-col h-full gap-1">
      <div
        className={`h-[37%] rounded-md border border-cyan-400/70 bg-blue-900/50 text-white flex items-center justify-center font-semibold ${txt}`}
      >
        Cara Streamer
      </div>
      <div
        className={`flex-1 rounded-md border border-emerald-400/80 bg-emerald-900/40 text-emerald-200 flex items-center justify-center font-semibold ${txt}`}
      >
        Gameplay / Juego
      </div>
    </div>
  );
}

function CroppedFrameRegion({
  frameUrl,
  box,
  alt,
  testId,
  className = '',
}: {
  frameUrl: string;
  box: [number, number, number, number];
  alt: string;
  testId: string;
  className?: string;
}) {
  const bx = Math.max(0, Math.min(0.92, box[0]));
  const by = Math.max(0, Math.min(0.92, box[1]));
  const bw = Math.max(0.08, Math.min(1 - bx, box[2]));
  const bh = Math.max(0.08, Math.min(1 - by, box[3]));
  return (
    <div className={`relative overflow-hidden bg-zinc-950 ${className}`}>
      <img
        data-testid={testId}
        src={frameUrl}
        alt={alt}
        draggable={false}
        className="max-w-none max-h-none absolute pointer-events-none select-none"
        style={{
          width: `${(1 / bw) * 100}%`,
          height: `${(1 / bh) * 100}%`,
          left: `${(-bx / bw) * 100}%`,
          top: `${(-by / bh) * 100}%`,
        }}
      />
    </div>
  );
}

export function LiveSceneCropPreview({
  frameUrl,
  layoutMode,
  camOverlayPos,
  customCamBox,
  customContentBox,
  compact = false,
}: {
  frameUrl?: string | null;
  layoutMode: LayoutMode;
  camOverlayPos: CamOverlayPos;
  customCamBox: [number, number, number, number];
  customContentBox: [number, number, number, number];
  compact?: boolean;
}) {
  if (!frameUrl) {
    return (
      <SceneLayoutWireframe
        layoutMode={layoutMode}
        camOverlayPos={camOverlayPos}
        compact={compact}
      />
    );
  }

  if (layoutMode === 'fullscreen') {
    return (
      <div className="relative z-10 flex-1 h-full rounded-lg overflow-hidden border border-cyan-400/70">
        <CroppedFrameRegion
          frameUrl={frameUrl}
          box={customCamBox}
          alt="Recorte en vivo Cámara 9:16"
          testId="live-crop-cam"
          className="w-full h-full"
        />
      </div>
    );
  }

  if (layoutMode === 'floating_circle' || layoutMode === 'floating_cam_top') {
    const isCircle = layoutMode === 'floating_circle';
    return (
      <>
        <CroppedFrameRegion
          frameUrl={frameUrl}
          box={customContentBox}
          alt="Recorte en vivo Contenido"
          testId="live-crop-content"
          className="absolute inset-0 w-full h-full"
        />
        <div
          className={`relative z-10 flex ${
            camOverlayPos.includes('right') ? 'justify-end' : 'justify-start'
          } ${camOverlayPos.startsWith('bottom') ? 'mt-auto mb-9' : compact ? 'mt-1.5' : 'mt-2'}`}
        >
          <CroppedFrameRegion
            frameUrl={frameUrl}
            box={customCamBox}
            alt="Recorte en vivo Cámara"
            testId="live-crop-cam"
            className={`border-2 border-cyan-400 shadow-lg ${
              isCircle
                ? compact
                  ? 'w-11 h-11 rounded-full'
                  : 'w-14 h-14 rounded-full'
                : compact
                ? 'w-14 h-10 rounded-md'
                : 'w-20 h-14 rounded-lg'
            }`}
          />
        </div>
      </>
    );
  }

  if (layoutMode === 'blur_16_9_cam') {
    return (
      <div className="relative z-10 flex flex-col items-center justify-center h-full gap-2 my-auto">
        <CroppedFrameRegion
          frameUrl={frameUrl}
          box={customCamBox}
          alt="Recorte en vivo Cámara"
          testId="live-crop-cam"
          className={`${compact ? 'w-16 h-11' : 'w-24 h-16'} rounded-lg border border-cyan-400 shadow-md`}
        />
        <CroppedFrameRegion
          frameUrl={frameUrl}
          box={customContentBox}
          alt="Recorte en vivo 16:9 Nítido"
          testId="live-crop-content"
          className="w-full aspect-video rounded-md border border-emerald-400 shadow-md"
        />
      </div>
    );
  }

  if (layoutMode === 'split_50_50' || layoutMode === 'podcast_dynamic') {
    return (
      <div className="relative z-10 flex flex-col h-full gap-0.5">
        <CroppedFrameRegion
          frameUrl={frameUrl}
          box={customCamBox}
          alt="Recorte en vivo Panel 1"
          testId="live-crop-cam"
          className="h-1/2 rounded-t-md border border-cyan-400/70"
        />
        <div className="h-[2px] w-full bg-zinc-950" />
        <CroppedFrameRegion
          frameUrl={frameUrl}
          box={customContentBox}
          alt="Recorte en vivo Panel 2"
          testId="live-crop-content"
          className="h-1/2 rounded-b-md border border-emerald-400/80"
        />
      </div>
    );
  }

  if (layoutMode === 'ometv') {
    return (
      <div className="relative z-10 flex flex-col h-full gap-0.5">
        <CroppedFrameRegion
          frameUrl={frameUrl}
          box={customCamBox}
          alt="Recorte en vivo Host"
          testId="live-crop-cam"
          className="h-[46%] rounded-t-md border border-cyan-400/70"
        />
        <div className="h-4 rounded-sm bg-amber-500/90 text-zinc-950 text-[8px] font-black flex items-center justify-center tracking-wide uppercase">
          OmeTV Banner
        </div>
        <CroppedFrameRegion
          frameUrl={frameUrl}
          box={customContentBox}
          alt="Recorte en vivo Invitado"
          testId="live-crop-content"
          className="flex-1 rounded-b-md border border-emerald-400/80"
        />
      </div>
    );
  }

  if (layoutMode === 'gaming_hud') {
    return (
      <div className="relative z-10 flex flex-col h-full gap-1">
        <CroppedFrameRegion
          frameUrl={frameUrl}
          box={customCamBox}
          alt="Recorte en vivo Facecam"
          testId="live-crop-cam"
          className="h-[25%] rounded-md border border-cyan-400/70"
        />
        <CroppedFrameRegion
          frameUrl={frameUrl}
          box={customContentBox}
          alt="Recorte en vivo Gameplay HUD"
          testId="live-crop-content"
          className="flex-1 rounded-md border border-emerald-400/80"
        />
      </div>
    );
  }

  if (layoutMode === 'reaction_pip') {
    return (
      <div className="relative z-10 flex flex-col h-full gap-1">
        <CroppedFrameRegion
          frameUrl={frameUrl}
          box={customContentBox}
          alt="Recorte en vivo Contenido Reacción"
          testId="live-crop-content"
          className="h-[59%] rounded-md border border-emerald-400/80"
        />
        <CroppedFrameRegion
          frameUrl={frameUrl}
          box={customCamBox}
          alt="Recorte en vivo Cámara Reacción"
          testId="live-crop-cam"
          className="flex-1 rounded-md border border-cyan-400/70"
        />
      </div>
    );
  }

  if (layoutMode === 'reality_multicam') {
    return (
      <div className="relative z-10 flex flex-col h-full gap-1">
        <CroppedFrameRegion
          frameUrl={frameUrl}
          box={customContentBox}
          alt="Recorte en vivo Panorámica Reality"
          testId="live-crop-content"
          className="h-[33%] rounded-md border border-amber-400/80"
        />
        <CroppedFrameRegion
          frameUrl={frameUrl}
          box={customCamBox}
          alt="Recorte en vivo Hablante Reality"
          testId="live-crop-cam"
          className="flex-1 rounded-md border border-cyan-400/70"
        />
      </div>
    );
  }

  return (
    <div className="relative z-10 flex flex-col h-full gap-1">
      <CroppedFrameRegion
        frameUrl={frameUrl}
        box={customCamBox}
        alt="Recorte en vivo Cara Streamer"
        testId="live-crop-cam"
        className="h-[37%] rounded-md border border-cyan-400/70"
      />
      <CroppedFrameRegion
        frameUrl={frameUrl}
        box={customContentBox}
        alt="Recorte en vivo Contenido"
        testId="live-crop-content"
        className="flex-1 rounded-md border border-emerald-400/80"
      />
    </div>
  );
}

export function LiveSubtitleOverlay({
  subtitlePreset,
  subtitlePosition,
  layoutMode,
  showNoneBadge = true,
}: {
  subtitlePreset: string;
  subtitlePosition: SubtitlePosition;
  layoutMode: LayoutMode;
  showNoneBadge?: boolean;
}) {
  const [activeWordIdx, setActiveWordIdx] = useState<number>(0);

  useEffect(() => {
    if (subtitlePreset === 'none') return;
    const timer = window.setInterval(() => {
      setActiveWordIdx((prev) => (prev + 1) % PREVIEW_SAMPLE_WORDS.length);
    }, 520);
    return () => window.clearInterval(timer);
  }, [subtitlePreset]);

  const isSplitLike =
    layoutMode === 'split_streamer' ||
    layoutMode === 'split_50_50' ||
    layoutMode === 'gaming_hud' ||
    layoutMode === 'reaction_pip' ||
    layoutMode === 'reality_multicam' ||
    layoutMode === 'podcast_dynamic' ||
    layoutMode === 'auto';

  const resolvedPos: 'top' | 'center' | 'bottom' =
    subtitlePosition === 'auto' ? (isSplitLike ? 'center' : 'bottom') : subtitlePosition;

  let centerYClass = 'top-[38%] left-2 right-2 -translate-y-1/2';
  if (subtitlePosition === 'auto') {
    if (layoutMode === 'split_50_50') centerYClass = 'top-1/2 left-2 right-2 -translate-y-1/2';
    else if (layoutMode === 'gaming_hud') centerYClass = 'top-[25%] left-2 right-2 -translate-y-1/2';
    else if (layoutMode === 'reaction_pip') centerYClass = 'top-[60%] left-2 right-2 -translate-y-1/2';
    else if (layoutMode === 'reality_multicam') centerYClass = 'top-[34%] left-2 right-2 -translate-y-1/2';
  } else {
    centerYClass = 'top-1/2 left-2 right-2 -translate-y-1/2';
  }

  const posClass =
    resolvedPos === 'top'
      ? 'top-5 left-2 right-2'
      : resolvedPos === 'center'
      ? centerYClass
      : 'bottom-5 left-2 right-2';

  if (subtitlePreset === 'none') {
    if (!showNoneBadge) return null;
    return (
      <div className="absolute inset-x-2 bottom-4 z-20 flex justify-center pointer-events-none">
        <span className="px-2.5 py-1 rounded-md bg-zinc-900/85 border border-zinc-700 text-[10px] font-medium text-zinc-300">
          Sin subtítulos activos (Video limpio)
        </span>
      </div>
    );
  }

  if (subtitlePreset === 'one_word_punch') {
    const word = PREVIEW_SAMPLE_WORDS[activeWordIdx];
    const colorClass =
      word.includes('100')
        ? 'text-[#00FF66]'
        : word.includes('!')
        ? 'text-[#FF3B30]'
        : 'text-[#FFE600]';
    return (
      <div className={`absolute z-20 flex justify-center pointer-events-none ${posClass}`}>
        <span
          className={`px-2 py-0.5 font-black uppercase tracking-tight text-lg scale-110 transition-transform duration-150 ${colorClass}`}
          style={{
            textShadow:
              '0 2px 0 #000, 0 -2px 0 #000, 2px 0 0 #000, -2px 0 0 #000, 0 4px 10px rgba(0,0,0,0.85)',
          }}
        >
          {word}
        </span>
      </div>
    );
  }

  if (subtitlePreset === 'clean_apple_box' || subtitlePreset === 'minimal_white') {
    return (
      <div className={`absolute z-20 flex justify-center pointer-events-none ${posClass}`}>
        <div className="px-2.5 py-1 rounded-lg bg-zinc-950/85 backdrop-blur-md border border-white/15 shadow-lg flex flex-wrap justify-center gap-1 text-[11px] font-semibold tracking-tight">
          {PREVIEW_SAMPLE_WORDS.map((word, idx) => (
            <span
              key={word}
              className={`transition-all duration-150 ${
                idx === activeWordIdx ? 'text-[#38BDF8] scale-105' : 'text-white/85'
              }`}
            >
              {word}
            </span>
          ))}
        </div>
      </div>
    );
  }

  if (subtitlePreset === 'nexus_cyber_glow') {
    return (
      <div className={`absolute z-20 flex justify-center pointer-events-none ${posClass}`}>
        <div
          className="px-2 py-0.5 flex flex-wrap justify-center gap-1 font-black uppercase italic tracking-wide text-xs"
          style={{ textShadow: '0 2px 0 #000, 0 0 10px rgba(0,229,255,0.75)' }}
        >
          {PREVIEW_SAMPLE_WORDS.slice(0, 3).map((word, idx) => (
            <span
              key={word}
              className={`transition-transform duration-150 ${
                idx === activeWordIdx % 3 ? 'text-cyan-300 scale-110' : 'text-white'
              }`}
            >
              {word}
            </span>
          ))}
        </div>
      </div>
    );
  }

  if (subtitlePreset === 'karaoke_duo' || subtitlePreset === 'tiktok_karaoke') {
    return (
      <div className={`absolute z-20 flex justify-center pointer-events-none ${posClass}`}>
        <div
          className="px-2 py-0.5 flex flex-wrap justify-center gap-1 font-black uppercase text-[11px]"
          style={{ textShadow: '0 2px 0 #000, 0 -1px 0 #000, 1px 0 0 #000, -1px 0 0 #000' }}
        >
          {PREVIEW_SAMPLE_WORDS.map((word, idx) => (
            <span
              key={word}
              className={`transition-colors duration-150 ${
                idx <= activeWordIdx ? 'text-[#44FF00]' : 'text-white/90'
              }`}
            >
              {word}
            </span>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className={`absolute z-20 flex justify-center pointer-events-none ${posClass}`}>
      <div
        className="px-2 py-0.5 flex flex-wrap justify-center gap-1 font-black uppercase tracking-tight text-xs"
        style={{
          textShadow:
            '0 2px 0 #000, 0 -2px 0 #000, 2px 0 0 #000, -2px 0 0 #000, 0 4px 8px rgba(0,0,0,0.8)',
        }}
      >
        {PREVIEW_SAMPLE_WORDS.map((word, idx) => {
          const isCurrent = idx === activeWordIdx;
          const activeColor = word.includes('100')
            ? 'text-[#00FF66]'
            : word.includes('¡')
            ? 'text-[#FF3B30]'
            : 'text-[#FFE600]';
          return (
            <span
              key={word}
              className={`transition-transform duration-150 ${
                isCurrent ? `${activeColor} scale-110` : 'text-white'
              }`}
            >
              {word}
            </span>
          );
        })}
      </div>
    </div>
  );
}
