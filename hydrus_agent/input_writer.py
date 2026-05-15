"""HYDRUS-1D input file writer.

Stub — implemented in a later milestone. Will translate a validated
``ModelConfig`` into the suite of HYDRUS-1D input files (SELECTOR.IN,
PROFILE.DAT, ATMOSPH.IN, ...).
"""

from __future__ import annotations

from pathlib import Path

from hydrus_agent.schema import ModelConfig


def write_inputs(config: ModelConfig, target_dir: Path) -> None:
    raise NotImplementedError(
        "Input writing is scheduled for a later milestone. "
        "Milestone 1 only validates configs and creates the run folder."
    )
