"""Core typed models used across the package.

These models intentionally represent an intermediate, package-level view of the
network. They are not a direct mirror of the EPANET INP text format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

Severity = Literal["info", "warning", "error"]


class PipeStatus(str, Enum):
    """Supported initial pipe statuses for EPANET export."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CV = "CV"


@dataclass(frozen=True)
class ValidationIssue:
    """Single validation issue detected during a workflow."""

    code: str
    severity: Severity
    message: str
    element_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Node:
    """Hydraulic node created from GIS topology."""

    id: str
    x: float
    y: float
    elevation_m: float | None = None
    source_id: str | None = None


@dataclass(frozen=True)
class Pipe:
    """Hydraulic pipe/link created from a GIS line feature."""

    id: str
    from_node: str
    to_node: str
    length_m: float
    diameter_mm: float | None = None
    roughness: float | None = None
    minor_loss: float = 0.0
    status: PipeStatus = PipeStatus.OPEN
    material: str | None = None
    source_id: str | None = None


@dataclass
class HydraulicModel:
    """Intermediate hydraulic model before INP serialization."""

    name: str
    nodes: dict[str, Node] = field(default_factory=dict)
    pipes: dict[str, Pipe] = field(default_factory=dict)
    issues: list[ValidationIssue] = field(default_factory=list)
