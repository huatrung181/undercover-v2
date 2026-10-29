"""The UnderCover backend."""

import json
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

from backend.db import DATA, database, path, seed

INSTRUCTIONS = Path(__file__).parent / "instructions.md"
POLICY_WORDING = (DATA / "policy_wording.md").read_text(encoding="utf-8")


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
        data = record(db, "claims", "claim_id", claim_id)
        status = db.execute(
            "SELECT status FROM claims WHERE claim_id = ?", (claim_id,)
        ).fetchone()["status"]
        return data | {
            "status": status,
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
