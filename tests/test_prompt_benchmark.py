"""Unit tests for hydrus_agent.prompt_benchmark.

All tests build synthetic cases under tmp_path. No HYDRUS execution.
No external LLM. The canonical cases under benchmarks/prompt_to_config/
are exercised separately in tests/test_prompt_benchmark_cases.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from hydrus_agent.prompt_benchmark import (
    SCHEMA_VERSION,
    evaluate_all,
    evaluate_case,
    load_case,
    render_markdown,
    result_to_dict,
    supported_feature_keys,
)


# --- Helpers -------------------------------------------------------------


def _valid_candidate() -> Dict[str, Any]:
    return {
        "project_name": "synthetic",
        "case_id": "synth_case",
        "simulation_time": {
            "t_init": 0.0, "t_end": 1.0, "dt_init": 0.001, "units": "days",
        },
        "soil_profile": [
            {"depth_top": 0.0, "depth_bottom": 1.0, "material_id": 1},
        ],
        "van_genuchten": [
            {"material_id": 1, "theta_r": 0.065, "theta_s": 0.41,
             "alpha": 7.5, "n": 1.89, "Ks": 1.061, "l": 0.5},
        ],
        "initial_condition": {"type": "pressure_head", "value": -1.0},
        "upper_boundary": {"type": "constant_flux", "flux": 0.001},
        "lower_boundary": {"type": "free_drainage"},
        "observation_depths": [0.25, 0.75],
        "output_settings": {"print_times": [0.25, 0.5, 0.75, 1.0]},
    }


def _write_case(tmp_path: Path, case_id: str, *,
                candidate: Dict[str, Any] | None,
                expected: Dict[str, Any]) -> Path:
    case_dir = tmp_path / case_id
    case_dir.mkdir()
    if candidate is not None:
        (case_dir / "candidate.json").write_text(
            json.dumps(candidate), encoding="utf-8",
        )
    (case_dir / "case.json").write_text(
        json.dumps({
            "case_id": case_id,
            "prompt": f"prompt for {case_id}",
            "tags": [],
            "candidate_config": "candidate.json",
            "expected": expected,
        }),
        encoding="utf-8",
    )
    return case_dir


# --- Pass paths ----------------------------------------------------------


def test_pass_case_with_no_extra_expectations_passes(tmp_path):
    case_dir = _write_case(
        tmp_path, "minimal",
        candidate=_valid_candidate(),
        expected={"schema_validation": "pass"},
    )
    result = evaluate_case(load_case(case_dir))
    assert result.passed, result.failures
    assert result.schema_validation == "pass"


def test_feature_check_mismatch_fails(tmp_path):
    case_dir = _write_case(
        tmp_path, "feature_mismatch",
        candidate=_valid_candidate(),
        expected={
            "schema_validation": "pass",
            "features": {"soil_layer_count": 2},
        },
    )
    result = evaluate_case(load_case(case_dir))
    assert not result.passed
    assert any("soil_layer_count" in f for f in result.failures)


def test_unknown_feature_key_fails_loudly(tmp_path):
    case_dir = _write_case(
        tmp_path, "unknown_feature",
        candidate=_valid_candidate(),
        expected={
            "schema_validation": "pass",
            "features": {"completely_made_up_key": "anything"},
        },
    )
    result = evaluate_case(load_case(case_dir))
    assert not result.passed
    msg = " ".join(result.failures)
    assert "completely_made_up_key" in msg
    assert "supported keys" in msg


# --- Schema-fail expectations -------------------------------------------


def test_schema_fail_expectation_passes_when_candidate_invalid(tmp_path):
    bad = _valid_candidate()
    bad["van_genuchten"][0].pop("n")
    case_dir = _write_case(
        tmp_path, "missing_n",
        candidate=bad,
        expected={
            "schema_validation": "fail",
            "schema_error_pattern": "\\bn\\b|van_genuchten",
        },
    )
    result = evaluate_case(load_case(case_dir))
    assert result.passed, result.failures
    assert result.schema_validation == "fail"


def test_schema_error_pattern_required_match(tmp_path):
    bad = _valid_candidate()
    bad["van_genuchten"][0].pop("n")
    case_dir = _write_case(
        tmp_path, "wrong_pattern",
        candidate=bad,
        expected={
            "schema_validation": "fail",
            "schema_error_pattern": "this_string_will_not_appear",
        },
    )
    result = evaluate_case(load_case(case_dir))
    assert not result.passed
    assert any("schema_validation" in f for f in result.failures)


def test_schema_pass_expectation_fails_when_candidate_invalid(tmp_path):
    bad = _valid_candidate()
    bad["van_genuchten"][0].pop("n")
    case_dir = _write_case(
        tmp_path, "wrong_outcome",
        candidate=bad,
        expected={"schema_validation": "pass"},
    )
    result = evaluate_case(load_case(case_dir))
    assert not result.passed


# --- Scientific review checks -------------------------------------------


def test_must_have_codes_passes_when_present(tmp_path):
    case_dir = _write_case(
        tmp_path, "have_codes",
        candidate=_valid_candidate(),
        expected={
            "schema_validation": "pass",
            "scientific_review": {
                "must_have_codes": ["RECHARGE_INTERPRETATION_CAVEAT"],
            },
        },
    )
    result = evaluate_case(load_case(case_dir))
    assert result.passed, result.failures


def test_must_not_have_codes_failure_reports_leaked_code(tmp_path):
    # IC_WC_BELOW_THETA_R is critical-triggering — make a candidate that
    # triggers it.
    bad = _valid_candidate()
    bad["initial_condition"] = {"type": "water_content", "value": 0.001}
    case_dir = _write_case(
        tmp_path, "leaked_code",
        candidate=bad,
        expected={
            "schema_validation": "pass",
            "scientific_review": {
                "must_not_have_codes": ["IC_WC_BELOW_THETA_R"],
            },
        },
    )
    result = evaluate_case(load_case(case_dir))
    assert not result.passed
    assert any("must_not_have_codes" in f for f in result.failures)


def test_max_critical_zero_enforced(tmp_path):
    bad = _valid_candidate()
    bad["initial_condition"] = {"type": "water_content", "value": 0.001}
    case_dir = _write_case(
        tmp_path, "max_crit",
        candidate=bad,
        expected={
            "schema_validation": "pass",
            "scientific_review": {"max_critical": 0},
        },
    )
    result = evaluate_case(load_case(case_dir))
    assert not result.passed


# --- Raw JSON checks ----------------------------------------------------


def test_raw_json_must_not_contain_keys_pass_and_fail(tmp_path):
    # Passing: keys absent.
    case_a = _write_case(
        tmp_path, "raw_pass",
        candidate=_valid_candidate(),
        expected={
            "schema_validation": "pass",
            "raw_json": {"must_not_contain_keys": ["heat_transport"]},
        },
    )
    assert evaluate_case(load_case(case_a)).passed

    # Failing: heat_transport silently embedded.
    bad = _valid_candidate()
    bad["heat_transport"] = {"enabled": True}  # ignored by pydantic, but raw JSON has it.
    case_b = _write_case(
        tmp_path, "raw_fail",
        candidate=bad,
        expected={
            "schema_validation": "pass",
            "raw_json": {"must_not_contain_keys": ["heat_transport"]},
        },
    )
    result = evaluate_case(load_case(case_b))
    assert not result.passed
    assert any("must_not_contain_keys" in f for f in result.failures)


def test_raw_json_must_contain_keys_enforced(tmp_path):
    case_dir = _write_case(
        tmp_path, "raw_must_contain",
        candidate=_valid_candidate(),
        expected={
            "schema_validation": "pass",
            "raw_json": {"must_contain_keys": ["nonexistent_top_level"]},
        },
    )
    result = evaluate_case(load_case(case_dir))
    assert not result.passed
    assert any("must_contain_keys" in f for f in result.failures)


# --- Missing candidate ---------------------------------------------------


def test_missing_candidate_file_reported_not_raised(tmp_path):
    case_dir = _write_case(
        tmp_path, "no_candidate",
        candidate=None,
        expected={"schema_validation": "pass"},
    )
    result = evaluate_case(load_case(case_dir))
    assert not result.passed
    assert result.schema_validation == "missing_candidate"
    assert any("candidate config not found" in f for f in result.failures)


# --- Aggregate API ------------------------------------------------------


def test_evaluate_all_aggregates_counts(tmp_path):
    _write_case(tmp_path, "a",
                candidate=_valid_candidate(),
                expected={"schema_validation": "pass"})
    _write_case(tmp_path, "b",
                candidate=_valid_candidate(),
                expected={"schema_validation": "pass"})
    bad = _valid_candidate()
    bad["van_genuchten"][0].pop("n")
    _write_case(tmp_path, "c",
                candidate=bad,
                expected={"schema_validation": "pass"})  # expects pass but it'll fail

    result = evaluate_all(tmp_path)
    assert result.counts["total"] == 3
    assert result.counts["passed"] == 2
    assert result.counts["failed"] == 1


def test_render_markdown_lists_each_case_id_and_total(tmp_path):
    _write_case(tmp_path, "ok_case",
                candidate=_valid_candidate(),
                expected={"schema_validation": "pass"})
    bad = _valid_candidate()
    bad["van_genuchten"][0].pop("n")
    _write_case(tmp_path, "fail_case",
                candidate=bad,
                expected={"schema_validation": "pass"})

    result = evaluate_all(tmp_path)
    text = render_markdown(result)
    assert "Total: 2" in text
    assert "Passed: 1" in text
    assert "Failed: 1" in text
    assert "ok_case" in text
    assert "fail_case" in text
    # Failed section enumerates the failing case_id explicitly.
    assert "## Failed cases" in text


def test_result_to_dict_round_trip_shape(tmp_path):
    _write_case(tmp_path, "x",
                candidate=_valid_candidate(),
                expected={"schema_validation": "pass"})
    result = evaluate_all(tmp_path)
    payload = result_to_dict(result)
    assert payload["schema_version"] == SCHEMA_VERSION
    assert set(payload.keys()) == {"schema_version", "counts", "cases"}
    assert payload["counts"]["total"] == 1


def test_supported_feature_keys_lists_known_extractors():
    keys = supported_feature_keys()
    assert "upper_boundary_type" in keys
    assert "soil_layer_count" in keys
    assert "has_atmospheric_csv" in keys
