from __future__ import annotations

import json
from pathlib import Path

import pytest

from hydrus_agent import load_config
from hydrus_agent.atmospheric_csv import (
    AtmosphericCsvError,
    load_atmospheric_records_from_csv,
)


def _write_csv(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


VALID_CSV = (
    "time_d,precipitation_m_d,potential_evaporation_m_d\n"
    "0,0.000,0.003\n"
    "1,0.010,0.002\n"
    "2,0.000,0.004\n"
)


def test_load_atmospheric_csv_valid(tmp_path: Path):
    csv_path = _write_csv(tmp_path / "atmosphere.csv", VALID_CSV)

    records, metadata = load_atmospheric_records_from_csv(
        csv_path,
        simulation_end_time=2.0,
    )

    assert [record["time"] for record in records] == [0.0, 1.0, 2.0]
    assert records[1]["precipitation"] == pytest.approx(0.01)
    assert records[0]["evaporation"] == pytest.approx(0.003)
    assert metadata["record_count"] == 3
    assert metadata["time_range"] == [0.0, 2.0]
    assert metadata["total_precipitation"] == pytest.approx(0.01)
    assert metadata["total_potential_evaporation"] == pytest.approx(0.005)
    assert metadata["max_precipitation_rate"] == pytest.approx(0.01)
    assert metadata["max_potential_evaporation_rate"] == pytest.approx(0.004)
    assert metadata["covers_simulation_end_time"] is True
    assert metadata["time_unit"] == "day"
    assert metadata["length_unit"] == "m"


def test_load_atmospheric_csv_missing_file(tmp_path: Path):
    with pytest.raises(AtmosphericCsvError, match="not found"):
        load_atmospheric_records_from_csv(tmp_path / "missing.csv")


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("time_d,precipitation_m_d\n0,0.0\n", "potential_evaporation_m_d"),
        ("time_d,precipitation_m_d,potential_evaporation_m_d\n", "empty"),
        ("time_d,precipitation_m_d,potential_evaporation_m_d\nbad,0,0\n", "time_d"),
        ("time_d,precipitation_m_d,potential_evaporation_m_d\n0,bad,0\n", "precipitation_m_d"),
        ("time_d,precipitation_m_d,potential_evaporation_m_d\n0,0,bad\n", "potential_evaporation_m_d"),
        ("time_d,precipitation_m_d,potential_evaporation_m_d\n0,-0.1,0\n", "non-negative"),
        ("time_d,precipitation_m_d,potential_evaporation_m_d\n0,0,-0.1\n", "non-negative"),
        ("time_d,precipitation_m_d,potential_evaporation_m_d\n-1,0,0\n", "non-negative"),
        ("time_d,precipitation_m_d,potential_evaporation_m_d\n0,0,0\n2,0,0\n1,0,0\n", "increasing"),
        ("time_d,precipitation_m_d,potential_evaporation_m_d\n0,,0\n", "missing"),
    ],
)
def test_load_atmospheric_csv_validation_errors(tmp_path: Path, body: str, message: str):
    csv_path = _write_csv(tmp_path / "bad.csv", body)

    with pytest.raises(AtmosphericCsvError, match=message):
        load_atmospheric_records_from_csv(csv_path)


def test_load_atmospheric_csv_rejects_insufficient_coverage(tmp_path: Path):
    csv_path = _write_csv(tmp_path / "short.csv", VALID_CSV)

    with pytest.raises(AtmosphericCsvError, match="simulation end time"):
        load_atmospheric_records_from_csv(csv_path, simulation_end_time=3.0)


