#!/usr/bin/env python3
"""Multiply all frequencies of a frequency file by an integer factor.

Used to scale the Redbench-based workloads:
    _2h      -> _2h_x2      (factor 2, " (doubled frequencies)")
    _2h_x2   -> _2h_x2_10x  (factor 10, " (frequencies x10)")
    _2h_x2_10x -> _2h_x2_50x (factor 5, " [x5 of _2h_x2_10x]"; written without indentation)

The output keeps the key order and (unless --indent is given) the indentation of the input;
its description is the input description followed by --description-suffix. An existing output file is never
overwritten.

Usage:
    python3 scripts/redbench_synthesizer/scale_frequency.py \\
        --input  01_queries/<set>/frequency_time_dependent_2h.json \\
        --output 01_queries/<set>/frequency_time_dependent_2h_x2.json \\
        --factor 2 --description-suffix " (doubled frequencies)"
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def detect_indent(text: str) -> int:
    """Indentation width of a JSON file written with json.dumps(..., indent=N)."""
    lines = text.splitlines()
    if len(lines) < 2:
        return 2
    return len(lines[1]) - len(lines[1].lstrip(" ")) or 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Multiply the frequencies of a frequency file")
    parser.add_argument("--input", required=True, help="input frequency_time_dependent*.json")
    parser.add_argument("--output", required=True, help="output frequency_time_dependent*.json")
    parser.add_argument("--factor", type=int, required=True, help="integer factor")
    parser.add_argument("--description-suffix", default=None,
                        help="text appended to the description (default: ' (frequencies x<factor>)')")
    parser.add_argument("--indent", default="auto",
                        help="JSON indentation: 'auto' (same as the input), a number, or 'none' (one line)")
    args = parser.parse_args()

    in_path, out_path = Path(args.input), Path(args.output)
    if out_path.exists():
        raise SystemExit(f"output already exists (not overwritten): {out_path}")

    text = in_path.read_text(encoding="utf-8")
    data = json.loads(text)
    data["queries"] = {name: [v * args.factor for v in freqs] for name, freqs in data["queries"].items()}
    suffix = args.description_suffix if args.description_suffix is not None else f" (frequencies x{args.factor})"
    data["description"] = data.get("description", "") + suffix

    if args.indent == "auto":
        indent = detect_indent(text)
    elif args.indent == "none":
        indent = None
    else:
        indent = int(args.indent)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")
    total = sum(sum(freqs) for freqs in data["queries"].values())
    print(f"[OK] {out_path}: {len(data['queries'])} queries, total frequency {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
