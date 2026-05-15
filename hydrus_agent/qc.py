"""HYDRUS-1D run quality control (milestone 5.5).

Lightweight rule-based checks that audit the parsed-output DataFrames and
the per-case figure folder. The module is intentionally:

    * Read-only — never modifies HYDRUS files or DataFrames.
    * Transparent — every warning is a plain string with the offending
      table/quantity named.
    * Deterministic — same inputs produce the same dict every time.

It does NOT attempt to fix bad runs or kick off retries. The output is a
JSON-serialisable dict suitable for milestone 6 (report generation) or for
human review via ``main.py --qc``.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


# Figures we consider "standard" — i.e. the set produced by
# plotter.generate_standard_plots when all 5 output tables are populated.
EXPECTED_FIGURE_NAMES = (
    "balance_storage_vs_time.png",
    "instantaneous_fluxes.png",
    "cumulative_water_balance.png",
    "obs_theta_vs_time.png",
    "obs_head_vs_time.png",
    "moisture_profiles.png",
    "pressure_head_profiles.png",
    "moisture_contour.png",
    "run_diagnostics.png",
)

CANONICAL_OUTPUT_NAMES = (
    "Obs_Node.out",
    "T_Level.out",
    "Balance.out",
    "Nod_Inf.out",
    "Run_Inf.out",
)

# Threshold (in percent) above which we flag a water balance error as
# "unusually large". HYDRUS's WatBalR is reported in percent.
WATER_BALANCE_WARN_PCT = 1.0


# --- Helpers --------------------------------------------------------------


def _is_usable(df: Optional[pd.DataFrame]) -> bool:
    return df is not None and isinstance(df, pd.DataFrame) and not df.empty


def _safe_float(x) -> Optional[float]:
    """Return float(x) if finite, else None. Used so output dicts are
    JSON-serialisable (no NaN/Inf in the JSON)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def _count_nans(df: Optional[pd.DataFrame]) -> int:
    if not _is_usable(df):
        return 0
    return int(df.isna().sum().sum())


# --- Per-section assessors -----------------------------------------------


def _assess_tables(
    outputs: Dict[str, Optional[pd.DataFrame]],
    warnings: List[str],
) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    dynamic_names = [
        name for name in sorted(outputs)
        if name not in CANONICAL_OUTPUT_NAMES
    ]
    for name in (*CANONICAL_OUTPUT_NAMES, *dynamic_names):
        df = outputs.get(name)
        present = df is not None
        non_empty = _is_usable(df)
        if not present or df is None:
            out[name] = {"present": False, "non_empty": False,
                         "rows": 0, "columns": 0, "nan_count": 0}
            warnings.append(f"{name}: not in outputs dict")
            continue
        rows = len(df)
        cols = df.shape[1] if hasattr(df, "shape") else 0
        nan_count = _count_nans(df)
        out[name] = {
            "present": True,
            "non_empty": non_empty,
            "rows": rows,
            "columns": cols,
            "nan_count": nan_count,
        }
        if not non_empty:
            warnings.append(f"{name}: present but empty (0 rows)")
        # NaNs in Balance.out are expected at t=0 for wat_bal_t/wat_bal_r;
        # other tables flag NaN as unusual.
        if nan_count > 0 and name != "Balance.out":
            warnings.append(f"{name}: contains {nan_count} NaN value(s)")
    return out


def _assess_water_balance(
    balance_df: Optional[pd.DataFrame],
    warnings: List[str],
) -> Dict[str, Any]:
    """Inspect Balance.out for the WatBalR / WatBalT diagnostic columns."""
    if not _is_usable(balance_df):
        return {"available": False}

    res: Dict[str, Any] = {"available": True}

    if "wat_bal_r" in balance_df.columns:
        series = balance_df["wat_bal_r"].dropna()
        if not series.empty:
            res["final_error_pct"] = _safe_float(series.iloc[-1])
            res["max_abs_error_pct"] = _safe_float(series.abs().max())
            if res.get("max_abs_error_pct") is not None \
                    and res["max_abs_error_pct"] > WATER_BALANCE_WARN_PCT:
                warnings.append(
                    f"Balance.out: water balance error "
                    f"{res['max_abs_error_pct']:.3f}% exceeds threshold "
                    f"{WATER_BALANCE_WARN_PCT:.1f}%"
                )

    if "wat_bal_t" in balance_df.columns:
        series_t = balance_df["wat_bal_t"].dropna()
        if not series_t.empty:
            res["final_wat_bal_t"] = _safe_float(series_t.iloc[-1])
            res["max_abs_wat_bal_t"] = _safe_float(series_t.abs().max())

    return res


