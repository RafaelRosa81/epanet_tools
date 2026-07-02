"""Post-normalization topology review utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import geopandas as gpd
import networkx as nx
from shapely.geometry import LineString, Point


@dataclass(frozen=True)
class TopologyReviewReport:
    """Summary of topology review checks."""

    pipe_count: int
    junction_count: int
    free_endpoint_count: int
    disconnected_component_count: int
    short_pipe_count: int
    possible_unconnected_crossing_count: int
    issue_count: int


def review_normalized_topology(
    pipes: gpd.GeoDataFrame,
    junctions: gpd.GeoDataFrame,
    min_pipe_length_m: float = 0.05,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, TopologyReviewReport]:
    """Create GIS review layers for a normalized EPANET network."""
    error_records: list[dict[str, Any]] = []
    report_records: list[dict[str, Any]] = []

    graph = nx.Graph()
    if "node_id" in junctions.columns:
        graph.add_nodes_from(str(value) for value in junctions["node_id"].tolist())
    if {"from_node", "to_node"}.issubset(pipes.columns):
        for _, row in pipes.iterrows():
            graph.add_edge(str(row["from_node"]), str(row["to_node"]))

    disconnected_component_count = nx.number_connected_components(graph) if graph.number_of_nodes() else 0
    component_lookup = _component_lookup(graph)

    short_pipe_count = 0
    for _, row in pipes.iterrows():
        geom = row.geometry
        if not isinstance(geom, LineString):
            continue
        pipe_id = str(row.get("pipe_id", ""))
        if geom.length < min_pipe_length_m:
            short_pipe_count += 1
            midpoint = geom.interpolate(0.5, normalized=True)
            error_records.append(
                _issue_record(
                    code="SHORT_PIPE",
                    severity="warning",
                    message=f"Pipe length is below {min_pipe_length_m} m.",
                    pipe_id=pipe_id,
                    node_id="",
                    geometry=midpoint,
                )
            )

    node_degree = dict(graph.degree())
    free_endpoint_count = 0
    for _, row in junctions.iterrows():
        node_id = str(row.get("node_id", ""))
        degree = int(node_degree.get(node_id, 0))
        if degree <= 1:
            free_endpoint_count += 1
            error_records.append(
                _issue_record(
                    code="FREE_ENDPOINT",
                    severity="info",
                    message="Junction has one or zero connected pipes.",
                    pipe_id="",
                    node_id=node_id,
                    geometry=row.geometry,
                )
            )
        report_records.append(
            {
                "id": node_id,
                "status": "ok" if degree > 1 else "review",
                "code": "NODE_DEGREE",
                "message": f"degree={degree}; component={component_lookup.get(node_id, -1)}",
                "notes": "",
                "geometry": row.geometry,
            }
        )

    possible_unconnected_crossing_count = _append_possible_crossing_issues(
        pipes,
        junctions,
        error_records,
    )

    errors = gpd.GeoDataFrame(error_records, geometry="geometry", crs=pipes.crs)
    topology_report = gpd.GeoDataFrame(report_records, geometry="geometry", crs=pipes.crs)
    report = TopologyReviewReport(
        pipe_count=len(pipes),
        junction_count=len(junctions),
        free_endpoint_count=free_endpoint_count,
        disconnected_component_count=disconnected_component_count,
        short_pipe_count=short_pipe_count,
        possible_unconnected_crossing_count=possible_unconnected_crossing_count,
        issue_count=len(error_records),
    )
    return errors, topology_report, report


def _component_lookup(graph: nx.Graph) -> dict[str, int]:
    lookup: dict[str, int] = {}
    for component_id, nodes in enumerate(nx.connected_components(graph), start=1):
        for node in nodes:
            lookup[str(node)] = component_id
    return lookup


def _append_possible_crossing_issues(
    pipes: gpd.GeoDataFrame,
    junctions: gpd.GeoDataFrame,
    error_records: list[dict[str, Any]],
) -> int:
    junction_points = list(junctions.geometry)
    pipe_items = [
        (str(row.get("pipe_id", "")), row.geometry)
        for _, row in pipes.iterrows()
        if isinstance(row.geometry, LineString)
    ]
    count = 0
    for left_pos, (left_id, left_geom) in enumerate(pipe_items):
        for right_id, right_geom in pipe_items[left_pos + 1 :]:
            intersection = left_geom.intersection(right_geom)
            if not isinstance(intersection, Point):
                continue
            if _point_matches_any_junction(intersection, junction_points):
                continue
            if _point_is_endpoint(left_geom, intersection) or _point_is_endpoint(right_geom, intersection):
                continue
            count += 1
            error_records.append(
                _issue_record(
                    code="POSSIBLE_UNCONNECTED_CROSSING",
                    severity="info",
                    message=(
                        "Two pipes cross without a junction. This may be correct "
                        "if they only cross visually."
                    ),
                    pipe_id=f"{left_id};{right_id}",
                    node_id="",
                    geometry=intersection,
                )
            )
    return count


def _point_matches_any_junction(point: Point, junction_points: list[object]) -> bool:
    return any(isinstance(junction, Point) and point.distance(junction) <= 1e-8 for junction in junction_points)


def _point_is_endpoint(line: LineString, point: Point) -> bool:
    coords = list(line.coords)
    return Point(coords[0]).distance(point) <= 1e-8 or Point(coords[-1]).distance(point) <= 1e-8


def _issue_record(
    code: str,
    severity: str,
    message: str,
    pipe_id: str,
    node_id: str,
    geometry: Point,
) -> dict[str, Any]:
    return {
        "id": f"{code}_{pipe_id}_{node_id}",
        "status": severity,
        "code": code,
        "message": message,
        "notes": f"pipe_id={pipe_id}; node_id={node_id}",
        "pipe_id": pipe_id,
        "node_id": node_id,
        "geometry": geometry,
    }
