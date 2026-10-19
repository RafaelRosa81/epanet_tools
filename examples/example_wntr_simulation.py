"""Run an INP and export full-precision time series and summaries to Excel."""
import argparse
from pathlib import Path

import pandas as pd

from epanet_postprocess.simulation import run_inp


def main() -> None:
    parser = argparse.ArgumentParser(description="EPANET simulation via WNTR")
    parser.add_argument("inp", type=Path, help="EPANET .inp model")
    parser.add_argument("--output", type=Path, default=Path("outputs/wntr_results.xlsx"))
    args = parser.parse_args()

    data = run_inp(args.inp)
    nodes, links = data["nodes"], data["links"]
    node_summary = nodes.groupby(["id", "element_type"], as_index=False).agg(
        pressure_min_m=("pressure_m", "min"),
        pressure_max_m=("pressure_m", "max"),
        pressure_mean_m=("pressure_m", "mean"),
        demand_max_lps=("demand_lps", "max"),
    )
    pipe_links = links[links["element_type"] == "Pipe"]
    pipe_summary = pipe_links.groupby("id", as_index=False).agg(
        velocity_max_m_s=("velocity_m_s", lambda s: s.abs().max()),
        flow_max_abs_lps=("flow_lps", lambda s: s.abs().max()),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(args.output, engine="openpyxl") as writer:
        for sheet, table in {
            "Nodes": nodes, "Links": links,
            "Node summary": node_summary, "Pipe summary": pipe_summary,
        }.items():
            table.to_excel(writer, sheet_name=sheet, index=False)
            ws = writer.sheets[sheet]
            for row in ws.iter_rows(min_row=2):
                for cell in row:
                    if isinstance(cell.value, (float, int)) and not isinstance(cell.value, bool):
                        cell.number_format = "0.0000"
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
