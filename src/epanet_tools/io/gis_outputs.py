"""GIS output writers for review in QGIS."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd


def write_combined_pipe_layer(
    pipes: gpd.GeoDataFrame,
    outdir: str | Path,
    name: str,
    layer_name: str = "pipes_combined",
) -> Path:
    """Write the combined pipe layer to a GeoPackage for QGIS review.

    Parameters
    ----------
    pipes:
        Combined pipe GeoDataFrame.
    outdir:
        Output directory root.
    name:
        Run/model name used as filename prefix.
    layer_name:
        GeoPackage layer name.
    """
    gis_dir = Path(outdir) / "gis"
    gis_dir.mkdir(parents=True, exist_ok=True)

    output_path = gis_dir / f"{name}_network.gpkg"
    pipes.to_file(output_path, layer=layer_name, driver="GPKG")
    return output_path
