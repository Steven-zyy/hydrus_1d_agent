# HYDRUS-1D Agent

A local, reproducible assistant workflow for preparing, running, reading, plotting, checking, and comparing HYDRUS-1D simulations.

This repository is intended for users who have PC-Progress HYDRUS-1D installed locally and want a safer command-line workflow that can also be operated through Claude Code, Claude Desktop/Cowork, or Codex.

**Platform requirement:** `H1D_CALC.EXE` is a Windows PE executable. It cannot be run on Linux, macOS, WSL, or remote cloud environments including Claude Cowork sessions without a local HYDRUS-1D installation on the same Windows machine. The Python agent code can run anywhere, but HYDRUS execution requires a local Windows installation.

Starting from zero with Codex or Claude Code? See [docs/getting_started_with_codex_or_claude_code.md](docs/getting_started_with_codex_or_claude_code.md).

For everyday use with Codex or Claude Code, see [docs/simple_user_prompts.md](docs/simple_user_prompts.md) for short modelling prompts that the assistant can translate into JSON configs and run through the review-before-run workflow.

## Current Status

This is a `v0.2-local` research prototype. It is useful for simple water-flow workflows, atmospheric forcing, simple root uptake, one-species conservative solute transport, field-data comparison, scenario/sensitivity batches, scenario comparison reports, and benchmark classification against official PC-Progress examples. It is not a replacement for expert HYDRUS model setup or review.

## What It Can Do

- Validate structured JSON HYDRUS-1D case configurations.
- Build simple water-flow configs from natural-language descriptions.
- Review generated configs before running HYDRUS.
- Guard against accidentally running a different config from the one reviewed.
- Prepare HYDRUS project files through the existing phydrus adapter.
- Run `H1D_CALC.EXE` with `--hydrus-launch-mode argv`.
- Distinguish process execution, HYDRUS numerical convergence, QC status, and final reliability in `pipeline_summary.json`.
- Read common HYDRUS outputs: `Balance.out`, `T_Level.out`, `Run_Inf.out`, `Obs_Node.out`, `Nod_Inf.out`, and discovered `SoluteN.out` files.
- Parse generic `Obs_Node.out` and `Nod_Inf.out` files with extra heat, solute, or root-related columns for reporting.
- Generate simple one-species conservative solute transport cases.
- Summarise and plot solute concentrations and solute flux tables from generated runs and copied official examples.
- Compare HYDRUS observation-node outputs against measured CSV field data.
- Run small scenario/sensitivity batches from explicit JSON scenario files.
- Generate comparison reports and optional metric plots from completed scenario batches.
- Generate standard PNG figures.
- Generate field-data overlay plots and simple model-observation metrics.
- Run QC checks and write `qc_summary.json`.
- Write a Markdown report for each run.
- Run copied official PC-Progress examples through a benchmark harness.
- Produce benchmark support and gap reports.
- Produce a full official example sweep report.
- Generate simple atmospheric water-flow `ATMOSPH.IN` records with precipitation, evaporation, and optional `hCritA`, either inline or from a CSV file.
- Read direct van Genuchten material hydraulic parameters from CSV and resolve named soil layers to material IDs.
- Generate simple water-flow root uptake cases with atmospheric forcing, fixed root depth, potential transpiration, and uniform root distribution.

## What It Cannot Do Yet

- Generate multi-solute, adsorption, decay, reaction-chain, volatilisation, non-equilibrium, or salinity/root-stress solute models.
- Generate heat transport models.
- Generate advanced root uptake models, crop growth, salinity stress, or solute uptake.
- Generate hysteresis models.
- Generate dual-porosity or dual-permeability models.
- Generate scaling-factor workflows.
- Automatically repair unsupported or failed HYDRUS inputs.
- Calibrate, optimise, or update parameters from measured field data.
- Expand parameter grids or automatically search parameter space.
- Select best-fit parameters automatically from scenario batches.
- Fit SWCC point-data curves to derive van Genuchten parameters; material hydraulic parameters must be supplied directly (inline or from CSV).
- Provide a GUI or web app.

