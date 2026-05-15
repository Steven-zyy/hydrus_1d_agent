# User Acceptance Tests

These manual tests verify that a non-developer can use the HYDRUS-1D agent through Claude/Codex without touching internal code.

Run commands from:

```powershell
cd D:\Claude\hydrus_1d_agent
```

Use this Python interpreter:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe
```

Before running acceptance tests, check the environment:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe scripts\check_hydrus_environment.py
```

Acceptance tests that launch HYDRUS require `HYDRUS_EXE` to point to `H1D_CALC.EXE`.

Paths inside the project are shown as project-relative paths. Absolute Windows paths appear only for this local workspace and the required Python interpreter.

## UAT-01: Generate And Review Config Only

Purpose: confirm an LLM can create a config from a natural-language request without running HYDRUS.

Command:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --describe "1 m sandy loam column, 1 day, 1 mm/day infiltration, free drainage lower boundary, initial pressure head -1 m, observations at 0.25 and 0.75 m" --write-config config\acceptance_simple_infiltration.json --review
```

Expected outputs:

| Item | Expected |
|---|---|
| Config path | `config\acceptance_simple_infiltration.json` |
| Run folder | Not created by this command |
| Report path | Not created |
| Figure count | 0 |
| QC status | Not run |
| CLI result | Review summary shows a valid `ModelConfig` |

Pass criteria:

- The config file is written.
- HYDRUS is not launched.
- The LLM summarizes assumptions and asks for approval before running.

## UAT-02: Run Reviewed Config

Purpose: confirm the reviewed-config guard allows the same reviewed config to run.

Prerequisite: UAT-01 completed without editing the generated config after review.

Command:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\acceptance_simple_infiltration.json --all --overwrite-run --timeout 30 --hydrus-launch-mode argv
```

Expected outputs:

| Item | Expected |
|---|---|
| Config path | `config\acceptance_simple_infiltration.json` |
| Run folder | `runs\<generated_case_id>\` |
| Report path | `runs\<generated_case_id>\report.md` |
| Figure count | Usually 9 standard figures for a complete simple water-flow run |
| QC status | Expected pass for the simple case; warnings should be explained if present |
| CLI result | Pipeline completes and writes `pipeline_summary.json` |

Pass criteria:

- HYDRUS launches with `argv` mode.
- `pipeline_summary.json`, `report.md`, `outputs\qc_summary.json`, and `figures\` are created.
- The LLM reports paths instead of pasting long raw output.

## UAT-03: Reject Wrong Config Mismatch

Purpose: confirm the guard blocks an accidental switch from a reviewed config to a different config.

Prerequisite: UAT-01 completed, so `.hydrus_agent_state\last_review.json` points at `config\acceptance_simple_infiltration.json`.

Command:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\simple_runnable_case.json --all --overwrite-run --timeout 30 --hydrus-launch-mode argv
```

Expected outputs:

| Item | Expected |
|---|---|
| Config path | `config\simple_runnable_case.json` requested, but blocked |
| Run folder | No new run should be started by this blocked command |
| Report path | Not created by this command |
| Figure count | 0 from this blocked command |
| QC status | Not run |
| CLI result | Error explaining that the requested config is not the last reviewed config |

Pass criteria:

- HYDRUS is not launched.
- The LLM does not automatically add `--allow-config-mismatch`.
- The LLM explains the mismatch and asks whether to review the requested config or intentionally bypass the guard.

## UAT-04: Run Full Pipeline From Existing Config

Purpose: confirm a known hand-authored demo config can run end to end.

Command:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\simple_runnable_case.json --all --overwrite-run --timeout 30 --hydrus-launch-mode argv --allow-config-mismatch
```

Expected outputs:

| Item | Expected |
|---|---|
| Config path | `config\simple_runnable_case.json` |
| Run folder | `runs\case_002\` |
| Report path | `runs\case_002\report.md` |
| Figure count | Usually 9 standard figures |
| QC status | Expected pass for the simple runnable case |
| CLI result | Pipeline completes and writes `runs\case_002\pipeline_summary.json` |

Pass criteria:

- The run uses `--hydrus-launch-mode argv`.
- `runs\case_002\hydrus_project\` contains HYDRUS inputs and outputs.
- The LLM summarizes QC, report path, and figure count.

## UAT-05: Run One Official Benchmark

Purpose: confirm the LLM can run a copied official example without modifying raw files.

Prerequisite: official examples are present under `benchmarks\pc_progress_raw\Direct\`.

Command:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --benchmark-official benchmarks\pc_progress_raw\Direct\1DRAINAG --benchmark-id 1DRAINAG --timeout 60 --hydrus-launch-mode argv
```

Expected outputs:

| Item | Expected |
|---|---|
| Source folder | `benchmarks\pc_progress_raw\Direct\1DRAINAG` |
| Copied workspace | `benchmarks\benchmark_results\1DRAINAG\hydrus_project\` |
| Summary path | `benchmarks\benchmark_results\1DRAINAG\benchmark_summary.json` |
| Figure count | Usually 9 standard figures for this supported water-flow example |
| QC status | Expected pass |
| CLI result | Benchmark summary records HYDRUS success and parsed outputs |

Pass criteria:

- Raw files under `benchmarks\pc_progress_raw\` are not modified.
- The benchmark runs from the copied workspace.
- The LLM reports HYDRUS status, parsed output count, QC status, figure count, and summary path.

## UAT-06: Inspect Report And Figures

Purpose: confirm an LLM can explain outputs in user-facing language after a run.

Prerequisite: UAT-04 completed.

Files to inspect:

```text
runs\case_002\report.md
runs\case_002\outputs\qc_summary.json
runs\case_002\pipeline_summary.json
runs\case_002\figures\
```

Expected outputs:

| Item | Expected |
|---|---|
| Run folder | `runs\case_002\` |
| Report path | `runs\case_002\report.md` |
| Figure count | Usually 9 standard figures |
| QC status | Expected pass for the simple runnable case |
| CLI result | No HYDRUS rerun required |

Pass criteria:

- The LLM summarizes the report and QC result without rerunning HYDRUS.
- The LLM identifies figure files and explains what they show.
- Any QC warnings are stated plainly with recommended next actions.

## Acceptance Checklist

Use this checklist after all tests:

- Config generation worked without running HYDRUS.
- The reviewed config ran successfully after approval.
- The mismatch guard blocked an unreviewed config.
- An existing config ran with explicit `--allow-config-mismatch`.
- One official benchmark ran from a copied workspace.
- Report, QC summary, and figures were easy to locate and explain.
- No raw official examples were modified.
- No generated run folders or benchmark result folders are committed.
