"""Prompt-to-config benchmark framework.

Evaluates pre-saved candidate JSON configs (representing the output of some
prompt-to-config workflow) against per-case expectations covering:

- whether the candidate passes schema validation;
- the deterministic scientific-reviewer output (counts and codes);
- structural ``features.*`` extracted from the validated ``ModelConfig``;
- presence or absence of top-level keys in the raw JSON.

This module never calls an LLM and never runs HYDRUS. It only reads files,
runs ``load_config``, runs ``review_config``, and compares.

The benchmark is informational. The runner script always exits 0; per-case
``passed`` is data, not a CLI gate.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Sequence

from hydrus_agent import ConfigError, load_config
from hydrus_agent.schema import ModelConfig
from hydrus_agent.scientific_reviewer import (
    ScientificReviewResult,
    review_config,
)

SCHEMA_VERSION = 1

SchemaValidation = Literal["pass", "fail", "missing_candidate"]


# --- Feature extractor registry -----------------------------------------
# Adding a new feature key = one entry here + one unit test. Unknown
# feature keys in case.json are reported as a per-case failure so typos
# fail loudly.

def _feat_upper_boundary_type(cfg: ModelConfig) -> Any:
    return cfg.upper_boundary.type.value


def _feat_lower_boundary_type(cfg: ModelConfig) -> Any:
    return cfg.lower_boundary.type.value


def _feat_soil_layer_count(cfg: ModelConfig) -> Any:
    return len(cfg.soil_profile)


def _feat_has_atmospheric_csv(cfg: ModelConfig) -> Any:
    return bool(cfg.atmospheric and cfg.atmospheric.source_csv)


def _feat_has_material_csv(cfg: ModelConfig) -> Any:
    return cfg.material_source is not None


def _feat_has_root_uptake(cfg: ModelConfig) -> Any:
    return bool(cfg.root_uptake and cfg.root_uptake.enabled)


def _feat_has_solute_transport(cfg: ModelConfig) -> Any:
    return bool(cfg.solute_transport and cfg.solute_transport.enabled)


def _feat_observation_depth_count(cfg: ModelConfig) -> Any:
    return len(cfg.observation_depths or [])


def _feat_simulation_units(cfg: ModelConfig) -> Any:
    return cfg.simulation_time.units.value


def _feat_initial_condition_type(cfg: ModelConfig) -> Any:
    return cfg.initial_condition.type.value


_FEATURE_EXTRACTORS: Dict[str, Callable[[ModelConfig], Any]] = {
    "upper_boundary_type": _feat_upper_boundary_type,
    "lower_boundary_type": _feat_lower_boundary_type,
    "soil_layer_count": _feat_soil_layer_count,
    "has_atmospheric_csv": _feat_has_atmospheric_csv,
    "has_material_csv": _feat_has_material_csv,
    "has_root_uptake": _feat_has_root_uptake,
    "has_solute_transport": _feat_has_solute_transport,
    "observation_depth_count": _feat_observation_depth_count,
    "simulation_units": _feat_simulation_units,
    "initial_condition_type": _feat_initial_condition_type,
}


def supported_feature_keys() -> List[str]:
    return sorted(_FEATURE_EXTRACTORS)


# --- Public dataclasses --------------------------------------------------


@dataclass(frozen=True)
class FeatureCheck:
    name: str
    expected: Any
    actual: Any
    passed: bool


@dataclass(frozen=True)
class ReviewCheck:
    name: str
    expected: Any
    actual: Any
    passed: bool


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    prompt: str
    tags: List[str]
    candidate_path: Path
    expected: Dict[str, Any]
    case_path: Path


@dataclass(frozen=True)
class BenchmarkCaseResult:
    case_id: str
    prompt: str
    tags: List[str]
    candidate_path: str
    schema_validation: SchemaValidation
    schema_error: Optional[str]
    schema_check: FeatureCheck
    scientific_review_summary: Optional[Dict[str, Any]]
    review_checks: List[ReviewCheck]
    feature_checks: List[FeatureCheck]
    raw_json_checks: List[FeatureCheck]
    passed: bool
    failures: List[str]


@dataclass(frozen=True)
class BenchmarkRunResult:
    cases: List[BenchmarkCaseResult]
    counts: Dict[str, int]
    schema_version: int = SCHEMA_VERSION


# --- Public API ----------------------------------------------------------


def load_case(case_dir: Path) -> BenchmarkCase:
    """Load a single benchmark case directory.

    A case directory must contain ``case.json``. The candidate config path
    is resolved relative to the case directory.
    """
    case_dir = Path(case_dir)
    case_json = case_dir / "case.json"
    if not case_json.is_file():
        raise FileNotFoundError(f"case.json not found in {case_dir}")
    raw = json.loads(case_json.read_text(encoding="utf-8"))
    candidate_rel = raw.get("candidate_config") or "candidate.json"
    candidate_path = (case_dir / candidate_rel).resolve()
    return BenchmarkCase(
        case_id=raw["case_id"],
        prompt=raw.get("prompt", ""),
        tags=list(raw.get("tags") or []),
        candidate_path=candidate_path,
        expected=dict(raw.get("expected") or {}),
        case_path=case_json,
    )


def evaluate_case(case: BenchmarkCase) -> BenchmarkCaseResult:
    """Evaluate a single loaded benchmark case. Never raises."""
    failures: List[str] = []
    expected = case.expected

    expected_schema = expected.get("schema_validation", "pass")
    if expected_schema not in ("pass", "fail"):
        failures.append(
            f"expected.schema_validation must be 'pass' or 'fail', got "
            f"{expected_schema!r}"
        )

    # --- Step 1: load the raw candidate JSON for raw_json checks --------
    raw_json: Optional[Dict[str, Any]] = None
    raw_json_error: Optional[str] = None
    if case.candidate_path.is_file():
        try:
            raw_json = json.loads(
                case.candidate_path.read_text(encoding="utf-8")
            )
        except Exception as exc:  # noqa: BLE001
            raw_json_error = f"candidate JSON did not parse: {exc}"
            failures.append(raw_json_error)

    # --- Step 2: schema validation -------------------------------------
    schema_validation: SchemaValidation
    schema_error: Optional[str] = None
    cfg: Optional[ModelConfig] = None
    if not case.candidate_path.is_file():
        schema_validation = "missing_candidate"
        schema_error = f"candidate config not found at {case.candidate_path}"
    else:
        try:
            cfg = load_config(case.candidate_path)
            schema_validation = "pass"
        except ConfigError as exc:
            schema_validation = "fail"
            schema_error = str(exc)
        except Exception as exc:  # noqa: BLE001 - never raise
            schema_validation = "fail"
            schema_error = f"unexpected error during load_config: {exc}"

    schema_check = _check_schema_expectation(
        expected_schema, schema_validation, schema_error,
        expected.get("schema_error_pattern"),
    )
    if not schema_check.passed:
        failures.append(
            f"schema_validation: expected={schema_check.expected!r} "
            f"actual={schema_check.actual!r}"
            + (f" error={schema_error}" if schema_error else "")
        )

    # --- Step 3: scientific review (only when schema passed) -----------
    review_checks: List[ReviewCheck] = []
    sr_summary: Optional[Dict[str, Any]] = None
    feature_checks: List[FeatureCheck] = []
    if cfg is not None and schema_validation == "pass":
        try:
            sr = review_config(cfg)
            sr_summary = {
                "ok": sr.ok,
                "counts": dict(sr.counts),
                "codes": [item.code for item in sr.items],
            }
        except Exception as exc:  # noqa: BLE001
            sr = None
            failures.append(f"scientific_reviewer crashed: {exc}")

        if sr is not None:
            review_checks = _check_review_expectations(
                sr, expected.get("scientific_review") or {},
            )
            for chk in review_checks:
                if not chk.passed:
                    failures.append(
                        f"scientific_review.{chk.name}: "
                        f"expected={chk.expected!r} actual={chk.actual!r}"
                    )

        feature_checks = _check_feature_expectations(
            cfg, expected.get("features") or {},
        )
        for chk in feature_checks:
            if not chk.passed:
                if chk.name.startswith("__unknown__"):
                    failures.append(chk.expected)  # the unknown-key message
                else:
                    failures.append(
                        f"features.{chk.name}: "
                        f"expected={chk.expected!r} actual={chk.actual!r}"
                    )

    # --- Step 4: raw JSON checks (always run when raw_json parsed) -----
    raw_json_checks = _check_raw_json_expectations(
        raw_json, expected.get("raw_json") or {},
    )
    for chk in raw_json_checks:
        if not chk.passed:
            failures.append(
                f"raw_json.{chk.name}: "
                f"expected={chk.expected!r} actual={chk.actual!r}"
            )

    passed = not failures

    return BenchmarkCaseResult(
        case_id=case.case_id,
        prompt=case.prompt,
        tags=list(case.tags),
        candidate_path=str(case.candidate_path),
        schema_validation=schema_validation,
        schema_error=schema_error,
        schema_check=schema_check,
        scientific_review_summary=sr_summary,
        review_checks=review_checks,
        feature_checks=feature_checks,
        raw_json_checks=raw_json_checks,
        passed=passed,
        failures=failures,
    )


def evaluate_all(cases_root: Path) -> BenchmarkRunResult:
    """Evaluate every case directory directly under ``cases_root``."""
    cases_root = Path(cases_root)
    results: List[BenchmarkCaseResult] = []
    for child in sorted(cases_root.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        if not (child / "case.json").is_file():
            continue
        case = load_case(child)
        results.append(evaluate_case(case))
    counts = {
        "total": len(results),
        "passed": sum(1 for r in results if r.passed),
        "failed": sum(1 for r in results if not r.passed),
    }
    return BenchmarkRunResult(cases=results, counts=counts)


def render_markdown(result: BenchmarkRunResult) -> str:
    """Render a concise markdown summary clearly listing total/passed/failed,
    each failed case_id, and its failure reasons."""
    lines: List[str] = []
    lines.append("# Prompt-to-config benchmark")
    lines.append("")
    lines.append(
        f"Total: {result.counts.get('total', 0)}. "
        f"Passed: {result.counts.get('passed', 0)}. "
        f"Failed: {result.counts.get('failed', 0)}."
    )
    lines.append("")

    failed = [r for r in result.cases if not r.passed]
    if failed:
        lines.append("## Failed cases")
        lines.append("")
        for r in failed:
            lines.append(f"### {r.case_id}")
            lines.append(f"- Candidate: `{r.candidate_path}`")
            lines.append(f"- Schema validation: {r.schema_validation}")
            if r.schema_error:
                lines.append(f"- Schema error: {r.schema_error}")
            if r.scientific_review_summary:
                counts = r.scientific_review_summary.get("counts", {})
                lines.append(
                    f"- Scientific review counts: critical={counts.get('critical', 0)}, "
                    f"warning={counts.get('warning', 0)}, info={counts.get('info', 0)}"
                )
            lines.append("- Failures:")
            for reason in r.failures:
                lines.append(f"  - {reason}")
            lines.append("")
    else:
        lines.append("_All cases passed._")
        lines.append("")

    lines.append("## All cases")
    lines.append("")
    lines.append("| case_id | schema | passed |")
    lines.append("|---|---|---|")
    for r in result.cases:
        lines.append(
            f"| {r.case_id} | {r.schema_validation} | "
            f"{'PASS' if r.passed else 'FAIL'} |"
        )
    return "\n".join(lines)


def result_to_dict(result: BenchmarkRunResult) -> Dict[str, Any]:
    return {
        "schema_version": result.schema_version,
        "counts": dict(result.counts),
        "cases": [asdict(c) for c in result.cases],
    }


# --- Internal helpers ----------------------------------------------------


def _check_schema_expectation(
    expected: str,
    actual: SchemaValidation,
    actual_error: Optional[str],
    pattern: Optional[str],
) -> FeatureCheck:
    if expected == "pass":
        return FeatureCheck(
            name="schema_validation",
            expected="pass", actual=actual, passed=actual == "pass",
        )
    # expected == "fail"
    if actual != "fail":
        return FeatureCheck(
            name="schema_validation",
            expected="fail", actual=actual, passed=False,
        )
    if pattern:
        if actual_error is None or not re.search(pattern, actual_error):
            return FeatureCheck(
                name="schema_validation",
                expected=f"fail matching {pattern!r}",
                actual=f"fail without matching error ({actual_error!r})",
                passed=False,
            )
    return FeatureCheck(
        name="schema_validation",
        expected="fail" + (f" matching {pattern!r}" if pattern else ""),
        actual="fail",
        passed=True,
    )


def _check_review_expectations(
    sr: ScientificReviewResult,
    spec: Dict[str, Any],
) -> List[ReviewCheck]:
    checks: List[ReviewCheck] = []
    codes = [item.code for item in sr.items]

    if "ok" in spec and spec["ok"] is not None:
        checks.append(ReviewCheck(
            name="ok", expected=spec["ok"], actual=sr.ok,
            passed=sr.ok == spec["ok"],
        ))
    must_have = spec.get("must_have_codes") or []
    if must_have:
        missing = [c for c in must_have if c not in codes]
        checks.append(ReviewCheck(
            name="must_have_codes",
            expected=list(must_have),
            actual=codes,
            passed=not missing,
        ))
    must_not = spec.get("must_not_have_codes") or []
    if must_not:
        leaked = [c for c in must_not if c in codes]
        checks.append(ReviewCheck(
            name="must_not_have_codes",
            expected=list(must_not),
            actual=leaked or [],
            passed=not leaked,
        ))
    if "max_critical" in spec and spec["max_critical"] is not None:
        actual = sr.counts.get("critical", 0)
        checks.append(ReviewCheck(
            name="max_critical", expected=spec["max_critical"], actual=actual,
            passed=actual <= int(spec["max_critical"]),
        ))
    if "max_warning" in spec and spec["max_warning"] is not None:
        actual = sr.counts.get("warning", 0)
        checks.append(ReviewCheck(
            name="max_warning", expected=spec["max_warning"], actual=actual,
            passed=actual <= int(spec["max_warning"]),
        ))
    return checks


def _check_feature_expectations(
    cfg: ModelConfig, spec: Dict[str, Any],
) -> List[FeatureCheck]:
    checks: List[FeatureCheck] = []
    for key, expected_value in spec.items():
        extractor = _FEATURE_EXTRACTORS.get(key)
        if extractor is None:
            # Unknown feature key: fail loudly with a clear message.
            checks.append(FeatureCheck(
                name=f"__unknown__{key}",
                expected=(
                    f"unknown feature key {key!r}; supported keys: "
                    f"{supported_feature_keys()}"
                ),
                actual=None, passed=False,
            ))
            continue
        actual = extractor(cfg)
        checks.append(FeatureCheck(
            name=key, expected=expected_value, actual=actual,
            passed=actual == expected_value,
        ))
    return checks


def _check_raw_json_expectations(
    raw_json: Optional[Dict[str, Any]], spec: Dict[str, Any],
) -> List[FeatureCheck]:
    checks: List[FeatureCheck] = []
    if raw_json is None:
        return checks
    top_keys = set(raw_json.keys())
    must_contain = spec.get("must_contain_keys") or []
    if must_contain:
        missing = [k for k in must_contain if k not in top_keys]
        checks.append(FeatureCheck(
            name="must_contain_keys",
            expected=list(must_contain),
            actual=sorted(top_keys),
            passed=not missing,
        ))
    must_not = spec.get("must_not_contain_keys") or []
    if must_not:
        leaked = [k for k in must_not if k in top_keys]
        checks.append(FeatureCheck(
            name="must_not_contain_keys",
            expected=list(must_not),
            actual=leaked,
            passed=not leaked,
        ))
    return checks


__all__ = [
    "BenchmarkCase",
    "BenchmarkCaseResult",
    "BenchmarkRunResult",
    "FeatureCheck",
    "ReviewCheck",
    "SCHEMA_VERSION",
    "evaluate_all",
    "evaluate_case",
    "load_case",
    "render_markdown",
    "result_to_dict",
    "supported_feature_keys",
]
