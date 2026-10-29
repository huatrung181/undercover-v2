import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.db import seed


class FakeAgent:
    """Stands in for the UnderCover Agent: makes the API calls a test gives it."""

    def __init__(self):
        self.calls = []
        self.replies = []
        self.error = None

    def run(self, claim_id, thread_id):
        api = TestClient(main.app)
        self.replies = [api.request(m, url, json=body) for m, url, body in self.calls]
        if self.error:
            raise self.error


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A client for the backend on a fresh database."""
    monkeypatch.setenv("UNDERCOVER_DB", str(tmp_path / "test.db"))
    seed()
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def agent(monkeypatch):
    """A fake agent in place of the real one, which would call a model."""
    fake = FakeAgent()
    monkeypatch.setattr(main, "run_claim", fake.run)
    return fake