Some official examples with future-scope physics can be executed, parsed, summarised, and plotted for benchmark reporting, but output interpretation is not the same as generating those physics.

## Documentation

- [User guide](docs/user_guide.md): installation, setup, commands, outputs, troubleshooting, and benchmarks.
- [Demo workflows](docs/demo_workflows.md): worked examples for infiltration, two-layer ponding, and atmospheric rainfall.
- [Benchmark support matrix](docs/benchmark_support_matrix.md): current official PC-Progress example support status.
- [Full official example sweep report](docs/full_example_sweep_report.md): complete benchmark sweep summary and gap categories.
- [Simple user prompts](docs/simple_user_prompts.md): short everyday modelling prompts for Codex / Claude Code users.
- [Using with Claude/Codex](docs/using_with_llm_agents.md): safe prompts and workflows for operating this local agent through an LLM.
- [LLM-assisted JSON configuration](docs/llm_assisted_json_configuration.md): how to use an external LLM to write JSON configs and validate them locally.
- [LLM prompt templates](docs/llm_prompt_templates.md): copy-paste prompts for common Claude/Codex tasks.
- [User acceptance tests](docs/user_acceptance_tests.md): manual checks for non-developer LLM-assisted workflows.
- [Release notes](RELEASE_NOTES.md): local prototype release summary.

## Quickstart

The commands below show the local maintainer paths used for this prototype:
`D:\Claude\hydrus_1d_agent` and
`C:\App\anaconda3\envs\hydrus-agent\python.exe`. Replace them with your own
project folder and Python interpreter path when installing elsewhere.

Open PowerShell in the project root:

```powershell
cd D:\Claude\hydrus_1d_agent
```

Use the project conda environment:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe scripts\check_hydrus_environment.py
```

For a fresh environment, install runtime dependencies with:

```powershell
<python.exe> -m pip install -r requirements.txt
```

Install test-only dependencies when developing or running the test suite:

```powershell
<python.exe> -m pip install -r requirements-dev.txt
```

Project files and output paths shown below are relative to the repository root unless an absolute local setup path is explicitly shown.

Run the simple demo pipeline:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\simple_runnable_case.json --all --overwrite-run --timeout 30 --hydrus-launch-mode argv --allow-config-mismatch
```

The `--allow-config-mismatch` flag is appropriate here because this is an existing hand-authored demo config, not a freshly reviewed natural-language config.

Run the simple root uptake demo:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\simple_root_uptake_case.json --all --overwrite-run --timeout 60 --hydrus-launch-mode argv --allow-config-mismatch
```

Compare a completed or newly run case against measured field data:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\simple_runnable_case.json --all --overwrite-run --timeout 30 --hydrus-launch-mode argv --allow-config-mismatch --field-data data\measured_obs_nodes.csv
```

Run a small sensitivity batch:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\simple_runnable_case.json --scenario-file config\scenarios\simple_sensitivity.json --timeout 60 --hydrus-launch-mode argv
```

Summarise an existing scenario batch without rerunning HYDRUS:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --scenario-report runs\simple_sensitivity
```

Review and run the CSV atmospheric boundary demo:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\csv_atmospheric_boundary_test.json --review
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\csv_atmospheric_boundary_test.json --all --overwrite-run --timeout 60 --hydrus-launch-mode argv
```

Review and run the stable combined CSV demo (30-day, two-layer, all steps converge):

Set `HYDRUS_EXE` before running:

```powershell
$env:HYDRUS_EXE = "C:\Program Files (x86)\PC-Progress\Hydrus-1D 4.xx\H1D_CALC.EXE"
```

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\new_user_dynamic_csv_test.json --review
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\new_user_dynamic_csv_test.json --all --overwrite-run --timeout 60 --hydrus-launch-mode argv
```

