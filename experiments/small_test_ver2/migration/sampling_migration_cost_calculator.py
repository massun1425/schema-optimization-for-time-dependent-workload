import json
import psycopg2
import re
import time
from pathlib import Path
from typing import Dict, Any, Tuple, List
from multiprocessing import Pool, cpu_count
from functools import partial

from config.settings import Settings

class SamplingMigrationCostCalculator:
    """サンプリングを使用してMVのサイズを推定するクラス"""

    TARGET_TABLES = [
        ("cast_info", "ci"),
        ("movie_info", "mi"),
        ("movie_companies", "mc"),
        ("person_info", "pi"),
        ("movie_keyword", "mk"),
        ("title", "t"),
        ("name", "n")
    ]

    SAMPLING_RATE = 0.01
    SCALE_FACTOR = 1.0 / SAMPLING_RATE
    OVERHEAD_MULTIPLIER = 1.2
    
    # PostgreSQLのコスト単位に合わせた書き込みコストパラメータ
    # postgresql.conf のデフォルト値を参考
    PAGE_SIZE = 8192            # PostgreSQLのページサイズ (8KB)
    SEQ_PAGE_COST = 1.0         # シーケンシャルページI/Oコスト
    CPU_TUPLE_COST = 0.01       # タプル処理コスト
    WRITE_PAGE_COST = 1.0       # 書き込みページコスト（読み取りと同程度と仮定）

    def __init__(self, settings: Settings, query_set: str = "job_like"):
        self.settings = settings
        self.query_set = query_set
        self.json_file_path = Path(__file__).parent.parent / "04_migration" / query_set / "simple_migration_plans.json"
        self.output_dir = self.json_file_path.parent
        self.plans = self._load_plans()
        self.costs = {}

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
        print("Creating sample tables...")
        for table, _ in self.TARGET_TABLES:
            sample_table = f"sample_{table}"
            # Check if table exists first to avoid errors on missing tables
            # But for now assuming tables exist as per original script
            print(f"  Creating {sample_table} ({self.SAMPLING_RATE * 100}% of {table})...")
            sql_text = f"""
            DROP TABLE IF EXISTS {sample_table};
            CREATE TABLE {sample_table} AS SELECT * FROM {table} TABLESAMPLE BERNOULLI ({self.SAMPLING_RATE * 100});
            ANALYZE {sample_table};
            """
            if not self._run_sql(conn, sql_text):
                print(f"  Failed to create {sample_table}")
                return False
        return True

    def drop_sample_tables(self, conn):
        print("Dropping sample tables...")
        for table, _ in self.TARGET_TABLES:
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
            # print(f"Error executing sample query: {e}")
            return 0, 0

    def _rewrite_query(self, query) -> Tuple[str, str]:
        best_table = None
        for table, alias in self.TARGET_TABLES:
            pattern = re.compile(f"\\b{table}\\s+(?:AS\\s+)?{alias}\\b", re.IGNORECASE)
            if pattern.search(query):
                best_table = (table, alias)
                break
        
        if best_table:
            table, alias = best_table
            sample_table = f"sample_{table}"
            pattern = re.compile(f"\\b{table}\\s+(?:AS\\s+)?{alias}\\b", re.IGNORECASE)
            new_query = pattern.sub(f"{sample_table} AS {alias}", query)
            return new_query, table
        
        return None, None
    
    @staticmethod
    def _process_single_node(args: Tuple[str, Dict, Settings, str, float, float]) -> Tuple[str, Dict[str, Dict[str, Any]]]:
        """単一ノードの処理（並列実行用の静的メソッド）"""
        node, plans, settings, query_set, sampling_rate, scale_factor = args
        
        # 新しい接続を作成（各プロセスで独立した接続が必要）
        conn = psycopg2.connect(
            host=settings.database.host,
            port=settings.database.port,
            dbname=settings.database.database,
            user=settings.database.user,
            password=settings.database.password
        )
        
        node_costs = {}
        overhead_multiplier = 1.2
        target_tables = [
            ("cast_info", "ci"),
            ("movie_info", "mi"),
            ("movie_companies", "mc"),
            ("person_info", "pi"),
            ("movie_keyword", "mk"),
            ("title", "t"),
            ("name", "n")
        ]
        
        try:
            for plan_key in sorted(plans.keys()):
                sql = plans[plan_key]
                
                if plan_key == "[]":
                    est_rows = 0
                    est_size = 0
                    cost = 0.0
                    
                    # EXPLAIN でコストを取得
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
                                est_rows = int(plan.get('Plan Rows', 0))
                                width = int(plan.get('Plan Width', 0))
                                est_size = est_rows * width
                    except Exception:
                        pass
                    
                    # サンプリングでサイズを推定
                    match = re.search(r"AS\s+(SELECT.*);", sql, re.IGNORECASE | re.DOTALL)
                    if not match:
                        match = re.search(r"AS\s+(SELECT.*)", sql, re.IGNORECASE | re.DOTALL)
                    
                    if match:
                        select_query = match.group(1)
                        
                        # クエリを書き換え
                        best_table = None
                        for table, alias in target_tables:
                            pattern = re.compile(f"\\b{table}\\s+(?:AS\\s+)?{alias}\\b", re.IGNORECASE)
                            if pattern.search(select_query):
                                best_table = (table, alias)
                                break
                        
                        if best_table:
                            table, alias = best_table
                            sample_table = f"sample_{table}"
                            pattern = re.compile(f"\\b{table}\\s+(?:AS\\s+)?{alias}\\b", re.IGNORECASE)
                            rewritten_query = pattern.sub(f"{sample_table} AS {alias}", select_query)
                            
                            # サンプルからサイズを取得
                            wrapped_query = f"""
                            SELECT count(*), sum(pg_column_size(sub)) 
                            FROM ({rewritten_query}) as sub;
                            """
                            try:
                                with conn.cursor() as cursor:
                                    cursor.execute(wrapped_query)
                                    result = cursor.fetchone()
                                    if result and len(result) >= 2:
                                        rows = int(result[0]) if result[0] else 0
                                        size = int(result[1]) if result[1] else 0
                                        if rows > 0:
                                            est_rows = int(rows * scale_factor)
                                            est_size = int(size * scale_factor * overhead_multiplier)
                            except Exception:
                                pass
                    
                    # 書き込みコストをPostgreSQLのコスト単位で計算
                    # write_cost = (pages * page_cost) + (rows * cpu_tuple_cost)
                    # サンプリングで得られた est_rows と est_size を使用
                    estimated_pages = est_size / SamplingMigrationCostCalculator.PAGE_SIZE
                    write_cost = (estimated_pages * SamplingMigrationCostCalculator.WRITE_PAGE_COST + 
                                  est_rows * SamplingMigrationCostCalculator.CPU_TUPLE_COST)
                    total_cost = cost + write_cost
                    
                    node_costs[plan_key] = {
                        "cost": total_cost,  # 読み取り + 書き込みコスト（PostgreSQL Cost Units）
                        "read_cost": cost,   # 元のEXPLAINコスト（読み取りのみ）
                        "write_cost": write_cost,  # 書き込みコスト（PostgreSQL Cost Units）
                        "rows": est_rows,
                        "width": int(est_size / est_rows) if est_rows > 0 else 0,
                        "size": est_size
                    }
                else:
                    node_costs[plan_key] = {
                        "cost": 0.0,
                        "rows": 0,
                        "width": 0,
                        "size": 0
                    }
        
        finally:
            conn.close()
        
        return node, node_costs

    def calculate_all_costs(self, use_parallel: bool = True, max_workers: int = None) -> Dict[str, Dict[str, Dict[str, Any]]]:
        print("\n" + "="*70)
        print(f"Calculating migration costs using SAMPLING ({'PARALLEL' if use_parallel else 'SEQUENTIAL'})...")
        print("="*70)

        conn = self._get_connection()
        try:
            if not self.create_sample_tables(conn):
                print("Failed to create sample tables.")
                return {}

            total_nodes = len(self.plans)
            
            if use_parallel:
                # 並列処理
                if max_workers is None:
                    max_workers = min(cpu_count(), total_nodes)
                
                print(f"  Using {max_workers} workers for parallel processing...")
                
                # 各ノードの処理用の引数を準備
                process_args = [
                    (node, plans, self.settings, self.query_set, self.SAMPLING_RATE, self.SCALE_FACTOR)
                    for node, plans in self.plans.items()
                ]
                
                # 並列実行
                with Pool(processes=max_workers) as pool:
                    results = []
                    for i, result in enumerate(pool.imap_unordered(self._process_single_node, process_args)):
                        results.append(result)
                        if (i + 1) % 10 == 0 or (i + 1) == total_nodes:
                            print(f"  Progress: {i + 1}/{total_nodes} ({(i + 1)*100//total_nodes}%)")
                
                # 結果をマージ
                for node, node_costs in results:
                    self.costs[node] = node_costs
                
                print(f"\nProcessed {total_nodes} MVs with parallel sampling.")
            
            else:
                # 逐次処理（元の実装）
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
                            
                            # EXPLAIN でコストを取得
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
                                pass

                            if match:
                                select_query = match.group(1)
                                rewritten_query, used_table = self._rewrite_query(select_query)
                                
                                if rewritten_query:
                                    rows, size = self._get_sample_estimate(conn, rewritten_query)
                                    if rows > 0:
                                        est_rows = int(rows * self.SCALE_FACTOR)
                                        est_size = int(size * self.SCALE_FACTOR * self.OVERHEAD_MULTIPLIER)
                                        updated_count += 1
                                    else:
                                        skipped_count += 1
                                else:
                                    skipped_count += 1
                            
                            # 書き込みコストをPostgreSQLのコスト単位で計算
                            # サンプリングで得られた est_rows と est_size を使用
                            estimated_pages = est_size / self.PAGE_SIZE
                            write_cost = (estimated_pages * self.WRITE_PAGE_COST + 
                                          est_rows * self.CPU_TUPLE_COST)
                            total_cost = cost + write_cost
                            
                            self.costs[node][plan_key] = {
                                "cost": total_cost,  # 読み取り + 書き込みコスト（PostgreSQL Cost Units）
                                "read_cost": cost,   # 元のEXPLAINコスト（読み取りのみ）
                                "write_cost": write_cost,  # 書き込みコスト（PostgreSQL Cost Units）
                                "rows": est_rows,
                                "width": int(est_size / est_rows) if est_rows > 0 else 0,
                                "size": est_size
                            }
                        else:
                            self.costs[node][plan_key] = {
                                "cost": 0.0,
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