def _assess_cumulative_fluxes(
    outputs: Dict[str, Optional[pd.DataFrame]],
) -> Dict[str, Any]:
    """Pull final cumulative flux values from T_Level (preferred) or
    Balance.out as a fallback."""
    res: Dict[str, Any] = {}
    t_level = outputs.get("T_Level.out")

    if _is_usable(t_level):
        res["source"] = "T_Level.out"
        for col, key in (
            ("sum_vTop", "final_sum_vTop"),
            ("sum_vBot", "final_sum_vBot"),
            ("sum_Infil", "final_sum_Infil"),
            ("sum_Evap", "final_sum_Evap"),
            ("sum_RunOff", "final_sum_RunOff"),
        ):
            if col in t_level.columns:
                v = _safe_float(t_level[col].dropna().iloc[-1]) \
                    if not t_level[col].dropna().empty else None
                if v is not None:
                    res[key] = v
        return res

    balance = outputs.get("Balance.out")
    if _is_usable(balance):
        res["source"] = "Balance.out"
        # Balance has instantaneous top_flux/bot_flux — not strictly
        # cumulative, but we can still report the last observed values
        # so the dashboard is meaningful.
        for col, key in (("top_flux", "final_top_flux"),
                         ("bot_flux", "final_bot_flux")):
            if col in balance.columns:
                series = balance[col].dropna()
                if not series.empty:
                    res[key] = _safe_float(series.iloc[-1])
        return res

    res["source"] = None
    return res


def _assess_obs_nodes(
    obs_df: Optional[pd.DataFrame],
) -> Dict[str, Any]:
    if not _is_usable(obs_df):
        return {"present": False, "node_count": 0, "row_count": 0,
                "node_ids": []}
    node_ids: List[int] = []
    if "node" in obs_df.columns:
        node_ids = sorted(int(n) for n in obs_df["node"].unique())
    return {
        "present": True,
        "node_count": len(node_ids),
        "row_count": int(len(obs_df)),
        "node_ids": node_ids,
    }


def _assess_profiles(
    nod_df: Optional[pd.DataFrame],
) -> Dict[str, Any]:
    if not _is_usable(nod_df):
        return {"present": False, "time_count": 0, "node_count": 0,
                "row_count": 0}
    time_count = int(nod_df["time"].nunique()) if "time" in nod_df.columns else 0
    node_count = int(nod_df["node"].nunique()) if "node" in nod_df.columns else 0
    return {
        "present": True,
        "time_count": time_count,
        "node_count": node_count,
        "row_count": int(len(nod_df)),
    }


def _first_existing_column(
    df: Optional[pd.DataFrame],
    candidates: Iterable[str],
) -> Optional[str]:
    if not _is_usable(df):
        return None
    for col in candidates:
        if col in df.columns:
            return col
    return None


def _assess_solute(
    outputs: Dict[str, Optional[pd.DataFrame]],
) -> Dict[str, Any]:
    obs = outputs.get("Obs_Node.out")
    nod = outputs.get("Nod_Inf.out")
    conc_col = _first_existing_column(obs, ("conc", "conc_1"))
    profile_conc_col = _first_existing_column(nod, ("conc_1", "conc"))
    solute_outputs = {
        name: df for name, df in outputs.items()
        if name.lower().startswith("solute")
        and _is_usable(df)
    }

    res: Dict[str, Any] = {
        "available": bool(conc_col or profile_conc_col or solute_outputs),
        "observation_concentration": {"available": False, "nodes": {}},
        "profile_concentration": {"available": bool(profile_conc_col)},
        "flux_tables": {},
    }

    if conc_col and _is_usable(obs) and {"time", "node"}.issubset(obs.columns):
        nodes: Dict[str, Dict[str, Any]] = {}
        for node, sub in obs.sort_values("time").groupby("node"):
            series = sub[conc_col].dropna()
            if series.empty:
                continue
            positive = sub[sub[conc_col] > 1.0e-12]
            breakthrough = None
            if not positive.empty:
                breakthrough = _safe_float(positive["time"].iloc[0])
            nodes[str(int(node))] = {
                "final": _safe_float(series.iloc[-1]),
                "max": _safe_float(series.max()),
                "breakthrough_time": breakthrough,
            }
        res["observation_concentration"] = {
            "available": bool(nodes),
            "column": conc_col,
            "nodes": nodes,
        }

    if profile_conc_col and _is_usable(nod):
        res["profile_concentration"] = {
            "available": True,
            "column": profile_conc_col,
            "time_count": int(nod["time"].nunique()) if "time" in nod.columns else 0,
            "node_count": int(nod["node"].nunique()) if "node" in nod.columns else 0,
            "max": _safe_float(nod[profile_conc_col].max()),
        }

    for name, df in solute_outputs.items():
        info: Dict[str, Any] = {"rows": int(len(df))}
        for col, key in (
            ("Sum_cvTop", "final_sum_cvTop"),
            ("Sum_cvBot", "final_sum_cvBot"),
            ("Sum_cvRoot", "final_sum_cvRoot"),
            ("Sum_cRunOff", "final_sum_cRunOff"),
        ):
            if col in df.columns:
                series = df[col].dropna()
                if not series.empty:
                    info[key] = _safe_float(series.iloc[-1])
        res["flux_tables"][name] = info

    return res


