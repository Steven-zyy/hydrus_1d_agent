# HYDRUS-1D Agent User Guide

This guide is for users who want to generate, run, and review HYDRUS-1D cases without reading the internal Python code. It covers all currently supported usage modes — config-driven, built-in `--describe`, and LLM-assisted JSON — and the reliability checks that follow every run.

The `v0.5-csv-reliability` prototype covers simple water-flow cases, CSV-driven atmospheric forcing, CSV-driven material hydraulic parameters, simple root uptake, one-species conservative solute transport, field-data comparison, scenario/sensitivity batches, scenario comparison reports, and official benchmark reporting. It does not perform calibration, optimisation, heat transport generation, hysteresis, dual porosity, advanced solute chemistry, or SWCC point-data curve fitting.

The examples use PowerShell from the project root. The paths `D:\Claude\hydrus_1d_agent` and `C:\App\anaconda3\envs\hydrus-agent\python.exe` are local prototype paths; replace them with your own project folder and Python interpreter path on a different machine.

```powershell
cd D:\Claude\hydrus_1d_agent
```

---

## 1. What This Agent Does

The HYDRUS-1D agent is a deterministic Python wrapper around PC-Progress HYDRUS-1D. Given a validated JSON configuration, it:

1. Validates the configuration against a strict schema.
2. Creates a run folder under `runs\<case_id>\`.
3. Prepares HYDRUS-1D input files through the `phydrus` adapter.
4. Invokes `H1D_CALC.EXE` with a timeout and a chosen launch mode.
5. Reads HYDRUS output tables (`Balance.out`, `T_Level.out`, `Run_Inf.out`, `Obs_Node.out`, `Nod_Inf.out`, and discovered `SoluteN.out` files).
6. Generates standard PNG figures.
7. Runs rule-based QC and writes `qc_summary.json`.
8. Writes a Markdown reliability-aware report (`report.md`).

The agent never calls an external LLM API. When you operate it through Codex or Claude Code, the assistant is the external LLM — it writes JSON; the agent validates, runs, and checks reliability.

---

## 2. Platform Requirements

- **Operating system:** Windows. `H1D_CALC.EXE` is a Windows PE executable. Linux, macOS, WSL, and remote cloud sandboxes cannot directly execute it.
- **HYDRUS-1D:** PC-Progress HYDRUS-1D installed locally. The agent does not ship HYDRUS.
- **Python:** Python 3.10 or newer with the project requirements installed. The maintainer workspace uses `C:\App\anaconda3\envs\hydrus-agent\python.exe`.
- **Environment variable:** `HYDRUS_EXE` must point to the full path of `H1D_CALC.EXE`.

The Python agent code (validation, `--review`, `--write-config-template`, `--print-config-schema`) can run on any platform. Only `--all`, `--run`, and benchmark commands require Windows + HYDRUS.

If your coding assistant is in a Linux/cloud sandbox, it can still help you prepare and review configs, but it cannot launch HYDRUS. You will run those commands yourself in a local Windows PowerShell session.

---

## 3. Choosing a Usage Mode

The agent supports three usage modes. They differ in **who writes the JSON config**:

| Mode | Config author | Best for |
|---|---|---|
| **Config-driven** | You (by hand or by editing a template) | Reproducible runs, version-controlled experiments, demos |
| **Built-in `--describe`** | The agent's rule-based parser | Quick one-liners that match supported patterns |
| **LLM-assisted JSON** | An external LLM (Claude Code, Codex, GPT-4) | Everyday natural-language requests, custom or complex setups |

All three modes feed into the **same** review-before-run workflow:

```
JSON config → --review → check review → --all → inspect reliability outputs
```

**For everyday users with Codex or Claude Code, the LLM-assisted JSON mode is the recommended path.** See section 9 below and [docs/simple_user_prompts.md](simple_user_prompts.md) for short modelling prompts.

---

## 4. Recommended Workflow for Most Users

If you are using Codex or Claude Code in this project:

1. Open the project folder. The assistant reads `AGENTS.md` and `CLAUDE.md` automatically.
2. Give a short modelling prompt, for example:

   > "Use the HYDRUS-1D agent to build and run a 30-day 1D infiltration model for a 2 m sandy loam over sand profile. Use existing CSV inputs for atmosphere and material properties. Review before running and tell me whether the result is reliable."

3. The assistant should then internally:
   - infer a reasonable `case_id`;
   - choose or create the CSV inputs (defaulting to the stable demo CSVs when the request is generic);
   - write `config\<case_id>.json`;
   - run `--review`;
   - run `--all` only if the review is valid;
   - inspect `pipeline_summary.json`, `qc_summary.json`, `Error.msg` (if present), `report.md`, and `figures\`;
   - report `execution_status`, `hydrus_numerical_status`, `qc_status`, `overall_status`, max water-balance error, and whether the result is suitable for interpretation.

You do not need to repeat any of these commands in your prompt. The project-level instructions teach the assistant to follow this workflow by default.

For full detail on the LLM-assisted JSON workflow, see [docs/llm_assisted_json_configuration.md](llm_assisted_json_configuration.md).

---

## 5. Environment Setup

### 5.1 Conda environment

Create and activate an environment using your normal conda workflow. The repository expects Python 3.10+ and the packages in `requirements.txt`.

```powershell
conda create -n hydrus-agent python=3.10
conda activate hydrus-agent
C:\App\anaconda3\envs\hydrus-agent\python.exe -m pip install -r requirements.txt
```

For development and tests, also install the test-only requirements:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe -m pip install -r requirements-dev.txt
```

