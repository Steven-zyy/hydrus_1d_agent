# Getting Started with Codex or Claude Code

This guide walks a new user through setting up and running the HYDRUS-1D agent with help from an LLM coding assistant such as Codex or Claude Code.

The LLM assistant helps you write commands, review configuration files, check outputs, and interpret results. The actual HYDRUS simulation must run on your local Windows machine with HYDRUS-1D installed.

## Who This Guide Is For

- Users who have PC-Progress HYDRUS-1D installed on a Windows machine.
- Users who want to use Codex or Claude Code to help set up, run, and check HYDRUS-1D simulations.
- Users who are new to the HYDRUS-1D agent and want a clear starting point.

If you do not have HYDRUS-1D installed, install it from PC-Progress before continuing.

## Important Platform Note

Before starting, read this carefully:

- **Full HYDRUS execution requires Windows.** `H1D_CALC.EXE` is a Windows PE executable.
- **HYDRUS-1D must be installed locally.** It is not included in this repository.
- **`HYDRUS_EXE` must point to `H1D_CALC.EXE`.** The agent will not run HYDRUS without it.
- **Linux, macOS, WSL, and remote cloud sandboxes generally cannot execute `H1D_CALC.EXE`.** If your coding assistant is running in a remote or cloud environment (for example, a cloud-hosted Codex session or a Claude Cowork session without local file access), it can help you prepare commands and interpret results, but it cannot launch HYDRUS for you.
- **The Python agent code can run on any platform.** Only the HYDRUS execution step requires Windows.

If you are unsure whether your coding assistant has access to your local Windows environment, use the environment check prompt in Step 3 before doing anything else.

## Workflow Overview

```
User + Codex/Claude Code
    ↓
Check local Windows environment
    ↓
Install Python dependencies
    ↓
Set HYDRUS_EXE
    ↓
Review model config
    ↓
Run HYDRUS locally
    ↓
Inspect pipeline_summary.json, qc_summary.json, report.md, and figures
```

---

## Step 1: Clone the Repository

Open PowerShell and run:

```powershell
git clone https://github.com/Steven-zyy/hydrus_1d_agent.git
cd hydrus_1d_agent
```

If you downloaded a ZIP instead, extract it and open a PowerShell terminal in the project folder.

