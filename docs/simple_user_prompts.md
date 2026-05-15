# Simple User Prompts

For everyday use of the HYDRUS-1D agent through Codex or Claude Code, you do not need to paste long technical instructions. The project-level instructions (see [AGENTS.md](../AGENTS.md) and [CLAUDE.md](../CLAUDE.md)) already tell the assistant how to translate a simple modelling request into the correct workflow.

**Where this fits:**

- This document gives **short user-facing prompts** for everyday modelling.
- [docs/llm_assisted_json_configuration.md](llm_assisted_json_configuration.md) is the **technical reference** for the underlying JSON config workflow that the assistant uses internally.
- [AGENTS.md](../AGENTS.md) is the **assistant-facing instruction set** that defines the default workflow.

**Important:** Long developer prompts (with every command spelled out) are still useful for testing, debugging, and acceptance checks. For normal use, the shorter prompts below are sufficient.

---

## What the assistant does behind the scenes

When you give a short modelling request, the coding assistant should:

```
Simple user prompt
  → infer a reasonable case_id
  → choose or create CSV inputs (atmosphere and material parameters)
  → write config/<case_id>.json (LLM-assisted JSON mode)
  → main.py --config config/<case_id>.json --review
  → check the review output is valid
  → main.py --config config/<case_id>.json --all --overwrite-run --timeout 60 --hydrus-launch-mode argv
  → inspect pipeline_summary.json, qc_summary.json, Error.msg, report.md, figures/
  → report whether the result is suitable for interpretation
```

You do not need to mention any of these commands in your prompt. The assistant should follow this workflow by default.

---

## Example 1 — very simple prompt

> Use the HYDRUS-1D agent to build and run a 30-day 1D infiltration model for a 2 m sandy loam over sand profile. Use existing CSV inputs for atmosphere and material properties. Review before running and tell me whether the result is reliable.

This is enough. The assistant should:

- pick a sensible `case_id` such as `sandy_loam_over_sand_30d`;
- reuse the stable demo CSVs under `test_inputs/new_user_dynamic_test/` for atmosphere and material parameters;
- create the JSON config in `config/`;
- run `--review`, then `--all` if review passes;
- summarise the reliability statuses.

---

## Example 2 — intermediate prompt

> Build a 30-day HYDRUS-1D model with a 2 m column. Use sandy loam from 0–1 m and sand from 1–2 m. Use atmospheric CSV forcing, material parameter CSV input, free drainage bottom boundary, initial pressure head -1 m, and observation depths at 0.2, 0.6, 1.2, and 1.8 m. Create a JSON config, review it, run HYDRUS if valid, and summarize the reliability of the result.

Here the user has specified the physical setup but still leaves the file paths and command choices to the assistant. The assistant should use the stable demo CSVs unless told otherwise.

---

## Example 3 — advanced prompt (explicit inputs)

> Create a JSON config for a 30-day HYDRUS-1D simulation with a 2 m sandy-loam-over-sand profile, `atmospheric.source_csv = test_inputs/new_user_dynamic_test/atmosphere_stable_30d.csv`, `van_genuchten.source_csv = test_inputs/new_user_dynamic_test/materials_vg_stable.csv`, free drainage lower boundary, uniform initial pressure head = -1.0 m, observation depths `[0.2, 0.6, 1.2, 1.8]`, and print times `[1, 3, 5, 7, 10, 14, 20, 25, 30]`. Review before running and report pipeline/QC reliability.

This level of detail is optional. It pins down every input but the assistant still follows the same review-before-run workflow.

---

## What your final response should include

When the assistant finishes, the report back to you should include:

- the **config file path** (e.g. `config/sandy_loam_over_sand_30d.json`);
- the **run folder** (e.g. `runs/sandy_loam_over_sand_30d/`);
- the **validation status** from `--review` (valid `ModelConfig` or specific errors);
- **`execution_status`** (did the HYDRUS process complete?);
- **`hydrus_numerical_status`** (did HYDRUS report convergence?);
- **`qc_status`** (did post-run QC pass?);
- **`overall_status`** (`ok`, `failed`, or `incomplete`);
- **maximum water-balance error** if available (from `qc_summary.json`);
- a clear sentence on **whether the result is suitable for interpretation** (only `ok` is suitable).

If `Error.msg` reports non-convergence even though HYDRUS returned exit code 0, the assistant must flag this and not call the run successful.

---

## When the assistant should ask one clarification

The assistant should not invent missing inputs silently. It should ask one concise clarification when:

- no atmospheric forcing data is available and the request is not generic enough to justify the stable demo CSV;
- no material parameters are available and the request is not generic enough to justify the stable demo CSV;
- the requested process is unsupported (e.g. multi-solute transport, heat transport, hysteresis, dual porosity, calibration, optimisation);
- the units or a boundary condition are physically ambiguous;
- the user asks for **SWCC point-data fitting** — explain that this is not implemented and ask for direct van Genuchten parameters (`theta_r`, `theta_s`, `alpha_1_m`, `n`, `Ks_m_d`, `l`) instead.

For anything else, the assistant should proceed with sensible defaults derived from the project's stable demo and report what it chose.

---

## Platform reminder

Full HYDRUS execution requires Windows with PC-Progress HYDRUS-1D installed locally. The Python helpers, JSON template generation, schema printing, and review-only workflows work on any platform, but `--all` and real HYDRUS execution require access to `H1D_CALC.EXE`. See [docs/getting_started_with_codex_or_claude_code.md](getting_started_with_codex_or_claude_code.md) for setup.

## See also

- [AGENTS.md](../AGENTS.md) — full assistant instructions
- [docs/llm_assisted_json_configuration.md](llm_assisted_json_configuration.md) — technical reference for the JSON config workflow
- [docs/getting_started_with_codex_or_claude_code.md](getting_started_with_codex_or_claude_code.md) — first-run walkthrough
- [docs/using_with_llm_agents.md](using_with_llm_agents.md) — reference prompts for developer-level testing
