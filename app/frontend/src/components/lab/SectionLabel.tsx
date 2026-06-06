export function SectionLabel({
  index, children,
}: { index?: string; children: React.ReactNode }) {
  return (
    <div className="text-3xs font-mono font-semibold tracking-wide3 uppercase
                    text-text-faint mb-1">
      {index && <span className="text-text-faint mr-2">{index}</span>}
      <span>{children}</span>
    </div>
  );
}
