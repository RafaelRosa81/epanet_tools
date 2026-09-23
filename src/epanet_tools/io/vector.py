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
    """Read, reproject when needed, and combine several pipe layers.

    Source files are never modified. When ``working_crs`` is provided, each layer
    is reprojected in memory before concatenation. The returned GeoDataFrame keeps
    source traceability fields including the original CRS.
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


def read_existing_network(
    path: str | Path,
    node_layer: str,
    pipe_layer: str,
    working_crs: str | int | CRS | None = None,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Read explicit node and pipe layers from an existing GIS network.

    The source dataset is never modified. Both layers must define a CRS. If a
    projected working CRS is provided, both layers are reprojected in memory.
    Without a working CRS, node and pipe layers must already use the same CRS.
    """
    vector_path = Path(path)
    if not vector_path.exists():
        msg = f"Network dataset does not exist: {vector_path}"
        raise FileNotFoundError(msg)

    nodes = gpd.read_file(vector_path, layer=node_layer)
    pipes = gpd.read_file(vector_path, layer=pipe_layer)

    if nodes.empty:
        raise ConfigurationError(f"Node layer is empty: {node_layer}")
    if pipes.empty:
        raise ConfigurationError(f"Pipe layer is empty: {pipe_layer}")
    if nodes.crs is None:
        raise ConfigurationError(f"Node layer has no CRS: {node_layer}")
    if pipes.crs is None:
        raise ConfigurationError(f"Pipe layer has no CRS: {pipe_layer}")

    node_crs = CRS.from_user_input(nodes.crs)
    pipe_crs = CRS.from_user_input(pipes.crs)
    target_crs = _resolve_target_crs(working_crs)

    if target_crs is None:
        if node_crs != pipe_crs:
            msg = (
                "Node and pipe layers use different CRS. Define spatial.working_crs "
                "to reproject them safely in memory."
            )
            raise ConfigurationError(msg)
    else:
        if node_crs != target_crs:
            nodes = nodes.to_crs(target_crs)
        if pipe_crs != target_crs:
            pipes = pipes.to_crs(target_crs)

    nodes = nodes.copy()
    pipes = pipes.copy()
    nodes["_source_path"] = str(path)
    nodes["_source_layer"] = node_layer
    nodes["_source_crs"] = node_crs.to_string()
    pipes["_source_path"] = str(path)
    pipes["_source_layer"] = pipe_layer
    pipes["_source_crs"] = pipe_crs.to_string()
    return nodes, pipes


def _resolve_target_crs(working_crs: str | int | CRS | None) -> CRS | None:
    if working_crs in (None, "", "null"):
        return None
    crs = CRS.from_user_input(working_crs)
    if not crs.is_projected:
        msg = f"Working CRS must be projected and metric: {working_crs}"
        raise ConfigurationError(msg)
    return crs
