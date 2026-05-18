# boundary_condition

## Purpose

Choose and configure the upper boundary, lower boundary, and (when
applicable) atmospheric forcing and root uptake sections of a
`ModelConfig`. This skill is normally composed by `case_design` while a
new config is being assembled.

## When to use this skill

Use this skill when:

- A new config is being designed and the boundary type is not obvious from
  the user's words ("rainfall", "ponded surface", "free drainage at the
  base").
- An existing config needs its boundary changed (e.g. switching from
  constant flux to atmospheric forcing).
- Atmospheric forcing is requested and the agent must decide between
  inline records and a CSV reference.

Do **not** use this skill when:

- The user only wants to change soil hydraulic parameters → use
  `soil_profile`.
- The user only wants to compare runs with different boundary fluxes →
  use `scenario_comparison` (the base config still goes through this skill
  once).

## Expected inputs

- The user's description of the surface and basal conditions.
- The simulation period (so atmospheric records can be checked against the
  window).
- Optionally: a CSV file with daily atmospheric data (precipitation,
  potential evaporation, potential transpiration).

## Expected outputs

A `ModelConfig` section that contains:

- `upper_boundary` with a supported `boundary_type`
  (`constant_head`, `constant_flux`, `atmospheric`, etc., per
  `schema.UpperBoundary`).
- `lower_boundary` with a supported `boundary_type`
  (`free_drainage`, `constant_head`, `constant_flux`, `seepage_face`, ...).
- If `upper_boundary.boundary_type == "atmospheric"`, an
  `atmospheric_forcing` block with either inline `records` or a
  `csv_path`.
- If root uptake is in scope, a `root_uptake` block consistent with
  `schema.RootUptake` (atmospheric forcing is required).

## Existing modules and tools used

- [hydrus_agent/schema.py](../../hydrus_agent/schema.py) —
  `UpperBoundary`, `LowerBoundary`, `AtmosphericForcing`, `RootUptake`.
- [hydrus_agent/atmospheric_csv.py](../../hydrus_agent/atmospheric_csv.py)
  — `load_atmospheric_records_from_csv()`, `AtmosphericCsvError`.
- [hydrus_agent/validator.py](../../hydrus_agent/validator.py) —
  cross-field validation (e.g. atmospheric required when boundary is
  atmospheric; root uptake requires atmospheric forcing).
- [hydrus_agent/phydrus_adapter.py](../../hydrus_agent/phydrus_adapter.py)
  — translates boundary settings into phydrus / HYDRUS input files; the
  source of truth for which boundary types are actually supported.
- Reference configs:
  [config/simple_atmospheric_case.json](../../config/simple_atmospheric_case.json),
  [config/simple_root_uptake_case.json](../../config/simple_root_uptake_case.json),
  [config/csv_atmospheric_boundary_test.json](../../config/csv_atmospheric_boundary_test.json),
  [config/csv_atmospheric_and_materials_test.json](../../config/csv_atmospheric_and_materials_test.json).

## Guardrails

- Only use boundary types declared in `schema.UpperBoundary` /
  `schema.LowerBoundary`. Unsupported types will be rejected by the
  validator or by `phydrus_adapter` with
  `UnsupportedFeatureError`.
- When using an atmospheric CSV, verify the file exists and covers the
  simulation period before writing the config. The validator resolves
  the CSV at `--review` time; reading the file first avoids review-time
  surprises.
- `root_uptake` requires `atmospheric_forcing`. Do not produce a config
  that has root uptake without an atmospheric block.
- Do not enable physics outside the current scope (no hysteresis,
  no dual-porosity, no advanced root uptake). See `AGENTS.md` →
  Scope Boundaries.

## Failure modes

- **Atmospheric block missing when required** — validator raises
  `ConfigError`. Report the field path; do not silently add empty
  records.
- **CSV column names don't match what the loader expects** — surface the
  `AtmosphericCsvError` message verbatim; the loader documents the
  required column names.
- **Records do not span the simulation window** — validator flags this.
  Ask the user whether to shorten the simulation or extend the CSV.
- **User asks for hysteresis, salinity stress, or other unsupported
  physics** — explain it is out of scope and suggest the closest
  supported approximation.

## Example user prompts

- "Use atmospheric forcing from `test_inputs/new_user_dynamic_test/atmosphere.csv` for the upper boundary."
- "Set the lower boundary to free drainage."
- "Add root uptake down to 40 cm to the existing atmospheric case."
- "Switch the surface boundary from constant flux to ponded
  (atmospheric with prescribed head)."

## Testing expectations

The following existing tests exercise the modules this skill depends on:

- [tests/test_schema.py](../../tests/test_schema.py) — boundary,
  atmospheric, root-uptake validation rules.
- [tests/test_atmospheric_csv.py](../../tests/test_atmospheric_csv.py) —
  atmospheric CSV loader.
- [tests/test_phydrus_adapter.py](../../tests/test_phydrus_adapter.py) —
  translation of boundary settings into HYDRUS inputs (catches
  `UnsupportedFeatureError` regressions).

There is currently **no direct test file** for
`hydrus_agent/validator.py`. Future changes to cross-field boundary
validation should add or extend tests for the validator alongside the
schema and CSV-loader tests.
