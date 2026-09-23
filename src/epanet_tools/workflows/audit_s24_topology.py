"""Audit topology and hydraulic paths for the final S24 required-head scenario."""
from __future__ import annotations

import argparse
from pathlib import Path

import networkx as nx
import pandas as pd

from epanet_tools.hydraulic.runepanet import parse_inp_pipes, parse_link_flows


def _active_nodes_from_scenarios(path: Path, sector: int) -> list[str]:
    df = pd.read_csv(path)
    row = df.loc[df["sector"] == sector]
    if len(row) != 1:
        raise ValueError(f"Expected one row for sector {sector}, found {len(row)}")
    return [x for x in str(row.iloc[0]["active_nodes"]).split(";") if x]


def audit_s24_topology(
    inp: str | Path = "outputs/molino_florida/required_head/S24/s24_final.inp",
    rpt: str | Path = "outputs/molino_florida/required_head/S24/s24_final.rpt",
    scenarios_csv: str | Path = "outputs/molino_florida/report/molino_florida_sector_scenarios.csv",
    outdir: str | Path = "outputs/molino_florida/required_head/S24/topology_audit",
    source_node: str = "P-0001",
) -> dict[str, object]:
    inp, rpt, scenarios_csv, outdir = map(Path, (inp, rpt, scenarios_csv, outdir))
    for p in (inp, rpt, scenarios_csv):
        if not p.exists():
            raise FileNotFoundError(p)
    outdir.mkdir(parents=True, exist_ok=True)

    sprinklers = _active_nodes_from_scenarios(scenarios_csv, 24)
    pipes = parse_inp_pipes(inp)
    flows = parse_link_flows(rpt, list(pipes))

    g = nx.Graph()
    for pid, meta in pipes.items():
        u, v = str(meta["from_node"]), str(meta["to_node"])
        g.add_edge(u, v, pipe_id=pid, diameter_mm=float(meta["diameter_mm"]), abs_flow_l_min=abs(float(flows.get(pid, 0.0))))

    if source_node not in g:
        raise ValueError(f"Source node {source_node} not found in pipe graph")

    path_rows: list[dict[str, object]] = []
    usage: dict[str, int] = {}
    for sprinkler in sprinklers:
        if sprinkler not in g:
            raise ValueError(f"Sprinkler {sprinkler} not found in pipe graph")
        # Structural shortest path: number of pipe edges, independent of hydraulic flow.
        nodes = nx.shortest_path(g, source_node, sprinkler)
        for order, (u, v) in enumerate(zip(nodes, nodes[1:]), start=1):
            e = g[u][v]; pid = str(e["pipe_id"]); usage[pid] = usage.get(pid, 0) + 1
            path_rows.append({
                "sprinkler": sprinkler, "order": order, "pipe_id": pid,
                "from_node_path": u, "to_node_path": v,
                "diameter_mm": e["diameter_mm"], "abs_flow_l_min": e["abs_flow_l_min"],
            })

    paths = pd.DataFrame(path_rows)
    paths.to_csv(outdir / "s24_paths_from_P0001.csv", index=False)

    common = pd.DataFrame([
        {"pipe_id": pid, "path_count": count, "fraction_of_12_paths": count / len(sprinklers),
         "diameter_mm": pipes[pid]["diameter_mm"], "from_node": pipes[pid]["from_node"],
         "to_node": pipes[pid]["to_node"], "abs_flow_l_min": abs(float(flows.get(pid, 0.0)))}
        for pid, count in usage.items()
    ]).sort_values(["path_count", "abs_flow_l_min"], ascending=[False, False])
    common.to_csv(outdir / "s24_common_path_pipes.csv", index=False)

    # Local neighborhood of the suspected bottleneck and its two endpoints.
    bottleneck = "24_P019"
    if bottleneck not in pipes:
        raise ValueError(f"{bottleneck} not found")
    a, b = str(pipes[bottleneck]["from_node"]), str(pipes[bottleneck]["to_node"])
    neighborhood_nodes = {a, b} | set(g.neighbors(a)) | set(g.neighbors(b))
    local_rows=[]
    seen=set()
    for u in neighborhood_nodes:
        for v, e in g[u].items():
            pid=str(e["pipe_id"])
            if pid in seen: continue
            if u in neighborhood_nodes or v in neighborhood_nodes:
                seen.add(pid)
                local_rows.append({"pipe_id":pid,"node1":u,"node2":v,"diameter_mm":e["diameter_mm"],"flow_l_min":float(flows.get(pid,0.0)),"abs_flow_l_min":e["abs_flow_l_min"]})
    local=pd.DataFrame(local_rows).sort_values("abs_flow_l_min",ascending=False)
    local.to_csv(outdir / "s24_P019_neighborhood.csv",index=False)

    # Cut test: removing P019 tells us whether it is a true topological bridge from source to sprinklers.
    g2=g.copy(); g2.remove_edge(a,b)
    disconnected=[s for s in sprinklers if not nx.has_path(g2,source_node,s)]
    summary=pd.DataFrame([{
        "sector":24,"source_node":source_node,"sprinkler_count":len(sprinklers),
        "bottleneck_pipe":bottleneck,"bottleneck_from":a,"bottleneck_to":b,
        "bottleneck_diameter_mm":pipes[bottleneck]["diameter_mm"],
        "bottleneck_abs_flow_l_min":abs(float(flows.get(bottleneck,0.0))),
        "shortest_paths_using_bottleneck":usage.get(bottleneck,0),
        "sprinklers_disconnected_if_bottleneck_removed":len(disconnected),
        "disconnected_sprinklers":";".join(disconnected),
    }])
    summary.to_csv(outdir / "s24_topology_summary.csv",index=False)
    return {"status":"ok","summary":summary.iloc[0].to_dict(),"outdir":str(outdir)}


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inp",default="outputs/molino_florida/required_head/S24/s24_final.inp")
    p.add_argument("--rpt",default="outputs/molino_florida/required_head/S24/s24_final.rpt")
    p.add_argument("--scenarios-csv",default="outputs/molino_florida/report/molino_florida_sector_scenarios.csv")
    p.add_argument("--outdir",default="outputs/molino_florida/required_head/S24/topology_audit")
    a=p.parse_args(); print(audit_s24_topology(a.inp,a.rpt,a.scenarios_csv,a.outdir))

if __name__ == "__main__": main()
