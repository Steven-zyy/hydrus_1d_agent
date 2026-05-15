"""HYDRUS-1D Markdown report generation (milestone 6).

Stitches together the outputs of the milestone 1-5.5 modules into a single
``report.md`` per case. The report intentionally:

    * Uses Markdown only (no PDF, no HTML, no DOCX).
    * Is read-only with respect to HYDRUS files.
    * Composes content already produced by other modules; no new analysis.
    * Embeds figures with **relative** links so the report is portable.
"""

from __future__ import annotations

import datetime as _dt
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import pandas as pd

from hydrus_agent.schema import ModelConfig

logger = logging.getLogger(__name__)


REPORT_FILENAME = "report.md"


def generate_markdown_report(
    config: ModelConfig,
    run_dir: Path,
    outputs: Dict[str, Optional[pd.DataFrame]],
    qc_summary: Dict[str, Any],
    figures: Sequence[Path],
    *,
    run_log_path: Optional[Path] = None,
) -> Path:
    """Write a Markdown report for ``config`` into ``run_dir / report.md``.

    Parameters
    ----------
    config
        The validated ``ModelConfig`` (from milestone 1).
    run_dir
        The case run folder (e.g. ``runs/case_002``).
    outputs
        Output DataFrame dict from ``output_reader.read_outputs``.
    qc_summary
        Report dict from ``qc.assess_run_quality``.
    figures
        Iterable of figure paths. Linked relative to ``run_dir`` so the
        report is portable.
    run_log_path
        Optional path of ``hydrus_run.log``. If provided and present, a
        single-line summary is added to the execution section.

    Returns the path of the report file (always ``run_dir / report.md``).
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / REPORT_FILENAME

    sections: List[str] = []
    sections.append(_format_header(config))
    sections.append(_format_reliability_warning_section(qc_summary))
    sections.append(_format_setup_section(config))
    sections.append(_format_execution_section(run_dir, run_log_path))
    sections.append(_format_outputs_section(outputs))
    sections.append(_format_qc_section(qc_summary))
    sections.append(_format_field_comparison_section(qc_summary))
    sections.append(_format_figures_section(figures, run_dir))
    sections.append(_format_interpretation_section(qc_summary))

    body = "\n\n".join(s for s in sections if s).rstrip() + "\n"
    report_path.write_text(body, encoding="utf-8")
    return report_path


# --- Section formatters --------------------------------------------------


def _format_header(config: ModelConfig) -> str:
    now = _dt.datetime.now().isoformat(timespec="seconds")
    lines = [
        f"# HYDRUS-1D Run Report — {config.case_id}",
        "",
        f"- **Project:** {config.project_name}",
        f"- **Case ID:** `{config.case_id}`",
        f"- **Generated:** {now}",
    ]
    return "\n".join(lines)


def _format_reliability_warning_section(qc_summary: Dict[str, Any]) -> str:
    hydrus_status = qc_summary.get("hydrus_status", {}) or {}
    reliability = qc_summary.get("reliability", {}) or {}
    warnings: List[str] = []

    if hydrus_status.get("numerical_failure_detected"):
        rc = hydrus_status.get("return_code")
        warnings.append(
            f"HYDRUS returned code {rc}, but numerical failure was detected "
            "in Error.msg."
        )
        if hydrus_status.get("failure_reason"):
            warnings.append(f"Failure reason: {hydrus_status['failure_reason']}")
        if hydrus_status.get("error_excerpt"):
            warnings.append(f"Error.msg excerpt: {hydrus_status['error_excerpt']}")
    if reliability.get("qc_status") == "failed" or qc_summary.get("ok") is False:
        warnings.append("QC status: failed.")

    if not warnings:
        return ""

    out = ["## Run Reliability Warning", ""]
    out.extend(f"- {warning}" for warning in warnings)
    out.append("- Results may be incomplete or unreliable.")
    out.append("")
    out.append(
        "This status separates process execution from HYDRUS numerical "
        "convergence and post-run QC. Output files may exist even when the "
        "run should not be treated as reliable."
    )
    return "\n".join(out)


def _format_setup_section(config: ModelConfig) -> str:
    out: List[str] = ["## Simulation setup"]

    # Time
    st = config.simulation_time
    out.append("")
    out.append("### Time")
    out.append("")
    out.append(f"- Start (`t_init`): {st.t_init} {st.units.value}")
    out.append(f"- End (`t_end`): {st.t_end} {st.units.value}")
    out.append(f"- Initial step (`dt_init`): {st.dt_init} {st.units.value}")

    # Soil profile
    out.append("")
    out.append("### Soil profile")
    out.append("")
    out.append("| Layer | depth_top [m] | depth_bottom [m] | material_id |")
    out.append("|---|---:|---:|---:|")
    for i, layer in enumerate(config.soil_profile, start=1):
        out.append(f"| {i} | {layer.depth_top} | {layer.depth_bottom} | "
                   f"{layer.material_id} |")

    # van Genuchten
    out.append("")
    out.append("### van Genuchten parameters")
    out.append("")
    out.append("| material_id | θr | θs | α [1/L] | n | Ks [L/T] | l |")
    out.append("|---:|---:|---:|---:|---:|---:|---:|")
    for vg in sorted(config.van_genuchten, key=lambda v: v.material_id):
        out.append(
            f"| {vg.material_id} | {vg.theta_r} | {vg.theta_s} | {vg.alpha} | "
            f"{vg.n} | {vg.Ks} | {vg.l} |"
        )

    # Boundaries
    out.append("")
    out.append("### Boundary conditions")
    out.append("")
    upper_extra = ""
    if config.upper_boundary.flux is not None:
        upper_extra = f", flux = {config.upper_boundary.flux}"
    if config.upper_boundary.head is not None:
        upper_extra += f", head = {config.upper_boundary.head}"
    out.append(f"- **Upper:** `{config.upper_boundary.type.value}`{upper_extra}")
    lower_extra = ""
    if config.lower_boundary.flux is not None:
        lower_extra = f", flux = {config.lower_boundary.flux}"
    if config.lower_boundary.head is not None:
        lower_extra += f", head = {config.lower_boundary.head}"
    out.append(f"- **Lower:** `{config.lower_boundary.type.value}`{lower_extra}")

    # Initial condition
    out.append("")
    out.append("### Initial condition")
    out.append("")
    out.append(f"- Type: `{config.initial_condition.type.value}`")
    out.append(f"- Value: {config.initial_condition.value}")
    if config.initial_condition.profile:
        out.append("- Profile:")
        for point in config.initial_condition.profile:
            out.append(f"  - depth {point.depth} m: {point.value}")

    # Observation depths
    out.append("")
    out.append("### Observation depths")
    out.append("")
    if config.observation_depths:
        out.append(f"{list(config.observation_depths)}")
    else:
        out.append("(none)")

    # Output settings
    out.append("")
    out.append("### Output settings")
    out.append("")
    if config.output_settings.print_times:
        out.append(f"- Print times: {list(config.output_settings.print_times)}")
    if config.output_settings.print_interval is not None:
        out.append(f"- Print interval: {config.output_settings.print_interval}")

    return "\n".join(out)


def _format_execution_section(
    run_dir: Path,
    run_log_path: Optional[Path],
) -> str:
    out: List[str] = ["## Execution"]
    out.append("")
    out.append(f"- Run folder: `{run_dir}`")

    log_path = run_log_path
    if log_path is None:
        candidate = run_dir / "logs" / "hydrus_run.log"
        if candidate.is_file():
            log_path = candidate

    if log_path is not None and Path(log_path).is_file():
        text = Path(log_path).read_text(encoding="utf-8", errors="replace")
        rc = _scan_for_field(text, "return code:")
        launch = _scan_for_field(text, "launch mode:")
        cmd = _scan_for_field(text, "command:")
        note = _scan_for_field(text, "note:")
        out.append(f"- Run log: `{log_path}`")
        if launch:
            out.append(f"- Launch mode: `{launch}`")
        if cmd:
            out.append(f"- Command: `{cmd}`")
        if rc:
            out.append(f"- Return code: `{rc}`")
        if note:
            out.append(f"- Note: {note}")
    else:
        out.append("- Run log: not found (was the executable run?)")

    return "\n".join(out)


def _scan_for_field(text: str, prefix: str) -> Optional[str]:
    """First line that starts with ``prefix`` (after stripping leading
    whitespace), with the prefix removed."""
    for line in text.splitlines():
        s = line.strip()
        if s.lower().startswith(prefix.lower()):
            return s[len(prefix):].strip()
    return None


def _format_outputs_section(
    outputs: Dict[str, Optional[pd.DataFrame]],
) -> str:
    out: List[str] = ["## Outputs"]
    out.append("")
    out.append("| File | Rows × Cols | First columns |")
    out.append("|---|---|---|")
    preferred = (
        "Balance.out", "T_Level.out", "Run_Inf.out",
        "Obs_Node.out", "Nod_Inf.out",
    )
    extra = tuple(name for name in sorted(outputs) if name not in preferred)
    for name in (*preferred, *extra):
        df = outputs.get(name)
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            out.append(f"| `{name}` | (empty / missing) | – |")
            continue
        cols_preview = ", ".join(str(c) for c in df.columns[:6])
        if df.shape[1] > 6:
            cols_preview += ", …"
        out.append(f"| `{name}` | {len(df)} × {df.shape[1]} | {cols_preview} |")
    return "\n".join(out)


def _format_qc_section(qc_summary: Dict[str, Any]) -> str:
    out: List[str] = ["## Quality control"]
    out.append("")
    out.append(f"- **Overall:** {'OK' if qc_summary.get('ok') else 'WARNINGS'}")

    wb = qc_summary.get("water_balance", {})
    if wb.get("available"):
        if "max_abs_error_pct" in wb:
            out.append(f"- max |WatBalR|: {wb['max_abs_error_pct']:.3f} %")
        if "final_error_pct" in wb:
            out.append(f"- final WatBalR: {wb['final_error_pct']:.3f} %")
        if "max_abs_wat_bal_t" in wb:
            out.append(f"- max |WatBalT|: {wb['max_abs_wat_bal_t']:.3e}")

    cf = qc_summary.get("cumulative_fluxes", {})
    if cf.get("source"):
        out.append(f"- cumulative fluxes (from `{cf['source']}`):")
        for k in ("final_sum_vTop", "final_sum_vBot", "final_sum_Infil",
                  "final_sum_Evap", "final_sum_RunOff",
                  "final_top_flux", "final_bot_flux"):
            if k in cf and isinstance(cf[k], (int, float)):
                out.append(f"  - `{k}`: {cf[k]:.4e}")

    obs = qc_summary.get("observation_nodes", {})
    if obs.get("present"):
        out.append(f"- observation nodes: {obs['node_count']} "
                   f"(IDs {obs.get('node_ids', [])}), "
                   f"{obs['row_count']} rows")
    prof = qc_summary.get("profiles", {})
    if prof.get("present"):
        out.append(f"- profiles: {prof['time_count']} times × "
                   f"{prof['node_count']} nodes = {prof['row_count']} rows")
    solute = qc_summary.get("solute", {})
    if solute.get("available"):
        out.append("- solute outputs: available")
        obs_sol = solute.get("observation_concentration", {})
        if obs_sol.get("available"):
            out.append(
                f"  - observation concentration nodes: "
                f"{len(obs_sol.get('nodes', {}))}"
            )
        for name, info in solute.get("flux_tables", {}).items():
            out.append(f"  - `{name}`: {info.get('rows', 0)} rows")
            if "final_sum_cvTop" in info:
                out.append(
                    f"    - final cumulative top solute flux: "
                    f"{info['final_sum_cvTop']:.4e}"
                )
            if "final_sum_cvBot" in info:
                out.append(
                    f"    - final cumulative bottom solute flux: "
                    f"{info['final_sum_cvBot']:.4e}"
                )
    conv = qc_summary.get("convergence", {})
    if conv.get("present"):
        if conv.get("all_converged"):
            out.append(f"- convergence: {conv.get('total_steps', 0)}/"
                       f"{conv.get('total_steps', 0)} steps converged")
        else:
            out.append(
                f"- convergence: {conv.get('converged_steps', 0)}/"
                f"{conv.get('total_steps', 0)} converged "
                f"({conv.get('non_converged_steps', 0)} failed)"
            )

    warnings = qc_summary.get("warnings", []) or []
    if warnings:
        out.append("")
        out.append(f"### Warnings ({len(warnings)})")
        out.append("")
        for w in warnings:
            out.append(f"- {w}")
    else:
        out.append("- warnings: none")

    return "\n".join(out)


def _format_field_comparison_section(qc_summary: Dict[str, Any]) -> str:
    field = qc_summary.get("field_comparison", {})
    if not field or not field.get("requested"):
        return ""
    out: List[str] = ["## Field Data Comparison"]
    out.append("")
    if not field.get("available"):
        out.append("No matched field-data comparison is available for this run.")
        warnings = field.get("warnings", []) or []
        if warnings:
            out.append("")
            out.append("Warnings:")
            for warning in warnings:
                out.append(f"- {warning}")
        return "\n".join(out)

    out.append(f"- Field data: `{field.get('field_data_path', '')}`")
    out.append(f"- Matched rows: {field.get('matched_rows', 0)}")
    out.append("")
    out.append("| Variable | Node | Matched points | RMSE | MAE | Bias | Correlation |")
    out.append("|---|---:|---:|---:|---:|---:|---:|")
    for variable, info in field.get("variables", {}).items():
        for node, metrics in info.get("nodes", {}).items():
            out.append(
                f"| {variable} | {node} | "
                f"{metrics.get('matched_count', 0)} | "
                f"{_fmt_metric(metrics.get('rmse'))} | "
                f"{_fmt_metric(metrics.get('mae'))} | "
                f"{_fmt_metric(metrics.get('bias'))} | "
                f"{_fmt_metric(metrics.get('correlation'))} |"
            )
    if field.get("figures"):
        out.append("")
        out.append("Overlay figures are included in the Figures section.")
    return "\n".join(out)


def _fmt_metric(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.4g}"
    return "n/a"


def _format_figures_section(
    figures: Iterable[Path],
    run_dir: Path,
) -> str:
    figures = list(figures)
    out: List[str] = ["## Figures"]
    if not figures:
        out.append("")
        out.append("No figures were generated for this run.")
        return "\n".join(out)
    out.append("")
    for path in figures:
        rel = _relative_to_run(path, run_dir)
        out.append(f"### {Path(path).stem.replace('_', ' ')}")
        out.append("")
        out.append(f"![{Path(path).stem}]({rel})")
        out.append("")
    return "\n".join(out).rstrip()


def _relative_to_run(path: Path, run_dir: Path) -> str:
    """Build a forward-slash relative path from ``run_dir`` to ``path``.
    Falls back to the absolute path if ``path`` is not under ``run_dir``."""
    try:
        rel = Path(path).resolve().relative_to(Path(run_dir).resolve())
        return rel.as_posix()
    except ValueError:
        return Path(path).as_posix()


def _format_interpretation_section(qc_summary: Dict[str, Any]) -> str:
    out: List[str] = ["## Interpretation"]
    out.append("")

    pieces: List[str] = []
    hydrus_status = qc_summary.get("hydrus_status", {}) or {}
    reliability = qc_summary.get("reliability", {}) or {}
    hydrus_numerical_status = (
        reliability.get("hydrus_numerical_status")
        or hydrus_status.get("status")
        or "unknown"
    )
    qc_status = reliability.get("qc_status") or (
        "failed" if qc_summary.get("ok") is False else "unknown"
    )
    overall_status = reliability.get("overall_status") or "unknown"
    hydrus_failed = (
        hydrus_status.get("numerical_failure_detected") is True
        or hydrus_status.get("status") == "failed"
        or reliability.get("hydrus_numerical_status") == "failed"
    )
    qc_failed = (
        reliability.get("qc_status") == "failed"
        or qc_summary.get("ok") is False
    )
    overall_failed = reliability.get("overall_status") == "failed"
    reliability_limited = hydrus_failed or qc_failed or overall_failed

    conv = qc_summary.get("convergence", {})
    if conv.get("present"):
        total_steps = conv.get("total_steps", 0)
        converged_steps = conv.get("converged_steps", total_steps)
        if conv.get("all_converged"):
            if hydrus_failed:
                pieces.append(
                    "The parsed output-step records report "
                    f"{converged_steps}/{total_steps} converged steps; "
                    "however, HYDRUS Error.msg indicates a later numerical "
                    "failure. Therefore, the convergence summary should be "
                    "interpreted as incomplete and does not confirm a fully "
                    "reliable simulation."
                )
            elif qc_failed or overall_failed:
                pieces.append(
                    "The parsed output-step records report "
                    f"{converged_steps}/{total_steps} converged steps, but "
                    f"QC status is {qc_status} and overall reliability is "
                    f"{overall_status}; this convergence summary alone does "
                    "not confirm a fully reliable simulation."
                )
            else:
                pieces.append(
                    f"All {total_steps} solver steps converged."
                )
        else:
            pieces.append(
                f"{conv.get('non_converged_steps', 0)} of "
                f"{total_steps} solver steps did not converge — "
                "the run may not be physically reliable."
            )

    wb = qc_summary.get("water_balance", {})
    if wb.get("available") and "max_abs_error_pct" in wb:
        max_pct = wb["max_abs_error_pct"]
        if max_pct < 0.1:
            if reliability_limited:
                pieces.append(
                    "Parsed water-balance records show low error "
                    f"(max |WatBalR| = {max_pct:.3f} %), but this check "
                    "alone does not confirm overall reliability."
                )
            else:
                pieces.append(f"Water balance is excellent "
                              f"(max |WatBalR| = {max_pct:.3f} %).")
        elif max_pct < 1.0:
            if reliability_limited:
                pieces.append(
                    "Parsed water-balance records show moderate error "
                    f"(max |WatBalR| = {max_pct:.3f} %), but this check "
                    "alone does not confirm overall reliability."
                )
            else:
                pieces.append(f"Water balance is acceptable "
                              f"(max |WatBalR| = {max_pct:.3f} %).")
        else:
            pieces.append(
                f"Water balance error of {max_pct:.3f} % is high — "
                "consider refining the time step or mesh."
            )

    cf = qc_summary.get("cumulative_fluxes", {})
    if cf.get("source") == "T_Level.out":
        infil = cf.get("final_sum_Infil")
        v_bot = cf.get("final_sum_vBot")
        if isinstance(infil, (int, float)) and isinstance(v_bot, (int, float)):
            pieces.append(
                f"Final cumulative infiltration was {infil:.3e} L; "
                f"final cumulative bottom flux was {v_bot:.3e} L."
            )

    obs = qc_summary.get("observation_nodes", {})
    if obs.get("present"):
        pieces.append(
            f"Observation-node time series available for "
            f"{obs['node_count']} node(s)."
        )
    prof = qc_summary.get("profiles", {})
    if prof.get("present"):
        pieces.append(
            f"Spatial profiles available at {prof['time_count']} times."
        )
    solute = qc_summary.get("solute", {})
    if solute.get("available"):
        parts = []
        if solute.get("observation_concentration", {}).get("available"):
            parts.append("observation-node concentrations")
        if solute.get("profile_concentration", {}).get("available"):
            parts.append("profile concentrations")
        if solute.get("flux_tables"):
            parts.append("solute flux summaries")
        if parts:
            pieces.append("Solute outputs include " + ", ".join(parts) + ".")

    if reliability_limited and pieces:
        pieces.append(
            "Reliability status: HYDRUS numerical status is "
            f"{hydrus_numerical_status}, QC status is {qc_status}, and "
            f"overall reliability is {overall_status}."
        )

    warnings = qc_summary.get("warnings", []) or []
    has_substantive = bool(pieces)
    if warnings and has_substantive:
        pieces.append(
            f"{len(warnings)} QC warning(s) were raised — see the "
            "Warnings section above for details."
        )

    if not has_substantive:
        msg = ("No outputs were available for automatic interpretation. "
               "Run HYDRUS first (`--prepare-input --run`) and then re-run "
               "the report.")
        if warnings:
            msg += (f" Additionally, {len(warnings)} QC warning(s) were "
                    "raised — see the Warnings section above for details.")
        out.append(msg)
    else:
        out.append(" ".join(pieces))
    return "\n".join(out)
