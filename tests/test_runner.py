"""Tests for hydrus_agent.runner.

These tests use a platform-aware fake executable so they do not require the
real HYDRUS-1D binary.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

from hydrus_agent.runner import (
    REQUIRED_INPUT_FILES,
    TIMEOUT_MARKER,
    RunnerError,
    RunResult,
    inventory_dir,
    run_hydrus_project,
)


def _make_fake_exe(tmp_path: Path, *, return_code: int = 0,
                   output_files: tuple = ("Obs_Node.out", "T_Level.out"),
                   stdout: str = "Fake HYDRUS started\nFake HYDRUS finished\n",
                   stderr: str = "") -> Path:
    if sys.platform == "win32":
        exe = tmp_path / "fake_hydrus.bat"
        lines = ["@echo off"]
        for line in stdout.splitlines():
            lines.append(f"echo {line}")
        for fname in output_files:
            lines.append(f"echo. > {fname}")
        if stderr:
            for line in stderr.splitlines():
                lines.append(f"echo {line} 1>&2")
        lines.append(f"exit /b {return_code}")
        exe.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    else:
        exe = tmp_path / "fake_hydrus.sh"
        body = ["#!/bin/sh"]
        for line in stdout.splitlines():
            body.append(f'echo "{line}"')
        for fname in output_files:
            body.append(f'touch "{fname}"')
        if stderr:
            for line in stderr.splitlines():
                body.append(f'echo "{line}" >&2')
        body.append(f"exit {return_code}")
        exe.write_text("\n".join(body) + "\n", encoding="utf-8")
        exe.chmod(0o755)
    return exe


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    p = tmp_path / "hydrus_project"
    p.mkdir()
    for fname in REQUIRED_INPUT_FILES:
        (p / fname).write_text("(stub input file)", encoding="utf-8")
    return p


@pytest.fixture
def log_dir(tmp_path: Path) -> Path:
    return tmp_path / "logs"


def test_run_success(project_dir, log_dir, tmp_path):
    exe = _make_fake_exe(tmp_path, return_code=0,
                         output_files=("Obs_Node.out", "T_Level.out"))
    result = run_hydrus_project(project_dir, exe, log_dir)
    assert isinstance(result, RunResult)
    assert result.success is True
    assert result.return_code == 0
    assert "Fake HYDRUS finished" in result.stdout
    names = {p.name for p in result.generated_files}
    assert "Obs_Node.out" in names
    assert "T_Level.out" in names
    assert "SELECTOR.IN" not in names
    assert "PROFILE.DAT" not in names


def test_run_nonzero_returncode_does_not_raise(project_dir, log_dir, tmp_path):
    exe = _make_fake_exe(tmp_path, return_code=2, output_files=(),
                         stdout="something failed\n",
                         stderr="ERROR: convergence not reached\n")
    result = run_hydrus_project(project_dir, exe, log_dir)
    assert result.success is False
    assert result.return_code == 2
    assert "convergence not reached" in result.stderr
    assert result.generated_files == []


def test_missing_inputs_raises(tmp_path, log_dir):
    empty = tmp_path / "empty_project"
    empty.mkdir()
    exe = _make_fake_exe(tmp_path)
    with pytest.raises(RunnerError) as excinfo:
        run_hydrus_project(empty, exe, log_dir)
    assert "SELECTOR.IN" in str(excinfo.value)


def test_missing_project_dir_raises(tmp_path, log_dir):
    nonexistent = tmp_path / "no_such"
    exe = _make_fake_exe(tmp_path)
    with pytest.raises(RunnerError) as excinfo:
        run_hydrus_project(nonexistent, exe, log_dir)
    assert "Project directory does not exist" in str(excinfo.value)


def test_missing_exe_raises(project_dir, log_dir, tmp_path):
    bogus = tmp_path / "definitely_not_here.exe"
    with pytest.raises(RunnerError) as excinfo:
        run_hydrus_project(project_dir, bogus, log_dir)
    assert "HYDRUS executable not found" in str(excinfo.value)


def test_log_file_is_written(project_dir, log_dir, tmp_path):
    exe = _make_fake_exe(tmp_path, stdout="hello stdout\n", stderr="hello stderr\n")
    result = run_hydrus_project(project_dir, exe, log_dir)
    assert result.log_path.is_file()
    log_text = result.log_path.read_text(encoding="utf-8")
    assert "command:" in log_text
    assert "cwd:" in log_text
    assert "return code: 0" in log_text
    assert "hello stdout" in log_text
    assert "hello stderr" in log_text


def test_log_contains_pre_and_post_inventories(project_dir, log_dir, tmp_path):
    exe = _make_fake_exe(tmp_path, return_code=0, output_files=("Obs_Node.out",))
    result = run_hydrus_project(project_dir, exe, log_dir)
    log_text = result.log_path.read_text(encoding="utf-8")
    assert "--- pre-run inventory ---" in log_text
    assert "--- post-run inventory ---" in log_text
    pre_section = log_text.split("--- pre-run inventory ---")[1].split("--- stdout ---")[0]
    assert "SELECTOR.IN" in pre_section
    assert "PROFILE.DAT" in pre_section
    post_section = log_text.split("--- post-run inventory ---")[1]
    assert "Obs_Node.out" in post_section


def test_timeout_terminates_process_and_raises(project_dir, log_dir, tmp_path):
    if sys.platform == "win32":
        pytest.skip("sleep-based timeout test uses /bin/sh; skipped on Windows")
    exe = tmp_path / "slow.sh"
    exe.write_text("#!/bin/sh\necho 'starting'\nsleep 5\necho 'done'\n", encoding="utf-8")
    exe.chmod(0o755)
    with pytest.raises(RunnerError) as excinfo:
        run_hydrus_project(project_dir, exe, log_dir, timeout=0.5)
    assert "did not finish within" in str(excinfo.value)
    log_text = (log_dir / "hydrus_run.log").read_text(encoding="utf-8")
    assert TIMEOUT_MARKER in log_text
    assert "process killed" in log_text
    assert "--- pre-run inventory ---" in log_text
    assert "--- post-run inventory ---" in log_text


def test_post_inventory_captures_partial_files_on_timeout(project_dir, log_dir, tmp_path):
    if sys.platform == "win32":
        pytest.skip("partial-write timeout test uses /bin/sh; skipped on Windows")
    exe = tmp_path / "partial.sh"
    exe.write_text("#!/bin/sh\ntouch H_PARTIAL.out\nsleep 5\n", encoding="utf-8")
    exe.chmod(0o755)
    with pytest.raises(RunnerError):
        run_hydrus_project(project_dir, exe, log_dir, timeout=0.5)
    log_text = (log_dir / "hydrus_run.log").read_text(encoding="utf-8")
    post_section = log_text.split("--- post-run inventory ---")[1]
    assert "H_PARTIAL.out" in post_section


def test_inventory_dir_returns_files_only(tmp_path):
    (tmp_path / "a.txt").write_text("hi")
    (tmp_path / "b.txt").write_text("hello world")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "nested.txt").write_text("nope")
    items = inventory_dir(tmp_path)
    names = [item.name for item in items]
    assert names == ["a.txt", "b.txt"]
    assert items[0].size_bytes == 2
    assert items[1].size_bytes == 11
    assert "T" in items[0].mtime


def test_subprocess_actually_executed(project_dir, log_dir, tmp_path):
    sentinel = "SENTINEL_FROM_FAKE_HYDRUS"
    if sys.platform == "win32":
        exe = tmp_path / "fake_hydrus.bat"
        exe.write_text(textwrap.dedent(f"""\
            @echo off
            echo {sentinel} > sentinel.out
            exit /b 0
            """), encoding="utf-8")
    else:
        exe = tmp_path / "fake_hydrus.sh"
        exe.write_text(textwrap.dedent(f"""\
            #!/bin/sh
            echo "{sentinel}" > sentinel.out
            exit 0
            """), encoding="utf-8")
        exe.chmod(0o755)
    run_hydrus_project(project_dir, exe, log_dir)
    sentinel_path = project_dir / "sentinel.out"
    assert sentinel_path.is_file()
    assert sentinel in sentinel_path.read_text(encoding="utf-8")


# --- Milestone 3.1 tests --------------------------------------------------


def test_level_01_dir_is_created(project_dir, log_dir, tmp_path):
    """run_hydrus_project must create LEVEL_01.DIR in the project directory
    containing the absolute path of the project directory."""
    from hydrus_agent.runner import LEVEL_01_DIR_FILENAME

    exe = _make_fake_exe(tmp_path, return_code=0, output_files=())
    run_hydrus_project(project_dir, exe, log_dir)

    level_01 = project_dir / LEVEL_01_DIR_FILENAME
    assert level_01.is_file(), "LEVEL_01.DIR must exist after the run"
    contents = level_01.read_text(encoding="utf-8")
    # First non-empty line should equal the absolute project_dir path.
    first_line = contents.splitlines()[0]
    assert first_line == str(project_dir.resolve()), (
        f"LEVEL_01.DIR first line should be {project_dir.resolve()}, got {first_line!r}"
    )


def test_runner_does_not_hang_on_press_enter(project_dir, log_dir, tmp_path):
    """A fake exe that reads stdin must NOT hang the runner.

    With ``input='\\n'`` the runner sends a single newline; the fake exe's
    ``read`` returns immediately. The exe exits 0, but because the stdout
    contains the false-success pattern "Press Enter to continue", the
    runner correctly downgrades ``success`` to False.
    """
    if sys.platform == "win32":
        pytest.skip("stdin-blocking test uses /bin/sh; skipped on Windows")

    exe = tmp_path / "press_enter.sh"
    exe.write_text(
        "#!/bin/sh\n"
        "echo 'Press Enter to continue'\n"
        "read line\n"
        "echo 'Continued'\n"
        "exit 0\n",
        encoding="utf-8",
    )
    exe.chmod(0o755)

    # 5s is far more than the read should take given we feed stdin a newline.
    # The point of the test is no hang: if the runner blocked, the timeout
    # would fire and RunnerError would be raised.
    result = run_hydrus_project(project_dir, exe, log_dir, timeout=5.0)
    assert result.return_code == 0, "exe exited cleanly, no timeout"
    assert "Press Enter to continue" in result.stdout
    assert "Continued" in result.stdout
    # And the false-success rule correctly flags it.
    assert result.success is False
    assert result.false_success_reason == (
        "press enter to continue without successful completion"
    )


def test_hydrus_side_error_captured_in_log(project_dir, log_dir, tmp_path):
    """A simulated HYDRUS error (non-zero exit + stderr message) must end up
    in hydrus_run.log so the user can diagnose it."""
    err_msg = "ERROR: Folder with input data of the specified project does not exist"
    exe = _make_fake_exe(
        tmp_path,
        return_code=1,
        output_files=(),
        stdout="",
        stderr=err_msg + "\n",
    )
    result = run_hydrus_project(project_dir, exe, log_dir)
    assert result.success is False
    assert result.return_code == 1
    log_text = result.log_path.read_text(encoding="utf-8")
    assert err_msg in log_text, "HYDRUS-side error must appear in hydrus_run.log"
    assert "return code: 1" in log_text


def test_log_includes_level_01_dir_contents(project_dir, log_dir, tmp_path):
    """The log file's LEVEL_01.DIR section must show what was written."""
    exe = _make_fake_exe(tmp_path, return_code=0, output_files=())
    result = run_hydrus_project(project_dir, exe, log_dir)
    log_text = result.log_path.read_text(encoding="utf-8")
    assert "--- LEVEL_01.DIR contents ---" in log_text
    assert str(project_dir.resolve()) in log_text


