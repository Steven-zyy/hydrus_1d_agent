"""Tests for hydrus_agent.output_reader (milestone 4, revised).

Uses synthetic fixture files copied from the real HYDRUS-1D output of
config/simple_runnable_case.json. Does NOT require the real HYDRUS executable.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from hydrus_agent.output_reader import (
    DEFAULT_OUTPUT_NAMES,
    discover_outputs,
    find_output_file,
    read_balance,
    read_nod_inf,
    read_obs_node,
    read_outputs,
    read_run_inf,
    read_solute,
    read_t_level,
    summarise_outputs,
)


# --- Fixtures: real HYDRUS output slices ----------------------------------

BALANCE_FIXTURE = """\
 ******* Program HYDRUS
 ******* 
 simple infiltration column
 Date:   3. 5.2026    Time:  10:17:59
 Units: L = m    , T = days , M = mmol 

----------------------------------------------------------
 Time       [T]        0.0000
----------------------------------------------------------
 Sub-region num.                     1
----------------------------------------------------------
 Length   [L]        0.10000E+01  0.10000E+01
 W-volume [L]        0.12240E+00  0.12240E+00
 In-flow  [L/T]      0.00000E+00  0.00000E+00
 h Mean   [L]       -0.10000E+01 -0.10000E+01
 Top Flux [L/T]     -0.51504E-04
 Bot Flux [L/T]     -0.51504E-04
----------------------------------------------------------

----------------------------------------------------------
 Time       [T]        0.5000
----------------------------------------------------------
 Sub-region num.                     1
----------------------------------------------------------
 Length   [L]        0.10000E+01  0.10000E+01
 W-volume [L]        0.12187E+00  0.12187E+00
 In-flow  [L/T]     -0.10515E-02 -0.10515E-02
 h Mean   [L]       -0.10127E+01 -0.10127E+01
 Top Flux [L/T]      0.48496E-04
 Bot Flux [L/T]     -0.51504E-04
 WatBalT  [L]        0.81491E-09
 WatBalR  [%]              0.000
----------------------------------------------------------
 Calculation time [sec]  0.000000000000000E+000
"""


T_LEVEL_FIXTURE = """\
 ******* Program HYDRUS
 ******* 
 simple infiltration column
 Date:   3. 5.2026    Time:  10:17:59
 Units: L = m    , T = days , M = mmol 

       Time          rTop        rRoot        vTop         vRoot        vBot       sum(rTop)   sum(rRoot)    sum(vTop)   sum(vRoot)    sum(vBot)      hTop         hRoot        hBot        RunOff    sum(RunOff)     Volume     sum(Infil)    sum(Evap) TLevel Cum(WTrans)  SnowLayer
        [T]         [L/T]        [L/T]        [L/T]        [L/T]        [L/T]         [L]          [L]          [L]         [L]           [L]         [L]           [L]         [L]          [L/T]         [L]          [L]          [L]          [L]

       0.2500  0.10000E-02  0.00000E+00  0.10000E-02  0.00000E+00 -0.51504E-04  0.25000E-03  0.00000E+00  0.25000E-03  0.00000E+00 -0.12876E-04 -0.11076E+01  0.00000E+00 -0.10000E+01  0.00000E+00  0.00000E+00  0.12214E+00  0.00000E+00  0.25000E-03     17  0.00000E+00      0.000
       0.5000  0.10000E-02  0.00000E+00  0.10000E-02  0.00000E+00 -0.51504E-04  0.50000E-03  0.00000E+00  0.50000E-03  0.00000E+00 -0.25752E-04 -0.12423E+01  0.00000E+00 -0.10000E+01  0.00000E+00  0.00000E+00  0.12187E+00  0.00000E+00  0.50000E-03     20  0.00000E+00      0.000
       1.0000  0.10000E-02  0.00000E+00  0.10000E-02  0.00000E+00 -0.51504E-04  0.10000E-02  0.00000E+00  0.10000E-02  0.00000E+00 -0.51504E-04 -0.15818E+01  0.00000E+00 -0.10000E+01  0.00000E+00  0.00000E+00  0.12135E+00  0.00000E+00  0.10000E-02     24  0.00000E+00      0.000
