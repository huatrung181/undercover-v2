import json

import pytest

from backend.db import database


def start(client, claim_id):
    return client.post(f"/api/claims/{claim_id}/runs").json()["thread_id"]


def decide(client, claim_id, decision, payout):
    return client.post(
        f"/api/claims/{claim_id}/decision",
        json={
            "decision": decision,
            "payout": payout,
            "reason": "The reason.",
            "policy_section": "Section 3, Trip Delay",
        },
    )


def pay(client, claim_id, amount):
    return client.post(f"/api/claims/{claim_id}/payments", json={"amount": amount})


def sign_off(client, claim_id, handler_id):
    return client.post(
        f"/api/claims/{claim_id}/sign-off", json={"handler_id": handler_id}
    )


def test_run_agent(client):
    thread_id = start(client, "CLM-1001")
    assert thread_id.startswith("CLM-1001-")
    assert client.get("/api/claims/CLM-1001").json()["status"] == "in_progress"


def test_approve_under_the_limit_and_pay(client):
    start(client, "CLM-1001")
    assert decide(client, "CLM-1001", "approve", 420).json() == {
        "status": "decided",
        "payout": 420,
    }
    assert pay(client, "CLM-1001", 420).json()["amount"] == 420
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "decided"
    assert claim["decision"]["decision"] == "approve"
    assert claim["decision"]["policy_section"] == "Section 3, Trip Delay"
    assert claim["payment"]["amount"] == 420
    queued = client.get("/api/claims").json()[0]
    assert (queued["decision"], queued["payout"]) == ("approve", 420)


def test_approve_over_the_limit_waits_for_sign_off(client):
    start(client, "CLM-1002")
    assert decide(client, "CLM-1002", "approve", 1150).json() == {
        "status": "awaiting_sign_off",
        "payout": 1150,
    }
    response = pay(client, "CLM-1002", 1150)
    assert response.status_code == 403
    assert response.json() == {
        "detail": "A payout over $1,000.00 waits for a handler's sign-off"
    }
    claim = client.get("/api/claims/CLM-1002").json()
    assert claim["status"] == "awaiting_sign_off"
    assert claim["payment"] is None


def test_sign_off_pays(client):
    start(client, "CLM-1002")
    decide(client, "CLM-1002", "approve", 1150)
    assert sign_off(client, "CLM-1002", "HND-01").json() == {
        "status": "decided",
        "payout": 1150,
    }
    claim = client.get("/api/claims/CLM-1002").json()
    assert claim["status"] == "decided"
    assert claim["payment"]["amount"] == 1150
    assert claim["sign_off"]["handler_id"] == "HND-01"


@pytest.mark.parametrize("decision", ["decline", "refer"])
def test_decline_and_refer_pay_nothing(client, decision):
    start(client, "CLM-1005")
    assert decide(client, "CLM-1005", decision, 243).json() == {
        "status": "decided",
        "payout": 0,
    }
    response = pay(client, "CLM-1005", 0)
    assert response.status_code == 409
    assert response.json() == {"detail": "CLM-1005 is not approved"}


def test_pay_the_wrong_amount(client):
    start(client, "CLM-1001")
    decide(client, "CLM-1001", "approve", 420)
    response = pay(client, "CLM-1001", 500)
    assert response.status_code == 409
    assert response.json() == {
        "detail": "The payment must be the approved payout, $420.00"
    }


def test_pay_twice(client):
    start(client, "CLM-1001")
    decide(client, "CLM-1001", "approve", 420)
    pay(client, "CLM-1001", 420)
    response = pay(client, "CLM-1001", 420)
    assert response.status_code == 409
    assert response.json() == {"detail": "CLM-1001 is already paid"}


def test_decide_a_claim_not_in_progress(client):
    response = decide(client, "CLM-1001", "approve", 420)
    assert response.status_code == 409
    assert response.json() == {
        "detail": "CLM-1001 must be in progress to record a decision"
    }


def test_run_a_claim_not_waiting(client):
    start(client, "CLM-1001")
    response = client.post("/api/claims/CLM-1001/runs")
    assert response.status_code == 409
    assert response.json() == {"detail": "CLM-1001 must be waiting to run the agent"}


def test_sign_off_a_claim_not_waiting_for_it(client):
    response = sign_off(client, "CLM-1001", "HND-01")
    assert response.status_code == 409
    assert response.json() == {
        "detail": "CLM-1001 must be waiting for sign-off to sign off"
    }


def test_sign_off_by_a_handler_without_authority(client):
    trainee = {"handler_id": "HND-09", "name": "Sam Trainee"}
    with database() as db:
        db.execute(
            "INSERT INTO handlers VALUES (?, ?)",
            ("HND-09", json.dumps(trainee | {"can_approve_over_limit": False})),
        )
    start(client, "CLM-1002")
    decide(client, "CLM-1002", "approve", 1150)
    response = sign_off(client, "CLM-1002", "HND-09")
    assert response.status_code == 403
    assert client.get("/api/claims/CLM-1002").json()["payment"] is None


def test_sign_off_by_an_unknown_handler(client):
    start(client, "CLM-1002")
    decide(client, "CLM-1002", "approve", 1150)
    assert sign_off(client, "CLM-1002", "HND-99").status_code == 404


def test_steps(client):
    thread_id = start(client, "CLM-1001")
    for kind, text in [("tool_call", "get_claim(CLM-1001)"), ("model", "Approved.")]:
        response = client.post(
            "/api/claims/CLM-1001/steps",
            json={"thread_id": thread_id, "kind": kind, "text": text},
        )
        assert response.json() == {"status": "recorded"}
    steps = client.get("/api/claims/CLM-1001/steps").json()
    assert [(s["kind"], s["text"]) for s in steps] == [
        ("tool_call", "get_claim(CLM-1001)"),
        ("model", "Approved."),
    ]
    assert steps[0]["thread_id"] == thread_id


def test_steps_of_an_unknown_claim(client):
    assert client.get("/api/claims/CLM-9999/steps").status_code == 404
