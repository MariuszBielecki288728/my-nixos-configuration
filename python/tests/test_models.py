"""Discovery model validation tests."""

from __future__ import annotations

import pytest

from mini_pc_provision.errors import ProvisioningError
from mini_pc_provision.models import DiscoveryReport


@pytest.mark.parametrize("value", [{}, {"schema_version": "2.0"}, []])
def test_rejects_unsupported_schema(value) -> None:
    """Unknown or missing schemas fail before disk policy evaluation."""
    with pytest.raises(ProvisioningError, match="schema"):
        DiscoveryReport.from_json(value)


def test_rejects_missing_device_arrays() -> None:
    """Required discovery arrays cannot be silently defaulted."""
    with pytest.raises(ProvisioningError, match="block-device"):
        DiscoveryReport.from_json({"schema_version": "1.0"})
