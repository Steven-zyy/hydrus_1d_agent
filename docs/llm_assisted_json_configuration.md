# LLM-Assisted JSON Configuration Mode

This guide explains how to use an external LLM (Claude, Codex, GPT-4, or any other) to write HYDRUS-1D agent configuration files in JSON, and then validate and run them locally.

**No LLM API is called by the agent.** The LLM runs externally in your browser, IDE, or coding assistant. It writes a JSON file; the agent validates and runs it.

**Platform reminder.** Full HYDRUS execution requires Windows with PC-Progress HYDRUS-1D installed locally. The Python helpers, JSON template generation (`--write-config-template`), schema printing (`--print-config-schema`), and review-only workflows (`--review`) can be used without running HYDRUS, but `--all` and any real HYDRUS execution requires access to `H1D_CALC.EXE`.

This document is the **technical reference** for the JSON config workflow. If you just want to give the assistant a short modelling request and let it do the rest, read [simple_user_prompts.md](simple_user_prompts.md) instead.

New to the agent? Read [getting_started_with_codex_or_claude_code.md](getting_started_with_codex_or_claude_code.md) first.

---

## When to Use This Mode

| Mode | Best for |
|---|---|
| `--describe "..."` | Simple descriptions in plain English; agent parses them with a rule-based builder |
| LLM-assisted JSON | Custom or complex configs where the LLM writes JSON directly; you review before running |

Use `--describe` when a short sentence captures your model. Use LLM-assisted JSON when you want precise control over every field — for example, specifying exact van Genuchten parameters, multiple soil layers, or non-standard print times.

---

## Workflow

```
LLM writes config JSON
        ↓
You save it to  config/<name>.json
        ↓
python main.py --config config/<name>.json --review
        ↓
You read the review summary, approve it
        ↓
python main.py --config config/<name>.json --all --overwrite-run --timeout 60 --hydrus-launch-mode argv
        ↓
Inspect pipeline_summary.json, qc_summary.json, report.md
```

---

## Step 1: Get the Canonical Template

The agent ships a ready-to-run template that validates cleanly with stable CSV inputs. Use it as your starting point.

Print the template to the terminal:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --write-config-template
```

Write the template directly to a config file:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --write-config-template config\my_model.json
```

The template points to the stable demo CSV files that ship with the agent:

- `test_inputs/new_user_dynamic_test/atmosphere_stable_30d.csv` — 30-day atmospheric forcing
- `test_inputs/new_user_dynamic_test/materials_vg_stable.csv` — sandy loam and sand van Genuchten parameters

Both CSV paths are relative to the project root, so the template works on any machine where the project folder is intact.

---

## Step 2: Get the JSON Schema (Optional)

To help an LLM understand every field precisely, print the Pydantic JSON schema for `ModelConfig`:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --print-config-schema
```

Write the schema to a file instead:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --print-config-schema --schema-output docs\model_config_schema.json
```

You can paste this schema into an LLM prompt to get precise, schema-aware config generation.

---

## Step 3: Give the LLM a Prompt

Paste the following prompt into your LLM (Claude, Codex, GPT-4, etc.). Replace the `[DESCRIPTION]` placeholder with your model description.

```text
You are helping set up a HYDRUS-1D agent configuration file in JSON.

I will give you a model description, and you will produce a valid JSON config that matches
the ModelConfig schema below. Do not call any APIs. Write JSON only.

Rules:
- "case_id" must match the regex ^[A-Za-z0-9_\-]+$ (letters, digits, underscores, hyphens).
- "simulation_time.units" must be one of: "seconds", "minutes", "hours", "days".
- "soil_profile" layers must be contiguous (each depth_top equals the previous depth_bottom).
- Every "material" name in soil_profile must match a row in the material CSV if source_csv is used.
- "observation_depths" must lie within the soil profile depth range.
- "print_times" must be strictly increasing and within [t_init, t_end].
- "upper_boundary.type" must be "atmospheric" when an atmospheric CSV is supplied.
- "lower_boundary.type" must be one of: "free_drainage", "constant_head", "constant_flux", "seepage_face".
- "initial_condition.type" must be one of: "pressure_head", "water_content".
- For atmospheric forcing, set "atmospheric.source_csv" to the CSV path and
  "atmospheric.enabled" to true.
- For material parameters, set "van_genuchten.source_csv" to the CSV path.
  Use relative paths from the project root (e.g., "test_inputs/.../file.csv").
- Use null for unused optional fields (root_uptake, solute_transport).

Here is the canonical template to start from:

[PASTE OUTPUT OF: python main.py --write-config-template]

Here is the JSON schema for ModelConfig:

[PASTE OUTPUT OF: python main.py --print-config-schema]

My model description:

[DESCRIPTION]

Produce only the JSON config. Do not add explanatory text, markdown fences, or comments.
```

