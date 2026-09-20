"""Workflow for importing an existing node-pipe GIS network into EPANET."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from epanet_tools.config import load_yaml_config, require_mapping
from epanet_tools.hydraulic.attributes import HydraulicAttributeReport, apply_hydraulic_attributes
from epanet_tools.hydraulic.validation import BasicModelValidationReport, validate_basic_epanet_model
from epanet_tools.io.inp import write_basic_inp
from epanet_tools.io.reports import write_basic_model_validation_report, write_summary_report
from epanet_tools.io.vector import read_existing_network


@dataclass(frozen=True)
class ExistingNetworkImportResult:
    """Result returned by the existing-network import workflow."""

    status: str
    node_count: int
    pipe_count: int
    report_paths: dict[str, Path]
    inp_paths: dict[str, Path]
    hydraulic_report: HydraulicAttributeReport
    basic_model_report: BasicModelValidationReport


def import_existing_network(config_path: str | Path) -> ExistingNetworkImportResult:
    """Import an existing GIS network with explicit node and pipe layers."""
    config = load_yaml_config(config_path)
    inputs = require_mapping(config, "inputs")
    existing = require_mapping(inputs, "existing_network")

    path = existing.get("path")
    node_layer = existing.get("node_layer")
    pipe_layer = existing.get("pipe_layer")
    if not path or not node_layer or not pipe_layer:
        raise ValueError(
            "inputs.existing_network must define path, node_layer and pipe_layer."
        )

    name = str(config.get("name", "epanet_model"))
    outdir = Path(str(config.get("outdir", "outputs")))
    working_crs = _working_crs(config)

    junctions, pipes = read_existing_network(
        path=path,
        node_layer=str(node_layer),
        pipe_layer=str(pipe_layer),
        working_crs=working_crs,
    )

    field_mapping = _mapping(config, "field_mapping")
    junctions = _map_fields(
        junctions,
        field_mapping.get("nodes"),
        defaults={"demand": 0.0},
    )
    pipes = _map_fields(
        pipes,
        field_mapping.get("pipes"),
        defaults={"minor_loss": 0.0, "status": "OPEN"},
    )

    junctions, pipes = _filter_network(junctions, pipes, _mapping(config, "network_filter"))
    junctions = _apply_node_attributes_csv(
        junctions, _mapping(config, "node_attributes_csv")
    )
    pipes = _apply_pipe_attributes_csv(
        pipes, _mapping(config, "pipe_attributes_csv")
    )

    if "length_m" not in pipes.columns:
        pipes["length_m"] = pipes.geometry.length

    pipes, hydraulic_report = apply_hydraulic_attributes(
        pipes,
        hydraulics_config=_mapping(config, "hydraulics"),
    )
    basic_model_report = validate_basic_epanet_model(junctions, pipes)

    report_paths: dict[str, Path] = {}
    report_paths["hydraulics_csv"] = write_summary_report(
        hydraulic_report, outdir, name, "hydraulics"
    )
    report_paths["basic_model_validation_csv"] = write_basic_model_validation_report(
        basic_model_report,
        outdir=outdir,
        name=name,
    )

    inp_path = write_basic_inp(
        junctions=junctions,
        pipes=pipes,
        outdir=outdir,
        name=name,
        flow_units=str(_mapping(config, "hydraulics").get("flow_units", "LPS")),
        headloss=str(_mapping(config, "hydraulics").get("headloss", "H-W")),
    )

    return ExistingNetworkImportResult(
        status="ok" if basic_model_report.export_ready else "failed",
        node_count=len(junctions),
        pipe_count=len(pipes),
        report_paths=report_paths,
        inp_paths={"inp": inp_path},
        hydraulic_report=hydraulic_report,
        basic_model_report=basic_model_report,
    )


def _map_fields(
    data: gpd.GeoDataFrame,
    mapping_value: Any,
    defaults: dict[str, Any] | None = None,
) -> gpd.GeoDataFrame:
    """Copy source attributes into canonical epanet_tools field names."""
    mapping = mapping_value if isinstance(mapping_value, dict) else {}
    result = data.copy()
    for canonical, source in mapping.items():
        source_name = str(source)
        if source_name not in result.columns:
            raise ValueError(
                f"Configured source field '{source_name}' for '{canonical}' does not exist."
            )
        result[str(canonical)] = result[source_name]

    for field, value in (defaults or {}).items():
        if field not in result.columns:
            result[field] = value
        else:
            result[field] = result[field].where(~pd.isna(result[field]), value)
    return result


def _apply_node_attributes_csv(
    junctions: gpd.GeoDataFrame,
    csv_config: dict[str, Any],
) -> gpd.GeoDataFrame:
    """Override configured node attributes from a CSV joined by node identifier."""
    if not csv_config:
        return junctions

    path_value = csv_config.get("path")
    fields = csv_config.get("fields", {})
    csv_key = str(csv_config.get("key", "ID"))
    node_key = str(csv_config.get("node_key", "node_id"))
    if not path_value or not isinstance(fields, dict) or not fields:
        raise ValueError("node_attributes_csv requires path and a non-empty fields mapping.")
    if node_key not in junctions.columns:
        raise ValueError(f"Node join field '{node_key}' does not exist.")

    csv_path = Path(str(path_value))
    if not csv_path.exists():
        raise FileNotFoundError(f"Node attributes CSV not found: {csv_path}")
    attributes = pd.read_csv(csv_path)
    required = {csv_key, *(str(source) for source in fields.values())}
    missing = sorted(required.difference(attributes.columns))
    if missing:
        raise ValueError(f"Node attributes CSV is missing fields: {', '.join(missing)}")
    if attributes[csv_key].isna().any():
        raise ValueError(f"Node attributes CSV contains missing values in key '{csv_key}'.")
    if attributes[csv_key].astype(str).duplicated().any():
        raise ValueError(f"Node attributes CSV contains duplicate values in key '{csv_key}'.")

    lookup = attributes.set_index(attributes[csv_key].astype(str))
    result = junctions.copy()
    node_ids = result[node_key].astype(str)
    unmatched = ~node_ids.isin(lookup.index)
    if unmatched.any():
        examples = ", ".join(node_ids.loc[unmatched].head(5).tolist())
        raise ValueError(
            f"Node attributes CSV does not contain {int(unmatched.sum())} retained nodes. "
            f"Examples: {examples}"
        )

    for target, source in fields.items():
        source_name = str(source)
        result[str(target)] = node_ids.map(lookup[source_name])
    return result


def _apply_pipe_attributes_csv(
    pipes: gpd.GeoDataFrame,
    csv_config: dict[str, Any],
) -> gpd.GeoDataFrame:
    """Override configured pipe attributes from a CSV joined by pipe identifier."""
    if not csv_config:
        return pipes

    path_value = csv_config.get("path")
    fields = csv_config.get("fields", {})
    csv_key = str(csv_config.get("key", "ID"))
    pipe_key = str(csv_config.get("pipe_key", "pipe_id"))
    if not path_value or not isinstance(fields, dict) or not fields:
        raise ValueError("pipe_attributes_csv requires path and a non-empty fields mapping.")
    if pipe_key not in pipes.columns:
        raise ValueError(f"Pipe join field '{pipe_key}' does not exist.")

    csv_path = Path(str(path_value))
    if not csv_path.exists():
        raise FileNotFoundError(f"Pipe attributes CSV not found: {csv_path}")
    attributes = pd.read_csv(csv_path)
    required = {csv_key, *(str(source) for source in fields.values())}
    missing = sorted(required.difference(attributes.columns))
    if missing:
        raise ValueError(f"Pipe attributes CSV is missing fields: {', '.join(missing)}")
    if attributes[csv_key].isna().any():
        raise ValueError(f"Pipe attributes CSV contains missing values in key '{csv_key}'.")
    if attributes[csv_key].astype(str).duplicated().any():
        raise ValueError(f"Pipe attributes CSV contains duplicate values in key '{csv_key}'.")

    lookup = attributes.set_index(attributes[csv_key].astype(str))
    result = pipes.copy()
    pipe_ids = result[pipe_key].astype(str)
    unmatched = ~pipe_ids.isin(lookup.index)
    if unmatched.any():
        examples = ", ".join(pipe_ids.loc[unmatched].head(5).tolist())
        raise ValueError(
            f"Pipe attributes CSV does not contain {int(unmatched.sum())} retained pipes. "
            f"Examples: {examples}"
        )

    for target, source in fields.items():
        source_name = str(source)
        result[str(target)] = pipe_ids.map(lookup[source_name])
    return result


def _filter_network(
    junctions: gpd.GeoDataFrame,
    pipes: gpd.GeoDataFrame,
    filter_config: dict[str, Any],
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Filter an existing network by sector while preserving node-pipe consistency."""
    excluded = filter_config.get("exclude_sectors", [])
    if not excluded:
        return junctions, pipes
    if "SECTOR" not in junctions.columns or "SECTOR" not in pipes.columns:
        raise ValueError("network_filter.exclude_sectors requires a SECTOR field in nodes and pipes.")

    excluded_values = {str(value) for value in excluded}
    node_sector = junctions["SECTOR"].map(_sector_key)
    pipe_sector = pipes["SECTOR"].map(_sector_key)
    filtered_junctions = junctions.loc[~node_sector.isin(excluded_values)].copy()
    filtered_pipes = pipes.loc[~pipe_sector.isin(excluded_values)].copy()

    retained_nodes = set(filtered_junctions["node_id"].astype(str))
    endpoints_ok = (
        filtered_pipes["from_node"].astype(str).isin(retained_nodes)
        & filtered_pipes["to_node"].astype(str).isin(retained_nodes)
    )
    filtered_pipes = filtered_pipes.loc[endpoints_ok].copy()
    return filtered_junctions, filtered_pipes


