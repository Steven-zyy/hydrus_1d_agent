"""Tests for milestone 8: natural-language config builder."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from hydrus_agent.config_builder import (
    ConfigBuildError,
    build_config_from_description,
    write_config,
)
from hydrus_agent.schema import LowerBoundaryType, UpperBoundaryType


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import main as cli  # noqa: E402


def _remove_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


def _remove_dir_if_empty(path: Path) -> None:
    if path.is_dir():
        path.rmdir()


EXAMPLE_DESCRIPTION = (
    "1 m sandy loam column, 1 day, 1 mm/day infiltration, "
    "free drainage lower boundary, initial pressure head -1 m, "
    "observations at 0.3 and 0.7 m"
)


def _write_atmospheric_csv(path: Path, *, final_time: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "time_d,precipitation_m_d,potential_evaporation_m_d\n"
        "0,0,0.003\n"
        f"{final_time},0.001,0.002\n",
        encoding="utf-8",
    )
    return path


def _write_material_csv(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "material,theta_r,theta_s,alpha_1_m,n,Ks_m_d,l\n"
        "sandy_loam,0.065,0.410,7.5,1.89,1.061,0.5\n"
        "sand,0.045,0.430,14.5,2.68,7.128,0.5\n",
        encoding="utf-8",
    )
    return path


def test_builds_valid_config_from_simple_description():
    result = build_config_from_description(
        EXAMPLE_DESCRIPTION,
        case_id="from_description",
    )

    cfg = result.config
    assert cfg.case_id == "from_description"
    assert cfg.simulation_time.t_init == 0.0
    assert cfg.simulation_time.t_end == pytest.approx(1.0)
    assert cfg.simulation_time.units.value == "days"
    assert len(cfg.soil_profile) == 1
    assert cfg.soil_profile[0].depth_top == 0.0
    assert cfg.soil_profile[0].depth_bottom == pytest.approx(1.0)
    assert cfg.upper_boundary.type == UpperBoundaryType.constant_flux
    assert cfg.upper_boundary.flux == pytest.approx(0.001)
    assert cfg.lower_boundary.type == LowerBoundaryType.free_drainage
    assert cfg.initial_condition.type.value == "pressure_head"
    assert cfg.initial_condition.value == pytest.approx(-1.0)
    assert cfg.observation_depths == [0.3, 0.7]
    assert cfg.output_settings.print_times == [0.25, 0.5, 0.75, 1.0]
    assert result.warnings


def test_builds_multiple_layers_with_matching_materials():
    result = build_config_from_description(
        "1 m column, 2 days, two layers: 0-0.3 m sand, "
        "0.3-1.0 m sandy loam, constant flux 2 mm/day, "
        "free drainage, initial pressure head -0.5 m, "
        "observations at 0.2 and 0.8 m, print times 0.5, 1.0, 2.0 days",
        case_id="layered_case",
    )

    cfg = result.config
    assert [layer.depth_bottom for layer in cfg.soil_profile] == [0.3, 1.0]
    assert [layer.material_id for layer in cfg.soil_profile] == [1, 2]
    assert [vg.material_id for vg in cfg.van_genuchten] == [1, 2]
    assert cfg.upper_boundary.flux == pytest.approx(0.002)
    assert cfg.output_settings.print_times == [0.5, 1.0, 2.0]


def test_builds_over_layers_and_linear_initial_pressure_head():
    result = build_config_from_description(
        "A 2 m soil column consists of 1 m clay over 1 m sand. "
        "Run the simulation for 10 days. The upper boundary is a constant "
        "1 m pressure head representing surface ponding. The lower boundary "
        "is free drainage. The initial pressure head is -1 m at top and "
        "gradually reduced to 1m at the bottom throughout the profile. "
        "Add observation depths at 0.3 m and 1.7 m.",
        case_id="two_layer_surface_ponding",
    )

    cfg = result.config
    assert cfg.simulation_time.t_end == pytest.approx(10.0)
    assert [layer.depth_bottom for layer in cfg.soil_profile] == [1.0, 2.0]
    assert [vg.material_id for vg in cfg.van_genuchten] == [1, 2]
    assert cfg.van_genuchten[0].Ks == pytest.approx(0.0048)
    assert cfg.van_genuchten[1].Ks == pytest.approx(7.128)
    assert cfg.upper_boundary.type == UpperBoundaryType.constant_head
    assert cfg.upper_boundary.head == pytest.approx(1.0)
    assert cfg.initial_condition.value == pytest.approx(-1.0)
    assert cfg.initial_condition.profile is not None
    assert [p.depth for p in cfg.initial_condition.profile] == [0.0, 2.0]
    assert [p.value for p in cfg.initial_condition.profile] == [-1.0, 1.0]
    assert cfg.observation_depths == [0.3, 1.7]


def test_rejects_atmospheric_boundary_as_out_of_scope():
    with pytest.raises(ConfigBuildError) as excinfo:
        build_config_from_description(
            "1 m sandy loam column, 1 day, atmospheric upper boundary, "
            "free drainage, initial pressure head -1 m",
        )
    msg = str(excinfo.value).lower()
    assert "atmospheric" in msg
    assert "rainfall" in msg or "precipitation" in msg


def test_builds_simple_atmospheric_config_from_rainfall_and_evaporation():
    result = build_config_from_description(
        "1 m sandy loam column, 1 day, atmospheric upper boundary with "
        "rainfall 1 mm/day and evaporation 0 mm/day, free drainage lower "
        "boundary, initial pressure head -1 m, observations at 0.3 and 0.7 m",
        case_id="simple_atmospheric_from_description",
    )

    cfg = result.config
    assert cfg.upper_boundary.type == UpperBoundaryType.atmospheric
    assert cfg.atmospheric is not None
    assert cfg.atmospheric.enabled is True
    assert [record.time for record in cfg.atmospheric.records] == [0.0, 1.0]
    assert cfg.atmospheric.records[0].precipitation == pytest.approx(0.0)
    assert cfg.atmospheric.records[1].precipitation == pytest.approx(0.001)
    assert cfg.atmospheric.records[1].evaporation == pytest.approx(0.0)
    assert cfg.atmospheric.records[1].hCritA == pytest.approx(-10000.0)


def test_builds_atmospheric_csv_config_from_description(tmp_path, monkeypatch):
    _write_atmospheric_csv(tmp_path / "atmosphere.csv", final_time=45)
    monkeypatch.chdir(tmp_path)

    result = build_config_from_description(
        "Build a 45-day HYDRUS-1D model for a 2 m sandy loam column. "
        "Use atmospheric upper boundary forcing from atmosphere.csv, "
        "use free drainage at the bottom, initial pressure head -1.5 m "
        "throughout, observation depths 0.2 and 1.8 m, and print times "
        "1, 10, 20, and 45 days.",
        case_id="atmospheric_csv_from_description",
    )

    cfg = result.config
    assert cfg.upper_boundary.type == UpperBoundaryType.atmospheric
    assert cfg.atmospheric is not None
    assert cfg.atmospheric.source_csv == "atmosphere.csv"
    assert cfg.atmospheric.time_column == "time_d"
    assert cfg.atmospheric.precipitation_column == "precipitation_m_d"
    assert cfg.atmospheric.potential_evaporation_column == "potential_evaporation_m_d"
    assert len(cfg.atmospheric.records) == 2
    assert cfg.atmospheric.source_metadata is not None
    assert cfg.atmospheric.source_metadata.record_count == 2


def test_builds_material_csv_config_from_description(tmp_path, monkeypatch):
    _write_material_csv(tmp_path / "materials.csv")
    monkeypatch.chdir(tmp_path)

    result = build_config_from_description(
        "Build a 2 day HYDRUS-1D model for a 2 m column with sandy loam "
        "from 0 to 1 m and sand from 1 to 2 m. Use material hydraulic "
        "parameters from materials.csv, use constant flux 1 mm/day, use "
        "free drainage at the bottom, initial pressure head -1 m throughout, "
        "observation depths 0.2 and 1.8 m, and print times 1 and 2 days.",
        case_id="material_csv_from_description",
    )

    cfg = result.config
    assert cfg.material_source is not None
    assert cfg.material_source.source_csv.endswith("materials.csv")
    assert cfg.material_source.material_names == ["sandy_loam", "sand"]
    assert [layer.material_id for layer in cfg.soil_profile] == [1, 2]
    assert [vg.Ks for vg in cfg.van_genuchten] == pytest.approx([1.061, 7.128])


def test_builds_atmospheric_and_material_csv_config_from_windows_style_paths(
    tmp_path, monkeypatch,
):
    input_dir = tmp_path / "test_inputs" / "language_dynamic_test"
    input_dir.mkdir(parents=True)
    _write_atmospheric_csv(input_dir / "atmosphere_dynamic_45d.csv", final_time=45)
    _write_material_csv(input_dir / "materials_vg_dynamic.csv")
    monkeypatch.chdir(tmp_path)

    result = build_config_from_description(
        "Build a 45-day HYDRUS-1D model for a 2 m column with sandy loam "
        "from 0 to 1 m and sand from 1 to 2 m. Use atmospheric upper "
        "boundary forcing from test_inputs\\language_dynamic_test\\"
        "atmosphere_dynamic_45d.csv, use material hydraulic parameters "
        "from test_inputs\\language_dynamic_test\\materials_vg_dynamic.csv, "
        "use free drainage at the bottom, initial pressure head -1.5 m "
        "throughout, observation depths 0.2, 0.6, 1.2, and 1.8 m, and "
        "print times 1, 3, 5, 7, 10, 14, 20, 25, 30, 35, 40, and 45 days.",
        case_id="both_csv_from_description",
    )

    cfg = result.config
    assert cfg.upper_boundary.type == UpperBoundaryType.atmospheric
    assert cfg.atmospheric is not None
    assert cfg.atmospheric.source_csv.endswith("atmosphere_dynamic_45d.csv")
    assert cfg.material_source is not None
    assert cfg.material_source.source_csv.endswith("materials_vg_dynamic.csv")
    assert [layer.material_id for layer in cfg.soil_profile] == [1, 2]
    assert cfg.initial_condition.value == pytest.approx(-1.5)
    assert cfg.observation_depths == [0.2, 0.6, 1.2, 1.8]
    assert cfg.output_settings.print_times[-1] == pytest.approx(45.0)


def test_builds_simple_root_uptake_config_from_description():
    result = build_config_from_description(
        "1 m sandy loam column, 1 day, atmospheric upper boundary with "
        "rainfall 1 mm/day and evaporation 0 mm/day, with root uptake, "
        "root depth 0.5 m, potential transpiration 1 mm/day, uniform root "
        "distribution, free drainage lower boundary, initial pressure head "
        "-1 m, observations at 0.25 and 0.75 m",
        case_id="simple_root_uptake_from_description",
    )

    cfg = result.config
    assert cfg.upper_boundary.type == UpperBoundaryType.atmospheric
    assert cfg.root_uptake is not None
    assert cfg.root_uptake.enabled is True
    assert cfg.root_uptake.root_depth == pytest.approx(0.5)
    assert cfg.root_uptake.potential_transpiration == pytest.approx(0.001)
    assert cfg.root_uptake.distribution.value == "uniform"


def test_builds_simple_conservative_solute_config_from_description():
    result = build_config_from_description(
        "1 m sandy loam column, 1 day, 1 mm/day infiltration, free drainage "
        "lower boundary, initial pressure head -1 m, conservative tracer, "
        "initial concentration 0, upper boundary concentration 1, "
        "dispersivity 0.01 m, observations at 0.25 and 0.75 m",
        case_id="simple_solute_from_description",
    )

    cfg = result.config
    assert cfg.solute_transport is not None
    assert cfg.solute_transport.enabled is True
    assert cfg.solute_transport.model.value == "conservative"
    species = cfg.solute_transport.species[0]
    assert species.name == "tracer"
    assert species.initial_concentration == pytest.approx(0.0)
    assert species.upper_boundary_concentration == pytest.approx(1.0)
    assert species.dispersivity == pytest.approx(0.01)


def test_unsupported_solute_description_fails_clearly():
    with pytest.raises(ConfigBuildError) as excinfo:
        build_config_from_description(
            "1 m sandy loam column, 1 day, 1 mm/day infiltration, "
            "free drainage, initial pressure head -1 m, conservative tracer "
            "with adsorption and decay",
        )

    msg = str(excinfo.value).lower()
    assert "solute" in msg
    assert "adsorption" in msg


@pytest.mark.parametrize(
    "unsupported",
    [
        "multiple solutes",
        "nitrification reaction chain",
        "volatile solute",
        "salinity root stress",
        "non-equilibrium transport",
    ],
)
def test_unsupported_solute_variants_fail_clearly(unsupported):
    with pytest.raises(ConfigBuildError) as excinfo:
        build_config_from_description(
            "1 m sandy loam column, 1 day, 1 mm/day infiltration, "
            "free drainage, initial pressure head -1 m, solute transport "
            f"with {unsupported}",
        )

    msg = str(excinfo.value).lower()
    assert "solute" in msg
    assert unsupported.split()[0] in msg or "reaction" in msg


def test_unsupported_root_uptake_description_fails_clearly():
    with pytest.raises(ConfigBuildError) as excinfo:
        build_config_from_description(
            "1 m sandy loam column, 1 day, atmospheric upper boundary with "
            "rainfall 1 mm/day, with root uptake and salinity stress, root "
            "depth 0.5 m, potential transpiration 1 mm/day, free drainage, "
            "initial pressure head -1 m",
        )

    msg = str(excinfo.value).lower()
    assert "root uptake" in msg
    assert "salinity" in msg


def test_write_config_round_trips_valid_json():
    result = build_config_from_description(
        EXAMPLE_DESCRIPTION,
        case_id="from_description",
    )
    output_path = PROJECT_ROOT / "runs" / "_test_from_description.json"
    _remove_if_exists(output_path)
    try:
        path = write_config(result.config, output_path)

        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["case_id"] == "from_description"
        assert raw["upper_boundary"]["type"] == "constant_flux"
        assert raw["lower_boundary"]["type"] == "free_drainage"
    finally:
        _remove_if_exists(output_path)


def test_cli_describe_writes_config_without_creating_run_folder(
    monkeypatch, capsys,
):
    output_path = PROJECT_ROOT / "runs" / "_test_generated.json"
    runs_root = PROJECT_ROOT / "runs" / "_test_generated_runs"
    _remove_if_exists(output_path)
    monkeypatch.setattr(cli, "RUNS_ROOT", runs_root)

    def _boom(*args, **kwargs):
        raise AssertionError("--describe must not create run folders or run HYDRUS")

    monkeypatch.setattr(cli, "create_run_folder", _boom)

    try:
        rc = cli.main([
            "--describe", EXAMPLE_DESCRIPTION,
            "--write-config", str(output_path),
        ])

        out = capsys.readouterr().out
        assert rc == 0
        assert output_path.is_file()
        assert not runs_root.exists()
        assert "Generated HYDRUS-1D config" in out
        assert "HYDRUS was not run" in out
    finally:
        _remove_if_exists(output_path)


def test_cli_review_prints_validation_status(monkeypatch, capsys):
    output_path = PROJECT_ROOT / "runs" / "_test_reviewed.json"
    _remove_if_exists(output_path)
    monkeypatch.setattr(cli, "RUNS_ROOT", PROJECT_ROOT / "runs" / "_test_review_runs")

    try:
        rc = cli.main([
            "--describe", EXAMPLE_DESCRIPTION,
            "--write-config", str(output_path),
            "--review",
        ])

        out = capsys.readouterr().out
        assert rc == 0
        assert output_path.is_file()
        assert "Generated HYDRUS-1D config" in out
        assert "Validation status: valid ModelConfig" in out
        assert "HYDRUS was not run" in out
    finally:
        _remove_if_exists(output_path)


def test_cli_describe_review_shows_csv_source_metadata(
    monkeypatch, capsys, tmp_path,
):
    input_dir = tmp_path / "test_inputs" / "language_dynamic_test"
    _write_atmospheric_csv(input_dir / "atmosphere_dynamic_45d.csv", final_time=45)
    _write_material_csv(input_dir / "materials_vg_dynamic.csv")
    output_path = tmp_path / "generated_csv_config.json"
    state_dir = tmp_path / "review_state"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "REVIEW_STATE_DIR", state_dir)

    rc = cli.main([
        "--describe",
        "Build a 45-day HYDRUS-1D model for a 2 m column with sandy loam "
        "from 0 to 1 m and sand from 1 to 2 m. Use atmospheric upper "
        "boundary forcing from test_inputs\\language_dynamic_test\\"
        "atmosphere_dynamic_45d.csv, use material hydraulic parameters "
        "from test_inputs\\language_dynamic_test\\materials_vg_dynamic.csv, "
        "use free drainage at the bottom, initial pressure head -1.5 m "
        "throughout, observation depths 0.2, 0.6, 1.2, and 1.8 m, and "
        "print times 1, 3, 5, 7, 10, 14, 20, 25, 30, 35, 40, and 45 days.",
        "--write-config", str(output_path),
        "--review",
    ])

    out = capsys.readouterr().out
    assert rc == 0
    assert output_path.is_file()
    raw = json.loads(output_path.read_text(encoding="utf-8"))
    assert raw["atmospheric"]["source_csv"].endswith("atmosphere_dynamic_45d.csv")
    assert "records" not in raw["atmospheric"]
    assert raw["van_genuchten"]["source_csv"].endswith("materials_vg_dynamic.csv")
    assert raw["soil_profile"][0]["material"] == "sandy_loam"
    assert "Validation status: valid ModelConfig" in out
    assert "atmospheric CSV" in out
    assert "atmosphere_dynamic_45d.csv" in out
    assert "material CSV" in out
    assert "materials_vg_dynamic.csv" in out
    assert (state_dir / "last_review.json").is_file()


def test_cli_run_after_review_triggers_pipeline_only_when_explicit(
    monkeypatch, capsys,
):
    output_path = PROJECT_ROOT / "runs" / "_test_review_then_run.json"
    _remove_if_exists(output_path)
    calls = []

    def _fake_run_all(config_path, *, overwrite_run, timeout, launch_mode):
        calls.append({
            "config_path": Path(config_path),
            "overwrite_run": overwrite_run,
            "timeout": timeout,
            "launch_mode": launch_mode,
        })
        return 0

    monkeypatch.setattr(cli, "_run_all", _fake_run_all)

    try:
        rc = cli.main([
            "--describe", EXAMPLE_DESCRIPTION,
            "--write-config", str(output_path),
            "--run-after-review",
            "--overwrite-run",
            "--timeout", "30",
            "--hydrus-launch-mode", "argv",
        ])

        out = capsys.readouterr().out
        assert rc == 0
        assert output_path.is_file()
        assert "Validation status: valid ModelConfig" in out
        assert "Running full pipeline from reviewed config" in out
        assert calls == [{
            "config_path": output_path,
            "overwrite_run": True,
            "timeout": 30.0,
            "launch_mode": "argv",
        }]
    finally:
        _remove_if_exists(output_path)


def test_cli_describe_without_run_after_review_does_not_trigger_pipeline(
    monkeypatch,
):
    output_path = PROJECT_ROOT / "runs" / "_test_review_only.json"
    _remove_if_exists(output_path)

    def _boom(*args, **kwargs):
        raise AssertionError("Pipeline must only run with --run-after-review")

    monkeypatch.setattr(cli, "_run_all", _boom)

    try:
        rc = cli.main([
            "--describe", EXAMPLE_DESCRIPTION,
            "--write-config", str(output_path),
            "--review",
        ])

        assert rc == 0
        assert output_path.is_file()
    finally:
        _remove_if_exists(output_path)


def test_invalid_description_fails_before_pipeline_execution(
    monkeypatch,
):
    output_path = PROJECT_ROOT / "runs" / "_test_invalid.json"
    _remove_if_exists(output_path)

    def _boom(*args, **kwargs):
        raise AssertionError("Pipeline must not run after invalid description")

    monkeypatch.setattr(cli, "_run_all", _boom)

    try:
        rc = cli.main([
            "--describe", "1 m sandy loam column, 1 day, atmospheric upper boundary",
            "--write-config", str(output_path),
            "--run-after-review",
        ])

        assert rc == 1
        assert not output_path.exists()
    finally:
        _remove_if_exists(output_path)


def test_review_writes_last_review_json(monkeypatch, capsys):
    output_path = PROJECT_ROOT / "runs" / "_test_review_state_config.json"
    state_dir = PROJECT_ROOT / "runs" / "_test_review_state"
    state_path = state_dir / "last_review.json"
    _remove_if_exists(output_path)
    _remove_if_exists(state_path)
    _remove_dir_if_empty(state_dir)
    monkeypatch.setattr(cli, "REVIEW_STATE_DIR", state_dir)

    try:
        rc = cli.main([
            "--describe", EXAMPLE_DESCRIPTION,
            "--write-config", str(output_path),
            "--review",
        ])

        assert rc == 0
        assert state_path.is_file()
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["config_path"] == str(output_path)
        assert state["absolute_config_path"] == str(output_path.resolve())
        assert state["case_id"] == "test_review_state_config"
        assert state["project_name"] == "natural language HYDRUS model"
        assert state["simulation_time"]["start"] == 0.0
        assert state["simulation_time"]["end"] == 1.0
        assert state["simulation_time"]["units"] == "days"
        assert len(state["content_hash_sha256"]) == 64
        assert state["timestamp"]
    finally:
        _remove_if_exists(output_path)
        _remove_if_exists(state_path)
        _remove_dir_if_empty(state_dir)


def test_running_reviewed_config_passes_consistency_guard(monkeypatch):
    output_path = PROJECT_ROOT / "runs" / "_test_reviewed_run_config.json"
    state_dir = PROJECT_ROOT / "runs" / "_test_reviewed_run_state"
    state_path = state_dir / "last_review.json"
    _remove_if_exists(output_path)
    _remove_if_exists(state_path)
    _remove_dir_if_empty(state_dir)
    calls = []
    monkeypatch.setattr(cli, "REVIEW_STATE_DIR", state_dir)

    def _fake_run_all(config_path, *, overwrite_run, timeout, launch_mode):
        calls.append(Path(config_path))
        return 0

    monkeypatch.setattr(cli, "_run_all", _fake_run_all)

    try:
        assert cli.main([
            "--describe", EXAMPLE_DESCRIPTION,
            "--write-config", str(output_path),
            "--review",
        ]) == 0

        rc = cli.main([
            "--config", str(output_path),
            "--all",
            "--overwrite-run",
        ])

        assert rc == 0
        assert calls == [output_path]
    finally:
        _remove_if_exists(output_path)
        _remove_if_exists(state_path)
        _remove_dir_if_empty(state_dir)


def test_running_different_config_is_blocked(monkeypatch, capsys):
    reviewed_path = PROJECT_ROOT / "runs" / "_test_reviewed_guard_config.json"
    requested_path = PROJECT_ROOT / "runs" / "_test_requested_guard_config.json"
    state_dir = PROJECT_ROOT / "runs" / "_test_guard_state"
    state_path = state_dir / "last_review.json"
    _remove_if_exists(reviewed_path)
    _remove_if_exists(requested_path)
    _remove_if_exists(state_path)
    _remove_dir_if_empty(state_dir)
    monkeypatch.setattr(cli, "REVIEW_STATE_DIR", state_dir)

    def _boom(*args, **kwargs):
        raise AssertionError("Pipeline must not run when config mismatches review")

    monkeypatch.setattr(cli, "_run_all", _boom)

    try:
        assert cli.main([
            "--describe", EXAMPLE_DESCRIPTION,
            "--write-config", str(reviewed_path),
            "--review",
        ]) == 0
        result = build_config_from_description(EXAMPLE_DESCRIPTION, case_id=requested_path.stem)
        write_config(result.config, requested_path)

        rc = cli.main([
            "--config", str(requested_path),
            "--all",
        ])

        out = capsys.readouterr().out
        assert rc == 1
        assert "The config being run is not the last reviewed config." in out
        assert "Last reviewed config:" in out
        assert "Requested config:" in out
    finally:
        _remove_if_exists(reviewed_path)
        _remove_if_exists(requested_path)
        _remove_if_exists(state_path)
        _remove_dir_if_empty(state_dir)


def test_allow_config_mismatch_permits_advanced_use(monkeypatch):
    reviewed_path = PROJECT_ROOT / "runs" / "_test_reviewed_allow_config.json"
    requested_path = PROJECT_ROOT / "runs" / "_test_requested_allow_config.json"
    state_dir = PROJECT_ROOT / "runs" / "_test_allow_state"
    state_path = state_dir / "last_review.json"
    _remove_if_exists(reviewed_path)
    _remove_if_exists(requested_path)
    _remove_if_exists(state_path)
    _remove_dir_if_empty(state_dir)
    calls = []
    monkeypatch.setattr(cli, "REVIEW_STATE_DIR", state_dir)

    def _fake_run_all(config_path, *, overwrite_run, timeout, launch_mode):
        calls.append(Path(config_path))
        return 0

    monkeypatch.setattr(cli, "_run_all", _fake_run_all)

    try:
        assert cli.main([
            "--describe", EXAMPLE_DESCRIPTION,
            "--write-config", str(reviewed_path),
            "--review",
        ]) == 0
        result = build_config_from_description(EXAMPLE_DESCRIPTION, case_id=requested_path.stem)
        write_config(result.config, requested_path)

        rc = cli.main([
            "--config", str(requested_path),
            "--all",
            "--allow-config-mismatch",
        ])

        assert rc == 0
        assert calls == [requested_path]
    finally:
        _remove_if_exists(reviewed_path)
        _remove_if_exists(requested_path)
        _remove_if_exists(state_path)
        _remove_dir_if_empty(state_dir)


def test_modifying_reviewed_config_after_review_is_blocked(monkeypatch, capsys):
    output_path = PROJECT_ROOT / "runs" / "_test_modified_review_config.json"
    state_dir = PROJECT_ROOT / "runs" / "_test_modified_review_state"
    state_path = state_dir / "last_review.json"
    _remove_if_exists(output_path)
    _remove_if_exists(state_path)
    _remove_dir_if_empty(state_dir)
    monkeypatch.setattr(cli, "REVIEW_STATE_DIR", state_dir)

    def _boom(*args, **kwargs):
        raise AssertionError("Pipeline must not run when reviewed config changed")

    monkeypatch.setattr(cli, "_run_all", _boom)

    try:
        assert cli.main([
            "--describe", EXAMPLE_DESCRIPTION,
            "--write-config", str(output_path),
            "--review",
        ]) == 0
        raw = json.loads(output_path.read_text(encoding="utf-8"))
        raw["project_name"] = "modified after review"
        output_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

        rc = cli.main([
            "--config", str(output_path),
            "--all",
        ])

        out = capsys.readouterr().out
        assert rc == 1
        assert "The config being run is not the last reviewed config." in out
        assert "content_hash_sha256" in out
    finally:
        _remove_if_exists(output_path)
        _remove_if_exists(state_path)
        _remove_dir_if_empty(state_dir)