---

## Step 4: Save and Review the Config

Save the LLM output to a JSON file in the `config/` folder:

```text
config\my_model.json
```

Review it without running HYDRUS:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\my_model.json --review
```

The review prints:

- Validation status (valid or error details)
- Simulation window and time units
- Soil layers and material parameters
- Upper and lower boundary types
- Initial condition
- Observation depths
- Atmospheric CSV metadata (if applicable): path, record count, time range, total precipitation
- Material CSV metadata (if applicable): path, material names, van Genuchten parameters
- Warnings about unsupported features

Read the review summary carefully. If validation fails, the error message will tell you which field is wrong.

---

## Step 5: Run the Validated Config

After the review looks correct:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\my_model.json --all --overwrite-run --timeout 60 --hydrus-launch-mode argv
```

The `--all` flag runs the full eight-step pipeline: validate, create run folder, prepare inputs, run HYDRUS, read outputs, generate figures, run QC, and write a report.

Check outputs in `runs\<case_id>\`:

```text
runs\<case_id>\pipeline_summary.json    ← execution_status, hydrus_numerical_status, overall_status
runs\<case_id>\outputs\qc_summary.json  ← ok, warnings, water-balance error
runs\<case_id>\report.md               ← full run report with reliability notes
runs\<case_id>\figures\                ← PNG figures
```

### Reliability status fields

`pipeline_summary.json` carries four independent status fields. Inspect all four — **HYDRUS exit code 0 alone is not enough to confirm numerical success.** `H1D_CALC.EXE` can return exit code 0 and still write output files when `Error.msg` reports non-convergence.

| Field | Meaning | Source |
|---|---|---|
| `execution_status` | Did the `H1D_CALC.EXE` process complete without timeout or process error? | Runner exit code and timeout marker |
| `hydrus_numerical_status` | Did HYDRUS report numerical convergence? | Parsing `Error.msg` |
| `qc_status` | Did post-run QC checks (water balance, expected outputs) pass? | `qc_summary.json` |
| `overall_status` | Combined reliability: `ok`, `failed`, or `incomplete` | Aggregated from the three above |

A run is suitable for interpretation only when `overall_status` is `ok`. If any of the three component statuses is `failed`, treat outputs as incomplete and consult the report for guidance.

---

## Concrete Example: 30-Day Two-Layer Sandy Loam Over Sand

### User description

> Build a 30-day HYDRUS-1D model for a 2 m vertical soil column with sandy loam from
> 0 to 1 m and sand from 1 to 2 m. Use atmospheric upper boundary forcing from
> `test_inputs/new_user_dynamic_test/atmosphere_stable_30d.csv`, use material hydraulic
> parameters from `test_inputs/new_user_dynamic_test/materials_vg_stable.csv`. Use
> free drainage at the bottom, initial pressure head -1.0 m throughout the profile,
> observation depths 0.2, 0.6, 1.2, and 1.8 m, and print times 1, 3, 5, 7, 10, 14,
> 20, 25, and 30 days.

### LLM-generated config (`config/my_sandy_loam_model.json`)

```json
{
  "project_name": "Sandy loam over sand, 30-day atmospheric",
  "case_id": "sandy_loam_30d",
  "simulation_time": {
    "t_init": 0.0,
    "t_end": 30.0,
    "dt_init": 0.001,
    "units": "days"
  },
  "soil_profile": [
    { "depth_top": 0.0, "depth_bottom": 1.0, "material": "sandy_loam" },
    { "depth_top": 1.0, "depth_bottom": 2.0, "material": "sand" }
  ],
  "van_genuchten": {
    "source_csv": "test_inputs/new_user_dynamic_test/materials_vg_stable.csv"
  },
  "initial_condition": {
    "type": "pressure_head",
    "value": -1.0
  },
  "upper_boundary": { "type": "atmospheric" },
  "lower_boundary": { "type": "free_drainage" },
  "atmospheric": {
    "enabled": true,
    "source_csv": "test_inputs/new_user_dynamic_test/atmosphere_stable_30d.csv",
    "time_column": "time_d",
    "precipitation_column": "precipitation_m_d",
    "potential_evaporation_column": "potential_evaporation_m_d",
    "units": { "time": "day", "length": "m" },
    "hCritA": -10000.0
  },
  "root_uptake": null,
  "solute_transport": null,
  "observation_depths": [0.2, 0.6, 1.2, 1.8],
  "output_settings": {
    "print_times": [1.0, 3.0, 5.0, 7.0, 10.0, 14.0, 20.0, 25.0, 30.0],
    "print_interval": 1.5
  }
}
```

### Commands

Review:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\my_sandy_loam_model.json --review
```

