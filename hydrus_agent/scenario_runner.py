"""Scenario and sensitivity batch runner.

This module creates explicit, finite scenario batches from a base HYDRUS
configuration plus a small scenario file. It is not a calibration or
optimisation engine: every override is user-specified, validated up front,
and then run through the existing pipeline.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from pydantic import ValidationError

from hydrus_agent import load_config
from hydrus_agent.schema import ModelConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = PROJECT_ROOT / "runs"

SCENARIO_SUMMARY_CSV = "scenario_summary.csv"
SCENARIO_SUMMARY_JSON = "scenario_summary.json"
SCENARIO_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
VG_PATH_RE = re.compile(r"^van_genuchten\[(\d+)\]\.(Ks|alpha|n)$")


class ScenarioError(ValueError):
    """Raised when a scenario file or override is invalid."""


def load_scenario_file(path: Path | str) -> Dict[str, Any]:
    """Load and validate a scenario batch JSON file."""
    path = Path(path)
    if not path.is_file():
        raise ScenarioError(f"Scenario file not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScenarioError(
            f"{path} is not valid JSON: {exc.msg} "
            f"(line {exc.lineno}, column {exc.colno})"
        ) from exc

    if not isinstance(raw, dict):
        raise ScenarioError("Scenario file must contain a JSON object.")
    batch_id = raw.get("batch_id")
    if not _is_safe_id(batch_id):
        raise ScenarioError("batch_id contains unsafe path characters.")
    scenarios = raw.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ScenarioError("Scenario file must contain a non-empty scenarios list.")

    seen = set()
    validated = []
    for item in scenarios:
        if not isinstance(item, dict):
            raise ScenarioError("Each scenario must be a JSON object.")
        scenario_id = item.get("scenario_id")
        if not _is_safe_id(scenario_id):
            raise ScenarioError("scenario_id contains unsafe path characters.")
        if scenario_id in seen:
            raise ScenarioError(f"Duplicate scenario_id: {scenario_id}")
        seen.add(scenario_id)
        overrides = item.get("overrides", {})
        if not isinstance(overrides, dict):
            raise ScenarioError(f"Scenario {scenario_id} overrides must be an object.")
        validated.append({
            "scenario_id": scenario_id,
            "overrides": overrides,
        })

    return {"batch_id": batch_id, "scenarios": validated}


def apply_scenario_overrides(
    base_config: ModelConfig,
    *,
    scenario_id: str,
    overrides: Dict[str, Any],
) -> ModelConfig:
    """Return a new validated config with a scenario-specific case ID."""
    if not _is_safe_id(scenario_id):
        raise ScenarioError("scenario_id contains unsafe path characters.")
    raw = base_config.model_dump(mode="json")
    raw["case_id"] = f"{base_config.case_id}__{scenario_id}"
    for path, value in overrides.items():
        _apply_override(raw, path, value)
    try:
        return ModelConfig.model_validate(raw)
    except ValidationError as exc:
        raise ScenarioError(
            f"Scenario {scenario_id} failed ModelConfig validation: "
            f"{_format_validation_error(exc)}"
        ) from exc


def run_scenario_batch(
    base_config_path: Path | str,
    scenario_file: Path | str,
    *,
    timeout: Optional[float] = None,
    hydrus_launch_mode: str = "argv",
    field_data_path: Optional[Path | str] = None,
    overwrite_run: bool = True,
    runs_root: Path | str = RUNS_ROOT,
    pipeline_runner: Optional[Callable[..., Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Run all scenarios from ``scenario_file`` against ``base_config_path``.

    All scenario IDs and overrides are validated before the first scenario is
    run. Per-scenario configs are written under
    ``runs/<batch_id>/configs/<case_id>.json``.
    """
    base_config = load_config(base_config_path)
    spec = load_scenario_file(scenario_file)
    runs_root = Path(runs_root)
    batch_dir = runs_root / spec["batch_id"]
    config_dir = batch_dir / "configs"

    prepared: List[Tuple[Dict[str, Any], ModelConfig]] = []
    for scenario in spec["scenarios"]:
        prepared.append((
            scenario,
            apply_scenario_overrides(
                base_config,
                scenario_id=scenario["scenario_id"],
                overrides=scenario.get("overrides", {}),
            ),
        ))

    config_dir.mkdir(parents=True, exist_ok=True)
    pipeline = pipeline_runner or _default_pipeline_runner
    rows: List[Dict[str, Any]] = []
    for scenario, config in prepared:
        config_path = config_dir / f"{config.case_id}.json"
        _write_config(config, config_path)
        result = pipeline(
            config_path,
            overwrite_run=overwrite_run,
            timeout=timeout,
            hydrus_launch_mode=hydrus_launch_mode,
            field_data_path=field_data_path,
        )
        rows.append(_summary_row(
            batch_id=spec["batch_id"],
            scenario=scenario,
            config=config,
            pipeline_summary=result,
        ))

    csv_path = batch_dir / SCENARIO_SUMMARY_CSV
    json_path = batch_dir / SCENARIO_SUMMARY_JSON
    _write_summary_csv(rows, csv_path)
    summary = {
        "ok": all(row.get("status") == "pass" for row in rows),
        "batch_id": spec["batch_id"],
        "base_config_path": str(Path(base_config_path)),
        "scenario_file": str(Path(scenario_file)),
        "summary_csv_path": str(csv_path),
        "summary_json_path": str(json_path),
        "counts": _counts(rows),
        "scenarios": rows,
    }
    json_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return summary