# --- Milestone 3.1b tests: launch modes + false-success detection ---------


def _make_argv_recording_exe(tmp_path: Path, *, return_code: int = 0,
                             stdout: str = "ok\n") -> Path:
    """Fake exe that writes its argv to a file 'argv.json' in cwd, then exits."""
    if sys.platform == "win32":
        pytest.skip("argv-recording fake exe is /bin/sh; skipped on Windows")
    exe = tmp_path / "record_argv.sh"
    exe.write_text(
        '#!/bin/sh\n'
        'python3 -c "import json,sys; '
        'open(\\"argv.json\\",\\"w\\").write(json.dumps(sys.argv[1:]))" '
        '"$@"\n'
        f'echo "{stdout.rstrip()}"\n'
        f'exit {return_code}\n',
        encoding="utf-8",
    )
    exe.chmod(0o755)
    return exe


def test_argv_launch_mode_passes_project_path_and_minus_1(
    project_dir, log_dir, tmp_path,
):
    """In argv mode the runner must invoke [exe, str(project_dir), "-1"]."""
    import json

    exe = _make_argv_recording_exe(tmp_path, return_code=0)
    result = run_hydrus_project(
        project_dir, exe, log_dir, launch_mode="argv",
    )
    assert result.success is True
    assert result.launch_mode == "argv"

    argv_file = project_dir / "argv.json"
    assert argv_file.is_file(), "fake exe should have recorded its argv"
    recorded = json.loads(argv_file.read_text())
    # Two extra args beyond argv[0]: project_dir then "-1".
    assert len(recorded) == 2, f"unexpected argv: {recorded}"
    assert Path(recorded[0]).resolve() == project_dir.resolve()
    assert recorded[1] == "-1"

    # The result also exposes the cmd it ran:
    assert result.cmd[1:] == [str(project_dir.resolve()), "-1"]


