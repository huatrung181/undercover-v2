"""The UnderCover Agent."""

import json
import os
from typing import Any, Literal

import httpx
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

load_dotenv(override=True)

BACKEND_URL = "http://localhost:8000"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-6-luna"
PREVIEW_LENGTH = 300


def backend() -> httpx.Client:
    """Return a client for the UnderCover backend."""
    return httpx.Client(base_url=BACKEND_URL, timeout=30)


def call(method: str, url: str, body: dict[str, Any] | None = None) -> str:
    """Call the backend and return its reply, or why it refused."""
    with backend() as client:
        response = client.request(method, url, json=body)
    if response.is_client_error:
        return f"Refused ({response.status_code}): {response.json()['detail']}"
    response.raise_for_status()
    return response.text


@tool
def get_claim(claim_id: str) -> str:
    """Get a claim: the customer's story, the items claimed and the documents."""
    return call("GET", f"/api/claims/{claim_id}")


@tool
def get_policy(policy_id: str) -> str:
    """Get a policy with its plan's limits, its add-ons, the trip and the travelers."""
    return call("GET", f"/api/policies/{policy_id}")


@tool
def get_claim_history(customer_id: str) -> str:
    """Get a customer's earlier claims."""
    return call("GET", f"/api/customers/{customer_id}/claims")


@tool
def get_policy_wording() -> str:
    """Get the policy wording, the contract that every decision must follow."""
    return json.loads(call("GET", "/api/policy-wording"))["wording"]


@tool
def record_decision(
    claim_id: str,
    decision: Literal["approve", "decline", "refer"],
    payout: float,
    reason: str,
    policy_section: str,
) -> str:
    """Record the decision on a claim, with the payout in US dollars (0 unless
    approved), a reason of two or three sentences and the policy section."""
    return call(
        "POST",
        f"/api/claims/{claim_id}/decision",
        {
            "decision": decision,
            "payout": payout,
            "reason": reason,
            "policy_section": policy_section,
        },
    )


@tool
def pay_claim(claim_id: str, amount: float) -> str:
    """Pay an approved claim its payout in US dollars."""
    return call("POST", f"/api/claims/{claim_id}/payments", {"amount": amount})


TOOLS = [
    get_claim,
    get_policy,
    get_claim_history,
    get_policy_wording,
    record_decision,
    pay_claim,
]


def model() -> ChatOpenAI:
    """Return the model named in MODEL_NAME, or GPT-6 Luna by default."""
    name = os.getenv("MODEL_NAME")
    return ChatOpenAI(
        model=name or DEFAULT_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        reasoning_effort=None if name else "low",
    )


def preview(text: str) -> str:
    """Shorten a long text for the steps."""
    if len(text) <= PREVIEW_LENGTH:
        return text
    return f"{text[:PREVIEW_LENGTH]}... ({len(text):,} characters)"


def steps(message: AnyMessage) -> list[tuple[str, str]]:
    """Describe a message from the agent as steps: (kind, text)."""
    if isinstance(message, ToolMessage):
        return [("tool_result", f"{message.name}: {preview(message.text)}")]
    if not isinstance(message, AIMessage):
        return []
    text = str(message.text)
    described = [("model", text)] if text else []
    for call_ in message.tool_calls:
        described.append(("tool_call", f"{call_['name']}({json.dumps(call_['args'])})"))
    return described


def run(claim_id: str, thread_id: str) -> str:
    """Run the agent on one claim, recording each step, and return its final reply."""
    with backend() as client:
        response = client.get("/api/instructions").raise_for_status()
    agent = create_agent(
        model(), tools=TOOLS, system_prompt=response.json()["instructions"]
    )
    reply = ""
    for update in agent.stream(
        {"messages": [{"role": "user", "content": f"Please decide claim {claim_id}."}]},
        config={"configurable": {"thread_id": thread_id}},
        stream_mode="updates",
    ):
        for state in update.values():
            for message in state["messages"]:
                for kind, text in steps(message):
                    call(
                        "POST",
                        f"/api/claims/{claim_id}/steps",
                        {"thread_id": thread_id, "kind": kind, "text": text},
                    )
                if isinstance(message, AIMessage):
                    reply = message.text
    return reply
