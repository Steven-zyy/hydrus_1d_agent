# case_design

## Purpose

Translate a user's natural-language HYDRUS-1D modelling request into a
single validated, reviewable JSON config under `config/<case_id>.json`,
using LLM-assisted JSON mode. This skill is the entry point for almost
every new user prompt; it does **not** run HYDRUS.

## When to use this skill

Use this skill when:

- The user describes a new modelling problem ("build a 30-day infiltration
  case on sandy loam with daily rainfall").
- The user asks to modify an existing config in a non-trivial way (adding
  a layer, switching boundary type, enabling root uptake).
- An agent needs to produce a config that downstream skills (`run_qc`,
  `scenario_comparison`, `field_comparison`) can consume.

Do **not** use this skill when:

- The request is only about interpreting an existing run → use `run_qc` or
  `scientific_reporting`.
- The user is editing benchmark-official copies under
  `benchmarks/pc_progress_raw/` (those are read-only).

## Expected inputs

- A user request in natural language.
- Optionally: a stable demo CSV under `test_inputs/new_user_dynamic_test/`
  or `test_inputs/csv_boundary_test/` if the user did not supply their own
  data.
- Knowledge of soil templates available in
  [hydrus_agent/config_builder.py](../../hydrus_agent/config_builder.py)
  (sand, sandy loam, loam, silt loam, clay loam, clay).
- The canonical template at
  [config/templates/llm_config_template.json](../../config/templates/llm_config_template.json).

## Expected outputs

- A new file `config/<case_id>.json` that:
  - Loads cleanly via `--review`.
  - Has a `case_id` that is filesystem-safe and descriptive
    (e.g. `sandy_loam_30day_rainfall`, not `case1`).
  - Resolves any referenced CSVs to real, readable files.
- A recorded `last_review.json` entry (written by `--review`) pinning the
  SHA256 hash of the reviewed config, so downstream `--all` runs do not
  trip the config-mismatch guard.

## Existing modules and tools used

- [hydrus_agent/schema.py](../../hydrus_agent/schema.py) — Pydantic
  `ModelConfig` and child models.
- [hydrus_agent/validator.py](../../hydrus_agent/validator.py) —
  `load_config()` and `ConfigError` (entry point used by `--review`).
- [hydrus_agent/config_builder.py](../../hydrus_agent/config_builder.py) —
  rule-based natural-language → config (used by `--describe`); soil
  template library.
- [hydrus_agent/review_state.py](../../hydrus_agent/review_state.py) —
  records the reviewed config + SHA256 hash.
- [hydrus_agent/scientific_reviewer.py](../../hydrus_agent/scientific_reviewer.py)
  — deterministic, rule-based science-level reviewer. Available via the
  `--science-review` CLI flag (does not run HYDRUS) and emitted as
  `scientific_review.json` in every run directory. Items are heuristic
  flags, not hard validity criteria.
- [hydrus_agent/prompt_benchmark.py](../../hydrus_agent/prompt_benchmark.py)
  and [benchmarks/prompt_to_config/](../../benchmarks/prompt_to_config/)
  — deterministic offline benchmark that grades candidate configs
  against per-case expectations (schema validation, scientific-reviewer
  codes, structural features, raw JSON shape). Useful for verifying
  that a new prompt-to-config workflow does not silently regress on
  canonical cases. Run via `scripts/run_prompt_benchmark.py`. Does not
  call any LLM and does not run HYDRUS.
- [hydrus_agent/atmospheric_csv.py](../../hydrus_agent/atmospheric_csv.py)
  and [hydrus_agent/material_csv.py](../../hydrus_agent/material_csv.py)
  — CSV resolution paths that downstream validation will exercise.
- [config/templates/llm_config_template.json](../../config/templates/llm_config_template.json)
  — canonical schema example for LLM-assisted JSON mode.
- [docs/llm_assisted_json_configuration.md](../../docs/llm_assisted_json_configuration.md)
  — full workflow reference.
- CLI flags: `--config`, `--review`, `--write-config-template`,
  `--print-config-schema`. (`--describe` exists but is legacy / rule-based;
  prefer LLM-assisted JSON for new prompts.)

## Guardrails

- **Prefer LLM-assisted JSON mode over `--describe`.** Write
  `config/<case_id>.json` directly, then `--review`. `--describe` is a
  rule-based legacy path kept for developer use.
- **Always `--review` before any `--all`.** Never skip the review gate.
- **Never pass `--allow-config-mismatch` unless the user explicitly
  approves it.** The config-hash guard exists to prevent accidentally
  running a different JSON than the one reviewed.
- Use stable demo CSVs under `test_inputs/new_user_dynamic_test/` only
  when the request is generic and the user has not supplied their own
  data; otherwise ask one concise clarification.
- If the user asks for SWCC point-data fitting, explain it is not
  implemented and ask for direct van Genuchten parameters
  (`theta_r`, `theta_s`, `alpha_1_m`, `n`, `Ks_m_d`, `l`).
- Do not invent fields that are not in `ModelConfig`. When unsure, run
  `--print-config-schema`.

## Failure modes

- **`ConfigError` on `--review`** — report the field path and message
  back to the user verbatim; do not silently patch the JSON without
  user confirmation.
- **Referenced CSV not found** — list the resolved absolute path and ask
  the user where the file should live.
- **Ambiguous request** — ask one short clarification rather than guess.
  Common ambiguities: simulation length units, depth units, whether the
  upper boundary is atmospheric or constant flux.
- **case_id collides with an existing run** — pick a more specific name
  (append a date or experiment tag); do not silently overwrite.

## Example user prompts

- "Build a 30-day sandy loam over sand infiltration case and review it."
- "Add a clay layer between 20 and 40 cm in the existing two-layer
  config."
- "I have a CSV of daily rainfall and PET — set up a 90-day atmospheric
  case with root uptake to 50 cm."
- "Switch the lower boundary on `example_case.json` to free drainage."

## Testing expectations

The following existing tests exercise the modules this skill depends on:

- [tests/test_schema.py](../../tests/test_schema.py) — Pydantic
  validation rules.
- [tests/test_config_builder.py](../../tests/test_config_builder.py) —
  rule-based natural-language builder.
- [tests/test_atmospheric_csv.py](../../tests/test_atmospheric_csv.py) —
  atmospheric CSV resolution.
- [tests/test_material_csv.py](../../tests/test_material_csv.py) —
  material CSV resolution.
- [tests/test_llm_json_mode.py](../../tests/test_llm_json_mode.py) —
  LLM-assisted JSON mode end-to-end checks.
- [tests/test_cli.py](../../tests/test_cli.py) — CLI argument handling
  for `--review`, `--write-config-template`, `--print-config-schema`.

There is currently **no direct test file** for `hydrus_agent/validator.py`
or `hydrus_agent/review_state.py`. Future changes to validation messages
or to the review-state file format should add or extend tests covering
those modules.
