"""Sparse drop-in containers for large-scale (scalability) experiments.

These containers store only the non-zero entries of u_ij (utility matrix) and
X (containment matrix), while still supporting dense-style ``m[i][j]`` access
that returns 0 for absent entries. This lets existing dense code paths keep
working unchanged (correctness preserved), while the hot O(I*J) / O(I*J^2)
loops can be rewritten to iterate only over the stored non-zeros (speed) and
the huge all-zero blocks are never materialized in memory (scalability).

Used ONLY by the synthetic scaling experiment (opt-in). The normal experiment
flow keeps passing plain ``list[list[...]]`` and never touches this module.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Set, Tuple


class _SparseRow:
    """Row proxy: dense-style ``row[j]`` (0.0 default) over a sparse dict."""

    __slots__ = ("_d", "_width")

    def __init__(self, d: Dict[int, float], width: int) -> None:
        self._d = d
        self._width = width

    def __getitem__(self, j: int) -> float:
        return self._d.get(j, 0.0)

    def __setitem__(self, j: int, value: float) -> None:
        # Keep storage sparse: drop entries that become zero.
        if value:
            self._d[j] = value
        elif j in self._d:
            del self._d[j]

    def __len__(self) -> int:
        # Report the full (dense) width so ``range(len(row))`` covers all j.
        return self._width

    def items(self) -> Iterable[Tuple[int, float]]:
        """Iterate only the stored non-zero (j, value) pairs."""
        return self._d.items()


class SparseMatrix:
    """Sparse 2D matrix with dense-style indexing and non-zero iteration.

    ``m[i][j]`` returns the value or 0.0; ``len(m)`` is the number of rows I;
    ``m.nonzero_items(i)`` yields only the stored (j, value) pairs of row i.
    """

    __slots__ = ("rows", "I", "J")

    def __init__(self, rows: Dict[int, Dict[int, float]], I: int, J: int) -> None:
        self.rows = rows  # {i: {j: value}}
        self.I = I
        self.J = J

    def __getitem__(self, i: int) -> _SparseRow:
        d = self.rows.get(i)
        if d is None:
            d = self.rows[i] = {}
        return _SparseRow(d, self.J)

    def __len__(self) -> int:
        return self.I

    def nonzero_items(self, i: int) -> Iterable[Tuple[int, float]]:
        """Yield only the stored non-zero (j, value) pairs of row i."""
        return self.rows.get(i, {}).items()

    def nnz(self) -> int:
        return sum(len(d) for d in self.rows.values())


class _XRowView:
    """Row proxy for the containment matrix: ``row[u]`` -> 1 if edge else 0."""

    __slots__ = ("_s", "_width")

    def __init__(self, s: Set[int], width: int) -> None:
        self._s = s
        self._width = width

    def __getitem__(self, u: int) -> int:
        return 1 if u in self._s else 0

    def __len__(self) -> int:
        return self._width


class SparseX:
    """Sparse containment matrix stored as adjacency sets.

    ``X[j][u]`` returns 1/0; ``X.children(j)`` returns the set of u with an edge.
    """

    __slots__ = ("adj", "J")

    def __init__(self, adj: Dict[int, Set[int]], J: int) -> None:
        self.adj = adj  # {j: {u, ...}}
        self.J = J

    def __getitem__(self, j: int) -> _XRowView:
        return _XRowView(self.adj.get(j, frozenset()), self.J)

    def __len__(self) -> int:
        return self.J

    def children(self, j: int) -> Set[int]:
        return self.adj.get(j, frozenset())

    def nnz(self) -> int:
        return sum(len(s) for s in self.adj.values())


class SparseQM:
    """Minimal QueryManager stand-in holding only the node-keyed dicts that the
    optimizers actually read (subquery_costs/positions/sizes, non_leaf children).
    All are sparse dicts, so they scale fine.
    """

    def __init__(
        self,
        subquery_costs: Dict[str, float],
        subquery_positions: Dict[str, List[List[int]]],
        subquery_sizes: Dict[str, int],
        non_leaf_nodes_map_r: Dict[str, Tuple[str, ...]],
    ) -> None:
        self.subquery_costs = subquery_costs
        self.subquery_positions = subquery_positions
        self.subquery_sizes = subquery_sizes
        self.non_leaf_nodes_map_r = non_leaf_nodes_map_r


class SparseQP:
    """QueryParser stand-in for the sparse scaling experiment.

    Exposes the same attribute names the optimization phases read
    (node_list, u_ij, X, s_num, qm, q_s_list, b_j), but u_ij/X are sparse.
    Detection downstream is via ``isinstance(qp.u_ij, SparseMatrix)``.
    """

    def __init__(
        self,
        node_list: List[str],
        u_ij: SparseMatrix,
        X: SparseX,
        s_num: int,
        qm: SparseQM,
        q_s_list: List[List[int]],
        b_j: List[float],
        query_files: List[str],
    ) -> None:
        self.node_list = node_list
        self.u_ij = u_ij
        self.X = X
        self.s_num = s_num
        self.qm = qm
        self.q_s_list = q_s_list
        self.b_j = b_j
        self.query_files = query_files
        self.is_sparse = True
