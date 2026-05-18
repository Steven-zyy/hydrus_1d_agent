# Release Notes

## v0.6.0-skills-reproducibility — 2026-05-18

Released as a research software prototype. **License not specified yet.**

This release adds a skills documentation layer, run-time provenance, a deterministic scientific reviewer, and an offline prompt-to-config benchmark. It also formalises Python packaging and CI.

### Added

- **Skills documentation layer** under [`skills/`](skills/README.md): seven workflow-level `SKILL.md` files (`case_design`, `boundary_condition`, `soil_profile`, `run_qc`, `scenario_comparison`, `field_comparison`, `scientific_reporting`) plus an index. Skills are documentation, not a runtime framework; there is no `--skill` CLI flag.
- **`runs/<case_id>/run_manifest.json`**: a reproducibility provenance file written alongside `pipeline_summary.json`. Records config hash, HYDRUS executable and launch mode, Python and OS environment, `hydrus_agent` version, input file hashes, and key output paths. Independent of `pipeline_summary.json`; never changes `overall_status`.
- **`hydrus_agent/scientific_reviewer.py`**: deterministic, rule-based science-level reviewer that emits structured items (severity, category, code, message, implication, suggested_action). Available via the new `--science-review` CLI flag (does not run HYDRUS, does not modify review state, always exits 0) and written as `scientific_review.json` in every run directory. Items are heuristic flags; they do not change `overall_status`. `critical` is reserved for clearly-impossible inputs (uniform initial water content outside `[theta_r, theta_s]`).
- **Offline prompt-to-config benchmark** under [`benchmarks/prompt_to_config/`](benchmarks/prompt_to_config/README.md) plus [`scripts/run_prompt_benchmark.py`](scripts/run_prompt_benchmark.py). **The benchmark evaluates pre-saved candidate JSON configs against per-case expectations (schema validation, scientific-reviewer codes, structural features, raw JSON shape). It does not call an LLM at runtime and does not run HYDRUS.** Eleven canonical cases ship with the release.
- **Python packaging**: `pyproject.toml` with PEP 621 metadata. New console script `hydrus-agent` (entry point `main:main`). `python main.py …` continues to work unchanged.
- **Recommended environment**: `environment.yml` for conda users. `requirements.txt` is preserved for pip users. No strict lock file added.
- **Citation file**: `CITATION.cff` (Citation File Format 1.2.0). No DOI yet.
- **CI**: `.github/workflows/tests.yml` runs `pytest tests/ -q` on Windows and Linux with Python 3.10 and 3.11. CI does **not** set `HYDRUS_EXE`; the six HYDRUS-execution-dependent tests skip cleanly in CI.

### Changed

- `hydrus_agent.__version__` bumped from `"0.2.0-local"` to `"0.6.0"`.
- README restructured: explicit Installation section, generic `python` in user-facing commands, maintainer-specific Windows paths moved to a dedicated "Maintainer-specific notes" section, new "Supported Scope and Limitations" and "License" sections.

### Tests

- 374 tests pass, 6 skipped (HYDRUS-execution-dependent). Zero failures.

### Known Limitations

- All v0.5 limitations remain in scope.
- Skills are documentation only; the agent does not auto-select or auto-execute them.
- The scientific reviewer uses heuristic plausibility thresholds, not hard validity criteria. `critical` is used very conservatively.
- The prompt-to-config benchmark grades saved JSON files; it does not evaluate any LLM at run time.
- **License not specified yet.** Contact the author for reuse terms.

---

## v0.5-csv-reliability - 2026-05-15

This release adds CSV-driven input support and robust HYDRUS reliability reporting on top of the v0.2-local prototype.

### Added

- CSV-driven atmospheric boundary input: supply time-series precipitation and potential evaporation from a separate CSV file instead of inline JSON records. Required columns: `time_d`, `precipitation_m_d`, `potential_evaporation_m_d`. Config loading validates the file, checks coverage, and prints full metadata on review.
- CSV-driven material hydraulic parameter input: supply van Genuchten parameters from a CSV table and reference soil layers by name. Required columns: `material`, `theta_r`, `theta_s`, `alpha_1_m`, `n`, `Ks_m_d`, `l`. This is direct parameter input; SWCC point-data curve fitting is not implemented.
- Natural-language `--describe` recognises CSV file paths in the description and sets `source_csv` fields automatically for both atmospheric forcing and material parameters.
- Improved HYDRUS `Error.msg` detection: `pipeline_summary.json` now records `hydrus_numerical_status` (`converged` vs `failed`) separately from `execution_status`, detecting numerical failure even when HYDRUS returns exit code 0.
- Reliability-aware `pipeline_summary.json`: separate fields for `execution_status`, `hydrus_numerical_status`, `qc_status`, and `overall_status`.
- Reliability-aware `report.md`: the interpretation section qualifies positive convergence wording when `Error.msg` reports a numerical failure or when QC has failed.
- Stable user demo: `config/new_user_dynamic_csv_test.json` with supporting CSV inputs in `test_inputs/new_user_dynamic_test/`; 30-day two-layer (sandy loam over sand) atmospheric case, all 30 steps converge, max water-balance error 0.456 %.

### Tests

- 262 tests pass, 6 skipped (platform-dependent runner tests). Zero failures.

### Known Limitations

