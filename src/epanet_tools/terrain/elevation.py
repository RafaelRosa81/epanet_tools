"""Elevation sampling utilities for hydraulic nodes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import rasterio
from pyproj import CRS, Transformer
from pyproj.exceptions import ProjError

from epanet_tools.exceptions import ConfigurationError


@dataclass(frozen=True)
class ElevationSamplingReport:
    """Summary of DEM sampling for junction elevations."""

    node_count: int
    sampled_count: int
    missing_count: int
    dem_crs: str | None


def sample_junction_elevations(
    junctions: gpd.GeoDataFrame,
    dem_path: str | Path | None,
    elevation_field: str = "elevation_m",
    dem_crs_override: str | int | None = None,
) -> tuple[gpd.GeoDataFrame, ElevationSamplingReport]:
    """Sample DEM elevation at each junction point.

    If ``dem_path`` is ``None`` or empty, the input junctions are returned with an
    empty/unchanged elevation field and a report with zero sampled nodes.
    """
    sampled = junctions.copy()
    if elevation_field not in sampled.columns:
        sampled[elevation_field] = None

    if dem_path in (None, ""):
        report = ElevationSamplingReport(
            node_count=len(sampled),
            sampled_count=0,
            missing_count=len(sampled),
            dem_crs=None,
        )
        return sampled, report

    raster_path = Path(str(dem_path))
    if not raster_path.exists():
        msg = f"DEM path does not exist: {raster_path}"
        raise FileNotFoundError(msg)

    with rasterio.open(raster_path) as dataset:
        dem_crs = _resolve_dem_crs(dataset.crs, dem_crs_override)
        transformer = _coordinate_transformer(sampled, dem_crs)
        coords = [_point_coordinate(point, transformer) for point in sampled.geometry]
        values = list(dataset.sample(coords, indexes=1, masked=True))
        elevations: list[float | None] = []
        sampled_count = 0
        for value in values:
            if value is None or value[0] is None:
                elevations.append(None)
                continue
            scalar = value[0]
            if hasattr(scalar, "mask") and bool(scalar.mask):
                elevations.append(None)
                continue
            elevations.append(float(scalar))
            sampled_count += 1

        sampled[elevation_field] = elevations
        report = ElevationSamplingReport(
            node_count=len(sampled),
            sampled_count=sampled_count,
            missing_count=len(sampled) - sampled_count,
            dem_crs=dem_crs.to_string() if dem_crs is not None else None,
        )
        return sampled, report


def _resolve_dem_crs(dataset_crs: Any, dem_crs_override: str | int | None) -> CRS | None:
    if dem_crs_override not in (None, ""):
        return CRS.from_user_input(dem_crs_override)
    if dataset_crs is None:
        return None
    try:
        return CRS.from_user_input(dataset_crs)
    except ProjError as exc:
        msg = (
            "DEM CRS could not be interpreted. Define inputs.dem_crs explicitly "
            "in the YAML, for example dem_crs: EPSG:32719."
        )
        raise ConfigurationError(msg) from exc


def _coordinate_transformer(
    junctions: gpd.GeoDataFrame,
    dem_crs: CRS | None,
) -> Transformer | None:
    if junctions.crs is None or dem_crs is None:
        return None
    junction_crs = CRS.from_user_input(junctions.crs)
    if junction_crs == dem_crs:
        return None
    try:
        return Transformer.from_crs(junction_crs, dem_crs, always_xy=True)
    except ProjError as exc:
        msg = (
            "Could not transform junction coordinates to DEM CRS. If the DEM CRS "
            "is wrong or ambiguous, define inputs.dem_crs explicitly in the YAML."
        )
        raise ConfigurationError(msg) from exc


def _point_coordinate(point: object, transformer: Transformer | None) -> tuple[float, float]:
    x = float(point.x)  # type: ignore[attr-defined]
    y = float(point.y)  # type: ignore[attr-defined]
    if transformer is None:
        return x, y
    transformed_x, transformed_y = transformer.transform(x, y)
    return float(transformed_x), float(transformed_y)
