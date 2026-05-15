"""HYDRUS-1D executable runner (milestones 3, 3.1, 3.5).

Two launch modes are supported:

    "argv" (default)
        cmd = [hydrus_exe, str(project_dir), "-1"]
        cwd = project_dir
        Matches what phydrus's own ``Model.simulate()`` does. Most robust
        across PC-Progress builds.

    "level-dir"
        cmd = [hydrus_exe]
        cwd = project_dir
        Relies on ``LEVEL_01.DIR`` in cwd. Older mechanism; some Fortran
        builds mishandle long path strings here.

In both modes the runner writes ``LEVEL_01.DIR`` (cheap, harmless) and
sends a single newline on stdin to unblock any "Press Enter to continue"
prompt.

Even when HYDRUS returns 0, the runner inspects stdout/stderr for explicit
failure indicators (e.g. "does not exist or pathway is too long",
"cannot open", "convergence not reached"). The normal console prompt
"Press Enter to continue" is neutral when HYDRUS also reports successful
completion. The reason for any downgraded run is exposed via
``RunResult.false_success_reason``.
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Union


logger = logging.getLogger(__name__)

REQUIRED_INPUT_FILES = ("SELECTOR.IN", "PROFILE.DAT")
TIMEOUT_MARKER = "TIMEOUT"
LEVEL_01_DIR_FILENAME = "LEVEL_01.DIR"

LAUNCH_MODE_ARGV = "argv"
LAUNCH_MODE_LEVEL_DIR = "level-dir"
LAUNCH_MODES = (LAUNCH_MODE_ARGV, LAUNCH_MODE_LEVEL_DIR)
DEFAULT_LAUNCH_MODE = LAUNCH_MODE_ARGV

# Substrings that indicate HYDRUS completed normally.
SUCCESS_PATTERNS = (
    "calculations have finished successfully",
)

# Substrings/regexes that indicate HYDRUS hit an error path *despite*
# exiting 0. Matched case-insensitively against joined stdout+stderr.
FAILURE_PATTERNS = (
    "does not exist or pathway is too long or corrupted",
    "convergence not reached",
    "cannot open",
    r"\berror\b",
)

# This prompt is common for successful console runs and is not, by itself,
# a HYDRUS-side failure. If it appears without any success indicator, we
# still treat the run as suspicious instead of silently accepting it.
NEUTRAL_PROMPT_PATTERNS = (
    "press enter to continue",
)

# Backwards-compatible name for callers/tests that imported the old constant.
FALSE_SUCCESS_PATTERNS = FAILURE_PATTERNS


@dataclass
class FileInfo:
    name: str
    size_bytes: int
    mtime: str

    def format_line(self) -> str:
        return f"  {self.name:<24} {self.size_bytes:>10} B   {self.mtime}"


def inventory_dir(path: Union[str, Path]) -> List[FileInfo]:
    path = Path(path)
    if not path.is_dir():
        return []
    items: List[FileInfo] = []
    for entry in sorted(path.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_file():
            continue
        stat = entry.stat()
        items.append(FileInfo(
            name=entry.name,
            size_bytes=stat.st_size,
            mtime=_dt.datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        ))
    return items


def write_level_01_dir(project_dir: Union[str, Path]) -> Path:
    """Write a LEVEL_01.DIR manifest in ``project_dir``.

    Format: a single line containing the absolute path of ``project_dir``,
    terminated with the OS line separator. Always written (cheap; harmless
    in argv mode).
    """
    project_dir = Path(project_dir).resolve()
    path = project_dir / LEVEL_01_DIR_FILENAME
    path.write_text(str(project_dir) + os.linesep, encoding="utf-8")
    return path


class RunnerError(Exception):
    pass


@dataclass
class RunResult:
    success: bool
    return_code: int
    log_path: Path
    stdout: str
    stderr: str
    generated_files: List[Path] = field(default_factory=list)
    launch_mode: str = DEFAULT_LAUNCH_MODE
    cmd: List[str] = field(default_factory=list)
    false_success_reason: Optional[str] = None


def _build_command(
    hydrus_exe: Path,
    project_dir: Path,
    launch_mode: str,
) -> List[str]:
    if launch_mode == LAUNCH_MODE_ARGV:
        # phydrus convention: <exe> <project_dir> -1
        return [str(hydrus_exe), str(project_dir), "-1"]
    if launch_mode == LAUNCH_MODE_LEVEL_DIR:
        return [str(hydrus_exe)]
    raise RunnerError(
        f"Unknown launch mode {launch_mode!r}. Expected one of: {LAUNCH_MODES}"
    )


def _detect_false_success(stdout: str, stderr: str) -> Optional[str]:
    """Return a reason when return-code-0 output should be downgraded.

    Explicit failure indicators take precedence over success indicators.
    ``Press Enter to continue`` is neutral when paired with HYDRUS's
    successful-completion line, but remains suspicious on its own.
    """
    haystack = (stdout + "\n" + stderr).lower()
    for pattern in FAILURE_PATTERNS:
        if re.search(pattern, haystack):
            return pattern

    has_success = any(pattern in haystack for pattern in SUCCESS_PATTERNS)
    for pattern in NEUTRAL_PROMPT_PATTERNS:
        if pattern in haystack and not has_success:
            return f"{pattern} without successful completion"
    return None


def run_hydrus_project(
    project_dir: Union[str, Path],
    hydrus_exe: Union[str, Path],
    log_dir: Union[str, Path],
    *,
    timeout: Optional[float] = None,
    launch_mode: str = DEFAULT_LAUNCH_MODE,
) -> RunResult:
    project_dir = Path(project_dir)
    hydrus_exe = Path(hydrus_exe)
    log_dir = Path(log_dir)

    if launch_mode not in LAUNCH_MODES:
        raise RunnerError(
            f"Unknown launch_mode={launch_mode!r}. Expected one of: {LAUNCH_MODES}"
        )

    if not project_dir.is_dir():
        raise RunnerError(f"Project directory does not exist: {project_dir}")
    for fname in REQUIRED_INPUT_FILES:
        if not (project_dir / fname).is_file():
            raise RunnerError(
                f"Missing required HYDRUS input file: {project_dir / fname}. "
                "Run main.py --prepare-input before --run."
            )
    if not hydrus_exe.exists():
        raise RunnerError(
            f"HYDRUS executable not found at {hydrus_exe}. "
            "Set HYDRUS_EXE in your environment or .env file."
        )
    if not hydrus_exe.is_file():
        raise RunnerError(f"HYDRUS executable path is not a file: {hydrus_exe}")

    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "hydrus_run.log"

    # Always write LEVEL_01.DIR. argv mode doesn't depend on it but we keep
    # it for compat with the level-dir mechanism, and for diagnostics.
    level_01_path = write_level_01_dir(project_dir)
    level_01_contents = level_01_path.read_text(encoding="utf-8")

    pre_inventory = inventory_dir(project_dir)
    files_before = {fi.name for fi in pre_inventory}

    cmd = _build_command(hydrus_exe, project_dir.resolve(), launch_mode)
    logger.info(
        "Running HYDRUS in %s mode: %s (cwd=%s, timeout=%s)",
        launch_mode, cmd, project_dir, timeout,
    )

    timed_out = False
    note: Optional[str] = None
    return_code: Optional[int] = None
    stdout = ""
    stderr = ""

    try:
        completed = subprocess.run(
            cmd,
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
            input="\n",  # unblock any "Press Enter to continue" prompt
        )
        return_code = completed.returncode
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        note = f"{TIMEOUT_MARKER} after {timeout}s (process killed)"
        partial_out = exc.stdout or ""
        partial_err = exc.stderr or ""
        if isinstance(partial_out, bytes):
            partial_out = partial_out.decode("utf-8", errors="replace")
        if isinstance(partial_err, bytes):
            partial_err = partial_err.decode("utf-8", errors="replace")
        stdout = partial_out
        stderr = partial_err
    except OSError as exc:
        log_path.write_text(
            _format_log(
                cmd, project_dir,
                return_code=None,
                stdout="", stderr="",
                pre_inventory=pre_inventory,
                post_inventory=inventory_dir(project_dir),
                level_01_contents=level_01_contents,
                launch_mode=launch_mode,
                note=f"FAILED to start HYDRUS executable: {exc}",
            ),
            encoding="utf-8",
        )
        raise RunnerError(
            f"Could not start HYDRUS executable {hydrus_exe}: {exc}"
        ) from exc

    post_inventory = inventory_dir(project_dir)

    # False-success detection: if exit 0 but output contains a known
    # error pattern, downgrade to failure.
    false_success_reason: Optional[str] = None
    if not timed_out and return_code == 0:
        false_success_reason = _detect_false_success(stdout, stderr)
        if false_success_reason is not None:
            note_addendum = (
                f"FALSE SUCCESS: return code 0 but output contains "
                f"{false_success_reason!r}; treating as failure."
            )
            note = f"{note}; {note_addendum}" if note else note_addendum

    log_path.write_text(
        _format_log(
            cmd, project_dir,
            return_code=return_code,
            stdout=stdout, stderr=stderr,
            pre_inventory=pre_inventory,
            post_inventory=post_inventory,
            level_01_contents=level_01_contents,
            launch_mode=launch_mode,
            note=note,
        ),
        encoding="utf-8",
    )

    if timed_out:
        raise RunnerError(
            f"HYDRUS run did not finish within {timeout}s. "
            f"Process was terminated; partial log at {log_path}."
        )

    files_after = {fi.name for fi in post_inventory}
    new_names = sorted(files_after - files_before)
    generated_files = [project_dir / name for name in new_names]

    success = (return_code == 0) and (false_success_reason is None)

    return RunResult(
        success=success,
        return_code=return_code if return_code is not None else -1,
        log_path=log_path,
        stdout=stdout,
        stderr=stderr,
        generated_files=generated_files,
        launch_mode=launch_mode,
        cmd=cmd,
        false_success_reason=false_success_reason,
    )


def _format_inventory(label: str, inventory: List[FileInfo]) -> str:
    if not inventory:
        return f"--- {label} ---\n  (no files)\n"
    lines = [f"--- {label} ---"]
    lines.extend(fi.format_line() for fi in inventory)
    return "\n".join(lines) + "\n"


def _format_log(cmd, cwd, *, return_code, stdout, stderr, pre_inventory,
                post_inventory, level_01_contents=None, launch_mode=None,
                note=None) -> str:
    parts = [
        f"command: {cmd}",
        f"cwd: {cwd}",
    ]
    if launch_mode is not None:
        parts.append(f"launch mode: {launch_mode}")
    parts.append(f"return code: {return_code}")
    if note:
        parts.append(f"note: {note}")
    if level_01_contents is not None:
        parts.append("--- LEVEL_01.DIR contents ---")
        parts.append(level_01_contents.rstrip("\n") or "(empty)")
    parts.append(_format_inventory("pre-run inventory", pre_inventory))
    parts.append("--- stdout ---")
    parts.append(stdout or "")
    parts.append("--- stderr ---")
    parts.append(stderr or "")
    parts.append(_format_inventory("post-run inventory", post_inventory))
    return "\n".join(parts) + "\n"