end
"""


RUN_INF_FIXTURE = """\
 ******* Program HYDRUS
 ******* 
 simple infiltration column
 Date:   3. 5.2026    Time:  10:17:59
 Units: L = m    , T = days , M = mmol 


    TLevel      Time          dt      Iter    ItCum  KodT  KodB  Convergency

       17  0.2500000E+00  0.40990E-01    2       34    -1    -5     T
       20  0.5000000E+00  0.93750E-01    2       40    -1    -5     T
       24  0.1000000E+01  0.12500E+00    2       48    -1    -5     T
end
"""


OBS_NODE_FIXTURE = """\
 ******* Program HYDRUS
 ******* 
 simple infiltration column
 Date:   3. 5.2026    Time:  10:17:59
 Units: L = m    , T = days , M = mmol 



                               Node(  3)                      Node(  8)

         time            h        theta    Temp           h        theta    Temp  
          0.2500       -1.00  0.1224   20.000         -1.00  0.1224   20.000
          0.5000       -1.00  0.1224   20.000         -1.00  0.1224   20.000
          1.0000       -1.00  0.1224   20.000         -1.00  0.1224   20.000
end
"""


OBS_NODE_HEAT_SOLUTE_FIXTURE = """\
 ******* Program HYDRUS
 ******* 
 official-style observation output
 Date:   4. 5.2026    Time:  15:37:56
 Units: L = cm   , T = days , M = -



                               Node( 10)                                 Node( 20)

         time            h        theta    Temp     Conc              h        theta    Temp     Conc
          0.0500     -150.00  0.0773   20.000  0.0000E+00       -140.00  0.0873   21.000  0.1000E-01
          0.1000     -151.00  0.0774   20.100  0.2000E-01       -141.00  0.0874   21.100  0.3000E-01
end
"""


NOD_INF_FIXTURE = """\
 ******* Program HYDRUS
 ******* 
 simple infiltration column
 Date:   3. 5.2026    Time:  10:17:59
 Units: L = m    , T = days , M = mmol 


 Time:        0.0000


 Node      Depth      Head Moisture       K          C         Flux        Sink         Kappa   v/KsTop   Temp
           [L]        [L]    [-]        [L/T]      [1/L]      [L/T]        [1/T]         [-]      [-]      [C]

   1     0.0000      -1.000 0.1224   0.5150E-04  0.5105E-01 -0.5150E-04  0.0000E+00      -1  -0.485E-04   20.00
   2    -0.1000      -1.000 0.1224   0.5150E-04  0.5105E-01 -0.5150E-04  0.0000E+00      -1  -0.485E-04   20.00
end


 Time:        0.2500


 Node      Depth      Head Moisture       K          C         Flux        Sink         Kappa   v/KsTop   Temp
           [L]        [L]    [-]        [L/T]      [1/L]      [L/T]        [1/T]         [-]      [-]      [C]

   1     0.0000      -1.108 0.1173   0.3279E-04  0.4188E-01  0.1000E-02  0.0000E+00      -1   0.943E-03   20.00
   2    -0.1000      -1.002 0.1223   0.5122E-04  0.5091E-01 -0.2401E-04  0.0000E+00      -1  -0.226E-04   20.00
