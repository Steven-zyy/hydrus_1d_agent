"""HYDRUS-1D plotting (milestone 5).

Generates standard result figures from the parsed DataFrames produced by
``hydrus_agent.output_reader``. Each plotting function:

    * Takes one or two DataFrames plus a ``figure_dir`` Path.
    * Returns the path of the saved PNG, or ``None`` if the input is missing
      or empty (the caller decides how to report this; we never crash).
    * Saves PNG files only — no other formats, no interactive windows.

Use ``generate_standard_plots(outputs, figure_dir)`` to produce all
available figures from a dict like the one returned by
``output_reader.read_outputs``.

Out of scope (later milestones):
    * Report generation (Markdown/PDF assembly).
    * Field-data overlays (Excel monitoring data).
    * Interactive dashboards.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Union

import matplotlib

# Force a non-interactive backend before pyplot is imported. This is required
# for headless environments and for tests that run without a display.
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


logger = logging.getLogger(__name__)


# --- Helpers --------------------------------------------------------------


def _is_usable(df: Optional[pd.DataFrame]) -> bool:
    """A DataFrame is usable for plotting if it's not None and not empty."""
    return df is not None and isinstance(df, pd.DataFrame) and not df.empty


def _ensure_figure_dir(figure_dir: Union[str, Path]) -> Path:
    figure_dir = Path(figure_dir)
    figure_dir.mkdir(parents=True, exist_ok=True)
    return figure_dir


def _save_close(fig: plt.Figure, path: Path) -> Path:
    """Save a figure and close it. Returns the path."""
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def _select_times(
    nod_df: pd.DataFrame,
    times: Optional[Sequence[float]],
    *,
    max_default: int = 6,
) -> List[float]:
    """Select a list of times to display in profile plots.

    If the caller supplied a list, snap each requested time to the nearest
    actually-available value. Otherwise pick up to ``max_default`` evenly
    spaced unique times across what's in the file.
    """
    available = sorted(nod_df["time"].unique())
    if not available:
        return []
    if times is not None and len(times) > 0:
        snapped = []
        for t in times:
            nearest = min(available, key=lambda a: abs(a - t))
            if nearest not in snapped:
                snapped.append(nearest)
        return snapped
    if len(available) <= max_default:
        return list(available)
    idx = np.linspace(0, len(available) - 1, max_default).astype(int)
    return [available[i] for i in idx]


# --- 1. Balance: storage vs time ----------------------------------------


def plot_balance_storage_vs_time(
    balance_df: Optional[pd.DataFrame],
    figure_dir: Union[str, Path],
) -> Optional[Path]:
    """Plot the in-domain water storage (W-volume) over time.

    Source: ``Balance.out`` parsed by ``read_balance``. Skipped if the
    DataFrame is missing/empty or the ``w_volume`` column is absent.
    """
    if not _is_usable(balance_df):
        return None
    if "w_volume" not in balance_df.columns or "time" not in balance_df.columns:
        return None

    figure_dir = _ensure_figure_dir(figure_dir)
    fig, ax = plt.subplots(figsize=(7.5, 4.0))
    ax.plot(balance_df["time"], balance_df["w_volume"], marker="o",
            linewidth=1.5, color="#1f77b4")
    ax.set_xlabel("Time")
    ax.set_ylabel("W-volume (storage) [L]")
    ax.set_title("Profile water storage vs time (Balance.out)")
    ax.grid(True, alpha=0.3)
    return _save_close(fig, figure_dir / "balance_storage_vs_time.png")


# --- 2. Instantaneous fluxes -------------------------------------------


