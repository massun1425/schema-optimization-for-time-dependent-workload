"""Query execution and benchmarking for time-dependent workloads

This module runs benchmarks for workloads that change over time.
At each time step:
1. Execute the migration SQL (create/drop MVs)
2. Execute queries repeatedly according to their frequencies
3. Record execution time and cost
"""

import json
import logging
import random
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extensions import QueryCanceledError

from config.settings import Settings

logger = logging.getLogger(__name__)


class TimeDependentQueryExecutor:
    """Query execution manager for time-dependent workloads"""
    
    def __init__(self, settings: Settings):
        """Initialize.
        
        Args:
            settings: Settings object
        """
        self.settings = settings
        self.db_config = settings.database
        self.connection = None
        
        # Noise injection settings
        # noise_ratio: probability of replacing each query execution with noise (0.0-1.0)
        # noise_pool: preloaded dict of original (pre-rewrite) query SQL {query_stem: sql_text}
        self.noise_ratio: float = 0.0
        self.noise_pool: Dict[str, str] = {}
    
    def load_noise_pool(self, noise_dir: Path) -> int:
        """Preload the noise query pool (original queries before rewriting) into memory.
        
        Loading everything up front before the benchmark starts eliminates disk I/O during execution.
        When noise occurs, the original query with the same name is executed instead of the rewritten query.
        
        Args:
            noise_dir: Directory containing the SQL files of the original (pre-rewrite) queries
            
        Returns:
            Number of queries loaded
        """
        if not noise_dir.exists():
            logger.warning(f"Noise directory not found: {noise_dir}")
            return 0
        
        sql_files = sorted(noise_dir.glob("*.sql"))
        if not sql_files:
            logger.warning(f"No SQL files found in noise directory: {noise_dir}")
            return 0
        
        self.noise_pool = {}
        for sql_file in sql_files:
            try:
                with open(sql_file, 'r', encoding='utf-8') as f:
                    sql_text = f.read().strip()
                if sql_text:
                    self.noise_pool[sql_file.stem] = sql_text
            except Exception as e:
                logger.warning(f"Failed to load noise query {sql_file.name}: {e}")
        
        logger.info(f"Loaded {len(self.noise_pool)} original (non-rewritten) queries from {noise_dir}")
        return len(self.noise_pool)
    
    def _get_connection(self):
        """Get or create a database connection.
        
        Note:
            Connects via localhost even in the Docker environment (using port forwarding).
            The Docker container is mapped as 0.0.0.0:5432->5432/tcp,
            so it is reachable at localhost:5432
        """
        if self.connection is None or self.connection.closed:
            self.connection = psycopg2.connect(
                host=self.db_config.host,
                port=self.db_config.port,
                user=self.db_config.user,
                password=self.db_config.password,
                database=self.db_config.database
            )
            # Set the statistics target to 1000 (set here because it is reset per session)
            try:
                with self.connection.cursor() as cursor:
                    # cursor.execute("SET default_statistics_target = 1000;")
                    cursor.execute("SET random_page_cost = 1.1;")
                self.connection.commit()
            except Exception as e:
                logger.warning(f"Failed to set random_page_cost: {e}")
        return self.connection

    
    def _execute_sql_file(
        self, 
        sql_file: Path, 
        timeout_minutes: int = 30
    ) -> Tuple[bool, float, Optional[str]]:
        """Execute an SQL file.
        
        Args:
            sql_file: Path to the SQL file to execute
            timeout_minutes: Timeout (minutes)
            
        Returns:
            Tuple of (success, elapsed_time, error_message)
        """
        start_time = time.time()
        
        # Read the SQL file
        try:
            with open(sql_file, 'r', encoding='utf-8') as f:
                sql_content = f.read()
        except Exception as e:
            logger.error(f"Error reading {sql_file.name}: {e}")
            return False, 0.0, str(e)
        
        # Remove psql meta-commands (\c, \set, etc.)
        # These are specific to the psql command-line tool and cannot be executed with psycopg2
        lines = sql_content.split('\n')
        filtered_lines = []
        for line in lines:
            stripped = line.strip()
            # Skip lines starting with a backslash (psql meta-commands)
            if stripped.startswith('\\'):
                logger.debug(f"Skipping psql meta-command: {stripped}")
                continue
            filtered_lines.append(line)
        
        sql_content = '\n'.join(filtered_lines).strip()
        
        if not sql_content:
            logger.warning(f"Empty SQL file after filtering: {sql_file.name}")
            return False, 0.0, "Empty SQL file"
        
        # Execute the SQL (each statement individually)
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Set the timeout
            timeout_ms = timeout_minutes * 60 * 1000
            cursor.execute(f"SET statement_timeout = '{timeout_ms}'")
            
            logger.debug(f"Executing SQL file: {sql_file.name}")
            
            # Split the SQL into individual statements and execute them
            # Split on semicolons and execute only non-empty statements
            statements = []
            current_statement = []
            
            for line in sql_content.split('\n'):
                stripped = line.strip()
                # Skip comment lines and empty lines
                if not stripped or stripped.startswith('--'):
                    continue
                    
                current_statement.append(line)
                
                # A trailing semicolon completes the statement
                if stripped.endswith(';'):
                    stmt = '\n'.join(current_statement).strip()
                    if stmt and stmt != ';':
                        statements.append(stmt)
                    current_statement = []
            
            # Append any remaining statement
            if current_statement:
                stmt = '\n'.join(current_statement).strip()
                if stmt:
                    statements.append(stmt)
            
            print(f"DEBUG: Executing {len(statements)} SQL statements from {sql_file.name}")
            
            # Execute each statement individually
            for idx, statement in enumerate(statements, 1):
                if idx % 10 == 0 or idx == len(statements):
                    print(f"DEBUG: Executing statement {idx}/{len(statements)}")
                    logger.info(f"  Progress: {idx}/{len(statements)} statements")
                
                cursor.execute(statement)
            
            conn.commit()
            cursor.close()
            
            elapsed = time.time() - start_time
            print(f"DEBUG: Completed {len(statements)} statements in {elapsed:.2f}s")
            return True, elapsed, None
            
        except QueryCanceledError:
            elapsed = time.time() - start_time
            logger.warning(f"SQL file {sql_file.name} timed out after {timeout_minutes} minutes")
            if self.connection:
                self.connection.rollback()
            return False, elapsed, f'Timeout after {timeout_minutes} minutes'
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Error executing {sql_file.name}: {e}")
            if self.connection:
                self.connection.rollback()
            return False, elapsed, str(e)
    
    def _execute_query(
        self, 
        query_sql: str, 
        query_name: str,
        timeout_minutes: int = 30
    ) -> Tuple[bool, float, Optional[str]]:
        """Execute a single query.
        
        Args:
            query_sql: SQL to execute
            query_name: Query name (for logging)
            timeout_minutes: Timeout (minutes)
            
        Returns:
            Tuple of (success, elapsed_time, error_message)
        """
        start_time = time.time()
        
        if not query_sql.strip():
            return False, 0.0, "Empty query"
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Set the timeout
            timeout_ms = timeout_minutes * 60 * 1000
            cursor.execute(f"SET statement_timeout = '{timeout_ms}'")
            
            # Execute the query
            cursor.execute(query_sql)
            
            # Fetch the results (important to make the query actually execute)
            try:
                results = cursor.fetchall()
                row_count = len(results)
            except psycopg2.ProgrammingError:
                # Queries that return no results (CREATE, INSERT, etc.)
                row_count = cursor.rowcount
            
            conn.commit()
            cursor.close()
            
            elapsed = time.time() - start_time
            return True, elapsed, None
            
        except QueryCanceledError:
            elapsed = time.time() - start_time
            logger.warning(f"Query {query_name} timed out after {timeout_minutes} minutes")
            if self.connection:
                self.connection.rollback()
            return False, elapsed, f'Timeout after {timeout_minutes} minutes'
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Error executing query {query_name}: {e}")
            if self.connection:
                self.connection.rollback()
            return False, elapsed, str(e)
    
    def _execute_queries_with_frequency(
        self,
        query_files: List[Path],
        frequencies: List[float],
        timeout_minutes: int = 30,
        verbose: bool = False,
        ease_mode: bool = False
    ) -> Dict:
        """Execute queries according to their frequencies.
        
        Args:
            query_files: List of query files
            frequencies: Execution frequency (number of executions) of each query
            timeout_minutes: Timeout (minutes)
            verbose: Whether to output detailed logs
            ease_mode: Ease mode (execute each query once and multiply the time by the frequency.
                       When noise is enabled, the original query is also executed once and the frequency is split into noise/rewritten for the estimate)

        Returns:
            Dict of execution results
        """
        # Determine whether noise injection is enabled
        # Noise is also supported in ease_mode:
        #   Normal mode -> within the loop of frequency iterations, probabilistically replace with the original query
        #   ease_mode   -> execute the original query only once more and split the frequency into noise/rewritten for the estimate
        use_noise = (self.noise_ratio > 0.0) and (len(self.noise_pool) > 0)
        
        results = []
        total_time = 0.0
        total_executions = 0
        successful_executions = 0
        failed_executions = 0
        noise_executions = 0  # Number of executions performed as noise
        
        for query_file, frequency in zip(query_files, frequencies):
            # Skip if the frequency is 0
            if frequency <= 0:
                if verbose:
                    logger.debug(f"Skipping {query_file.name} (frequency=0)")
                continue
            
            # Read the SQL file
            try:
                with open(query_file, 'r', encoding='utf-8') as f:
                    query_sql = f.read().strip()
            except Exception as e:
                logger.error(f"Error reading {query_file.name}: {e}")
                results.append({
                    'query_id': query_file.stem,
                    'frequency': frequency,
                    'executions': 0,
                    'success': False,
                    'error': str(e)
                })
                continue
            
            execution_times = []
            execution_count = int(frequency)
            query_successful = 0
            query_failed = 0
            
            if ease_mode:
                # Ease mode: execute the rewritten query only once and estimate by multiplying the time by the frequency.
                # When noise is enabled, also execute the original (pre-rewrite) query once and split the frequency for the estimate:
                #   estimated = t_original * noise_count + t_rewritten * rewritten_count
                #   noise_count = round(frequency * noise_ratio)  <- round half up
                #   rewritten_count = frequency - noise_count      <- the rest (the total stays equal to frequency)
                if verbose:
                    logger.info(f"  [EASE] Executing {query_file.name} (single run, freq={frequency})...")

                success, elapsed, error = self._execute_query(
                    query_sql,
                    query_file.name,
                    timeout_minutes
                )
                rewritten_time = elapsed
                execution_times.append(rewritten_time)
                total_executions += 1
                if success:
                    query_successful += 1
                    successful_executions += 1
                else:
                    query_failed += 1
                    failed_executions += 1

                # Noise part: execute the original query once (only if enabled and the original query exists in the pool)
                noise_sql = self.noise_pool.get(query_file.stem) if use_noise else None
                noise_time = None
                if noise_sql is not None:
                    if verbose:
                        logger.info(f"  [EASE][NOISE] Executing {query_file.stem} (original, single run)...")
                    n_success, noise_time, n_error = self._execute_query(
                        noise_sql,
                        f"[NOISE] {query_file.stem} (original)",
                        timeout_minutes
                    )
                    execution_times.append(noise_time)
                    total_executions += 1
                    noise_executions += 1
                    if n_success:
                        query_successful += 1
                        successful_executions += 1
                    else:
                        query_failed += 1
                        failed_executions += 1
                        success = False
                        if error is None:
                            error = n_error

                    # Split the frequency into noise / rewritten (total = frequency is preserved)
                    noise_count = int(frequency * self.noise_ratio + 0.5)  # round half up
                    rewritten_count = frequency - noise_count
                    estimated_total = noise_time * noise_count + rewritten_time * rewritten_count
                else:
                    noise_count = 0
                    rewritten_count = frequency
                    estimated_total = rewritten_time * frequency

                total_time += estimated_total  # Add the estimated time to the total

                if verbose:
                    if noise_sql is not None:
                        logger.info(
                            f"    {'✓' if success else '✗'} EASE+NOISE "
                            f"(rewritten: {rewritten_time:.2f}s x{rewritten_count}, "
                            f"original: {noise_time:.2f}s x{noise_count}, "
                            f"estimated: {estimated_total:.2f}s)"
                        )
                    elif success:
                        logger.info(f"    ✓ Success (actual: {rewritten_time:.2f}s, estimated: {estimated_total:.2f}s)")
                    else:
                        logger.warning(f"    ✗ Failed ({rewritten_time:.2f}s): {error}")

                # Record the result
                results.append({
                    'query_id': query_file.stem,
                    'frequency': frequency,
                    'executions': len(execution_times),  # Actual number of executions (2 with noise)
                    'estimated_executions': execution_count,  # Number of executions expected from the frequency
                    'successful': query_successful,
                    'failed': query_failed,
                    'actual_time': round(rewritten_time, 5),  # Measured time of the rewritten query
                    'noise_time': round(noise_time, 5) if noise_time is not None else None,
                    'noise_count': noise_count,
                    'rewritten_count': rewritten_count,
                    'total_time': round(estimated_total, 5),  # Estimated total time
                    'avg_time': round(sum(execution_times) / len(execution_times), 5),
                    'min_time': round(min(execution_times), 5),
                    'max_time': round(max(execution_times), 5),
                    'ease_mode': True,
                    'noise_applied': noise_sql is not None,
                })
            else:
                # Normal mode: execute the query as many times as its frequency
                for exec_idx in range(execution_count):
                    # Noise injection: replace with the original pre-rewrite query with probability noise_ratio
                    if use_noise and random.random() < self.noise_ratio:
                        original_sql = self.noise_pool.get(query_file.stem)
                        if original_sql is not None:
                            actual_sql = original_sql
                            actual_name = f"[NOISE] {query_file.stem} (original)"
                            is_noise = True
                        else:
                            # Skip noise if the original query is not found in the pool
                            actual_sql = query_sql
                            actual_name = query_file.name
                            is_noise = False
                    else:
                        actual_sql = query_sql
                        actual_name = query_file.name
                        is_noise = False
                    
                    if verbose:
                        label = "NOISE" if is_noise else f"{exec_idx+1}/{execution_count}"
                        logger.info(f"  [{label}] Executing {actual_name}...")
                    
                    success, elapsed, error = self._execute_query(
                        actual_sql,
                        actual_name,
                        timeout_minutes
                    )
                    
                    execution_times.append(elapsed)
                    total_time += elapsed
                    total_executions += 1
                    if is_noise:
                        noise_executions += 1
                    
                    if success:
                        query_successful += 1
                        successful_executions += 1
                        if verbose:
                            logger.info(f"    ✓ Success ({elapsed:.2f}s){'  [noise]' if is_noise else ''}")
                    else:
                        query_failed += 1
                        failed_executions += 1
                        if verbose:
                            logger.warning(f"    ✗ Failed ({elapsed:.2f}s): {error}{'  [noise]' if is_noise else ''}")
                
                # Per-query aggregation
                avg_time = sum(execution_times) / len(execution_times) if execution_times else 0.0
                results.append({
                    'query_id': query_file.stem,
                    'frequency': frequency,
                    'executions': execution_count,
                    'successful': query_successful,
                    'failed': query_failed,
                    'total_time': round(sum(execution_times), 5),
                    'avg_time': round(avg_time, 5),
                    'min_time': round(min(execution_times), 5) if execution_times else 0,
                    'max_time': round(max(execution_times), 5) if execution_times else 0,
                })
        
        return {
            'queries': results,
            'total_executions': total_executions,
            'successful_executions': successful_executions,
            'failed_executions': failed_executions,
            'noise_executions': noise_executions,
            'noise_ratio_applied': self.noise_ratio if use_noise else 0.0,
            'total_time': round(total_time, 5),
            'ease_mode': ease_mode
        }
    
    def execute_time_dependent_benchmark(
        self,
        optimization_result: Dict,
        migration_sql_dir: Path,
        rewritten_queries_base_dir: Path,
        frequencies_by_timestep: Dict[str, List[float]],
        timeout_minutes: int = 30,
        verbose: bool = False,
        ease_mode: bool = False
    ) -> Dict:
        """Run the time-dependent benchmark.
        
        Args:
            optimization_result: Optimization result (including migration_analysis)
            migration_sql_dir: Directory containing the migration SQL
            rewritten_queries_base_dir: Base directory of the rewritten queries (e.g., jobs/)
            frequencies_by_timestep: Frequencies per time step
            timeout_minutes: Timeout (minutes)
            verbose: Whether to output detailed logs
            ease_mode: Ease mode (execute each query once and multiply the time by the frequency)
            
        Returns:
            Dict of benchmark results
        """
        print("DEBUG: execute_time_dependent_benchmark called")
        logger.info("Starting time-dependent benchmark execution")
        
        print("DEBUG: Getting migration_analysis and timesteps...")
        migration_analysis = optimization_result.get('migration_analysis', [])
        timesteps = optimization_result.get('timesteps', [])
        print(f"DEBUG: Got {len(migration_analysis)} migration_analysis entries, {len(timesteps)} timesteps")
        
        if not migration_analysis:
            logger.error("No migration_analysis found in optimization result")
            return {'error': 'No migration_analysis found'}
        
        print(f"DEBUG: About to log 'Found {len(timesteps)} timesteps to execute'")
        logger.info(f"Found {len(timesteps)} timesteps to execute")
        print("DEBUG: Logger.info completed")
        
        benchmark_start = time.time()
        timestep_results = []
        total_migration_time = 0.0
        total_query_time = 0.0
        
        print("DEBUG: Starting timestep loop...")
        # Execute each time step in order
        for t_idx, (timestep_name, timestep_info) in enumerate(zip(timesteps, migration_analysis)):
            logger.info(f"\n{'='*60}")
            logger.info(f"Timestep {t_idx}: {timestep_name}")
            logger.info(f"{'='*60}")
            
            timestep_start = time.time()
            
            # Execute the migration SQL (when t > 0)
            migration_time = 0.0
            migration_success = True
            migration_error = None
            
            if t_idx == 0:
                # Initial time step: create the initial MVs
                migration_sql_file = migration_sql_dir / f"timestep_{t_idx}_{timestep_name}.sql"
                
                if migration_sql_file.exists():
                    logger.info(f"Creating initial MVs from {migration_sql_file.name}...")
                    success, elapsed, error = self._execute_sql_file(migration_sql_file, 0)
                    migration_time = elapsed
                    migration_success = success
                    migration_error = error
                    
                    if success:
                        logger.info(f"  ✓ Initial MVs created ({elapsed:.2f}s)")
                    else:
                        logger.error(f"  ✗ Failed to create initial MVs: {error}")
                else:
                    logger.info(f"No initial migration SQL found (skipping)")
            else:
                # Migration between time steps
                migration_sql_file = migration_sql_dir / f"timestep_{t_idx}_{timestep_name}.sql"
                
                if migration_sql_file.exists():
                    logger.info(f"Executing migration SQL: {migration_sql_file.name}...")
                    success, elapsed, error = self._execute_sql_file(migration_sql_file, 0)
                    migration_time = elapsed
                    migration_success = success
                    migration_error = error
                    
                    if success:
                        logger.info(f"  ✓ Migration completed ({elapsed:.2f}s)")
                    else:
                        logger.error(f"  ✗ Migration failed: {error}")
                else:
                    logger.info(f"No migration SQL found for timestep {t_idx} (no changes)")
            
            total_migration_time += migration_time
            
            # Get the rewritten query files (per time step)
            rewritten_queries_dir = rewritten_queries_base_dir / f"timestep_{t_idx}_{timestep_name}"
            
            if not rewritten_queries_dir.exists():
                logger.error(f"Rewritten queries directory not found: {rewritten_queries_dir}")
                return {'error': f'Rewritten queries directory not found for timestep {timestep_name}'}
            
            # Helper for natural sort (to match io_loaders.py behavior)
            import re
            def natural_sort_key(s):
                return [int(text) if text.isdigit() else text.lower() for text in re.split("([0-9]+)", str(s))]
            
            query_files_for_timestep = sorted(rewritten_queries_dir.glob("*.sql"), key=lambda x: natural_sort_key(x.name))
            
            if not query_files_for_timestep:
                logger.error(f"No query files found in {rewritten_queries_dir}")
                return {'error': f'No query files found for timestep {timestep_name}'}
            
            logger.info(f"Executing queries for timestep {timestep_name}...")
            logger.info(f"  Using rewritten queries from: {rewritten_queries_dir}")
            logger.info(f"  Query count: {len(query_files_for_timestep)}")
            
            frequencies = frequencies_by_timestep.get(timestep_name, [1.0] * len(query_files_for_timestep))
            
            # Adjust the length of the frequency list
            if len(frequencies) < len(query_files_for_timestep):
                frequencies.extend([0.0] * (len(query_files_for_timestep) - len(frequencies)))
            elif len(frequencies) > len(query_files_for_timestep):
                frequencies = frequencies[:len(query_files_for_timestep)]
            
            query_results = self._execute_queries_with_frequency(
                query_files_for_timestep,
                frequencies,
                timeout_minutes,
                verbose,
                ease_mode
            )
            
            total_query_time += query_results['total_time']
            
            if ease_mode:
                timestep_elapsed = migration_time + query_results['total_time']
            else:
                timestep_elapsed = time.time() - timestep_start
            
            # Save the results for each time step
            timestep_result = {
                'timestep': timestep_name,
                'timestep_index': t_idx,
                'migration': {
                    'success': migration_success,
                    'time': round(migration_time, 5),
                    'error': migration_error,
                    'sql_file': str(migration_sql_file) if 'migration_sql_file' in locals() else None
                },
                'queries': query_results,
                'total_time': round(timestep_elapsed, 5),
            }
            
            timestep_results.append(timestep_result)
            
            # Show summary
            logger.info(f"\nTimestep {timestep_name} Summary:")
            logger.info(f"  Migration time: {migration_time:.2f}s")
            logger.info(f"  Query executions: {query_results['total_executions']}")
            logger.info(f"  Query time: {query_results['total_time']:.2f}s")
            logger.info(f"  Total timestep time: {timestep_elapsed:.2f}s")
        
        if ease_mode:
            benchmark_elapsed = total_migration_time + total_query_time
        else:
            benchmark_elapsed = time.time() - benchmark_start
        
        # Overall summary
        logger.info(f"\n{'='*60}")
        logger.info("Benchmark Summary:")
        logger.info(f"  Total timesteps: {len(timesteps)}")
        logger.info(f"  Total migration time: {total_migration_time:.2f}s")
        logger.info(f"  Total query time: {total_query_time:.2f}s")
        logger.info(f"  Total benchmark time: {benchmark_elapsed:.2f}s")
        logger.info(f"{'='*60}")
        
        return {
            'timesteps': timesteps,
            'timestep_results': timestep_results,
            'summary': {
                'total_timesteps': len(timesteps),
                'total_migration_time': round(total_migration_time, 5),
                'total_query_time': round(total_query_time, 5),
                'total_benchmark_time': round(benchmark_elapsed, 2),
            }
        }
    
    def execute_baseline_benchmark(
        self,
        query_files: List[Path],
        frequencies_by_timestep: Dict[str, List[float]],
        timesteps: List[str],
        timeout_minutes: int = 30,
        verbose: bool = False,
        ease_mode: bool = False
    ) -> Dict:
        """Baseline: execute queries without MVs.
        
        Args:
            query_files: List of query files
            frequencies_by_timestep: Frequencies per time step
            timesteps: List of time steps
            timeout_minutes: Timeout (minutes)
            verbose: Whether to output detailed logs
            ease_mode: Ease mode (execute each query once and multiply the time by the frequency)
            
        Returns:
            Dict of benchmark results
        """
        print("DEBUG: execute_baseline_benchmark called")
        logger.info("Starting baseline benchmark execution (no materialized views)")
        
        benchmark_start = time.time()
        timestep_results = []
        total_query_time = 0.0
        
        # Execute each time step in order (without MVs)
        for t_idx, timestep_name in enumerate(timesteps):
            logger.info(f"\n{'='*60}")
            logger.info(f"Timestep {t_idx}: {timestep_name}")
            logger.info(f"{'='*60}")
            
            timestep_start = time.time()
            
            logger.info(f"Executing queries for timestep {timestep_name} (no MVs)...")
            
            frequencies = frequencies_by_timestep.get(timestep_name, [1.0] * len(query_files))
            
            # Adjust the length of the frequency list
            if len(frequencies) < len(query_files):
                frequencies.extend([0.0] * (len(query_files) - len(frequencies)))
            elif len(frequencies) > len(query_files):
                frequencies = frequencies[:len(query_files)]
            
            query_results = self._execute_queries_with_frequency(
                query_files,
                frequencies,
                timeout_minutes,
                verbose,
                ease_mode
            )
            
            total_query_time += query_results['total_time']
            
            if ease_mode:
                timestep_elapsed = query_results['total_time']
            else:
                timestep_elapsed = time.time() - timestep_start
            
            timestep_result = {
                'timestep': timestep_name,
                'timestep_index': t_idx,
                'queries': query_results,
                'total_time': round(timestep_elapsed, 5),
            }
            
            timestep_results.append(timestep_result)
            
            logger.info(f"\nTimestep {timestep_name} Summary:")
            logger.info(f"  Query executions: {query_results['total_executions']}")
            logger.info(f"  Query time: {query_results['total_time']:.2f}s")
            logger.info(f"  Total timestep time: {timestep_elapsed:.2f}s")
        
        if ease_mode:
            benchmark_elapsed = total_query_time
        else:
            benchmark_elapsed = time.time() - benchmark_start
        
        logger.info(f"\n{'='*60}")
        logger.info("Baseline Benchmark Summary:")
        logger.info(f"  Total timesteps: {len(timesteps)}")
        logger.info(f"  Total query time: {total_query_time:.2f}s")
        logger.info(f"  Total benchmark time: {benchmark_elapsed:.2f}s")
        logger.info(f"{'='*60}")
        
        return {
            'mode': 'baseline',
            'timesteps': timesteps,
            'timestep_results': timestep_results,
            'summary': {
                'total_timesteps': len(timesteps),
                'total_query_time': round(total_query_time, 5),
                'total_benchmark_time': round(benchmark_elapsed, 2),
            }
        }
    
    def execute_static_mv_benchmark(
        self,
        optimization_result: Dict,
        migration_sql_dir: Path,
        rewritten_queries_base_dir: Path,
        frequencies_by_timestep: Dict[str, List[float]],
        timesteps: List[str] = None,
        timeout_minutes: int = 30,
        verbose: bool = False,
        static_algorithm: str = 'normal',
        ease_mode: bool = False
    ) -> Dict:
        """Static MV: create MVs at the first time step and run without migration.
        
        Args:
            optimization_result: Optimization result (including migration_analysis)
            migration_sql_dir: Directory containing the migration SQL
            rewritten_queries_base_dir: Base directory of the rewritten queries (e.g., jobs/)
            frequencies_by_timestep: Frequencies per time step
            timeout_minutes: Timeout (minutes)
            verbose: Whether to output detailed logs
            static_algorithm: Algorithm to use ('normal' or 'bigsubs')
            ease_mode: Ease mode (execute each query once and multiply the time by the frequency)
            
        Returns:
            Dict of benchmark results
        """
        print("DEBUG: execute_static_mv_benchmark called")
        logger.info("Starting static MV benchmark execution (initial MVs only, no migration)")
        
        migration_analysis = optimization_result.get('migration_analysis', [])
        # In static mode, migration_analysis may be absent (pure static optimization)
        is_pure_static = 'migration_analysis' not in optimization_result and 'selected_mvs' in optimization_result
        
        timesteps = optimization_result.get('timesteps', [])
        # For pure static optimization, timesteps may not be included, so get them from frequencies_by_timestep
        if not timesteps and frequencies_by_timestep:
            timesteps = sorted(frequencies_by_timestep.keys(), key=lambda x: int(x))
        
        if not migration_analysis and not is_pure_static:
            logger.error("No migration_analysis found in optimization result")
            return {'error': 'No migration_analysis found'}
        
        benchmark_start = time.time()
        timestep_results = []
        initial_mv_creation_time = 0.0
        total_query_time = 0.0
        
        # Create MVs at the first time step
        logger.info(f"\n{'='*60}")
        logger.info("Creating initial MVs (timestep 0)")
        logger.info(f"{'='*60}")
        
        if is_pure_static:
            # For pure static optimization, select the SQL file according to the algorithm
            if static_algorithm == 'bigsubs':
                migration_sql_file = migration_sql_dir / "static_bigsubs_initial_mvs.sql"
            else:
                migration_sql_file = migration_sql_dir / "static_initial_mvs.sql"
        else:
            # When using the first step of the conventional time-dependent optimization
            migration_sql_file = migration_sql_dir / f"timestep_0_{timesteps[0]}.sql"
        
        if migration_sql_file.exists():
            logger.info(f"Creating initial MVs from {migration_sql_file.name}...")
            success, elapsed, error = self._execute_sql_file(migration_sql_file, 0)
            initial_mv_creation_time = elapsed
            
            if success:
                logger.info(f"  ✓ Initial MVs created ({elapsed:.2f}s)")
            else:
                logger.error(f"  ✗ Failed to create initial MVs: {error}")
                return {'error': f'Failed to create initial MVs: {error}'}
        else:
            logger.warning(f"No initial migration SQL found: {migration_sql_file}")
        
        # Get the rewritten queries of the first time step (used for all time steps)
        # In static mode the MVs do not change, so the queries do not change either
        if is_pure_static:
            # For pure static optimization, rewritten_queries_base_dir is itself the query directory
            initial_rewritten_queries_dir = rewritten_queries_base_dir
        else:
            initial_rewritten_queries_dir = rewritten_queries_base_dir / f"timestep_0_{timesteps[0]}"
        
        if not initial_rewritten_queries_dir.exists():
            logger.error(f"Initial rewritten queries directory not found: {initial_rewritten_queries_dir}")
            return {'error': f'Initial rewritten queries directory not found'}
        
        # Helper for natural sort (to match io_loaders.py behavior)
        import re
        def natural_sort_key(s):
            return [int(text) if text.isdigit() else text.lower() for text in re.split("([0-9]+)", str(s))]
        
        static_query_files = sorted(initial_rewritten_queries_dir.glob("*.sql"), key=lambda x: natural_sort_key(x.name))
        
        if not static_query_files:
            logger.error(f"No query files found in {initial_rewritten_queries_dir}")
            return {'error': f'No initial query files found'}
        
        logger.info(f"Loaded {len(static_query_files)} queries from: {initial_rewritten_queries_dir}")
        logger.info(f"These queries will be used for all timesteps (MVs do not change)")
        
        # Execute queries at each time step (with the same MVs and queries)
        for t_idx, timestep_name in enumerate(timesteps):
            logger.info(f"\n{'='*60}")
            logger.info(f"Timestep {t_idx}: {timestep_name} (using initial MVs and queries)")
            logger.info(f"{'='*60}")
            
            timestep_start = time.time()
            
            logger.info(f"Executing queries for timestep {timestep_name}...")
            logger.info(f"  Using initial rewritten queries (timestep 0)")
            logger.info(f"  Query count: {len(static_query_files)}")
            
            frequencies = frequencies_by_timestep.get(timestep_name, [1.0] * len(static_query_files))
            
            # Adjust the length of the frequency list
            if len(frequencies) < len(static_query_files):
                frequencies.extend([0.0] * (len(static_query_files) - len(frequencies)))
            elif len(frequencies) > len(static_query_files):
                frequencies = frequencies[:len(static_query_files)]
            
            query_results = self._execute_queries_with_frequency(
                static_query_files,  # Always use the queries of the first time step
                frequencies,
                timeout_minutes,
                verbose,
                ease_mode
            )
            
            total_query_time += query_results['total_time']
            
            if ease_mode:
                timestep_elapsed = query_results['total_time']
            else:
                timestep_elapsed = time.time() - timestep_start
            
            timestep_result = {
                'timestep': timestep_name,
                'timestep_index': t_idx,
                'queries': query_results,
                'total_time': round(timestep_elapsed, 5),
            }
            
            timestep_results.append(timestep_result)
            
            logger.info(f"\nTimestep {timestep_name} Summary:")
            logger.info(f"  Query executions: {query_results['total_executions']}")
            logger.info(f"  Query time: {query_results['total_time']:.2f}s")
            logger.info(f"  Total timestep time: {timestep_elapsed:.2f}s")
        
        if ease_mode:
            benchmark_elapsed = total_query_time + initial_mv_creation_time
        else:
            benchmark_elapsed = time.time() - benchmark_start
        
        logger.info(f"\n{'='*60}")
        logger.info("Static MV Benchmark Summary:")
        logger.info(f"  Total timesteps: {len(timesteps)}")
        logger.info(f"  Initial MV creation time: {initial_mv_creation_time:.2f}s")
        logger.info(f"  Total query time: {total_query_time:.2f}s")
        logger.info(f"  Total benchmark time: {benchmark_elapsed:.2f}s")
        logger.info(f"{'='*60}")
        
        return {
            'mode': 'static',
            'timesteps': timesteps,
            'initial_mv_creation_time': round(initial_mv_creation_time, 5),
            'timestep_results': timestep_results,
            'summary': {
                'total_timesteps': len(timesteps),
                'initial_mv_creation_time': round(initial_mv_creation_time, 5),
                'total_query_time': round(total_query_time, 5),
                'total_benchmark_time': round(benchmark_elapsed, 2),
            }
        }
    
    def close(self):
        """Close the database connection"""
        if self.connection and not self.connection.closed:
            self.connection.close()
            logger.debug("Database connection closed")
