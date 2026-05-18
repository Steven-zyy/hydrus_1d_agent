"""Reproducibility run manifest.

Writes ``runs/<case_id>/run_manifest.json`` as a separate artefact from
``pipeline_summary.json``. The manifest records provenance metadata
(config hash, HYDRUS executable, environment, input file hashes, key
output file paths, and the four reliability statuses).

All helpers are best-effort: any individual collector that fails returns
a fallback value rather than raising, so a manifest failure can never
abort a successful pipeline run.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


RUN_MANIFEST_FILENAME = "run_manifest.json"
MANIFEST_SCHEMA_VERSION = 1

# Important HYDRUS input filenames matched case-insensitively. These are
# always hashed when present. Other input-like files in ``hydrus_project``
# matching the input extension set are also hashed (see _INPUT_EXTENSIONS).
_KNOWN_INPUT_FILES = (
    "SELECTOR.IN",
    "PROFILE.DAT",
    "ATMOSPH.IN",
    "METEO.IN",
    "FIT.IN",
    "LEVEL_01.DIR",
)

# Case-insensitive extension set for general HYDRUS input-like files
# inside ``hydrus_project``. Output files (``.out``) and the error
# message file are deliberately excluded.
_INPUT_EXTENSIONS = {".in", ".dat", ".dir"}

# Output file globs (case-insensitive matching applied below).
_OUTPUT_GLOBS = (
    ("hydrus_project", ("*.out", "*.OUT")),
    ("hydrus_project", ("Error.msg", "error.msg", "ERROR.MSG")),
)


# --- Public API ----------------------------------------------------------


def build_run_manifest(
    *,
    summary: Dict[str, Any],
    run_dir: Path,
    config_path: Optional[Path],
    hydrus_launch_mode: Optional[str],
) -> Dict[str, Any]:
    """Assemble the manifest dict from the pipeline summary and the run dir."""
    run_dir = Path(run_dir)
    manifest: Dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "case_id": summary.get("case_id"),
        "run_dir": str(run_dir),
        "config": _config_block(config_path),
        "hydrus": _hydrus_block(hydrus_launch_mode),
        "environment": collect_environment(),
        "timestamps": {
            "started_at": summary.get("started_at"),
            "finished_at": summary.get("finished_at"),
            "manifest_written_at": _utc_now_iso(),
        },
        "inputs": discover_input_files(run_dir),
        "outputs": discover_output_files(run_dir),
        "reliability": {
            "execution_status": summary.get("execution_status"),
            "hydrus_numerical_status": summary.get("hydrus_numerical_status"),
            "qc_status": summary.get("qc_status"),
            "overall_status": summary.get("overall_status"),
        },
    }
    return manifest


def write_run_manifest(manifest: Dict[str, Any], run_dir: Path) -> Path:
    """Write the manifest to ``run_dir/run_manifest.json`` and return the path."""
    path = Path(run_dir) / RUN_MANIFEST_FILENAME
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return path


def write_run_manifest_for_pipeline(
    *,
    summary: Dict[str, Any],
    run_dir: Union[str, Path],
    config_path: Optional[Union[str, Path]],
    hydrus_launch_mode: Optional[str],
) -> Optional[Path]:
    """Best-effort manifest write called from the pipeline finaliser.

    Never raises. Returns the manifest path on success or ``None`` on
    failure (a warning is logged).
    """
    try:
        run_dir = Path(run_dir)
        if not run_dir.is_dir():
            return None
        manifest = build_run_manifest(
            summary=summary,
            run_dir=run_dir,
            config_path=Path(config_path) if config_path else None,
            hydrus_launch_mode=hydrus_launch_mode,
        )
        return write_run_manifest(manifest, run_dir)
    except Exception as exc:  # noqa: BLE001 - explicit broad catch
        logger.warning("Failed to write run_manifest.json: %s", exc)
        return None


# --- Collectors ----------------------------------------------------------


def collect_environment() -> Dict[str, Any]:
    """Capture Python, OS, hydrus_agent version, and git commit metadata."""
    return {
        "python_version": _safe(lambda: platform.python_version(), "unknown"),
        "python_implementation": _safe(
            lambda: platform.python_implementation(), "unknown"
        ),
        "platform": _safe(lambda: platform.platform(), "unknown"),
        "system": _safe(lambda: platform.system(), "unknown"),
        "hydrus_agent_version": _hydrus_agent_version(),
        "git_commit": _git_commit(),
    }


def discover_input_files(run_dir: Path) -> List[Dict[str, Any]]:
    """List + hash known and general HYDRUS input files under ``run_dir``."""
    run_dir = Path(run_dir)
    entries: List[Dict[str, Any]] = []
    seen: set[Path] = set()

    # Validated config snapshot at the run root.
    snapshot = run_dir / "config.json"
    if snapshot.is_file():
        entries.append(_file_entry(snapshot, run_dir, with_hash=True))
        seen.add(snapshot.resolve())

    project_dir = run_dir / "hydrus_project"
    if not project_dir.is_dir():
        return entries

    # Walk hydrus_project. Match the known filename set case-insensitively
    # first (so the canonical order is stable), then include any other
    # file whose extension is in the input extension set.
    known_lower = {name.lower() for name in _KNOWN_INPUT_FILES}
    candidates: List[Path] = []
    for child in sorted(project_dir.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_file():
            continue
        name_lower = child.name.lower()
        ext_lower = child.suffix.lower()
        if name_lower in known_lower or ext_lower in _INPUT_EXTENSIONS:
            candidates.append(child)

    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        entry = _file_entry(path, run_dir, with_hash=True)
        if entry is not None:
            entries.append(entry)
            seen.add(resolved)
    return entries


def discover_output_files(run_dir: Path) -> List[Dict[str, Any]]:
    """List key output files (no hashing) under ``run_dir``."""
    run_dir = Path(run_dir)
    entries: List[Dict[str, Any]] = []
    seen: set[Path] = set()

    project_dir = run_dir / "hydrus_project"
    if project_dir.is_dir():
        for child in sorted(project_dir.iterdir(), key=lambda p: p.name.lower()):
            if not child.is_file():
                continue
            name_lower = child.name.lower()
            if name_lower.endswith(".out") or name_lower == "error.msg":
                _append_unique(entries, seen, child, run_dir, with_hash=False)

    qc_path = run_dir / "outputs" / "qc_summary.json"
    if qc_path.is_file():
        _append_unique(entries, seen, qc_path, run_dir, with_hash=False)

    field_summary = run_dir / "outputs" / "field_comparison_summary.json"
    if field_summary.is_file():
        _append_unique(entries, seen, field_summary, run_dir, with_hash=False)

    report_path = run_dir / "report.md"
    if report_path.is_file():
        _append_unique(entries, seen, report_path, run_dir, with_hash=False)

    figures_dir = run_dir / "figures"
    if figures_dir.is_dir():
        for child in sorted(figures_dir.iterdir(), key=lambda p: p.name.lower()):
            if child.is_file() and child.suffix.lower() == ".png":
                _append_unique(entries, seen, child, run_dir, with_hash=False)

    log_path = run_dir / "logs" / "hydrus_run.log"
    if log_path.is_file():
        _append_unique(entries, seen, log_path, run_dir, with_hash=False)

    return entries


# --- Internal helpers ----------------------------------------------------


def _config_block(config_path: Optional[Path]) -> Dict[str, Any]:
    if config_path is None:
        return {
            "path": None,
            "absolute_path": None,
            "content_hash_sha256": None,
        }
    path = Path(config_path)
    return {
        "path": str(path),
        "absolute_path": _safe(lambda: str(path.resolve()), None),
        "content_hash_sha256": _hash_file(path),
    }


def _hydrus_block(hydrus_launch_mode: Optional[str]) -> Dict[str, Any]:
    exe_path: Optional[str] = None
    exe_exists = False
    try:
        from hydrus_agent.env import resolve_hydrus_exe
        exe_str, _source = resolve_hydrus_exe()
        if exe_str:
            exe_path = exe_str
            exe_exists = Path(exe_str).is_file()
    except Exception as exc:  # noqa: BLE001
        logger.debug("resolve_hydrus_exe failed: %s", exc)
    return {
        "executable_path": exe_path,
        "executable_exists": exe_exists,
        "launch_mode": hydrus_launch_mode,
    }


def _file_entry(
    path: Path,
    run_dir: Path,
    *,
    with_hash: bool,
) -> Optional[Dict[str, Any]]:
    try:
        rel = _relative_path(path, run_dir)
        size = path.stat().st_size
    except OSError as exc:
        logger.debug("Could not stat %s: %s", path, exc)
        return None
    entry: Dict[str, Any] = {
        "path": rel,
        "size_bytes": size,
    }
    if with_hash:
        entry["sha256"] = _hash_file(path)
    return entry


def _append_unique(
    entries: List[Dict[str, Any]],
    seen: set[Path],
    path: Path,
    run_dir: Path,
    *,
    with_hash: bool,
) -> None:
    try:
        resolved = path.resolve()
    except OSError:
        return
    if resolved in seen:
        return
    entry = _file_entry(path, run_dir, with_hash=with_hash)
    if entry is None:
        return
    entries.append(entry)
    seen.add(resolved)


def _relative_path(path: Path, run_dir: Path) -> str:
    try:
        rel = path.resolve().relative_to(run_dir.resolve())
        return rel.as_posix()
    except (ValueError, OSError):
        return str(path)


def _hash_file(path: Path) -> Optional[str]:
    """SHA-256 hex of a file, or None if unreadable. Reuses the helper in
    ``review_state`` when available so the algorithm stays consistent."""
    try:
        from hydrus_agent.review_state import hash_file_sha256
        return hash_file_sha256(path)
    except Exception as exc:  # noqa: BLE001
        logger.debug("hash_file_sha256 failed for %s: %s", path, exc)
        return None


def _hydrus_agent_version() -> str:
    try:
        import hydrus_agent
        return getattr(hydrus_agent, "__version__", "unknown")
    except Exception:  # noqa: BLE001
        return "unknown"


def _git_commit() -> Optional[str]:
    """Return the current git HEAD commit or None when unavailable.

    Never raises and never blocks for more than 2 seconds.
    """
    if shutil.which("git") is None:
        return None
    try:
        project_root = Path(__file__).resolve().parents[1]
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("git rev-parse failed: %s", exc)
        return None
    if proc.returncode != 0:
        return None
    commit = (proc.stdout or "").strip()
    return commit or None


def _utc_now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).isoformat(timespec="seconds")


def _safe(callable_, fallback):
    try:
        return callable_()
    except Exception:  # noqa: BLE001
        return fallback


__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "RUN_MANIFEST_FILENAME",
    "build_run_manifest",
    "collect_environment",
    "discover_input_files",
    "discover_output_files",
    "write_run_manifest",
    "write_run_manifest_for_pipeline",
]