A clean run produces `execution_status: completed`, `hydrus_numerical_status: converged`, `qc_status: passed`, `overall_status: ok`. Inspect:

```text
runs\new_user_dynamic_csv_test\pipeline_summary.json
runs\new_user_dynamic_csv_test\outputs\qc_summary.json
runs\new_user_dynamic_csv_test\report.md
runs\new_user_dynamic_csv_test\figures\
```

Generate the same stable demo from natural language using both CSV sources:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --describe "Build a 30-day HYDRUS-1D model for a 2 m vertical soil column with sandy loam from 0 to 1 m and sand from 1 to 2 m. Use atmospheric upper boundary forcing from test_inputs\new_user_dynamic_test\atmosphere_stable_30d.csv, use material hydraulic parameters from test_inputs\new_user_dynamic_test\materials_vg_stable.csv, use free drainage at the bottom, initial pressure head -1.0 m throughout the profile, observation depths 0.2, 0.6, 1.2, and 1.8 m, and print times 1, 3, 5, 7, 10, 14, 20, 25, and 30 days." --write-config config\from_csv_description.json --review
```

## Safe Two-Step Workflow

For a new natural-language case, generate and review the config first:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --describe "1 m sandy loam column, 1 day, 1 mm/day infiltration, free drainage lower boundary, initial pressure head -1 m, observations at 0.3 and 0.7 m" --write-config config\from_description.json --review
```

