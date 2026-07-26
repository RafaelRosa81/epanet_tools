"""Vector GIS readers used by EPANET workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from pyproj import CRS

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
    if pipes.crs is None:
        msg = f"Pipe layer has no CRS: {vector_path}"
        raise ConfigurationError(msg)
    return pipes


def read_pipe_layers(
    pipe_inputs: list[dict[str, Any]],
    working_crs: str | int | CRS | None = None,
) -> gpd.GeoDataFrame:
    """Read, reproject when needed, classify, and combine pipe layers.

    Source files are never modified. Each input may define ``pipe_class`` or the
    backward-compatible alias ``layer_name``. That value is written to the
    ``clase`` field of every feature from that input layer.
    """
    if not pipe_inputs:
        msg = "At least one pipe input is required."
        raise ConfigurationError(msg)

    target_crs = _resolve_target_crs(working_crs)
    loaded_layers: list[gpd.GeoDataFrame] = []
    reference_crs: CRS | None = None

    for order, pipe_input in enumerate(pipe_inputs, start=1):
        path = pipe_input.get("path")
        if path is None:
            msg = "Each pipe input must define a path."
            raise ConfigurationError(msg)
        layer = pipe_input.get("layer")
        pipe_class = pipe_input.get("pipe_class", pipe_input.get("layer_name"))
        pipes = read_pipe_layer(path, layer=layer)
        source_crs = CRS.from_user_input(pipes.crs)

        if target_crs is None:
            if reference_crs is None:
                reference_crs = source_crs
            elif source_crs != reference_crs:
                msg = (
                    "Pipe layers have different CRS. Define spatial.working_crs "
                    "to reproject them safely in memory."
                )
                raise ConfigurationError(msg)
        elif source_crs != target_crs:
            pipes = pipes.to_crs(target_crs)

        pipes = pipes.copy()
        if pipe_class is not None:
            pipes["clase"] = str(pipe_class)
        elif "clase" not in pipes.columns:
            pipes["clase"] = pd.NA

        pipes["_source_order"] = order
        pipes["_source_path"] = str(path)
        pipes["_source_layer"] = layer
        pipes["_source_index"] = pipes.index.astype(str)
        pipes["_source_crs"] = source_crs.to_string()
        loaded_layers.append(pipes)

    combined_crs = target_crs or reference_crs
    combined = gpd.GeoDataFrame(
        pd.concat(loaded_layers, ignore_index=True),
        geometry=loaded_layers[0].geometry.name,
        crs=combined_crs,
    )
    if combined.empty:
        msg = "Combined pipe layer is empty."
        raise ConfigurationError(msg)
    return combined


def _resolve_target_crs(working_crs: str | int | CRS | None) -> CRS | None:
    if working_crs in (None, "", "null"):
        return None
    crs = CRS.from_user_input(working_crs)
    if not crs.is_projected:
        msg = f"Working CRS must be projected and metric: {working_crs}"
        raise ConfigurationError(msg)
    return crs