All subsequent commands in this guide should be run from the project root (`hydrus_1d_agent\`).

---

## Step 2: Open the Project in Codex or Claude Code

Open the project folder in your preferred LLM coding tool:

- **Claude Code** — open a session pointing to the `hydrus_1d_agent` folder.
- **Codex CLI** — run `codex` in the project folder.
- **Codex IDE extension** — open the folder in VS Code with the Codex extension active.

Tell the assistant to read `AGENTS.md` first. That file describes the safe workflow and the constraints the agent should follow.

---

## Step 3: Ask the Coding Assistant to Verify the Environment

Paste this prompt into your coding assistant before running anything:

> Before running the HYDRUS-1D agent, check whether you are using my local Windows environment or a remote/cloud/Linux sandbox.
>
> Do not edit source code.
>
> Please run and report:
>
> ```powershell
> pwd
> whoami
> $PSVersionTable.PSVersion
> Test-Path 'D:\Claude\hydrus_1d_agent'
> Test-Path 'C:\App\anaconda3\envs\hydrus-agent\python.exe'
> Test-Path 'C:\Program Files (x86)\PC-Progress\Hydrus-1D 4.xx\H1D_CALC.EXE'
> ```
>
> If these PowerShell commands are unavailable, or if the paths return False, stop and tell me this is not a usable local Windows environment for full HYDRUS execution.

**Replace the paths with your own** before pasting:

- `D:\Claude\hydrus_1d_agent` → your project folder.
- `C:\App\anaconda3\envs\hydrus-agent\python.exe` → your conda environment Python.
- `C:\Program Files (x86)\PC-Progress\Hydrus-1D 4.xx\H1D_CALC.EXE` → your HYDRUS executable.

If the assistant reports that it is in a Linux/cloud sandbox or that the paths return `False`, do not proceed with HYDRUS execution. You can still use the assistant to review configs and prepare commands, but you will need to run them yourself in a local PowerShell session.

**Tip:** Once setup is verified, you do not need to paste long prompts for everyday work. See [docs/simple_user_prompts.md](simple_user_prompts.md) for short modelling prompts that the assistant can translate into JSON configs and run through the review-before-run workflow.

---

## Step 4: Install Dependencies

Use the full path to your conda environment Python. Do not use plain `python` — on Windows it often resolves to the Microsoft Store stub or the wrong environment.

Install runtime dependencies:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe -m pip install -r requirements.txt
```

If you also want to run the automated test suite:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe -m pip install -r requirements-dev.txt
```

Replace `C:\App\anaconda3\envs\hydrus-agent\python.exe` with the full path to your Python interpreter.

---

## Step 5: Set HYDRUS_EXE

The agent reads `HYDRUS_EXE` from the environment to find `H1D_CALC.EXE`. Set it for the current terminal session:

```powershell
$env:HYDRUS_EXE = "C:\Program Files (x86)\PC-Progress\Hydrus-1D 4.xx\H1D_CALC.EXE"
```

Verify the path exists:

```powershell
Test-Path $env:HYDRUS_EXE
```

This should return `True`. If it returns `False`, check your HYDRUS-1D installation path and update the value.

This setting applies only to the current terminal session. For a persistent setup, add the same line to a `.env` file in the project root (see the user guide for details). Do not commit the `.env` file.

---

## Step 6: Run the Environment Check

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe scripts\check_hydrus_environment.py
```

Common outcomes:

| Result | What to do |
|---|---|
| `[OK] HYDRUS executable exists` | Continue to Step 7. |
| `HYDRUS_EXE not set` | Run Step 5 first. |
| Import error for `phydrus` or other packages | Run Step 4 first. |
| `HYDRUS_EXE` set but path does not exist | Fix the path or reinstall HYDRUS-1D. |

---

## Step 7: Run a Review-Only Demo

Before running HYDRUS, review the stable demo config to confirm the agent loads the CSV inputs correctly. This does not run HYDRUS.

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\new_user_dynamic_csv_test.json --review
```

The review summary should show:

- `Validation status: valid ModelConfig`
- Atmospheric CSV: path, record count, time range 0–30 days, coverage confirmed
- Material CSV: path, two materials (sandy\_loam, sand), van Genuchten parameters
- Simulation window: 0.0 to 30.0 days
- Observation depths: 0.2, 0.6, 1.2, 1.8 m
- Upper boundary: atmospheric / Lower boundary: free drainage

If validation fails, the message will explain which field or file is the problem.

---

## Step 8: Run the Stable HYDRUS Demo

After a clean review, run the full pipeline:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\new_user_dynamic_csv_test.json --all --overwrite-run --timeout 60 --hydrus-launch-mode argv
```

The pipeline runs eight steps: validate config, create run folder, prepare inputs, run HYDRUS, read outputs, generate figures, run QC, and write a report.

Expected output files:

```text
runs\new_user_dynamic_csv_test\pipeline_summary.json
runs\new_user_dynamic_csv_test\outputs\qc_summary.json
runs\new_user_dynamic_csv_test\report.md
runs\new_user_dynamic_csv_test\figures\
runs\new_user_dynamic_csv_test\hydrus_project\
runs\new_user_dynamic_csv_test\logs\hydrus_run.log
```

A clean successful run prints `Pipeline succeeded` and reports all steps as `[OK]`.

---

## Step 9: Ask the Assistant to Interpret the Outputs

Paste this prompt into your coding assistant after the run completes:

> Please inspect the HYDRUS agent run results without editing source code.
>
> Read:
>
> ```text
> runs\new_user_dynamic_csv_test\pipeline_summary.json
> runs\new_user_dynamic_csv_test\outputs\qc_summary.json
> runs\new_user_dynamic_csv_test\report.md
> ```
>
> Report:
>
> 1. `execution_status`
> 2. `hydrus_numerical_status`
> 3. `qc_status`
> 4. `overall_status`
> 5. Whether `qc_summary.json` reports `ok: true`
> 6. Maximum water-balance error
> 7. Whether `Error.msg` contains any numerical failure message
> 8. Whether expected figures were generated
> 9. Whether the report includes any reliability warning
> 10. Whether the run is suitable for interpretation

The assistant will read the JSON files and the report, then summarise the key reliability indicators for you.

---

## Step 10: Use Natural-Language Model Setup

Once the demo run works, you can describe your own model in plain language. The agent parses the description and generates a validated JSON config.

Use the stable stable CSV inputs as a starting point:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --describe "Build a 30-day HYDRUS-1D model for a 2 m vertical soil column with sandy loam from 0 to 1 m and sand from 1 to 2 m. Use atmospheric upper boundary forcing from test_inputs\new_user_dynamic_test\atmosphere_stable_30d.csv, use material hydraulic parameters from test_inputs\new_user_dynamic_test\materials_vg_stable.csv, use free drainage at the bottom, initial pressure head -1.0 m throughout the profile, observation depths 0.2, 0.6, 1.2, and 1.8 m, and print times 1, 3, 5, 7, 10, 14, 20, 25, and 30 days." --write-config config\my_first_dynamic_case.json --review
```

Check the review summary carefully. When it looks correct, run the reviewed config:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\my_first_dynamic_case.json --all --overwrite-run --timeout 60 --hydrus-launch-mode argv
```

To use your own CSV inputs, replace the file paths in the description with paths to your own atmospheric forcing and material parameter CSVs. See [docs/user_guide.md](user_guide.md) for the required column names and units.

---

## Troubleshooting

**Coding assistant is in a Linux or cloud sandbox**

The assistant cannot reach Windows paths or launch `H1D_CALC.EXE`. Use the assistant to prepare commands and review outputs, but run HYDRUS commands yourself in a local PowerShell session.

---

**`python` opens the Microsoft Store or is not found**

The `python` alias on Windows often resolves to a stub. Use the full path to your conda environment:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe
```

---

**`HYDRUS_EXE` is not set**

```powershell
$env:HYDRUS_EXE = "C:\Program Files (x86)\PC-Progress\Hydrus-1D 4.xx\H1D_CALC.EXE"
```

---

**HYDRUS returns code 0 but the run shows a failure**

`H1D_CALC.EXE` can return exit code 0 even when the numerical solution stopped early due to non-convergence. The agent checks `Error.msg` and QC outputs separately from the exit code. If `hydrus_numerical_status` is `failed` or `qc_status` is `failed`, treat the run as incomplete:

1. Open `runs\<case_id>\pipeline_summary.json` and check `hydrus_numerical_status`.
2. Open `runs\<case_id>\outputs\qc_summary.json` and check `ok` and `warnings`.
3. Open `runs\<case_id>\report.md` and read the interpretation section.
4. Reduce rainfall intensity, check hydraulic parameters, or adjust the initial condition.

---

**SWCC point-data CSV does not work**

SWCC curve fitting is not implemented. The material CSV must contain direct van Genuchten parameters (`theta_r`, `theta_s`, `alpha_1_m`, `n`, `Ks_m_d`, `l`). Derive the parameters outside the agent and supply them directly.

---

**Config mismatch error when running after review**

The agent records the reviewed config and blocks running a different one. Either re-run `--review` on the config you want to run, or use `--allow-config-mismatch` if you intentionally changed the config after review and understand the implications.

---

## Safety and Reliability Notes

- **Do not interpret HYDRUS exit code 0 alone as success.** The agent separates process execution, numerical convergence, and QC status.
- **Always check `pipeline_summary.json`** for `execution_status`, `hydrus_numerical_status`, and `overall_status`.
- **Always check `qc_summary.json`** for `ok` and any warnings about water balance errors or missing outputs.
- **Always check `report.md`** for the interpretation section and any reliability warnings.
- **Treat reliability warnings as requiring model review** before using results.
- **The agent automates and checks HYDRUS workflows but does not replace hydrogeological judgement.** Review simulation setup, boundary conditions, and outputs yourself before drawing conclusions.

---

## Next Steps

- [User guide](user_guide.md): full command reference, atmospheric forcing, material CSV format, field comparison, and scenario batches.
- [Demo workflows](demo_workflows.md): worked examples including simple infiltration, two-layer ponding, and atmospheric rainfall.
- [Simple user prompts](simple_user_prompts.md): short everyday modelling prompts for Codex / Claude Code.
- [Using with LLM agents](using_with_llm_agents.md): safe prompts and constraints for operating the agent through Claude or Codex.
- [LLM-assisted JSON configuration](llm_assisted_json_configuration.md): how to use an external LLM to write JSON configs and validate them locally.
- [Release notes](../RELEASE_NOTES.md): what changed in each version.
