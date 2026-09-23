from pathlib import Path

from epanet_tools.analysis.required_head import binary_search_required_head, prepare_constant_head_scenario


def test_binary_search_required_head():
    def evaluate(h):
        return (h - 10.0) / 10.0, "J1"
    head,trials=binary_search_required_head(evaluate,target_pressure_bar=2.0,low_head_m=0,high_head_m=50,pressure_tolerance_bar=0.001,head_tolerance_m=0.01)
    assert abs(head-30.0)<0.1
    assert trials[-1].critical_node=="J1"


def test_prepare_constant_head_scenario(tmp_path: Path):
    src=tmp_path/"master.inp"; out=tmp_path/"trial.inp"
    src.write_text("""[JUNCTIONS]\nJ1 0 5 S24_ON\nJ2 0 6 S24_ON\nJ3 0 7\n[RESERVOIRS]\nTanque_1 8\n[PIPES]\nP1 J1 J2 10 50 120 0 OPEN\n[PUMPS]\nB_Impulsion Tanque_1 J1 HEAD C1\n[DEMANDS]\nJ1 2 X\n[CONTROLS]\nLINK B_Impulsion OPEN AT TIME 0\n[RULES]\n; none\n[TIMES]\nDURATION 10:00\n[PATTERNS]\nS24_ON 0 0 0 1 1 0\n[REPORT]\nSTATUS NO\n[END]\n""",encoding="utf-8")
    prepare_constant_head_scenario(src,out,active_demands_l_min={"J2":97.2},trial_head_m=31.5)
    text=out.read_text(encoding="utf-8")
    assert "Tanque_1\t31.5" in text
    assert "J2\t0\t97.2" in text
    assert "J1\t0\t0.0" in text
    assert "J3\t0\t0.0" in text
    # The source schedule may remain defined in [PATTERNS], but no junction in
    # the constant-head experiment is allowed to reference it.
    junction_block=text.split("[JUNCTIONS]",1)[1].split("[RESERVOIRS]",1)[0]
    assert "S24_ON" not in junction_block
    assert "B_Impulsion\tTanque_1\tJ1\t0.01\t1000.0" in text
    assert "DURATION\t0:00" in text
    assert "NODES\tALL" in text
