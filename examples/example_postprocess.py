"""Example: read an EPANET report, diagnose it and write outputs.

Usage
-----
python examples/example_postprocess.py palo_alto_secundarias.rpt

On Windows, wrap long paths in quotes:
python examples/example_postprocess.py "H:\path\to\palo_alto_secundarias.rpt"
"""

from __future__ import annotations

import argparse
from pathlib import Path

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
    return parser.parse_args()


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
    plot_node_pressures(
        results,
        nodes=["J000021", "J000024"],
        output=output_folder / "pressures_selected_nodes.png",
    )

    link_summary = summarize_links(results)
    node_summary = summarize_nodes(results)
    diagnostics = {
        "negative_pressures": check_negative_pressures(results),
        "negative_flows": check_negative_flows(results),
        "low_pressures": check_low_pressures(results, min_pressure=10.0),
        "high_velocities": check_high_velocities(results, max_velocity=2.0),
    }

    print(results["metadata"])
    print(diagnostics["negative_pressures"])

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
