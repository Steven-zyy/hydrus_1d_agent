"""Benchmark harness for official HYDRUS-1D example projects.

The harness never runs in-place inside the raw PC-Progress examples. Each
benchmark first copies the selected example folder to
``benchmarks/benchmark_results/<benchmark_id>/hydrus_project/`` and all
runner side effects happen inside that copied project.
"""

from __future__ import annotations

import csv
import datetime as _dt
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Union

from hydrus_agent.env import resolve_hydrus_exe
from hydrus_agent.runner import RunnerError, run_hydrus_project


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS_ROOT = PROJECT_ROOT / "benchmarks"
BENCHMARK_RESULTS_ROOT = BENCHMARKS_ROOT / "benchmark_results"
BENCHMARK_SUMMARY_FILENAME = "benchmark_summary.json"
BATCH_SUMMARY_CSV_FILENAME = "benchmark_batch_summary.csv"
BATCH_SUMMARY_JSON_FILENAME = "benchmark_batch_summary.json"
GAP_REPORT_FILENAME = "benchmark_gap_report.md"
DEFAULT_OFFICIAL_EXAMPLES_ROOT = BENCHMARKS_ROOT / "pc_progress_raw" / "Direct"
FULL_SWEEP_SUMMARY_CSV_FILENAME = "full_example_sweep_summary.csv"
FULL_SWEEP_SUMMARY_JSON_FILENAME = "full_example_sweep_summary.json"
FULL_SWEEP_REPORT_FILENAME = "full_example_sweep_report.md"
MANIFEST_COLUMNS = [
    "case_id",
    "process_type",
    "source_dir",
    "supported_now",
    "description",
    "notes",
]
BATCH_SUMMARY_COLUMNS = [
    "case_id",
    "process_type",
    "source_folder",
    "status",
    "hydrus_success",
    "parsed_outputs_count",
    "qc_ok",
    "warning_count",
    "figure_count",
    "benchmark_summary_path",
    "failure_classification",
    "notes",
]
FULL_SWEEP_COLUMNS = [
    "case_id",
    "source_folder",
    "process_type",
    "supported_now",
    "status",
    "hydrus_success",
    "return_code",
    "timeout",
    "timed_out",
    "parsed_outputs_count",
    "qc_status",
    "qc_ok",
    "warning_count",
    "figure_count",
    "failure_classification",
    "raw_folder_unchanged",
    "benchmark_summary_path",
    "description",
    "notes",
]
GAP_PRIORITY_LABELS = [
    "atmospheric boundary / ATMOSPH.IN",
    "root uptake",
    "solute transport",
    "heat transport",
    "hysteresis",
    "dual porosity / dual permeability",
    "scaling factors",
    "output reader extension",
]
FULL_SWEEP_FAILURE_CATEGORIES = [
    "water_flow_supported",
    "atmospheric_supported",
    "root_uptake_supported",
    "root_uptake_gap",
    "solute_transport_gap",
    "heat_transport_gap",
    "hysteresis_gap",
    "dual_porosity_gap",
    "scaling_factor_gap",
    "output_reader_gap",
    "runner_or_launch_failure",
    "missing_or_corrupt_input",
    "input_timing_compatibility",
    "timeout",
    "qc_warning_only",
    "unknown",
]


def _validate_benchmark_id(benchmark_id: str) -> str:
    benchmark_id = str(benchmark_id).strip()
    if not benchmark_id:
        raise ValueError("benchmark_id must not be empty.")
    if benchmark_id in {".", ".."}:
        raise ValueError(f"benchmark_id must be a simple folder name: {benchmark_id!r}")
    if os.sep in benchmark_id or (os.altsep and os.altsep in benchmark_id):
        raise ValueError(f"benchmark_id must be a simple folder name: {benchmark_id!r}")
    return benchmark_id


def _benchmark_run_dir(benchmark_id: str) -> Path:
    benchmark_id = _validate_benchmark_id(benchmark_id)
    return BENCHMARK_RESULTS_ROOT / benchmark_id


def _safe_remove_run_dir(run_dir: Path) -> None:
    root = BENCHMARK_RESULTS_ROOT.resolve()
    target = run_dir.resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Refusing to remove path outside benchmark results: {target}") from exc
    if target == root:
        raise ValueError(f"Refusing to remove benchmark results root: {target}")
    if target.exists():
        shutil.rmtree(target)


def copy_official_example(source_dir: Union[str, Path], benchmark_id: str) -> Path:
    """Copy an official example folder into an isolated benchmark run folder.

    Parameters
    ----------
    source_dir
        Official PC-Progress example directory. It is only read.
    benchmark_id
        Simple folder name used below ``benchmarks/benchmark_results``.

    Returns
    -------
    Path
        The copied HYDRUS project directory:
        ``benchmarks/benchmark_results/<benchmark_id>/hydrus_project``.
    """
    source = Path(source_dir)
    if not source.is_dir():
        raise FileNotFoundError(f"Official example directory does not exist: {source}")

    run_dir = _benchmark_run_dir(benchmark_id)
    project_dir = run_dir / "hydrus_project"

    _safe_remove_run_dir(run_dir)
    project_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, project_dir)
    return project_dir


