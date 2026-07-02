"""Vector GIS readers used by EPANET workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd

from epanet_tools.exceptions import ConfigurationError


def read_pipe_layer(path: str | Path, layer: str | None = None, **kwargs: Any) -> gpd.GeoDataFrame:
    """Read a pipe vector layer as a GeoDataFrame.

    Parameters
    ----------
    path:
        Path to a vector dataset supported by GeoPandas/Fiona/Pyogrio.
    layer:
        Optional layer name, mainly used for GeoPackage inputs.
    **kwargs:
        Additional keyword arguments passed to ``geopandas.read_file``.

    Returns
    -------
    geopandas.GeoDataFrame
        Loaded pipe layer.
    """
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
