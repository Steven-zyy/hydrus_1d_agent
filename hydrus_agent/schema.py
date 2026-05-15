"""Pydantic models for the HYDRUS-1D agent configuration.

Only the fields needed for milestone 1 (read + validate JSON) are modelled.
Later milestones may extend these models, but should keep backward
compatibility with existing example configs where possible.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TimeUnits(str, Enum):
    seconds = "seconds"
    minutes = "minutes"
    hours = "hours"
    days = "days"


class InitialConditionType(str, Enum):
    pressure_head = "pressure_head"
    water_content = "water_content"


class UpperBoundaryType(str, Enum):
    atmospheric = "atmospheric"
    constant_flux = "constant_flux"
    constant_head = "constant_head"


class LowerBoundaryType(str, Enum):
    free_drainage = "free_drainage"
    constant_head = "constant_head"
    constant_flux = "constant_flux"
    seepage_face = "seepage_face"


class RootUptakeModel(str, Enum):
    simple = "simple"


class RootDistribution(str, Enum):
    uniform = "uniform"


class SoluteTransportModel(str, Enum):
    conservative = "conservative"


class SimulationTime(BaseModel):
    t_init: float = Field(..., description="Start time")
    t_end: float = Field(..., description="End time")
    dt_init: float = Field(..., gt=0, description="Initial time step")
    units: TimeUnits = TimeUnits.days

    @model_validator(mode="after")
    def _check_time_window(self) -> "SimulationTime":
        if self.t_end <= self.t_init:
            raise ValueError(
                f"t_end ({self.t_end}) must be greater than t_init ({self.t_init})"
            )
        if self.dt_init >= (self.t_end - self.t_init):
            raise ValueError(
                f"dt_init ({self.dt_init}) must be smaller than the simulation "
                f"window ({self.t_end - self.t_init})"
            )
        return self


class SoilLayer(BaseModel):
    depth_top: float = Field(..., ge=0, description="Top depth (m, positive down)")
    depth_bottom: float = Field(..., gt=0, description="Bottom depth (m, positive down)")
    material_id: int = Field(..., ge=1, description="Material reference id")

    @model_validator(mode="after")
    def _check_depths(self) -> "SoilLayer":
        if self.depth_bottom <= self.depth_top:
            raise ValueError(
                f"depth_bottom ({self.depth_bottom}) must be greater than "
                f"depth_top ({self.depth_top})"
            )
        return self


class VanGenuchtenParams(BaseModel):
    material_id: int = Field(..., ge=1)
    theta_r: float = Field(..., ge=0, le=1, description="Residual water content")
    theta_s: float = Field(..., gt=0, le=1, description="Saturated water content")
    alpha: float = Field(..., gt=0, description="van Genuchten alpha (1/m)")
    n: float = Field(..., gt=1, description="van Genuchten n (must be > 1)")
    Ks: float = Field(..., gt=0, description="Saturated hydraulic conductivity")
    l: float = Field(0.5, description="Pore connectivity parameter")

    @model_validator(mode="after")
    def _check_theta(self) -> "VanGenuchtenParams":
        if self.theta_s <= self.theta_r:
            raise ValueError(
                f"theta_s ({self.theta_s}) must be greater than theta_r ({self.theta_r})"
            )
        return self


class MaterialSourceRow(BaseModel):
    name: str
    material_id: int = Field(..., ge=1)
    theta_r: float = Field(..., ge=0)
    theta_s: float = Field(..., gt=0)
    alpha: float = Field(..., gt=0)
    n: float = Field(..., gt=1)
    Ks: float = Field(..., gt=0)
    l: float


class MaterialSourceMetadata(BaseModel):
    source_type: str = "csv"
    source_csv: str
    material_count: int = Field(..., ge=1)
    material_names: List[str]
    name_to_material_id: Dict[str, int]
    materials: List[MaterialSourceRow]
    theta_unit: str = "-"
    alpha_unit: str = "1/m"
    ks_unit: str = "m/day"
    l_unit: str = "-"


class InitialCondition(BaseModel):
    type: InitialConditionType
    value: Optional[float] = Field(
        None,
        description="Uniform pressure head (m), water content (-), or top value "
                    "when a profile is provided",
    )
    profile: Optional[List["InitialConditionPoint"]] = Field(
        None,
        description="Optional depth-value profile for pressure head, depth positive down",
    )

    @model_validator(mode="after")
    def _check_value_or_profile(self) -> "InitialCondition":
        if self.value is None and not self.profile:
            raise ValueError("initial_condition requires either value or profile")
        if self.profile and len(self.profile) < 2:
            raise ValueError("initial_condition.profile requires at least two points")
        if self.profile and self.type != InitialConditionType.pressure_head:
            raise ValueError("initial_condition.profile is only supported for pressure_head")
        return self


class InitialConditionPoint(BaseModel):
    depth: float = Field(..., ge=0, description="Depth in m, positive down")
    value: float = Field(..., description="Pressure head at this depth")


class UpperBoundary(BaseModel):
    type: UpperBoundaryType
    flux: Optional[float] = None
    head: Optional[float] = None


class AtmosphericRecord(BaseModel):
    time: float = Field(..., description="Atmospheric record time")
    precipitation: float = Field(
        ...,
        ge=0,
        description="Precipitation/infiltration flux rate, positive value",
    )
    evaporation: float = Field(
        ...,
        ge=0,
        description="Potential soil evaporation rate, positive value",
    )
    hCritA: float = Field(
        -10000.0,
        description="Minimum allowed pressure head at the soil surface",
    )


class AtmosphericCsvUnits(BaseModel):
    time: str = "day"
    length: str = "m"


class AtmosphericSourceMetadata(BaseModel):
    source_type: str = "csv"
    source_csv: str
    record_count: int = Field(..., ge=1)
    time_range: List[float]
    total_precipitation: float = Field(..., ge=0)
    total_potential_evaporation: float = Field(..., ge=0)
    max_precipitation_rate: float = Field(..., ge=0)
    max_potential_evaporation_rate: float = Field(..., ge=0)
    time_unit: str = "day"
    length_unit: str = "m"
    rate_unit: str = "m/day"
    covers_simulation_end_time: bool


class AtmosphericForcing(BaseModel):
    enabled: bool = False
    records: List[AtmosphericRecord] = Field(default_factory=list)
    source_csv: Optional[str] = None
    time_column: str = "time_d"
    precipitation_column: str = "precipitation_m_d"
    potential_evaporation_column: str = "potential_evaporation_m_d"
    units: Optional[AtmosphericCsvUnits] = None
    source_metadata: Optional[AtmosphericSourceMetadata] = None
    hCritA: float = -10000.0

    @model_validator(mode="after")
    def _check_records_when_enabled(self) -> "AtmosphericForcing":
        if self.enabled and not self.records:
            raise ValueError("atmospheric.records is required when atmospheric.enabled=true")
        times = [record.time for record in self.records]
        if any(b <= a for a, b in zip(times, times[1:])):
            raise ValueError("atmospheric.records times must be strictly increasing")
        return self


class RootUptake(BaseModel):
    enabled: bool = False
    model: RootUptakeModel = RootUptakeModel.simple
    root_depth: Optional[float] = Field(
        None,
        gt=0,
        description="Rooting depth in m, positive downward from the soil surface",
    )
    potential_transpiration: Optional[float] = Field(
        None,
        gt=0,
        description="Potential transpiration/root water uptake demand",
    )
    distribution: RootDistribution = RootDistribution.uniform

    @model_validator(mode="after")
    def _check_required_when_enabled(self) -> "RootUptake":
        if self.enabled:
            if self.root_depth is None:
                raise ValueError("root_uptake.root_depth is required when enabled")
            if self.potential_transpiration is None:
                raise ValueError(
                    "root_uptake.potential_transpiration is required when enabled"
                )
        return self


class SoluteSpecies(BaseModel):
    """Single conservative solute species supported by Milestone 16."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    initial_concentration: float = Field(..., ge=0)
    upper_boundary_concentration: float = Field(..., ge=0)
    lower_boundary_concentration: Optional[float] = Field(None, ge=0)
    diffusion_coefficient: float = Field(0.0, ge=0)
    dispersivity: float = Field(..., ge=0)


