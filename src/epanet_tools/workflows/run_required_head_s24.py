"""Run the first minimum required-head experiment for Molino Florida sector 24."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
import shutil

import pandas as pd

from epanet_tools.analysis.required_head import binary_search_required_head, prepare_constant_head_scenario
from epanet_tools.hydraulic.runepanet import parse_node_pressures, report_has_hydraulic_warnings, run_epanet

M_PER_BAR = 10.197162129779


def run_s24(
    master_inp: str | Path = "data/molino_florida_5.inp",
    scenarios_csv: str | Path = "outputs/molino_florida/report/molino_florida_sector_scenarios.csv",
    executable: str | Path = r"C:\Program Files (x86)\EPANET 2.2\runepanet.exe",
    outdir: str | Path = "outputs/molino_florida/required_head/S24",
) -> dict[str, object]:
    master_inp=Path(master_inp); scenarios_csv=Path(scenarios_csv); executable=Path(executable); outdir=Path(outdir)
    for path,label in ((master_inp,"master INP"),(scenarios_csv,"scenario CSV"),(executable,"runepanet.exe")):
        if not path.exists(): raise FileNotFoundError(f"{label} not found: {path}")
    scenarios=pd.read_csv(scenarios_csv); row=scenarios.loc[scenarios["sector"]==24]
    if len(row)!=1: raise ValueError(f"Expected exactly one sector 24 row, found {len(row)}")
    row=row.iloc[0]; nodes=[v for v in str(row["active_nodes"]).split(";") if v]; q=float(row["q_sprinkler_l_min"]); target=float(row["pressure_target_bar"])
    demands={node:q for node in nodes}; outdir.mkdir(parents=True,exist_ok=True)
    trial_counter=0
    def evaluate(head_m: float) -> tuple[float,str]:
        nonlocal trial_counter
        trial_counter+=1; stem=f"s24_trial_{trial_counter:02d}_{head_m:.4f}m"; inp=outdir/f"{stem}.inp"; rpt=outdir/f"{stem}.rpt"; binary=outdir/f"{stem}.bin"
        prepare_constant_head_scenario(master_inp,inp,active_demands_l_min=demands,trial_head_m=head_m)
        run_epanet(executable,inp,rpt,binary)
        if report_has_hydraulic_warnings(rpt): raise RuntimeError(f"Hydraulic warning in trial {head_m:.4f} m; inspect {rpt}")
        pressure_m=parse_node_pressures(rpt,nodes); pressure_bar={k:v/M_PER_BAR for k,v in pressure_m.items()}; critical=min(pressure_bar,key=pressure_bar.get)
        return pressure_bar[critical],critical
    required,trials=binary_search_required_head(evaluate,target_pressure_bar=target,low_head_m=0.0,high_head_m=80.0,pressure_tolerance_bar=0.01,head_tolerance_m=0.02,max_iterations=20)
    trials_df=pd.DataFrame([asdict(t) for t in trials]); trials_path=outdir/"s24_iterations.csv"; trials_df.to_csv(trials_path,index=False)
    # Re-run exact accepted head and keep a stable verification INP/RPT.
    final_inp=outdir/"s24_final.inp"; final_rpt=outdir/"s24_final.rpt"; final_bin=outdir/"s24_final.bin"
    prepare_constant_head_scenario(master_inp,final_inp,active_demands_l_min=demands,trial_head_m=required)
    run_epanet(executable,final_inp,final_rpt,final_bin); pressure_m=parse_node_pressures(final_rpt,nodes); pressure_bar={k:v/M_PER_BAR for k,v in pressure_m.items()}; critical=min(pressure_bar,key=pressure_bar.get); pmin=pressure_bar[critical]
    summary=pd.DataFrame([{"sector":24,"n_sprinklers":len(nodes),"q_sprinkler_l_min":q,"q_sector_l_min":q*len(nodes),"target_pressure_bar":target,"required_head_m":required,"critical_node":critical,"achieved_min_pressure_bar":pmin,"margin_bar":pmin-target,"reservoir_reference_head_m":0.0}])
    summary_path=outdir/"s24_summary.csv"; summary.to_csv(summary_path,index=False)
    return {"status":"ok","sector":24,"required_head_m":required,"critical_node":critical,"min_pressure_bar":pmin,"target_pressure_bar":target,"iterations":len(trials),"iterations_csv":str(trials_path),"summary_csv":str(summary_path),"final_inp":str(final_inp),"final_rpt":str(final_rpt)}

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--master-inp",default="data/molino_florida_5.inp"); p.add_argument("--scenarios-csv",default="outputs/molino_florida/report/molino_florida_sector_scenarios.csv"); p.add_argument("--epanet",default=r"C:\Program Files (x86)\EPANET 2.2\runepanet.exe"); p.add_argument("--outdir",default="outputs/molino_florida/required_head/S24"); a=p.parse_args(); print(run_s24(a.master_inp,a.scenarios_csv,a.epanet,a.outdir))

if __name__=="__main__": main()
