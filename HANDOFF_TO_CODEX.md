# HYDRUS-1D Agent Handoff

## Current status

This project is a local HYDRUS-1D automation workflow.

Completed milestones:

1. Config validation
   - JSON config is validated with Pydantic.
   - Run folder is created safely.
   - Config snapshot is saved.

2. Phydrus adapter
   - Validated config is converted to Phydrus/HYDRUS input files.
   - SELECTOR.IN and PROFILE.DAT are generated.

3. HYDRUS runner
   - Real PC-Progress H1D_CALC.EXE can be invoked successfully.
   - The working launch mode is argv:
     [H1D_CALC.EXE, project_dir, "-1"]
   - LEVEL_01.DIR-only launch had path issues and should not be the default.
   - Logs are saved to runs/<case_id>/logs/hydrus_run.log.

4. Output reader
   - Parses:
     - Balance.out
     - T_Level.out
     - Run_Inf.out
     - Obs_Node.out
     - Nod_Inf.out
   - Real output structures have been tested with fixtures.

5. Plotter
   - Generates 9 standard figures:
     - balance_storage_vs_time.png
     - instantaneous_fluxes.png
     - cumulative_water_balance.png
     - obs_theta_vs_time.png
     - obs_head_vs_time.png
     - moisture_profiles.png
     - pressure_head_profiles.png
     - moisture_contour.png
     - run_diagnostics.png

6. QC
   - Generates qc_summary.json.

7. Pipeline
   - One-command workflow works:
     python main.py --config config/simple_runnable_case.json --all --overwrite-run --timeout 30 --hydrus-launch-mode argv
   - Produces:
     - HYDRUS input files
     - HYDRUS outputs
     - logs
     - figures
     - qc_summary.json
     - report.md
     - pipeline_summary.json

## Test status

The most recent full test suite passed:
117/117 tests passed.

Before making changes, always run:
python -m pytest tests/ -v

## Important implementation notes

- Do not modify Phydrus source code.
- Do not modify raw HYDRUS output files.
- Keep argv launch mode as default for PC-Progress H1D_CALC.EXE.
- Do not rely on LEVEL_01.DIR-only mode unless explicitly requested.
- Preserve existing CLI commands.
- Use existing modules rather than rewriting the project.

## Next milestone

Milestone 8: natural-language configuration builder.

Goal:
Allow a user to describe a simple HYDRUS-1D model in natural language and generate a validated JSON config, without running HYDRUS automatically.

Scope:
- No autonomous model running yet.
- No auto-correction or retry.
- No online API calls.
- No atmospheric boundary / ATMOSPH.IN yet.
- Only simple 1D cases:
  - one or more layers
  - van Genuchten parameters
  - pressure-head initial condition
  - constant flux / constant head / free drainage
  - observation depths
  - print times

Suggested files:
- hydrus_agent/config_builder.py
- tests/test_config_builder.py
- README.md update
- main.py CLI update

Suggested CLI:
python main.py --describe "1 m sandy loam column, 1 day, 1 mm/day infiltration, free drainage, initial head -1 m, observations at 0.3 and 0.7 m" --write-config config/from_description.json

Expected behaviour:
- Generate draft JSON config.
- Validate it using existing ModelConfig schema.
- Print summary.
- Do not run HYDRUS automatically.