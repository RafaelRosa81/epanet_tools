from __future__ import annotations

import pandas as pd

from epanet_tools.analysis.sector_scenarios import (
    prepare_sector_scenarios,
    select_farthest_sprinklers,
)


def _network() -> tuple[pd.DataFrame, pd.DataFrame]:
    nodes = pd.DataFrame(
        {
            "node_id": ["P-0001", "01_J001", "01_J002", "01_J003"],
            "SECTOR": [None, 1, 1, 1],
            "description": ["CONEXION", "SPRINKLER", "SPRINKLER", "SPRINKLER"],
        }
    )
    pipes = pd.DataFrame(
        {
            "from_node": ["P-0001", "01_J001", "01_J002"],
            "to_node": ["01_J001", "01_J002", "01_J003"],
            "length_m": [10.0, 5.0, 2.0],
        }
    )
    return nodes, pipes


def test_select_farthest_sprinklers_uses_network_distance() -> None:
    nodes, pipes = _network()
    selected = select_farthest_sprinklers(nodes, pipes, sector=1, count=2)
    assert selected["node_id"].tolist() == ["01_J003", "01_J002"]
    assert selected["distance_from_source_m"].tolist() == [17.0, 15.0]


def test_prepare_sector_scenarios_recomputes_total_flow_and_zero_head() -> None:
    nodes, pipes = _network()
    design = pd.DataFrame(
        {
            "sector": [1],
            "rociadores_activos": [2],
            "q_por_rociador_l_min": [82.0],
            "P rociador (bar)": [1.050625],
            "caudal_total_sector_l_min": [0.0],
        }
    )
    scenarios = prepare_sector_scenarios(design, nodes, pipes, reservoir_head_m=0.0)
    assert scenarios.loc[0, "q_sector_l_min"] == 164.0
    assert scenarios.loc[0, "active_nodes"] == "01_J003;01_J002"
    assert scenarios.loc[0, "critical_candidate"] == "01_J003"
    assert scenarios.loc[0, "reservoir_head_m"] == 0.0
