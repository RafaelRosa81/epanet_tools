"""Align a group of displaced vertical sectors using one shared XY translation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.affinity import translate

from epanet_tools.config import load_yaml_config, require_mapping


@dataclass(frozen=True)
class SectorAlignmentResult:
    """Summary returned by the vertical-sector alignment workflow."""

    output_path: Path
    report_path: Path
    aligned_sectors: int
    node_count: int
    pipe_count: int
    dx_m: float
    dy_m: float


def align_vertical_sectors(config_path: str | Path) -> SectorAlignmentResult:
    """Apply one rigid XY translation to all configured vertical sectors."""
    config = load_yaml_config(config_path)
    inputs = require_mapping(config, "inputs")
    existing = require_mapping(inputs, "existing_network")
    path_value = existing.get("path")
    node_layer = str(existing.get("node_layer", "nodos"))
    pipe_layer = str(existing.get("pipe_layer", "tramos"))
    if not path_value:
        raise ValueError("inputs.existing_network.path is required.")

    source_path = Path(str(path_value))
    if not source_path.exists():
        raise FileNotFoundError(f"GeoPackage not found: {source_path}")

    alignment = require_mapping(config, "vertical_sector_alignment")
    moving_reference_node = str(alignment.get("moving_reference_node", "")).strip()
    fixed_reference_node = str(alignment.get("fixed_reference_node", "")).strip()
    sectors = {_sector_key(value) for value in alignment.get("sectors", [])}
    if not moving_reference_node or not fixed_reference_node:
        raise ValueError(
            "vertical_sector_alignment requires moving_reference_node and fixed_reference_node."
        )
    if not sectors:
        raise ValueError("vertical_sector_alignment.sectors must not be empty.")

    table_path = Path(str(alignment.get("table_path", "")))
    if not table_path.exists():
        raise FileNotFoundError(f"Connection table not found: {table_path}")

    output_path = Path(str(alignment.get(
        "output_path",
        source_path.with_name(source_path.stem + "_conectada.gpkg"),
    )))
    report_path = Path(str(alignment.get(
        "report_path",
        output_path.with_name(output_path.stem + "_alignment_report.csv"),
    )))

    nodes = gpd.read_file(source_path, layer=node_layer)
    pipes = gpd.read_file(source_path, layer=pipe_layer)
    table = pd.read_csv(table_path)

    _validate_source_layers(nodes, pipes)
    _validate_connection_table(table, sectors)

    moving = _unique_node(nodes, moving_reference_node)
    fixed = _unique_node(nodes, fixed_reference_node)
    moving_sector = _sector_key(moving["SECTOR"])
    if moving_sector not in sectors:
        raise ValueError(
            f"Moving reference node {moving_reference_node} belongs to sector "
            f"{moving_sector}, which is not in the configured sector group."
        )

    dx = float(fixed.geometry.x - moving.geometry.x)
    dy = float(fixed.geometry.y - moving.geometry.y)

    nodes_out = nodes.copy()
    pipes_out = pipes.copy()
    node_mask = nodes_out["SECTOR"].map(_sector_key).isin(sectors)
    pipe_mask = pipes_out["SECTOR"].map(_sector_key).isin(sectors)

    nodes_out.loc[node_mask, "geometry"] = nodes_out.loc[node_mask, "geometry"].map(
        lambda geom: translate(geom, xoff=dx, yoff=dy)
    )
    pipes_out.loc[pipe_mask, "geometry"] = pipes_out.loc[pipe_mask, "geometry"].map(
        lambda geom: translate(geom, xoff=dx, yoff=dy)
    )
    if "X" in nodes_out.columns:
        nodes_out.loc[node_mask, "X"] = nodes_out.loc[node_mask, "geometry"].x
    if "Y" in nodes_out.columns:
        nodes_out.loc[node_mask, "Y"] = nodes_out.loc[node_mask, "geometry"].y

    moved_after = _unique_node(nodes_out, moving_reference_node)
    residual = float(moved_after.geometry.distance(fixed.geometry))
    if residual > 1e-8:
        raise ValueError(f"Reference alignment residual is {residual:.12f} m.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    nodes_out.to_file(output_path, layer=node_layer, driver="GPKG")
    pipes_out.to_file(output_path, layer=pipe_layer, driver="GPKG")

    _copy_aligned_aux_nodes(
        source_path=source_path,
        output_path=output_path,
        nodes=nodes,
        sectors=sectors,
        dx=dx,
        dy=dy,
    )

    report_rows: list[dict[str, Any]] = []
    for sector in sorted(sectors, key=lambda value: int(value)):
        sector_nodes = nodes["SECTOR"].map(_sector_key).eq(sector)
        sector_pipes = pipes["SECTOR"].map(_sector_key).eq(sector)
        connection = table.loc[table["sector"].map(_sector_key).eq(sector)].iloc[0]
        report_rows.append(
            {
                "sector": sector,
                "status": "aligned",
                "moving_reference_node": moving_reference_node,
                "fixed_reference_node": fixed_reference_node,
                "dx_m": dx,
                "dy_m": dy,
                "moved_nodes": int(sector_nodes.sum()),
                "moved_pipes": int(sector_pipes.sum()),
                "source_node": connection["source_node"],
                "target_node": connection["target_node"],
                "target_z": connection["target_z"],
                "vertical_length_m": connection["vertical_length_m"],
                "direction": connection["direction"],
            }
        )

    report = pd.DataFrame(report_rows)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(report_path, index=False)

    return SectorAlignmentResult(
        output_path=output_path,
        report_path=report_path,
        aligned_sectors=len(sectors),
        node_count=len(nodes_out),
        pipe_count=len(pipes_out),
        dx_m=dx,
        dy_m=dy,
    )


def _copy_aligned_aux_nodes(
    source_path: Path,
    output_path: Path,
    nodes: gpd.GeoDataFrame,
    sectors: set[str],
    dx: float,
    dy: float,
) -> None:
    """Copy nodos_utm when present, applying the same group translation."""
    try:
        aux = gpd.read_file(source_path, layer="nodos_utm")
    except Exception:
        return

    aux_out = aux.copy()
    if "SECTOR" in aux_out.columns:
        mask = aux_out["SECTOR"].map(_sector_key).isin(sectors)
    elif "ID" in aux_out.columns:
        ids = set(nodes.loc[nodes["SECTOR"].map(_sector_key).isin(sectors), "ID"].astype(str))
        mask = aux_out["ID"].astype(str).isin(ids)
    else:
        return

    aux_out.loc[mask, "geometry"] = aux_out.loc[mask, "geometry"].map(
        lambda geom: translate(geom, xoff=dx, yoff=dy)
    )
    if "X" in aux_out.columns:
        aux_out.loc[mask, "X"] = aux_out.loc[mask, "geometry"].x
    if "Y" in aux_out.columns:
        aux_out.loc[mask, "Y"] = aux_out.loc[mask, "geometry"].y
    aux_out.to_file(output_path, layer="nodos_utm", driver="GPKG")


def _validate_source_layers(nodes: gpd.GeoDataFrame, pipes: gpd.GeoDataFrame) -> None:
    node_required = {"ID", "SECTOR", "geometry"}
    pipe_required = {"ID", "SECTOR", "geometry"}
    missing_nodes = sorted(node_required.difference(nodes.columns))
    missing_pipes = sorted(pipe_required.difference(pipes.columns))
    if missing_nodes:
        raise ValueError(f"Node layer is missing fields: {', '.join(missing_nodes)}")
    if missing_pipes:
        raise ValueError(f"Pipe layer is missing fields: {', '.join(missing_pipes)}")
    if nodes["ID"].astype(str).duplicated().any():
        raise ValueError("Node IDs must be unique before alignment.")


def _validate_connection_table(table: pd.DataFrame, sectors: set[str]) -> None:
    required = {
        "sector",
        "source_node",
        "target_node",
        "target_z",
        "vertical_length_m",
        "direction",
    }
    missing = sorted(required.difference(table.columns))
    if missing:
        raise ValueError(f"Connection table is missing fields: {', '.join(missing)}")
    table_sectors = table["sector"].map(_sector_key)
    if table_sectors.duplicated().any():
        raise ValueError("Connection table must contain one row per sector.")
    missing_sectors = sorted(sectors.difference(set(table_sectors)))
    if missing_sectors:
        raise ValueError(
            "Connection table is missing configured sectors: " + ", ".join(missing_sectors)
        )


def _unique_node(nodes: gpd.GeoDataFrame, node_id: str) -> pd.Series:
    matches = nodes.loc[nodes["ID"].astype(str).eq(node_id)]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one node '{node_id}', found {len(matches)}.")
    return matches.iloc[0]


def _sector_key(value: Any) -> str:
    if pd.isna(value):
        return ""
    try:
        number = float(value)
        if number.is_integer():
            return str(int(number))
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Align a group of displaced vertical sectors using one shared XY translation."
    )
    parser.add_argument("--config", required=True, help="Path to the YAML configuration.")
    args = parser.parse_args()
    result = align_vertical_sectors(args.config)
    print(
        {
            "output_path": str(result.output_path),
            "report_path": str(result.report_path),
            "aligned_sectors": result.aligned_sectors,
            "node_count": result.node_count,
            "pipe_count": result.pipe_count,
            "dx_m": result.dx_m,
            "dy_m": result.dy_m,
        }
    )


if __name__ == "__main__":
    main()
