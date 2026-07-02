"""GIS pipe network validation workflow."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from epanet_tools.config import load_yaml_config, require_mapping
from epanet_tools.hydraulic.attributes import HydraulicAttributeReport, apply_hydraulic_attributes
from epanet_tools.hydraulic.demands import DemandAssignmentReport, apply_node_demands
from epanet_tools.hydraulic.validation import BasicModelValidationReport, validate_basic_epanet_model
from epanet_tools.io.gis_outputs import write_combined_pipe_layer, write_working_geopackage
from epanet_tools.io.inp import write_basic_inp
from epanet_tools.io.reports import (
    write_basic_model_validation_report,
    write_summary_report,
    write_validation_report,
)
from epanet_tools.io.vector import read_pipe_layers
from epanet_tools.model.nodes import (
    build_nodes_from_junctions,
    junctions_from_nodes,
    reservoirs_from_nodes,
    tanks_from_nodes,
)
from epanet_tools.terrain.elevation import ElevationSamplingReport, sample_junction_elevations
from epanet_tools.topology.cleaning import CleaningReport, normalize_pipe_topology
from epanet_tools.topology.connectivity import ConnectivityReport, build_junctions_and_connectivity
from epanet_tools.topology.review import TopologyReviewReport, review_normalized_topology
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
    inp_paths: dict[str, Path]
    cleaning_report: CleaningReport
    connectivity_report: ConnectivityReport
    elevation_report: ElevationSamplingReport
    hydraulic_report: HydraulicAttributeReport
    demand_report: DemandAssignmentReport
    basic_model_report: BasicModelValidationReport
    topology_review_report: TopologyReviewReport


def validate_network(config_path: str | Path) -> ValidationWorkflowResult:
    """Validate pipe layers from a YAML configuration file."""
    config = load_yaml_config(config_path)
    inputs = require_mapping(config, "inputs")
    pipe_inputs = _pipe_inputs(inputs)

    name = str(config.get("name", "epanet_model"))
    outdir = Path(str(config.get("outdir", "outputs")))
    working_crs = _working_crs(config)

    pipes = read_pipe_layers(pipe_inputs, working_crs=working_crs)

    topology_config = _mapping(config, "topology")
    options = PipeValidationOptions(
        allow_multilines=bool(topology_config.get("explode_multilines", False)),
        min_length_m=float(topology_config.get("min_length_m", 0.0)),
    )
    report = validate_pipe_layer(pipes, options)

    snap_tolerance_m = _snap_tolerance_m(config)
    pipes_clean_auto, cleaning_report = normalize_pipe_topology(pipes, tolerance_m=snap_tolerance_m)
    pipes_clean, generated_junctions, connectivity_report = build_junctions_and_connectivity(pipes_clean_auto)
    pipes_clean, hydraulic_report = apply_hydraulic_attributes(
        pipes_clean,
        hydraulics_config=_mapping(config, "hydraulics"),
    )
    generated_junctions, elevation_report = sample_junction_elevations(
        generated_junctions,
        dem_path=inputs.get("dem"),
        dem_crs_override=inputs.get("dem_crs"),
    )

    nodes = build_nodes_from_junctions(generated_junctions, node_config=_mapping(config, "nodes"))
    nodes, demand_report = apply_node_demands(nodes, demands_config=_mapping(config, "demands"))
    junctions = junctions_from_nodes(nodes)
    reservoirs = reservoirs_from_nodes(nodes)
    tanks = tanks_from_nodes(nodes)

    topology_errors, topology_report, topology_review_report = review_normalized_topology(
        pipes_clean,
        junctions,
        min_pipe_length_m=float(topology_config.get("min_length_m", 0.05)),
    )
    basic_model_report = validate_basic_epanet_model(junctions, pipes_clean)

    report_paths = write_validation_report(report, outdir=outdir, name=name)
    report_paths["cleaning_csv"] = write_summary_report(cleaning_report, outdir, name, "cleaning")
    report_paths["connectivity_csv"] = write_summary_report(connectivity_report, outdir, name, "connectivity")
    report_paths["elevation_csv"] = write_summary_report(elevation_report, outdir, name, "elevation")
    report_paths["hydraulics_csv"] = write_summary_report(hydraulic_report, outdir, name, "hydraulics")
    report_paths["demands_csv"] = write_summary_report(demand_report, outdir, name, "demands")
    report_paths["topology_review_csv"] = write_summary_report(topology_review_report, outdir, name, "topology_review")
    report_paths["basic_model_validation_csv"] = write_basic_model_validation_report(
        basic_model_report,
        outdir=outdir,
        name=name,
    )
    combined_path = write_combined_pipe_layer(pipes, outdir=outdir, name=name)
    working_path = write_working_geopackage(
        pipes,
        outdir=outdir,
        name=name,
        pipes_clean_auto=pipes_clean_auto,
        pipes_clean=pipes_clean,
        nodes=nodes,
        junctions=junctions,
        reservoirs=reservoirs,
        tanks=tanks,
        topology_errors=topology_errors,
        topology_report=topology_report,
    )
    inp_path = write_basic_inp(
        junctions=junctions,
        pipes=pipes_clean,
        outdir=outdir,
        name=name,
        flow_units=str(_mapping(config, "hydraulics").get("flow_units", "LPS")),
        headloss=str(_mapping(config, "hydraulics").get("headloss", "H-W")),
    )

    return ValidationWorkflowResult(
        status="failed" if report.has_errors else "ok",
        feature_count=report.feature_count,
        has_errors=report.has_errors,
        issue_counts=report.count_by_severity(),
        report_paths=report_paths,
        gis_paths={"combined_pipes": combined_path, "working_geopackage": working_path},
        inp_paths={"inp": inp_path},
        cleaning_report=cleaning_report,
        connectivity_report=connectivity_report,
        elevation_report=elevation_report,
        hydraulic_report=hydraulic_report,
        demand_report=demand_report,
        basic_model_report=basic_model_report,
        topology_review_report=topology_review_report,
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


def _mapping(config: dict[str, Any], key: str) -> dict[str, Any]:
    value = config.get(key, {})
    return value if isinstance(value, dict) else {}


def _working_crs(config: dict[str, Any]) -> str | None:
    spatial = _mapping(config, "spatial")
    value = spatial.get("working_crs")
    return str(value) if value is not None else None


def _snap_tolerance_m(config: dict[str, Any]) -> float:
    topology = _mapping(config, "topology")
    spatial = _mapping(config, "spatial")
    value = topology.get("snap_tolerance_m", spatial.get("snap_tolerance_m", 0.0))
    return float(value or 0.0)


def main() -> None:
    """Command-line entrypoint for network validation."""
    parser = argparse.ArgumentParser(description="Validate a GIS pipe network for EPANET export.")
    parser.add_argument("--config", required=True, help="Path to the workflow YAML configuration.")
    args = parser.parse_args()
    result = validate_network(args.config)
    report_paths = {key: str(value) for key, value in result.report_paths.items()}
    gis_paths = {key: str(value) for key, value in result.gis_paths.items()}
    inp_paths = {key: str(value) for key, value in result.inp_paths.items()}
    output = {
        "status": result.status,
        "feature_count": result.feature_count,
        "has_errors": result.has_errors,
        "issue_counts": result.issue_counts,
        "cleaning": {
            "snapped_endpoint_count": result.cleaning_report.snapped_endpoint_count,
            "snap_group_count": result.cleaning_report.snap_group_count,
            "endpoint_to_segment_snap_count": result.cleaning_report.endpoint_to_segment_snap_count,
            "connection_split_point_count": result.cleaning_report.connection_split_point_count,
            "split_pipe_count": result.cleaning_report.split_pipe_count,
            "output_feature_count": result.cleaning_report.output_feature_count,
        },
        "connectivity": {
            "pipe_count": result.connectivity_report.pipe_count,
            "junction_count": result.connectivity_report.junction_count,
            "skipped_geometry_count": result.connectivity_report.skipped_geometry_count,
        },
        "elevation": {
            "node_count": result.elevation_report.node_count,
            "sampled_count": result.elevation_report.sampled_count,
            "missing_count": result.elevation_report.missing_count,
            "dem_crs": result.elevation_report.dem_crs,
        },
        "hydraulics": {
            "pipe_count": result.hydraulic_report.pipe_count,
            "existing_value_count": result.hydraulic_report.existing_value_count,
            "category_value_count": result.hydraulic_report.category_value_count,
            "default_value_count": result.hydraulic_report.default_value_count,
            "missing_required_count": result.hydraulic_report.missing_required_count,
            "invalid_value_count": result.hydraulic_report.invalid_value_count,
            "undefined_category_count": result.hydraulic_report.undefined_category_count,
        },
        "demands": {
            "node_count": result.demand_report.node_count,
            "existing_demand_count": result.demand_report.existing_demand_count,
            "default_demand_count": result.demand_report.default_demand_count,
            "rule_demand_count": result.demand_report.rule_demand_count,
            "missing_demand_count": result.demand_report.missing_demand_count,
        },
        "topology_review": {
            "pipe_count": result.topology_review_report.pipe_count,
            "junction_count": result.topology_review_report.junction_count,
            "free_endpoint_count": result.topology_review_report.free_endpoint_count,
            "disconnected_component_count": result.topology_review_report.disconnected_component_count,
            "short_pipe_count": result.topology_review_report.short_pipe_count,
            "possible_unconnected_crossing_count": result.topology_review_report.possible_unconnected_crossing_count,
            "issue_count": result.topology_review_report.issue_count,
        },
        "basic_model_validation": {
            "junction_count": result.basic_model_report.junction_count,
            "pipe_count": result.basic_model_report.pipe_count,
            "missing_elevations": result.basic_model_report.missing_elevations,
            "missing_diameters": result.basic_model_report.missing_diameters,
            "missing_roughness": result.basic_model_report.missing_roughness,
            "missing_minor_loss": result.basic_model_report.missing_minor_loss,
            "invalid_pipe_status": result.basic_model_report.invalid_pipe_status,
            "invalid_node_references": result.basic_model_report.invalid_node_references,
            "self_loop_pipes": result.basic_model_report.self_loop_pipes,
            "isolated_junctions": result.basic_model_report.isolated_junctions,
            "disconnected_components": result.basic_model_report.disconnected_components,
            "export_ready": result.basic_model_report.export_ready,
        },
        "report_paths": report_paths,
        "gis_paths": gis_paths,
        "inp_paths": inp_paths,
    }
    print(output)


if __name__ == "__main__":
    main()
