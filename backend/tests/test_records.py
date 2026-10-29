import pytest
from fastapi.testclient import TestClient

from backend import db
from backend.main import app


def test_list_claims(client):
    claims = client.get("/api/claims").json()
    assert len(claims) == 25
    assert claims[0] == {
        "claim_id": "CLM-1001",
        "claim_type": "trip_delay",
        "summary": "Flight home canceled by the airline, rebooked the next morning",
        "customer_name": "Maya Patel",
        "submitted_on": "2026-06-24",
        "amount_claimed": 420.0,
        "status": "waiting",
        "decision": None,
        "payout": None,
    }
    assert {claim["status"] for claim in claims} == {"waiting"}


def test_get_claim(client):
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "waiting"
    assert len(claim["items"]) == 3
    assert len(claim["documents"]) == 4
    assert claim["decision"] is None
    assert claim["payment"] is None
    assert claim["sign_off"] is None


def test_get_policy(client):
    policy = client.get("/api/policies/POL-2001").json()
    assert policy["plan"] == "premium"
    assert policy["plan_details"]["trip_delay_max"] == 800.0
    assert policy["plan_details"]["deductible"] == 50.0
    assert policy["plan_details"]["deductible_applies_to"] == [
        "baggage",
        "emergency_medical",
    ]
    assert policy["add_on_details"] == []


def test_get_policy_with_add_ons(client):
    policies = db.load("policies.json")
    with_add_on = next(p for p in policies if p["add_ons"])
    policy = client.get(f"/api/policies/{with_add_on['policy_id']}").json()
    assert [a["add_on"] for a in policy["add_on_details"]] == with_add_on["add_ons"]


def test_get_claim_history(client):
    history = client.get("/api/customers/CUS-3001/claims").json()
    assert [claim["claim_id"] for claim in history] == ["CLM-0412"]
    assert "email" not in str(history)


@pytest.mark.parametrize(
    ("url", "detail"),
    [
        ("/api/claims/CLM-9999", "No claim CLM-9999"),
        ("/api/policies/POL-9999", "No policy POL-9999"),
        ("/api/customers/CUS-9999/claims", "No customer CUS-9999"),
    ],
)
def test_not_found(client, url, detail):
    response = client.get(url)
    assert response.status_code == 404
    assert response.json() == {"detail": detail}


def test_policy_wording(client):
    wording = client.get("/api/policy-wording").json()["wording"]
    assert wording.startswith("# UnderCover Travel Insurance: Policy Wording")


def test_instructions(client):
    instructions = client.get("/api/instructions").json()["instructions"]
    assert instructions.startswith("You are the UnderCover Agent.")


def test_list_handlers(client):
    handlers = client.get("/api/handlers").json()
    assert [h["handler_id"] for h in handlers] == ["HND-01", "HND-02", "HND-03"]


def test_operations_are_documented(client):
    for methods in client.get("/openapi.json").json()["paths"].values():
        for operation in methods.values():
            assert operation["operationId"]
            assert operation["description"]
            for parameter in operation.get("parameters", []):
                assert parameter["required"]


def test_startup_seeds_a_missing_database(tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERCOVER_DB", str(tmp_path / "new.db"))
    with TestClient(app) as client:
        assert len(client.get("/api/claims").json()) == 25
    assert (tmp_path / "new.db").exists()
