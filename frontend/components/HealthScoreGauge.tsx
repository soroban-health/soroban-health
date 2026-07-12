"use client";

import { useEffect, useRef, useState } from "react";

interface HealthScoreGaugeProps {
  score: number;
}

function bandFor(score: number): {
  label: string;
  stroke: string;
  text: string;
} {
  if (score >= 85)
    return { label: "Healthy", stroke: "stroke-signal", text: "text-signal" };
  if (score >= 60)
    return {
      label: "Needs attention",
      stroke: "stroke-warn",
      text: "text-warn",
    };
  return { label: "At risk", stroke: "stroke-critical", text: "text-critical" };
}

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

/** Counts up from 0 to `target` over `duration`ms, driving both the ring
 * fill and its text. Deriving the color band from the in-flight value
 * (not the final score) is what produces the "red -> amber -> green"
 * sweep as the ring fills, per the design brief's signature element. */
function useCountUp(target: number, duration = 900): number {
  const [value, setValue] = useState(0);
  const startRef = useRef<number | null>(null);

  useEffect(() => {
    startRef.current = null;
    let frame: number;

    function tick(timestamp: number) {
      if (startRef.current === null) startRef.current = timestamp;
      const elapsed = timestamp - startRef.current;
      const progress = Math.min(elapsed / duration, 1);
      setValue(target * easeOutCubic(progress));
      if (progress < 1) frame = requestAnimationFrame(tick);
    }

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, duration]);

  return value;
}

export function HealthScoreGauge({ score }: HealthScoreGaugeProps) {
  const animated = useCountUp(score);
  const band = bandFor(animated);
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - animated / 100);

  return (
    <div className="flex items-center gap-6">
      <div className="relative h-32 w-32 shrink-0">
        <svg viewBox="0 0 120 120" className="h-32 w-32 -rotate-90">
          <circle
            cx="60"
            cy="60"
            r={radius}
            fill="none"
            className="stroke-line"
            strokeWidth="10"
          />
          <circle
            cx="60"
            cy="60"
            r={radius}
            fill="none"
            className={`${band.stroke} transition-[stroke] duration-300 ease-out`}
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-mono text-3xl font-semibold tabular-nums text-ink">
            {Math.round(animated)}
          </span>
          <span className="font-mono text-xs text-muted">/ 100</span>
        </div>
      </div>
      <div>
        <p className="font-mono text-xs uppercase tracking-widest text-muted">
          Health score
        </p>
        <p className={`mt-1 text-lg font-semibold ${band.text}`}>
          {band.label}
        </p>
      </div>
    </div>
  );
}
