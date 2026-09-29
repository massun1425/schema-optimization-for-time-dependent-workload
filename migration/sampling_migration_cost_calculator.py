import json
import psycopg2
import re
import time
from pathlib import Path
from typing import Dict, Any, Tuple, List

from config.settings import Settings

class SamplingMigrationCostCalculator:
    """Class that estimates MV sizes using sampling"""

    # Table settings: {table_name: (alias, sampling_rate)}
    # Sampling rates are set in tiers according to the population size
    # Ordered by priority (tables on the many side first)
    TARGET_TABLES = {
        # === 1. Huge Fact Tables (1% sampling) ===
        "cast_info": ("ci", 0.01),          # 3.8GB, 36M rows - many side of title/name/char_name
        "movie_info": ("mi", 0.01),          # 1.9GB, 15M rows - many side of title
        
        # === 2. Medium Fact Tables (5% sampling) ===
        "movie_keyword": ("mk", 0.05),       # 361MB, 4.5M rows - many side of title/keyword
        "movie_companies": ("mc", 0.05),     # 282MB, 2.6M rows - many side of title/company_name
        "person_info": ("pi", 0.05),         # 550MB, 3.0M rows - many side of name
        "movie_info_idx": ("mi_idx", 0.05),  # 123MB, 1.4M rows - many side of title
        "aka_name": ("an", 0.05),            # 125MB, 901K rows - many side of name
        
        # === 3. Small Fact Tables (100% sampling = all rows) ===
        "aka_title": ("at", 1.0),           # 67MB, 361K rows - many side of title
        "complete_cast": ("cc", 1.0),       # 11MB, 135K rows - many side of title
        "movie_link": ("ml", 1.0),          # 3MB, 30K rows - many side of title
        
        # === 4. Entity/Dimension Tables (10% sampling) ===
        "title": ("t", 0.10),                # 368MB, 2.5M rows - master table
        "name": ("n", 0.10),                 # 552MB, 4.2M rows - master table
        "char_name": ("chn", 0.10),          # 373MB, 3.1M rows - dimension table
        
        # === 5. Small Dictionary Tables (100% sampling = all rows) ===
        "company_name": ("cn", 1.0),        # 31MB, 235K rows - dimension table
        "keyword": ("k", 1.0),              # 12MB, 134K rows - dimension table
        
        # === 6. Type Tables (100% sampling = all rows) ===
        "info_type": ("it", 1.0),            # 24kB, 113 rows
        "kind_type": ("kt", 1.0),            # 24kB, 7 rows
        "company_type": ("ct", 1.0),         # 24kB, 4 rows
        "role_type": ("rt", 1.0),            # 24kB, 12 rows
        "link_type": ("lt", 1.0),            # 24kB, 18 rows
        "comp_cast_type": ("cct", 1.0),      # 24kB, 4 rows
    }
    
    # Table list in priority order (used in _rewrite_query)
    TABLE_PRIORITY = [
        "cast_info", "movie_info", "movie_keyword", "movie_companies",
        "person_info", "movie_info_idx", "aka_name", "aka_title",
        "complete_cast", "movie_link", "title", "name", "char_name",
        "company_name", "keyword", "info_type", "kind_type",
        "company_type", "role_type", "link_type", "comp_cast_type"
    ]

    # Default settings (kept for compatibility)
    SAMPLING_RATE = 0.10  # Unused (each table has its own rate)
    SCALE_FACTOR = 1.0 / SAMPLING_RATE  # Unused
    OVERHEAD_MULTIPLIER = 1.0
    # EXPLAIN-based size estimates are typically 64x smaller than actual sizes
    # (based on analysis of 22 root nodes from JOB workload)
    EXPLAIN_SIZE_CORRECTION_FACTOR = 1 # 64

    def __init__(self, settings: Settings, query_set: str = "job_like", precomputed_costs_file: str = None,
                 exp_dir: str | Path | None = None):
        self.settings = settings
        self.query_set = query_set
        # Experiment directory holding 04_migration/ (default: the repository root)
        base_dir = Path(exp_dir) if exp_dir is not None else Path(__file__).parent.parent
        self.json_file_path = base_dir / "04_migration" / query_set / "simple_migration_plans.json"
        self.output_dir = self.json_file_path.parent
        self.plans = self._load_plans()
        self.costs = {}
        self.precomputed_costs_file = precomputed_costs_file

    def _load_plans(self) -> Dict[str, Any]:
        with open(self.json_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _get_connection(self):
        return psycopg2.connect(
            host=self.settings.database.host,
            port=self.settings.database.port,
            dbname=self.settings.database.database,
            user=self.settings.database.user,
            password=self.settings.database.password
        )

    def _run_sql(self, conn, sql_text):
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql_text)
            conn.commit()
            return True
        except Exception as e:
            print(f"Error running SQL: {sql_text}")
            print(str(e))
            conn.rollback()
            return False

    def create_sample_tables(self, conn):
        """Create sample tables (hash-based correlated sampling to prevent the zero-tuple problem)"""
        print("Dropping existing sample tables first...")
        self.drop_sample_tables(conn)
        
        print("Creating sample tables...")
        created_tables = []
        failed_tables = []
        
        for table, (alias, sampling_rate) in self.TARGET_TABLES.items():
            sample_table = f"sample_{table}"
            rate_percent = sampling_rate * 100
            print(f"  Creating {sample_table} ({rate_percent:.0f}% of {table})")
            
            # Create the table with hash-based sampling
            # Prefer columns likely to be join keys as the hash key
            hash_key = None
            if table in ["cast_info", "movie_info", "movie_keyword", "movie_companies", "movie_info_idx", "complete_cast", "movie_link", "aka_title"]:
                hash_key = "movie_id"
            elif table in ["person_info", "aka_name"]:
                hash_key = "person_id"
            elif table in ["title", "name", "char_name", "company_name", "keyword"]:
                hash_key = "id"
            
            if hash_key and sampling_rate < 1.0:
                # Correlated sampling (the same ID is always kept/dropped in every table)
                sql_text = f"""
                CREATE TABLE {sample_table} AS 
                SELECT * FROM {table} 
                WHERE mod(abs(hashtext({hash_key}::text)), 100) < {rate_percent};
                """
            elif sampling_rate < 1.0:
                # BERNOULLI when there is no join key or it is unknown
                sql_text = f"""
                CREATE TABLE {sample_table} AS SELECT * FROM {table} TABLESAMPLE BERNOULLI ({rate_percent});
                """
            else:
                # For 100%, copy all rows
                sql_text = f"""
                CREATE TABLE {sample_table} AS SELECT * FROM {table};
                """
                
            if self._run_sql(conn, sql_text):
                created_tables.append(sample_table)
                
                # Add the minimum indexes needed for JOINs
                index_sqls = []
                if table in ["title", "name", "char_name", "company_name", "keyword"]:
                    index_sqls.append(f"CREATE INDEX ON {sample_table}(id);")
                if table in ["cast_info", "movie_info", "movie_keyword", "movie_companies", "movie_info_idx", "complete_cast", "movie_link", "aka_title"]:
                    index_sqls.append(f"CREATE INDEX ON {sample_table}(movie_id);")
                if table in ["cast_info", "person_info", "aka_name"]:
                    index_sqls.append(f"CREATE INDEX ON {sample_table}(person_id);")
                if table == "movie_keyword":
                    index_sqls.append(f"CREATE INDEX ON {sample_table}(keyword_id);")
                if table == "movie_companies":
                    index_sqls.append(f"CREATE INDEX ON {sample_table}(company_id);")
                if table == "cast_info":
                    index_sqls.append(f"CREATE INDEX ON {sample_table}(person_role_id);")
                    index_sqls.append(f"CREATE INDEX ON {sample_table}(role_id);")
                
                for idx_sql in index_sqls:
                    self._run_sql(conn, idx_sql)
                
                self._run_sql(conn, f"ANALYZE {sample_table};")
            else:
                print(f"  Failed to create {sample_table}")
                failed_tables.append(sample_table)
        
        # Check the created tables
        print(f"\nSample table creation summary:")
        print(f"  Created: {len(created_tables)}/{len(self.TARGET_TABLES)}")
        if failed_tables:
            print(f"  Failed: {failed_tables}")
            return False
        
        # Check that they actually exist in the database
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'sample_%'")
                existing = {row[0] for row in cursor.fetchall()}
                missing = [t for t in created_tables if t not in existing]
                if missing:
                    print(f"  Warning: Some tables missing in DB: {missing}")
                    return False
                print(f"  All {len(created_tables)} sample tables verified in database.")
        except Exception as e:
            print(f"  Error verifying tables: {e}")
            conn.rollback()
        
        return True

    def drop_sample_tables(self, conn):
        print("Dropping sample tables...")
        for table in self.TARGET_TABLES.keys():
            sample_table = f"sample_{table}"
            self._run_sql(conn, f"DROP TABLE IF EXISTS {sample_table};")

    def _get_sample_estimate(self, conn, query) -> Tuple[int, int]:
        query = query.strip().rstrip(';')
        wrapped_query = f"""
        SELECT count(*), sum(pg_column_size(sub)) 
        FROM ({query}) as sub;
        """
        try:
            with conn.cursor() as cursor:
                cursor.execute(wrapped_query)
                result = cursor.fetchone()
                if result and len(result) >= 2:
                    rows = int(result[0]) if result[0] else 0
                    size = int(result[1]) if result[1] else 0
                    return rows, size
            return 0, 0
        except Exception as e:
            print(f"Error executing sample query: {e}")
            print(f"  Query: {query[:200]}...")
            conn.rollback()  # Roll back the transaction to clear the error state
            return 0, 0

    def _rewrite_query(self, query) -> Tuple[str, List[str], float]:
        """Replace as many tables in the query as possible with sample tables
        
        Returns:
            Tuple[str, List[str], float]: (rewritten query, list of replaced table names, overall scale factor)
            (None, [], 1.0) if nothing matches
        """
        new_query = query
        replaced_tables = set()
        
        for table in self.TABLE_PRIORITY:
            # Match table references in FROM/JOIN clauses
            pattern = re.compile(
                rf"(?:FROM|JOIN|,)\s+{table}\s+(?:AS\s+)?(\w+)\b",
                re.IGNORECASE
            )
            
            def replace_func(match):
                alias = match.group(1)
                prefix = match.group(0).split()[0]  # FROM, JOIN, or ,
                sample_table = f"sample_{table}"
                replaced_tables.add(table)
                return f"{prefix} {sample_table} AS {alias}"

            modified_query = pattern.sub(replace_func, new_query)
            if modified_query != new_query:
                new_query = modified_query
        
        if not replaced_tables:
            return None, [], 1.0
            
        # With correlated (hash-based) sampling, the match rate at JOINs is preserved,
        # so using the "smallest sampling rate (strongest compression)" as the base scale factor is closer to reality.
        # Plain BERNOULLI multiplication (1/(0.1*0.1) = 100) overestimates, so this was fixed.
        min_sampling_rate = 1.0
        for table in replaced_tables:
            rate = self.TARGET_TABLES[table][1]
            if rate < min_sampling_rate:
                min_sampling_rate = rate
                
        total_scale_factor = 1.0 / min_sampling_rate
        
        return new_query, list(replaced_tables), total_scale_factor
    
    def calculate_all_costs(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        if self.precomputed_costs_file:
            print(f"Using precomputed costs from: {self.precomputed_costs_file}")
            with open(self.precomputed_costs_file, 'r', encoding='utf-8') as f:
                self.costs = json.load(f)
            self.save_costs() # Ensure it's saved to the expected location for downstream phases
            return self.costs

        print("\n" + "="*70)
        print("Calculating migration costs using SAMPLING...")
        print("="*70)

        conn = self._get_connection()
        try:
            if not self.create_sample_tables(conn):
                print("Failed to create sample tables.")
                return {}

            total_nodes = len(self.plans)
            
            processed = 0
            updated_count = 0
            skipped_count = 0

            for node, plans in self.plans.items():
                processed += 1
                if processed % 10 == 0 or processed == total_nodes:
                    print(f"  Progress: {processed}/{total_nodes} ({processed*100//total_nodes}%)")

                self.costs[node] = {}

                for plan_key in sorted(plans.keys()):
                    sql = plans[plan_key]

                    if plan_key == "[]":
                        # Extract SELECT part
                        match = re.search(r"AS\s+(SELECT.*);", sql, re.IGNORECASE | re.DOTALL)
                        if not match:
                            match = re.search(r"AS\s+(SELECT.*)", sql, re.IGNORECASE | re.DOTALL)

                        est_rows = 0
                        est_size = 0
                        cost = 0.0

                        # Get the cost with EXPLAIN
                        try:
                            with conn.cursor() as cursor:
                                select_part = sql
                                if "CREATE MATERIALIZED VIEW" in sql:
                                    match_create = re.search(r"AS\s+(SELECT.*)", sql, re.IGNORECASE | re.DOTALL)
                                    if match_create:
                                        select_part = match_create.group(1)

                                cursor.execute(f"EXPLAIN (FORMAT JSON) {select_part}")
                                res = cursor.fetchone()
                                if res:
                                    plan = res[0][0]['Plan']
                                    cost = float(plan.get('Total Cost', 0.0))
                                    # Fallback values
                                    est_rows = int(plan.get('Plan Rows', 0))
                                    width = int(plan.get('Plan Width', 0))
                                    est_size = est_rows * width
                        except Exception:
                            conn.rollback()  # Roll back the transaction

                        select_query = match.group(1) if match else sql
                        size_source = "explain"

                        # Rewrite the query (replace all target tables)
                        rewritten_query, matched_tables, total_scale_factor_seq = self._rewrite_query(select_query)

                        if rewritten_query and matched_tables:
                            # Get the size from the sample
                            wrapped_query = f"""
                            SELECT count(*), sum(pg_column_size(sub)) 
                            FROM ({rewritten_query}) as sub;
                            """
                            try:
                                with conn.cursor() as cursor:
                                    cursor.execute("SET statement_timeout = '10s';")
                                    cursor.execute(wrapped_query)
                                    result = cursor.fetchone()
                                    if result and len(result) >= 2:
                                        rows = int(result[0]) if result[0] else 0
                                        size = int(result[1]) if result[1] else 0
                                        if rows > 0:
                                            est_rows = int(rows * total_scale_factor_seq)
                                            est_size = int(size * total_scale_factor_seq * self.OVERHEAD_MULTIPLIER)
                                            size_source = "sampling"  # Sampling succeeded
                                            updated_count += 1
                                        else:
                                            skipped_count += 1
                                    else:
                                        skipped_count += 1
                            except psycopg2.errors.QueryCanceled:
                                skipped_count += 1
                                pass # On timeout, silently fall back to EXPLAIN
                            except Exception:
                                skipped_count += 1
                                pass
                        else:
                            skipped_count += 1

                        # For EXPLAIN-based estimates, correct the size (accounting for the gap from actual sizes)
                        if size_source == "explain" and est_size > 0:
                            est_size = int(est_size * self.EXPLAIN_SIZE_CORRECTION_FACTOR)
                            est_rows = int(est_rows * self.EXPLAIN_SIZE_CORRECTION_FACTOR)

                        # Use the EXPLAIN cost as utility, and compute creation cost = read + write
                        # Write cost = page writes + tuple processing
                        write_pages = (est_size // 8192) + 1 if est_size > 0 else 0
                        write_cost = (write_pages * 1.0) + (est_rows * 0.01)  # SEQ_PAGE_COST + CPU_TUPLE_COST
                        creation_cost = cost + write_cost  # Read + write

                        self.costs[node][plan_key] = {
                            "cost": creation_cost,  # Creation cost (read + write)
                            "utility": cost,  # Utility (EXPLAIN cost = read only)
                            "rows": est_rows,
                            "width": int(est_size / est_rows) if est_rows > 0 else 0,
                            "size": est_size,
                            "size_source": size_source  # "sampling" or "explain"
                        }
                    else:
                        self.costs[node][plan_key] = {
                            "cost": 0.0,
                            "utility": 0.0,
                            "rows": 0,
                            "width": 0,
                            "size": 0
                        }
            
            print(f"\nProcessed {updated_count} MVs with sampling, Skipped/Fallback {skipped_count} MVs.")
            self.drop_sample_tables(conn)
            
        finally:
            conn.close()

        self.save_costs()
        return self.costs

    def save_costs(self, output_file: str = "simple_migration_costs.json"):
        try:
            output_path = self.output_dir / output_file
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self.costs, f, indent=2, ensure_ascii=False)
            print(f"Migration costs saved to: {output_path}")
        except Exception as e:
            print(f"Failed to save JSON file: {e}")
