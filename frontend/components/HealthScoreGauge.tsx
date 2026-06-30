interface HealthScoreGaugeProps {
  score: number;
}

function bandFor(score: number): { label: string; color: string } {
  if (score >= 85) return { label: "Healthy", color: "#3DDC97" };
  if (score >= 60) return { label: "Needs attention", color: "#E8A33D" };
  return { label: "At risk", color: "#E2574C" };
}

export function HealthScoreGauge({ score }: HealthScoreGaugeProps) {
  const band = bandFor(score);
  const circumference = 2 * Math.PI * 54;
  const offset = circumference * (1 - score / 100);

  return (
    <div className="flex items-center gap-5">
      <div className="relative h-32 w-32">
        <svg viewBox="0 0 120 120" className="h-32 w-32 -rotate-90">
          <circle
            cx="60"
            cy="60"
            r="54"
            fill="none"
            stroke="#22272E"
            strokeWidth="10"
          />
          <circle
            cx="60"
            cy="60"
            r="54"
            fill="none"
            stroke={band.color}
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            style={{ transition: "stroke-dashoffset 0.6s ease" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-mono text-3xl font-semibold text-ink">
            {score.toFixed(0)}
          </span>
          <span className="text-xs text-muted">/ 100</span>
        </div>
      </div>
      <div>
        <p className="font-mono text-sm uppercase tracking-wide text-muted">
          Health score
        </p>
        <p className="text-lg font-medium" style={{ color: band.color }}>
          {band.label}
        </p>
      </div>
    </div>
  );
}
