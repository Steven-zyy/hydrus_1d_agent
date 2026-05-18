"""HYDRUS-1D agent package.

Milestone 1: configuration loading, validation, run folder creation.
Milestone 2: phydrus adapter that writes HYDRUS-1D input files.
Milestone 3: runner that invokes the local HYDRUS-1D executable.
Later milestones will add output reading, plotting, and reporting.
"""

from hydrus_agent.case import create_run_folder
from hydrus_agent.schema import ModelConfig
from hydrus_agent.validator import ConfigError, load_config

__version__ = "0.6.0"

__all__ = [
    "ConfigError",
    "ModelConfig",
    "create_run_folder",
    "load_config",
    "prepare_phydrus_project",
    "UnsupportedFeatureError",
    "run_hydrus_project",
    "RunResult",
    "RunnerError",
]


_LAZY = {
    "prepare_phydrus_project": ("hydrus_agent.phydrus_adapter", "prepare_phydrus_project"),
    "UnsupportedFeatureError": ("hydrus_agent.phydrus_adapter", "UnsupportedFeatureError"),
    "run_hydrus_project": ("hydrus_agent.runner", "run_hydrus_project"),
    "RunResult": ("hydrus_agent.runner", "RunResult"),
    "RunnerError": ("hydrus_agent.runner", "RunnerError"),
}


def __getattr__(name):
    """Lazy re-exports so importing the package does not pull in phydrus
    or the runner when the caller only wants milestone-1 features."""
    if name in _LAZY:
        import importlib
        module_name, attr = _LAZY[name]
        return getattr(importlib.import_module(module_name), attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
