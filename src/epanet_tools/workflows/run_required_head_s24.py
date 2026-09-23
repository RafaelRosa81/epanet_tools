"""Run the first minimum required-head experiment for Molino Florida sector 24."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from epanet_tools.analysis.required_head import binary_search_required_head, prepare_constant_head_scenario
from epanet_tools.hydraulic.runepanet import (
    parse_node_pressures,
    pipe_hydraulic_results,
    report_has_hydraulic_warnings,
    run_epanet,
)

M_PER_BAR = 10.197162129779


def _report_warning_types(rpt: str | Path) -> set[str]:
    """Classify hydraulic warnings relevant to the required-head search."""
    text=Path(rpt).read_text(encoding="utf-8",errors="replace").lower()
    tokens={
        "negative_pressures":"negative pressures",
        "system_unbalanced":"system unbalanced",
        "system_disconnected":"system disconnected",
        "ill_conditioned":"ill-conditioned",
        "cannot_solve":"cannot solve network hydraulic equations",
    }
    return {name for name,token in tokens.items() if token in text}


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
    trial_warning_types: dict[int,str] = {}
    def evaluate(head_m: float) -> tuple[float,str]:
        nonlocal trial_counter
        trial_counter+=1; stem=f"s24_trial_{trial_counter:02d}_{head_m:.4f}m"; inp=outdir/f"{stem}.inp"; rpt=outdir/f"{stem}.rpt"; binary=outdir/f"{stem}.bin"
        prepare_constant_head_scenario(master_inp,inp,active_demands_l_min=demands,trial_head_m=head_m)
        run_epanet(executable,inp,rpt,binary)
        warnings=_report_warning_types(rpt)
        trial_warning_types[trial_counter]=";".join(sorted(warnings))
        severe=warnings-{"negative_pressures"}
        if severe:
            raise RuntimeError(f"Severe hydraulic warning in trial {head_m:.4f} m ({', '.join(sorted(severe))}); inspect {rpt}")
        # Negative pressure is an expected lower-bound result in a minimum-head
        # search. EPANET still supplies the node pressures, so let the binary
        # search classify this trial as insufficient and increase the head.
        pressure_m=parse_node_pressures(rpt,nodes); pressure_bar={k:v/M_PER_BAR for k,v in pressure_m.items()}; critical=min(pressure_bar,key=pressure_bar.get)
        return pressure_bar[critical],critical
    required,trials=binary_search_required_head(evaluate,target_pressure_bar=target,low_head_m=0.0,high_head_m=80.0,pressure_tolerance_bar=0.01,head_tolerance_m=0.02,max_iterations=20)
    trials_df=pd.DataFrame([asdict(t) for t in trials])
    trials_df["warning_types"]=[trial_warning_types.get(i,"") for i in range(1,len(trials_df)+1)]
    trials_path=outdir/"s24_iterations.csv"; trials_df.to_csv(trials_path,index=False)

    final_inp=outdir/"s24_final.inp"; final_rpt=outdir/"s24_final.rpt"; final_bin=outdir/"s24_final.bin"
    prepare_constant_head_scenario(master_inp,final_inp,active_demands_l_min=demands,trial_head_m=required)
    run_epanet(executable,final_inp,final_rpt,final_bin)
    if report_has_hydraulic_warnings(final_rpt): raise RuntimeError(f"Hydraulic warning in final S24 run; inspect {final_rpt}")
    pressure_m=parse_node_pressures(final_rpt,nodes); pressure_bar={k:v/M_PER_BAR for k,v in pressure_m.items()}; critical=min(pressure_bar,key=pressure_bar.get); pmin=pressure_bar[critical]

    # Pipe audit: retain every pipe carrying meaningful flow in the final hydraulic state.
    pipe_rows=pipe_hydraulic_results(final_inp,final_rpt,min_abs_flow_l_min=0.01)
    pipes_df=pd.DataFrame(pipe_rows)
    if not pipes_df.empty:
        pipes_df.insert(0,"sector",24)
        pipes_df=pipes_df.sort_values(["velocity_m_s","abs_flow_l_min"],ascending=[False,False])
        max_row=pipes_df.iloc[0]
        max_velocity=float(max_row["velocity_m_s"]); max_velocity_pipe=str(max_row["pipe_id"])
        active_pipe_count=len(pipes_df)
        weighted_velocity=float((pipes_df["velocity_m_s"]*pipes_df["abs_flow_l_min"]).sum()/pipes_df["abs_flow_l_min"].sum())
    else:
        max_velocity=float("nan"); max_velocity_pipe=""; active_pipe_count=0; weighted_velocity=float("nan")
    pipes_path=outdir/"s24_pipe_velocities.csv"; pipes_df.to_csv(pipes_path,index=False)

    summary=pd.DataFrame([{
        "sector":24,"n_sprinklers":len(nodes),"q_sprinkler_l_min":q,"q_sector_l_min":q*len(nodes),
        "target_pressure_bar":target,"required_head_m":required,"critical_node":critical,
        "achieved_min_pressure_bar":pmin,"margin_bar":pmin-target,"reservoir_reference_head_m":0.0,
        "active_pipe_count":active_pipe_count,"max_velocity_m_s":max_velocity,
        "max_velocity_pipe":max_velocity_pipe,"flow_weighted_mean_velocity_m_s":weighted_velocity,
    }])
    summary_path=outdir/"s24_summary.csv"; summary.to_csv(summary_path,index=False)
    return {
        "status":"ok","sector":24,"required_head_m":required,"critical_node":critical,
        "min_pressure_bar":pmin,"target_pressure_bar":target,"iterations":len(trials),
        "active_pipe_count":active_pipe_count,"max_velocity_m_s":max_velocity,"max_velocity_pipe":max_velocity_pipe,
        "iterations_csv":str(trials_path),"summary_csv":str(summary_path),"pipe_velocities_csv":str(pipes_path),
        "final_inp":str(final_inp),"final_rpt":str(final_rpt),
    }

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--master-inp",default="data/molino_florida_5.inp"); p.add_argument("--scenarios-csv",default="outputs/molino_florida/report/molino_florida_sector_scenarios.csv"); p.add_argument("--epanet",default=r"C:\Program Files (x86)\EPANET 2.2\runepanet.exe"); p.add_argument("--outdir",default="outputs/molino_florida/required_head/S24"); a=p.parse_args(); print(run_s24(a.master_inp,a.scenarios_csv,a.epanet,a.outdir))

if __name__=="__main__": main()
