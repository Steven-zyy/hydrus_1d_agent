# Full Official Example Sweep Report

- Manifest: `benchmarks\manifest.csv`
- Examples root: `D:\Claude\hydrus_1d_agent\benchmarks\pc_progress_raw\Direct`
- Timeout per example: 60.0 seconds
- HYDRUS launch mode: `argv`
- Total examples found: 23

## Status Counts

| Status | Count |
|---|---:|
| pass | 8 |
| partial | 14 |
| fail | 1 |
| skipped | 0 |
| future | 0 |

## All Examples

| case_id | process_type | supported_now | status | HYDRUS | return_code | parsed outputs | QC | warnings | figures | category | raw unchanged | summary |
|---|---|---|---|---:|---:|---:|---|---:|---:|---|---:|---|
| 1DRAINAG | water_flow | yes | pass | True | 0 | 5 | ok | 0 | 9 | water_flow_supported | True | `D:\Claude\hydrus_1d_agent\benchmarks\benchmark_results\1DRAINAG\benchmark_summary.json` |
| 1INFILTR | water_flow | yes | pass | True | 0 | 5 | ok | 0 | 9 | water_flow_supported | True | `D:\Claude\hydrus_1d_agent\benchmarks\benchmark_results\1INFILTR\benchmark_summary.json` |
| 1SCALING | scaling_factor | no | partial | True | 0 | 4 | warning | 2 | 7 | scaling_factor_gap | True | `D:\Claude\hydrus_1d_agent\benchmarks\benchmark_results\1SCALING\benchmark_summary.json` |
| 2HYSTER | hysteresis | no | partial | True | 0 | 5 | ok | 0 | 9 | hysteresis_gap | True | `D:\Claude\hydrus_1d_agent\benchmarks\benchmark_results\2HYSTER\benchmark_summary.json` |
| 2NOHYSTR | atmospheric_field_profile | partial | fail | False | 0 | 0 | warning | 6 | 0 | input_timing_compatibility | True | `D:\Claude\hydrus_1d_agent\benchmarks\benchmark_results\2NOHYSTR\benchmark_summary.json` |
| 3LAIJURI | solute | partial | partial | True | 0 | 6 | ok | 0 | 11 | solute_transport_gap | True | `D:\Claude\hydrus_1d_agent\benchmarks\benchmark_results\3LAIJURI\benchmark_summary.json` |
| 3SELIM | solute | partial | partial | True | 0 | 6 | ok | 0 | 11 | solute_transport_gap | True | `D:\Claude\hydrus_1d_agent\benchmarks\benchmark_results\3SELIM\benchmark_summary.json` |
| 4HEAT | heat_transport | no | partial | True | 0 | 5 | warning | 1 | 9 | heat_transport_gap | True | `D:\Claude\hydrus_1d_agent\benchmarks\benchmark_results\4HEAT\benchmark_summary.json` |
| 5SEASON | atmospheric_field_profile | partial | partial | True | 0 | 5 | warning | 1 | 9 | qc_warning_only | True | `D:\Claude\hydrus_1d_agent\benchmarks\benchmark_results\5SEASON\benchmark_summary.json` |
| DRAINAGE | atmospheric_field_profile | partial | partial | True | 0 | 5 | warning | 1 | 9 | qc_warning_only | True | `D:\Claude\hydrus_1d_agent\benchmarks\benchmark_results\DRAINAGE\benchmark_summary.json` |
| EnBal2b | heat_transport | no | partial | True | 0 | 5 | warning | 1 | 9 | heat_transport_gap | True | `D:\Claude\hydrus_1d_agent\benchmarks\benchmark_results\EnBal2b\benchmark_summary.json` |
| ROOTUPTK | root_uptake | partial | pass | True | 0 | 5 | ok | 0 | 9 | root_uptake_supported | True | `D:\Claude\hydrus_1d_agent\benchmarks\benchmark_results\ROOTUPTK\benchmark_summary.json` |
| TEST1 | solute | partial | partial | True | 0 | 6 | ok | 0 | 11 | solute_transport_gap | True | `D:\Claude\hydrus_1d_agent\benchmarks\benchmark_results\TEST1\benchmark_summary.json` |
| Test10 | atmospheric_field_profile | partial | pass | True | 0 | 5 | ok | 0 | 9 | atmospheric_supported | True | `D:\Claude\hydrus_1d_agent\benchmarks\benchmark_results\Test10\benchmark_summary.json` |
| TEST11 | solute | partial | partial | True | 0 | 5 | ok | 0 | 9 | solute_transport_gap | True | `D:\Claude\hydrus_1d_agent\benchmarks\benchmark_results\TEST11\benchmark_summary.json` |
| TEST2 | atmospheric_field_profile | partial | partial | True | 0 | 5 | warning | 1 | 9 | qc_warning_only | True | `D:\Claude\hydrus_1d_agent\benchmarks\benchmark_results\TEST2\benchmark_summary.json` |
| TEST3 | solute | partial | partial | True | 0 | 8 | ok | 0 | 11 | solute_transport_gap | True | `D:\Claude\hydrus_1d_agent\benchmarks\benchmark_results\TEST3\benchmark_summary.json` |
| TEST4 | solute | partial | partial | True | 0 | 6 | ok | 0 | 11 | solute_transport_gap | True | `D:\Claude\hydrus_1d_agent\benchmarks\benchmark_results\TEST4\benchmark_summary.json` |
| TEST5 | solute | partial | partial | True | 0 | 6 | ok | 0 | 11 | solute_transport_gap | True | `D:\Claude\hydrus_1d_agent\benchmarks\benchmark_results\TEST5\benchmark_summary.json` |
| Test9 | atmospheric_field_profile | partial | pass | True | 0 | 5 | ok | 0 | 9 | atmospheric_supported | True | `D:\Claude\hydrus_1d_agent\benchmarks\benchmark_results\Test9\benchmark_summary.json` |
| TEST9a | atmospheric_field_profile | partial | pass | True | 0 | 5 | ok | 0 | 9 | atmospheric_supported | True | `D:\Claude\hydrus_1d_agent\benchmarks\benchmark_results\TEST9a\benchmark_summary.json` |
| UPINFIL | water_flow | yes | pass | True | 0 | 5 | ok | 0 | 9 | water_flow_supported | True | `D:\Claude\hydrus_1d_agent\benchmarks\benchmark_results\UPINFIL\benchmark_summary.json` |
| VOLATILE | atmospheric_field_profile | partial | pass | True | 0 | 5 | ok | 0 | 9 | atmospheric_supported | True | `D:\Claude\hydrus_1d_agent\benchmarks\benchmark_results\VOLATILE\benchmark_summary.json` |

