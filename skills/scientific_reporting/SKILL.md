# scientific_reporting

## Purpose

Compose the final user-facing answer for a HYDRUS-1D modelling request.
This skill consumes the artefacts produced by `run_qc` (and optionally
`scenario_comparison` or `field_comparison`) and packages them into a
short, scientifically defensible summary. It is the only skill that
speaks directly to the user about whether a result is suitable for
interpretation.

## When to use this skill

Use this skill when:

- A pipeline run has completed (success, partial, or failure) and the
  user expects a written answer.
- A scenario batch or a field comparison has completed and the user
  wants the headline findings, not the raw tables.

Do **not** use this skill when:

- The pipeline has not run yet → use `run_qc`.
- The user is asking how to set up a case → use `case_design`.

## Expected inputs

- A `runs/<case_id>/` directory containing at minimum:
  - `pipeline_summary.json`
  - `run_manifest.json` (reproducibility provenance: config hash,
    HYDRUS executable + launch mode, environment, input/output file
    inventory, reliability statuses)
  - `scientific_review.json` (heuristic science-level review items;
    advisory only — a review item does not by itself make a run
    unreliable, and the four reliability statuses in
    `pipeline_summary.json` remain authoritative for go/no-go)
  - `outputs/qc_summary.json` (when QC ran)
  - `report.md`
  - `figures/`
  - `hydrus_project/Error.msg` if present.
- For batches: the `runs/<batch_id>/` comparison report from
  `scenario_analysis`.
- For field comparisons: the metrics table produced by
  `field_comparison`.

## Expected outputs

A concise message to the user that **always** includes:

- `execution_status`
- `hydrus_numerical_status`
- `qc_status`
- `overall_status`
- Maximum water-balance error if available.
- An explicit reliability statement: the result is suitable for
  interpretation **only when `overall_status == ok`**. Otherwise state
  what failed and what the user can do (re-design, re-run, adjust
  timestep, etc.) — do not present numerical findings as if they were
  reliable.
- Pointers to the most relevant figures and tables, by relative path.

## Existing modules and tools used

- [hydrus_agent/reporter.py](../../hydrus_agent/reporter.py) — assembles
  `report.md` from the pipeline artefacts; this skill summarises that
  file rather than re-implementing it.
- [hydrus_agent/qc.py](../../hydrus_agent/qc.py) — defines the QC checks
  whose results appear in `qc_summary.json`.
- [hydrus_agent/output_reader.py](../../hydrus_agent/output_reader.py)
  — source of the parsed outputs that `reporter.py` consumes.
- [hydrus_agent/plotter.py](../../hydrus_agent/plotter.py) — produces
  the figures the agent references by filename.
- [hydrus_agent/scenario_analysis.py](../../hydrus_agent/scenario_analysis.py)
  — source of the comparison artefacts for batch runs.
- [hydrus_agent/field_comparison.py](../../hydrus_agent/field_comparison.py)
  — source of the goodness-of-fit metrics for field comparisons.
- Reference documents: [AGENTS.md](../../AGENTS.md) → "Reliability
  reporting"; [docs/user_guide.md](../../docs/user_guide.md).

## Guardrails

- **Never claim a result is reliable when `overall_status` is not
  `ok`.** This is the single most important rule of this skill.
- **Never treat HYDRUS exit code 0 alone as success.** Always cite
  `pipeline_summary.json` and `qc_summary.json`.
- **Report uncertainty and scope honestly.** If the model uses
  unsupported approximations (e.g. SWCC fitting was requested but
  van Genuchten parameters were substituted), say so.
- **Do not invent numbers.** Every reported value should be traceable to
  a parsed output file or `pipeline_summary.json`.
- **Do not auto-fix.** If the run failed, describe the failure and
  options; let the user decide whether to invoke `case_design` /
  `run_qc` again.
- **Do not embed huge tables.** Reference files; quote at most a few
  rows or one small summary table.
- Keep the message scoped to this run / batch. Do not compare to
  unrelated runs the user did not ask about.

## Failure modes

- **`pipeline_summary.json` missing** — say so plainly; the pipeline
  likely did not start.
- **Inconsistent statuses** (e.g. `hydrus_numerical_status == converged`
  but `qc_status == failed`) — report both and explain that QC adds
  checks beyond convergence (typically water-balance error or output
  completeness).
- **Report references figures that do not exist** — list which figures
  are missing rather than silently dropping them.
- **User asks "is it good?" and `overall_status != ok`** — answer "no,
  for the following reasons" and enumerate them; do not soften.

## Example user prompts

- "Summarise the run and tell me if it is reliable."
- "Write a short paragraph I can put in my notebook for this case."
- "Give me the headline findings from the scenario batch under
  `runs/<batch_id>`."
- "What does the field comparison say about the model fit?"

## Testing expectations

The following existing tests exercise the modules this skill depends on:

- [tests/test_reporter.py](../../tests/test_reporter.py) — Markdown
  report assembly.
- [tests/test_qc.py](../../tests/test_qc.py) — QC checks reflected in
  the reliability summary.
- [tests/test_pipeline.py](../../tests/test_pipeline.py) —
  `pipeline_summary.json` structure and status assembly.
- [tests/test_plotter.py](../../tests/test_plotter.py) — figure files
  this skill references.
- [tests/test_scenario_analysis.py](../../tests/test_scenario_analysis.py)
  — batch comparison artefacts when summarising scenarios.
- [tests/test_field_comparison.py](../../tests/test_field_comparison.py)
  — field metrics when summarising field comparisons.

This skill is itself documentation-only and has **no direct test file**.
Future changes to the required reliability statement, the set of
fields reported, or the report layout should be reflected in updates to
this SKILL.md and to the relevant tests above (`test_reporter.py`,
`test_pipeline.py`).
