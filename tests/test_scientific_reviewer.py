"""Tests for hydrus_agent.scientific_reviewer."""

from __future__ import annotations

import copy
from typing import Any, Dict

import pytest

from hydrus_agent.schema import ModelConfig
from hydrus_agent.scientific_reviewer import (
    SCHEMA_VERSION,
    ScientificReviewResult,
    render_markdown,
    result_to_dict,
    review_config,
)


# --- Baseline config helpers --------------------------------------------


def _baseline_dict() -> Dict[str, Any]:
    """A schema-valid config with sane heuristic values.

    free_drainage lower boundary => always emits RECHARGE_INTERPRETATION_CAVEAT.
    Atmospheric forcing disabled => emits RECHARGE_NO_ATMOSPH.
    Window is 365 days so RECHARGE_SHORT_WINDOW does NOT fire.
    """
    return {
        "project_name": "baseline",
        "case_id": "baseline_case",
        "simulation_time": {
            "t_init": 0.0,
            "t_end": 365.0,
            "dt_init": 0.01,
            "units": "days",
        },
        "soil_profile": [
            {"depth_top": 0.0, "depth_bottom": 0.5, "material_id": 1},
            {"depth_top": 0.5, "depth_bottom": 1.0, "material_id": 2},
        ],
        "van_genuchten": [
            {"material_id": 1, "theta_r": 0.065, "theta_s": 0.41,
             "alpha": 7.5, "n": 1.89, "Ks": 1.061, "l": 0.5},
            {"material_id": 2, "theta_r": 0.078, "theta_s": 0.43,
             "alpha": 3.6, "n": 1.56, "Ks": 0.25, "l": 0.5},
        ],
        "initial_condition": {"type": "pressure_head", "value": -1.0},
        "upper_boundary": {"type": "constant_flux", "flux": 0.001},
        "lower_boundary": {"type": "free_drainage"},
        "observation_depths": [0.25, 0.75],
        "output_settings": {"print_times": [90.0, 180.0, 270.0, 360.0]},
    }


def _make(overrides: Dict[str, Any] | None = None,
          *, deep_set: Dict[str, Any] | None = None) -> ModelConfig:
    raw = _baseline_dict()
    if overrides:
        raw.update(overrides)
    if deep_set:
        for dotted, value in deep_set.items():
            target = raw
            parts = dotted.split(".")
            for part in parts[:-1]:
                if part.isdigit():
                    target = target[int(part)]
                else:
                    target = target[part]
            last = parts[-1]
            if last.isdigit():
                target[int(last)] = value
            else:
                target[last] = value
    return ModelConfig.model_validate(raw)


def _codes(result: ScientificReviewResult) -> set[str]:
    return {item.code for item in result.items}


# --- Cross-cutting -------------------------------------------------------


def test_review_returns_only_baseline_items_on_clean_baseline():
    result = review_config(_make())
    # Always-on caveat for free_drainage + the no-atmos info note.
    expected = {"RECHARGE_INTERPRETATION_CAVEAT", "RECHARGE_NO_ATMOSPH"}
    assert expected.issubset(_codes(result))
    # No critical items in a clean baseline.
    assert result.counts["critical"] == 0
    assert result.ok is True


def test_counts_and_ok_reflect_severity():
    # Trigger one critical: water_content below theta_r.
    result = review_config(_make(deep_set={
        "initial_condition.type": "water_content",
        "initial_condition.value": 0.001,
    }))
    assert "IC_WC_BELOW_THETA_R" in _codes(result)
    assert result.counts["critical"] >= 1
    assert result.ok is False
    # Counts add up to len(items).
    assert sum(result.counts.values()) == len(result.items)


def test_review_is_deterministic():
    cfg = _make()
    a = review_config(cfg)
    b = review_config(cfg)
    assert result_to_dict(a) == result_to_dict(b)


