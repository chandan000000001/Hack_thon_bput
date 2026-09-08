export default function LoadingSkeleton({ rows = 3, className = '' }: { rows?: number; className?: string }) {
  return (
    <div className={`animate-pulse space-y-2.5 ${className}`}>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="h-4 rounded bg-zinc-700/50"
          style={{ width: `${100 - ((i * 13) % 40)}%` }}
        />
      ))}
    </div>
  );
}

export function PanelSkeleton({
  height = 'h-48',
  className = '',
  rows,
}: {
  height?: string;
  className?: string;
  rows?: number;
}) {
  if (rows !== undefined) {
    return (
      <div className={`${height} rounded-xl border border-zinc-700/50 bg-zinc-800/40 p-4 ${className}`}>
        <LoadingSkeleton rows={rows} />
      </div>
    );
  }
  return <div className={`${height} animate-pulse rounded-xl bg-zinc-800/40 ${className}`} />;
}
