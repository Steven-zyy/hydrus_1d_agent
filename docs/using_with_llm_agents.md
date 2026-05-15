# Using The HYDRUS-1D Agent With Claude, Codex, Or Claude Code

This guide is for users who want Claude Code, Claude Desktop/Cowork, or Codex to operate this local HYDRUS-1D agent on their behalf.

The short version: open this project folder in your LLM coding tool, tell it to read `AGENTS.md`, and ask it to use the exact Python interpreter and safe review-first workflow below.

New to this setup? Start with [getting_started_with_codex_or_claude_code.md](getting_started_with_codex_or_claude_code.md) for a step-by-step walkthrough before reading this reference guide.

Want to use an external LLM to write JSON configs directly? See [llm_assisted_json_configuration.md](llm_assisted_json_configuration.md).

The paths shown in this guide are local prototype examples:
`D:\Claude\hydrus_1d_agent` and
`C:\App\anaconda3\envs\hydrus-agent\python.exe`. Replace them with your own
project folder and Python interpreter path when using another machine.

## What This Agent Can Currently Do

- Build validated JSON configs from simple natural-language water-flow descriptions.
- Review generated configs without running HYDRUS.
- Prepare HYDRUS-1D project files through the existing phydrus adapter.
- Run HYDRUS-1D with `H1D_CALC.EXE`.
- Read common HYDRUS outputs, including generic `Obs_Node.out` tables with extra heat/solute-style columns.
- Generate standard PNG figures.
- Run QC checks and write `qc_summary.json`.
- Write a Markdown report for each run.
- Generate simple atmospheric water-flow cases.
- Generate simple root uptake water-flow cases with atmospheric forcing.
- Generate simple one-species conservative solute transport cases.
- Compare HYDRUS observation-node outputs with measured CSV field data.
- Run small explicit scenario/sensitivity batches.
- Generate scenario comparison reports from existing batch summaries.
- Run official PC-Progress examples through copied benchmark workspaces.
- Summarize benchmark support status.

## What It Cannot Do Yet

- Generate advanced solute transport models with multiple species, adsorption, decay, reaction chains, volatilisation, non-equilibrium transport, heat coupling, or salinity/root stress.
- Generate heat transport models.
- Generate advanced root uptake models, root growth, crop growth, salinity stress, or solute uptake.
- Generate hysteresis models.
- Generate dual porosity or dual permeability models.
- Generate scaling-factor workflows.
- Calibrate, optimise, fit, or automatically improve parameters.
- Expand scenario grids automatically.
- Automatically fix failed HYDRUS inputs.
- Treat unsupported official examples as full agent failures.

The agent can parse some outputs from solute/heat official examples, but parsing output is not the same as generating those physics.

## Open The Project In An LLM Tool

Use one of these workflows:

- Codex desktop or Codex CLI: open `D:\Claude\hydrus_1d_agent` as the workspace.
- Claude Code: start Claude Code from `D:\Claude\hydrus_1d_agent`.
- Claude Desktop/Cowork: attach or open the local project folder `D:\Claude\hydrus_1d_agent` if your setup supports local file access.

Ask the LLM to start by reading:

```text
AGENTS.md
README.md
docs/user_guide.md
docs/demo_workflows.md
docs/benchmark_support_matrix.md
```

## Required Python Interpreter

For this workspace, the LLM must use:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe
```

Tell the LLM:

- Do not use bundled Python.
- Do not use plain `python`.
- Do not install dependencies unless I explicitly ask.
- Use PowerShell commands from `D:\Claude\hydrus_1d_agent`.

## Exact Commands The LLM Should Use

Environment check:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe scripts\check_hydrus_environment.py
```

Generate and review a config without running HYDRUS:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --describe "1 m sandy loam column, 1 day, 1 mm/day infiltration, free drainage lower boundary, initial pressure head -1 m, observations at 0.3 and 0.7 m" --write-config config\from_description.json --review
```

Run the reviewed config:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\from_description.json --all --overwrite-run --timeout 30 --hydrus-launch-mode argv
```

Run an existing demo config:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\simple_runnable_case.json --all --overwrite-run --timeout 30 --hydrus-launch-mode argv --allow-config-mismatch
```

Run the simple root uptake demo:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\simple_root_uptake_case.json --all --overwrite-run --timeout 60 --hydrus-launch-mode argv --allow-config-mismatch
```