def test_render_markdown_contains_each_code_and_disclaimer():
    result = review_config(_make())
    text = render_markdown(result)
    assert "Heuristic review flags" in text
    for item in result.items:
        assert item.code in text


def test_result_to_dict_round_trip_shape():
    result = review_config(_make())
    payload = result_to_dict(result)
    assert payload["schema_version"] == SCHEMA_VERSION
    assert set(payload.keys()) == {"schema_version", "ok", "counts", "items"}
    for item in payload["items"]:
        assert set(item.keys()) >= {
            "severity", "category", "code", "message",
            "implication", "suggested_action",
        }


# --- Rule 1: soil hydraulic parameters ----------------------------------


def test_vg_theta_s_high():
    r = review_config(_make(deep_set={"van_genuchten.0.theta_s": 0.7}))
    assert "VG_THETA_S_HIGH" in _codes(r)


def test_vg_theta_s_low():
    r = review_config(_make(deep_set={
        "van_genuchten.0.theta_s": 0.2,
        # Keep theta_s > theta_r and range >= 0.10 to isolate the rule.
        "van_genuchten.0.theta_r": 0.05,
    }))
    assert "VG_THETA_S_LOW" in _codes(r)


def test_vg_theta_r_high():
    r = review_config(_make(deep_set={
        "van_genuchten.0.theta_r": 0.2,
        "van_genuchten.0.theta_s": 0.5,
    }))
    assert "VG_THETA_R_HIGH" in _codes(r)


def test_vg_theta_range_narrow():
    r = review_config(_make(deep_set={
        "van_genuchten.0.theta_r": 0.30,
        "van_genuchten.0.theta_s": 0.35,
    }))
    assert "VG_THETA_RANGE_NARROW" in _codes(r)


@pytest.mark.parametrize("alpha", [0.05, 75.0])
def test_vg_alpha_extreme(alpha):
    r = review_config(_make(deep_set={"van_genuchten.0.alpha": alpha}))
    assert "VG_ALPHA_EXTREME" in _codes(r)


def test_vg_n_near_one():
    r = review_config(_make(deep_set={"van_genuchten.0.n": 1.05}))
    assert "VG_N_NEAR_ONE" in _codes(r)


def test_vg_n_low_info():
    r = review_config(_make(deep_set={"van_genuchten.0.n": 1.15}))
    codes = _codes(r)
    assert "VG_N_LOW" in codes
    assert "VG_N_NEAR_ONE" not in codes


def test_vg_ks_very_low():
    r = review_config(_make(deep_set={"van_genuchten.0.Ks": 1e-7}))
    assert "VG_KS_VERY_LOW" in _codes(r)


def test_vg_ks_low_info():
    r = review_config(_make(deep_set={"van_genuchten.0.Ks": 1e-5}))
    codes = _codes(r)
    assert "VG_KS_LOW" in codes
    assert "VG_KS_VERY_LOW" not in codes


def test_vg_ks_high_info():
    r = review_config(_make(deep_set={"van_genuchten.0.Ks": 25.0}))
    codes = _codes(r)
    assert "VG_KS_HIGH" in codes
    assert "VG_KS_VERY_HIGH" not in codes


def test_vg_ks_very_high():
    r = review_config(_make(deep_set={"van_genuchten.0.Ks": 250.0}))
    assert "VG_KS_VERY_HIGH" in _codes(r)


# --- Rule 2: boundary condition consistency -----------------------------


def test_upper_const_flux_large():
    r = review_config(_make(deep_set={
        "upper_boundary.type": "constant_flux",
        "upper_boundary.flux": 1.0,
    }))
    assert "UPPER_CONST_FLUX_LARGE" in _codes(r)


def test_upper_const_head_ponded():
    r = review_config(_make(deep_set={
        "upper_boundary.type": "constant_head",
        "upper_boundary.head": 0.05,
        "upper_boundary.flux": None,
    }))
    assert "UPPER_CONST_HEAD_PONDED_NO_NOTE" in _codes(r)


