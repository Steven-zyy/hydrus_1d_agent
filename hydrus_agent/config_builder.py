"""Rule-based natural-language configuration builder (milestone 8).

This module deliberately does not call online APIs, phydrus, or HYDRUS.
It translates a constrained description of a simple 1D case into a
``ModelConfig`` and lets the existing Pydantic schema do the final validation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Union

from pydantic import ValidationError

from hydrus_agent.schema import ModelConfig
from hydrus_agent.validator import _resolve_atmospheric_csv, _resolve_material_csv


class ConfigBuildError(ValueError):
    """Raised when a natural-language description cannot be converted safely."""


@dataclass
class ConfigBuildResult:
    """A validated config plus non-fatal assumptions made while building it."""

    config: ModelConfig
    warnings: List[str] = field(default_factory=list)


_SOIL_TEMPLATES: Dict[str, Dict[str, float]] = {
    "sand": {
        "theta_r": 0.045,
        "theta_s": 0.43,
        "alpha": 14.5,
        "n": 2.68,
        "Ks": 7.128,
        "l": 0.5,
    },
    "sandy loam": {
        "theta_r": 0.065,
        "theta_s": 0.41,
        "alpha": 7.5,
        "n": 1.89,
        "Ks": 1.061,
        "l": 0.5,
    },
    "loam": {
        "theta_r": 0.078,
        "theta_s": 0.43,
        "alpha": 3.6,
        "n": 1.56,
        "Ks": 0.2496,
        "l": 0.5,
    },
    "silt loam": {
        "theta_r": 0.067,
        "theta_s": 0.45,
        "alpha": 2.0,
        "n": 1.41,
        "Ks": 0.108,
        "l": 0.5,
    },
    "clay loam": {
        "theta_r": 0.095,
        "theta_s": 0.41,
        "alpha": 1.9,
        "n": 1.31,
        "Ks": 0.0624,
        "l": 0.5,
    },
    "clay": {
        "theta_r": 0.068,
        "theta_s": 0.38,
        "alpha": 0.8,
        "n": 1.09,
        "Ks": 0.0048,
        "l": 0.5,
    },
}

_TEXTURES = sorted(_SOIL_TEMPLATES, key=len, reverse=True)
_TIME_UNITS = {
    "second": "seconds",
    "seconds": "seconds",
    "sec": "seconds",
    "secs": "seconds",
    "minute": "minutes",
    "minutes": "minutes",
    "min": "minutes",
    "mins": "minutes",
    "hour": "hours",
    "hours": "hours",
    "hr": "hours",
    "hrs": "hours",
    "day": "days",
    "days": "days",
    "d": "days",
}
_LENGTH_TO_M = {
    "m": 1.0,
    "meter": 1.0,
    "meters": 1.0,
    "metre": 1.0,
    "metres": 1.0,
    "cm": 0.01,
    "centimeter": 0.01,
    "centimeters": 0.01,
    "centimetre": 0.01,
    "centimetres": 0.01,
    "mm": 0.001,
    "millimeter": 0.001,
    "millimeters": 0.001,
    "millimetre": 0.001,
    "millimetres": 0.001,
}
_SECONDS_PER_UNIT = {
    "seconds": 1.0,
    "minutes": 60.0,
    "hours": 3600.0,
    "days": 86400.0,
}


def build_config_from_description(
    description: str,
    *,
    case_id: str = "from_description",
    project_name: Optional[str] = None,
) -> ConfigBuildResult:
    """Build and validate a ``ModelConfig`` from constrained natural language.

    The parser is intentionally conservative. Unsupported or ambiguous
    features raise ``ConfigBuildError`` instead of guessing silently.
    """
    if not description or not description.strip():
        raise ConfigBuildError("Description is empty.")

    text = _normalise(description)

    warnings: List[str] = []
    t_end, time_units = _parse_simulation_time(text)
    material_csv_source = _parse_material_csv_source(text)
    soil_profile, van_genuchten = _parse_soils(text)
    if material_csv_source is not None:
        soil_profile = _soil_layers_for_material_csv(soil_profile)
        van_genuchten = {"source_csv": material_csv_source}
    atmospheric = _parse_atmospheric_forcing(
        text,
        t_end=t_end,
        target_time_units=time_units,
    )
    root_uptake = _parse_root_uptake(
        text,
        target_time_units=time_units,
    )
    solute_transport = _parse_solute_transport(text)
    upper_boundary = (
        {"type": "atmospheric"}
        if atmospheric is not None
        else _parse_upper_boundary(text, target_time_units=time_units)
    )
    if root_uptake is not None and atmospheric is None:
        raise ConfigBuildError(
            "Root uptake descriptions currently require atmospheric forcing "
            "with rainfall or precipitation records."
        )
    lower_boundary = _parse_lower_boundary(text, target_time_units=time_units)
    initial_condition = _parse_initial_condition(text)
    observation_depths = _parse_observation_depths(text)
    profile_bottom = soil_profile[-1]["depth_bottom"]
    if any(d < 0 or d > profile_bottom for d in observation_depths):
        raise ConfigBuildError(
            "Observation depths must be within the described soil column."
        )

    print_times = _parse_print_times(text)
    if not print_times:
        print_times = [round(t_end * f, 10) for f in (0.25, 0.5, 0.75, 1.0)]
        warnings.append(
            "No print times found; using quarter-window print times."
        )

    dt_init = min(t_end / 1000.0, 0.001 if time_units == "days" else t_end / 100.0)
    if dt_init <= 0 or dt_init >= t_end:
        dt_init = t_end / 1000.0

    raw = {
        "project_name": project_name or "natural language HYDRUS model",
        "case_id": _clean_case_id(case_id),
        "simulation_time": {
            "t_init": 0.0,
            "t_end": t_end,
            "dt_init": dt_init,
            "units": time_units,
        },
        "soil_profile": soil_profile,
        "van_genuchten": van_genuchten,
        "initial_condition": initial_condition,
        "upper_boundary": upper_boundary,
        "lower_boundary": lower_boundary,
        "atmospheric": atmospheric,
        "root_uptake": root_uptake,
        "solute_transport": solute_transport,
        "observation_depths": observation_depths,
        "output_settings": {
            "print_times": print_times,
            "print_interval": _default_print_interval(t_end),
        },
    }
    raw = _resolve_csv_sources_for_builder(raw)

    try:
        config = ModelConfig.model_validate(raw)
    except ValidationError as exc:
        details = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "<root>"
            details.append(f"{loc}: {err['msg']}")
        raise ConfigBuildError(
            "Generated config failed validation: " + "; ".join(details)
        ) from exc

    return ConfigBuildResult(config=config, warnings=warnings)


_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _make_relative_if_under_root(path_str: str) -> str:
    """Return a POSIX-style relative path if *path_str* is inside the project root.

    Keeps paths portable: configs written in the worktree or on any machine
    will contain relative paths that resolve from the project root rather than
    absolute machine-specific paths.
    """
    try:
        abs_path = Path(path_str).resolve()
        return abs_path.relative_to(_PROJECT_ROOT).as_posix()
    except (ValueError, OSError):
        return path_str


def write_config(config: ModelConfig, path: Union[str, Path]) -> Path:
    """Write a validated config to JSON and return the written path."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(_config_dump_for_user(config), indent=2),
        encoding="utf-8",
    )
    return out_path


