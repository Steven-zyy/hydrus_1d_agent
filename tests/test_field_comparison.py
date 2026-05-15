"""Tests for field-data overlay and model-observation comparison."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from hydrus_agent.field_comparison import (
    compare_field_data,
    load_field_data,
    plot_field_overlays,
    write_field_comparison_summary,
)
from tests.test_plotter import make_obs_df


def _write_csv(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_load_field_data_normalises_csv_aliases(tmp_path: Path):
    csv_path = _write_csv(
        tmp_path / "measured.csv",
        "Time,Node,Water_Content,Pressure_Head\n"
        "0.25,3,0.121,-1.02\n"
        "0.50,3,0.120,-1.04\n",
    )

    measured = load_field_data(csv_path)

    assert list(measured.columns) == ["time", "node", "theta", "h"]
    assert measured["time"].tolist() == [0.25, 0.5]
    assert measured["node"].tolist() == [3, 3]


def test_load_field_data_requires_time_and_location(tmp_path: Path):
    csv_path = _write_csv(
        tmp_path / "bad.csv",
        "time,theta\n"
        "0.25,0.12\n",
    )

    with pytest.raises(ValueError, match="node or depth"):
        load_field_data(csv_path)


def test_compare_field_data_matches_by_node_and_computes_metrics(tmp_path: Path):
    csv_path = _write_csv(
        tmp_path / "measured.csv",
        "time,node,theta,h\n"
        "0.25,3,0.12000,-1.000\n"
        "0.50,3,0.12100,-1.010\n"
        "0.25,8,0.11900,-1.020\n"
        "0.50,8,0.11800,-1.030\n",
    )
    obs = make_obs_df()

    summary, matched = compare_field_data(
        {"Obs_Node.out": obs},
        csv_path,
    )

    assert summary["available"] is True
    assert summary["matched_rows"] == 4
    assert matched is not None and len(matched) == 4
    theta_node3 = summary["variables"]["theta"]["nodes"]["3"]
    assert theta_node3["matched_count"] == 2
    assert theta_node3["rmse"] >= 0.0
    assert theta_node3["mae"] >= 0.0
    assert "bias" in theta_node3
    assert "correlation" in theta_node3
    head_node8 = summary["variables"]["head"]["nodes"]["8"]
    assert head_node8["matched_count"] == 2


def test_compare_field_data_maps_depth_when_observation_depths_available(tmp_path: Path):
    csv_path = _write_csv(
        tmp_path / "measured_by_depth.csv",
        "time,depth,theta\n"
        "0.25,0.25,0.120\n"
        "0.50,0.25,0.121\n"
        "0.25,0.75,0.119\n"
        "0.50,0.75,0.118\n",
    )

    summary, matched = compare_field_data(
        {"Obs_Node.out": make_obs_df()},
        csv_path,
        observation_depths=[0.25, 0.75],
    )

    assert summary["available"] is True
    assert summary["matched_rows"] == 4
    assert matched is not None
    assert sorted(matched["node"].unique()) == [3, 8]


def test_compare_field_data_depth_requires_observation_depths(tmp_path: Path):
    csv_path = _write_csv(
        tmp_path / "measured_by_depth.csv",
        "time,depth,theta\n"
        "0.25,0.25,0.120\n",
    )

    summary, matched = compare_field_data({"Obs_Node.out": make_obs_df()}, csv_path)

    assert summary["available"] is False
    assert matched is None
    assert any("observation_depths" in w for w in summary["warnings"])


def test_compare_field_data_ignores_variables_missing_from_model(tmp_path: Path):
    csv_path = _write_csv(
        tmp_path / "measured.csv",
        "time,node,theta,h\n"
        "0.25,3,0.12000,-1.000\n"
        "0.50,3,0.12100,-1.010\n",
    )
    obs = make_obs_df().drop(columns=["h"])

    summary, matched = compare_field_data({"Obs_Node.out": obs}, csv_path)

    assert summary["available"] is True
    assert "theta" in summary["variables"]
    assert "head" not in summary["variables"]
    assert matched is not None
    assert "model_head" not in matched.columns


def test_write_summary_and_plot_overlays(tmp_path: Path):
    csv_path = _write_csv(
        tmp_path / "measured.csv",
        "time,node,theta,h\n"
        "0.25,3,0.12000,-1.000\n"
        "0.50,3,0.12100,-1.010\n"
        "0.25,8,0.11900,-1.020\n"
        "0.50,8,0.11800,-1.030\n",
    )
    summary, matched = compare_field_data({"Obs_Node.out": make_obs_df()}, csv_path)

    json_path = write_field_comparison_summary(summary, tmp_path / "outputs")
    figures = plot_field_overlays(matched, tmp_path / "figures")

    assert json_path.name == "field_comparison_summary.json"
    parsed = json.loads(json_path.read_text(encoding="utf-8"))
    assert parsed["matched_rows"] == 4
    names = {p.name for p in figures}
    assert "field_overlay_theta.png" in names
    assert "field_overlay_head.png" in names
    for path in figures:
        assert path.is_file()
        assert path.stat().st_size > 1000
