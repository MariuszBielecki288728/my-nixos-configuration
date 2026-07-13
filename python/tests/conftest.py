"""Shared paths and report loaders for Python tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from mini_pc_provision.models import DiscoveryReport

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def fixture_report() -> Callable[[str], DiscoveryReport]:
    """Load existing repository discovery fixtures through the real model parser."""

    def load(name: str) -> DiscoveryReport:
        value = json.loads((ROOT / "tests/fixtures" / name).read_text(encoding="utf-8"))
        return DiscoveryReport.from_json(value)

    return load
