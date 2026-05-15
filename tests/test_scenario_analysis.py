from __future__ import annotations

import csv
from pathlib import Path

import pytest

from hydrus_agent.scenario_analysis import (
    ScenarioAnalysisError,
    generate_scenario_comparison_report,
)


def _write_summary(batch_dir: Path, rows: list[dict[str, object]]) -> Path:
    path = batch_dir / "scenario_summary.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_generate_scenario_comparison_report_summarises_batch(tmp_path):
    batch_dir = tmp_path / "simple_sensitivity"
    _write_summary(batch_dir, [
        {
            "scenario_id": "base",
            "status": "pass",
            "warning_count": 0,
            "final_sum_Infil": 0.10,
            "final_sum_vBot": -0.04,
            "theta_node_3_rmse": 0.020,
        },
        {
            "scenario_id": "wet",
            "status": "pass",
            "warning_count": 1,
            "final_sum_Infil": 0.15,
            "final_sum_vBot": -0.08,
            "theta_node_3_rmse": 0.015,
        },
        {
            "scenario_id": "dry",
            "status": "fail",
            "warning_count": 2,
            "final_sum_Infil": 0.05,
            "final_sum_vBot": -0.02,
            "theta_node_3_rmse": 0.040,
        },
    ])

    report_path = generate_scenario_comparison_report(batch_dir)

    assert report_path == batch_dir / "scenario_report.md"
    text = report_path.read_text(encoding="utf-8")
    assert "# Scenario Comparison Report" in text
    assert "Batch ID: `simple_sensitivity`" in text
    assert "Number of scenarios: 3" in text
    assert "Passed: 2" in text
    assert "Failed: 1" in text
    assert "Best field-data RMSE: `wet`" in text
    assert "Largest infiltration: `wet`" in text
    assert "Largest absolute bottom flux: `wet`" in text
    assert "| dry | fail |" in text
    assert "| wet | pass |" in text


def test_generate_scenario_comparison_report_creates_optional_plots(tmp_path):
    batch_dir = tmp_path / "simple_sensitivity"
    _write_summary(batch_dir, [
        {
            "scenario_id": "base",
            "status": "pass",
            "final_sum_Infil": 0.10,
            "final_sum_vBot": -0.04,
            "theta_node_3_rmse": 0.020,
        },
        {
            "scenario_id": "wet",
            "status": "pass",
            "final_sum_Infil": 0.15,
            "final_sum_vBot": -0.08,
            "theta_node_3_rmse": 0.015,
        },
    ])

    generate_scenario_comparison_report(batch_dir)

    figures_dir = batch_dir / "figures"
    assert (figures_dir / "scenario_metric_bar_infiltration.png").is_file()
    assert (figures_dir / "scenario_metric_bar_bottom_flux.png").is_file()
    assert (figures_dir / "scenario_field_rmse_comparison.png").is_file()


def test_generate_scenario_comparison_report_handles_no_field_metrics(tmp_path):
    batch_dir = tmp_path / "no_field"
    _write_summary(batch_dir, [
        {
            "scenario_id": "base",
            "status": "pass",
            "final_sum_Infil": 0.10,
            "final_sum_vBot": -0.04,
        },
    ])

    report_path = generate_scenario_comparison_report(batch_dir)

    text = report_path.read_text(encoding="utf-8")
    assert "Best field-data RMSE: not available" in text
    assert not (batch_dir / "figures" / "scenario_field_rmse_comparison.png").exists()


def test_generate_scenario_comparison_report_requires_summary_csv(tmp_path):
    with pytest.raises(ScenarioAnalysisError, match="scenario_summary.csv"):
        generate_scenario_comparison_report(tmp_path / "missing_batch")
