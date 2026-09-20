"""Align displaced vertical sectors in an existing GeoPackage network."""

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
    skipped_sectors: int
    node_count: int
    pipe_count: int


def align_vertical_sectors(config_path: str | Path) -> SectorAlignmentResult:
    """Translate configured sectors rigidly in XY and write a new GeoPackage."""
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
    table_path = Path(str(alignment.get("table_path", "")))
    if not table_path.exists():
        raise FileNotFoundError(f"Alignment table not found: {table_path}")

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
    _validate_alignment_table(table)

    nodes_out = nodes.copy()
    pipes_out = pipes.copy()
    report_rows: list[dict[str, Any]] = []

    for row in table.itertuples(index=False):
        sector = _sector_key(row.sector)
        enabled = bool(row.enabled)
        moving_node = str(row.moving_reference_node).strip()
        fixed_node = str(row.fixed_reference_node).strip() if pd.notna(row.fixed_reference_node) else ""

        if not enabled:
            report_rows.append(_report_row(row, "skipped", "", "", 0.0, 0.0, 0, 0))
            continue
        if not moving_node or not fixed_node:
            report_rows.append(
                _report_row(row, "pending_reference", moving_node, fixed_node, 0.0, 0.0, 0, 0)
            )
            continue

        moving = _unique_node(nodes_out, moving_node)
        fixed = _unique_node(nodes_out, fixed_node)
        if _sector_key(moving["SECTOR"]) != sector:
            raise ValueError(
                f"Moving reference node {moving_node} is not in configured sector {sector}."
            )

        dx = float(fixed.geometry.x - moving.geometry.x)
        dy = float(fixed.geometry.y - moving.geometry.y)

        node_mask = nodes_out["SECTOR"].map(_sector_key).eq(sector)
        pipe_mask = pipes_out["SECTOR"].map(_sector_key).eq(sector)
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

        moved_after = _unique_node(nodes_out, moving_node)
        residual = moved_after.geometry.distance(fixed.geometry)
        if residual > 1e-8:
            raise ValueError(
                f"Alignment residual for sector {sector} is {residual:.12f} m."
            )

        report_rows.append(
            _report_row(
                row,
                "aligned",
                moving_node,
                fixed_node,
                dx,
                dy,
                int(node_mask.sum()),
                int(pipe_mask.sum()),
            )
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    nodes_out.to_file(output_path, layer=node_layer, driver="GPKG")
    pipes_out.to_file(output_path, layer=pipe_layer, driver="GPKG")

    # Preserve optional auxiliary node layer by applying the same node transforms.
    try:
        aux = gpd.read_file(source_path, layer="nodos_utm")
    except Exception:
        aux = None
    if aux is not None:
        aux_out = aux.copy()
        for row in table.itertuples(index=False):
            if not bool(row.enabled) or pd.isna(row.fixed_reference_node):
                continue
            sector = _sector_key(row.sector)
            moving_node = str(row.moving_reference_node).strip()
            fixed_node = str(row.fixed_reference_node).strip()
            moving = _unique_node(nodes, moving_node)
            fixed = _unique_node(nodes, fixed_node)
            dx = float(fixed.geometry.x - moving.geometry.x)
            dy = float(fixed.geometry.y - moving.geometry.y)
            if "SECTOR" in aux_out.columns:
                mask = aux_out["SECTOR"].map(_sector_key).eq(sector)
            elif "ID" in aux_out.columns:
                ids = set(nodes.loc[nodes["SECTOR"].map(_sector_key).eq(sector), "ID"].astype(str))
                mask = aux_out["ID"].astype(str).isin(ids)
            else:
                continue
            aux_out.loc[mask, "geometry"] = aux_out.loc[mask, "geometry"].map(
                lambda geom: translate(geom, xoff=dx, yoff=dy)
            )
            if "X" in aux_out.columns:
                aux_out.loc[mask, "X"] = aux_out.loc[mask, "geometry"].x
            if "Y" in aux_out.columns:
                aux_out.loc[mask, "Y"] = aux_out.loc[mask, "geometry"].y
        aux_out.to_file(output_path, layer="nodos_utm", driver="GPKG")

    report = pd.DataFrame(report_rows)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(report_path, index=False)

    return SectorAlignmentResult(
        output_path=output_path,
        report_path=report_path,
        aligned_sectors=int((report["status"] == "aligned").sum()),
        skipped_sectors=int((report["status"] != "aligned").sum()),
        node_count=len(nodes_out),
        pipe_count=len(pipes_out),
    )


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


def _validate_alignment_table(table: pd.DataFrame) -> None:
    required = {
        "sector",
        "moving_reference_node",
        "fixed_reference_node",
        "enabled",
        "target_z",
        "vertical_length_m",
        "direction",
        "source_node",
        "target_node",
    }
    missing = sorted(required.difference(table.columns))
    if missing:
        raise ValueError(f"Alignment table is missing fields: {', '.join(missing)}")
    if table["sector"].map(_sector_key).duplicated().any():
        raise ValueError("Alignment table must contain one row per sector.")


def _unique_node(nodes: gpd.GeoDataFrame, node_id: str) -> pd.Series:
    matches = nodes.loc[nodes["ID"].astype(str).eq(node_id)]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one node '{node_id}', found {len(matches)}.")
    return matches.iloc[0]


def _report_row(
    row: Any,
    status: str,
    moving_node: str,
    fixed_node: str,
    dx: float,
    dy: float,
    moved_nodes: int,
    moved_pipes: int,
) -> dict[str, Any]:
    return {
        "sector": row.sector,
        "status": status,
        "moving_reference_node": moving_node,
        "fixed_reference_node": fixed_node,
        "dx_m": dx,
        "dy_m": dy,
        "moved_nodes": moved_nodes,
        "moved_pipes": moved_pipes,
        "source_node": row.source_node,
        "target_node": row.target_node,
        "target_z": row.target_z,
        "vertical_length_m": row.vertical_length_m,
        "direction": row.direction,
    }


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
        description="Align displaced vertical sectors in a GeoPackage without modifying the source."
    )
    parser.add_argument("--config", required=True, help="Path to the YAML configuration.")
    args = parser.parse_args()
    result = align_vertical_sectors(args.config)
    print(
        {
            "output_path": str(result.output_path),
            "report_path": str(result.report_path),
            "aligned_sectors": result.aligned_sectors,
            "skipped_sectors": result.skipped_sectors,
            "node_count": result.node_count,
            "pipe_count": result.pipe_count,
        }
    )


if __name__ == "__main__":
    main()