end
"""


# --- Discovery ------------------------------------------------------------


def test_find_output_file_case_insensitive(tmp_path):
    (tmp_path / "Balance.out").write_text("dummy")
    assert find_output_file(tmp_path, "BALANCE.OUT") == tmp_path / "Balance.out"
    assert find_output_file(tmp_path, "balance.out") == tmp_path / "Balance.out"
    assert find_output_file(tmp_path, "Balance.OUT") == tmp_path / "Balance.out"


def test_find_output_file_returns_none_when_missing(tmp_path):
    assert find_output_file(tmp_path, "T_Level.out") is None


def test_discover_outputs_uses_canonical_keys(tmp_path):
    (tmp_path / "balance.out").write_text("dummy")
    (tmp_path / "T_Level.OUT").write_text("dummy")
    found = discover_outputs(tmp_path)
    assert set(found.keys()) == set(DEFAULT_OUTPUT_NAMES)
    assert found["Balance.out"] is not None
    assert found["T_Level.out"] is not None
    assert found["Obs_Node.out"] is None


# --- Empty / missing ------------------------------------------------------


def test_read_balance_empty_file_returns_empty_df(tmp_path):
    f = tmp_path / "Balance.out"
    f.write_text("")
    assert read_balance(f).empty


def test_read_balance_missing_path(tmp_path):
    assert read_balance(tmp_path / "no_such.out").empty


def test_read_t_level_empty(tmp_path):
    f = tmp_path / "T_Level.out"
    f.write_text("")
    assert read_t_level(f).empty


def test_read_run_inf_empty(tmp_path):
    f = tmp_path / "Run_Inf.out"
    f.write_text("")
    assert read_run_inf(f).empty


def test_read_obs_node_empty(tmp_path):
    f = tmp_path / "Obs_Node.out"
    f.write_text("")
    assert read_obs_node(f).empty


def test_read_nod_inf_empty(tmp_path):
    f = tmp_path / "Nod_Inf.out"
    f.write_text("")
    assert read_nod_inf(f).empty


# --- Balance.out ----------------------------------------------------------


def test_read_balance_parses_fixture(tmp_path):
    f = tmp_path / "Balance.out"
    f.write_text(BALANCE_FIXTURE)
    df = read_balance(f)
    assert len(df) == 2
    expected = ["time", "length", "w_volume", "in_flow", "h_mean",
                "top_flux", "bot_flux", "wat_bal_t", "wat_bal_r"]
    assert list(df.columns) == expected
    assert df.iloc[0]["time"] == pytest.approx(0.0)
    assert df.iloc[0]["w_volume"] == pytest.approx(0.12240)
    assert df.iloc[0]["top_flux"] == pytest.approx(-0.51504e-4)
    assert pd.isna(df.iloc[0]["wat_bal_t"])
    assert df.iloc[1]["time"] == pytest.approx(0.5)
    assert df.iloc[1]["wat_bal_r"] == pytest.approx(0.0)


def test_read_balance_does_not_modify_source(tmp_path):
    f = tmp_path / "Balance.out"
    f.write_text(BALANCE_FIXTURE)
    before = f.read_text()
    read_balance(f)
    assert f.read_text() == before


# --- T_Level.out ----------------------------------------------------------


def test_read_t_level_parses_fixture(tmp_path):
    f = tmp_path / "T_Level.out"
    f.write_text(T_LEVEL_FIXTURE)
    df = read_t_level(f)
    assert len(df) == 3
    # Case-preserving column names per the user's preference.
    cols = list(df.columns)
    assert "Time" in cols
    assert "rTop" in cols
    assert "vTop" in cols
    assert "vBot" in cols
    assert "hTop" in cols
    assert "hBot" in cols
    assert "Volume" in cols
    assert "sum_Infil" in cols
    assert "TLevel" in cols
    assert "Cum_WTrans" in cols
    assert "SnowLayer" in cols
    # Numeric content of the first row.
    assert df.iloc[0]["Time"] == pytest.approx(0.25)
    assert df.iloc[0]["rTop"] == pytest.approx(1.0e-3)
    assert df.iloc[0]["Volume"] == pytest.approx(0.12214)


# --- Run_Inf.out ----------------------------------------------------------


def test_read_run_inf_parses_fixture(tmp_path):
    f = tmp_path / "Run_Inf.out"
    f.write_text(RUN_INF_FIXTURE)
    df = read_run_inf(f)
    assert len(df) == 3
    assert list(df.columns) == [
        "TLevel", "Time", "dt", "Iter", "ItCum", "KodT", "KodB", "Convergency",
    ]
    assert df.iloc[0]["TLevel"] == 17
    assert df.iloc[0]["Time"] == pytest.approx(0.25)
    assert df.iloc[0]["dt"] == pytest.approx(0.04099)
    assert df.iloc[0]["Iter"] == 2
    assert df.iloc[0]["ItCum"] == 34
    assert df.iloc[0]["KodT"] == -1
    assert df.iloc[0]["KodB"] == -5
    # Convergency is a string flag.
    assert df.iloc[0]["Convergency"] == "T"


# --- Obs_Node.out ---------------------------------------------------------


def test_read_obs_node_long_format(tmp_path):
    f = tmp_path / "Obs_Node.out"
    f.write_text(OBS_NODE_FIXTURE)
    df = read_obs_node(f)
    # 3 times x 2 nodes = 6 rows
    assert len(df) == 6
    assert list(df.columns) == ["time", "node", "h", "theta", "temp"]
    # Node IDs detected from the Node(N) header
    assert sorted(df["node"].unique().tolist()) == [3, 8]
    # First row: time=0.25, node=3
    first = df.iloc[0]
    assert first["time"] == pytest.approx(0.25)
    assert first["node"] == 3
    assert first["h"] == pytest.approx(-1.0)
    assert first["theta"] == pytest.approx(0.1224)
    assert first["temp"] == pytest.approx(20.0)


def test_read_obs_node_variable_columns_preserves_concentration(tmp_path):
    f = tmp_path / "Obs_Node.out"
    f.write_text(OBS_NODE_HEAT_SOLUTE_FIXTURE)
    df = read_obs_node(f)

    assert len(df) == 4
    assert list(df.columns) == ["time", "node", "h", "theta", "temp", "conc"]
    assert sorted(df["node"].unique().tolist()) == [10, 20]

    first = df.iloc[0]
    assert first["time"] == pytest.approx(0.05)
    assert first["node"] == 10
    assert first["h"] == pytest.approx(-150.0)
    assert first["theta"] == pytest.approx(0.0773)
    assert first["temp"] == pytest.approx(20.0)
    assert first["conc"] == pytest.approx(0.0)

    second_node = df[(df["time"].sub(0.05).abs() < 1e-9) & (df["node"] == 20)].iloc[0]
    assert second_node["h"] == pytest.approx(-140.0)
    assert second_node["conc"] == pytest.approx(0.01)


def test_read_obs_node_does_not_modify_source(tmp_path):
    f = tmp_path / "Obs_Node.out"
    f.write_text(OBS_NODE_FIXTURE)
    before = f.read_text()
    read_obs_node(f)
    assert f.read_text() == before


# --- Nod_Inf.out ----------------------------------------------------------


def test_read_nod_inf_long_format(tmp_path):
    f = tmp_path / "Nod_Inf.out"
    f.write_text(NOD_INF_FIXTURE)
    df = read_nod_inf(f)
    # 2 time blocks x 2 nodes = 4 rows
    assert len(df) == 4
    expected_cols = ["time", "node", "depth", "head", "moisture",
                     "K", "C", "flux", "sink", "kappa", "vKsTop", "temp"]
    assert list(df.columns) == expected_cols
    # First time block: t=0.0, node 1
    first = df.iloc[0]
    assert first["time"] == pytest.approx(0.0)
    assert first["node"] == 1
    assert first["depth"] == pytest.approx(0.0)
    assert first["head"] == pytest.approx(-1.0)
    assert first["moisture"] == pytest.approx(0.1224)
    assert first["K"] == pytest.approx(0.5150e-4)
    assert first["temp"] == pytest.approx(20.0)
    # Second time block has different head values
    block2 = df[df["time"] == 0.25]
    assert len(block2) == 2
    assert block2.iloc[0]["head"] == pytest.approx(-1.108)


def test_read_nod_inf_preserves_solute_columns(tmp_path):
    f = tmp_path / "Nod_Inf.out"
    f.write_text("""\
 Time:        0.0000

 Node      Depth      Head Moisture       K          C         Flux        Sink         Kappa   v/KsTop   Temp   Conc(1..NS) Sorb(1...NS)
           [L]        [L]    [-]        [L/T]      [1/L]      [L/T]        [1/T]         [-]      [-]      [C]      [M/L*3]

   1     0.0000      -1.000 0.3497   0.7205E-03  0.5982E-03 -0.5407E-01  0.0000E+00      -1  -0.749E+02   20.00  0.1200E+00  0.0100E+00
   2    -1.0000    -150.000 0.0773   0.4315E-06  0.3685E-03 -0.2703E-01  0.0000E+00      -1  -0.374E+02   20.00  0.2400E+00  0.0200E+00
