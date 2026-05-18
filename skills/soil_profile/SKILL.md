# soil_profile

## Purpose

Build the layered soil profile and associated van Genuchten hydraulic
parameters for a `ModelConfig`. Covers depth ordering, observation node
placement, and the choice between built-in soil templates, inline van
Genuchten parameters, and CSV-supplied parameters.

## When to use this skill

Use this skill when:

- A new config is being designed and the profile needs to be specified.
- An existing config needs a new layer added, removed, or its hydraulic
  parameters changed.
- The user supplies a material CSV.

Do **not** use this skill when:

- The user asks the agent to fit van Genuchten parameters from a soil
  water characteristic curve (SWCC) point dataset. SWCC fitting is
  **not implemented**. Ask the user for direct van Genuchten parameters
  instead (`theta_r`, `theta_s`, `alpha_1_m`, `n`, `Ks_m_d`, `l`).
- The change is purely about boundaries → use `boundary_condition`.

## Expected inputs

- The user's description of the soil column (layer thicknesses, soil
  types, total depth).
- Either named soil templates (sand, sandy loam, loam, silt loam, clay
  loam, clay) **or** explicit van Genuchten parameter sets **or** a
  material CSV path.
- Desired observation depths (where `Obs_Node.out` rows should be
  produced).

## Expected outputs

A `ModelConfig` section with:

- `soil_layers` listed top-to-bottom, contiguous (no gaps, no overlaps),
  with monotonic depths.
- One `van_genuchten` parameter set per material, with all of
  `theta_r`, `theta_s`, `alpha_1_m`, `n`, `Ks_m_d`, `l` populated.
- `initial_condition` consistent with the profile bounds.
- `observation_depths` strictly within `[0, total_depth]`.

## Existing modules and tools used

- [hydrus_agent/schema.py](../../hydrus_agent/schema.py) —
  `SoilLayer`, `VanGenuchtenParams`, `InitialCondition`.
- [hydrus_agent/material_csv.py](../../hydrus_agent/material_csv.py) —
  `load_van_genuchten_from_csv()`, `MaterialCsvError`.
- [hydrus_agent/config_builder.py](../../hydrus_agent/config_builder.py) —
  built-in soil template library (sand, sandy loam, loam, silt loam,
  clay loam, clay) plus depth/observation parsing.
- [hydrus_agent/validator.py](../../hydrus_agent/validator.py) — profile
  contiguity, depth ordering, observation-depth bounds checks.
- [hydrus_agent/phydrus_adapter.py](../../hydrus_agent/phydrus_adapter.py)
  — turns the layered profile into HYDRUS `PROFILE.DAT` and related
  inputs.
- Reference configs:
  [config/example_case.json](../../config/example_case.json),
  [config/demo_two_layer_inundation.json](../../config/demo_two_layer_inundation.json),
  [config/csv_atmospheric_and_materials_test.json](../../config/csv_atmospheric_and_materials_test.json).

## Guardrails

- Layers must be **contiguous and ordered top-to-bottom**. The validator
  refuses gaps, overlaps, or out-of-order depths.
- Every layer must reference a van Genuchten parameter set; do not leave
  a layer without parameters expecting a default.
- Observation depths must lie strictly inside the profile.
- **No SWCC fitting.** If the user provides only a curve of measured
  matric potential vs water content, explain that point-data fitting is
  not implemented and request direct van Genuchten parameters.
- The current scope supports homogeneous van Genuchten layers only —
  no hysteresis, no dual-porosity, no scaling factors.
- Note `hydrus_agent/input_writer.py` is a documented **stub**; the
  actual HYDRUS input files are written via `phydrus_adapter.py`. Do
  not extend `input_writer.py` as part of this skill.

## Failure modes

- **Non-contiguous profile** — validator raises `ConfigError` naming the
  offending layer indices. Report verbatim.
- **Missing van Genuchten field** — validator raises `ConfigError` with
  the field path. Ask the user for the missing value rather than
  guessing.
- **Observation depth outside profile** — surface the validator error;
  ask whether to drop the observation or extend the profile.
- **Material CSV column mismatch** — surface `MaterialCsvError` verbatim;
  the loader documents the required columns.
- **User wants SWCC fitting** — politely refuse and ask for direct
  parameters.

## Example user prompts

- "Set up a two-layer profile: 0-30 cm sandy loam, 30-100 cm clay loam,
  observations at 10, 30, and 60 cm."
- "Use the material CSV at `test_inputs/new_user_dynamic_test/materials.csv`."
- "Make the top layer thicker — extend it from 30 to 50 cm."
- "Change the bottom layer to clay using the built-in template."

## Testing expectations

The following existing tests exercise the modules this skill depends on:

- [tests/test_schema.py](../../tests/test_schema.py) — `SoilLayer` and
  `VanGenuchtenParams` validation, observation depth checks.
- [tests/test_material_csv.py](../../tests/test_material_csv.py) —
  material CSV loader and `MaterialCsvError`.
- [tests/test_config_builder.py](../../tests/test_config_builder.py) —
  soil template library and profile assembly in the rule-based builder.
- [tests/test_phydrus_adapter.py](../../tests/test_phydrus_adapter.py) —
  profile translation into HYDRUS inputs.

There is currently **no direct test file** for
`hydrus_agent/validator.py`. Future changes to contiguity or observation-
depth validation should add or extend validator tests.
