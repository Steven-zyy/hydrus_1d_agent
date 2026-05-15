"""Review-state persistence for generated HYDRUS configs.

The state file records the last config that was explicitly reviewed so CLI
execution can guard against accidentally running a different JSON file.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from pathlib import Path
from typing import Dict, Optional, Union

from hydrus_agent.schema import ModelConfig


REVIEW_STATE_FILENAME = "last_review.json"


def hash_file_sha256(path: Union[str, Path]) -> str:
    """Return the SHA-256 content hash of a config file."""
    data = Path(path).read_bytes()
    return hashlib.sha256(data).hexdigest()


def build_review_state(
    *,
    config: ModelConfig,
    config_path: Union[str, Path],
) -> Dict[str, object]:
    """Build the JSON-serialisable review-state payload."""
    path = Path(config_path)
    return {
        "config_path": str(path),
        "absolute_config_path": str(path.resolve()),
        "case_id": config.case_id,
        "project_name": config.project_name,
        "simulation_time": {
            "start": config.simulation_time.t_init,
            "end": config.simulation_time.t_end,
            "units": config.simulation_time.units.value,
        },
        "content_hash_sha256": hash_file_sha256(path),
        "timestamp": _dt.datetime.now().isoformat(timespec="seconds"),
    }


def write_review_state(
    *,
    config: ModelConfig,
    config_path: Union[str, Path],
    state_dir: Union[str, Path],
) -> Path:
    """Persist the last-reviewed config state and return the state path."""
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / REVIEW_STATE_FILENAME
    state = build_review_state(config=config, config_path=config_path)
    state_path.write_text(
        json.dumps(state, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return state_path


def read_review_state(state_dir: Union[str, Path]) -> Optional[Dict[str, object]]:
    """Read review state, returning None when no state file exists."""
    state_path = Path(state_dir) / REVIEW_STATE_FILENAME
    if not state_path.is_file():
        return None
    return json.loads(state_path.read_text(encoding="utf-8"))


def build_requested_state(
    *,
    config: ModelConfig,
    config_path: Union[str, Path],
) -> Dict[str, object]:
    """Build a comparable state payload for a config about to run."""
    return build_review_state(config=config, config_path=config_path)


def states_match(reviewed: Dict[str, object], requested: Dict[str, object]) -> bool:
    """Return True iff requested path and content hash match reviewed state."""
    return (
        reviewed.get("absolute_config_path") == requested.get("absolute_config_path")
        and reviewed.get("content_hash_sha256") == requested.get("content_hash_sha256")
    )


def format_state_summary(label: str, state: Dict[str, object]) -> str:
    """Return a concise summary suitable for CLI mismatch errors."""
    sim = state.get("simulation_time") or {}
    if not isinstance(sim, dict):
        sim = {}
    lines = [
        f"{label}:",
        f"  config_path          : {state.get('config_path')}",
        f"  absolute_config_path : {state.get('absolute_config_path')}",
        f"  case_id              : {state.get('case_id')}",
        f"  project_name         : {state.get('project_name')}",
        f"  sim window           : {sim.get('start')} to {sim.get('end')} {sim.get('units')}",
        f"  content_hash_sha256  : {state.get('content_hash_sha256')}",
    ]
    if state.get("timestamp"):
        lines.append(f"  timestamp            : {state.get('timestamp')}")
    return "\n".join(lines)


__all__ = [
    "REVIEW_STATE_FILENAME",
    "build_requested_state",
    "format_state_summary",
    "hash_file_sha256",
    "read_review_state",
    "states_match",
    "write_review_state",
]
