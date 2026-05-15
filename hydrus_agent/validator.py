"""Configuration loader and validator.

Wraps json + pydantic so the caller gets a single, readable error type with
the file path and the offending field path included.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Union

from pydantic import ValidationError

from hydrus_agent.atmospheric_csv import (
    AtmosphericCsvError,
    load_atmospheric_records_from_csv,
)
from hydrus_agent.material_csv import (
    MaterialCsvError,
    load_van_genuchten_from_csv,
)
from hydrus_agent.schema import ModelConfig


class ConfigError(Exception):
    """Raised when a configuration file cannot be parsed or validated."""


def load_config(path: Union[str, Path]) -> ModelConfig:
    """Load and validate a HYDRUS-1D agent configuration file.

    Parameters
    ----------
    path
        Path to a JSON file matching the ``ModelConfig`` schema.

    Returns
    -------
    ModelConfig
        A validated configuration object.

    Raises
    ------
    ConfigError
        If the file is missing, is not valid JSON, or fails schema validation.
    """
    config_path = Path(path)

    if not config_path.is_file():
        raise ConfigError(f"Configuration file not found: {config_path}")

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"{config_path} is not valid JSON: {exc.msg} "
            f"(line {exc.lineno}, column {exc.colno})"
        ) from exc

    try:
        raw = _resolve_material_csv(raw, config_path)
        raw = _resolve_atmospheric_csv(raw, config_path)
        return ModelConfig.model_validate(raw)
    except AtmosphericCsvError as exc:
        raise ConfigError(
            f"Configuration in {config_path} failed atmospheric CSV validation: {exc}"
        ) from exc
    except MaterialCsvError as exc:
        raise ConfigError(
            f"Configuration in {config_path} failed material CSV validation: {exc}"
        ) from exc
    except ValidationError as exc:
        details = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "<root>"
            details.append(f"  - {loc}: {err['msg']}")
        joined = "\n".join(details)
        raise ConfigError(
            f"Configuration in {config_path} failed validation:\n{joined}"
        ) from exc


def _resolve_material_csv(raw: Any, config_path: Path) -> Any:
    if not isinstance(raw, dict):
        return raw

    van_genuchten = raw.get("van_genuchten")
    if not isinstance(van_genuchten, dict) or not van_genuchten.get("source_csv"):
        return raw

    csv_path = _resolve_csv_path(str(van_genuchten["source_csv"]), config_path)
    materials, metadata = load_van_genuchten_from_csv(csv_path)
    raw["van_genuchten"] = materials
    raw["material_source"] = metadata
    _resolve_soil_layer_material_names(raw, metadata["name_to_material_id"])
    return raw


def _resolve_soil_layer_material_names(
    raw: dict[str, Any],
    name_to_material_id: dict[str, int],
) -> None:
    soil_profile = raw.get("soil_profile")
    if not isinstance(soil_profile, list):
        return

    for index, layer in enumerate(soil_profile, start=1):
        if not isinstance(layer, dict):
            continue
        material_name = layer.get("material", layer.get("material_name"))
        if material_name is None:
            continue
        material_name = str(material_name).strip()
        if material_name not in name_to_material_id:
            known = ", ".join(name_to_material_id)
            raise MaterialCsvError(
                f"soil_profile layer {index} references material "
                f"{material_name!r}, which is not defined in the material CSV. "
                f"Known materials: {known}"
            )
        resolved_id = name_to_material_id[material_name]
        if "material_id" in layer and int(layer["material_id"]) != resolved_id:
            raise MaterialCsvError(
                f"soil_profile layer {index} material_id={layer['material_id']} "
                f"does not match material {material_name!r} "
                f"(expected material_id={resolved_id})."
            )
        layer["material_id"] = resolved_id


def _resolve_atmospheric_csv(raw: Any, config_path: Path) -> Any:
    if not isinstance(raw, dict):
        return raw

    upper_boundary = raw.get("upper_boundary")
    if isinstance(upper_boundary, dict) and upper_boundary.get("type") == "atmospheric":
        source_keys = {
            "source_csv",
            "time_column",
            "precipitation_column",
            "potential_evaporation_column",
            "units",
        }
        if any(key in upper_boundary for key in source_keys):
            atmospheric = raw.setdefault("atmospheric", {})
            if isinstance(atmospheric, dict):
                atmospheric.setdefault("enabled", True)
                for key in source_keys:
                    if key in upper_boundary and key not in atmospheric:
                        atmospheric[key] = upper_boundary[key]

    atmospheric = raw.get("atmospheric")
    if not isinstance(atmospheric, dict) or not atmospheric.get("source_csv"):
        return raw

    simulation_time = raw.get("simulation_time") or {}
    if not isinstance(simulation_time, dict):
        simulation_time = {}
    units = atmospheric.get("units") or {}
    if not isinstance(units, dict):
        units = {}

    simulation_units = str(simulation_time.get("units", "days")).lower()
    if simulation_units not in {"days", "day", "d"}:
        raise AtmosphericCsvError(
            "CSV atmospheric forcing currently requires simulation_time.units='days'."
        )

    csv_path = _resolve_csv_path(str(atmospheric["source_csv"]), config_path)
    records, metadata = load_atmospheric_records_from_csv(
        csv_path,
        time_column=atmospheric.get("time_column", "time_d"),
        precipitation_column=atmospheric.get(
            "precipitation_column", "precipitation_m_d"
        ),
        potential_evaporation_column=atmospheric.get(
            "potential_evaporation_column",
            "potential_evaporation_m_d",
        ),
        simulation_end_time=simulation_time.get("t_end"),
        hCritA=atmospheric.get("hCritA", -10000.0),
        time_unit=units.get("time", "day"),
        length_unit=units.get("length", "m"),
    )
    atmospheric["enabled"] = True
    atmospheric["records"] = records
    atmospheric["source_metadata"] = metadata
    return raw


def _resolve_csv_path(source_csv: str, config_path: Path) -> Path:
    path = Path(source_csv)
    if path.is_absolute():
        return path
    candidates = [
        config_path.parent / path,
        Path.cwd() / path,
        Path(__file__).resolve().parents[1] / path,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]
