"use client";

import { useState } from "react";
import { HealthScoreGauge } from "@/components/HealthScoreGauge";
import { FindingsList } from "@/components/FindingsList";
import { HealthHistoryChart } from "@/components/HealthHistoryChart";
import { runScan, getScanHistory } from "@/lib/api";
import type { ScanResult, ScanHistoryEntry } from "@/lib/types";

const PLACEHOLDER_SOURCE = `pub fn withdraw(env: &Env, amount: i128) -> i128 {
    if amount <= 0 {
        panic!("amount must be positive");
    }
    BALANCE - amount
}`;

export default function Home() {
  const [contractId, setContractId] = useState("");
  const [source, setSource] = useState(PLACEHOLDER_SOURCE);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [history, setHistory] = useState<ScanHistoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleScan() {
    setLoading(true);
    setError(null);
    try {
      const scan = await runScan({
        contract_id: contractId || "unregistered-snippet",
        files: { "lib.rs": source },
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
      <header className="mb-10">
        <p className="font-mono text-xs uppercase tracking-widest text-accent">
          Soroban Health
        </p>
        <h1 className="mt-2 text-2xl font-semibold text-ink">
          Scan a Soroban contract
        </h1>
        <p className="mt-2 text-sm text-muted">
          Paste a contract ID and source to check for common anti-patterns
          before they cost you in production.
        </p>
      </header>

      <section className="space-y-4">
        <div>
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
            className="w-full rounded-md border border-line bg-surface px-3 py-2 font-mono text-sm text-ink placeholder:text-muted focus:border-accent focus:outline-none"
          />
        </div>

        <div>
          <label
            htmlFor="source"
            className="mb-1 block font-mono text-xs uppercase tracking-wide text-muted"
          >
            Rust source to scan
          </label>
          <textarea
            id="source"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            rows={10}
            className="w-full rounded-md border border-line bg-surface px-3 py-2 font-mono text-sm text-ink focus:border-accent focus:outline-none"
          />
        </div>

        <button
          onClick={handleScan}
          disabled={loading || source.trim().length === 0}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-base disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Scanning..." : "Run scan"}
        </button>

        {error && (
          <p className="font-mono text-sm severity-high">{error}</p>
        )}
      </section>

      {loading ? (
        <section className="mt-12 space-y-6 animate-pulse">
          <div className="flex items-center gap-5">
            <div className="h-32 w-32 rounded-full bg-surface border-8 border-line"></div>
            <div className="space-y-3">
              <div className="h-3 w-24 rounded bg-line"></div>
              <div className="h-5 w-32 rounded bg-line"></div>
            </div>
          </div>
          <div>
            <div className="mb-3 h-3 w-20 rounded bg-line"></div>
            <div className="h-24 rounded-lg border border-line bg-surface"></div>
          </div>
        </section>
      ) : result ? (
        <section className="mt-12 space-y-6">
          <HealthScoreGauge score={result.health_score} />
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
