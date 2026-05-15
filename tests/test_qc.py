"""Tests for hydrus_agent.qc (milestone 5.5).

Synthetic DataFrames; no real HYDRUS run required.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from hydrus_agent.qc import (
    EXPECTED_FIGURE_NAMES,
    WATER_BALANCE_WARN_PCT,
    assess_run_quality,
    format_qc_summary,
    write_qc_summary,
)


# Reuse the plotter fixture builders for parity with milestone 5 tests.
from tests.test_plotter import (
    make_balance_df,
    make_nod_inf_df,
    make_obs_df,
    make_run_inf_df,
    make_t_level_df,
)


def _all_outputs():
    return {
        "Balance.out": make_balance_df(),
        "T_Level.out": make_t_level_df(),
        "Obs_Node.out": make_obs_df(),
        "Nod_Inf.out": make_nod_inf_df(),
        "Run_Inf.out": make_run_inf_df(),
    }


# --- Top-level shape ------------------------------------------------------


def test_assess_run_quality_returns_full_dict():
    report = assess_run_quality(_all_outputs())
    for key in ("tables", "water_balance", "cumulative_fluxes",
                "observation_nodes", "profiles", "convergence",
                "solute", "field_comparison", "figures", "warnings", "ok"):
        assert key in report, f"missing key: {key}"


def test_assess_run_quality_ok_with_clean_data():
    report = assess_run_quality(_all_outputs(), figures=[
        Path(name) for name in EXPECTED_FIGURE_NAMES
    ])
    assert report["ok"] is True, f"unexpected warnings: {report['warnings']}"
    assert report["warnings"] == []


# --- Tables section -------------------------------------------------------


def test_tables_section_reports_rows_and_columns():
    report = assess_run_quality(_all_outputs())
    bal = report["tables"]["Balance.out"]
    assert bal["present"] is True
    assert bal["non_empty"] is True
    assert bal["rows"] == 5
    assert bal["columns"] == 9


def test_tables_section_flags_missing_and_empty():
    outputs = {
        "Balance.out": make_balance_df(),
        # T_Level.out missing entirely
        "Obs_Node.out": pd.DataFrame(),  # empty
        "Nod_Inf.out": make_nod_inf_df(),
        "Run_Inf.out": make_run_inf_df(),
    }
    report = assess_run_quality(outputs)
    assert any("T_Level.out" in w for w in report["warnings"])
    assert any("Obs_Node.out" in w and "empty" in w for w in report["warnings"])


def test_tables_section_flags_unexpected_nan():
    obs = make_obs_df()
    obs.loc[0, "theta"] = np.nan
    outputs = _all_outputs()
    outputs["Obs_Node.out"] = obs
    report = assess_run_quality(outputs)
    assert any("Obs_Node.out" in w and "NaN" in w for w in report["warnings"])


def test_tables_section_includes_solute_outputs_when_present():
    outputs = _all_outputs()
    outputs["Solute1.out"] = pd.DataFrame({
        "Time": [0.0, 1.0],
        "Sum_cvTop": [0.0, 0.2],
        "Sum_cvBot": [0.0, 0.1],
    })
    report = assess_run_quality(outputs)
    assert report["tables"]["Solute1.out"]["present"] is True
    assert report["tables"]["Solute1.out"]["rows"] == 2


def test_tables_section_does_not_flag_balance_nan():
    """Balance.out has expected NaN at t=0 (wat_bal_t/wat_bal_r). Don't warn."""
    outputs = _all_outputs()  # already has the t=0 NaN
    report = assess_run_quality(outputs)
    bal = report["tables"]["Balance.out"]
    assert bal["nan_count"] >= 1
    # No warning naming Balance.out and NaN
    assert not any("Balance.out" in w and "NaN" in w for w in report["warnings"])


# --- Water balance --------------------------------------------------------


def test_water_balance_reports_final_and_max_error():
    report = assess_run_quality(_all_outputs())
    wb = report["water_balance"]
    assert wb["available"] is True
    assert "final_error_pct" in wb
    assert "max_abs_error_pct" in wb
    # Fixture's wat_bal_r values are very small → no warning
    assert not any("water balance error" in w for w in report["warnings"])


def test_water_balance_warns_when_error_exceeds_threshold():
    bad_balance = make_balance_df()
    bad_balance.loc[bad_balance.index[-1], "wat_bal_r"] = 5.5  # 5.5%
    outputs = _all_outputs()
    outputs["Balance.out"] = bad_balance
    report = assess_run_quality(outputs)
    assert any("water balance error" in w and "5.500%" in w
               for w in report["warnings"]), report["warnings"]
    assert report["water_balance"]["max_abs_error_pct"] >= WATER_BALANCE_WARN_PCT


def test_water_balance_unavailable_when_balance_missing():
    outputs = _all_outputs()
    del outputs["Balance.out"]
    report = assess_run_quality(outputs)
    assert report["water_balance"]["available"] is False


# --- Cumulative fluxes ----------------------------------------------------


def test_cumulative_fluxes_uses_t_level_when_available():
    report = assess_run_quality(_all_outputs())
    cf = report["cumulative_fluxes"]
    assert cf["source"] == "T_Level.out"
    assert "final_sum_vTop" in cf
    assert "final_sum_vBot" in cf
    assert "final_sum_Infil" in cf


