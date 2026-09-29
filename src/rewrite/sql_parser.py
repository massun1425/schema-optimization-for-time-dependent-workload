"""SQL parsing utilities"""

import re


class SQLParser:
    """Helper class for parsing SQL queries"""

    def __init__(self):
        """Initialize"""
        pass

    def extract_from_clause(self, sql: str) -> str:
        """Extract the FROM clause

        Args:
            sql: SQL string

        Returns:
            The FROM clause string
        """
        pattern = r"FROM\s+(.+?)(?:WHERE|GROUP BY|ORDER BY|LIMIT|$)"
        match = re.search(pattern, sql, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""

    def extract_where_clause(self, sql: str) -> str:
        """Extract the WHERE clause

        Args:
            sql: SQL string

        Returns:
            The WHERE clause string
        """
        pattern = r"WHERE\s+(.+?)(?:GROUP BY|ORDER BY|LIMIT|$)"
        match = re.search(pattern, sql, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""

    def extract_tables(self, from_clause: str) -> list[tuple[str, str]]:
        """Extract tables and aliases from the FROM clause

        Args:
            from_clause: FROM clause string

        Returns:
            List of (table name, alias)
        """
        tables = []
        # Split on commas
        parts = from_clause.split(",")

        for part in parts:
            part = part.strip()
            # If the part contains a JOIN clause
            if "JOIN" in part.upper():
                # Handle multiple JOINs
                join_parts = re.split(
                    r"\s+(?:INNER|LEFT|RIGHT|FULL)?\s*JOIN\s+", part, flags=re.IGNORECASE
                )
                for jp in join_parts:
                    table_alias = self._extract_table_alias(jp)
                    if table_alias:
                        tables.append(table_alias)
            else:
                table_alias = self._extract_table_alias(part)
                if table_alias:
                    tables.append(table_alias)

        return tables

    def _extract_table_alias(self, part: str) -> tuple[str, str] | None:
        """Extract the table name and alias

        Args:
            part: SQL fragment

        Returns:
            (table name, alias) or None
        """
        # Remove the ON clause
        part = re.sub(r"\s+ON\s+.+$", "", part, flags=re.IGNORECASE)
        part = part.strip()

        # Form "table AS alias" or "table alias"
        match = re.match(r"(\w+)(?:\s+(?:AS\s+)?(\w+))?", part, re.IGNORECASE)
        if match:
            table = match.group(1)
            alias = match.group(2) if match.group(2) else table
            return (table, alias)
        return None

    def parse_condition(self, condition: str) -> dict[str, list[str]]:
        """Parse a condition expression and group it by column

        Args:
            condition: Condition expression of the WHERE clause

        Returns:
            {alias.column: [condition1, condition2, ...]}
        """
        conditions = {}

        # Split on AND/OR
        parts = re.split(r"\s+(?:AND|OR)\s+", condition, flags=re.IGNORECASE)

        for part in parts:
            part = part.strip()
            # Extract alias.column
            match = re.match(r"(\w+)\.(\w+)\s*([<>=!]+|LIKE|IN)\s*(.+)", part, re.IGNORECASE)
            if match:
                alias = match.group(1)
                column = match.group(2)
                operator = match.group(3)
                value = match.group(4)

                key = f"{alias}.{column}"
                if key not in conditions:
                    conditions[key] = []
                conditions[key].append(f"{column} {operator} {value}")

        return conditions

    def reconstruct_query(
        self,
        select_clause: str,
        from_clause: str,
        where_clause: str = "",
        group_by: str = "",
        order_by: str = "",
        limit: str = "",
    ) -> str:
        """Reconstruct a query

        Args:
            select_clause: SELECT clause
            from_clause: FROM clause
            where_clause: WHERE clause
            group_by: GROUP BY clause
            order_by: ORDER BY clause
            limit: LIMIT clause

        Returns:
            The reconstructed SQL
        """
        sql = f"SELECT {select_clause}\nFROM {from_clause}"

        if where_clause:
            sql += f"\nWHERE {where_clause}"
        if group_by:
            sql += f"\nGROUP BY {group_by}"
        if order_by:
            sql += f"\nORDER BY {order_by}"
        if limit:
            sql += f"\nLIMIT {limit}"

        return sql