def test_lower_const_head_deep_water_table():
    r = review_config(_make(deep_set={
        "lower_boundary.type": "constant_head",
        "lower_boundary.head": -20.0,
    }))
    assert "LOWER_CONST_HEAD_DEEP_WATER_TABLE" in _codes(r)


def test_lower_seepage_face_no_atmosph_info():
    r = review_config(_make(deep_set={"lower_boundary.type": "seepage_face"}))
    assert "LOWER_SEEPAGE_FACE_NO_ATMOSPH" in _codes(r)


def test_atmos_pet_no_rootuptake_info():
    raw = _baseline_dict()
    raw["upper_boundary"] = {"type": "atmospheric"}
    raw["atmospheric"] = {
        "enabled": True,
        "records": [
            {"time": 0.0, "precipitation": 0.0, "evaporation": 0.002},
            {"time": 10.0, "precipitation": 0.005, "evaporation": 0.001},
        ],
    }
    cfg = ModelConfig.model_validate(raw)
    r = review_config(cfg)
    assert "ATMOS_PET_NO_ROOTUPTAKE" in _codes(r)


# --- Rule 3: initial condition consistency ------------------------------


def test_ic_wc_below_theta_r_critical():
    r = review_config(_make(deep_set={
        "initial_condition.type": "water_content",
        "initial_condition.value": 0.001,
    }))
    assert "IC_WC_BELOW_THETA_R" in _codes(r)
    item = next(i for i in r.items if i.code == "IC_WC_BELOW_THETA_R")
    assert item.severity == "critical"


def test_ic_wc_above_theta_s_critical():
    r = review_config(_make(deep_set={
        "initial_condition.type": "water_content",
        "initial_condition.value": 0.99,
    }))
    assert "IC_WC_ABOVE_THETA_S" in _codes(r)


def test_ic_pressure_positive_surface_info():
    r = review_config(_make(deep_set={"initial_condition.value": 0.05}))
    assert "IC_PRESSURE_POSITIVE_SURFACE" in _codes(r)


def test_ic_pressure_very_dry_warning():
    r = review_config(_make(deep_set={"initial_condition.value": -200.0}))
    assert "IC_PRESSURE_VERY_DRY" in _codes(r)


def test_ic_profile_shallow_sampling_info():
    raw = _baseline_dict()
    raw["initial_condition"] = {
        "type": "pressure_head",
        "value": -1.0,
        "profile": [
            {"depth": 0.0, "value": -1.0},
            {"depth": 0.2, "value": -1.5},
        ],
    }
    cfg = ModelConfig.model_validate(raw)
    r = review_config(cfg)
    assert "IC_PROFILE_SHALLOW_SAMPLING" in _codes(r)


# --- Rule 4: observation node placement ---------------------------------


def test_obs_none_defined_info():
    r = review_config(_make(deep_set={"observation_depths": []}))
    assert "OBS_NONE_DEFINED" in _codes(r)


def test_obs_at_layer_interface_info():
    # Baseline has interface at 0.5; place an observation exactly there.
    r = review_config(_make(deep_set={"observation_depths": [0.25, 0.5]}))
    assert "OBS_AT_LAYER_INTERFACE" in _codes(r)


def test_obs_clustered_one_layer_info():
    # Both obs in the top layer (0..0.5).
    r = review_config(_make(deep_set={"observation_depths": [0.1, 0.4]}))
    assert "OBS_CLUSTERED_ONE_LAYER" in _codes(r)


def test_obs_below_root_zone_only_info():
    raw = _baseline_dict()
    raw["upper_boundary"] = {"type": "atmospheric"}
    raw["atmospheric"] = {
        "enabled": True,
        "records": [
            {"time": 0.0, "precipitation": 0.001, "evaporation": 0.001},
            {"time": 10.0, "precipitation": 0.0, "evaporation": 0.001},
        ],
    }
    raw["root_uptake"] = {
        "enabled": True,
        "root_depth": 0.3,
        "potential_transpiration": 0.002,
    }
    raw["observation_depths"] = [0.6, 0.9]
    cfg = ModelConfig.model_validate(raw)
    r = review_config(cfg)
    assert "OBS_BELOW_ROOT_ZONE_ONLY" in _codes(r)


