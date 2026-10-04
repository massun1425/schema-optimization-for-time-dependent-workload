# ILP formulation of `TimeDependentOptimizer`

This note describes the integer linear program built by `core/time_dependent_optimizer.py`
(the proposed time-dependent MV selection, `--optimization-mode dynamic`).

## Notation

| Symbol | Code | Meaning |
|---|---|---|
| *I*, *J*, *T* | `I`, `J`, `T` | number of queries, MV candidates and time steps |
| *J*′ ⊆ *J* | `cand_j` | candidates kept by the candidate pruning (all candidates without pruning) |
| *u*<sub>ij</sub> | `u_ij[i][j]` | utility (cost saving) when query *i* uses MV *j* |
| *f*<sub>ti</sub> | `freq[t][i]` | frequency of query *i* at time step *t* |
| *b*<sub>j</sub> | `b_j[j]` | size of MV *j* |
| *B*<sub>max</sub> | `B_max` | storage budget |
| *X*<sub>ju</sub> | `X[j][u]` | 1 if MV *j* includes MV *u* |
| *m*<sub>j</sub> | `migration_cost[j]` | cost of creating MV *j* (full build: read + write; the `[]` entry of `simple_migration_costs.json`) |
| *w* | `migration_cost_weight` | weight of the migration cost (1.0 in all experiments) |

## Variables

| Variable | Type | Meaning |
|---|---|---|
| *y*<sub>ijt</sub> | binary | query *i* uses MV *j* at time step *t*; created only for *j* ∈ *J*′ with *u*<sub>ij</sub> > 0 |
| *z*<sub>jt</sub> | binary | MV *j* exists at time step *t* (*j* ∈ *J*′) |
| *c*<sub>jt</sub> | continuous in [0, 1] | MV *j* is created at time step *t*; the constraints below force it to 0 or 1 |

## Objective (minimized)

```
  - Σ_t Σ_i Σ_j  u_ij · f_ti · y_ijt          (workload cost: negative frequency-weighted utility)
  + Σ_t Σ_j      w · m_j · c_jt               (migration cost: creation cost of new MVs)
```

## Constraints

1. **Usage requires materialization**: *y*<sub>ijt</sub> ≤ *z*<sub>jt</sub> for every created *y*<sub>ijt</sub>.
2. **Inclusion exclusion**: for every created *y*<sub>ijt</sub>,

   *y*<sub>ijt</sub> + (Σ<sub>u ≠ j</sub> *X*<sub>ju</sub> · *y*<sub>iut</sub>) / |*J*′| ≤ 1.

   The sum is at most |*J*′|, so the scaled term is at most 1. If query *i* uses MV *j*, it
   cannot also use an MV that *j* includes; otherwise the constraint is not binding. One
   constraint per (*i*, *j*, *t*) replaces the pairwise constraints.
3. **Storage budget**: Σ<sub>j</sub> *b*<sub>j</sub> · *z*<sub>jt</sub> ≤ *B*<sub>max</sub> for every time step *t*.
4. **Creation flags**:
   - *t* = 0: *c*<sub>j0</sub> = *z*<sub>j0</sub> (every MV of the first schema is created);
   - *t* > 0: *c*<sub>jt</sub> ≥ *z*<sub>jt</sub> − *z*<sub>j,t−1</sub>, *c*<sub>jt</sub> ≤ *z*<sub>jt</sub>,
     *c*<sub>jt</sub> ≤ 1 − *z*<sub>j,t−1</sub> (an MV that already existed is kept, not created).

   Dropping an MV has no cost.

## Size of the model

With pruning, the model has |*J*′| · *T* variables *z* and *c*, one variable *y* per
(query, candidate with positive utility, time step), 2 constraints per *y*, *T* storage
constraints and 3 · |*J*′| · (*T* − 1) + |*J*′| creation constraints. The candidate pruning
(`core/cf_pruner.py`) reduces |*J*′| before the model is built.