def _sector_key(value: Any) -> str:
    """Normalize numeric sector labels so 8, 8.0 and '8' compare equally."""
    if pd.isna(value):
        return ""
    try:
        number = float(value)
        if number.is_integer():
            return str(int(number))
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _mapping(config: dict[str, Any], key: str) -> dict[str, Any]:
    value = config.get(key, {})
    return value if isinstance(value, dict) else {}


def _working_crs(config: dict[str, Any]) -> str | None:
    spatial = _mapping(config, "spatial")
    value = spatial.get("working_crs")
    return str(value) if value is not None else None


def main() -> None:
    """Command-line entrypoint for importing an existing network."""
    parser = argparse.ArgumentParser(
        description="Import an existing GIS node-pipe network for EPANET export."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the workflow YAML configuration.",
    )
    args = parser.parse_args()
    result = import_existing_network(args.config)
    print(
        {
            "status": result.status,
            "node_count": result.node_count,
            "pipe_count": result.pipe_count,
            "report_paths": {k: str(v) for k, v in result.report_paths.items()},
            "inp_paths": {k: str(v) for k, v in result.inp_paths.items()},
            "basic_model_validation": {
                "junction_count": result.basic_model_report.junction_count,
                "pipe_count": result.basic_model_report.pipe_count,
                "invalid_node_references": result.basic_model_report.invalid_node_references,
                "self_loop_pipes": result.basic_model_report.self_loop_pipes,
                "isolated_junctions": result.basic_model_report.isolated_junctions,
                "disconnected_components": result.basic_model_report.disconnected_components,
                "export_ready": result.basic_model_report.export_ready,
            },
        }
    )


if __name__ == "__main__":
    main()