# --- Rule 5: simulation duration and print times ------------------------


def test_sim_dt_init_large_warning():
    r = review_config(_make(deep_set={"simulation_time.dt_init": 50.0}))
    codes = _codes(r)
    assert "SIM_DT_INIT_LARGE" in codes
    assert "SIM_DT_INIT_VERY_LARGE" not in codes


def test_sim_dt_init_very_large_warning_not_critical():
    r = review_config(_make(deep_set={"simulation_time.dt_init": 250.0}))
    assert "SIM_DT_INIT_VERY_LARGE" in _codes(r)
    item = next(i for i in r.items if i.code == "SIM_DT_INIT_VERY_LARGE")
    # Per the conservative-critical constraint, this is warning, not critical.
    assert item.severity == "warning"


def test_sim_print_none_info():
    raw = _baseline_dict()
    raw["output_settings"] = {"print_times": []}
    cfg = ModelConfig.model_validate(raw)
    r = review_config(cfg)
    assert "SIM_PRINT_NONE" in _codes(r)


def test_sim_print_sparse_vs_atmosph_info():
    raw = _baseline_dict()
    raw["upper_boundary"] = {"type": "atmospheric"}
    raw["atmospheric"] = {
        "enabled": True,
        "records": [
            {"time": float(i), "precipitation": 0.001, "evaporation": 0.001}
            for i in range(0, 200, 1)
        ],
    }
    raw["output_settings"] = {"print_times": [180.0]}
    cfg = ModelConfig.model_validate(raw)
    r = review_config(cfg)
    assert "SIM_PRINT_SPARSE_VS_ATMOSPH" in _codes(r)


def test_sim_short_for_atmosph_only_when_units_are_days():
    # Window < 1 day with atmospheric forcing and units=days => info fires.
    raw = _baseline_dict()
    raw["simulation_time"] = {
        "t_init": 0.0, "t_end": 0.5, "dt_init": 0.001, "units": "days",
    }
    raw["upper_boundary"] = {"type": "atmospheric"}
    raw["atmospheric"] = {
        "enabled": True,
        "records": [
            {"time": 0.0, "precipitation": 0.0, "evaporation": 0.001},
            {"time": 0.4, "precipitation": 0.001, "evaporation": 0.001},
        ],
    }
    raw["output_settings"] = {"print_times": [0.25]}
    cfg = ModelConfig.model_validate(raw)
    r = review_config(cfg)
    assert "SIM_SHORT_FOR_ATMOSPH" in _codes(r)


def test_sim_short_for_atmosph_skipped_when_units_not_days():
    # Same short window but units=hours => threshold not applied, no flag.
    raw = _baseline_dict()
    raw["simulation_time"] = {
        "t_init": 0.0, "t_end": 12.0, "dt_init": 0.01, "units": "hours",
    }
    raw["upper_boundary"] = {"type": "atmospheric"}
    raw["atmospheric"] = {
        "enabled": True,
        "records": [
            {"time": 0.0, "precipitation": 0.0, "evaporation": 0.001},
            {"time": 6.0, "precipitation": 0.001, "evaporation": 0.001},
        ],
    }
    raw["output_settings"] = {"print_times": [6.0]}
    cfg = ModelConfig.model_validate(raw)
    r = review_config(cfg)
    assert "SIM_SHORT_FOR_ATMOSPH" not in _codes(r)


# --- Rule 6: recharge over-interpretation -------------------------------


def test_recharge_caveat_always_emitted_for_free_drainage():
    r = review_config(_make())
    assert "RECHARGE_INTERPRETATION_CAVEAT" in _codes(r)