Run after review confirms the config looks correct:

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe main.py --config config\my_sandy_loam_model.json --all --overwrite-run --timeout 60 --hydrus-launch-mode argv
```

Expected outcome: 30/30 time steps converge, max water-balance error under 1 %, pipeline reports `overall_status: ok`.

---

## CSV File Formats

### Atmospheric forcing CSV

Required columns: `time_d`, `precipitation_m_d`, `potential_evaporation_m_d`

```csv
time_d,precipitation_m_d,potential_evaporation_m_d
0.0,0.0,0.0
1.0,0.005,0.001
...
30.0,0.0,0.0
```

- Time must span from `t_init` to `t_end`.
- Precipitation and evaporation must be non-negative.
- Units: days and m/day.

### Material hydraulic parameters CSV

Required columns: `material`, `theta_r`, `theta_s`, `alpha_1_m`, `n`, `Ks_m_d`, `l`

```csv
material,theta_r,theta_s,alpha_1_m,n,Ks_m_d,l
sandy_loam,0.065,0.41,7.5,1.89,1.061,0.5
sand,0.045,0.43,14.5,2.68,7.128,0.5
```

- Each `material` name must match a `"material"` field in `soil_profile`.
- SWCC point-data fitting is not supported; supply van Genuchten parameters directly.

---

## Review-Config Guard

When you run `--review`, the agent records the reviewed config path and a content hash in `.hydrus_agent_state/last_review.json`. Before `--all` runs, the agent checks that the config matches the reviewed one.

This prevents an LLM from accidentally reviewing one config and running another.

If the guard blocks a run:

- Run `--review` again on the config you want to run, then re-run `--all`.
- Use `--allow-config-mismatch` only for existing demo or hand-authored configs where you already understand the content.

---

## Supported Config Features

The agent validator accepts JSON configs for:

- Simple water-flow cases (constant flux, constant head, atmospheric upper boundary)
- CSV-driven atmospheric boundary forcing
- CSV-driven van Genuchten material parameters
- Simple root uptake with atmospheric forcing
- Simple one-species conservative solute transport

The following are not supported in generated configs:

- Advanced solute chemistry (adsorption, decay, reactions, multi-solute)
- Heat transport
- Advanced root uptake, crop growth, salinity stress
- Hysteresis, dual porosity, dual permeability
- Calibration or automatic parameter fitting

If you include unsupported features, validation will fail with a descriptive error.

---

## Troubleshooting

**Validation fails: "soil_profile layer references material not defined in the material CSV"**

The `"material"` field in a `soil_profile` layer must exactly match a row in the material CSV. Check spelling and case.

---

**Validation fails: "atmospheric record time is outside the simulation window"**

The atmospheric CSV must span from `t_init` to `t_end`. Add records at `t_init` and `t_end` if the CSV is shorter than the simulation window.

---

**Validation fails: "upper_boundary.type='atmospheric' requires atmospheric.enabled=true and atmospheric.records"**

When `upper_boundary.type` is `"atmospheric"`, the `atmospheric` block must exist, `enabled` must be `true`, and either `source_csv` or inline `records` must be provided.

---

**Review guard blocks `--all` after editing the config**

Re-run `--review` on the edited config to update the state, then run `--all` again.

---

**`pipeline_summary.json` reports `hydrus_numerical_status: failed` even though HYDRUS returned exit code 0**

`H1D_CALC.EXE` can return exit code 0 even when the numerical solution stopped early. The agent checks `Error.msg` and QC outputs separately. Check `qc_summary.json` and `report.md` for details. Possible causes: precipitation too high for the soil conductivity, initial pressure head inconsistent with boundary conditions, or insufficient time stepping resolution (`dt_init` too large).

---

## Safety Notes

- Do not commit CSV files containing sensitive field-site data without review.
- Do not use `--allow-config-mismatch` for LLM-generated configs unless you have reviewed the config manually.
- The agent automates HYDRUS workflows but does not replace hydrogeological judgement. Review simulation setup, boundary conditions, and outputs before interpreting results.

---

## Verifying prompt-to-config quality

A deterministic, offline benchmark grades pre-saved candidate configs against per-case expectations (schema validation, scientific-reviewer codes, structural features, raw JSON shape). It never calls an LLM and never runs HYDRUS, so it is safe to run on any platform.

```powershell
C:\App\anaconda3\envs\hydrus-agent\python.exe scripts\run_prompt_benchmark.py
```

See [benchmarks/prompt_to_config/README.md](../benchmarks/prompt_to_config/README.md) for the case schema and instructions for adding new cases.
