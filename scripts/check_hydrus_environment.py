"""Check that the local environment is ready for Milestone 2.

Verifies that ``phydrus`` is importable and that ``HYDRUS_EXE`` resolves to
an existing file. Does NOT execute HYDRUS-1D.

The ``HYDRUS_EXE`` resolution logic lives in ``hydrus_agent.env`` so this
script and ``main.py --prepare-input`` agree on where to look.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Tuple

# Make sure ``hydrus_agent`` is importable when this script is run directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hydrus_agent.env import DEFAULT_ENV_FILE, ENV_VAR, resolve_hydrus_exe  # noqa: E402


def check_phydrus() -> Tuple[bool, str]:
    """Try to import phydrus and report version. No side effects."""
    try:
        import phydrus  # type: ignore[import-not-found]
    except ImportError as exc:
        return False, f"phydrus is NOT installed ({exc})"

    version = getattr(phydrus, "__version__", "unknown")
    return True, f"phydrus is installed (version: {version})"


def check_executable(exe_path_str: Optional[str]) -> Tuple[bool, str]:
    """Verify that the supplied path points at an existing file."""
    if exe_path_str is None:
        return False, (
            f"{ENV_VAR} is not set "
            f"(checked process environment and {DEFAULT_ENV_FILE})"
        )

    exe_path = Path(exe_path_str)
    if not exe_path.exists():
        return False, f"HYDRUS executable not found at {exe_path}"
    if not exe_path.is_file():
        return False, f"HYDRUS executable path is not a file: {exe_path}"

    return True, f"HYDRUS executable exists at {exe_path}"


def main() -> int:
    print("HYDRUS-1D environment check")
    print("=" * 50)

    phydrus_ok, phydrus_msg = check_phydrus()
    print(f"  [{'OK  ' if phydrus_ok else 'FAIL'}] {phydrus_msg}")

    exe_path_str, source = resolve_hydrus_exe()
    if exe_path_str is not None:
        print(f"  [INFO] {ENV_VAR} read from {source}")

    exe_ok, exe_msg = check_executable(exe_path_str)
    print(f"  [{'OK  ' if exe_ok else 'FAIL'}] {exe_msg}")

    print("=" * 50)
    if phydrus_ok and exe_ok:
        print("Environment is READY for Milestone 2.")
        print("(HYDRUS was NOT executed by this check.)")
        return 0

    print("Environment is NOT ready for Milestone 2.")
    if not phydrus_ok:
        print("  - install phydrus:  pip install phydrus")
    if not exe_ok:
        print(f"  - set {ENV_VAR} to the absolute path of your HYDRUS-1D executable")
        print("    See README.md ('HYDRUS_EXE Setup') for options.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
