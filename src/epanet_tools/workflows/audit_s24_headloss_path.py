"""Build a hydraulic balance for the critical feed path into sector 24."""
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd

from epanet_tools.hydraulic.runepanet import parse_link_flows


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


def _parse_link_table(rpt: str|Path, wanted: set[str]):
    """Parse Flow, Velocity and Headloss from EPANET's standard link table.

    We identify rows by known link IDs instead of relying on a table-start
    phrase, which varies slightly between EPANET report formats.
    """
    out={}
    for line in Path(rpt).read_text(encoding="utf-8",errors="replace").splitlines():
        cols=line.split()
        if len(cols)<4 or cols[0] not in wanted:
            continue
        try:
            out[cols[0]]={
                "flow_l_min":float(cols[1]),
                "velocity_m_s":float(cols[2]),
                "headloss_m_per_km":float(cols[3]),
            }
        except ValueError:
            continue
    return out

def audit(inp,rpt,outdir):
    inp=Path(inp); rpt=Path(rpt); outdir=Path(outdir); outdir.mkdir(parents=True,exist_ok=True)
    sec=_sections(inp.read_text(encoding="utf-8-sig",errors="replace"))
    pipes={r[0]:{"node1":r[1],"node2":r[2],"length_m":float(r[3]),"diameter_mm":float(r[4]),"roughness":float(r[5])} for r in _rows(sec.get("PIPES",[])) if len(r)>=6}
    hyd=_parse_link_table(rpt,set(pipes))
    if not hyd:
        raise RuntimeError(f"No pipe hydraulic results parsed from {rpt}")
    sequence=["PRI_P037","PRI_P038","24_P019","24_P089","24_P018","24_P088"]
    rows=[]
    for pid in sequence:
        if pid not in pipes: continue
        d=dict(pipe_id=pid,**pipes[pid]); h=hyd.get(pid,{})
        d.update(h)
        d["headloss_m"]=h["headloss_m_per_km"]*d["length_m"]/1000.0 if "headloss_m_per_km" in h else float("nan")
        rows.append(d)
    df=pd.DataFrame(rows); path=outdir/"s24_feed_headloss_detail.csv"; df.to_csv(path,index=False)
    allrows=[]
    for pid,p in pipes.items():
        if pid not in hyd: continue
        h=hyd[pid]; loss=h["headloss_m_per_km"]*p["length_m"]/1000.0
        allrows.append({"pipe_id":pid,**p,**h,"headloss_m":loss})
    rank=pd.DataFrame(allrows)
    if rank.empty:
        raise RuntimeError(f"No pipe rows available for hydraulic ranking from {rpt}")
    rank=rank.sort_values("headloss_m",ascending=False)
    rank_path=outdir/"s24_pipe_headloss_ranking.csv"; rank.to_csv(rank_path,index=False)
    common=["PRI_P001","PRI_P002","PRI_P003","PRI_P004","PRI_P005","PRI_P006","PRI_P007","PRI_P008","PRI_P009","PRI_P010","PRI_P011","PRI_P012","PRI_P013","PRI_P014","PRI_P015","PRI_P035","PRI_P037","PRI_P038","24_P019"]
    common_df=rank[rank["pipe_id"].isin(common)].copy()
    common_path=outdir/"s24_common_feed_headloss.csv"; common_df.to_csv(common_path,index=False)
    p019=rank.loc[rank["pipe_id"]=="24_P019"]
    summary={
        "common_feed_pipe_count":len(common_df),
        "common_feed_total_headloss_m":float(common_df["headloss_m"].sum()) if len(common_df) else float("nan"),
        "p019_headloss_m":float(p019["headloss_m"].iloc[0]) if len(p019) else float("nan"),
        "p019_velocity_m_s":float(p019["velocity_m_s"].iloc[0]) if len(p019) else float("nan"),
    }
    summary_path=outdir/"s24_headloss_summary.csv"; pd.DataFrame([summary]).to_csv(summary_path,index=False)
    return {"status":"ok",**summary,"detail_csv":str(path),"common_feed_csv":str(common_path),"ranking_csv":str(rank_path),"summary_csv":str(summary_path)}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inp",default="outputs/molino_florida/required_head/S24/s24_final.inp")
    p.add_argument("--rpt",default="outputs/molino_florida/required_head/S24/s24_final.rpt")
    p.add_argument("--outdir",default="outputs/molino_florida/required_head/S24/topology_audit")
    a=p.parse_args(); print(audit(a.inp,a.rpt,a.outdir))
if __name__=="__main__": main()