Do not install dependencies unless you are setting up a fresh environment.

### 5.2 HYDRUS-1D installation

Install HYDRUS-1D from PC-Progress. Find the executable. It is usually similar to:

```text
C:\Program Files\PC-Progress\Hydrus-1D 4.xx\H1D_CALC.EXE
```

The path must point to `H1D_CALC.EXE` itself, not the installation folder.

### 5.3 Setting `HYDRUS_EXE`

The agent reads `HYDRUS_EXE` from the process environment first, then from a project-local `.env` file.

**Project-local `.env` (recommended):**

```powershell
Set-Content -Path .env -Value 'HYDRUS_EXE=C:\Program Files\PC-Progress\Hydrus-1D 4.xx\H1D_CALC.EXE'
```

Do not commit `.env`.

**One-session:**

```powershell
$env:HYDRUS_EXE = "C:\Program Files\PC-Progress\Hydrus-1D 4.xx\H1D_CALC.EXE"
```

**Persistent user setup:**

```powershell
setx HYDRUS_EXE "C:\Program Files\PC-Progress\Hydrus-1D 4.xx\H1D_CALC.EXE"
```

Open a new terminal after `setx`.

### 5.4 Verify the environment

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe scripts\check_hydrus_environment.py
```

This checks that `phydrus` imports and `HYDRUS_EXE` points to a real file. It does not run HYDRUS. Successful output ends with `Environment is READY`.

### 5.5 Always use the full Python path

On Windows, plain `python` often resolves to the Microsoft Store stub or the wrong environment. Use the full conda interpreter path:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe
```

---

## 6. Review-Before-Run Workflow

All three usage modes share the same safety workflow:

```
1. Produce config\<case_id>.json   (config-driven, --describe, or LLM-assisted JSON)
2. main.py --config config\<case_id>.json --review
3. Read the review summary; abort if anything looks wrong
4. main.py --config config\<case_id>.json --all --overwrite-run --timeout 60 --hydrus-launch-mode argv
5. Inspect pipeline_summary.json, qc_summary.json, Error.msg, report.md, figures\
```

`--review` validates the config, prints a human-readable summary (case ID, simulation window, soil layers, material parameters, boundaries, **initial condition**, observation depths, print times, atmospheric CSV metadata, material CSV metadata), and records the reviewed file path and content hash in `.hydrus_agent_state\last_review.json`. It does **not** run HYDRUS.

Before `--all` runs, the agent checks that the requested config is the same reviewed file with the same content. If it has changed, the CLI stops and prints both the reviewed and requested paths. To proceed, either re-`--review` the edited config, or pass `--allow-config-mismatch`.

**Do not use `--allow-config-mismatch` unless you understand the safety implications.** It is appropriate for existing hand-authored demo configs and intentional manual edits — not for accidental mismatches or LLM-generated configs that have not been re-reviewed.