def test_recharge_caveat_not_emitted_for_non_bottom_flux_boundaries():
    r = review_config(_make(deep_set={
        "lower_boundary.type": "constant_head",
        "lower_boundary.head": -1.0,
    }))
    assert "RECHARGE_INTERPRETATION_CAVEAT" not in _codes(r)


def test_recharge_short_window_warning_when_units_days():
    r = review_config(_make(deep_set={
        "simulation_time.t_end": 10.0,
        "simulation_time.dt_init": 0.01,
        "output_settings.print_times": [2.0, 5.0, 8.0],
    }))
    assert "RECHARGE_SHORT_WINDOW" in _codes(r)


def test_recharge_short_window_skipped_when_units_not_days():
    raw = _baseline_dict()
    raw["simulation_time"] = {
        "t_init": 0.0, "t_end": 10.0, "dt_init": 0.01, "units": "hours",
    }
    raw["output_settings"] = {"print_times": [2.0, 5.0, 8.0]}
    cfg = ModelConfig.model_validate(raw)
    r = review_config(cfg)
    assert "RECHARGE_SHORT_WINDOW" not in _codes(r)


# --- Rule 7: unsupported / simplified physics ---------------------------


def test_phys_solute_single_species_info():
    raw = _baseline_dict()
    raw["solute_transport"] = {
        "enabled": True,
        "model": "conservative",
        "species": [{
            "name": "tracer",
            "initial_concentration": 0.0,
            "upper_boundary_concentration": 0.0,
            "dispersivity": 0.05,
        }],
    }
    cfg = ModelConfig.model_validate(raw)
    r = review_config(cfg)
    assert "PHYS_SOLUTE_SINGLE_SPECIES" in _codes(r)


def test_phys_root_distribution_uniform_info():
    raw = _baseline_dict()
    raw["upper_boundary"] = {"type": "atmospheric"}
    raw["atmospheric"] = {
        "enabled": True,
        "records": [
            {"time": 0.0, "precipitation": 0.001, "evaporation": 0.001},
            {"time": 10.0, "precipitation": 0.0, "evaporation": 0.001},
        ],
    }
    raw["root_uptake"] = {
        "enabled": True, "root_depth": 0.3, "potential_transpiration": 0.001,
    }
    cfg = ModelConfig.model_validate(raw)
    r = review_config(cfg)
    assert "PHYS_ROOT_DISTRIBUTION_UNIFORM" in _codes(r)


def test_phys_no_hysteresis_and_no_temperature_info():
    raw = _baseline_dict()
    raw["upper_boundary"] = {"type": "atmospheric"}
    raw["atmospheric"] = {
        "enabled": True,
        "records": [
            {"time": 0.0, "precipitation": 0.0, "evaporation": 0.001},
            {"time": 1.0, "precipitation": 0.005, "evaporation": 0.001},
            {"time": 2.0, "precipitation": 0.0, "evaporation": 0.001},
        ],
    }
    cfg = ModelConfig.model_validate(raw)
    r = review_config(cfg)
    codes = _codes(r)
    assert "PHYS_NO_HYSTERESIS" in codes
    assert "PHYS_NO_TEMPERATURE" in codes
    for code in ("PHYS_NO_HYSTERESIS", "PHYS_NO_TEMPERATURE"):
        item = next(i for i in r.items if i.code == code)
        assert item.severity == "info"


# --- Reviewer is tolerant of internal errors ----------------------------


def test_internal_rule_error_yields_info_item(monkeypatch):
    from hydrus_agent import scientific_reviewer as sr

    def _boom(_cfg):
        raise RuntimeError("synthetic")

    monkeypatch.setattr(sr, "_rule_soil_hydraulic_parameters", _boom)
    result = sr.review_config(_make())
    assert "REVIEWER_INTERNAL_ERROR" in {i.code for i in result.items}
    # Other rules still ran.
    assert any(i.code == "RECHARGE_INTERPRETATION_CAVEAT" for i in result.items)
