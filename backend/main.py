"""The UnderCover backend."""

import json
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent.main import run as run_claim
from backend.db import DATA, database, load, path, seed

INSTRUCTIONS = Path(__file__).parent / "instructions.md"
POLICY_WORDING = (DATA / "policy_wording.md").read_text(encoding="utf-8")
APPROVAL_LIMIT: float = load("company.json")["payout_approval_limit"]
STATUS_LABELS = {
    "waiting": "waiting",
    "in_progress": "in progress",
    "awaiting_sign_off": "waiting for sign-off",
    "decided": "decided",
}


class Decision(BaseModel):
    decision: Literal["approve", "decline", "refer"]
    payout: Annotated[float, Field(ge=0)]
    reason: str
    policy_section: str


class Payment(BaseModel):
    amount: float


class SignOff(BaseModel):
    handler_id: str


class Step(BaseModel):
    thread_id: str
    kind: Literal["model", "tool_call", "tool_result", "error"]
    text: str


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if not path().exists():
        seed()
    yield


app = FastAPI(title="UnderCover", lifespan=lifespan)


def record(db: sqlite3.Connection, table: str, key: str, value: str) -> dict[str, Any]:
    """Return one reference record, or raise a 404."""
    row = db.execute(
        f"SELECT data FROM {table} WHERE {key} = ?",  # noqa: S608
        (value,),
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"No {key.removesuffix('_id')} {value}")
    return json.loads(row["data"])


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def money(amount: float) -> str:
    return f"${amount:,.2f}"


