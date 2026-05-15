"""CSV loader for simple atmospheric boundary forcing.

The loader converts user CSV rows into the same atmospheric record dictionaries
used by inline ``atmospheric.records`` configs. Units are intentionally narrow:
time in days and flux rates in m/day.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_TIME_COLUMN = "time_d"
DEFAULT_PRECIPITATION_COLUMN = "precipitation_m_d"
DEFAULT_EVAPORATION_COLUMN = "potential_evaporation_m_d"


class AtmosphericCsvError(ValueError):
    """Raised when atmospheric CSV input cannot be loaded safely."""


def load_atmospheric_records_from_csv(
    csv_path: Path | str,
    *,
    time_column: str = DEFAULT_TIME_COLUMN,
    precipitation_column: str = DEFAULT_PRECIPITATION_COLUMN,
    potential_evaporation_column: str = DEFAULT_EVAPORATION_COLUMN,
    simulation_end_time: float | None = None,
    hCritA: float = -10000.0,
    time_unit: str = "day",
    length_unit: str = "m",
) -> tuple[list[dict[str, float]], dict[str, Any]]:
    """Load atmospheric forcing records from a CSV file.

    Returns ``(records, metadata)`` where records are suitable for
    ``AtmosphericForcing.records`` and metadata is JSON-serialisable.
    """
    csv_path = Path(csv_path)
    if not csv_path.is_file():
        raise AtmosphericCsvError(f"Atmospheric CSV file not found: {csv_path}")

    _validate_units(time_unit=time_unit, length_unit=length_unit)

    try:
        df = pd.read_csv(csv_path)
    except pd.errors.EmptyDataError as exc:
        raise AtmosphericCsvError(f"Atmospheric CSV is empty: {csv_path}") from exc

    if df.empty:
        raise AtmosphericCsvError(f"Atmospheric CSV is empty: {csv_path}")

    required = [time_column, precipitation_column, potential_evaporation_column]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise AtmosphericCsvError(
            "Atmospheric CSV is missing required column(s): "
            + ", ".join(missing)
        )

    subset = df[required].copy()
    if subset.isnull().any().any():
        raise AtmosphericCsvError(
            "Atmospheric CSV contains missing values in required columns."
        )

    time = _numeric_column(subset, time_column)
    precipitation = _numeric_column(subset, precipitation_column)
    evaporation = _numeric_column(subset, potential_evaporation_column)

    if (time < 0).any():
        raise AtmosphericCsvError("Atmospheric CSV time_d values must be non-negative.")
    if (precipitation < 0).any():
        raise AtmosphericCsvError(
            "Atmospheric CSV precipitation_m_d values must be non-negative."
        )
    if (evaporation < 0).any():
        raise AtmosphericCsvError(
            "Atmospheric CSV potential_evaporation_m_d values must be non-negative."
        )

    times = [float(value) for value in time.tolist()]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise AtmosphericCsvError(
            "Atmospheric CSV time_d values must be strictly increasing."
        )

    if simulation_end_time is not None and times[-1] < float(simulation_end_time):
        raise AtmosphericCsvError(
            "Atmospheric CSV final time does not cover the simulation end time "
            f"({times[-1]} < {float(simulation_end_time)})."
        )

    precip_values = [float(value) for value in precipitation.tolist()]
    evaporation_values = [float(value) for value in evaporation.tolist()]
    records = [
        {
            "time": t,
            "precipitation": p,
            "evaporation": e,
            "hCritA": float(hCritA),
        }
        for t, p, e in zip(times, precip_values, evaporation_values)
    ]
    metadata = {
        "source_type": "csv",
        "source_csv": str(csv_path),
        "record_count": len(records),
        "time_range": [times[0], times[-1]],
        "total_precipitation": _integrate_piecewise_constant(times, precip_values),
        "total_potential_evaporation": _integrate_piecewise_constant(times, evaporation_values),
        "max_precipitation_rate": max(precip_values),
        "max_potential_evaporation_rate": max(evaporation_values),
        "time_unit": "day",
        "length_unit": "m",
        "rate_unit": "m/day",
        "covers_simulation_end_time": (
            True if simulation_end_time is None else times[-1] >= float(simulation_end_time)
        ),
    }
    return records, metadata


def _numeric_column(df, column: str):
    try:
        return pd.to_numeric(df[column], errors="raise")
    except Exception as exc:
        raise AtmosphericCsvError(
            f"Atmospheric CSV column {column} must be numeric."
        ) from exc


def _validate_units(*, time_unit: str, length_unit: str) -> None:
    if str(time_unit).lower() not in {"day", "days", "d"}:
        raise AtmosphericCsvError(
            "Atmospheric CSV time unit must be 'day' for this milestone."
        )
    if str(length_unit).lower() not in {"m", "meter", "meters", "metre", "metres"}:
        raise AtmosphericCsvError(
            "Atmospheric CSV length unit must be 'm' for this milestone."
        )


def _integrate_piecewise_constant(times: list[float], values: list[float]) -> float:
    if len(times) < 2:
        return 0.0
    total = 0.0
    for t0, t1, value in zip(times, times[1:], values[:-1]):
        total += float(value) * (float(t1) - float(t0))
    return total
