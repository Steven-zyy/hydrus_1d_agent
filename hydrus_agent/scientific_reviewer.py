"""Deterministic scientific reviewer for HYDRUS-1D configurations.

This module emits **heuristic review flags** on top of the schema
validator. Items are advisory: they document modelling assumptions,
plausibility checks against typical soil-physics ranges, and
interpretation limits. They are **not hard validity criteria** — a
config can be entirely valid and still produce review items, and an
item flagged here does not by itself make a HYDRUS run unreliable.

Severity convention
-------------------
- ``info``     — documents an assumption, limitation, or context-free reminder
- ``warning``  — heuristic plausibility flag worth a second look
- ``critical`` — a clearly impossible or unsafe input. Used very
  conservatively; today this only covers uniform initial water content
  that lies strictly outside the material's [theta_r, theta_s] window
  (a physical impossibility), where the comparison is unambiguous.

Thresholds in this module are deliberately conservative and drawn from
typical agricultural-soil ranges (Carsel & Parrish 1988-style). They
are not authoritative; users with site-specific data should override.

Design rules
------------
- Pure, deterministic, no I/O, no LLM.
- Never raises; on internal error a single ``REVIEWER_INTERNAL_ERROR``
  info item is emitted so the caller still gets a structured result.
- Time-unit-sensitive rules (e.g. "window < 30 days") only fire when
  the configured time units are ``days``; otherwise they are skipped
  rather than emitting noise.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Literal, Optional

from hydrus_agent.schema import (
    InitialConditionType,
    LowerBoundaryType,
    ModelConfig,
    RootDistribution,
    TimeUnits,
    UpperBoundaryType,
)

logger = logging.getLogger(__name__)

Severity = Literal["info", "warning", "critical"]

SCHEMA_VERSION = 1

# --- Heuristic thresholds (NOT hard validity rules) ----------------------
# Sources: typical mineral-soil ranges per Carsel & Parrish (1988) and
# common HYDRUS-1D modelling guidance. Adjust with care.

THETA_S_HIGH = 0.60
THETA_S_LOW = 0.25
THETA_R_HIGH = 0.15
THETA_RANGE_NARROW = 0.10

ALPHA_LOW = 0.1     # 1/m
ALPHA_HIGH = 50.0   # 1/m

N_STIFF = 1.10
N_LOW_INFO = 1.20

KS_VERY_LOW = 1e-6   # m/day
KS_LOW_INFO = 1e-4   # m/day
KS_HIGH_INFO = 10.0  # m/day
KS_VERY_HIGH = 100.0  # m/day

DT_RATIO_WARN = 0.10
DT_RATIO_VERY_LARGE = 0.50  # warning (not critical — heuristic only)

UPPER_FLUX_LARGE_M_PER_DAY = 0.5
UPPER_CONST_HEAD_PONDED_M = 0.0
LOWER_CONST_HEAD_DEEP_M = -10.0

PRESSURE_VERY_DRY_M = -150.0
PROFILE_SHALLOW_FRACTION = 0.5

LAYER_INTERFACE_TOL = 1e-6

RECHARGE_SHORT_WINDOW_DAYS = 30.0
ATMOS_SHORT_WINDOW_DAYS = 1.0
SPARSE_PRINT_FACTOR = 10  # atmos records per print step

BOTTOM_FLUX_BOUNDARY_TYPES = {
    LowerBoundaryType.free_drainage,
    LowerBoundaryType.seepage_face,
}


# --- Public dataclasses --------------------------------------------------


@dataclass(frozen=True)
class ReviewItem:
    severity: Severity
    category: str
    code: str
    message: str
    implication: str
    suggested_action: str
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class ScientificReviewResult:
    items: List[ReviewItem]
    counts: Dict[str, int]
    ok: bool
    schema_version: int = SCHEMA_VERSION


# --- Public API ----------------------------------------------------------


def review_config(config: ModelConfig) -> ScientificReviewResult:
    """Run every rule against ``config`` and return a structured result.

    Never raises. A reviewer internal error is reported as a single
    ``REVIEWER_INTERNAL_ERROR`` info item so callers still get a result.
    """
    items: List[ReviewItem] = []
    rules: List[Callable[[ModelConfig], List[ReviewItem]]] = [
        _rule_soil_hydraulic_parameters,
        _rule_boundary_condition_consistency,
        _rule_initial_condition_consistency,
        _rule_observation_node_placement,
        _rule_simulation_duration_and_print_times,
        _rule_recharge_over_interpretation,
        _rule_unsupported_or_simplified_physics,
    ]
    for rule in rules:
        try:
            items.extend(rule(config))
        except Exception as exc:  # noqa: BLE001
            logger.warning("scientific_reviewer rule %s failed: %s", rule.__name__, exc)
            items.append(
                ReviewItem(
                    severity="info",
                    category="reviewer_internal",
                    code="REVIEWER_INTERNAL_ERROR",
                    message=f"Rule '{rule.__name__}' raised an exception and was skipped.",
                    implication="One heuristic check did not run; other checks were not affected.",
                    suggested_action="Report the failing rule name and the offending config.",
                    context={"rule": rule.__name__, "error": str(exc)},
                )
            )

    counts = {"info": 0, "warning": 0, "critical": 0}
    for item in items:
        counts[item.severity] = counts.get(item.severity, 0) + 1
    return ScientificReviewResult(
        items=items,
        counts=counts,
        ok=counts.get("critical", 0) == 0,
    )


def render_markdown(result: ScientificReviewResult) -> str:
    """Render the result as a short markdown summary suitable for terminals.

    No emoji. ASCII only. Items are grouped by severity (critical first).
    A standing reminder is printed up front that flags are heuristic.
    """
    lines: List[str] = []
    lines.append("# Scientific review")
    lines.append("")
    lines.append(
        "Heuristic review flags. These are advisory checks against typical "
        "soil-physics ranges and modelling conventions; they are not hard "
        "validity criteria. Schema-level errors are caught separately by "
        "the validator."
    )
    lines.append("")
    lines.append(
        f"Counts: critical={result.counts.get('critical', 0)}, "
        f"warning={result.counts.get('warning', 0)}, "
        f"info={result.counts.get('info', 0)}. "
        f"ok={result.ok}."
    )
    lines.append("")
    if not result.items:
        lines.append("_No review items emitted._")
        return "\n".join(lines)

    order = {"critical": 0, "warning": 1, "info": 2}
    grouped = sorted(result.items, key=lambda i: (order.get(i.severity, 99), i.category, i.code))
    current_sev: Optional[str] = None
    for item in grouped:
        if item.severity != current_sev:
            lines.append("")
            lines.append(f"## {item.severity.upper()}")
            current_sev = item.severity
        lines.append("")
        lines.append(f"### [{item.code}] {item.category}")
        lines.append(f"- Message: {item.message}")
        lines.append(f"- Implication: {item.implication}")
        lines.append(f"- Suggested action: {item.suggested_action}")
        if item.context:
            lines.append(f"- Context: {item.context}")
    return "\n".join(lines)


def result_to_dict(result: ScientificReviewResult) -> Dict[str, Any]:
    """Plain-dict serialisation suitable for json.dumps."""
    return {
        "schema_version": result.schema_version,
        "ok": result.ok,
        "counts": dict(result.counts),
        "items": [asdict(item) for item in result.items],
    }


# --- Rule helpers --------------------------------------------------------


def _make(severity, category, code, message, implication, action, context=None):
    return ReviewItem(
        severity=severity, category=category, code=code,
        message=message, implication=implication,
        suggested_action=action, context=context,
    )


def _is_days(config: ModelConfig) -> bool:
    return config.simulation_time.units == TimeUnits.days


def _window(config: ModelConfig) -> float:
    return float(config.simulation_time.t_end - config.simulation_time.t_init)


# --- Rule 1: Soil hydraulic parameters -----------------------------------


def _rule_soil_hydraulic_parameters(config: ModelConfig) -> List[ReviewItem]:
    out: List[ReviewItem] = []
    cat = "soil_hydraulic_parameters"
    for vg in config.van_genuchten:
        ctx = {"material_id": vg.material_id}
        if vg.theta_s > THETA_S_HIGH:
            out.append(_make(
                "warning", cat, "VG_THETA_S_HIGH",
                f"theta_s={vg.theta_s:g} is above the typical mineral-soil range (~{THETA_S_HIGH}).",
                "May reflect organic or heavily structured material; storage may be over-estimated for mineral soils.",
                "Confirm the soil is organic/peat or measured directly; otherwise lower theta_s toward 0.40-0.55.",
                ctx,
            ))
        if vg.theta_s < THETA_S_LOW:
            out.append(_make(
                "warning", cat, "VG_THETA_S_LOW",
                f"theta_s={vg.theta_s:g} is below the typical mineral-soil range (~{THETA_S_LOW}).",
                "Saturated storage will be small; saturated flow events may be under-predicted.",
                "Verify the value against measured porosity for this material.",
                ctx,
            ))
        if vg.theta_r > THETA_R_HIGH:
            out.append(_make(
                "warning", cat, "VG_THETA_R_HIGH",
                f"theta_r={vg.theta_r:g} is unusually high for typical soils (>{THETA_R_HIGH}).",
                "Residual water content limits the dry end of the retention curve.",
                "Confirm theta_r is consistent with measured wilting-point data.",
                ctx,
            ))
        if (vg.theta_s - vg.theta_r) < THETA_RANGE_NARROW:
            out.append(_make(
                "warning", cat, "VG_THETA_RANGE_NARROW",
                f"theta_s - theta_r = {vg.theta_s - vg.theta_r:g} is narrow (<{THETA_RANGE_NARROW}).",
                "Plant-available water and retention dynamic range are small.",
                "Re-check theta_r and theta_s against independent retention measurements.",
                ctx,
            ))
        if vg.alpha < ALPHA_LOW or vg.alpha > ALPHA_HIGH:
            out.append(_make(
                "warning", cat, "VG_ALPHA_EXTREME",
                f"alpha={vg.alpha:g} 1/m lies outside the typical range [{ALPHA_LOW}, {ALPHA_HIGH}].",
                "Air-entry behaviour may be unrealistic; matric-potential curves can become very steep or very flat.",
                "Confirm the alpha unit (1/m vs 1/cm) and the soil texture class.",
                ctx,
            ))
        if vg.n < N_STIFF:
            out.append(_make(
                "warning", cat, "VG_N_NEAR_ONE",
                f"n={vg.n:g} is close to 1 (<{N_STIFF}); the retention curve is nearly flat and numerically stiff.",
                "Solver convergence is harder and time steps may be forced very small.",
                "Consider a slightly larger n if supported by measurements; otherwise expect longer runs.",
                ctx,
            ))
        elif vg.n < N_LOW_INFO:
            out.append(_make(
                "info", cat, "VG_N_LOW",
                f"n={vg.n:g} is on the low side (<{N_LOW_INFO}); retention curve is gentle.",
                "Typical of fine-textured soils; numerical performance may be slower than for coarser soils.",
                "No action required if this is intentional.",
                ctx,
            ))
        if vg.Ks < KS_VERY_LOW:
            out.append(_make(
                "warning", cat, "VG_KS_VERY_LOW",
                f"Ks={vg.Ks:g} m/day is below the typical range (<{KS_VERY_LOW:g}).",
                "Effectively impervious; vertical flow may be negligible.",
                "Confirm the Ks unit (m/day vs cm/day) and the measurement method.",
                ctx,
            ))
        elif vg.Ks < KS_LOW_INFO:
            out.append(_make(
                "info", cat, "VG_KS_LOW",
                f"Ks={vg.Ks:g} m/day is low; flow will be slow.",
                "Long simulations may be needed to see drainage signals.",
                "No action required if this matches the soil texture.",
                ctx,
            ))
        if vg.Ks > KS_VERY_HIGH:
            out.append(_make(
                "warning", cat, "VG_KS_VERY_HIGH",
                f"Ks={vg.Ks:g} m/day is above the typical range (>{KS_VERY_HIGH:g}).",
                "Very fast drainage; numerical stability may suffer near saturation.",
                "Confirm the Ks unit and that the value is not in cm/day mistakenly converted.",
                ctx,
            ))
        elif vg.Ks > KS_HIGH_INFO:
            out.append(_make(
                "info", cat, "VG_KS_HIGH",
                f"Ks={vg.Ks:g} m/day is on the high side (>{KS_HIGH_INFO:g}).",
                "Typical of coarse sands or gravels.",
                "No action required if this matches the soil texture.",
                ctx,
            ))
    return out


# --- Rule 2: Boundary condition consistency ------------------------------


def _rule_boundary_condition_consistency(config: ModelConfig) -> List[ReviewItem]:
    out: List[ReviewItem] = []
    cat = "boundary_condition_consistency"

    upper = config.upper_boundary
    if upper.type == UpperBoundaryType.constant_flux and upper.flux is not None:
        if abs(upper.flux) > UPPER_FLUX_LARGE_M_PER_DAY and _is_days(config):
            out.append(_make(
                "warning", cat, "UPPER_CONST_FLUX_LARGE",
                f"Upper constant flux |{upper.flux:g}| m/day is large (>{UPPER_FLUX_LARGE_M_PER_DAY}).",
                "Surface ponding or non-convergence is more likely under sustained large fluxes.",
                "Confirm the flux magnitude and unit; consider an atmospheric boundary if temporal variation is expected.",
            ))
    if upper.type == UpperBoundaryType.constant_head and upper.head is not None:
        if upper.head > UPPER_CONST_HEAD_PONDED_M:
            out.append(_make(
                "info", cat, "UPPER_CONST_HEAD_PONDED_NO_NOTE",
                f"Upper constant head={upper.head:g} m implies a ponded surface.",
                "Infiltration will be limited by Ks rather than by atmospheric forcing.",
                "Confirm that surface ponding is intended for this case.",
            ))

    lower = config.lower_boundary
    if lower.type == LowerBoundaryType.constant_head and lower.head is not None:
        if lower.head < LOWER_CONST_HEAD_DEEP_M:
            out.append(_make(
                "info", cat, "LOWER_CONST_HEAD_DEEP_WATER_TABLE",
                f"Lower constant head={lower.head:g} m implies a deep water table.",
                "Drainage will be effectively unrestricted; results approximate a free-drainage case.",
                "Consider using free_drainage if the actual water table is far below the profile.",
            ))
    if lower.type == LowerBoundaryType.seepage_face:
        if config.atmospheric is None or not config.atmospheric.enabled:
            out.append(_make(
                "info", cat, "LOWER_SEEPAGE_FACE_NO_ATMOSPH",
                "Seepage-face lower boundary is used without atmospheric forcing.",
                "Outflow is driven entirely by initial conditions and any constant upper flux/head.",
                "Confirm this matches the conceptual model.",
            ))

    atmos = config.atmospheric
    if atmos is not None and atmos.enabled and atmos.records:
        total_pet = sum(r.evaporation for r in atmos.records)
        has_root = config.root_uptake is not None and config.root_uptake.enabled
        if total_pet > 0 and not has_root:
            out.append(_make(
                "info", cat, "ATMOS_PET_NO_ROOTUPTAKE",
                "Atmospheric forcing has positive potential evaporation but no root uptake is enabled.",
                "All atmospheric demand is routed to soil evaporation; transpiration is not modelled.",
                "Enable root_uptake if a vegetated surface is intended.",
            ))
    return out


# --- Rule 3: Initial condition consistency -------------------------------


def _rule_initial_condition_consistency(config: ModelConfig) -> List[ReviewItem]:
    out: List[ReviewItem] = []
    cat = "initial_condition_consistency"
    ic = config.initial_condition

    if ic.type == InitialConditionType.water_content and ic.value is not None and not ic.profile:
        # Uniform water-content initial condition can be confidently
        # compared against material theta_r / theta_s. This is the only
        # place we emit critical.
        theta_r_min = min(vg.theta_r for vg in config.van_genuchten)
        theta_s_max = max(vg.theta_s for vg in config.van_genuchten)
        if ic.value < theta_r_min:
            out.append(_make(
                "critical", cat, "IC_WC_BELOW_THETA_R",
                f"Uniform initial water content {ic.value:g} is below the minimum theta_r ({theta_r_min:g}) among materials.",
                "Physically impossible; HYDRUS may fail or produce nonsensical results.",
                "Raise the initial value above theta_r for every material, or switch to pressure_head.",
                {"theta_r_min": theta_r_min},
            ))
        if ic.value > theta_s_max:
            out.append(_make(
                "critical", cat, "IC_WC_ABOVE_THETA_S",
                f"Uniform initial water content {ic.value:g} exceeds the maximum theta_s ({theta_s_max:g}) among materials.",
                "Physically impossible; HYDRUS may fail or treat the cell as super-saturated.",
                "Lower the initial value below theta_s for every material, or switch to pressure_head.",
                {"theta_s_max": theta_s_max},
            ))
    elif ic.type == InitialConditionType.water_content and ic.profile:
        # Profile-based water content cannot be confidently mapped to
        # per-depth materials without solving the full layer lookup;
        # downgrade to info rather than emit critical.
        out.append(_make(
            "info", cat, "IC_WC_PROFILE_NOT_CHECKED",
            "Initial water-content profile is provided; per-depth plausibility against theta_r/theta_s was not checked.",
            "The reviewer cannot reliably bracket profile points against layer materials.",
            "Spot-check each profile point lies inside [theta_r, theta_s] for the material at that depth.",
        ))

    if ic.type == InitialConditionType.pressure_head and ic.value is not None and not ic.profile:
        if ic.value > 0:
            out.append(_make(
                "info", cat, "IC_PRESSURE_POSITIVE_SURFACE",
                f"Uniform initial pressure head {ic.value:g} m is positive (saturated/ponded).",
                "The column starts wetter than typical field conditions.",
                "Confirm the ponded start is intended.",
            ))
        if ic.value < PRESSURE_VERY_DRY_M:
            out.append(_make(
                "warning", cat, "IC_PRESSURE_VERY_DRY",
                f"Uniform initial pressure head {ic.value:g} m is drier than the conventional wilting point (~{PRESSURE_VERY_DRY_M} m).",
                "Initial water content may be very close to theta_r; convergence near the dry end may be slow.",
                "Confirm the dry start is intended and that theta_r is realistic.",
            ))

    if ic.profile and ic.type == InitialConditionType.pressure_head:
        profile_top = config.soil_profile[0].depth_top
        profile_bottom = config.soil_profile[-1].depth_bottom
        column = profile_bottom - profile_top
        depths = [p.depth for p in ic.profile]
        span = max(depths) - min(depths)
        if column > 0 and span / column < PROFILE_SHALLOW_FRACTION:
            out.append(_make(
                "info", cat, "IC_PROFILE_SHALLOW_SAMPLING",
                f"Initial-condition profile covers only {span/column:.0%} of the column depth.",
                "Pressure head between the deepest profile point and the column base is interpolated.",
                "Add a deeper profile point if better resolution is needed.",
            ))
    return out


# --- Rule 4: Observation node placement ----------------------------------


def _rule_observation_node_placement(config: ModelConfig) -> List[ReviewItem]:
    out: List[ReviewItem] = []
    cat = "observation_node_placement"
    depths = list(config.observation_depths or [])
    if not depths:
        out.append(_make(
            "info", cat, "OBS_NONE_DEFINED",
            "No observation depths are configured.",
            "Obs_Node.out will not be produced; depth-resolved time series and field-comparison are not possible.",
            "Add observation_depths if depth-specific outputs are needed.",
        ))
        return out

    interfaces = [layer.depth_bottom for layer in config.soil_profile[:-1]]
    for d in depths:
        for iface in interfaces:
            if abs(d - iface) <= LAYER_INTERFACE_TOL:
                out.append(_make(
                    "info", cat, "OBS_AT_LAYER_INTERFACE",
                    f"Observation depth {d:g} lies on a soil-layer interface.",
                    "Output values at the interface depend on which side the node falls on; interpretation can be ambiguous.",
                    "Move the observation a few mm above or below the interface if a unique material is desired.",
                    {"depth": d, "interface": iface},
                ))
                break

    if len(config.soil_profile) >= 2:
        layer_of = []
        for d in depths:
            for idx, layer in enumerate(config.soil_profile):
                if layer.depth_top <= d <= layer.depth_bottom:
                    layer_of.append(idx)
                    break
        if layer_of and len(set(layer_of)) == 1:
            out.append(_make(
                "info", cat, "OBS_CLUSTERED_ONE_LAYER",
                "All observation depths fall in a single soil layer.",
                "Inter-layer comparison and depth-spread plots will be limited.",
                "Add observations in other layers if cross-layer signals are of interest.",
            ))

    if config.root_uptake is not None and config.root_uptake.enabled:
        rd = config.root_uptake.root_depth
        if rd is not None and depths and all(d > rd for d in depths):
            out.append(_make(
                "info", cat, "OBS_BELOW_ROOT_ZONE_ONLY",
                f"All observation depths are below the rooting depth ({rd:g}).",
                "Root-zone moisture dynamics will not be directly observable in Obs_Node.out.",
                "Add at least one observation within the root zone if root-water-uptake effects are of interest.",
            ))
    return out


# --- Rule 5: Simulation duration and print times -------------------------


def _rule_simulation_duration_and_print_times(config: ModelConfig) -> List[ReviewItem]:
    out: List[ReviewItem] = []
    cat = "simulation_duration_and_print_times"
    window = _window(config)
    if window > 0:
        ratio = config.simulation_time.dt_init / window
        if ratio > DT_RATIO_VERY_LARGE:
            out.append(_make(
                "warning", cat, "SIM_DT_INIT_VERY_LARGE",
                f"dt_init is {ratio:.0%} of the simulation window.",
                "Solver behaviour is likely to be poor; even if HYDRUS runs, results will be coarse.",
                "Reduce dt_init by at least one order of magnitude.",
            ))
        elif ratio > DT_RATIO_WARN:
            out.append(_make(
                "warning", cat, "SIM_DT_INIT_LARGE",
                f"dt_init is {ratio:.0%} of the simulation window.",
                "Initial steps may be too coarse to resolve sharp wetting fronts.",
                "Consider lowering dt_init so it represents at most a few percent of the window.",
            ))

    print_times = list(config.output_settings.print_times or [])
    if not print_times and config.output_settings.print_interval is None:
        out.append(_make(
            "info", cat, "SIM_PRINT_NONE",
            "No print_times and no print_interval are configured.",
            "Only end-of-simulation state will be printed; intermediate dynamics will not be available.",
            "Add print_times or print_interval to capture intermediate states.",
        ))

    atmos = config.atmospheric
    if atmos is not None and atmos.enabled and atmos.records:
        if len(atmos.records) >= SPARSE_PRINT_FACTOR * max(1, len(print_times) or 1):
            if not print_times and config.output_settings.print_interval is None:
                pass  # already flagged
            elif len(atmos.records) >= SPARSE_PRINT_FACTOR * max(1, len(print_times)):
                out.append(_make(
                    "info", cat, "SIM_PRINT_SPARSE_VS_ATMOSPH",
                    f"Atmospheric records ({len(atmos.records)}) are much denser than print times ({len(print_times)}).",
                    "Plots may smooth over short-duration events such as individual rainfall pulses.",
                    "Add print_times or shorten print_interval if event-scale resolution is needed.",
                ))

        # Day-based threshold; only fire when units are days.
        if _is_days(config) and window < ATMOS_SHORT_WINDOW_DAYS:
            out.append(_make(
                "info", cat, "SIM_SHORT_FOR_ATMOSPH",
                f"Simulation window is shorter than {ATMOS_SHORT_WINDOW_DAYS:g} day with atmospheric forcing enabled.",
                "Daily forcing data may not have time to express its effect on the column.",
                "Consider a longer simulation if the atmospheric signal is of interest.",
            ))
    return out


# --- Rule 6: Recharge over-interpretation --------------------------------


def _rule_recharge_over_interpretation(config: ModelConfig) -> List[ReviewItem]:
    out: List[ReviewItem] = []
    cat = "recharge_over_interpretation"
    if config.lower_boundary.type not in BOTTOM_FLUX_BOUNDARY_TYPES:
        return out

    # Always emit a standing caveat when a bottom-flux boundary is in use.
    out.append(_make(
        "info", cat, "RECHARGE_INTERPRETATION_CAVEAT",
        "Modelled bottom flux is a model output under the stated boundary conditions.",
        "It does not by itself prove field recharge magnitude or timing.",
        "When reporting recharge, state the boundary condition assumption and the simulation window explicitly.",
    ))

    # Day-based thresholds only fire when configured units are days.
    if _is_days(config) and _window(config) < RECHARGE_SHORT_WINDOW_DAYS:
        out.append(_make(
            "warning", cat, "RECHARGE_SHORT_WINDOW",
            f"Simulation window is shorter than {RECHARGE_SHORT_WINDOW_DAYS:g} days for a bottom-flux boundary.",
            "Cumulative bottom flux over a short window is unlikely to represent long-term recharge.",
            "Lengthen the simulation, or qualify any recharge statement with the actual window length.",
        ))

    atmos = config.atmospheric
    if atmos is None or not atmos.enabled:
        out.append(_make(
            "info", cat, "RECHARGE_NO_ATMOSPH",
            "Bottom-flux boundary is used with no atmospheric forcing.",
            "Flux at the base is driven entirely by initial conditions and any constant upper boundary.",
            "Confirm this matches the conceptual model before interpreting bottom flux as recharge.",
        ))
    return out


# --- Rule 7: Unsupported or simplified physics ---------------------------


def _rule_unsupported_or_simplified_physics(config: ModelConfig) -> List[ReviewItem]:
    out: List[ReviewItem] = []
    cat = "unsupported_or_simplified_physics"

    if config.solute_transport is not None and config.solute_transport.enabled:
        out.append(_make(
            "info", cat, "PHYS_SOLUTE_SINGLE_SPECIES",
            "Solute transport is enabled with a single conservative species.",
            "Multi-species transport, sorption, decay, and reaction chains are not supported in this configuration.",
            "If reactive transport is required, document the limitation explicitly in the report.",
        ))

    if config.root_uptake is not None and config.root_uptake.enabled:
        if config.root_uptake.distribution == RootDistribution.uniform:
            out.append(_make(
                "info", cat, "PHYS_ROOT_DISTRIBUTION_UNIFORM",
                "Root distribution is uniform; Feddes-style water-stress and salinity-stress reductions are not modelled.",
                "Root water uptake is a simplified representation rather than a stress-aware sink term.",
                "Document the simplification; consider a more detailed root model if stress response is of interest.",
            ))

    atmos = config.atmospheric
    if atmos is not None and atmos.enabled and atmos.records:
        has_rain = any(r.precipitation > 0 for r in atmos.records)
        has_dry = any(r.precipitation == 0 for r in atmos.records)
        if has_rain and has_dry:
            out.append(_make(
                "info", cat, "PHYS_NO_HYSTERESIS",
                "Atmospheric records contain both wet and dry periods, and hysteresis is not modelled.",
                "Wetting and drying retention curves are assumed identical; this is a common modelling simplification, not an error.",
                "If hysteresis is suspected to matter for the question, note this limitation in the interpretation.",
            ))
        out.append(_make(
            "info", cat, "PHYS_NO_TEMPERATURE",
            "Heat transport is not generated; temperature effects on flow and on retention are not modelled.",
            "This is a documented modelling limitation, not a sign that the run is invalid.",
            "If thermal effects are expected to matter, note this limitation in the interpretation.",
        ))
    return out


__all__ = [
    "ReviewItem",
    "ScientificReviewResult",
    "SCHEMA_VERSION",
    "render_markdown",
    "result_to_dict",
    "review_config",
]
