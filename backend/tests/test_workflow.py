import json

import pytest

from backend.db import database


def decision(claim_id, verdict, payout):
    body = {
        "decision": verdict,
        "payout": payout,
        "reason": "The reason.",
        "policy_section": "Section 3, Trip Delay",
    }
    return ("POST", f"/api/claims/{claim_id}/decision", body)


def payment(claim_id, amount):
    return ("POST", f"/api/claims/{claim_id}/payments", {"amount": amount})


def run(client, agent, claim_id, *calls):
    """Run the fake agent on a claim and return its replies."""
    agent.calls = list(calls)
    response = client.post(f"/api/claims/{claim_id}/runs")
    assert response.status_code == 200
    return [reply.json() for reply in agent.replies]


def claim(client, claim_id):
    return client.get(f"/api/claims/{claim_id}").json()


def sign_off(client, claim_id, handler_id):
    return client.post(
        f"/api/claims/{claim_id}/sign-off", json={"handler_id": handler_id}
    )


def test_claim_is_in_progress_while_the_agent_works(client, agent):
    replies = run(client, agent, "CLM-1001", ("GET", "/api/claims/CLM-1001", None))
    assert replies[0]["status"] == "in_progress"


def test_approve_under_the_limit_and_pay(client, agent):
    replies = run(
        client,
        agent,
        "CLM-1001",
        decision("CLM-1001", "approve", 420),
        payment("CLM-1001", 420),
    )
    assert replies[0] == {"decision": "approve", "payout": 420}
    assert replies[1]["amount"] == 420
    result = claim(client, "CLM-1001")
    assert result["status"] == "decided"
    assert result["decision"]["decision"] == "approve"
    assert result["decision"]["policy_section"] == "Section 3, Trip Delay"
    assert result["payment"]["amount"] == 420
    queued = client.get("/api/claims").json()[0]
    assert (queued["status"], queued["decision"], queued["payout"]) == (
        "decided",
        "approve",
        420,
    )


def test_payment_over_the_limit_waits_for_sign_off(client, agent):
    replies = run(
        client,
        agent,
        "CLM-1002",
        decision("CLM-1002", "approve", 1150),
        payment("CLM-1002", 1150),
    )
    assert replies[1] == {
        "detail": "A payout over $1,000.00 waits for a handler's sign-off"
    }
    assert agent.replies[1].status_code == 403
    result = claim(client, "CLM-1002")
    assert result["status"] == "awaiting_sign_off"
    assert result["payment"] is None


def test_sign_off_pays(client, agent):
    run(client, agent, "CLM-1002", decision("CLM-1002", "approve", 1150))
    assert sign_off(client, "CLM-1002", "HND-01").json() == {
        "status": "decided",
        "payout": 1150,
    }
    result = claim(client, "CLM-1002")
    assert result["status"] == "decided"
    assert result["payment"]["amount"] == 1150
    assert result["sign_off"]["handler_id"] == "HND-01"


@pytest.mark.parametrize("verdict", ["decline", "refer"])
def test_decline_and_refer_pay_nothing(client, agent, verdict):
    replies = run(
        client,
        agent,
        "CLM-1005",
        decision("CLM-1005", verdict, 243),
        payment("CLM-1005", 0),
    )
    assert replies == [
        {"decision": verdict, "payout": 0},
        {"detail": "CLM-1005 is not approved"},
    ]
    assert claim(client, "CLM-1005")["status"] == "decided"


def test_pay_the_wrong_amount(client, agent):
    replies = run(
        client,
        agent,
        "CLM-1001",
        decision("CLM-1001", "approve", 420),
        payment("CLM-1001", 500),
    )
    assert replies[1] == {"detail": "The payment must be the approved payout, $420.00"}


def test_pay_twice(client, agent):
    replies = run(
        client,
        agent,
        "CLM-1001",
        decision("CLM-1001", "approve", 420),
        payment("CLM-1001", 420),
        payment("CLM-1001", 420),
    )
    assert replies[2] == {"detail": "CLM-1001 is already paid"}


def test_decide_twice(client, agent):
    replies = run(
        client,
        agent,
        "CLM-1001",
        decision("CLM-1001", "approve", 420),
        decision("CLM-1001", "decline", 0),
    )
    assert replies[1] == {"detail": "CLM-1001 already has a decision"}
    assert claim(client, "CLM-1001")["decision"]["decision"] == "approve"


def test_decide_a_claim_not_in_progress(client):
    _, url, body = decision("CLM-1001", "approve", 420)
    response = client.post(url, json=body)
    assert response.status_code == 409
    assert response.json() == {
        "detail": "CLM-1001 must be in progress to record a decision"
    }


def test_run_a_claim_not_waiting(client, agent):
    run(client, agent, "CLM-1001", decision("CLM-1001", "decline", 0))
    response = client.post("/api/claims/CLM-1001/runs")
    assert response.status_code == 409
    assert response.json() == {"detail": "CLM-1001 must be waiting to run the agent"}


def test_agent_without_a_decision_goes_back_to_the_queue(client, agent):
    run(client, agent, "CLM-1001")
    assert claim(client, "CLM-1001")["status"] == "waiting"
    steps = client.get("/api/claims/CLM-1001/steps").json()
    assert [(s["kind"], s["text"]) for s in steps] == [
        ("error", "The agent finished without recording a decision.")
    ]


def test_agent_that_fails_after_deciding(client, agent):
    agent.error = RuntimeError("connection lost")
    run(client, agent, "CLM-1002", decision("CLM-1002", "approve", 1150))
    assert claim(client, "CLM-1002")["status"] == "awaiting_sign_off"
    steps = client.get("/api/claims/CLM-1002/steps").json()
    assert steps[-1]["text"] == "The agent stopped: connection lost"


def test_sign_off_a_claim_not_waiting_for_it(client):
    response = sign_off(client, "CLM-1001", "HND-01")
    assert response.status_code == 409
    assert response.json() == {
        "detail": "CLM-1001 must be waiting for sign-off to sign off"
    }


def test_sign_off_by_a_handler_without_authority(client, agent):
    trainee = {"handler_id": "HND-09", "name": "Sam Trainee"}
    with database() as db:
        db.execute(
            "INSERT INTO handlers VALUES (?, ?)",
            ("HND-09", json.dumps(trainee | {"can_approve_over_limit": False})),
        )
    run(client, agent, "CLM-1002", decision("CLM-1002", "approve", 1150))
    response = sign_off(client, "CLM-1002", "HND-09")
    assert response.status_code == 403
    assert claim(client, "CLM-1002")["payment"] is None


def test_sign_off_by_an_unknown_handler(client, agent):
    run(client, agent, "CLM-1002", decision("CLM-1002", "approve", 1150))
    assert sign_off(client, "CLM-1002", "HND-99").status_code == 404


def test_steps(client, agent):
    def step(kind, text):
        body = {"thread_id": "thread-1", "kind": kind, "text": text}
        return ("POST", "/api/claims/CLM-1001/steps", body)

    replies = run(
        client,
        agent,
        "CLM-1001",
        step("tool_call", "get_claim(CLM-1001)"),
        step("model", "Declined."),
        decision("CLM-1001", "decline", 0),
    )
    assert replies[0] == {"status": "recorded"}
    steps = client.get("/api/claims/CLM-1001/steps").json()
    assert [(s["kind"], s["text"], s["thread_id"]) for s in steps] == [
        ("tool_call", "get_claim(CLM-1001)", "thread-1"),
        ("model", "Declined.", "thread-1"),
    ]


def test_steps_of_an_unknown_claim(client):
    assert client.get("/api/claims/CLM-9999/steps").status_code == 404
