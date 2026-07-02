"""Validation checks for basic EPANET model readiness."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import geopandas as gpd
import networkx as nx
import pandas as pd


@dataclass(frozen=True)
class BasicModelValidationReport:
    """Summary of basic EPANET model validation checks."""

    junction_count: int
    pipe_count: int
    missing_elevations: int
    missing_diameters: int
    missing_roughness: int
    missing_minor_loss: int
    invalid_pipe_status: int
    invalid_node_references: int
    self_loop_pipes: int
    isolated_junctions: int
    disconnected_components: int
    export_ready: bool


def validate_basic_epanet_model(
    junctions: gpd.GeoDataFrame,
    pipes: gpd.GeoDataFrame,
) -> BasicModelValidationReport:
    """Validate a minimal junction/pipe model before or after INP export."""
    node_ids = set(_string_values(junctions, "node_id"))
    from_nodes = _string_values(pipes, "from_node")
    to_nodes = _string_values(pipes, "to_node")

    invalid_node_references = sum(
        1
        for from_node, to_node in zip(from_nodes, to_nodes, strict=False)
        if from_node not in node_ids or to_node not in node_ids
    )
    self_loop_pipes = sum(
        1 for from_node, to_node in zip(from_nodes, to_nodes, strict=False) if from_node == to_node
    )

    graph = nx.Graph()
    graph.add_nodes_from(node_ids)
    for from_node, to_node in zip(from_nodes, to_nodes, strict=False):
        if from_node in node_ids and to_node in node_ids and from_node != to_node:
            graph.add_edge(from_node, to_node)

    isolated_junctions = nx.number_of_isolates(graph) if graph.number_of_nodes() else 0
    disconnected_components = nx.number_connected_components(graph) if graph.number_of_nodes() else 0

    missing_elevations = _missing_or_invalid_numeric(junctions, "elevation_m", allow_zero=True)
    missing_diameters = _missing_or_invalid_numeric(pipes, "diameter_mm", allow_zero=False)
    missing_roughness = _missing_or_invalid_numeric(pipes, "roughness", allow_zero=False)
    missing_minor_loss = _missing_or_invalid_numeric(pipes, "minor_loss", allow_zero=True)
    invalid_pipe_status = _invalid_status_count(pipes)

    export_ready = all(
        count == 0
        for count in (
            missing_elevations,
            missing_diameters,
            missing_roughness,
            missing_minor_loss,
            invalid_pipe_status,
            invalid_node_references,
            self_loop_pipes,
            isolated_junctions,
        )
    )

    return BasicModelValidationReport(
        junction_count=len(junctions),
        pipe_count=len(pipes),
        missing_elevations=missing_elevations,
        missing_diameters=missing_diameters,
        missing_roughness=missing_roughness,
        missing_minor_loss=missing_minor_loss,
        invalid_pipe_status=invalid_pipe_status,
        invalid_node_references=invalid_node_references,
        self_loop_pipes=self_loop_pipes,
        isolated_junctions=isolated_junctions,
        disconnected_components=disconnected_components,
        export_ready=export_ready,
    )


def _string_values(data: gpd.GeoDataFrame, field: str) -> list[str]:
    if field not in data.columns:
        return []
    return [str(value).strip() for value in data[field].tolist()]


def _missing_or_invalid_numeric(
    data: gpd.GeoDataFrame,
    field: str,
    allow_zero: bool,
) -> int:
    if field not in data.columns:
        return len(data)
    count = 0
    for value in data[field].tolist():
        if _is_missing(value):
            count += 1
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            count += 1
            continue
        if allow_zero:
            if number < 0:
                count += 1
        elif number <= 0:
            count += 1
    return count


def _invalid_status_count(pipes: gpd.GeoDataFrame) -> int:
    if "status" not in pipes.columns:
        return len(pipes)
    valid_statuses = {"OPEN", "CLOSED", "CV"}
    return sum(
        1
        for value in pipes["status"].tolist()
        if _is_missing(value) or str(value).strip().upper() not in valid_statuses
    )


def _is_missing(value: Any) -> bool:
    if value is None or value is pd.NA:
        return True
    try:
        return bool(pd.isna(value))
    except TypeError:
        return False