end
""")
    df = read_nod_inf(f)
    assert list(df.columns)[-2:] == ["conc_1", "sorb_1"]
    assert df.loc[df["node"] == 1, "conc_1"].iloc[0] == pytest.approx(0.12)
    assert df.loc[df["node"] == 2, "sorb_1"].iloc[0] == pytest.approx(0.02)


# --- Solute*.out ----------------------------------------------------------


SOLUTE_FIXTURE = """\
 All solute fluxes and cumulative solute fluxes are positive into the region

       Time         cvTop        cvBot      Sum(cvTop)   Sum(cvBot)     cvCh0        cvCh1         cTop        cRoot         cBot        cvRoot    Sum(cvRoot)  Sum(cvNEql) TLevel      cGWL        cRunOff   Sum(cRunOff)
        [T]        [M/L2/T]     [M/L2/T]      [M/L2]       [M/L2]       [M/L2]      [M/L2]        [M/L3]      [M/L3]        [M/L3]      [M/L2/T]      [M/L2]       [M/L2]              [M/L3]        [M/L2]      [M/L3]      [M/L2/T]
        0.0500  0.51552E-01  0.00000E+00  0.25776E-02  0.00000E+00  0.00000E+00  0.00000E+00  0.10677E-01  0.00000E+00  0.00000E+00  0.00000E+00  0.00000E+00  0.00000E+00       1  0.00000E+00  0.00000E+00  0.00000E+00
        0.1000  0.50350E-01  0.10000E-02  0.50951E-02  0.20000E-03  0.00000E+00 -0.11293E-09  0.20656E-01  0.00000E+00  0.10000E-04  0.00000E+00  0.00000E+00  0.00000E+00       2  0.00000E+00  0.00000E+00  0.00000E+00
