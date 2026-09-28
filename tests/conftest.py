import json
import time
from pathlib import Path

import pytest

from app.quran_source import build_index

FIXTURE = Path(__file__).parent / "fixtures" / "hafs_subset.json"


@pytest.fixture(scope="session")
def records():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["ayahs"]


@pytest.fixture(scope="session")
def index(records):
    return build_index(records, time.time())


class FakeSource:
    def __init__(self, index=None, error=False):
        self.index, self.error = index, error

    def get(self):
        from app.quran_source import SourceUnavailable

        if self.error:
            raise SourceUnavailable("offline")
        return self.index

    def status(self):
        return {"loaded": self.index is not None}


@pytest.fixture
def use_source(monkeypatch, index):
    """Patch the audit pipeline to use the offline fixture and no AI provider."""
    import app.audit as audit

    fake = FakeSource(index)
    monkeypatch.setattr(audit, "source", fake)
    monkeypatch.setattr(audit, "get_provider", lambda: None)
    return fake