def run_official_benchmark(
    source_dir: Union[str, Path],
    benchmark_id: str,
    timeout: Optional[float] = 60,
    hydrus_launch_mode: str = "argv",
) -> Dict[str, Any]:
    """Run a copied official HYDRUS example and write a JSON summary."""
    source = Path(source_dir)
    started_at = _dt.datetime.now().isoformat(timespec="seconds")
    benchmark_id = _validate_benchmark_id(benchmark_id)
    run_dir = _benchmark_run_dir(benchmark_id)
    summary_path = run_dir / BENCHMARK_SUMMARY_FILENAME

    summary: Dict[str, Any] = {
        "benchmark_id": benchmark_id,
        "source_dir": str(source),
        "run_dir": str(run_dir),
        "project_dir": None,
        "started_at": started_at,
        "finished_at": None,
        "timeout": timeout,
        "hydrus_launch_mode": hydrus_launch_mode,
        "ok": False,
        "stopped_after_step": None,
        "copy": {"success": False},
        "run": {"success": False},
        "outputs": {},
        "figures": [],
        "qc": {},
        "summary_path": str(summary_path),
    }

    try:
        project_dir = copy_official_example(source, benchmark_id)
    except Exception as exc:
        summary["copy"] = {"success": False, "error": str(exc)}
        summary["stopped_after_step"] = "copy_official_example"
        return _finish_summary(summary, summary_path)

    summary["project_dir"] = str(project_dir)
    summary["copy"] = {"success": True, "project_dir": str(project_dir)}

    exe_str, source_name = resolve_hydrus_exe()
    if exe_str is None:
        summary["run"] = {
            "success": False,
            "error": f"HYDRUS_EXE is not set (source: {source_name}).",
        }
        summary["stopped_after_step"] = "run_hydrus"
        return _finish_summary(summary, summary_path)
    exe_path = Path(exe_str)
    if not exe_path.is_file():
        summary["run"] = {
            "success": False,
            "error": f"HYDRUS executable not found at {exe_path}.",
        }
        summary["stopped_after_step"] = "run_hydrus"
        return _finish_summary(summary, summary_path)

    try:
        result = run_hydrus_project(
            project_dir,
            exe_path,
            run_dir / "logs",
            timeout=timeout,
            launch_mode=hydrus_launch_mode,
        )
    except RunnerError as exc:
        summary["run"] = {"success": False, "error": str(exc)}
        summary["stopped_after_step"] = "run_hydrus"
        return _finish_summary(summary, summary_path)

    summary["run"] = {
        "success": bool(result.success),
        "return_code": result.return_code,
        "log_path": str(result.log_path),
        "cmd": list(result.cmd),
        "generated_files": [str(p) for p in result.generated_files],
        "launch_mode": result.launch_mode,
        "false_success_reason": result.false_success_reason,
        "stdout_preview": (result.stdout or "")[:2000],
        "stderr_preview": (result.stderr or "")[:2000],
    }

    outputs = _read_outputs(project_dir)
    summary["outputs"] = _summarise_output_tables(outputs)

    figures = _generate_plots(outputs, run_dir / "figures")
    summary["figures"] = [str(p) for p in figures]

    qc_summary = _run_qc(outputs, figures, run_dir / "outputs" / "qc_summary.json")
    summary["qc"] = qc_summary

    if result.false_success_reason:
        summary["stopped_after_step"] = "run_hydrus"
    elif not result.success:
        summary["stopped_after_step"] = "run_hydrus"
    summary["ok"] = bool(result.success and qc_summary.get("ok", False))
    return _finish_summary(summary, summary_path)


