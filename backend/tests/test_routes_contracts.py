"""Route tests for /contracts/, exercised against the fake Supabase client."""


def test_register_contract_returns_201(client):
    response = client.post(
        "/contracts/",
        json={"contract_id": "C123", "network": "testnet", "label": "Demo"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["contract_id"] == "C123"
    assert body["label"] == "Demo"


def test_register_duplicate_contract_returns_409(client):
    client.post("/contracts/", json={"contract_id": "C123"})
    response = client.post("/contracts/", json={"contract_id": "C123"})
    assert response.status_code == 409


def test_list_contracts_returns_registered_contracts(client):
    client.post("/contracts/", json={"contract_id": "C1"})
    client.post("/contracts/", json={"contract_id": "C2"})
    response = client.get("/contracts/")
    assert response.status_code == 200
    contract_ids = {c["contract_id"] for c in response.json()}
    assert contract_ids == {"C1", "C2"}


def test_get_contract_returns_404_when_missing(client):
    response = client.get("/contracts/does-not-exist")
    assert response.status_code == 404


def test_get_contract_returns_registered_contract(client):
    client.post("/contracts/", json={"contract_id": "C123"})
    response = client.get("/contracts/C123")
    assert response.status_code == 200
    assert response.json()["contract_id"] == "C123"
