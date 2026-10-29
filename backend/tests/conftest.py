import pytest
from fastapi.testclient import TestClient

from backend.db import seed
from backend.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A client for the backend on a fresh database."""
    monkeypatch.setenv("UNDERCOVER_DB", str(tmp_path / "test.db"))
    seed()
    return TestClient(app)
