/**
 * Skeleton placeholder shown while a scan is in flight.
 *
 * Mirrors the rough shape of the results section:
 *   - A circle matching the HealthScoreGauge ring + label block
 *   - A narrow bar for the "Health history" section header + chart area
 *   - Three finding rows matching FindingsList item height
 *
 * Uses `animate-pulse` so the muted blocks breathe without any layout shift
 * when the real results replace them.
 */
export function ScanSkeleton() {
  return (
    <section
      aria-busy="true"
      aria-label="Scan results loading"
      className="mt-12 space-y-8 animate-pulse"
    >
      {/* Gauge skeleton -------------------------------------------------- */}
      <div className="flex items-center gap-6">
        {/* Circle ring */}
        <div className="h-32 w-32 shrink-0 rounded-full border-[10px] border-line bg-surface" />
        {/* Label + band text */}
        <div className="space-y-3">
          <div className="h-2.5 w-20 rounded bg-line" />
          <div className="h-5 w-28 rounded bg-line" />
        </div>
      </div>

      {/* History chart skeleton ------------------------------------------ */}
      <div>
        <div className="mb-3 h-2.5 w-24 rounded bg-line" />
        <div className="h-24 rounded-lg border border-line bg-surface" />
      </div>

      {/* Findings list skeleton ------------------------------------------ */}
      <div>
        <div className="mb-3 h-2.5 w-20 rounded bg-line" />
        <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
          {[0, 1, 2].map((i) => (
            <li key={i} className="flex items-start justify-between gap-4 p-4">
              <div className="flex-1 space-y-2">
                {/* filename:line */}
                <div className="h-3 w-40 rounded bg-line" />
                {/* message */}
                <div className="h-3 w-64 rounded bg-line" />
              </div>
              {/* severity badge */}
              <div className="h-5 w-14 shrink-0 rounded-full bg-line" />
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
