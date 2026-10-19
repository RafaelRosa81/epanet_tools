"""Run EPANET INP models through WNTR's EPANET engine.

Outputs follow the read_rpt contract: nodes, links, metadata.
Hydraulic units are explicit: pressure/head in m, flow/demand in L/s,
velocity in m/s. Values are not rounded.
"""
from pathlib import Path

import pandas as pd


def run_inp(inp_path: str | Path) -> dict:
    """Simulate an INP and return long-form node/link time series.

    WNTR is an optional dependency: install with pip install -e ".[simulation]".
    """
    try:
        import wntr
    except ImportError as exc:
        raise ImportError(
            'WNTR is required: pip install -e ".[simulation]"'
        ) from exc

    path = Path(inp_path)
    if not path.is_file():
        raise FileNotFoundError(path)

    network = wntr.network.WaterNetworkModel(str(path))
    results = wntr.sim.EpanetSimulator(network).run_sim()

    def long_frame(variable: str, frame: pd.DataFrame, factor: float = 1.0) -> pd.DataFrame:
        table = frame.rename_axis(index="time_seconds", columns="id")
        table = table.stack().rename(variable).reset_index()
        table[variable] = table[variable] * factor
        return table

    node_specs = [
        ("pressure", "pressure_m", 1.0),
        ("head", "head_m", 1.0),
        ("demand", "demand_lps", 1000.0),
    ]
    link_specs = [
        ("flowrate", "flow_lps", 1000.0),
        ("velocity", "velocity_m_s", 1.0),
        ("headloss", "headloss", 1.0),
        ("status", "status", 1.0),
    ]

    def assemble(group: dict, specs: list[tuple[str, str, float]]) -> pd.DataFrame:
        frames = [
            long_frame(column, group[source], factor)
            for source, column, factor in specs
            if source in group
        ]
        if not frames:
            return pd.DataFrame(columns=["time_seconds", "hour", "id"])
        merged = frames[0]
        for frame in frames[1:]:
            merged = merged.merge(frame, on=["time_seconds", "id"], how="outer")
        merged.insert(1, "hour", merged["time_seconds"] / 3600.0)
        return merged.sort_values(["time_seconds", "id"]).reset_index(drop=True)

    nodes = assemble(results.node, node_specs)
    links = assemble(results.link, link_specs)
    node_types = {name: type(network.get_node(name)).__name__ for name in network.node_name_list}
    link_types = {name: type(network.get_link(name)).__name__ for name in network.link_name_list}
    nodes["element_type"] = nodes["id"].map(node_types)
    links["element_type"] = links["id"].map(link_types)
    return {
        "nodes": nodes,
        "links": links,
        "metadata": {
            "source": str(path),
            "engine": "WNTR EpanetSimulator",
            "units": {
                "pressure_m": "m", "head_m": "m", "demand_lps": "L/s",
                "flow_lps": "L/s", "velocity_m_s": "m/s",
                "time_seconds": "s", "hour": "h",
                "headloss": "WNTR EPANET output units",
            },
            "rounded": False,
        },
    }