def plot_instantaneous_fluxes(
    t_level_df: Optional[pd.DataFrame],
    balance_df: Optional[pd.DataFrame],
    figure_dir: Union[str, Path],
) -> Optional[Path]:
    """Plot instantaneous top/bottom fluxes vs time.

    Prefers ``T_Level.out`` (rTop / vTop / vBot at every time level) and
    falls back to ``Balance.out`` (Top Flux / Bot Flux at print times) if
    T_Level is unavailable. Skipped when neither source has the needed
    columns.
    """
    figure_dir = _ensure_figure_dir(figure_dir)
    fig, ax = plt.subplots(figsize=(7.5, 4.0))
    plotted = False

    if _is_usable(t_level_df):
        # Case-preserving columns: Time, rTop, vTop, vBot.
        wanted = [c for c in ("rTop", "vTop", "vBot") if c in t_level_df.columns]
        if "Time" in t_level_df.columns and wanted:
            for col in wanted:
                ax.plot(t_level_df["Time"], t_level_df[col],
                        marker="o", linewidth=1.2, label=col)
            plotted = True

    if not plotted and _is_usable(balance_df):
        if "time" in balance_df.columns:
            for col, label in (("top_flux", "Top Flux"),
                               ("bot_flux", "Bot Flux")):
                if col in balance_df.columns:
                    ax.plot(balance_df["time"], balance_df[col],
                            marker="o", linewidth=1.2, label=label)
                    plotted = True

    if not plotted:
        plt.close(fig)
        return None

    ax.axhline(0.0, color="black", linewidth=0.6)
    ax.set_xlabel("Time")
    ax.set_ylabel("Flux [L/T]")
    ax.set_title("Instantaneous fluxes vs time")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    return _save_close(fig, figure_dir / "instantaneous_fluxes.png")


# --- 3. Cumulative water balance --------------------------------------


def plot_cumulative_water_balance(
    t_level_df: Optional[pd.DataFrame],
    balance_df: Optional[pd.DataFrame],
    figure_dir: Union[str, Path],
) -> Optional[Path]:
    """Plot cumulative water-balance components.

    Uses T_Level columns when available: ``sum_Infil``, ``sum_vBot``,
    ``sum_Evap``, ``sum_RunOff``, ``Volume``. Falls back to a simpler
    panel from Balance.out if T_Level is missing.
    """
    figure_dir = _ensure_figure_dir(figure_dir)
    fig, ax = plt.subplots(figsize=(7.5, 4.0))
    plotted = False

    if _is_usable(t_level_df) and "Time" in t_level_df.columns:
        cumulative_columns = [
            ("sum_Infil", "Cumulative infiltration"),
            ("sum_vBot", "Cumulative bottom flux"),
            ("sum_Evap", "Cumulative evaporation"),
            ("sum_RunOff", "Cumulative runoff"),
            ("Volume", "Storage (Volume)"),
        ]
        for col, label in cumulative_columns:
            if col in t_level_df.columns:
                ax.plot(t_level_df["Time"], t_level_df[col],
                        marker="o", linewidth=1.2, label=label)
                plotted = True

    if not plotted and _is_usable(balance_df) and "time" in balance_df.columns:
        # Approximate cumulative storage from Balance.w_volume
        if "w_volume" in balance_df.columns:
            ax.plot(balance_df["time"], balance_df["w_volume"],
                    marker="o", label="W-volume (storage)")
            plotted = True

    if not plotted:
        plt.close(fig)
        return None

    ax.axhline(0.0, color="black", linewidth=0.6)
    ax.set_xlabel("Time")
    ax.set_ylabel("Cumulative water [L]")
    ax.set_title("Cumulative water balance")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    return _save_close(fig, figure_dir / "cumulative_water_balance.png")


# --- 4 & 5. Observation node time series ------------------------------


def _plot_obs_series(
    obs_df: pd.DataFrame,
    figure_dir: Path,
    *,
    column: str,
    ylabel: str,
    title: str,
    filename: str,
) -> Optional[Path]:
    if not _is_usable(obs_df):
        return None
    if not {"time", "node", column}.issubset(obs_df.columns):
        return None

    figure_dir = _ensure_figure_dir(figure_dir)
    fig, ax = plt.subplots(figsize=(7.5, 4.0))
    for node, sub in obs_df.groupby("node"):
        sub = sub.sort_values("time")
        ax.plot(sub["time"], sub[column], marker="o",
                linewidth=1.2, label=f"Node {int(node)}")
    ax.set_xlabel("Time")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    return _save_close(fig, figure_dir / filename)


def plot_obs_theta_vs_time(
    obs_df: Optional[pd.DataFrame],
    figure_dir: Union[str, Path],
) -> Optional[Path]:
    """Water content theta at observation nodes vs time."""
    return _plot_obs_series(
        obs_df, Path(figure_dir),
        column="theta",
        ylabel=r"Water content $\theta$ [-]",
        title="Observation-node water content vs time",
        filename="obs_theta_vs_time.png",
    )


def plot_obs_head_vs_time(
    obs_df: Optional[pd.DataFrame],
    figure_dir: Union[str, Path],
) -> Optional[Path]:
    """Pressure head h at observation nodes vs time."""
    return _plot_obs_series(
        obs_df, Path(figure_dir),
        column="h",
        ylabel="Pressure head h [L]",
        title="Observation-node pressure head vs time",
        filename="obs_head_vs_time.png",
    )