CSV path displays in the review output now carry a `(relative)` or `(absolute)` annotation so you can see at a glance whether the config will be portable across machines.

---

## 7. Config-Driven Mode

You write or edit a JSON config directly and run it. This is the most reproducible mode.

### Example 1: review and run the stable 30-day demo

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\new_user_dynamic_csv_test.json --review
```

The review should report:

- `Validation status: valid ModelConfig`
- atmospheric CSV: path, 31 records, time range 0–30 days
- material CSV: path, two materials (sandy_loam, sand) with van Genuchten parameters
- initial condition: `pressure_head = -1.0`
- observation depths: 0.2, 0.6, 1.2, 1.8 m
- upper boundary: atmospheric / lower boundary: free drainage

After the review passes:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\new_user_dynamic_csv_test.json --all --overwrite-run --timeout 60 --hydrus-launch-mode argv
```

A clean run produces `execution_status: completed`, `hydrus_numerical_status: converged`, `qc_status: passed`, `overall_status: ok`.

### Starting from the canonical template

To produce a fresh editable config:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --write-config-template config\my_model.json
```

The template points to the stable demo CSVs using relative paths, so a copy-and-edit workflow produces portable configs by default.

### Hand-authored demo configs

Older hand-authored demos (e.g. `config\simple_runnable_case.json`, `config\simple_root_uptake_case.json`, `config\simple_conservative_solute_case.json`) ship with the repository for reference. Because they were not produced via `--review` in this session, pass `--allow-config-mismatch` when running them:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\simple_runnable_case.json --all --overwrite-run --timeout 30 --hydrus-launch-mode argv --allow-config-mismatch
```

---

## 8. Built-in `--describe` Mode

`--describe` is a rule-based parser implemented in the agent itself. It converts a constrained natural-language description into a validated JSON config. It does **not** call an LLM.

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --describe "1 m sandy loam column, 1 day, 1 mm/day infiltration, free drainage lower boundary, initial pressure head -1 m, observations at 0.3 and 0.7 m" --write-config config\from_description.json --review
```

After review:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\from_description.json --all --overwrite-run --timeout 30 --hydrus-launch-mode argv
```

### Stable 30-day sandy-loam-over-sand example with CSV sources

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --describe "Build a 30-day HYDRUS-1D model for a 2 m vertical soil column with sandy loam from 0 to 1 m and sand from 1 to 2 m. Use atmospheric upper boundary forcing from test_inputs\new_user_dynamic_test\atmosphere_stable_30d.csv, use material hydraulic parameters from test_inputs\new_user_dynamic_test\materials_vg_stable.csv, use free drainage at the bottom, initial pressure head -1.0 m throughout the profile, observation depths 0.2, 0.6, 1.2, and 1.8 m, and print times 1, 3, 5, 7, 10, 14, 20, 25, and 30 days." --write-config config\from_csv_description.json --review
```

The builder recognises phrases such as `atmospheric upper boundary forcing from <path>.csv`, `material hydraulic parameters from <path>.csv`, `van Genuchten parameters from <path>.csv`, `VG parameters from <path>.csv`, and `use material CSV <path>.csv`.

### Scope and limits

`--describe` supports simple 1D water-flow columns, one or more contiguous soil layers, pressure-head initial conditions, constant-flux or constant-head upper boundaries, inline or CSV atmospheric forcing, simple atmospheric root uptake (fixed root depth, uniform distribution), simple one-species conservative tracer transport, free-drainage lower boundaries, observation depths, and print times.

It does **not** support multi-solute transport, adsorption, decay, reaction chains, volatilisation, non-equilibrium transport, heat transport, advanced root uptake, crop growth, salinity stress, hysteresis, dual porosity, dual permeability, scaling factors, or SWCC fitting.

When `--describe` is too narrow for your case, switch to LLM-assisted JSON mode (section 9) and let the assistant write the JSON directly.

### One-shot describe-review-run

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --describe "..." --write-config config\from_description.json --run-after-review --overwrite-run --timeout 30 --hydrus-launch-mode argv
```

---

## 9. LLM-Assisted JSON Configuration Mode

This is the recommended mode for everyday users operating through Codex or Claude Code.