def test_cumulative_fluxes_falls_back_to_balance():
    outputs = _all_outputs()
    del outputs["T_Level.out"]
    report = assess_run_quality(outputs)
    cf = report["cumulative_fluxes"]
    assert cf["source"] == "Balance.out"
    assert "final_top_flux" in cf
    assert "final_bot_flux" in cf


def test_cumulative_fluxes_source_none_when_no_data():
    report = assess_run_quality({})
    assert report["cumulative_fluxes"]["source"] is None


# --- Obs nodes / profiles -------------------------------------------------


def test_observation_nodes_reports_node_ids():
    report = assess_run_quality(_all_outputs())
    obs = report["observation_nodes"]
    assert obs["present"] is True
    assert obs["node_count"] == 2
    assert obs["node_ids"] == [3, 8]
    assert obs["row_count"] == 8


def test_solute_section_reports_observation_and_flux_metrics():
    outputs = _all_outputs()
    obs = make_obs_df().copy()
    obs["conc"] = [0.0, 0.0, 0.25, 0.0, 0.5, 0.75, 1.0, 0.5]
    outputs["Obs_Node.out"] = obs
    outputs["Solute1.out"] = pd.DataFrame({
        "Time": [0.0, 1.0],
        "Sum_cvTop": [0.0, 0.2],
        "Sum_cvBot": [0.0, 0.1],
    })

    report = assess_run_quality(outputs)
    solute = report["solute"]
    assert solute["available"] is True
    node3 = solute["observation_concentration"]["nodes"]["3"]
    node8 = solute["observation_concentration"]["nodes"]["8"]
    assert node3["final"] == pytest.approx(1.0)
    assert node8["max"] == pytest.approx(0.75)
    assert node3["breakthrough_time"] == pytest.approx(0.5)
    assert solute["flux_tables"]["Solute1.out"]["final_sum_cvTop"] == pytest.approx(0.2)
    text = format_qc_summary(report)
    assert "Solute outputs" in text


def test_field_comparison_section_is_included_when_supplied():
    field_summary = {
        "available": True,
        "matched_rows": 4,
        "variables": {
            "theta": {
                "nodes": {
                    "3": {
                        "matched_count": 2,
                        "rmse": 0.01,
                        "mae": 0.01,
                        "bias": -0.005,
                        "correlation": 1.0,
                    }
                }
            }
        },
        "warnings": [],
        "figures": ["figures/field_overlay_theta.png"],
    }

    report = assess_run_quality(
        _all_outputs(),
        figures=[Path(name) for name in EXPECTED_FIGURE_NAMES],
        field_comparison=field_summary,
    )

    assert report["ok"] is True
    assert report["field_comparison"]["available"] is True
    assert report["field_comparison"]["matched_rows"] == 4
    text = format_qc_summary(report)
    assert "Field data comparison" in text
    assert "theta" in text


def test_profiles_reports_time_x_node_counts():
    report = assess_run_quality(_all_outputs())
    pr = report["profiles"]
    assert pr["present"] is True
    assert pr["time_count"] == 5
    assert pr["node_count"] == 11
    assert pr["row_count"] == 55


# --- Convergence ----------------------------------------------------------


def test_convergence_all_converged():
    report = assess_run_quality(_all_outputs())
    conv = report["convergence"]
    assert conv["present"] is True
    assert conv["all_converged"] is True
    assert conv["converged_steps"] == 4
    assert conv["non_converged_steps"] == 0


def test_convergence_warns_when_some_failed():
    run = make_run_inf_df()
    run.loc[1, "Convergency"] = "F"
    run.loc[2, "Convergency"] = "F"
    outputs = _all_outputs()
    outputs["Run_Inf.out"] = run
    report = assess_run_quality(outputs)
    assert report["convergence"]["all_converged"] is False
    assert report["convergence"]["non_converged_steps"] == 2
    assert any("did not converge" in w for w in report["warnings"])


# --- Figures --------------------------------------------------------------


def test_figures_check_skipped_when_none_passed():
    report = assess_run_quality(_all_outputs(), figures=None)
    assert report["figures"]["checked"] is False
    # No figure-related warning in this case.
    assert not any("expected figure" in w for w in report["warnings"])


def test_figures_warns_about_missing():
    # Provide only 5 of the 9 expected figures.
    paths = [Path(name) for name in EXPECTED_FIGURE_NAMES[:5]]
    report = assess_run_quality(_all_outputs(), figures=paths)
    figs = report["figures"]
    assert figs["checked"] is True
    assert len(figs["missing"]) == 4
    assert any("expected figure" in w for w in report["warnings"])


def test_figures_full_set_no_warning():
    paths = [Path(name) for name in EXPECTED_FIGURE_NAMES]
    report = assess_run_quality(_all_outputs(), figures=paths)
    assert report["figures"]["missing"] == []


# --- JSON serialisation + format ------------------------------------------


def test_write_qc_summary_produces_valid_json(tmp_path):
    report = assess_run_quality(_all_outputs())
    path = tmp_path / "outputs" / "qc_summary.json"
    written = write_qc_summary(report, path)
    assert written.is_file()
    parsed = json.loads(written.read_text(encoding="utf-8"))
    assert "tables" in parsed
    assert parsed["ok"] is True


def test_format_qc_summary_returns_string():
    report = assess_run_quality(_all_outputs())
    text = format_qc_summary(report)
    assert isinstance(text, str)
    assert "Tables:" in text
    assert "Water balance" in text
    assert "Convergence" in text
