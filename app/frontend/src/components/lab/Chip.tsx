import clsx from "clsx";

type Tone = "mute" | "ink" | "coral" | "amber" | "good" | "bad";

const tones: Record<Tone, string> = {
  mute:  "bg-bg3 text-text-mute border-line",
  ink:   "bg-ink-soft text-ink border-ink/30",
  coral: "bg-coral-soft text-coral border-coral/30",
  amber: "bg-amber-soft text-amber border-amber/30",
  good:  "bg-good-soft text-good border-good/30",
  bad:   "bg-bad-soft text-bad border-bad/30",
};

export function Chip({
  children, tone = "mute", className,
}: { children: React.ReactNode; tone?: Tone; className?: string }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 px-1.5 py-[2px] rounded-[3px]",
        "font-mono text-[10.5px] font-medium tracking-wide2 uppercase",
        "border",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
