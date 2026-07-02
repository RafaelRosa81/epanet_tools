"""Build hydraulic connectivity from cleaned pipe geometries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, Point

from epanet_tools.topology.identifiers import make_sequential_id


@dataclass(frozen=True)
class ConnectivityReport:
    """Summary of node/link connectivity construction."""

    pipe_count: int
    junction_count: int
    skipped_geometry_count: int


def build_junctions_and_connectivity(
    pipes: gpd.GeoDataFrame,
    node_prefix: str = "J",
    pipe_prefix: str = "P",
    coordinate_precision: int = 6,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, ConnectivityReport]:
    """Create junctions and from/to node attributes from a cleaned pipe layer.

    Parameters
    ----------
    pipes:
        Cleaned pipe layer. Only LineString geometries are converted to links.
    node_prefix:
        Prefix used for generated junction IDs.
    pipe_prefix:
        Prefix used for generated pipe IDs.
    coordinate_precision:
        Decimal precision used to group coincident endpoints.
    """
    geometry_column = pipes.geometry.name
    node_lookup: dict[tuple[float, float], str] = {}
    node_records: list[dict[str, Any]] = []
    pipe_records: list[dict[str, Any]] = []
    skipped_count = 0

    for _, row in pipes.iterrows():
        geom = row[geometry_column]
        if isinstance(geom, MultiLineString):
            skipped_count += 1
            continue
        if not isinstance(geom, LineString) or geom.is_empty or geom.length <= 0:
            skipped_count += 1
            continue

        coords = list(geom.coords)
        from_node = _node_id_for_coordinate(
            coords[0],
            node_lookup,
            node_records,
            node_prefix,
            coordinate_precision,
        )
        to_node = _node_id_for_coordinate(
            coords[-1],
            node_lookup,
            node_records,
            node_prefix,
            coordinate_precision,
        )

        pipe_record = row.to_dict()
        pipe_record[geometry_column] = geom
        pipe_record["pipe_id"] = make_sequential_id(pipe_prefix, len(pipe_records) + 1)
        pipe_record["from_node"] = from_node
        pipe_record["to_node"] = to_node
        pipe_record["length_m"] = float(geom.length)
        pipe_records.append(pipe_record)

    pipes_with_connectivity = gpd.GeoDataFrame(
        pipe_records,
        geometry=geometry_column,
        crs=pipes.crs,
    )
    junctions = gpd.GeoDataFrame(node_records, geometry="geometry", crs=pipes.crs)
    report = ConnectivityReport(
        pipe_count=len(pipes_with_connectivity),
        junction_count=len(junctions),
        skipped_geometry_count=skipped_count,
    )
    return pipes_with_connectivity.reset_index(drop=True), junctions.reset_index(drop=True), report


def _node_id_for_coordinate(
    coordinate: tuple[float, ...],
    node_lookup: dict[tuple[float, float], str],
    node_records: list[dict[str, Any]],
    node_prefix: str,
    coordinate_precision: int,
) -> str:
    key = (round(coordinate[0], coordinate_precision), round(coordinate[1], coordinate_precision))
    existing = node_lookup.get(key)
    if existing is not None:
        return existing

    node_id = make_sequential_id(node_prefix, len(node_records) + 1)
    node_lookup[key] = node_id
    node_records.append(
        {
            "node_id": node_id,
            "x": float(coordinate[0]),
            "y": float(coordinate[1]),
            "elevation_m": None,
            "geometry": Point(coordinate[0], coordinate[1]),
        }
    )
    return node_id
