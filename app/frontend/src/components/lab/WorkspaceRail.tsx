"use client";

import clsx from "clsx";
import type { ModeId } from "@/lib/types";

interface RailItem {
  id: ModeId | "gallery" | "logs";
  glyph: string;
  label: string;
  sub?: string;
  isMode: boolean;
}

const items: RailItem[] = [
  { id: "yolo",    glyph: "◢",  label: "YOLO",   sub: "seg",   isMode: true },
  { id: "unet",    glyph: "ʃ",  label: "U-NET",  sub: "train", isMode: true },
  { id: "legacy",  glyph: "◇",  label: "LEGACY", sub: "otsu",  isMode: true },
];

const utility: RailItem[] = [
  { id: "gallery", glyph: "▦", label: "GALLERY", sub: "all",  isMode: false },
  { id: "logs",    glyph: "#", label: "LOGS",    sub: "run",  isMode: false },
];

export function WorkspaceRail({
  active, onChange,
}: { active: ModeId; onChange: (m: ModeId) => void }) {
  return (
    <aside className="w-[78px] flex-shrink-0 bg-bg1 border-r border-line
                      flex flex-col py-3">
      <div className="px-2 pb-2 text-3xs font-mono text-text-faint
                      tracking-wide3 uppercase">
        Workspace
      </div>

      {items.map((it) => {
        const isActive = it.isMode && active === (it.id as ModeId);
        return (
          <button
            key={it.id}
            onClick={() => it.isMode && onChange(it.id as ModeId)}
            className={clsx(
              "relative mx-2 my-1 px-2 py-3 rounded text-center cursor-pointer",
              "border transition-colors",
              isActive
                ? "bg-bg2 border-ink/30"
                : "border-transparent hover:bg-bg2",
            )}
          >
            {isActive && (
              <span className="absolute -left-[9px] top-1/2 -translate-y-1/2
                               w-[3px] h-6 bg-ink rounded" />
            )}
            <div className={clsx(
              "text-[22px] font-mono font-bold leading-none",
              isActive ? "text-ink" : "text-text-mute",
            )}>{it.glyph}</div>
            <div className={clsx(
              "text-3xs font-mono font-semibold mt-1.5 tracking-wide2",
              isActive ? "text-text" : "text-text-faint",
            )}>{it.label}</div>
            {it.sub && (
              <div className="text-[9px] font-mono text-text-faint mt-[2px] tracking-wide">
                {it.sub}
              </div>
            )}
          </button>
        );
      })}

      <div className="flex-1" />

      <div className="px-2 pb-2 pt-3 text-3xs font-mono text-text-faint
                      tracking-wide3 uppercase">
        Utility
      </div>
      {utility.map((it) => (
        <div key={it.id}
             className="mx-2 my-1 px-2 py-3 rounded text-center
                        cursor-pointer hover:bg-bg2">
          <div className="text-[18px] font-mono font-bold leading-none text-text-mute">
            {it.glyph}
          </div>
          <div className="text-3xs font-mono font-semibold mt-1.5
                          tracking-wide2 text-text-faint">{it.label}</div>
          {it.sub && (
            <div className="text-[9px] font-mono text-text-faint mt-[2px] tracking-wide">
              {it.sub}
            </div>
          )}
        </div>
      ))}
    </aside>
  );
}