def run_benchmark_manifest(
    manifest_path: Path,
    *,
    timeout: float = 60,
    hydrus_launch_mode: str = "argv",
    only_supported: bool = True,
) -> Dict[str, Any]:
    """Run or skip official examples listed in a benchmark manifest.

    By default, only rows marked ``supported_now=yes`` are run. Rows marked
    ``partial`` or ``no`` are recorded as skipped so the batch report explains
    what was intentionally left out.
    """
    manifest = Path(manifest_path)
    if not manifest.is_file():
        raise FileNotFoundError(f"Benchmark manifest does not exist: {manifest}")

    started_at = _dt.datetime.now().isoformat(timespec="seconds")
    rows = _read_manifest_rows(manifest)
    case_results: list[Dict[str, Any]] = []

    for row in rows:
        case_id = _manifest_case_id(row)
        source_folder = _resolve_manifest_source(manifest, row.get("source_dir", ""))
        process_type = row.get("process_type", "")
        supported_now = row.get("supported_now", "")
        notes = row.get("notes", "")

        skip_reason = _manifest_skip_reason(supported_now, only_supported=only_supported)
        if skip_reason is not None:
            case_results.append(
                _skipped_batch_row(
                    case_id=case_id,
                    process_type=process_type,
                    source_folder=source_folder,
                    supported_now=supported_now,
                    notes=notes,
                    failure_classification=skip_reason,
                )
            )
            continue

        try:
            summary = run_official_benchmark(
                source_folder,
                case_id,
                timeout=timeout,
                hydrus_launch_mode=hydrus_launch_mode,
            )
            case_results.append(
                _batch_row_from_official_summary(
                    summary,
                    case_id=case_id,
                    process_type=process_type,
                    source_folder=source_folder,
                    notes=notes,
                )
            )
        except Exception as exc:
            case_results.append(
                {
                    "case_id": case_id,
                    "process_type": process_type,
                    "source_folder": str(source_folder),
                    "status": "fail",
                    "hydrus_success": False,
                    "parsed_outputs_count": 0,
                    "qc_ok": False,
                    "warning_count": 0,
                    "figure_count": 0,
                    "benchmark_summary_path": "",
                    "failure_classification": "unknown",
                    "notes": f"{notes}; batch runner error: {exc}".strip("; "),
                }
            )

    counts = {status: 0 for status in ["pass", "partial", "fail", "skipped"]}
    for case in case_results:
        counts[case["status"]] += 1

    summary_csv = BENCHMARK_RESULTS_ROOT / BATCH_SUMMARY_CSV_FILENAME
    summary_json = BENCHMARK_RESULTS_ROOT / BATCH_SUMMARY_JSON_FILENAME
    batch_summary: Dict[str, Any] = {
        "ok": counts["fail"] == 0 and counts["partial"] == 0,
        "manifest_path": str(manifest),
        "started_at": started_at,
        "finished_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "timeout": timeout,
        "hydrus_launch_mode": hydrus_launch_mode,
        "only_supported": only_supported,
        "counts": counts,
        "cases": case_results,
        "summary_csv_path": str(summary_csv),
        "summary_json_path": str(summary_json),
    }

    _write_batch_summary_csv(case_results, summary_csv)
    summary_json.parent.mkdir(parents=True, exist_ok=True)
    summary_json.write_text(
        json.dumps(batch_summary, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return batch_summary


def sync_benchmark_manifest_with_directories(
    manifest_path: Path,
    *,
    examples_root: Path | None = None,
) -> list[Dict[str, str]]:
    """Ensure every official example folder is represented in the manifest.

    Existing rows are preserved, including manual process classifications and
    notes. Missing folders are added with a conservative inferred
    classification so the full sweep can run every discovered example while
    still making future-scope gaps visible.
    """
    manifest = Path(manifest_path)
    root = Path(examples_root) if examples_root is not None else DEFAULT_OFFICIAL_EXAMPLES_ROOT
    if not root.is_dir():
        raise FileNotFoundError(f"Official examples root does not exist: {root}")

    existing_rows = _read_manifest_rows(manifest) if manifest.is_file() else []
    by_case = {row.get("case_id", ""): dict(row) for row in existing_rows}

    for source in sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name.lower()):
        case_id = source.name
        if case_id in by_case:
            row = by_case[case_id]
            row.setdefault("source_dir", _format_manifest_source_dir(source))
            if not row.get("source_dir"):
                row["source_dir"] = _format_manifest_source_dir(source)
            continue
        by_case[case_id] = _infer_manifest_row(case_id, source)

    rows = [by_case[key] for key in sorted(by_case, key=lambda value: value.lower())]
    _write_manifest_rows(manifest, rows)
    return rows


def run_full_example_sweep(
    manifest_path: Path,
    *,
    examples_root: Path | None = None,
    timeout: float = 60,
    hydrus_launch_mode: str = "argv",
    report_path: Path | None = None,
) -> Dict[str, Any]:
    """Run every official example listed/discovered for a full support sweep."""
    manifest = Path(manifest_path)
    root = Path(examples_root) if examples_root is not None else DEFAULT_OFFICIAL_EXAMPLES_ROOT
    rows = sync_benchmark_manifest_with_directories(manifest, examples_root=root)
    started_at = _dt.datetime.now().isoformat(timespec="seconds")
    case_results: list[Dict[str, Any]] = []

    for row in rows:
        case_id = _manifest_case_id(row)
        source_folder = _resolve_manifest_source(manifest, row.get("source_dir", ""))
        before = _snapshot_directory(source_folder)
        try:
            summary = run_official_benchmark(
                source_folder,
                case_id,
                timeout=timeout,
                hydrus_launch_mode=hydrus_launch_mode,
            )
            result_row = _full_sweep_row_from_summary(
                summary,
                manifest_row=row,
                source_folder=source_folder,
                timeout=timeout,
            )
        except Exception as exc:
            result_row = _full_sweep_error_row(
                manifest_row=row,
                source_folder=source_folder,
                timeout=timeout,
                error=exc,
            )
        after = _snapshot_directory(source_folder)
        result_row["raw_folder_unchanged"] = before == after
        case_results.append(result_row)

    counts = {status: 0 for status in ["pass", "partial", "fail", "skipped", "future"]}
    for case in case_results:
        counts[case["status"]] += 1

    summary_csv = BENCHMARK_RESULTS_ROOT / FULL_SWEEP_SUMMARY_CSV_FILENAME
    summary_json = BENCHMARK_RESULTS_ROOT / FULL_SWEEP_SUMMARY_JSON_FILENAME
    report = Path(report_path) if report_path is not None else PROJECT_ROOT / "docs" / FULL_SWEEP_REPORT_FILENAME
    sweep_summary: Dict[str, Any] = {
        "ok": counts["fail"] == 0,
        "manifest_path": str(manifest),
        "examples_root": str(root),
        "started_at": started_at,
        "finished_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "timeout": timeout,
        "hydrus_launch_mode": hydrus_launch_mode,
        "counts": counts,
        "cases": case_results,
        "summary_csv_path": str(summary_csv),
        "summary_json_path": str(summary_json),
        "report_path": str(report),
    }

    _write_full_sweep_summary_csv(case_results, summary_csv)
    summary_json.parent.mkdir(parents=True, exist_ok=True)
    summary_json.write_text(
        json.dumps(sweep_summary, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    _write_full_sweep_report(sweep_summary, report)
    return sweep_summary


def generate_benchmark_gap_report(
    manifest_path: Path,
    batch_summary_path: Path,
    output_path: Path,
) -> Path:
    """Write a Markdown gap analysis from the manifest and latest batch summary."""
    manifest = Path(manifest_path)
    batch_summary = Path(batch_summary_path)
    output = Path(output_path)
    if not manifest.is_file():
        raise FileNotFoundError(f"Benchmark manifest does not exist: {manifest}")
    if not batch_summary.is_file():
        raise FileNotFoundError(f"Benchmark batch summary does not exist: {batch_summary}")

    manifest_rows = _read_manifest_rows(manifest)
    batch_rows = _read_batch_summary_rows(batch_summary)
    batch_by_case = {row.get("case_id", ""): row for row in batch_rows}

    support_counts = _count_manifest_support(manifest_rows)
    run_counts = _count_batch_status(batch_rows)
    supported_passed = _supported_cases_with_status(
        manifest_rows, batch_by_case, statuses={"pass"}
    )
    supported_failed = _supported_cases_with_status(
        manifest_rows, batch_by_case, statuses={"fail", "partial"}
    )
    partial_skipped = _partial_cases_skipped(manifest_rows, batch_by_case)
    unsupported_by_process = _unsupported_by_process_type(manifest_rows)
    priorities = _recommend_gap_priorities(manifest_rows, batch_rows)

    lines = [
        "# HYDRUS-1D Benchmark Gap Analysis",
        "",
        f"- Manifest: `{manifest}`",
        f"- Batch summary: `{batch_summary}`",
        f"- Examples in manifest: {len(manifest_rows)}",
        "",
        "## Manifest Coverage",
        "",
        "| Category | Count |",
        "|---|---:|",
        f"| supported_now=yes | {support_counts['yes']} |",
        f"| partial | {support_counts['partial']} |",
        f"| no | {support_counts['no']} |",
        "",
        "## Latest Batch Results",
        "",
        "| Category | Count |",
        "|---|---:|",
        f"| run | {run_counts['run']} |",
        f"| passed | {run_counts['pass']} |",
        f"| failed | {run_counts['fail']} |",
        f"| partial | {run_counts['partial']} |",
        f"| skipped | {run_counts['skipped']} |",
        "",
        "## Supported Examples That Passed",
        "",
    ]
    lines.extend(_markdown_table(
        supported_passed,
        ["case_id", "process_type"],
        empty_line="No supported examples passed in the latest batch.",
    ))
    lines.extend([
        "",
        "## Supported Examples That Failed",
        "",
    ])
    lines.extend(_markdown_table(
        supported_failed,
        ["case_id", "process_type", "status", "failure_classification"],
        empty_line="No supported examples failed in the latest batch.",
    ))
    lines.extend([
        "",
        "## Partial Examples Skipped",
        "",
    ])
    lines.extend(_markdown_table(
        partial_skipped,
        ["case_id", "process_type", "failure_classification", "notes"],
        empty_line="No partial examples were skipped in the latest batch.",
    ))
    lines.extend([
        "",
        "## Unsupported Examples By Process Type",
        "",
    ])
    if unsupported_by_process:
        lines.extend(["| Process type | Examples |", "|---|---|"])
        for process_type in sorted(unsupported_by_process):
            case_ids = ", ".join(sorted(unsupported_by_process[process_type]))
            lines.append(f"| {process_type or '<blank>'} | {case_ids} |")
    else:
        lines.append("No unsupported examples are listed in the manifest.")
    lines.extend([
        "",
        "## Recommended Next Development Priorities",
        "",
    ])
    if priorities:
        for priority in priorities:
            lines.append(
                f"- {priority['gap']}: {priority['count']} case(s) - "
                f"{', '.join(priority['case_ids'])}"
            )
    else:
        lines.append("- No manifest gaps detected from current classifications.")
    lines.append("")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def _read_outputs(project_dir: Path):
    from hydrus_agent.output_reader import read_outputs

    return read_outputs(project_dir)


def _read_manifest_rows(manifest: Path) -> list[Dict[str, str]]:
    with manifest.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return []
        return [
            {str(k): (v or "").strip() for k, v in row.items() if k is not None}
            for row in reader
        ]


def _read_batch_summary_rows(batch_summary: Path) -> list[Dict[str, str]]:
    if batch_summary.suffix.lower() == ".json":
        data = json.loads(batch_summary.read_text(encoding="utf-8"))
        return [
            {str(k): "" if v is None else str(v) for k, v in row.items()}
            for row in data.get("cases", [])
        ]
    with batch_summary.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return []
        return [
            {str(k): (v or "").strip() for k, v in row.items() if k is not None}
            for row in reader
        ]


def _write_manifest_rows(manifest: Path, rows: list[Dict[str, str]]) -> None:
    manifest.parent.mkdir(parents=True, exist_ok=True)
    extra_columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in MANIFEST_COLUMNS and key not in extra_columns:
                extra_columns.append(key)
    fieldnames = [*MANIFEST_COLUMNS, *extra_columns]
    with manifest.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in fieldnames})


def _format_manifest_source_dir(source: Path) -> str:
    try:
        return str(source.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(source)


def _infer_manifest_row(case_id: str, source: Path) -> Dict[str, str]:
    process_type, supported_now, notes = _infer_process_support(case_id, source)
    return {
        "case_id": case_id,
        "process_type": process_type,
        "source_dir": _format_manifest_source_dir(source),
        "supported_now": supported_now,
        "description": f"Official PC-Progress example {case_id}",
        "notes": notes,
    }


def _infer_process_support(case_id: str, source: Path) -> tuple[str, str, str]:
    name = case_id.lower()
    file_names = {p.name.lower() for p in source.iterdir() if p.is_file()}
    text = " ".join([name, " ".join(file_names)])

    if "heat" in text or name.startswith("enbal"):
        return (
            "heat_transport",
            "no",
            "Auto-detected heat transport; future scope.",
        )
    if "hyster" in text or "hystr" in name and "nohystr" not in name:
        return (
            "hysteresis",
            "no",
            "Auto-detected hysteresis; future scope.",
        )
    if "scaling" in text or "scale" in text:
        return (
            "scaling_factor",
            "no",
            "Auto-detected scaling factors; future scope.",
        )
    if "root" in text or "uptk" in text:
        return (
            "root_uptake",
            "no",
            "Auto-detected root uptake; future scope.",
        )
    if "dual" in text or "porosity" in text or "permeability" in text:
        return (
            "dual_porosity",
            "no",
            "Auto-detected dual porosity/permeability; future scope.",
        )
    if "atmosph.in" in file_names or name in {"5season", "test2"}:
        return (
            "atmospheric_field_profile",
            "partial",
            "Auto-detected atmospheric boundary candidate; may include future-scope processes.",
        )
    if any(fn.startswith("solute") for fn in file_names) or name in {
        "test1", "test3", "test4", "test5", "test9", "test9a", "test10",
        "test11", "volatile", "3selim", "3laijuri",
    }:
        return (
            "solute",
            "partial",
            "Auto-detected solute-related output/input; solute generation is future scope.",
        )
    return (
        "water_flow",
        "yes",
        "Auto-detected water-flow candidate.",
    )


def _snapshot_directory(path: Path) -> Dict[str, tuple[int, int]] | None:
    if not path.is_dir():
        return None
    snapshot: Dict[str, tuple[int, int]] = {}
    for file_path in sorted((p for p in path.rglob("*") if p.is_file()), key=lambda p: str(p)):
        try:
            stat = file_path.stat()
        except OSError:
            continue
        rel = str(file_path.relative_to(path)).replace("\\", "/")
        snapshot[rel] = (int(stat.st_size), int(stat.st_mtime_ns))
    return snapshot


def _manifest_case_id(row: Dict[str, str]) -> str:
    case_id = row.get("case_id") or row.get("benchmark_id") or ""
    return _validate_benchmark_id(case_id)


def _resolve_manifest_source(manifest: Path, source_dir: str) -> Path:
    if not source_dir.strip():
        return Path(source_dir)
    source = Path(source_dir)
    if source.is_absolute():
        return source

    manifest_relative = (manifest.parent / source).resolve()
    if manifest_relative.exists():
        return manifest_relative
    return (PROJECT_ROOT / source).resolve()


def _manifest_skip_reason(
    supported_now: str,
    *,
    only_supported: bool,
) -> Optional[str]:
    marker = supported_now.strip().lower()
    if marker in {"partial", "partly", "maybe"}:
        return "partial_not_in_scope"
    if marker in {"no", "n", "false", "0", "unsupported"}:
        return "unsupported_official_example"
    if only_supported and marker not in {"yes", "y", "true", "1"}:
        return "not_marked_supported_now"
    return None


def _skipped_batch_row(
    *,
    case_id: str,
    process_type: str,
    source_folder: Path,
    supported_now: str,
    notes: str,
    failure_classification: str,
) -> Dict[str, Any]:
    prefix = f"supported_now={supported_now or '<blank>'}"
    merged_notes = f"{prefix}; {notes}".strip("; ")
    return {
        "case_id": case_id,
        "process_type": process_type,
        "source_folder": str(source_folder),
        "status": "skipped",
        "hydrus_success": None,
        "parsed_outputs_count": 0,
        "qc_ok": None,
        "warning_count": 0,
        "figure_count": 0,
        "benchmark_summary_path": "",
        "failure_classification": failure_classification,
        "notes": merged_notes,
    }


def _batch_row_from_official_summary(
    summary: Dict[str, Any],
    *,
    case_id: str,
    process_type: str,
    source_folder: Path,
    notes: str,
) -> Dict[str, Any]:
    outputs = summary.get("outputs") or {}
    qc = summary.get("qc") or {}
    run_info = summary.get("run") or {}

    hydrus_success = bool(run_info.get("success", False))
    parsed_outputs_count = _count_parsed_outputs(outputs)
    qc_ok = bool(qc.get("ok", False))
    warning_count = len(qc.get("warnings") or [])
    figure_count = len(summary.get("figures") or [])

    if hydrus_success and summary.get("ok"):
        status = "pass"
        failure_classification = ""
    elif hydrus_success and parsed_outputs_count > 0:
        status = "partial"
        failure_classification = _classify_partial_summary(qc_ok, warning_count)
    else:
        status = "fail"
        failure_classification = _classify_failed_summary(summary, parsed_outputs_count)

    return {
        "case_id": case_id,
        "process_type": process_type,
        "source_folder": str(source_folder),
        "status": status,
        "hydrus_success": hydrus_success,
        "parsed_outputs_count": parsed_outputs_count,
        "qc_ok": qc_ok,
        "warning_count": warning_count,
        "figure_count": figure_count,
        "benchmark_summary_path": summary.get("summary_path", ""),
        "failure_classification": failure_classification,
        "notes": notes,
    }


def _full_sweep_row_from_summary(
    summary: Dict[str, Any],
    *,
    manifest_row: Dict[str, str],
    source_folder: Path,
    timeout: float,
) -> Dict[str, Any]:
    outputs = summary.get("outputs") or {}
    qc = summary.get("qc") or {}
    run_info = summary.get("run") or {}
    hydrus_success = bool(run_info.get("success", False))
    return_code = run_info.get("return_code", "")
    parsed_outputs_count = _count_parsed_outputs(outputs)
    qc_ok = bool(qc.get("ok", False))
    warnings = qc.get("warnings") or []
    warning_count = len(warnings)
    figure_count = len(summary.get("figures") or [])
    timed_out = _summary_timed_out(summary)
    failure_classification = _classify_full_sweep_case(
        manifest_row=manifest_row,
        summary=summary,
        hydrus_success=hydrus_success,
        parsed_outputs_count=parsed_outputs_count,
        qc_ok=qc_ok,
        warning_count=warning_count,
        timed_out=timed_out,
    )
    status = _status_for_full_sweep_case(
        hydrus_success=hydrus_success,
        parsed_outputs_count=parsed_outputs_count,
        qc_ok=qc_ok,
        warning_count=warning_count,
        classification=failure_classification,
    )
    return {
        "case_id": _manifest_case_id(manifest_row),
        "source_folder": str(source_folder),
        "process_type": manifest_row.get("process_type", ""),
        "supported_now": manifest_row.get("supported_now", ""),
        "status": status,
        "hydrus_success": hydrus_success,
        "return_code": return_code,
        "timeout": timeout,
        "timed_out": timed_out,
        "parsed_outputs_count": parsed_outputs_count,
        "qc_status": "ok" if qc_ok else ("warning" if warning_count else "failed"),
        "qc_ok": qc_ok,
        "warning_count": warning_count,
        "figure_count": figure_count,
        "failure_classification": failure_classification,
        "raw_folder_unchanged": None,
        "benchmark_summary_path": summary.get("summary_path", ""),
        "description": manifest_row.get("description", ""),
        "notes": manifest_row.get("notes", ""),
    }


def _full_sweep_error_row(
    *,
    manifest_row: Dict[str, str],
    source_folder: Path,
    timeout: float,
    error: Exception,
) -> Dict[str, Any]:
    return {
        "case_id": _manifest_case_id(manifest_row),
        "source_folder": str(source_folder),
        "process_type": manifest_row.get("process_type", ""),
        "supported_now": manifest_row.get("supported_now", ""),
        "status": "fail",
        "hydrus_success": False,
        "return_code": "",
        "timeout": timeout,
        "timed_out": False,
        "parsed_outputs_count": 0,
        "qc_status": "failed",
        "qc_ok": False,
        "warning_count": 0,
        "figure_count": 0,
        "failure_classification": "unknown",
        "raw_folder_unchanged": None,
        "benchmark_summary_path": "",
        "description": manifest_row.get("description", ""),
        "notes": f"{manifest_row.get('notes', '')}; sweep error: {error}".strip("; "),
    }


def _summary_timed_out(summary: Dict[str, Any]) -> bool:
    run_info = summary.get("run") or {}
    text = " ".join([
        str(run_info.get("error", "")),
        str(run_info.get("stdout_preview", "")),
        str(run_info.get("stderr_preview", "")),
    ]).lower()
    return "timeout" in text or "timed out" in text


def _classify_full_sweep_case(
    *,
    manifest_row: Dict[str, str],
    summary: Dict[str, Any],
    hydrus_success: bool,
    parsed_outputs_count: int,
    qc_ok: bool,
    warning_count: int,
    timed_out: bool,
) -> str:
    if timed_out:
        return "timeout"

    if _summary_has_input_timing_error(summary):
        return "input_timing_compatibility"

    if not hydrus_success:
        failed = _classify_failed_summary(summary, parsed_outputs_count).lower()
        if "missing" in failed or "corrupt" in failed or "cannot open" in failed:
            return "missing_or_corrupt_input"
        return "runner_or_launch_failure"

    process_text = _gap_text(manifest_row)
    process_type = manifest_row.get("process_type", "").lower()
    if parsed_outputs_count == 0:
        return "output_reader_gap"
    if "hyster" in process_text:
        return "hysteresis_gap"
    if "dual" in process_text or "porosity" in process_text or "permeability" in process_text:
        return "dual_porosity_gap"
    if "scaling" in process_text or "scale" in process_text:
        return "scaling_factor_gap"
    if "root" in process_text or "uptk" in process_text:
        return "qc_warning_only" if warning_count or not qc_ok else "root_uptake_supported"
    if "solute" in process_text or process_type == "solute":
        return "solute_transport_gap"
    if "heat" in process_text or "temperature" in process_text:
        return "heat_transport_gap"
    if "atmos" in process_text:
        return "qc_warning_only" if warning_count or not qc_ok else "atmospheric_supported"
    if warning_count or not qc_ok:
        return "qc_warning_only"
    if process_type == "water_flow":
        return "water_flow_supported"
    return "unknown"


def _summary_has_input_timing_error(summary: Dict[str, Any]) -> bool:
    run_info = summary.get("run") or {}
    text = " ".join([
        str(run_info.get("error", "")),
        str(run_info.get("stdout_preview", "")),
        str(run_info.get("stderr_preview", "")),
        str(run_info.get("false_success_reason", "")),
    ]).lower()
    return (
        "first time-variable bc record" in text
        and "tinit+dtinit" in text
    )


def _status_for_full_sweep_case(
    *,
    hydrus_success: bool,
    parsed_outputs_count: int,
    qc_ok: bool,
    warning_count: int,
    classification: str,
) -> str:
    if not hydrus_success:
        return "fail"
    if parsed_outputs_count == 0:
        return "fail"
    if (
        classification in {
            "water_flow_supported",
            "atmospheric_supported",
            "root_uptake_supported",
        }
        and qc_ok
    ):
        return "pass"
    if classification.endswith("_gap") or warning_count or not qc_ok:
        return "partial"
    return "partial"


def _count_parsed_outputs(outputs: Dict[str, Dict[str, Any]]) -> int:
    return sum(1 for table in outputs.values() if not table.get("empty", True))


def _classify_partial_summary(qc_ok: bool, warning_count: int) -> str:
    if not qc_ok and warning_count > 0:
        return "QC warning only"
    return "unknown"


def _classify_failed_summary(
    summary: Dict[str, Any],
    parsed_outputs_count: int,
) -> str:
    copy_info = summary.get("copy") or {}
    run_info = summary.get("run") or {}
    false_success = str(run_info.get("false_success_reason") or "").lower()
    run_error = str(run_info.get("error") or "").lower()

    if copy_info and not copy_info.get("success", False):
        return "missing/corrupt official input files"
    if "does not exist or pathway is too long or corrupted" in false_success:
        return "missing/corrupt official input files"
    if "cannot open" in false_success:
        return "missing/corrupt official input files"
    if run_error or not run_info.get("success", False):
        return "HYDRUS executable / launch issue"
    if parsed_outputs_count == 0:
        return "output_reader limitation"
    return "unknown"


def _write_batch_summary_csv(rows: list[Dict[str, Any]], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=BATCH_SUMMARY_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in BATCH_SUMMARY_COLUMNS})


def _write_full_sweep_summary_csv(rows: list[Dict[str, Any]], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FULL_SWEEP_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in FULL_SWEEP_COLUMNS})


