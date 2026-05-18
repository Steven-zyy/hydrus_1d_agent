# scenario_comparison

## Purpose

Run a batch of parameter-override scenarios from a reviewed base config
and produce the comparison report. This skill wraps the deterministic
scenario runner; it does **not** auto-generate scenarios from sensitivity
ranges (that would be a future skill).

## When to use this skill

Use this skill when:

- The user wants to compare a small, explicit set of "what if"
  variations on a base case (a few values of Ks, alpha, n, root depth,
  boundary flux, initial condition, or solute dispersivity).
- A `case_design` and `run_qc` cycle has already been completed for the
  base case.

Do **not** use this skill when:

- The user only wants a single run → use `run_qc`.
- The user wants to compare a model result against measured field
  observations → use `field_comparison`.
- The desired comparison is between two existing standalone runs (not a
  batch from one base) — this is currently not directly supported; the
  user would need to convert the second run into an explicit scenario
  override on the first.

## Expected inputs

- A reviewed base `config/<case_id>.json` (review-state must match).
- A `scenarios/*.json` file (see
  [config/scenarios/](../../config/scenarios/) for the schema)
  enumerating overrides. Each scenario must use one of the supported
  override paths.
- `HYDRUS_EXE` set; a reasonable per-scenario timeout.

## Expected outputs

Under `runs/<batch_id>/`:

- `configs/<base>__<scenario_id>.json` per scenario.
- `runs/<base>__<scenario_id>/` per scenario, each containing the same
  pipeline outputs as a single `run_qc` run.
- A batch-level summary CSV and a comparison report produced by
  `scenario_analysis`.

## Existing modules and tools used

- [hydrus_agent/scenario_runner.py](../../hydrus_agent/scenario_runner.py)
  — validates all overrides up front, then executes each scenario
  through `pipeline.py`. Each scenario gets a unique case ID of the form
  `<base>__<scenario_id>`.
- [hydrus_agent/scenario_analysis.py](../../hydrus_agent/scenario_analysis.py)
  — post-processes a completed batch and writes the comparison report
  and metric plots.
- [hydrus_agent/pipeline.py](../../hydrus_agent/pipeline.py) — invoked
  once per scenario.
- [hydrus_agent/validator.py](../../hydrus_agent/validator.py) — used to
  validate each per-scenario derived config.
- Reference scenario file:
  [config/scenarios/](../../config/scenarios/).
- CLI flags: `--scenario-file`, `--scenario-report`, plus the standard
  run-time flags `--timeout` and `--hydrus-launch-mode`.

## Guardrails

- The base config must pass `--review` first. The same hash guard that
  protects `--all` protects the scenario base.
- **Supported override paths only** (current list):
  - `van_genuchten[i].Ks`, `.alpha`, `.n`
  - `initial_condition.value`
  - `upper_boundary.flux`, `.head`
  - `root_uptake.root_depth`
  - `solute_transport.species[0].dispersivity`

  Other override paths must not be invented; if the user asks for one,
  ask whether to extend the runner in a separate task or fall back to
  separate configs.
- Validation happens **before** any scenario runs; if any scenario fails
  validation, none run. Report the failure exactly.
- Each scenario is a full HYDRUS run; respect the per-scenario timeout
  and the `--hydrus-launch-mode argv` default.
- Do not silently re-use an old batch directory; pick a new
  `batch_id` or pass `--overwrite-run` only with the user's awareness.

## Failure modes

- **One or more scenarios fail validation** — no scenarios run; report
  the validator messages.
- **Some scenarios converge, others do not** — the batch completes; the
  comparison report lists per-scenario status. Do not hide the failures
  in the summary back to the user.
- **`overall_status == failed` on the base** — discuss with the user
  before running the batch; comparing against a broken base is rarely
  meaningful.
- **Override path not supported** — report the offending key; do not
  attempt to monkey-patch the runner.

## Example user prompts

- "Run a small sweep over Ks values 0.1, 1.0 and 10.0 m/d on the
  current sandy loam case."
- "Compare three root depths: 30, 50 and 70 cm."
- "Use `config/scenarios/simple_sensitivity.json` against the reviewed
  base and give me the comparison."
- "Regenerate the comparison report for the existing batch under
  `runs/<batch_id>`."

## Testing expectations

The following existing tests exercise the modules this skill depends on:

- [tests/test_scenario_runner.py](../../tests/test_scenario_runner.py)
  — scenario validation, derived-config writing, per-scenario
  invocation.
- [tests/test_scenario_analysis.py](../../tests/test_scenario_analysis.py)
  — batch post-processing and comparison report generation.
- [tests/test_pipeline.py](../../tests/test_pipeline.py) — the per-
  scenario pipeline call path.
- [tests/test_cli.py](../../tests/test_cli.py) — `--scenario-file` and
  `--scenario-report` argument handling.

Future changes to the supported-override-path list, batch directory
layout, or comparison metrics should extend the scenario runner and
scenario analysis tests above.
