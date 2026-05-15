"""Tests for the scenario/sensitivity batch runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hydrus_agent import load_config
from hydrus_agent.scenario_runner import (
    ScenarioError,
    apply_scenario_overrides,
    load_scenario_file,
    run_scenario_batch,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SIMPLE_RUNNABLE_CONFIG = PROJECT_ROOT / "config" / "simple_runnable_case.json"


def _write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def test_load_scenario_file_validates_basic_shape(tmp_path: Path):
    scenario_file = _write_json(
        tmp_path / "scenarios.json",
        {
            "batch_id": "simple_sensitivity",
            "scenarios": [
                {"scenario_id": "base", "overrides": {}},
                {"scenario_id": "ks_low", "overrides": {"van_genuchten[0].Ks": 0.5}},
            ],
        },
    )

    spec = load_scenario_file(scenario_file)

    assert spec["batch_id"] == "simple_sensitivity"
    assert [s["scenario_id"] for s in spec["scenarios"]] == ["base", "ks_low"]


def test_load_scenario_file_rejects_unsafe_and_duplicate_ids(tmp_path: Path):
    unsafe = _write_json(
        tmp_path / "unsafe.json",
        {"batch_id": "batch", "scenarios": [{"scenario_id": "../bad", "overrides": {}}]},
    )
    with pytest.raises(ScenarioError, match="unsafe"):
        load_scenario_file(unsafe)

    duplicate = _write_json(
        tmp_path / "duplicate.json",
        {
            "batch_id": "batch",
            "scenarios": [
                {"scenario_id": "same", "overrides": {}},
                {"scenario_id": "same", "overrides": {}},
            ],
        },
    )
    with pytest.raises(ScenarioError, match="Duplicate scenario_id"):
        load_scenario_file(duplicate)


def test_apply_overrides_generates_unique_case_id_and_updates_values():
    base = load_config(SIMPLE_RUNNABLE_CONFIG)

    updated = apply_scenario_overrides(
        base,
        scenario_id="ks_alpha_flux",
        overrides={
            "van_genuchten[0].Ks": 0.5,
            "van_genuchten[0].alpha": 6.0,
            "van_genuchten[0].n": 1.7,
            "initial_condition.value": -0.8,
            "upper_boundary.flux": 0.002,
        },
    )

    assert updated.case_id == "case_002__ks_alpha_flux"
    assert updated.van_genuchten[0].Ks == pytest.approx(0.5)
    assert updated.van_genuchten[0].alpha == pytest.approx(6.0)
    assert updated.van_genuchten[0].n == pytest.approx(1.7)
    assert updated.initial_condition.value == pytest.approx(-0.8)
    assert updated.upper_boundary.flux == pytest.approx(0.002)
    assert base.case_id == "case_002"


def test_apply_overrides_supports_optional_root_and_solute_paths():
    root = load_config(PROJECT_ROOT / "config" / "simple_root_uptake_case.json")
    root_updated = apply_scenario_overrides(
        root,
        scenario_id="root_shallow",
        overrides={"root_uptake.root_depth": 0.3},
    )
    assert root_updated.root_uptake.root_depth == pytest.approx(0.3)

    solute = load_config(PROJECT_ROOT / "config" / "simple_conservative_solute_case.json")
    solute_updated = apply_scenario_overrides(
        solute,
        scenario_id="disp_high",
        overrides={"solute_transport.species[0].dispersivity": 0.02},
    )
    assert solute_updated.solute_transport.species[0].dispersivity == pytest.approx(0.02)


def test_apply_overrides_rejects_unsupported_path_and_validation_failure():
    base = load_config(SIMPLE_RUNNABLE_CONFIG)

    with pytest.raises(ScenarioError, match="Unsupported override path"):
        apply_scenario_overrides(
            base,
            scenario_id="bad_path",
            overrides={"lower_boundary.type": "constant_head"},
        )

    with pytest.raises(ScenarioError, match="failed ModelConfig validation"):
        apply_scenario_overrides(
            base,
            scenario_id="bad_n",
            overrides={"van_genuchten[0].n": 1.0},
        )


def test_run_scenario_batch_validates_all_before_running(tmp_path: Path):
    scenario_file = _write_json(
        tmp_path / "bad_batch.json",
        {
            "batch_id": "bad_batch",
            "scenarios": [
                {"scenario_id": "base", "overrides": {}},
                {"scenario_id": "bad", "overrides": {"not.supported": 1.0}},
            ],
        },
    )
    calls = []

    def fake_pipeline(*args, **kwargs):
        calls.append((args, kwargs))
        return {"ok": True}

    with pytest.raises(ScenarioError, match="Unsupported override path"):
        run_scenario_batch(
            SIMPLE_RUNNABLE_CONFIG,
            scenario_file,
            runs_root=tmp_path / "runs",
            pipeline_runner=fake_pipeline,
        )
    assert calls == []


def test_run_scenario_batch_calls_pipeline_and_writes_summaries(tmp_path: Path):
    scenario_file = _write_json(
        tmp_path / "scenarios.json",
        {
            "batch_id": "simple_sensitivity",
            "scenarios": [
                {"scenario_id": "base", "overrides": {}},
                {"scenario_id": "ks_low", "overrides": {"van_genuchten[0].Ks": 0.5}},
            ],
        },
    )
    calls = []

    def fake_pipeline(config_path, *, overwrite_run, timeout, hydrus_launch_mode, field_data_path=None):
        calls.append({
            "config_path": Path(config_path),
            "overwrite_run": overwrite_run,
            "timeout": timeout,
            "hydrus_launch_mode": hydrus_launch_mode,
            "field_data_path": field_data_path,
        })
        cfg = load_config(config_path)
        run_dir = tmp_path / "runs" / cfg.case_id
        (run_dir / "outputs").mkdir(parents=True)
        qc = {
            "ok": True,
            "warnings": [],
            "water_balance": {"final_error_pct": 0.1},
            "cumulative_fluxes": {
                "final_sum_Infil": 1.0,
                "final_sum_vBot": -0.2,
            },
            "field_comparison": {"available": False, "requested": False},
        }
        (run_dir / "outputs" / "qc_summary.json").write_text(
            json.dumps(qc), encoding="utf-8",
        )
        summary_path = run_dir / "pipeline_summary.json"
        summary_path.write_text("{}", encoding="utf-8")
        return {
            "ok": True,
            "case_id": cfg.case_id,
            "run_dir": str(run_dir),
            "summary_path": str(summary_path),
            "steps": [],
        }

    summary = run_scenario_batch(
        SIMPLE_RUNNABLE_CONFIG,
        scenario_file,
        runs_root=tmp_path / "runs",
        timeout=60,
        hydrus_launch_mode="argv",
        pipeline_runner=fake_pipeline,
    )

    assert summary["ok"] is True
    assert [c["config_path"].name for c in calls] == [
        "case_002__base.json",
        "case_002__ks_low.json",
    ]
    assert all(c["overwrite_run"] is True for c in calls)
    assert all(c["timeout"] == 60 for c in calls)
    assert (tmp_path / "runs" / "simple_sensitivity" / "scenario_summary.csv").is_file()
    assert (tmp_path / "runs" / "simple_sensitivity" / "scenario_summary.json").is_file()
    rows = summary["scenarios"]
    assert rows[0]["case_id"] == "case_002__base"
    assert rows[1]["overrides"] == {"van_genuchten[0].Ks": 0.5}
    assert rows[1]["qc_ok"] is True
    assert rows[1]["final_sum_Infil"] == pytest.approx(1.0)


def test_run_scenario_batch_flattens_field_metrics(tmp_path: Path):
    scenario_file = _write_json(
        tmp_path / "scenarios.json",
        {
            "batch_id": "field_batch",
            "scenarios": [
                {"scenario_id": "base", "overrides": {}},
            ],
        },
    )
    field_csv = tmp_path / "field.csv"
    field_csv.write_text("time,node,theta\n0.25,3,0.12\n", encoding="utf-8")

    def fake_pipeline(config_path, *, overwrite_run, timeout, hydrus_launch_mode, field_data_path=None):
        cfg = load_config(config_path)
        run_dir = tmp_path / "runs" / cfg.case_id
        (run_dir / "outputs").mkdir(parents=True)
        qc = {
            "ok": True,
            "warnings": [],
            "field_comparison": {
                "available": True,
                "requested": True,
                "matched_rows": 2,
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
                    }
                },
            },
        }
        (run_dir / "outputs" / "qc_summary.json").write_text(
            json.dumps(qc), encoding="utf-8",
        )
        summary_path = run_dir / "pipeline_summary.json"
        summary_path.write_text("{}", encoding="utf-8")
        return {
            "ok": True,
            "case_id": cfg.case_id,
            "run_dir": str(run_dir),
            "summary_path": str(summary_path),
            "steps": [],
        }

    summary = run_scenario_batch(
        SIMPLE_RUNNABLE_CONFIG,
        scenario_file,
        runs_root=tmp_path / "runs",
        field_data_path=field_csv,
        pipeline_runner=fake_pipeline,
    )

    row = summary["scenarios"][0]
    assert row["field_data_available"] is True
    assert row["field_matched_rows"] == 2
    assert row["theta_node_3_rmse"] == pytest.approx(0.01)
    assert row["theta_node_3_mae"] == pytest.approx(0.008)
    assert row["theta_node_3_bias"] == pytest.approx(-0.002)
    assert row["theta_node_3_correlation"] == pytest.approx(0.99)