class SoluteTransport(BaseModel):
    """Minimal one-solute conservative transport configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    model: SoluteTransportModel = SoluteTransportModel.conservative
    species: List[SoluteSpecies] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_one_conservative_species(self) -> "SoluteTransport":
        if not self.enabled:
            return self
        if self.model != SoluteTransportModel.conservative:
            raise ValueError("Only solute_transport.model='conservative' is supported")
        if len(self.species) != 1:
            raise ValueError(
                "Milestone 16 supports exactly one solute species; "
                "multiple solutes are not supported"
            )
        return self


class LowerBoundary(BaseModel):
    type: LowerBoundaryType
    flux: Optional[float] = None
    head: Optional[float] = None


class OutputSettings(BaseModel):
    print_times: List[float] = Field(default_factory=list)
    print_interval: Optional[float] = Field(None, gt=0)

    @field_validator("print_times")
    @classmethod
    def _check_monotonic(cls, v: List[float]) -> List[float]:
        if any(b <= a for a, b in zip(v, v[1:])):
            raise ValueError("print_times must be strictly increasing")
        return v


class ModelConfig(BaseModel):
    project_name: str = Field(..., min_length=1)
    case_id: str = Field(..., pattern=r"^[A-Za-z0-9_\-]+$")
    simulation_time: SimulationTime
    soil_profile: List[SoilLayer] = Field(..., min_length=1)
    van_genuchten: List[VanGenuchtenParams] = Field(..., min_length=1)
    initial_condition: InitialCondition
    upper_boundary: UpperBoundary
    lower_boundary: LowerBoundary
    atmospheric: Optional[AtmosphericForcing] = None
    material_source: Optional[MaterialSourceMetadata] = None
    root_uptake: Optional[RootUptake] = None
    solute_transport: Optional[SoluteTransport] = None
    observation_depths: List[float] = Field(default_factory=list)
    output_settings: OutputSettings

    @model_validator(mode="after")
    def _cross_field_checks(self) -> "ModelConfig":
        # 1. Soil profile must be contiguous and ordered top-down.
        for prev, nxt in zip(self.soil_profile, self.soil_profile[1:]):
            if abs(nxt.depth_top - prev.depth_bottom) > 1e-9:
                raise ValueError(
                    f"Soil layers must be contiguous: layer ending at "
                    f"{prev.depth_bottom} is followed by a layer starting at "
                    f"{nxt.depth_top}"
                )

        # 2. Every material referenced by a layer must have van Genuchten params.
        layer_materials = {layer.material_id for layer in self.soil_profile}
        vg_materials = {vg.material_id for vg in self.van_genuchten}
        missing = layer_materials - vg_materials
        if missing:
            raise ValueError(
                f"Soil profile references material(s) {sorted(missing)} that have "
                f"no van Genuchten parameters defined"
            )

        # 3. Observation depths must lie within the soil profile.
        profile_top = self.soil_profile[0].depth_top
        profile_bottom = self.soil_profile[-1].depth_bottom
        for d in self.observation_depths:
            if d < profile_top or d > profile_bottom:
                raise ValueError(
                    f"Observation depth {d} is outside the soil profile "
                    f"[{profile_top}, {profile_bottom}]"
                )

        # 4. Print times must lie inside the simulation window.
        for t in self.output_settings.print_times:
            if t < self.simulation_time.t_init or t > self.simulation_time.t_end:
                raise ValueError(
                    f"print_time {t} is outside the simulation window "
                    f"[{self.simulation_time.t_init}, {self.simulation_time.t_end}]"
                )

        # 4a. Atmospheric upper boundaries require explicit ATMOSPH records.
        if self.upper_boundary.type == UpperBoundaryType.atmospheric:
            if (
                self.atmospheric is None
                or not self.atmospheric.enabled
                or not self.atmospheric.records
            ):
                raise ValueError(
                    "upper_boundary.type='atmospheric' requires "
                    "atmospheric.enabled=true and atmospheric.records"
                )
            for record in self.atmospheric.records:
                if (
                    record.time < self.simulation_time.t_init
                    or record.time > self.simulation_time.t_end
                ):
                    raise ValueError(
                        f"atmospheric record time {record.time} is outside "
                        f"the simulation window "
                        f"[{self.simulation_time.t_init}, {self.simulation_time.t_end}]"
                    )
        elif self.atmospheric is not None and self.atmospheric.enabled:
            raise ValueError(
                "atmospheric.enabled=true requires upper_boundary.type='atmospheric'"
            )

        # 4b. Minimal root uptake is currently tied to atmospheric forcing.
        if self.root_uptake is not None and self.root_uptake.enabled:
            if self.upper_boundary.type != UpperBoundaryType.atmospheric:
                raise ValueError(
                    "root uptake currently requires upper_boundary.type='atmospheric'"
                )
            if (
                self.atmospheric is None
                or not self.atmospheric.enabled
                or not self.atmospheric.records
            ):
                raise ValueError(
                    "root uptake currently requires atmospheric forcing records"
                )
            if self.root_uptake.root_depth is not None:
                profile_bottom = self.soil_profile[-1].depth_bottom
                if self.root_uptake.root_depth > profile_bottom:
                    raise ValueError(
                        "root_uptake.root_depth must be within the soil profile "
                        f"[0, {profile_bottom}]"
                    )

        # 5. Initial-condition profiles must be ordered and within the column.
        if self.initial_condition.profile:
            profile_top = self.soil_profile[0].depth_top
            profile_bottom = self.soil_profile[-1].depth_bottom
            depths = [point.depth for point in self.initial_condition.profile]
            if any(b <= a for a, b in zip(depths, depths[1:])):
                raise ValueError("initial_condition.profile depths must increase")
            for depth in depths:
                if depth < profile_top or depth > profile_bottom:
                    raise ValueError(
                        f"Initial condition profile depth {depth} is outside "
                        f"the soil profile [{profile_top}, {profile_bottom}]"
                    )

        return self
