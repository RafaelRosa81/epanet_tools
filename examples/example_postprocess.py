"""Example: read an EPANET report and generate sector pressure plots.

Usage
-----
python examples/example_postprocess.py palo_alto_secundarias.rpt

On Windows, wrap long paths in quotes:
python examples/example_postprocess.py "H:\path\to\palo_alto_secundarias.rpt"
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from epanet_postprocess.diagnostics import (
    check_high_velocities,
    check_low_pressures,
    check_negative_flows,
    check_negative_pressures,
)
from epanet_postprocess.export import export_results_to_excel, export_summary_to_excel
from epanet_postprocess.plots import plot_link_flows, plot_node_pressures
from epanet_postprocess.reader import read_rpt
from epanet_postprocess.summary import summarize_links, summarize_nodes

SECTOR_NODES = {
    "S1": {
        "initial": ["J000013"],
        "final": ["J000024", "J000023"],
    },
    "S2": {
        "initial": ["J000014"],
        "final": ["J000021"],
    },
    "S3": {
        "initial": ["J000011"],
        "final": ["J000026", "J000027"],
    },
    "S41": {
        "initial": ["J000007"],
        "final": ["J000017", "J000042", "J000016"],
    },
    "S42": {
        "initial": ["J000008"],
        "final": ["J000020", "J000041"],
    },
    "S5": {
        "initial": ["J000006"],
        "final": ["J000031", "J000032", "J000039"],
    },
    "S6": {
        "initial": ["J000002"],
        "final": ["J000037"],
    },
    "S7": {
        "initial": ["J000004"],
        "final": ["J000035", "J000033"],
    },
    "S8": {
        "initial": ["J000003"],
        "final": ["J000048", "J000047", "J000044", "J000045"],
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Postprocess an EPANET RPT result file.")
    parser.add_argument(
        "rpt_path",
        type=Path,
        help="Path to the EPANET .rpt file.",
    )
    parser.add_argument(
        "--output-folder",
        type=Path,
        default=Path("outputs/postprocess"),
        help="Folder where plots and Excel files will be written.",
    )
    parser.add_argument(
        "--sectors",
        nargs="*",
        default=list(SECTOR_NODES),
        help="Optional list of sectors to plot, for example: --sectors S1 S2 S8",
    )
    return parser.parse_args()


def selected_sector_nodes(sector_name: str) -> list[str]:
    sector = SECTOR_NODES[sector_name]
    return sector["initial"] + sector["final"]


def export_sector_pressure_table(
    results: dict,
    sector_name: str,
    nodes: list[str],
    output_folder: Path,
) -> pd.DataFrame:
    pressures = results["nodes"].loc[
        results["nodes"]["node_id"].isin(nodes),
        ["time", "node_id", "pressure"],
    ].copy()
    pressures["sector"] = sector_name
    pressures = pressures[["sector", "time", "node_id", "pressure"]]
    pressures.to_csv(output_folder / f"pressures_{sector_name}.csv", index=False)
    return pressures


def main() -> None:
    args = parse_args()
    output_folder = args.output_folder
    output_folder.mkdir(parents=True, exist_ok=True)

    results = read_rpt(args.rpt_path)

    plot_link_flows(
        results,
        links=["P000008", "P000009", "P000016"],
        output=output_folder / "flows_selected_links.png",
    )

    sector_tables = []
    for sector_name in args.sectors:
        if sector_name not in SECTOR_NODES:
            valid = ", ".join(SECTOR_NODES)
            raise ValueError(f"Unknown sector '{sector_name}'. Valid sectors are: {valid}")

        nodes = selected_sector_nodes(sector_name)
        plot_node_pressures(
            results,
            nodes=nodes,
            output=output_folder / f"pressures_{sector_name}.png",
        )
        sector_tables.append(
            export_sector_pressure_table(results, sector_name, nodes, output_folder)
        )

    all_sector_pressures = pd.concat(sector_tables, ignore_index=True)
    all_sector_pressures.to_csv(output_folder / "pressures_all_sectors.csv", index=False)

    link_summary = summarize_links(results)
    node_summary = summarize_nodes(results)
    diagnostics = {
        "negative_pressures": check_negative_pressures(results),
        "negative_flows": check_negative_flows(results),
        "low_pressures": check_low_pressures(results, min_pressure=10.0),
        "high_velocities": check_high_velocities(results, max_velocity=2.0),
        "sector_pressures": all_sector_pressures,
    }

    print(results["metadata"])
    print("Sector pressure files written to:", output_folder)

    export_results_to_excel(
        results,
        output_folder / "epanet_results.xlsx",
        diagnostics=diagnostics,
    )
    export_summary_to_excel(
        link_summary,
        node_summary,
        output_folder / "epanet_summary.xlsx",
    )


if __name__ == "__main__":
    main()
