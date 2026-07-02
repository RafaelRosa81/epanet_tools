"""GIS pipe network validation workflow."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from epanet_tools.config import load_yaml_config, require_mapping
from epanet_tools.io.reports import write_validation_report
from epanet_tools.io.vector import read_pipe_layer
from epanet_tools.topology.validation import PipeValidationOptions, validate_pipe_layer


@dataclass(frozen=True)
class ValidationWorkflowResult:
    """Result returned by the validation workflow."""

    status: str
    feature_count: int
    has_errors: bool
    issue_counts: dict[str, int]
    report_paths: dict[str, Path]


def validate_network(config_path: str | Path) -> ValidationWorkflowResult:
    """Validate a pipe network from a YAML configuration file."""
    config = load_yaml_config(config_path)
    inputs = require_mapping(config, "inputs")
    pipes_config = _first_pipe_input(inputs)

    name = str(config.get("name", "epanet_model"))
    outdir = Path(str(config.get("outdir", "outputs")))

    pipes = read_pipe_layer(
        pipes_config["path"],
        layer=pipes_config.get("layer"),
    )

    topology_config = config.get("topology", {})
    if not isinstance(topology_config, dict):
        topology_config = {}

    options = PipeValidationOptions(
        allow_multilines=bool(topology_config.get("explode_multilines", False)),
        min_length_m=float(topology_config.get("min_length_m", 0.0)),
    )
    report = validate_pipe_layer(pipes, options)
    report_paths = write_validation_report(report, outdir=outdir, name=name)

    return ValidationWorkflowResult(
        status="failed" if report.has_errors else "ok",
        feature_count=report.feature_count,
        has_errors=report.has_errors,
        issue_counts=report.count_by_severity(),
        report_paths=report_paths,
    )


def _first_pipe_input(inputs: dict[str, Any]) -> dict[str, Any]:
    pipes = inputs.get("pipes")
    if not isinstance(pipes, list) or not pipes:
        msg = "Configuration must define at least one input pipe layer under inputs.pipes."
        raise ValueError(msg)
    first = pipes[0]
    if not isinstance(first, dict) or "path" not in first:
        msg = "Each pipe input must be a mapping containing at least a path."
        raise ValueError(msg)
    return first


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
    output = {
        "status": result.status,
        "feature_count": result.feature_count,
        "has_errors": result.has_errors,
        "issue_counts": result.issue_counts,
        "report_paths": {key: str(value) for key, value in result.report_paths.items()},
    }
    print(output)


if __name__ == "__main__":
    main()
