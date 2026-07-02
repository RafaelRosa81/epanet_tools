"""Vector GIS readers used by EPANET workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from epanet_tools.exceptions import ConfigurationError


def read_pipe_layer(path: str | Path, layer: str | None = None, **kwargs: Any) -> gpd.GeoDataFrame:
    """Read one pipe vector layer as a GeoDataFrame."""
    vector_path = Path(path)
    if not vector_path.exists():
        msg = f"Pipe layer path does not exist: {vector_path}"
        raise FileNotFoundError(msg)

    read_kwargs: dict[str, Any] = dict(kwargs)
    if layer is not None:
        read_kwargs["layer"] = layer

    pipes = gpd.read_file(vector_path, **read_kwargs)
    if pipes.empty:
        msg = f"Pipe layer is empty: {vector_path}"
        raise ConfigurationError(msg)
    return pipes


def read_pipe_layers(pipe_inputs: list[dict[str, Any]]) -> gpd.GeoDataFrame:
    """Read and combine several pipe layers.

    The original files are not modified. The returned GeoDataFrame keeps traceability
    columns for the source path, source layer and original feature index.
    """
    if not pipe_inputs:
        msg = "At least one pipe input is required."
        raise ConfigurationError(msg)

    loaded_layers: list[gpd.GeoDataFrame] = []
    reference_crs: Any | None = None

    for order, pipe_input in enumerate(pipe_inputs, start=1):
        path = pipe_input.get("path")
        if path is None:
            msg = "Each pipe input must define a path."
            raise ConfigurationError(msg)
        layer = pipe_input.get("layer")
        pipes = read_pipe_layer(path, layer=layer)

        if reference_crs is None:
            reference_crs = pipes.crs
        elif pipes.crs != reference_crs:
            msg = (
                "All pipe layers must use the same CRS in this workflow. "
                "Define a future explicit working CRS before combining different CRS."
            )
            raise ConfigurationError(msg)

        pipes = pipes.copy()
        pipes["_source_order"] = order
        pipes["_source_path"] = str(path)
        pipes["_source_layer"] = layer
        pipes["_source_index"] = pipes.index.astype(str)
        loaded_layers.append(pipes)

    combined = gpd.GeoDataFrame(
        pd.concat(loaded_layers, ignore_index=True),
        geometry=loaded_layers[0].geometry.name,
        crs=reference_crs,
    )
    if combined.empty:
        msg = "Combined pipe layer is empty."
        raise ConfigurationError(msg)
    return combined
