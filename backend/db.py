"""The UnderCover database, seeded from the records in data/."""

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

DATA = Path(__file__).parent.parent / "data"
DEFAULT_PATH = Path(__file__).parent / "undercover.db"

SCHEMA = """
CREATE TABLE claims (
    claim_id TEXT PRIMARY KEY, policy_id TEXT, customer_id TEXT, status TEXT, data TEXT
);
CREATE TABLE policies (policy_id TEXT PRIMARY KEY, data TEXT);
CREATE TABLE customers (customer_id TEXT PRIMARY KEY, data TEXT);
CREATE TABLE plans (plan TEXT PRIMARY KEY, data TEXT);
CREATE TABLE add_ons (add_on TEXT PRIMARY KEY, data TEXT);
CREATE TABLE handlers (handler_id TEXT PRIMARY KEY, data TEXT);
CREATE TABLE decisions (
    claim_id TEXT PRIMARY KEY, decision TEXT, payout REAL, reason TEXT,
    policy_section TEXT, decided_at TEXT
);
CREATE TABLE payments (claim_id TEXT PRIMARY KEY, amount REAL, paid_at TEXT);
CREATE TABLE sign_offs (claim_id TEXT PRIMARY KEY, handler_id TEXT, signed_at TEXT);
CREATE TABLE steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT, claim_id TEXT, thread_id TEXT,
    kind TEXT, text TEXT, created_at TEXT
);
"""


def load(name: str) -> Any:
    """Load one of the JSON files in data/."""
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def path() -> Path:
    """Return the database file, from UNDERCOVER_DB if set."""
    return Path(os.getenv("UNDERCOVER_DB", str(DEFAULT_PATH)))


@contextmanager
def database() -> Iterator[sqlite3.Connection]:
    """Open the database, commit on success and close it."""
    connection = sqlite3.connect(path())
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def seed() -> None:
    """Create the database afresh from data/."""
    path().unlink(missing_ok=True)
    plans = load("plans.json")
    records = {
        "policies": [(p["policy_id"], p) for p in load("policies.json")],
        "customers": [(c["customer_id"], c) for c in load("customers.json")],
        "plans": [
            (p["plan"], p | {"deductible_applies_to": plans["deductible_applies_to"]})
            for p in plans["plans"]
        ],
        "add_ons": [(a["add_on"], a) for a in plans["add_ons"]],
        "handlers": [(h["handler_id"], h) for h in load("handlers.json")],
    }
    with database() as db:
        db.executescript(SCHEMA)
        db.executemany(
            "INSERT INTO claims VALUES (?, ?, ?, 'waiting', ?)",
            [
                (c["claim_id"], c["policy_id"], c["customer_id"], json.dumps(c))
                for c in load("claims.json")
            ],
        )
        for table, rows in records.items():
            db.executemany(
                f"INSERT INTO {table} VALUES (?, ?)",  # noqa: S608
                [(key, json.dumps(data)) for key, data in rows],
            )


if __name__ == "__main__":
    seed()
    print(f"Seeded {path()}")
