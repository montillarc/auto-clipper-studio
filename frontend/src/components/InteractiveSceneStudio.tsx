import { useEffect, useState } from 'react';
import type React from 'react';
import { Camera, Clock, Loader2, Sliders } from 'lucide-react';
import type { CamOverlayPos, LayoutMode, SceneDetectResponse, SubtitlePosition } from '../types';
import { LiveSceneCropPreview, LiveSubtitleOverlay } from './LiveSubtitlePreview';
import {
  DUAL_BOX_LAYOUTS,
  formatSecondsToTimestamp,
  parseTimestampInput,
} from './studioHelpers';

export interface StudioDragTarget {
  box: 'cam' | 'content';
  mode: 'move' | 'resize' | 'resize_nw' | 'resize_ne' | 'resize_sw';
  startX: number;
  startY: number;
  origBox: [number, number, number, number];
}

export function InteractiveSceneStudio({
  sceneData,
  layoutMode,
  camOverlayPos,
  subtitlePreset,
  subtitlePosition,
  customCamBox,
  customContentBox,
  customBoxesManual,
  videoDurationSec,
  sampleTimestampSec,
  isDetectingFrame = false,
  studioCanvasRef,
  onSetCustomBoxesManual,
  onStartDragging,
  onSeekTimestamp,
}: {
  sceneData: SceneDetectResponse;
  layoutMode: LayoutMode;
  camOverlayPos: CamOverlayPos;
  subtitlePreset: string;
  subtitlePosition: SubtitlePosition;
  customCamBox: [number, number, number, number];
  customContentBox: [number, number, number, number];
  customBoxesManual: boolean;
  videoDurationSec?: number | null;
  sampleTimestampSec?: number | null;
  isDetectingFrame?: boolean;
  studioCanvasRef: React.RefObject<HTMLDivElement>;
  onSetCustomBoxesManual: (manual: boolean) => void;
  onStartDragging: (target: StudioDragTarget) => void;
  onSeekTimestamp?: (sec: number) => void;
}) {
  const initialSec = Math.max(0, sceneData.timestamp_sec ?? sampleTimestampSec ?? 0);
  const [scrubSec, setScrubSec] = useState<number>(initialSec);
  const [tsInputText, setTsInputText] = useState<string>(() => formatSecondsToTimestamp(initialSec));

  useEffect(() => {
    const nextSec = Math.max(0, sceneData.timestamp_sec ?? sampleTimestampSec ?? 0);
    setScrubSec(nextSec);
    setTsInputText(formatSecondsToTimestamp(nextSec));
  }, [sceneData.timestamp_sec, sceneData.frame_url, sampleTimestampSec]);

  const effectiveDurationSec = Math.max(
    10,
    Math.round(sceneData.duration_sec ?? videoDurationSec ?? Math.max(60, scrubSec + 60))
  );
  const hasKnownDuration = Boolean(
    (sceneData.duration_sec && sceneData.duration_sec > 0) ||
      (videoDurationSec && videoDurationSec > 0)
  );
  const isFullscreenOnly = layoutMode === 'fullscreen';
  const manualActive =
    customBoxesManual && (isFullscreenOnly || DUAL_BOX_LAYOUTS.includes(layoutMode));

  const commitTimestampSeek = (targetSec: number) => {
    const clamped = Math.max(
      0,
      hasKnownDuration ? Math.min(effectiveDurationSec, targetSec) : targetSec
    );
    setScrubSec(clamped);
    setTsInputText(formatSecondsToTimestamp(clamped));
    onSeekTimestamp?.(clamped);
  };

  const handleCaptureInputClick = () => {
    const parsed = parseTimestampInput(tsInputText);
    commitTimestampSeek(parsed !== null ? parsed : scrubSec);
  };

  return (
    <section className="bg-white dark:bg-[#11151F]/90 backdrop-blur-md rounded-2xl border border-zinc-200/80 dark:border-white/[0.08] shadow-sm p-6 flex flex-col gap-5 text-left">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2">
        <div>
          <h2 className="text-xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50 flex items-center gap-2">
            <Sliders className="w-5 h-5 text-cyan-500" />
            Estudio Interactivo de Escena 16:9 &rarr; 9:16
          </h2>
          <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5 tabular-nums">
            {manualActive
              ? isFullscreenOnly
                ? `Encuadre manual 9:16 fijado · Arrastra o redimensiona libremente desde cualquier esquina · ${sceneData.resolution} · ${sceneData.faces_detected} rostro(s)`
                : `Recorte manual Studio fijado · Arrastra o redimensiona Cámara (Azul) y Juego/Contenido (Verde) · ${sceneData.resolution} · ${sceneData.faces_detected} rostro(s)`
              : isFullscreenOnly
              ? `Detección IA automática · Mueve el encuadre Cámara 9:16 donde quieras · ${sceneData.resolution} · ${sceneData.faces_detected} rostro(s)`
              : `Detección IA automática · Arrastra o redimensiona Cámara (Azul) y Juego/Contenido (Verde) · ${sceneData.resolution} · ${sceneData.faces_detected} rostro(s)`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={() => onSetCustomBoxesManual(!customBoxesManual)}
            className={`h-10 px-3 rounded-lg border inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium transition-colors ${
              customBoxesManual
                ? 'border-cyan-500/50 bg-cyan-500/15 text-cyan-700 dark:text-cyan-300 hover:bg-cyan-500/25'
                : 'border-zinc-200/80 dark:border-white/[0.08] bg-zinc-100 dark:bg-[#090B10] text-zinc-800 dark:text-zinc-200 hover:bg-zinc-200/70 dark:hover:bg-[#171C29]'
            }`}
          >
            {customBoxesManual ? 'Usar Detección Automática' : 'Fijar Encuadre Manual'}
          </button>
          <span className="h-10 px-3 rounded-lg bg-zinc-100 dark:bg-[#090B10] border border-zinc-200/80 dark:border-white/[0.08] text-xs font-medium text-zinc-700 dark:text-zinc-300 inline-flex items-center tabular-nums">
            Encuadre: {layoutMode}
          </span>
        </div>
      </div>

      {/* Selector libre de cualquier fotograma del video (Línea de tiempo completa) */}
      <div className="p-4 rounded-xl bg-zinc-50 dark:bg-[#090B10] border border-zinc-200/80 dark:border-white/[0.08] flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-xs font-semibold text-zinc-800 dark:text-zinc-200 tabular-nums">
            <Clock className="w-3.5 h-3.5 text-cyan-500 shrink-0" />
            <span>
              Fotograma del video: {formatSecondsToTimestamp(scrubSec)}
              {hasKnownDuration ? ` / ${formatSecondsToTimestamp(effectiveDurationSec)}` : ''}
            </span>
          </div>
          {sceneData.frame_source === 'thumbnail_fallback' ? (
            <span className="px-2.5 py-1 rounded-md bg-amber-500/15 border border-amber-500/35 text-[11px] font-medium text-amber-700 dark:text-amber-300">
              Vista de portada (stream directo no disponible; elige otro momento e intenta capturar)
            </span>
          ) : (
            <span className="px-2.5 py-1 rounded-md bg-emerald-500/15 border border-emerald-500/35 text-[11px] font-medium text-emerald-700 dark:text-emerald-300">
              Fotograma real del video · Ajusta cualquier punto de la línea de tiempo
            </span>
          )}
        </div>

        <input
          type="range"
          min={0}
          max={effectiveDurationSec}
          step={1}
          value={Math.min(effectiveDurationSec, Math.max(0, Math.round(scrubSec)))}
          aria-label="Línea de tiempo del video"
          onChange={(e) => {
            const val = Number(e.target.value);
            setScrubSec(val);
            setTsInputText(formatSecondsToTimestamp(val));
          }}
          onPointerUp={() => commitTimestampSeek(scrubSec)}
          onKeyUp={() => commitTimestampSeek(scrubSec)}
          className="w-full accent-cyan-500 cursor-pointer"
        />

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={isDetectingFrame}
            onClick={() => commitTimestampSeek(Math.max(0, scrubSec - 15))}
            className="h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#171C29] hover:bg-zinc-100 dark:hover:bg-[#1F2638] text-zinc-800 dark:text-zinc-200 inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium tabular-nums disabled:opacity-50"
          >
            -15s
          </button>

          <input
            id="studio-timestamp-input"
            aria-label="Minuto o segundo del video"
            type="text"
            value={tsInputText}
            onChange={(e) => setTsInputText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                handleCaptureInputClick();
              }
            }}
            placeholder="MM:SS"
            className="w-28 h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#11151F] text-sm text-center font-medium text-zinc-900 dark:text-zinc-50 tabular-nums focus:outline-none focus:ring-2 focus:ring-cyan-500"
          />

          <button
            type="button"
            disabled={isDetectingFrame}
            onClick={() => commitTimestampSeek(scrubSec + 15)}
            className="h-10 px-3 rounded-lg border border-zinc-200/80 dark:border-white/[0.08] bg-white dark:bg-[#171C29] hover:bg-zinc-100 dark:hover:bg-[#1F2638] text-zinc-800 dark:text-zinc-200 inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-medium tabular-nums disabled:opacity-50"
          >
            +15s
          </button>

          <button
            type="button"
            disabled={isDetectingFrame}
            onClick={handleCaptureInputClick}
            className="h-10 px-3.5 rounded-lg border border-cyan-500/40 bg-cyan-500/15 hover:bg-cyan-500/25 text-cyan-800 dark:text-cyan-200 inline-flex items-center justify-center whitespace-nowrap leading-none text-xs font-semibold gap-1.5 transition-colors disabled:opacity-50"
          >
            {isDetectingFrame ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Camera className="w-3.5 h-3.5" />
            )}
            Capturar Fotograma
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Lienzo 16:9 Interactivo */}
        <div className="lg:col-span-8 flex flex-col gap-3">
          <div
            ref={studioCanvasRef}
            className="relative w-full aspect-video rounded-xl overflow-hidden border border-zinc-200/80 dark:border-white/[0.08] bg-zinc-950 select-none touch-none"
          >
            <img
              src={sceneData.frame_url}
              alt={`Fotograma 16:9 de ${sceneData.video_filename}`}
              className="w-full h-full object-cover pointer-events-none"
            />

            {/* Caja Contenido / Juego (visible en todos los layouts duales/compuestos) */}
            {!isFullscreenOnly && (
              <div
                onPointerDown={(e) => {
                  onSetCustomBoxesManual(true);
                  onStartDragging({
                    box: 'content',
                    mode: 'move',
                    startX: e.clientX,
                    startY: e.clientY,
                    origBox: customContentBox,
                  });
                }}
                style={{
                  left: `${customContentBox[0] * 100}%`,
                  top: `${customContentBox[1] * 100}%`,
                  width: `${customContentBox[2] * 100}%`,
                  height: `${customContentBox[3] * 100}%`,
                }}
                className="absolute border-2 border-emerald-400 bg-emerald-500/15 rounded-lg cursor-move"
              >
                <span className="px-2 py-0.5 text-[11px] font-semibold bg-emerald-600 text-white rounded-br-md inline-block">
                  Contenido / Juego
                </span>
                <div
                  onPointerDown={(e) => {
                    e.stopPropagation();
                    onSetCustomBoxesManual(true);
                    onStartDragging({
                      box: 'content',
                      mode: 'resize_nw',
                      startX: e.clientX,
                      startY: e.clientY,
                      origBox: customContentBox,
                    });
                  }}
                  className="absolute -left-1 -top-1 w-3.5 h-3.5 bg-emerald-400 rounded-sm cursor-nwse-resize"
                />
                <div
                  onPointerDown={(e) => {
                    e.stopPropagation();
                    onSetCustomBoxesManual(true);
                    onStartDragging({
                      box: 'content',
                      mode: 'resize_ne',
                      startX: e.clientX,
                      startY: e.clientY,
                      origBox: customContentBox,
                    });
                  }}
                  className="absolute -right-1 -top-1 w-3.5 h-3.5 bg-emerald-400 rounded-sm cursor-nesw-resize"
                />
                <div
                  onPointerDown={(e) => {
                    e.stopPropagation();
                    onSetCustomBoxesManual(true);
                    onStartDragging({
                      box: 'content',
                      mode: 'resize_sw',
                      startX: e.clientX,
                      startY: e.clientY,
                      origBox: customContentBox,
                    });
                  }}
                  className="absolute -left-1 -bottom-1 w-3.5 h-3.5 bg-emerald-400 rounded-sm cursor-nesw-resize"
                />
                <div
                  onPointerDown={(e) => {
                    e.stopPropagation();
                    onSetCustomBoxesManual(true);
                    onStartDragging({
                      box: 'content',
                      mode: 'resize',
                      startX: e.clientX,
                      startY: e.clientY,
                      origBox: customContentBox,
                    });
                  }}
                  className="absolute -right-1 -bottom-1 w-4 h-4 bg-emerald-400 rounded-sm cursor-nwse-resize"
                />
              </div>
            )}

            {/* Caja Cámara Streamer / Encuadre 9:16 */}
            <div
              onPointerDown={(e) => {
                onSetCustomBoxesManual(true);
                onStartDragging({
                  box: 'cam',
                  mode: 'move',
                  startX: e.clientX,
                  startY: e.clientY,
                  origBox: customCamBox,
                });
              }}
              style={{
                left: `${customCamBox[0] * 100}%`,
                top: `${customCamBox[1] * 100}%`,
                width: `${customCamBox[2] * 100}%`,
                height: `${customCamBox[3] * 100}%`,
              }}
              className="absolute border-2 border-cyan-400 bg-cyan-500/20 rounded-lg cursor-move"
            >
              <span className="px-2 py-0.5 text-[11px] font-semibold bg-cyan-600 text-white rounded-br-md inline-block">
                {isFullscreenOnly ? 'Encuadre Cámara 9:16' : 'Cámara Rostro'}
              </span>
              <div
                onPointerDown={(e) => {
                  e.stopPropagation();
                  onSetCustomBoxesManual(true);
                  onStartDragging({
                    box: 'cam',
                    mode: 'resize_nw',
                    startX: e.clientX,
                    startY: e.clientY,
                    origBox: customCamBox,
                  });
                }}
                className="absolute -left-1 -top-1 w-3.5 h-3.5 bg-cyan-400 rounded-sm cursor-nwse-resize"
              />
              <div
                onPointerDown={(e) => {
                  e.stopPropagation();
                  onSetCustomBoxesManual(true);
                  onStartDragging({
                    box: 'cam',
                    mode: 'resize_ne',
                    startX: e.clientX,
                    startY: e.clientY,
                    origBox: customCamBox,
                  });
                }}
                className="absolute -right-1 -top-1 w-3.5 h-3.5 bg-cyan-400 rounded-sm cursor-nesw-resize"
              />
              <div
                onPointerDown={(e) => {
                  e.stopPropagation();
                  onSetCustomBoxesManual(true);
                  onStartDragging({
                    box: 'cam',
                    mode: 'resize_sw',
                    startX: e.clientX,
                    startY: e.clientY,
                    origBox: customCamBox,
                  });
                }}
                className="absolute -left-1 -bottom-1 w-3.5 h-3.5 bg-cyan-400 rounded-sm cursor-nesw-resize"
              />
              <div
                onPointerDown={(e) => {
                  e.stopPropagation();
                  onSetCustomBoxesManual(true);
                  onStartDragging({
                    box: 'cam',
                    mode: 'resize',
                    startX: e.clientX,
                    startY: e.clientY,
                    origBox: customCamBox,
                  });
                }}
                className="absolute -right-1 -bottom-1 w-4 h-4 bg-cyan-400 rounded-sm cursor-nwse-resize"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs text-zinc-600 dark:text-zinc-400 tabular-nums">
            <div className="p-2.5 rounded-lg bg-zinc-50 dark:bg-[#090B10] border border-zinc-200/80 dark:border-white/[0.08]">
              Cámara X/Y: {(customCamBox[0] * 100).toFixed(0)}% / {(customCamBox[1] * 100).toFixed(0)}%
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-50 dark:bg-[#090B10] border border-zinc-200/80 dark:border-white/[0.08]">
              Cámara W/H: {(customCamBox[2] * 100).toFixed(0)}% / {(customCamBox[3] * 100).toFixed(0)}%
            </div>
            {!isFullscreenOnly && (
              <>
                <div className="p-2.5 rounded-lg bg-zinc-50 dark:bg-[#090B10] border border-zinc-200/80 dark:border-white/[0.08]">
                  Juego X/Y: {(customContentBox[0] * 100).toFixed(0)}% / {(customContentBox[1] * 100).toFixed(0)}%
                </div>
                <div className="p-2.5 rounded-lg bg-zinc-50 dark:bg-[#090B10] border border-zinc-200/80 dark:border-white/[0.08]">
                  Juego W/H: {(customContentBox[2] * 100).toFixed(0)}% / {(customContentBox[3] * 100).toFixed(0)}%
                </div>
              </>
            )}
          </div>
        </div>

        {/* Vista Previa 9:16 en Vivo con Recorte Óptico Real */}
        <div className="lg:col-span-4 flex flex-col items-center gap-2">
          <span className="text-xs font-medium text-zinc-700 dark:text-zinc-300">
            Vista Previa 9:16 en Tiempo Real
          </span>
          <div
            data-testid="studio-preview-9-16"
            className="relative w-52 aspect-[9/16] rounded-2xl overflow-hidden border-2 border-zinc-300 dark:border-white/[0.14] bg-zinc-950 shadow-inner flex flex-col justify-between p-2"
          >
            <LiveSceneCropPreview
              frameUrl={sceneData.frame_url}
              layoutMode={layoutMode}
              camOverlayPos={camOverlayPos}
              customCamBox={customCamBox}
              customContentBox={customContentBox}
            />

            <LiveSubtitleOverlay
              subtitlePreset={subtitlePreset}
              subtitlePosition={subtitlePosition}
              layoutMode={layoutMode}
              showNoneBadge={false}
            />
          </div>
        </div>
      </div>
    </section>
  );
}