def test_level_dir_launch_mode_passes_only_exe(
    project_dir, log_dir, tmp_path,
):
    """In level-dir mode the runner must invoke [exe] only - no extra argv."""
    import json

    exe = _make_argv_recording_exe(tmp_path, return_code=0)
    result = run_hydrus_project(
        project_dir, exe, log_dir, launch_mode="level-dir",
    )
    assert result.success is True
    assert result.launch_mode == "level-dir"
    argv_file = project_dir / "argv.json"
    recorded = json.loads(argv_file.read_text())
    assert recorded == [], f"level-dir mode should pass no extra argv, got {recorded}"


def test_argv_mode_does_not_require_level_01_dir(
    project_dir, log_dir, tmp_path,
):
    """argv mode shouldn't fail if LEVEL_01.DIR is removed - the runner
    re-creates it but the exe doesn't depend on it in argv mode."""
    from hydrus_agent.runner import LEVEL_01_DIR_FILENAME

    # Verify the runner writes LEVEL_01.DIR but the exe ignores it.
    exe = _make_argv_recording_exe(tmp_path, return_code=0)
    result = run_hydrus_project(project_dir, exe, log_dir, launch_mode="argv")
    assert result.success is True
    assert (project_dir / LEVEL_01_DIR_FILENAME).is_file()


