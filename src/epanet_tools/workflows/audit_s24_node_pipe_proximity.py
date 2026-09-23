"""Audit S24 nodes that lie close to non-incident pipe segments.

This complements the node-to-node near-miss audit by detecting a common GIS/
EPANET topology defect: a node visually lying on (or very close to) a pipe
whose endpoints do not include that node, i.e. a missing split/snap.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd


def _sections(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}; current = ""
    for line in text.splitlines():
        s=line.strip()
        if s.startswith("[") and s.endswith("]"):
            current=s[1:-1].upper(); out.setdefault(current,[])
        elif current:
            out[current].append(line)
    return out


def _rows(lines: list[str]):
    for line in lines:
        raw=line.split(";",1)[0].strip()
        if raw:
            yield raw.split()


def _point_segment_distance(px,py,ax,ay,bx,by):
    vx,vy=bx-ax,by-ay; wx,wy=px-ax,py-ay
    vv=vx*vx+vy*vy
    if vv == 0:
        return math.hypot(px-ax,py-ay),0.0,(ax,ay)
    t=max(0.0,min(1.0,(wx*vx+wy*vy)/vv))
    qx,qy=ax+t*vx,ay+t*vy
    return math.hypot(px-qx,py-qy),t,(qx,qy)


def audit(inp: str|Path, outdir: str|Path, threshold_m: float=0.50):
    inp=Path(inp); outdir=Path(outdir); outdir.mkdir(parents=True,exist_ok=True)
    sec=_sections(inp.read_text(encoding="utf-8-sig",errors="replace"))
    coords={r[0]:(float(r[1]),float(r[2])) for r in _rows(sec.get("COORDINATES",[])) if len(r)>=3}
    pipes=[]
    for r in _rows(sec.get("PIPES",[])):
        if len(r)>=3 and r[1] in coords and r[2] in coords:
            pipes.append((r[0],r[1],r[2],float(r[4]) if len(r)>4 else float("nan")))
    s24=sorted(n for n in coords if n.startswith("24_J"))
    rows=[]
    for node in s24:
        px,py=coords[node]
        for pid,n1,n2,diam in pipes:
            if node in (n1,n2):
                continue
            ax,ay=coords[n1]; bx,by=coords[n2]
            d,t,(qx,qy)=_point_segment_distance(px,py,ax,ay,bx,by)
            if d <= threshold_m:
                rows.append({"s24_node":node,"pipe_id":pid,"pipe_node1":n1,"pipe_node2":n2,"diameter_mm":diam,"distance_m":d,"projection_fraction":t,"projection_x":qx,"projection_y":qy,"projection_inside_segment":0.0<t<1.0,"pipe_is_s24":pid.startswith("24_")})
    df=pd.DataFrame(rows)
    if not df.empty:
        df=df.sort_values(["distance_m","s24_node","pipe_id"])
    path=outdir/"s24_node_pipe_near_misses.csv"; df.to_csv(path,index=False)
    # Focused table for the bottleneck endpoints and their immediate neighbours.
    focus={"24_J061","24_J016","24_J060"}
    focus_df=df[df["s24_node"].isin(focus)].copy() if not df.empty else pd.DataFrame()
    focus_path=outdir/"s24_P019_node_pipe_proximity.csv"; focus_df.to_csv(focus_path,index=False)
    return {"status":"ok","threshold_m":threshold_m,"candidate_count":len(df),"focus_count":len(focus_df),"candidates_csv":str(path),"focus_csv":str(focus_path)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inp",default="outputs/molino_florida/required_head/S24/s24_final.inp")
    p.add_argument("--outdir",default="outputs/molino_florida/required_head/S24/topology_audit")
    p.add_argument("--threshold-m",type=float,default=0.50)
    a=p.parse_args(); print(audit(a.inp,a.outdir,a.threshold_m))

if __name__=="__main__": main()
