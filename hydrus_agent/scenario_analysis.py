"""Scenario comparison reporting for completed scenario batches.

This module is post-processing only. It reads an existing
``scenario_summary.csv`` created by ``scenario_runner`` and writes a Markdown
comparison report plus optional summary plots.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any, Iterable


SCENARIO_SUMMARY_CSV = "scenario_summary.csv"
SCENARIO_REPORT_MD = "scenario_report.md"

INFILTRATION_COLUMN = "final_sum_Infil"
BOTTOM_FLUX_COLUMN = "final_sum_vBot"
WARNING_COUNT_COLUMN = "warning_count"


class ScenarioAnalysisError(ValueError):
    """Raised when scenario comparison inputs are missing or invalid."""


def generate_scenario_comparison_report(batch_dir: Path | str) -> Path:
    """Generate a scenario comparison report from an existing batch folder."""
    batch_dir = Path(batch_dir)
    summary_path = batch_dir / SCENARIO_SUMMARY_CSV
    if not summary_path.is_file():
        raise ScenarioAnalysisError(f"Missing scenario_summary.csv: {summary_path}")

    rows = _read_summary_rows(summary_path)
    if not rows:
        raise ScenarioAnalysisError(f"No scenarios found in {summary_path}")
    if "scenario_id" not in rows[0]:
        raise ScenarioAnalysisError("scenario_summary.csv must include a scenario_id column.")

    enriched = [_enrich_row(row) for row in rows]
    report_path = batch_dir / SCENARIO_REPORT_MD
    figure_paths = _generate_optional_plots(batch_dir, enriched)
    report_path.write_text(
        _build_report(batch_dir, enriched, figure_paths),
        encoding="utf-8",
    )
    return report_path


def _read_summary_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _enrich_row(row: dict[str, str]) -> dict[str, Any]:
    enriched: dict[str, Any] = dict(row)
    enriched["warning_count_value"] = _to_number(row.get(WARNING_COUNT_COLUMN))
    enriched["infiltration_value"] = _to_number(row.get(INFILTRATION_COLUMN))
    enriched["bottom_flux_value"] = _to_number(row.get(BOTTOM_FLUX_COLUMN))
    rmse_values = [
        value for key, raw in row.items()
        if key.lower().endswith("_rmse")
        for value in [_to_number(raw)]
        if value is not None
    ]
    enriched["field_rmse_mean"] = (
        sum(rmse_values) / len(rmse_values) if rmse_values else None
    )
    return enriched


def _build_report(
    batch_dir: Path,
    rows: list[dict[str, Any]],
    figure_paths: list[Path],
) -> str:
    pass_count = sum(1 for row in rows if row.get("status") == "pass")
    fail_count = sum(1 for row in rows if row.get("status") == "fail")
    sorted_rows = _sort_for_table(rows)
    best_rmse = _best_by(rows, "field_rmse_mean", smallest=True)
    largest_infil = _best_by(rows, "infiltration_value", smallest=False)
    largest_bottom_flux = _largest_abs(rows, "bottom_flux_value")
    warning_rows = [
        row for row in rows
        if row.get("status") != "pass"
        or ((row.get("warning_count_value") or 0) > 0)
    ]

    lines = [
        "# Scenario Comparison Report",
        "",
        f"Batch ID: `{batch_dir.name}`",
        "",
        "## Summary",
        "",
        f"- Number of scenarios: {len(rows)}",
        f"- Passed: {pass_count}",
        f"- Failed: {fail_count}",
        f"- Scenario IDs: {', '.join(_scenario_id(row) for row in rows)}",
        f"- Best field-data RMSE: {_format_best(best_rmse, 'field_rmse_mean', lower_is_better=True)}",
        f"- Largest infiltration: {_format_best(largest_infil, 'infiltration_value')}",
        f"- Largest absolute bottom flux: {_format_best(largest_bottom_flux, 'bottom_flux_value')}",
        "",
        "## Scenario Table",
        "",
        _markdown_table(
            [
                "scenario_id",
                "status",
                "warning_count",
                INFILTRATION_COLUMN,
                BOTTOM_FLUX_COLUMN,
                "field_rmse_mean",
            ],
            [
                [
                    _scenario_id(row),
                    str(row.get("status", "")),
                    _format_cell(row.get(WARNING_COUNT_COLUMN)),
                    _format_number(row.get("infiltration_value")),
                    _format_number(row.get("bottom_flux_value")),
                    _format_number(row.get("field_rmse_mean")),
                ]
                for row in sorted_rows
            ],
        ),
        "",
        "## Interpretation Notes",
        "",
        _interpretation_notes(best_rmse, largest_infil, largest_bottom_flux),
        "",
        "## Warnings And Failed Scenarios",
        "",
    ]
    if warning_rows:
        lines.extend([
            _markdown_table(
                ["scenario_id", "status", "warning_count"],
                [
                    [
                        _scenario_id(row),
                        str(row.get("status", "")),
                        _format_cell(row.get(WARNING_COUNT_COLUMN)),
                    ]
                    for row in warning_rows
                ],
            ),
            "",
        ])
    else:
        lines.extend(["No failed scenarios or warning counts were reported.", ""])

    lines.extend(["## Figures", ""])
    if figure_paths:
        for path in figure_paths:
            lines.append(f"- `{path.relative_to(batch_dir)}`")
    else:
        lines.append("No comparison figures were generated.")
    lines.append("")
    return "\n".join(lines)


def _sort_for_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if any(row.get("field_rmse_mean") is not None for row in rows):
        return sorted(
            rows,
            key=lambda row: (
                row.get("field_rmse_mean") is None,
                row.get("field_rmse_mean") or math.inf,
                _scenario_id(row),
            ),
        )
    if any(row.get("infiltration_value") is not None for row in rows):
        return sorted(
            rows,
            key=lambda row: (
                row.get("infiltration_value") is None,
                -(row.get("infiltration_value") or -math.inf),
                _scenario_id(row),
            ),
        )
    return sorted(rows, key=_scenario_id)


def _best_by(
    rows: Iterable[dict[str, Any]],
    key: str,
    *,
    smallest: bool,
) -> dict[str, Any] | None:
    candidates = [row for row in rows if row.get(key) is not None]
    if not candidates:
        return None
    return min(candidates, key=lambda row: row[key]) if smallest else max(candidates, key=lambda row: row[key])


def _largest_abs(rows: Iterable[dict[str, Any]], key: str) -> dict[str, Any] | None:
    candidates = [row for row in rows if row.get(key) is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda row: abs(row[key]))


def _interpretation_notes(
    best_rmse: dict[str, Any] | None,
    largest_infil: dict[str, Any] | None,
    largest_bottom_flux: dict[str, Any] | None,
) -> str:
    notes = [
        "This report compares completed scenario outputs only. It does not rerun HYDRUS, calibrate parameters, or optimise the model.",
    ]
    if best_rmse is None:
        notes.append("Field-data RMSE metrics were not available in the scenario summary.")
    else:
        notes.append(
            f"`{_scenario_id(best_rmse)}` has the lowest mean field-data RMSE among scenarios with RMSE metrics."
        )
    if largest_infil is not None:
        notes.append(
            f"`{_scenario_id(largest_infil)}` has the largest cumulative infiltration metric."
        )
    if largest_bottom_flux is not None:
        notes.append(
            f"`{_scenario_id(largest_bottom_flux)}` has the largest absolute cumulative bottom-flux metric."
        )
    return "\n".join(f"- {note}" for note in notes)


def _generate_optional_plots(batch_dir: Path, rows: list[dict[str, Any]]) -> list[Path]:
    figures_dir = batch_dir / "figures"
    generated: list[Path] = []
    generated.extend(_try_bar_plot(
        figures_dir,
        rows,
        metric_key="bottom_flux_value",
        title="Scenario cumulative bottom flux",
        ylabel=BOTTOM_FLUX_COLUMN,
        filename="scenario_metric_bar_bottom_flux.png",
    ))
    generated.extend(_try_bar_plot(
        figures_dir,
        rows,
        metric_key="infiltration_value",
        title="Scenario cumulative infiltration",
        ylabel=INFILTRATION_COLUMN,
        filename="scenario_metric_bar_infiltration.png",
    ))
    generated.extend(_try_bar_plot(
        figures_dir,
        rows,
        metric_key="field_rmse_mean",
        title="Scenario field-data RMSE",
        ylabel="mean RMSE",
        filename="scenario_field_rmse_comparison.png",
    ))
    return generated


def _try_bar_plot(
    figures_dir: Path,
    rows: list[dict[str, Any]],
    *,
    metric_key: str,
    title: str,
    ylabel: str,
    filename: str,
) -> list[Path]:
    candidates = [(row, row.get(metric_key)) for row in rows if row.get(metric_key) is not None]
    if not candidates:
        return []
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except Exception:
        return []

    figures_dir.mkdir(parents=True, exist_ok=True)
    path = figures_dir / filename
    labels = [_scenario_id(row) for row, _ in candidates]
    values = [value for _, value in candidates]
    fig, ax = plt.subplots(figsize=(max(6, 0.8 * len(labels)), 4))
    ax.bar(labels, values, color="#3b82f6")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("scenario")
    ax.tick_params(axis="x", rotation=35)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return [path]


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def _format_best(
    row: dict[str, Any] | None,
    key: str,
    *,
    lower_is_better: bool = False,
) -> str:
    if row is None:
        return "not available"
    suffix = " (lower is better)" if lower_is_better else ""
    return f"`{_scenario_id(row)}` ({_format_number(row.get(key))}){suffix}"


def _format_cell(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value)


def _format_number(value: Any) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):.6g}"
    except (TypeError, ValueError):
        return str(value)


def _to_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _scenario_id(row: dict[str, Any]) -> str:
    return str(row.get("scenario_id", ""))