Run the simple conservative solute demo:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\simple_conservative_solute_case.json --all --overwrite-run --timeout 60 --hydrus-launch-mode argv --allow-config-mismatch
```

Compare a run with field data:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\simple_runnable_case.json --all --overwrite-run --timeout 30 --hydrus-launch-mode argv --allow-config-mismatch --field-data data\measured_obs_nodes.csv
```

Run a scenario batch:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\simple_runnable_case.json --scenario-file config\scenarios\simple_sensitivity.json --timeout 60 --hydrus-launch-mode argv
```

Generate a scenario comparison report from an existing batch:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --scenario-report runs\simple_sensitivity
```

Read outputs for a run:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\simple_runnable_case.json --read-output
```

Run QC:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\simple_runnable_case.json --qc
```

Write the Markdown report:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\simple_runnable_case.json --report
```

Run the test suite:

```powershell
New-Item -ItemType Directory -Force "D:\Claude\hydrus_1d_agent\.codex_tmp"
$env:TEMP="D:\Claude\hydrus_1d_agent\.codex_tmp"
$env:TMP="D:\Claude\hydrus_1d_agent\.codex_tmp"
C:\App\anaconda3\envs\hydrus-agent\python.exe -m pytest tests/ -v --basetemp "D:\Claude\hydrus_1d_agent\.codex_tmp\pytest_base"
```

## Recommended User Prompts

Use prompts like these:

```text
Read AGENTS.md and docs/user_guide.md. Use the exact Python interpreter from AGENTS.md. Check the HYDRUS environment, then stop and tell me whether it is ready.
```

```text
Generate a HYDRUS config for a 1 m sandy loam column with 1 mm/day infiltration, free drainage, initial pressure head -1 m, and observation depths at 0.3 and 0.7 m. Review it only. Do not run HYDRUS yet.
```

```text
Run the last reviewed config using the one-command pipeline with argv launch mode and timeout 30. After it finishes, summarize the report, QC result, figures generated, and any warnings.
```

```text
Compare the completed simple runnable case with measured CSV field data at data/measured_obs_nodes.csv. Use --field-data, do not calibrate or change model parameters, and summarize RMSE, MAE, bias, correlation, overlay figures, QC status, and report path.
```

```text
Run the scenario batch in config/scenarios/simple_sensitivity.json using config/simple_runnable_case.json. Use argv launch mode and timeout 60. Do not add calibration, optimisation, or automatic parameter fitting. After it finishes, summarize scenario_summary.csv and scenario_summary.json.
```

```text
Generate a scenario comparison report from runs/simple_sensitivity. Do not rerun HYDRUS. Summarize the best field-data RMSE if available, largest infiltration, largest bottom flux, warnings, failed scenarios, report path, and generated comparison figures.
```

```text
Run the simple atmospheric rainfall demo from config/simple_atmospheric_case.json. Do not add root uptake, solute, or heat. Use --allow-config-mismatch if needed because this is an existing hand-authored config.
```

```text
Generate and review a simple atmospheric root uptake config: 1 m sandy loam column, 1 day, rainfall 1 mm/day, evaporation 0, root depth 0.5 m, potential transpiration 1 mm/day, uniform root distribution, free drainage, initial pressure head -1 m, observations at 0.25 and 0.75 m. Do not run HYDRUS yet.
```

```text
Run the official benchmark 1DRAINAG through the benchmark harness only. Do not modify raw files under benchmarks/pc_progress_raw.
```

## Safe Two-Step Workflow

The safest workflow is:

1. Generate and review.
2. Run only after the user approves the reviewed config.

Step 1:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --describe "your model description here" --write-config config\from_description.json --review
```

The LLM should summarize:

- case ID;
- simulation time;
- soil layers;
- van Genuchten parameters;
- initial condition;
- upper and lower boundaries;
- observation depths;
- assumptions and limitations.

