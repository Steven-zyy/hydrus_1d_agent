"""Adapter from a validated ``ModelConfig`` to a Phydrus ``Model``.

This module is the only place that imports ``phydrus``. It deliberately
avoids importing it at module load so the rest of the package stays usable
when phydrus is not installed.

Scope (Milestone 2):
    * Translate ``ModelConfig`` fields into Phydrus API calls.
    * Write the HYDRUS-1D input files via ``Model.write_input()``.

Out of scope:
    * Calling ``Model.simulate()`` or otherwise running HYDRUS-1D.
    * Reading HYDRUS output files, plotting, reporting.
    * Auto-correcting invalid configurations.

If a configuration field cannot be mapped, ``UnsupportedFeatureError`` is
raised with a message that names the offending field.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Union

from hydrus_agent.schema import (
    InitialConditionType,
    LowerBoundaryType,
    ModelConfig,
    TimeUnits,
    UpperBoundaryType,
)


logger = logging.getLogger(__name__)


class UnsupportedFeatureError(NotImplementedError):
    """A validated ModelConfig field is not handled by the adapter yet."""


# --- Static maps ----------------------------------------------------------

# ``Model(time_unit=...)`` accepts these strings (per phydrus 0.2.0 source).
_TIME_UNIT_MAP: Dict[TimeUnits, str] = {
    TimeUnits.days: "days",
    TimeUnits.hours: "hours",
    TimeUnits.minutes: "min",
    TimeUnits.seconds: "sec",
}

# Top boundary codes per ``Model.add_waterflow`` docstring (HYDRUS-1D convention).
#   0 = Constant Pressure Head
#   1 = Constant Flux
#   2 = Atmospheric BC with Surface Layer
#   3 = Atmospheric BC with Surface Run Off  <-- chosen for "atmospheric"
#   4 = Variable Pressure Head
#   5 = Variable Pressure Head/Flux
_TOP_BC_MAP: Dict[UpperBoundaryType, int] = {
    UpperBoundaryType.constant_head: 0,
    UpperBoundaryType.constant_flux: 1,
    UpperBoundaryType.atmospheric: 3,
}

# Bottom boundary codes per ``Model.add_waterflow`` docstring.
#   0 = Constant Pressure Head
#   1 = Constant Flux
#   4 = Free Drainage
#   6 = Seepage Face
_BOT_BC_MAP: Dict[LowerBoundaryType, int] = {
    LowerBoundaryType.constant_head: 0,
    LowerBoundaryType.constant_flux: 1,
    LowerBoundaryType.free_drainage: 4,
    LowerBoundaryType.seepage_face: 6,
}

# Default node spacing in metres for ``create_profile``. Configurable via the
# ``dx`` keyword on ``prepare_phydrus_project``. Not currently exposed in the
# JSON schema — add a field there if users need per-case control.
DEFAULT_DX = 0.1


# --- Public entry point ---------------------------------------------------


def prepare_phydrus_project(
    config: ModelConfig,
    run_dir: Union[str, Path],
    hydrus_exe: Union[str, Path],
    *,
    dx: float = DEFAULT_DX,
) -> Path:
    """Translate ``config`` into a phydrus ``Model`` and write its input files.

    This function never calls ``Model.simulate()``. Running HYDRUS is a later
    milestone.

    Parameters
    ----------
    config
        A validated ``ModelConfig``.
    run_dir
        The case run folder (e.g. ``runs/case_001``). Must already exist —
        create it with ``hydrus_agent.create_run_folder`` first.
    hydrus_exe
        Path to the HYDRUS-1D executable. The file must exist because phydrus
        validates it inside ``Model.__init__``.
    dx
        Soil profile node spacing in metres. Default ``DEFAULT_DX`` (0.1 m).

    Returns
    -------
    Path
        The ``hydrus_project/`` subfolder containing the written input files.

    Raises
    ------
    UnsupportedFeatureError
        If ``config`` uses a feature the adapter does not yet map.
    FileNotFoundError
        If ``run_dir`` does not exist.
    """
    try:
        import phydrus as ps
    except ImportError as exc:
        raise UnsupportedFeatureError(
            "phydrus is not installed. Run `pip install phydrus` "
            "(see README.md, 'Check the environment for Milestone 2')."
        ) from exc

    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise FileNotFoundError(
            f"Run folder does not exist: {run_dir}. "
            "Create it via main.py (milestone 1) before preparing inputs."
        )

    project_dir = run_dir / "hydrus_project"
    project_dir.mkdir(exist_ok=True)

    # --- 1. Build the phydrus.Model ---------------------------------------
    time_unit = _TIME_UNIT_MAP.get(config.simulation_time.units)
    if time_unit is None:
        raise UnsupportedFeatureError(
            f"simulation_time.units={config.simulation_time.units!r} is not mapped"
        )

    ml = ps.Model(
        exe_name=str(hydrus_exe),
        ws_name=str(project_dir),
        name=config.case_id,
        description=config.project_name,
        length_unit="m",
        time_unit=time_unit,
        mass_units="mmol",
        print_screen=False,
    )

    # --- 2. Time information ---------------------------------------------
    time_kwargs = {
        "tinit": config.simulation_time.t_init,
        "tmax": config.simulation_time.t_end,
        "dt": config.simulation_time.dt_init,
    }
    print_array = list(config.output_settings.print_times)
    if print_array:
        time_kwargs["print_times"] = True
        time_kwargs["print_array"] = print_array
    if config.output_settings.print_interval is not None:
        time_kwargs["dtprint"] = config.output_settings.print_interval
    ml.add_time_info(**time_kwargs)

    # --- 3. Water flow + boundary conditions -----------------------------
    top_bc = _TOP_BC_MAP.get(config.upper_boundary.type)
    if top_bc is None:
        raise UnsupportedFeatureError(
            f"upper_boundary.type={config.upper_boundary.type.value!r} "
            "is not supported in milestone 2."
        )
    bot_bc = _BOT_BC_MAP.get(config.lower_boundary.type)
    if bot_bc is None:
        raise UnsupportedFeatureError(
            f"lower_boundary.type={config.lower_boundary.type.value!r} "
            "is not supported in milestone 2."
        )

    waterflow_kwargs = {"top_bc": top_bc, "bot_bc": bot_bc}
    if config.upper_boundary.flux is not None:
        waterflow_kwargs["rtop"] = config.upper_boundary.flux
    if config.lower_boundary.flux is not None:
        waterflow_kwargs["rbot"] = config.lower_boundary.flux
    ml.add_waterflow(**waterflow_kwargs)

    if config.upper_boundary.type == UpperBoundaryType.atmospheric:
        _add_atmospheric_forcing(ml, config)

    if _solute_enabled(config):
        _add_solute_transport_settings(ml, config)

    # --- 4. Materials (sorted by material_id, 1-based row index) ---------
    sorted_vg = sorted(config.van_genuchten, key=lambda v: v.material_id)
    material_df = ml.get_empty_material_df(n=len(sorted_vg))
    id_to_row: Dict[int, int] = {}
    for row_idx, vg in enumerate(sorted_vg, start=1):
        # Phydrus material_df has MultiIndex columns [(water, thr), (water, ths),
        # (water, Alfa), (water, n), (water, Ks), (water, l)]. Positional
        # assignment is avoided so optional solute columns can coexist.
        material_df.loc[row_idx, ("water", "thr")] = vg.theta_r
        material_df.loc[row_idx, ("water", "ths")] = vg.theta_s
        material_df.loc[row_idx, ("water", "Alfa")] = vg.alpha
        material_df.loc[row_idx, ("water", "n")] = vg.n
        material_df.loc[row_idx, ("water", "Ks")] = vg.Ks
        material_df.loc[row_idx, ("water", "l")] = vg.l
        if _solute_enabled(config):
            species = config.solute_transport.species[0]
            material_df.loc[row_idx, ("solute", "bulk.d")] = 1.0
            material_df.loc[row_idx, ("solute", "DisperL")] = species.dispersivity
            material_df.loc[row_idx, ("solute", "frac")] = 1.0
            material_df.loc[row_idx, ("solute", "mobile_wc")] = 0.0
        id_to_row[vg.material_id] = row_idx
    ml.add_material(material_df)

    if _solute_enabled(config):
        _add_solute_species(ml, config)

    if config.root_uptake is not None and config.root_uptake.enabled:
        _add_root_uptake(ml, config)

    # --- 5. Initial condition --------------------------------------------
    if config.initial_condition.type == InitialConditionType.water_content:
        raise UnsupportedFeatureError(
            "initial_condition.type='water_content' is not supported in "
            "milestone 2. Use 'pressure_head' for now."
        )
    if config.initial_condition.profile:
        h_init = config.initial_condition.profile[0].value
    else:
        h_init = config.initial_condition.value

    # --- 6. Soil profile -------------------------------------------------
    # Config uses positive depths (down). Phydrus uses negative x (up=0).
    profile_top_x = -config.soil_profile[0].depth_top      # typically 0.0
    profile_bot_x = -config.soil_profile[-1].depth_bottom  # negative
    first_layer_row = id_to_row[config.soil_profile[0].material_id]

    profile = ps.create_profile(
        top=profile_top_x,
        bot=profile_bot_x,
        dx=dx,
        h=h_init,
        mat=first_layer_row,
    )

    if config.initial_condition.profile:
        points = sorted(
            config.initial_condition.profile,
            key=lambda point: point.depth,
        )
        profile["h"] = [
            _interpolate_initial_head(-float(x), points)
            for x in profile["x"]
        ]

    # Override Mat for layers other than the first.
    for layer in config.soil_profile[1:]:
        x_upper = -layer.depth_top      # less negative (closer to surface)
        x_lower = -layer.depth_bottom   # more negative (deeper)
        mask = (profile["x"] <= x_upper) & (profile["x"] >= x_lower)
        profile.loc[mask, "Mat"] = id_to_row[layer.material_id]
    if config.root_uptake is not None and config.root_uptake.enabled:
        _apply_root_distribution(profile, config)
    if _solute_enabled(config):
        _apply_initial_solute_concentration(profile, config)
    ml.add_profile(profile)

    # --- 7. Observation nodes --------------------------------------------
    if config.observation_depths:
        ml.add_obs_nodes([-d for d in config.observation_depths])

    # --- 8. Write inputs (NEVER simulate in this milestone) --------------
    ml.write_input()

    return project_dir


def _add_atmospheric_forcing(ml, config: ModelConfig) -> None:
    """Pass simple water-flow atmospheric forcing records to phydrus."""
    try:
        import pandas as pd
    except ImportError as exc:
        raise UnsupportedFeatureError(
            "pandas is required to generate atmospheric boundary input."
        ) from exc

    if config.atmospheric is None or not config.atmospheric.records:
        raise UnsupportedFeatureError(
            "Atmospheric upper boundary requires atmospheric.records."
        )

    root_demand = 0.0
    if config.root_uptake is not None and config.root_uptake.enabled:
        root_demand = float(config.root_uptake.potential_transpiration)

    atmosphere = pd.DataFrame(
        [
            {
                "tAtm": time,
                "Prec": record.precipitation,
                "rSoil": record.evaporation,
                # HYDRUS stores potential transpiration demand in ATMOSPH.IN
                # as rRoot. Actual extraction is reduced by the sink model and
                # the PROFILE.DAT Beta distribution.
                "rRoot": root_demand,
                "hCritA": record.hCritA,
            }
            for time, record in _hydrus_atmospheric_records(config)
        ]
    )
    ml.add_atmospheric_bc(
        atmosphere,
        tatm=0.0,
        prec=0.0,
        rsoil=0.0,
        rroot=0.0,
        hcrita=-10000.0,
        rb=0.0,
        hb=0.0,
        ht=0.0,
        ttop=0.0,
        tbot=0.0,
        ampl=0.0,
    )


def _solute_enabled(config: ModelConfig) -> bool:
    return (
        config.solute_transport is not None
        and config.solute_transport.enabled
    )


def _add_solute_transport_settings(ml, config: ModelConfig) -> None:
    """Enable one conservative solute using Phydrus's Block F writer."""
    solute = config.solute_transport
    if solute is None or not solute.enabled:
        return
    if solute.model.value != "conservative":
        raise UnsupportedFeatureError(
            "Only solute_transport.model='conservative' is supported"
        )
    if len(solute.species) != 1:
        raise UnsupportedFeatureError(
            "Only one conservative solute species is supported"
        )

    species = solute.species[0]
    bot_bc = 1 if species.lower_boundary_concentration is not None else 0
    ml.add_solute_transport(
        model=0,
        epsi=0.5,
        lupw=False,
        lartd=False,
        ltdep=False,
        ctola=0,
        ctolr=0,
        maxit=1,
        pecr=2,
        ltort=True,
        top_bc=-1,
        bot_bc=bot_bc,
        tpulse=config.simulation_time.t_end - config.simulation_time.t_init,
    )


