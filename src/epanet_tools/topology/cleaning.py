"""Topology cleaning tools for pipe layers."""

from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, Point


@dataclass(frozen=True)
class CleaningReport:
    """Summary of a topology cleaning operation."""

    feature_count: int
    snapped_endpoint_count: int
    snap_group_count: int


def snap_pipe_endpoints(
    pipes: gpd.GeoDataFrame,
    tolerance_m: float,
) -> tuple[gpd.GeoDataFrame, CleaningReport]:
    """Snap pipe endpoints that fall within a tolerance.

    Only first and last coordinates of LineString geometries are moved. Interior
    vertices are preserved. MultiLineString geometries are currently left
    unchanged because they must be explicitly normalized before topology building.
    """
    if tolerance_m <= 0:
        cleaned = pipes.copy()
        return cleaned, CleaningReport(len(cleaned), 0, 0)

    cleaned = pipes.copy()
    endpoint_records = _collect_linestring_endpoints(cleaned)
    groups = _build_endpoint_groups(endpoint_records, tolerance_m)
    replacements = _endpoint_replacements(groups)

    snapped_count = 0
    for row_index, endpoint_position, replacement in replacements:
        geom = cleaned.at[row_index, cleaned.geometry.name]
        if not isinstance(geom, LineString):
            continue
        new_geom = _replace_endpoint(geom, endpoint_position, replacement)
        if new_geom is not geom:
            cleaned.at[row_index, cleaned.geometry.name] = new_geom
            snapped_count += 1

    report = CleaningReport(
        feature_count=len(cleaned),
        snapped_endpoint_count=snapped_count,
        snap_group_count=len(groups),
    )
    return cleaned, report


def _collect_linestring_endpoints(
    pipes: gpd.GeoDataFrame,
) -> list[tuple[object, str, Point]]:
    endpoints: list[tuple[object, str, Point]] = []
    geometry_column = pipes.geometry.name
    for idx, geom in pipes[geometry_column].items():
        if isinstance(geom, LineString):
            coords = list(geom.coords)
            if len(coords) < 2:
                continue
            endpoints.append((idx, "start", Point(coords[0])))
            endpoints.append((idx, "end", Point(coords[-1])))
        elif isinstance(geom, MultiLineString):
            continue
    return endpoints


def _build_endpoint_groups(
    endpoints: list[tuple[object, str, Point]],
    tolerance_m: float,
) -> list[list[tuple[object, str, Point]]]:
    groups: list[list[tuple[object, str, Point]]] = []
    used: set[int] = set()

    for i, endpoint in enumerate(endpoints):
        if i in used:
            continue
        group = [endpoint]
        used.add(i)
        changed = True
        while changed:
            changed = False
            for j, candidate in enumerate(endpoints):
                if j in used:
                    continue
                if any(candidate[2].distance(member[2]) <= tolerance_m for member in group):
                    group.append(candidate)
                    used.add(j)
                    changed = True
        if len(group) > 1:
            groups.append(group)
    return groups


def _endpoint_replacements(
    groups: list[list[tuple[object, str, Point]]],
) -> list[tuple[object, str, Point]]:
    replacements: list[tuple[object, str, Point]] = []
    for group in groups:
        x = sum(endpoint[2].x for endpoint in group) / len(group)
        y = sum(endpoint[2].y for endpoint in group) / len(group)
        replacement = Point(x, y)
        for row_index, endpoint_position, point in group:
            if not point.equals_exact(replacement, tolerance=0.0):
                replacements.append((row_index, endpoint_position, replacement))
    return replacements


def _replace_endpoint(geom: LineString, endpoint_position: str, replacement: Point) -> LineString:
    coords = list(geom.coords)
    endpoint_index = 0 if endpoint_position == "start" else -1
    current_coord = coords[endpoint_index]
    new_coord = _replacement_coordinate(current_coord, replacement)

    if current_coord == new_coord:
        return geom

    coords[endpoint_index] = new_coord
    return LineString(coords)


def _replacement_coordinate(current_coord: tuple[float, ...], replacement: Point) -> tuple[float, ...]:
    """Create a replacement coordinate preserving extra dimensions such as Z."""
    if len(current_coord) <= 2:
        return (replacement.x, replacement.y)
    return (replacement.x, replacement.y, *current_coord[2:])
