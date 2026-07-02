"""Example: read an EPANET report, diagnose it and write outputs."""

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

results = read_rpt("palo_alto_secundarias.rpt")

plot_link_flows(
    results,
    links=["P000008", "P000009", "P000016"],
    output="outputs/postprocess/flows_selected_links.png",
)
plot_node_pressures(
    results,
    nodes=["J000021", "J000024"],
    output="outputs/postprocess/pressures_selected_nodes.png",
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
    "outputs/postprocess/epanet_results.xlsx",
    diagnostics=diagnostics,
)
export_summary_to_excel(
    link_summary,
    node_summary,
    "outputs/postprocess/epanet_summary.xlsx",
)