After reviewing the summary, run that same config:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\from_description.json --all --overwrite-run --timeout 30 --hydrus-launch-mode argv
```

The reviewed-config guard records the reviewed file path and content hash in `.hydrus_agent_state\last_review.json`. If a later command tries to run a different config, the CLI stops before launching HYDRUS unless `--allow-config-mismatch` is explicitly provided.

## Run Reliability

HYDRUS process success is not the same as numerical success. `H1D_CALC.EXE` can return code 0 and write output files even when `Error.msg` reports numerical non-convergence.

The full pipeline now records separate status fields in `runs\<case_id>\pipeline_summary.json`:

- `execution_status`: whether the executable process completed;
- `hydrus_numerical_status`: whether HYDRUS reported convergence or numerical failure;
- `qc_status`: whether post-run QC passed;
- `overall_status`: `ok`, `failed`, or `incomplete`.

If `Error.msg` contains messages such as `stopped after 10 consecutive non-converged steps`, the console and report warn that results may be incomplete or unreliable. Output files and plots are kept for inspection, but they should not be treated as a clean successful simulation. If this happens, review the atmospheric forcing, reduce excessive rainfall or time-step stress, check hydraulic parameters, and adjust numerical controls when that support is available.

## Atmospheric Forcing

Atmospheric upper boundaries can be provided in two ways.

Inline records keep all forcing values in the JSON config:

```json
"upper_boundary": {"type": "atmospheric"},
"atmospheric": {
  "enabled": true,
  "records": [
    {"time": 0.0, "precipitation": 0.0, "evaporation": 0.003, "hCritA": -10000.0},
    {"time": 1.0, "precipitation": 0.001, "evaporation": 0.003, "hCritA": -10000.0}
  ]
}
```

CSV forcing keeps the time series in a separate file and resolves it into the same internal `atmospheric.records` representation during config loading:

```json
"upper_boundary": {"type": "atmospheric"},
"atmospheric": {
  "enabled": true,
  "source_csv": "test_inputs/csv_boundary_test/atmosphere_30d.csv",
  "time_column": "time_d",
  "precipitation_column": "precipitation_m_d",
  "potential_evaporation_column": "potential_evaporation_m_d",
  "units": {"time": "day", "length": "m"}
}
```

Required CSV columns are `time_d`, `precipitation_m_d`, and `potential_evaporation_m_d`. Times are days, flux rates are m/day, and precipitation/evaporation values are non-negative positive-down magnitudes. Review the config before running so the CLI can show the CSV path, record count, time range, totals, maximum rates, unit convention, and whether the forcing covers the simulation end time.

## Material Hydraulic Parameters

Van Genuchten material parameters can be provided inline, as in the older demo configs:

```json
"soil_profile": [
  {"depth_top": 0.0, "depth_bottom": 1.0, "material_id": 1}
],
"van_genuchten": [
  {"material_id": 1, "theta_r": 0.065, "theta_s": 0.41, "alpha": 7.5, "n": 1.89, "Ks": 1.061, "l": 0.5}
]
```

They can also be read directly from CSV:

```json
"soil_profile": [
  {"depth_top": 0.0, "depth_bottom": 1.0, "material": "sandy_loam"},
  {"depth_top": 1.0, "depth_bottom": 2.0, "material": "sand"}
],
"van_genuchten": {
  "source_csv": "test_inputs/csv_boundary_test/materials_vg.csv"
}
```

Required CSV columns are `material`, `theta_r`, `theta_s`, `alpha_1_m`, `n`, `Ks_m_d`, and `l`. The loader validates the file, assigns material IDs in CSV row order, resolves named layers to those IDs, and passes the normal internal `van_genuchten` list to the existing HYDRUS writer. Units are direct HYDRUS-style conventions: water contents are dimensionless, `alpha_1_m` is 1/m, `Ks_m_d` is m/day, and `l` is dimensionless. This is direct parameter input only; SWCC curve fitting is not implemented.

## Using With Claude Or Codex

Open `D:\Claude\hydrus_1d_agent` in Codex, Claude Code, or another local LLM coding tool. Ask it to read `AGENTS.md` and [docs/using_with_llm_agents.md](docs/using_with_llm_agents.md) first.

The LLM should:

- Use `C:\App\anaconda3\envs\hydrus-agent\python.exe` for every Python command.
- Avoid bundled Python and plain `python`.
- Avoid printing `.env` contents.
- Use the generate/review workflow before running newly generated configs.
- Use `--hydrus-launch-mode argv` and a timeout for HYDRUS runs.
- Never modify raw official benchmark examples under `benchmarks\pc_progress_raw\`.

## Output Locations

Normal runs are written under:

```text
runs\<case_id>\
```

Important files:

```text
runs\<case_id>\pipeline_summary.json
runs\<case_id>\report.md
runs\<case_id>\outputs\qc_summary.json
runs\<case_id>\outputs\field_comparison_summary.json
runs\<case_id>\logs\hydrus_run.log
runs\<case_id>\figures\
runs\<case_id>\hydrus_project\
```

Generated run folders are local artifacts and should not be committed.

## Field Data Comparison

Measured field data can be supplied as CSV. Excel files are optional and only work when the installed pandas environment has the needed Excel reader dependency.

CSV columns may use aliases, but the normalized shape is:

```text
time,node,theta,h
0.25,3,0.121,-1.02
0.50,3,0.120,-1.04
```

Use `node` when possible. A `depth` column can be used instead only when the config has `observation_depths`, so the agent can map measured depths to HYDRUS observation nodes.

When `--field-data` is supplied, the agent writes:

```text
runs\<case_id>\outputs\field_comparison_summary.json
runs\<case_id>\figures\field_overlay_theta.png
runs\<case_id>\figures\field_overlay_head.png
```

The summary includes RMSE, MAE, bias, correlation, and matched point count for each comparable variable and node. This is comparison only; it does not calibrate or change model parameters.

## Scenario Batches

Scenario files run a small, explicit list of parameter variants. They are for transparent sensitivity checks, not calibration or optimisation.

Example:

```text
config\scenarios\simple_sensitivity.json
```

Run:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\simple_runnable_case.json --scenario-file config\scenarios\simple_sensitivity.json --timeout 60 --hydrus-launch-mode argv
```

Each scenario gets a case ID:

```text
<base_case_id>__<scenario_id>
```

Batch summaries are written to:

```text
runs\<batch_id>\scenario_summary.csv
runs\<batch_id>\scenario_summary.json
```