def status_of(db: sqlite3.Connection, claim_id: str) -> str:
    """Return a claim's status, or raise a 404."""
    row = db.execute(
        "SELECT status FROM claims WHERE claim_id = ?", (claim_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"No claim {claim_id}")
    return row["status"]


def require_status(
    db: sqlite3.Connection, claim_id: str, status: str, action: str
) -> None:
    """Raise a 409 unless the claim has the status the action needs."""
    if status_of(db, claim_id) != status:
        raise HTTPException(
            409, f"{claim_id} must be {STATUS_LABELS[status]} to {action}"
        )


def set_status(db: sqlite3.Connection, claim_id: str, status: str) -> None:
    db.execute("UPDATE claims SET status = ? WHERE claim_id = ?", (status, claim_id))


def add_step(
    db: sqlite3.Connection, claim_id: str, thread_id: str, kind: str, text: str
) -> None:
    db.execute(
        "INSERT INTO steps (claim_id, thread_id, kind, text, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (claim_id, thread_id, kind, text, now()),
    )


def work(claim_id: str, thread_id: str) -> None:
    """Run the agent on a claim, then settle the claim's status from its decision,
    or put it back in the queue if there is none."""
    problem = None
    try:
        run_claim(claim_id, thread_id)
    except Exception as error:
        problem = f"The agent stopped: {error}"
    with database() as db:
        decision = optional_row(db, "decisions", claim_id)
        if decision is None:
            problem = problem or "The agent finished without recording a decision."
            status = "waiting"
        elif decision["payout"] > APPROVAL_LIMIT:
            status = "awaiting_sign_off"
        else:
            status = "decided"
        if problem:
            add_step(db, claim_id, thread_id, "error", problem)
        set_status(db, claim_id, status)


def optional_row(db: sqlite3.Connection, table: str, claim_id: str) -> Any:
    """Return a claim's row in a table as a dict, or None."""
    row = db.execute(
        f"SELECT * FROM {table} WHERE claim_id = ?",  # noqa: S608
        (claim_id,),
    ).fetchone()
    if row is None:
        return None
    data = dict(row)
    del data["claim_id"]
    return data


@app.get("/api/health", operation_id="health")
def health() -> dict[str, str]:
    """Check that the backend is running."""
    return {"status": "ok"}


@app.get("/api/claims", operation_id="list_claims")
def list_claims() -> list[dict[str, Any]]:
    """List the claims queue with each claim's status and decision."""
    with database() as db:
        rows = db.execute(
            """SELECT c.status, c.data, json_extract(u.data, '$.name') AS customer,
                      d.decision, d.payout
               FROM claims c
               JOIN customers u ON u.customer_id = c.customer_id
               LEFT JOIN decisions d ON d.claim_id = c.claim_id
               ORDER BY c.claim_id"""
        ).fetchall()
    claims = []
    for row in rows:
        data = json.loads(row["data"])
        claims.append(
            {
                "claim_id": data["claim_id"],
                "claim_type": data["claim_type"],
                "summary": data["summary"],
                "customer_name": row["customer"],
                "submitted_on": data["submitted_on"],
                "amount_claimed": data["amount_claimed"],
                "status": row["status"],
                "decision": row["decision"],
                "payout": row["payout"],
            }
        )
    return claims


@app.get("/api/claims/{claim_id}", operation_id="get_claim")
def get_claim(claim_id: str) -> dict[str, Any]:
    """Get a claim in full, with its decision, payment and sign-off."""
    with database() as db:
        return record(db, "claims", "claim_id", claim_id) | {
            "status": status_of(db, claim_id),
            "decision": optional_row(db, "decisions", claim_id),
            "payment": optional_row(db, "payments", claim_id),
            "sign_off": optional_row(db, "sign_offs", claim_id),
        }


@app.get("/api/policies/{policy_id}", operation_id="get_policy")
def get_policy(policy_id: str) -> dict[str, Any]:
    """Get a policy with its plan's limits and its add-ons."""
    with database() as db:
        policy = record(db, "policies", "policy_id", policy_id)
        return policy | {
            "plan_details": record(db, "plans", "plan", policy["plan"]),
            "add_on_details": [
                record(db, "add_ons", "add_on", add_on) for add_on in policy["add_ons"]
            ],
        }


@app.get("/api/customers/{customer_id}/claims", operation_id="get_claim_history")
def get_claim_history(customer_id: str) -> list[dict[str, Any]]:
    """Get a customer's earlier claims."""
    with database() as db:
        return record(db, "customers", "customer_id", customer_id)["previous_claims"]


@app.get("/api/policy-wording", operation_id="get_policy_wording")
def get_policy_wording() -> dict[str, str]:
    """Get the policy wording, the contract with the customer."""
    return {"wording": POLICY_WORDING}


@app.get("/api/instructions", operation_id="get_instructions")
def get_instructions() -> dict[str, str]:
    """Get the UnderCover Agent's instructions."""
    return {"instructions": INSTRUCTIONS.read_text(encoding="utf-8")}


@app.get("/api/handlers", operation_id="list_handlers")
def list_handlers() -> list[dict[str, Any]]:
    """List the claims handlers."""
    with database() as db:
        rows = db.execute("SELECT data FROM handlers ORDER BY handler_id").fetchall()
    return [json.loads(row["data"]) for row in rows]


@app.post("/api/claims/{claim_id}/runs", operation_id="run_agent")
def run_agent(claim_id: str, background_tasks: BackgroundTasks) -> dict[str, str]:
    """Start the UnderCover Agent on a waiting claim."""
    thread_id = f"{claim_id}-{uuid4().hex[:8]}"
    with database() as db:
        require_status(db, claim_id, "waiting", "run the agent")
        set_status(db, claim_id, "in_progress")
    background_tasks.add_task(work, claim_id, thread_id)
    return {"thread_id": thread_id}


@app.get("/api/claims/{claim_id}/steps", operation_id="list_steps")
def list_steps(claim_id: str) -> list[dict[str, Any]]:
    """List the agent's steps on a claim, oldest first."""
    with database() as db:
        status_of(db, claim_id)
        rows = db.execute(
            "SELECT id, thread_id, kind, text, created_at FROM steps"
            " WHERE claim_id = ? ORDER BY id",
            (claim_id,),
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/claims/{claim_id}/steps", operation_id="record_step")
def record_step(claim_id: str, step: Step) -> dict[str, str]:
    """Record a step the agent took on a claim."""
    with database() as db:
        status_of(db, claim_id)
        add_step(db, claim_id, step.thread_id, step.kind, step.text)
    return {"status": "recorded"}


@app.post("/api/claims/{claim_id}/decision", operation_id="record_decision")
def record_decision(claim_id: str, decision: Decision) -> dict[str, Any]:
    """Record the decision on a claim the agent is working on."""
    payout = decision.payout if decision.decision == "approve" else 0
    with database() as db:
        require_status(db, claim_id, "in_progress", "record a decision")
        if optional_row(db, "decisions", claim_id) is not None:
            raise HTTPException(409, f"{claim_id} already has a decision")
        db.execute(
            "INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?)",
            (
                claim_id,
                decision.decision,
                payout,
                decision.reason,
                decision.policy_section,
                now(),
            ),
        )
    return {"decision": decision.decision, "payout": payout}


@app.post("/api/claims/{claim_id}/payments", operation_id="pay_claim")
def pay_claim(claim_id: str, payment: Payment) -> dict[str, Any]:
    """Pay an approved claim its payout."""
    with database() as db:
        status_of(db, claim_id)
        decision = optional_row(db, "decisions", claim_id)
        if decision is None or decision["decision"] != "approve":
            raise HTTPException(409, f"{claim_id} is not approved")
        if optional_row(db, "payments", claim_id) is not None:
            raise HTTPException(409, f"{claim_id} is already paid")
        if round(payment.amount, 2) != round(decision["payout"], 2):
            raise HTTPException(
                409,
                f"The payment must be the approved payout, {money(decision['payout'])}",
            )
        if (
            payment.amount > APPROVAL_LIMIT
            and optional_row(db, "sign_offs", claim_id) is None
        ):
            raise HTTPException(
                403,
                f"A payout over {money(APPROVAL_LIMIT)} waits for a handler's sign-off",
            )
        paid_at = now()
        db.execute(
            "INSERT INTO payments VALUES (?, ?, ?)", (claim_id, payment.amount, paid_at)
        )
    return {"amount": payment.amount, "paid_at": paid_at}


@app.post("/api/claims/{claim_id}/sign-off", operation_id="sign_off_claim")
def sign_off_claim(claim_id: str, sign_off: SignOff) -> dict[str, Any]:
    """Sign off a payout over the approval limit and pay it."""
    with database() as db:
        require_status(db, claim_id, "awaiting_sign_off", "sign off")
        handler = record(db, "handlers", "handler_id", sign_off.handler_id)
        if not handler["can_approve_over_limit"]:
            raise HTTPException(
                403, f"{handler['name']} cannot sign off payouts over the limit"
            )
        payout = db.execute(
            "SELECT payout FROM decisions WHERE claim_id = ?", (claim_id,)
        ).fetchone()["payout"]
        signed_at = now()
        db.execute(
            "INSERT INTO sign_offs VALUES (?, ?, ?)",
            (claim_id, sign_off.handler_id, signed_at),
        )
        db.execute(
            "INSERT INTO payments VALUES (?, ?, ?)", (claim_id, payout, signed_at)
        )
        set_status(db, claim_id, "decided")
    return {"status": "decided", "payout": payout}
