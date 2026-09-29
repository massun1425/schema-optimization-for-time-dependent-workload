"""Merge two query sets by summing their frequencies time step by time step.

- Files with the same SQL are merged into one (the file name of dir1 has priority)
- The number of time steps is unchanged; the frequencies of the same time step are added
- Query only in dir1: freq_dir1
- Query only in dir2: freq_dir2
- Query in both: freq_dir1 + freq_dir2 (element-wise)

This is the step that combined clusters 53 and 55 into cluster_55_53_combined
(see build_cluster_53_55_combined.sh).

Usage:
    python3 scripts/redbench_synthesizer/merge_query_folders_sum.py \
        --dir1 01_queries/cluster_55_join_12 \
        --dir2 01_queries/cluster_55_join_05_25 \
        --out  01_queries/cluster_55_join_12_25 \
        --freq-name frequency_time_dependent.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().lower()


def load_freq_json(path: Path) -> dict[str, list[int]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("queries", {})


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge two query sets (sum the frequencies)")
    parser.add_argument("--dir1", required=True, help="first query set")
    parser.add_argument("--dir2", required=True, help="second query set")
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument(
        "--freq-name",
        default="frequency_time_dependent.json",
        help="name of the frequency JSON (same in both directories)",
    )
    parser.add_argument("--freq-name1", help="name of the frequency JSON of dir1 (default: --freq-name)")
    parser.add_argument("--freq-name2", help="name of the frequency JSON of dir2 (default: --freq-name)")
    parser.add_argument("--description", help="description field of the output frequency JSON "
                        "(default: 'Merged by SUMMING frequencies from <dir1> and <dir2> (<T> steps)')")
    args = parser.parse_args()

    dir1 = Path(args.dir1)
    dir2 = Path(args.dir2)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Load the frequency JSONs ---
    freq_name1 = args.freq_name1 if args.freq_name1 else args.freq_name
    freq_name2 = args.freq_name2 if args.freq_name2 else args.freq_name
    freq1_path = dir1 / freq_name1
    freq2_path = dir2 / freq_name2
    freq1: dict[str, list[int]] = load_freq_json(freq1_path) if freq1_path.exists() else {}
    freq2: dict[str, list[int]] = load_freq_json(freq2_path) if freq2_path.exists() else {}


    # Number of time steps
    n1 = len(next(iter(freq1.values()), []))
    n2 = len(next(iter(freq2.values()), []))
    print(f"[INFO] dir1 timesteps: {n1}, dir2 timesteps: {n2}")
    
    max_steps = max(n1, n2)

    # --- Read the SQL files and deduplicate them by content ---
    # normalized_sql -> (canonical_fname, sql_content)
    sql_to_canonical: dict[str, tuple[str, str]] = {}

    # dir1 file name -> normalized SQL
    dir1_fname_to_norm: dict[str, str] = {}

    print(f"[INFO] Reading dir1: {dir1}")
    for sql_file in sorted(dir1.glob("*.sql")):
        raw = sql_file.read_text(encoding="utf-8")
        norm = normalize_sql(raw)
        fname = sql_file.name
        dir1_fname_to_norm[fname] = norm
        if norm not in sql_to_canonical:
            sql_to_canonical[norm] = (fname, raw)

    # dir2 file name -> canonical file name (in sql_to_canonical)
    dir2_fname_to_canonical: dict[str, str] = {}

    print(f"[INFO] Reading dir2: {dir2}")
    for sql_file in sorted(dir2.glob("*.sql")):
        raw = sql_file.read_text(encoding="utf-8")
        norm = normalize_sql(raw)
        fname = sql_file.name
        if norm not in sql_to_canonical:
            # Query only in dir2 -> keep the file name of dir2
            sql_to_canonical[norm] = (fname, raw)
        canonical_fname = sql_to_canonical[norm][0]
        dir2_fname_to_canonical[fname] = canonical_fname

    print(f"[INFO] Unique queries total: {len(sql_to_canonical)}")

    # --- Combine the frequencies (element-wise sum) ---
    # canonical_fname -> [freq_dir1 + freq_dir2]
    merged_freq: dict[str, list[int]] = {}

    # Frequencies of dir1
    for fname, freqs in freq1.items():
        norm = dir1_fname_to_norm.get(fname)
        if norm is None:
            continue
        canonical = sql_to_canonical[norm][0]
        if canonical not in merged_freq:
            merged_freq[canonical] = [0] * max_steps
        for i, v in enumerate(freqs):
            if i < max_steps:
                merged_freq[canonical][i] += v

    # Frequencies of dir2
    for fname, freqs in freq2.items():
        sql_file = dir2 / fname
        if not sql_file.exists():
            continue
        raw = sql_file.read_text(encoding="utf-8")
        norm = normalize_sql(raw)
        canonical = sql_to_canonical[norm][0]
        if canonical not in merged_freq:
            merged_freq[canonical] = [0] * max_steps
        for i, v in enumerate(freqs):
            if i < max_steps:
                merged_freq[canonical][i] += v

    # Add the queries that are missing from the frequency JSON (all zeros)
    for norm, (canonical, _) in sql_to_canonical.items():
        if canonical not in merged_freq:
            merged_freq[canonical] = [0] * max_steps

    # --- Write the SQL files ---
    for norm, (canonical, raw) in sql_to_canonical.items():
        (out_dir / canonical).write_text(raw, encoding="utf-8")

    print(f"[INFO] SQL files written: {len(sql_to_canonical)}")

    # --- Write the frequency JSON ---
    freq_payload = {
        "description": args.description or (
            f"Merged by SUMMING frequencies from {dir1.name} and {dir2.name} ({max_steps} steps)"
        ),
        "note": "queries format: filename -> frequency list per timestep",
        "queries": dict(sorted(merged_freq.items())),
    }
    out_freq_path = out_dir / args.freq_name
    out_freq_path.write_text(json.dumps(freq_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[INFO] Frequency JSON written: {out_freq_path}")
    print(f"[INFO] Total timesteps: {max_steps}")

    print(f"[OK] Done. Output: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
