#!/usr/bin/env python3
"""Normalize the version suffixes (_0, _1, ...) of the table names in a query set.

Purpose:
- The SQL of the Redbench generation strategy refers to versioned tables such as
  `movie_info_1`. This maps them back to the tables of the IMDB database (`movie_info`)
  so that the queries can be executed. (Not needed for the matching strategy.)

Examples:
- "movie_info_1"."note" -> "movie_info"."note"
- movie_info_1 -> movie_info

Notes:
- String literals are not changed
- Only the known IMDB base table names are changed
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

IMDB_BASE_TABLES = [
    "title",
    "cast_info",
    "movie_info",
    "movie_companies",
    "movie_keyword",
    "name",
    "person_info",
    "movie_info_idx",
    "aka_name",
    "aka_title",
    "char_name",
    "complete_cast",
    "movie_link",
    "keyword",
    "company_name",
    "company_type",
    "info_type",
    "kind_type",
    "role_type",
    "link_type",
    "comp_cast_type",
]


def protect_single_quoted_literals(sql: str) -> tuple[str, list[str]]:
    literals: list[str] = []

    def repl(match: re.Match[str]) -> str:
        literals.append(match.group(0))
        return f"__SQL_LITERAL_{len(literals)-1}__"

    protected = re.sub(r"'(?:[^']|'')*'", repl, sql, flags=re.DOTALL)
    return protected, literals


def restore_single_quoted_literals(sql: str, literals: list[str]) -> str:
    restored = sql
    for i, lit in enumerate(literals):
        restored = restored.replace(f"__SQL_LITERAL_{i}__", lit)
    return restored


def normalize_table_versions(sql: str) -> tuple[str, int]:
    protected, literals = protect_single_quoted_literals(sql)

    total_changes = 0
    normalized = protected

    for table in IMDB_BASE_TABLES:
        # quoted identifier: "movie_info_1" -> "movie_info"
        quoted_pattern = re.compile(rf'"{re.escape(table)}_\d+"')
        normalized, c1 = quoted_pattern.subn(f'"{table}"', normalized)

        # unquoted identifier: movie_info_1 -> movie_info
        unquoted_pattern = re.compile(rf"\b{re.escape(table)}_\d+\b")
        normalized, c2 = unquoted_pattern.subn(table, normalized)

        total_changes += c1 + c2

    normalized = restore_single_quoted_literals(normalized, literals)
    return normalized, total_changes


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize the table name versions of a query set")
    parser.add_argument("--input-dir", required=True, help="input query set directory")
    parser.add_argument("--output-dir", default="", help="output query set directory (--in-place is required if omitted)")
    parser.add_argument("--in-place", action="store_true", help="overwrite the input directory")
    parser.add_argument("--copy-frequency-json", action="store_true", help="also copy frequency_time_dependent*.json")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.exists() or not input_dir.is_dir():
        raise FileNotFoundError(f"input-dir not found: {input_dir}")

    if args.in_place:
        output_dir = input_dir
    else:
        if not args.output_dir:
            raise ValueError("--output-dir is required when --in-place is not set")
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    sql_files = sorted(input_dir.glob("*.sql"))
    if not sql_files:
        raise FileNotFoundError(f"no .sql files found in: {input_dir}")

    changed_files = 0
    total_replacements = 0

    for sql_file in sql_files:
        src_sql = sql_file.read_text(encoding="utf-8")
        normalized_sql, replacements = normalize_table_versions(src_sql)

        out_path = output_dir / sql_file.name
        out_path.write_text(normalized_sql, encoding="utf-8")

        if replacements > 0:
            changed_files += 1
            total_replacements += replacements

    if args.copy_frequency_json and output_dir != input_dir:
        for freq_json in input_dir.glob("frequency_time_dependent*.json"):
            shutil.copy2(freq_json, output_dir / freq_json.name)

    print(f"[OK] input_dir: {input_dir}")
    print(f"[OK] output_dir: {output_dir}")
    print(f"[OK] sql_files: {len(sql_files)}")
    print(f"[OK] changed_files: {changed_files}")
    print(f"[OK] total_replacements: {total_replacements}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
