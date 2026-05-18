"""Integration test: every canonical prompt-to-config benchmark case must pass.

If a case ever stops passing, this test fails with the case_id and the
specific failure reasons. New cases under benchmarks/prompt_to_config/
cases/ are picked up automatically.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hydrus_agent.prompt_benchmark import (
    evaluate_all,
    evaluate_case,
    load_case,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = PROJECT_ROOT / "benchmarks" / "prompt_to_config" / "cases"


def _case_dirs():
    if not CASES_DIR.is_dir():
        return []
    return sorted(
        [p for p in CASES_DIR.iterdir() if p.is_dir() and (p / "case.json").is_file()],
        key=lambda p: p.name,
    )


@pytest.mark.parametrize("case_dir", _case_dirs(), ids=lambda p: p.name)
def test_canonical_case_passes(case_dir):
    case = load_case(case_dir)
    result = evaluate_case(case)
    assert result.passed, (
        f"{case.case_id} failed:\n  - " + "\n  - ".join(result.failures)
    )


def test_canonical_cases_directory_is_populated():
    """Guard against an empty cases directory silently producing zero parametrised
    runs."""
    assert _case_dirs(), f"No canonical cases found under {CASES_DIR}"


def test_evaluate_all_canonical_cases_pass_summary():
    result = evaluate_all(CASES_DIR)
    assert result.counts["failed"] == 0, (
        f"{result.counts['failed']} canonical case(s) failed:\n"
        + "\n".join(
            f"  - {c.case_id}: {c.failures}"
            for c in result.cases if not c.passed
        )
    )
    assert result.counts["total"] >= 11