## Top Failure And Gap Categories

| Category | Count |
|---|---:|
| solute_transport_gap | 7 |
| atmospheric_supported | 4 |
| water_flow_supported | 3 |
| qc_warning_only | 3 |
| heat_transport_gap | 2 |
| hysteresis_gap | 1 |
| input_timing_compatibility | 1 |
| root_uptake_supported | 1 |
| scaling_factor_gap | 1 |

## Recommended Next Development Priorities

- solute_transport_gap: 7 case(s)
- heat_transport_gap: 2 case(s)
- hysteresis_gap: 1 case(s)
- scaling_factor_gap: 1 case(s)
- input_timing_compatibility: 1 case(s)

## Case Notes

- 2NOHYSTR: failed due to input timing compatibility, not runner failure. See `docs/2NOHYSTR_failure_diagnostic.md`.
- Milestone 16 added generated one-species conservative solute transport and reran `TEST1`, `3LAIJURI`, and `3SELIM` only. These copied official examples still run, parse `Solute1.out`, pass QC, and generate 11 figures. They remain partial because official solute examples include chemistry beyond simple conservative tracer generation.
- Milestone 15 reran `TEST1`, `3LAIJURI`, `3SELIM`, `TEST3`, `TEST4`, and `TEST5` only. These copied official solute examples parse `SoluteN.out`, preserve concentration columns in observation/profile outputs, pass QC, and generate 11 figures including concentration time series and profiles. They remain partial because advanced solute transport model generation is not implemented.
- Milestone 14 reran `ROOTUPTK`, `5SEASON`, and `TEST2` only. `ROOTUPTK` is now a clean root uptake benchmark pass. `5SEASON` and `TEST2` still run, parse 5 outputs, and generate 9 figures, but remain partial because QC water-balance warnings remain and the official cases include process features beyond simple generated root uptake.

## Good Regression Benchmarks

- 1DRAINAG: water_flow_supported, 5 parsed outputs, 9 figures
- 1INFILTR: water_flow_supported, 5 parsed outputs, 9 figures
- ROOTUPTK: root_uptake_supported, 5 parsed outputs, 9 figures
- config\simple_conservative_solute_case.json: generated one-species conservative tracer case, writes `Solute1.out`, passes QC, and generates concentration figures
- TEST1: solute output interpretation, 6 parsed outputs, 11 figures
- TEST3: multi-solute output interpretation, 8 parsed outputs, 11 figures
- Test10: atmospheric_supported, 5 parsed outputs, 9 figures
- Test9: atmospheric_supported, 5 parsed outputs, 9 figures
- TEST9a: atmospheric_supported, 5 parsed outputs, 9 figures
- UPINFIL: water_flow_supported, 5 parsed outputs, 9 figures
- VOLATILE: atmospheric_supported, 5 parsed outputs, 9 figures

## Examples That Should Remain Future Scope

- 1SCALING: scaling_factor_gap (scaling_factor)
- 2HYSTER: hysteresis_gap (hysteresis)
- 3LAIJURI: advanced solute chemistry gap (solute)
- 3SELIM: advanced solute chemistry gap (solute)
- 4HEAT: heat_transport_gap (heat_transport)
- EnBal2b: heat_transport_gap (heat_transport)
- TEST1: advanced solute chemistry gap (solute)
- TEST11: advanced solute chemistry gap (solute)
- TEST3: multi-solute / advanced solute chemistry gap (solute)
- TEST4: advanced solute chemistry gap (solute)
- TEST5: advanced solute chemistry gap (solute)
