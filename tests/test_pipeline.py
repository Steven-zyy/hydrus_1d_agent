"""Tests for hydrus_agent.pipeline (milestone 7).

Uses a monkey-patched runner that writes verbatim slices of the real
HYDRUS-1D output, so the pipeline is exercised end-to-end without
requiring the real H1D_CALC.EXE.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

import hydrus_agent.pipeline as pipeline
from hydrus_agent.pipeline import (
    HARD_STEPS,
    PIPELINE_SUMMARY_FILENAME,
    run_full_pipeline,
)
from hydrus_agent.runner import RunResult


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SIMPLE_RUNNABLE_CONFIG = PROJECT_ROOT / "config" / "simple_runnable_case.json"


# Reuse fixtures from milestone-4 tests.
from tests.test_output_reader import (
    BALANCE_FIXTURE, NOD_INF_FIXTURE, OBS_NODE_FIXTURE,
    RUN_INF_FIXTURE, T_LEVEL_FIXTURE,
)


def _write_real_outputs(project_dir: Path) -> None:
    """Write fixture HYDRUS output files into ``project_dir``."""
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "Balance.out").write_text(BALANCE_FIXTURE)
    (project_dir / "T_Level.out").write_text(T_LEVEL_FIXTURE)
    (project_dir / "Run_Inf.out").write_text(RUN_INF_FIXTURE)
    (project_dir / "Obs_Node.out").write_text(OBS_NODE_FIXTURE)
    (project_dir / "Nod_Inf.out").write_text(NOD_INF_FIXTURE)


@pytest.fixture
def isolated_runs(tmp_path, monkeypatch):
    """Redirect pipeline RUNS_ROOT to a tmp dir."""
    runs_root = tmp_path / "runs"
    monkeypatch.setattr(pipeline, "RUNS_ROOT", runs_root)
    return runs_root


@pytest.fixture
def fake_hydrus_exe(tmp_path, monkeypatch):
    """Touch a stand-in HYDRUS_EXE file so adapter and runner pre-flight pass."""
    exe = tmp_path / "fake_hydrus.exe"
    exe.write_text("not a real executable", encoding="utf-8")
    monkeypatch.setenv("HYDRUS_EXE", str(exe))
    return exe


@pytest.fixture
def fake_runner_writes_real_outputs(monkeypatch, isolated_runs):
    """Monkey-patch pipeline._resolve_runner to a runner that writes
    fixture HYDRUS outputs and returns a successful RunResult."""
    def _fake(project_dir, hydrus_exe, log_dir, *, timeout=None,
              launch_mode="argv"):
        project_dir = Path(project_dir)
        log_dir = Path(log_dir)
        _write_real_outputs(project_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "hydrus_run.log"
        log_path.write_text(
            f"command: ['{hydrus_exe}', '{project_dir}', '-1']\n"
            f"cwd: {project_dir}\n"
            f"launch mode: {launch_mode}\n"
            f"return code: 0\n"
            "--- stdout ---\nSimulation finished\n",
            encoding="utf-8",
        )
        return RunResult(
            success=True, return_code=0, log_path=log_path,
            stdout="Simulation finished\n", stderr="",
            generated_files=[
                project_dir / n for n in (
                    "Balance.out", "T_Level.out", "Run_Inf.out",
                    "Obs_Node.out", "Nod_Inf.out",
                )
            ],
            launch_mode=launch_mode,
            cmd=[str(hydrus_exe), str(project_dir), "-1"],
        )
    monkeypatch.setattr(pipeline, "_resolve_runner", lambda: _fake)
    return _fake


@pytest.fixture
def fake_runner_returns_nonzero(monkeypatch):
    """Monkey-patch the runner to return RunResult.success=False."""
    def _fake(project_dir, hydrus_exe, log_dir, *, timeout=None,
              launch_mode="argv"):
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "hydrus_run.log"
        log_path.write_text("return code: 2\nERROR: convergence not reached\n",
                             encoding="utf-8")
        return RunResult(
            success=False, return_code=2, log_path=log_path,
            stdout="", stderr="ERROR: convergence not reached\n",
            generated_files=[],
            launch_mode=launch_mode,
            cmd=[str(hydrus_exe), str(project_dir), "-1"],
        )
    monkeypatch.setattr(pipeline, "_resolve_runner", lambda: _fake)
    return _fake


# --- Happy path -----------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "stopped after 10 consecutive non-converged steps",
        "stopped after 10 consecutiv\ne non-converged steps",
        "stopped after 10 consecutive non-\nconverged steps",
        "stopped after 10 consecutive non converged steps",
        "stopped after 10 consecutive time steps",
        "numerical solution stopped after 10 consecutive non-converged steps",
    ],
)
def test_detect_numerical_failure_normalises_wrapped_error_msg(message):
    reason, excerpt = pipeline._detect_numerical_failure(message)

    assert reason is not None
    assert "stopped after 10 consecutive" in reason
    assert "\n" not in reason
    assert excerpt
    assert len(excerpt) <= 240


def test_full_pipeline_happy_path(
    isolated_runs, fake_hydrus_exe, fake_runner_writes_real_outputs,
):
    summary = run_full_pipeline(
        SIMPLE_RUNNABLE_CONFIG, overwrite_run=True, timeout=30,
    )
    assert summary["ok"] is True, summary
    assert summary["stopped_after_step"] is None
    assert summary["case_id"] == "case_002"

    # 8 steps recorded.
    step_names = [s["step"] for s in summary["steps"]]
    assert step_names == [
        "load_and_validate_config", "create_run_folder", "prepare_input",
        "run_hydrus", "read_outputs", "generate_plots", "run_qc",
        "generate_report",
    ]
    assert all(s["ok"] for s in summary["steps"])

    # Run folder + report + summary exist.
    run_dir = Path(summary["run_dir"])
    assert (run_dir / "report.md").is_file()
    assert (run_dir / "outputs" / "qc_summary.json").is_file()
    assert (run_dir / PIPELINE_SUMMARY_FILENAME).is_file()
    assert any(run_dir.glob("figures/*.png"))

    # Reproducibility manifest is written as an independent artefact.
    manifest_path = run_dir / "run_manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["case_id"] == summary["case_id"]
    assert manifest["hydrus"]["launch_mode"] == "argv"
    assert manifest["reliability"]["overall_status"] in {"ok", "incomplete"}
    assert any(
        entry["path"].lower().endswith(".in")
        or entry["path"].lower().endswith(".dat")
        or entry["path"].lower().endswith(".dir")
        or entry["path"] == "config.json"
        for entry in manifest["inputs"]
    )
    # pipeline_summary.json keys remain unchanged (no manifest_path key).
    assert "manifest_path" not in summary

    # Scientific review is written as a non-blocking artefact.
    sr_path = run_dir / "scientific_review.json"
    assert sr_path.is_file()
    sr = json.loads(sr_path.read_text(encoding="utf-8"))
    assert sr["schema_version"] == 1
    assert isinstance(sr["items"], list)
    assert {"info", "warning", "critical"} <= set(sr["counts"].keys())
    # Reviewer must not change pipeline_summary or overall_status.
    assert "scientific_review" not in summary
    assert summary["overall_status"] == "ok"


def test_full_pipeline_summary_json_round_trip(
    isolated_runs, fake_hydrus_exe, fake_runner_writes_real_outputs,
):
    summary = run_full_pipeline(SIMPLE_RUNNABLE_CONFIG, overwrite_run=True)
    on_disk = json.loads(
        Path(summary["summary_path"]).read_text(encoding="utf-8")
    )
    # Same step list and ok flag whether read in memory or from disk.
    assert on_disk["case_id"] == summary["case_id"]
    assert [s["step"] for s in on_disk["steps"]] == [
        s["step"] for s in summary["steps"]
    ]
    assert on_disk["ok"] is summary["ok"]


def test_full_pipeline_with_field_data_writes_comparison_outputs(
    isolated_runs, fake_hydrus_exe, fake_runner_writes_real_outputs, tmp_path,
):
    field_csv = tmp_path / "field_theta_head.csv"
    field_csv.write_text(
        "time,node,theta,h\n"
        "0.25,3,0.120,-1.000\n"
        "0.50,3,0.121,-1.010\n"
        "0.25,8,0.119,-1.020\n"
        "0.50,8,0.118,-1.030\n",
        encoding="utf-8",
    )

    summary = run_full_pipeline(
        SIMPLE_RUNNABLE_CONFIG,
        overwrite_run=True,
        timeout=30,
        field_data_path=field_csv,
    )

    assert summary["ok"] is True, summary
    step_names = [s["step"] for s in summary["steps"]]
    assert "compare_field_data" in step_names
    run_dir = Path(summary["run_dir"])
    assert (run_dir / "outputs" / "field_comparison_summary.json").is_file()
    assert (run_dir / "figures" / "field_overlay_theta.png").is_file()
    assert (run_dir / "figures" / "field_overlay_head.png").is_file()
    qc = json.loads((run_dir / "outputs" / "qc_summary.json").read_text(encoding="utf-8"))
    assert qc["field_comparison"]["available"] is True
    assert "Field Data Comparison" in (run_dir / "report.md").read_text(encoding="utf-8")


def test_pipeline_summary_records_atmospheric_csv_metadata(
    isolated_runs, fake_hydrus_exe, fake_runner_writes_real_outputs, tmp_path,
):
    csv_path = tmp_path / "atmosphere.csv"
    csv_path.write_text(
        "time_d,precipitation_m_d,potential_evaporation_m_d\n"
        "0,0,0.003\n"
        "1,0.01,0.002\n"
        "2,0,0.004\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "csv_atmospheric.json"
    raw = json.loads(SIMPLE_RUNNABLE_CONFIG.read_text(encoding="utf-8"))
    raw["case_id"] = "pipeline_csv_atmospheric"
    raw["simulation_time"] = {
        "t_init": 0.0,
        "t_end": 2.0,
        "dt_init": 0.001,
        "units": "days",
    }
    raw["upper_boundary"] = {"type": "atmospheric"}
    raw["atmospheric"] = {
        "enabled": True,
        "source_csv": csv_path.name,
        "time_column": "time_d",
        "precipitation_column": "precipitation_m_d",
        "potential_evaporation_column": "potential_evaporation_m_d",
        "units": {"time": "day", "length": "m"},
    }
    raw["output_settings"] = {
        "print_times": [1.0, 2.0],
        "print_interval": 0.5,
    }
    config_path.write_text(json.dumps(raw), encoding="utf-8")

    summary = run_full_pipeline(config_path, overwrite_run=True, timeout=30)

    assert summary["ok"] is True, summary
    atmospheric_source = summary["atmospheric_source"]
    assert atmospheric_source["source_type"] == "csv"
    assert atmospheric_source["record_count"] == 3
    assert atmospheric_source["covers_simulation_end_time"] is True
    on_disk = json.loads(Path(summary["summary_path"]).read_text(encoding="utf-8"))
    assert on_disk["atmospheric_source"]["source_type"] == "csv"


def test_pipeline_summary_records_material_csv_metadata(
    isolated_runs, fake_hydrus_exe, fake_runner_writes_real_outputs, tmp_path,
):
    csv_path = tmp_path / "materials.csv"
    csv_path.write_text(
        "material,theta_r,theta_s,alpha_1_m,n,Ks_m_d,l\n"
        "sandy_loam,0.065,0.410,7.5,1.89,1.061,0.5\n"
        "sand,0.045,0.430,14.5,2.68,7.128,0.5\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "csv_materials.json"
    raw = json.loads(SIMPLE_RUNNABLE_CONFIG.read_text(encoding="utf-8"))
    raw["case_id"] = "pipeline_csv_materials"
    raw["soil_profile"] = [
        {"depth_top": 0.0, "depth_bottom": 0.5, "material": "sandy_loam"},
        {"depth_top": 0.5, "depth_bottom": 1.0, "material": "sand"},
    ]
    raw["van_genuchten"] = {"source_csv": csv_path.name}
    config_path.write_text(json.dumps(raw), encoding="utf-8")

    summary = run_full_pipeline(config_path, overwrite_run=True, timeout=30)

    assert summary["ok"] is True, summary
    material_source = summary["material_source"]
    assert material_source["source_type"] == "csv"
    assert material_source["material_count"] == 2
    assert material_source["material_names"] == ["sandy_loam", "sand"]
    on_disk = json.loads(Path(summary["summary_path"]).read_text(encoding="utf-8"))
    assert on_disk["material_source"]["source_type"] == "csv"


def test_pipeline_detects_error_msg_numerical_failure(
    isolated_runs, fake_hydrus_exe, monkeypatch,
):
    def _fake(project_dir, hydrus_exe, log_dir, *, timeout=None,
              launch_mode="argv"):
        project_dir = Path(project_dir)
        log_dir = Path(log_dir)
        _write_real_outputs(project_dir)
        (project_dir / "Error.msg").write_text(
            "The numerical solution stopped after 10 consecutive "
            "non-converged steps.",
            encoding="utf-8",
        )
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "hydrus_run.log"
        log_path.write_text("return code: 0\n", encoding="utf-8")
        return RunResult(
            success=True,
            return_code=0,
            log_path=log_path,
            stdout="Calculations have finished successfully\n",
            stderr="",
            generated_files=[
                project_dir / "Balance.out",
                project_dir / "Error.msg",
            ],
            launch_mode=launch_mode,
            cmd=[str(hydrus_exe), str(project_dir), "-1"],
        )

    monkeypatch.setattr(pipeline, "_resolve_runner", lambda: _fake)

    summary = run_full_pipeline(SIMPLE_RUNNABLE_CONFIG, overwrite_run=True)

    assert summary["ok"] is False
    assert summary["overall_status"] == "failed"
    assert summary["execution_status"] == "completed"
    assert summary["hydrus_numerical_status"] == "failed"
    assert summary["hydrus_status"]["return_code"] == 0
    assert summary["hydrus_status"]["error_message_file"].endswith("Error.msg")
    assert summary["hydrus_status"]["numerical_failure_detected"] is True
    assert "10 consecutive non-converged steps" in summary["hydrus_status"]["failure_reason"]
    run_step = next(s for s in summary["steps"] if s["step"] == "run_hydrus")
    assert run_step["ok"] is True
    on_disk = json.loads(Path(summary["summary_path"]).read_text(encoding="utf-8"))
    assert on_disk["overall_status"] == "failed"
    assert on_disk["hydrus_status"]["numerical_failure_detected"] is True


def test_pipeline_detects_wrapped_error_msg_with_generated_outputs_and_qc_failure(
    isolated_runs, fake_hydrus_exe, monkeypatch,
):
    bad_balance = BALANCE_FIXTURE.replace(
        " WatBalR  [%]              0.000",
        " WatBalR  [%]             50.231",
    )

    def _fake(project_dir, hydrus_exe, log_dir, *, timeout=None,
              launch_mode="argv"):
        project_dir = Path(project_dir)
        log_dir = Path(log_dir)
        _write_real_outputs(project_dir)
        (project_dir / "Balance.out").write_text(bad_balance)
        (project_dir / "Error.msg").write_text(
            "The numerical solution stoppe\n"
            "d after 10 consecutiv\n"
            "e non-\n"
            "converged steps.",
            encoding="utf-8",
        )
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "hydrus_run.log"
        log_path.write_text("return code: 0\n", encoding="utf-8")
        return RunResult(
            success=True,
            return_code=0,
            log_path=log_path,
            stdout="Calculations have finished successfully\n",
            stderr="",
            generated_files=[
                project_dir / "Balance.out",
                project_dir / "T_Level.out",
                project_dir / "Obs_Node.out",
                project_dir / "Error.msg",
            ],
            launch_mode=launch_mode,
            cmd=[str(hydrus_exe), str(project_dir), "-1"],
        )

    monkeypatch.setattr(pipeline, "_resolve_runner", lambda: _fake)

    summary = run_full_pipeline(SIMPLE_RUNNABLE_CONFIG, overwrite_run=True)

    assert summary["execution_status"] == "completed"
    assert summary["hydrus_numerical_status"] == "failed"
    assert summary["qc_status"] == "failed"
    assert summary["overall_status"] == "failed"
    assert summary["ok"] is False
    assert summary["hydrus_status"]["return_code"] == 0
    assert summary["hydrus_status"]["numerical_failure_detected"] is True
    assert "stopped after 10 consecutive" in summary["hydrus_status"]["failure_reason"]
    assert "error_excerpt" in summary["hydrus_status"]
    assert "consecutiv" in summary["hydrus_status"]["error_excerpt"]
    report_text = Path(summary["run_dir"], "report.md").read_text(encoding="utf-8")
    assert "## Run Reliability Warning" in report_text
    assert "HYDRUS returned code 0" in report_text
    assert "parsed output-step records" in report_text
    assert "HYDRUS Error.msg indicates" in report_text
    assert "All 4 solver steps converged." not in report_text


def test_pipeline_qc_failure_sets_overall_status_failed(
    isolated_runs, fake_hydrus_exe, monkeypatch,
):
    bad_balance = BALANCE_FIXTURE.replace(
        " WatBalR  [%]              0.000",
        " WatBalR  [%]             50.231",
    )

    def _fake(project_dir, hydrus_exe, log_dir, *, timeout=None,
              launch_mode="argv"):
        project_dir = Path(project_dir)
        log_dir = Path(log_dir)
        _write_real_outputs(project_dir)
        (project_dir / "Balance.out").write_text(bad_balance)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "hydrus_run.log"
        log_path.write_text("return code: 0\n", encoding="utf-8")
        return RunResult(
            success=True,
            return_code=0,
            log_path=log_path,
            stdout="Calculations have finished successfully\n",
            stderr="",
            generated_files=[project_dir / "Balance.out"],
            launch_mode=launch_mode,
            cmd=[str(hydrus_exe), str(project_dir), "-1"],
        )

    monkeypatch.setattr(pipeline, "_resolve_runner", lambda: _fake)

    summary = run_full_pipeline(SIMPLE_RUNNABLE_CONFIG, overwrite_run=True)

    assert summary["ok"] is False
    assert summary["hydrus_numerical_status"] == "converged"
    assert summary["qc_status"] == "failed"
    assert summary["overall_status"] == "failed"
    qc_step = next(s for s in summary["steps"] if s["step"] == "run_qc")
    assert qc_step["ok"] is True


def test_pipeline_clean_run_status_remains_ok(
    isolated_runs, fake_hydrus_exe, fake_runner_writes_real_outputs,
):
    summary = run_full_pipeline(SIMPLE_RUNNABLE_CONFIG, overwrite_run=True)

    assert summary["ok"] is True
    assert summary["execution_status"] == "completed"
    assert summary["hydrus_numerical_status"] == "converged"
    assert summary["qc_status"] == "passed"
    assert summary["overall_status"] == "ok"
    assert summary["hydrus_status"]["numerical_failure_detected"] is False


# --- Hard-failure stops ---------------------------------------------------


def test_pipeline_stops_when_config_invalid(isolated_runs, fake_hydrus_exe,
                                            tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ this is not json }")
    summary = run_full_pipeline(bad, overwrite_run=True)
    assert summary["ok"] is False
    assert summary["stopped_after_step"] == "load_and_validate_config"
    # Only one step recorded.
    assert len(summary["steps"]) == 1
    assert "summary_path" not in summary  # no run_dir to write into


def test_pipeline_stops_after_failed_run(
    isolated_runs, fake_hydrus_exe, fake_runner_returns_nonzero,
):
    summary = run_full_pipeline(SIMPLE_RUNNABLE_CONFIG, overwrite_run=True)
    assert summary["ok"] is False
    assert summary["stopped_after_step"] == "run_hydrus"

    step_names = [s["step"] for s in summary["steps"]]
    # Read/plot/QC/report not recorded because run_hydrus stopped us.
    assert "read_outputs" not in step_names
    assert "generate_report" not in step_names

    run_step = next(s for s in summary["steps"] if s["step"] == "run_hydrus")
    assert run_step["ok"] is False
    assert "non-zero" in run_step["error"]
    # pipeline_summary.json is still written because run_dir exists.
    assert "summary_path" in summary


def test_pipeline_stops_when_hydrus_exe_missing(
    isolated_runs, monkeypatch,
):
    """No HYDRUS_EXE → prepare_input is the hard step that fails."""
    monkeypatch.delenv("HYDRUS_EXE", raising=False)
    # Override the .env-based resolver to return None.
    monkeypatch.setattr(
        "hydrus_agent.pipeline.resolve_hydrus_exe"
        if hasattr(pipeline, "resolve_hydrus_exe") else
        "hydrus_agent.env.resolve_hydrus_exe",
        lambda *a, **k: (None, "unset"),
    )
    summary = run_full_pipeline(SIMPLE_RUNNABLE_CONFIG, overwrite_run=True)
    assert summary["ok"] is False
    assert summary["stopped_after_step"] == "prepare_input"


# --- Soft steps continue --------------------------------------------------


def test_pipeline_continues_through_qc_warnings(
    isolated_runs, fake_hydrus_exe, monkeypatch,
):
    """High water-balance error generates a QC warning, but the pipeline
    still progresses to report generation."""
    bad_balance = BALANCE_FIXTURE.replace(
        " WatBalR  [%]              0.000",
        " WatBalR  [%]              5.500",
    )

    def _fake(project_dir, hydrus_exe, log_dir, *, timeout=None,
              launch_mode="argv"):
        project_dir = Path(project_dir)
        log_dir = Path(log_dir)
        _write_real_outputs(project_dir)
        # Replace Balance.out with the high-error fixture.
        (project_dir / "Balance.out").write_text(bad_balance)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "hydrus_run.log"
        log_path.write_text("return code: 0\n")
        return RunResult(
            success=True, return_code=0, log_path=log_path,
            stdout="", stderr="",
            generated_files=[project_dir / "Balance.out"],
            launch_mode=launch_mode, cmd=[str(hydrus_exe)],
        )

    monkeypatch.setattr(pipeline, "_resolve_runner", lambda: _fake)
    summary = run_full_pipeline(SIMPLE_RUNNABLE_CONFIG, overwrite_run=True)

    qc_step = next(s for s in summary["steps"] if s["step"] == "run_qc")
    assert qc_step["ok"] is True  # soft step -> ok even with warnings
    assert any("water balance error" in w for w in qc_step["warnings"])
    # Report still generated.
    report_step = next(
        s for s in summary["steps"] if s["step"] == "generate_report"
    )
    assert report_step["ok"] is True
    assert summary["stopped_after_step"] is None
    assert summary["qc_status"] == "failed"
    assert summary["overall_status"] == "failed"
    assert summary["ok"] is False


def test_hard_steps_constant_is_correct():
    """Sanity check: HARD_STEPS exposes the expected set."""
    assert "load_and_validate_config" in HARD_STEPS
    assert "create_run_folder" in HARD_STEPS
    assert "prepare_input" in HARD_STEPS
    assert "run_hydrus" in HARD_STEPS
    assert "read_outputs" not in HARD_STEPS
    assert "generate_report" not in HARD_STEPS
