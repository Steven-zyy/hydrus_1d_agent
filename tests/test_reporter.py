"""Tests for hydrus_agent.reporter (milestone 6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hydrus_agent import load_config
from hydrus_agent.qc import assess_run_quality
from hydrus_agent.reporter import (
    REPORT_FILENAME,
    generate_markdown_report,
)

# Reuse fixture builders from milestone-5 tests for parity.
from tests.test_plotter import (
    make_balance_df, make_nod_inf_df, make_obs_df,
    make_run_inf_df, make_t_level_df,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SIMPLE_RUNNABLE_CONFIG = PROJECT_ROOT / "config" / "simple_runnable_case.json"


def _all_outputs():
    return {
        "Balance.out": make_balance_df(),
        "T_Level.out": make_t_level_df(),
        "Obs_Node.out": make_obs_df(),
        "Nod_Inf.out": make_nod_inf_df(),
        "Run_Inf.out": make_run_inf_df(),
    }


def _make_fake_figures(figure_dir: Path, names: list[str]) -> list[Path]:
    figure_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for n in names:
        p = figure_dir / n
        # Tiny PNG-like stub so the file exists with non-zero size.
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"stub" * 4)
        paths.append(p)
    return paths


# --- Basic structure ------------------------------------------------------


def test_report_file_is_written_to_run_dir(tmp_path):
    cfg = load_config(SIMPLE_RUNNABLE_CONFIG)
    outputs = _all_outputs()
    qc = assess_run_quality(outputs)
    figures = _make_fake_figures(
        tmp_path / "figures",
        ["balance_storage_vs_time.png", "moisture_contour.png"],
    )
    path = generate_markdown_report(cfg, tmp_path, outputs, qc, figures)
    assert path == tmp_path / REPORT_FILENAME
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# HYDRUS-1D Run Report")


def test_report_contains_all_required_sections(tmp_path):
    cfg = load_config(SIMPLE_RUNNABLE_CONFIG)
    outputs = _all_outputs()
    qc = assess_run_quality(outputs)
    figures = _make_fake_figures(
        tmp_path / "figures",
        ["balance_storage_vs_time.png"],
    )
    path = generate_markdown_report(cfg, tmp_path, outputs, qc, figures)
    text = path.read_text(encoding="utf-8")

    for heading in (
        "## Simulation setup",
        "### Time",
        "### Soil profile",
        "### van Genuchten parameters",
        "### Boundary conditions",
        "### Initial condition",
        "### Observation depths",
        "## Execution",
        "## Outputs",
        "## Quality control",
        "## Figures",
        "## Interpretation",
    ):
        assert heading in text, f"section missing: {heading}"


def test_report_includes_project_name_and_case_id(tmp_path):
    cfg = load_config(SIMPLE_RUNNABLE_CONFIG)
    figures = _make_fake_figures(tmp_path / "figures", [])
    path = generate_markdown_report(
        cfg, tmp_path, _all_outputs(), assess_run_quality(_all_outputs()),
        figures,
    )
    text = path.read_text(encoding="utf-8")
    assert cfg.project_name in text
    assert f"`{cfg.case_id}`" in text


def test_report_warns_when_numerical_failure_detected(tmp_path):
    cfg = load_config(SIMPLE_RUNNABLE_CONFIG)
    outputs = _all_outputs()
    qc = assess_run_quality(outputs)
    qc["hydrus_status"] = {
        "return_code": 0,
        "error_message_file": str(tmp_path / "hydrus_project" / "Error.msg"),
        "numerical_failure_detected": True,
        "failure_reason": "stopped after 10 consecutive non-converged steps",
        "error_excerpt": "stopped after 10 consecutiv e non- converged steps",
        "status": "failed",
    }
    qc["reliability"] = {
        "execution_status": "completed",
        "hydrus_numerical_status": "failed",
        "qc_status": "passed",
        "overall_status": "failed",
    }
    figures = _make_fake_figures(
        tmp_path / "figures",
        ["balance_storage_vs_time.png"],
    )

    path = generate_markdown_report(cfg, tmp_path, outputs, qc, figures)

    text = path.read_text(encoding="utf-8")
    assert "## Run Reliability Warning" in text
    assert "HYDRUS returned code 0" in text
    assert "numerical failure" in text
    assert "10 consecutive non-converged steps" in text
    assert "stopped after 10 consecutiv e non- converged steps" in text
    assert "Results may be incomplete or unreliable" in text


def test_report_includes_van_genuchten_parameters(tmp_path):
    cfg = load_config(SIMPLE_RUNNABLE_CONFIG)
    figures = _make_fake_figures(tmp_path / "figures", [])
    path = generate_markdown_report(
        cfg, tmp_path, _all_outputs(), assess_run_quality(_all_outputs()),
        figures,
    )
    text = path.read_text(encoding="utf-8")
    # Bundled config has theta_r=0.065, n=1.89, Ks=1.061
    assert "0.065" in text
    assert "1.89" in text
    assert "1.061" in text


# --- Outputs section ------------------------------------------------------


def test_report_outputs_table_lists_present_and_missing(tmp_path):
    cfg = load_config(SIMPLE_RUNNABLE_CONFIG)
    outputs = {
        "Balance.out": make_balance_df(),
        "T_Level.out": make_t_level_df(),
        # Obs_Node, Nod_Inf, Run_Inf missing -> reported as empty
    }
    figures = _make_fake_figures(tmp_path / "figures", [])
    path = generate_markdown_report(
        cfg, tmp_path, outputs, assess_run_quality(outputs), figures,
    )
    text = path.read_text(encoding="utf-8")
    # Present rows
    assert "5 × 9" in text  # Balance
    assert "4 × 16" in text  # T_Level (15 cols + sum_vTop = 16)
    # Missing rows
    assert "(empty / missing)" in text


def test_report_mentions_solute_outputs_when_present(tmp_path):
    cfg = load_config(SIMPLE_RUNNABLE_CONFIG)
    outputs = _all_outputs()
    obs = make_obs_df().copy()
    obs["conc"] = [0.0, 0.0, 0.25, 0.0, 0.5, 0.75, 1.0, 0.5]
    outputs["Obs_Node.out"] = obs
    outputs["Solute1.out"] = make_t_level_df()[["Time"]].copy()
    outputs["Solute1.out"]["Sum_cvTop"] = [0.0, 0.1, 0.2, 0.3]
    outputs["Solute1.out"]["Sum_cvBot"] = [0.0, 0.0, 0.05, 0.1]
    qc = assess_run_quality(outputs)

    path = generate_markdown_report(
        cfg, tmp_path, outputs, qc, figures=[],
    )
    text = path.read_text(encoding="utf-8")
    assert "`Solute1.out`" in text
    assert "solute outputs" in text.lower()
    assert "final cumulative top solute flux" in text.lower()


def test_report_includes_field_data_comparison_section(tmp_path):
    cfg = load_config(SIMPLE_RUNNABLE_CONFIG)
    outputs = _all_outputs()
    qc = assess_run_quality(outputs, field_comparison={
        "available": True,
        "matched_rows": 4,
        "variables": {
            "theta": {
                "nodes": {
                    "3": {
                        "matched_count": 2,
                        "rmse": 0.01,
                        "mae": 0.008,
                        "bias": -0.002,
                        "correlation": 0.99,
                    }
                }
            },
            "head": {
                "nodes": {
                    "3": {
                        "matched_count": 2,
                        "rmse": 0.05,
                        "mae": 0.04,
                        "bias": 0.01,
                        "correlation": 1.0,
                    }
                }
            },
        },
        "warnings": [],
        "figures": ["figures/field_overlay_theta.png"],
    })
    figures = _make_fake_figures(
        tmp_path / "figures",
        ["field_overlay_theta.png"],
    )

    path = generate_markdown_report(cfg, tmp_path, outputs, qc, figures)
    text = path.read_text(encoding="utf-8")

    assert "## Field Data Comparison" in text
    assert "| theta | 3 | 2 |" in text
    assert "field_overlay_theta.png" in text


# --- Figures section: relative links ------------------------------------


def test_report_uses_relative_figure_links(tmp_path):
    cfg = load_config(SIMPLE_RUNNABLE_CONFIG)
    outputs = _all_outputs()
    qc = assess_run_quality(outputs)
    figures = _make_fake_figures(
        tmp_path / "figures",
        ["balance_storage_vs_time.png", "moisture_contour.png"],
    )
    path = generate_markdown_report(cfg, tmp_path, outputs, qc, figures)
    text = path.read_text(encoding="utf-8")

    # Markdown image links should be relative (no absolute paths).
    assert "![balance_storage_vs_time](figures/balance_storage_vs_time.png)" in text
    assert "![moisture_contour](figures/moisture_contour.png)" in text
    # Relative links use forward slashes; no absolute figure path leaks.
    figs_section = text.split("## Figures")[1]
    assert str(tmp_path) not in figs_section


def test_report_figures_section_handles_no_figures(tmp_path):
    cfg = load_config(SIMPLE_RUNNABLE_CONFIG)
    outputs = _all_outputs()
    qc = assess_run_quality(outputs)
    path = generate_markdown_report(cfg, tmp_path, outputs, qc, figures=[])
    text = path.read_text(encoding="utf-8")
    assert "## Figures" in text
    assert "No figures were generated" in text


# --- QC section -----------------------------------------------------------


def test_report_qc_section_reports_warnings(tmp_path):
    cfg = load_config(SIMPLE_RUNNABLE_CONFIG)
    bal = make_balance_df()
    bal.loc[bal.index[-1], "wat_bal_r"] = 5.5  # high error -> warning
    outputs = _all_outputs()
    outputs["Balance.out"] = bal
    qc = assess_run_quality(outputs)
    figures = _make_fake_figures(tmp_path / "figures", [])
    path = generate_markdown_report(cfg, tmp_path, outputs, qc, figures)
    text = path.read_text(encoding="utf-8")
    assert "WARNINGS" in text
    assert "### Warnings" in text


def test_report_qc_section_clean_when_ok(tmp_path):
    cfg = load_config(SIMPLE_RUNNABLE_CONFIG)
    outputs = _all_outputs()
    qc = assess_run_quality(outputs)
    figures = _make_fake_figures(tmp_path / "figures", [])
    path = generate_markdown_report(cfg, tmp_path, outputs, qc, figures)
    text = path.read_text(encoding="utf-8")
    assert "**Overall:** OK" in text
    assert "warnings: none" in text


# --- Execution section ----------------------------------------------------


def test_report_execution_section_includes_log_summary(tmp_path):
    cfg = load_config(SIMPLE_RUNNABLE_CONFIG)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_path = log_dir / "hydrus_run.log"
    log_path.write_text(
        "command: ['/path/to/H1D_CALC.EXE']\n"
        "cwd: /tmp/case\n"
        "launch mode: argv\n"
        "return code: 0\n"
        "--- stdout ---\n"
        "Simulation finished\n",
        encoding="utf-8",
    )
    figures = _make_fake_figures(tmp_path / "figures", [])
    path = generate_markdown_report(
        cfg, tmp_path, _all_outputs(), assess_run_quality(_all_outputs()),
        figures, run_log_path=log_path,
    )
    text = path.read_text(encoding="utf-8")
    assert "Launch mode" in text and "argv" in text
    assert "Return code" in text and "0" in text


def test_report_execution_section_when_log_missing(tmp_path):
    cfg = load_config(SIMPLE_RUNNABLE_CONFIG)
    figures = _make_fake_figures(tmp_path / "figures", [])
    path = generate_markdown_report(
        cfg, tmp_path, _all_outputs(), assess_run_quality(_all_outputs()),
        figures,
    )
    text = path.read_text(encoding="utf-8")
    assert "Run log: not found" in text


# --- Interpretation section ----------------------------------------------


def test_clean_report_keeps_positive_convergence_wording(tmp_path):
    cfg = load_config(SIMPLE_RUNNABLE_CONFIG)
    outputs = _all_outputs()
    qc = assess_run_quality(outputs)
    total_steps = qc["convergence"]["total_steps"]
    figures = _make_fake_figures(tmp_path / "figures", [])

    path = generate_markdown_report(cfg, tmp_path, outputs, qc, figures)

    text = path.read_text(encoding="utf-8")
    assert f"All {total_steps} solver steps converged." in text


def test_numerical_failure_report_qualifies_parsed_convergence(tmp_path):
    cfg = load_config(SIMPLE_RUNNABLE_CONFIG)
    outputs = _all_outputs()
    qc = assess_run_quality(outputs)
    total_steps = qc["convergence"]["total_steps"]
    qc["hydrus_status"] = {
        "return_code": 0,
        "error_message_file": str(tmp_path / "hydrus_project" / "Error.msg"),
        "numerical_failure_detected": True,
        "failure_reason": "stopped after 10 consecutive non-converged steps",
        "error_excerpt": "stopped after 10 consecutive non-converged steps",
        "status": "failed",
    }
    qc["reliability"] = {
        "execution_status": "completed",
        "hydrus_numerical_status": "failed",
        "qc_status": "passed",
        "overall_status": "failed",
    }
    figures = _make_fake_figures(tmp_path / "figures", [])

    path = generate_markdown_report(cfg, tmp_path, outputs, qc, figures)

    text = path.read_text(encoding="utf-8")
    assert f"All {total_steps} solver steps converged." not in text
    assert (
        f"The parsed output-step records report {total_steps}/{total_steps} "
        "converged steps"
    ) in text
    assert "HYDRUS Error.msg indicates" in text


def test_qc_failure_report_qualifies_positive_convergence_wording(tmp_path):
    cfg = load_config(SIMPLE_RUNNABLE_CONFIG)
    outputs = _all_outputs()
    balance = make_balance_df()
    balance.loc[balance.index[-1], "wat_bal_r"] = 5.5
    outputs["Balance.out"] = balance
    qc = assess_run_quality(outputs)
    total_steps = qc["convergence"]["total_steps"]
    qc["hydrus_status"] = {
        "return_code": 0,
        "numerical_failure_detected": False,
        "status": "converged",
    }
    qc["reliability"] = {
        "execution_status": "completed",
        "hydrus_numerical_status": "converged",
        "qc_status": "failed",
        "overall_status": "failed",
    }
    figures = _make_fake_figures(tmp_path / "figures", [])

    path = generate_markdown_report(cfg, tmp_path, outputs, qc, figures)

    text = path.read_text(encoding="utf-8")
    assert f"All {total_steps} solver steps converged." not in text
    assert (
        f"The parsed output-step records report {total_steps}/{total_steps} "
        "converged steps"
    ) in text
    assert "QC status is failed" in text


def test_report_interpretation_paragraph_present_when_data_available(tmp_path):
    cfg = load_config(SIMPLE_RUNNABLE_CONFIG)
    outputs = _all_outputs()
    qc = assess_run_quality(outputs)
    figures = _make_fake_figures(tmp_path / "figures", [])
    path = generate_markdown_report(cfg, tmp_path, outputs, qc, figures)
    text = path.read_text(encoding="utf-8")
    # Should mention solver convergence and water balance.
    assert "solver step" in text.lower() or "converged" in text.lower()
    assert "water balance" in text.lower()


def test_report_interpretation_when_no_outputs(tmp_path):
    cfg = load_config(SIMPLE_RUNNABLE_CONFIG)
    qc = assess_run_quality({})
    figures = _make_fake_figures(tmp_path / "figures", [])
    path = generate_markdown_report(cfg, tmp_path, {}, qc, figures)
    text = path.read_text(encoding="utf-8")
    assert "No outputs were available" in text \
        or "Run HYDRUS first" in text
