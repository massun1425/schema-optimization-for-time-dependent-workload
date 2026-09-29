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


class SparseMatrixBase:
    """Common read API for sparse utility matrices.

    Both the dict-backed ``SparseMatrix`` (used in-process, incl. the sequential
    path) and the shared-memory CSR ``SharedSparseMatrix`` (used by parallel
    workers) implement this, so optimizer code can iterate non-zeros the same
    way regardless of backend:

        for i, items in m.iter_rows():       # items yields (j, value)
            ...
        for j, v in m.row_items(i):          # one row's non-zeros
            ...
        m[i][j]                              # value or 0.0

    Detection downstream should use ``isinstance(x, SparseMatrixBase)``.
    """

    __slots__ = ()

    def iter_rows(self):  # -> Iterable[Tuple[int, Iterable[Tuple[int, float]]]]
        raise NotImplementedError

    def row_items(self, i: int):  # -> Iterable[Tuple[int, float]]
        raise NotImplementedError


class SparseXBase:
    """Common read API for sparse containment matrices.

    ``X[j][u]`` returns 1/0; ``X.children(j)`` returns the u's with an edge.
    Detection downstream should use ``isinstance(x, SparseXBase)``.
    """

    __slots__ = ()

    def children(self, j: int):
        raise NotImplementedError


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


class SparseMatrix(SparseMatrixBase):
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

    # --- common SparseMatrixBase API (delegates to the underlying dict) ---
    def iter_rows(self):
        for i, row in self.rows.items():
            yield i, row.items()

    def row_items(self, i: int):
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


class SparseX(SparseXBase):
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


# ============================================================================
# Shared-memory CSR variants (for parallel workers)
# ----------------------------------------------------------------------------
# Same read API as SparseMatrix/SparseX, but backed by flat CSR numpy arrays
# that can live in multiprocessing.shared_memory. Workers attach by name -> one
# physical copy shared across all processes, no per-task pickling, portable
# (works under both fork and spawn). Read-only; rows are sorted by column index.
# ============================================================================


class _CSRRow:
    """Row view over CSR slices supporting dense-style ``row[j]`` (0.0 default)."""

    __slots__ = ("_cols", "_data")

    def __init__(self, cols, data) -> None:
        self._cols = cols  # sorted 1-D int array of this row's column indices
        self._data = data  # 1-D float array aligned with _cols

    def __getitem__(self, j: int) -> float:
        import numpy as np
        cols = self._cols
        k = int(np.searchsorted(cols, j))
        if k < cols.shape[0] and int(cols[k]) == j:
            return float(self._data[k])
        return 0.0

    def items(self):
        return zip(self._cols.tolist(), self._data.tolist())


class SharedSparseMatrix(SparseMatrixBase):
    """CSR utility matrix backed by (indptr, col, data) arrays (rows sorted)."""

    def __init__(self, indptr, col, data, I: int, J: int) -> None:
        self.indptr = indptr
        self.col = col
        self.data = data
        self.I = I
        self.J = J

    def __len__(self) -> int:
        return self.I

    def __getitem__(self, i: int) -> _CSRRow:
        s = int(self.indptr[i]); e = int(self.indptr[i + 1])
        return _CSRRow(self.col[s:e], self.data[s:e])

    def iter_rows(self):
        ip, col, data = self.indptr, self.col, self.data
        for i in range(self.I):
            s = int(ip[i]); e = int(ip[i + 1])
            if e > s:  # skip all-zero rows, matching dict-backed behavior
                yield i, list(zip(col[s:e].tolist(), data[s:e].tolist()))

    def row_items(self, i: int):
        s = int(self.indptr[i]); e = int(self.indptr[i + 1])
        return list(zip(self.col[s:e].tolist(), self.data[s:e].tolist()))

    def nnz(self) -> int:
        return int(self.indptr[-1])


class _CSRXRow:
    """Containment row view over a CSR slice: ``row[u]`` -> 1/0 (sorted)."""

    __slots__ = ("_idx",)

    def __init__(self, idx) -> None:
        self._idx = idx  # sorted 1-D int array of this row's column indices

    def __getitem__(self, u: int) -> int:
        import numpy as np
        idx = self._idx
        k = int(np.searchsorted(idx, u))
        return 1 if (k < idx.shape[0] and int(idx[k]) == u) else 0


class SharedSparseX(SparseXBase):
    """CSR containment matrix backed by (indptr, idx) arrays (rows sorted)."""

    def __init__(self, indptr, idx, J: int) -> None:
        self.indptr = indptr
        self.idx = idx
        self.J = J

    def __len__(self) -> int:
        return self.J

    def __getitem__(self, j: int) -> _CSRXRow:
        s = int(self.indptr[j]); e = int(self.indptr[j + 1])
        return _CSRXRow(self.idx[s:e])

    def children(self, j: int):
        s = int(self.indptr[j]); e = int(self.indptr[j + 1])
        return self.idx[s:e].tolist()

    def nnz(self) -> int:
        return int(self.indptr[-1])


# --- CSR builders (run once in the main process, on dict-backed Sparse*) ---

def build_u_csr(sm: SparseMatrix):
    """SparseMatrix -> (indptr, col, data) numpy arrays; rows sorted by column."""
    import numpy as np
    I, J = sm.I, sm.J
    indptr = np.zeros(I + 1, dtype=np.int64)
    for i in range(I):
        indptr[i + 1] = indptr[i] + len(sm.rows.get(i, ()))
    nnz = int(indptr[I])
    col = np.empty(nnz, dtype=np.int32)
    data = np.empty(nnz, dtype=np.float64)
    pos = 0
    for i in range(I):
        row = sm.rows.get(i)
        if row:
            for j in sorted(row):
                col[pos] = j
                data[pos] = row[j]
                pos += 1
    return indptr, col, data


def build_x_csr(sx: SparseX):
    """SparseX -> (indptr, idx) numpy arrays; rows sorted by column."""
    import numpy as np
    J = sx.J
    indptr = np.zeros(J + 1, dtype=np.int64)
    for j in range(J):
        indptr[j + 1] = indptr[j] + len(sx.adj.get(j, ()))
    nnz = int(indptr[J])
    idx = np.empty(nnz, dtype=np.int32)
    pos = 0
    for j in range(J):
        s = sx.adj.get(j)
        if s:
            for u in sorted(s):
                idx[pos] = u
                pos += 1
    return indptr, idx


# --- multiprocessing.shared_memory helpers ---

def put_array_to_shm(arr):
    """Copy a numpy array into a fresh SharedMemory block.

    Returns (shm, spec) where spec=(name, shape, dtype_str) is small/picklable.
    Keep `shm` referenced in the parent until after all workers are done.
    """
    import numpy as np
    from multiprocessing import shared_memory
    shm = shared_memory.SharedMemory(create=True, size=max(1, int(arr.nbytes)))
    view = np.ndarray(arr.shape, dtype=arr.dtype, buffer=shm.buf)
    view[:] = arr[:]
    return shm, (shm.name, arr.shape, arr.dtype.str)


def attach_array_from_shm(spec):
    """Attach to an existing SharedMemory block; returns (shm, ndarray view).

    Keep `shm` referenced for the lifetime of the returned array.
    """
    import numpy as np
    from multiprocessing import shared_memory
    name, shape, dtype_str = spec
    shm = shared_memory.SharedMemory(name=name)
    arr = np.ndarray(shape, dtype=np.dtype(dtype_str), buffer=shm.buf)
    return shm, arr
