"use client";

import { useRef, useState } from "react";
import type { ScanHistoryEntry } from "@/lib/types";

interface HealthHistoryChartProps {
  entries: ScanHistoryEntry[];
}

const VIEW_WIDTH = 320;
const VIEW_HEIGHT = 140;
const PADDING = { top: 12, right: 16, bottom: 24, left: 32 };
const PLOT_WIDTH = VIEW_WIDTH - PADDING.left - PADDING.right;
const PLOT_HEIGHT = VIEW_HEIGHT - PADDING.top - PADDING.bottom;

const LINE_COLOR = "#22272E";
const MUTED_COLOR = "#8A93A0";
const INK_COLOR = "#E6EAEE";
const ACCENT_COLOR = "#5B8CFF";
const SURFACE_COLOR = "#12161B";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

// X spacing is by scan index, not literal elapsed time — a deliberate v0
// simplification (see docs/architecture.md). The Y-axis (the score trend)
// is what this chart actually needs to convey.
function xFor(index: number, count: number): number {
  if (count <= 1) return PADDING.left + PLOT_WIDTH / 2;
  return PADDING.left + (index / (count - 1)) * PLOT_WIDTH;
}

function yFor(score: number): number {
  return PADDING.top + (1 - score / 100) * PLOT_HEIGHT;
}

export function HealthHistoryChart({ entries }: HealthHistoryChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  if (entries.length === 0) {
    return (
      <div className="rounded-lg border border-line bg-surface p-6 text-center">
        <p className="font-mono text-sm text-muted">No scan history yet.</p>
      </div>
    );
  }

  const points = entries.map((entry, i) => ({
    x: xFor(i, entries.length),
    y: yFor(entry.health_score),
    entry,
  }));

  function handlePointerMove(e: React.PointerEvent<HTMLDivElement>) {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const svgX = ((e.clientX - rect.left) / rect.width) * VIEW_WIDTH;
    let nearest = 0;
    let nearestDist = Infinity;
    points.forEach((p, i) => {
      const dist = Math.abs(p.x - svgX);
      if (dist < nearestDist) {
        nearestDist = dist;
        nearest = i;
      }
    });
    setActiveIndex(nearest);
  }

  const active = activeIndex !== null ? points[activeIndex] : null;
  const last = points[points.length - 1];

  // Anchor the tooltip to whichever edge keeps it inside the container
  // instead of always centering, which would overflow past the y-axis
  // labels when hovering the first/last point.
  let tooltipAnchor = "-translate-x-1/2";
  if (active) {
    const fraction = active.x / VIEW_WIDTH;
    if (fraction < 0.2) tooltipAnchor = "translate-x-0";
    else if (fraction > 0.8) tooltipAnchor = "-translate-x-full";
  }

  return (
    <div
      ref={containerRef}
      className="relative rounded-lg border border-line bg-surface p-4"
      onPointerMove={handlePointerMove}
      onPointerLeave={() => setActiveIndex(null)}
    >
      <svg
        viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
        className="w-full"
        role="img"
        aria-label="Health score history"
      >
        {[0, 50, 100].map((tick) => (
          <g key={tick}>
            <line
              x1={PADDING.left}
              x2={VIEW_WIDTH - PADDING.right}
              y1={yFor(tick)}
              y2={yFor(tick)}
              stroke={LINE_COLOR}
              strokeWidth={1}
            />
            <text
              x={PADDING.left - 6}
              y={yFor(tick)}
              fill={MUTED_COLOR}
              fontSize={9}
              textAnchor="end"
              dominantBaseline="middle"
            >
              {tick}
            </text>
          </g>
        ))}

        {points.length > 1 && (
          <polyline
            points={points.map((p) => `${p.x},${p.y}`).join(" ")}
            fill="none"
            stroke={ACCENT_COLOR}
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}

        {active && (
          <line
            x1={active.x}
            x2={active.x}
            y1={PADDING.top}
            y2={VIEW_HEIGHT - PADDING.bottom}
            stroke={MUTED_COLOR}
            strokeWidth={1}
          />
        )}

        {points.map((p, i) => (
          <circle
            key={p.entry.scanned_at}
            cx={p.x}
            cy={p.y}
            r={activeIndex === i ? 5 : 4}
            fill={ACCENT_COLOR}
            stroke={SURFACE_COLOR}
            strokeWidth={2}
            tabIndex={0}
            onFocus={() => setActiveIndex(i)}
            onBlur={() => setActiveIndex(null)}
            aria-label={`${formatDate(p.entry.scanned_at)}: ${p.entry.health_score.toFixed(0)}`}
          >
            <title>
              {formatDate(p.entry.scanned_at)}: {p.entry.health_score.toFixed(0)}
            </title>
          </circle>
        ))}

        {/* Direct label on the last point, per line-chart convention. */}
        <text
          x={last.x}
          y={last.y - 10}
          fill={INK_COLOR}
          fontSize={10}
          fontFamily="monospace"
          textAnchor="end"
        >
          {last.entry.health_score.toFixed(0)}
        </text>

        <text
          x={points[0].x}
          y={VIEW_HEIGHT - 6}
          fill={MUTED_COLOR}
          fontSize={9}
          textAnchor="start"
        >
          {formatDate(points[0].entry.scanned_at)}
        </text>
        {points.length > 1 && (
          <text
            x={last.x}
            y={VIEW_HEIGHT - 6}
            fill={MUTED_COLOR}
            fontSize={9}
            textAnchor="end"
          >
            {formatDate(last.entry.scanned_at)}
          </text>
        )}
      </svg>

      {active && (
        <div
          className={`pointer-events-none absolute top-2 ${tooltipAnchor} rounded-md border border-line bg-base px-2 py-1 font-mono text-xs text-ink shadow-lg`}
          style={{ left: `${(active.x / VIEW_WIDTH) * 100}%` }}
        >
          <p className="font-semibold">{active.entry.health_score.toFixed(0)}</p>
          <p className="text-muted">{formatDate(active.entry.scanned_at)}</p>
        </div>
      )}

      {entries.length === 1 && (
        <p className="mt-2 text-center font-mono text-xs text-muted">
          Run another scan to see a trend.
        </p>
      )}
    </div>
  );
}
