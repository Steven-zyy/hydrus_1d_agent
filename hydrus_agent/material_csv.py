"""CSV loader for direct van Genuchten material parameters.

This loader supports direct material hydraulic parameters only. It does not
fit SWCC curves or infer parameters from measured retention data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


REQUIRED_COLUMNS = [
    "material",
    "theta_r",
    "theta_s",
    "alpha_1_m",
    "n",
    "Ks_m_d",
    "l",
]


class MaterialCsvError(ValueError):
    """Raised when material parameter CSV input cannot be loaded safely."""


def load_van_genuchten_from_csv(
    csv_path: Path | str,
) -> tuple[list[dict[str, float]], dict[str, Any]]:
    """Load direct van Genuchten material parameters from a CSV file.

    Returns ``(materials, metadata)``. The materials list is suitable for the
    existing ``van_genuchten`` config field.
    """
    csv_path = Path(csv_path)
    if not csv_path.is_file():
        raise MaterialCsvError(f"Material CSV file not found: {csv_path}")

    try:
        df = pd.read_csv(csv_path)
    except pd.errors.EmptyDataError as exc:
        raise MaterialCsvError(f"Material CSV is empty: {csv_path}") from exc

    if df.empty:
        raise MaterialCsvError(f"Material CSV is empty: {csv_path}")

    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise MaterialCsvError(
            "Material CSV is missing required column(s): " + ", ".join(missing)
        )

    subset = df[REQUIRED_COLUMNS].copy()
    names = [str(value).strip() for value in subset["material"].tolist()]
    if subset["material"].isnull().any() or any(not name for name in names):
        raise MaterialCsvError("Material names must be non-empty.")
    if subset.drop(columns=["material"]).isnull().any().any():
        raise MaterialCsvError(
            "Material CSV contains missing values in required columns."
        )
    if len(set(names)) != len(names):
        raise MaterialCsvError("Material names must be unique.")

    theta_r = _numeric_column(subset, "theta_r")
    theta_s = _numeric_column(subset, "theta_s")
    alpha = _numeric_column(subset, "alpha_1_m")
    n_values = _numeric_column(subset, "n")
    ks = _numeric_column(subset, "Ks_m_d")
    l_values = _numeric_column(subset, "l")

    if (theta_r < 0).any():
        raise MaterialCsvError("Material CSV theta_r values must be >= 0.")
    if (theta_s <= theta_r).any():
        raise MaterialCsvError("Material CSV theta_s values must be greater than theta_r.")
    if (alpha <= 0).any():
        raise MaterialCsvError("Material CSV alpha_1_m values must be positive.")
    if (n_values <= 1).any():
        raise MaterialCsvError("Material CSV n values must be greater than 1.")
    if (ks <= 0).any():
        raise MaterialCsvError("Material CSV Ks_m_d values must be positive.")

    materials: list[dict[str, float]] = []
    material_rows: list[dict[str, Any]] = []
    name_to_material_id: dict[str, int] = {}
    for idx, name in enumerate(names, start=1):
        row = {
            "material_id": idx,
            "theta_r": float(theta_r.iloc[idx - 1]),
            "theta_s": float(theta_s.iloc[idx - 1]),
            "alpha": float(alpha.iloc[idx - 1]),
            "n": float(n_values.iloc[idx - 1]),
            "Ks": float(ks.iloc[idx - 1]),
            "l": float(l_values.iloc[idx - 1]),
        }
        materials.append(row)
        material_rows.append({"name": name, **row})
        name_to_material_id[name] = idx

    metadata = {
        "source_type": "csv",
        "source_csv": str(csv_path),
        "material_count": len(materials),
        "material_names": names,
        "name_to_material_id": name_to_material_id,
        "materials": material_rows,
        "theta_unit": "-",
        "alpha_unit": "1/m",
        "ks_unit": "m/day",
        "l_unit": "-",
    }
    return materials, metadata


def _numeric_column(df, column: str):
    try:
        return pd.to_numeric(df[column], errors="raise")
    except Exception as exc:
        raise MaterialCsvError(f"Material CSV column {column} must be numeric.") from exc
