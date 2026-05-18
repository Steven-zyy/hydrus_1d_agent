"""Run the prompt-to-config benchmark.

Standalone CLI wrapper. Does NOT call any LLM. Does NOT run HYDRUS.
Always exits 0; per-case ``passed`` is data, not a CLI gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from hydrus_agent.prompt_benchmark import (  # noqa: E402
    evaluate_all,
    render_markdown,
    result_to_dict,
)


DEFAULT_CASES_DIR = _PROJECT_ROOT / "benchmarks" / "prompt_to_config" / "cases"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_prompt_benchmark",
        description=(
            "Evaluate pre-saved candidate HYDRUS-1D configs against per-case "
            "expectations. Never calls an LLM. Never runs HYDRUS. Always "
            "exits 0; per-case results are reported in stdout and optional "
            "JSON output."
        ),
    )
    parser.add_argument(
        "--cases-dir", type=Path, default=DEFAULT_CASES_DIR,
        help=f"Directory containing case subdirectories. Default: {DEFAULT_CASES_DIR}",
    )
    parser.add_argument(
        "--json-out", type=Path, default=None,
        help="Optional path; if set, writes the full structured result as JSON.",
    )
    args = parser.parse_args(argv)

    if not args.cases_dir.is_dir():
        print(f"[ERROR] cases dir not found: {args.cases_dir}", file=sys.stderr)
        return 0  # informational; never block

    result = evaluate_all(args.cases_dir)
    print(render_markdown(result))
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(result_to_dict(result), indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        print(f"\n[info] wrote {args.json_out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
