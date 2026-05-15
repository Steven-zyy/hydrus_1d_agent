"""Pytest configuration for this repository's Windows sandbox.

The Codex desktop sandbox makes directories created with ``mode=0o700``
unreadable on this machine. Pytest uses that mode for ``tmp_path`` base
directories, so tests that rely on ``tmp_path`` fail before reaching any
project code. Use normal Windows-accessible directory creation instead.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path


if sys.platform == "win32":
    from _pytest.tmpdir import TempPathFactory

    def _sandbox_friendly_getbasetemp(self: TempPathFactory) -> Path:
        if self._basetemp is not None:
            return self._basetemp

        if self._given_basetemp is not None:
            basetemp = self._given_basetemp
            if basetemp.exists():
                # Keep the requested path usable even when an earlier pytest
                # run left an unreadable 0o700 directory behind.
                basetemp = basetemp.with_name(f"{basetemp.name}_{os.getpid()}")
            try:
                basetemp.mkdir(parents=True, exist_ok=False)
            except PermissionError:
                basetemp = Path.cwd() / ".codex_tmp" / f"{basetemp.name}_{os.getpid()}"
                basetemp.parent.mkdir(parents=True, exist_ok=True)
                basetemp.mkdir(exist_ok=False)
        else:
            temproot = Path(
                os.environ.get("PYTEST_DEBUG_TEMPROOT")
                or os.environ.get("TMP")
                or os.environ.get("TEMP")
                or tempfile.gettempdir()
            ).resolve()
            rootdir = temproot / "pytest-of-codex"
            rootdir.mkdir(parents=True, exist_ok=True)
            basetemp = rootdir / f"pytest-{os.getpid()}"
            if basetemp.exists():
                shutil.rmtree(basetemp)
            basetemp.mkdir()

        self._basetemp = basetemp.resolve()
        self._trace("new basetemp", self._basetemp)
        return self._basetemp

    TempPathFactory.getbasetemp = _sandbox_friendly_getbasetemp

    def _sandbox_friendly_mktemp(
        self: TempPathFactory, basename: str, numbered: bool = True,
    ) -> Path:
        basename = self._ensure_relative_to_basetemp(basename)
        root = self.getbasetemp()
        if not numbered:
            path = root / basename
            path.mkdir()
            return path

        index = 0
        while True:
            path = root / f"{basename}{index}"
            try:
                path.mkdir()
            except FileExistsError:
                index += 1
                continue
            self._trace("mktemp", path)
            return path

    TempPathFactory.mktemp = _sandbox_friendly_mktemp
