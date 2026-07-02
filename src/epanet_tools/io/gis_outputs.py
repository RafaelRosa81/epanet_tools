"""GIS output writers for review in QGIS."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd


WORKING_GPKG_LAYERS = (
    "pipes_raw",
    "pipes_clean",
    "junctions",
    "reservoirs",
    "tanks",
    "pumps",
    "valves",
    "demands",
    "sectors",
    "topology_errors",
    "topology_report",
)


def write_combined_pipe_layer(
    pipes: gpd.GeoDataFrame,
    outdir: str | Path,
    name: str,
    layer_name: str = "pipes_combined",
) -> Path:
    """Write the combined pipe layer to a GeoPackage for QGIS review."""
    gis_dir = Path(outdir) / "gis"
    gis_dir.mkdir(parents=True, exist_ok=True)

    output_path = gis_dir / f"{name}_network.gpkg"
    pipes.to_file(output_path, layer=layer_name, driver="GPKG")
    return output_path


def write_working_geopackage(
    pipes_raw: gpd.GeoDataFrame,
    outdir: str | Path,
    name: str,
) -> Path:
    """Write the standard working GeoPackage used by downstream EPANET steps.

    The current implementation stores `pipes_raw` and creates empty placeholder
    layers for the planned processing stages. Future workflow steps will fill
    these layers progressively without modifying the original source files.
    """
    gis_dir = Path(outdir) / "gis"
    gis_dir.mkdir(parents=True, exist_ok=True)

    output_path = gis_dir / f"{name}_working.gpkg"
    pipes_raw.to_file(output_path, layer="pipes_raw", driver="GPKG")

    line_layers = {"pipes_clean"}
    point_layers = {"junctions", "reservoirs", "tanks", "pumps", "valves", "demands"}
    polygon_layers = {"sectors"}
    table_layers = {"topology_report"}

    for layer_name in WORKING_GPKG_LAYERS:
        if layer_name == "pipes_raw":
            continue
        if layer_name in line_layers:
            _empty_geodataframe(pipes_raw.crs, "LineString").to_file(
                output_path,
                layer=layer_name,
                driver="GPKG",
            )
        elif layer_name in point_layers:
            _empty_geodataframe(pipes_raw.crs, "Point").to_file(
                output_path,
                layer=layer_name,
                driver="GPKG",
            )
        elif layer_name in polygon_layers:
            _empty_geodataframe(pipes_raw.crs, "Polygon").to_file(
                output_path,
                layer=layer_name,
                driver="GPKG",
            )
        elif layer_name == "topology_errors":
            _empty_geodataframe(pipes_raw.crs, "Point").to_file(
                output_path,
                layer=layer_name,
                driver="GPKG",
            )
        elif layer_name in table_layers:
            _empty_table().to_file(output_path, layer=layer_name, driver="GPKG")

    return output_path


def _empty_geodataframe(crs: object, geometry_type: str) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "id": pd.Series(dtype="str"),
            "status": pd.Series(dtype="str"),
            "notes": pd.Series(dtype="str"),
        },
        geometry=gpd.GeoSeries([], crs=crs),
        crs=crs,
    ).set_geometry("geometry")


def _empty_table() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "issue_id": pd.Series(dtype="str"),
            "severity": pd.Series(dtype="str"),
            "code": pd.Series(dtype="str"),
            "message": pd.Series(dtype="str"),
            "element_id": pd.Series(dtype="str"),
        },
        geometry=gpd.GeoSeries([], crs=None),
    )