def _default_pipeline_runner(*args, **kwargs):
    from hydrus_agent.pipeline import run_full_pipeline

    return run_full_pipeline(*args, **kwargs)


def _apply_override(raw: Dict[str, Any], path: str, value: Any) -> None:
    match = VG_PATH_RE.match(path)
    if match:
        index = int(match.group(1))
        field = match.group(2)
        try:
            raw["van_genuchten"][index][field] = value
        except IndexError as exc:
            raise ScenarioError(f"Override path {path} references a missing material index.") from exc
        return

    if path == "initial_condition.value":
        raw["initial_condition"]["value"] = value
        return
    if path in {"upper_boundary.flux", "upper_boundary.head"}:
        _, field = path.split(".", 1)
        raw["upper_boundary"][field] = value
        return
    if path == "root_uptake.root_depth":
        if not raw.get("root_uptake"):
            raise ScenarioError("Override path root_uptake.root_depth requires root_uptake in the base config.")
        raw["root_uptake"]["root_depth"] = value
        return
    if path == "solute_transport.species[0].dispersivity":
        solute = raw.get("solute_transport")
        if not solute or not solute.get("species"):
            raise ScenarioError(
                "Override path solute_transport.species[0].dispersivity "
                "requires solute_transport.species in the base config."
            )
        raw["solute_transport"]["species"][0]["dispersivity"] = value
        return

    raise ScenarioError(f"Unsupported override path: {path}")


def _summary_row(
    *,
    batch_id: str,
    scenario: Dict[str, Any],
    config: ModelConfig,
    pipeline_summary: Dict[str, Any],
) -> Dict[str, Any]:
    run_dir = Path(pipeline_summary.get("run_dir") or RUNS_ROOT / config.case_id)
    qc = _read_json_if_exists(run_dir / "outputs" / "qc_summary.json")
    row: Dict[str, Any] = {
        "batch_id": batch_id,
        "scenario_id": scenario["scenario_id"],
        "case_id": config.case_id,
        "status": "pass" if pipeline_summary.get("ok") else "fail",
        "run_dir": str(run_dir) if run_dir else "",
        "pipeline_summary_path": pipeline_summary.get("summary_path", ""),
        "qc_ok": qc.get("ok") if qc else None,
        "warning_count": len(qc.get("warnings", []) if qc else []),
        "field_data_available": False,
        "overrides": dict(scenario.get("overrides", {})),
    }
    if qc:
        wb = qc.get("water_balance", {})
        cf = qc.get("cumulative_fluxes", {})
        for key in ("final_error_pct", "max_abs_error_pct"):
            if key in wb:
                row[key] = wb[key]
        for key in ("final_sum_Infil", "final_sum_vBot"):
            if key in cf:
                row[key] = cf[key]
        _flatten_field_metrics(qc.get("field_comparison", {}), row)
    return row


def _flatten_field_metrics(field: Dict[str, Any], row: Dict[str, Any]) -> None:
    row["field_data_available"] = bool(field.get("available"))
    if "matched_rows" in field:
        row["field_matched_rows"] = field.get("matched_rows")
    for variable, info in field.get("variables", {}).items():
        for node, metrics in info.get("nodes", {}).items():
            prefix = f"{variable}_node_{node}"
            for metric in ("matched_count", "rmse", "mae", "bias", "correlation"):
                if metric in metrics:
                    row[f"{prefix}_{metric}"] = metrics[metric]


def _write_summary_csv(rows: List[Dict[str, Any]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: List[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            if isinstance(out.get("overrides"), dict):
                out["overrides"] = json.dumps(out["overrides"], sort_keys=True)
            writer.writerow(out)
    return path


def _write_config(config: ModelConfig, path: Path) -> Path:
    path.write_text(
        json.dumps(config.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    return path


def _read_json_if_exists(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _counts(rows: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"pass": 0, "fail": 0}
    for row in rows:
        status = row.get("status", "fail")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _format_validation_error(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ())) or "<root>"
        parts.append(f"{loc}: {err.get('msg')}")
    return "; ".join(parts)


def _is_safe_id(value: Any) -> bool:
    return isinstance(value, str) and bool(SCENARIO_ID_RE.fullmatch(value))