- SWCC point-data curve fitting to derive van Genuchten parameters is not implemented.
- `H1D_CALC.EXE` is a Windows PE; it cannot execute on Linux, macOS, WSL, or remote cloud environments.
- All other v0.2 limitations remain in scope (no advanced solute chemistry, no heat transport, no calibration, no GUI).

---

## v0.2-local - 2026-05-15

This release prepares the project as a broader local research prototype for generated HYDRUS-1D runs, official benchmark interpretation, field-data comparison, and scenario/sensitivity workflows.

### Added Since v0.1-local

- Simple atmospheric root uptake generation for water-flow cases, with fixed root depth, potential transpiration, and uniform root distribution.
- Simple one-species conservative solute transport generation through Phydrus input APIs.
- Solute output interpretation for generated runs and copied official examples, including discovered `SoluteN.out` files, concentration summaries, and solute figures.
- Field-data comparison from CSV observation data, including RMSE, MAE, bias, correlation, matched point counts, overlay figures, QC integration, and report sections.
- Scenario/sensitivity batch runner for small explicit parameter variants.
- Scenario comparison report for completed batches, including sorted metric tables, best field-data RMSE, largest infiltration, largest bottom flux, and optional comparison plots.
- Expanded user documentation, demo workflows, LLM-agent prompts, acceptance-test docs, benchmark support matrix, and full official example sweep report.

### Current v0.2 Capabilities

- Natural-language config builder for simple supported descriptions.
- Reviewed-config guard to prevent accidentally running a different generated config.
- Full HYDRUS pipeline: validate, prepare inputs, run, read outputs, plot, QC, and report.
- Atmospheric forcing with precipitation, evaporation, and optional `hCritA`.
- Simple root uptake for atmospheric water-flow cases.
- Simple conservative one-solute transport generation.
- Field-data comparison and model-observation metrics.
- Scenario/sensitivity batches from explicit JSON scenario files.
- Scenario comparison reporting from existing batch summaries.
- Official PC-Progress benchmark harness and full example sweep reporting.

### Still Out Of Scope

- Calibration, optimisation, parameter fitting, automatic model improvement, or automatic scenario grid expansion.
- Advanced solute chemistry: multiple solutes, adsorption, decay, reactions, volatilisation, non-equilibrium transport, heat coupling, and salinity/root stress.
- Heat transport generation.
- Advanced root uptake, crop growth, salinity stress, or solute uptake.
- Hysteresis, dual porosity, dual permeability, and scaling-factor generation.
- GUI, web app, MCP server, or cloud service packaging.

## v0.1-local - 2026-05-14

This release prepares the HYDRUS-1D agent as a stable local prototype for simple water-flow workflows and official-example benchmark reporting.

### Included

- Natural-language config builder for simple water-flow descriptions.
- Reviewed-config guard that prevents accidentally running a different generated config from the one reviewed.
- End-to-end HYDRUS pipeline: validate, prepare inputs, run `H1D_CALC.EXE`, read outputs, plot, QC, and report.
- HYDRUS runner support for `argv` launch mode and neutral handling of successful runs that also print `Press Enter to continue`.
- Output readers for common HYDRUS tables, including generic `Obs_Node.out` parsing with variable columns.
- Solute-output interpretation for copied official examples: discovered `SoluteN.out` files, concentration columns in observation/profile outputs, summary metrics, and optional solute figures.
- Standard PNG figure generation for balance, flux, observation-node, profile, contour, and run-diagnostic outputs.
- Rule-based QC with `qc_summary.json`.
- Markdown run reports.
- Simple atmospheric water-flow support using `ATMOSPH.IN` records for precipitation, evaporation, and optional `hCritA`.
- Simple atmospheric root uptake support with fixed root depth, potential transpiration, and uniform root distribution.
- Simple one-species conservative solute transport generation using Phydrus solute APIs.
- Field-data comparison against HYDRUS observation-node outputs from CSV, with RMSE, MAE, bias, correlation, overlay figures, QC, and report sections.
- Scenario/sensitivity batch runner for small explicit parameter variants with batch CSV/JSON summaries.
- Scenario comparison reporting for completed batches, including key metric tables, best field-data RMSE identification, largest infiltration/bottom-flux scenarios, and optional comparison plots.
- Official PC-Progress benchmark harness that copies raw examples before running them.
- Manifest batch runner, gap report, support matrix, and full official example sweep report.
- Documentation for direct CLI use and use through Claude/Codex-style local LLM agents.

### Current Support Gaps

- Advanced solute transport: multi-solute systems, adsorption, decay, reaction chains, volatilisation, non-equilibrium transport, heat coupling, and salinity/root stress.
- Heat transport model generation.
- Advanced root uptake, root growth, crop growth, salinity stress, and solute uptake.
- Hysteresis.
- Dual porosity and dual permeability.
- Scaling-factor workflows.
- Calibration, optimisation, or automatic parameter updating from measured field data.
- Automatic scenario grid expansion or parameter search.
- Automatic repair of unsupported or incompatible official examples.
- GUI or web interface.

### Safety Notes

- Raw official examples under `benchmarks/pc_progress_raw/` are treated as read-only inputs.
- Benchmark runs use copied workspaces under `benchmarks/benchmark_results/`.
- Local secrets and machine-specific paths belong in `.env`, which should not be committed.
- Generated run folders, benchmark results, `.hydrus_agent_state/`, and `.codex_tmp/` are local artifacts.
