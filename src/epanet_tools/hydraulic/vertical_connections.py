"""Add explicit vertical connections between the main network and upper/lower sectors."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point


def add_vertical_connections(
    junctions: gpd.GeoDataFrame,
    pipes: gpd.GeoDataFrame,
    config: dict[str, Any],
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, pd.DataFrame]:
    """Connect configured sectors while keeping their EPANET drawing positions separated.

    Each configured connection adds:
    - one riser junction at the target sector elevation;
    - one vertical hydraulic pipe from the main-network source to the riser;
    - one short entry pipe from the riser to the existing sector target.

    The vertical pipe uses the explicit hydraulic length from the master table.
    The entry pipe length is derived from the real XY distance between the source
    node and the configured ground-floor anchor. Drawing geometry is independent
    from these hydraulic lengths.
    """
    if not config:
        return junctions, pipes, pd.DataFrame()

    table_path = Path(str(config.get("table_path", "")))
    if not table_path.exists():
        raise FileNotFoundError(f"Vertical connection table not found: {table_path}")

    table = pd.read_csv(table_path)
    _validate_table(table)

    diameter = float(config.get("diameter_mm", 63.0))
    roughness = float(config.get("roughness", 120.0))
    minor_loss = float(config.get("minor_loss", 0.0))
    status = str(config.get("status", "OPEN")).upper()
    display_offset_x = float(config.get("display_offset_x", -0.75))
    display_offset_y = float(config.get("display_offset_y", 0.0))

    nodes_out = junctions.copy()
    pipes_out = pipes.copy()
    node_ids = set(nodes_out["node_id"].astype(str))
    pipe_ids = set(pipes_out["pipe_id"].astype(str))
    report_rows: list[dict[str, Any]] = []

    for row in table.itertuples(index=False):
        sector = _sector_key(row.sector)
        source_id = str(row.source_node).strip()
        target_id = str(row.target_node).strip()
        anchor_id = str(row.anchor_node).strip()
        target_z = float(row.target_z)
        vertical_length = float(row.vertical_length_m)

        source = _unique_node(nodes_out, source_id)
        target = _unique_node(nodes_out, target_id)
        anchor = _unique_node(nodes_out, anchor_id)
        if _sector_key(target.get("SECTOR")) != sector:
            raise ValueError(f"Target node {target_id} is not in sector {sector}.")

        # Replace provisional/test elevations for the whole floor/sector.
        sector_mask = nodes_out["SECTOR"].map(_sector_key).eq(sector)
        nodes_out.loc[sector_mask, "elevation_m"] = target_z
        if "Z" in nodes_out.columns:
            nodes_out.loc[sector_mask, "Z"] = target_z

        riser_id = f"{int(float(row.sector)):02d}_R001"
        vertical_pipe_id = f"{int(float(row.sector)):02d}_V001"
        entry_pipe_id = f"{int(float(row.sector)):02d}_E001"
        for value, existing, kind in (
            (riser_id, node_ids, "node"),
            (vertical_pipe_id, pipe_ids, "pipe"),
            (entry_pipe_id, pipe_ids, "pipe"),
        ):
            if value in existing:
                raise ValueError(f"Generated {kind} ID already exists: {value}")

        target_geom = target.geometry
        riser_geom = Point(
            float(target_geom.x) + display_offset_x,
            float(target_geom.y) + display_offset_y,
        )
        entry_length = float(source.geometry.distance(anchor.geometry))
        if entry_length <= 0:
            raise ValueError(
                f"Entry length for sector {sector} is zero; source={source_id}, anchor={anchor_id}."
            )

        node_record = {column: pd.NA for column in nodes_out.columns if column != "geometry"}
        node_record.update(
            {
                "node_id": riser_id,
                "elevation_m": target_z,
                "demand": 0.0,
                "ID": riser_id,
                "SECTOR": float(row.sector),
                "TIPO": "MONTANTE",
                "SUBTIPO": "CONEXION_VERTICAL",
                "X": riser_geom.x,
                "Y": riser_geom.y,
                "Z": target_z,
            }
        )
        new_node = gpd.GeoDataFrame(
            [node_record], geometry=[riser_geom], crs=nodes_out.crs
        )
        nodes_out = pd.concat([nodes_out, new_node], ignore_index=True)
        nodes_out = gpd.GeoDataFrame(nodes_out, geometry="geometry", crs=junctions.crs)
        node_ids.add(riser_id)

        vertical_geom = LineString([source.geometry, riser_geom])
        entry_geom = LineString([riser_geom, target_geom])
        vertical_record = _pipe_record(
            pipes_out,
            pipe_id=vertical_pipe_id,
            from_node=source_id,
            to_node=riser_id,
            length_m=vertical_length,
            diameter_mm=diameter,
            roughness=roughness,
            minor_loss=minor_loss,
            status=status,
            sector=row.sector,
            geometry=vertical_geom,
            pipe_type="MONTANTE_VERTICAL",
        )
        entry_record = _pipe_record(
            pipes_out,
            pipe_id=entry_pipe_id,
            from_node=riser_id,
            to_node=target_id,
            length_m=entry_length,
            diameter_mm=diameter,
            roughness=roughness,
            minor_loss=minor_loss,
            status=status,
            sector=row.sector,
            geometry=entry_geom,
            pipe_type="ENTRADA_SECTOR",
        )
        additions = gpd.GeoDataFrame(
            [vertical_record, entry_record],
            geometry="geometry",
            crs=pipes_out.crs,
        )
        pipes_out = pd.concat([pipes_out, additions], ignore_index=True)
        pipes_out = gpd.GeoDataFrame(pipes_out, geometry="geometry", crs=pipes.crs)
        pipe_ids.update({vertical_pipe_id, entry_pipe_id})

        report_rows.append(
            {
                "sector": sector,
                "source_node": source_id,
                "riser_node": riser_id,
                "target_node": target_id,
                "anchor_node": anchor_id,
                "target_z": target_z,
                "vertical_pipe": vertical_pipe_id,
                "vertical_length_m": vertical_length,
                "entry_pipe": entry_pipe_id,
                "entry_length_m": entry_length,
                "direction": str(row.direction).strip().upper(),
            }
        )

    return nodes_out, pipes_out, pd.DataFrame(report_rows)


def _pipe_record(
    template: gpd.GeoDataFrame,
    *,
    pipe_id: str,
    from_node: str,
    to_node: str,
    length_m: float,
    diameter_mm: float,
    roughness: float,
    minor_loss: float,
    status: str,
    sector: Any,
    geometry: LineString,
    pipe_type: str,
) -> dict[str, Any]:
    record = {column: pd.NA for column in template.columns if column != "geometry"}
    record.update(
        {
            "pipe_id": pipe_id,
            "from_node": from_node,
            "to_node": to_node,
            "length_m": length_m,
            "diameter_mm": diameter_mm,
            "roughness": roughness,
            "minor_loss": minor_loss,
            "status": status,
            "ID": pipe_id,
            "NODE_INI": from_node,
            "NODE_FIN": to_node,
            "LONGITUD": length_m,
            "DIAMETRO": diameter_mm,
            "C_HW": roughness,
            "SECTOR": float(sector),
            "TIPO": pipe_type,
            "geometry": geometry,
        }
    )
    return record


def _validate_table(table: pd.DataFrame) -> None:
    required = {
        "sector",
        "source_node",
        "anchor_node",
        "target_node",
        "target_z",
        "vertical_length_m",
        "direction",
    }
    missing = sorted(required.difference(table.columns))
    if missing:
        raise ValueError(f"Vertical connection table is missing fields: {', '.join(missing)}")
    if table["sector"].map(_sector_key).duplicated().any():
        raise ValueError("Vertical connection table must contain one row per sector.")


def _unique_node(nodes: gpd.GeoDataFrame, node_id: str) -> pd.Series:
    matches = nodes.loc[nodes["node_id"].astype(str).eq(node_id)]
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
