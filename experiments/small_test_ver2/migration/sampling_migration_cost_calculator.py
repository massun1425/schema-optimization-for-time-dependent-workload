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
        # === Fact Tables (巨大・最重要) ===
        ("cast_info", "ci"),
        ("movie_info", "mi"),
        ("movie_companies", "mc"),
        ("movie_keyword", "mk"),
        ("movie_info_idx", "mi_idx"),
        ("person_info", "pi"),

        # === Entity Tables (中心となる実体) ===
        ("title", "t"),
        ("name", "n"),

        # === Dictionary/Dimension Tables (フィルタ条件の要) ===
        ("keyword", "k"),
        ("info_type", "it"),
        ("company_name", "cn"),
        ("company_type", "ct"),
        ("kind_type", "kt"),
        ("role_type", "rt"),
        ("char_name", "chn"),
        ("aka_name", "an"),

        # === Additional Tables (追加) ===
        ("movie_link", "ml"),
        ("link_type", "lt"),
        ("complete_cast", "cc"),
        ("comp_cast_type", "cct"),
        ("aka_title", "at"),
    ]

    # 小さいテーブル（数行〜数千行）はサンプリングせず全件使用
    SMALL_TABLES = {
        "info_type",      # 113行
        "kind_type",      # 7行
        "company_type",   # 4行
        "role_type",      # 12行
        "link_type",      # 18行
        "comp_cast_type", # 4行
    }

    SAMPLING_RATE = 0.10
    SCALE_FACTOR = 1.0 / SAMPLING_RATE
    OVERHEAD_MULTIPLIER = 1.2

    def __init__(self, settings: Settings, query_set: str = "job_like", precomputed_costs_file: str = None):
        self.settings = settings
        self.query_set = query_set
        self.json_file_path = Path(__file__).parent.parent / "04_migration" / query_set / "simple_migration_plans.json"
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
        """サンプルテーブルを作成（既存のものは削除）"""
        # まず既存のサンプルテーブルを削除
        print("Dropping existing sample tables first...")
        self.drop_sample_tables(conn)
        
        print("Creating sample tables...")
        created_tables = []
        failed_tables = []
        
        for table, _ in self.TARGET_TABLES:
            sample_table = f"sample_{table}"
            
            # 小さいテーブルは100%、それ以外はSAMPLING_RATE
            if table in self.SMALL_TABLES:
                rate = 100
                print(f"  Creating {sample_table} (100% - small table)")
            else:
                rate = self.SAMPLING_RATE * 100
                print(f"  Creating {sample_table} ({rate}% of {table})")
            
            sql_text = f"""
            CREATE TABLE {sample_table} AS SELECT * FROM {table} TABLESAMPLE BERNOULLI ({rate});
            ANALYZE {sample_table};
            """
            if self._run_sql(conn, sql_text):
                created_tables.append(sample_table)
            else:
                print(f"  Failed to create {sample_table}")
                failed_tables.append(sample_table)
        
        # 作成されたテーブルを確認
        print(f"\nSample table creation summary:")
        print(f"  Created: {len(created_tables)}/{len(self.TARGET_TABLES)}")
        if failed_tables:
            print(f"  Failed: {failed_tables}")
            return False
        
        # データベースで実際に存在するか確認
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
            print(f"Error executing sample query: {e}")
            print(f"  Query: {query[:200]}...")
            conn.rollback()  # トランザクションをロールバックしてエラー状態を解除
            return 0, 0

    def _rewrite_query(self, query) -> Tuple[str, str]:
        """クエリ内のテーブルをサンプルテーブルに置換（最初の1件のみ）
        
        TARGET_TABLESの順序で検索し、最初にマッチしたテーブルを
        サンプルテーブルに置換する。エイリアスは元のものを保持。
        
        Note: FROM/JOIN句のテーブル参照のみマッチし、
              SELECT句のカラム別名はマッチしない。
        
        Returns:
            Tuple[str, str]: (置換後のクエリ, 置換したテーブル名) 
            マッチしない場合は (None, None)
        """
        for table, _ in self.TARGET_TABLES:
            # SMALL_TABLESはサンプルテーブルも全件なのでスキップ不要だが、
            # 大きいテーブルを優先するためそのまま順序通り検索
            
            # FROM/JOIN句のテーブル参照にマッチ
            # パターン: FROM table AS alias / JOIN table AS alias / , table AS alias
            pattern = re.compile(
                rf"(?:FROM|JOIN|,)\s+{table}\s+(?:AS\s+)?(\w+)\b",
                re.IGNORECASE
            )
            match = pattern.search(query)
            if match:
                alias = match.group(1)  # 元のエイリアスを保持
                sample_table = f"sample_{table}"
                
                # マッチした部分の先頭（FROM/JOIN/,）を保持して置換
                matched_text = match.group(0)
                prefix = matched_text.split()[0]  # FROM, JOIN, or ,
                new_text = f"{prefix} {sample_table} AS {alias}"
                
                new_query = query[:match.start()] + new_text + query[match.end():]
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
            # === Fact Tables ===
            ("cast_info", "ci"),
            ("movie_info", "mi"),
            ("movie_companies", "mc"),
            ("movie_keyword", "mk"),
            ("movie_info_idx", "mi_idx"),
            ("person_info", "pi"),
            # === Entity Tables ===
            ("title", "t"),
            ("name", "n"),
            # === Dictionary Tables ===
            ("keyword", "k"),
            ("info_type", "it"),
            ("company_name", "cn"),
            ("company_type", "ct"),
            ("kind_type", "kt"),
            ("role_type", "rt"),
            ("char_name", "chn"),
            ("aka_name", "an"),
            # === Additional Tables ===
            ("movie_link", "ml"),
            ("link_type", "lt"),
            ("complete_cast", "cc"),
            ("comp_cast_type", "cct"),
            ("aka_title", "at"),
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
                    size_source = "explain"  # デフォルトはEXPLAIN
                    match = re.search(r"AS\s+(SELECT.*);", sql, re.IGNORECASE | re.DOTALL)
                    if not match:
                        match = re.search(r"AS\s+(SELECT.*)", sql, re.IGNORECASE | re.DOTALL)
                    
                    if match:
                        select_query = match.group(1)
                        
                        # クエリを書き換え（FROM/JOIN句のテーブル参照にマッチ）
                        matched_table = None
                        rewritten_query = None
                        for table, _ in target_tables:
                            # FROM/JOIN句のテーブル参照にマッチ
                            pattern = re.compile(
                                rf"(?:FROM|JOIN|,)\s+{table}\s+(?:AS\s+)?(\w+)\b",
                                re.IGNORECASE
                            )
                            match_result = pattern.search(select_query)
                            if match_result:
                                alias = match_result.group(1)  # 元のエイリアスを保持
                                sample_table = f"sample_{table}"
                                
                                # マッチした部分の先頭（FROM/JOIN/,）を保持して置換
                                matched_text = match_result.group(0)
                                prefix = matched_text.split()[0]  # FROM, JOIN, or ,
                                new_text = f"{prefix} {sample_table} AS {alias}"
                                
                                rewritten_query = select_query[:match_result.start()] + new_text + select_query[match_result.end():]
                                matched_table = table
                                break
                        
                        if rewritten_query:
                            
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
                                            size_source = "sampling"  # サンプリング成功
                            except Exception:
                                pass
                    
                    # EXPLAINのコストをutilityとし、作成コスト=読み取り+書き込みを計算
                    # 書き込みコスト = ページ書き込み + タプル処理
                    write_pages = (est_size // 8192) + 1 if est_size > 0 else 0
                    write_cost = (write_pages * 1.0) + (est_rows * 0.01)  # SEQ_PAGE_COST + CPU_TUPLE_COST
                    creation_cost = cost + write_cost  # 読み取り + 書き込み
                    
                    node_costs[plan_key] = {
                        "cost": creation_cost,  # 作成コスト（読み取り + 書き込み）
                        "utility": cost,  # 利得（EXPLAINコスト = 読み取りのみ）
                        "rows": est_rows,
                        "width": int(est_size / est_rows) if est_rows > 0 else 0,
                        "size": est_size,
                        "size_source": size_source  # "sampling" or "explain"
                    }
                else:
                    node_costs[plan_key] = {
                        "cost": 0.0,
                        "utility": 0.0,
                        "rows": 0,
                        "width": 0,
                        "size": 0
                    }
        
        finally:
            conn.close()
        
        return node, node_costs

    def calculate_all_costs(self, use_parallel: bool = False, max_workers: int = None) -> Dict[str, Dict[str, Dict[str, Any]]]:
        if self.precomputed_costs_file:
            print(f"Using precomputed costs from: {self.precomputed_costs_file}")
            with open(self.precomputed_costs_file, 'r', encoding='utf-8') as f:
                self.costs = json.load(f)
            self.save_costs() # Ensure it's saved to the expected location for downstream phases
            return self.costs

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
                                conn.rollback()  # トランザクションをロールバック

                            size_source = "explain"  # デフォルトはEXPLAIN
                            if match:
                                select_query = match.group(1)
                                rewritten_query, used_table = self._rewrite_query(select_query)
                                
                                if rewritten_query:
                                    rows, size = self._get_sample_estimate(conn, rewritten_query)
                                    if rows > 0:
                                        est_rows = int(rows * self.SCALE_FACTOR)
                                        est_size = int(size * self.SCALE_FACTOR * self.OVERHEAD_MULTIPLIER)
                                        size_source = "sampling"  # サンプリング成功
                                        updated_count += 1
                                    else:
                                        skipped_count += 1
                                else:
                                    skipped_count += 1
                            
                            # EXPLAINのコストをutilityとし、作成コスト=読み取り+書き込みを計算
                            # 書き込みコスト = ページ書き込み + タプル処理
                            write_pages = (est_size // 8192) + 1 if est_size > 0 else 0
                            write_cost = (write_pages * 1.0) + (est_rows * 0.01)  # SEQ_PAGE_COST + CPU_TUPLE_COST
                            creation_cost = cost + write_cost  # 読み取り + 書き込み
                            
                            self.costs[node][plan_key] = {
                                "cost": creation_cost,  # 作成コスト（読み取り + 書き込み）
                                "utility": cost,  # 利得（EXPLAINコスト = 読み取りのみ）
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
