"""Data models for query optimization.

This module defines the core data structures used throughout the application,
including query nodes, materialized views, and optimization results.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueryNode:
    """Base class for query plan nodes.

    Attributes:
        node_id: Unique identifier for the node
        total_cost: Total cost of executing this node
        size: Size of the result set (rows * width)
        width: Width of the result tuples in bytes
    """

    node_id: str
    total_cost: float
    size: int
    width: int


@dataclass
class LeafNode(QueryNode):
    """Leaf node representing a table scan.

    Attributes:
        operator: Operator type (e.g., 'Seq Scan', 'Index Scan')
        table_name: Name of the table being scanned
        alias: Alias used in the query
        filter_condition: Filter condition applied to the scan
    """

    operator: str
    table_name: str
    alias: str
    filter_condition: str


@dataclass
class NonLeafNode(QueryNode):
    """Non-leaf node representing a join or other operation.

    Attributes:
        child_ids: Tuple of child node IDs
        operator: Operator type (e.g., 'Hash Join', 'Merge Join')
        filter_condition: Filter condition applied after the operation
    """

    child_ids: tuple[str, ...]
    operator: str
    filter_condition: str = ""


@dataclass
class MaterializedView:
    """Represents a materialized view candidate.

    Attributes:
        view_id: Unique identifier for the view
        node_id: ID of the query node this view corresponds to
        create_sql: SQL statement to create the materialized view
        size: Storage size of the view in bytes
        maintenance_cost: Cost of maintaining the view during updates
        usage_positions: List of [query_id, position] where this view is used
    """

    view_id: str
    node_id: str
    create_sql: str
    size: int
    maintenance_cost: float
    usage_positions: list[list[int]] = field(default_factory=list)


@dataclass
class OptimizationResult:
    """Result of an optimization algorithm run.

    Attributes:
        algorithm: Name of the algorithm used
        selected_views: List of selected materialized views
        total_utility: Total utility achieved
        total_storage: Total storage used in bytes
        execution_time: Time taken for optimization in seconds
        metadata: Additional algorithm-specific metadata
    """

    algorithm: str
    selected_views: list[MaterializedView]
    total_utility: float
    total_storage: int
    execution_time: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class QueryPlan:
    """Represents a complete query plan.

    Attributes:
        query_id: Unique identifier for the query
        root_node_id: ID of the root node in the plan tree
        frequency: Frequency of query execution
        original_cost: Original cost without materialized views
        subquery_list: List of subquery nodes in execution order
        depth_list: List of depths for each node
    """

    query_id: int
    root_node_id: str
    frequency: int
    original_cost: float
    subquery_list: list[dict[str, Any]] = field(default_factory=list)
    depth_list: list[int] = field(default_factory=list)
