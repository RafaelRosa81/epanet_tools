"""Topology cleaning tools for pipe layers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import split


@dataclass(frozen=True)
class CleaningReport:
    """Summary of a topology cleaning operation."""

    feature_count: int
    snapped_endpoint_count: int
    snap_group_count: int
    endpoint_to_segment_snap_count: int = 0
    split_pipe_count: int = 0
    output_feature_count: int | None = None


def normalize_pipe_topology(
    pipes: gpd.GeoDataFrame,
    tolerance_m: float,
) -> tuple[gpd.GeoDataFrame, CleaningReport]:
    """Normalize pipe topology for EPANET-oriented workflows.

    Current stages:

    1. Snap near endpoints to a common point.
    2. Snap endpoints near the interior of another pipe onto that pipe.
    3. Split target pipes at the new connection points.
    """
    endpoint_cleaned, endpoint_report = snap_pipe_endpoints(pipes, tolerance_m=tolerance_m)
    if tolerance_m <= 0:
        report = CleaningReport(
            feature_count=len(pipes),
            snapped_endpoint_count=0,
            snap_group_count=0,
            output_feature_count=len(endpoint_cleaned),
        )
        return endpoint_cleaned, report

    segment_cleaned, segment_snap_count, split_points = _snap_endpoints_to_segments(
        endpoint_cleaned,
        tolerance_m=tolerance_m,
    )
    split_cleaned, split_pipe_count = _split_pipes_at_points(segment_cleaned, split_points)

    report = CleaningReport(
        feature_count=len(pipes),
        snapped_endpoint_count=endpoint_report.snapped_endpoint_count,
        snap_group_count=endpoint_report.snap_group_count,
        endpoint_to_segment_snap_count=segment_snap_count,
        split_pipe_count=split_pipe_count,
        output_feature_count=len(split_cleaned),
    )
    return split_cleaned, report


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
        return cleaned, CleaningReport(len(cleaned), 0, 0, output_feature_count=len(cleaned))

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
        output_feature_count=len(cleaned),
    )
    return cleaned, report


def _snap_endpoints_to_segments(
    pipes: gpd.GeoDataFrame,
    tolerance_m: float,
) -> tuple[gpd.GeoDataFrame, int, dict[object, list[Point]]]:
    cleaned = pipes.copy()
    geometry_column = cleaned.geometry.name
    endpoints = _collect_linestring_endpoints(cleaned)
    split_points: dict[object, list[Point]] = {}
    snap_count = 0

    for row_index, endpoint_position, point in endpoints:
        best_target_index: object | None = None
        best_projected_point: Point | None = None
        best_distance = tolerance_m

        for target_index, target_geom in cleaned[geometry_column].items():
            if target_index == row_index or not isinstance(target_geom, LineString):
                continue
            projected_distance = target_geom.project(point)
            if _is_at_line_endpoint(target_geom, projected_distance, tolerance_m):
                continue
            projected_point = target_geom.interpolate(projected_distance)
            distance = point.distance(projected_point)
            if distance <= best_distance:
                best_distance = distance
                best_target_index = target_index
                best_projected_point = projected_point

        if best_target_index is None or best_projected_point is None:
            continue

        geom = cleaned.at[row_index, geometry_column]
        if not isinstance(geom, LineString):
            continue
        new_geom = _replace_endpoint(geom, endpoint_position, best_projected_point)
        if new_geom is not geom:
            cleaned.at[row_index, geometry_column] = new_geom
            split_points.setdefault(best_target_index, []).append(best_projected_point)
            snap_count += 1

    return cleaned, snap_count, split_points


def _split_pipes_at_points(
    pipes: gpd.GeoDataFrame,
    split_points: dict[object, list[Point]],
) -> tuple[gpd.GeoDataFrame, int]:
    if not split_points:
        return pipes.copy(), 0

    records: list[dict[str, Any]] = []
    geometry_column = pipes.geometry.name
    split_pipe_count = 0

    for row_index, row in pipes.iterrows():
        geom = row[geometry_column]
        if row_index not in split_points or not isinstance(geom, LineString):
            records.append(row.to_dict())
            continue

        pieces = _split_line_at_points(geom, split_points[row_index])
        if len(pieces) <= 1:
            records.append(row.to_dict())
            continue

        split_pipe_count += 1
        for part_number, piece in enumerate(pieces, start=1):
            new_record = row.to_dict()
            new_record[geometry_column] = piece
            new_record["_split_from_index"] = str(row_index)
            new_record["_split_part"] = part_number
            records.append(new_record)

    result = gpd.GeoDataFrame(records, geometry=geometry_column, crs=pipes.crs)
    return result.reset_index(drop=True), split_pipe_count


def _split_line_at_points(line: LineString, points: list[Point]) -> list[LineString]:
    pieces = [line]
    unique_points = _unique_points_on_line(line, points)
    for point in unique_points:
        next_pieces: list[LineString] = []
        for piece in pieces:
            if piece.distance(point) > 1e-8 or _point_is_at_piece_endpoint(piece, point):
                next_pieces.append(piece)
                continue
            split_result = split(piece, point)
            next_pieces.extend([geom for geom in split_result.geoms if isinstance(geom, LineString)])
        pieces = next_pieces
    return [piece for piece in pieces if piece.length > 0]


def _unique_points_on_line(line: LineString, points: list[Point]) -> list[Point]:
    seen_distances: set[float] = set()
    unique: list[Point] = []
    for point in points:
        projected_distance = round(line.project(point), 8)
        if projected_distance in seen_distances:
            continue
        if _is_at_line_endpoint(line, projected_distance, 1e-8):
            continue
        seen_distances.add(projected_distance)
        unique.append(line.interpolate(projected_distance))
    return unique


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


def _is_at_line_endpoint(line: LineString, projected_distance: float, tolerance_m: float) -> bool:
    return projected_distance <= tolerance_m or line.length - projected_distance <= tolerance_m


def _point_is_at_piece_endpoint(line: LineString, point: Point) -> bool:
    coords = list(line.coords)
    return Point(coords[0]).distance(point) <= 1e-8 or Point(coords[-1]).distance(point) <= 1e-8
