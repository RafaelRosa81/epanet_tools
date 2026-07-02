"""Topology and geometry validation for pipe GIS layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import geopandas as gpd
from shapely.geometry import LineString, MultiLineString

from epanet_tools.models import ValidationIssue


@dataclass(frozen=True)
class PipeValidationOptions:
    """Configuration for pipe layer validation."""

    require_projected_crs: bool = True
    allow_multilines: bool = False
    min_length_m: float = 0.0
    allowed_geometry_types: tuple[str, ...] = ("LineString",)


@dataclass
class PipeValidationReport:
    """Validation result for a pipe layer."""

    feature_count: int
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """Return True when at least one blocking error was found."""
        return any(issue.severity == "error" for issue in self.issues)

    def count_by_severity(self) -> dict[str, int]:
        """Count validation issues by severity."""
        counts = {"info": 0, "warning": 0, "error": 0}
        for issue in self.issues:
            counts[issue.severity] += 1
        return counts


def validate_pipe_layer(
    pipes: gpd.GeoDataFrame,
    options: PipeValidationOptions | None = None,
) -> PipeValidationReport:
    """Validate a GIS pipe layer without modifying it.

    The function checks only pre-topology conditions: CRS, empty/null geometries,
    geometry type and non-positive lengths. Automatic snapping or line splitting
    belongs to later topology-construction steps.
    """
    opts = options or PipeValidationOptions()
    issues: list[ValidationIssue] = []

    _validate_crs(pipes, opts, issues)

    geometry_column = pipes.geometry.name
    for idx, row in pipes.iterrows():
        geom = row[geometry_column]
        element_id = str(idx)

        if geom is None or geom.is_empty:
            issues.append(
                ValidationIssue(
                    code="EMPTY_GEOMETRY",
                    severity="error",
                    message="Pipe feature has a null or empty geometry.",
                    element_id=element_id,
                )
            )
            continue

        geom_type = geom.geom_type
        if geom_type not in opts.allowed_geometry_types:
            severity = "error"
            if geom_type == "MultiLineString" and opts.allow_multilines:
                severity = "warning"
            issues.append(
                ValidationIssue(
                    code="UNSUPPORTED_GEOMETRY_TYPE",
                    severity=severity,
                    message=f"Unsupported pipe geometry type: {geom_type}.",
                    element_id=element_id,
                    details={"geometry_type": geom_type},
                )
            )

        if isinstance(geom, (LineString, MultiLineString)) and geom.length <= opts.min_length_m:
            issues.append(
                ValidationIssue(
                    code="NON_POSITIVE_LENGTH",
                    severity="error",
                    message="Pipe geometry length is not greater than the configured minimum.",
                    element_id=element_id,
                    details={"length": float(geom.length), "min_length_m": opts.min_length_m},
                )
            )

    return PipeValidationReport(feature_count=len(pipes), issues=issues)


def _validate_crs(
    pipes: gpd.GeoDataFrame,
    options: PipeValidationOptions,
    issues: list[ValidationIssue],
) -> None:
    if pipes.crs is None:
        issues.append(
            ValidationIssue(
                code="MISSING_CRS",
                severity="error",
                message="Pipe layer has no CRS. A projected metric CRS is required.",
            )
        )
        return

    if options.require_projected_crs and not pipes.crs.is_projected:
        issues.append(
            ValidationIssue(
                code="NON_PROJECTED_CRS",
                severity="error",
                message="Pipe layer CRS is not projected. Lengths and tolerances must be metric.",
                details={"crs": str(pipes.crs)},
            )
        )


def issues_to_records(issues: list[ValidationIssue]) -> list[dict[str, Any]]:
    """Convert validation issues to serializable dictionaries."""
    return [
        {
            "code": issue.code,
            "severity": issue.severity,
            "message": issue.message,
            "element_id": issue.element_id,
            "details": issue.details,
        }
        for issue in issues
    ]
