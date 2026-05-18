# AGENTS.md - HYDRUS-1D Agent Project Instructions

This repository contains a local HYDRUS-1D automation agent.

It is a **Windows-local** HYDRUS-1D automation agent. Full HYDRUS execution requires a local Windows installation of PC-Progress HYDRUS-1D and access to `H1D_CALC.EXE`. The Python helpers (`--review`, `--write-config-template`, `--print-config-schema`) work on any platform.

## Step 0 — Identify the relevant skill

Before writing configs, running HYDRUS, or interpreting results, identify which skill(s) under [`skills/`](skills/) the user's request maps to and read the matching `SKILL.md`. Skills describe the standard workflow, guardrails, and failure modes for each modelling activity. The current skill catalogue:

- [`skills/case_design/`](skills/case_design/SKILL.md) — translating a request into a reviewable config
- [`skills/boundary_condition/`](skills/boundary_condition/SKILL.md) — choosing boundaries and atmospheric forcing
- [`skills/soil_profile/`](skills/soil_profile/SKILL.md) — building the layered profile and van Genuchten parameters
- [`skills/run_qc/`](skills/run_qc/SKILL.md) — executing the pipeline and reading the four-status reliability report
- [`skills/scenario_comparison/`](skills/scenario_comparison/SKILL.md) — running parameter-override batches
- [`skills/field_comparison/`](skills/field_comparison/SKILL.md) — comparing measured data against `Obs_Node.out`
- [`skills/scientific_reporting/`](skills/scientific_reporting/SKILL.md) — composing the final answer with the required reliability statement

If the request spans multiple skills (typical), read each `SKILL.md` in the order they will be applied. Skills do not replace the rules in this file — they specialise them. There is no runtime skill framework and no `--skill` CLI flag; skills are documentation. See [`skills/README.md`](skills/README.md) for the index and structure.

## Default workflow for everyday user prompts

When a user gives a short modelling request such as "build a 30-day model with sandy loam over sand and tell me whether the result is reliable", you should follow this workflow without asking the user to repeat the steps. See [docs/simple_user_prompts.md](docs/simple_user_prompts.md) for prompt examples.

```
User prompt
  → infer reasonable case_id
  → choose existing CSV inputs (or ask the user once if missing)
  → write config/<case_id>.json directly (LLM-assisted JSON mode)
  → main.py --config config/<case_id>.json --review
  → check the review output is valid
  → main.py --config config/<case_id>.json --all --overwrite-run --timeout 60 --hydrus-launch-mode argv
  → inspect pipeline_summary.json, qc_summary.json, Error.msg if present, report.md, figures/
  → report execution_status, hydrus_numerical_status, qc_status, overall_status,
    max water-balance error, and whether the result is suitable for interpretation
```

Prefer **LLM-assisted JSON configuration mode** (you write `config/<case_id>.json`) over `--describe` for new user prompts. `--describe` is a rule-based parser kept for legacy and developer use; the JSON path is more transparent and reviewable. See [docs/llm_assisted_json_configuration.md](docs/llm_assisted_json_configuration.md) for the schema, template, and prompt.

Use stable demo CSV files under `test_inputs/new_user_dynamic_test/` only when the request is generic and the user has not supplied their own data. Otherwise ask one concise clarification.

## Environment

For this maintainer workspace, always use this Python interpreter:

```text
C:\App\anaconda3\envs\hydrus-agent\python.exe
```

If this repository is copied to another machine, update this path and the
project-local temp paths below to match that machine. Do not use bundled
Python or plain `python` in this workspace.

Rules:

- Do not use bundled Python.
- Do not use plain `python`.
- Do not install dependencies unless explicitly instructed by the user.
- Do not print `.env` contents. It is fine to report whether required variables such as `HYDRUS_EXE` appear to be configured.

## Test Command

Use this command for the full test suite:

```powershell
New-Item -ItemType Directory -Force "D:\Claude\hydrus_1d_agent\.codex_tmp"
$env:TEMP="D:\Claude\hydrus_1d_agent\.codex_tmp"
$env:TMP="D:\Claude\hydrus_1d_agent\.codex_tmp"
C:\App\anaconda3\envs\hydrus-agent\python.exe -m pytest tests/ -v --basetemp "D:\Claude\hydrus_1d_agent\.codex_tmp\pytest_base"
```

## HYDRUS Runs

- Before running HYDRUS, set the executable path for the current shell (or rely on a `.env` file if the user has one):

  ```powershell
  $env:HYDRUS_EXE = "C:\Program Files (x86)\PC-Progress\Hydrus-1D 4.xx\H1D_CALC.EXE"
  ```

- Use `--hydrus-launch-mode argv` unless the user explicitly asks to test another mode.
- Use a timeout for HYDRUS runs.
- Run generated configs only after `--review`.
- Do not bypass the reviewed-config guard unless the user explicitly approves `--allow-config-mismatch` or the workflow is clearly using an existing hand-authored demo config.
- Do not change the core HYDRUS numerical workflow unless the user explicitly asks for a development task that requires it.

## Reliability reporting

**Never treat HYDRUS exit code 0 alone as success.** `H1D_CALC.EXE` can return 0 and still write output files when `Error.msg` reports non-convergence.

After every `--all` run, inspect:

- `runs/<case_id>/pipeline_summary.json`
- `runs/<case_id>/outputs/qc_summary.json`
- `runs/<case_id>/hydrus_project/Error.msg` if present
- `runs/<case_id>/report.md`
- `runs/<case_id>/figures/`

And report to the user:

- `execution_status`
- `hydrus_numerical_status`
- `qc_status`
- `overall_status`
- maximum water-balance error if available
- whether the run is suitable for interpretation (only when `overall_status` is `ok`)

## SWCC and unsupported physics

If the user asks for SWCC point-data fitting, explain that it is not implemented and ask them to supply direct van Genuchten parameters (`theta_r`, `theta_s`, `alpha_1_m`, `n`, `Ks_m_d`, `l`) inline or via a material CSV. Do the same for any other unsupported physics listed under Scope Boundaries.

## Benchmarks

- Treat raw official PC-Progress examples under `benchmarks/pc_progress_raw/` as read-only.
- Do not modify raw official example folders.
- Run official examples only through copied workspaces under `benchmarks/benchmark_results/`.
- Use `--hydrus-launch-mode argv` and the requested timeout for benchmark runs.
- Do not treat unsupported physics examples as whole-agent failures; classify them as documented gaps.

## Scope Boundaries

Do not implement new physics unless the user explicitly requests it. Current
supported generated workflows include simple water flow, atmospheric forcing,
simple root uptake, and one-species conservative solute transport. Current
future-scope features include:

- advanced solute transport generation;
- heat transport generation;
- advanced root uptake and sink terms;
- hysteresis;
- dual porosity or dual permeability;
- scaling-factor workflows;
- GUI or web app development.
