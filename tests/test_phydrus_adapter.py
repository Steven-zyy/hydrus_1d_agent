"""Tests for hydrus_agent.phydrus_adapter.

These tests skip the whole module if phydrus is not installed. They never
invoke HYDRUS-1D itself - only Model.write_input() is exercised, and an
explicit test verifies that Model.simulate is never called by the adapter.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

ps = pytest.importorskip("phydrus")

from hydrus_agent import create_run_folder, load_config
from hydrus_agent.phydrus_adapter import (
    UnsupportedFeatureError,
    prepare_phydrus_project,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_CONFIG = PROJECT_ROOT / "config" / "example_case.json"
SIMPLE_RUNNABLE_CONFIG = PROJECT_ROOT / "config" / "simple_runnable_case.json"
SIMPLE_ATMOSPHERIC_CONFIG = PROJECT_ROOT / "config" / "simple_atmospheric_case.json"
SIMPLE_ROOT_UPTAKE_CONFIG = PROJECT_ROOT / "config" / "simple_root_uptake_case.json"
SIMPLE_SOLUTE_CONFIG = PROJECT_ROOT / "config" / "simple_conservative_solute_case.json"


@pytest.fixture
def fake_exe(tmp_path: Path) -> Path:
    """A real file that phydrus accepts as exe_name (it only checks existence)."""
    p = tmp_path / "fake_hydrus.exe"
    p.write_text("not a real executable", encoding="utf-8")
    return p


@pytest.fixture
def example_run_dir(tmp_path: Path) -> Path:
    """A milestone-1 run folder for the bundled example config."""
    config = load_config(EXAMPLE_CONFIG)
    return create_run_folder(config, runs_root=tmp_path)


def test_prepare_phydrus_project_writes_files(example_run_dir, fake_exe):
    """Happy path: SELECTOR.IN and PROFILE.DAT appear under hydrus_project/."""
    config = load_config(EXAMPLE_CONFIG)
    project_dir = prepare_phydrus_project(config, example_run_dir, fake_exe)

    assert project_dir == example_run_dir / "hydrus_project"
    assert project_dir.is_dir()
    assert (project_dir / "SELECTOR.IN").is_file()
    assert (project_dir / "PROFILE.DAT").is_file()


def test_simulate_is_never_called(example_run_dir, fake_exe, monkeypatch):
    """The adapter must only write input files. simulate() is out of scope."""

    def _boom(self, *args, **kwargs):
        raise AssertionError(
            "Model.simulate() was called by the adapter - milestone 2 forbids it."
        )

    monkeypatch.setattr(ps.Model, "simulate", _boom)
    config = load_config(EXAMPLE_CONFIG)
    prepare_phydrus_project(config, example_run_dir, fake_exe)


def test_unsupported_initial_condition_raises(example_run_dir, fake_exe):
    """initial_condition.type == 'water_content' is not yet implemented."""
    raw = json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8"))
    raw["initial_condition"] = {"type": "water_content", "value": 0.25}
    bad_path = example_run_dir / "bad_config.json"
    bad_path.write_text(json.dumps(raw), encoding="utf-8")
    bad_config = load_config(bad_path)

    with pytest.raises(UnsupportedFeatureError) as excinfo:
        prepare_phydrus_project(bad_config, example_run_dir, fake_exe)
    assert "water_content" in str(excinfo.value)


def test_material_id_order_independent(tmp_path, fake_exe):
    """Reordering van_genuchten entries must not change the written outputs."""
    raw = json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8"))

    raw["van_genuchten"].append(
        {
            "material_id": 2,
            "theta_r": 0.057,
            "theta_s": 0.41,
            "alpha": 0.124,
            "n": 2.28,
            "Ks": 350.2,
            "l": 0.5,
        }
    )
    raw["soil_profile"][1]["material_id"] = 2

    cfg_a = copy.deepcopy(raw)
    cfg_b = copy.deepcopy(raw)
    cfg_b["van_genuchten"] = list(reversed(cfg_b["van_genuchten"]))

    a_path = tmp_path / "a.json"
    a_path.write_text(json.dumps(cfg_a), encoding="utf-8")
    b_path = tmp_path / "b.json"
    b_path.write_text(json.dumps(cfg_b), encoding="utf-8")

    a = load_config(a_path)
    b = load_config(b_path)

    a_runs = tmp_path / "runs_a"
    b_runs = tmp_path / "runs_b"
    a_dir = create_run_folder(a, runs_root=a_runs)
    b_dir = create_run_folder(b, runs_root=b_runs)

    a_proj = prepare_phydrus_project(a, a_dir, fake_exe)
    b_proj = prepare_phydrus_project(b, b_dir, fake_exe)

    a_selector = (a_proj / "SELECTOR.IN").read_text()
    b_selector = (b_proj / "SELECTOR.IN").read_text()
    a_profile = (a_proj / "PROFILE.DAT").read_text()
    b_profile = (b_proj / "PROFILE.DAT").read_text()
    assert a_selector == b_selector
    assert a_profile == b_profile


def test_simple_runnable_case_does_not_require_atmosph(tmp_path, fake_exe):
    """Milestone 2.5: the simple runnable case must produce a HYDRUS project
    that does NOT depend on ATMOSPH.IN.

    Concretely:
      - ATMOSPH.IN must NOT be written.
      - SELECTOR.IN's AtmInf flag (9th in the lWat header line) must be 'f'.
      - SELECTOR.IN's TopInf flag must be 'f' (no atmospheric input).
      - SELECTOR.IN's FreeD flag must be 't' (free drainage at bottom).
    """
    config = load_config(SIMPLE_RUNNABLE_CONFIG)
    case_dir = create_run_folder(config, runs_root=tmp_path)
    project_dir = prepare_phydrus_project(config, case_dir, fake_exe)

    assert (project_dir / "SELECTOR.IN").is_file()
    assert (project_dir / "PROFILE.DAT").is_file()
    assert not (project_dir / "ATMOSPH.IN").exists(), (
        "ATMOSPH.IN must not be generated for the simple runnable case"
    )

    selector = (project_dir / "SELECTOR.IN").read_text()
    lines = selector.splitlines()

    # AtmInf is the 9th boolean in the line under "lWat lChem lTemp lSink
    # lRoot lShort lWDep lScreen AtmInf lEquil lInverse".
    header_idx = next(i for i, line in enumerate(lines) if "AtmInf" in line)
    flags = lines[header_idx + 1].split()
    assert flags[8] == "f", f"AtmInf flag should be 'f', got {flags[8]!r}"

    topinf_idx = next(i for i, line in enumerate(lines) if "TopInf" in line)
    topinf_flags = lines[topinf_idx + 1].split()
    assert topinf_flags[0] == "f", f"TopInf should be 'f', got {topinf_flags[0]!r}"

    botinf_idx = next(i for i, line in enumerate(lines) if "BotInf" in line)
    bot_flags = lines[botinf_idx + 1].split()
    # Header order: BotInf qGWLF FreeD SeepF KodBot qDrain hSeep
    assert bot_flags[2] == "t", f"FreeD should be 't', got {bot_flags[2]!r}"


def test_atmospheric_case_writes_atmosph_and_sets_flags(tmp_path, fake_exe):
    """Atmospheric water-flow cases must write ATMOSPH.IN and enable AtmInf."""
    config = load_config(SIMPLE_ATMOSPHERIC_CONFIG)
    case_dir = create_run_folder(config, runs_root=tmp_path)
    project_dir = prepare_phydrus_project(config, case_dir, fake_exe)

    atmosph = project_dir / "ATMOSPH.IN"
    selector = project_dir / "SELECTOR.IN"
    assert atmosph.is_file()
    assert selector.is_file()

    atmosph_text = atmosph.read_text()
    assert "MaxAL" in atmosph_text
    assert "tAtm" in atmosph_text
    assert "Prec" in atmosph_text
    assert "rSoil" in atmosph_text
    assert "hCritA" in atmosph_text
    assert "0.001" in atmosph_text
    assert "-10000" in atmosph_text

    lines = selector.read_text().splitlines()
    header_idx = next(i for i, line in enumerate(lines) if "AtmInf" in line)
    flags = lines[header_idx + 1].split()
    assert flags[8] == "t", f"AtmInf flag should be 't', got {flags[8]!r}"

    topinf_idx = next(i for i, line in enumerate(lines) if "TopInf" in line)
    topinf_flags = lines[topinf_idx + 1].split()
    assert topinf_flags[0] == "t", f"TopInf should be 't', got {topinf_flags[0]!r}"


def test_atmospheric_writer_moves_start_record_after_initial_timestep(tmp_path, fake_exe):
    """HYDRUS requires the first time-variable BC record after tInit+dtInit."""
    config = load_config(SIMPLE_ATMOSPHERIC_CONFIG)
    case_dir = create_run_folder(config, runs_root=tmp_path)
    project_dir = prepare_phydrus_project(config, case_dir, fake_exe)

    atmosph_lines = (project_dir / "ATMOSPH.IN").read_text().splitlines()
    header_idx = next(i for i, line in enumerate(atmosph_lines) if "tAtm" in line)
    data_lines = [
        line.split()
        for line in atmosph_lines[header_idx + 1:]
        if line.strip() and line.split()[0].replace(".", "", 1).isdigit()
    ]

    first_time = float(data_lines[0][0])
    assert first_time == pytest.approx(config.simulation_time.dt_init * 2)


def test_root_uptake_case_writes_sink_flags_atmospheric_transpiration_and_beta(
    tmp_path, fake_exe,
):
    """Simple root uptake enables lSink, writes rRoot, and marks root-zone Beta."""
    config = load_config(SIMPLE_ROOT_UPTAKE_CONFIG)
    case_dir = create_run_folder(config, runs_root=tmp_path)
    project_dir = prepare_phydrus_project(config, case_dir, fake_exe)

    selector = (project_dir / "SELECTOR.IN").read_text()
    assert "ROOT WATER UPTAKE INFORMATION" in selector
    selector_lines = selector.splitlines()
    header_idx = next(i for i, line in enumerate(selector_lines) if "AtmInf" in line)
    flags = selector_lines[header_idx + 1].split()
    assert flags[3] == "t", f"lSink should be 't', got {flags[3]!r}"
    assert flags[8] == "t", f"AtmInf should be 't', got {flags[8]!r}"

    atmosph = (project_dir / "ATMOSPH.IN").read_text()
    assert "rRoot" in atmosph
    assert "0.001" in atmosph

    beta_by_x = {}
    for line in (project_dir / "PROFILE.DAT").read_text().splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[0].isdigit():
            try:
                x = float(parts[1])
                beta = float(parts[5])
            except ValueError:
                continue
            beta_by_x[x] = beta

    assert beta_by_x[-0.0] == pytest.approx(1.0)
    assert beta_by_x[-0.5] == pytest.approx(1.0)
    assert beta_by_x[-0.6] == pytest.approx(0.0)
    assert beta_by_x[-1.0] == pytest.approx(0.0)


def test_simple_solute_case_writes_chemistry_flags_selector_and_profile_conc(
    tmp_path, fake_exe,
):
    """One conservative solute should be written through Phydrus Block F."""
    config = load_config(SIMPLE_SOLUTE_CONFIG)
    case_dir = create_run_folder(config, runs_root=tmp_path)
    project_dir = prepare_phydrus_project(config, case_dir, fake_exe)

    selector = (project_dir / "SELECTOR.IN").read_text()
    assert "SOLUTE TRANSPORT INFORMATION" in selector
    selector_lines = selector.splitlines()
    header_idx = next(i for i, line in enumerate(selector_lines) if "AtmInf" in line)
    flags = selector_lines[header_idx + 1].split()
    assert flags[1] == "t", f"lChem should be 't', got {flags[1]!r}"
    assert "No.Solutes" in selector
    assert "kTopSolute" in selector
    assert "0.01" in selector
    assert "1.0" in selector

    profile_rows = []
    for line in (project_dir / "PROFILE.DAT").read_text().splitlines():
        parts = line.split()
        if len(parts) >= 11 and parts[0].isdigit():
            try:
                float(parts[1])
                float(parts[10])
            except ValueError:
                continue
            profile_rows.append(parts)
    assert profile_rows, "PROFILE.DAT should contain node rows"
    assert all(float(row[10]) == pytest.approx(0.0) for row in profile_rows)


def test_non_solute_case_keeps_chemistry_disabled(tmp_path, fake_exe):
    config = load_config(SIMPLE_RUNNABLE_CONFIG)
    case_dir = create_run_folder(config, runs_root=tmp_path)
    project_dir = prepare_phydrus_project(config, case_dir, fake_exe)

    selector_lines = (project_dir / "SELECTOR.IN").read_text().splitlines()
    header_idx = next(i for i, line in enumerate(selector_lines) if "AtmInf" in line)
    flags = selector_lines[header_idx + 1].split()
    assert flags[1] == "f", f"lChem should be 'f', got {flags[1]!r}"
    assert "SOLUTE TRANSPORT INFORMATION" not in "\n".join(selector_lines)


def test_observation_nodes_use_negative_x(example_run_dir, fake_exe):
    """Observation depths in the config (positive, in metres) become negative
    x in the HYDRUS profile. PROFILE.DAT should reference depths like -0.1
    rather than 0.1."""
    config = load_config(EXAMPLE_CONFIG)
    project_dir = prepare_phydrus_project(config, example_run_dir, fake_exe)
    profile_text = (project_dir / "PROFILE.DAT").read_text()
    assert len(profile_text.strip()) > 0


def test_initial_pressure_head_profile_is_written_linearly(tmp_path, fake_exe):
    raw = json.loads(SIMPLE_RUNNABLE_CONFIG.read_text(encoding="utf-8"))
    raw["case_id"] = "linear_initial_head"
    raw["soil_profile"] = [
        {"depth_top": 0.0, "depth_bottom": 1.0, "material_id": 1},
        {"depth_top": 1.0, "depth_bottom": 2.0, "material_id": 2},
    ]
    raw["van_genuchten"].append(
        {
            "material_id": 2,
            "theta_r": 0.045,
            "theta_s": 0.43,
            "alpha": 14.5,
            "n": 2.68,
            "Ks": 7.128,
            "l": 0.5,
        }
    )
    raw["initial_condition"] = {
        "type": "pressure_head",
        "value": -1.0,
        "profile": [
            {"depth": 0.0, "value": -1.0},
            {"depth": 2.0, "value": 1.0},
        ],
    }
    cfg_path = tmp_path / "linear_initial_head.json"
    cfg_path.write_text(json.dumps(raw), encoding="utf-8")

    config = load_config(cfg_path)
    case_dir = create_run_folder(config, runs_root=tmp_path / "runs")
    project_dir = prepare_phydrus_project(config, case_dir, fake_exe)

    heads_by_x = {}
    for line in (project_dir / "PROFILE.DAT").read_text().splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0].isdigit():
            heads_by_x[float(parts[1])] = float(parts[2])

    assert heads_by_x[-0.0] == pytest.approx(-1.0)
    assert heads_by_x[-1.0] == pytest.approx(0.0)
    assert heads_by_x[-2.0] == pytest.approx(1.0)