Step 2:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\from_description.json --all --overwrite-run --timeout 30 --hydrus-launch-mode argv
```

The LLM should then summarize:

- pipeline success or failure;
- HYDRUS return status;
- QC status;
- figure count;
- report path;
- warnings or unsupported features.

## Reviewed-Config Guard

When a generated config is reviewed, the agent writes:

```text
.hydrus_agent_state\last_review.json
```

That state records the reviewed config path and file hash. Before `--all` runs, the CLI checks that the requested config is the same reviewed file with the same content.

This prevents an LLM from accidentally reviewing one config and running another.

If the guard blocks a run, the LLM should not bypass it automatically. It should show the mismatch to the user and ask whether to:

- run the reviewed config;
- review the requested config first;
- or intentionally use `--allow-config-mismatch`.

Use `--allow-config-mismatch` for existing demo configs or deliberate manual workflows, not for accidental mismatches.

## Where To Find Outputs

For a case ID such as `case_002`, outputs are under:

```text
runs\case_002\
```

Key files:

```text
runs\case_002\pipeline_summary.json
runs\case_002\report.md
runs\case_002\outputs\qc_summary.json
runs\case_002\outputs\field_comparison_summary.json
runs\case_002\logs\hydrus_run.log
runs\case_002\figures\
runs\case_002\hydrus_project\
```

Ask the LLM to summarize `report.md`, `qc_summary.json`, and `pipeline_summary.json` instead of pasting long raw HYDRUS output.

Scenario batch outputs are under:

```text
runs\<batch_id>\scenario_summary.csv
runs\<batch_id>\scenario_summary.json
runs\<batch_id>\scenario_report.md
runs\<batch_id>\figures\
```

## Benchmark Examples

Raw official examples belong under:

```text
benchmarks\pc_progress_raw\Direct\
```

The LLM must not modify raw examples. It should use the benchmark harness, which copies each case to:

```text
benchmarks\benchmark_results\<benchmark_id>\hydrus_project\
```

Run one official benchmark:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --benchmark-official benchmarks\pc_progress_raw\Direct\1DRAINAG --benchmark-id 1DRAINAG --timeout 60 --hydrus-launch-mode argv
```

Run currently supported manifest cases:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --benchmark-manifest benchmarks\manifest.csv --timeout 60 --hydrus-launch-mode argv
```

Open the support matrix:

```text
docs\benchmark_support_matrix.md
```

## Safety Rules For LLM Agents

Tell the LLM to follow these rules:

- Read `AGENTS.md` before running commands.
- Use `C:\App\anaconda3\envs\hydrus-agent\python.exe`.
- Do not use plain `python`.
- Do not install packages unless explicitly asked.
- Do not print `.env` contents; only report whether required settings appear to be configured.
- Do not edit raw official examples under `benchmarks\pc_progress_raw\`.
- Only run benchmarks through `--benchmark-official` or `--benchmark-manifest`.
- Prefer `--hydrus-launch-mode argv`.
- Use a timeout for HYDRUS runs.
- Generate and review configs before running them.
- Do not bypass the reviewed-config guard without user approval.
- Do not calibrate, optimise, fit, or automatically improve parameters unless the user requests a future development milestone for that feature.
- Do not implement new physics unless the user explicitly asks for a development milestone.
- Do not treat unsupported solute, heat, advanced root uptake, hysteresis, dual porosity, or scaling examples as whole-agent failures.
- Report paths to outputs, figures, QC summaries, and reports.
- Run the AGENTS test command after documentation or code changes when requested.

## Copy-and-paste prompt for Claude/Codex

```text
You are working in D:\Claude\hydrus_1d_agent.

First read AGENTS.md, README.md, docs/user_guide.md, docs/demo_workflows.md, docs/benchmark_support_matrix.md, and docs/using_with_llm_agents.md.

Follow these rules:
- Use C:\App\anaconda3\envs\hydrus-agent\python.exe for every Python command.
- Do not use bundled Python or plain python.
- Do not install dependencies unless I explicitly ask.
- Do not modify raw official PC-Progress examples under benchmarks\pc_progress_raw\.
- Use --hydrus-launch-mode argv and a timeout for HYDRUS runs.
- Use the safe two-step workflow: generate/review a config first, summarize it for me, and wait for approval before running HYDRUS.
- Respect the reviewed-config guard. Do not use --allow-config-mismatch unless I explicitly approve it or we are running an existing demo config.
- Current generation support includes simple water flow, atmospheric forcing, simple root uptake, and one-species conservative solute transport.
- Field-data comparison and scenario reports are post-processing only. Do not calibrate, optimise, fit, or automatically improve parameters.
- Do not implement new physics beyond the current supported scope. Advanced solute chemistry, heat, advanced root uptake, hysteresis, dual porosity, and scaling are future scope unless I explicitly request a development milestone.

Start by running the environment check:
C:\App\anaconda3\envs\hydrus-agent\python.exe scripts\check_hydrus_environment.py

Then help me create and review a simple HYDRUS-1D water-flow case from this description:
[paste my case description here]

After review, summarize the case ID, soil profile, parameters, initial condition, boundaries, observation depths, assumptions, and exact run command. Do not run HYDRUS until I approve.
```
