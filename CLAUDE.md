# CLAUDE.md — HYDRUS-1D Agent

Project-level instructions for Claude Code working in this repository.

**Read [AGENTS.md](AGENTS.md) first.** It contains the canonical environment rules, default workflow for simple user prompts, HYDRUS run rules, reliability-reporting requirements, and scope boundaries.

## Quick reference

- This is a **Windows-local** HYDRUS-1D automation agent. Full HYDRUS execution requires Windows + PC-Progress HYDRUS-1D + `H1D_CALC.EXE`.
- Always use the full Python path: `C:\App\anaconda3\envs\hydrus-agent\python.exe`. Never plain `python`.
- Before `--all` or `--run`, set `$env:HYDRUS_EXE` to the full path of `H1D_CALC.EXE`.
- For new user prompts, prefer **LLM-assisted JSON mode** (write `config/<case_id>.json`, then `--review`, then `--all`) over `--describe`.
- Do not pass `--allow-config-mismatch` unless the user explicitly approves it.
- HYDRUS exit code 0 alone is not success. Always inspect `pipeline_summary.json`, `qc_summary.json`, `Error.msg` if present, `report.md`, and `figures/`, then report `execution_status`, `hydrus_numerical_status`, `qc_status`, `overall_status`, max water-balance error, and whether the result is suitable for interpretation.
- SWCC point-data fitting is not implemented. Ask for direct van Genuchten parameters instead.

## Key docs

- [AGENTS.md](AGENTS.md) — full project instructions
- [skills/README.md](skills/README.md) — workflow-level skill catalogue (read the relevant `SKILL.md` before modifying configs or running HYDRUS)
- [docs/simple_user_prompts.md](docs/simple_user_prompts.md) — short prompts users can write
- [docs/llm_assisted_json_configuration.md](docs/llm_assisted_json_configuration.md) — technical LLM-assisted JSON workflow
- [docs/getting_started_with_codex_or_claude_code.md](docs/getting_started_with_codex_or_claude_code.md) — first-run walkthrough
- [docs/using_with_llm_agents.md](docs/using_with_llm_agents.md) — reference for LLM operating constraints
