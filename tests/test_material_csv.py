from __future__ import annotations

import json
from pathlib import Path

import pytest

from hydrus_agent import ConfigError, load_config
from hydrus_agent.material_csv import (
    MaterialCsvError,
    load_van_genuchten_from_csv,
)


VALID_MATERIAL_CSV = (
    "material,theta_r,theta_s,alpha_1_m,n,Ks_m_d,l\n"
    "sandy_loam,0.065,0.410,7.5,1.89,1.061,0.5\n"
    "sand,0.045,0.430,14.5,2.68,7.128,0.5\n"
)


def _write_csv(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_load_material_csv_valid(tmp_path: Path):
    csv_path = _write_csv(tmp_path / "materials.csv", VALID_MATERIAL_CSV)

    materials, metadata = load_van_genuchten_from_csv(csv_path)

    assert [material["material_id"] for material in materials] == [1, 2]
    assert materials[0]["theta_r"] == pytest.approx(0.065)
    assert materials[0]["theta_s"] == pytest.approx(0.410)
    assert materials[0]["alpha"] == pytest.approx(7.5)
    assert materials[0]["n"] == pytest.approx(1.89)
    assert materials[0]["Ks"] == pytest.approx(1.061)
    assert materials[0]["l"] == pytest.approx(0.5)
    assert metadata["source_type"] == "csv"
    assert metadata["material_count"] == 2
    assert metadata["material_names"] == ["sandy_loam", "sand"]
    assert metadata["name_to_material_id"] == {"sandy_loam": 1, "sand": 2}
    assert metadata["alpha_unit"] == "1/m"
    assert metadata["ks_unit"] == "m/day"


def test_load_material_csv_missing_file(tmp_path: Path):
    with pytest.raises(MaterialCsvError, match="not found"):
        load_van_genuchten_from_csv(tmp_path / "missing.csv")


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("material,theta_r,theta_s,alpha_1_m,n,Ks_m_d\nsand,0.1,0.4,1,2,1\n", "l"),
        ("material,theta_r,theta_s,alpha_1_m,n,Ks_m_d,l\n", "empty"),
        ("material,theta_r,theta_s,alpha_1_m,n,Ks_m_d,l\nsand,0.1,0.4,1,2,1,0.5\nsand,0.1,0.4,1,2,1,0.5\n", "unique"),
        ("material,theta_r,theta_s,alpha_1_m,n,Ks_m_d,l\n,0.1,0.4,1,2,1,0.5\n", "non-empty"),
        ("material,theta_r,theta_s,alpha_1_m,n,Ks_m_d,l\nsand,,0.4,1,2,1,0.5\n", "missing"),
        ("material,theta_r,theta_s,alpha_1_m,n,Ks_m_d,l\nsand,bad,0.4,1,2,1,0.5\n", "theta_r"),
        ("material,theta_r,theta_s,alpha_1_m,n,Ks_m_d,l\nsand,0.1,bad,1,2,1,0.5\n", "theta_s"),
        ("material,theta_r,theta_s,alpha_1_m,n,Ks_m_d,l\nsand,0.1,0.4,bad,2,1,0.5\n", "alpha_1_m"),
        ("material,theta_r,theta_s,alpha_1_m,n,Ks_m_d,l\nsand,0.1,0.4,1,bad,1,0.5\n", "n"),
        ("material,theta_r,theta_s,alpha_1_m,n,Ks_m_d,l\nsand,0.1,0.4,1,2,bad,0.5\n", "Ks_m_d"),
        ("material,theta_r,theta_s,alpha_1_m,n,Ks_m_d,l\nsand,0.1,0.4,1,2,1,bad\n", "l"),
        ("material,theta_r,theta_s,alpha_1_m,n,Ks_m_d,l\nsand,-0.1,0.4,1,2,1,0.5\n", "theta_r"),
        ("material,theta_r,theta_s,alpha_1_m,n,Ks_m_d,l\nsand,0.4,0.4,1,2,1,0.5\n", "theta_s"),
        ("material,theta_r,theta_s,alpha_1_m,n,Ks_m_d,l\nsand,0.1,0.4,0,2,1,0.5\n", "alpha_1_m"),
        ("material,theta_r,theta_s,alpha_1_m,n,Ks_m_d,l\nsand,0.1,0.4,1,1,1,0.5\n", "greater than 1"),
        ("material,theta_r,theta_s,alpha_1_m,n,Ks_m_d,l\nsand,0.1,0.4,1,2,0,0.5\n", "Ks_m_d"),
    ],
)
def test_load_material_csv_validation_errors(tmp_path: Path, body: str, message: str):
    csv_path = _write_csv(tmp_path / "bad_materials.csv", body)

    with pytest.raises(MaterialCsvError, match=message):
        load_van_genuchten_from_csv(csv_path)


def test_load_config_resolves_material_source_csv(tmp_path: Path):
    csv_path = _write_csv(tmp_path / "materials.csv", VALID_MATERIAL_CSV)
    raw = _material_csv_config(source_csv=csv_path.name)
    config_path = tmp_path / "material_csv_config.json"
    config_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    config = load_config(config_path)

    assert [layer.material_id for layer in config.soil_profile] == [1, 2]
    assert len(config.van_genuchten) == 2
    assert config.van_genuchten[0].alpha == pytest.approx(7.5)
    assert config.van_genuchten[1].Ks == pytest.approx(7.128)
    assert config.material_source is not None
    assert config.material_source.material_names == ["sandy_loam", "sand"]


def test_load_config_rejects_layer_material_missing_from_csv(tmp_path: Path):
    csv_path = _write_csv(tmp_path / "materials.csv", VALID_MATERIAL_CSV)
    raw = _material_csv_config(source_csv=csv_path.name)
    raw["soil_profile"][1]["material"] = "clay"
    config_path = tmp_path / "bad_layer_material.json"
    config_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ConfigError, match="clay"):
        load_config(config_path)


def test_inline_material_definitions_still_validate():
    config = load_config(
        Path(__file__).resolve().parents[1] / "config" / "simple_runnable_case.json"
    )

    assert config.material_source is None
    assert len(config.van_genuchten) == 1


def test_bundled_material_csv_demo_config_loads():
    config = load_config(
        Path(__file__).resolve().parents[1]
        / "config"
        / "csv_atmospheric_and_materials_test.json"
    )

    assert config.case_id == "csv_atmospheric_and_materials_test"
    assert config.atmospheric is not None
    assert config.atmospheric.source_metadata is not None
    assert config.material_source is not None
    assert config.material_source.material_count == 2
    assert [layer.material_id for layer in config.soil_profile] == [1, 2]


def _material_csv_config(*, source_csv: str) -> dict:
    return {
        "project_name": "material csv test",
        "case_id": "material_csv_test",
        "simulation_time": {
            "t_init": 0.0,
            "t_end": 2.0,
            "dt_init": 0.001,
            "units": "days",
        },
        "soil_profile": [
            {"depth_top": 0.0, "depth_bottom": 1.0, "material": "sandy_loam"},
            {"depth_top": 1.0, "depth_bottom": 2.0, "material": "sand"},
        ],
        "van_genuchten": {
            "source_csv": source_csv,
        },
        "initial_condition": {"type": "pressure_head", "value": -1.0},
        "upper_boundary": {"type": "constant_flux", "flux": 0.0},
        "lower_boundary": {"type": "free_drainage"},
        "observation_depths": [0.3, 1.7],
        "output_settings": {
            "print_times": [1.0, 2.0],
            "print_interval": 0.5,
        },
    }