"""


def test_read_solute_flux_table(tmp_path):
    f = tmp_path / "SOLUTE1.OUT"
    f.write_text(SOLUTE_FIXTURE)
    df = read_solute(f)
    assert len(df) == 2
    assert "Time" in df.columns
    assert "Sum_cvTop" in df.columns
    assert "Sum_cvBot" in df.columns
    assert df["Time"].iloc[-1] == pytest.approx(0.1)
    assert df["Sum_cvBot"].iloc[-1] == pytest.approx(0.0002)


def test_read_outputs_discovers_existing_solute_outputs(tmp_path):
    (tmp_path / "Balance.out").write_text(BALANCE_FIXTURE)
    (tmp_path / "solute1.out").write_text(SOLUTE_FIXTURE)
    (tmp_path / "SOLUTE2.OUT").write_text(SOLUTE_FIXTURE)

    out = read_outputs(tmp_path)
    assert "Solute1.out" in out
    assert "Solute2.out" in out
    assert not out["Solute1.out"].empty

    summary = summarise_outputs(tmp_path)
    by_name = {entry["name"]: entry for entry in summary}
    assert by_name["Solute1.out"]["found"] is True
    assert by_name["Solute2.out"]["rows"] == 2


# --- Top-level ------------------------------------------------------------


def test_read_outputs_handles_mixed_presence(tmp_path):
    """Five canonical names; populate three of them; the other two remain
    empty."""
    (tmp_path / "Balance.out").write_text(BALANCE_FIXTURE)
    (tmp_path / "T_Level.out").write_text(T_LEVEL_FIXTURE)
    (tmp_path / "Nod_Inf.out").write_text(NOD_INF_FIXTURE)
    out = read_outputs(tmp_path)
    assert set(out.keys()) == set(DEFAULT_OUTPUT_NAMES)
    assert not out["Balance.out"].empty
    assert not out["T_Level.out"].empty
    assert not out["Nod_Inf.out"].empty
    assert out["Obs_Node.out"].empty
    assert out["Run_Inf.out"].empty


def test_summarise_outputs_reports_all_five(tmp_path):
    (tmp_path / "Balance.out").write_text(BALANCE_FIXTURE)
    (tmp_path / "T_Level.out").write_text(T_LEVEL_FIXTURE)
    (tmp_path / "Run_Inf.out").write_text(RUN_INF_FIXTURE)
    (tmp_path / "Obs_Node.out").write_text(OBS_NODE_FIXTURE)
    (tmp_path / "Nod_Inf.out").write_text(NOD_INF_FIXTURE)
    summary = summarise_outputs(tmp_path)
    by_name = {entry["name"]: entry for entry in summary}

    for name in DEFAULT_OUTPUT_NAMES:
        assert by_name[name]["found"] is True, f"{name} should be found"
        assert by_name[name]["rows"] > 0, f"{name} should have rows"

    assert by_name["Balance.out"]["columns"] >= 7
    assert by_name["T_Level.out"]["columns"] == 22
    assert by_name["Run_Inf.out"]["columns"] == 8
    assert by_name["Obs_Node.out"]["columns"] == 5
    assert by_name["Nod_Inf.out"]["columns"] == 12

    # Spot-check that case-preserved column names appear in T_Level summary.
    assert "rTop" in by_name["T_Level.out"]["first_columns"] \
        or "Time" in by_name["T_Level.out"]["first_columns"]
