"""Tests for hydrus_agent.plotter (milestone 5).

Uses synthetic fixture DataFrames; no real HYDRUS run is required.
Verifies that:
  * each plot function writes a PNG when its required columns are present
  * each plot function returns None for missing/empty inputs (no crash)
  * generate_standard_plots returns the list of created paths
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from hydrus_agent.plotter import (
    generate_standard_plots,
    plot_balance_storage_vs_time,
    plot_cumulative_water_balance,
    plot_instantaneous_fluxes,
    plot_moisture_contour,
    plot_moisture_profiles,
    plot_obs_head_vs_time,
    plot_obs_theta_vs_time,
    plot_pressure_head_profiles,
    plot_run_diagnostics,
)


# --- Fixture builders -----------------------------------------------------


def make_balance_df():
    return pd.DataFrame({
        "time":     [0.0, 0.25, 0.5, 0.75, 1.0],
        "length":   [1.0, 1.0, 1.0, 1.0, 1.0],
        "w_volume": [0.1224, 0.12214, 0.12187, 0.12161, 0.12135],
        "in_flow":  [0.0, -1.05e-3, -1.05e-3, -1.05e-3, -1.05e-3],
        "h_mean":   [-1.0, -1.005, -1.012, -1.020, -1.031],
        "top_flux": [-5.15e-5, 2.49e-6, 4.85e-5, 8.65e-5, 1.28e-4],
        "bot_flux": [-5.15e-5] * 5,
        "wat_bal_t": [np.nan, 3.5e-9, 8.1e-10, -2.0e-9, 2.7e-9],
        "wat_bal_r": [np.nan, 0.001, 0.0, 0.0, 0.0],
    })


def make_t_level_df():
    return pd.DataFrame({
        "Time":       [0.25, 0.5, 0.75, 1.0],
        "rTop":       [1e-3] * 4,
        "rRoot":      [0.0] * 4,
        "vTop":       [1e-3, 1e-3, 1e-3, 1e-3],
        "vRoot":      [0.0] * 4,
        "vBot":       [-5.15e-5] * 4,
        "sum_rTop":   [2.5e-4, 5.0e-4, 7.5e-4, 1.0e-3],
        "sum_vTop":   [2.5e-4, 5.0e-4, 7.5e-4, 1.0e-3],
        "sum_vBot":   [-1.29e-5, -2.58e-5, -3.86e-5, -5.15e-5],
        "sum_Infil":  [2.5e-4, 5.0e-4, 7.5e-4, 1.0e-3],
        "sum_Evap":   [0.0] * 4,
        "sum_RunOff": [0.0] * 4,
        "hTop":       [-1.108, -1.242, -1.391, -1.582],
        "hBot":       [-1.0] * 4,
        "Volume":     [0.12214, 0.12187, 0.12161, 0.12135],
        "TLevel":     [17, 20, 22, 24],
    })


def make_run_inf_df():
    return pd.DataFrame({
        "TLevel": [17, 20, 22, 24],
        "Time":   [0.25, 0.5, 0.75, 1.0],
        "dt":     [0.041, 0.0938, 0.125, 0.125],
        "Iter":   [2, 2, 2, 2],
        "ItCum":  [34, 40, 44, 48],
        "KodT":   [-1, -1, -1, -1],
        "KodB":   [-5, -5, -5, -5],
        "Convergency": ["T", "T", "T", "T"],
    })


def make_obs_df():
    rows = []
    for t in [0.25, 0.5, 0.75, 1.0]:
        for node in [3, 8]:
            rows.append({
                "time": t, "node": node,
                "h": -1.0 - 0.05 * t,
                "theta": 0.1224 - 0.001 * t,
                "temp": 20.0,
            })
    return pd.DataFrame(rows)


def make_nod_inf_df():
    rows = []
    times = [0.0, 0.25, 0.5, 0.75, 1.0]
    depths = [-i * 0.1 for i in range(11)]  # 0 to -1 m
    for t in times:
        for n, d in enumerate(depths, start=1):
            rows.append({
                "time": t, "node": n, "depth": d,
                "head": -1.0 - 0.1 * t * (1 + (d == 0)),
                "moisture": 0.12 + 0.005 * t * (1 + (d == 0)),
                "K": 5e-5, "C": 5e-2,
                "flux": -5e-5 + 1e-3 * t * (d == 0),
                "sink": 0.0, "kappa": -1.0,
                "vKsTop": -5e-5,
                "temp": 20.0,
            })
    return pd.DataFrame(rows)


# --- Individual plotters --------------------------------------------------


def test_plot_balance_storage_vs_time_creates_png(tmp_path: Path):
    out = plot_balance_storage_vs_time(make_balance_df(), tmp_path)
    assert out is not None
    assert out.is_file()
    assert out.name == "balance_storage_vs_time.png"
    assert out.stat().st_size > 1000  # actual PNG, not stub


def test_plot_balance_storage_vs_time_skips_empty(tmp_path: Path):
    assert plot_balance_storage_vs_time(None, tmp_path) is None
    assert plot_balance_storage_vs_time(pd.DataFrame(), tmp_path) is None


def test_plot_instantaneous_fluxes_uses_t_level(tmp_path: Path):
    out = plot_instantaneous_fluxes(make_t_level_df(), None, tmp_path)
    assert out is not None and out.is_file()
    assert out.name == "instantaneous_fluxes.png"


def test_plot_instantaneous_fluxes_falls_back_to_balance(tmp_path: Path):
    out = plot_instantaneous_fluxes(None, make_balance_df(), tmp_path)
    assert out is not None and out.is_file()


def test_plot_instantaneous_fluxes_skips_when_no_data(tmp_path: Path):
    assert plot_instantaneous_fluxes(None, None, tmp_path) is None
    assert plot_instantaneous_fluxes(pd.DataFrame(), pd.DataFrame(), tmp_path) is None


def test_plot_cumulative_water_balance_creates(tmp_path: Path):
    out = plot_cumulative_water_balance(make_t_level_df(), make_balance_df(),
                                        tmp_path)
    assert out is not None and out.is_file()


def test_plot_cumulative_water_balance_skips_empty(tmp_path: Path):
    assert plot_cumulative_water_balance(None, None, tmp_path) is None


def test_plot_obs_theta_vs_time_creates(tmp_path: Path):
    out = plot_obs_theta_vs_time(make_obs_df(), tmp_path)
    assert out is not None and out.is_file()
    assert out.name == "obs_theta_vs_time.png"


def test_plot_obs_head_vs_time_creates(tmp_path: Path):
    out = plot_obs_head_vs_time(make_obs_df(), tmp_path)
    assert out is not None and out.is_file()
    assert out.name == "obs_head_vs_time.png"


def test_plot_obs_skips_empty(tmp_path: Path):
    assert plot_obs_theta_vs_time(None, tmp_path) is None
    assert plot_obs_head_vs_time(pd.DataFrame(), tmp_path) is None


def test_plot_moisture_profiles_creates(tmp_path: Path):
    out = plot_moisture_profiles(make_nod_inf_df(), tmp_path)
    assert out is not None and out.is_file()


def test_plot_moisture_profiles_with_explicit_times(tmp_path: Path):
    """Caller can specify times; the parser snaps to nearest available."""
    out = plot_moisture_profiles(make_nod_inf_df(), tmp_path,
                                 times=[0.0, 0.5, 1.0])
    assert out is not None and out.is_file()


def test_plot_pressure_head_profiles_creates(tmp_path: Path):
    out = plot_pressure_head_profiles(make_nod_inf_df(), tmp_path)
    assert out is not None and out.is_file()


def test_plot_profiles_skips_empty(tmp_path: Path):
    assert plot_moisture_profiles(None, tmp_path) is None
    assert plot_pressure_head_profiles(pd.DataFrame(), tmp_path) is None


def test_plot_moisture_contour_creates(tmp_path: Path):
    out = plot_moisture_contour(make_nod_inf_df(), tmp_path)
    assert out is not None and out.is_file()
    assert out.name == "moisture_contour.png"


def test_plot_moisture_contour_skips_empty(tmp_path: Path):
    assert plot_moisture_contour(None, tmp_path) is None


def test_plot_moisture_contour_skips_too_few_points(tmp_path: Path):
    """Need at least 2 times AND 2 depths for a contour."""
    tiny = pd.DataFrame({"time": [0.0], "depth": [0.0], "moisture": [0.1]})
    assert plot_moisture_contour(tiny, tmp_path) is None


def test_plot_run_diagnostics_creates(tmp_path: Path):
    out = plot_run_diagnostics(make_run_inf_df(), tmp_path)
    assert out is not None and out.is_file()


def test_plot_run_diagnostics_skips_empty(tmp_path: Path):
    assert plot_run_diagnostics(None, tmp_path) is None
    assert plot_run_diagnostics(pd.DataFrame(), tmp_path) is None


# --- High-level orchestration --------------------------------------------


def test_generate_standard_plots_full_outputs(tmp_path: Path):
    outputs = {
        "Balance.out": make_balance_df(),
        "T_Level.out": make_t_level_df(),
        "Obs_Node.out": make_obs_df(),
        "Nod_Inf.out": make_nod_inf_df(),
        "Run_Inf.out": make_run_inf_df(),
    }
    figures = generate_standard_plots(outputs, tmp_path)
    # All 9 plots should be created.
    assert len(figures) == 9
    for path in figures:
        assert path.is_file()
        assert path.stat().st_size > 1000

    # Every expected filename appears.
    names = {f.name for f in figures}
    expected = {
        "balance_storage_vs_time.png",
        "instantaneous_fluxes.png",
        "cumulative_water_balance.png",
        "obs_theta_vs_time.png",
        "obs_head_vs_time.png",
        "moisture_profiles.png",
        "pressure_head_profiles.png",
        "moisture_contour.png",
        "run_diagnostics.png",
    }
    assert names == expected


def test_generate_standard_plots_adds_solute_figures_when_available(tmp_path: Path):
    obs = make_obs_df().copy()
    obs["conc"] = [0.0, 0.0, 0.1, 0.0, 0.2, 0.3, 0.4, 0.2]
    nod = make_nod_inf_df().copy()
    nod["conc_1"] = nod["time"] * (1.0 + nod["node"] / 100.0)
    outputs = {
        "Balance.out": make_balance_df(),
        "T_Level.out": make_t_level_df(),
        "Obs_Node.out": obs,
        "Nod_Inf.out": nod,
        "Run_Inf.out": make_run_inf_df(),
    }
    figures = generate_standard_plots(outputs, tmp_path)
    names = {f.name for f in figures}
    assert "obs_concentration_vs_time.png" in names
    assert "concentration_profiles.png" in names


def test_generate_standard_plots_partial_outputs(tmp_path: Path):
    """Missing keys / empty DataFrames must not crash the generator."""
    outputs = {
        "Balance.out": make_balance_df(),
        "T_Level.out": pd.DataFrame(),     # empty - skipped
        # Obs_Node.out missing entirely
        "Nod_Inf.out": make_nod_inf_df(),
        "Run_Inf.out": None,               # explicit None - skipped
    }
    figures = generate_standard_plots(outputs, tmp_path)
    names = {f.name for f in figures}
    # Plots from Balance and Nod_Inf should appear.
    assert "balance_storage_vs_time.png" in names
    assert "moisture_profiles.png" in names
    assert "pressure_head_profiles.png" in names
    assert "moisture_contour.png" in names
    # Plots that need T_Level / Obs_Node / Run_Inf should be absent.
    assert "obs_theta_vs_time.png" not in names
    assert "obs_head_vs_time.png" not in names
    assert "run_diagnostics.png" not in names
    # instantaneous_fluxes can fall back to Balance.out
    assert "instantaneous_fluxes.png" in names


def test_generate_standard_plots_empty_dict(tmp_path: Path):
    """An empty outputs dict must just return [] (no crash, no PNGs)."""
    figures = generate_standard_plots({}, tmp_path)
    assert figures == []
