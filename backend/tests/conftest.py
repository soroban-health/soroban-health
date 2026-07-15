"""Shared pytest fixtures.

`FakeSupabaseClient` is a minimal hand-rolled test double implementing only
the chainable calls `ContractRepository` actually uses (`.table()`,
`.insert()`, `.upsert()`, `.select()`, `.eq()`, `.order()`, `.execute()` ->
`.data`), backed by an in-memory `dict[str, list[dict]]`. It lets `ContractRepository`'s
own query-building logic run for real in tests, with the network boundary
(`get_supabase_client`) faked via `app.dependency_overrides` — so CI needs no
real Supabase credentials.

`FakeSorobanServer` is the equivalent double for the RPC boundary, covering
only the three `stellar_sdk.SorobanServer` calls `app.services.rpc` uses
(`get_contract_info`, `get_latest_ledger`, `get_transactions`), swapped in
via `get_soroban_server`.

`_make_tarball` builds a real gzip tar archive in memory, shaped exactly
like GitHub's tarball-endpoint response (a single top-level
"<owner>-<repo>-<sha>/" directory wrapping the repo contents), so
`app.services.github_fetch`'s real extraction logic is exercised in tests
against a real archive, not a mocked one.
"""

import io
import tarfile
import uuid

import pytest
from fastapi.testclient import TestClient
from stellar_sdk import exceptions as stellar_exceptions

from app.main import app
from app.services.soroban_client import get_soroban_server
from app.services.supabase_client import get_supabase_client


def _make_tarball(
    files: dict[str, bytes], top_level: str = "owner-repo-abc123"
) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(f"{top_level}/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


class _FakeResponse:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _FakeQuery:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def eq(self, column: str, value) -> "_FakeQuery":
        self._rows = [row for row in self._rows if row.get(column) == value]
        return self

    def order(self, column: str, *, desc: bool = False) -> "_FakeQuery":
        # Mirrors postgrest-py's order(column, *, desc=False). Sorting ISO-8601
        # strings lexicographically only matches chronological order because
        # every timestamp here is fixed-offset UTC (see scans.py) — this would
        # not hold for mixed offsets or a "Z" suffix.
        self._rows = sorted(
            self._rows, key=lambda row: row.get(column) or "", reverse=desc
        )
        return self

    def execute(self) -> _FakeResponse:
        return _FakeResponse(self._rows)


# Mirrors the column defaults declared in `supabase/schema.sql` for tables
# where a row can be created with a partial payload (contracts, via the
# upsert path in `record_scan`) — real Postgres would fill these in.
_TABLE_DEFAULTS: dict[str, dict] = {
    "contracts": {
        "network": "testnet",
        "label": None,
        "latest_health_score": None,
        "last_scanned_at": None,
    },
}


class _FakeTable:
    def __init__(self, store: dict[str, list[dict]], name: str) -> None:
        self._store = store
        self._name = name
        self._store.setdefault(name, [])

    def _new_row(self, payload: dict) -> dict:
        row = {**_TABLE_DEFAULTS.get(self._name, {}), **payload}
        row.setdefault("id", str(uuid.uuid4()))
        return row

    def insert(self, payload: dict | list[dict]) -> _FakeQuery:
        rows = payload if isinstance(payload, list) else [payload]
        inserted = []
        for row in rows:
            new_row = self._new_row(row)
            self._store[self._name].append(new_row)
            inserted.append(new_row)
        return _FakeQuery(inserted)

    def upsert(
        self, payload: dict | list[dict], on_conflict: str | None = None
    ) -> _FakeQuery:
        rows = payload if isinstance(payload, list) else [payload]
        upserted = []
        for row in rows:
            existing = None
            if on_conflict:
                existing = next(
                    (
                        r
                        for r in self._store[self._name]
                        if r.get(on_conflict) == row.get(on_conflict)
                    ),
                    None,
                )
            if existing is not None:
                existing.update(row)
                upserted.append(existing)
            else:
                new_row = self._new_row(row)
                self._store[self._name].append(new_row)
                upserted.append(new_row)
        return _FakeQuery(upserted)

    def select(self, *columns: str) -> _FakeQuery:
        return _FakeQuery(list(self._store[self._name]))


class FakeSupabaseClient:
    def __init__(self) -> None:
        self._store: dict[str, list[dict]] = {}

    def table(self, name: str) -> _FakeTable:
        return _FakeTable(self._store, name)


@pytest.fixture
def fake_client() -> FakeSupabaseClient:
    return FakeSupabaseClient()


class _FakeLatestLedger:
    def __init__(self, sequence: int) -> None:
        self.sequence = sequence


class _FakeTransactionsPage:
    def __init__(self, transactions: list, cursor: str = "") -> None:
        self.transactions = transactions
        self.cursor = cursor


class FakeSorobanServer:
    """Minimal double for the three SorobanServer calls app/services/rpc.py
    uses. `pages` is consumed one per `get_transactions` call, in order,
    regardless of the `start_ledger`/`cursor` passed — good enough to test
    pagination-stopping logic without modeling real cursor semantics."""

    def __init__(
        self,
        *,
        deployed: bool = True,
        pages: list[_FakeTransactionsPage] | None = None,
        latest_ledger: int = 100_000,
    ) -> None:
        self._deployed = deployed
        self._pages = list(pages or [])
        self._latest_ledger = latest_ledger
        self._page_index = 0

    def get_contract_info(self, contract_id: str):
        if not self._deployed:
            raise stellar_exceptions.ContractInstanceNotFoundError(
                f"Contract instance ledger entry was not found: {contract_id}."
            )
        return object()

    def get_latest_ledger(self) -> _FakeLatestLedger:
        return _FakeLatestLedger(self._latest_ledger)

    def get_transactions(self, *, start_ledger=None, cursor=None, limit=None):
        if self._page_index >= len(self._pages):
            return _FakeTransactionsPage([])
        page = self._pages[self._page_index]
        self._page_index += 1
        return page


@pytest.fixture
def fake_soroban_server() -> FakeSorobanServer:
    return FakeSorobanServer(pages=[])


@pytest.fixture
def client(
    fake_client: FakeSupabaseClient, fake_soroban_server: FakeSorobanServer
) -> TestClient:
    app.dependency_overrides[get_supabase_client] = lambda: fake_client
    app.dependency_overrides[get_soroban_server] = lambda: fake_soroban_server
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
