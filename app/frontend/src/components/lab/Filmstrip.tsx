"use client";

import clsx from "clsx";
import type { FilmstripItem } from "@/lib/types";

export function Filmstrip({
  items, activeIdx, onPick,
}: {
  items: FilmstripItem[];
  activeIdx: number;
  onPick: (i: number) => void;
}) {
  return (
    <div className="bg-bg1 border border-line rounded p-2">
      <div className="flex items-center justify-between mb-2 px-1">
        <span className="font-mono text-[10px] text-text-faint tracking-wide2 uppercase">
          Filmstrip · {items.length} samples
        </span>
        <span className="font-mono text-[10px] text-text-faint tracking-wide">
          scroll →
        </span>
      </div>
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        {items.map((it) => {
          const isActive = it.index === activeIdx;
          return (
            <button
              key={it.index}
              onClick={() => onPick(it.index)}
              className={clsx(
                "relative flex-shrink-0 w-14 h-14 rounded-[3px] overflow-hidden cursor-pointer",
                "border",
                isActive
                  ? "border-ink ring-1 ring-ink"
                  : "border-line hover:border-line-strong",
              )}
            >
              <div className="absolute inset-0"
                   style={{
                     background:
                       "repeating-linear-gradient(45deg, #2a2a30 0 3px, #1f1f25 3px 6px)",
                   }}/>
              <div className="absolute inset-[20%_25%_35%_30%] bg-[#3a3f48]/90 rounded-[40%]" />
              <div className="absolute top-0.5 left-1 font-mono text-[8px] text-text-mute"
                   style={{ textShadow: "0 1px 2px rgba(0,0,0,.8)" }}>
                {it.label}
              </div>
              {it.ok && (
                <div className="absolute bottom-0.5 right-1 w-1.5 h-1.5
                                rounded-full bg-good" />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
