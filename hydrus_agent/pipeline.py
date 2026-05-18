"""End-to-end HYDRUS-1D workflow orchestration (milestone 7).

A single ``run_full_pipeline()`` runs the eight pipeline steps in order:

    1. load_and_validate_config
    2. create_run_folder
    3. prepare_input          (phydrus adapter)
    4. run_hydrus             (subprocess; uses HYDRUS_EXE)
    5. read_outputs
    6. generate_plots
    7. run_qc
    8. generate_report

Each step records a structured ``StepResult``. The pipeline writes a
JSON-serialised summary to ``runs/<case_id>/pipeline_summary.json``.

Stopping rules:
    * Steps 1-4 are "hard": failure stops the pipeline.
    * Steps 5-8 are "soft": failures (or empty data) are recorded as
      warnings but do not abort subsequent steps.

This module does **not** implement automatic retry, correction, or any
natural-language interface. It is purely deterministic orchestration.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = PROJECT_ROOT / "runs"

PIPELINE_SUMMARY_FILENAME = "pipeline_summary.json"

NUMERICAL_FAILURE_PATTERNS = (
    r"non[-\s]?converged",
    r"non\s+convergence",
    r"did\s+not\s+converge",
    r"stopped\s+after",
    r"10\s+consecutive\s+non[-\s]?converged\s+steps",
    r"convergence\s+not\s+reached",
    r"\berror\b",
    r"\bfail(?:ed|ure)?\b",
)


@dataclass
class StepResult:
    """Outcome of one pipeline step."""

    step: str
    ok: bool
    outputs: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None


# Soft steps continue on failure; hard steps stop the pipeline.
HARD_STEPS = {
    "load_and_validate_config",
    "create_run_folder",
    "prepare_input",
    "run_hydrus",
}


# --- Public entry point ---------------------------------------------------


def run_full_pipeline(
    config_path: Union[str, Path],
    *,
    overwrite_run: bool = False,
    timeout: Optional[float] = None,
    hydrus_launch_mode: str = "argv",
    field_data_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Run the full HYDRUS pipeline and return a structured summary dict.

    Parameters
    ----------
    config_path
        Path to a model config JSON.
    overwrite_run
        Allow re-using an existing run folder in place.
    timeout
        Wall-clock seconds before HYDRUS is killed (passed to runner).
    hydrus_launch_mode
        ``"argv"`` (default) or ``"level-dir"``.

    Returns
    -------
    dict
        Pipeline summary with keys: ``config_path``, ``case_id``,
        ``run_dir``, ``started_at``, ``finished_at``, ``ok``,
        ``stopped_after_step``, ``steps`` (list of step dicts).
        Also written to ``<run_dir>/pipeline_summary.json`` when the
        run folder exists.
    """
    started_at = _dt.datetime.now().isoformat(timespec="seconds")

    summary: Dict[str, Any] = {
        "config_path": str(Path(config_path)),
        "case_id": None,
        "run_dir": None,
        "started_at": started_at,
        "finished_at": None,
        "ok": True,
        "stopped_after_step": None,
        "steps": [],
    }

    def _finalize(
        stopped_after: Optional[str] = None,
        run_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Write pipeline_summary.json (via _finish), then best-effort manifest
        and scientific_review.json. Neither side artefact mutates the summary
        or affects ``overall_status``."""
        result = _finish(summary, stopped_after=stopped_after, run_dir=run_dir)
        if run_dir is not None and Path(run_dir).is_dir():
            try:
                from hydrus_agent.run_manifest import (
                    write_run_manifest_for_pipeline,
                )
                write_run_manifest_for_pipeline(
                    summary=result,
                    run_dir=Path(run_dir),
                    config_path=Path(config_path),
                    hydrus_launch_mode=hydrus_launch_mode,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to write run_manifest.json: %s", exc)

            try:
                from hydrus_agent import load_config as _load_config
                from hydrus_agent.scientific_reviewer import (
                    result_to_dict,
                    review_config,
                )
                _cfg = _load_config(config_path)
                _sr = review_config(_cfg)
                (Path(run_dir) / "scientific_review.json").write_text(
                    json.dumps(result_to_dict(_sr), indent=2, sort_keys=True),
                    encoding="utf-8",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to write scientific_review.json: %s", exc)
        return result

    # --- Step 1: load + validate config ----------------------------------
    config = None
    step1 = _step_load_config(config_path)
    summary["steps"].append(asdict(step1))
    if not step1.ok:
        return _finalize(stopped_after="load_and_validate_config")

    # Late imports keep the pipeline module importable even when phydrus
    # is missing (e.g. for QC-only test environments).
    from hydrus_agent import load_config
    config = load_config(config_path)
    summary["case_id"] = config.case_id
    if (
        config.atmospheric is not None
        and config.atmospheric.source_metadata is not None
    ):
        summary["atmospheric_source"] = (
            config.atmospheric.source_metadata.model_dump(mode="json")
        )
    if config.material_source is not None:
        summary["material_source"] = (
            config.material_source.model_dump(mode="json")
        )

    # --- Step 2: create run folder ----------------------------------------
    step2 = _step_create_run_folder(config, overwrite_run)
    summary["steps"].append(asdict(step2))
    if not step2.ok:
        return _finalize(stopped_after="create_run_folder")

    run_dir = Path(step2.outputs[0])
    summary["run_dir"] = str(run_dir)

    # --- Step 3: prepare input -------------------------------------------
    step3 = _step_prepare_input(config, run_dir)
    summary["steps"].append(asdict(step3))
    if not step3.ok:
        return _finalize(stopped_after="prepare_input", run_dir=run_dir)

    project_dir = run_dir / "hydrus_project"

    # --- Step 4: run HYDRUS ----------------------------------------------
    step4 = _step_run_hydrus(
        run_dir=run_dir,
        project_dir=project_dir,
        timeout=timeout,
        launch_mode=hydrus_launch_mode,
    )
    summary["steps"].append(asdict(step4))
    summary["hydrus_status"] = _inspect_hydrus_status(project_dir, run_dir, step4)
    _set_reliability_status(summary, qc_summary=None)
    if not step4.ok:
        return _finalize(stopped_after="run_hydrus", run_dir=run_dir)

    # --- Steps 5-8: soft (continue on failure) ---------------------------
    outputs_data, step5 = _step_read_outputs(project_dir)
    summary["steps"].append(asdict(step5))

    figure_dir = run_dir / "figures"
    figures, step6 = _step_generate_plots(outputs_data, figure_dir)
    summary["steps"].append(asdict(step6))

    field_comparison = None
    if field_data_path is not None:
        field_comparison, field_figures, step_field = _step_compare_field_data(
            outputs_data,
            field_data_path,
            observation_depths=config.observation_depths,
            output_dir=run_dir / "outputs",
            figure_dir=figure_dir,
        )
        figures.extend(field_figures)
        summary["steps"].append(asdict(step_field))

    qc_summary, step7 = _step_run_qc(
        outputs_data,
        figures,
        qc_path=run_dir / "outputs" / "qc_summary.json",
        field_comparison=field_comparison,
    )
    summary["steps"].append(asdict(step7))
    _set_reliability_status(summary, qc_summary=qc_summary)
    qc_summary["hydrus_status"] = summary["hydrus_status"]
    qc_summary["reliability"] = {
        "execution_status": summary["execution_status"],
        "hydrus_numerical_status": summary["hydrus_numerical_status"],
        "qc_status": summary["qc_status"],
        "overall_status": summary["overall_status"],
    }

    step8 = _step_generate_report(
        config, run_dir, outputs_data, qc_summary, figures,
    )
    summary["steps"].append(asdict(step8))

    return _finalize(run_dir=run_dir)


# --- Internal step implementations ---------------------------------------


def _step_load_config(config_path: Union[str, Path]) -> StepResult:
    try:
        from hydrus_agent import ConfigError, load_config
    except Exception as exc:
        return StepResult(
            step="load_and_validate_config", ok=False,
            error=f"Could not import hydrus_agent: {exc}",
        )
    try:
        cfg = load_config(config_path)
    except ConfigError as exc:
        return StepResult(
            step="load_and_validate_config", ok=False,
            error=str(exc),
        )
    return StepResult(
        step="load_and_validate_config", ok=True,
        outputs=[cfg.case_id, str(config_path)],
    )


def _step_create_run_folder(config, overwrite_run: bool) -> StepResult:
    from hydrus_agent import create_run_folder
    try:
        case_dir = create_run_folder(
            config, runs_root=RUNS_ROOT, overwrite=overwrite_run,
        )
    except FileExistsError as exc:
        return StepResult(
            step="create_run_folder", ok=False,
            error=str(exc),
        )
    return StepResult(
        step="create_run_folder", ok=True, outputs=[str(case_dir)],
    )


def _step_prepare_input(config, run_dir: Path) -> StepResult:
    from hydrus_agent.env import resolve_hydrus_exe
    exe_str, source = resolve_hydrus_exe()
    if exe_str is None:
        return StepResult(
            step="prepare_input", ok=False,
            error=f"HYDRUS_EXE is not set (source: {source}).",
        )
    exe_path = Path(exe_str)
    if not exe_path.is_file():
        return StepResult(
            step="prepare_input", ok=False,
            error=f"HYDRUS executable not found at {exe_path}.",
        )

    try:
        from hydrus_agent.phydrus_adapter import (
            UnsupportedFeatureError, prepare_phydrus_project,
        )
    except Exception as exc:
        return StepResult(
            step="prepare_input", ok=False,
            error=f"Failed to import phydrus_adapter: {exc}",
        )
    try:
        project_dir = prepare_phydrus_project(config, run_dir, exe_path)
    except UnsupportedFeatureError as exc:
        return StepResult(
            step="prepare_input", ok=False, error=str(exc),
        )
    return StepResult(
        step="prepare_input", ok=True,
        outputs=[str(project_dir)],
    )


# Late-bind so tests can monkeypatch ``hydrus_agent.pipeline.run_hydrus_project``
# without restarting the process.
def _resolve_runner():
    from hydrus_agent.runner import run_hydrus_project
    return run_hydrus_project


def _step_run_hydrus(
    *,
    run_dir: Path,
    project_dir: Path,
    timeout: Optional[float],
    launch_mode: str,
) -> StepResult:
    from hydrus_agent.env import resolve_hydrus_exe
    from hydrus_agent.runner import RunnerError

    exe_str, source = resolve_hydrus_exe()
    if exe_str is None:
        return StepResult(
            step="run_hydrus", ok=False,
            error=f"HYDRUS_EXE is not set (source: {source}).",
        )
    exe_path = Path(exe_str)
    log_dir = run_dir / "logs"

    runner_fn = _resolve_runner()
    try:
        result = runner_fn(
            project_dir, exe_path, log_dir,
            timeout=timeout, launch_mode=launch_mode,
        )
    except RunnerError as exc:
        return StepResult(
            step="run_hydrus", ok=False,
            error=f"Runner failed: {exc}",
            outputs=[str(log_dir / "hydrus_run.log")] if (log_dir / "hydrus_run.log").is_file() else [],
        )

    outputs = [str(result.log_path)]
    outputs.extend(str(p) for p in result.generated_files)

    if result.false_success_reason:
        return StepResult(
            step="run_hydrus", ok=False, outputs=outputs,
            error=(f"HYDRUS exited 0 but output contained the failure marker "
                   f"'{result.false_success_reason}'. See {result.log_path}."),
        )
    if not result.success:
        return StepResult(
            step="run_hydrus", ok=False, outputs=outputs,
            error=(f"HYDRUS returned non-zero exit code {result.return_code}. "
                   f"See {result.log_path}."),
        )
    return StepResult(step="run_hydrus", ok=True, outputs=outputs)


def _step_read_outputs(project_dir: Path):
    """Soft step: returns (outputs_dict, StepResult). Never raises."""
    try:
        from hydrus_agent.output_reader import read_outputs
    except Exception as exc:
        return {}, StepResult(
            step="read_outputs", ok=False,
            error=f"Could not import output_reader: {exc}",
        )
    try:
        outputs = read_outputs(project_dir)
    except Exception as exc:
        return {}, StepResult(
            step="read_outputs", ok=False,
            error=f"read_outputs failed: {exc}",
        )

    warnings = []
    populated = []
    for name, df in outputs.items():
        if df is None or getattr(df, "empty", True):
            continue
        populated.append(f"{name} ({len(df)} rows)")
    if not populated:
        warnings.append("All output tables empty or missing")
    return outputs, StepResult(
        step="read_outputs", ok=True,
        outputs=populated, warnings=warnings,
    )


def _step_generate_plots(outputs, figure_dir: Path):
    """Soft step: returns (figure_paths, StepResult)."""
    try:
        from hydrus_agent.plotter import generate_standard_plots
    except Exception as exc:
        return [], StepResult(
            step="generate_plots", ok=False,
            error=f"Could not import plotter: {exc}",
        )
    try:
        figures = generate_standard_plots(outputs, figure_dir)
    except Exception as exc:
        return [], StepResult(
            step="generate_plots", ok=False,
            error=f"plotter failed: {exc}",
        )
    warnings = []
    if not figures:
        warnings.append("No figures created (outputs empty?)")
    return figures, StepResult(
        step="generate_plots", ok=True,
        outputs=[str(p) for p in figures], warnings=warnings,
    )


def _step_compare_field_data(
    outputs,
    field_data_path: Union[str, Path],
    *,
    observation_depths,
    output_dir: Path,
    figure_dir: Path,
):
    """Soft step: compare parsed Obs_Node.out against measured field data."""
    try:
        from hydrus_agent.field_comparison import run_field_comparison
    except Exception as exc:
        return None, [], StepResult(
            step="compare_field_data", ok=False,
            error=f"Could not import field_comparison: {exc}",
        )
    try:
        summary, figures, summary_path = run_field_comparison(
            outputs,
            field_data_path,
            output_dir=output_dir,
            figure_dir=figure_dir,
            observation_depths=observation_depths,
        )
    except Exception as exc:
        return None, [], StepResult(
            step="compare_field_data", ok=False,
            error=f"Field comparison failed: {exc}",
        )
    warnings = list(summary.get("warnings", []))
    out = [str(summary_path), *[str(path) for path in figures]]
    return summary, figures, StepResult(
        step="compare_field_data",
        ok=True,
        outputs=out,
        warnings=warnings,
    )


def _step_run_qc(outputs, figures, qc_path: Path, *, field_comparison=None):
    """Soft step: returns (qc_summary_dict, StepResult)."""
    try:
        from hydrus_agent.qc import assess_run_quality, write_qc_summary
    except Exception as exc:
        return {}, StepResult(
            step="run_qc", ok=False,
            error=f"Could not import qc: {exc}",
        )
    try:
        qc_summary = assess_run_quality(
            outputs, figures=figures, field_comparison=field_comparison,
        )
        write_qc_summary(qc_summary, qc_path)
    except Exception as exc:
        return {}, StepResult(
            step="run_qc", ok=False,
            error=f"QC failed: {exc}",
        )
    warnings = list(qc_summary.get("warnings", []))
    return qc_summary, StepResult(
        step="run_qc", ok=True,
        outputs=[str(qc_path)], warnings=warnings,
    )


def _step_generate_report(
    config, run_dir: Path, outputs, qc_summary, figures,
) -> StepResult:
    try:
        from hydrus_agent.reporter import generate_markdown_report
    except Exception as exc:
        return StepResult(
            step="generate_report", ok=False,
            error=f"Could not import reporter: {exc}",
        )
    try:
        report_path = generate_markdown_report(
            config, run_dir, outputs, qc_summary, figures,
        )
    except Exception as exc:
        return StepResult(
            step="generate_report", ok=False,
            error=f"Report generation failed: {exc}",
        )
    return StepResult(
        step="generate_report", ok=True,
        outputs=[str(report_path)],
    )


# --- Finalisation --------------------------------------------------------


def _finish(
    summary: Dict[str, Any],
    *,
    stopped_after: Optional[str] = None,
    run_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    summary["finished_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    summary["stopped_after_step"] = stopped_after

    # Pipeline is "ok" iff every recorded step is ok and the reliability
    # status is clean. This separates process execution from numerical/QC
    # reliability while keeping the historical top-level boolean useful.
    steps_ok = all(s.get("ok", False) for s in summary["steps"])
    if "overall_status" in summary:
        summary["ok"] = steps_ok and summary["overall_status"] == "ok"
    else:
        summary["ok"] = steps_ok

    # Persist if we have a run folder to write into.
    if run_dir is not None and Path(run_dir).is_dir():
        path = Path(run_dir) / PIPELINE_SUMMARY_FILENAME
        path.write_text(
            json.dumps(summary, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        summary["summary_path"] = str(path)
    return summary


def _inspect_hydrus_status(
    project_dir: Path,
    run_dir: Path,
    run_step: StepResult,
) -> Dict[str, Any]:
    log_path = run_dir / "logs" / "hydrus_run.log"
    return_code = _read_return_code(log_path)
    error_path = _find_error_message_file(project_dir)
    failure_reason = None
    numerical_failure = False
    error_excerpt = None
    if error_path is not None:
        text = error_path.read_text(encoding="utf-8", errors="replace").strip()
        failure_reason, error_excerpt = _detect_numerical_failure(text)
        numerical_failure = failure_reason is not None

    if numerical_failure:
        status = "failed"
    elif run_step.ok:
        status = "converged"
    else:
        status = "unknown"

    return {
        "return_code": return_code,
        "error_message_file": str(error_path) if error_path is not None else None,
        "numerical_failure_detected": numerical_failure,
        "failure_reason": failure_reason,
        "error_excerpt": error_excerpt,
        "status": status,
    }


def _find_error_message_file(project_dir: Path) -> Optional[Path]:
    for candidate in project_dir.glob("*"):
        if candidate.is_file() and candidate.name.lower() == "error.msg":
            return candidate
    return None


def _detect_numerical_failure(text: str) -> tuple[Optional[str], Optional[str]]:
    if not text.strip():
        return None, None
    readable, compact = _normalise_error_msg_for_matching(text)
    excerpt = _error_excerpt(text)

    if "stoppedafter" in compact and "consecutive" in compact:
        if "nonconverged" in compact:
            return (
                "numerical solution stopped after 10 consecutive "
                "non-converged steps",
                excerpt,
            )
        return "numerical solution stopped after 10 consecutive time steps", excerpt

    if "numericalsolution" in compact and "stopped" in compact:
        return "numerical solution stopped", excerpt
    if "didnotconverge" in compact:
        return "did not converge", excerpt
    if "nonconvergence" in compact:
        return "non convergence", excerpt
    if "failedtoconverge" in compact:
        return "failed to converge", excerpt
    if "nonconverged" in compact:
        return "non-converged", excerpt

    lower = readable.lower()
    for pattern in NUMERICAL_FAILURE_PATTERNS:
        if re.search(pattern, lower):
            return readable, excerpt
    return None, excerpt


def _normalise_error_msg_for_matching(text: str) -> tuple[str, str]:
    # HYDRUS wraps fixed-width console messages. First repair hyphenated
    # line breaks such as "non-\nconverged", then create two views:
    # a readable whitespace-collapsed form and a compact alphanumeric form.
    hyphen_joined = re.sub(
        r"(?<=[A-Za-z0-9])-\s*(?:\r?\n|\r)\s*(?=[A-Za-z0-9])",
        "-",
        text,
    )
    readable = re.sub(r"\s+", " ", hyphen_joined).strip()
    compact = re.sub(r"[^a-z0-9]+", "", hyphen_joined.lower())
    return readable, compact


def _error_excerpt(text: str, *, limit: int = 220) -> str:
    excerpt = re.sub(r"\s+", " ", text).strip()
    if len(excerpt) <= limit:
        return excerpt
    return excerpt[: limit - 3].rstrip() + "..."


def _read_return_code(log_path: Path) -> Optional[int]:
    if not log_path.is_file():
        return None
    text = log_path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"return code:\s*(-?\d+)", text, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _set_reliability_status(
    summary: Dict[str, Any],
    *,
    qc_summary: Optional[Dict[str, Any]],
) -> None:
    run_step = next(
        (step for step in summary["steps"] if step.get("step") == "run_hydrus"),
        None,
    )
    execution_status = (
        "completed"
        if run_step is not None and run_step.get("ok")
        else "failed_process"
    )
    hydrus_status = summary.get("hydrus_status", {})
    hydrus_numerical_status = hydrus_status.get("status", "unknown")
    qc_status = (
        "not_run"
        if qc_summary is None
        else "passed" if qc_summary.get("ok") else "failed"
    )

    if execution_status == "failed_process":
        overall_status = "failed"
    elif hydrus_numerical_status == "failed":
        overall_status = "failed"
    elif qc_status == "failed":
        overall_status = "failed"
    elif qc_status == "not_run":
        overall_status = "incomplete"
    else:
        overall_status = "ok"

    summary["execution_status"] = execution_status
    summary["hydrus_numerical_status"] = hydrus_numerical_status
    summary["qc_status"] = qc_status
    summary["overall_status"] = overall_status
