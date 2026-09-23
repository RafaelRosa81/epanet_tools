"""Build an auditable table of independent sprinkler-sector scenarios."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from epanet_tools.analysis.sector_scenarios import (
    prepare_sector_scenarios,
    read_sector_design_table,
)
from epanet_tools.config import load_yaml_config, require_mapping
from epanet_tools.hydraulic.vertical_connections import add_vertical_connections
from epanet_tools.io.vector import read_existing_network
from epanet_tools.workflows.import_existing_network import (
    _apply_node_attributes_csv,
    _apply_pipe_attributes_csv,
    _filter_network,
    _map_fields,
    _mapping,
    _working_crs,
)


def build_sector_scenarios(config_path: str | Path) -> dict[str, object]:
    config = load_yaml_config(config_path)
    inputs = require_mapping(config, "inputs")
    existing = require_mapping(inputs, "existing_network")
    scenarios_cfg = require_mapping(config, "sector_scenarios")

    nodes, pipes = read_existing_network(
        path=existing["path"],
        node_layer=str(existing["node_layer"]),
        pipe_layer=str(existing["pipe_layer"]),
        working_crs=_working_crs(config),
    )
    field_mapping = _mapping(config, "field_mapping")
    nodes = _map_fields(nodes, field_mapping.get("nodes"), defaults={"demand": 0.0})
    pipes = _map_fields(
        pipes,
        field_mapping.get("pipes"),
        defaults={"minor_loss": 0.0, "status": "OPEN"},
    )
    nodes, pipes = _filter_network(nodes, pipes, _mapping(config, "network_filter"))
    nodes = _apply_node_attributes_csv(nodes, _mapping(config, "node_attributes_csv"))
    pipes = _apply_pipe_attributes_csv(pipes, _mapping(config, "pipe_attributes_csv"))
    nodes, pipes, _ = add_vertical_connections(nodes, pipes, _mapping(config, "vertical_connections"))
    if "length_m" not in pipes.columns:
        pipes["length_m"] = pipes.geometry.length

    workbook = scenarios_cfg.get("workbook_path")
    if not workbook:
        raise ValueError("sector_scenarios.workbook_path is required.")
    design = read_sector_design_table(
        workbook,
        sheet_name=scenarios_cfg.get("sheet_name", 0),
        header_row=int(scenarios_cfg.get("header_row", 2)),
    )
    exclude = {int(v) for v in scenarios_cfg.get("exclude_sectors", [])}
    if exclude:
        design = design.loc[~design["sector"].isin(exclude)].copy()

    table = prepare_sector_scenarios(
        design,
        nodes,
        pipes,
        source_node=str(scenarios_cfg.get("source_node", "P-0001")),
        reservoir_head_m=float(scenarios_cfg.get("reservoir_head_m", 0.0)),
    )
    node_z = nodes.set_index(nodes["node_id"].astype(str))["elevation_m"]
    table["critical_candidate_z_m"] = table["critical_candidate"].map(node_z)

    outdir = Path(str(config.get("outdir", "outputs"))) / "report"
    outdir.mkdir(parents=True, exist_ok=True)
    name = str(config.get("name", "epanet_model"))
    output_path = outdir / f"{name}_sector_scenarios.csv"
    table.to_csv(output_path, index=False)
    return {
        "status": "ok",
        "sector_count": len(table),
        "output_path": str(output_path),
        "reservoir_head_m": float(scenarios_cfg.get("reservoir_head_m", 0.0)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    print(build_sector_scenarios(args.config))


if __name__ == "__main__":
    main()
