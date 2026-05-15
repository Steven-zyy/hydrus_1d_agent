"""Tests for milestone 1: config loading, schema validation, run folder creation."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from hydrus_agent import ConfigError, create_run_folder, load_config
from hydrus_agent.schema import ModelConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_CONFIG = PROJECT_ROOT / "config" / "example_case.json"


def test_example_case_loads():
    """The bundled example config must validate cleanly."""
    config = load_config(EXAMPLE_CONFIG)
    assert config.project_name == "example sand column"
    assert config.case_id == "case_001"
    assert len(config.soil_profile) == 2
    assert config.simulation_time.t_end > config.simulation_time.t_init


def test_invalid_depths_rejected(tmp_path):
    """A soil layer with depth_bottom <= depth_top must fail validation."""
    raw = json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8"))
    bad = copy.deepcopy(raw)
    # Flip the first layer so it is invalid.
    bad["soil_profile"][0]["depth_top"] = 0.5
    bad["soil_profile"][0]["depth_bottom"] = 0.2

    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")

    with pytest.raises(ConfigError) as excinfo:
        load_config(bad_path)
    msg = str(excinfo.value)
    assert "depth_bottom" in msg
    assert "depth_top" in msg


def test_run_folder_created(tmp_path):
    """create_run_folder must produce <runs>/<case_id>/ with the expected subfolders."""
    config = load_config(EXAMPLE_CONFIG)
    case_dir = create_run_folder(config, runs_root=tmp_path)

    assert case_dir == tmp_path / "case_001"
    assert case_dir.is_dir()
    for sub in ("inputs", "outputs", "logs"):
        assert (case_dir / sub).is_dir(), f"missing subfolder: {sub}"
    assert (case_dir / "config.json").is_file()

    # And: refusing to overwrite is part of the contract.
    with pytest.raises(FileExistsError):
        create_run_folder(config, runs_root=tmp_path)


def test_atmospheric_config_validates_with_forcing_records():
    """Atmospheric water-flow configs must carry explicit ATMOSPH records."""
    raw = json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8"))
    raw["case_id"] = "schema_atmospheric"
    raw["simulation_time"] = {
        "t_init": 0.0,
        "t_end": 1.0,
        "dt_init": 0.001,
        "units": "days",
    }
    raw["output_settings"] = {
        "print_times": [0.25, 0.5, 0.75, 1.0],
        "print_interval": 0.05,
    }
    raw["upper_boundary"] = {"type": "atmospheric"}
    raw["atmospheric"] = {
        "enabled": True,
        "records": [
            {
                "time": 0.0,
                "precipitation": 0.0,
                "evaporation": 0.0,
                "hCritA": -10000.0,
            },
            {
                "time": 1.0,
                "precipitation": 0.001,
                "evaporation": 0.0,
                "hCritA": -10000.0,
            },
        ],
    }

    config = ModelConfig.model_validate(raw)

    assert config.upper_boundary.type.value == "atmospheric"
    assert config.atmospheric is not None
    assert config.atmospheric.enabled is True
    assert [record.time for record in config.atmospheric.records] == [0.0, 1.0]
    assert config.atmospheric.records[1].precipitation == pytest.approx(0.001)


def test_atmospheric_boundary_requires_enabled_forcing_records():
    raw = json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8"))
    raw["upper_boundary"] = {"type": "atmospheric"}
    raw.pop("atmospheric", None)

    with pytest.raises(Exception) as excinfo:
        ModelConfig.model_validate(raw)

    assert "atmospheric" in str(excinfo.value).lower()
    assert "records" in str(excinfo.value).lower()


def test_root_uptake_config_validates_with_atmospheric_forcing():
    raw = json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8"))
    raw["case_id"] = "schema_root_uptake"
    raw["simulation_time"] = {
        "t_init": 0.0,
        "t_end": 1.0,
        "dt_init": 0.001,
        "units": "days",
    }
    raw["output_settings"] = {
        "print_times": [0.25, 0.5, 0.75, 1.0],
        "print_interval": 0.05,
    }
    raw["soil_profile"] = [
        {"depth_top": 0.0, "depth_bottom": 1.0, "material_id": 1},
    ]
    raw["upper_boundary"] = {"type": "atmospheric"}
    raw["lower_boundary"] = {"type": "free_drainage"}
    raw["atmospheric"] = {
        "enabled": True,
        "records": [
            {
                "time": 0.0,
                "precipitation": 0.0,
                "evaporation": 0.0,
                "hCritA": -10000.0,
            },
            {
                "time": 1.0,
                "precipitation": 0.001,
                "evaporation": 0.0,
                "hCritA": -10000.0,
            },
        ],
    }
    raw["root_uptake"] = {
        "enabled": True,
        "model": "simple",
        "root_depth": 0.5,
        "potential_transpiration": 0.001,
        "distribution": "uniform",
    }

    config = ModelConfig.model_validate(raw)

    assert config.root_uptake is not None
    assert config.root_uptake.enabled is True
    assert config.root_uptake.root_depth == pytest.approx(0.5)
    assert config.root_uptake.potential_transpiration == pytest.approx(0.001)


def test_root_uptake_rejects_depth_outside_profile():
    raw = json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8"))
    raw["case_id"] = "schema_root_uptake_bad_depth"
    raw["soil_profile"] = [
        {"depth_top": 0.0, "depth_bottom": 1.0, "material_id": 1},
    ]
    raw["upper_boundary"] = {"type": "atmospheric"}
    raw["atmospheric"] = {
        "enabled": True,
        "records": [
            {
                "time": 0.0,
                "precipitation": 0.0,
                "evaporation": 0.0,
                "hCritA": -10000.0,
            },
            {
                "time": 1.0,
                "precipitation": 0.001,
                "evaporation": 0.0,
                "hCritA": -10000.0,
            },
        ],
    }
    raw["root_uptake"] = {
        "enabled": True,
        "model": "simple",
        "root_depth": 1.5,
        "potential_transpiration": 0.001,
        "distribution": "uniform",
    }

    with pytest.raises(Exception) as excinfo:
        ModelConfig.model_validate(raw)

    assert "root_depth" in str(excinfo.value)
    assert "soil profile" in str(excinfo.value)


def test_root_uptake_requires_atmospheric_boundary():
    raw = json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8"))
    raw["case_id"] = "schema_root_uptake_without_atmosphere"
    raw["upper_boundary"] = {"type": "constant_flux", "flux": 0.001}
    raw.pop("atmospheric", None)
    raw["root_uptake"] = {
        "enabled": True,
        "model": "simple",
        "root_depth": 0.5,
        "potential_transpiration": 0.001,
        "distribution": "uniform",
    }

    with pytest.raises(Exception) as excinfo:
        ModelConfig.model_validate(raw)

    assert "root uptake" in str(excinfo.value).lower()
    assert "atmospheric" in str(excinfo.value).lower()


def _simple_solute_raw() -> dict:
    raw = json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8"))
    raw["case_id"] = "schema_simple_solute"
    raw["simulation_time"] = {
        "t_init": 0.0,
        "t_end": 1.0,
        "dt_init": 0.001,
        "units": "days",
    }
    raw["soil_profile"] = [
        {"depth_top": 0.0, "depth_bottom": 1.0, "material_id": 1},
    ]
    raw["upper_boundary"] = {"type": "constant_flux", "flux": 0.001}
    raw["lower_boundary"] = {"type": "free_drainage"}
    raw.pop("atmospheric", None)
    raw.pop("root_uptake", None)
    raw["observation_depths"] = [0.25, 0.75]
    raw["output_settings"] = {
        "print_times": [0.25, 0.5, 0.75, 1.0],
        "print_interval": 0.05,
    }
    raw["solute_transport"] = {
        "enabled": True,
        "model": "conservative",
        "species": [
            {
                "name": "tracer",
                "initial_concentration": 0.0,
                "upper_boundary_concentration": 1.0,
                "diffusion_coefficient": 0.0,
                "dispersivity": 0.01,
            }
        ],
    }
    return raw


def test_solute_transport_config_validates_one_conservative_species():
    config = ModelConfig.model_validate(_simple_solute_raw())

    assert config.solute_transport is not None
    assert config.solute_transport.enabled is True
    assert config.solute_transport.model.value == "conservative"
    species = config.solute_transport.species[0]
    assert species.name == "tracer"
    assert species.initial_concentration == pytest.approx(0.0)
    assert species.upper_boundary_concentration == pytest.approx(1.0)
    assert species.dispersivity == pytest.approx(0.01)


def test_solute_transport_rejects_multiple_species():
    raw = _simple_solute_raw()
    raw["solute_transport"]["species"].append({
        "name": "second",
        "initial_concentration": 0.0,
        "upper_boundary_concentration": 1.0,
        "diffusion_coefficient": 0.0,
        "dispersivity": 0.01,
    })

    with pytest.raises(Exception) as excinfo:
        ModelConfig.model_validate(raw)

    assert "one solute" in str(excinfo.value).lower()


def test_solute_transport_rejects_adsorption_and_decay_fields():
    raw = _simple_solute_raw()
    raw["solute_transport"]["species"][0]["adsorption_coefficient"] = 0.1
    raw["solute_transport"]["species"][0]["decay_rate"] = 0.01

    with pytest.raises(Exception) as excinfo:
        ModelConfig.model_validate(raw)

    msg = str(excinfo.value).lower()
    assert "adsorption" in msg
    assert "decay" in msg


def test_solute_transport_rejects_negative_concentration_and_dispersivity():
    raw = _simple_solute_raw()
    raw["solute_transport"]["species"][0]["upper_boundary_concentration"] = -1.0
    raw["solute_transport"]["species"][0]["dispersivity"] = -0.01

    with pytest.raises(Exception) as excinfo:
        ModelConfig.model_validate(raw)

    msg = str(excinfo.value).lower()
    assert "upper_boundary_concentration" in msg
    assert "dispersivity" in msg
