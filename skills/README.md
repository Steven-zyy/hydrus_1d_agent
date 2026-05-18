# Skills

This directory is a **documentation layer** describing the standard workflows
an agent (Claude Code, Codex, or a human contributor) should follow when
working in this repository. Each skill is a markdown file under a named
subdirectory; there is **no runtime skill framework, no `--skill` CLI flag,
and no Python registry**.

Skills exist so that an agent presented with a user request can:

1. Identify which skill(s) the request maps to.
2. Read the matching `SKILL.md` before modifying configs, running HYDRUS, or
   interpreting results.
3. Compose multiple skills in order when a request spans several stages.

## Current skill catalogue

| Skill | One-line purpose |
|---|---|
| [case_design](case_design/SKILL.md) | Translate a user's modelling request into a reviewable `config/<case_id>.json`. |
| [boundary_condition](boundary_condition/SKILL.md) | Choose and configure upper/lower boundaries and atmospheric forcing. |
| [soil_profile](soil_profile/SKILL.md) | Build a contiguous layered profile with van Genuchten parameters. |
| [run_qc](run_qc/SKILL.md) | Execute a reviewed config and interpret the four-status reliability report. |
| [scenario_comparison](scenario_comparison/SKILL.md) | Run and analyse parameter-override scenario batches. |
| [field_comparison](field_comparison/SKILL.md) | Compare measured observation data against `Obs_Node.out`. |
| [scientific_reporting](scientific_reporting/SKILL.md) | Compose the final user-facing answer with the required reliability statement. |

## SKILL.md structure

Every `SKILL.md` uses the same eight sections so an agent can scan them
quickly:

1. **Purpose**
2. **When to use this skill**
3. **Expected inputs**
4. **Expected outputs**
5. **Existing modules and tools used** — references real files under
   `hydrus_agent/` and real CLI flags in `main.py`. No invented tools.
6. **Guardrails** — review-before-run, config-hash consistency, Windows +
   `HYDRUS_EXE`, scope limits.
7. **Failure modes** — what commonly goes wrong and how the agent should
   respond (report, do not auto-fix).
8. **Example user prompts** and **Testing expectations**.

## How skills compose

A typical end-to-end request flows:

```
case_design
  ├── boundary_condition
  └── soil_profile
        ↓
      run_qc
        ↓
   (optional) scenario_comparison
   (optional) field_comparison
        ↓
   scientific_reporting
```

Skills do **not** override the rules in [AGENTS.md](../AGENTS.md). They
restate the relevant guardrails locally so an agent reading only the
SKILL.md still respects the review-before-run gate, the config-hash guard,
the "HYDRUS exit 0 ≠ success" rule, and the unsupported-physics scope
boundary. `AGENTS.md` remains the canonical source.

## What this directory is not

- Not a Python package. Do not `import skills`.
- Not a runtime registry. There is no `SkillBase`, `SkillResult`, or
  `--skill` flag.
- Not a replacement for the existing CLI workflows. Skills describe how to
  use the existing flags (`--review`, `--all`, `--scenario-file`,
  `--field-data`, etc.), not new ones.

A future milestone may introduce a Python skill framework if and when the
team agrees on a runtime contract. Until then, skills are documentation.