The external LLM (the coding assistant) writes a JSON config; the HYDRUS agent validates, reviews, runs, and checks reliability. No internal LLM API is called.

### Example 3: simple user prompt

You can simply ask:

> "Use the HYDRUS-1D agent to build and run a 30-day 1D infiltration model for a 2 m sandy loam over sand profile. Use existing CSV inputs for atmosphere and material properties. Review before running and tell me whether the result is reliable."

What the assistant should do internally:

```
simple prompt
  → pick a sensible case_id
  → choose CSV inputs (stable demo CSVs when the request is generic)
  → write config\<case_id>.json
  → main.py --config config\<case_id>.json --review
  → check the review output is valid
  → main.py --config config\<case_id>.json --all --overwrite-run --timeout 60 --hydrus-launch-mode argv
  → inspect pipeline_summary.json, qc_summary.json, Error.msg, report.md, figures\
  → report reliability statuses and whether the result is suitable for interpretation
```

### Tools the assistant uses

- `main.py --write-config-template [PATH]` — copy the canonical template (or print to stdout).
- `main.py --print-config-schema [--schema-output PATH]` — dump the Pydantic JSON schema for `ModelConfig`.
- `main.py --config <path> --review` — validate and summarise.
- `main.py --config <path> --all ...` — run the full pipeline.

### Safety rules for LLM-generated configs

- LLM-generated JSON must always pass `--review` before running.
- The reviewed-config guard prevents accidentally running a different config than the one reviewed.
- Do not bypass the guard with `--allow-config-mismatch` for LLM-generated configs unless you have manually inspected the config.
- Configs should use relative `source_csv` paths so they are portable across machines.

For the full technical reference (template, schema, prompt template, troubleshooting), see [docs/llm_assisted_json_configuration.md](llm_assisted_json_configuration.md). For short user-facing prompt examples, see [docs/simple_user_prompts.md](simple_user_prompts.md).

---

## 10. Atmospheric CSV Input

Atmospheric upper boundaries use:

```json
"upper_boundary": {"type": "atmospheric"}
```

The forcing itself can be supplied inline or from CSV.

**Inline records** are stored directly in the JSON:

```json
"atmospheric": {
  "enabled": true,
  "records": [
    {"time": 0.0, "precipitation": 0.0, "evaporation": 0.003, "hCritA": -10000.0},
    {"time": 1.0, "precipitation": 0.001, "evaporation": 0.003, "hCritA": -10000.0}
  ]
}
```

**CSV forcing** stores the time series in a separate file and resolves it into the same internal `atmospheric.records` representation during config validation:

```json
"atmospheric": {
  "enabled": true,
  "source_csv": "test_inputs/new_user_dynamic_test/atmosphere_stable_30d.csv",
  "time_column": "time_d",
  "precipitation_column": "precipitation_m_d",
  "potential_evaporation_column": "potential_evaporation_m_d",
  "units": {"time": "day", "length": "m"}
}
```

For compatibility with compact configs, the same CSV fields can also be placed under `upper_boundary` when its `type` is `atmospheric`; the loader copies them into the atmospheric forcing structure.

**Required CSV columns** (in any order):

```text
time_d,precipitation_m_d,potential_evaporation_m_d
```

Rules:

- `time_d` is time in days, numeric, non-negative, and strictly increasing.
- `precipitation_m_d` is precipitation/infiltration flux rate in m/day, numeric, and non-negative.
- `potential_evaporation_m_d` is potential soil evaporation rate in m/day, numeric, and non-negative.
- The forcing must cover the full simulation window. Empty files, missing values, missing columns, non-numeric values, negative values, and forcing that does not cover the end time are rejected with clear validation errors.

The review output shows the CSV path, record count, time range, total precipitation, total potential evaporation, maximum rates, unit convention, whether the forcing covers the simulation end time, and a `(relative)` / `(absolute)` annotation on the path.

---

## 11. Material Hydraulic Parameter CSV Input

Van Genuchten material parameters can be supplied inline or from CSV.

**Inline parameters** are the simplest option for small hand-written configs:

```json
"soil_profile": [
  {"depth_top": 0.0, "depth_bottom": 1.0, "material_id": 1}
],
"van_genuchten": [
  {
    "material_id": 1,
    "theta_r": 0.065,
    "theta_s": 0.41,
    "alpha": 7.5,
    "n": 1.89,
    "Ks": 1.061,
    "l": 0.5
  }
]
```

