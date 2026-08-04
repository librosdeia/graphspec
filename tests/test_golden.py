"""Golden-file tests: the DOT for the book's example is frozen byte-for-byte.

Regenerate deliberately (after a reviewed grammar change) with:
    GRAPHSPEC_REGEN=1 .venv/bin/python -m pytest tests/test_golden.py
"""

import os
import pathlib

import pytest

from graphspec.parser import load
from graphspec.render import to_dot

GOLDEN_DIR = pathlib.Path("tests/golden")

CASES = [
    ("examples/software-delivery.yaml", "software-delivery.dot"),
    ("examples/research-publishing.yaml", "research-publishing.dot"),
    ("examples/support-triage.yaml", "support-triage.dot"),
]


@pytest.mark.parametrize("source,golden", CASES)
def test_dot_matches_golden(source, golden):
    if not os.path.exists(source):
        pytest.skip(f"{source} not shipped yet")
    dot = to_dot(load(source))
    path = GOLDEN_DIR / golden
    if os.environ.get("GRAPHSPEC_REGEN") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dot, encoding="utf-8")
    assert path.exists(), f"golden file missing — run with GRAPHSPEC_REGEN=1 to create {path}"
    assert dot == path.read_text(encoding="utf-8"), (
        f"DOT for {source} changed. If the grammar change is intentional and reviewed, "
        f"regenerate with GRAPHSPEC_REGEN=1; the book prints these figures."
    )