def _config_dump_for_user(config: ModelConfig) -> Dict[str, object]:
    raw = config.model_dump(mode="json")
    if config.atmospheric and config.atmospheric.source_csv:
        atmospheric = raw.get("atmospheric")
        if isinstance(atmospheric, dict):
            atmospheric.pop("records", None)
            atmospheric.pop("source_metadata", None)
            if isinstance(atmospheric.get("source_csv"), str):
                atmospheric["source_csv"] = _make_relative_if_under_root(
                    atmospheric["source_csv"]
                )
    if config.material_source is not None:
        raw["van_genuchten"] = {
            "source_csv": _make_relative_if_under_root(config.material_source.source_csv),
        }
        id_to_name = {
            material_id: name
            for name, material_id in config.material_source.name_to_material_id.items()
        }
        layers = []
        for layer in config.soil_profile:
            layer_raw = layer.model_dump(mode="json")
            material_name = id_to_name.get(layer.material_id)
            if material_name is not None:
                layer_raw["material"] = material_name
                layer_raw.pop("material_id", None)
            layers.append(layer_raw)
        raw["soil_profile"] = layers
        raw.pop("material_source", None)
    return raw


def summarise_built_config(result: ConfigBuildResult) -> str:
    """Return a concise human-readable summary for CLI output."""
    cfg = result.config
    if cfg.initial_condition.profile:
        points = [
            f"{point.value} m at {point.depth} m"
            for point in cfg.initial_condition.profile
        ]
        initial_summary = "profile (" + " to ".join(points) + ")"
    else:
        initial_summary = f"{cfg.initial_condition.value} m"

    lines = [
        "Generated HYDRUS-1D config",
        f"  project_name : {cfg.project_name}",
        f"  case_id      : {cfg.case_id}",
        f"  sim window   : {cfg.simulation_time.t_init} to "
        f"{cfg.simulation_time.t_end} {cfg.simulation_time.units.value}",
        f"  soil layers  : {len(cfg.soil_profile)}",
        f"  materials    : {len(cfg.van_genuchten)}",
        f"  upper BC     : {cfg.upper_boundary.type.value}",
        f"  lower BC     : {cfg.lower_boundary.type.value}",
        f"  initial head : {initial_summary}",
        f"  obs depths   : {cfg.observation_depths}",
        f"  print times  : {cfg.output_settings.print_times}",
    ]
    if cfg.root_uptake and cfg.root_uptake.enabled:
        lines.extend([
            "  root uptake  : enabled",
            f"    depth      : {cfg.root_uptake.root_depth} m",
            "    demand     : "
            f"{cfg.root_uptake.potential_transpiration} "
            f"m/{cfg.simulation_time.units.value}",
            f"    distribution: {cfg.root_uptake.distribution.value}",
        ])
    if cfg.solute_transport and cfg.solute_transport.enabled:
        species = cfg.solute_transport.species[0]
        lines.extend([
            "  solute      : conservative tracer",
            f"    initial c : {species.initial_concentration}",
            f"    upper c   : {species.upper_boundary_concentration}",
            f"    dispers.  : {species.dispersivity} m",
        ])
    if cfg.atmospheric and cfg.atmospheric.source_metadata:
        meta = cfg.atmospheric.source_metadata
        lines.extend([
            "  atmospheric CSV:",
            f"    path       : {meta.source_csv}",
            f"    records    : {meta.record_count}",
            f"    time range : {meta.time_range[0]} to {meta.time_range[1]} {meta.time_unit}",
            f"    total precip: {meta.total_precipitation} m",
            f"    total evap : {meta.total_potential_evaporation} m",
        ])
    if cfg.material_source:
        meta = cfg.material_source
        lines.extend([
            "  material CSV:",
            f"    path       : {meta.source_csv}",
            f"    materials  : {meta.material_count}",
            f"    names      : {', '.join(meta.material_names)}",
        ])
    if result.warnings:
        lines.append("  warnings     :")
        lines.extend(f"    - {warning}" for warning in result.warnings)
    lines.append("HYDRUS was not run.")
    return "\n".join(lines)