def test_false_success_path_too_long_pattern(
    project_dir, log_dir, tmp_path,
):
    """exit 0 + 'does not exist or pathway is too long or corrupted' in
    stdout must be reported as success=False with a false_success_reason."""
    bad_msg = "Folder with input data of the specified project does not exist or pathway is too long or corrupted"
    exe = _make_fake_exe(
        tmp_path, return_code=0, output_files=(),
        stdout=bad_msg + "\n",
    )
    result = run_hydrus_project(project_dir, exe, log_dir)
    assert result.return_code == 0
    assert result.success is False, "false-success pattern must downgrade success"
    assert result.false_success_reason is not None
    assert "pathway is too long" in result.false_success_reason


def test_successful_completion_with_press_enter_is_success(project_dir, log_dir, tmp_path):
    """A normal PC-Progress console run prints 'Press Enter to continue'
    after a successful completion. That prompt must not downgrade success."""
    exe = _make_fake_exe(
        tmp_path,
        return_code=0,
        output_files=("Obs_Node.out",),
        stdout=(
            "Beginning of numerical solution.\n"
            "Calculations have finished successfully.\n"
            "Press Enter to continue\n"
        ),
    )
    result = run_hydrus_project(project_dir, exe, log_dir)
    assert result.return_code == 0
    assert result.success is True
    assert result.false_success_reason is None


def test_press_enter_without_success_indicator_is_not_accepted(
    project_dir, log_dir, tmp_path,
):
    """A bare prompt without HYDRUS's explicit success line remains
    suspicious and must not be silently accepted."""
    exe = _make_fake_exe(
        tmp_path, return_code=0, output_files=(),
        stdout="Press Enter to continue\n",
    )
    result = run_hydrus_project(project_dir, exe, log_dir)
    assert result.success is False
    assert result.false_success_reason is not None
    assert "press enter" in result.false_success_reason.lower()


def test_failure_indicator_beats_success_indicator(project_dir, log_dir, tmp_path):
    """If HYDRUS prints both success-looking and error-looking text, the
    explicit failure indicator takes precedence."""
    bad_msg = (
        "Calculations have finished successfully.\n"
        "Folder with input data of the specified project does not exist "
        "or pathway is too long or corrupted\n"
        "Press Enter to continue\n"
    )
    exe = _make_fake_exe(
        tmp_path, return_code=0, output_files=(), stdout=bad_msg,
    )
    result = run_hydrus_project(project_dir, exe, log_dir)
    assert result.return_code == 0
    assert result.success is False
    assert result.false_success_reason is not None
    assert "pathway is too long" in result.false_success_reason


def test_return_zero_with_cannot_open_is_failure(project_dir, log_dir, tmp_path):
    exe = _make_fake_exe(
        tmp_path,
        return_code=0,
        output_files=(),
        stdout="Cannot open SELECTOR.IN\nPress Enter to continue\n",
    )
    result = run_hydrus_project(project_dir, exe, log_dir)
    assert result.success is False
    assert result.false_success_reason is not None
    assert "cannot open" in result.false_success_reason


def test_genuine_success_not_flagged(project_dir, log_dir, tmp_path):
    """Sanity check: a clean exit 0 with normal stdout must NOT be flagged
    as false success."""
    exe = _make_fake_exe(
        tmp_path, return_code=0, output_files=("Obs_Node.out",),
        stdout="Simulation finished successfully\n",
    )
    result = run_hydrus_project(project_dir, exe, log_dir)
    assert result.success is True
    assert result.false_success_reason is None


def test_log_records_launch_mode(project_dir, log_dir, tmp_path):
    """The log file must contain a 'launch mode:' line."""
    exe = _make_fake_exe(tmp_path, return_code=0, output_files=())
    result = run_hydrus_project(
        project_dir, exe, log_dir, launch_mode="argv",
    )
    log_text = result.log_path.read_text(encoding="utf-8")
    assert "launch mode: argv" in log_text


def test_unknown_launch_mode_raises(project_dir, log_dir, tmp_path):
    exe = _make_fake_exe(tmp_path)
    with pytest.raises(RunnerError) as excinfo:
        run_hydrus_project(
            project_dir, exe, log_dir, launch_mode="not-a-mode",
        )
    assert "Unknown launch_mode" in str(excinfo.value)