def _assess_field_comparison(
    field_comparison: Optional[Dict[str, Any]],
    warnings: List[str],
) -> Dict[str, Any]:
    if not field_comparison:
        return {"available": False, "requested": False}
    res = dict(field_comparison)
    res["requested"] = True
    for warning in res.get("warnings", []) or []:
        warnings.append(f"Field data comparison: {warning}")
    return res


def _assess_convergence(
    run_inf_df: Optional[pd.DataFrame],
    warnings: List[str],
) -> Dict[str, Any]:
    if not _is_usable(run_inf_df):
        return {"present": False}
    res: Dict[str, Any] = {"present": True, "total_steps": int(len(run_inf_df))}
    if "Convergency" in run_inf_df.columns:
        flags = run_inf_df["Convergency"].astype(str).str.upper()
        n_t = int((flags == "T").sum())
        n_total = int(len(flags))
        res["converged_steps"] = n_t
        res["non_converged_steps"] = n_total - n_t
        res["all_converged"] = (n_t == n_total)
        if n_t < n_total:
            warnings.append(
                f"Run_Inf.out: {n_total - n_t}/{n_total} steps did not converge"
            )
    return res


def _assess_figures(
    figures: Optional[Iterable[Path]],
) -> Dict[str, Any]:
    if figures is None:
        return {"checked": False, "expected": list(EXPECTED_FIGURE_NAMES),
                "found": [], "missing": []}
    found_names = sorted({Path(p).name for p in figures})
    expected = list(EXPECTED_FIGURE_NAMES)
    missing = [n for n in expected if n not in found_names]
    return {
        "checked": True,
        "expected": expected,
        "found": found_names,
        "missing": missing,
    }


# --- Public entry point ---------------------------------------------------


