"""Shared pytest fixtures.

`FakeSupabaseClient` is a minimal hand-rolled test double implementing only
the chainable calls `ContractRepository` actually uses (`.table()`,
`.insert()`, `.upsert()`, `.select()`, `.eq()`, `.execute()` -> `.data`),
backed by an in-memory `dict[str, list[dict]]`. It lets `ContractRepository`'s
own query-building logic run for real in tests, with the network boundary
(`get_supabase_client`) faked via `app.dependency_overrides` — so CI needs no
real Supabase credentials.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.supabase_client import get_supabase_client


class _FakeResponse:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _FakeQuery:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def eq(self, column: str, value) -> "_FakeQuery":
        self._rows = [row for row in self._rows if row.get(column) == value]
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


@pytest.fixture
def client(fake_client: FakeSupabaseClient) -> TestClient:
    app.dependency_overrides[get_supabase_client] = lambda: fake_client
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
