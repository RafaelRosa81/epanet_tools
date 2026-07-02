"""Project-specific exceptions."""


class EpanetToolsError(Exception):
    """Base exception for epanet_tools."""


class ConfigurationError(EpanetToolsError):
    """Raised when a workflow configuration is invalid."""


class TopologyValidationError(EpanetToolsError):
    """Raised when a topology problem prevents a workflow from continuing."""
