"use client";

import clsx from "clsx";
import { useState } from "react";
import type { CanvasMeta, Particle } from "@/lib/types";

type Layer = "SEM" | "PRED" | "GT" | "DIFF";

export function CanvasViewer({
  meta, particles, sampleIdx, sampleTotal, onPrev, onNext,
}: {
  meta: CanvasMeta;
  particles: Particle[];
  sampleIdx: number;
  sampleTotal: number;
  onPrev?: () => void;
  onNext?: () => void;
}) {
  const [layers, setLayers] = useState<Record<Layer, boolean>>({
    SEM: true, PRED: true, GT: true, DIFF: false,
  });
  const [zoom, setZoom] = useState(1);

  return (
    <div className="flex flex-col flex-1 bg-bg1 border border-line rounded overflow-hidden">
      {/* canvas top bar */}
      <div className="flex items-center gap-3 px-3 py-2 border-b border-line bg-bg1">
        <span className="font-mono text-[10px] text-text-faint tracking-wide2 uppercase">
          Sample {String(sampleIdx).padStart(2, "0")}/{String(sampleTotal).padStart(2, "0")}
        </span>
        <span className="font-mono text-[12px] text-text font-semibold">
          {meta.file}
        </span>

        <div className="flex-1" />

        {/* layer toggles */}
        <div className="flex bg-bg2 border border-line rounded overflow-hidden">
          {(["SEM", "PRED", "GT", "DIFF"] as Layer[]).map((L) => (
            <button
              key={L}
              onClick={() => setLayers({ ...layers, [L]: !layers[L] })}
              className={clsx(
                "px-3 py-1 font-mono text-[10px] font-semibold tracking-wide2 transition-colors",
                layers[L]
                  ? L === "PRED" ? "bg-ink text-white"
                    : L === "GT" ? "bg-coral text-white"
                    : L === "DIFF" ? "bg-amber text-white"
                    : "bg-text text-bg1"
                  : "text-text-mute hover:bg-bg3",
              )}
            >
              {L}
            </button>
          ))}
        </div>

        {/* zoom */}
        <div className="flex items-center gap-1 px-2 py-1 bg-bg2 border border-line rounded">
          <span className="font-mono text-[10px] text-text">
            {zoom === 1 ? "1:1" : `${zoom.toFixed(1)}×`}
          </span>
          <button onClick={() => setZoom(Math.max(0.5, zoom - 0.25))}
                  className="font-mono text-[10px] px-2 hover:text-ink">− Zoom</button>
          <button onClick={() => setZoom(Math.min(4, zoom + 0.25))}
                  className="font-mono text-[10px] px-2 hover:text-ink">+ Zoom</button>
        </div>

        {/* prev/next */}
        <div className="flex bg-bg2 border border-line rounded">
          <button onClick={onPrev}
                  className="px-3 py-1 hover:bg-bg3 border-r border-line">
            ◀
          </button>
          <button onClick={onNext}
                  className="px-3 py-1 hover:bg-bg3">▶</button>
        </div>
      </div>

      {/* canvas body — black SEM area */}
      <div className="relative flex-1 bg-black overflow-hidden">
        <svg width="100%" height="100%" viewBox="0 0 100 100"
             preserveAspectRatio="xMidYMid slice"
             className="absolute inset-0">
          <defs>
            <filter id="grain">
              <feTurbulence type="fractalNoise" baseFrequency="3.2" numOctaves="2" seed="7" />
              <feColorMatrix values="0 0 0 0 0.18  0 0 0 0 0.18  0 0 0 0 0.20  0 0 0 1 0" />
            </filter>
            <radialGradient id="vignette" cx="50%" cy="50%" r="70%">
              <stop offset="0%" stopColor="#1a1a1f" stopOpacity="0" />
              <stop offset="100%" stopColor="#000" stopOpacity="0.7" />
            </radialGradient>
            <radialGradient id="particle-fill" cx="35%" cy="35%" r="70%">
              <stop offset="0%" stopColor="#3a3f48" />
              <stop offset="60%" stopColor="#22262d" />
              <stop offset="100%" stopColor="#0d0f12" />
            </radialGradient>
          </defs>

          {layers.SEM && <rect width="100" height="100" filter="url(#grain)" />}

          {layers.SEM && particles.map((p) => (
            <g key={`b-${p.id}`} transform={`rotate(${p.rot} ${p.cx} ${p.cy})`}>
              <ellipse cx={p.cx} cy={p.cy} rx={p.rx} ry={p.ry}
                       fill="url(#particle-fill)" />
            </g>
          ))}

          {layers.SEM && <rect width="100" height="100" fill="url(#vignette)" />}

          {/* PRED overlay (cyan/ink) */}
          {layers.PRED && particles.map((p) => (
            <g key={`pred-${p.id}`} transform={`rotate(${p.rot} ${p.cx} ${p.cy})`}>
              <ellipse cx={p.cx} cy={p.cy} rx={p.rx + 0.4} ry={p.ry + 0.4}
                       fill="rgba(31,95,214,0.10)" stroke="#1f5fd6"
                       strokeWidth="0.35" />
            </g>
          ))}

          {/* GT overlay (coral) */}
          {layers.GT && particles.map((p) => (
            <g key={`gt-${p.id}`} transform={`rotate(${p.rot} ${p.cx} ${p.cy})`}>
              <ellipse cx={p.cx + 0.3} cy={p.cy - 0.2}
                       rx={p.rx - 0.2} ry={p.ry - 0.2}
                       fill="none" stroke="#d6336c" strokeWidth="0.2"
                       strokeDasharray="0.6 0.4" opacity="0.8" />
            </g>
          ))}
        </svg>

        {/* particle labels (first 4) */}
        <div className="absolute inset-0 pointer-events-none">
          {particles.slice(0, 4).map((p) => (
            <div key={`lbl-${p.id}`}
                 style={{
                   position: "absolute",
                   left: `${p.cx + p.rx + 1}%`,
                   top: `${p.cy - p.ry}%`,
                 }}
                 className="font-mono text-[9px] text-ink
                            bg-black/60 px-1 rounded-[2px] border border-ink/40">
              {p.id} · {p.conf}
            </div>
          ))}
        </div>

        {/* scale bar */}
        <div className="absolute left-4 bottom-4 flex items-center gap-2
                        bg-black/70 px-2 py-1 rounded-[3px]
                        border border-line/40
                        font-mono text-[10px] text-text">
          <div className="w-[60px] h-[3px] bg-text" />
          <span>1 μm</span>
        </div>

        {/* image meta */}
        <div className="absolute right-4 top-4 bg-black/70 px-3 py-1.5
                        rounded-[3px] border border-line/40
                        font-mono text-[10px] text-text-mute leading-relaxed">
          <div><span className="text-text-faint">FILE  </span>{meta.file}</div>
          <div><span className="text-text-faint">SIZE  </span>{meta.size}</div>
          <div><span className="text-text-faint">MAG   </span>{meta.mag}</div>
          <div><span className="text-text-faint">DETECT </span>
            <span className="text-ink">{meta.detect}</span></div>
        </div>

        {/* crosshair */}
        <div className="absolute left-[42%] top-[58%] w-8 h-8 -ml-4 -mt-4
                        pointer-events-none">
          <div className="absolute left-1/2 top-0 bottom-0 w-px bg-ink/60" />
          <div className="absolute top-1/2 left-0 right-0 h-px bg-ink/60" />
          <div className="absolute inset-[40%] border border-ink" />
        </div>
      </div>
    </div>
  );
}
