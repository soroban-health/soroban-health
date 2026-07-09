-- Soroban Health — Supabase Postgres schema.
--
-- Flat, idempotent DDL. Apply manually via the Supabase SQL editor or
-- `psql "$SUPABASE_DB_URL" -f schema.sql`. No migration tooling (Supabase
-- CLI / supabase/migrations) is adopted yet — this single file is the
-- source of truth for v0.

create extension if not exists pgcrypto;

-- The backend connects using the service_role key (a trusted server-side
-- caller), so Row Level Security is intentionally left disabled on these
-- tables for v0.

create table if not exists contracts (
  contract_id text primary key,
  network text not null default 'testnet',
  label text,
  latest_health_score double precision,
  last_scanned_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists scans (
  id uuid primary key default gen_random_uuid(),
  contract_id text not null references contracts(contract_id) on delete cascade,
  health_score double precision not null,
  test_coverage_pct double precision,
  scanned_at timestamptz not null default now()
);

create table if not exists findings (
  id uuid primary key default gen_random_uuid(),
  scan_id uuid not null references scans(id) on delete cascade,
  type text not null check (type in (
    'unbounded_storage_growth', 'bare_panic_used',
    'missing_ttl_extension', 'dependency_version_drift'
  )),
  severity text not null check (severity in ('low', 'medium', 'high')),
  file text not null,
  line integer not null,
  message text not null
);

create index if not exists idx_scans_contract_id_scanned_at
  on scans(contract_id, scanned_at desc);
create index if not exists idx_findings_scan_id on findings(scan_id);