Generate a comparison report from an existing batch:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --scenario-report runs\simple_sensitivity
```

This reads `runs\<batch_id>\scenario_summary.csv` and writes:

```text
runs\<batch_id>\scenario_report.md
runs\<batch_id>\figures\scenario_metric_bar_infiltration.png
runs\<batch_id>\figures\scenario_metric_bar_bottom_flux.png
runs\<batch_id>\figures\scenario_field_rmse_comparison.png
```

The field RMSE figure is written only when field-data RMSE columns are present in the scenario summary. This comparison step does not rerun simulations, calibrate parameters, optimise parameters, or change existing run outputs.

Supported override paths are:

```text
van_genuchten[i].Ks
van_genuchten[i].alpha
van_genuchten[i].n
initial_condition.value
upper_boundary.flux
upper_boundary.head
root_uptake.root_depth
solute_transport.species[0].dispersivity
```

The runner validates every scenario before running the first one, so unsupported override paths, duplicate IDs, unsafe IDs, and invalid generated configs fail early.

## Official Benchmarks

Place official PC-Progress examples under:

```text
benchmarks\pc_progress_raw\Direct\
```

Run one example through a copied workspace:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --benchmark-official benchmarks\pc_progress_raw\Direct\1DRAINAG --benchmark-id 1DRAINAG --timeout 60 --hydrus-launch-mode argv
```

The harness copies the raw example to:

```text
benchmarks\benchmark_results\<case_id>\hydrus_project\
```

Run the manifest-supported set:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --benchmark-manifest benchmarks\manifest.csv --timeout 60 --hydrus-launch-mode argv
```

Run the full official example sweep when needed:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --benchmark-manifest benchmarks\manifest.csv --all-examples --timeout 60 --hydrus-launch-mode argv
```

Benchmark inputs and generated benchmark results are ignored by git. Current benchmark status is documented in [docs/benchmark_support_matrix.md](docs/benchmark_support_matrix.md) and [docs/full_example_sweep_report.md](docs/full_example_sweep_report.md).

## HYDRUS_EXE Setup

Set `HYDRUS_EXE` to the absolute path of `H1D_CALC.EXE`. A project-local `.env` file is usually easiest:

```text
HYDRUS_EXE=C:\Program Files\PC-Progress\Hydrus-1D 4.xx\H1D_CALC.EXE
```

Do not commit `.env`.

You can verify setup with:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe scripts\check_hydrus_environment.py
```

## Test Command

Use the project-local temporary directory:

```powershell
New-Item -ItemType Directory -Force "D:\Claude\hydrus_1d_agent\.codex_tmp"
$env:TEMP="D:\Claude\hydrus_1d_agent\.codex_tmp"
$env:TMP="D:\Claude\hydrus_1d_agent\.codex_tmp"
C:\App\anaconda3\envs\hydrus-agent\python.exe -m pytest tests/ -v --basetemp "D:\Claude\hydrus_1d_agent\.codex_tmp\pytest_base"
```

## Repository Layout

```text
hydrus_1d_agent/
  config/                 Example JSON configs
  docs/                   User, demo, and benchmark documentation
  hydrus_agent/           Library modules
  scripts/                Environment and maintenance scripts
  tests/                  Unit tests
  benchmarks/             Manifest plus ignored raw/results folders
  runs/                   Ignored runtime outputs
  main.py                 CLI entry point
```

## Safety Rules

- Do not modify raw official examples under `benchmarks\pc_progress_raw\`.
- Do not commit `.env`, `runs\`, `.hydrus_agent_state\`, `.codex_tmp\`, raw official examples, or benchmark result folders.
- Use copied benchmark workspaces under `benchmarks\benchmark_results\`.
- Run only reviewed generated configs unless a mismatch is explicitly allowed.
- Treat unsupported solute, heat, advanced root uptake, hysteresis, dual-porosity, and scaling examples as documented gaps, not whole-agent failures.
