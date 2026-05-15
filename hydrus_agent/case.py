"""Per-case run folder management.

A 'case' here is one execution of the workflow described by a ``ModelConfig``.
Each case gets its own folder under ``runs/<case_id>/`` containing input,
output, and log subfolders. The validated config is also written to the case
folder for traceability.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from hydrus_agent.schema import ModelConfig


SUBFOLDERS = ("inputs", "outputs", "logs")


def create_run_folder(
    config: ModelConfig,
    runs_root: Union[str, Path] = "runs",
    overwrite: bool = False,
) -> Path:
    """Create a fresh run folder for a validated configuration.

    Parameters
    ----------
    config
        A validated ``ModelConfig``.
    runs_root
        Root folder under which case folders are created. Defaults to ``runs``.
    overwrite
        If False (default) and a folder for this case already exists, raise
        ``FileExistsError`` rather than touching the existing folder. The
        project brief forbids overwriting without an explicit backup step;
        automatic backup is intentionally out of scope for milestone 1.

    Returns
    -------
    Path
        The created case folder.
    """
    runs_root = Path(runs_root)
    case_dir = runs_root / config.case_id

    if case_dir.exists() and not overwrite:
        raise FileExistsError(
            f"Run folder already exists: {case_dir}. "
            "Pass overwrite=True only after manually backing it up."
        )

    case_dir.mkdir(parents=True, exist_ok=overwrite)
    for sub in SUBFOLDERS:
        (case_dir / sub).mkdir(exist_ok=True)

    # Persist the validated config alongside the run for reproducibility.
    config_snapshot = case_dir / "config.json"
    config_snapshot.write_text(
        json.dumps(config.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )

    return case_dir
