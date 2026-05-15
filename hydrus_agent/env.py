"""Resolve ``HYDRUS_EXE`` from a process env var or a project ``.env`` file.

Single source of truth so ``main.py`` and ``scripts/check_hydrus_environment.py``
don't drift apart.

Resolution order:
    1. ``HYDRUS_EXE`` in the process environment (``os.environ``).
    2. ``HYDRUS_EXE`` in ``<project_root>/.env``.
    3. Not found.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional, Tuple


# Project root is the parent of this package's parent (..\hydrus_agent\env.py -> ..)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"
ENV_VAR = "HYDRUS_EXE"


def parse_dotenv(path: Path) -> Dict[str, str]:
    """Minimal ``KEY=VALUE`` parser. Returns ``{}`` if the file is missing.

    Lines starting with ``#`` and blank lines are skipped. Surrounding
    single/double quotes around the value are stripped. Escape sequences are
    NOT expanded — keep paths on a single line.
    """
    if not path.is_file():
        return {}

    parsed: Dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            parsed[key] = value
    return parsed


def resolve_hydrus_exe(
    env_file: Path = DEFAULT_ENV_FILE,
) -> Tuple[Optional[str], str]:
    """Return ``(path_string, source_description)``.

    ``source_description`` is one of:
        - ``"process environment variable"``
        - ``".env file (<path>)"``
        - ``"unset"``  (in which case ``path_string`` is ``None``)
    """
    val = os.environ.get(ENV_VAR)
    if val:
        return val, "process environment variable"

    parsed = parse_dotenv(env_file)
    if parsed.get(ENV_VAR):
        return parsed[ENV_VAR], f".env file ({env_file})"

    return None, "unset"