def assess_run_quality(
    outputs: Dict[str, Optional[pd.DataFrame]],
    figures: Optional[Iterable[Path]] = None,
    field_comparison: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Audit a HYDRUS run from its parsed outputs and figure list.

    Parameters
    ----------
    outputs
        Dict mapping canonical filenames (``Balance.out``, ``T_Level.out``,
        ``Obs_Node.out``, ``Nod_Inf.out``, ``Run_Inf.out``) to DataFrames or
        ``None``. Missing keys are treated as "not present".
    figures
        Iterable of paths to expected figure files. Pass ``None`` to skip
        the figure-presence check (useful when called from contexts that
        don't generate figures).

    Returns
    -------
    dict
        JSON-serialisable report. The top-level keys are::

            tables, water_balance, cumulative_fluxes,
            observation_nodes, profiles, convergence,
            figures, warnings, ok

        ``ok`` is ``True`` when no warnings were raised.
    """
    warnings: List[str] = []
    report: Dict[str, Any] = {}

    report["tables"] = _assess_tables(outputs, warnings)
    report["water_balance"] = _assess_water_balance(
        outputs.get("Balance.out"), warnings
    )
    report["cumulative_fluxes"] = _assess_cumulative_fluxes(outputs)
    report["observation_nodes"] = _assess_obs_nodes(outputs.get("Obs_Node.out"))
    report["profiles"] = _assess_profiles(outputs.get("Nod_Inf.out"))
    report["solute"] = _assess_solute(outputs)
    report["field_comparison"] = _assess_field_comparison(
        field_comparison, warnings
    )
    report["convergence"] = _assess_convergence(
        outputs.get("Run_Inf.out"), warnings
    )
    report["figures"] = _assess_figures(figures)
    if report["figures"].get("missing"):
        warnings.append(
            f"Figures: {len(report['figures']['missing'])} expected figure(s) "
            f"missing: {', '.join(report['figures']['missing'])}"
        )

    report["warnings"] = warnings
    report["ok"] = len(warnings) == 0
    return report


def write_qc_summary(report: Dict[str, Any], path: Path) -> Path:
    """Write the QC report as JSON. Returns the path written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return path


def format_qc_summary(report: Dict[str, Any]) -> str:
    """Render a concise human-readable summary string."""
    lines: List[str] = []
    lines.append(f"Overall: {'OK' if report.get('ok') else 'WARNINGS'}")
    lines.append("")
    lines.append("Tables:")
    for name, info in report.get("tables", {}).items():
        if not info.get("present"):
            state = "missing"
        elif not info.get("non_empty"):
            state = "empty"
        else:
            state = f"{info.get('rows')} rows × {info.get('columns')} cols"
            if info.get("nan_count", 0):
                state += f" ({info['nan_count']} NaN)"
        lines.append(f"  {name:<14} : {state}")

    wb = report.get("water_balance", {})
    if wb.get("available"):
        lines.append("")
        lines.append("Water balance:")
        if "max_abs_error_pct" in wb:
            lines.append(f"  max |WatBalR| : {wb['max_abs_error_pct']:.3f} %")
        if "final_error_pct" in wb:
            lines.append(f"  final WatBalR : {wb['final_error_pct']:.3f} %")
        if "max_abs_wat_bal_t" in wb:
            lines.append(f"  max |WatBalT| : {wb['max_abs_wat_bal_t']:.3e}")

    cf = report.get("cumulative_fluxes", {})
    src = cf.get("source")
    if src:
        lines.append("")
        lines.append(f"Cumulative fluxes (source: {src}):")
        for k, v in cf.items():
            if k == "source":
                continue
            if isinstance(v, float):
                lines.append(f"  {k:<22}: {v:.4e}")

    obs = report.get("observation_nodes", {})
    if obs.get("present"):
        lines.append("")
        lines.append(
            f"Observation nodes: {obs['node_count']} node(s) "
            f"(IDs {obs.get('node_ids', [])}), {obs['row_count']} rows"
        )
    prof = report.get("profiles", {})
    if prof.get("present"):
        lines.append(
            f"Profiles (Nod_Inf): {prof['time_count']} times × "
            f"{prof['node_count']} nodes = {prof['row_count']} rows"
        )

    solute = report.get("solute", {})
    if solute.get("available"):
        lines.append("")
        lines.append("Solute outputs:")
        obs_sol = solute.get("observation_concentration", {})
        if obs_sol.get("available"):
            lines.append(
                f"  observation concentration nodes: "
                f"{len(obs_sol.get('nodes', {}))}"
            )
        prof_sol = solute.get("profile_concentration", {})
        if prof_sol.get("available"):
            lines.append(
                f"  profile concentration: {prof_sol.get('time_count', 0)} "
                f"times x {prof_sol.get('node_count', 0)} nodes"
            )
        for name, info in solute.get("flux_tables", {}).items():
            parts = [f"  {name}: {info.get('rows', 0)} rows"]
            for key in ("final_sum_cvTop", "final_sum_cvBot",
                        "final_sum_cvRoot", "final_sum_cRunOff"):
                if key in info:
                    parts.append(f"{key}={info[key]:.4e}")
            lines.append(", ".join(parts))

    field = report.get("field_comparison", {})
    if field.get("available"):
        lines.append("")
        lines.append("Field data comparison:")
        lines.append(f"  matched rows: {field.get('matched_rows', 0)}")
        for variable, info in field.get("variables", {}).items():
            nodes = info.get("nodes", {})
            lines.append(f"  {variable}: {len(nodes)} node(s)")

    conv = report.get("convergence", {})
    if conv.get("present"):
        lines.append("")
        if conv.get("all_converged"):
            lines.append(f"Convergence: {conv['total_steps']}/"
                         f"{conv['total_steps']} steps converged")
        else:
            lines.append(
                f"Convergence: {conv.get('converged_steps')}/"
                f"{conv.get('total_steps')} steps converged "
                f"({conv.get('non_converged_steps')} failed)"
            )

    figs = report.get("figures", {})
    if figs.get("checked"):
        lines.append("")
        lines.append(
            f"Figures: {len(figs.get('found', []))}/"
            f"{len(figs.get('expected', []))} expected present"
        )
        if figs.get("missing"):
            lines.append(f"  missing: {', '.join(figs['missing'])}")

    if report.get("warnings"):
        lines.append("")
        lines.append(f"Warnings ({len(report['warnings'])}):")
        for w in report["warnings"]:
            lines.append(f"  - {w}")
    return "\n".join(lines)
