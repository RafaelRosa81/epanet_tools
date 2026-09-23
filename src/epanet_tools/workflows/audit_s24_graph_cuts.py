"""Audit graph bridges and articulation points between P-0001 and S24 sprinklers."""
from __future__ import annotations
import argparse
from collections import defaultdict, deque
from pathlib import Path
import pandas as pd


def _sections(text):
    out={}; cur=""
    for line in text.splitlines():
        s=line.strip()
        if s.startswith("[") and s.endswith("]"):
            cur=s[1:-1].upper(); out.setdefault(cur,[])
        elif cur: out[cur].append(line)
    return out

def _rows(lines):
    for line in lines:
        raw=line.split(";",1)[0].strip()
        if raw: yield raw.split()

def _reachable(adj, source, blocked_edge=None, blocked_node=None):
    if source==blocked_node: return set()
    seen={source}; q=deque([source])
    while q:
        u=q.popleft()
        for v,eid in adj.get(u,[]):
            if v==blocked_node: continue
            if blocked_edge and eid==blocked_edge: continue
            if v not in seen: seen.add(v); q.append(v)
    return seen

def audit(inp, scenarios_csv, outdir):
    inp=Path(inp); outdir=Path(outdir); outdir.mkdir(parents=True,exist_ok=True)
    sec=_sections(inp.read_text(encoding="utf-8-sig",errors="replace"))
    links=[]
    for section in ("PIPES","PUMPS","VALVES"):
        for r in _rows(sec.get(section,[])):
            if len(r)>=3: links.append((r[0],r[1],r[2],section))
    adj=defaultdict(list)
    for eid,a,b,typ in links:
        adj[a].append((b,eid)); adj[b].append((a,eid))
    row=pd.read_csv(scenarios_csv).loc[lambda d:d["sector"]==24].iloc[0]
    sprinklers=[x for x in str(row["active_nodes"]).split(";") if x]; source="P-0001"
    base=_reachable(adj,source)
    missing=[n for n in sprinklers if n not in base]
    if missing: raise RuntimeError(f"Sprinklers unreachable before cut audit: {missing}")
    edge_rows=[]
    for eid,a,b,typ in links:
        seen=_reachable(adj,source,blocked_edge=eid)
        lost=[n for n in sprinklers if n not in seen]
        if lost:
            edge_rows.append({"link_id":eid,"node1":a,"node2":b,"link_type":typ,"sprinklers_lost":len(lost),"all_12_lost":len(lost)==len(sprinklers),"lost_nodes":";".join(lost)})
    edge_df=pd.DataFrame(edge_rows)
    if not edge_df.empty: edge_df=edge_df.sort_values(["sprinklers_lost","link_id"],ascending=[False,True])
    edge_path=outdir/"s24_critical_edge_cuts.csv"; edge_df.to_csv(edge_path,index=False)
    nodes=set(adj)
    node_rows=[]
    for node in nodes-{source}:
        seen=_reachable(adj,source,blocked_node=node)
        lost=[n for n in sprinklers if n!=node and n not in seen]
        direct=1 if node in sprinklers else 0
        total=len(lost)+direct
        if total:
            node_rows.append({"node_id":node,"degree":len(adj[node]),"sprinklers_lost":total,"all_12_lost":total==len(sprinklers),"node_is_sprinkler":node in sprinklers,"lost_nodes":";".join(([node] if node in sprinklers else [])+lost)})
    node_df=pd.DataFrame(node_rows)
    if not node_df.empty: node_df=node_df.sort_values(["sprinklers_lost","node_id"],ascending=[False,True])
    node_path=outdir/"s24_critical_articulation_nodes.csv"; node_df.to_csv(node_path,index=False)
    full_edges=edge_df[edge_df["all_12_lost"]==True] if not edge_df.empty else edge_df
    full_nodes=node_df[node_df["all_12_lost"]==True] if not node_df.empty else node_df
    summary=pd.DataFrame([{"sector":24,"source_node":source,"sprinkler_count":len(sprinklers),"single_link_cuts_disconnect_all":len(full_edges),"single_node_cuts_disconnect_all":len(full_nodes),"full_cut_links":";".join(full_edges["link_id"].astype(str)) if len(full_edges) else "","full_cut_nodes":";".join(full_nodes["node_id"].astype(str)) if len(full_nodes) else ""}])
    summary_path=outdir/"s24_graph_cut_summary.csv"; summary.to_csv(summary_path,index=False)
    return {"status":"ok","critical_link_count":len(edge_df),"critical_node_count":len(node_df),"full_cut_link_count":len(full_edges),"full_cut_node_count":len(full_nodes),"summary_csv":str(summary_path),"edge_csv":str(edge_path),"node_csv":str(node_path)}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inp",default="outputs/molino_florida/required_head/S24/s24_final.inp")
    p.add_argument("--scenarios-csv",default="outputs/molino_florida/report/molino_florida_sector_scenarios.csv")
    p.add_argument("--outdir",default="outputs/molino_florida/required_head/S24/topology_audit")
    a=p.parse_args(); print(audit(a.inp,a.scenarios_csv,a.outdir))
if __name__=="__main__": main()
