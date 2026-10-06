"use client";

import { useEffect, useState } from "react";
import { HealthScoreGauge } from "@/components/HealthScoreGauge";
import { FindingsList } from "@/components/FindingsList";
import { HealthHistoryChart } from "@/components/HealthHistoryChart";
import { ScanSkeleton } from "@/components/ScanSkeleton";
import { ThemeToggle } from "@/components/ThemeToggle";
import { runScan, getScanHistory } from "@/lib/api";
import type { ScanResult, ScanHistoryEntry } from "@/lib/types";


const PLACEHOLDER_SOURCE = `pub fn withdraw(env: &Env, amount: i128) -> i128 {
    if amount <= 0 {
        panic!("amount must be positive");
    }
    BALANCE - amount
}`;

function Logo() {
  return (
    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-line bg-surface">
      <svg viewBox="0 0 24 24" className="h-4 w-4 text-signal">
        <path
          d="M2 12h4l2-7 4 14 3-9 2 5h5"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

export default function Home() {
  const [contractId, setContractId] = useState("");
  const [wasmSizeKb, setWasmSizeKb] = useState("");
  const [source, setSource] = useState(PLACEHOLDER_SOURCE);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [history, setHistory] = useState<ScanHistoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reflect scan state in the browser tab so results are visible without
  // switching back. Derived from local state only — no API calls.
  const sourceIsEmpty = source.trim().length === 0;
  useEffect(() => {
    if (loading) {
      document.title = "Soroban Health — Scanning…";
    } else if (result && !sourceIsEmpty) {
      document.title = `Soroban Health — ${result.health_score} | ${result.findings.length} findings`;
    } else {
      document.title = "Soroban Health";
    }
  }, [loading, result, sourceIsEmpty]);

  async function handleScan() {
    setLoading(true);
    setError(null);
    try {
      const wasmSizeBytes = wasmSizeKb.trim()
        ? Math.round(parseFloat(wasmSizeKb) * 1024)
        : undefined;
      const scan = await runScan({
        contract_id: contractId || "unregistered-snippet",
        files: { "lib.rs": source },
        wasm_size_bytes: wasmSizeBytes,
      });
      setResult(scan);

      try {
        setHistory(await getScanHistory(scan.contract_id));
      } catch {
        // A flaky history fetch shouldn't hide the scan result that just
        // succeeded — degrade to "no history shown" instead.
        setHistory([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <header className="mb-10 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Logo />
          <div>
            <p className="font-mono text-xs uppercase tracking-widest text-accent-text">
              Soroban Health
            </p>
            <h1 className="mt-0.5 text-xl font-semibold text-ink">
              Scan a Soroban contract
            </h1>
          </div>
        </div>
        <ThemeToggle />
      </header>

      <p className="-mt-6 mb-8 text-sm text-muted">
        Paste a contract ID and source to check for common anti-patterns before
        they cost you in production.
      </p>

      <section className="space-y-3">
        <div className="flex flex-col gap-3 sm:flex-row">
          <div className="flex-1">
            <label
              htmlFor="contract-id"
              className="mb-1 block font-mono text-xs uppercase tracking-wide text-muted"
            >
              Contract ID (optional)
            </label>
            <input
              id="contract-id"
              value={contractId}
              onChange={(e) => setContractId(e.target.value)}
              placeholder="CABC...XYZ"
              className="w-full rounded-md border border-line bg-surface px-3 py-2 font-mono text-sm text-ink placeholder:text-muted/60 focus:border-signal focus:outline-none focus:ring-2 focus:ring-signal/30"
            />
          </div>
          <div className="w-full sm:w-44">
            <label
              htmlFor="wasm-size"
              className="mb-1 block font-mono text-xs uppercase tracking-wide text-muted"
            >
              WASM size (KB, optional)
            </label>
            <input
              id="wasm-size"
              type="number"
              min="0"
              step="any"
              value={wasmSizeKb}
              onChange={(e) => setWasmSizeKb(e.target.value)}
              placeholder="e.g. 64"
              className="w-full rounded-md border border-line bg-surface px-3 py-2 font-mono text-sm text-ink placeholder:text-muted/60 focus:border-signal focus:outline-none focus:ring-2 focus:ring-signal/30"
            />
          </div>
          <button
            onClick={handleScan}
            disabled={loading || source.trim().length === 0}
            className="h-10 shrink-0 self-end rounded-md bg-signal px-5 text-sm font-semibold text-base transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40 sm:mt-6"
          >
            {loading ? "Scanning…" : "Run scan"}
          </button>
        </div>

        <div className="overflow-hidden rounded-md border border-line bg-surface">
          <div className="flex items-center gap-2 border-b border-line px-3 py-2">
            <span className="h-2 w-2 rounded-full bg-critical/70" />
            <span className="h-2 w-2 rounded-full bg-warn/70" />
            <span className="h-2 w-2 rounded-full bg-signal/70" />
            <label
              htmlFor="source"
              className="ml-2 font-mono text-xs uppercase tracking-wide text-muted"
            >
              lib.rs
            </label>
          </div>
          <textarea
            id="source"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            rows={10}
            spellCheck={false}
            className="w-full resize-y bg-transparent px-3 py-3 font-mono text-sm text-ink focus:outline-none"
          />
        </div>

        {error && <p className="font-mono text-sm text-critical">{error}</p>}
      </section>

      {loading ? (
        <ScanSkeleton />
      ) : result ? (
        <section className="mt-12 space-y-8">
          <HealthScoreGauge score={result.health_score} findingsSummary={result.findings_summary} />
          <div>
            <h2 className="mb-3 font-mono text-xs uppercase tracking-wide text-muted">
              Health history
            </h2>
            <HealthHistoryChart entries={history} />
          </div>
          <div>
            <h2 className="mb-3 font-mono text-xs uppercase tracking-wide text-muted">
              Findings ({result.findings.length})
            </h2>
            <FindingsList findings={result.findings} />
          </div>
        </section>
      ) : null}
    </main>
  );
}
