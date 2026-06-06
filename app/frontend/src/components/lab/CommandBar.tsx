import { Kbd } from "./Kbd";

export function CommandBar() {
  return (
    <header className="h-12 flex-shrink-0 flex items-center gap-4 px-4
                       bg-bg1 border-b border-line">
      {/* logo */}
      <div className="flex items-center gap-2">
        <div className="w-6 h-6 rounded grid place-items-center
                        font-mono font-bold text-[13px] text-white"
             style={{ background: "linear-gradient(135deg, #1f5fd6, #d6336c)" }}>
          P
        </div>
        <div className="leading-tight">
          <div className="text-[13px] font-bold">Particle Lab</div>
          <div className="text-3xs font-mono text-text-faint tracking-wide2 mt-[2px]">
            v0.4.2 · CUDA 12.1
          </div>
        </div>
      </div>

      <div className="w-px h-6 bg-line" />

      {/* breadcrumb */}
      <div className="flex items-center gap-2 font-mono text-[11px]">
        <span className="text-text-faint">SESSION</span>
        <span className="text-text">session_2026-05-02_14:32</span>
        <span className="text-text-faint">›</span>
        <span className="text-ink">YOLOv11-seg · INFERENCE</span>
      </div>

      {/* command palette */}
      <div className="flex-1 flex justify-center">
        <div className="w-[360px] flex items-center gap-2 px-3 py-1.5
                        bg-bg2 border border-line rounded text-[12px]
                        text-text-faint">
          <span>Run command, switch sample, jump to metric…</span>
          <span className="ml-auto flex items-center gap-1">
            <Kbd>⌘</Kbd><Kbd>K</Kbd>
          </span>
        </div>
      </div>

      {/* GPU status */}
      <div className="flex items-center gap-3 font-mono text-[11px] text-text-mute">
        <span className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-good" />
          GPU RTX 4090 · 24GB
        </span>
        <span className="text-text-faint">·</span>
        <span>VRAM <span className="text-text">4.2 / 24 GB</span></span>
      </div>

      <div className="flex items-center gap-2">
        <button className="px-3 py-1.5 rounded text-[12px] font-semibold
                           border border-line bg-bg1 text-text
                           hover:bg-bg2 transition-colors">
          ↻ Reload
        </button>
        <button className="px-3 py-1.5 rounded text-[12px] font-semibold
                           border border-line bg-bg1 text-text
                           hover:bg-bg2 transition-colors">
          ⚙ Settings
        </button>
      </div>
    </header>
  );
}