def _add_solute_species(ml, config: ModelConfig) -> None:
    """Write conservative solute parameters for all materials.

    Phydrus writes the HYDRUS solute-reaction row from this DataFrame. For a
    conservative tracer, sorption, decay, production, and gas exchange terms
    remain zero. ``beta=1`` is HYDRUS's neutral exponent value.
    """
    species = config.solute_transport.species[0]
    solute_df = ml.get_empty_solute_df()
    solute_df.loc[:, :] = 0.0
    if "beta" in solute_df.columns:
        solute_df.loc[:, "beta"] = 1.0

    ml.add_solute(
        solute_df,
        difw=species.diffusion_coefficient,
        difg=0.0,
        top_conc=species.upper_boundary_concentration,
        bot_conc=(
            species.lower_boundary_concentration
            if species.lower_boundary_concentration is not None
            else 0.0
        ),
    )


def _apply_initial_solute_concentration(profile, config: ModelConfig) -> None:
    species = config.solute_transport.species[0]
    profile["Conc"] = float(species.initial_concentration)
    if "SConc" in profile.columns:
        profile["SConc"] = 0.0


def _add_root_uptake(ml, config: ModelConfig) -> None:
    """Enable HYDRUS root water uptake using phydrus's Feddes sink block.

    The schema exposes this as ``model='simple'``. Internally, phydrus writes
    HYDRUS SELECTOR.IN Block G with the Feddes stress response defaults. The
    requested transpiration demand is supplied through ATMOSPH.IN rRoot, while
    PROFILE.DAT Beta controls where uptake can occur.
    """
    if config.root_uptake is None or not config.root_uptake.enabled:
        return
    if config.root_uptake.model.value != "simple":
        raise UnsupportedFeatureError(
            f"root_uptake.model={config.root_uptake.model.value!r} is not supported"
        )
    if config.root_uptake.distribution.value != "uniform":
        raise UnsupportedFeatureError(
            "Only root_uptake.distribution='uniform' is supported"
        )

    ml.add_root_uptake(
        model=0,
        # Phydrus requires POptm values for every material when writing Block G.
        poptm=[-25.0 for _ in config.van_genuchten],
    )


