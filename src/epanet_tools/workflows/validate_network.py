"""GIS pipe network validation workflow."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from epanet_tools.config import load_yaml_config, require_mapping
from epanet_tools.io.gis_outputs import write_combined_pipe_layer, write_working_geopackage
from epanet_tools.io.reports import write_validation_report
from epanet_tools.io.vector import read_pipe_layers
from epanet_tools.topology.validation import PipeValidationOptions, validate_pipe_layer


@dataclass(frozen=True)
class ValidationWorkflowResult:
    """Result returned by the validation workflow."""

    status: str
    feature_count: int
    has_errors: bool
    issue_counts: dict[str, int]
    report_paths: dict[str, Path]
    gis_paths: dict[str, Path]


def validate_network(config_path: str | Path) -> ValidationWorkflowResult:
    """Validate pipe layers from a YAML configuration file."""
    config = load_yaml_config(config_path)
    inputs = require_mapping(config, "inputs")
    pipe_inputs = _pipe_inputs(inputs)

    name = str(config.get("name", "epanet_model"))
    outdir = Path(str(config.get("outdir", "outputs")))
    working_crs = _working_crs(config)

    pipes = read_pipe_layers(pipe_inputs, working_crs=working_crs)

    topology_config = config.get("topology", {})
    if not isinstance(topology_config, dict):
        topology_config = {}

    options = PipeValidationOptions(
        allow_multilines=bool(topology_config.get("explode_multilines", False)),
        min_length_m=float(topology_config.get("min_length_m", 0.0)),
    )
    report = validate_pipe_layer(pipes, options)
    report_paths = write_validation_report(report, outdir=outdir, name=name)
    combined_path = write_combined_pipe_layer(pipes, outdir=outdir, name=name)
    working_path = write_working_geopackage(pipes, outdir=outdir, name=name)

    return ValidationWorkflowResult(
        status="failed" if report.has_errors else "ok",
        feature_count=report.feature_count,
        has_errors=report.has_errors,
        issue_counts=report.count_by_severity(),
        report_paths=report_paths,
        gis_paths={
            "combined_pipes": combined_path,
            "working_geopackage": working_path,
        },
    )


def _pipe_inputs(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    pipes = inputs.get("pipes")
    if not isinstance(pipes, list) or not pipes:
        msg = "Configuration must define at least one input pipe layer under inputs.pipes."
        raise ValueError(msg)
    for pipe_input in pipes:
        if not isinstance(pipe_input, dict) or "path" not in pipe_input:
            msg = "Each pipe input must be a mapping containing at least a path."
            raise ValueError(msg)
    return pipes


def _working_crs(config: dict[str, Any]) -> str | None:
    spatial = config.get("spatial", {})
    if not isinstance(spatial, dict):
        return None
    value = spatial.get("working_crs")
    return str(value) if value is not None else None


def main() -> None:
    """Command-line entrypoint for network validation."""
    parser = argparse.ArgumentParser(
        description="Validate a GIS pipe network for EPANET export."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the workflow YAML configuration.",
    )
    args = parser.parse_args()
    result = validate_network(args.config)
    report_paths = {key: str(value) for key, value in result.report_paths.items()}
    gis_paths = {key: str(value) for key, value in result.gis_paths.items()}
    output = {
        "status": result.status,
        "feature_count": result.feature_count,
        "has_errors": result.has_errors,
        "issue_counts": result.issue_counts,
        "report_paths": report_paths,
        "gis_paths": gis_paths,
    }
    print(output)


if __name__ == "__main__":
    main()