def test_load_config_resolves_atmospheric_source_csv(tmp_path: Path):
    csv_path = _write_csv(tmp_path / "atmosphere.csv", VALID_CSV)
    config_path = tmp_path / "csv_config.json"
    config_path.write_text(
        json.dumps(_csv_config_raw(source_csv=csv_path.name), indent=2),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.atmospheric is not None
    assert len(config.atmospheric.records) == 3
    assert config.atmospheric.records[1].precipitation == pytest.approx(0.01)
    assert config.atmospheric.source_metadata is not None
    assert config.atmospheric.source_metadata.source_type == "csv"
    assert config.atmospheric.source_metadata.record_count == 3


def test_load_config_accepts_source_csv_on_upper_boundary(tmp_path: Path):
    csv_path = _write_csv(tmp_path / "atmosphere.csv", VALID_CSV)
    raw = _csv_config_raw(source_csv=None)
    raw["upper_boundary"] = {
        "type": "atmospheric",
        "source_csv": csv_path.name,
        "time_column": "time_d",
        "precipitation_column": "precipitation_m_d",
        "potential_evaporation_column": "potential_evaporation_m_d",
        "units": {"time": "day", "length": "m"},
    }
    raw.pop("atmospheric")
    config_path = tmp_path / "upper_boundary_csv_config.json"
    config_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    config = load_config(config_path)

    assert config.atmospheric is not None
    assert len(config.atmospheric.records) == 3
    assert config.atmospheric.source_metadata is not None


def test_inline_atmospheric_records_still_validate():
    raw = _csv_config_raw(source_csv=None)
    raw["atmospheric"] = {
        "enabled": True,
        "records": [
            {
                "time": 0.0,
                "precipitation": 0.0,
                "evaporation": 0.003,
                "hCritA": -10000.0,
            },
            {
                "time": 2.0,
                "precipitation": 0.01,
                "evaporation": 0.002,
                "hCritA": -10000.0,
            },
        ],
    }

    config_path = Path(__file__).parent / "_inline_atmospheric_tmp.json"
    try:
        config_path.write_text(json.dumps(raw), encoding="utf-8")
        config = load_config(config_path)
    finally:
        config_path.unlink(missing_ok=True)

    assert config.atmospheric is not None
    assert [record.time for record in config.atmospheric.records] == [0.0, 2.0]
    assert config.atmospheric.source_metadata is None


def test_bundled_csv_atmospheric_demo_config_loads():
    config = load_config(
        Path(__file__).resolve().parents[1]
        / "config"
        / "csv_atmospheric_boundary_test.json"
    )

    assert config.case_id == "csv_atmospheric_boundary_test"
    assert config.atmospheric is not None
    assert len(config.atmospheric.records) == 31
    assert config.atmospheric.records[-1].time == pytest.approx(30.0)
    assert config.atmospheric.source_metadata is not None
    assert config.atmospheric.source_metadata.covers_simulation_end_time is True


def _csv_config_raw(*, source_csv: str | None) -> dict:
    atmospheric = {
        "enabled": True,
        "source_csv": source_csv,
        "time_column": "time_d",
        "precipitation_column": "precipitation_m_d",
        "potential_evaporation_column": "potential_evaporation_m_d",
        "units": {
            "time": "day",
            "length": "m",
        },
    }
    if source_csv is None:
        atmospheric.pop("source_csv")
        atmospheric.pop("time_column")
        atmospheric.pop("precipitation_column")
        atmospheric.pop("potential_evaporation_column")
        atmospheric.pop("units")
    return {
        "project_name": "csv atmospheric test",
        "case_id": "csv_atmospheric_test",
        "simulation_time": {
            "t_init": 0.0,
            "t_end": 2.0,
            "dt_init": 0.001,
            "units": "days",
        },
        "soil_profile": [
            {"depth_top": 0.0, "depth_bottom": 1.0, "material_id": 1},
        ],
        "van_genuchten": [
            {
                "material_id": 1,
                "theta_r": 0.065,
                "theta_s": 0.41,
                "alpha": 7.5,
                "n": 1.89,
                "Ks": 1.061,
                "l": 0.5,
            },
        ],
        "initial_condition": {"type": "pressure_head", "value": -1.0},
        "upper_boundary": {"type": "atmospheric"},
        "lower_boundary": {"type": "free_drainage"},
        "atmospheric": atmospheric,
        "observation_depths": [0.3, 0.7],
        "output_settings": {
            "print_times": [1.0, 2.0],
            "print_interval": 0.5,
        },
    }
