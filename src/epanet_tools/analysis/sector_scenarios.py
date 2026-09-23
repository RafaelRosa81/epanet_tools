"""Prepare independent sprinkler-sector scenarios for pump-envelope analysis."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import networkx as nx
import pandas as pd


@dataclass(frozen=True)
class SectorScenarioColumns:
    """Column names expected in the sector-demand workbook."""

    sector: str = "sector"
    active_sprinklers: str = "rociadores_activos"
    sprinkler_flow_l_min: str = "q_por_rociador_l_min"
    pressure_target_bar: str = "P rociador (bar)"


def read_sector_design_table(
    path: str | Path,
    *,
    sheet_name: str | int = 0,
    header_row: int = 2,
    columns: SectorScenarioColumns = SectorScenarioColumns(),
) -> pd.DataFrame:
    """Read and validate sector design conditions from the project workbook."""
    table = pd.read_excel(path, sheet_name=sheet_name, header=header_row)
    required = {
        columns.sector,
        columns.active_sprinklers,
        columns.sprinkler_flow_l_min,
        columns.pressure_target_bar,
    }
    missing = sorted(required.difference(table.columns))
    if missing:
        raise ValueError(f"Sector workbook is missing columns: {', '.join(missing)}")

    result = table.copy()
    result[columns.sector] = pd.to_numeric(result[columns.sector], errors="raise").astype(int)
    result[columns.active_sprinklers] = pd.to_numeric(
        result[columns.active_sprinklers], errors="raise"
    ).astype(int)
    result[columns.sprinkler_flow_l_min] = pd.to_numeric(
        result[columns.sprinkler_flow_l_min], errors="raise"
    )
    result[columns.pressure_target_bar] = pd.to_numeric(
        result[columns.pressure_target_bar], errors="raise"
    )
    if result[columns.sector].duplicated().any():
        raise ValueError("Sector workbook contains duplicate sector numbers.")
    if (result[columns.active_sprinklers] < 0).any():
        raise ValueError("Active sprinkler count cannot be negative.")
    if (result[columns.sprinkler_flow_l_min] < 0).any():
        raise ValueError("Sprinkler flow cannot be negative.")
    if (result[columns.pressure_target_bar] < 0).any():
        raise ValueError("Target sprinkler pressure cannot be negative.")
    result["q_sector_l_min"] = (
        result[columns.active_sprinklers] * result[columns.sprinkler_flow_l_min]
    )
    return result


def build_network_graph(pipes: pd.DataFrame) -> nx.Graph:
    """Build a length-weighted undirected graph from canonical pipe fields."""
    required = {"from_node", "to_node", "length_m"}
    missing = sorted(required.difference(pipes.columns))
    if missing:
        raise ValueError(f"Pipe table is missing fields: {', '.join(missing)}")
    graph = nx.Graph()
    for row in pipes.itertuples(index=False):
        graph.add_edge(str(row.from_node), str(row.to_node), weight=float(row.length_m))
    return graph


def select_farthest_sprinklers(
    nodes: pd.DataFrame,
    pipes: pd.DataFrame,
    *,
    sector: int,
    count: int,
    source_node: str = "P-0001",
    sprinkler_descriptions: Iterable[str] = ("SPRINKLER", "ROCIADOR"),
) -> pd.DataFrame:
    """Select N sprinkler candidates farthest from the source by network length."""
    if count == 0:
        return pd.DataFrame(columns=["node_id", "distance_from_source_m"])
    required = {"node_id", "SECTOR"}
    missing = sorted(required.difference(nodes.columns))
    if missing:
        raise ValueError(f"Node table is missing fields: {', '.join(missing)}")

    sector_nodes = nodes.loc[pd.to_numeric(nodes["SECTOR"], errors="coerce") == sector].copy()
    if "description" in sector_nodes.columns:
        allowed = {str(value).strip().upper() for value in sprinkler_descriptions}
        descriptions = sector_nodes["description"].fillna("").astype(str).str.strip().str.upper()
        explicit = sector_nodes.loc[descriptions.isin(allowed)]
        if not explicit.empty:
            sector_nodes = explicit
    if len(sector_nodes) < count:
        raise ValueError(
            f"Sector {sector} needs {count} active sprinklers but only "
            f"{len(sector_nodes)} candidates were found."
        )

    graph = build_network_graph(pipes)
    if source_node not in graph:
        raise ValueError(f"Source node '{source_node}' is not present in the network graph.")
    distances = nx.single_source_dijkstra_path_length(graph, source_node, weight="weight")
    sector_nodes["distance_from_source_m"] = sector_nodes["node_id"].astype(str).map(distances)
    unreachable = sector_nodes["distance_from_source_m"].isna()
    if unreachable.any():
        examples = ", ".join(sector_nodes.loc[unreachable, "node_id"].astype(str).head(5))
        raise ValueError(f"Sector {sector} contains unreachable sprinkler candidates: {examples}")
    return sector_nodes.sort_values(
        ["distance_from_source_m", "node_id"], ascending=[False, True]
    ).head(count)


def prepare_sector_scenarios(
    design: pd.DataFrame,
    nodes: pd.DataFrame,
    pipes: pd.DataFrame,
    *,
    source_node: str = "P-0001",
    reservoir_head_m: float = 0.0,
    columns: SectorScenarioColumns = SectorScenarioColumns(),
) -> pd.DataFrame:
    """Create the auditable input table for independent sector simulations."""
    records: list[dict[str, object]] = []
    for _, row in design.iterrows():
        sector = int(row[columns.sector])
        count = int(row[columns.active_sprinklers])
        q_sprinkler = float(row[columns.sprinkler_flow_l_min])
        pressure = float(row[columns.pressure_target_bar])
        selected = select_farthest_sprinklers(
            nodes, pipes, sector=sector, count=count, source_node=source_node
        )
        records.append(
            {
                "sector": sector,
                "n_sprinklers": count,
                "q_sprinkler_l_min": q_sprinkler,
                "q_sector_l_min": count * q_sprinkler,
                "pressure_target_bar": pressure,
                "active_nodes": ";".join(selected["node_id"].astype(str)),
                "critical_candidate": (
                    str(selected.iloc[0]["node_id"]) if not selected.empty else ""
                ),
                "max_distance_from_P0001_m": (
                    float(selected.iloc[0]["distance_from_source_m"])
                    if not selected.empty
                    else 0.0
                ),
                "reservoir_head_m": float(reservoir_head_m),
            }
        )
    return pd.DataFrame.from_records(records).sort_values("sector").reset_index(drop=True)
