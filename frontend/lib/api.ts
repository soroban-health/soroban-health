import type { ContractSummary, ScanHistoryEntry, ScanResult } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body}`);
  }

  return res.json() as Promise<T>;
}

export function listContracts(): Promise<ContractSummary[]> {
  return request<ContractSummary[]>("/contracts/");
}

export function registerContract(input: {
  contract_id: string;
  network: string;
  label?: string;
}): Promise<ContractSummary> {
  return request<ContractSummary>("/contracts/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function runScan(input: {
  contract_id: string;
  files: Record<string, string>;
  test_coverage_pct?: number;
}): Promise<ScanResult> {
  return request<ScanResult>("/scans/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getScanHistory(contractId: string): Promise<ScanHistoryEntry[]> {
  return request<ScanHistoryEntry[]>(
    `/contracts/${encodeURIComponent(contractId)}/scans`,
  );
}