def _first_existing_column(
    df: Optional[pd.DataFrame],
    candidates: Sequence[str],
) -> Optional[str]:
    if not _is_usable(df):
        return None
    for col in candidates:
        if col in df.columns:
            return col
    return None


def plot_obs_concentration_vs_time(
    obs_df: Optional[pd.DataFrame],
    figure_dir: Union[str, Path],
) -> Optional[Path]:
    """Solute concentration at observation nodes vs time."""
    column = _first_existing_column(obs_df, ("conc", "conc_1"))
    if column is None:
        return None
    return _plot_obs_series(
        obs_df, Path(figure_dir),
        column=column,
        ylabel="Concentration [M/L^3]",
        title="Observation-node solute concentration vs time",
        filename="obs_concentration_vs_time.png",
    )


# --- 6 & 7. Profiles vs depth at selected times -----------------------


def _plot_profile_at_times(
    nod_df: pd.DataFrame,
    figure_dir: Path,
    *,
    column: str,
    xlabel: str,
    title: str,
    filename: str,
    times: Optional[Sequence[float]],
) -> Optional[Path]:
    if not _is_usable(nod_df):
        return None
    if not {"time", "depth", column}.issubset(nod_df.columns):
        return None

    figure_dir = _ensure_figure_dir(figure_dir)
    fig, ax = plt.subplots(figsize=(6.0, 6.5))

    chosen = _select_times(nod_df, times)
    if not chosen:
        plt.close(fig)
        return None

    cmap = plt.get_cmap("viridis", max(len(chosen), 2))
    for i, t in enumerate(chosen):
        sub = nod_df[nod_df["time"] == t].sort_values("depth", ascending=False)
        if sub.empty:
            continue
        ax.plot(sub[column], sub["depth"], marker="o", linewidth=1.2,
                color=cmap(i), label=f"t = {t:g}")

    ax.set_xlabel(xlabel)
    ax.set_ylabel("Depth (negative downward) [L]")
    ax.set_title(title)
    ax.legend(loc="best", fontsize=9)
    ax.grid(True, alpha=0.3)
    return _save_close(fig, figure_dir / filename)


def plot_moisture_profiles(
    nod_df: Optional[pd.DataFrame],
    figure_dir: Union[str, Path],
    *,
    times: Optional[Sequence[float]] = None,
) -> Optional[Path]:
    """Theta vs depth at selected times. ``times=None`` picks up to 6 evenly
    spaced print times automatically."""
    return _plot_profile_at_times(
        nod_df, Path(figure_dir),
        column="moisture",
        xlabel=r"Water content $\theta$ [-]",
        title="Moisture profiles at selected times",
        filename="moisture_profiles.png",
        times=times,
    )


def plot_pressure_head_profiles(
    nod_df: Optional[pd.DataFrame],
    figure_dir: Union[str, Path],
    *,
    times: Optional[Sequence[float]] = None,
) -> Optional[Path]:
    """Pressure head vs depth at selected times."""
    return _plot_profile_at_times(
        nod_df, Path(figure_dir),
        column="head",
        xlabel="Pressure head h [L]",
        title="Pressure head profiles at selected times",
        filename="pressure_head_profiles.png",
        times=times,
    )


def plot_concentration_profiles(
    nod_df: Optional[pd.DataFrame],
    figure_dir: Union[str, Path],
    *,
    times: Optional[Sequence[float]] = None,
) -> Optional[Path]:
    """Solute concentration profiles vs depth."""
    column = _first_existing_column(nod_df, ("conc_1", "conc"))
    if column is None:
        return None
    return _plot_profile_at_times(
        nod_df, Path(figure_dir),
        column=column,
        xlabel="Concentration [M/L^3]",
        title="Solute concentration profiles",
        filename="concentration_profiles.png",
        times=times,
    )


# --- 8. Moisture contour (time × depth) -------------------------------


