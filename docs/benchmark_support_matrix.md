# Benchmark Support Matrix

Date: 2026-05-15

This matrix summarises the current status of the PC-Progress official HYDRUS-1D examples listed in `benchmarks/manifest.csv`, using the latest existing per-case benchmark summaries under `benchmarks/benchmark_results/`. ROOTUPTK, 5SEASON, and TEST2 were rerun during root uptake validation. TEST1, 3LAIJURI, 3SELIM, TEST3, TEST4, and TEST5 were rerun during solute-output interpretation validation. TEST1, 3LAIJURI, and 3SELIM were rerun again after simple conservative solute generation was added.

Support levels:

- `pass`: HYDRUS ran successfully, outputs parsed, QC passed.
- `partial`: HYDRUS ran successfully, but QC warnings remain or the case uses process features that the agent does not generate yet.
- `skipped`: intentionally not run in the current scope.
- `future`: not supported yet.

## Support Matrix

| case_id | description | process_type | supported_now | latest benchmark status | parsed outputs count | QC status | figure count | limitation / next action |
| --- | --- | --- | --- | --- | ---: | --- | ---: | --- |
| `1DRAINAG` | Official drainage example | water_flow | yes | pass | 5 | ok | 9 | Keep as a clean supported official water-flow regression benchmark. |
| `1INFILTR` | Official infiltration example | water_flow | yes | pass | 5 | ok | 9 | Keep as a clean supported official water-flow regression benchmark. |
| `TEST1` | Official solute-enabled example | solute | partial | partial | 6 | ok | 11 | Official copied output includes parsed `Solute1.out`, concentration summaries, and solute figures. Simple conservative tracer generation is supported; advanced official solute chemistry remains future scope. |
| `3LAIJURI` | Official solute-enabled example | solute | partial | partial | 6 | ok | 11 | Official copied output includes parsed `Solute1.out`, concentration summaries, and solute figures. Simple conservative tracer generation is supported; advanced official solute chemistry remains future scope. |
| `3SELIM` | Official solute-enabled example | solute | partial | partial | 6 | ok | 11 | Official copied output includes parsed `Solute1.out`, concentration summaries, and solute figures. Simple conservative tracer generation is supported; advanced official solute chemistry remains future scope. |
| `TEST3` | Official multi-solute example | solute | partial | partial | 8 | ok | 11 | Official copied output includes parsed `Solute1.out`, `Solute2.out`, and `Solute3.out`; multi-solute generation remains future scope. |
| `TEST4` | Official solute-enabled example | solute | partial | partial | 6 | ok | 11 | Official copied output includes parsed `Solute1.out`, concentration summaries, and solute figures. Advanced solute chemistry remains future scope. |
| `TEST5` | Official solute-enabled example | solute | partial | partial | 6 | ok | 11 | Official copied output includes parsed `Solute1.out`, concentration summaries, and solute figures. Advanced solute chemistry remains future scope. |
| `ROOTUPTK` | Official root uptake example | root_uptake | partial | pass | 5 | ok | 9 | Official copied example now runs, parses, passes QC, and generates figures. Generated simple root uptake is supported; this official case still includes solute settings, so solute generation remains future scope. |
| `5SEASON` | Official field soil profile under grass with atmospheric boundary | atmospheric_field_profile | partial | partial | 5 | warning: water balance threshold | 9 | Root uptake is no longer the primary generation gap for simple water-flow cases; this official case remains partial because it also includes heat/solute features and a QC water-balance warning. |
| `TEST2` | Official field soil profile under grass with atmospheric boundary | atmospheric_field_profile | partial | partial | 5 | warning: water balance threshold | 9 | Root uptake is no longer the primary generation gap for simple water-flow cases; this official case remains partial because it also includes heat/solute features and a QC water-balance warning. |
| `4HEAT` | Official heat transport under fluctuating atmospheric condition | heat_transport | no | future | 0 | not run | 0 | Heat transport generation is not supported yet; keep for a future heat milestone. |

## Current Validated Capability

- Simple water flow: generated runnable water-flow cases validate, run, parse outputs, produce QC, and generate figures.
- Atmospheric forcing: simple water-flow atmospheric forcing with `ATMOSPH.IN` is supported for generated cases.
- Root uptake: simple atmospheric water-flow cases can now write `rRoot`, HYDRUS root water uptake settings, and a uniform `Beta` root distribution profile.
- Official water-flow examples: `1DRAINAG` and `1INFILTR` are clean official benchmark passes.
- Generic Obs_Node parser: simple water-flow observation tables and official heat/solute-style observation tables with extra per-node columns now parse into a stable long table.
- Solute output interpretation: copied official solute examples can parse `SoluteN.out`, preserve observation/profile concentration columns, produce solute QC summaries, and generate concentration figures.
- Solute generation: simple one-species conservative tracer transport is supported for generated cases.

## Remaining Gaps

- Advanced solute transport generation: multiple solutes, adsorption, decay, reaction chains, volatilisation, salinity/root stress, and non-equilibrium transport.
- Heat transport generation.
- Advanced root uptake, root growth, crop growth, salinity stress, and solute uptake.
- Hysteresis.
- Dual porosity / dual permeability.
- Scaling factors.

## Notes

`TEST1`, `3LAIJURI`, `3SELIM`, `TEST3`, `TEST4`, and `TEST5` read solute concentration and flux outputs successfully. Their partial status is not an output-reader failure; it reflects official solute features beyond simple one-species conservative tracer generation.

`TEST1`, `5SEASON`, and `TEST2` can now read `Obs_Node.out` successfully. Their partial status is not an observation-output parser failure; it reflects unsupported process features or remaining QC warnings.

Milestone 14 root uptake validation reran `ROOTUPTK`, `5SEASON`, and `TEST2` only. `ROOTUPTK` is a clean official benchmark pass. `5SEASON` and `TEST2` still run successfully with 5 parsed outputs and 9 figures, but remain partial because QC water-balance warnings remain and the official cases include heat/solute features beyond the current generation scope.

`2NOHYSTR` fails on this `H1D_CALC.EXE` build because the first `ATMOSPH.IN` `tAtm` equals `tInit + dtInit` and is rejected during HYDRUS input/time reading. This is an input timing compatibility issue, not a runner/path/output-reader failure. See [`docs/2NOHYSTR_failure_diagnostic.md`](2NOHYSTR_failure_diagnostic.md).

Raw PC-Progress folders under `benchmarks/pc_progress_raw/` should remain read-only inputs. Benchmark runs should continue to use copied workspaces under `benchmarks/benchmark_results/`.
