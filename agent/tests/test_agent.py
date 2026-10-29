import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent import __main__ as cli
from agent import main
from backend.db import seed
from backend.main import app


class StubModel(GenericFakeChatModel):
    """A chat model that gives scripted replies in place of a real model."""

    def bind_tools(self, tools, **kwargs):
        return self


def tool_calls(*calls):
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": args, "id": str(i)}
            for i, (name, args) in enumerate(calls)
        ],
    )


def decision(claim_id, verdict, payout):
    return (
        "record_decision",
        {
            "claim_id": claim_id,
            "decision": verdict,
            "payout": payout,
            "reason": "The reason.",
            "policy_section": "Section 3, Trip Delay",
        },
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A backend on a fresh database that the agent reaches through its API."""
    monkeypatch.setenv("UNDERCOVER_DB", str(tmp_path / "test.db"))
    seed()
    monkeypatch.setattr(main, "backend", lambda: TestClient(app))
    return TestClient(app)


def script(monkeypatch, *replies):
    monkeypatch.setattr(main, "model", lambda: StubModel(messages=iter(replies)))


def test_approve_and_pay(client, monkeypatch):
    script(
        monkeypatch,
        tool_calls(
            ("get_claim", {"claim_id": "CLM-1001"}),
            ("get_policy", {"policy_id": "POL-2001"}),
            ("get_claim_history", {"customer_id": "CUS-3001"}),
            ("get_policy_wording", {}),
        ),
        tool_calls(decision("CLM-1001", "approve", 420)),
        tool_calls(("pay_claim", {"claim_id": "CLM-1001", "amount": 420})),
        AIMessage(content="Approved and paid $420.00."),
    )
    client.post("/api/claims/CLM-1001/runs")
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "decided"
    assert claim["decision"]["payout"] == 420
    assert claim["payment"]["amount"] == 420
    steps = client.get("/api/claims/CLM-1001/steps").json()
    kinds = [step["kind"] for step in steps]
    assert kinds.count("tool_call") == 6
    assert kinds.count("tool_result") == 6
    assert steps[0]["text"] == 'get_claim({"claim_id": "CLM-1001"})'
    assert (steps[-1]["kind"], steps[-1]["text"]) == (
        "model",
        "Approved and paid $420.00.",
    )
    wording = next(s for s in steps if s["text"].startswith("get_policy_wording: "))
    assert wording["text"].endswith(" characters)")


def test_payment_over_the_limit_waits_for_sign_off(client, monkeypatch):
    script(
        monkeypatch,
        tool_calls(decision("CLM-1003", "approve", 3800)),
        tool_calls(("pay_claim", {"claim_id": "CLM-1003", "amount": 3800})),
        AIMessage(content="Approved. The payment waits for sign-off."),
    )
    client.post("/api/claims/CLM-1003/runs")
    claim = client.get("/api/claims/CLM-1003").json()
    assert claim["status"] == "awaiting_sign_off"
    assert claim["payment"] is None
    texts = [step["text"] for step in client.get("/api/claims/CLM-1003/steps").json()]
    refusal = "Refused (403): A payout over $1,000.00 waits for a handler's sign-off"
    assert f"pay_claim: {refusal}" in texts


def test_agent_that_fails(client, monkeypatch):
    def broken_model():
        raise RuntimeError("no model")

    monkeypatch.setattr(main, "model", broken_model)
    client.post("/api/claims/CLM-1001/runs")
    assert client.get("/api/claims/CLM-1001").json()["status"] == "waiting"
    steps = client.get("/api/claims/CLM-1001/steps").json()
    assert [(s["kind"], s["text"]) for s in steps] == [
        ("error", "The agent stopped: no model")
    ]


def test_agent_that_finishes_without_a_decision(client, monkeypatch):
    script(monkeypatch, AIMessage(content="I am not sure."))
    client.post("/api/claims/CLM-1001/runs")
    assert client.get("/api/claims/CLM-1001").json()["status"] == "waiting"
    assert client.get("/api/claims/CLM-1001/steps").json()[-1]["text"] == (
        "The agent finished without recording a decision."
    )


def test_steps_of_other_messages():
    assert main.steps(HumanMessage(content="Hello")) == []
    assert main.steps(
        ToolMessage(content="ok", name="pay_claim", tool_call_id="1")
    ) == [("tool_result", "pay_claim: ok")]


def test_cli(client, monkeypatch, capsys):
    script(
        monkeypatch,
        tool_calls(decision("CLM-1001", "decline", 0)),
        AIMessage(content="Declined."),
    )
    monkeypatch.setattr(cli, "backend", lambda: TestClient(app))
    cli.main("CLM-1001")
    output = capsys.readouterr().out
    assert "[tool_call] record_decision(" in output
    assert "Status: decided" in output
    assert "Decision: decline, $0.00" in output


def test_model_name(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("MODEL_NAME", raising=False)
    assert main.model().model_name == "openai/gpt-6-luna"
    monkeypatch.setenv("MODEL_NAME", "openrouter/free")
    assert main.model().model_name == "openrouter/free"