def plot_moisture_contour(
    nod_df: Optional[pd.DataFrame],
    figure_dir: Union[str, Path],
) -> Optional[Path]:
    """Time-depth contour of moisture from Nod_Inf.out.

    Pivots ``nod_df`` to a (depth × time) grid of moisture values and
    draws filled contours. Skipped when the DataFrame is missing or has
    fewer than two times or two depths.
    """
    if not _is_usable(nod_df):
        return None
    if not {"time", "depth", "moisture"}.issubset(nod_df.columns):
        return None

    pivot = nod_df.pivot_table(index="depth", columns="time",
                               values="moisture", aggfunc="mean")
    if pivot.shape[0] < 2 or pivot.shape[1] < 2:
        return None

    figure_dir = _ensure_figure_dir(figure_dir)
    fig, ax = plt.subplots(figsize=(8.0, 5.0))
    times = pivot.columns.values
    depths = pivot.index.values
    T, D = np.meshgrid(times, depths)
    cs = ax.contourf(T, D, pivot.values, levels=12, cmap="viridis")
    cb = fig.colorbar(cs, ax=ax)
    cb.set_label(r"Water content $\theta$ [-]")
    ax.set_xlabel("Time")
    ax.set_ylabel("Depth (negative downward) [L]")
    ax.set_title("Moisture contour (time × depth)")
    return _save_close(fig, figure_dir / "moisture_contour.png")


# --- 9. Run diagnostics (Run_Inf.out) ---------------------------------


def plot_run_diagnostics(
    run_inf_df: Optional[pd.DataFrame],
    figure_dir: Union[str, Path],
) -> Optional[Path]:
    """Solver-diagnostic panel: Iter and dt vs time + a convergence summary.

    Uses ``Run_Inf.out``. Plot becomes useful for later agent-based model
    diagnostics (e.g. detecting non-converging runs).
    """
    if not _is_usable(run_inf_df):
        return None
    if "Time" not in run_inf_df.columns:
        return None

    figure_dir = _ensure_figure_dir(figure_dir)
    fig, axes = plt.subplots(2, 1, figsize=(7.5, 6.0), sharex=True)

    if "Iter" in run_inf_df.columns:
        axes[0].plot(run_inf_df["Time"], run_inf_df["Iter"],
                     marker="o", color="#d62728")
    axes[0].set_ylabel("Iter (per step)")
    axes[0].grid(True, alpha=0.3)

    if "dt" in run_inf_df.columns:
        axes[1].plot(run_inf_df["Time"], run_inf_df["dt"],
                     marker="o", color="#2ca02c")
    axes[1].set_xlabel("Time")
    axes[1].set_ylabel("dt")
    axes[1].grid(True, alpha=0.3)

    # Convergence summary.
    if "Convergency" in run_inf_df.columns:
        flags = run_inf_df["Convergency"].astype(str).str.upper()
        n_total = len(flags)
        n_t = (flags == "T").sum()
        summary = f"Convergency: {n_t}/{n_total} steps converged"
    else:
        summary = "Convergency column not found"
    fig.suptitle(f"Run diagnostics — {summary}", y=0.995)

    return _save_close(fig, figure_dir / "run_diagnostics.png")


# --- High-level orchestration ----------------------------------------


def generate_standard_plots(
    outputs: dict,
    figure_dir: Union[str, Path],
) -> List[Path]:
    """Call every plot function for which the source DataFrame is present.

    ``outputs`` is the dict returned by ``output_reader.read_outputs``: it
    maps canonical filenames (``Balance.out``, ``T_Level.out`` ...) to
    DataFrames. Missing keys or empty DataFrames are silently skipped.

    Returns the list of created figure paths in the order they were
    successfully created.
    """
    figure_dir = _ensure_figure_dir(figure_dir)
    balance = outputs.get("Balance.out")
    t_level = outputs.get("T_Level.out")
    obs = outputs.get("Obs_Node.out")
    nod_inf = outputs.get("Nod_Inf.out")
    run_inf = outputs.get("Run_Inf.out")

    candidates = [
        plot_balance_storage_vs_time(balance, figure_dir),
        plot_instantaneous_fluxes(t_level, balance, figure_dir),
        plot_cumulative_water_balance(t_level, balance, figure_dir),
        plot_obs_theta_vs_time(obs, figure_dir),
        plot_obs_head_vs_time(obs, figure_dir),
        plot_obs_concentration_vs_time(obs, figure_dir),
        plot_moisture_profiles(nod_inf, figure_dir),
        plot_pressure_head_profiles(nod_inf, figure_dir),
        plot_concentration_profiles(nod_inf, figure_dir),
        plot_moisture_contour(nod_inf, figure_dir),
        plot_run_diagnostics(run_inf, figure_dir),
    ]
    return [p for p in candidates if p is not None]
