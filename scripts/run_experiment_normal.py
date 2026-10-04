#!/usr/bin/env python3
"""
Small-scale experiment - normal-mode runner script

Runs MV optimization with a single frequency setting.

Usage:
    python experiments/small_test/run_experiment_normal.py --phase all
    python experiments/small_test/run_experiment_normal.py --phase 2
"""

import argparse
import json
import logging
import pickle
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# Logging configuration (to show pruning logs)
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(name)s - %(message)s'
)

# Add the project root to the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from core.sparse_structures import SparseMatrix
from src.core.query_parser import QueryParser
from src.utils.legacy import get_all_job_queries, natural_sort_key

# Docker/Local switching helper
experiment_dir = Path(__file__).parent.parent
sys.path.insert(0, str(experiment_dir))
from utils.postgres_executor import PostgresExecutor, add_docker_args


class NormalModeExperiment:
    """Class that runs the normal-mode experiment phase by phase"""
    
    def __init__(self, exp_dir: str = ".", query_set: str = "job", exp_suffix: str = "", use_docker: Optional[bool] = None, recalc_mode: bool = False, window_size: int = 4, freq_weight: str = "uniform"):
        """Initialize

        Args:
            exp_dir: Path to the experiment directory
            query_set: Name of the query set to use (e.g., job, job_like, explicit_join)
            exp_suffix: Suffix identifying the experiment (e.g., _16_2, _16_4)
            use_docker: Whether to use Docker (None: determined from environment variables)
            recalc_mode: Whether to use recalculated costs
            window_size: Moving-average window width used by adaptive optimization (default: 4)
            freq_weight: Weighting of frequencies within the window ("uniform"=simple moving average, "linear"=DeepSea-style linear recency weights)
        """
        self.exp_dir = Path(exp_dir)
        self.query_set = query_set  # Store the query set name
        self.exp_suffix = exp_suffix  # Store the suffix
        self.recalc_mode = recalc_mode
        self.window_size = window_size  # Store the moving-average window width
        self.freq_weight = freq_weight  # Weighting scheme for frequencies within the window
        
        # Initialize the PostgreSQL executor
        self.pg_executor = PostgresExecutor(use_docker=use_docker)
        
        # Settings() loads config/default.yaml (or the file given by $CONFIG_PATH), relative to
        # the current directory, so run this script from the repository root. The DB_HOST,
        # DB_PORT, DB_NAME, DB_USER and DB_PASSWORD environment variables override the database
        # settings. The storage budget of the experiments is given by --b-max, not by the
        # optimization.storage_limit_* values of the configuration file.
        self.settings = Settings()
        
        # Paths of each directory (per query set)
        self.queries_dir = self.exp_dir / "01_queries" / self.query_set
        self.json_dir = self.exp_dir / "02_json" / self.query_set
        self.parsed_dir = self.exp_dir / "03_parsed" / self.query_set
        self.optimized_dir = self.exp_dir / "04_optimized" / self.query_set
        self.mv_sql_dir = self.exp_dir / "05_mv_sql" / self.query_set
        self.rewritten_dir = self.exp_dir / "06_rewritten" / self.query_set

        # The pickle file is also stored per query set inside the 03_parsed folder
        self.pickle_path = self.parsed_dir / "qp_class.pkl"

        self.qp: Optional[QueryParser] = None
        self.result = None
        
        # Record the execution time of each phase
        self.phase_times = {}

        # Command-line arguments of this run (set by main()); recorded in the result files
        self.run_args = {}
        
        # Check that the query set exists
        if not self.queries_dir.exists():
            print(f"Warning: query directory not found: {self.queries_dir}")
            print(f"Available query sets:")
            base_dir = self.exp_dir / "01_queries"
            if base_dir.exists():
                for d in base_dir.iterdir():
                    if d.is_dir():
                        print(f"  - {d.name}")
    
    def print_header(self, title: str, phase: int = 0):
        """Print a phase header"""
        print("\n" + "=" * 70)
        if phase > 0:
            print(f"Phase {phase}: {title}")
        else:
            print(title)
        print("=" * 70)
    
    def print_success(self, message: str):
        """Print a success message"""
        print(f"  [OK] {message}")
    
    def print_info(self, message: str):
        """Print an info message"""
        print(f"  → {message}")
    
    def print_error(self, message: str):
        """Print an error message"""
        print(f"  [ERROR] {message}")

    # ------------------------------------------------------------------
    # Run configuration recorded in the result files
    #
    # The result JSON files get one additional top-level key "run_config"; existing keys are
    # unchanged, so the readers (Phases 7-9, paper_figures/) are not affected.
    # The preprocessing settings are written to a separate file next to the cost file
    # (04_migration/<set>/simple_migration_costs.meta.json), because the cost file itself is
    # read as a mapping from MV names to costs.
    # ------------------------------------------------------------------
    _code_version_cache = None

    @classmethod
    def _code_version(cls) -> dict:
        """Git commit of the code and whether tracked files had uncommitted changes."""
        if cls._code_version_cache is None:
            repo = Path(__file__).resolve().parent.parent
            info = {"git_commit": None, "git_dirty": None}
            try:
                info["git_commit"] = subprocess.run(
                    ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True,
                    timeout=30, check=True).stdout.strip()
                status = subprocess.run(
                    ["git", "status", "--porcelain", "--untracked-files=no"], cwd=repo,
                    capture_output=True, text=True, timeout=120, check=True).stdout
                info["git_dirty"] = bool(status.strip())
            except Exception:
                pass
            cls._code_version_cache = info
        return cls._code_version_cache

    def _preprocessing_meta_path(self) -> Path:
        return self.exp_dir / "04_migration" / self.query_set / "simple_migration_costs.meta.json"

    def _run_config(self, phase: str, **settings) -> dict:
        """Build the "run_config" entry of a result file.

        Args:
            phase: Phase that produced the file (e.g. "6", "9")
            settings: Settings actually used by the phase (e.g. the storage budget in bytes)
        """
        import datetime
        import platform
        from importlib import metadata

        packages = {}
        for name in ("gurobipy", "numpy", "psycopg2-binary", "PyYAML", "sqlparse"):
            try:
                packages[name] = metadata.version(name)
            except metadata.PackageNotFoundError:
                packages[name] = None
        config = {
            "phase": phase,
            "timestamp": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "command": list(sys.argv),
            "args": self.run_args,
            "settings": {k: (str(v) if isinstance(v, Path) else v) for k, v in settings.items()},
            "query_set": self.query_set,
            "exp_suffix": self.exp_suffix,
            "code_version": self._code_version(),
            "python": platform.python_version(),
            "packages": packages,
        }
        meta_path = self._preprocessing_meta_path()
        if meta_path.exists():
            try:
                config["preprocessing"] = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                config["preprocessing"] = None
        return config

    def _write_preprocessing_meta(self, step: str, **info) -> None:
        """Record the settings of a preprocessing step (Phase 5 or 5.5) next to the cost file.

        Phase 5 rewrites the cost file, so it also discards the record of an earlier
        recalculation.
        """
        import datetime

        meta_path = self._preprocessing_meta_path()
        meta = {}
        if meta_path.exists() and step != "cost_estimation":
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
        meta[step] = {
            "timestamp": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "command": list(sys.argv),
            "code_version": self._code_version(),
            **info,
        }
        try:
            meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception as e:
            self.print_error(f"Could not write {meta_path}: {e}")
    
    def _drop_all_mvs(self):
        """Drop all existing materialized views"""
        import psycopg2
        
        try:
            conn = psycopg2.connect(
                database=self.settings.database.database,
                user=self.settings.database.user,
                password=self.settings.database.password,
                host='localhost'
            )
            
            with conn.cursor() as cursor:
                # Fetch the existing MVs
                cursor.execute("""
                    SELECT schemaname, matviewname 
                    FROM pg_matviews 
                    WHERE schemaname = 'public'
                """)
                mvs = cursor.fetchall()
                
                if not mvs:
                    self.print_info("No MVs to drop")
                    conn.close()
                    return True
                
                # Drop all MVs
                dropped_count = 0
                for schema, mv_name in mvs:
                    try:
                        cursor.execute(f"DROP MATERIALIZED VIEW IF EXISTS {schema}.{mv_name} CASCADE;")
                        dropped_count += 1
                    except Exception as e:
                        self.print_error(f"  {mv_name}: drop failed: {e}")
            
            conn.commit()
            conn.close()
            
            self.print_success(f"Dropped {dropped_count} existing MVs")
            return True
            
        except Exception as e:
            self.print_error(f"MV drop error: {e}")
            return False
    
    def _analyze_base_tables(self):
        """Run ANALYZE on the base tables"""
        import psycopg2
        
        # All base tables of the JOB (IMDB) dataset (21 tables)
        base_tables = [
            # Main large tables
            'title', 'cast_info', 'movie_info', 'movie_companies',
            'movie_keyword', 'name', 'person_info', 'movie_info_idx',
            # Other entity tables
            'aka_name', 'aka_title', 'char_name', 'complete_cast',
            'movie_link',
            # Dimension tables (small but important)
            'keyword', 'company_name', 'company_type', 'info_type',
            'kind_type', 'role_type', 'link_type', 'comp_cast_type'
        ]
        
        try:
            conn = psycopg2.connect(
                database=self.settings.database.database,
                user=self.settings.database.user,
                password=self.settings.database.password,
                host='localhost'
            )
            
            analyzed_count = 0
            with conn.cursor() as cursor:
                # Raise the statistics target at session level (default 100 -> 1000)
                # This makes histograms finer-grained and improves estimation accuracy on skewed data such as JOB
                # Persisting it at table level costs storage and ANALYZE time, so session level is sufficient
                try:
                    cursor.execute("SET default_statistics_target = 1000;")
                    cursor.execute("SET random_page_cost = 1.1;")
                except Exception as e:
                    pass
                
                for table in base_tables:
                    try:
                        cursor.execute(f"ANALYZE {table};")
                        analyzed_count += 1
                    except Exception:
                        pass  # Skip if the table does not exist
            
            conn.commit()
            conn.close()
            
            self.print_success(f"ANALYZE completed on {analyzed_count} base tables")
            return True
            
        except Exception as e:
            self.print_error(f"ANALYZE error: {e}")
            return False

    def _update_u_ij_if_recalc(self):
        """If --recalc mode is enabled, load the costs and update u_ij
        
        Returns:
            Tuple[Dict[int, float], List[float]]: (migration_cost, b_j) 
            Returns (None, None) if recalc is disabled
        """
        if not self.recalc_mode:
            return None, None
            
        from core.io_loaders import load_full_build_costs_and_sizes
        
        self.print_info("RECALC MODE: overwriting u_ij (utility) with utility...")
        migration_cost, utilities, b_j = load_full_build_costs_and_sizes(
            str(self.exp_dir), 
            self.qp.node_list, 
            self.query_set
        )
        
        updated_count = 0
        if isinstance(self.qp.u_ij, SparseMatrix):
            # Sparse: traverse and update only the existing non-zeros (usage relations), avoiding an O(I*J) scan
            for row in self.qp.u_ij.rows.values():
                for j in list(row.keys()):
                    if row[j] > 0 and j in utilities:
                        row[j] = utilities[j]
                        updated_count += 1
        else:
            for i in range(len(self.qp.u_ij)):
                for j in range(len(self.qp.u_ij[i])):
                    # Update only where a structure (usage relation) already exists
                    if self.qp.u_ij[i][j] > 0:
                        # Update the utility using utilities (not migration_cost)
                        if j in utilities:
                            self.qp.u_ij[i][j] = utilities[j]
                            updated_count += 1
                        
        self.print_success(f"  {updated_count} utility entries updated")
        return migration_cost, b_j  # Return migration_cost unchanged (used as creation cost)
    
    def _clear_caches(self):
        """Clear the PostgreSQL cache
        
        Clears shared_buffers using pg_drop_caches() from the pg_prewarm extension.
        Available in PostgreSQL 14 or later. On older versions, prints a warning and skips.
        """
        import psycopg2
        
        try:
            conn = psycopg2.connect(
                database=self.settings.database.database,
                user=self.settings.database.user,
                password=self.settings.database.password,
                host='localhost'
            )
            
            with conn.cursor() as cursor:
                # First check/create the pg_prewarm extension
                try:
                    cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_prewarm;")
                    conn.commit()
                except Exception:
                    pass  # Skip if we lack the privilege
                
                # Run pg_drop_caches() to clear shared_buffers
                try:
                    cursor.execute("SELECT pg_drop_caches();")
                    conn.commit()
                    self.print_success("Cleared the PostgreSQL cache")
                except psycopg2.errors.UndefinedFunction:
                    # pg_drop_caches() does not exist (PostgreSQL older than 14)
                    self.print_info("pg_drop_caches() is unavailable (requires PostgreSQL 14+)")
                    # Fallback: clear the session cache with the DISCARD command
                    try:
                        cursor.execute("DISCARD ALL;")
                        conn.commit()
                        self.print_info("Cleared the session cache (DISCARD ALL)")
                    except Exception:
                        pass
                except Exception as e:
                    self.print_info(f"Skipping cache clearing: {e}")
            
            conn.close()
            return True
            
        except Exception as e:
            self.print_error(f"Cache clearing error: {e}")
            return False
    
    def _disable_autovacuum(self):
        """Disable autovacuum on all tables (for benchmarking)
        
        Disables autovacuum on all user tables (base tables and MVs).
        This reduces timing variance caused by background activity during the benchmark.
        """
        import psycopg2
        
        try:
            conn = psycopg2.connect(
                database=self.settings.database.database,
                user=self.settings.database.user,
                password=self.settings.database.password,
                host='localhost'
            )
            
            disabled_count = 0
            with conn.cursor() as cursor:
                # Fetch all tables and MVs in the public schema
                cursor.execute("""
                    SELECT tablename FROM pg_tables WHERE schemaname = 'public'
                    UNION
                    SELECT matviewname FROM pg_matviews WHERE schemaname = 'public'
                """)
                tables = cursor.fetchall()
                
                # Disable autovacuum on each table/MV
                for (table_name,) in tables:
                    try:
                        cursor.execute(f"ALTER TABLE {table_name} SET (autovacuum_enabled = false);")
                        disabled_count += 1
                    except Exception as e:
                        # Skip, e.g., if the table has been dropped
                        pass
            
            conn.commit()
            conn.close()
            
            self.print_success(f"Disabled autovacuum: {disabled_count} tables/MVs")
            return True
            
        except Exception as e:
            self.print_error(f"Error disabling autovacuum: {e}")
            return False
    
    def _enable_autovacuum(self):
        """Enable autovacuum on all tables (restore the default)
        
        After the benchmark, restores the autovacuum setting of all tables to the default.
        """
        import psycopg2
        
        try:
            conn = psycopg2.connect(
                database=self.settings.database.database,
                user=self.settings.database.user,
                password=self.settings.database.password,
                host='localhost'
            )
            
            enabled_count = 0
            with conn.cursor() as cursor:
                # Fetch all tables and MVs in the public schema
                cursor.execute("""
                    SELECT tablename FROM pg_tables WHERE schemaname = 'public'
                    UNION
                    SELECT matviewname FROM pg_matviews WHERE schemaname = 'public'
                """)
                tables = cursor.fetchall()
                
                # Reset the autovacuum setting of each table/MV (restore the default)
                for (table_name,) in tables:
                    try:
                        cursor.execute(f"ALTER TABLE {table_name} RESET (autovacuum_enabled);")
                        enabled_count += 1
                    except Exception as e:
                        # Skip, e.g., if the table has been dropped
                        pass
            
            conn.commit()
            conn.close()
            
            self.print_success(f"Enabled autovacuum: {enabled_count} tables/MVs")
            return True
            
        except Exception as e:
            self.print_error(f"Error enabling autovacuum: {e}")
            return False
    
    def _force_checkpoint(self):
        """Force a checkpoint
        
        Running a checkpoint before the benchmark:
        - clears the WAL (Write-Ahead Log) buffers so that every run starts from the same state
        - delays irregular checkpoints during the benchmark
        - guarantees the same initial conditions for each run, reducing timing variance
        
        A checkpoint can take tens to hundreds of seconds, so if one occurs at a random
        point during the benchmark it causes large variance.
        """
        import psycopg2
        
        try:
            conn = psycopg2.connect(
                database=self.settings.database.database,
                user=self.settings.database.user,
                password=self.settings.database.password,
                host='localhost'
            )
            
            self.print_info("Running a forced checkpoint (clearing WAL buffers)...")
            checkpoint_start = time.time()
            
            with conn.cursor() as cursor:
                # Run the CHECKPOINT command
                # This writes all dirty buffers to disk
                cursor.execute("CHECKPOINT;")
            
            conn.commit()
            conn.close()
            
            checkpoint_time = time.time() - checkpoint_start
            self.print_success(f"Checkpoint completed ({checkpoint_time:.2f}s)")
            return True
            
        except Exception as e:
            self.print_error(f"Checkpoint error: {e}")
            return False
    
    def _convert_select_to_star(self, query: str) -> str:
        """Rewrite the SELECT clause to *
        
        Since MVs are created with SELECT *, running EXPLAIN with SELECT * as well
        makes Plan Width match the actual MV size and improves size-estimation accuracy.
        
        Args:
            query: Original SQL query
            
        Returns:
            Query whose SELECT clause is rewritten to *
        """
        import re
        
        # Replace the part between SELECT and FROM with *
        # Group 1: SELECT + whitespace
        # Group 2: FROM + whitespace (kept)
        # Replace the part in between (.*?) with *
        pattern = r'(SELECT\s+).*?(\s+FROM\s+)'
        replacement = r'\1*\2'
        
        converted = re.sub(pattern, replacement, query, count=1, flags=re.IGNORECASE | re.DOTALL)
        
        return converted
    
    def _create_extended_statistics(self):
        """Create multivariate statistics (Extended Statistics) to improve estimation accuracy for JOB queries
        
        So that the PostgreSQL planner can understand correlations between columns,
        this creates multi-column dependency and MCV (Most Common Values) statistics.
        This improves row-count estimation for queries with complex WHERE clauses,
        leading to better join orders.
        """
        import psycopg2
        
        # List of statistics to create (only the most effective ones)
        # (statistics name, statistics type, target columns, table name)
        extended_stats = [
            # ===== Most important: filter-column correlations on large tables =====
            # title: correlation between kind and production year (helps almost all queries)
            ("stts_title_kind_year", "(dependencies, mcv)", "kind_id, production_year", "title"),
            
            # movie_info: correlation between info type and content (used by 30% of queries)
            ("stts_movie_info_corr", "(dependencies, mcv)", "info_type_id, info", "movie_info"),
            
            # cast_info: correlation between role and note (large effect on 10c, 25c, 20a, etc.)
            ("stts_cast_info_note", "(dependencies, mcv)", "role_id, note", "cast_info"),
            
            # ===== Important: join key + filter correlations (helps post-join row-count estimation) =====
            # movie_info: movie ID and info type (estimation of intermediate join results)
            ("stts_mi_movie_info", "(dependencies, mcv)", "movie_id, info_type_id", "movie_info"),
            
            # cast_info: movie ID and role (estimation of large JOINs)
            ("stts_ci_join_corr", "(dependencies, mcv)", "movie_id, role_id", "cast_info"),
            
            # movie_companies: movie and company type (helps the 17* queries)
            ("stts_mc_movie_company", "(dependencies, mcv)", "movie_id, company_type_id", "movie_companies"),
            
            # ===== Somewhat important: frequently used medium-sized tables =====
            # movie_keyword: movie and keyword (used by 6f, 29c, etc.)
            ("stts_mk_movie_keyword", "(dependencies, mcv)", "movie_id, keyword_id", "movie_keyword"),
            
            # person_info: info type and content (helps 7c, 29c)
            ("stts_person_info_corr", "(dependencies, mcv)", "info_type_id, info", "person_info"),
        ]
        
        try:
            conn = psycopg2.connect(
                database=self.settings.database.database,
                user=self.settings.database.user,
                password=self.settings.database.password,
                host='localhost'
            )
            
            created_count = 0
            skipped_count = 0
            
            with conn.cursor() as cursor:
                for stat_name, stat_type, columns, table in extended_stats:
                    try:
                        # Drop the existing statistics (if any)
                        cursor.execute(f"DROP STATISTICS IF EXISTS {stat_name};")
                        
                        # Create the new statistics
                        sql = f"CREATE STATISTICS {stat_name} {stat_type} ON {columns} FROM {table};"
                        cursor.execute(sql)
                        created_count += 1
                        
                    except psycopg2.errors.UndefinedTable:
                        # Skip if the table does not exist
                        conn.rollback()
                        skipped_count += 1
                    except psycopg2.errors.UndefinedColumn:
                        # Skip if the column does not exist
                        conn.rollback()
                        skipped_count += 1
                    except Exception as e:
                        # Log other errors and skip
                        conn.rollback()
                        self.print_info(f"  Skipping creation of statistics {stat_name}: {e}")
                        skipped_count += 1
                
                conn.commit()
            
            conn.close()
            
            if created_count > 0:
                self.print_success(f"Created {created_count} extended statistics")
                if skipped_count > 0:
                    self.print_info(f"  {skipped_count} skipped (table or column does not exist)")
            else:
                self.print_info("Skipping creation of extended statistics (target tables do not exist)")
            
            return True
            
        except Exception as e:
            self.print_error(f"Extended statistics creation error: {e}")
            return False
    
    def phase1_generate_explain_json(self):
        """Phase 1: EXPLAIN JSON generation"""
        self.print_header("EXPLAIN JSON generation", 1)
        
        # Drop all existing MVs
        self.print_info("Cleaning up existing MVs...")
        if not self._drop_all_mvs():
            self.print_error("Failed to drop MVs")
            # Continue even on failure (warning only)
        
        # Update base-table statistics (to keep statistics fixed throughout the experiment)
        # NOTE: Not run in the Phase 9 benchmark (to avoid statistics variance)
        # ANALYZE uses random sampling, so each run produces slightly different statistics,
        # which may change query plans and introduce variance into benchmark results
        self.print_info("Updating base-table statistics (fixed for the whole experiment)...")
        if not self._analyze_base_tables():
            self.print_error("ANALYZE on base tables failed")
            # Continue even on failure (warning only)
        
        # Create extended statistics (Extended Statistics)
        # Multivariate statistics to improve join-order estimation for JOB queries

        # self.print_info("Creating extended statistics...")
        # if not self._create_extended_statistics():
        #     self.print_error("Failed to create extended statistics")
        #     # Continue even on failure (warning only)
        
        # Clear the PostgreSQL cache
        # self.print_info("Clearing the PostgreSQL cache...")
        # self._clear_caches()
        # Start timing after cleanup has finished
        phase_start = time.time()
        
        # Check the query directory
        if not self.queries_dir.exists():
            self.print_error(f"Query directory not found: {self.queries_dir}")
            return False
        
        query_files = sorted(self.queries_dir.glob("*.sql"))
        
        if not query_files:
            self.print_error(f"No query files found in {self.queries_dir}")
            return False
        
        self.print_info(f"Query set: {self.query_set}")
        self.print_info(f"Processing {len(query_files)} query files")
        
        # Create the output directory (per query set)
        self.json_dir.mkdir(parents=True, exist_ok=True)
        
        for query_file in query_files:
            output_file = self.json_dir / f"{query_file.stem}.json"
            
            self.print_info(f"Processing: {query_file.name}")
            
            # Read the query (removing comment lines)
            with open(query_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            query_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped and not stripped.startswith('--'):
                    query_lines.append(line)
            
            query_sql = ''.join(query_lines).strip()
            
            # *** Rewrite the SELECT clause to * ***
            # Since MVs are created with SELECT *, running EXPLAIN with SELECT * as well
            # makes Plan Width match the actual MV size and improves size-estimation accuracy
            query_sql_star = self._convert_select_to_star(query_sql)
            
            # Run EXPLAIN JSON (Bitmap Scan disabled + better statistics accuracy)
            # Run the SET statements and EXPLAIN separately and take only the EXPLAIN result
            
            try:
                result = self.pg_executor.run_explain_json(
                    query_sql_star,  # <- use the SELECT * version
                    database=self.settings.database.database,
                    set_options=[
                        "SET enable_bitmapscan = off;",
                        "SET default_statistics_target = 1000;",
                        "SET random_page_cost = 1.1;"
                    ]
                )
                
                # Extract only the last JSON part from the output (excluding output of the SET statements)
                output_lines = result.stdout.strip().split('\n')
                # Exclude "SET" lines and keep only the JSON
                json_lines = [line for line in output_lines if line and line != 'SET']
                json_text = '\n'.join(json_lines)
                json_data = json.loads(json_text)
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, indent=2, ensure_ascii=False)
                
                self.print_success(f"Generated {output_file.name}")
                
            except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
                self.print_error(f"Failed to process {query_file.name}: {e}")
                return False
        
        return True
    
    def phase2_parse_queries(self):
        """Phase 2: Query parsing (changed to not apply frequency weighting)"""
        self.print_header("Query parsing", 2)
        phase_start = time.time()
        
        # from frequency_weighted_parser import FrequencyWeightedParser
        
        # self.print_info("Initializing FrequencyWeightedParser")
        
        # frequency_file = self.queries_dir / "frequency.json"
        
        # if frequency_file.exists():
           # self.print_info(f"Frequency file: {frequency_file}")
           # self.qp = FrequencyWeightedParser(self.settings, str(frequency_file))
    
        # self.print_info("Frequency file not found. Using the regular parser")
        self.qp = QueryParser(self.settings)
        
        self.print_info("Parsing queries...")
        try:
            query_dir = str(self.json_dir)
            
            # Check the JSON files
            json_files = list(self.json_dir.glob("*.json"))
            self.print_info(f"JSON files found: {len(json_files)}")
            if json_files:
                self.print_info(f"  Example: {json_files[0].name}")
            
            # Monkey patch: replace get_all_job_queries in the query_parser module
            # This part is convoluted and should be simplified, but that requires modifying query_parser.py
            import src.core.query_parser as qp_module
            original_get_all_job_queries = qp_module.get_all_job_queries
            
            def custom_get_all_job_queries(path):
                """Custom function: get JSON files directly from the specified directory"""
                import re
                
                def natural_sort_key(s):
                    return [int(text) if text.isdigit() else text.lower() for text in re.split("([0-9]+)", str(s))]
                
                query_paths = []
                query_count = {}
                
                job_dir = Path(path)
                print(f"  [DEBUG] custom_get_all_job_queries called with path: {path}")
                print(f"  [DEBUG] Directory exists: {job_dir.exists()}")
                
                if not job_dir.exists():
                    return [], {}
                
                # Sort in natural order
                json_files = sorted(job_dir.glob("*.json"), key=lambda x: natural_sort_key(x.name))
                
                for json_file in json_files:
                    query_path = str(json_file)
                    query_paths.append(query_path)
                    query_count[query_path] = 1
                
                print(f"  [DEBUG] Found {len(query_paths)} JSON files (sorted naturally)")
                return query_paths, query_count
            
            # Replace the reference in the query_parser module
            qp_module.get_all_job_queries = custom_get_all_job_queries
            
            try:
                self.qp.query_parse(
                    q_num=0,
                    path=str(self.json_dir),
                    insert_query=self.settings.optimization.insert_queries,
                    sql_dir=str(self.queries_dir)
                )
            finally:
                # Restore the original function
                qp_module.get_all_job_queries = original_get_all_job_queries
            
            insert_query = self.settings.optimization.insert_queries
            
            #if isinstance(self.qp, FrequencyWeightedParser):
             #   self.qp.apply_frequency_weights(files)
              #  self.qp.calculate_maintenance_costs(insert_query)
            
            self.print_success(f"Parsed {len(self.qp.query)} queries")
            self.print_info(f"  Number of leaf nodes: {len(self.qp.qm.leaf_nodes_map)}")
            self.print_info(f"  Number of non-leaf nodes: {len(self.qp.qm.non_leaf_nodes_map)}")
            self.print_info(f"  Total number of nodes: {self.qp.s_num}")
            
            self._save_parse_results()
            
            # Record the phase time
            self.phase_times['phase2_parse'] = time.time() - phase_start
            
            return True
            
        except Exception as e:
            self.print_error(f"Query parsing failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
# Run only phase 2.5
# python scripts/run_experiment_normal.py --phase 2.5 --query-set job

    def phase3_annotate_json(self):
        """Phase 3: Annotate JSON files with node IDs"""
        self.print_header("Annotate JSON files with node IDs", 3)
        phase_start = time.time()
        
        if self.qp is None:
            if not self.pickle_path.exists():
                self.print_error(f"{self.pickle_path} not found")
                self.print_info("Run phase 2 first")
                return False
            
            self.print_info(f"Loading parse results: {self.pickle_path}")
            try:
                with open(self.pickle_path, 'rb') as f:
                    self.qp = pickle.load(f)
                self.print_success(f"Loaded {self.qp.s_num} nodes")
            except Exception as e:
                self.print_error(f"Failed to load parse results: {e}")
                return False
        
        # Get the list of JSON files
        json_files = sorted(self.json_dir.glob("*.json"))
        
        if not json_files:
            self.print_error(f"No JSON files found in {self.json_dir}")
            return False
        
        self.print_info(f"Processing {len(json_files)} JSON files")
        
        try:
            from src.core.parse_exporter import ParseExporter
            
            # Initialize ParseExporter
            exporter = ParseExporter(self.qp.qm)
            
            # Overwrite the JSON files directly (set output_dir to the same directory)
            self.print_info("Adding node IDs...")
            
            # Write to a temporary directory, then overwrite
            temp_dir = self.json_dir.parent / f".temp_{self.query_set}"
            
            # Write the annotated files to the temporary directory
            exporter.annotate_query_files(
                [str(f) for f in json_files],
                temp_dir
            )
            
            # Move from the temporary directory to the original location (overwrite)
            annotated_files = list(temp_dir.glob("*.json"))
            for annotated_file in annotated_files:
                target_file = self.json_dir / annotated_file.name
                import shutil
                shutil.move(str(annotated_file), str(target_file))
            
            # Remove the temporary directory
            if temp_dir.exists():
                import shutil
                shutil.rmtree(temp_dir)
            
            self.print_success(f"Added node IDs to {len(json_files)} JSON files")
            self.print_info(f"  Updated in: {self.json_dir}")
            
            # Record the phase time
            self.phase_times['phase3_annotate_json'] = time.time() - phase_start
            
            return True
            
        except Exception as e:
            self.print_error(f"Node ID annotation failed: {e}")
            import traceback
            traceback.print_exc()
            
            # Clean up the temporary directory on error
            if temp_dir.exists():
                import shutil
                shutil.rmtree(temp_dir)
            
            return False
    
    def _save_parse_results(self):
        """Save the parse results"""
        # Create the directory where the pickle file is saved
        self.pickle_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.pickle_path, 'wb') as f:
            pickle.dump(self.qp, f)
        
        self.print_success(f"Saved parse results to {self.pickle_path}")
        
        summary = {
            "num_queries": len(self.qp.query),
            "num_leaf_nodes": len(self.qp.qm.leaf_nodes_map),
            "num_non_leaf_nodes": len(self.qp.qm.non_leaf_nodes_map),
            "total_nodes": self.qp.s_num,
            "node_list": self.qp.node_list,
            "u_ij_shape": [len(self.qp.u_ij), len(self.qp.u_ij[0]) if self.qp.u_ij else 0],
            "b_j_length": len(self.qp.b_j),
            "m_cost_length": len(self.qp.m_cost),
        }
        summary_path = self.parsed_dir / "parse_summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        self.print_success(f"Saved summary to {summary_path}")
    
    def phase4_enumerate_migration_plans(self):
        """Phase 4: Migration plan enumeration"""
        self.print_header("Migration plan enumeration", 4)
        phase_start = time.time()
        
        if self.qp is None:
            if not self.pickle_path.exists():
                self.print_error(f"{self.pickle_path} not found")
                self.print_info("Run phase 2 first")
                return False
            
            self.print_info(f"Loading parse results: {self.pickle_path}")
            try:
                with open(self.pickle_path, 'rb') as f:
                    self.qp = pickle.load(f)
                self.print_success(f"Loaded {self.qp.s_num} nodes")
            except Exception as e:
                self.print_error(f"Failed to load parse results: {e}")
                return False
        
        try:
            from migration.enumerate_simple_migration_plan import GetSimpleMigrationPlans
            
            self.print_info("Enumerating migration plans...")
            
            # Create a GetSimpleMigrationPlans instance
            migrator = GetSimpleMigrationPlans(
                settings=self.settings,
                query_set=self.query_set,
                exp_dir=self.exp_dir
            )
            
            # Get and save the migration plans
            migrator.get_migration_sqls()
            
            # Check the output file path
            output_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_plans.json"
            
            if output_file.exists():
                self.print_success(f"Saved migration plans: {output_file}")
                
                # Show statistics of the file
                with open(output_file, 'r', encoding='utf-8') as f:
                    plans = json.load(f)
                self.print_info(f"  {len(plans)} node plans generated")
            else:
                self.print_error("Migration plan file not found")
                return False
            
            # Record the phase time
            self.phase_times['phase4_migration_plans'] = time.time() - phase_start
            
            return True
            
        except Exception as e:
            self.print_error(f"Migration plan enumeration failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def phase5_calculate_migration_costs(self, use_sampling=True, sampling_high=False):
        """Phase 5: Migration cost calculation"""
        self.print_header("Migration cost calculation", 5)
        phase_start = time.time()
        
        # Check that the migration plan file exists
        plans_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_plans.json"

        if not plans_file.exists():
            self.print_error("Migration plans not found")
            self.print_info("Run phase 4 first")
            return False

        try:
            # Select the Calculator to use
            if use_sampling:
                if sampling_high:
                    from migration.sampling_migration_cost_calculator_high import SamplingMigrationCostCalculator
                    self.print_info("Estimating sizes using sampling (high sampling rate)")
                else:
                    from migration.sampling_migration_cost_calculator import SamplingMigrationCostCalculator
                    self.print_info("Estimating sizes using sampling (low sampling rate)")
                CalculatorClass = SamplingMigrationCostCalculator
            else:
                from migration.simple_migration_cost_calculator import SimpleMigrationCostCalculator
                CalculatorClass = SimpleMigrationCostCalculator

            self.print_info("Calculating migration costs...")
            
            # Create the CostCalculator instance
            if self.recalc_mode and use_sampling:
                recalc_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_costs.json"
                # Only SamplingMigrationCostCalculator accepts precomputed_costs_file
                calculator = CalculatorClass(
                    settings=self.settings,
                    query_set=self.query_set,
                    precomputed_costs_file=str(recalc_file),
                    exp_dir=self.exp_dir
                )
            else:
                calculator = CalculatorClass(
                    settings=self.settings,
                    query_set=self.query_set,
                    exp_dir=self.exp_dir
                )
            
            # Calculate and save the costs
            costs = calculator.calculate_all_costs()
            
            # Check the output file path (every Calculator saves to simple_migration_costs.json)
            output_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_costs.json"
            
            if output_file.exists():
                self.print_success(f"Saved migration costs: {output_file}")
                self.print_info(f"  {len(costs)} node costs calculated")
            else:
                # Even if the file is not found, one could treat it as success if the calculation itself finished normally,
                # but the goal is basically to produce the file
                self.print_warning("Migration cost file not found (the save step may have been skipped)")

            if output_file.exists():
                self._write_preprocessing_meta(
                    "cost_estimation",
                    calculator=f"{CalculatorClass.__module__}.{CalculatorClass.__name__}",
                    use_sampling=bool(use_sampling),
                    sampling_rate=("high" if sampling_high else "low") if use_sampling else None,
                    precomputed_costs=bool(self.recalc_mode and use_sampling),
                )

            # Record the phase time
            self.phase_times['phase5_migration_costs'] = time.time() - phase_start
            
            return True
            
        except Exception as e:
            self.print_error(f"Migration cost calculation failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        
    def phase5_5_recalculate_costs(self):
        """Phase 5.5: recalculate the MV costs with the node structure of the parsed plans.

        Runs scripts/recalculate_costs.py on 04_migration/<set>/simple_migration_costs.json
        (overwriting it), as done after Phase 5 for all experiments of the paper. The
        experiments then use the recalculated costs via --recalc.
        """
        self.print_header("Cost recalculation (recalculate_costs.py)", 5.5)
        phase_start = time.time()

        costs_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_costs.json"
        if not self.pickle_path.exists():
            self.print_error(f"{self.pickle_path} not found (run Phase 2 first)")
            return False
        if not costs_file.exists():
            self.print_error(f"{costs_file} not found (run Phase 5 first)")
            return False

        try:
            from scripts.recalculate_costs import recalculate_costs

            recalculate_costs(self.pickle_path, costs_file, costs_file)
            self._write_preprocessing_meta("cost_recalculation", method="pickle_recursive_v2",
                                           script="scripts/recalculate_costs.py")
            self.phase_times['phase5_5_cost_recalculation'] = time.time() - phase_start
            self.print_success(f"Recalculated costs saved to {costs_file}")
            return True
        except Exception as e:
            self.print_error(f"Cost recalculation failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def phase6_optimize(self, mode='dynamic', use_pruning=False, pruning_parallel=False, pruning_workers=None, static_timestep='last', use_static_protection=False, static_algorithm='normal', b_max=None, inherit_parent_constraints=True):
        """Phase 6: MV optimization

        Args:
            mode: 'static', 'dynamic', or 'adaptive' (default: 'dynamic')
            use_pruning: Whether to use pruning (default: False)
            pruning_parallel: Whether to run pruning in parallel (default: False)
            pruning_workers: Number of workers for parallel execution (default: number of CPU cores)
            static_timestep: Time step used by static optimization ('first' or 'last')
            use_static_protection: Protect the static-optimization MVs as a sanctuary (default: False)
            static_algorithm: Static optimization algorithm ('normal', 'bigsubs', 'both')
            inherit_parent_constraints: Propagate boundary constraints from parent nodes in the WST (default: True)
        """
        # First branch on the mode
        if mode == 'static':
            return self.phase6b_optimize_static(timestep_position=static_timestep, static_algorithm=static_algorithm, b_max=b_max)
        elif mode == 'adaptive':
            return self.phase6c_optimize_adaptive(window_size=self.window_size, b_max=b_max)
        elif mode == 'peloton':
            return self.phase6c_optimize_adaptive(b_max=b_max, lookahead=True)
        
        # The rest handles dynamic mode
        self.print_header("ILP optimization (time-dependent)", 6)
        
        if not self.pickle_path.exists():
            self.print_error(f"{self.pickle_path} not found")
            self.print_info("Run phase 2 first")
            return False
        
        if self.qp is None:
            self.print_info(f"Loading parse results: {self.pickle_path}")
            try:
                with open(self.pickle_path, 'rb') as f:
                    self.qp = pickle.load(f)
                self.print_success(f"Loaded {self.qp.s_num} nodes")
            except Exception as e:
                self.print_error(f"Failed to load parse results: {e}")
                return False
        
        self.print_info("Running time-dependent optimization (considering migration costs)")
        if use_pruning:
            mode_str = "parallel" if pruning_parallel else "sequential"
            self.print_info(f"  Using pruning ({mode_str} execution)")
            if use_static_protection:
                self.print_info(f"  Static protection: enabled (hybrid approach)")
            self.print_info(f"  WST parent-constraint propagation: {'enabled' if inherit_parent_constraints else 'disabled'}")
            if pruning_parallel:
                import multiprocessing
                workers = pruning_workers or multiprocessing.cpu_count()
                self.print_info(f"  Number of workers: {workers}")
        
        # Start timing the phase
        phase_start = time.time()
        
        try:
            from core.io_loaders import (
                load_timesteps_and_frequencies,
                load_full_build_costs_and_sizes,
            )
            from core.time_dependent_optimizer import TimeDependentOptimizer
            
            # Storage budget
            B_max = float((b_max if b_max is not None else 100) * 1024 * 1024)
            
            # Load time steps and frequencies
            self.print_info("Loading time steps and frequency information...")
            timesteps, frequencies = load_timesteps_and_frequencies(str(self.exp_dir), self.query_set, freq_suffix=self.exp_suffix)
            self.print_success(f"  Number of time steps: {len(timesteps)}")
            
            # Validate/adjust the frequency dimensions
            query_count = len(self.qp.u_ij)
            for ts in timesteps:
                if len(frequencies[ts]) != query_count:
                    self.print_info(f"  Adjusted frequency count: {ts} ({len(frequencies[ts])} -> {query_count})")
                    if len(frequencies[ts]) < query_count:
                        frequencies[ts].extend([1.0] * (query_count - len(frequencies[ts])))
                    else:
                        frequencies[ts] = frequencies[ts][:query_count]
            
            # Get migration costs from subquery_costs (same scale as u_ij)
            # self.print_info("Calculating migration costs...")
            # migration_cost = {
            #     j: self.qp.qm.subquery_costs[node_id]
            #     for j, node_id in enumerate(self.qp.node_list)
            # }
            
            # In --recalc mode, overwrite u_ij with the loaded costs and use those costs
            migration_cost, b_j_from_migration = self._update_u_ij_if_recalc()
            
            if migration_cost is None:
                # Normal mode: load sizes and costs
                migration_cost, _, b_j_from_migration = load_full_build_costs_and_sizes(
                    str(self.exp_dir), 
                    self.qp.node_list, 
                    self.query_set
                )
                self.print_success(f"  {len(migration_cost)} MV migration costs computed (based on subquery_costs)")

            # Run pruning (optional)
            pruning_info = None
            candidate_filter = None
            if use_pruning:
                from core.cf_pruner import CFPruner
                
                self.print_info("Running CF Pruning...")
                pruning_start = time.time()
                
                pruner = CFPruner(
                    node_list=self.qp.node_list,
                    u_ij=self.qp.u_ij,
                    X=self.qp.X,
                    b_j=b_j_from_migration,
                    B_max=B_max,
                    timesteps=timesteps,
                    migration_cost=migration_cost,
                    query_frequency_by_timestep=frequencies,
                    gurobi_output=0,  # Keep quiet during pruning
                    use_parallel=pruning_parallel,
                    max_workers=pruning_workers,
                    inherit_parent_constraints=inherit_parent_constraints,
                )
                
                promising_mvs = pruner.prune_candidates(use_static_protection=use_static_protection)
                pruning_time = time.time() - pruning_start
                
                pruning_info = pruner.get_filtering_info(promising_mvs)
                candidate_filter = promising_mvs
                
                self.print_success(
                    f"  Pruning completed ({pruning_time:.2f}s): "
                    f"{pruning_info['promising_candidates']}/{pruning_info['total_candidates']} MVs are promising "
                    f"({pruning_info['reduction_rate']*100:.1f}% reduction)"
                )
                # NOTE: pruning_info is saved later as enhanced_result['pruning_info']
                # in td_mv_optimization_result, so it is not written to a separate file.

            # Initialize the optimizer
            self.print_info("Initializing the optimizer...")
            optimizer = TimeDependentOptimizer(
                node_list=self.qp.node_list,
                u_ij=self.qp.u_ij,
                X=self.qp.X,
                b_j=b_j_from_migration,  # Use sizes from the Phase 5 EXPLAIN results
                B_max=B_max,
                timesteps=timesteps,
                migration_cost=migration_cost,
                query_frequency_by_timestep=frequencies,
                gurobi_output=1,
            )
            
            # Apply the pruning result (candidate filtering)
            if candidate_filter is not None:
                original_cand = optimizer.cand_j.copy()
                optimizer.set_candidates([j for j in optimizer.cand_j if j in candidate_filter])
                self.print_info(
                    f"  Filtered candidates: {len(original_cand)} -> {len(optimizer.cand_j)}"
                )
            
            # Run the optimization
            self.print_info("Running optimization...")
            result = optimizer.optimize()
            
            # Migration analysis
            self.print_info("Running migration analysis...")
            enhanced_result = self._analyze_migration_transitions(result, migration_cost, b_j_from_migration, B_max)
            
            # Add pruning information to the result
            if pruning_info:
                enhanced_result['pruning_info'] = pruning_info
                enhanced_result['pruning_time_sec'] = pruning_time
            
            # Record the phase time
            phase_time = time.time() - phase_start
            self.phase_times['phase6_optimization'] = phase_time
            enhanced_result['phase_time_sec'] = phase_time
            
            # Show the results
            self.print_success("Optimization completed")
            self.print_info(f"  Total objective value: {enhanced_result['objective']:.4f}")
            self.print_info(f"  Workload cost: {enhanced_result['workload_cost']:.4f}")
            self.print_info(f"  Migration cost: {enhanced_result['migration_cost']:.4f}")
            self.print_info(f"  ILP solve time: {enhanced_result['solve_time_sec']:.2f} s")
            if pruning_info:
                self.print_info(f"  Pruning time: {pruning_time:.2f} s")
            self.print_info(f"  Total phase execution time: {phase_time:.2f} s")
            
            # Save the results (same directory structure as run_time_dependent_with_migration.py)
            # z_by_timestep and y_by_timestep are not needed from Phase 7 on, so exclude them to reduce file size
            result_to_save = {k: v for k, v in enhanced_result.items() 
                            if k not in ('z_by_timestep', 'y_by_timestep')}
            
            result_dir = self.exp_dir / "time_dependent_output" / self.query_set
            result_dir.mkdir(parents=True, exist_ok=True)
            result_file = result_dir / f"td_mv_optimization_result{self.exp_suffix}.json"
            import multiprocessing
            result_to_save["run_config"] = self._run_config(
                "6",
                optimization_mode="dynamic",
                b_max_mb=b_max if b_max is not None else 100,
                b_max_bytes=B_max,
                recalc=self.recalc_mode,
                use_pruning=use_pruning,
                pruning_parallel=pruning_parallel if use_pruning else None,
                pruning_workers=((pruning_workers or multiprocessing.cpu_count())
                                 if use_pruning and pruning_parallel else None),
                inherit_parent_constraints=inherit_parent_constraints if use_pruning else None,
                static_protection=use_static_protection if use_pruning else None,
            )
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result_to_save, f, indent=2, ensure_ascii=False)
            self.print_success(f"Saved results to {result_file}")
            
            # Store the results in an instance variable (used by later phases)
            self.result = enhanced_result
            
            return True

        except Exception as e:
            self.print_error(f"Optimization failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _analyze_migration_transitions(self, result: dict, migration_cost: dict, b_j: list, B_max: float) -> dict:
        """Analyze migration transitions
        
        Args:
            result: Optimization result
            migration_cost: Migration cost (full build)
            b_j: List of MV sizes (from the Phase 5 EXPLAIN results)
            B_max: Storage budget
        """
        timesteps = result["timesteps"]
        z_by_timestep = result["z_by_timestep"]
        
        migration_analysis = []
        
        for t in range(len(timesteps)):
            timestep_name = timesteps[t]
            current_mvs = set(j for j, v in enumerate(z_by_timestep[t]) if v == 1)
            
            # Per-time-step information
            selected_nodes = [self.qp.node_list[j] for j in sorted(current_mvs)]
            total_size = sum(b_j[j] for j in current_mvs)  # Use the correct b_j
            utilization = (total_size / B_max * 100) if B_max > 0 else 0
            
            timestep_info = {
                "timestep": timestep_name,
                "selected_mvs": selected_nodes,
                "mv_count": len(current_mvs),
                "total_size": round(total_size, 2),
                "storage_budget": round(B_max, 2),
                "utilization_percent": round(utilization, 2)
            }
            
            # Migration information (when t > 0)
            if t > 0:
                prev_mvs = set(j for j, v in enumerate(z_by_timestep[t-1]) if v == 1)
                
                maintained = current_mvs & prev_mvs
                created = current_mvs - prev_mvs
                deleted = prev_mvs - current_mvs
                
                migration_details = {
                    "from_timestep": timesteps[t-1],
                    "to_timestep": timestep_name,
                    "maintained": {
                        "count": len(maintained),
                        "mvs": [self.qp.node_list[j] for j in sorted(maintained)],
                        "total_size": round(sum(b_j[j] for j in maintained), 2)  # Use the correct b_j
                    },
                    "created": {
                        "count": len(created),
                        "mvs": [self.qp.node_list[j] for j in sorted(created)],
                        "total_size": round(sum(b_j[j] for j in created), 2)  # Use the correct b_j
                    },
                    "deleted": {
                        "count": len(deleted),
                        "mvs": [self.qp.node_list[j] for j in sorted(deleted)],
                        "total_size": round(sum(b_j[j] for j in deleted), 2)  # Use the correct b_j
                    }
                }
                
                # Compute the creation cost
                creation_cost = 0.0
                creation_details = []
                
                for j in sorted(created):
                    cost = migration_cost.get(j, float("inf"))
                    creation_cost += cost
                    creation_details.append({
                        "mv": self.qp.node_list[j],
                        "size": round(b_j[j], 2),
                        "cost": round(cost, 2),
                        "dependencies": [] # Dependencies left empty for simplicity (full build)
                    })
                
                migration_details["creation_cost"] = round(creation_cost, 2)
                migration_details["creation_details"] = creation_details
                
                timestep_info["migration"] = migration_details
            else:
                # Initial time step
                initial_cost = 0.0
                creation_details = []
                
                for j in sorted(current_mvs):
                    cost = migration_cost.get(j, 0.0)
                    initial_cost += cost
                    creation_details.append({
                        "mv": self.qp.node_list[j],
                        "size": round(b_j[j], 2),
                        "cost": round(cost, 2),
                        "dependencies": []
                    })
                
                timestep_info["initial_creation"] = {
                    "total_cost": round(initial_cost, 2),
                    "creation_details": creation_details
                }
            
            migration_analysis.append(timestep_info)
        
        # Build the extended result
        enhanced = result.copy()
        enhanced["migration_analysis"] = migration_analysis
        
        # Add summary statistics
        total_created = sum(
            len(ma.get("migration", {}).get("created", {}).get("mvs", []))
            for ma in migration_analysis if "migration" in ma
        )
        total_deleted = sum(
            len(ma.get("migration", {}).get("deleted", {}).get("mvs", []))
            for ma in migration_analysis if "migration" in ma
        )
        total_maintained = sum(
            len(ma.get("migration", {}).get("maintained", {}).get("mvs", []))
            for ma in migration_analysis if "migration" in ma
        )
        
        enhanced["summary"] = {
            "total_timesteps": len(timesteps),
            "total_mvs_created": total_created + len(migration_analysis[0].get("initial_creation", {}).get("creation_details", [])),
            "total_mvs_deleted": total_deleted,
            "total_transitions_maintained": total_maintained,
            "avg_mvs_per_timestep": round(sum(ma["mv_count"] for ma in migration_analysis) / len(migration_analysis), 2),
            "avg_storage_utilization": round(sum(ma["utilization_percent"] for ma in migration_analysis) / len(migration_analysis), 2)
        }
        
        return enhanced
    
    def phase6b_optimize_static(self, timestep_position='last', static_algorithm='normal', b_max=None):
        """Phase 6b: Static optimization (not time-dependent; a single time step only)
        
        Args:
            timestep_position: Time step to use
                'first': first, 'last': last, 'average': average over all time steps,
                'addmv': weighted by the frequency sum + considering MV creation cost
            static_algorithm: Algorithm to use ('normal': regular ILP, 'bigsubs': BigSubs, 'both': both)
        """
        if timestep_position == 'first':
            position_name = "first"
        elif timestep_position == 'average':
            position_name = "average over all time steps"
        elif timestep_position == 'addmv':
            position_name = "frequency sum + MV creation cost"
        else:
            position_name = "last"
        self.print_header(f"Static optimization (time step: {position_name})", 6.5)
        
        if not self.pickle_path.exists():
            self.print_error(f"{self.pickle_path} not found")
            return False
            
        if self.qp is None:
            self.print_info(f"Loading parse results: {self.pickle_path}")
            try:
                with open(self.pickle_path, 'rb') as f:
                    self.qp = pickle.load(f)
            except Exception as e:
                self.print_error(f"Failed to load parse results: {e}")
                return False

        self.print_info("Running static optimization (workload of the initial time step only)")
        phase_start = time.time()
        
        try:
            from core.io_loaders import (
                load_timesteps_and_frequencies,
                load_full_build_costs_and_sizes,
            )
            from src.optimization.normal import NormalOptimizer
            
            # Storage budget
            B_max = float((b_max if b_max is not None else 100) * 1024 * 1024)
            
            # Load time steps and frequencies
            timesteps, frequencies = load_timesteps_and_frequencies(str(self.exp_dir), self.query_set, freq_suffix=self.exp_suffix)
            
            if not timesteps:
                self.print_error("No time step information")
                return False
                
            # Select the time step
            if timestep_position == 'first':
                selected_timestep = timesteps[0]
                selected_frequencies = frequencies[selected_timestep]
                self.print_info(f"Time step used: {selected_timestep} (first)")
            elif timestep_position == 'average':
                # Compute the frequency sum over all time steps (the sum for normal/bigsubs; averaged later for utility)
                selected_timestep = "average"
                self.print_info(f"Time step used: frequency average/sum over all time steps")
                
                # For each query, compute the sum of frequencies over all time steps
                query_count = len(self.qp.u_ij)
                selected_frequencies = [0.0] * query_count
                
                for timestep in timesteps:
                    timestep_freq = frequencies[timestep]
                    # Adjust the frequency dimensions
                    if len(timestep_freq) < query_count:
                        timestep_freq = timestep_freq + [1.0] * (query_count - len(timestep_freq))
                    else:
                        timestep_freq = timestep_freq[:query_count]
                    
                    # Accumulate
                    for i in range(query_count):
                        selected_frequencies[i] += timestep_freq[i]
                
                num_timesteps = len(timesteps)
                if static_algorithm == 'utility':
                    for i in range(query_count):
                        selected_frequencies[i] /= num_timesteps
                    self.print_info(f"  {num_timesteps} time steps: frequencies averaged (for Utility)")
                else:
                    self.print_info(f"  {num_timesteps} time steps: frequencies summed")
            elif timestep_position == 'addmv':
                # Weight by the frequency sum (to match the scale of the MV creation cost)
                selected_timestep = "addmv"
                self.print_info(f"Time step used: frequency sum + considering MV creation cost")
                
                # For each query, compute the sum of frequencies over all time steps (not the average)
                query_count = len(self.qp.u_ij)
                selected_frequencies = [0.0] * query_count
                
                for timestep in timesteps:
                    timestep_freq = frequencies[timestep]
                    # Adjust the frequency dimensions
                    if len(timestep_freq) < query_count:
                        timestep_freq = timestep_freq + [1.0] * (query_count - len(timestep_freq))
                    else:
                        timestep_freq = timestep_freq[:query_count]
                    
                    # Accumulate (no averaging)
                    for i in range(query_count):
                        selected_frequencies[i] += timestep_freq[i]
                
                self.print_info(f"  {len(timesteps)} time steps: frequencies summed")
            else:  # 'last'
                selected_timestep = timesteps[-1]
                selected_frequencies = frequencies[selected_timestep]
                self.print_info(f"Time step used: {selected_timestep} (last)")
            
            # Adjust the frequency dimensions (already done for average/addmv)
            query_count = len(self.qp.u_ij)
            if timestep_position not in ('average', 'addmv'):
                if len(selected_frequencies) < query_count:
                    selected_frequencies.extend([1.0] * (query_count - len(selected_frequencies)))
                else:
                    selected_frequencies = selected_frequencies[:query_count]
                
            # In --recalc mode, update u_ij and get the costs
            recalc_migration_cost, _ = self._update_u_ij_if_recalc()

            # Compute the weighted utility (u_ij * frequency)
            if isinstance(self.qp.u_ij, SparseMatrix):
                # Sparse: weight only the non-zeros by frequency and keep them as a SparseMatrix
                wrows = {}
                for i, row in self.qp.u_ij.rows.items():
                    freq = selected_frequencies[i]
                    if freq:
                        wrows[i] = {j: v * freq for j, v in row.items()}
                weighted_u_ij = SparseMatrix(wrows, self.qp.u_ij.I, self.qp.u_ij.J)
            else:
                weighted_u_ij = []
                for i in range(len(self.qp.u_ij)):
                    freq = selected_frequencies[i]
                    weighted_row = [u * freq for u in self.qp.u_ij[i]]
                    weighted_u_ij.append(weighted_row)
            
            # Load size data (creation_costs is not needed because the MV creation cost uses subquery_costs)
            _, _, b_j_from_migration = load_full_build_costs_and_sizes(
                str(self.exp_dir), 
                self.qp.node_list, 
                self.query_set
            )
            
            # Set m_cost to 0 (migration costs are not considered)
            m_cost = [0.0] * len(self.qp.node_list)
            
            # In addmv mode, use the MV creation cost as index_build_costs
            # Use subquery_costs as in dynamic optimization (same scale as u_ij)
            if timestep_position == 'addmv':
                if self.recalc_mode and recalc_migration_cost is not None:
                     # Recalc mode: use the recalculated costs
                    index_build_costs = [
                        recalc_migration_cost.get(j, float('inf'))
                        for j in range(len(self.qp.node_list))
                    ]
                    self.print_info(f"  Including MV creation cost in the objective (based on Recalc costs)")
                else:
                    # Normal mode: use subquery_costs
                    index_build_costs = [
                        self.qp.qm.subquery_costs[node_id]
                        for node_id in self.qp.node_list
                    ]
                    self.print_info(f"  Including MV creation cost in the objective (based on subquery_costs)")
                
                total_creation_cost = sum(val for val in index_build_costs if val != float('inf'))
                self.print_info(f"  Upper bound of total MV creation cost: {total_creation_cost:.4f}")
            else:
                index_build_costs = None  # Default (creation cost not considered)
            
            # Variables for storing the results
            result_dir = self.exp_dir / "time_dependent_output" / self.query_set
            result_dir.mkdir(parents=True, exist_ok=True)
            
            # Run NormalOptimizer (normal or both)
            if static_algorithm in ('normal', 'both'):
                self.print_info(f"Running optimization with NormalOptimizer...")
                
                optimizer = NormalOptimizer(
                    qm=self.qp.qm,
                    s_num=len(self.qp.node_list),
                    m_cost=m_cost,
                    node_list=self.qp.node_list,
                    B_max=B_max,
                    b_j=b_j_from_migration,
                    u_ij=weighted_u_ij,
                    X=self.qp.X,
                    q_s_list=[],
                    settings=self.settings,
                    index_build_costs=index_build_costs  # Pass the MV creation cost in addmv mode
                )
                
                result = optimizer.optimize()
                
                # Format the result
                selected_mvs = [mv.node_id for mv in result.selected_views]
                selected_indices = [self.qp.node_list.index(mv.node_id) for mv in result.selected_views]
                total_size = result.total_storage
                
                # Change the algorithm name in addmv mode
                algorithm_name = "static_normal_with_creation_cost" if timestep_position == 'addmv' else "static_normal"
                
                static_result = {
                    "algorithm": algorithm_name,
                    "timestep": selected_timestep,
                    "selected_mvs": selected_mvs,
                    "mv_count": len(selected_mvs),
                    "total_size": total_size,
                    "storage_budget": B_max,
                    "utilization_percent": (total_size / B_max * 100) if B_max > 0 else 0,
                    "objective_value": result.total_utility,
                    "execution_time": result.execution_time,
                    "considers_creation_cost": timestep_position == 'addmv'
                }
                
                # In addmv mode, compute the utility and the MV creation cost separately
                if timestep_position == 'addmv' and index_build_costs is not None:
                    # Compute the total utility of the selected MVs (only pairs with y_ij=1)
                    # y_ij is taken from the Gurobi optimization result
                    y_ij = result.metadata.get("y_ij", [[0] * len(self.qp.node_list) for _ in range(len(weighted_u_ij))])
                    total_utility_gain = 0.0
                    for i in range(len(weighted_u_ij)):
                        for j in selected_indices:
                            if y_ij[i][j] == 1:  # Only when actually used
                                total_utility_gain += weighted_u_ij[i][j]
                    
                    # Compute the total initial creation cost of the selected MVs
                    total_creation_cost = sum(index_build_costs[j] for j in selected_indices)
                    
                    static_result["total_utility_gain"] = total_utility_gain
                    static_result["total_creation_cost"] = total_creation_cost
                    
                    self.print_success("NormalOptimizer completed")
                    self.print_info(f"  Number of selected MVs: {len(selected_mvs)}")
                    self.print_info(f"  Storage used: {total_size / 1024 / 1024:.2f} MB")
                    self.print_info(f"  Total utility: {total_utility_gain:.4f}")
                    self.print_info(f"  Total initial MV creation cost: {total_creation_cost:.4f}")
                    self.print_info(f"  Objective value (utility - creation cost): {result.total_utility:.4f}")
                else:
                    self.print_success("NormalOptimizer completed")
                    self.print_info(f"  Number of selected MVs: {len(selected_mvs)}")
                    self.print_info(f"  Storage used: {total_size / 1024 / 1024:.2f} MB")
                
                # Save the result
                result_file = result_dir / f"static_mv_optimization_result{self.exp_suffix}.json"
                static_result["run_config"] = self._run_config("6", optimization_mode="static", static_algorithm="normal", static_timestep=timestep_position, b_max_mb=b_max if b_max is not None else 100, b_max_bytes=B_max, recalc=self.recalc_mode)
                with open(result_file, 'w', encoding='utf-8') as f:
                    json.dump(static_result, f, indent=2, ensure_ascii=False)
                self.print_success(f"Saved NormalOptimizer result to {result_file}")
            
            # Run utility
            if static_algorithm == 'utility':
                from core.utility_v2 import UtilityOptimizerV2
                
                self.print_info(f"Running optimization with UtilityOptimizerV2...")
                
                utility_optimizer = UtilityOptimizerV2(
                    qm=self.qp.qm,
                    s_num=len(self.qp.node_list),
                    m_cost=m_cost,
                    node_list=self.qp.node_list,
                    B_max=B_max,
                    b_j=b_j_from_migration,
                    u_ij=weighted_u_ij,
                    X=self.qp.X,
                    q_s_list=self.qp.q_s_list,
                    settings=self.settings
                )
                
                utility_result = utility_optimizer.optimize()
                
                # Format the result
                # For UtilityOptimizerV2 the result is a dict and some keys may differ;
                # handle it depending on whether an OptimizationResult object or a dict is returned (here we assume BaseILPOptimizer.create_result returns a dict)
                if isinstance(utility_result, dict):
                    utility_selected_mvs = utility_result.get("selected_mvs_t1", utility_result.get("materialized_nodes", []))
                    utility_total_size = utility_result.get("storage_used", 0)
                    utility_objective = utility_result.get("objective_value", 0)
                    utility_execution_time = utility_result.get("execution_time", 0)
                else:
                    utility_selected_mvs = [mv.node_id for mv in utility_result.selected_views]
                    utility_total_size = utility_result.total_storage
                    utility_objective = utility_result.total_utility
                    utility_execution_time = utility_result.execution_time
                
                utility_static_result = {
                    "algorithm": "static_utility",
                    "timestep": selected_timestep,
                    "selected_mvs": utility_selected_mvs,
                    "mv_count": len(utility_selected_mvs),
                    "total_size": utility_total_size,
                    "storage_budget": B_max,
                    "utilization_percent": (utility_total_size / B_max * 100) if B_max > 0 else 0,
                    "objective_value": utility_objective,
                    "execution_time": utility_execution_time
                }
                
                self.print_success("UtilityOptimizerV2 completed")
                self.print_info(f"  Number of selected MVs: {len(utility_selected_mvs)}")
                self.print_info(f"  Storage used: {utility_total_size / 1024 / 1024:.2f} MB")
                
                # Save the result (whether to overwrite as in average mode or use a separate name; here it follows the average format as specified)
                utility_result_file = result_dir / f"static_mv_optimization_result{self.exp_suffix}.json"
                utility_static_result["run_config"] = self._run_config("6", optimization_mode="static", static_algorithm="utility", static_timestep=timestep_position, b_max_mb=b_max if b_max is not None else 100, b_max_bytes=B_max, recalc=self.recalc_mode)
                with open(utility_result_file, 'w', encoding='utf-8') as f:
                    json.dump(utility_static_result, f, indent=2, ensure_ascii=False)
                self.print_success(f"Saved UtilityOptimizerV2 result to {utility_result_file}")

            # Run BigSubsOptimizer (bigsubs or both)
            if static_algorithm in ('bigsubs', 'both'):
                from src.optimization.bigsubs import BigSubsOptimizer
                
                self.print_info(f"Running optimization with BigSubsOptimizer...")
                
                # Compute U_j_max and U_max from weighted_u_ij
                # Following the original BigSubs, use sum instead of max
                # NOTE: BigSubs recomputes U_j_max/U_max/y_ij internally, so in the sparse case
                #       the dense O(I*J) construction (a huge I*J array) is skipped entirely.
                if isinstance(weighted_u_ij, SparseMatrix):
                    weighted_U_j_max = None
                    weighted_U_max = None
                    initial_y_ij = None
                else:
                    weighted_U_j_max = [
                        sum((weighted_u_ij[i][j] for i in range(len(weighted_u_ij))))
                        for j in range(len(self.qp.node_list))
                    ]
                    weighted_U_max = sum(weighted_U_j_max)
                    # y_ij is taken from the query parser (as in the original static experiment)
                    initial_y_ij = self.qp.y_ij if hasattr(self.qp, 'y_ij') else [[0] * len(self.qp.node_list) for _ in range(len(weighted_u_ij))]
                
                bigsubs_optimizer = BigSubsOptimizer(
                    qm=self.qp.qm,
                    s_num=len(self.qp.node_list),
                    m_cost=m_cost,
                    node_list=self.qp.node_list,
                    B_max=B_max,
                    b_j=b_j_from_migration,
                    u_ij=weighted_u_ij,
                    X=self.qp.X,
                    q_s_list=self.qp.q_s_list,
                    settings=self.settings,
                    U_j_max=weighted_U_j_max,
                    U_max=weighted_U_max,
                    y_ij=initial_y_ij
                )
                
                bigsubs_result = bigsubs_optimizer.optimize(iter_max=200)
                
                # Format the result
                bigsubs_selected_mvs = [mv.node_id for mv in bigsubs_result.selected_views]
                bigsubs_total_size = bigsubs_result.total_storage
                
                bigsubs_static_result = {
                    "algorithm": "static_bigsubs",
                    "timestep": selected_timestep,
                    "selected_mvs": bigsubs_selected_mvs,
                    "mv_count": len(bigsubs_selected_mvs),
                    "total_size": bigsubs_total_size,
                    "storage_budget": B_max,
                    "utilization_percent": (bigsubs_total_size / B_max * 100) if B_max > 0 else 0,
                    "objective_value": bigsubs_result.total_utility,
                    "execution_time": bigsubs_result.execution_time,
                    "iterations": bigsubs_result.metadata.get('iterations'),
                    "convergence_summary": bigsubs_result.metadata.get('convergence_summary', {})
                }
                
                self.print_success("BigSubsOptimizer completed")
                self.print_info(f"  Number of selected MVs: {len(bigsubs_selected_mvs)}")
                self.print_info(f"  Storage used: {bigsubs_total_size / 1024 / 1024:.2f} MB")
                
                # Save the result (file name for BigSubs)
                bigsubs_result_file = result_dir / f"static_bigsubs_optimization_result{self.exp_suffix}.json"
                bigsubs_static_result["run_config"] = self._run_config("6", optimization_mode="static", static_algorithm="bigsubs", static_timestep=timestep_position, b_max_mb=b_max if b_max is not None else 100, b_max_bytes=B_max, recalc=self.recalc_mode)
                with open(bigsubs_result_file, 'w', encoding='utf-8') as f:
                    json.dump(bigsubs_static_result, f, indent=2, ensure_ascii=False)
                self.print_success(f"Saved BigSubsOptimizer result to {bigsubs_result_file}")
            
            # SQL generation has moved to Phase 7
            self.phase_times['phase6b_static_optimization'] = time.time() - phase_start
            return True
            
        except Exception as e:
            self.print_error(f"Static optimization failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def phase6c_optimize_adaptive(self, window_size: Optional[int] = None, b_max=None, lookahead: bool = False):
        """Phase 6c: Adaptive MV optimization (sliding-window scheme) / Peloton (one-step lookahead)

        Sequential optimization using a two-time-step ILP.
        - Initial MVs: built from the empty set with the time-0 frequencies (Option B)
        - Each step: fix the current MVs and optimize the next MVs

        Args:
            window_size: Moving-average window width (uses self.window_size if None). Unused with lookahead.
            lookahead: If True, Peloton mode. Instead of a window, the "actual frequencies of the next time step"
                       are used directly as curr_freq (perfect one-step foresight). False is the conventional adaptive mode
                       (weighted moving average over the past window_size time steps; reactive).

        The output format has the same structure as dynamic optimization.
        """
        if window_size is None:
            window_size = self.window_size
        
        self.print_header("ILP optimization (adaptive)", 6)
        
        if not self.pickle_path.exists():
            self.print_error(f"{self.pickle_path} not found")
            self.print_info("Run phase 2 first")
            return False
        
        if self.qp is None:
            self.print_info(f"Loading parse results: {self.pickle_path}")
            try:
                with open(self.pickle_path, 'rb') as f:
                    self.qp = pickle.load(f)
                self.print_success(f"Loaded {self.qp.s_num} nodes")
            except Exception as e:
                self.print_error(f"Failed to load parse results: {e}")
                return False
        
        self.print_info("Running adaptive optimization (sliding-window scheme)")
        
        # Start timing the phase
        phase_start = time.time()
        
        try:
            from core.io_loaders import (
                load_timesteps_and_frequencies,
                load_full_build_costs_and_sizes,
            )
            from core.two_step_optimizer import TwoStepOptimizer
            from core.time_dependent_optimizer import TimeDependentOptimizer
            
            # Storage budget
            B_max = float((b_max if b_max is not None else 100) * 1024 * 1024)
            
            # Load time steps and frequencies
            self.print_info("Loading time steps and frequency information...")
            timesteps, frequencies = load_timesteps_and_frequencies(str(self.exp_dir), self.query_set, freq_suffix=self.exp_suffix)
            self.print_success(f"  Number of time steps: {len(timesteps)}")
            
            # Validate/adjust the frequency dimensions
            query_count = len(self.qp.u_ij)
            for ts in timesteps:
                if len(frequencies[ts]) != query_count:
                    if len(frequencies[ts]) < query_count:
                        frequencies[ts].extend([1.0] * (query_count - len(frequencies[ts])))
                    else:
                        frequencies[ts] = frequencies[ts][:query_count]
            
            # Load migration costs and sizes
            migration_cost, b_j_from_migration = self._update_u_ij_if_recalc()
            
            if migration_cost is None:
                migration_cost, _, b_j_from_migration = load_full_build_costs_and_sizes(
                    str(self.exp_dir), 
                    self.qp.node_list, 
                    self.query_set
                )
                self.print_success(f"  {len(migration_cost)} MV migration costs computed")
            
            b_j = b_j_from_migration
            
            # Get the frequencies of the first time step
            self.print_info("Using the frequencies of the first time step...")
            initial_freq = frequencies[timesteps[0]]
            
            # === Initial MV computation (Option B: built from the empty set with actual migration costs) ===
            # Use the same TwoStepOptimizer as each step, fix t=0 to the empty set, and
            # choose the set that maximizes "benefit - build cost" for the time-0 frequencies.
            # This makes the formulation and benefit model of the initial MVs match those of each step, and removes
            # the inconsistency (caused by migration_cost=0) where the number of MVs changed even when frequencies did not.
            self.print_info("Computing initial MVs (Option B: built from the empty set with actual migration costs)...")
            initial_start = time.time()

            initial_optimizer = TwoStepOptimizer(
                node_list=self.qp.node_list,
                u_ij=self.qp.u_ij,
                X=self.qp.X,
                b_j=b_j,
                B_max=B_max,
                prev_freq=initial_freq,   # Effectively irrelevant since t=0 is fixed to empty
                curr_freq=initial_freq,   # Optimize for the time-0 frequencies
                migration_cost=migration_cost,  # Actual costs (not 0)
                fixed_mvs=set(),          # Fix t=0 to "no MVs" -> full build cost
                gurobi_output=0,
            )
            initial_result = initial_optimizer.optimize()
            current_mvs = set(initial_result["selected_mvs_t1"])

            initial_solve_time = time.time() - initial_start
            self.print_success(f"  Initial number of MVs: {len(current_mvs)}, computation time: {initial_solve_time:.2f}s")
            
            # === Adaptive optimization at each time step ===
            # Principle of adaptive optimization (uses a simple moving average over the past N time steps):
            # - The views at time t are optimized with the average frequencies of times (t-N+1, ..., t-1, t)
            # - e.g., with window_size=4, the views at time 5 are optimized with the average frequencies of times 2,3,4,5
            # - If there are not enough time steps, the first time step is extended (repeated)
            if lookahead:
                self.print_info("Starting Peloton optimization (one-step lookahead: uses the actual frequencies of the next time step, no window)...")
            else:
                _decay_desc = "linear decay (DeepSea-style)" if self.freq_weight == "linear" else "uniform average"
                self.print_info(f"Starting adaptive optimization (past {window_size} time steps, {_decay_desc})...")
            
            z_by_timestep = []
            step_solve_times = []
            migration_analysis = []
            prev_freq = initial_freq
            
            # pending_migration: migration information to be recorded at the next time step
            pending_migration = None
            
            for t, ts_name in enumerate(timesteps):
                self.print_info(f"  Timestep {t}: {ts_name}...")
                step_start = time.time()
                
                # Record the current state
                z_t = [1 if j in current_mvs else 0 for j in range(len(self.qp.node_list))]
                z_by_timestep.append(z_t)
                
                query_count = len(self.qp.u_ij)
                # At the last time step, computing the "next MVs" is pointless (there is nothing to record),
                # so frequency aggregation, the two-time-step ILP and candidate generation are skipped entirely (common to adaptive/peloton).
                is_last = (t + 1 >= len(timesteps))
                next_mvs = set(current_mvs)
                step_elapsed = 0.0

                if not is_last:
                    if lookahead:
                        # Peloton: use the actual frequencies of the next time step directly (no window, perfect foresight)
                        src_freq = frequencies[timesteps[t + 1]]
                        curr_freq = [0.0] * query_count
                        for i in range(query_count):
                            curr_freq[i] = src_freq[i] if i < len(src_freq) else 1.0
                        self.print_info(f"    One-step lookahead: using the actual frequencies of timesteps[{t + 1}]")
                    else:
                        # Take the frequencies of the past N time steps (t-N+1, ..., t-1, t) as the window
                        # freq_window is ordered oldest -> newest (index window_size-1 is the current time t)
                        freq_window = []
                        for offset in range(-window_size + 1, 1):  # -N+1, ..., -1, 0
                            target_idx = t + offset
                            if target_idx < 0:
                                # If there are not enough time steps, extend (repeat) the first time step
                                freq_window.append(frequencies[timesteps[0]])
                            else:
                                freq_window.append(frequencies[timesteps[target_idx]])

                        # Weights of the frequencies within the window (oldest -> newest). uniform=simple moving average, linear=linear recency weights.
                        # Normalize by the sum of weights to keep the frequency scale (required because migration cost vs. benefit is scale-dependent).
                        if self.freq_weight == "linear":
                            weights = [k + 1 for k in range(window_size)]
                        else:  # "uniform"
                            weights = [1 for _ in range(window_size)]
                        wsum = sum(weights)

                        curr_freq = [0.0] * query_count
                        for i in range(query_count):
                            total = sum(weights[k] * freq_window[k][i] for k in range(window_size))
                            curr_freq[i] = total / wsum

                        used_indices = [max(0, t + offset) for offset in range(-window_size + 1, 1)]
                        avg_kind = "linear decay (DeepSea-style)" if self.freq_weight == "linear" else "uniform average"
                        self.print_info(f"    {window_size}-time-step {avg_kind}: timesteps[{used_indices}] used")

                    # Two-time-step ILP (fix the current MVs, optimize the next MVs)
                    step_optimizer = TwoStepOptimizer(
                        node_list=self.qp.node_list,
                        u_ij=self.qp.u_ij,
                        X=self.qp.X,
                        b_j=b_j,
                        B_max=B_max,
                        prev_freq=prev_freq,
                        curr_freq=curr_freq,
                        migration_cost=migration_cost,
                        fixed_mvs=current_mvs,
                        gurobi_output=0,
                    )
                    step_result = step_optimizer.optimize()
                    next_mvs = step_result["selected_mvs_t1"]
                    step_elapsed = time.time() - step_start
                    step_solve_times.append(step_elapsed)
                else:
                    self.print_info("    Last time step, skipping next-MV optimization")
                
                # Record in migration_analysis format
                timestep_info = {
                    "timestep": ts_name,
                    "selected_mvs": [self.qp.node_list[j] for j in sorted(current_mvs)],
                    "mv_count": len(current_mvs),
                    "total_size": sum(b_j[j] for j in current_mvs),
                    "utilization_percent": sum(b_j[j] for j in current_mvs) / B_max * 100 if B_max > 0 else 0,
                    "solve_time_sec": step_elapsed,
                }
                
                if t == 0:
                    # Initial time step: record the creation of the initial MVs
                    initial_cost = sum(migration_cost.get(j, 0.0) for j in current_mvs)
                    timestep_info["initial_creation"] = {
                        "total_cost": round(initial_cost, 2),
                        "creation_details": [
                            {
                                "mv": self.qp.node_list[j],
                                "size": round(b_j[j], 2),
                                "cost": round(migration_cost.get(j, 0.0), 2),
                                "dependencies": []
                            }
                            for j in sorted(current_mvs)
                        ]
                    }
                else:
                    # t>0: record the migration decided by the previous optimization
                    if pending_migration is not None:
                        timestep_info["migration"] = pending_migration
                
                migration_analysis.append(timestep_info)
                
                # Compute the migration information to be recorded at the next time step
                created = next_mvs - current_mvs
                deleted = current_mvs - next_mvs
                maintained = current_mvs & next_mvs
                creation_cost = sum(migration_cost.get(j, 0.0) for j in created)
                
                pending_migration = {
                    "created": {
                        "count": len(created),
                        "mvs": [self.qp.node_list[j] for j in sorted(created)]
                    },
                    "deleted": {
                        "count": len(deleted),
                        "mvs": [self.qp.node_list[j] for j in sorted(deleted)]
                    },
                    "maintained": {
                        "count": len(maintained),
                        "mvs": [self.qp.node_list[j] for j in sorted(maintained)]
                    },
                    "creation_cost": round(creation_cost, 2),
                    "creation_details": [
                        {
                            "mv": self.qp.node_list[j],
                            "size": round(b_j[j], 2),
                            "cost": round(migration_cost.get(j, 0.0), 2),
                            "dependencies": []
                        }
                        for j in sorted(created)
                    ]
                }
                
                # Update the state (skipped at the last step, where curr_freq is undefined and no update is needed)
                if not is_last:
                    prev_freq = curr_freq
                    current_mvs = next_mvs
            
            total_solve_time = time.time() - phase_start
            
            # Total pure optimization time (initial MVs + each step)
            total_optimization_time = initial_solve_time + sum(step_solve_times)
            
            # Build the result in the dynamic-optimization format
            result = {
                "algorithm": "peloton_lookahead" if lookahead else "adaptive_sliding_window",
                "timesteps": timesteps,
                "node_list": self.qp.node_list,
                # "z_by_timestep": z_by_timestep,
                "phase_time_sec": total_solve_time,  # Execution time of the whole phase
                "total_optimization_time_sec": total_optimization_time,  # Total pure optimization time
                "initial_solve_time_sec": initial_solve_time,
                "step_solve_times_sec": step_solve_times,
                "avg_step_time_sec": round(sum(step_solve_times) / len(step_solve_times), 2) if step_solve_times else 0,
                "migration_analysis": migration_analysis,
                "summary": {
                    "total_timesteps": len(timesteps),
                    "total_mvs_created": sum(
                        ma.get("migration", {}).get("created", {}).get("count", 0)
                        for ma in migration_analysis if "migration" in ma
                    ) + len(migration_analysis[0].get("initial_creation", {}).get("creation_details", [])),
                    "total_mvs_deleted": sum(
                        ma.get("migration", {}).get("deleted", {}).get("count", 0)
                        for ma in migration_analysis if "migration" in ma
                    ),
                    "avg_mvs_per_timestep": round(sum(ma["mv_count"] for ma in migration_analysis) / len(migration_analysis), 2),
                    "avg_storage_utilization": round(sum(ma["utilization_percent"] for ma in migration_analysis) / len(migration_analysis), 2)
                }
            }
            
            # Save the result
            result_dir = self.exp_dir / "time_dependent_output" / self.query_set
            result_dir.mkdir(parents=True, exist_ok=True)
            if lookahead:
                result_file = result_dir / f"peloton_mv_optimization_result{self.exp_suffix}.json"
            else:
                result_file = result_dir / f"adaptive_mv_optimization_result_w{window_size}{self.exp_suffix}.json"

            result["run_config"] = self._run_config(
                "6",
                optimization_mode="peloton" if lookahead else "adaptive",
                window_size=None if lookahead else window_size,
                freq_weight=None if lookahead else self.freq_weight,
                b_max_mb=b_max if b_max is not None else 100,
                b_max_bytes=B_max,
                recalc=self.recalc_mode,
            )
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

            self.print_success(f"Saved {'Peloton' if lookahead else 'adaptive'} optimization result to {result_file}")
            
            # Show the summary
            self.print_info(f"\n=== Optimization summary ===")
            self.print_info(f"  Initial MV computation time: {initial_solve_time:.2f}s")
            self.print_info(f"  Total computation time over steps: {sum(step_solve_times):.2f}s")
            self.print_info(f"  Average computation time per step: {sum(step_solve_times)/len(step_solve_times):.2f}s")
            self.print_info(f"  Total pure optimization time: {total_optimization_time:.2f}s")
            self.print_info(f"  Total phase execution time: {total_solve_time:.2f}s")
            self.print_info(f"  Average number of MVs: {result['summary']['avg_mvs_per_timestep']}")
            self.print_info(f"  Total number of MVs created: {result['summary']['total_mvs_created']}")
            self.print_info(f"  Total number of MVs dropped: {result['summary']['total_mvs_deleted']}")
            
            self.phase_times['phase6c_adaptive_optimization'] = total_solve_time
            return True
            
        except Exception as e:
            self.print_error(f"Adaptive optimization failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def phase7_generate_mv_sql(self, mode='dynamic', static_algorithm='normal'):
        """Phase 7: MV creation SQL generation
        
        Args:
            mode: 'static', 'dynamic', or 'adaptive' (default: 'dynamic')
            static_algorithm: Static optimization algorithm ('normal', 'bigsubs', 'both')
        """
        # Static mode: generate SQL from the static optimization result
        if mode == 'static':
            self.print_header("Static MV creation SQL generation", 7)
            phase_start = time.time()
            
            success = self._generate_static_mv_sql(static_algorithm=static_algorithm)
            
            self.phase_times['phase7_static_sql_generation'] = time.time() - phase_start
            if success:
                self.print_info(f"  SQL generation time: {self.phase_times['phase7_static_sql_generation']:.2f} s")
            return success
        
        # Dynamic/Adaptive/Peloton mode: create migration SQL for each time step
        mode_name = {"adaptive": "Adaptive", "peloton": "Peloton"}.get(mode, "Dynamic")
        self.print_header(f"Migration SQL generation ({mode_name})", 7)

        if self.result is None:
            # Load optimization result (adaptive / peloton / dynamic)
            if mode == 'adaptive':
                result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"adaptive_mv_optimization_result_w{self.window_size}{self.exp_suffix}.json"
            elif mode == 'peloton':
                result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"peloton_mv_optimization_result{self.exp_suffix}.json"
            else:
                result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"td_mv_optimization_result{self.exp_suffix}.json"
            
            if not result_file.exists():
                self.print_error(f"Optimization result not found: {result_file}")
                self.print_info("Run phase 6 first")
                return False
            
            with open(result_file, 'r', encoding='utf-8') as f:
                result_data = json.load(f)
                self.result = result_data
        
        # Check if result is from time-dependent optimizer
        if 'migration_analysis' not in self.result:
            self.print_error("Not a time-dependent/adaptive optimization result")
            return False
        
        return self._generate_time_dependent_migration_sql()
    
    def _generate_time_dependent_migration_sql(self):
        """Generate per-time-step migration SQL from the time-dependent optimization result"""
        
        # Start timing the phase
        phase_start = time.time()
        
        try:
            # Load the migration plans
            plans_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_plans.json"
            if not plans_file.exists():
                self.print_error("Migration plans not found")
                self.print_info("Run phase 2.7 first")
                return False
            
            with open(plans_file, 'r', encoding='utf-8') as f:
                migration_plans = json.load(f)
            
            self.print_info(f"Loaded migration plans: {len(migration_plans)} MVs")
            
            # Output directory (same location as the phase 3 optimization results)
            output_dir = self.exp_dir / "time_dependent_output" / self.query_set
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Delete existing migration SQL files
            existing_sql_files = list(output_dir.glob("timestep_*.sql"))
            if existing_sql_files:
                self.print_info(f"Deleting existing migration SQL files: {len(existing_sql_files)}")
                for sql_file in existing_sql_files:
                    sql_file.unlink()
                self.print_success("Deleted existing files")
            
            # Process each time step
            migration_analysis = self.result['migration_analysis']
            timesteps = self.result['timesteps']
            
            self.print_info(f"Number of time steps: {len(timesteps)}")
            
            total_sql_count = 0
            
            for t_idx, timestep_info in enumerate(migration_analysis):
                timestep_name = timestep_info['timestep']
                current_mvs = set(timestep_info.get('selected_mvs', []))
                
                # MVs of the previous time step
                prev_mvs = set()
                if t_idx > 0:
                    prev_mvs = set(migration_analysis[t_idx - 1].get('selected_mvs', []))
                
                # MVs that need to be newly created
                mvs_to_create = current_mvs - prev_mvs
                # MVs that need to be dropped
                mvs_to_drop = prev_mvs - current_mvs
                
                if not mvs_to_create and not mvs_to_drop:
                    self.print_info(f"  Time step '{timestep_name}': no changes (skipped)")
                    continue
                
                # Create the SQL file for each time step
                output_file = output_dir / f"timestep_{t_idx}_{timestep_name}.sql"
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(f"-- =====================================================\n")
                    f.write(f"-- Time step {t_idx}: {timestep_name}\n")
                    f.write(f"-- =====================================================\n\n")
                    f.write(f"\\c {self.settings.database.database}\n\n")
                    
                    # Set the statistics detail level (applies to the whole file)
                    # if mvs_to_create:
                    #     f.write(f"-- Enlarge statistics (statistics_target = 1000)\n")
                    #     f.write(f"SET default_statistics_target = 1000;\n\n")
                    
                    # MVs that need to be dropped
                    if mvs_to_drop:
                        f.write(f"-- MVs to drop: {len(mvs_to_drop)}\n")
                        for mv_id in sorted(mvs_to_drop):
                            f.write(f"DROP MATERIALIZED VIEW IF EXISTS {mv_id} CASCADE;\n")
                        f.write("\n")
                    
                    # MVs that need to be newly created
                    if mvs_to_create:
                        f.write(f"-- MVs to create: {len(mvs_to_create)}\n\n")
                        
                        created_count = 0
                        for mv_id in sorted(mvs_to_create):
                            # Get the appropriate SQL from the migration plans
                            if mv_id not in migration_plans:
                                self.print_info(f"  Warning: migration plan for {mv_id} not found")
                                continue
                            
                            plans = migration_plans[mv_id]
                            
                            # Create from scratch without dependent MVs (the "[]" key)
                            # In the time-dependent case the MVs of the previous time step could also be used for creation,
                            # but simple migration plans only have "[]" (no dependencies), so use that
                            if "[]" in plans:
                                sql = plans["[]"]
                                if sql and sql != "NON_MIGRATE":
                                    f.write(f"-- MV: {mv_id}\n")
                                    f.write(f"{sql}\n")
                                    f.write(f"ANALYZE {mv_id};\n\n")
                                    created_count += 1
                        
                        f.write(f"-- {created_count} MVs created\n\n")
                        # Restore the statistics settings
                        # f.write(f"-- Restore the statistics settings\n")
                        # f.write(f"RESET default_statistics_target;\n")
                
                sql_count = len(mvs_to_create) + len(mvs_to_drop)
                total_sql_count += sql_count
                
                self.print_success(f"  Time step '{timestep_name}': {output_file.name}")
                self.print_info(f"    Create: {len(mvs_to_create)}, drop: {len(mvs_to_drop)}")
            
            # Record the phase time
            self.phase_times['phase7_mv_sql_generation'] = time.time() - phase_start
            
            self.print_success(f"Generated per-time-step migration SQL -> {output_dir}")
            self.print_info(f"  Total number of operations: {total_sql_count}")
            self.print_info(f"  SQL generation time: {self.phase_times['phase7_mv_sql_generation']:.2f} s")
            
            return True
            
        except Exception as e:
            self.print_error(f"SQL generation failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    


    
    
    def _generate_static_mv_sql(self, static_algorithm='normal'):
        """Generate MV creation SQL from the static optimization result
        
        Args:
            static_algorithm: Algorithm to use ('normal' or 'bigsubs')
        """
        try:
            # Load the static optimization result (select the file according to the algorithm)
            if static_algorithm == 'bigsubs':
                result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"static_bigsubs_optimization_result{self.exp_suffix}.json"
                sql_file_name = "static_bigsubs_initial_mvs.sql"
            else:
                result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"static_mv_optimization_result{self.exp_suffix}.json"
                sql_file_name = "static_initial_mvs.sql"
            
            if not result_file.exists():
                self.print_error(f"Static optimization result not found: {result_file}")
                self.print_info("Run phase 6.5 first")
                return False
            
            with open(result_file, 'r', encoding='utf-8') as f:
                static_result = json.load(f)
            
            selected_mvs = static_result.get('selected_mvs', [])
            self.print_info(f"Loaded static optimization result ({static_algorithm}): {len(selected_mvs)} MVs")
            
            # Load the migration plans
            plans_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_plans.json"
            if not plans_file.exists():
                self.print_error(f"Migration plans not found: {plans_file}")
                self.print_info("Run phase 4 first")
                return False
            
            with open(plans_file, 'r', encoding='utf-8') as f:
                migration_plans = json.load(f)
            
            # Generate the SQL statements
            sql_statements = []
            sql_statements.append(f"-- =====================================================")
            sql_statements.append(f"-- Static optimization MV creation SQL ({static_algorithm})")
            sql_statements.append(f"-- Number of selected MVs: {len(selected_mvs)}")
            sql_statements.append(f"-- =====================================================")
            sql_statements.append(f"\\c {self.settings.database.database}")
            sql_statements.append("")
            
            # Set the statistics detail level (applies to the whole file)
            # sql_statements.append(f"-- Enlarge statistics (statistics_target = 1000)")
            # sql_statements.append(f"SET default_statistics_target = 1000;")
            # sql_statements.append("")
            
            created_count = 0
            for node_id in selected_mvs:
                if node_id in migration_plans and "[]" in migration_plans[node_id]:
                    sql = migration_plans[node_id]["[]"]
                    if sql and sql != "NON_MIGRATE":
                        sql_statements.append(f"-- MV: {node_id}")
                        sql_statements.append(sql)
                        sql_statements.append(f"ANALYZE {node_id};")
                        sql_statements.append("")
                        created_count += 1
            
            # Restore the statistics settings
            # sql_statements.append(f"-- Restore the statistics settings")
            # sql_statements.append(f"RESET default_statistics_target;")
            
            # Save the SQL file
            output_dir = self.exp_dir / "time_dependent_output" / self.query_set
            output_dir.mkdir(parents=True, exist_ok=True)
            sql_file = output_dir / sql_file_name
            
            # Delete the existing static MV file
            if sql_file.exists():
                self.print_info(f"Deleting existing static MV SQL file: {sql_file_name}")
                sql_file.unlink()
            
            with open(sql_file, 'w', encoding='utf-8') as f:
                f.write("\n".join(sql_statements))
            
            self.print_success(f"Generated static MV creation SQL: {sql_file}")
            self.print_info(f"  Number of MVs to create: {created_count}")
            return True
            
        except Exception as e:
            self.print_error(f"Static SQL generation failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def phase8_rewrite_queries(self, mode='dynamic', static_algorithm='normal'):
        """Phase 8: Query rewriting
        
        Args:
            mode: 'static', 'dynamic', or 'adaptive' (default: 'dynamic')
            static_algorithm: Static optimization algorithm ('normal', 'bigsubs', 'both')
        """
        # First branch on the mode
        if mode == 'static':
            # Static mode
            self.print_header("Query rewriting (static mode)", 8)
            
            # Select the file according to the algorithm
            if static_algorithm == 'bigsubs':
                static_result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"static_bigsubs_optimization_result{self.exp_suffix}.json"
            else:
                static_result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"static_mv_optimization_result{self.exp_suffix}.json"
            
            if not static_result_file.exists():
                self.print_error(f"Static optimization result not found: {static_result_file}")
                self.print_info("Run phase 6 with --optimization-mode static first")
                return False
            
            self.print_info(f"Rewriting queries using the static optimization result ({static_algorithm}).")
            
            phase_start = time.time()
            success = self._rewrite_static_queries(static_result_file, static_algorithm=static_algorithm)
            self.phase_times['phase8_rewrite_queries_static'] = time.time() - phase_start
            
            return success
        
        # Handling of Dynamic/Adaptive/Peloton modes
        mode_name = {"adaptive": "Adaptive", "peloton": "Peloton"}.get(mode, "Time-dependent")
        self.print_header(f"{mode_name} query rewriting", 8)
        
        # Start timing the phase
        phase_start = time.time()
        
        from src.rewrite.query_rewriter import QueryRewriter
        from src.core.models import MaterializedView
        
        if self.qp is None:
            self.print_info("Loading QueryParser...")
            if not self.pickle_path.exists():
                self.print_error("Parse results not found")
                return False
            
            with open(self.pickle_path, 'rb') as f:
                self.qp = pickle.load(f)
        
        # Load optimization result (adaptive / peloton / dynamic)
        if mode == 'adaptive':
            result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"adaptive_mv_optimization_result_w{self.window_size}{self.exp_suffix}.json"
        elif mode == 'peloton':
            result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"peloton_mv_optimization_result{self.exp_suffix}.json"
        else:
            result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"td_mv_optimization_result{self.exp_suffix}.json"

        if not result_file.exists():
            self.print_error(f"Optimization result not found: {result_file}")
            self.print_info("Run phase 6 first")
            return False

        with open(result_file, 'r', encoding='utf-8') as f:
            result_data = json.load(f)

        # Check if result is from time-dependent/adaptive optimizer
        if 'migration_analysis' not in result_data:
            self.print_error(f"Not a {mode_name} optimization result")
            return False
        
        # Get query files
        query_files = sorted(self.queries_dir.glob("*.sql"), key=lambda x: x.name)
        if not query_files:
            self.print_error("Query files not found")
            return False
        
        self.print_info(f"Number of queries: {len(query_files)}")
        
        # Base output directory
        base_output_dir = self.exp_dir / "time_dependent_output" / self.query_set / "jobs"
        base_output_dir.mkdir(parents=True, exist_ok=True)
        
        migration_analysis = result_data['migration_analysis']
        self.print_info(f"Number of time steps: {len(migration_analysis)}")
        
        # Load migration plans to get SQL for each MV
        plans_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_plans.json"
        if not plans_file.exists():
            self.print_error("Migration plans not found")
            self.print_info("Run phase 2.7 first")
            return False
        
        with open(plans_file, 'r', encoding='utf-8') as f:
            migration_plans = json.load(f)
        
        self.print_info(f"Loaded migration plans: {len(migration_plans)} MVs")
        
        total_rewritten = 0
        
        # Process each timestep
        for t_idx, timestep_info in enumerate(migration_analysis):
            timestep_name = timestep_info['timestep']
            selected_mvs = timestep_info.get('selected_mvs', [])
            
            self.print_info(f"\nTime step {t_idx} ({timestep_name}): {len(selected_mvs)} MVs")
            
            # Create MaterializedView objects for the selected MVs
            mv_objects = []
            for node_id in selected_mvs:
                # Find node index
                try:
                    node_idx = self.qp.node_list.index(node_id)
                except ValueError:
                    self.print_info(f"  Warning: node {node_id} not found")
                    continue
                
                # Get node size
                node_size = self.qp.b_j[node_idx] if node_idx < len(self.qp.b_j) else 0
                
                # Get usage positions from qm (which queries use this node?)
                # For now, apply all MVs to all queries (safe but not optimal)
                # TODO: Use actual usage information from query manager
                usage_positions = self.qp.qm.subquery_positions.get(node_id, [])
                # Get create_sql from migration plans
                create_sql = ""
                if node_id in migration_plans:
                    plans = migration_plans[node_id]
                    # Use the plan with no dependencies ("[]" key)
                    if "[]" in plans:
                        sql = plans["[]"]
                        if sql and sql != "NON_MIGRATE":
                            create_sql = sql
                
                # Create MaterializedView object
                mv = MaterializedView(
                    view_id=f"mv_{node_id}",
                    node_id=node_id,
                    create_sql=create_sql,  # SQL from migration plans
                    size=node_size,
                    maintenance_cost=0.0,  # Not needed for rewriting
                    usage_positions=usage_positions  # Apply to all queries
                )
                mv_objects.append(mv)
            
            # Create output directory for this timestep
            timestep_output_dir = base_output_dir / f"timestep_{t_idx}_{timestep_name}"
            if timestep_output_dir.exists():
                existing_sql_files = list(timestep_output_dir.glob("*.sql"))
                if existing_sql_files:
                    self.print_info(f"  Cleaned up existing SQL: {len(existing_sql_files)} files")
                    for sql_file in existing_sql_files:
                        sql_file.unlink()
            timestep_output_dir.mkdir(parents=True, exist_ok=True)
            
            # Rewrite queries using QueryRewriter with settings
            # Copy settings and specify the query directory
            from copy import deepcopy
            rewrite_settings = deepcopy(self.settings)
            rewrite_settings.benchmark.sql_dir = str(self.queries_dir.parent)  # Specify the 01_queries directory
            
            # Pass the containment matrix to enable redundant-MV elimination
            rewriter = QueryRewriter(
                rewrite_settings,
                containment_matrix=self.qp.X,
                node_list=self.qp.node_list,
                query_set=self.query_set
            )
            rewritten_queries = rewriter.rewrite_queries(mv_objects)
            
            # Save rewritten queries
            rewritten_count = 0
            for query_id, rewritten_sql in rewritten_queries.items():
                output_file = timestep_output_dir / f"{query_id}.sql"
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(rewritten_sql)
                rewritten_count += 1
            
            total_rewritten += rewritten_count
            self.print_success(f"  {rewritten_count} queries rewritten -> {timestep_output_dir}")
        
        # Record the phase time
        self.phase_times['phase8_query_rewriting'] = time.time() - phase_start
        
        self.print_success(f"\nRewrote {total_rewritten} queries in total")
        self.print_info(f"  Output directory: {base_output_dir}")
        self.print_info(f"  Query rewriting time: {self.phase_times['phase8_query_rewriting']:.2f} s")
        
        return True
    
    def _rewrite_static_queries(self, result_file, static_algorithm='normal'):
        """Rewrite queries based on the static optimization result
        
        Args:
            result_file: Path to the optimization result file
            static_algorithm: Algorithm to use ('normal' or 'bigsubs')
        """
        try:
            from src.rewrite.query_rewriter import QueryRewriter
            from src.core.models import MaterializedView
            
            # Load QueryParser if not already loaded
            if self.qp is None:
                self.print_info("Loading QueryParser...")
                if not self.pickle_path.exists():
                    self.print_error("Parse results not found")
                    return False
                
                with open(self.pickle_path, 'rb') as f:
                    self.qp = pickle.load(f)
            
            with open(result_file, 'r', encoding='utf-8') as f:
                result_data = json.load(f)
            
            selected_mvs = result_data.get('selected_mvs', [])
            self.print_info(f"Static mode ({static_algorithm}): {len(selected_mvs)} MVs used to rewrite queries")
            
            # Get the query files
            query_files = sorted(self.queries_dir.glob("*.sql"), key=lambda x: x.name)
            
            # Load the migration plans
            plans_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_plans.json"
            if not plans_file.exists():
                return
                
            with open(plans_file, 'r', encoding='utf-8') as f:
                migration_plans = json.load(f)
            
            # Create MV objects
            mv_objects = []
            for node_id in selected_mvs:
                # Look up the node index
                try:
                    node_idx = self.qp.node_list.index(node_id)
                    node_size = self.qp.b_j[node_idx] if node_idx < len(self.qp.b_j) else 0
                except ValueError:
                    continue
                
                create_sql = ""
                if node_id in migration_plans and "[]" in migration_plans[node_id]:
                    sql = migration_plans[node_id]["[]"]
                    if sql and sql != "NON_MIGRATE":
                        create_sql = sql
                
                mv = MaterializedView(
                    view_id=f"mv_{node_id}",
                    node_id=node_id,
                    create_sql=create_sql,
                    size=node_size,
                    maintenance_cost=0.0,
                    usage_positions=self.qp.qm.subquery_positions.get(node_id, [])
                )
                mv_objects.append(mv)
            
            # Run the rewriting
            # Copy settings and specify the query directory
            from copy import deepcopy
            rewrite_settings = deepcopy(self.settings)
            rewrite_settings.benchmark.sql_dir = str(self.queries_dir.parent)  # Specify the 01_queries directory
            
            # Pass the containment matrix to enable redundant-MV elimination
            rewriter = QueryRewriter(
                rewrite_settings,
                containment_matrix=self.qp.X,
                node_list=self.qp.node_list,
                query_set=self.query_set
            )
            rewritten_queries = rewriter.rewrite_queries(mv_objects)
            
            # Output location (changes according to the algorithm)
            if static_algorithm == 'bigsubs':
                output_dir = self.exp_dir / "time_dependent_output" / self.query_set / "jobs" / "rewritten_static_bigsubs"
            else:
                output_dir = self.exp_dir / "time_dependent_output" / self.query_set / "jobs" / "rewritten_static"
            if output_dir.exists():
                existing_sql_files = list(output_dir.glob("*.sql"))
                if existing_sql_files:
                    self.print_info(f"  Cleaned up existing static-mode SQL: {len(existing_sql_files)} files")
                    for sql_file in existing_sql_files:
                        sql_file.unlink()
            output_dir.mkdir(parents=True, exist_ok=True)
            
            for query_id, rewritten_sql in rewritten_queries.items():
                output_file = output_dir / f"{query_id}.sql"
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(rewritten_sql)
            
            self.print_success(f"  Rewrote queries for static mode ({static_algorithm}): {output_dir}")
            return True
            
        except Exception as e:
            self.print_error(f"Query rewriting for static mode failed: {e}")
            return False

    def phase9_execute_benchmark(self, mode='dynamic', static_algorithm='normal', ease_mode=False, noise_ratio=0.0, noise_query_dir=None):
        """Phase 9: Time-dependent benchmark execution
        
        Args:
            mode: Benchmark mode
                - 'dynamic': dynamic MVs (with migration)
                - 'adaptive': adaptive MVs (sliding window)
                - 'static': static MVs (first time step only)
                - 'baseline': baseline (no MVs)
            static_algorithm: Static optimization algorithm ('normal', 'bigsubs', 'both')
            ease_mode: Ease mode (run each query once and multiply its time by the frequency)
            noise_ratio: Noise injection ratio (0.0-1.0). In ease_mode, the original query is additionally run once and the frequency is split for estimation
            noise_query_dir: Directory containing the noise queries (the default job folder if None)
        """
        mode_names = {
            'dynamic': 'Dynamic MV (with migration)',
            'adaptive': 'Adaptive MV (sliding window)',
            'static': 'Static MV (first time step only)',
            'baseline': 'Baseline (no MVs)'
        }
        
        self.print_header(f"Time-dependent benchmark execution - {mode_names.get(mode, mode)}", 9)
        phase_start = time.time()
        
        # Drop all existing MVs (to guarantee a uniform initial state)
        # If the number of dropped MVs differed between runs, the amount of WAL generated would differ and make runs unequal, so do this first
        self.print_info("Cleaning up existing MVs...")
        if not self._drop_all_mvs():
            self.print_error("Failed to drop MVs")
            # Continue even on failure (warning only)
        
        # Update base-table statistics (raising the statistics target as in phase 1)
        # Running ANALYZE on every run means the benchmark uses up-to-date statistics
        self.print_info("Updating base-table statistics...")
        if not self._analyze_base_tables():
            self.print_error("ANALYZE on base tables failed")
            # Continue even on failure (warning only)
        
        # Clear the PostgreSQL cache (for a fair benchmark)
        # self.print_info("Clearing the PostgreSQL cache...")
        # self._clear_caches()
        
        # Disable autovacuum (suppress background activity during the benchmark)
        # NOTE: Temporarily commented out - to examine the effect on execution time
        self.print_info("Disabling autovacuum...")
        self._disable_autovacuum()
        
        # Run a forced checkpoint (clear WAL buffers and start from the same initial state)
        # WAL generated by dropping MVs is also processed here
        # This delays irregular checkpoints during the benchmark
        # and reduces execution-time variance
        self._force_checkpoint()       
        
        from benchmark import TimeDependentQueryExecutor
        from core.io_loaders import load_timesteps_and_frequencies
        
        # Decide whether optimization results need to be loaded, depending on the mode
        optimization_result = None
        migration_sql_dir = None
        rewritten_queries_base_dir = None # Initialize here
        result_file = None  # optimization result executed by this benchmark (recorded in run_config)
        
        if mode == 'dynamic':
            # Load the optimization result
            result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"td_mv_optimization_result{self.exp_suffix}.json"
            
            if not result_file.exists():
                self.print_error("Time-dependent optimization result not found")
                self.print_info("Run phase 6 first")
                return False
            
            with open(result_file, 'r', encoding='utf-8') as f:
                optimization_result = json.load(f)
                
            migration_sql_dir = self.exp_dir / "time_dependent_output" / self.query_set # This should point to the directory containing timestep_X_Y.sql
            rewritten_queries_base_dir = self.exp_dir / "time_dependent_output" / self.query_set / "jobs"
        
        elif mode == 'adaptive':
            # Load the adaptive optimization result
            result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"adaptive_mv_optimization_result_w{self.window_size}{self.exp_suffix}.json"

            if not result_file.exists():
                self.print_error("Adaptive optimization result not found")
                self.print_info("Run phase 6 with --optimization-mode adaptive first")
                return False

            with open(result_file, 'r', encoding='utf-8') as f:
                optimization_result = json.load(f)

            migration_sql_dir = self.exp_dir / "time_dependent_output" / self.query_set
            rewritten_queries_base_dir = self.exp_dir / "time_dependent_output" / self.query_set / "jobs"

        elif mode == 'peloton':
            # Load the Peloton (one-step lookahead) optimization result
            result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"peloton_mv_optimization_result{self.exp_suffix}.json"

            if not result_file.exists():
                self.print_error("Peloton optimization result not found")
                self.print_info("Run phase 6 with --optimization-mode peloton first")
                return False

            with open(result_file, 'r', encoding='utf-8') as f:
                optimization_result = json.load(f)

            migration_sql_dir = self.exp_dir / "time_dependent_output" / self.query_set
            rewritten_queries_base_dir = self.exp_dir / "time_dependent_output" / self.query_set / "jobs"

        elif mode == 'static':
            # Load the static optimization result (select the file according to the algorithm)
            if static_algorithm == 'bigsubs':
                result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"static_bigsubs_optimization_result{self.exp_suffix}.json"
                rewritten_queries_base_dir = self.exp_dir / "time_dependent_output" / self.query_set / "jobs" / "rewritten_static_bigsubs"
            else:
                result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"static_mv_optimization_result{self.exp_suffix}.json"
                rewritten_queries_base_dir = self.exp_dir / "time_dependent_output" / self.query_set / "jobs" / "rewritten_static"
            
            if not result_file.exists():
                self.print_error(f"Static optimization result not found: {result_file}")
                self.print_info("Run phase 6b first")
                return False
                
            with open(result_file, 'r', encoding='utf-8') as f:
                optimization_result = json.load(f)
            
            self.print_info(f"Using static optimization result ({static_algorithm}): {result_file.name}")
                
            # Settings for static mode
            # migration_sql_dir is the directory containing static_initial_mvs.sql
            migration_sql_dir = self.exp_dir / "time_dependent_output" / self.query_set
            
            if not rewritten_queries_base_dir.exists():
                self.print_error(f"Query directory for static mode not found: {rewritten_queries_base_dir}")
                return False

        elif mode == 'baseline':
            # Baseline mode does not need optimization results, but
            # to get the time steps and frequency information we could load a dummy,
            # or leave optimization_result as None.
            # Here we leave it as None and pass the original queries directly to the executor.
            optimization_result = None
            migration_sql_dir = None # Baseline does not need MV operation SQL
            rewritten_queries_base_dir = self.queries_dir # Directory of the original queries
            
        # Check that migration_sql_dir exists (dynamic/adaptive modes)
        if mode in ('dynamic', 'adaptive') and (not migration_sql_dir or not migration_sql_dir.exists()):
            self.print_error(f"Migration SQL directory not found: {migration_sql_dir}")
            self.print_info("Run phase 7 first")
            return False
        
        # Use the rewritten query files
        # rewritten_base_dir = self.exp_dir / "time_dependent_output" / self.query_set / "jobs" # This line is now handled by rewritten_queries_base_dir
        
        # Get the list of original query files (used as the list of query names)
        import re
        def natural_sort_key(s):
            return [int(text) if text.isdigit() else text.lower() for text in re.split("([0-9]+)", str(s))]
            
        original_query_files = sorted(self.queries_dir.glob("*.sql"), key=lambda x: natural_sort_key(x.name))
        
        if not original_query_files:
            self.print_error("Query files not found")
            return False
        
        self.print_info(f"Number of queries: {len(original_query_files)}")
        
        # Load frequency information
        self.print_info("Loading frequency information...")
        try:
            timesteps, frequencies_by_timestep = load_timesteps_and_frequencies(
                str(self.exp_dir), 
                self.query_set,
                freq_suffix=self.exp_suffix
            )
            self.print_success(f"  Number of time steps: {len(timesteps)}")
        except Exception as e:
            self.print_error(f"Failed to load frequency information: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        # Initialize TimeDependentQueryExecutor
        self.print_info("Preparing benchmark execution...")
        executor = TimeDependentQueryExecutor(self.settings)
        
        # Noise injection settings (also effective in ease_mode)
        # In ease_mode, the original query is additionally run only once and the frequency is split for estimation (handled by the executor)
        if noise_ratio > 0.0:
            executor.noise_ratio = noise_ratio

            # Determine the noise query folder (default: 01_queries/job)
            if noise_query_dir is not None:
                resolved_noise_dir = Path(noise_query_dir)
            else:
                resolved_noise_dir = self.queries_dir  # Original queries in 01_queries/{query_set}

            mode_label = "ease" if ease_mode else "normal"
            self.print_info(f"Noise injection settings ({mode_label} mode): ratio={noise_ratio:.2f}, dir={resolved_noise_dir}")
            loaded_count = executor.load_noise_pool(resolved_noise_dir)
            if loaded_count == 0:
                self.print_error(f"Noise queries not found: {resolved_noise_dir}")
                self.print_info("Continuing without noise")
                executor.noise_ratio = 0.0
            else:
                self.print_success(f"  Noise pool: preloaded {loaded_count} queries")
        
        try:
            # Run the benchmark according to the mode
            self.print_info(f"Starting benchmark execution (mode: {mode})...\n")
            
            if mode == 'baseline':
                # Baseline: no MVs (use the original queries)
                benchmark_results = executor.execute_baseline_benchmark(
                    query_files=original_query_files,
                    frequencies_by_timestep=frequencies_by_timestep,
                    timesteps=timesteps,
                    timeout_minutes=60,
                    verbose=True,
                    ease_mode=ease_mode
                )
            elif mode == 'static':
                # Static MVs: first time step only
                benchmark_results = executor.execute_static_mv_benchmark(
                    optimization_result=optimization_result,
                    migration_sql_dir=migration_sql_dir,
                    # query_files=query_files, # Not used directly, rewritten_queries_base_dir is used
                    rewritten_queries_base_dir = rewritten_queries_base_dir,
                    frequencies_by_timestep=frequencies_by_timestep,
                    timesteps=timesteps, # Pass timesteps for static mode as well
                    timeout_minutes=60,
                    verbose=True,
                    static_algorithm=static_algorithm,
                    ease_mode=ease_mode
                )
            else:  # dynamic / adaptive / peloton
                # Dynamic/adaptive/Peloton MVs: with migration
                benchmark_results = executor.execute_time_dependent_benchmark(
                    optimization_result=optimization_result,
                    migration_sql_dir=migration_sql_dir,
                    #query_files=query_files, # Not used directly, rewritten_queries_base_dir is used
                    rewritten_queries_base_dir = rewritten_queries_base_dir,
                    frequencies_by_timestep=frequencies_by_timestep,
                    timeout_minutes=60,
                    verbose=True,
                    ease_mode=ease_mode
                )
            
            # Save the results
            output_dir = self.exp_dir / "time_dependent_output" / self.query_set
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Static mode + bigsubs uses a separate file name
            # If noise_ratio > 0, append _noise{XX} to the file name to avoid collisions
            noise_suffix = f"_noise{int(noise_ratio * 100)}" if noise_ratio > 0.0 else ""
            window_suffix = f"_w{self.window_size}" if mode == 'adaptive' else ""
            if mode == 'static' and static_algorithm == 'bigsubs':
                output_file = output_dir / f"benchmark_results_static_bigsubs{self.exp_suffix}{noise_suffix}.json"
            else:
                output_file = output_dir / f"benchmark_results_{mode}{window_suffix}{self.exp_suffix}{noise_suffix}.json"
            
            if noise_ratio > 0.0:
                noise_dir_used = Path(noise_query_dir) if noise_query_dir is not None else self.queries_dir
            else:
                noise_dir_used = None
            benchmark_results["run_config"] = self._run_config(
                "9",
                benchmark_mode=mode,
                static_algorithm=static_algorithm if mode == 'static' else None,
                window_size=self.window_size if mode == 'adaptive' else None,
                ease_mode=ease_mode,
                noise_ratio=noise_ratio,
                noise_query_dir=noise_dir_used,
                optimization_result=result_file,
            )
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(benchmark_results, f, indent=2, ensure_ascii=False)
            
            self.print_success(f"\nSaved benchmark results: {output_file}")
            
            # Show the summary
            summary = benchmark_results.get('summary', {})
            self.print_info(f"  Total number of time steps: {summary.get('total_timesteps', 0)}")
            
            if mode == 'dynamic':
                self.print_info(f"  Total migration time: {summary.get('total_migration_time', 0):.2f}s")
            elif mode == 'static':
                self.print_info(f"  Initial MV creation time: {summary.get('initial_mv_creation_time', 0):.2f}s")
            
            self.print_info(f"  Total query execution time: {summary.get('total_query_time', 0):.2f}s")
            self.print_info(f"  Total benchmark time: {summary.get('total_benchmark_time', 0):.2f}s")
            
            # Record the phase time
            self.phase_times['phase9_benchmark'] = time.time() - phase_start
            
            return True
            
        except Exception as e:
            self.print_error(f"Benchmark execution failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # Enable autovacuum (restore)
            # NOTE: Since disabling is commented out, this does not need to run either
            self.print_info("Enabling autovacuum...")
            self._enable_autovacuum()
            
            executor.close()

    
    def run_post_optimization_phases(self, optimization_mode='dynamic', use_pruning=False, pruning_parallel=False, pruning_workers=None, static_timestep='last', use_static_protection=False, static_algorithm='normal', ease_mode=False, noise_ratio=0.0, noise_query_dir=None, b_max=None, inherit_parent_constraints=True):
        """Run the phases after optimization (Phase 6-9)

        Args:
            optimization_mode: 'static' or 'dynamic' (default: 'dynamic')
            use_pruning: Whether to use CF Pruning (default: False)
            pruning_parallel: Whether to run pruning in parallel (default: False)
            pruning_workers: Number of workers for parallel execution (default: number of CPU cores)
            static_timestep: Time step used by static optimization ('first' or 'last')
            use_static_protection: Protect the static-optimization MVs as a sanctuary (default: False)
            static_algorithm: Static optimization algorithm ('normal', 'bigsubs', 'both')
            inherit_parent_constraints: Propagate boundary constraints from parent nodes in the WST (default: True)
        """
        self.print_header(f"Running post-optimization phases ({optimization_mode} mode)")

        # Record the overall start time
        total_start_time = time.time()

        # Optimization phase (selected according to the mode)
        optimization_phase = (6, "MV optimization", lambda: self.phase6_optimize(
            mode=optimization_mode,
            use_pruning=use_pruning,
            pruning_parallel=pruning_parallel,
            pruning_workers=pruning_workers,
            static_timestep=static_timestep,
            use_static_protection=use_static_protection,
            static_algorithm=static_algorithm,
            b_max=b_max,
            inherit_parent_constraints=inherit_parent_constraints,
        ))
        
        # SQL generation, query rewriting and benchmark phases
        post_optimization_phases = [
            (7, "MV creation SQL generation", lambda: self.phase7_generate_mv_sql(mode=optimization_mode, static_algorithm=static_algorithm)),
            (8, "Query rewriting", lambda: self.phase8_rewrite_queries(mode=optimization_mode, static_algorithm=static_algorithm)),
            (9, "Benchmark execution", lambda: self.phase9_execute_benchmark(mode=optimization_mode, static_algorithm=static_algorithm, ease_mode=ease_mode, noise_ratio=noise_ratio, noise_query_dir=noise_query_dir)),
        ]
        
        # Combine all phases
        phases = [optimization_phase] + post_optimization_phases
        
        for phase_num, phase_name, phase_func in phases:
            try:
                if not phase_func():
                    self.print_error(f"Phase {phase_num} failed")
                    return False
            except Exception as e:
                self.print_error(f"Error in phase {phase_num}: {e}")
                import traceback
                traceback.print_exc()
                return False
        
        # Record the overall execution time
        total_elapsed = time.time() - total_start_time
        
        self.print_header("Post-optimization phases completed")
        self.print_success(f"Total execution time: {total_elapsed:.2f} s")
        
        if self.phase_times:
            self.print_info("Execution time per phase:")
            for phase, elapsed in self.phase_times.items():
                if phase in ['phase6_optimization', 'phase7_mv_sql_generation', 'phase8_query_rewriting', 'phase9_benchmark']:
                    self.print_info(f"  {phase}: {elapsed:.2f} s")
        
        return True
    
    def run_all_phases(self, optimization_mode='dynamic', use_pruning=False, pruning_parallel=False, pruning_workers=None, static_timestep='last', use_static_protection=False, ease_mode=False, noise_ratio=0.0, noise_query_dir=None, b_max=None, inherit_parent_constraints=True, sampling_high=False):
        """Run all phases sequentially

        Args:
            optimization_mode: 'static' or 'dynamic' (default: 'dynamic')
            use_pruning: Whether to use CF Pruning (default: False)
            pruning_parallel: Whether to run pruning in parallel (default: False)
            pruning_workers: Number of workers for parallel execution (default: number of CPU cores)
            static_timestep: Time step used by static optimization ('first' or 'last')
            use_static_protection: Protect the static-optimization MVs as a sanctuary (default: False)
            inherit_parent_constraints: Propagate boundary constraints from parent nodes in the WST (default: True)
        """
        self.print_header("Small-scale experiment (normal mode) - running all phases")

        success = True

        # Record the overall start time
        total_start_time = time.time()

        # Basic phases (independent of the mode)
        basic_phases = [
            (1, "EXPLAIN JSON generation", self.phase1_generate_explain_json),
            (2, "Query parsing", self.phase2_parse_queries),
            (3, "JSON node ID annotation", self.phase3_annotate_json),
            (4, "Migration plan enumeration", self.phase4_enumerate_migration_plans),
            (5, "Migration cost calculation", lambda: self.phase5_calculate_migration_costs(use_sampling=True, sampling_high=sampling_high)),
            (5.5, "Cost recalculation", self.phase5_5_recalculate_costs),
        ]

        # Optimization phase (selected according to the mode)
        optimization_phase = (6, "MV optimization", lambda: self.phase6_optimize(
            mode=optimization_mode,
            use_pruning=use_pruning,
            pruning_parallel=pruning_parallel,
            pruning_workers=pruning_workers,
            static_timestep=static_timestep,
            use_static_protection=use_static_protection,
            b_max=b_max,
            inherit_parent_constraints=inherit_parent_constraints,
        ))
        
        # SQL generation, query rewriting and benchmark phases
        post_optimization_phases = [
            (7, "MV creation SQL generation", lambda: self.phase7_generate_mv_sql(mode=optimization_mode)),
            (8, "Query rewriting", lambda: self.phase8_rewrite_queries(mode=optimization_mode)),
            (9, "Benchmark execution", lambda: self.phase9_execute_benchmark(mode=optimization_mode, ease_mode=ease_mode, noise_ratio=noise_ratio, noise_query_dir=noise_query_dir)),
        ]
        
        # Combine all phases
        phases = basic_phases + [optimization_phase] + post_optimization_phases
        
        for phase_num, phase_name, phase_func in phases:
            try:
                if not phase_func():
                    self.print_error(f"Phase {phase_num} failed")
                    return False
            except Exception as e:
                self.print_error(f"Error in phase {phase_num}: {e}")
                import traceback
                traceback.print_exc()
                return False
        
        # Record the overall execution time
        total_elapsed = time.time() - total_start_time
        
        # Save the summary of phase times
        result_dir = self.exp_dir / "time_dependent_output" / self.query_set
        result_dir.mkdir(parents=True, exist_ok=True)
        
        summary = {
            "query_set": self.query_set,
            "total_execution_time": round(total_elapsed, 2),
            "phase_times": {
                key: round(value, 2) for key, value in self.phase_times.items()
            },
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        
        summary_file = result_dir / "execution_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        self.print_header("All phases completed")
        self.print_success(f"Total execution time: {total_elapsed:.2f} s")
        if self.phase_times:
            self.print_info("Execution time per phase:")
            for phase_name, phase_time in self.phase_times.items():
                self.print_info(f"  {phase_name}: {phase_time:.2f} s")
        self.print_success(f"Saved summary to {summary_file}")
        
        return True


def main():
    parser = argparse.ArgumentParser(description="Small-scale experiment - normal mode")
    parser.add_argument(
        '--phase',
        type=str,
        default='all',
        choices=['all', 'post-opt', '1', '2', '3', '4', '5', '5.5', '6', '6.5', '7', '8', '9'],
        help='Phase to run (all: run everything, post-opt: phases after optimization (6-9), 1: EXPLAIN, 2: Parse, 3: Annotate, 4: Migration plans, 5: Migration costs, 5.5: Cost recalculation, 6: Optimize, 6.5: Static Optimize, 7: MV SQL, 8: Rewrite, 9: Benchmark). The database is set up with docker/create_container.sh'
    )
    parser.add_argument(
        '--config',
        type=str,
        default='.',
        help='Path to the experiment directory (no configuration file required)'
    )
    parser.add_argument(
        '--query-set',
        type=str,
        default='job',
        help='Query set to run (job, job_like, explicit_join, etc.)'
    )
    parser.add_argument(
        '--benchmark-mode',
        type=str,
        default='dynamic',
        choices=['dynamic', 'adaptive', 'peloton', 'static', 'baseline'],
        help='Benchmark mode (dynamic: dynamic MVs, adaptive: adaptive MVs, peloton: one-step lookahead, static: static MVs, baseline: no MVs)'
    )
    parser.add_argument(
        '--optimization-mode',
        type=str,
        default='dynamic',
        choices=['static', 'dynamic', 'adaptive', 'peloton'],
        help='Optimization mode (static: initial time step only, dynamic: time-dependent optimization, adaptive: adaptive optimization, peloton: one-step lookahead with perfect foresight)'
    )
    parser.add_argument(
        '--use-sampling',
        action='store_true',
        help='Use sampling for cost estimation'
    )
    parser.add_argument(
        '--sampling-rate',
        type=str,
        default='low',
        choices=['low', 'high'],
        help='Choice of sampling rate (low: low sampling rate/Correlated Sampling, high: high sampling rate/BERNOULLI). Default: low'
    )
    parser.add_argument(
        '--use-pruning',
        action='store_true',
        help='Use CF Pruning to reduce MV candidates (recommended for a large number of time steps)'
    )
    parser.add_argument(
        '--pruning-parallel',
        action='store_true',
        help='Run CF Pruning in parallel (recommended on many-core servers)'
    )
    parser.add_argument(
        '--pruning-workers',
        type=int,
        default=None,
        help='Number of workers for parallel execution (default: number of CPU cores)'
    )
    parser.add_argument(
        '--static-protection',
        action='store_true',
        help='Protect the static-optimization MVs as a sanctuary during pruning (hybrid approach)'
    )
    parser.add_argument(
        '--exp-suffix',
        type=str,
        default='',
        help='Suffix identifying the experiment (e.g., _16_2, _16_4). Applied to the frequency file and the optimization result files'
    )
    parser.add_argument(
        '--static-timestep',
        type=str,
        default='last',
        choices=['first', 'last', 'average', 'addmv'],
        help='Time step used by static optimization (first: first, last: last, average: average over all time steps, addmv: frequency sum + considering MV creation cost)'
    )
    parser.add_argument(
        '--static-algorithm',
        type=str,
        default='normal',
        choices=['normal', 'bigsubs', 'both', 'utility'],
        help='Algorithm used by static optimization (normal: regular ILP, bigsubs: BigSubs, both: both, utility: UtilityOptimizerV2)'
    )
    parser.add_argument(
        '--ease',
        action='store_true',
        help='Ease benchmark mode: run each query only once and multiply its execution time by the frequency to estimate the time'
    )
    parser.add_argument(
        '--recalc',
        action='store_true',
        help='Compute migration and utility using the recalculated costs (simple_migration_costs.json)'
    )
    parser.add_argument(
        '--noise-ratio',
        type=float,
        default=0.0,
        help='Noise injection ratio (0.0-1.0). In normal mode, each query execution is replaced by the original query with the given probability. In ease_mode, the original query is run once and the frequency is split into noise/rewritten for estimation (fast). e.g., 0.2 = 20%% original queries'
    )
    parser.add_argument(
        '--noise-query-dir',
        type=str,
        default=None,
        help='Directory containing the noise queries (default: 01_queries/job)'
    )
    parser.add_argument(
        '--window-size',
        type=int,
        default=4,
        help='Moving-average window width used by adaptive optimization (default: 4)'
    )
    parser.add_argument(
        '--freq-weight',
        type=str,
        default='uniform',
        choices=['uniform', 'linear'],
        help='Weighting of frequencies within the window in adaptive optimization (uniform=simple moving average, linear=DeepSea-style linear recency weights)'
    )
    parser.add_argument(
        '--b-max',
        type=float,
        default=100.0,
        help='Storage budget B_max (in MB, default: 100). Used by phases 6/6b/6c'
    )
    parser.add_argument(
        '--no-wst-parent-constraints',
        action='store_true',
        help='Disable propagation of boundary constraints from parent nodes in the WST (default: enabled)'
    )

    # Docker/Local switching arguments
    add_docker_args(parser)
    
    args = parser.parse_args()
    
    exp = NormalModeExperiment(
        exp_dir=args.config, 
        query_set=args.query_set, 
        exp_suffix=args.exp_suffix,
        use_docker=args.use_docker,
        recalc_mode=args.recalc,
        window_size=args.window_size,
        freq_weight=args.freq_weight
    )
    
    # Record the command-line arguments in the result files (key "run_config")
    exp.run_args = {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()}

    # Show the connection mode
    print(f"\n[Connection mode: {exp.pg_executor.get_mode_description()}]")
    
    if args.phase == 'all':
        success = exp.run_all_phases(
            optimization_mode=args.optimization_mode,
            use_pruning=args.use_pruning,
            pruning_parallel=args.pruning_parallel,
            pruning_workers=args.pruning_workers,
            static_timestep=args.static_timestep,
            use_static_protection=args.static_protection,
            noise_ratio=args.noise_ratio,
            noise_query_dir=args.noise_query_dir,
            b_max=args.b_max,
            inherit_parent_constraints=not args.no_wst_parent_constraints,
            sampling_high=(args.sampling_rate == 'high'),
        )
    elif args.phase == 'post-opt':
        success = exp.run_post_optimization_phases(
            optimization_mode=args.optimization_mode,
            use_pruning=args.use_pruning,
            pruning_parallel=args.pruning_parallel,
            pruning_workers=args.pruning_workers,
            static_timestep=args.static_timestep,
            use_static_protection=args.static_protection,
            static_algorithm=args.static_algorithm,
            ease_mode=args.ease,
            noise_ratio=args.noise_ratio,
            noise_query_dir=args.noise_query_dir,
            b_max=args.b_max,
            inherit_parent_constraints=not args.no_wst_parent_constraints,
        )
    elif args.phase == '1':
        success = exp.phase1_generate_explain_json()
    elif args.phase == '2':
        success = exp.phase2_parse_queries()
    elif args.phase == '3':
        success = exp.phase3_annotate_json()
    elif args.phase == '4':
        success = exp.phase4_enumerate_migration_plans()
    elif args.phase == '5':
        success = exp.phase5_calculate_migration_costs(
            use_sampling=args.use_sampling,
            sampling_high=(args.sampling_rate == 'high')
        )
    elif args.phase == '5.5':
        success = exp.phase5_5_recalculate_costs()
    elif args.phase == '6':
        success = exp.phase6_optimize(
            mode=args.optimization_mode,
            use_pruning=args.use_pruning,
            pruning_parallel=args.pruning_parallel,
            pruning_workers=args.pruning_workers,
            static_timestep=args.static_timestep,
            use_static_protection=args.static_protection,
            static_algorithm=args.static_algorithm,
            b_max=args.b_max,
            inherit_parent_constraints=not args.no_wst_parent_constraints,
        )
    elif args.phase == '6.5':
        success = exp.phase6b_optimize_static(timestep_position=args.static_timestep, static_algorithm=args.static_algorithm, b_max=args.b_max)
    elif args.phase == '7':
        success = exp.phase7_generate_mv_sql(mode=args.optimization_mode)
    elif args.phase == '8':
        success = exp.phase8_rewrite_queries(mode=args.optimization_mode)
    elif args.phase == '9':
        success = exp.phase9_execute_benchmark(
            mode=args.benchmark_mode,
            ease_mode=args.ease,
            noise_ratio=args.noise_ratio,
            noise_query_dir=args.noise_query_dir
        )
    else:
        print(f"Unknown phase: {args.phase}")
        success = False
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
