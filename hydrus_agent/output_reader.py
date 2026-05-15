"""HYDRUS-1D output discovery and parsing (milestone 4).

Scope:
    * Discover output files case-insensitively in a project directory.
    * Parse the milestone-4 output files into pandas DataFrames:
        Balance.out (wide, time-blocks)
        T_Level.out (wide, whitespace tabular)
        Run_Inf.out (wide, whitespace tabular)
        Obs_Node.out (long: time x node)
        Nod_Inf.out (long: time x node)
    * Return empty DataFrames for empty files (HYDRUS may produce 0-byte
      files when the corresponding output is suppressed).
    * Read-only: never modifies or deletes the source files.

Out of scope (later milestones):
    * Plotting, report generation, auto-correction.
    * Parsing I_Check.out (input echo) and Profile.out (final profile).
"""

from __future__ import annotations

import logging
import re
from io import StringIO
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Union

import pandas as pd

logger = logging.getLogger(__name__)


DEFAULT_OUTPUT_NAMES = (
    "Obs_Node.out",
    "T_Level.out",
    "Balance.out",
    "Nod_Inf.out",
    "Run_Inf.out",
)

_SOLUTE_NAME_RE = re.compile(r"^solute(?P<index>\d+)\.out$", re.IGNORECASE)


# --- Discovery -----------------------------------------------------------


def find_output_file(project_dir: Union[str, Path], filename: str) -> Optional[Path]:
    """Return the path of ``filename`` inside ``project_dir`` regardless of
    casing. Returns ``None`` if no match."""
    project_dir = Path(project_dir)
    if not project_dir.is_dir():
        return None
    target = filename.lower()
    for entry in project_dir.iterdir():
        if entry.is_file() and entry.name.lower() == target:
            return entry
    return None


def discover_outputs(
    project_dir: Union[str, Path],
    names=DEFAULT_OUTPUT_NAMES,
) -> Dict[str, Optional[Path]]:
    """Return ``{canonical_name: matched_path_or_None}``."""
    out = {name: find_output_file(project_dir, name) for name in names}
    if tuple(names) == DEFAULT_OUTPUT_NAMES:
        for canonical, path in _discover_solute_outputs(project_dir).items():
            out[canonical] = path
    return out


def _discover_solute_outputs(project_dir: Union[str, Path]) -> Dict[str, Path]:
    project_dir = Path(project_dir)
    if not project_dir.is_dir():
        return {}
    matches = []
    for entry in project_dir.iterdir():
        if not entry.is_file():
            continue
        m = _SOLUTE_NAME_RE.match(entry.name)
        if m:
            idx = int(m.group("index"))
            matches.append((idx, f"Solute{idx}.out", entry))
    return {canonical: path for _, canonical, path in sorted(matches)}


# --- Helpers --------------------------------------------------------------


def _is_empty(path: Optional[Path]) -> bool:
    return path is None or not path.is_file() or path.stat().st_size == 0


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame()


def _clean_column(name: str) -> str:
    """Normalise a HYDRUS column header into a Python-safe identifier while
    PRESERVING case.

    Examples:
        'rTop'         -> 'rTop'
        'sum(rTop)'    -> 'sum_rTop'
        'h Mean'       -> 'h_Mean'
        'Cum(WTrans)'  -> 'Cum_WTrans'
        'v/KsTop'      -> 'v_KsTop'
    """
    out = str(name).strip()
    out = re.sub(r"[()\[\]{}]", " ", out)
    out = re.sub(r"[^\w\s]", "_", out)
    out = re.sub(r"\s+", "_", out)
    out = re.sub(r"_+", "_", out)
    out = out.strip("_")
    return out


def _is_numeric_token(token: str) -> bool:
    try:
        float(token)
    except ValueError:
        return False
    return True


def _rows_to_df(rows: Iterable[Dict]) -> pd.DataFrame:
    rows = list(rows)
    if not rows:
        return _empty_df()
    return pd.DataFrame(rows)


# --- Balance.out ----------------------------------------------------------

# Each time block is a sequence of "Key [unit]  value..." lines:
#   Time       [T]        0.0000
#   W-volume   [L]        0.12240E+00  0.12240E+00
#   ...

_BALANCE_LINE_KEY = re.compile(
    r"^\s*(?P<key>[A-Za-z][\w\-./ ]*?)\s+\[(?P<unit>[^\]]*)\]\s+(?P<rest>.+)$"
)

_BALANCE_KEY_MAP = {
    "time": "time",
    "length": "length",
    "w-volume": "w_volume",
    "in-flow": "in_flow",
    "h mean": "h_mean",
    "top flux": "top_flux",
    "bot flux": "bot_flux",
    "watbalt": "wat_bal_t",
    "watbalr": "wat_bal_r",
}


