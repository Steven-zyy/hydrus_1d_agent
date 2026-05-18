# run_qc

## Purpose

Execute a reviewed config end-to-end through the deterministic pipeline
(`--all`) and interpret the four-status reliability report. This skill is
the gate between "config exists" and "results can be discussed". It
enforces the project rule that **HYDRUS exit code 0 alone is never
treated as success**.

## When to use this skill

Use this skill when:

- A `config/<case_id>.json` has been produced by `case_design` and
  `--review` has been run successfully.
- A previously failed or incomplete run needs to be re-executed after a
  config fix.
- A user asks "run it" or "now run the model" after design work.

Do **not** use this skill when:

- The config has not been reviewed yet → use `case_design`.
- The intent is a batch over parameter overrides → use
  `scenario_comparison` (it calls the same pipeline internally per
  scenario).
- The intent is only post-hoc interpretation of an existing run →
  use `scientific_reporting`.

## Expected inputs

- A `config/<case_id>.json` whose SHA256 hash matches the last reviewed
  config (so the config-hash guard does not block the run).
- `HYDRUS_EXE` set in the current shell or in `.env`, pointing at
  `H1D_CALC.EXE` on a Windows machine with PC-Progress HYDRUS-1D
  installed.
- A reasonable wall-clock timeout (the project default in examples is
  60 seconds).

## Expected outputs

Under `runs/<case_id>/`:

- `pipeline_summary.json` with the four status fields:
  - `execution_status` — `completed` or `failed_process`
  - `hydrus_numerical_status` — `converged`, `failed`, or `unknown`
  - `qc_status` — `passed`, `failed`, or `not_run`
  - `overall_status` — `ok`, `failed`, or `incomplete`
- `outputs/qc_summary.json` (when QC ran).
- `hydrus_project/Error.msg` if HYDRUS wrote one.
- `report.md` and `figures/` populated by the reporting and plotting
  steps.
- `run_manifest.json` — a reproducibility manifest written as a
  separate artefact (independent of `pipeline_summary.json`) that
  records config hash, HYDRUS executable + launch mode, environment
  metadata, input file hashes, key output file paths, and the four
  reliability statuses.
- `scientific_review.json` — non-blocking deterministic science-level
  review output. Items are heuristic flags (info/warning/critical) and
  do not change `overall_status`. `critical` items document
  clearly-impossible inputs (e.g. initial water content outside
  [theta_r, theta_s]) and are deliberately rare.

## Existing modules and tools used

- [hydrus_agent/pipeline.py](../../hydrus_agent/pipeline.py) — the
  8-step orchestrator (load config → create run folder → prepare input →
  run HYDRUS → read outputs → plot → QC → report).
- [hydrus_agent/case.py](../../hydrus_agent/case.py) — run folder
  creation and config snapshot.
- [hydrus_agent/phydrus_adapter.py](../../hydrus_agent/phydrus_adapter.py)
  — HYDRUS input generation.
- [hydrus_agent/runner.py](../../hydrus_agent/runner.py) — subprocess
  executor with two launch modes (`argv`, `level-dir`) and false-success
  detection.
- [hydrus_agent/output_reader.py](../../hydrus_agent/output_reader.py) —
  case-insensitive output discovery and parsing
  (`Balance.out`, `T_Level.out`, `Run_Inf.out`, `Obs_Node.out`,
  `Nod_Inf.out`, `SoluteN.out`).
- [hydrus_agent/qc.py](../../hydrus_agent/qc.py) — rule-based QC
  (output completeness, NaN counts, water-balance error threshold).
- [hydrus_agent/plotter.py](../../hydrus_agent/plotter.py) — standard
  figure set.
- [hydrus_agent/reporter.py](../../hydrus_agent/reporter.py) — Markdown
  report assembly.
- [hydrus_agent/review_state.py](../../hydrus_agent/review_state.py) —
  enforces the reviewed-config / hash guard.
- [hydrus_agent/env.py](../../hydrus_agent/env.py) — resolves
  `HYDRUS_EXE` from the process environment or a `.env` file.
- CLI flags: `--config`, `--all`, `--overwrite-run`,
  `--clean-run-folder`, `--timeout`, `--hydrus-launch-mode`,
  `--diagnose-run`, plus the individual step flags `--prepare-input`,
  `--run`, `--read-output`, `--plot`, `--qc`, `--report`.

## Guardrails

- **Never run `--all` on a config that has not been reviewed.** The
  config-hash guard will block it; do not bypass with
  `--allow-config-mismatch` unless the user explicitly approves.
- **Set `HYDRUS_EXE` first.** Confirm the variable is set; do not echo
  the contents of `.env`.
- **Use `--hydrus-launch-mode argv`** unless the user specifically asks
  to test `level-dir`.
- **Always supply a `--timeout`.** Default to 60 s for typical short
  cases; larger for long simulations.
- **Never treat exit code 0 alone as success.** The runner already
  detects "false success" patterns in `Error.msg`; the agent must still
  read `pipeline_summary.json`.
- After the run, report all four status fields plus the maximum
  water-balance error and whether the result is suitable for
  interpretation (only when `overall_status == ok`).
- This is a Windows-local workflow. On non-Windows machines, only the
  Python-only helpers (`--review`, `--print-config-schema`,
  `--write-config-template`) are usable.

## Failure modes

- **`execution_status == failed_process`** — HYDRUS could not be launched
  or crashed early. Check `HYDRUS_EXE`, the `inputs/` folder, and the
  console output. Report; do not retry blindly.
- **`hydrus_numerical_status == failed`** — read `Error.msg` and report
  the diagnostic line; do not silently re-run with different parameters.
- **`qc_status == failed`** — inspect `qc_summary.json` and report which
  checks failed (typically water-balance error above threshold or
  missing outputs).
- **`overall_status == incomplete`** — a soft step (reading outputs,
  plotting, QC, reporting) failed but HYDRUS itself converged. Report
  which step failed.
- **Config-hash mismatch** — run `--review` again on the current config
  before retrying. Do not bypass the guard.

## Example user prompts

- "Run the reviewed config."
- "Execute `config/sandy_loam_30day_rainfall.json` end-to-end and tell
  me if it is reliable."
- "Re-run after my edit."
- "Run again with a 5-minute timeout."

## Testing expectations

The following existing tests exercise the modules this skill depends on:

- [tests/test_pipeline.py](../../tests/test_pipeline.py) — end-to-end
  pipeline orchestration and status assembly.
- [tests/test_runner.py](../../tests/test_runner.py) — subprocess
  execution and false-success detection.
- [tests/test_output_reader.py](../../tests/test_output_reader.py) —
  HYDRUS output discovery and parsing.
- [tests/test_qc.py](../../tests/test_qc.py) — QC rules and thresholds.
- [tests/test_plotter.py](../../tests/test_plotter.py) — figure
  generation.
- [tests/test_reporter.py](../../tests/test_reporter.py) — Markdown
  report assembly.
- [tests/test_phydrus_adapter.py](../../tests/test_phydrus_adapter.py)
  — HYDRUS input generation.
- [tests/test_cli.py](../../tests/test_cli.py) — CLI argument handling
  for `--all` and the per-step flags.

There is currently **no direct test file** for
`hydrus_agent/case.py`, `hydrus_agent/review_state.py`, or
`hydrus_agent/env.py`. Future changes to run-folder layout, the
reviewed-config guard, or `HYDRUS_EXE` resolution should add or extend
tests covering those modules.
