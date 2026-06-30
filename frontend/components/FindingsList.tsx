import type { Finding } from "@/lib/types";

const SEVERITY_LABEL: Record<Finding["severity"], string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

const SEVERITY_CLASS: Record<Finding["severity"], string> = {
  high: "severity-high",
  medium: "severity-medium",
  low: "severity-low",
};

interface FindingsListProps {
  findings: Finding[];
}

export function FindingsList({ findings }: FindingsListProps) {
  if (findings.length === 0) {
    return (
      <div className="rounded-lg border border-line bg-surface p-6 text-center">
        <p className="font-mono text-sm text-signal">
          No anti-patterns detected in this scan.
        </p>
      </div>
    );
  }

  return (
    <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
      {findings.map((finding, idx) => (
        <li key={`${finding.file}-${finding.line}-${idx}`} className="p-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="font-mono text-sm text-ink">
                {finding.file}
                <span className="text-muted">:{finding.line}</span>
              </p>
              <p className="mt-1 text-sm text-muted">{finding.message}</p>
            </div>
            <span
              className={`shrink-0 font-mono text-xs uppercase tracking-wide ${SEVERITY_CLASS[finding.severity]}`}
            >
              {SEVERITY_LABEL[finding.severity]}
            </span>
          </div>
        </li>
      ))}
    </ul>
  );
}
