"""Tests for the CLI flags introduced in milestone 3.5.

These exercise main.main() in-process so we can capture stdout and inspect
exit codes without a subprocess. HYDRUS is never actually invoked.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Importing main triggers no side effects at module level.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main as cli  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SIMPLE_RUNNABLE_CONFIG = PROJECT_ROOT / "config" / "simple_runnable_case.json"


@pytest.fixture(autouse=True)
def isolated_runs(tmp_path, monkeypatch):
    """Redirect main.RUNS_ROOT to a tmp dir so tests don't touch the real
    runs/ directory."""
    monkeypatch.setattr(cli, "RUNS_ROOT", tmp_path / "runs")
    return tmp_path / "runs"


def test_diagnose_run_does_not_invoke_subprocess(isolated_runs, monkeypatch,
                                                 capsys, tmp_path):
    """--diagnose-run must NOT call subprocess.run.

    We monkeypatch subprocess.run inside hydrus_agent.runner to raise; if the
    diagnostic path tries to run HYDRUS the test fails loudly.
    """
    from hydrus_agent import runner as runner_module

    def _explode(*args, **kwargs):
        raise AssertionError(
            "subprocess.run was called during --diagnose-run; that flag must be read-only"
        )

    monkeypatch.setattr(runner_module.subprocess, "run", _explode)

    rc = cli.main([
        "--config", str(SIMPLE_RUNNABLE_CONFIG),
        "--diagnose-run",
    ])
    captured = capsys.readouterr()
    assert rc == 0
    assert "HYDRUS-1D run diagnostic" in captured.out
    assert "Diagnostic complete. HYDRUS was NOT invoked." in captured.out


def test_diagnose_run_reports_prior_timeout(isolated_runs, capsys):
    """If a previous hydrus_run.log contains the TIMEOUT marker, the
    diagnostic must report 'timed out: True'."""
    from hydrus_agent.runner import TIMEOUT_MARKER

    case_dir = isolated_runs / "case_002"
    (case_dir / "logs").mkdir(parents=True)
    (case_dir / "hydrus_project").mkdir()
    (case_dir / "logs" / "hydrus_run.log").write_text(
        f"command: ['fake']\n"
        f"cwd: somewhere\n"
        f"return code: None\n"
        f"note: {TIMEOUT_MARKER} after 30.0s (process killed)\n",
        encoding="utf-8",
    )

    rc = cli.main([
        "--config", str(SIMPLE_RUNNABLE_CONFIG),
        "--diagnose-run",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "timed out  : True" in out


def test_clean_run_folder_removes_existing_case(isolated_runs, capsys):
    """--clean-run-folder should wipe runs/<case_id>/ before recreating it."""
    case_dir = isolated_runs / "case_002"
    (case_dir).mkdir(parents=True)
    sentinel = case_dir / "STALE_FROM_PREV_RUN.out"
    sentinel.write_text("should be deleted")

    rc = cli.main([
        "--config", str(SIMPLE_RUNNABLE_CONFIG),
        "--clean-run-folder",
    ])
    assert rc == 0
    assert not sentinel.exists(), (
        "--clean-run-folder did not remove the stale file"
    )
    # The case folder is recreated with the standard subfolders.
    assert (isolated_runs / "case_002" / "inputs").is_dir()


def test_clean_run_folder_refuses_to_delete_outside_runs(isolated_runs, monkeypatch):
    """Defence-in-depth: _safe_clean must refuse to delete a path outside
    the configured runs root."""
    bogus = isolated_runs.parent / "definitely-not-in-runs"
    bogus.mkdir()
    with pytest.raises(SystemExit) as excinfo:
        cli._safe_clean(bogus)
    assert "Refusing to clean" in str(excinfo.value)


def test_benchmark_official_cli_delegates_to_benchmark_harness(monkeypatch, capsys, tmp_path):
    """--benchmark-official should run the official benchmark harness without
    loading a generated config."""
    from hydrus_agent import benchmark as benchmark_module

    source = tmp_path / "raw" / "Direct" / "FAKECASE"
    source.mkdir(parents=True)

    calls = {}

    def fake_run_official_benchmark(source_dir, benchmark_id, *, timeout, hydrus_launch_mode):
        calls["source_dir"] = Path(source_dir)
        calls["benchmark_id"] = benchmark_id
        calls["timeout"] = timeout
        calls["hydrus_launch_mode"] = hydrus_launch_mode
        return {
            "ok": True,
            "benchmark_id": benchmark_id,
            "summary_path": str(tmp_path / "benchmark_summary.json"),
        }

    monkeypatch.setattr(
        benchmark_module,
        "run_official_benchmark",
        fake_run_official_benchmark,
    )

    rc = cli.main([
        "--benchmark-official", str(source),
        "--benchmark-id", "FAKECASE",
        "--timeout", "60",
        "--hydrus-launch-mode", "argv",
    ])

    out = capsys.readouterr().out
    assert rc == 0
    assert calls == {
        "source_dir": source,
        "benchmark_id": "FAKECASE",
        "timeout": 60.0,
        "hydrus_launch_mode": "argv",
    }
    assert "Official benchmark: FAKECASE" in out
    assert "Summary JSON" in out


def test_benchmark_manifest_cli_delegates_to_batch_harness(monkeypatch, capsys, tmp_path):
    """--benchmark-manifest should run the batch benchmark harness."""
    from hydrus_agent import benchmark as benchmark_module

    manifest = tmp_path / "manifest.csv"
    manifest.write_text("case_id,source_dir,supported_now\n", encoding="utf-8")
    csv_path = tmp_path / "benchmark_batch_summary.csv"
    json_path = tmp_path / "benchmark_batch_summary.json"

    calls = {}

    def fake_run_benchmark_manifest(
        manifest_path,
        *,
        timeout,
        hydrus_launch_mode,
        only_supported,
    ):
        calls["manifest_path"] = Path(manifest_path)
        calls["timeout"] = timeout
        calls["hydrus_launch_mode"] = hydrus_launch_mode
        calls["only_supported"] = only_supported
        return {
            "ok": True,
            "summary_csv_path": str(csv_path),
            "summary_json_path": str(json_path),
            "counts": {
                "pass": 1,
                "partial": 0,
                "fail": 0,
                "skipped": 2,
            },
            "cases": [],
        }

    monkeypatch.setattr(
        benchmark_module,
        "run_benchmark_manifest",
        fake_run_benchmark_manifest,
    )

    rc = cli.main([
        "--benchmark-manifest", str(manifest),
        "--timeout", "60",
        "--hydrus-launch-mode", "argv",
    ])

    out = capsys.readouterr().out
    assert rc == 0
    assert calls == {
        "manifest_path": manifest,
        "timeout": 60.0,
        "hydrus_launch_mode": "argv",
        "only_supported": True,
    }
    assert "HYDRUS-1D official benchmark batch" in out
    assert "Batch summary CSV" in out
    assert "pass=1" in out


def test_benchmark_manifest_all_examples_cli_delegates_to_full_sweep(
    monkeypatch, capsys, tmp_path
):
    """--benchmark-manifest --all-examples should run the full official sweep."""
    from hydrus_agent import benchmark as benchmark_module

    manifest = tmp_path / "manifest.csv"
    manifest.write_text("case_id,source_dir,supported_now\n", encoding="utf-8")
    csv_path = tmp_path / "full_example_sweep_summary.csv"
    json_path = tmp_path / "full_example_sweep_summary.json"
    report_path = tmp_path / "full_example_sweep_report.md"

    calls = {}

    def fake_run_full_example_sweep(
        manifest_path,
        *,
        examples_root,
        timeout,
        hydrus_launch_mode,
        report_path,
    ):
        calls["manifest_path"] = Path(manifest_path)
        calls["examples_root"] = examples_root
        calls["timeout"] = timeout
        calls["hydrus_launch_mode"] = hydrus_launch_mode
        calls["report_path"] = Path(report_path)
        return {
            "ok": False,
            "summary_csv_path": str(csv_path),
            "summary_json_path": str(json_path),
            "report_path": str(report_path),
            "counts": {
                "pass": 1,
                "partial": 2,
                "fail": 1,
                "skipped": 0,
                "future": 3,
            },
            "cases": [],
        }

    monkeypatch.setattr(
        benchmark_module,
        "run_full_example_sweep",
        fake_run_full_example_sweep,
    )

    rc = cli.main([
        "--benchmark-manifest", str(manifest),
        "--all-examples",
        "--timeout", "60",
        "--hydrus-launch-mode", "argv",
    ])

    out = capsys.readouterr().out
    assert rc == 7
    assert calls == {
        "manifest_path": manifest,
        "examples_root": None,
        "timeout": 60.0,
        "hydrus_launch_mode": "argv",
        "report_path": Path("docs/full_example_sweep_report.md"),
    }
    assert "HYDRUS-1D full official example sweep" in out
    assert "Full sweep CSV" in out
    assert "future=3" in out


def test_benchmark_gap_report_cli_delegates_to_reporter(monkeypatch, capsys, tmp_path):
    """--benchmark-gap-report should write the report without running HYDRUS."""
    from hydrus_agent import benchmark as benchmark_module

    manifest = tmp_path / "manifest.csv"
    manifest.write_text("case_id,source_dir,supported_now\n", encoding="utf-8")
    report = tmp_path / "benchmark_gap_report.md"
    batch = tmp_path / "benchmark_batch_summary.csv"

    calls = {}

    def fake_generate_benchmark_gap_report(
        manifest_path,
        batch_summary_path,
        output_path,
    ):
        calls["manifest_path"] = Path(manifest_path)
        calls["batch_summary_path"] = Path(batch_summary_path)
        calls["output_path"] = Path(output_path)
        output_path.write_text("fake report", encoding="utf-8")
        return output_path

    monkeypatch.setattr(
        benchmark_module,
        "BENCHMARK_RESULTS_ROOT",
        tmp_path,
    )
    monkeypatch.setattr(
        benchmark_module,
        "generate_benchmark_gap_report",
        fake_generate_benchmark_gap_report,
    )

    rc = cli.main([
        "--benchmark-gap-report", str(manifest),
    ])

    out = capsys.readouterr().out
    assert rc == 0
    assert calls == {
        "manifest_path": manifest,
        "batch_summary_path": batch,
        "output_path": report,
    }
    assert "HYDRUS-1D benchmark gap report" in out
    assert "Gap report" in out


def test_all_cli_passes_field_data_to_pipeline(monkeypatch, capsys, tmp_path):
    field_csv = tmp_path / "field.csv"
    field_csv.write_text("time,node,theta\n0.25,3,0.12\n", encoding="utf-8")

    calls = {}

    def fake_run_all(config_path, *, overwrite_run, timeout, launch_mode, field_data_path=None):
        calls["config_path"] = Path(config_path)
        calls["overwrite_run"] = overwrite_run
        calls["timeout"] = timeout
        calls["launch_mode"] = launch_mode
        calls["field_data_path"] = Path(field_data_path)
        return 0

    monkeypatch.setattr(cli, "_run_all", fake_run_all)

    rc = cli.main([
        "--config", str(SIMPLE_RUNNABLE_CONFIG),
        "--all",
        "--allow-config-mismatch",
        "--field-data", str(field_csv),
        "--timeout", "30",
        "--hydrus-launch-mode", "argv",
    ])

    assert rc == 0
    assert calls == {
        "config_path": SIMPLE_RUNNABLE_CONFIG,
        "overwrite_run": False,
        "timeout": 30.0,
        "launch_mode": "argv",
        "field_data_path": field_csv,
    }


def test_scenario_file_cli_delegates_to_scenario_runner(monkeypatch, capsys, tmp_path):
    from hydrus_agent import scenario_runner

    scenario_file = tmp_path / "scenarios.json"
    scenario_file.write_text('{"batch_id": "batch", "scenarios": []}', encoding="utf-8")
    field_csv = tmp_path / "field.csv"
    field_csv.write_text("time,node,theta\n0.25,3,0.12\n", encoding="utf-8")
    calls = {}

    def fake_run_scenario_batch(
        base_config_path,
        scenario_file_path,
        *,
        timeout,
        hydrus_launch_mode,
        field_data_path,
        overwrite_run,
    ):
        calls["base_config_path"] = Path(base_config_path)
        calls["scenario_file_path"] = Path(scenario_file_path)
        calls["timeout"] = timeout
        calls["hydrus_launch_mode"] = hydrus_launch_mode
        calls["field_data_path"] = Path(field_data_path)
        calls["overwrite_run"] = overwrite_run
        return {
            "ok": False,
            "batch_id": "batch",
            "summary_csv_path": str(tmp_path / "scenario_summary.csv"),
            "summary_json_path": str(tmp_path / "scenario_summary.json"),
            "scenarios": [{"status": "pass"}, {"status": "fail"}],
            "counts": {"pass": 1, "fail": 1},
        }

    monkeypatch.setattr(
        scenario_runner,
        "run_scenario_batch",
        fake_run_scenario_batch,
    )

    rc = cli.main([
        "--config", str(SIMPLE_RUNNABLE_CONFIG),
        "--scenario-file", str(scenario_file),
        "--field-data", str(field_csv),
        "--timeout", "60",
        "--hydrus-launch-mode", "argv",
    ])

    out = capsys.readouterr().out
    assert rc == 7
    assert calls == {
        "base_config_path": SIMPLE_RUNNABLE_CONFIG,
        "scenario_file_path": scenario_file,
        "timeout": 60.0,
        "hydrus_launch_mode": "argv",
        "field_data_path": field_csv,
        "overwrite_run": True,
    }
    assert "HYDRUS-1D scenario batch" in out
    assert "Scenario summary CSV" in out


def test_scenario_report_cli_delegates_to_scenario_analysis(monkeypatch, capsys, tmp_path):
    from hydrus_agent import scenario_analysis

    batch_dir = tmp_path / "simple_sensitivity"
    batch_dir.mkdir()
    report_path = batch_dir / "scenario_report.md"
    calls = {}

    def fake_generate_scenario_comparison_report(path):
        calls["batch_dir"] = Path(path)
        report_path.write_text("fake report", encoding="utf-8")
        return report_path

    monkeypatch.setattr(
        scenario_analysis,
        "generate_scenario_comparison_report",
        fake_generate_scenario_comparison_report,
    )

    rc = cli.main([
        "--scenario-report", str(batch_dir),
    ])

    out = capsys.readouterr().out
    assert rc == 0
    assert calls == {"batch_dir": batch_dir}
    assert "HYDRUS-1D scenario comparison report" in out
    assert "Scenario report" in out


def test_config_review_prints_csv_atmospheric_metadata(monkeypatch, capsys, tmp_path):
    csv_path = tmp_path / "atmosphere.csv"
    csv_path.write_text(
        "time_d,precipitation_m_d,potential_evaporation_m_d\n"
        "0,0,0.003\n"
        "1,0.01,0.002\n"
        "2,0,0.004\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "csv_atmospheric.json"
    config_path.write_text(
        """
{
  "project_name": "csv atmospheric review test",
  "case_id": "csv_review_test",
  "simulation_time": {"t_init": 0.0, "t_end": 2.0, "dt_init": 0.001, "units": "days"},
  "soil_profile": [{"depth_top": 0.0, "depth_bottom": 1.0, "material_id": 1}],
  "van_genuchten": [{"material_id": 1, "theta_r": 0.065, "theta_s": 0.41, "alpha": 7.5, "n": 1.89, "Ks": 1.061, "l": 0.5}],
  "initial_condition": {"type": "pressure_head", "value": -1.0},
  "upper_boundary": {"type": "atmospheric"},
  "lower_boundary": {"type": "free_drainage"},
  "atmospheric": {
    "enabled": true,
    "source_csv": "atmosphere.csv",
    "time_column": "time_d",
    "precipitation_column": "precipitation_m_d",
    "potential_evaporation_column": "potential_evaporation_m_d",
    "units": {"time": "day", "length": "m"}
  },
  "observation_depths": [0.3, 0.7],
  "output_settings": {"print_times": [1.0, 2.0], "print_interval": 0.5}
}
""",
        encoding="utf-8",
    )
    state_dir = tmp_path / "review_state"
    monkeypatch.setattr(cli, "REVIEW_STATE_DIR", state_dir)

    rc = cli.main(["--config", str(config_path), "--review"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "Validation status: valid ModelConfig" in out
    assert "atmospheric CSV" in out
    assert "atmosphere.csv" in out
    assert "records     : 3" in out
    assert "time range  : 0.0 to 2.0 day" in out
    assert "total precip" in out
    assert "covers end  : yes" in out
    assert (state_dir / "last_review.json").is_file()


def test_config_review_prints_material_csv_metadata(monkeypatch, capsys, tmp_path):
    csv_path = tmp_path / "materials.csv"
    csv_path.write_text(
        "material,theta_r,theta_s,alpha_1_m,n,Ks_m_d,l\n"
        "sandy_loam,0.065,0.410,7.5,1.89,1.061,0.5\n"
        "sand,0.045,0.430,14.5,2.68,7.128,0.5\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "csv_materials.json"
    config_path.write_text(
        """
{
  "project_name": "csv material review test",
  "case_id": "csv_material_review_test",
  "simulation_time": {"t_init": 0.0, "t_end": 2.0, "dt_init": 0.001, "units": "days"},
  "soil_profile": [
    {"depth_top": 0.0, "depth_bottom": 1.0, "material": "sandy_loam"},
    {"depth_top": 1.0, "depth_bottom": 2.0, "material": "sand"}
  ],
  "van_genuchten": {"source_csv": "materials.csv"},
  "initial_condition": {"type": "pressure_head", "value": -1.0},
  "upper_boundary": {"type": "constant_flux", "flux": 0.0},
  "lower_boundary": {"type": "free_drainage"},
  "observation_depths": [0.3, 1.7],
  "output_settings": {"print_times": [1.0, 2.0], "print_interval": 0.5}
}
""",
        encoding="utf-8",
    )
    state_dir = tmp_path / "review_state"
    monkeypatch.setattr(cli, "REVIEW_STATE_DIR", state_dir)

    rc = cli.main(["--config", str(config_path), "--review"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "Validation status: valid ModelConfig" in out
    assert "material CSV" in out
    assert "materials.csv" in out
    assert "materials   : 2" in out
    assert "sandy_loam" in out
    assert "theta_r=0.065" in out
    assert "alpha=7.5 1/m" in out
    assert "Ks=1.061 m/day" in out
    assert "units       : theta=-, alpha=1/m, Ks=m/day, l=-" in out
    assert (state_dir / "last_review.json").is_file()


def test_all_cli_prints_numerical_failure_and_qc_status(monkeypatch, capsys):
    from hydrus_agent import pipeline

    def fake_run_full_pipeline(*args, **kwargs):
        return {
            "ok": False,
            "run_dir": "runs\\bad_case",
            "summary_path": "runs\\bad_case\\pipeline_summary.json",
            "stopped_after_step": None,
            "qc_status": "failed",
            "hydrus_status": {
                "return_code": 0,
                "numerical_failure_detected": True,
                "failure_reason": (
                    "stopped after 10 consecutive non-converged steps"
                ),
                "error_excerpt": (
                    "stopped after 10 consecutiv e non- converged steps"
                ),
            },
            "steps": [
                {"step": "run_hydrus", "ok": True, "warnings": []},
                {"step": "run_qc", "ok": True, "warnings": ["bad balance"]},
            ],
        }

    monkeypatch.setattr(pipeline, "run_full_pipeline", fake_run_full_pipeline)

    rc = cli.main([
        "--config", str(SIMPLE_RUNNABLE_CONFIG),
        "--all",
        "--allow-config-mismatch",
    ])

    out = capsys.readouterr().out
    assert rc == 7
    assert (
        "HYDRUS returned code 0, but numerical failure was detected in Error.msg."
        in out
    )
    assert "QC status: failed." in out
    assert "Results may be incomplete or unreliable." in out