**CSV input** stores direct van Genuchten parameters in a separate table and references soil layers by material name:

```json
"soil_profile": [
  {"depth_top": 0.0, "depth_bottom": 1.0, "material": "sandy_loam"},
  {"depth_top": 1.0, "depth_bottom": 2.0, "material": "sand"}
],
"van_genuchten": {
  "source_csv": "test_inputs/new_user_dynamic_test/materials_vg_stable.csv"
}
```

**Required CSV columns** (in any order):

```text
material,theta_r,theta_s,alpha_1_m,n,Ks_m_d,l
```

Rules:

- `material` must be non-empty and unique. Soil layers that use `material` or `material_name` must match a name in the CSV.
- `theta_r` and `theta_s` are dimensionless water contents; `theta_r >= 0` and `theta_s > theta_r`.
- `alpha_1_m` is van Genuchten alpha in 1/m, positive.
- `n` must be greater than 1.
- `Ks_m_d` is saturated hydraulic conductivity in m/day, positive.
- `l` is dimensionless and numeric.

Empty files, missing files, missing columns, duplicate names, missing values, and out-of-range numerics are rejected during config validation.

The review output shows the material CSV path (with `(relative)` / `(absolute)` annotation), number of materials, material names, each material's parameters, and the unit conventions.

---

## 12. SWCC Point-Data Fitting Is Not Implemented

The agent accepts **direct** van Genuchten parameters only. It does **not** fit a soil-water characteristic curve from point measurements such as `(matric potential, water content)` pairs.

