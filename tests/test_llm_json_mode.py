"""Tests for Milestone 22: LLM-assisted JSON configuration mode.

Covers:
- config/templates/llm_config_template.json is valid JSON and validates via load_config
- --write-config-template CLI flag (to file and to stdout)
- --print-config-schema CLI flag (to stdout and to file)
- Relative path preservation in _config_dump_for_user (Part D)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main as cli  # noqa: E402
from hydrus_agent.config_builder import _config_dump_for_user, _make_relative_if_under_root
from hydrus_agent.validator import load_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = PROJECT_ROOT / "config" / "templates" / "llm_config_template.json"


@pytest.fixture(autouse=True)
def isolated_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "RUNS_ROOT", tmp_path / "runs")
    return tmp_path / "runs"


# ---------------------------------------------------------------------------
# Part B: template file
# ---------------------------------------------------------------------------

def test_template_exists():
    assert TEMPLATE_PATH.is_file(), f"Template not found: {TEMPLATE_PATH}"


def test_template_is_valid_json():
    data = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "project_name" in data
    assert "case_id" in data
    assert "simulation_time" in data
    assert "soil_profile" in data
    assert "van_genuchten" in data
    assert "observation_depths" in data
    assert "output_settings" in data


def test_template_validates_as_model_config():
    """Template must load and validate without error."""
    config = load_config(TEMPLATE_PATH)
    assert config.case_id == "my_model_001"
    assert len(config.soil_profile) == 2
    assert config.simulation_time.t_end == 30.0
    assert config.lower_boundary.type.value == "free_drainage"


def test_template_uses_relative_csv_paths():
    """Template source_csv paths must be relative (portable)."""
    data = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    vg = data.get("van_genuchten", {})
    assert not Path(vg.get("source_csv", "")).is_absolute(), (
        "van_genuchten.source_csv in template must be relative"
    )
    atm = data.get("atmospheric", {})
    if atm and atm.get("source_csv"):
        assert not Path(atm["source_csv"]).is_absolute(), (
            "atmospheric.source_csv in template must be relative"
        )


# ---------------------------------------------------------------------------
# Part C: --write-config-template CLI
# ---------------------------------------------------------------------------

def test_write_config_template_to_file(tmp_path, capsys):
    dest = tmp_path / "my_model.json"
    rc = cli.main(["--write-config-template", str(dest)])
    assert rc == 0
    assert dest.is_file()
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert "case_id" in data


def test_write_config_template_to_stdout(capsys):
    rc = cli.main(["--write-config-template"])
    captured = capsys.readouterr()
    assert rc == 0
    data = json.loads(captured.out)
    assert "case_id" in data


def test_write_config_template_creates_parent_dirs(tmp_path, capsys):
    dest = tmp_path / "deep" / "subdir" / "model.json"
    rc = cli.main(["--write-config-template", str(dest)])
    assert rc == 0
    assert dest.is_file()


# ---------------------------------------------------------------------------
# Part C: --print-config-schema CLI
# ---------------------------------------------------------------------------

def test_print_config_schema_stdout(capsys):
    rc = cli.main(["--print-config-schema"])
    captured = capsys.readouterr()
    assert rc == 0
    schema = json.loads(captured.out)
    assert schema.get("title") == "ModelConfig" or "properties" in schema


def test_print_config_schema_to_file(tmp_path, capsys):
    out_file = tmp_path / "schema.json"
    rc = cli.main(["--print-config-schema", "--schema-output", str(out_file)])
    assert rc == 0
    assert out_file.is_file()
    schema = json.loads(out_file.read_text(encoding="utf-8"))
    assert "properties" in schema


def test_schema_contains_required_fields(capsys):
    rc = cli.main(["--print-config-schema"])
    captured = capsys.readouterr()
    assert rc == 0
    schema = json.loads(captured.out)
    props = schema.get("properties", {})
    for field in ("project_name", "case_id", "simulation_time", "soil_profile",
                  "van_genuchten", "observation_depths", "output_settings"):
        assert field in props, f"Expected field {field!r} missing from schema"


# ---------------------------------------------------------------------------
# Part D: relative path preservation
# ---------------------------------------------------------------------------

def test_make_relative_if_under_root_returns_relative():
    abs_path = str(PROJECT_ROOT / "test_inputs" / "some.csv")
    result = _make_relative_if_under_root(abs_path)
    assert not Path(result).is_absolute()
    assert "test_inputs" in result


def test_make_relative_if_under_root_leaves_outside_paths():
    outside = "C:/outside/project/some.csv"
    result = _make_relative_if_under_root(outside)
    assert result == outside


def test_make_relative_if_under_root_handles_already_relative():
    rel = "test_inputs/new_user_dynamic_test/materials_vg_stable.csv"
    result = _make_relative_if_under_root(rel)
    assert not Path(result).is_absolute()


def test_config_dump_preserves_relative_material_csv():
    """When writing a config built from the stable template, van_genuchten.source_csv
    must be a relative (not absolute) path."""
    config = load_config(TEMPLATE_PATH)
    dumped = _config_dump_for_user(config)
    vg = dumped.get("van_genuchten", {})
    source_csv = vg.get("source_csv", "")
    assert not Path(source_csv).is_absolute(), (
        f"Expected relative van_genuchten.source_csv, got: {source_csv!r}"
    )


def test_config_dump_preserves_relative_atmospheric_csv():
    """atmospheric.source_csv in dumped config must be relative."""
    config = load_config(TEMPLATE_PATH)
    dumped = _config_dump_for_user(config)
    atm = dumped.get("atmospheric", {})
    source_csv = atm.get("source_csv", "")
    if source_csv:
        assert not Path(source_csv).is_absolute(), (
            f"Expected relative atmospheric.source_csv, got: {source_csv!r}"
        )


# ---------------------------------------------------------------------------
# Review output for LLM-assisted JSON configs
# ---------------------------------------------------------------------------

def test_review_template_succeeds(capsys):
    """The shipped LLM template must --review cleanly."""
    rc = cli.main(["--config", str(TEMPLATE_PATH), "--review"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "Validation status: valid ModelConfig" in captured.out
    assert "case_id      : my_model_001" in captured.out


def test_review_includes_initial_condition(capsys):
    """Review output must show the initial condition so a human reviewer
    can catch wrong values in LLM-generated configs."""
    rc = cli.main(["--config", str(TEMPLATE_PATH), "--review"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "initial cond" in captured.out
    # Template uses uniform pressure_head = -1.0
    assert "pressure_head" in captured.out
    assert "-1.0" in captured.out


def test_review_includes_atmospheric_csv_path_with_relativity(capsys):
    rc = cli.main(["--config", str(TEMPLATE_PATH), "--review"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "atmospheric CSV" in captured.out
    assert "atmosphere_stable_30d.csv" in captured.out
    # Annotation must be present and one of the two valid kinds.
    assert "(absolute)" in captured.out or "(relative)" in captured.out


def test_review_includes_material_csv_path_with_relativity(capsys):
    rc = cli.main(["--config", str(TEMPLATE_PATH), "--review"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "material CSV" in captured.out
    assert "materials_vg_stable.csv" in captured.out
    # Material CSV path is also annotated.
    # Extract just the material CSV section to avoid colliding with the
    # atmospheric CSV annotation already asserted above.
    out = captured.out
    material_idx = out.index("material CSV")
    material_block = out[material_idx:]
    assert "(absolute)" in material_block or "(relative)" in material_block


def test_review_initial_condition_profile_format(capsys, tmp_path, monkeypatch):
    """When initial_condition uses a profile, review must list the depth-value
    points in a compact form."""
    config_data = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    config_data["case_id"] = "profile_ic_test"
    config_data["initial_condition"] = {
        "type": "pressure_head",
        "profile": [
            {"depth": 0.0, "value": -0.5},
            {"depth": 2.0, "value": -2.0},
        ],
    }
    cfg_path = tmp_path / "profile_ic.json"
    cfg_path.write_text(json.dumps(config_data), encoding="utf-8")

    rc = cli.main(["--config", str(cfg_path), "--review"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "initial cond" in captured.out
    assert "profile" in captured.out
    assert "-0.5 m at 0.0 m" in captured.out
    assert "-2.0 m at 2.0 m" in captured.out