def _write_full_sweep_report(sweep_summary: Dict[str, Any], output_path: Path) -> Path:
    cases = sweep_summary.get("cases", [])
    counts = sweep_summary.get("counts", {})
    category_counts: Dict[str, int] = {}
    for case in cases:
        category = str(case.get("failure_classification", "") or "unknown")
        category_counts[category] = category_counts.get(category, 0) + 1

    regression_cases = [
        case for case in cases
        if case.get("status") == "pass"
        and case.get("failure_classification") in {
            "water_flow_supported",
            "atmospheric_supported",
            "root_uptake_supported",
        }
    ]
    future_cases = [
        case for case in cases
        if str(case.get("failure_classification", "")).endswith("_gap")
    ]

    lines = [
        "# Full Official Example Sweep Report",
        "",
        f"- Manifest: `{sweep_summary.get('manifest_path', '')}`",
        f"- Examples root: `{sweep_summary.get('examples_root', '')}`",
        f"- Timeout per example: {sweep_summary.get('timeout')} seconds",
        f"- HYDRUS launch mode: `{sweep_summary.get('hydrus_launch_mode')}`",
        f"- Total examples found: {len(cases)}",
        "",
        "## Status Counts",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status in ["pass", "partial", "fail", "skipped", "future"]:
        lines.append(f"| {status} | {counts.get(status, 0)} |")

    lines.extend([
        "",
        "## All Examples",
        "",
        "| case_id | process_type | supported_now | status | HYDRUS | return_code | parsed outputs | QC | warnings | figures | category | raw unchanged | summary |",
        "|---|---|---|---|---:|---:|---:|---|---:|---:|---|---:|---|",
    ])
    for case in cases:
        summary_path = case.get("benchmark_summary_path", "")
        summary_cell = f"`{summary_path}`" if summary_path else ""
        lines.append(
            "| "
            + " | ".join([
                _escape_markdown_table_value(str(case.get("case_id", ""))),
                _escape_markdown_table_value(str(case.get("process_type", ""))),
                _escape_markdown_table_value(str(case.get("supported_now", ""))),
                _escape_markdown_table_value(str(case.get("status", ""))),
                _escape_markdown_table_value(str(case.get("hydrus_success", ""))),
                _escape_markdown_table_value(str(case.get("return_code", ""))),
                _escape_markdown_table_value(str(case.get("parsed_outputs_count", ""))),
                _escape_markdown_table_value(str(case.get("qc_status", ""))),
                _escape_markdown_table_value(str(case.get("warning_count", ""))),
                _escape_markdown_table_value(str(case.get("figure_count", ""))),
                _escape_markdown_table_value(str(case.get("failure_classification", ""))),
                _escape_markdown_table_value(str(case.get("raw_folder_unchanged", ""))),
                _escape_markdown_table_value(summary_cell),
            ])
            + " |"
        )

    lines.extend([
        "",
        "## Top Failure And Gap Categories",
        "",
        "| Category | Count |",
        "|---|---:|",
    ])
    for category, count in sorted(category_counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| {category} | {count} |")

    lines.extend([
        "",
        "## Recommended Next Development Priorities",
        "",
    ])
    for category in [
        "root_uptake_gap",
        "solute_transport_gap",
        "heat_transport_gap",
        "hysteresis_gap",
        "dual_porosity_gap",
        "scaling_factor_gap",
        "output_reader_gap",
        "runner_or_launch_failure",
        "missing_or_corrupt_input",
        "input_timing_compatibility",
        "timeout",
    ]:
        count = category_counts.get(category, 0)
        if count:
            lines.append(f"- {category}: {count} case(s)")
    if not any(category_counts.get(category, 0) for category in FULL_SWEEP_FAILURE_CATEGORIES):
        lines.append("- No failure or gap categories detected.")

    lines.extend([
        "",
        "## Case Notes",
        "",
    ])
    timing_cases = [
        case for case in cases
        if case.get("failure_classification") == "input_timing_compatibility"
    ]
    if timing_cases:
        for case in timing_cases:
            lines.append(
                f"- {case.get('case_id')}: failed due to input timing "
                "compatibility, not runner failure. See "
                "`docs/2NOHYSTR_failure_diagnostic.md`."
            )
    else:
        lines.append("- No input timing compatibility failures were detected.")

    lines.extend([
        "",
        "## Good Regression Benchmarks",
        "",
    ])
    if regression_cases:
        for case in regression_cases:
            lines.append(
                f"- {case.get('case_id')}: {case.get('failure_classification')}, "
                f"{case.get('parsed_outputs_count')} parsed outputs, "
                f"{case.get('figure_count')} figures"
            )
    else:
        lines.append("- No pass-status regression benchmarks were identified.")

    lines.extend([
        "",
        "## Examples That Should Remain Future Scope",
        "",
    ])
    if future_cases:
        for case in future_cases:
            lines.append(
                f"- {case.get('case_id')}: {case.get('failure_classification')} "
                f"({case.get('process_type')})"
            )
    else:
        lines.append("- No future-scope examples were identified.")
    lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _support_marker(row: Dict[str, str]) -> str:
    marker = row.get("supported_now", "").strip().lower()
    if marker in {"yes", "y", "true", "1"}:
        return "yes"
    if marker in {"partial", "partly", "maybe"}:
        return "partial"
    if marker in {"no", "n", "false", "0", "unsupported"}:
        return "no"
    return "unknown"


def _count_manifest_support(rows: list[Dict[str, str]]) -> Dict[str, int]:
    counts = {"yes": 0, "partial": 0, "no": 0, "unknown": 0}
    for row in rows:
        counts[_support_marker(row)] += 1
    return counts


def _count_batch_status(rows: list[Dict[str, str]]) -> Dict[str, int]:
    counts = {"run": 0, "pass": 0, "fail": 0, "partial": 0, "skipped": 0}
    for row in rows:
        status = row.get("status", "").strip().lower()
        if status in {"pass", "fail", "partial", "skipped"}:
            counts[status] += 1
        if status and status != "skipped":
            counts["run"] += 1
    return counts


def _supported_cases_with_status(
    manifest_rows: list[Dict[str, str]],
    batch_by_case: Dict[str, Dict[str, str]],
    *,
    statuses: set[str],
) -> list[Dict[str, str]]:
    rows: list[Dict[str, str]] = []
    for manifest_row in manifest_rows:
        if _support_marker(manifest_row) != "yes":
            continue
        case_id = _manifest_case_id(manifest_row)
        batch_row = batch_by_case.get(case_id, {})
        status = batch_row.get("status", "").strip().lower()
        if status not in statuses:
            continue
        rows.append({
            "case_id": case_id,
            "process_type": manifest_row.get("process_type", ""),
            "status": status,
            "failure_classification": batch_row.get("failure_classification", ""),
        })
    return rows


def _partial_cases_skipped(
    manifest_rows: list[Dict[str, str]],
    batch_by_case: Dict[str, Dict[str, str]],
) -> list[Dict[str, str]]:
    rows: list[Dict[str, str]] = []
    for manifest_row in manifest_rows:
        if _support_marker(manifest_row) != "partial":
            continue
        case_id = _manifest_case_id(manifest_row)
        batch_row = batch_by_case.get(case_id, {})
        if batch_row.get("status", "").strip().lower() != "skipped":
            continue
        notes = batch_row.get("notes") or manifest_row.get("notes", "")
        rows.append({
            "case_id": case_id,
            "process_type": manifest_row.get("process_type", ""),
            "failure_classification": batch_row.get("failure_classification", ""),
            "notes": notes,
        })
    return rows


def _unsupported_by_process_type(
    manifest_rows: list[Dict[str, str]],
) -> Dict[str, list[str]]:
    grouped: Dict[str, list[str]] = {}
    for row in manifest_rows:
        if _support_marker(row) != "no":
            continue
        process_type = row.get("process_type", "")
        grouped.setdefault(process_type, []).append(_manifest_case_id(row))
    return grouped


def _recommend_gap_priorities(
    manifest_rows: list[Dict[str, str]],
    batch_rows: list[Dict[str, str]],
) -> list[Dict[str, Any]]:
    hits: Dict[str, set[str]] = {label: set() for label in GAP_PRIORITY_LABELS}
    for row in manifest_rows:
        marker = _support_marker(row)
        if marker == "yes":
            continue
        text = _gap_text(row)
        case_id = _manifest_case_id(row)
        for label in _priority_labels_for_text(text):
            hits[label].add(case_id)

    for row in batch_rows:
        text = _gap_text(row)
        case_id = row.get("case_id", "").strip()
        if not case_id:
            continue
        for label in _priority_labels_for_text(text):
            hits[label].add(case_id)

    priorities = []
    for label in GAP_PRIORITY_LABELS:
        case_ids = sorted(hits[label])
        if not case_ids:
            continue
        priorities.append({
            "gap": label,
            "count": len(case_ids),
            "case_ids": case_ids,
        })
    return priorities


def _gap_text(row: Dict[str, str]) -> str:
    fields = [
        row.get("case_id", ""),
        row.get("process_type", ""),
        row.get("description", ""),
        row.get("notes", ""),
        row.get("failure_classification", ""),
    ]
    return " ".join(fields).lower()


def _priority_labels_for_text(text: str) -> list[str]:
    labels: list[str] = []
    if "atmos" in text or "atmosph" in text:
        labels.append("atmospheric boundary / ATMOSPH.IN")
    if "root" in text:
        labels.append("root uptake")
    if "solute" in text or "transport" in text and "heat" not in text:
        labels.append("solute transport")
    if "heat" in text or "temperature" in text:
        labels.append("heat transport")
    if "hyster" in text:
        labels.append("hysteresis")
    if "dual" in text or "porosity" in text or "permeability" in text:
        labels.append("dual porosity / dual permeability")
    if "scaling" in text or "scale" in text:
        labels.append("scaling factors")
    if (
        "output_reader" in text
        or "output reader" in text
        or "parser" in text
        or "parsing" in text
        or "obs_node" in text
    ):
        labels.append("output reader extension")
    return labels


def _markdown_table(
    rows: list[Dict[str, str]],
    columns: list[str],
    *,
    empty_line: str,
) -> list[str]:
    if not rows:
        return [empty_line]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for row in rows:
        values = [_escape_markdown_table_value(str(row.get(column, ""))) for column in columns]
        lines.append("| " + " | ".join(values) + " |")
    return lines


def _escape_markdown_table_value(value: str) -> str:
    return value.replace("|", "\\|")


def _summarise_output_tables(outputs) -> Dict[str, Dict[str, Any]]:
    summary: Dict[str, Dict[str, Any]] = {}
    for name, df in outputs.items():
        rows = int(len(df)) if df is not None else 0
        columns = int(df.shape[1]) if df is not None and hasattr(df, "shape") else 0
        first_columns = list(df.columns[:6]) if df is not None and hasattr(df, "columns") else []
        summary[name] = {
            "rows": rows,
            "columns": columns,
            "empty": rows == 0,
            "first_columns": first_columns,
        }
    return summary


def _generate_plots(outputs, figure_dir: Path) -> list[Path]:
    try:
        from hydrus_agent.plotter import generate_standard_plots
        return generate_standard_plots(outputs, figure_dir)
    except Exception:
        return []


def _run_qc(outputs, figures, qc_path: Path) -> Dict[str, Any]:
    from hydrus_agent.qc import assess_run_quality, write_qc_summary

    qc_summary = assess_run_quality(outputs, figures=figures)
    write_qc_summary(qc_summary, qc_path)
    return qc_summary


def _finish_summary(summary: Dict[str, Any], summary_path: Path) -> Dict[str, Any]:
    summary["finished_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return summary
