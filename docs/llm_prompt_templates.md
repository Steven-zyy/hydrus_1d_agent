# LLM Prompt Templates

Use these prompts with Claude Code, Claude Desktop/Cowork, Codex, or another local LLM coding tool that can work inside this project folder.

All prompts assume the project is open at:

```text
D:\Claude\hydrus_1d_agent
```

The LLM must use:

```text
C:\App\anaconda3\envs\hydrus-agent\python.exe
```

Paths inside the project are shown as project-relative paths. Absolute Windows paths appear only for this local workspace and the required Python interpreter.

## Simple Infiltration Case

```text
You are working in D:\Claude\hydrus_1d_agent.

Read AGENTS.md, README.md, docs/user_guide.md, and docs/demo_workflows.md first.

Use C:\App\anaconda3\envs\hydrus-agent\python.exe for every Python command. Do not use bundled Python or plain python. Do not install dependencies.

Create and review a HYDRUS-1D config only. Do not run HYDRUS yet.

Case description:
1 m sandy loam column, 1 day simulation, 1 mm/day infiltration at the top, free drainage lower boundary, initial pressure head -1 m, observation depths at 0.25 m and 0.75 m.

Write the config to config\acceptance_simple_infiltration.json and run review mode. Then summarize the case ID, soil profile, initial condition, upper and lower boundaries, observation depths, assumptions, and the exact command I should approve if I want to run it.
```

Expected reviewed config path:

```text
config\acceptance_simple_infiltration.json
```

## Two-Layer Ponding Case

```text
You are working in D:\Claude\hydrus_1d_agent.

Read AGENTS.md and docs/demo_workflows.md first.

Use C:\App\anaconda3\envs\hydrus-agent\python.exe. Use the safe two-step workflow: generate/review first, then wait for approval before running.

Create and review a HYDRUS-1D config only. Do not run HYDRUS yet.

Case description:
2 m column with 0-1 m clay over 1-2 m sand, 10 day simulation, ponded constant head 1 m at the surface, free drainage lower boundary, initial pressure head profile from -1 m at the surface to 1 m at 2 m depth, observation depths at 0.3 m and 1.7 m.

Write the config to config\acceptance_two_layer_ponding.json and review it. Summarize the generated config and tell me the exact run command, but do not run it yet.
```

Expected reviewed config path:

```text
config\acceptance_two_layer_ponding.json
```

## Simple Atmospheric Rainfall Case

```text
You are working in D:\Claude\hydrus_1d_agent.

Read AGENTS.md, README.md, and docs/demo_workflows.md first.

Use C:\App\anaconda3\envs\hydrus-agent\python.exe. Do not implement root uptake, solute transport, heat transport, hysteresis, or dual porosity.

Create and review a simple atmospheric water-flow config only. Do not run HYDRUS yet.

Case description:
1 m sandy loam column, 1 day simulation, atmospheric upper boundary with rainfall 1 mm/day, potential evaporation 0, hCritA -10000, free drainage lower boundary, initial pressure head -1 m, observation depths at 0.25 m and 0.75 m.

Write the config to config\acceptance_atmospheric_rainfall.json and review it. Confirm that this is water-flow only and that ATMOSPH.IN will be generated only if I approve the run.
```

Expected reviewed config path:

```text
config\acceptance_atmospheric_rainfall.json
```

## Benchmark Official Example

```text
You are working in D:\Claude\hydrus_1d_agent.

Read AGENTS.md and docs/benchmark_support_matrix.md first.

Use C:\App\anaconda3\envs\hydrus-agent\python.exe. Use --hydrus-launch-mode argv and timeout 60. Do not modify raw official examples under benchmarks\pc_progress_raw\.

Run only this official benchmark through the benchmark harness:
benchmarks\pc_progress_raw\Direct\1DRAINAG

Use benchmark ID 1DRAINAG. After the run, summarize the copied benchmark workspace, HYDRUS status, parsed output count, QC status, figure count, failure classification if any, and benchmark_summary.json path.
```

Expected benchmark summary path:

```text
benchmarks\benchmark_results\1DRAINAG\benchmark_summary.json
```

## Explain Report And QC Result

```text
You are working in D:\Claude\hydrus_1d_agent.

Read AGENTS.md first.

Use C:\App\anaconda3\envs\hydrus-agent\python.exe only if you need to run a read-only command. Do not rerun HYDRUS unless I explicitly ask.

Please inspect and explain this completed run:
runs\case_002\

Summarize:
- whether the pipeline completed;
- HYDRUS return status;
- QC pass/warning status;
- water-balance result;
- cumulative infiltration and bottom flux if available;
- observation-node behavior;
- figure files generated;
- any warnings and whether they affect trust in the result.

Use report.md, outputs\qc_summary.json, pipeline_summary.json, and figures\. Do not paste long raw HYDRUS logs unless needed.
```

Expected files to inspect:

```text
runs\case_002\report.md
runs\case_002\outputs\qc_summary.json
runs\case_002\pipeline_summary.json
runs\case_002\figures\
```
