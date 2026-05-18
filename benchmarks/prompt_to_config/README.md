# Prompt-to-config benchmark

Deterministic, offline framework for grading **pre-saved candidate JSON
configs** against per-case expectations. Each case represents a natural-
language modelling prompt; the candidate config is what some prompt-to-
config workflow produced for that prompt.

The benchmark **never calls an LLM** and **never runs HYDRUS**. It only:

1. Loads the candidate JSON.
2. Runs `hydrus_agent.load_config()` (the existing schema validator).
3. Runs `hydrus_agent.scientific_reviewer.review_config()`.
4. Checks structural features against expected values.
5. Checks raw JSON top-level keys against required/forbidden lists.

## Running the benchmark

From the repository root:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe scripts\run_prompt_benchmark.py
C:\App\anaconda3\envs\hydrus-agent\python.exe scripts\run_prompt_benchmark.py --json-out results.json
```

The script always exits 0. Failures are reported in the markdown output
(printed to stdout) and in the optional `--json-out` file.

## Directory layout

```
benchmarks/prompt_to_config/
  README.md              ← this file
  cases/
    <case_id>/
      case.json          ← prompt + expectations
      candidate.json     ← the config under test
    ...
```

## Path semantics for candidate configs

Candidate configs are loaded with the standard
`hydrus_agent.load_config()` function. When a candidate references CSV
files (atmospheric forcing, material parameters), the existing resolver
first looks **relative to the candidate JSON's parent directory**, and
then falls back to **paths relative to the repository root**. No new
path semantics are introduced for the benchmark.

For stability, canonical cases reference CSVs by **repository-root-
relative paths** (e.g. `test_inputs/new_user_dynamic_test/atmosphere_stable_30d.csv`).
This means cases work regardless of where the cases directory sits,
provided the benchmark is run from a checkout that includes the
`test_inputs/` tree.

## `case.json` schema

Only `case_id`, `prompt`, and `candidate_config` are required. Everything
under `expected.*` is optional; unspecified expectations are not checked.

```json
{
  "case_id": "simple_infiltration_free_drainage",
  "prompt": "Set up a 1-day infiltration model on sandy loam with free drainage.",
  "tags": ["infiltration", "free_drainage", "single_layer"],
  "candidate_config": "candidate.json",
  "expected": {
    "schema_validation": "pass",
    "schema_error_pattern": null,
    "scientific_review": {
      "ok": true,
      "must_have_codes":     ["RECHARGE_INTERPRETATION_CAVEAT"],
      "must_not_have_codes": ["IC_WC_BELOW_THETA_R"],
      "max_critical": 0,
      "max_warning":  null
    },
    "features": {
      "upper_boundary_type": "constant_flux",
      "lower_boundary_type": "free_drainage",
      "soil_layer_count": 1,
      "has_atmospheric_csv": false,
      "has_material_csv": false,
      "has_root_uptake": false,
      "has_solute_transport": false,
      "observation_depth_count": 2,
      "simulation_units": "days",
      "initial_condition_type": "pressure_head"
    },
    "raw_json": {
      "must_contain_keys":     [],
      "must_not_contain_keys": ["heat_transport", "dual_porosity"]
    },
    "notes": "Free-cite documentation of the prompt's intent."
  }
}
```

### Supported feature keys

Defined by `hydrus_agent.prompt_benchmark.supported_feature_keys()`. Any
unrecognised key in `features` is reported as a per-case failure (typos
fail loudly).

Current keys: `upper_boundary_type`, `lower_boundary_type`,
`soil_layer_count`, `has_atmospheric_csv`, `has_material_csv`,
`has_root_uptake`, `has_solute_transport`, `observation_depth_count`,
`simulation_units`, `initial_condition_type`.

To add a new feature key, add an extractor to `_FEATURE_EXTRACTORS` in
`hydrus_agent/prompt_benchmark.py` and add a unit test.

### Schema-fail cases

For cases where the candidate is intentionally invalid (e.g. missing
`van_genuchten`), set `expected.schema_validation = "fail"` and supply
a robust `schema_error_pattern` regex. The pattern is matched with
`re.search` against the `ConfigError` message. Prefer short field-name
substrings (`"van_genuchten"`, `"\\bn\\b"`) over long Pydantic phrases.

### Unsupported-physics cases

For cases where the prompt asks for unsupported physics (heat transport,
dual porosity, hysteresis, etc.), the candidate should **omit** the
unsupported keys rather than embedding them silently. Use
`raw_json.must_not_contain_keys` to enforce the omission. The `notes`
field should document what the prompt asked for and why it was dropped.

## Adding a new case

1. Create `benchmarks/prompt_to_config/cases/<case_id>/`.
2. Add `candidate.json` (the config to grade).
3. Add `case.json` (prompt + expectations).
4. Run the benchmark; verify the new case passes.
5. The case will be picked up automatically by
   `tests/test_prompt_benchmark_cases.py` and asserted to pass.

## What this benchmark does NOT check

- Quality of the prompt prose itself.
- Whether the candidate would converge in HYDRUS (that's the
  `benchmarks/pc_progress_raw/` suite).
- Whether the underlying LLM workflow is well-calibrated (the candidate
  is pre-saved; the benchmark only grades the saved JSON).
