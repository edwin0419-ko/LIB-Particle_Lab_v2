export function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-grid place-items-center px-1.5 min-w-4 h-[18px]
                     rounded-[3px] font-mono text-[10px] font-semibold
                     bg-bg3 text-text-mute border border-line border-b-2">
      {children}
    </span>
  );
}