def _normalise(description: str) -> str:
    text = description.lower()
    text = text.replace("metres", "meters").replace("metre", "meter")
    text = text.replace("centimetres", "centimeters").replace("centimetre", "centimeter")
    text = text.replace("millimetres", "millimeters").replace("millimetre", "millimeter")
    return re.sub(r"\s+", " ", text).strip()


def _clean_case_id(case_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", case_id.strip())
    cleaned = cleaned.strip("_-")
    if not cleaned:
        raise ConfigBuildError("case_id must contain at least one letter or number.")
    return cleaned


def _parse_simulation_time(text: str) -> Tuple[float, str]:
    pattern = re.compile(
        r"\b([0-9]+(?:\.[0-9]+)?)\s*"
        r"-?\s*"
        r"(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|d)\b"
    )
    for match in pattern.finditer(text):
        if match.start() > 0 and text[match.start() - 1] in {"/", "-"}:
            continue
        value = float(match.group(1))
        unit = _TIME_UNITS[match.group(2)]
        if value <= 0:
            raise ConfigBuildError("Simulation duration must be positive.")
        return value, unit
    raise ConfigBuildError(
        "Could not find a simulation duration such as '1 day' or '12 hours'."
    )


def _parse_soils(text: str) -> Tuple[List[Dict[str, float]], List[Dict[str, float]]]:
    named_layer_matches = list(re.finditer(
        r"([a-z ]+?)\s+from\s+([0-9]+(?:\.[0-9]+)?)\s+to\s+"
        r"([0-9]+(?:\.[0-9]+)?)\s*"
        r"(m|meters?|cm|centimeters?|mm|millimeters?)",
        text,
    ))
    if named_layer_matches:
        layers = []
        material_by_texture: Dict[str, int] = {}
        materials = []
        for match in named_layer_matches:
            texture = _find_texture(match.group(1))
            top = _length_to_m(float(match.group(2)), match.group(4))
            bottom = _length_to_m(float(match.group(3)), match.group(4))
            material_id = material_by_texture.get(texture)
            if material_id is None:
                material_id = len(material_by_texture) + 1
                material_by_texture[texture] = material_id
                materials.append(_material_from_template(texture, material_id))
            layers.append({
                "depth_top": top,
                "depth_bottom": bottom,
                "material_id": material_id,
                "material": _material_name_for_csv(texture),
            })
        return layers, materials

    layer_matches = list(re.finditer(
        r"([0-9]+(?:\.[0-9]+)?)\s*-\s*([0-9]+(?:\.[0-9]+)?)\s*"
        r"(m|meters?|cm|centimeters?|mm|millimeters?)\s+"
        r"([a-z ]+?)(?=,|;|$)",
        text,
    ))
    if layer_matches:
        layers = []
        material_by_texture: Dict[str, int] = {}
        materials = []
        for match in layer_matches:
            top = _length_to_m(float(match.group(1)), match.group(3))
            bottom = _length_to_m(float(match.group(2)), match.group(3))
            texture = _find_texture(match.group(4))
            material_id = material_by_texture.get(texture)
            if material_id is None:
                material_id = len(material_by_texture) + 1
                material_by_texture[texture] = material_id
                materials.append(_material_from_template(texture, material_id))
            layers.append({
                "depth_top": top,
                "depth_bottom": bottom,
                "material_id": material_id,
                "material": _material_name_for_csv(texture),
            })
        return layers, materials

    over_match = re.search(
        r"([0-9]+(?:\.[0-9]+)?)\s*"
        r"(m|meters?|cm|centimeters?|mm|millimeters?)\s+"
        r"([a-z ]+?)\s+over\s+"
        r"([0-9]+(?:\.[0-9]+)?)\s*"
        r"(m|meters?|cm|centimeters?|mm|millimeters?)\s+"
        r"([a-z ]+?)(?=\.|,|;|$)",
        text,
    )
    if over_match:
        top_thickness = _length_to_m(float(over_match.group(1)), over_match.group(2))
        bottom_thickness = _length_to_m(float(over_match.group(4)), over_match.group(5))
        top_texture = _find_texture(over_match.group(3))
        bottom_texture = _find_texture(over_match.group(6))
        textures = [top_texture, bottom_texture]
        material_by_texture: Dict[str, int] = {}
        materials = []
        material_ids = []
        for texture in textures:
            material_id = material_by_texture.get(texture)
            if material_id is None:
                material_id = len(material_by_texture) + 1
                material_by_texture[texture] = material_id
                materials.append(_material_from_template(texture, material_id))
            material_ids.append(material_id)
        interface = top_thickness
        bottom = top_thickness + bottom_thickness
        return (
            [
                {
                    "depth_top": 0.0,
                    "depth_bottom": interface,
                    "material_id": material_ids[0],
                    "material": _material_name_for_csv(top_texture),
                },
                {
                    "depth_top": interface,
                    "depth_bottom": bottom,
                    "material_id": material_ids[1],
                    "material": _material_name_for_csv(bottom_texture),
                },
            ],
            materials,
        )

    depth_match = re.search(
        r"\b([0-9]+(?:\.[0-9]+)?)\s*"
        r"(m|meters?|cm|centimeters?|mm|millimeters?)\s+"
        r"(?:[a-z ]+?\s+)?column\b",
        text,
    )
    if not depth_match:
        raise ConfigBuildError("Could not find a column depth such as '1 m column'.")
    depth = _length_to_m(float(depth_match.group(1)), depth_match.group(2))
    texture = _find_texture(text)
    return (
        [
            {
                "depth_top": 0.0,
                "depth_bottom": depth,
                "material_id": 1,
                "material": _material_name_for_csv(texture),
            }
        ],
        [_material_from_template(texture, 1)],
    )


def _material_from_template(texture: str, material_id: int) -> Dict[str, float]:
    values = dict(_SOIL_TEMPLATES[texture])
    values["material_id"] = material_id
    return values


def _material_name_for_csv(texture: str) -> str:
    return texture.replace(" ", "_")


def _soil_layers_for_material_csv(
    soil_profile: List[Dict[str, object]],
) -> List[Dict[str, object]]:
    layers: List[Dict[str, object]] = []
    for layer in soil_profile:
        updated = dict(layer)
        material = updated.get("material")
        if material is None:
            material_id = int(updated.get("material_id", 0))
            material = f"material_{material_id}"
        updated["material"] = str(material)
        updated.pop("material_id", None)
        layers.append(updated)
    return layers


def _resolve_csv_sources_for_builder(raw: Dict[str, object]) -> Dict[str, object]:
    config_path = Path.cwd() / "_natural_language_config.json"
    try:
        raw = _resolve_material_csv(raw, config_path)
        raw = _resolve_atmospheric_csv(raw, config_path)
    except Exception as exc:
        raise ConfigBuildError(str(exc)) from exc
    return raw


def _find_texture(text: str) -> str:
    for texture in _TEXTURES:
        if re.search(rf"\b{re.escape(texture)}\b", text):
            return texture
    raise ConfigBuildError(
        "Could not identify a supported soil texture. Supported textures: "
        + ", ".join(sorted(_SOIL_TEMPLATES))
        + "."
    )


def _parse_upper_boundary(text: str, *, target_time_units: str) -> Dict[str, float]:
    if "atmospheric" in text or "atmosph.in" in text:
        raise ConfigBuildError(
            "Atmospheric upper boundary descriptions need rainfall or "
            "precipitation and optional evaporation rates, for example "
            "'rainfall 1 mm/day and evaporation 0 mm/day'."
        )

    head = _parse_boundary_head(text, "upper")
    if head is not None:
        return {"type": "constant_head", "head": head}

    rate = _parse_rate(text, target_time_units=target_time_units)
    if rate is not None:
        return {"type": "constant_flux", "flux": rate}

    if "constant flux" in text or "infiltration" in text:
        raise ConfigBuildError(
            "Upper boundary mentions flux or infiltration but no rate was found."
        )
    raise ConfigBuildError(
        "Could not identify an upper boundary. Use constant flux, infiltration, "
        "or constant head."
    )


def _parse_atmospheric_forcing(
    text: str,
    *,
    t_end: float,
    target_time_units: str,
) -> Optional[Dict[str, object]]:
    if "atmospheric" not in text and "atmosph.in" not in text:
        csv_source = _parse_atmospheric_csv_source(text)
        if csv_source is None:
            return None
    else:
        csv_source = _parse_atmospheric_csv_source(text)

    if csv_source is not None:
        return {
            "enabled": True,
            "source_csv": csv_source,
            "time_column": "time_d",
            "precipitation_column": "precipitation_m_d",
            "potential_evaporation_column": "potential_evaporation_m_d",
            "units": {
                "time": "day",
                "length": "m",
            },
        }

    precipitation = _parse_labeled_rate(
        text,
        labels=("rainfall", "rain", "precipitation", "precip"),
        target_time_units=target_time_units,
    )
    if precipitation is None:
        raise ConfigBuildError(
            "Atmospheric upper boundary descriptions need a rainfall or "
            "precipitation rate."
        )

    evaporation = _parse_labeled_rate(
        text,
        labels=("evaporation", "evap"),
        target_time_units=target_time_units,
    )
    if evaporation is None:
        evaporation = 0.0

    hcrita = _parse_hcrita(text)
    return {
        "enabled": True,
        "records": [
            {
                "time": 0.0,
                "precipitation": 0.0,
                "evaporation": 0.0,
                "hCritA": hcrita,
            },
            {
                "time": t_end,
                "precipitation": precipitation,
                "evaporation": evaporation,
                "hCritA": hcrita,
            },
        ],
    }


def _parse_atmospheric_csv_source(text: str) -> Optional[str]:
    return _parse_source_csv(
        text,
        (
            r"atmospheric\s+upper\s+boundary\s+forcing\s+from",
            r"atmospheric\s+boundary\s+from",
            r"rainfall\s+and\s+evaporation\s+from",
            r"use\s+atmosphere\s+csv",
            r"use\s+atmospheric\s+forcing\s+csv",
        ),
    )


def _parse_material_csv_source(text: str) -> Optional[str]:
    return _parse_source_csv(
        text,
        (
            r"material\s+hydraulic\s+parameters\s+from",
            r"van\s+genuchten\s+parameters\s+from",
            r"vg\s+parameters\s+from",
            r"use\s+material\s+csv",
            r"use\s+soil\s+hydraulic\s+parameter\s+csv",
        ),
    )


def _parse_source_csv(text: str, prefixes: Iterable[str]) -> Optional[str]:
    for prefix in prefixes:
        match = re.search(
            rf"\b{prefix}\s+([^\s,;]+\.csv)\b",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            return match.group(1).strip().strip("\"'")
    return None


def _parse_root_uptake(
    text: str,
    *,
    target_time_units: str,
) -> Optional[Dict[str, object]]:
    root_requested = any(
        phrase in text
        for phrase in (
            "root uptake",
            "root water uptake",
            "sink term",
            "plant water uptake",
            "transpiration",
        )
    )
    if not root_requested:
        return None

    unsupported_terms = [
        "salinity",
        "solute uptake",
        "crop growth",
        "root growth",
        "lai",
        "feddes parameters",
        "s-shaped",
        "compensated",
    ]
    for term in unsupported_terms:
        if term in text:
            raise ConfigBuildError(
                "Unsupported root uptake description: "
                f"{term}. This milestone only supports simple water-flow "
                "root uptake with fixed root depth, potential transpiration, "
                "and uniform root distribution."
            )

    root_depth = _parse_root_depth(text)
    if root_depth is None:
        raise ConfigBuildError(
            "Root uptake descriptions need a root depth, for example "
            "'root depth 0.5 m'."
        )

    potential_transpiration = _parse_labeled_rate(
        text,
        labels=(
            "potential transpiration",
            "transpiration",
            "root water uptake demand",
            "uptake demand",
        ),
        target_time_units=target_time_units,
    )
    if potential_transpiration is None:
        raise ConfigBuildError(
            "Root uptake descriptions need a potential transpiration rate, "
            "for example 'potential transpiration 1 mm/day'."
        )

    if "uniform" not in text:
        raise ConfigBuildError(
            "Root uptake currently supports only uniform root distribution. "
            "Include 'uniform root distribution' in the description."
        )

    return {
        "enabled": True,
        "model": "simple",
        "root_depth": root_depth,
        "potential_transpiration": potential_transpiration,
        "distribution": "uniform",
    }


def _parse_root_depth(text: str) -> Optional[float]:
    match = re.search(
        r"\broot\s+depth\b[^,;.]*?([0-9]+(?:\.[0-9]+)?)\s*"
        r"(m|meters?|cm|centimeters?|mm|millimeters?)\b",
        text,
    )
    if not match:
        return None
    return _length_to_m(float(match.group(1)), match.group(2))


def _parse_solute_transport(text: str) -> Optional[Dict[str, object]]:
    solute_requested = any(
        phrase in text
        for phrase in (
            "conservative tracer",
            "tracer",
            "solute transport",
            "one solute",
        )
    )
    if not solute_requested:
        return None

    unsupported_terms = [
        "adsorption",
        "adsorbed",
        "decay",
        "degradation",
        "reaction",
        "reaction chain",
        "nitrification",
        "multiple solutes",
        "multi-solute",
        "volatile",
        "volatilisation",
        "volatilization",
        "salinity",
        "root stress",
        "solute uptake",
        "heat coupling",
        "temperature coupling",
        "non-equilibrium",
        "nonequilibrium",
        "dual porosity",
        "dual permeability",
    ]
    for term in unsupported_terms:
        if term in text:
            raise ConfigBuildError(
                "Unsupported solute transport description: "
                f"{term}. This milestone only supports one conservative "
                "solute with no adsorption, decay, reactions, volatilisation, "
                "heat coupling, salinity/root stress, or non-equilibrium transport."
            )

    if "conservative" not in text:
        raise ConfigBuildError(
            "Solute transport currently requires a conservative tracer "
            "description."
        )

    initial = _parse_labeled_number(
        text,
        labels=("initial concentration", "initial solute concentration"),
    )
    if initial is None:
        raise ConfigBuildError(
            "Conservative tracer descriptions need an initial concentration."
        )

    upper = _parse_labeled_number(
        text,
        labels=(
            "upper boundary concentration",
            "top concentration",
            "inflow concentration",
        ),
    )
    if upper is None:
        raise ConfigBuildError(
            "Conservative tracer descriptions need an upper boundary concentration."
        )

    lower = _parse_labeled_number(
        text,
        labels=("lower boundary concentration", "bottom concentration"),
    )

    dispersivity = _parse_labeled_length(
        text,
        labels=("dispersivity", "longitudinal dispersivity"),
    )
    if dispersivity is None:
        raise ConfigBuildError(
            "Conservative tracer descriptions need a dispersivity such as "
            "'dispersivity 0.01 m'."
        )

    diffusion = _parse_labeled_number(
        text,
        labels=("diffusion coefficient", "molecular diffusion"),
    )
    if diffusion is None:
        diffusion = 0.0

    return {
        "enabled": True,
        "model": "conservative",
        "species": [
            {
                "name": "tracer",
                "initial_concentration": initial,
                "upper_boundary_concentration": upper,
                "lower_boundary_concentration": lower,
                "diffusion_coefficient": diffusion,
                "dispersivity": dispersivity,
            }
        ],
    }


def _parse_labeled_number(
    text: str,
    *,
    labels: Iterable[str],
) -> Optional[float]:
    label_pattern = "|".join(re.escape(label) for label in labels)
    match = re.search(
        rf"\b(?:{label_pattern})\b[^,;.]*?(-?[0-9]+(?:\.[0-9]+)?)\b",
        text,
    )
    return float(match.group(1)) if match else None


def _parse_labeled_length(
    text: str,
    *,
    labels: Iterable[str],
) -> Optional[float]:
    label_pattern = "|".join(re.escape(label) for label in labels)
    match = re.search(
        rf"\b(?:{label_pattern})\b[^,;.]*?([0-9]+(?:\.[0-9]+)?)\s*"
        r"(m|meters?|cm|centimeters?|mm|millimeters?)\b",
        text,
    )
    if not match:
        return None
    return _length_to_m(float(match.group(1)), match.group(2))


def _parse_lower_boundary(text: str, *, target_time_units: str) -> Dict[str, float]:
    if "free drainage" in text:
        return {"type": "free_drainage"}

    head = _parse_boundary_head(text, "lower")
    if head is not None:
        return {"type": "constant_head", "head": head}

    if "lower" in text and "constant flux" in text:
        rate = _parse_rate(text, target_time_units=target_time_units)
        if rate is None:
            raise ConfigBuildError("Lower constant flux boundary needs a rate.")
        return {"type": "constant_flux", "flux": rate}

    raise ConfigBuildError(
        "Could not identify a lower boundary. Use free drainage, constant head, "
        "or constant flux."
    )


def _parse_boundary_head(text: str, boundary_word: str) -> Optional[float]:
    match = re.search(
        rf"{boundary_word}[^,;]*constant head[^,;]*?(-?[0-9]+(?:\.[0-9]+)?)\s*"
        r"(m|meters?|cm|centimeters?|mm|millimeters?)?",
        text,
    )
    if match:
        unit = match.group(2) or "m"
        return _length_to_m(float(match.group(1)), unit)
    match = re.search(
        rf"{boundary_word}[^,;.]*constant\s+(-?[0-9]+(?:\.[0-9]+)?)\s*"
        r"(m|meters?|cm|centimeters?|mm|millimeters?)?\s*"
        r"(?:pressure\s+head|head)",
        text,
    )
    if match:
        unit = match.group(2) or "m"
        return _length_to_m(float(match.group(1)), unit)
    return None


def _parse_rate(text: str, *, target_time_units: str) -> Optional[float]:
    match = re.search(
        r"\b([0-9]+(?:\.[0-9]+)?)\s*"
        r"(m|meters?|cm|centimeters?|mm|millimeters?)\s*/\s*"
        r"(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|d)\b",
        text,
    )
    if not match:
        return None
    length_m = _length_to_m(float(match.group(1)), match.group(2))
    source_time = _TIME_UNITS[match.group(3)]
    return _rate_to_target_time_unit(length_m, source_time, target_time_units)


def _parse_labeled_rate(
    text: str,
    *,
    labels: Iterable[str],
    target_time_units: str,
) -> Optional[float]:
    label_pattern = "|".join(re.escape(label) for label in labels)
    match = re.search(
        rf"\b(?:{label_pattern})\b[^,;.]*?"
        r"([0-9]+(?:\.[0-9]+)?)\s*"
        r"(m|meters?|cm|centimeters?|mm|millimeters?)\s*/\s*"
        r"(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|d)\b",
        text,
    )
    if not match:
        return None
    length_m = _length_to_m(float(match.group(1)), match.group(2))
    source_time = _TIME_UNITS[match.group(3)]
    return _rate_to_target_time_unit(length_m, source_time, target_time_units)


def _parse_hcrita(text: str) -> float:
    match = re.search(
        r"\bhcrita\b[^,;.]*?(-?[0-9]+(?:\.[0-9]+)?)\s*"
        r"(m|meters?|cm|centimeters?|mm|millimeters?)?",
        text,
    )
    if not match:
        return -10000.0
    unit = match.group(2) or "m"
    return _length_to_m(float(match.group(1)), unit)


def _parse_initial_condition(text: str) -> Dict[str, float]:
    if "water content" in text:
        raise ConfigBuildError(
            "Initial water-content conditions are out of scope; use pressure head."
        )
    gradient_match = re.search(
        r"initial[^,;.]*(?:pressure head|head)[^,;.]*?"
        r"(-?[0-9]+(?:\.[0-9]+)?)\s*"
        r"(m|meters?|cm|centimeters?|mm|millimeters?)?\s*(?:at\s+)?top"
        r"[^,;.]*?(?:to|reduced to|increased to|and)[^,;.]*?"
        r"(-?[0-9]+(?:\.[0-9]+)?)\s*"
        r"(m|meters?|cm|centimeters?|mm|millimeters?)?\s*(?:at\s+(?:the\s+)?)bottom",
        text,
    )
    if gradient_match:
        profile_bottom = _parse_soils(text)[0][-1]["depth_bottom"]
        top_unit = gradient_match.group(2) or "m"
        bottom_unit = gradient_match.group(4) or top_unit
        top_value = _length_to_m(float(gradient_match.group(1)), top_unit)
        bottom_value = _length_to_m(float(gradient_match.group(3)), bottom_unit)
        return {
            "type": "pressure_head",
            "value": top_value,
            "profile": [
                {"depth": 0.0, "value": top_value},
                {"depth": profile_bottom, "value": bottom_value},
            ],
        }

    match = re.search(
        r"initial[^,;]*(?:pressure head|head)[^,;]*?"
        r"(-?[0-9]+(?:\.[0-9]+)?)\s*"
        r"(m|meters?|cm|centimeters?|mm|millimeters?)?",
        text,
    )
    if not match:
        raise ConfigBuildError(
            "Could not find an initial pressure head such as 'initial pressure head -1 m'."
        )
    unit = match.group(2) or "m"
    return {
        "type": "pressure_head",
        "value": _length_to_m(float(match.group(1)), unit),
    }


def _parse_observation_depths(text: str) -> List[float]:
    match = re.search(r"observations?(?: depths?)?(?: at| of)? ([^;]+)", text)
    if not match:
        return []
    segment = match.group(1).split("print times")[0]
    return _parse_length_list(segment)


def _parse_print_times(text: str) -> List[float]:
    match = re.search(r"print times? ([^;]+)", text)
    if not match:
        return []
    segment = match.group(1)
    return [float(n) for n in re.findall(r"-?[0-9]+(?:\.[0-9]+)?", segment)]


def _parse_length_list(segment: str) -> List[float]:
    tokens = list(re.finditer(
        r"([0-9]+(?:\.[0-9]+)?)\s*"
        r"(m|meters?|cm|centimeters?|mm|millimeters?)?",
        segment,
    ))
    if not tokens:
        return []
    default_unit = "m"
    for token in reversed(tokens):
        if token.group(2):
            default_unit = token.group(2)
            break
    return [
        _length_to_m(float(token.group(1)), token.group(2) or default_unit)
        for token in tokens
    ]


def _length_to_m(value: float, unit: str) -> float:
    unit_key = unit.rstrip(".")
    factor = _LENGTH_TO_M.get(unit_key)
    if factor is None:
        raise ConfigBuildError(f"Unsupported length unit: {unit}")
    return value * factor


def _rate_to_target_time_unit(
    length_m: float, source_time_units: str, target_time_units: str,
) -> float:
    source_seconds = _SECONDS_PER_UNIT[source_time_units]
    target_seconds = _SECONDS_PER_UNIT[target_time_units]
    return length_m * (target_seconds / source_seconds)


def _default_print_interval(t_end: float) -> float:
    return max(t_end / 20.0, t_end / 1000.0)


__all__ = [
    "ConfigBuildError",
    "ConfigBuildResult",
    "build_config_from_description",
    "summarise_built_config",
    "write_config",
]
