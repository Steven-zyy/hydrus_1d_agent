"""Field-data overlay and model-observation comparison utilities.

This module is deliberately post-processing only. It reads measured
monitoring data, matches it against parsed ``Obs_Node.out`` rows, computes
simple model-observation metrics, and writes optional overlay plots. It never
modifies HYDRUS inputs or model parameters.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402


FIELD_COMPARISON_FILENAME = "field_comparison_summary.json"


_COLUMN_ALIASES = {
    "time": "time",
    "t": "time",
    "node": "node",
    "obs_node": "node",
    "observation_node": "node",
    "depth": "depth",
    "z": "depth",
    "theta": "theta",
    "water_content": "theta",
    "watercontent": "theta",
    "moisture": "theta",
    "pressure_head": "h",
    "head": "h",
    "h": "h",
}


def load_field_data(path: Path | str) -> pd.DataFrame:
    """Load measured field data from CSV or, optionally, Excel.

    Required normalized columns are ``time`` plus either ``node`` or ``depth``.
    At least one comparable variable, ``theta`` or ``h``, is also required.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Field data file not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(path)
    elif suffix in {".xlsx", ".xls"}:
        try:
            df = pd.read_excel(path)
        except ImportError as exc:
            raise ValueError(
                "Excel field data requires optional pandas Excel dependencies "
                "(for example openpyxl). Use CSV or install the dependency."
            ) from exc
    else:
        raise ValueError(f"Unsupported field data format: {path.suffix}. Use CSV.")

    renamed = {}
    for col in df.columns:
        key = str(col).strip().lower().replace(" ", "_").replace("-", "_")
        renamed[col] = _COLUMN_ALIASES.get(key, key)
    df = df.rename(columns=renamed)
    keep = [c for c in ("time", "node", "depth", "theta", "h") if c in df.columns]
    df = df[keep].copy()

    if "time" not in df.columns:
        raise ValueError("Field data must include a time column.")
    if "node" not in df.columns and "depth" not in df.columns:
        raise ValueError("Field data must include either a node or depth column.")
    if "theta" not in df.columns and "h" not in df.columns:
        raise ValueError("Field data must include theta and/or pressure head data.")

    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["time"])
    if "node" in df.columns:
        df = df.dropna(subset=["node"])
        df["node"] = df["node"].astype(int)
    if "depth" in df.columns:
        df = df.dropna(subset=["depth"])
    return df


def compare_field_data(
    outputs: Dict[str, Optional[pd.DataFrame]],
    field_data_path: Path | str,
    *,
    observation_depths: Optional[Iterable[float]] = None,
) -> Tuple[Dict[str, Any], Optional[pd.DataFrame]]:
    """Compare measured field data against parsed ``Obs_Node.out``.

    Returns ``(summary, matched_df)``. ``matched_df`` is useful for overlay
    plots and is ``None`` when no comparison can be made.
    """
    warnings = []
    obs = outputs.get("Obs_Node.out")
    if obs is None or not isinstance(obs, pd.DataFrame) or obs.empty:
        return _empty_summary(field_data_path, ["Obs_Node.out is missing or empty."]), None
    if not {"time", "node"}.issubset(obs.columns):
        return _empty_summary(field_data_path, ["Obs_Node.out must include time and node."]), None

    measured = load_field_data(field_data_path)
    measured = measured.copy()
    if "node" not in measured.columns:
        mapped = _map_depths_to_nodes(
            obs,
            measured,
            observation_depths,
        )
        if mapped is None:
            return _empty_summary(
                field_data_path,
                ["Field data uses depth, but observation_depths are unavailable or incomplete."],
            ), None
        measured = mapped

    variable_map = {
        "theta": ("theta", "theta"),
        "head": ("h", "h"),
    }
    available = {
        name: (model_col, measured_col)
        for name, (model_col, measured_col) in variable_map.items()
        if model_col in obs.columns and measured_col in measured.columns
    }
    if not available:
        return _empty_summary(
            field_data_path,
            ["No comparable variables found in both field data and Obs_Node.out."],
        ), None

    obs_cols = ["time", "node", *sorted({cols[0] for cols in available.values()})]
    measured_cols = ["time", "node", *sorted({cols[1] for cols in available.values()})]
    merged = pd.merge(
        obs[obs_cols],
        measured[measured_cols],
        on=["time", "node"],
        how="inner",
        suffixes=("_model", "_measured"),
    )
    if merged.empty:
        return _empty_summary(
            field_data_path,
            ["No field-data rows matched HYDRUS observation times and nodes."],
        ), None

    # Rename columns to stable, report-friendly names.
    rename = {}
    for variable, (model_col, measured_col) in available.items():
        rename[f"{model_col}_model"] = f"model_{variable}"
        rename[f"{measured_col}_measured"] = f"measured_{variable}"
    merged = merged.rename(columns=rename)

    variables: Dict[str, Any] = {}
    for variable in available:
        model_col = f"model_{variable}"
        measured_col = f"measured_{variable}"
        if model_col not in merged.columns or measured_col not in merged.columns:
            continue
        nodes = {}
        for node, sub in merged.groupby("node"):
            metrics = _metrics(sub[model_col], sub[measured_col])
            if metrics["matched_count"] > 0:
                nodes[str(int(node))] = metrics
        if nodes:
            variables[variable] = {"nodes": nodes}

    summary = {
        "available": bool(variables),
        "field_data_path": str(Path(field_data_path)),
        "matched_rows": int(len(merged)),
        "variables": variables,
        "warnings": warnings,
        "figures": [],
    }
    return summary, merged if variables else None


