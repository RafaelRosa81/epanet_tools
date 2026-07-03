"""Topology cleaning tools for pipe layers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import substring


@dataclass(frozen=True)
class CleaningReport:
    """Summary of a topology cleaning operation."""

    feature_count: int
    snapped_endpoint_count: int
    snap_group_count: int
    endpoint_to_segment_snap_count: int = 0
    split_pipe_count: int = 0
    output_feature_count: int | None = None
    connection_split_point_count: int = 0


def normalize_pipe_topology(
    pipes: gpd.GeoDataFrame,
    tolerance_m: float,
) -> tuple[gpd.GeoDataFrame, CleaningReport]:
    """Normalize pipe topology using hydraulic endpoint-connection rules."""
    endpoint_cleaned, endpoint_report = snap_pipe_endpoints(pipes, tolerance_m=tolerance_m)
    if tolerance_m <= 0:
        report = CleaningReport(
            feature_count=len(pipes),
            snapped_endpoint_count=0,
            snap_group_count=0,
            output_feature_count=len(endpoint_cleaned),
        )
        return endpoint_cleaned, report

    segment_cleaned, segment_snap_count, snap_split_points = _snap_endpoints_to_segments(
        endpoint_cleaned,
        tolerance_m=tolerance_m,
    )
    connection_split_points = _collect_endpoint_connection_split_points(
        segment_cleaned,
        tolerance_m=tolerance_m,
    )
    all_split_points = _merge_split_points(snap_split_points, connection_split_points)
    split_cleaned, split_pipe_count = _split_pipes_at_points(segment_cleaned, all_split_points)

    report = CleaningReport(
        feature_count=len(pipes),
        snapped_endpoint_count=endpoint_report.snapped_endpoint_count,
        snap_group_count=endpoint_report.snap_group_count,
        endpoint_to_segment_snap_count=segment_snap_count,
        split_pipe_count=split_pipe_count,
        output_feature_count=len(split_cleaned),
        connection_split_point_count=sum(len(points) for points in connection_split_points.values()),
    )
    return split_cleaned, report


def snap_pipe_endpoints(
    pipes: gpd.GeoDataFrame,
    tolerance_m: float,
) -> tuple[gpd.GeoDataFrame, CleaningReport]:
    """Snap pipe endpoints that fall within a tolerance."""
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
    spatial_index = cleaned.sindex

    for row_index, endpoint_position, point in endpoints:
        best_target_index: object | None = None
        best_projected_point: Point | None = None
        best_distance = tolerance_m

        candidate_positions = spatial_index.query(point.buffer(tolerance_m), predicate="intersects")
        for target_pos in candidate_positions:
            target_index = cleaned.index[int(target_pos)]
            if target_index == row_index:
                continue
            target_geom = cleaned.at[target_index, geometry_column]
            if not isinstance(target_geom, LineString) or target_geom.is_empty:
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


def _collect_endpoint_connection_split_points(
    pipes: gpd.GeoDataFrame,
    tolerance_m: float,
) -> dict[object, list[Point]]:
    """Collect target-pipe split points implied by endpoints on pipe interiors."""
    geometry_column = pipes.geometry.name
    endpoints = _collect_linestring_endpoints(pipes)
    split_points: dict[object, list[Point]] = {}
    endpoint_tolerance = max(tolerance_m, 1e-8)
    spatial_index = pipes.sindex

    for source_index, _, endpoint in endpoints:
        candidate_positions = spatial_index.query(endpoint.buffer(endpoint_tolerance), predicate="intersects")
        for target_pos in candidate_positions:
            target_index = pipes.index[int(target_pos)]
            if source_index == target_index:
                continue
            target_geom = pipes.at[target_index, geometry_column]
            if not isinstance(target_geom, LineString) or target_geom.is_empty:
                continue
            projected_distance = target_geom.project(endpoint)
            if _is_at_line_endpoint(target_geom, projected_distance, 1e-8):
                continue
            projected_point = target_geom.interpolate(projected_distance)
            if endpoint.distance(projected_point) <= endpoint_tolerance:
                split_points.setdefault(target_index, []).append(projected_point)

    return split_points


def _merge_split_points(
    *split_point_groups: dict[object, list[Point]],
) -> dict[object, list[Point]]:
    merged: dict[object, list[Point]] = {}
    for split_points in split_point_groups:
        for row_index, points in split_points.items():
            merged.setdefault(row_index, []).extend(points)
    return merged


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
    distances = _unique_split_distances(line, points)
    if not distances:
        return [line]

    cut_distances = [0.0, *distances, float(line.length)]
    pieces: list[LineString] = []
    for start, end in zip(cut_distances, cut_distances[1:], strict=False):
        if end - start <= 1e-8:
            continue
        piece = substring(line, start, end)
        if isinstance(piece, LineString) and piece.length > 0:
            pieces.append(piece)
    return pieces or [line]


def _unique_split_distances(line: LineString, points: list[Point]) -> list[float]:
    distances: list[float] = []
    seen: set[float] = set()
    for point in points:
        projected_distance = line.project(point)
        if _is_at_line_endpoint(line, projected_distance, 1e-8):
            continue
        projected_point = line.interpolate(projected_distance)
        if point.distance(projected_point) > 1e-6:
            continue
        key = round(projected_distance, 8)
        if key in seen:
            continue
        seen.add(key)
        distances.append(float(projected_distance))
    return sorted(distances)


def _collect_linestring_endpoints(
    pipes: gpd.GeoDataFrame,
) -> list[tuple[object, str, Point]]:
    endpoints: list[tuple[object, str, Point]] = []
    geometry_column = pipes.geometry.name
    for idx, geom in pipes[geometry_column].items():
        if isinstance(geom, LineString) and not geom.is_empty:
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
    """Group nearby endpoints using a spatial index instead of all-pairs checks."""
    if not endpoints:
        return []
    endpoint_gdf = gpd.GeoDataFrame(
        {"endpoint_id": list(range(len(endpoints)))},
        geometry=[record[2] for record in endpoints],
    )
    spatial_index = endpoint_gdf.sindex
    parent = list(range(len(endpoints)))

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: int, right: int) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for i, (_, _, point) in enumerate(endpoints):
        candidate_positions = spatial_index.query(point.buffer(tolerance_m), predicate="intersects")
        for candidate_pos in candidate_positions:
            j = int(candidate_pos)
            if i >= j:
                continue
            if point.distance(endpoints[j][2]) <= tolerance_m:
                union(i, j)

    grouped_ids: dict[int, list[int]] = {}
    for i in range(len(endpoints)):
        grouped_ids.setdefault(find(i), []).append(i)

    return [[endpoints[i] for i in ids] for ids in grouped_ids.values() if len(ids) > 1]


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
    if len(current_coord) <= 2:
        return (replacement.x, replacement.y)
    return (replacement.x, replacement.y, *current_coord[2:])


def _is_at_line_endpoint(line: LineString, projected_distance: float, tolerance_m: float) -> bool:
    return projected_distance <= tolerance_m or line.length - projected_distance <= tolerance_m
