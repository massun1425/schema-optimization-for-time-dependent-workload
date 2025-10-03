"""Database schema management for PostgreSQL.

This module provides functionality for querying and managing database schema
information such as tables, columns, indexes, and constraints.
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from .connection import DatabaseConnection

logger = logging.getLogger(__name__)


@dataclass
class ColumnInfo:
    """Information about a table column.
    
    Attributes:
        name: Column name
        data_type: PostgreSQL data type
        is_nullable: Whether the column accepts NULL values
        column_default: Default value expression
        character_maximum_length: Max length for character types
        numeric_precision: Precision for numeric types
        numeric_scale: Scale for numeric types
    """
    name: str
    data_type: str
    is_nullable: bool
    column_default: Optional[str] = None
    character_maximum_length: Optional[int] = None
    numeric_precision: Optional[int] = None
    numeric_scale: Optional[int] = None


@dataclass
class TableInfo:
    """Information about a database table.
    
    Attributes:
        name: Table name
        schema: Schema name
        row_count: Estimated number of rows
        size_bytes: Total table size in bytes
        columns: List of column information
        primary_keys: List of primary key columns
        indexes: List of index names
    """
    name: str
    schema: str
    row_count: Optional[int] = None
    size_bytes: Optional[int] = None
    columns: List[ColumnInfo] = None
    primary_keys: List[str] = None
    indexes: List[str] = None


@dataclass
class IndexInfo:
    """Information about an index.
    
    Attributes:
        name: Index name
        table_name: Table the index belongs to
        columns: List of indexed columns
        is_unique: Whether the index is unique
        is_primary: Whether this is the primary key index
        index_type: Type of index (btree, hash, etc.)
    """
    name: str
    table_name: str
    columns: List[str]
    is_unique: bool
    is_primary: bool
    index_type: str


class SchemaManager:
    """Manages database schema information.
    
    This class provides methods for querying table structures, columns,
    indexes, and other schema metadata.
    
    Attributes:
        db: Database connection instance
        schema: Default schema name
    
    Examples:
        >>> schema_mgr = SchemaManager(db_connection)
        >>> tables = schema_mgr.list_tables()
        >>> info = schema_mgr.get_table_info("users")
        >>> columns = schema_mgr.get_column_info("users")
    """
    
    def __init__(self, db: DatabaseConnection, schema: str = "public"):
        """Initialize schema manager.
        
        Args:
            db: Database connection
            schema: Default schema name (default: 'public')
        """
        self.db = db
        self.schema = schema
        logger.debug(f"SchemaManager initialized for schema '{schema}'")
    
    def table_exists(self, table_name: str, schema: Optional[str] = None) -> bool:
        """Check if a table exists.
        
        Args:
            table_name: Name of the table
            schema: Schema name (defaults to instance schema)
            
        Returns:
            True if table exists, False otherwise
            
        Examples:
            >>> if schema_mgr.table_exists("users"):
            ...     print("Table exists")
        """
        schema = schema or self.schema
        
        sql = """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = %s AND table_name = %s
            )
        """
        
        result = self.db.fetch_value(sql, (schema, table_name), default=False)
        return bool(result)
    
    def list_tables(self, schema: Optional[str] = None, pattern: Optional[str] = None) -> List[str]:
        """List all tables in a schema.
        
        Args:
            schema: Schema name (defaults to instance schema)
            pattern: Optional SQL LIKE pattern to filter tables
            
        Returns:
            List of table names
            
        Examples:
            >>> tables = schema_mgr.list_tables()
            >>> user_tables = schema_mgr.list_tables(pattern="user%")
        """
        schema = schema or self.schema
        
        sql = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
            AND table_type = 'BASE TABLE'
        """
        params = [schema]
        
        if pattern:
            sql += " AND table_name LIKE %s"
            params.append(pattern)
        
        sql += " ORDER BY table_name"
        
        results = self.db.fetch_all(sql, tuple(params))
        table_names = [row[0] for row in results]
        
        logger.debug(f"Found {len(table_names)} tables in schema '{schema}'")
        return table_names
    
    def get_table_info(
        self,
        table_name: str,
        schema: Optional[str] = None,
        include_columns: bool = True
    ) -> Optional[TableInfo]:
        """Get detailed information about a table.
        
        Args:
            table_name: Name of the table
            schema: Schema name (defaults to instance schema)
            include_columns: Whether to include column information
            
        Returns:
            TableInfo object, or None if table doesn't exist
            
        Examples:
            >>> info = schema_mgr.get_table_info("users")
            >>> print(f"Table has {len(info.columns)} columns")
            >>> print(f"Table size: {info.size_bytes} bytes")
        """
        schema = schema or self.schema
        
        if not self.table_exists(table_name, schema):
            return None
        
        # Get row count estimate
        row_count = self.get_row_count(table_name, schema)
        
        # Get table size
        size_bytes = self.get_table_size(table_name, schema)
        
        # Get columns if requested
        columns = None
        if include_columns:
            columns = self.get_column_info(table_name, schema)
        
        # Get primary keys
        primary_keys = self.get_primary_keys(table_name, schema)
        
        # Get indexes
        indexes = self.list_indexes(table_name, schema)
        
        return TableInfo(
            name=table_name,
            schema=schema,
            row_count=row_count,
            size_bytes=size_bytes,
            columns=columns,
            primary_keys=primary_keys,
            indexes=indexes
        )
    
    def get_column_info(
        self,
        table_name: str,
        schema: Optional[str] = None
    ) -> List[ColumnInfo]:
        """Get information about all columns in a table.
        
        Args:
            table_name: Name of the table
            schema: Schema name (defaults to instance schema)
            
        Returns:
            List of ColumnInfo objects
            
        Examples:
            >>> columns = schema_mgr.get_column_info("users")
            >>> for col in columns:
            ...     print(f"{col.name}: {col.data_type}")
        """
        schema = schema or self.schema
        
        sql = """
            SELECT
                column_name,
                data_type,
                is_nullable,
                column_default,
                character_maximum_length,
                numeric_precision,
                numeric_scale
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
        """
        
        results = self.db.fetch_all(sql, (schema, table_name))
        
        columns = [
            ColumnInfo(
                name=row[0],
                data_type=row[1],
                is_nullable=(row[2] == 'YES'),
                column_default=row[3],
                character_maximum_length=row[4],
                numeric_precision=row[5],
                numeric_scale=row[6]
            )
            for row in results
        ]
        
        logger.debug(f"Found {len(columns)} columns in {schema}.{table_name}")
        return columns
    
    def get_column_names(
        self,
        table_name: str,
        schema: Optional[str] = None
    ) -> List[str]:
        """Get list of column names for a table.
        
        Args:
            table_name: Name of the table
            schema: Schema name (defaults to instance schema)
            
        Returns:
            List of column names
            
        Examples:
            >>> columns = schema_mgr.get_column_names("users")
            >>> print(f"Columns: {', '.join(columns)}")
        """
        columns = self.get_column_info(table_name, schema)
        return [col.name for col in columns]
    
    def column_exists(
        self,
        table_name: str,
        column_name: str,
        schema: Optional[str] = None
    ) -> bool:
        """Check if a column exists in a table.
        
        Args:
            table_name: Name of the table
            column_name: Name of the column
            schema: Schema name (defaults to instance schema)
            
        Returns:
            True if column exists, False otherwise
            
        Examples:
            >>> if schema_mgr.column_exists("users", "email"):
            ...     print("Email column exists")
        """
        schema = schema or self.schema
        
        sql = """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = %s
                AND table_name = %s
                AND column_name = %s
            )
        """
        
        result = self.db.fetch_value(sql, (schema, table_name, column_name), default=False)
        return bool(result)
    
    def get_primary_keys(
        self,
        table_name: str,
        schema: Optional[str] = None
    ) -> List[str]:
        """Get primary key columns for a table.
        
        Args:
            table_name: Name of the table
            schema: Schema name (defaults to instance schema)
            
        Returns:
            List of primary key column names
            
        Examples:
            >>> pk_columns = schema_mgr.get_primary_keys("users")
            >>> print(f"Primary key: {', '.join(pk_columns)}")
        """
        schema = schema or self.schema
        
        sql = """
            SELECT a.attname
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = %s::regclass
            AND i.indisprimary
            ORDER BY a.attnum
        """
        
        full_name = f"{schema}.{table_name}"
        results = self.db.fetch_all(sql, (full_name,))
        
        pk_columns = [row[0] for row in results]
        logger.debug(f"Primary keys for {schema}.{table_name}: {pk_columns}")
        return pk_columns
    
    def list_indexes(
        self,
        table_name: str,
        schema: Optional[str] = None
    ) -> List[str]:
        """List all indexes for a table.
        
        Args:
            table_name: Name of the table
            schema: Schema name (defaults to instance schema)
            
        Returns:
            List of index names
            
        Examples:
            >>> indexes = schema_mgr.list_indexes("users")
            >>> print(f"Indexes: {', '.join(indexes)}")
        """
        schema = schema or self.schema
        
        sql = """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = %s AND tablename = %s
            ORDER BY indexname
        """
        
        results = self.db.fetch_all(sql, (schema, table_name))
        index_names = [row[0] for row in results]
        
        logger.debug(f"Found {len(index_names)} indexes for {schema}.{table_name}")
        return index_names
    
    def get_index_info(
        self,
        index_name: str,
        schema: Optional[str] = None
    ) -> Optional[IndexInfo]:
        """Get detailed information about an index.
        
        Args:
            index_name: Name of the index
            schema: Schema name (defaults to instance schema)
            
        Returns:
            IndexInfo object, or None if index doesn't exist
            
        Examples:
            >>> info = schema_mgr.get_index_info("users_pkey")
            >>> print(f"Index on columns: {', '.join(info.columns)}")
        """
        schema = schema or self.schema
        
        sql = """
            SELECT
                i.tablename,
                i.indexdef,
                ix.indisunique,
                ix.indisprimary
            FROM pg_indexes i
            JOIN pg_class c ON c.relname = i.indexname
            JOIN pg_index ix ON ix.indexrelid = c.oid
            WHERE i.schemaname = %s AND i.indexname = %s
        """
        
        result = self.db.fetch_one(sql, (schema, index_name))
        
        if not result:
            return None
        
        # Extract column names from index definition
        # This is a simple parser; for complex indexes, you might need more sophisticated parsing
        indexdef = result[1]
        columns = []
        
        # Try to extract columns from CREATE INDEX statement
        import re
        match = re.search(r'\((.*?)\)', indexdef)
        if match:
            columns_str = match.group(1)
            columns = [col.strip() for col in columns_str.split(',')]
        
        # Determine index type from definition
        index_type = 'btree'  # default
        if 'USING hash' in indexdef:
            index_type = 'hash'
        elif 'USING gin' in indexdef:
            index_type = 'gin'
        elif 'USING gist' in indexdef:
            index_type = 'gist'
        
        return IndexInfo(
            name=index_name,
            table_name=result[0],
            columns=columns,
            is_unique=result[2],
            is_primary=result[3],
            index_type=index_type
        )
    
    def get_table_size(
        self,
        table_name: str,
        schema: Optional[str] = None
    ) -> int:
        """Get the total size of a table in bytes.
        
        This includes the table data, indexes, and TOAST data.
        
        Args:
            table_name: Name of the table
            schema: Schema name (defaults to instance schema)
            
        Returns:
            Size in bytes
            
        Examples:
            >>> size = schema_mgr.get_table_size("users")
            >>> print(f"Table size: {size / 1024 / 1024:.2f} MB")
        """
        schema = schema or self.schema
        full_name = f"{schema}.{table_name}"
        
        sql = "SELECT pg_total_relation_size(%s)"
        size = self.db.fetch_value(sql, (full_name,), default=0)
        
        return int(size) if size else 0
    
    def get_row_count(
        self,
        table_name: str,
        schema: Optional[str] = None,
        exact: bool = False
    ) -> Optional[int]:
        """Get the number of rows in a table.
        
        Args:
            table_name: Name of the table
            schema: Schema name (defaults to instance schema)
            exact: If True, do exact COUNT(*); if False, use estimate
            
        Returns:
            Number of rows, or None if unavailable
            
        Examples:
            >>> # Fast estimate
            >>> count = schema_mgr.get_row_count("users")
            
            >>> # Exact count (slower)
            >>> count = schema_mgr.get_row_count("users", exact=True)
        """
        schema = schema or self.schema
        
        if exact:
            # Exact count (can be slow for large tables)
            sql = f"SELECT COUNT(*) FROM {schema}.{table_name}"
            return self.db.fetch_value(sql)
        else:
            # Estimated count from statistics (fast)
            sql = """
                SELECT reltuples::bigint
                FROM pg_class
                WHERE oid = %s::regclass
            """
            full_name = f"{schema}.{table_name}"
            return self.db.fetch_value(sql, (full_name,))
    
    def get_schema_size(self, schema: Optional[str] = None) -> int:
        """Get the total size of all tables in a schema.
        
        Args:
            schema: Schema name (defaults to instance schema)
            
        Returns:
            Total size in bytes
            
        Examples:
            >>> size = schema_mgr.get_schema_size()
            >>> print(f"Schema size: {size / 1024 / 1024 / 1024:.2f} GB")
        """
        schema = schema or self.schema
        
        sql = """
            SELECT COALESCE(SUM(pg_total_relation_size(quote_ident(schemaname) || '.' || quote_ident(tablename))), 0)
            FROM pg_tables
            WHERE schemaname = %s
        """
        
        size = self.db.fetch_value(sql, (schema,), default=0)
        return int(size) if size else 0
    
    def get_database_size(self) -> int:
        """Get the total size of the current database.
        
        Returns:
            Size in bytes
            
        Examples:
            >>> size = schema_mgr.get_database_size()
            >>> print(f"Database size: {size / 1024 / 1024 / 1024:.2f} GB")
        """
        sql = "SELECT pg_database_size(current_database())"
        size = self.db.fetch_value(sql, default=0)
        
        return int(size) if size else 0
