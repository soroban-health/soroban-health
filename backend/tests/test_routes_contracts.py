"""Route tests for /contracts/, exercised against the fake Supabase client."""

GOOD_SOURCE = """
pub fn safe_add(a: i128, b: i128) -> i128 {
    a + b
}
"""

BAD_SOURCE = """
pub fn bad_unchecked_withdraw(_env: &Env, amount: i128) -> i128 {
    if amount <= 0 {
        panic!("amount must be positive");
    }
    BALANCE - amount
}
"""

VALID_CONTRACT_ID_1 = "CAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
VALID_CONTRACT_ID_2 = "CBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"


def test_register_contract_returns_201(client):
    response = client.post(
        "/contracts/",
        json={
            "contract_id": VALID_CONTRACT_ID_1,
            "network": "testnet",
            "label": "Demo",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["contract_id"] == VALID_CONTRACT_ID_1
    assert body["label"] == "Demo"


def test_register_duplicate_contract_returns_409(client):
    client.post("/contracts/", json={"contract_id": VALID_CONTRACT_ID_1})
    response = client.post("/contracts/", json={"contract_id": VALID_CONTRACT_ID_1})
    assert response.status_code == 409


def test_list_contracts_returns_registered_contracts(client):
    client.post("/contracts/", json={"contract_id": VALID_CONTRACT_ID_1})
    client.post("/contracts/", json={"contract_id": VALID_CONTRACT_ID_2})
    response = client.get("/contracts/")
    assert response.status_code == 200
    contract_ids = {c["contract_id"] for c in response.json()}
    assert contract_ids == {VALID_CONTRACT_ID_1, VALID_CONTRACT_ID_2}


def test_get_contract_returns_404_when_missing(client):
    response = client.get("/contracts/does-not-exist")
    assert response.status_code == 404


def test_get_contract_returns_registered_contract(client):
    client.post("/contracts/", json={"contract_id": VALID_CONTRACT_ID_1})
    response = client.get(f"/contracts/{VALID_CONTRACT_ID_1}")
    assert response.status_code == 200
    assert response.json()["contract_id"] == VALID_CONTRACT_ID_1


def test_register_contract_rejects_invalid_contract_id(client):
    response = client.post("/contracts/", json={"contract_id": "C123"})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail[0]["msg"] == (
        "Value error, contract_id must be a Stellar contract address "
        "(56 chars, starts with 'C', and uses A-Z2-7)"
    )


def test_get_contract_scan_history_returns_ascending_scores(client):
    client.post(
        "/scans/", json={"contract_id": "C123", "files": {"lib.rs": GOOD_SOURCE}}
    )
    client.post(
        "/scans/", json={"contract_id": "C123", "files": {"lib.rs": BAD_SOURCE}}
    )

    response = client.get("/contracts/C123/scans")
    assert response.status_code == 200
    history = response.json()
    assert len(history) == 2
    assert history[0]["scanned_at"] <= history[1]["scanned_at"]


def test_get_contract_scan_history_returns_empty_for_unscanned_contract(client):
    response = client.get("/contracts/does-not-exist/scans")
    assert response.status_code == 200
    assert response.json() == []
