"""Tests for official-example benchmark harnesses.

These use fake example folders and monkeypatched runner hooks. The real
PC-Progress examples are intentionally not read by the tests.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from hydrus_agent import benchmark


@dataclass
class FakeRunResult:
    success: bool = True
    return_code: int = 0
    log_path: Path | None = None
    stdout: str = "fake hydrus ok"
    stderr: str = ""
    generated_files: list[Path] | None = None
    launch_mode: str = "argv"
    cmd: list[str] | None = None
    false_success_reason: str | None = None


@pytest.fixture
def fake_source(tmp_path: Path) -> Path:
    source = tmp_path / "pc_progress_raw" / "Direct" / "FAKECASE"
    source.mkdir(parents=True)
    (source / "Selector.in").write_text("selector", encoding="utf-8")
    (source / "PROFILE.DAT").write_text("profile", encoding="utf-8")
    (source / "DESCRIPT.TXT").write_text("official example", encoding="utf-8")
    (source / "nested").mkdir()
    (source / "nested" / "KEEP.DAT").write_text("nested", encoding="utf-8")
    return source


def test_copy_official_example_copies_into_benchmark_results_without_touching_source(
    tmp_path: Path, fake_source: Path, monkeypatch,
):
    results_root = tmp_path / "benchmark_results"
    stale = results_root / "FAKECASE" / "hydrus_project" / "STALE.OUT"
    stale.parent.mkdir(parents=True)
    stale.write_text("old", encoding="utf-8")
    monkeypatch.setattr(benchmark, "BENCHMARK_RESULTS_ROOT", results_root)

    copied = benchmark.copy_official_example(fake_source, "FAKECASE")

    assert copied == results_root / "FAKECASE" / "hydrus_project"
    assert (copied / "Selector.in").read_text(encoding="utf-8") == "selector"
    assert (copied / "PROFILE.DAT").read_text(encoding="utf-8") == "profile"
    assert (copied / "nested" / "KEEP.DAT").read_text(encoding="utf-8") == "nested"
    assert not stale.exists()
    assert not (fake_source / "LEVEL_01.DIR").exists()
    assert (fake_source / "DESCRIPT.TXT").read_text(encoding="utf-8") == "official example"


def test_run_official_benchmark_runs_copied_project_and_writes_summary(
    tmp_path: Path, fake_source: Path, monkeypatch,
):
    results_root = tmp_path / "benchmark_results"
    monkeypatch.setattr(benchmark, "BENCHMARK_RESULTS_ROOT", results_root)

    fake_exe = tmp_path / "H1D_CALC.EXE"
    fake_exe.write_text("not actually executed", encoding="utf-8")
    monkeypatch.setattr(
        benchmark,
        "resolve_hydrus_exe",
        lambda: (str(fake_exe), "test"),
    )

    calls = {}

    def fake_runner(project_dir, hydrus_exe, log_dir, *, timeout, launch_mode):
        calls["project_dir"] = Path(project_dir)
        calls["hydrus_exe"] = Path(hydrus_exe)
        calls["log_dir"] = Path(log_dir)
        calls["timeout"] = timeout
        calls["launch_mode"] = launch_mode
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True)
        log_path = log_dir / "hydrus_run.log"
        log_path.write_text("fake run log", encoding="utf-8")
        generated = Path(project_dir) / "Balance.out"
        generated.write_text(
            "Time [T] 0\n"
            "W-volume [L] 1.0\n"
            "WatBalR [%] 0.0\n",
            encoding="utf-8",
        )
        return FakeRunResult(
            log_path=log_path,
            generated_files=[generated],
            cmd=[str(hydrus_exe), str(project_dir), "-1"],
        )

    monkeypatch.setattr(benchmark, "run_hydrus_project", fake_runner)

    summary = benchmark.run_official_benchmark(
        fake_source,
        "FAKECASE",
        timeout=12,
        hydrus_launch_mode="level-dir",
    )

    run_dir = results_root / "FAKECASE"
    project_dir = run_dir / "hydrus_project"
    assert calls == {
        "project_dir": project_dir,
        "hydrus_exe": fake_exe,
        "log_dir": run_dir / "logs",
        "timeout": 12,
        "launch_mode": "level-dir",
    }
    assert summary["ok"] is False
    assert summary["benchmark_id"] == "FAKECASE"
    assert summary["source_dir"] == str(fake_source)
    assert summary["project_dir"] == str(project_dir)
    assert summary["run"]["success"] is True
    assert summary["outputs"]["Balance.out"]["rows"] == 1
    assert summary["qc"]["tables"]["Balance.out"]["non_empty"] is True
    assert summary["summary_path"] == str(run_dir / "benchmark_summary.json")
    assert (run_dir / "benchmark_summary.json").is_file()

    on_disk = json.loads((run_dir / "benchmark_summary.json").read_text(encoding="utf-8"))
    assert on_disk["benchmark_id"] == "FAKECASE"
    assert isinstance(on_disk["figures"], list)
    for figure in on_disk["figures"]:
        assert Path(figure).is_file()


def test_run_official_benchmark_records_runner_error_and_still_writes_summary(
    tmp_path: Path, fake_source: Path, monkeypatch,
):
    from hydrus_agent.runner import RunnerError

    results_root = tmp_path / "benchmark_results"
    monkeypatch.setattr(benchmark, "BENCHMARK_RESULTS_ROOT", results_root)
    fake_exe = tmp_path / "H1D_CALC.EXE"
    fake_exe.write_text("not actually executed", encoding="utf-8")
    monkeypatch.setattr(benchmark, "resolve_hydrus_exe", lambda: (str(fake_exe), "test"))

    def fake_runner(*args, **kwargs):
        raise RunnerError("boom")

    monkeypatch.setattr(benchmark, "run_hydrus_project", fake_runner)

    summary = benchmark.run_official_benchmark(fake_source, "FAKECASE")

    assert summary["ok"] is False
    assert summary["run"]["success"] is False
    assert summary["run"]["error"] == "boom"
    assert summary["stopped_after_step"] == "run_hydrus"
    assert (results_root / "FAKECASE" / "benchmark_summary.json").is_file()


def test_run_benchmark_manifest_runs_supported_cases_and_records_skips(
    tmp_path: Path, monkeypatch,
):
    results_root = tmp_path / "benchmark_results"
    monkeypatch.setattr(benchmark, "BENCHMARK_RESULTS_ROOT", results_root)

    source_root = tmp_path / "pc_progress_raw" / "Direct"
    for case_id in ["SUPPORTED", "PARTIAL_CASE", "UNSUPPORTED"]:
        source = source_root / case_id
        source.mkdir(parents=True)
        (source / "Selector.in").write_text("selector", encoding="utf-8")

    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "case_id,process_type,source_dir,supported_now,notes\n"
        f"SUPPORTED,water_flow,{source_root / 'SUPPORTED'},yes,ready\n"
        f"PARTIAL_CASE,solute,{source_root / 'PARTIAL_CASE'},partial,solute out of scope\n"
        f"UNSUPPORTED,heat,{source_root / 'UNSUPPORTED'},no,heat out of scope\n",
        encoding="utf-8",
    )

    calls = []

    def fake_run_official_benchmark(source_dir, benchmark_id, *, timeout, hydrus_launch_mode):
        calls.append((Path(source_dir), benchmark_id, timeout, hydrus_launch_mode))
        summary_path = results_root / benchmark_id / "benchmark_summary.json"
        summary_path.parent.mkdir(parents=True)
        summary_path.write_text("{}", encoding="utf-8")
        return {
            "ok": True,
            "benchmark_id": benchmark_id,
            "source_dir": str(source_dir),
            "run": {"success": True},
            "outputs": {
                "Balance.out": {"empty": False},
                "T_Level.out": {"empty": False},
            },
            "qc": {"ok": True, "warnings": []},
            "figures": [str(results_root / benchmark_id / "figures" / "one.png")],
            "summary_path": str(summary_path),
        }

    monkeypatch.setattr(benchmark, "run_official_benchmark", fake_run_official_benchmark)

    batch = benchmark.run_benchmark_manifest(
        manifest,
        timeout=30,
        hydrus_launch_mode="argv",
    )

    assert calls == [
        (source_root / "SUPPORTED", "SUPPORTED", 30, "argv"),
    ]
    assert batch["ok"] is True
    assert batch["counts"] == {
        "pass": 1,
        "partial": 0,
        "fail": 0,
        "skipped": 2,
    }
    rows = {row["case_id"]: row for row in batch["cases"]}
    assert rows["SUPPORTED"]["status"] == "pass"
    assert rows["SUPPORTED"]["parsed_outputs_count"] == 2
    assert rows["SUPPORTED"]["figure_count"] == 1
    assert rows["PARTIAL_CASE"]["status"] == "skipped"
    assert rows["PARTIAL_CASE"]["failure_classification"] == "partial_not_in_scope"
    assert "supported_now=partial" in rows["PARTIAL_CASE"]["notes"]
    assert rows["UNSUPPORTED"]["status"] == "skipped"
    assert rows["UNSUPPORTED"]["failure_classification"] == "unsupported_official_example"
    assert (results_root / "benchmark_batch_summary.csv").is_file()
    assert (results_root / "benchmark_batch_summary.json").is_file()

    on_disk = json.loads(
        (results_root / "benchmark_batch_summary.json").read_text(encoding="utf-8")
    )
    assert on_disk["counts"]["skipped"] == 2


def test_run_benchmark_manifest_marks_supported_qc_warnings_as_partial(
    tmp_path: Path, monkeypatch,
):
    results_root = tmp_path / "benchmark_results"
    monkeypatch.setattr(benchmark, "BENCHMARK_RESULTS_ROOT", results_root)

    source = tmp_path / "pc_progress_raw" / "Direct" / "QC_WARN"
    source.mkdir(parents=True)
    (source / "Selector.in").write_text("selector", encoding="utf-8")
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "case_id,process_type,source_dir,supported_now,notes\n"
        f"QC_WARN,water_flow,{source},yes,ready\n",
        encoding="utf-8",
    )

    def fake_run_official_benchmark(source_dir, benchmark_id, *, timeout, hydrus_launch_mode):
        summary_path = results_root / benchmark_id / "benchmark_summary.json"
        summary_path.parent.mkdir(parents=True)
        summary_path.write_text("{}", encoding="utf-8")
        return {
            "ok": False,
            "benchmark_id": benchmark_id,
            "source_dir": str(source_dir),
            "run": {"success": True},
            "outputs": {
                "Balance.out": {"empty": False},
                "Obs_Node.out": {"empty": True},
            },
            "qc": {"ok": False, "warnings": ["missing observation figures"]},
            "figures": [],
            "summary_path": str(summary_path),
        }

    monkeypatch.setattr(benchmark, "run_official_benchmark", fake_run_official_benchmark)

    batch = benchmark.run_benchmark_manifest(manifest)

    row = batch["cases"][0]
    assert batch["ok"] is False
    assert row["status"] == "partial"
    assert row["hydrus_success"] is True
    assert row["qc_ok"] is False
    assert row["warning_count"] == 1
    assert row["parsed_outputs_count"] == 1
    assert row["failure_classification"] == "QC warning only"


def test_sync_benchmark_manifest_adds_discovered_folders_and_preserves_notes(
    tmp_path: Path,
):
    source_root = tmp_path / "pc_progress_raw" / "Direct"
    for case_id in ["EXISTING", "ROOTUPTK"]:
        source = source_root / case_id
        source.mkdir(parents=True)
        (source / "Selector.in").write_text("selector", encoding="utf-8")

    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "case_id,process_type,source_dir,supported_now,description,notes\n"
        f"EXISTING,water_flow,{source_root / 'EXISTING'},yes,"
        "Manual description,Keep this manual note\n",
        encoding="utf-8",
    )

    rows = benchmark.sync_benchmark_manifest_with_directories(
        manifest,
        examples_root=source_root,
    )

    by_case = {row["case_id"]: row for row in rows}
    assert sorted(by_case) == ["EXISTING", "ROOTUPTK"]
    assert by_case["EXISTING"]["description"] == "Manual description"
    assert by_case["EXISTING"]["notes"] == "Keep this manual note"
    assert by_case["ROOTUPTK"]["process_type"] == "root_uptake"
    assert by_case["ROOTUPTK"]["supported_now"] == "no"
    assert "root uptake" in by_case["ROOTUPTK"]["notes"].lower()

    on_disk = {
        row["case_id"]: row
        for row in benchmark._read_manifest_rows(manifest)
    }
    assert sorted(on_disk) == ["EXISTING", "ROOTUPTK"]


def test_run_full_example_sweep_runs_all_cases_and_writes_reports(
    tmp_path: Path, monkeypatch,
):
    results_root = tmp_path / "benchmark_results"
    monkeypatch.setattr(benchmark, "BENCHMARK_RESULTS_ROOT", results_root)

    source_root = tmp_path / "pc_progress_raw" / "Direct"
    for case_id in ["WATER_OK", "ROOT_CASE", "SOLUTE_CASE", "HEAT_CASE"]:
        source = source_root / case_id
        source.mkdir(parents=True)
        (source / "Selector.in").write_text("selector", encoding="utf-8")
        (source / "DESCRIPT.TXT").write_text(case_id, encoding="utf-8")

    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "case_id,process_type,source_dir,supported_now,description,notes\n"
        f"WATER_OK,water_flow,{source_root / 'WATER_OK'},yes,Water case,baseline\n"
        f"ROOT_CASE,root_uptake,{source_root / 'ROOT_CASE'},partial,Root uptake case,"
        "simple root uptake note\n"
        f"SOLUTE_CASE,solute,{source_root / 'SOLUTE_CASE'},partial,Solute case,"
        "manual solute note\n",
        encoding="utf-8",
    )
    report = tmp_path / "docs" / "full_example_sweep_report.md"

    calls = []

    def fake_run_official_benchmark(source_dir, benchmark_id, *, timeout, hydrus_launch_mode):
        calls.append((benchmark_id, Path(source_dir), timeout, hydrus_launch_mode))
        summary_path = results_root / benchmark_id / "benchmark_summary.json"
        summary_path.parent.mkdir(parents=True)
        summary_path.write_text("{}", encoding="utf-8")
        if benchmark_id == "WATER_OK":
            return {
                "ok": True,
                "benchmark_id": benchmark_id,
                "source_dir": str(source_dir),
                "run": {"success": True, "return_code": 0},
                "outputs": {
                    "Balance.out": {"empty": False},
                    "Obs_Node.out": {"empty": False},
                },
                "qc": {"ok": True, "warnings": []},
                "figures": ["one.png", "two.png"],
                "summary_path": str(summary_path),
            }
        if benchmark_id == "SOLUTE_CASE":
            return {
                "ok": False,
                "benchmark_id": benchmark_id,
                "source_dir": str(source_dir),
                "run": {"success": True, "return_code": 0},
                "outputs": {"Balance.out": {"empty": False}},
                "qc": {"ok": False, "warnings": ["solute warning"]},
                "figures": ["one.png"],
                "summary_path": str(summary_path),
            }
        if benchmark_id == "ROOT_CASE":
            return {
                "ok": True,
                "benchmark_id": benchmark_id,
                "source_dir": str(source_dir),
                "run": {"success": True, "return_code": 0},
                "outputs": {
                    "Balance.out": {"empty": False},
                    "Obs_Node.out": {"empty": False},
                    "T_Level.out": {"empty": False},
                },
                "qc": {"ok": True, "warnings": []},
                "figures": ["one.png", "two.png", "three.png"],
                "summary_path": str(summary_path),
            }
        return {
            "ok": False,
            "benchmark_id": benchmark_id,
            "source_dir": str(source_dir),
            "run": {"success": False, "return_code": 7, "error": "cannot open Selector.in"},
            "outputs": {},
            "qc": {"ok": False, "warnings": []},
            "figures": [],
            "summary_path": str(summary_path),
        }

    monkeypatch.setattr(benchmark, "run_official_benchmark", fake_run_official_benchmark)

    sweep = benchmark.run_full_example_sweep(
        manifest,
        examples_root=source_root,
        timeout=60,
        hydrus_launch_mode="argv",
        report_path=report,
    )

    assert [call[0] for call in calls] == [
        "HEAT_CASE",
        "ROOT_CASE",
        "SOLUTE_CASE",
        "WATER_OK",
    ]
    assert all(call[2:] == (60, "argv") for call in calls)
    assert sweep["counts"]["pass"] == 2
    assert sweep["counts"]["partial"] == 1
    assert sweep["counts"]["fail"] == 1
    assert sweep["counts"]["skipped"] == 0
    assert sweep["counts"]["future"] == 0

    rows = {row["case_id"]: row for row in sweep["cases"]}
    assert rows["WATER_OK"]["status"] == "pass"
    assert rows["WATER_OK"]["failure_classification"] == "water_flow_supported"
    assert rows["ROOT_CASE"]["status"] == "pass"
    assert rows["ROOT_CASE"]["failure_classification"] == "root_uptake_supported"
    assert rows["SOLUTE_CASE"]["status"] == "partial"
    assert rows["SOLUTE_CASE"]["failure_classification"] == "solute_transport_gap"
    assert rows["HEAT_CASE"]["status"] == "fail"
    assert rows["HEAT_CASE"]["failure_classification"] == "runner_or_launch_failure"
    assert rows["HEAT_CASE"]["raw_folder_unchanged"] is True
    assert (results_root / "full_example_sweep_summary.csv").is_file()
    assert (results_root / "full_example_sweep_summary.json").is_file()
    assert report.is_file()
    text = report.read_text(encoding="utf-8")
    assert "# Full Official Example Sweep Report" in text
    assert "Total examples found: 4" in text
    assert "root_uptake_supported" in text
    assert "solute_transport_gap" in text
    assert "WATER_OK" in text


def test_full_sweep_classifies_time_variable_bc_error_as_input_timing():
    summary = {
        "run": {
            "success": False,
            "return_code": 0,
            "stdout_preview": (
                "The first time-variable BC record is at time smaller than "
                "tInit+dtInit ! You may want to lower the initial time step."
            ),
            "error": "",
            "false_success_reason": "press enter to continue without successful completion",
        },
        "outputs": {},
        "qc": {"ok": False, "warnings": []},
        "figures": [],
        "summary_path": "benchmark_summary.json",
    }
    row = {
        "case_id": "2NOHYSTR",
        "process_type": "atmospheric_field_profile",
        "supported_now": "partial",
        "description": "Transient flow involving hysteresis",
        "notes": "diagnostic case",
    }

    result = benchmark._full_sweep_row_from_summary(
        summary,
        manifest_row=row,
        source_folder=Path("raw/2NOHYSTR"),
        timeout=60,
    )

    assert result["status"] == "fail"
    assert result["failure_classification"] == "input_timing_compatibility"


def test_generate_benchmark_gap_report_summarises_manifest_and_batch(tmp_path: Path):
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "case_id,process_type,source_dir,supported_now,description,notes\n"
        "WATER_OK,water_flow,raw/WATER_OK,yes,water flow,baseline\n"
        "WATER_FAIL,water_flow,raw/WATER_FAIL,yes,water flow,reader warning\n"
        "SOLUTE_PARTIAL,solute,raw/SOLUTE_PARTIAL,partial,solute transport,"
        "needs solute output reader extension\n"
        "ATM_ROOT,atmospheric,raw/ATM_ROOT,no,atmospheric boundary,"
        "ATMOSPH.IN with root uptake\n"
        "HEAT_CASE,heat,raw/HEAT_CASE,no,heat transport,temperature output\n"
        "DUAL_SCALE,dual_permeability,raw/DUAL_SCALE,no,dual permeability,"
        "dual porosity with scaling factors\n",
        encoding="utf-8",
    )
    batch = tmp_path / "benchmark_batch_summary.csv"
    batch.write_text(
        "case_id,process_type,source_folder,status,hydrus_success,"
        "parsed_outputs_count,qc_ok,warning_count,figure_count,"
        "benchmark_summary_path,failure_classification,notes\n"
        "WATER_OK,water_flow,raw/WATER_OK,pass,True,5,True,0,9,"
        "results/WATER_OK/benchmark_summary.json,,baseline\n"
        "WATER_FAIL,water_flow,raw/WATER_FAIL,fail,False,0,False,1,0,"
        "results/WATER_FAIL/benchmark_summary.json,output_reader limitation,"
        "reader warning\n"
        "SOLUTE_PARTIAL,solute,raw/SOLUTE_PARTIAL,skipped,,0,,0,0,,"
        "partial_not_in_scope,supported_now=partial; needs solute output reader extension\n",
        encoding="utf-8",
    )
    report = tmp_path / "benchmark_gap_report.md"

    result = benchmark.generate_benchmark_gap_report(manifest, batch, report)

    assert result == report
    text = report.read_text(encoding="utf-8")
    assert "# HYDRUS-1D Benchmark Gap Analysis" in text
    assert "- Examples in manifest: 6" in text
    assert "| supported_now=yes | 2 |" in text
    assert "| partial | 1 |" in text
    assert "| no | 3 |" in text
    assert "| run | 2 |" in text
    assert "| passed | 1 |" in text
    assert "| failed | 1 |" in text
    assert "| skipped | 1 |" in text
    assert "| WATER_OK | water_flow |" in text
    assert "| WATER_FAIL | water_flow | fail | output_reader limitation |" in text
    assert "| SOLUTE_PARTIAL | solute | partial_not_in_scope |" in text
    assert "dual_permeability" in text
    assert "atmospheric boundary / ATMOSPH.IN" in text
    assert "root uptake" in text
    assert "solute transport" in text
    assert "heat transport" in text
    assert "dual porosity / dual permeability" in text
    assert "scaling factors" in text
    assert "output reader extension" in text
