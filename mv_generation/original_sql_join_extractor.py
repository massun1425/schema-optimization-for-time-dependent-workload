"""Utilities for extracting join conditions and table aliases from the original SQL files.

PostgreSQL constant pushdown can make join conditions disappear from the
execution plan, so the exact join conditions are extracted from the original SQL query.

Example:
    sql = open("01_queries/cluster_53/5a9.sql").read()
    aliases = extract_aliases_from_sql(sql)
    # => {'t': 'title', 'mi1': 'movie_info', 'it3': 'info_type', ...}
    conditions = extract_equijoin_conditions(sql)
    # => [('mi1', 'info_type_id', 'it3', 'id'), ...]
"""

import re
from typing import Optional


def _normalize_identifier(token: str) -> str:
    """Normalize an identifier (strip double quotes + lowercase)."""
    token = token.strip()
    if token.startswith('"') and token.endswith('"') and len(token) >= 2:
        token = token[1:-1]
    return token.lower()


def _extract_main_clause(sql: str, clause: str) -> str:
    """Extract the body of the given clause (up to the next main clause)."""
    match = re.search(
        rf'\b{clause}\s+(.*?)(?:\bWHERE\b|\bGROUP\s+BY\b|\bORDER\s+BY\b|\bLIMIT\b|\bHAVING\b|;|$)',
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return ""
    return match.group(1).strip()


def _extract_equijoins_from_expression(expr: str) -> list[tuple[str, str, str, str]]:
    """Extract alias.column = alias.column from an expression string."""
    if not expr:
        return []

    ident = r'(?:"[^"]+"|[a-zA-Z_][a-zA-Z0-9_]*)'
    pattern = re.compile(
        rf'({ident})\s*\.\s*({ident})\s*=\s*({ident})\s*\.\s*({ident})',
        flags=re.IGNORECASE,
    )

    result = []
    for match in pattern.finditer(expr):
        left_alias = _normalize_identifier(match.group(1))
        left_column = _normalize_identifier(match.group(2))
        right_alias = _normalize_identifier(match.group(3))
        right_column = _normalize_identifier(match.group(4))

        if left_alias == right_alias:
            continue

        result.append((left_alias, left_column, right_alias, right_column))

    return result


def extract_aliases_from_sql(sql: str) -> dict[str, str]:
    """Extract the table alias mapping from the FROM clause.

    Supported forms:
      - table AS alias
      - table alias (without AS)

    Args:
        sql: SQL query string

    Returns:
        dict of {alias: table_name}
    """
    # Extract the FROM clause (up to WHERE/GROUP BY/ORDER BY/LIMIT/HAVING)
    from_clause = _extract_main_clause(sql, 'FROM')
    if not from_clause:
        return {}

    # Extract the tables and aliases referenced in FROM/JOIN
    ident = r'(?:"[^"]+"|[a-zA-Z_][a-zA-Z0-9_]*)'
    table_pattern = re.compile(
        rf'(?:^|,|\bJOIN\b)\s*({ident})\s+(?:AS\s+)?({ident})\b',
        re.IGNORECASE,
    )

    aliases = {}
    for match in table_pattern.finditer(from_clause):
        table_name = _normalize_identifier(match.group(1))
        alias = _normalize_identifier(match.group(2))
        if alias.upper() == 'AS':
            continue
        aliases[alias] = table_name

    # Fallback for no alias (single table)
    if not aliases:
        single = re.match(rf'^\s*({ident})\s*$', from_clause, re.IGNORECASE)
        if single:
            table_name = _normalize_identifier(single.group(1))
            aliases[table_name] = table_name

    return aliases


def extract_equijoin_conditions(sql: str) -> list[tuple[str, str, str, str]]:
    """Extract equi-join conditions of the form alias.column = alias.column from the WHERE clause.

    Constant conditions (alias.column = 'value' or alias.column = 123) are excluded;
    only joins between tables are returned.

    Args:
        sql: SQL query string

    Returns:
        List of [(left_alias, left_column, right_alias, right_column), ...]
    """
    conditions = []
    dedupe_keys = set()

    # 1) Equi-joins from the WHERE clause
    where_clause = _extract_main_clause(sql, 'WHERE')
    for cond in _extract_equijoins_from_expression(where_clause):
        key = tuple(sorted([(cond[0], cond[1]), (cond[2], cond[3])]))
        if key in dedupe_keys:
            continue
        dedupe_keys.add(key)
        conditions.append(cond)

    # 2) Equi-joins from JOIN ... ON
    on_pattern = re.compile(
        r'\bON\b\s+(.*?)(?=\b(?:INNER|LEFT|RIGHT|FULL|CROSS)\s+JOIN\b|\bJOIN\b|\bWHERE\b|\bGROUP\s+BY\b|\bORDER\s+BY\b|\bLIMIT\b|\bHAVING\b|;|$)',
        re.IGNORECASE | re.DOTALL,
    )
    for on_match in on_pattern.finditer(sql):
        on_expr = on_match.group(1).strip()
        for cond in _extract_equijoins_from_expression(on_expr):
            key = tuple(sorted([(cond[0], cond[1]), (cond[2], cond[3])]))
            if key in dedupe_keys:
                continue
            dedupe_keys.add(key)
            conditions.append(cond)

    return conditions


def get_join_conditions_for_aliases(
    sql: str,
    target_aliases: set[str]
) -> list[tuple[str, str, str, str]]:
    """Return only the join conditions related to the given alias set.

    Filters to the join conditions that involve only tables in the subtree.

    Args:
        sql: SQL query string
        target_aliases: Set of target aliases (lowercase)

    Returns:
        List of [(left_alias, left_column, right_alias, right_column), ...]
        Note: only those whose aliases on both sides are in target_aliases
    """
    all_conditions = extract_equijoin_conditions(sql)
    return [
        (la, lc, ra, rc)
        for la, lc, ra, rc in all_conditions
        if la in target_aliases and ra in target_aliases
    ]


def find_sql_file_for_query(
    json_file_path: str,
    sql_dir: Optional[str] = None
) -> Optional[str]:
    """Derive the corresponding SQL file path from a JSON file path.

    Args:
        json_file_path: Absolute path of the JSON file
            e.g., .../02_json/cluster_53/5a9.json
        sql_dir: Directory containing the SQL files
            e.g., .../01_queries/cluster_53
            If None, inferred from the JSON path

    Returns:
        Path of the SQL file, or None if not found
    """
    from pathlib import Path

    json_path = Path(json_file_path)
    stem = json_path.stem  # e.g., "5a9"

    if sql_dir:
        sql_path = Path(sql_dir) / f"{stem}.sql"
        return str(sql_path) if sql_path.exists() else None

    # Infer from the JSON path: replace 02_json with 01_queries
    json_dir = str(json_path.parent)
    possible_sql_dir = json_dir.replace("02_json", "01_queries")
    sql_path = Path(possible_sql_dir) / f"{stem}.sql"
    return str(sql_path) if sql_path.exists() else None
