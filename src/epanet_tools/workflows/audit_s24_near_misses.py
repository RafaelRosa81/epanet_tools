"""Find geometrically close but topologically disconnected nodes around sector 24."""
from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

import networkx as nx
import pandas as pd

from epanet_tools.hydraulic.runepanet import parse_inp_pipes


def _section(text: str, name: str) -> list[str]:
    m=re.search(rf"(?ms)^\s*\[{re.escape(name)}\]\s*$\n(.*?)(?=^\s*\[[^]]+\]\s*$|\Z)",text)
    return m.group(1).splitlines() if m else []


def _coordinates(inp: Path) -> dict[str,tuple[float,float]]:
    text=inp.read_text(encoding="utf-8-sig",errors="replace")
    out={}
    for line in _section(text,"COORDINATES"):
        raw=line.split(";",1)[0].strip(); cols=raw.split()
        if len(cols)>=3:
            try: out[cols[0]]=(float(cols[1]),float(cols[2]))
            except ValueError: pass
    return out


def audit(
    inp: str|Path="outputs/molino_florida/required_head/S24/s24_final.inp",
    outdir: str|Path="outputs/molino_florida/required_head/S24/topology_audit",
    radius_m: float=1.0,
) -> dict[str,object]:
    inp,outdir=Path(inp),Path(outdir); outdir.mkdir(parents=True,exist_ok=True)
    pipes=parse_inp_pipes(inp); xy=_coordinates(inp)
    g=nx.Graph()
    for pid,p in pipes.items(): g.add_edge(str(p["from_node"]),str(p["to_node"]),pipe_id=pid)
    focus={n for n in g if n.startswith("24_")} | {"24_J061","24_J016"}
    rows=[]
    nodes=list(xy)
    for a in sorted(focus):
        if a not in xy: continue
        ax,ay=xy[a]
        for b in nodes:
            if b==a or b in g.neighbors(a): continue
            bx,by=xy[b]; d=math.hypot(ax-bx,ay-by)
            if d<=radius_m:
                rows.append({"s24_node":a,"near_node":b,"distance_m":d,"near_node_is_s24":b.startswith("24_"),"already_connected":False,"same_component":nx.has_path(g,a,b) if b in g else False,"s24_degree":g.degree(a),"near_degree":g.degree(b) if b in g else 0})
    df=pd.DataFrame(rows)
    if not df.empty: df=df.sort_values(["distance_m","s24_node","near_node"])
    path=outdir/"s24_near_miss_nodes.csv"; df.to_csv(path,index=False)
    # Special view around the two bottleneck endpoints, with a wider 5 m search.
    local=[]
    for a in ("24_J061","24_J016"):
        if a not in xy: continue
        ax,ay=xy[a]
        for b,(bx,by) in xy.items():
            if b==a: continue
            d=math.hypot(ax-bx,ay-by)
            if d<=5.0:
                local.append({"endpoint":a,"node":b,"distance_m":d,"connected_directly":g.has_edge(a,b),"node_degree":g.degree(b) if b in g else 0})
    local_df=pd.DataFrame(local)
    if not local_df.empty: local_df=local_df.sort_values(["endpoint","distance_m"])
    local_path=outdir/"s24_P019_endpoint_proximity.csv"; local_df.to_csv(local_path,index=False)
    return {"status":"ok","radius_m":radius_m,"near_miss_count":len(df),"near_miss_csv":str(path),"endpoint_csv":str(local_path)}


def main()->None:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--inp",default="outputs/molino_florida/required_head/S24/s24_final.inp"); p.add_argument("--outdir",default="outputs/molino_florida/required_head/S24/topology_audit"); p.add_argument("--radius-m",type=float,default=1.0); a=p.parse_args(); print(audit(a.inp,a.outdir,a.radius_m))

if __name__=="__main__": main()