If you have SWCC measurements, derive the van Genuchten parameters outside the agent (for example with RETC, HYDRUS's bundled fitting GUI, or a SciPy/optimization script) and supply the results as either:

- inline `van_genuchten` entries with `theta_r`, `theta_s`, `alpha`, `n`, `Ks`, `l`; or
- a material CSV with columns `material`, `theta_r`, `theta_s`, `alpha_1_m`, `n`, `Ks_m_d`, `l`.

If you ask Codex or Claude Code for "SWCC fitting", the assistant should explain that this is not implemented and ask for direct parameters instead.

---

## 13. Running the Stable Demo

The stable demo config exercises CSV-driven atmospheric forcing, CSV-driven material parameters, two soil layers, free drainage, and a 30-day simulation window with safe rainfall rates. All 30 time steps converge.

Files:

- `config\new_user_dynamic_csv_test.json`
- `test_inputs\new_user_dynamic_test\atmosphere_stable_30d.csv`
- `test_inputs\new_user_dynamic_test\materials_vg_stable.csv`

Review and run:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\new_user_dynamic_csv_test.json --review
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\new_user_dynamic_csv_test.json --all --overwrite-run --timeout 60 --hydrus-launch-mode argv
```

A clean run produces `overall_status: ok` and a maximum water-balance error under 1 %. Inspect:

```text
runs\new_user_dynamic_csv_test\pipeline_summary.json
runs\new_user_dynamic_csv_test\outputs\qc_summary.json
runs\new_user_dynamic_csv_test\report.md
runs\new_user_dynamic_csv_test\figures\
```

---

## 14. Understanding Outputs

A run creates or reuses:

```text
runs\<case_id>\
  config.json
  pipeline_summary.json
  report.md
  hydrus_project\          ← HYDRUS input and output files, including Error.msg
  logs\
    hydrus_run.log         ← command, launch mode, stdout, stderr
  outputs\
    qc_summary.json        ← machine-readable QC result
    field_comparison_summary.json   ← present only with --field-data
  figures\
    balance_storage_vs_time.png
    instantaneous_fluxes.png
    cumulative_water_balance.png
    obs_theta_vs_time.png
    obs_head_vs_time.png
    moisture_profiles.png
    pressure_head_profiles.png
    moisture_contour.png
    run_diagnostics.png
    field_overlay_theta.png         ← with --field-data
    field_overlay_head.png          ← with --field-data
```

### Inspecting outputs after a run

Read outputs without running HYDRUS:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\<case_id>.json --read-output
```

Regenerate figures, QC, or the report independently:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\<case_id>.json --plot
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\<case_id>.json --qc
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\<case_id>.json --report
```

QC checks: output table presence, water balance, cumulative fluxes, observation nodes, profile output, solver convergence, expected figures, and any discovered solute concentration/flux outputs.

### Field-data comparison (post-processing only)

Field-data comparison is post-processing only. It does **not** calibrate, optimise, or change model parameters.

Preferred CSV shape:

```text
time,node,theta,h
0.25,3,0.121,-1.02
0.50,3,0.120,-1.04
```

Column aliases such as `Water_Content`, `Pressure_Head`, `head`, `moisture` are accepted. If `node` is present it is matched directly; if only `depth` is present, it is mapped to nodes via the config's `observation_depths`. Only matching times and nodes are compared, and only variables available in both the CSV and `Obs_Node.out`.

Run a full pipeline with field data:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\simple_runnable_case.json --all --overwrite-run --timeout 30 --hydrus-launch-mode argv --allow-config-mismatch --field-data data\measured_obs_nodes.csv
```

The summary reports RMSE, MAE, bias, correlation, and matched point count per comparable variable and node.

### Scenario and sensitivity batches

Scenario batches run a small, explicit list of parameter variants. They do **not** calibrate, optimise, fit parameters, or expand grids automatically.

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\simple_runnable_case.json --scenario-file config\scenarios\simple_sensitivity.json --timeout 60 --hydrus-launch-mode argv
```

Each scenario gets a unique case ID: `<base_case_id>__<scenario_id>`. Batch summaries land in `runs\<batch_id>\scenario_summary.csv` / `.json`. Generate a comparison report from an existing batch:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --scenario-report runs\simple_sensitivity
```

Supported override paths:

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

The runner validates every scenario ID and override path before running anything.

### Official benchmark runs

Raw official PC-Progress examples live under `benchmarks\pc_progress_raw\Direct\`. Do not run or edit them directly — the benchmark harness copies each example into `benchmarks\benchmark_results\<benchmark_id>\hydrus_project\` before running.

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --benchmark-official benchmarks\pc_progress_raw\Direct\1DRAINAG --benchmark-id 1DRAINAG --timeout 60 --hydrus-launch-mode argv
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --benchmark-manifest benchmarks\manifest.csv --timeout 60 --hydrus-launch-mode argv
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --benchmark-gap-report benchmarks\manifest.csv
```

Current support is summarised in [docs/benchmark_support_matrix.md](benchmark_support_matrix.md).

### Supported optional features (brief)

**Simple root uptake** — water-flow cases with atmospheric forcing, fixed root depth, uniform distribution. Demo: `config\simple_root_uptake_case.json`.

**Simple conservative solute** — single species, non-negative initial/boundary concentrations, no adsorption/decay/reactions. Demo: `config\simple_conservative_solute_case.json`.

Both are described in detail in [docs/demo_workflows.md](demo_workflows.md).

---

## 15. Reliability Status Fields

HYDRUS process return code is not the same as numerical convergence. `H1D_CALC.EXE` can return code 0 and write output files even when `Error.msg` reports the solver stopped after repeated non-converged steps.

**Never treat HYDRUS exit code 0 alone as success.**

`pipeline_summary.json` records four independent status fields:

| Field | Meaning | Source |
|---|---|---|
| `execution_status` | Did the `H1D_CALC.EXE` process complete without timeout or process error? | Runner exit code + timeout marker |
| `hydrus_numerical_status` | Did HYDRUS report numerical convergence? | Parsing `Error.msg` |
| `qc_status` | Did post-run QC (water balance, expected outputs) pass? | `qc_summary.json` |
| `overall_status` | Combined reliability: `ok`, `failed`, or `incomplete` | Aggregated from the three above |

A run is suitable for interpretation only when `overall_status` is `ok`. If any component status is `failed`, treat the run as diagnostic only — output files and figures after the failure time may be incomplete or unreliable.

After every `--all` run, the assistant (or you) should inspect and report:

- `execution_status`
- `hydrus_numerical_status`
- `qc_status`
- `overall_status`
- maximum water-balance error from `qc_summary.json` if available
- whether the run is suitable for interpretation

`report.md` qualifies its convergence wording automatically when `Error.msg` or QC indicates failure.

### What to check after numerical non-convergence

- Reduce rainfall intensity or sharp forcing changes;
- review the atmospheric CSV for time gaps, spikes, and unit mistakes;
- check `theta_r`, `theta_s`, `alpha`, `n`, `Ks`, and `l` values;
- review the initial pressure head and layer boundaries;
- if you intentionally want to inspect a failed run, keep the run folder for diagnosis — it is not deleted automatically.

---

## 16. Troubleshooting

### Python not found / Microsoft Store stub opens

Use the full conda interpreter path:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --help
```

If that path does not exist on your machine, activate your own conda environment and use its `python.exe`.

### `HYDRUS_EXE` not set or path wrong

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe scripts\check_hydrus_environment.py
```

If it fails, check that `.env` or `$env:HYDRUS_EXE` points to `H1D_CALC.EXE`, not the containing folder.

### Review guard blocks a run after editing the config

Either re-`--review` the edited config, or pass `--allow-config-mismatch` only if you intentionally want to run a manually edited config and understand the implications.

### HYDRUS returns 0 but the report says the run failed

`H1D_CALC.EXE` can return 0 while `Error.msg` reports non-convergence. The agent separates `execution_status` from `hydrus_numerical_status` for exactly this reason. Inspect `pipeline_summary.json`, `qc_summary.json`, and the run's `Error.msg` in `hydrus_project\`.

### SWCC point-data CSV does not work

SWCC fitting is not implemented. The material CSV must contain direct van Genuchten parameters (`theta_r`, `theta_s`, `alpha_1_m`, `n`, `Ks_m_d`, `l`). See section 12.

### Coding assistant is in a Linux/cloud sandbox

The assistant cannot reach Windows paths or launch `H1D_CALC.EXE`. Use it to prepare and review configs; run HYDRUS commands yourself in a local PowerShell session.

### `LEVEL_01.DIR` / `argv` mode issue

The recommended launch mode is `argv`. If it fails on your HYDRUS build, try `--hydrus-launch-mode level-dir`. For diagnostics without running HYDRUS:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\<case_id>.json --diagnose-run --hydrus-launch-mode argv
```

### Pytest temp permission issues

Use the project-local temp directory:

```powershell
New-Item -ItemType Directory -Force "D:\Claude\hydrus_1d_agent\.codex_tmp"
$env:TEMP="D:\Claude\hydrus_1d_agent\.codex_tmp"
$env:TMP="D:\Claude\hydrus_1d_agent\.codex_tmp"
C:\App\anaconda3\envs\hydrus-agent\python.exe -m pytest tests/ -v --basetemp "D:\Claude\hydrus_1d_agent\.codex_tmp\pytest_base"
```

### Benchmark raw-folder safety

Raw official examples under `benchmarks\pc_progress_raw\` must not be modified. Benchmark commands should always go through `--benchmark-official` or `--benchmark-manifest`, which copy each example into `benchmarks\benchmark_results\` before running. If you ever see new logs or modified timestamps inside the raw folder after a benchmark run, stop and inspect the command.

---

## 17. Links to Related Docs

- [docs/getting_started_with_codex_or_claude_code.md](getting_started_with_codex_or_claude_code.md) — first-run walkthrough from zero to a successful HYDRUS run.
- [docs/simple_user_prompts.md](simple_user_prompts.md) — short everyday modelling prompts for Codex / Claude Code users.
- [docs/llm_assisted_json_configuration.md](llm_assisted_json_configuration.md) — technical reference for the LLM-assisted JSON workflow: template, schema, prompt, troubleshooting.
- [docs/demo_workflows.md](demo_workflows.md) — worked examples for simple infiltration, two-layer ponding, atmospheric rainfall, root uptake, and conservative solute transport.
- [docs/using_with_llm_agents.md](using_with_llm_agents.md) — developer-level reference for operating the agent through Claude or Codex.
- [docs/benchmark_support_matrix.md](benchmark_support_matrix.md) — official PC-Progress example support status.
- [AGENTS.md](../AGENTS.md) / [CLAUDE.md](../CLAUDE.md) — assistant-facing project instructions.
- [RELEASE_NOTES.md](../RELEASE_NOTES.md) — what changed in each release.
