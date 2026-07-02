"""GIS output writers for review in QGIS."""

from __future__ import annotations

from pathlib import Path

import fiona
import geopandas as gpd


WORKING_GPKG_LAYERS = (
    "pipes_raw",
    "pipes_clean_auto",
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

_RESERVED_ATTRIBUTE_NAMES = {"geom", "geometry", "fid"}


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
    export_pipes = _sanitize_for_geopackage(pipes)
    export_pipes.to_file(output_path, layer=layer_name, driver="GPKG")
    return output_path


def write_working_geopackage(
    pipes_raw: gpd.GeoDataFrame,
    outdir: str | Path,
    name: str,
    pipes_clean_auto: gpd.GeoDataFrame | None = None,
) -> Path:
    """Write the standard working GeoPackage used by downstream EPANET steps.

    `pipes_clean_auto` stores the automatic normalization result. `pipes_clean`
    is initialized as an editable copy of `pipes_clean_auto` so the user can make
    manual corrections in QGIS before junction/connectivity generation.
    """
    gis_dir = Path(outdir) / "gis"
    gis_dir.mkdir(parents=True, exist_ok=True)

    output_path = gis_dir / f"{name}_working.gpkg"
    export_raw = _sanitize_for_geopackage(pipes_raw)
    export_raw.to_file(output_path, layer="pipes_raw", driver="GPKG")

    if pipes_clean_auto is not None:
        export_clean_auto = _sanitize_for_geopackage(pipes_clean_auto)
        export_clean_auto.to_file(output_path, layer="pipes_clean_auto", driver="GPKG")
        export_clean_auto.to_file(output_path, layer="pipes_clean", driver="GPKG")
        empty_line_layers: set[str] = set()
    else:
        empty_line_layers = {"pipes_clean_auto", "pipes_clean"}

    layer_geometry_types = {
        "junctions": "Point",
        "reservoirs": "Point",
        "tanks": "Point",
        "pumps": "Point",
        "valves": "Point",
        "demands": "Point",
        "sectors": "Polygon",
        "topology_errors": "Point",
        "topology_report": "Point",
    }

    crs_wkt = pipes_raw.crs.to_wkt() if pipes_raw.crs is not None else None
    for layer_name in empty_line_layers:
        _create_empty_layer(
            output_path=output_path,
            layer_name=layer_name,
            geometry_type="LineString",
            crs_wkt=crs_wkt,
        )
    for layer_name, geometry_type in layer_geometry_types.items():
        _create_empty_layer(
            output_path=output_path,
            layer_name=layer_name,
            geometry_type=geometry_type,
            crs_wkt=crs_wkt,
        )

    return output_path


def _sanitize_for_geopackage(data: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return a copy with attribute names safe for GeoPackage export.

    Some source layers contain fields such as `geom`, which conflicts with the
    geometry column name used internally by the GeoPackage driver. The original
    input data is preserved; only the exported copy is renamed.
    """
    sanitized = data.copy()
    geometry_column = sanitized.geometry.name
    rename_map: dict[str, str] = {}
    existing_names = set(sanitized.columns)

    for column in sanitized.columns:
        if column == geometry_column:
            continue
        if column.lower() in _RESERVED_ATTRIBUTE_NAMES:
            new_name = _unique_column_name(f"source_{column}", existing_names)
            rename_map[column] = new_name
            existing_names.add(new_name)

    if rename_map:
        sanitized = sanitized.rename(columns=rename_map)
    return sanitized


def _unique_column_name(base_name: str, existing_names: set[str]) -> str:
    candidate = base_name
    counter = 1
    while candidate in existing_names:
        candidate = f"{base_name}_{counter}"
        counter += 1
    return candidate


def _create_empty_layer(
    output_path: Path,
    layer_name: str,
    geometry_type: str,
    crs_wkt: str | None,
) -> None:
    schema = {
        "geometry": geometry_type,
        "properties": {
            "id": "str",
            "status": "str",
            "code": "str",
            "message": "str",
            "notes": "str",
        },
    }
    with fiona.open(
        output_path,
        mode="w",
        driver="GPKG",
        layer=layer_name,
        schema=schema,
        crs_wkt=crs_wkt,
    ):
        pass