def _apply_root_distribution(profile, config: ModelConfig) -> None:
    """Write a simple uniform root distribution into PROFILE.DAT Beta.

    Config depths are positive downward. Phydrus profile coordinates are
    negative below the soil surface. HYDRUS reads ``Beta`` as the relative root
    distribution factor: 1 inside the root zone, 0 below it.
    """
    root_depth = float(config.root_uptake.root_depth)
    profile["Beta"] = [
        1.0 if -float(x) <= root_depth + 1e-12 else 0.0
        for x in profile["x"]
    ]


def _hydrus_atmospheric_records(config: ModelConfig):
    """Yield HYDRUS-compatible atmospheric record times and records.

    HYDRUS rejects a first time-variable boundary record at ``tInit`` and this
    command-line build also rejects equality with ``tInit + dtInit``. A config
    record at the simulation start is interpreted as early forcing and written
    just after the first numerical interval.
    """
    first_allowed_time = (
        config.simulation_time.t_init + 2 * config.simulation_time.dt_init
    )
    previous_time = None
    for idx, record in enumerate(config.atmospheric.records):
        time = record.time
        if idx == 0 and time < first_allowed_time:
            time = first_allowed_time
        if previous_time is not None and time <= previous_time:
            raise UnsupportedFeatureError(
                "Atmospheric records must remain strictly increasing after "
                "the first HYDRUS interval adjustment."
            )
        previous_time = time
        yield time, record


def _interpolate_initial_head(depth: float, points) -> float:
    """Linearly interpolate an initial pressure head profile by depth."""
    if depth <= points[0].depth:
        return points[0].value
    if depth >= points[-1].depth:
        return points[-1].value
    for upper, lower in zip(points, points[1:]):
        if upper.depth <= depth <= lower.depth:
            fraction = (depth - upper.depth) / (lower.depth - upper.depth)
            return upper.value + fraction * (lower.value - upper.value)
    return points[-1].value
