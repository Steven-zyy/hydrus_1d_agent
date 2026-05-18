# field_comparison

## Purpose

Compare a completed HYDRUS run against measured observation data
(typically CSV or Excel from instrumented profiles) and produce overlay
plots and goodness-of-fit metrics (RMSE, MAE, bias, correlation) at
matching depths.

## When to use this skill

Use this skill when:

- The user provides measured pressure head, water content, or solute
  concentration time series at known depths and wants to know how well
  the model reproduces them.
- A `run_qc` cycle has already produced an `Obs_Node.out` file with
  observation depths aligned (or aliasable) to the measured depths.

Do **not** use this skill when:

- The user wants to compare two model runs to each other → use
  `scenario_comparison`.
- The user has no measured data → use `scientific_reporting` to discuss
  the model results on their own terms.
- The user asks for automatic parameter calibration against the field
  data — that is **out of scope** in the current project.

## Expected inputs

- A completed `runs/<case_id>/` directory with `outputs/Obs_Node.out`
  (the run must have configured observation depths).
- A measured-data file (CSV or Excel) supplied by the user. Columns may
  use common aliases (e.g. `pressure_head` is mapped to `h`); see
  [hydrus_agent/field_comparison.py](../../hydrus_agent/field_comparison.py)
  for the alias table the loader applies.
- A way to map measured depths to HYDRUS observation nodes (exact match
  preferred; nearest-node fallback documented in the module).

## Expected outputs

- A `field_comparison/` (or equivalent) subdirectory inside the run
  folder containing:
  - Overlay plots (modelled vs measured) per variable and depth.
  - A metrics table (RMSE, MAE, bias, correlation) per variable / node.
- A short summary embedded in the run's `report.md` (when the comparison
  is run alongside `--all` with `--field-data`).

## Existing modules and tools used

- [hydrus_agent/field_comparison.py](../../hydrus_agent/field_comparison.py)
  — measured-data loader (CSV / Excel), column alias resolution, depth
  matching, metric computation, overlay plotting.
- [hydrus_agent/output_reader.py](../../hydrus_agent/output_reader.py) —
  parses `Obs_Node.out` into the long-format DataFrame consumed by the
  comparator.
- [hydrus_agent/reporter.py](../../hydrus_agent/reporter.py) — embeds
  comparison metrics into the run report when triggered via `--all`.
- CLI flag: `--field-data` (passed alongside `--config ... --all`).

## Guardrails

- The run must have observation nodes at (or acceptably near) the
  measured depths. If not, do not silently average or interpolate
  without telling the user; either ask them to re-run with adjusted
  observation depths or report the depth gap explicitly.
- Confirm units before reporting metrics. Mixed units (cm vs m, hPa vs
  kPa, % vs cm³/cm³) silently corrupt RMSE. The loader does not
  reinterpret units.
- Do not present metrics for a run whose `overall_status` is not `ok`.
  Report the unreliable status first, then offer to compute the
  metrics on the user's explicit request.
- This skill does **not** perform parameter calibration. If the user
  asks for "best-fit parameters", explain the project does not currently
  support automated inversion and offer `scenario_comparison` with
  hand-picked variations instead.
- Do not modify the measured-data file.

## Failure modes

- **No `Obs_Node.out`** — the run did not declare observation depths.
  Re-design the config (use `case_design` and `soil_profile`) to include
  observations.
- **Measured-depth ↔ node mismatch** — surface the gap and the nearest
  available node. Do not auto-interpolate without the user's consent.
- **Unrecognised column names** — list the columns found and the
  aliases the loader supports; ask the user to rename or supply a
  mapping.
- **Date / time alignment off** — surface the first few mismatched
  timestamps; the loader does not silently shift time.
- **Excel file requires openpyxl that is not installed** — report the
  import error and ask the user whether to convert to CSV or install
  the extra dependency.

## Example user prompts

- "Compare the model to my measurements in
  `field_data/2024_summer.csv` and report RMSE per depth."
- "Run the reviewed config with field data overlay using
  `--field-data`."
- "Plot modelled vs measured pressure head at 30 cm and 60 cm."

## Testing expectations

The following existing tests exercise the modules this skill depends on:

- [tests/test_field_comparison.py](../../tests/test_field_comparison.py)
  — loader, alias handling, depth matching, metric computation.
- [tests/test_output_reader.py](../../tests/test_output_reader.py) —
  `Obs_Node.out` parsing that the comparator consumes.
- [tests/test_reporter.py](../../tests/test_reporter.py) — embedding of
  field-comparison output in the run report.
- [tests/test_cli.py](../../tests/test_cli.py) — `--field-data` argument
  handling.

Future changes to the alias table, depth-matching strategy, or metric
set should extend `tests/test_field_comparison.py`.
