"""Domain-specific errors exposed as concise command-line failures."""


class ProvisioningError(Exception):
    """A user-actionable provisioning or validation failure."""