def write_field_comparison_summary(summary: Dict[str, Any], output_dir: Path | str) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / FIELD_COMPARISON_FILENAME
    path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return path


def plot_field_overlays(
    matched: Optional[pd.DataFrame],
    figure_dir: Path | str,
) -> list[Path]:
    """Create model-vs-measured overlay plots for available variables."""
    if matched is None or not isinstance(matched, pd.DataFrame) or matched.empty:
        return []
    figure_dir = Path(figure_dir)
    figure_dir.mkdir(parents=True, exist_ok=True)

    figures: list[Path] = []
    for variable, ylabel, filename in (
        ("theta", r"Water content $\theta$ [-]", "field_overlay_theta.png"),
        ("head", "Pressure head h [L]", "field_overlay_head.png"),
    ):
        model_col = f"model_{variable}"
        measured_col = f"measured_{variable}"
        if model_col not in matched.columns or measured_col not in matched.columns:
            continue
        fig, ax = plt.subplots(figsize=(7.5, 4.0))
        for node, sub in matched.sort_values("time").groupby("node"):
            label = f"Node {int(node)}"
            ax.plot(sub["time"], sub[model_col], linewidth=1.4, label=f"{label} model")
            ax.scatter(sub["time"], sub[measured_col], s=28, label=f"{label} measured")
        ax.set_xlabel("Time")
        ax.set_ylabel(ylabel)
        ax.set_title(f"Field comparison: {variable}")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best", fontsize=8)
        fig.tight_layout()
        path = figure_dir / filename
        fig.savefig(path, dpi=120)
        plt.close(fig)
        figures.append(path)
    return figures


def run_field_comparison(
    outputs: Dict[str, Optional[pd.DataFrame]],
    field_data_path: Path | str,
    *,
    output_dir: Path | str,
    figure_dir: Path | str,
    observation_depths: Optional[Iterable[float]] = None,
) -> tuple[Dict[str, Any], list[Path], Path]:
    """Compare field data, write summary JSON, and generate overlay plots."""
    summary, matched = compare_field_data(
        outputs,
        field_data_path,
        observation_depths=observation_depths,
    )
    figures = plot_field_overlays(matched, figure_dir)
    summary["figures"] = [str(path) for path in figures]
    summary_path = write_field_comparison_summary(summary, output_dir)
    return summary, figures, summary_path


def _map_depths_to_nodes(
    obs: pd.DataFrame,
    measured: pd.DataFrame,
    observation_depths: Optional[Iterable[float]],
) -> Optional[pd.DataFrame]:
    if observation_depths is None:
        return None
    depths = list(observation_depths)
    node_ids = sorted(int(n) for n in obs["node"].dropna().unique())
    if len(depths) < len(node_ids):
        return None
    mapping = {float(depth): node for depth, node in zip(depths, node_ids)}
    nodes = []
    for depth in measured["depth"]:
        node = _lookup_depth(mapping, float(depth))
        if node is None:
            return None
        nodes.append(node)
    out = measured.copy()
    out["node"] = nodes
    return out


def _lookup_depth(mapping: Dict[float, int], depth: float) -> Optional[int]:
    for known, node in mapping.items():
        if math.isclose(known, depth, rel_tol=0.0, abs_tol=1.0e-6):
            return node
    return None


def _metrics(model: pd.Series, measured: pd.Series) -> Dict[str, Any]:
    df = pd.DataFrame({"model": model, "measured": measured}).dropna()
    if df.empty:
        return {
            "matched_count": 0,
            "rmse": None,
            "mae": None,
            "bias": None,
            "correlation": None,
        }
    err = df["model"] - df["measured"]
    corr = None
    if len(df) >= 2 and df["model"].nunique() > 1 and df["measured"].nunique() > 1:
        value = float(df["model"].corr(df["measured"]))
        if math.isfinite(value):
            corr = value
    return {
        "matched_count": int(len(df)),
        "rmse": _safe_float((err.pow(2).mean()) ** 0.5),
        "mae": _safe_float(err.abs().mean()),
        "bias": _safe_float(err.mean()),
        "correlation": corr,
    }


def _safe_float(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _empty_summary(path: Path | str, warnings: list[str]) -> Dict[str, Any]:
    return {
        "available": False,
        "field_data_path": str(Path(path)),
        "matched_rows": 0,
        "variables": {},
        "warnings": warnings,
        "figures": [],
    }