def read_balance(path: Optional[Path]) -> pd.DataFrame:
    """Parse Balance.out (block format) into a wide-form DataFrame.

    One row per time step, columns (when available):
    ``time, length, w_volume, in_flow, h_mean, top_flux, bot_flux,
    wat_bal_t, wat_bal_r``.
    """
    if _is_empty(path):
        return _empty_df()
    text = path.read_text(encoding="utf-8", errors="replace")
    rows: List[Dict[str, float]] = []
    current: Optional[Dict[str, float]] = None

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        m = _BALANCE_LINE_KEY.match(line)
        if not m:
            continue
        key_raw = m.group("key").strip().lower()
        rest = m.group("rest")
        token_match = re.search(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", rest)
        if token_match is None:
            continue
        try:
            value = float(token_match.group(0))
        except ValueError:
            continue
        canonical = _BALANCE_KEY_MAP.get(key_raw)
        if canonical is None:
            continue
        if canonical == "time":
            if current is not None:
                rows.append(current)
            current = {"time": value}
        else:
            if current is None:
                continue
            current[canonical] = value
    if current is not None:
        rows.append(current)
    if not rows:
        return _empty_df()
    columns = ["time", "length", "w_volume", "in_flow", "h_mean",
               "top_flux", "bot_flux", "wat_bal_t", "wat_bal_r"]
    df = pd.DataFrame(rows)
    return df.reindex(columns=[c for c in columns if c in df.columns])


# --- Generic whitespace-table parser (used by T_Level and Run_Inf) -------


def _read_whitespace_table(
    path: Optional[Path],
    header_marker: Optional[str] = None,
) -> pd.DataFrame:
    """Generic whitespace-separated table reader for HYDRUS .out files.

    Strips:
        * banner lines (``*``, ``Date:``, ``Units``, ``Program HYDRUS``)
        * units row directly under the header (``[T]``, ``[L/T]`` ...)
        * trailing ``end`` marker
    """
    if _is_empty(path):
        return _empty_df()
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    header_idx: Optional[int] = None
    for idx, ln in enumerate(lines):
        stripped = ln.strip()
        if not stripped:
            continue
        if stripped.startswith(("*", "Date:", "Units")):
            continue
        if stripped.lower().startswith("program hydrus"):
            continue
        if header_marker is not None and header_marker.lower() not in stripped.lower():
            continue
        header_idx = idx
        break
    if header_idx is None:
        return _empty_df()

    # Skip a possible units row directly under the header.
    body_start = header_idx + 1
    if body_start < len(lines):
        peek = lines[body_start].strip()
        if peek.startswith("["):
            body_start += 1

    body_lines = [
        ln for ln in lines[body_start:]
        if ln.strip() and ln.strip().lower() != "end"
    ]
    block = "\n".join([lines[header_idx]] + body_lines)
    try:
        df = pd.read_csv(StringIO(block), sep=r"\s+", engine="python", comment="*")
    except Exception as exc:
        logger.warning("Could not parse %s: %s", path, exc)
        return _empty_df()

    df.columns = [_clean_column(c) for c in df.columns]
    return df.reset_index(drop=True)


def read_t_level(path: Optional[Path]) -> pd.DataFrame:
    """Parse T_Level.out. Returns 22-column wide DataFrame on a populated
    file, empty DataFrame on a 0-byte file."""
    return _read_whitespace_table(path, header_marker="rTop")


def read_run_inf(path: Optional[Path]) -> pd.DataFrame:
    """Parse Run_Inf.out (8 columns: TLevel, Time, dt, Iter, ItCum, KodT,
    KodB, Convergency). Convergency is a string ``T``/``F``."""
    return _read_whitespace_table(path, header_marker="TLevel")


# --- Obs_Node.out ---------------------------------------------------------


def _normalise_obs_variable(name: str) -> str:
    """Return a stable lowercase column name for an Obs_Node variable."""
    cleaned = _clean_column(name).lower()
    return cleaned or "value"


def _dedupe_columns(names: List[str]) -> List[str]:
    """Make duplicate column names stable by appending a numeric suffix."""
    seen: Dict[str, int] = {}
    out: List[str] = []
    for name in names:
        count = seen.get(name, 0) + 1
        seen[name] = count
        out.append(name if count == 1 else f"{name}_{count}")
    return out


def read_obs_node(path: Optional[Path]) -> pd.DataFrame:
    """Parse Obs_Node.out into long format.

    Columns start with ``time, node`` followed by the per-node variables found
    in the HYDRUS sub-header. Simple water-flow outputs produce
    ``time, node, h, theta, temp``. Official heat/solute-style outputs with
    extra variables, for example ``Conc``, keep those variables as additional
    columns such as ``conc``.
    """
    if _is_empty(path):
        return _empty_df()
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    node_ids: List[int] = []
    node_line_idx: Optional[int] = None
    for i, line in enumerate(lines):
        ms = re.findall(r"Node\(\s*(\d+)\s*\)", line)
        if ms:
            node_ids = [int(n) for n in ms]
            node_line_idx = i
            break
    if not node_ids:
        return _empty_df()

    # Find the sub-header line with "time" and "theta".
    sub_header_idx: Optional[int] = None
    for i in range(node_line_idx + 1, len(lines)):
        s = lines[i].lower()
        if "time" in s and "theta" in s:
            sub_header_idx = i
            break
    if sub_header_idx is None:
        return _empty_df()

    header_tokens = lines[sub_header_idx].split()
    if len(header_tokens) < 2 or header_tokens[0].lower() != "time":
        return _empty_df()
    variable_tokens = header_tokens[1:]
    if len(variable_tokens) % len(node_ids) != 0:
        return _empty_df()
    variables_per_node = len(variable_tokens) // len(node_ids)
    variables = _dedupe_columns([
        _normalise_obs_variable(token)
        for token in variable_tokens[:variables_per_node]
    ])

    rows = []
    expected_cols = 1 + variables_per_node * len(node_ids)
    for line in lines[sub_header_idx + 1:]:
        s = line.strip()
        if not s or s.lower() == "end":
            continue
        toks = s.split()
        if len(toks) != expected_cols:
            continue
        try:
            time_val = float(toks[0])
        except ValueError:
            continue
        for j, node in enumerate(node_ids):
            base = 1 + variables_per_node * j
            try:
                row = {"time": time_val, "node": node}
                for offset, variable in enumerate(variables):
                    row[variable] = float(toks[base + offset])
                rows.append(row)
            except (ValueError, IndexError):
                continue

    if not rows:
        return _empty_df()
    return pd.DataFrame(rows, columns=["time", "node", *variables])


# --- Nod_Inf.out ----------------------------------------------------------


_TIME_BLOCK_RE = re.compile(r"^\s*Time:\s*([+\-]?\d+(?:\.\d+)?(?:[eE][+\-]?\d+)?)")


def read_nod_inf(path: Optional[Path]) -> pd.DataFrame:
    """Parse Nod_Inf.out into long format.

    Columns: ``time, node, depth, head, moisture, K, C, flux, sink, kappa,
    vKsTop, temp`` plus optional ``conc_N`` and ``sorb_N`` solute columns
    when HYDRUS writes them. One row per (time, node) pair.
    """
    if _is_empty(path):
        return _empty_df()
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    rows: List[Dict] = []
    i = 0
    n_lines = len(lines)
    while i < n_lines:
        m = _TIME_BLOCK_RE.match(lines[i])
        if m is None:
            i += 1
            continue
        try:
            time_val = float(m.group(1))
        except ValueError:
            i += 1
            continue
        # Advance to the column header line that starts with "Node".
        j = i + 1
        while j < n_lines and not lines[j].strip().startswith("Node"):
            j += 1
        if j >= n_lines:
            break
        extra_names = _nod_inf_extra_columns(lines[j])
        # Parse data rows after the header + units row(s) until 'end'.
        k = j + 1
        while k < n_lines:
            stripped = lines[k].strip()
            if not stripped:
                k += 1
                continue
            if stripped.lower() == "end":
                k += 1
                break
            # Skip the units line (starts with "[")
            if stripped.startswith("["):
                k += 1
                continue
            toks = stripped.split()
            if len(toks) < 11:
                k += 1
                continue
            try:
                row = {
                    "time": time_val,
                    "node": int(toks[0]),
                    "depth": float(toks[1]),
                    "head": float(toks[2]),
                    "moisture": float(toks[3]),
                    "K": float(toks[4]),
                    "C": float(toks[5]),
                    "flux": float(toks[6]),
                    "sink": float(toks[7]),
                    "kappa": float(toks[8]),
                    "vKsTop": float(toks[9]),
                    "temp": float(toks[10]),
                }
                for offset, name in enumerate(extra_names, start=11):
                    if offset < len(toks):
                        row[name] = float(toks[offset])
                rows.append(row)
            except (ValueError, IndexError):
                pass
            k += 1
        i = k

    if not rows:
        return _empty_df()
    cols = ["time", "node", "depth", "head", "moisture", "K", "C",
            "flux", "sink", "kappa", "vKsTop", "temp"]
    extra_cols = sorted(
        {col for row in rows for col in row if col not in cols},
        key=_extra_column_sort_key,
    )
    return pd.DataFrame(rows, columns=[*cols, *extra_cols])


def _nod_inf_extra_columns(header_line: str) -> List[str]:
    """Return stable names for optional columns after Temp in Nod_Inf.out."""
    header = header_line.lower()
    if "conc" not in header and "sorb" not in header:
        return []
    # HYDRUS prints one concentration and one sorbed concentration value per
    # solute. The header gives only compact ranges, so assign stable indexes
    # as data tokens appear.
    if "sorb" in header:
        return ["conc_1", "sorb_1"]
    return ["conc_1"]


def _extra_column_sort_key(name: str) -> tuple:
    if name.startswith("conc_"):
        return (0, int(name.split("_", 1)[1]))
    if name.startswith("sorb_"):
        return (1, int(name.split("_", 1)[1]))
    return (2, name)


# --- Solute*.out ----------------------------------------------------------


_SOLUTE_BASE_COLUMNS = [
    "Time",
    "cvTop",
    "cvBot",
    "Sum_cvTop",
    "Sum_cvBot",
    "cvCh0",
    "cvCh1",
    "cTop",
    "cRoot",
    "cBot",
    "cvRoot",
    "Sum_cvRoot",
    "Sum_cvNEql",
    "TLevel",
    "cGWL",
    "cRunOff",
    "Sum_cRunOff",
]


def read_solute(path: Optional[Path]) -> pd.DataFrame:
    """Parse HYDRUS SoluteN.out flux/balance tables.

    HYDRUS writes one ``SoluteN.out`` table per transported solute. The core
    table shape is stable across the official examples; optional observation
    node solute-flux columns are appended as ``obs_cv_N`` and
    ``obs_sum_cv_N`` pairs when present.
    """
    if _is_empty(path):
        return _empty_df()
    text = path.read_text(encoding="utf-8", errors="replace")
    rows: List[Dict] = []
    for line in text.splitlines():
        toks = line.split()
        if not toks or not _is_numeric_token(toks[0]):
            continue
        values: List[float] = []
        try:
            values = [float(tok) for tok in toks]
        except ValueError:
            continue
        names = _solute_columns_for_count(len(values))
        rows.append(dict(zip(names, values)))
    return _rows_to_df(rows)


def _solute_columns_for_count(count: int) -> List[str]:
    names = list(_SOLUTE_BASE_COLUMNS[:count])
    extra_count = max(0, count - len(names))
    for i in range(extra_count):
        obs_index = i // 2 + 1
        if i % 2 == 0:
            names.append(f"obs_cv_{obs_index}")
        else:
            names.append(f"obs_sum_cv_{obs_index}")
    return names


# --- Top-level read_outputs / summarise_outputs --------------------------


_PARSERS: Dict[str, Callable[[Optional[Path]], pd.DataFrame]] = {
    "Obs_Node.out": read_obs_node,
    "T_Level.out": read_t_level,
    "Balance.out": read_balance,
    "Nod_Inf.out": read_nod_inf,
    "Run_Inf.out": read_run_inf,
}


def read_outputs(
    project_dir: Union[str, Path],
    names=DEFAULT_OUTPUT_NAMES,
) -> Dict[str, pd.DataFrame]:
    """Discover and parse each requested output. Always returns one
    DataFrame per name; missing or empty files give an empty DataFrame."""
    found = discover_outputs(project_dir, names)
    out: Dict[str, pd.DataFrame] = {}
    for canonical, path in found.items():
        parser = _PARSERS.get(canonical)
        if parser is None and _SOLUTE_NAME_RE.match(canonical):
            parser = read_solute
        out[canonical] = parser(path) if parser else _empty_df()
    return out


def summarise_outputs(
    project_dir: Union[str, Path],
    names=DEFAULT_OUTPUT_NAMES,
    *,
    max_columns_shown: int = 6,
) -> List[Dict]:
    """Return a list of summary records for each requested file."""
    found = discover_outputs(project_dir, names)
    parsed = read_outputs(project_dir, names)
    summary: List[Dict] = []
    for canonical in found:
        path = found[canonical]
        df = parsed[canonical]
        if path is None:
            entry = {"name": canonical, "found": False, "path": None,
                     "size_bytes": None, "rows": 0, "columns": 0,
                     "first_columns": []}
        else:
            entry = {"name": canonical, "found": True, "path": str(path),
                     "size_bytes": path.stat().st_size,
                     "rows": len(df), "columns": df.shape[1],
                     "first_columns": list(df.columns[:max_columns_shown])}
        summary.append(entry)
    return summary
