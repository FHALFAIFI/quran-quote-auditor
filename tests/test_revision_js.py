"""Runs the browser revision-engine tests (tests/revision.test.mjs) under Node, if installed."""

import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_revision_engine_node():
    root = Path(__file__).resolve().parent.parent
    r = subprocess.run([NODE, "--test", str(root / "tests" / "revision.test.mjs")], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
