#!/usr/bin/env python3
"""
小規模実験 - 通常モード実行スクリプト

単一の頻度設定でMV最適化を実行します。

使い方:
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

# ロギング設定（プルーニングのログを表示するため）
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(name)s - %(message)s'
)

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from src.core.query_parser import QueryParser
from src.optimization.factory import OptimizerFactory
from src.utils.legacy import get_all_job_queries, natural_sort_key

# Docker/Local switching helper
experiment_dir = Path(__file__).parent.parent
sys.path.insert(0, str(experiment_dir))
from utils.postgres_executor import PostgresExecutor, add_docker_args


class NormalModeExperiment:
    """通常モード実験の段階的実行クラス"""
    
    def __init__(self, exp_dir: str = "experiments/small_test_ver2", query_set: str = "job", exp_suffix: str = "", use_docker: Optional[bool] = None, recalc_mode: bool = False):
        """初期化
        
        Args:
            exp_dir: 実験ディレクトリのパス
            query_set: 使用するクエリセット名 (例: job, job_like, explicit_join)
            exp_suffix: 実験識別用サフィックス (例: _16_2, _16_4)
            use_docker: Dockerを使用するかどうか (None: 環境変数から判定)
            recalc_mode: 再計算コストを使用するかどうか
        """
        self.exp_dir = Path(exp_dir)
        self.query_set = query_set  # クエリセット名を保存
        self.exp_suffix = exp_suffix  # サフィックスを保存
        self.recalc_mode = recalc_mode
        
        # PostgreSQL Executorを初期化
        self.pg_executor = PostgresExecutor(use_docker=use_docker)
        
        # config.yamlを使わず、settings.pyのデフォルト値を使用
        # デフォルト値:
        #   database.password: ""
        #   database.timeout: 1800
        #   optimization.storage_limit_mb: 50
        #   optimization.storage_limit_bytes: 52428800
        #   optimization.insert_queries: 1000
        self.settings = Settings()
        
        # 各ディレクトリのパス（クエリセット別）
        self.queries_dir = self.exp_dir / "01_queries" / self.query_set
        self.json_dir = self.exp_dir / "02_json" / self.query_set
        self.parsed_dir = self.exp_dir / "03_parsed" / self.query_set
        self.optimized_dir = self.exp_dir / "04_optimized" / self.query_set
        self.mv_sql_dir = self.exp_dir / "05_mv_sql" / self.query_set
        self.rewritten_dir = self.exp_dir / "06_rewritten" / self.query_set

        # pickleファイルも03_parsedフォルダ内にクエリセット別で保存
        self.pickle_path = self.parsed_dir / "qp_class.pkl"

        self.qp: Optional[QueryParser] = None
        self.result = None
        
        # 各フェーズの実行時間を記録
        self.phase_times = {}
        
        # クエリセットの存在確認
        if not self.queries_dir.exists():
            print(f"警告: クエリディレクトリが見つかりません: {self.queries_dir}")
            print(f"利用可能なクエリセット:")
            base_dir = self.exp_dir / "01_queries"
            if base_dir.exists():
                for d in base_dir.iterdir():
                    if d.is_dir():
                        print(f"  - {d.name}")
    
    def print_header(self, title: str, phase: int = 0):
        """フェーズヘッダーを表示"""
        print("\n" + "=" * 70)
        if phase > 0:
            print(f"フェーズ {phase}: {title}")
        else:
            print(title)
        print("=" * 70)
    
    def print_success(self, message: str):
        """成功メッセージを表示"""
        print(f"  [OK] {message}")
    
    def print_info(self, message: str):
        """情報メッセージを表示"""
        print(f"  → {message}")
    
    def print_error(self, message: str):
        """エラーメッセージを表示"""
        print(f"  [ERROR] {message}")
    
    def _drop_all_mvs(self):
        """既存のマテリアライズドビューを全て削除"""
        import psycopg2
        
        try:
            conn = psycopg2.connect(
                database=self.settings.database.database,
                user=self.settings.database.user,
                password=self.settings.database.password,
                host='localhost'
            )
            
            with conn.cursor() as cursor:
                # 既存のMVを取得
                cursor.execute("""
                    SELECT schemaname, matviewname 
                    FROM pg_matviews 
                    WHERE schemaname = 'public'
                """)
                mvs = cursor.fetchall()
                
                if not mvs:
                    self.print_info("削除するMVはありません")
                    conn.close()
                    return True
                
                # 全てのMVを削除
                dropped_count = 0
                for schema, mv_name in mvs:
                    try:
                        cursor.execute(f"DROP MATERIALIZED VIEW IF EXISTS {schema}.{mv_name} CASCADE;")
                        dropped_count += 1
                    except Exception as e:
                        self.print_error(f"  {mv_name}の削除に失敗: {e}")
            
            conn.commit()
            conn.close()
            
            self.print_success(f"{dropped_count}個の既存MVを削除完了")
            return True
            
        except Exception as e:
            self.print_error(f"MV削除エラー: {e}")
            return False
    
    def _analyze_base_tables(self):
        """ベーステーブルに対してANALYZEを実行"""
        import psycopg2
        
        # 主要なベーステーブルのリスト
        base_tables = [
            'title', 'cast_info', 'movie_info', 'movie_companies',
            'movie_keyword', 'name', 'person_info', 'keyword',
            'company_name', 'company_type', 'info_type', 'kind_type',
            'role_type', 'movie_info_idx'
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
                # 統計情報のターゲットを引き上げる（デフォルト100 -> 1000）
                # これによりヒストグラムの粒度が上がり、JOBのような偏ったデータの推定精度が向上する
                # try:
                #     cursor.execute("SET default_statistics_target = 1000;")
                #     self.print_info("統計情報のターゲットを1000に設定しました")
                # except Exception as e:
                #     self.print_info(f"統計情報のターゲット設定に失敗（デフォルトを使用）: {e}")
                
                for table in base_tables:
                    try:
                        cursor.execute(f"ANALYZE {table};")
                        analyzed_count += 1
                    except Exception:
                        pass  # テーブルが存在しない場合はスキップ
            
            conn.commit()
            conn.close()
            
            self.print_success(f"{analyzed_count}個のベーステーブルをANALYZE完了")
            return True
            
        except Exception as e:
            self.print_error(f"ANALYZE実行エラー: {e}")
            return False

    def _update_u_ij_if_recalc(self):
        """--recalcモードが有効な場合、コストを読み込んでu_ijを更新する
        
        Returns:
            Tuple[Dict[int, float], List[float]]: (migration_cost, b_j) 
            recalcが無効な場合は (None, None) を返す
        """
        if not self.recalc_mode:
            return None, None
            
        from experiments.small_test_ver2.core.io_loaders import load_full_build_costs_and_sizes
        
        self.print_info("RECALC MODE: u_ij（利得）を utility で上書き中...")
        migration_cost, utilities, b_j = load_full_build_costs_and_sizes(
            str(self.exp_dir), 
            self.qp.node_list, 
            self.query_set
        )
        
        updated_count = 0
        for i in range(len(self.qp.u_ij)):
            for j in range(len(self.qp.u_ij[i])):
                # 既存の構造（使用関係）がある場所のみ更新
                if self.qp.u_ij[i][j] > 0:
                    # utilities を使って利得を更新（migration_cost ではなく）
                    if j in utilities:
                        self.qp.u_ij[i][j] = utilities[j]
                        updated_count += 1
                        
        self.print_success(f"  {updated_count}箇所の利得エントリを更新しました")
        return migration_cost, b_j  # migration_cost はそのまま返す（作成コスト用）
    
    def _clear_caches(self):
        """PostgreSQLのキャッシュをクリア
        
        pg_prewarm拡張のpg_drop_caches()を使用してshared_buffersをクリアします。
        PostgreSQL 14以降で利用可能。古いバージョンでは警告を出してスキップします。
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
                # まずpg_prewarm拡張を確認・作成
                try:
                    cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_prewarm;")
                    conn.commit()
                except Exception:
                    pass  # 権限がない場合はスキップ
                
                # pg_drop_caches()を実行してshared_buffersをクリア
                try:
                    cursor.execute("SELECT pg_drop_caches();")
                    conn.commit()
                    self.print_success("PostgreSQLキャッシュをクリア完了")
                except psycopg2.errors.UndefinedFunction:
                    # pg_drop_caches()が存在しない（PostgreSQL 14未満）
                    self.print_info("pg_drop_caches()は利用不可（PostgreSQL 14+が必要）")
                    # 代替手段: DISCARDコマンドでセッションキャッシュをクリア
                    try:
                        cursor.execute("DISCARD ALL;")
                        conn.commit()
                        self.print_info("セッションキャッシュをクリア（DISCARD ALL）")
                    except Exception:
                        pass
                except Exception as e:
                    self.print_info(f"キャッシュクリアをスキップ: {e}")
            
            conn.close()
            return True
            
        except Exception as e:
            self.print_error(f"キャッシュクリアエラー: {e}")
            return False
    
    def _create_extended_statistics(self):
        """JOBクエリの推定精度向上のための多変量統計情報（Extended Statistics）を作成
        
        PostgreSQLプランナーが列間の相関を理解できるようにするために、
        複数列の依存関係とMCV（Most Common Values）統計を作成します。
        これにより、複雑なWHERE句を持つクエリの行数推定精度が向上し、
        より適切な結合順序が選択されます。
        """
        import psycopg2
        
        # 作成する統計情報のリスト
        # (統計名, 統計タイプ, 対象カラム, テーブル名)
        extended_stats = [
            # ===== 基本的な2カラム相関 =====
            # movie_info: info_type_id と info の相関（29c, 25cなどに効果）
            ("stts_movie_info_corr", "(dependencies, mcv)", "info_type_id, info", "movie_info"),
            
            # cast_info: 役割と注釈の相関（10c, 25c, 20a, 7cなどに効果）
            ("stts_cast_info_note", "(dependencies, mcv)", "role_id, note", "cast_info"),
            ("stts_cast_info_role_note", "(dependencies, mcv)", "person_role_id, note", "cast_info"),
            
            # title: 種類と制作年の相関（29c, 10c, 7c, 20aなどに効果）
            ("stts_title_kind_year", "(dependencies, mcv)", "kind_id, production_year", "title"),
            
            # movie_companies: 会社IDと役割の相関（17a-f, 16bなどに効果）
            ("stts_movie_companies_corr", "(dependencies, mcv)", "company_id, company_type_id", "movie_companies"),
            
            # person_info: 情報タイプと内容の相関（29c, 7cに効果）
            ("stts_person_info_corr", "(dependencies, mcv)", "info_type_id, info", "person_info"),
            
            # ===== 結合ハブテーブルの相関（結合順序改善用）=====
            # movie_keyword: 映画とキーワードの相関（結合の中間結果推定に効果）
            ("stts_mk_movie_keyword", "(dependencies, mcv)", "movie_id, keyword_id", "movie_keyword"),
            
            # movie_info_idx: 25cなどで使用されるインデックステーブル
            ("stts_mi_idx_corr", "(dependencies, mcv)", "info_type_id, info", "movie_info_idx"),
            
            # ===== 2カラム結合統計（3カラムは分解して使用）=====
            # movie_info: 映画ID・情報タイプの2カラム相関
            ("stts_mi_movie_info", "(dependencies, mcv)", "movie_id, info_type_id", "movie_info"),
            
            # cast_info: 3カラムはMCV漏れリスクがあるため削除
            # 代わりに既存の2カラム統計 (stts_ci_join_corr) を使用
            
            # movie_companies: 映画・会社・会社種別の3カラム相関
            ("stts_mc_movie_company", "(dependencies, mcv)", "movie_id, company_id, company_type_id", "movie_companies"),
            
            # movie_info_idx: 3カラムはMCV漏れリスクがあるため削除
            # 代わりに stts_mi_idx_corr の2カラム統計を使用
            
            # ===== name/aka_name 関連 =====
            # name: IDと性別の相関（29c, 7cのフィルタに効果）
            ("stts_name_gender", "(dependencies, mcv)", "id, gender", "name"),
            
            # ===== マスターテーブル（小さいが頻繁にフィルタされる）=====
            # keyword: キーワードのIDと名前（29c, 6f等でフィルタに使用）
            ("stts_keyword_id", "(dependencies, mcv)", "id, keyword", "keyword"),
            
            # info_type: 情報タイプのIDと名前（it.info='genres', 'rating'等のフィルタ）
            ("stts_info_type_id", "(dependencies, mcv)", "id, info", "info_type"),
            
            # company_name: 会社名と国コード（cn.country_code='[us]'等のフィルタ）
            ("stts_company_name_id", "(dependencies, mcv)", "id, country_code", "company_name"),
            
            # kind_type: 種類のIDと名前（kt.kind='movie'等のフィルタ）
            ("stts_kind_type_id", "(dependencies, mcv)", "id, kind", "kind_type"),
            
            # ===== 追加の結合テーブル =====
            # movie_link: ユニーク値同士の相関は効果が薄いため削除
            
            # aka_name: 人物別名検索（person_idとの相関）
            ("stts_aka_name_person", "(dependencies, mcv)", "person_id, name", "aka_name"),
            
            # person_info: 人物IDと情報タイプの相関
            ("stts_person_info_person", "(dependencies, mcv)", "person_id, info_type_id", "person_info"),
            
            # ===== 3カラム統計（安全なもののみ）=====
            # title: ID・種類・制作年の3カラム（結合キー＋フィルタの組み合わせ）
            ("stts_title_id_kind_year", "(dependencies, mcv)", "id, kind_id, production_year", "title"),
            
            # complete_cast: 出演情報（29c, 20a等で使用）
            ("stts_cc_complete_cast", "(dependencies, mcv)", "movie_id, subject_id, status_id", "complete_cast"),

            # ===== フィルタ列＋結合キーの相関（ndistinct推定精度向上用）=====
            # title: 年代とIDの相関（29c等、年代フィルタ後の結合に効果）
            ("stts_title_join_corr", "(dependencies, mcv)", "production_year, id", "title"),
            
            # movie_info: stts_mi_movie_info で代用（重複削除）
            
            # cast_info: 役割と映画IDの相関
            ("stts_ci_join_corr", "(dependencies, mcv)", "role_id, movie_id", "cast_info"),
            
            # char_name: 名前とIDの相関（NOT LIKE等の否定条件や部分一致の推定向上用）
            ("stts_chn_name_corr", "(dependencies, mcv)", "name, id", "char_name"),
            
            # ===== マスタテーブルの関数従属性 =====
            # 小さいテーブルなので標準統計で十分だが、害もないためキープ
            # role_type: 役割名とIDの完全従属
            ("stts_role_type_id", "(dependencies, mcv)", "id, role", "role_type"),
            
            # comp_cast_type: 種類名とIDの完全従属
            ("stts_comp_cast_type_id", "(dependencies, mcv)", "id, kind", "comp_cast_type"),
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
                        # 既存の統計情報をドロップ（存在する場合）
                        cursor.execute(f"DROP STATISTICS IF EXISTS {stat_name};")
                        
                        # 新しい統計情報を作成
                        sql = f"CREATE STATISTICS {stat_name} {stat_type} ON {columns} FROM {table};"
                        cursor.execute(sql)
                        created_count += 1
                        
                    except psycopg2.errors.UndefinedTable:
                        # テーブルが存在しない場合はスキップ
                        conn.rollback()
                        skipped_count += 1
                    except psycopg2.errors.UndefinedColumn:
                        # カラムが存在しない場合はスキップ
                        conn.rollback()
                        skipped_count += 1
                    except Exception as e:
                        # その他のエラーはログに記録してスキップ
                        conn.rollback()
                        self.print_info(f"  統計 {stat_name} の作成をスキップ: {e}")
                        skipped_count += 1
                
                conn.commit()
            
            conn.close()
            
            if created_count > 0:
                self.print_success(f"{created_count}個の拡張統計情報を作成完了")
                if skipped_count > 0:
                    self.print_info(f"  {skipped_count}個はスキップ（テーブルまたはカラムが存在しない）")
            else:
                self.print_info("拡張統計情報の作成をスキップ（対象テーブルが存在しない）")
            
            return True
            
        except Exception as e:
            self.print_error(f"拡張統計情報作成エラー: {e}")
            return False
    
    def phase1_generate_explain_json(self):
        """フェーズ1: EXPLAIN JSON 生成"""
        self.print_header("EXPLAIN JSON 生成", 1)
        
        # 既存のMVを全て削除
        self.print_info("既存のMVをクリーンアップ中...")
        if not self._drop_all_mvs():
            self.print_error("MVの削除に失敗しました")
            # 失敗しても続行（警告のみ）
        
        # ベーステーブルのANALYZEを実行
        self.print_info("ベーステーブルの統計情報を更新中...")
        if not self._analyze_base_tables():
            self.print_error("ベーステーブルのANALYZEに失敗しました")
            # 失敗しても続行（警告のみ）
        
        # # 拡張統計情報（Extended Statistics）を作成
        # # JOBクエリの結合順序推定精度を向上させるための多変量統計
        # self.print_info("拡張統計情報を作成中...")
        # if not self._create_extended_statistics():
        #     self.print_error("拡張統計情報の作成に失敗しました")
        #     # 失敗しても続行（警告のみ）
        
        # # 拡張統計情報を計算するためにANALYZEを再実行
        # self.print_info("拡張統計情報を計算するためANALYZEを再実行中...")
        # if not self._analyze_base_tables():
        #     self.print_error("ANALYZEの再実行に失敗しました")
        
        # PostgreSQLキャッシュをクリア
        self.print_info("PostgreSQLキャッシュをクリア中...")
        self._clear_caches()
        # クリーンアップが完了してから計測開始
        phase_start = time.time()
        
        # クエリディレクトリの確認
        if not self.queries_dir.exists():
            self.print_error(f"クエリディレクトリが見つかりません: {self.queries_dir}")
            return False
        
        query_files = sorted(self.queries_dir.glob("*.sql"))
        
        if not query_files:
            self.print_error(f"{self.queries_dir} にクエリファイルが見つかりません")
            return False
        
        self.print_info(f"クエリセット: {self.query_set}")
        self.print_info(f"{len(query_files)}個のクエリファイルを処理します")
        
        # 出力ディレクトリを作成(クエリセット別)
        self.json_dir.mkdir(parents=True, exist_ok=True)
        
        for query_file in query_files:
            output_file = self.json_dir / f"{query_file.stem}.json"
            
            self.print_info(f"処理中: {query_file.name}")
            
            # クエリを読み込み（コメント行を除去）
            with open(query_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            query_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped and not stripped.startswith('--'):
                    query_lines.append(line)
            
            query_sql = ''.join(query_lines).strip()
            
            # EXPLAIN JSON を実行（Bitmap Scanを無効化）
            # SET文とEXPLAINを分けて実行し、EXPLAIN結果のみを取得
            
            try:
                result = self.pg_executor.run_explain_json(
                    query_sql,
                    database=self.settings.database.database,
                    set_options=["SET enable_bitmapscan = off;"]
                )
                
                # 出力から最後のJSON部分のみを抽出（SET文の出力を除外）
                output_lines = result.stdout.strip().split('\n')
                # "SET"行を除外してJSONのみを取得
                json_lines = [line for line in output_lines if line and line != 'SET']
                json_text = '\n'.join(json_lines)
                json_data = json.loads(json_text)
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, indent=2, ensure_ascii=False)
                
                self.print_success(f"{output_file.name} を生成")
                
            except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
                self.print_error(f"{query_file.name} の処理に失敗: {e}")
                return False
        
        return True
    
    def phase2_parse_queries(self):
        """フェーズ2: クエリパース（頻度重み付けを行わないように変更済み）"""
        self.print_header("クエリパース", 2)
        phase_start = time.time()
        
        # from experiments.small_test_ver2.frequency_weighted_parser import FrequencyWeightedParser
        
        # self.print_info("FrequencyWeightedParser を初期化")
        
        # frequency_file = self.queries_dir / "frequency.json"
        
        # if frequency_file.exists():
           # self.print_info(f"頻度情報ファイル: {frequency_file}")
           # self.qp = FrequencyWeightedParser(self.settings, str(frequency_file))
    
        # self.print_info("頻度情報ファイルが見つかりません。通常のパーサーを使用")
        self.qp = QueryParser(self.settings)
        
        self.print_info("クエリをパース中...")
        try:
            query_dir = str(self.json_dir)
            
            # JSONファイルの確認
            json_files = list(self.json_dir.glob("*.json"))
            self.print_info(f"検出されたJSONファイル: {len(json_files)}個")
            if json_files:
                self.print_info(f"  例: {json_files[0].name}")
            
            # モンキーパッチ: query_parser モジュール内の get_all_job_queries を置き換え
            # この部分ややこしいから簡単にしたいけどquery_parser.pyをいじる必要がある
            import src.core.query_parser as qp_module
            original_get_all_job_queries = qp_module.get_all_job_queries
            
            def custom_get_all_job_queries(path):
                """カスタム関数: 指定ディレクトリから直接JSONファイルを取得"""
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
                
                # 自然順でソート
                json_files = sorted(job_dir.glob("*.json"), key=lambda x: natural_sort_key(x.name))
                
                for json_file in json_files:
                    query_path = str(json_file)
                    query_paths.append(query_path)
                    query_count[query_path] = 1
                
                print(f"  [DEBUG] Found {len(query_paths)} JSON files (sorted naturally)")
                return query_paths, query_count
            
            # query_parser モジュール内の参照を置き換え
            qp_module.get_all_job_queries = custom_get_all_job_queries
            
            try:
                self.qp.query_parse(
                    q_num=0,
                    path=str(self.json_dir),
                    insert_query=self.settings.optimization.insert_queries
                )
            finally:
                # 元の関数に戻す
                qp_module.get_all_job_queries = original_get_all_job_queries
            
            insert_query = self.settings.optimization.insert_queries
            
            #if isinstance(self.qp, FrequencyWeightedParser):
             #   self.qp.apply_frequency_weights(files)
              #  self.qp.calculate_maintenance_costs(insert_query)
            
            self.print_success(f"{len(self.qp.query)}個のクエリをパース完了")
            self.print_info(f"  リーフノード数: {len(self.qp.qm.leaf_nodes_map)}")
            self.print_info(f"  非リーフノード数: {len(self.qp.qm.non_leaf_nodes_map)}")
            self.print_info(f"  総ノード数: {self.qp.s_num}")
            
            self._save_parse_results()
            
            # フェーズ時間を記録
            self.phase_times['phase2_parse'] = time.time() - phase_start
            
            return True
            
        except Exception as e:
            self.print_error(f"クエリパースに失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
    
# フェーズ2.5のみ実行
# python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 2.5 --query-set job

    def phase3_annotate_json(self):
        """フェーズ3: JSONファイルへのノードID付加"""
        self.print_header("JSONファイルへのノードID付加", 3)
        phase_start = time.time()
        
        if self.qp is None:
            if not self.pickle_path.exists():
                self.print_error(f"{self.pickle_path} が見つかりません")
                self.print_info("先にフェーズ2を実行してください")
                return False
            
            self.print_info(f"パース結果を読み込み中: {self.pickle_path}")
            try:
                with open(self.pickle_path, 'rb') as f:
                    self.qp = pickle.load(f)
                self.print_success(f"{self.qp.s_num}個のノードを読み込み完了")
            except Exception as e:
                self.print_error(f"パース結果の読み込みに失敗: {e}")
                return False
        
        # JSONファイルの一覧を取得
        json_files = sorted(self.json_dir.glob("*.json"))
        
        if not json_files:
            self.print_error(f"{self.json_dir} にJSONファイルが見つかりません")
            return False
        
        self.print_info(f"{len(json_files)}個のJSONファイルを処理します")
        
        try:
            from src.core.parse_exporter import ParseExporter
            
            # ParseExporterを初期化
            exporter = ParseExporter(self.qp.qm)
            
            # JSONファイルを直接上書きする（output_dirを同じディレクトリに設定）
            self.print_info("ノードIDを付加中...")
            
            # 一時ディレクトリに出力してから上書き
            temp_dir = self.json_dir.parent / f".temp_{self.query_set}"
            
            # 注釈付きファイルを一時ディレクトリに出力
            exporter.annotate_query_files(
                [str(f) for f in json_files],
                temp_dir
            )
            
            # 一時ディレクトリから元の場所に移動（上書き）
            annotated_files = list(temp_dir.glob("*.json"))
            for annotated_file in annotated_files:
                target_file = self.json_dir / annotated_file.name
                import shutil
                shutil.move(str(annotated_file), str(target_file))
            
            # 一時ディレクトリを削除
            if temp_dir.exists():
                import shutil
                shutil.rmtree(temp_dir)
            
            self.print_success(f"{len(json_files)}個のJSONファイルにノードIDを付加完了")
            self.print_info(f"  更新先: {self.json_dir}")
            
            # フェーズ時間を記録
            self.phase_times['phase3_annotate_json'] = time.time() - phase_start
            
            return True
            
        except Exception as e:
            self.print_error(f"ノードID付加に失敗: {e}")
            import traceback
            traceback.print_exc()
            
            # エラー時に一時ディレクトリをクリーンアップ
            if temp_dir.exists():
                import shutil
                shutil.rmtree(temp_dir)
            
            return False
    
    def _save_parse_results(self):
        """パース結果を保存"""
        # pickleファイル保存先のディレクトリを作成
        self.pickle_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.pickle_path, 'wb') as f:
            pickle.dump(self.qp, f)
        
        self.print_success(f"パース結果を {self.pickle_path} に保存")
        
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
        
        self.print_success(f"サマリーを {summary_path} に保存")
    
    def phase4_enumerate_migration_plans(self):
        """フェーズ4: マイグレーションプラン列挙"""
        self.print_header("マイグレーションプラン列挙", 4)
        phase_start = time.time()
        
        if self.qp is None:
            if not self.pickle_path.exists():
                self.print_error(f"{self.pickle_path} が見つかりません")
                self.print_info("先にフェーズ2を実行してください")
                return False
            
            self.print_info(f"パース結果を読み込み中: {self.pickle_path}")
            try:
                with open(self.pickle_path, 'rb') as f:
                    self.qp = pickle.load(f)
                self.print_success(f"{self.qp.s_num}個のノードを読み込み完了")
            except Exception as e:
                self.print_error(f"パース結果の読み込みに失敗: {e}")
                return False
        
        try:
            from experiments.small_test_ver2.migration.enumerate_simple_migration_plan import GetSimpleMigrationPlans
            
            self.print_info("マイグレーションプランを列挙中...")
            
            # GetSimpleMigrationPlansのインスタンスを作成
            migrator = GetSimpleMigrationPlans(
                settings=self.settings,
                query_set=self.query_set
            )
            
            # マイグレーションプランを取得・保存
            migrator.get_migration_sqls()
            
            # 出力ファイルのパスを確認
            output_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_plans.json"
            
            if output_file.exists():
                self.print_success(f"マイグレーションプランを保存: {output_file}")
                
                # ファイルの統計情報を表示
                with open(output_file, 'r', encoding='utf-8') as f:
                    plans = json.load(f)
                self.print_info(f"  {len(plans)}個のノードのプランを生成")
            else:
                self.print_error("マイグレーションプランファイルが見つかりません")
                return False
            
            # フェーズ時間を記録
            self.phase_times['phase4_migration_plans'] = time.time() - phase_start
            
            return True
            
        except Exception as e:
            self.print_error(f"マイグレーションプラン列挙に失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def phase5_calculate_migration_costs(self, use_neurocard=False, use_deepdb=False, use_sampling=True, sampling_parallel=False, sampling_workers=None, compare=False):
        """フェーズ5: マイグレーションコスト計算"""
        self.print_header("マイグレーションコスト計算", 5)
        phase_start = time.time()
        
        # マイグレーションプランファイルの存在確認
        plans_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_plans.json"
        
        if not plans_file.exists():
            self.print_error("マイグレーションプランが見つかりません")
            self.print_info("先にフェーズ2.7を実行してください")
            return False
        
        try:
            if use_neurocard:
                from experiments.small_test_ver2.migration.neurocard_migration_cost_calculator import NeuroCardMigrationCostCalculator
                CalculatorClass = NeuroCardMigrationCostCalculator
                self.print_info("NeuroCardを使用してサイズ推定を行います")
            elif use_deepdb:
                from experiments.small_test_ver2.migration.deepdb_migration_cost_calculator import DeepDBMigrationCostCalculator
                CalculatorClass = DeepDBMigrationCostCalculator
                self.print_info("DeepDBを使用してサイズ推定を行います")
            elif use_sampling:
                from experiments.small_test_ver2.migration.sampling_migration_cost_calculator import SamplingMigrationCostCalculator
                CalculatorClass = SamplingMigrationCostCalculator
                self.print_info("サンプリングを使用してサイズ推定を行います")
            else:
                from experiments.small_test_ver2.migration.simple_migration_cost_calculator import SimpleMigrationCostCalculator
                CalculatorClass = SimpleMigrationCostCalculator

            
            self.print_info("マイグレーションコストを計算中...")
            
            # CostCalculatorのインスタンスを作成
            if self.recalc_mode and use_sampling:
                recalc_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_costs.json"
                # SamplingMigrationCostCalculatorのみがprecomputed_costs_fileを受け取る
                calculator = CalculatorClass(
                    settings=self.settings,
                    query_set=self.query_set,
                    precomputed_costs_file=str(recalc_file)
                )
            else:
                calculator = CalculatorClass(
                    settings=self.settings,
                    query_set=self.query_set
                )
            
            if compare and use_deepdb:
                self.print_info("PostgreSQL と DeepDB の推定値を比較します")
                calculator.compare_with_postgresql()
                # 比較のみの場合はここで終了（コスト保存は行わない）
                self.phase_times['phase5_migration_costs'] = time.time() - phase_start
                return True
            
            # コストを計算・保存
            if use_sampling and sampling_parallel:
                self.print_info(f"並列処理でサンプリングを実行します（ワーカー数: {sampling_workers if sampling_workers else 'auto'}）")
                costs = calculator.calculate_all_costs(use_parallel=True, max_workers=sampling_workers)
            else:
                costs = calculator.calculate_all_costs()
            
            # 出力ファイルのパスを確認（Calculatorによって出力ファイル名が異なる可能性があるため、ここではチェックを柔軟にするか統一する）
            # deepdb_migration_cost_calculator も simple_migration_costs.json に保存するように修正済み
            output_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_costs.json"
            
            if output_file.exists():
                self.print_success(f"マイグレーションコストを保存: {output_file}")
                self.print_info(f"  {len(costs)}個のノードのコストを計算")
            else:
                # ファイルが見つからない場合でも、計算処理自体が正常終了していれば成功とみなす場合もあるが、
                # 基本的にはファイル生成が目的
                self.print_warning("マイグレーションコストファイルが見つかりません (保存処理がスキップされた可能性があります)")
            
            # フェーズ時間を記録
            self.phase_times['phase5_migration_costs'] = time.time() - phase_start
            
            return True
            
        except Exception as e:
            self.print_error(f"マイグレーションコスト計算に失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        
    def phase6_optimize(self, mode='dynamic', use_pruning=False, pruning_parallel=False, pruning_workers=None, static_timestep='last', use_static_protection=False, static_algorithm='normal'):
        """フェーズ6: MV最適化
        
        Args:
            mode: 'static' または 'dynamic' (デフォルト: 'dynamic')
            use_pruning: プルーニングを使用するかどうか (デフォルト: False)
            pruning_parallel: プルーニングを並列実行するかどうか (デフォルト: False)
            pruning_workers: 並列実行時のワーカー数 (デフォルト: CPUコア数)
            static_timestep: 静的最適化時のタイムステップ ('first' or 'last')
            use_static_protection: 静的最適化のMVを聖域として保護する (デフォルト: False)
            static_algorithm: 静的最適化アルゴリズム ('normal', 'bigsubs', 'both')
        """
        # 最初にモードで分岐
        if mode == 'static':
            return self.phase6b_optimize_static(timestep_position=static_timestep, static_algorithm=static_algorithm)
        
        # 以下は dynamic モードの処理
        self.print_header("ILP最適化（時間依存型）", 6)
        
        if not self.pickle_path.exists():
            self.print_error(f"{self.pickle_path} が見つかりません")
            self.print_info("先にフェーズ2を実行してください")
            return False
        
        if self.qp is None:
            self.print_info(f"パース結果を読み込み中: {self.pickle_path}")
            try:
                with open(self.pickle_path, 'rb') as f:
                    self.qp = pickle.load(f)
                self.print_success(f"{self.qp.s_num}個のノードを読み込み完了")
            except Exception as e:
                self.print_error(f"パース結果の読み込みに失敗: {e}")
                return False
        
        self.print_info("時間依存型最適化（マイグレーションコスト考慮）を実行")
        if use_pruning:
            mode_str = "並列" if pruning_parallel else "逐次"
            self.print_info(f"  プルーニングを使用します（{mode_str}実行）")
            if use_static_protection:
                self.print_info(f"  静的保護: 有効（ハイブリッドアプローチ）")
            if pruning_parallel:
                import multiprocessing
                workers = pruning_workers or multiprocessing.cpu_count()
                self.print_info(f"  ワーカー数: {workers}")
        
        # フェーズ時間計測開始
        phase_start = time.time()
        
        try:
            from experiments.small_test_ver2.core.io_loaders import (
                load_timesteps_and_frequencies,
                load_full_build_costs_and_sizes,
            )
            from experiments.small_test_ver2.core.time_dependent_optimizer import TimeDependentOptimizer
            
            # ストレージ予算
            B_max = float(250*1024*1024)
            
            # タイムステップと頻度を読み込み
            self.print_info("タイムステップと頻度情報を読み込み中...")
            timesteps, frequencies = load_timesteps_and_frequencies(str(self.exp_dir), self.query_set, freq_suffix=self.exp_suffix)
            self.print_success(f"  タイムステップ数: {len(timesteps)}")
            
            # 頻度の次元を検証・調整
            query_count = len(self.qp.u_ij)
            for ts in timesteps:
                if len(frequencies[ts]) != query_count:
                    self.print_info(f"  頻度数を調整: {ts} ({len(frequencies[ts])} -> {query_count})")
                    if len(frequencies[ts]) < query_count:
                        frequencies[ts].extend([1.0] * (query_count - len(frequencies[ts])))
                    else:
                        frequencies[ts] = frequencies[ts][:query_count]
            
            # マイグレーションコストをsubquery_costsから取得（u_ijとスケール一致）
            # self.print_info("マイグレーションコストを計算中...")
            # migration_cost = {
            #     j: self.qp.qm.subquery_costs[node_id]
            #     for j, node_id in enumerate(self.qp.node_list)
            # }
            
            # --recalc モードの場合、ロードしたコストで u_ij を上書きし、そのコストを使用
            migration_cost, b_j_from_migration = self._update_u_ij_if_recalc()
            
            if migration_cost is None:
                # 通常モード：サイズとコストを読み込む
                migration_cost, _, b_j_from_migration = load_full_build_costs_and_sizes(
                    str(self.exp_dir), 
                    self.qp.node_list, 
                    self.query_set
                )
                self.print_success(f"  {len(migration_cost)}個のMVのマイグレーションコストを計算完了（subquery_costsベース）")

            # プルーニングを実行（オプション）
            pruning_info = None
            candidate_filter = None
            if use_pruning:
                from experiments.small_test_ver2.core.cf_pruner import CFPruner
                
                self.print_info("CF Pruningを実行中...")
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
                    gurobi_output=0,  # プルーニング中は静かに
                    use_parallel=pruning_parallel,
                    max_workers=pruning_workers,
                )
                
                promising_mvs = pruner.prune_candidates(use_static_protection=use_static_protection)
                pruning_time = time.time() - pruning_start
                
                pruning_info = pruner.get_filtering_info(promising_mvs)
                candidate_filter = promising_mvs
                
                self.print_success(
                    f"  プルーニング完了 ({pruning_time:.2f}秒): "
                    f"{pruning_info['promising_candidates']}/{pruning_info['total_candidates']} MVが有望 "
                    f"({pruning_info['reduction_rate']*100:.1f}% 削減)"
                )
                
                # 結果ディレクトリを準備
                result_dir = self.exp_dir / "time_dependent_output" / self.query_set
                result_dir.mkdir(parents=True, exist_ok=True)
                
                # プルーニング結果を保存
                pruning_result_file = result_dir / f"pruning_result{self.exp_suffix}.json"
                with open(pruning_result_file, 'w', encoding='utf-8') as f:
                    json.dump(pruning_info, f, indent=2, ensure_ascii=False)
                self.print_success(f"  プルーニング結果を {pruning_result_file} に保存")
            
            # オプティマイザを初期化
            self.print_info("オプティマイザを初期化中...")
            optimizer = TimeDependentOptimizer(
                node_list=self.qp.node_list,
                u_ij=self.qp.u_ij,
                X=self.qp.X,
                b_j=b_j_from_migration,  # Phase 5のEXPLAIN結果からのサイズを使用
                B_max=B_max,
                timesteps=timesteps,
                migration_cost=migration_cost,
                query_frequency_by_timestep=frequencies,
                gurobi_output=1,
            )
            
            # プルーニング結果を適用（候補フィルタリング）
            if candidate_filter is not None:
                # TimeDependentOptimizerはinitialize_candidates()で候補を絞るが、
                # その後にさらにフィルタリングすることはできない
                # そのため、プルーニング結果をcand_jに直接適用
                original_cand = optimizer.cand_j.copy()
                optimizer.cand_j = [j for j in optimizer.cand_j if j in candidate_filter]
                self.print_info(
                    f"  候補をフィルタリング: {len(original_cand)} -> {len(optimizer.cand_j)}"
                )
            
            # 最適化を実行
            self.print_info("最適化を実行中...")
            result = optimizer.optimize()
            
            # マイグレーション分析
            self.print_info("マイグレーション分析を実行中...")
            enhanced_result = self._analyze_migration_transitions(result, migration_cost, b_j_from_migration, B_max)
            
            # プルーニング情報を結果に追加
            if pruning_info:
                enhanced_result['pruning_info'] = pruning_info
                enhanced_result['pruning_time_sec'] = pruning_time
            
            # フェーズ時間を記録
            phase_time = time.time() - phase_start
            self.phase_times['phase6_optimization'] = phase_time
            enhanced_result['phase_time_sec'] = phase_time
            
            # 結果を表示
            self.print_success("最適化完了")
            self.print_info(f"  総目的関数値: {enhanced_result['objective']:.4f}")
            self.print_info(f"  ワークロードコスト: {enhanced_result['workload_cost']:.4f}")
            self.print_info(f"  マイグレーションコスト: {enhanced_result['migration_cost']:.4f}")
            self.print_info(f"  ILP求解時間: {enhanced_result['solve_time_sec']:.2f} 秒")
            if pruning_info:
                self.print_info(f"  プルーニング時間: {pruning_time:.2f} 秒")
            self.print_info(f"  フェーズ総実行時間: {phase_time:.2f} 秒")
            
            # 結果を保存（run_time_dependent_with_migration.pyと同じディレクトリ構造）
            # z_by_timestep と y_by_timestep は Phase 7以降で不要なので除外してファイルサイズを削減
            result_to_save = {k: v for k, v in enhanced_result.items() 
                            if k not in ('z_by_timestep', 'y_by_timestep')}
            
            result_dir = self.exp_dir / "time_dependent_output" / self.query_set
            result_dir.mkdir(parents=True, exist_ok=True)
            result_file = result_dir / f"td_mv_optimization_result{self.exp_suffix}.json"
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result_to_save, f, indent=2, ensure_ascii=False)
            self.print_success(f"結果を {result_file} に保存")
            
            # 結果をインスタンス変数に保存（後続フェーズで使用）
            self.result = enhanced_result
            
            return True

        except Exception as e:
            self.print_error(f"最適化に失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _analyze_migration_transitions(self, result: dict, migration_cost: dict, b_j: list, B_max: float) -> dict:
        """マイグレーション遷移を分析
        
        Args:
            result: 最適化結果
            migration_cost: マイグレーションコスト（フルビルド）
            b_j: 各MVのサイズリスト（Phase 5のEXPLAIN結果から取得）
            B_max: ストレージ予算
        """
        timesteps = result["timesteps"]
        z_by_timestep = result["z_by_timestep"]
        
        migration_analysis = []
        
        for t in range(len(timesteps)):
            timestep_name = timesteps[t]
            current_mvs = set(j for j, v in enumerate(z_by_timestep[t]) if v == 1)
            
            # タイムステップごとの情報
            selected_nodes = [self.qp.node_list[j] for j in sorted(current_mvs)]
            total_size = sum(b_j[j] for j in current_mvs)  # 正しいb_jを使用
            utilization = (total_size / B_max * 100) if B_max > 0 else 0
            
            timestep_info = {
                "timestep": timestep_name,
                "selected_mvs": selected_nodes,
                "mv_count": len(current_mvs),
                "total_size": round(total_size, 2),
                "storage_budget": round(B_max, 2),
                "utilization_percent": round(utilization, 2)
            }
            
            # マイグレーション情報（t > 0の場合）
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
                        "total_size": round(sum(b_j[j] for j in maintained), 2)  # 正しいb_jを使用
                    },
                    "created": {
                        "count": len(created),
                        "mvs": [self.qp.node_list[j] for j in sorted(created)],
                        "total_size": round(sum(b_j[j] for j in created), 2)  # 正しいb_jを使用
                    },
                    "deleted": {
                        "count": len(deleted),
                        "mvs": [self.qp.node_list[j] for j in sorted(deleted)],
                        "total_size": round(sum(b_j[j] for j in deleted), 2)  # 正しいb_jを使用
                    }
                }
                
                # 作成コストの計算
                creation_cost = 0.0
                creation_details = []
                
                for j in sorted(created):
                    cost = migration_cost.get(j, float("inf"))
                    creation_cost += cost
                    creation_details.append({
                        "mv": self.qp.node_list[j],
                        "size": round(b_j[j], 2),
                        "cost": round(cost, 2),
                        "dependencies": [] # 簡易化のため依存関係は空（フルビルド）
                    })
                
                migration_details["creation_cost"] = round(creation_cost, 2)
                migration_details["creation_details"] = creation_details
                
                timestep_info["migration"] = migration_details
            else:
                # 初期タイムステップ
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
        
        # 拡張結果を作成
        enhanced = result.copy()
        enhanced["migration_analysis"] = migration_analysis
        
        # サマリー統計を追加
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
    
    def phase6b_optimize_static(self, timestep_position='last', static_algorithm='normal'):
        """フェーズ6b: 静的最適化（時間依存なし・単一タイムステップのみ）
        
        Args:
            timestep_position: 使用するタイムステップ 
                'first': 最初, 'last': 最後, 'average': 全時刻の平均,
                'addmv': 頻度の和で重み付け + MV作成コスト考慮
            static_algorithm: 使用するアルゴリズム ('normal': 通常ILP, 'bigsubs': BigSubs, 'both': 両方)
        """
        if timestep_position == 'first':
            position_name = "最初"
        elif timestep_position == 'average':
            position_name = "全時刻平均"
        elif timestep_position == 'addmv':
            position_name = "頻度和+MV作成コスト"
        else:
            position_name = "最終"
        self.print_header(f"静的最適化（{position_name}タイムステップ）", 6.5)
        
        if not self.pickle_path.exists():
            self.print_error(f"{self.pickle_path} が見つかりません")
            return False
            
        if self.qp is None:
            self.print_info(f"パース結果を読み込み中: {self.pickle_path}")
            try:
                with open(self.pickle_path, 'rb') as f:
                    self.qp = pickle.load(f)
            except Exception as e:
                self.print_error(f"パース結果の読み込みに失敗: {e}")
                return False

        self.print_info("静的最適化（初期タイムステップのワークロードのみ）を実行")
        phase_start = time.time()
        
        try:
            from experiments.small_test_ver2.core.io_loaders import (
                load_timesteps_and_frequencies,
                load_full_build_costs_and_sizes,
            )
            from src.optimization.normal import NormalOptimizer
            
            # ストレージ予算
            B_max = float(250*1024*1024)
            
            # タイムステップと頻度を読み込み
            timesteps, frequencies = load_timesteps_and_frequencies(str(self.exp_dir), self.query_set, freq_suffix=self.exp_suffix)
            
            if not timesteps:
                self.print_error("タイムステップ情報がありません")
                return False
                
            # タイムステップの選択
            if timestep_position == 'first':
                selected_timestep = timesteps[0]
                selected_frequencies = frequencies[selected_timestep]
                self.print_info(f"使用タイムステップ: {selected_timestep} (最初)")
            elif timestep_position == 'average':
                # 全時刻での頻度の和を計算（平均ではなく和を使用）
                selected_timestep = "average"
                self.print_info(f"使用タイムステップ: 全時刻の頻度和")
                
                # 各クエリについて全タイムステップでの頻度の和を計算
                query_count = len(self.qp.u_ij)
                selected_frequencies = [0.0] * query_count
                
                for timestep in timesteps:
                    timestep_freq = frequencies[timestep]
                    # 頻度の次元を調整
                    if len(timestep_freq) < query_count:
                        timestep_freq = timestep_freq + [1.0] * (query_count - len(timestep_freq))
                    else:
                        timestep_freq = timestep_freq[:query_count]
                    
                    # 累積加算（平均化しない）
                    for i in range(query_count):
                        selected_frequencies[i] += timestep_freq[i]
                
                self.print_info(f"  {len(timesteps)}個のタイムステップの頻度を合計")
            elif timestep_position == 'addmv':
                # 頻度の和で重み付け（MV作成コストとスケールを合わせるため）
                selected_timestep = "addmv"
                self.print_info(f"使用タイムステップ: 頻度の和 + MV作成コスト考慮")
                
                # 各クエリについて全タイムステップでの頻度の和を計算（平均ではなく）
                query_count = len(self.qp.u_ij)
                selected_frequencies = [0.0] * query_count
                
                for timestep in timesteps:
                    timestep_freq = frequencies[timestep]
                    # 頻度の次元を調整
                    if len(timestep_freq) < query_count:
                        timestep_freq = timestep_freq + [1.0] * (query_count - len(timestep_freq))
                    else:
                        timestep_freq = timestep_freq[:query_count]
                    
                    # 累積加算（平均化しない）
                    for i in range(query_count):
                        selected_frequencies[i] += timestep_freq[i]
                
                self.print_info(f"  {len(timesteps)}個のタイムステップの頻度を合計")
            else:  # 'last'
                selected_timestep = timesteps[-1]
                selected_frequencies = frequencies[selected_timestep]
                self.print_info(f"使用タイムステップ: {selected_timestep} (最後)")
            
            # 頻度の次元調整（average/addmvの場合はすでに調整済み）
            query_count = len(self.qp.u_ij)
            if timestep_position not in ('average', 'addmv'):
                if len(selected_frequencies) < query_count:
                    selected_frequencies.extend([1.0] * (query_count - len(selected_frequencies)))
                else:
                    selected_frequencies = selected_frequencies[:query_count]
                
            # --recalc モードの場合、u_ij を更新し、コストを取得
            recalc_migration_cost, _ = self._update_u_ij_if_recalc()

            # 重み付き効用を計算 (u_ij * frequency)
            weighted_u_ij = []
            for i in range(len(self.qp.u_ij)):
                freq = selected_frequencies[i]
                weighted_row = [u * freq for u in self.qp.u_ij[i]]
                weighted_u_ij.append(weighted_row)
            
            # サイズデータの読み込み（MV作成コストはsubquery_costsを使用するためcreation_costsは不要）
            _, _, b_j_from_migration = load_full_build_costs_and_sizes(
                str(self.exp_dir), 
                self.qp.node_list, 
                self.query_set
            )
            
            # m_costは0とする（マイグレーションコストを考慮しないため）
            m_cost = [0.0] * len(self.qp.node_list)
            
            # addmvモードの場合、MV作成コストをindex_build_costsとして使用
            # 動的最適化と同様にsubquery_costsを使用（u_ijとスケール一致）
            if timestep_position == 'addmv':
                if self.recalc_mode and recalc_migration_cost is not None:
                     # Recalcモード: 再計算されたコストを使用
                    index_build_costs = [
                        recalc_migration_cost.get(j, float('inf'))
                        for j in range(len(self.qp.node_list))
                    ]
                    self.print_info(f"  MV作成コストを目的関数に含めます（Recalcコストベース）")
                else:
                    # 通常モード: subquery_costsを使用
                    index_build_costs = [
                        self.qp.qm.subquery_costs[node_id]
                        for node_id in self.qp.node_list
                    ]
                    self.print_info(f"  MV作成コストを目的関数に含めます（subquery_costsベース）")
                
                total_creation_cost = sum(val for val in index_build_costs if val != float('inf'))
                self.print_info(f"  総MV作成コスト上限: {total_creation_cost:.4f}")
            else:
                index_build_costs = None  # デフォルト（作成コストを考慮しない）
            
            # 結果保存用の変数
            result_dir = self.exp_dir / "time_dependent_output" / self.query_set
            result_dir.mkdir(parents=True, exist_ok=True)
            
            # NormalOptimizer実行 (normal or both)
            if static_algorithm in ('normal', 'both'):
                self.print_info(f"NormalOptimizer で最適化を実行中...")
                
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
                    index_build_costs=index_build_costs  # addmvモードでMV作成コストを渡す
                )
                
                result = optimizer.optimize()
                
                # 結果の整形
                selected_mvs = [mv.node_id for mv in result.selected_views]
                selected_indices = [self.qp.node_list.index(mv.node_id) for mv in result.selected_views]
                total_size = result.total_storage
                
                # addmvモードの場合はアルゴリズム名を変更
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
                
                # addmvモードの場合、利得とMV作成コストを分けて計算
                if timestep_position == 'addmv' and index_build_costs is not None:
                    # 選択されたMVの利得の総和を計算（y_ij=1のペアのみ）
                    # y_ijはGurobiの最適化結果から取得
                    y_ij = result.metadata.get("y_ij", [[0] * len(self.qp.node_list) for _ in range(len(weighted_u_ij))])
                    total_utility_gain = 0.0
                    for i in range(len(weighted_u_ij)):
                        for j in selected_indices:
                            if y_ij[i][j] == 1:  # 実際に使用される場合のみ
                                total_utility_gain += weighted_u_ij[i][j]
                    
                    # 選択されたMVの初期作成コストの和を計算
                    total_creation_cost = sum(index_build_costs[j] for j in selected_indices)
                    
                    static_result["total_utility_gain"] = total_utility_gain
                    static_result["total_creation_cost"] = total_creation_cost
                    
                    self.print_success("NormalOptimizer 完了")
                    self.print_info(f"  選択されたMV数: {len(selected_mvs)}")
                    self.print_info(f"  使用ストレージ: {total_size / 1024 / 1024:.2f} MB")
                    self.print_info(f"  利得の総和: {total_utility_gain:.4f}")
                    self.print_info(f"  初期MV作成コストの和: {total_creation_cost:.4f}")
                    self.print_info(f"  目的関数値 (利得 - 作成コスト): {result.total_utility:.4f}")
                else:
                    self.print_success("NormalOptimizer 完了")
                    self.print_info(f"  選択されたMV数: {len(selected_mvs)}")
                    self.print_info(f"  使用ストレージ: {total_size / 1024 / 1024:.2f} MB")
                
                # 結果保存
                result_file = result_dir / f"static_mv_optimization_result{self.exp_suffix}.json"
                with open(result_file, 'w', encoding='utf-8') as f:
                    json.dump(static_result, f, indent=2, ensure_ascii=False)
                self.print_success(f"NormalOptimizer結果を {result_file} に保存")
            
            # BigSubsOptimizer実行 (bigsubs or both)
            if static_algorithm in ('bigsubs', 'both'):
                from src.optimization.bigsubs import BigSubsOptimizer
                
                self.print_info(f"BigSubsOptimizer で最適化を実行中...")
                
                # weighted_u_ij に基づいて U_j_max と U_max を計算
                # オリジナルのBigSubsに合わせて、max ではなく sum を使用
                weighted_U_j_max = [
                    sum((weighted_u_ij[i][j] for i in range(len(weighted_u_ij))))
                    for j in range(len(self.qp.node_list))
                ]
                weighted_U_max = sum(weighted_U_j_max)
                
                # y_ijはクエリパーサから取得（オリジナルの静的実験と同様）
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
                
                # 結果の整形
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
                
                self.print_success("BigSubsOptimizer 完了")
                self.print_info(f"  選択されたMV数: {len(bigsubs_selected_mvs)}")
                self.print_info(f"  使用ストレージ: {bigsubs_total_size / 1024 / 1024:.2f} MB")
                
                # 結果保存（BigSubs用のファイル名）
                bigsubs_result_file = result_dir / f"static_bigsubs_optimization_result{self.exp_suffix}.json"
                with open(bigsubs_result_file, 'w', encoding='utf-8') as f:
                    json.dump(bigsubs_static_result, f, indent=2, ensure_ascii=False)
                self.print_success(f"BigSubsOptimizer結果を {bigsubs_result_file} に保存")
            
            # SQL生成はPhase 7に移動
            self.phase_times['phase6b_static_optimization'] = time.time() - phase_start
            return True
            
        except Exception as e:
            self.print_error(f"静的最適化に失敗: {e}")
            import traceback
            traceback.print_exc()
            return False

    def phase7_generate_mv_sql(self, mode='dynamic', static_algorithm='normal'):
        """フェーズ7: MV作成SQL生成
        
        Args:
            mode: 'static' または 'dynamic' (デフォルト: 'dynamic')
            static_algorithm: 静的最適化アルゴリズム ('normal', 'bigsubs', 'both')
        """
        # Static mode: 静的最適化結果からSQL生成
        if mode == 'static':
            self.print_header("静的MV作成SQL生成", 7)
            phase_start = time.time()
            
            success = self._generate_static_mv_sql(static_algorithm=static_algorithm)
            
            self.phase_times['phase7_static_sql_generation'] = time.time() - phase_start
            if success:
                self.print_info(f"  SQL生成時間: {self.phase_times['phase7_static_sql_generation']:.2f} 秒")
            return success
        
        # Dynamic mode: タイムステップごとのマイグレーションSQL作成
        self.print_header("マイグレーションSQL作成", 7)
        
        # if self.qp is None:
        #     if not self.pickle_path.exists():
        #         self.print_error(f"{self.pickle_path} が見つかりません")
        #         return False
            
        #     self.print_info(f"パース結果を読み込み中: {self.pickle_path}")
        #     with open(self.pickle_path, 'rb') as f:
        #         self.qp = pickle.load(f)
        
        if self.result is None:
            # Load time-dependent optimization result
            result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"td_mv_optimization_result{self.exp_suffix}.json"
            
            if not result_file.exists():
                self.print_error("時間依存型最適化結果が見つかりません")
                self.print_info("先にフェーズ3を実行してください")
                return False
            
            with open(result_file, 'r', encoding='utf-8') as f:
                result_data = json.load(f)
                self.result = result_data
        
        # Check if result is from time-dependent optimizer
        if 'migration_analysis' not in self.result:
            self.print_error("時間依存型最適化結果ではありません")
            return False
        
        return self._generate_time_dependent_migration_sql()
    
    def _generate_time_dependent_migration_sql(self):
        """時間依存型最適化の結果からタイムステップごとのマイグレーションSQLを生成"""
        
        # フェーズ時間計測開始
        phase_start = time.time()
        
        try:
            # マイグレーションプランを読み込み
            plans_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_plans.json"
            if not plans_file.exists():
                self.print_error("マイグレーションプランが見つかりません")
                self.print_info("先にフェーズ2.7を実行してください")
                return False
            
            with open(plans_file, 'r', encoding='utf-8') as f:
                migration_plans = json.load(f)
            
            self.print_info(f"マイグレーションプラン読み込み完了: {len(migration_plans)}個のMV")
            
            # 出力ディレクトリ（フェーズ3の最適化結果と同じ場所）
            output_dir = self.exp_dir / "time_dependent_output" / self.query_set
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 既存のマイグレーションSQLファイルを削除
            existing_sql_files = list(output_dir.glob("timestep_*.sql"))
            if existing_sql_files:
                self.print_info(f"既存のマイグレーションSQLファイルを削除中: {len(existing_sql_files)}個")
                for sql_file in existing_sql_files:
                    sql_file.unlink()
                self.print_success("既存ファイルを削除完了")
            
            # 各タイムステップについて処理
            migration_analysis = self.result['migration_analysis']
            timesteps = self.result['timesteps']
            
            self.print_info(f"タイムステップ数: {len(timesteps)}")
            
            total_sql_count = 0
            
            for t_idx, timestep_info in enumerate(migration_analysis):
                timestep_name = timestep_info['timestep']
                current_mvs = set(timestep_info.get('selected_mvs', []))
                
                # 前のタイムステップのMV
                prev_mvs = set()
                if t_idx > 0:
                    prev_mvs = set(migration_analysis[t_idx - 1].get('selected_mvs', []))
                
                # 新規作成が必要なMV
                mvs_to_create = current_mvs - prev_mvs
                # 削除が必要なMV
                mvs_to_drop = prev_mvs - current_mvs
                
                if not mvs_to_create and not mvs_to_drop:
                    self.print_info(f"  タイムステップ '{timestep_name}': 変更なし（スキップ）")
                    continue
                
                # タイムステップごとのSQLファイルを作成
                output_file = output_dir / f"timestep_{t_idx}_{timestep_name}.sql"
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(f"-- =====================================================\n")
                    f.write(f"-- タイムステップ {t_idx}: {timestep_name}\n")
                    f.write(f"-- =====================================================\n\n")
                    f.write(f"\\c {self.settings.database.database}\n\n")
                    
                    # 削除が必要なMV
                    if mvs_to_drop:
                        f.write(f"-- 削除するMV: {len(mvs_to_drop)}個\n")
                        for mv_id in sorted(mvs_to_drop):
                            f.write(f"DROP MATERIALIZED VIEW IF EXISTS {mv_id} CASCADE;\n")
                        f.write("\n")
                    
                    # 新規作成が必要なMV
                    if mvs_to_create:
                        f.write(f"-- 新規作成するMV: {len(mvs_to_create)}個\n\n")
                        
                        created_count = 0
                        for mv_id in sorted(mvs_to_create):
                            # マイグレーションプランから適切なSQLを取得
                            if mv_id not in migration_plans:
                                self.print_info(f"  警告: {mv_id} のマイグレーションプランが見つかりません")
                                continue
                            
                            plans = migration_plans[mv_id]
                            
                            # 依存MVなしで新規作成（"[]"キー）
                            # 時間依存型の場合、前のタイムステップのMVを使って作成することも可能だが、
                            # シンプルマイグレーションプランでは"[]"（依存なし）のみなのでそれを使用
                            if "[]" in plans:
                                sql = plans["[]"]
                                if sql and sql != "NON_MIGRATE":
                                    f.write(f"-- MV: {mv_id}\n")
                                    f.write(f"{sql}\n")
                                    f.write(f"ANALYZE {mv_id};\n\n")
                                    created_count += 1
                        
                        f.write(f"-- {created_count}個のMVを作成\n")
                
                sql_count = len(mvs_to_create) + len(mvs_to_drop)
                total_sql_count += sql_count
                
                self.print_success(f"  タイムステップ '{timestep_name}': {output_file.name}")
                self.print_info(f"    作成: {len(mvs_to_create)}個, 削除: {len(mvs_to_drop)}個")
            
            # フェーズ時間を記録
            self.phase_times['phase7_mv_sql_generation'] = time.time() - phase_start
            
            self.print_success(f"タイムステップごとのマイグレーションSQLを生成 → {output_dir}")
            self.print_info(f"  総操作数: {total_sql_count}")
            self.print_info(f"  SQL生成時間: {self.phase_times['phase7_mv_sql_generation']:.2f} 秒")
            
            return True
            
        except Exception as e:
            self.print_error(f"SQL生成に失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
    


    
    
    def _generate_static_mv_sql(self, static_algorithm='normal'):
        """静的最適化結果からMV作成SQLを生成
        
        Args:
            static_algorithm: 使用するアルゴリズム ('normal' or 'bigsubs')
        """
        try:
            # 静的最適化結果を読み込み（アルゴリズムに応じてファイルを選択）
            if static_algorithm == 'bigsubs':
                result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"static_bigsubs_optimization_result{self.exp_suffix}.json"
                sql_file_name = "static_bigsubs_initial_mvs.sql"
            else:
                result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"static_mv_optimization_result{self.exp_suffix}.json"
                sql_file_name = "static_initial_mvs.sql"
            
            if not result_file.exists():
                self.print_error(f"静的最適化結果が見つかりません: {result_file}")
                self.print_info("先にフェーズ6.5を実行してください")
                return False
            
            with open(result_file, 'r', encoding='utf-8') as f:
                static_result = json.load(f)
            
            selected_mvs = static_result.get('selected_mvs', [])
            self.print_info(f"静的最適化結果を読み込み ({static_algorithm}): {len(selected_mvs)}個のMV")
            
            # マイグレーションプランを読み込み
            plans_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_plans.json"
            if not plans_file.exists():
                self.print_error(f"マイグレーションプランが見つかりません: {plans_file}")
                self.print_info("先にフェーズ4を実行してください")
                return False
            
            with open(plans_file, 'r', encoding='utf-8') as f:
                migration_plans = json.load(f)
            
            # SQLステートメントを生成
            sql_statements = []
            sql_statements.append(f"-- =====================================================")
            sql_statements.append(f"-- 静的最適化MV作成SQL ({static_algorithm})")
            sql_statements.append(f"-- 選択されたMV数: {len(selected_mvs)}")
            sql_statements.append(f"-- =====================================================")
            sql_statements.append(f"\\c {self.settings.database.database}")
            sql_statements.append("")
            
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
            
            # SQLファイルを保存
            output_dir = self.exp_dir / "time_dependent_output" / self.query_set
            output_dir.mkdir(parents=True, exist_ok=True)
            sql_file = output_dir / sql_file_name
            
            # 既存の静的MVファイルを削除
            if sql_file.exists():
                self.print_info(f"既存の静的MV SQLファイルを削除中: {sql_file_name}")
                sql_file.unlink()
            
            with open(sql_file, 'w', encoding='utf-8') as f:
                f.write("\n".join(sql_statements))
            
            self.print_success(f"静的MV作成SQLを生成: {sql_file}")
            self.print_info(f"  作成するMV数: {created_count}")
            return True
            
        except Exception as e:
            self.print_error(f"静的SQL生成に失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def phase8_rewrite_queries(self, mode='dynamic', static_algorithm='normal'):
        """フェーズ8: クエリ書き換え
        
        Args:
            mode: 'static' または 'dynamic' (デフォルト: 'dynamic')
            static_algorithm: 静的最適化アルゴリズム ('normal', 'bigsubs', 'both')
        """
        # 最初にモードで分岐
        if mode == 'static':
            # Static mode
            self.print_header("クエリ書き換え（静的モード）", 8)
            
            # アルゴリズムに応じてファイルを選択
            if static_algorithm == 'bigsubs':
                static_result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"static_bigsubs_optimization_result{self.exp_suffix}.json"
            else:
                static_result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"static_mv_optimization_result{self.exp_suffix}.json"
            
            if not static_result_file.exists():
                self.print_error(f"静的最適化結果が見つかりません: {static_result_file}")
                self.print_info("先にフェーズ6を --optimization-mode static で実行してください")
                return False
            
            self.print_info(f"静的最適化結果を使用してクエリを書き換えます ({static_algorithm})。")
            
            phase_start = time.time()
            success = self._rewrite_static_queries(static_result_file, static_algorithm=static_algorithm)
            self.phase_times['phase8_rewrite_queries_static'] = time.time() - phase_start
            
            return success
        
        # 以下は dynamic モードの処理
        self.print_header("時間依存型クエリ書き換え", 8)
        
        # フェーズ時間計測開始
        phase_start = time.time()
        
        from src.rewrite.query_rewriter import QueryRewriter
        from src.core.models import MaterializedView
        
        if self.qp is None:
            self.print_info("QueryParserを読み込み中...")
            if not self.pickle_path.exists():
                self.print_error("パース結果が見つかりません")
                return False
            
            with open(self.pickle_path, 'rb') as f:
                self.qp = pickle.load(f)
        
        # Load time-dependent optimization result
        result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"td_mv_optimization_result{self.exp_suffix}.json"
        
        if not result_file.exists():
            self.print_error("時間依存型最適化結果が見つかりません")
            self.print_info("先にフェーズ6を実行してください")
            return False
        
        with open(result_file, 'r', encoding='utf-8') as f:
            result_data = json.load(f)
        
        # Check if result is from time-dependent optimizer
        if 'migration_analysis' not in result_data:
            self.print_error("時間依存型最適化結果ではありません")
            return False
        
        # Get query files
        query_files = sorted(self.queries_dir.glob("*.sql"), key=lambda x: x.name)
        if not query_files:
            self.print_error("クエリファイルが見つかりません")
            return False
        
        self.print_info(f"クエリ数: {len(query_files)}")
        
        # Base output directory
        base_output_dir = self.exp_dir / "time_dependent_output" / self.query_set / "jobs"
        base_output_dir.mkdir(parents=True, exist_ok=True)
        
        migration_analysis = result_data['migration_analysis']
        self.print_info(f"タイムステップ数: {len(migration_analysis)}")
        
        # Load migration plans to get SQL for each MV
        plans_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_plans.json"
        if not plans_file.exists():
            self.print_error("マイグレーションプランが見つかりません")
            self.print_info("先にフェーズ2.7を実行してください")
            return False
        
        with open(plans_file, 'r', encoding='utf-8') as f:
            migration_plans = json.load(f)
        
        self.print_info(f"マイグレーションプラン読み込み完了: {len(migration_plans)}個のMV")
        
        total_rewritten = 0
        
        # Process each timestep
        for t_idx, timestep_info in enumerate(migration_analysis):
            timestep_name = timestep_info['timestep']
            selected_mvs = timestep_info.get('selected_mvs', [])
            
            self.print_info(f"\nタイムステップ {t_idx} ({timestep_name}): {len(selected_mvs)}個のMV")
            
            # Create MaterializedView objects for the selected MVs
            mv_objects = []
            for node_id in selected_mvs:
                # Find node index
                try:
                    node_idx = self.qp.node_list.index(node_id)
                except ValueError:
                    self.print_info(f"  警告: ノード {node_id} が見つかりません")
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
            timestep_output_dir.mkdir(parents=True, exist_ok=True)
            
            # Rewrite queries using QueryRewriter with settings
            # settingsをコピーしてクエリディレクトリを指定
            from copy import deepcopy
            rewrite_settings = deepcopy(self.settings)
            rewrite_settings.benchmark.sql_dir = str(self.queries_dir.parent)  # 01_queriesディレクトリを指定
            
            # 包含行列を渡して冗長MV除去を有効化
            rewriter = QueryRewriter(
                rewrite_settings,
                containment_matrix=self.qp.X,
                node_list=self.qp.node_list
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
            self.print_success(f"  {rewritten_count}個のクエリを書き換え → {timestep_output_dir}")
        
        # フェーズ時間を記録
        self.phase_times['phase8_query_rewriting'] = time.time() - phase_start
        
        self.print_success(f"\n合計 {total_rewritten}個のクエリを書き換え完了")
        self.print_info(f"  出力先: {base_output_dir}")
        self.print_info(f"  クエリ書き換え時間: {self.phase_times['phase8_query_rewriting']:.2f} 秒")
        
        return True
    
    def _rewrite_static_queries(self, result_file, static_algorithm='normal'):
        """静的最適化結果に基づいてクエリを書き換え
        
        Args:
            result_file: 最適化結果ファイルパス
            static_algorithm: 使用するアルゴリズム ('normal' or 'bigsubs')
        """
        try:
            from src.rewrite.query_rewriter import QueryRewriter
            from src.core.models import MaterializedView
            
            # Load QueryParser if not already loaded
            if self.qp is None:
                self.print_info("QueryParserを読み込み中...")
                if not self.pickle_path.exists():
                    self.print_error("パース結果が見つかりません")
                    return False
                
                with open(self.pickle_path, 'rb') as f:
                    self.qp = pickle.load(f)
            
            with open(result_file, 'r', encoding='utf-8') as f:
                result_data = json.load(f)
            
            selected_mvs = result_data.get('selected_mvs', [])
            self.print_info(f"静的モード ({static_algorithm}): {len(selected_mvs)}個のMVを使用してクエリを書き換え")
            
            # クエリファイル取得
            query_files = sorted(self.queries_dir.glob("*.sql"), key=lambda x: x.name)
            
            # マイグレーションプラン読み込み
            plans_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_plans.json"
            if not plans_file.exists():
                return
                
            with open(plans_file, 'r', encoding='utf-8') as f:
                migration_plans = json.load(f)
            
            # MVオブジェクト作成
            mv_objects = []
            for node_id in selected_mvs:
                # ノードインデックス検索
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
            
            # 書き換え実行
            # settingsをコピーしてクエリディレクトリを指定
            from copy import deepcopy
            rewrite_settings = deepcopy(self.settings)
            rewrite_settings.benchmark.sql_dir = str(self.queries_dir.parent)  # 01_queriesディレクトリを指定
            
            # 包含行列を渡して冗長MV除去を有効化
            rewriter = QueryRewriter(
                rewrite_settings,
                containment_matrix=self.qp.X,
                node_list=self.qp.node_list
            )
            rewritten_queries = rewriter.rewrite_queries(mv_objects)
            
            # 保存先（アルゴリズムに応じて変更）
            if static_algorithm == 'bigsubs':
                output_dir = self.exp_dir / "time_dependent_output" / self.query_set / "jobs" / "rewritten_static_bigsubs"
            else:
                output_dir = self.exp_dir / "time_dependent_output" / self.query_set / "jobs" / "rewritten_static"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            for query_id, rewritten_sql in rewritten_queries.items():
                output_file = output_dir / f"{query_id}.sql"
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(rewritten_sql)
            
            self.print_success(f"  静的モード用クエリを書き換え完了 ({static_algorithm}): {output_dir}")
            return True
            
        except Exception as e:
            self.print_error(f"静的モード用クエリ書き換えに失敗: {e}")
            return False

    def phase9_execute_benchmark(self, mode='dynamic', static_algorithm='normal', ease_mode=False):
        """フェーズ9: 時間依存型ベンチマーク実行
        
        Args:
            mode: ベンチマークモード
                - 'dynamic': 動的MV（マイグレーションあり）
                - 'static': 静的MV（最初のタイムステップのみ）
                - 'baseline': ベースライン（MVなし）
            static_algorithm: 静的最適化アルゴリズム ('normal', 'bigsubs', 'both')
            ease_mode: 簡易モード（各クエリを1回実行し、時間に頻度を掛ける）
        """
        mode_names = {
            'dynamic': '動的MV（マイグレーションあり）',
            'static': '静的MV（最初のタイムステップのみ）',
            'baseline': 'ベースライン（MVなし）'
        }
        
        self.print_header(f"時間依存型ベンチマーク実行 - {mode_names.get(mode, mode)}", 9)
        phase_start = time.time()
        
        # ベンチマーク実行前に統計情報を更新
        self.print_info("ベンチマーク前にベーステーブルの統計情報を更新中...")
        self._analyze_base_tables()
        
        # PostgreSQLキャッシュをクリア（公平なベンチマークのため）
        self.print_info("PostgreSQLキャッシュをクリア中...")
        self._clear_caches()       
        
        from experiments.small_test_ver2.benchmark import TimeDependentQueryExecutor
        from experiments.small_test_ver2.core.io_loaders import load_timesteps_and_frequencies
        
        # モードに応じて最適化結果の読み込み要否を判定
        optimization_result = None
        migration_sql_dir = None
        rewritten_queries_base_dir = None # Initialize here
        
        if mode == 'dynamic':
            # 最適化結果を読み込み
            result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"td_mv_optimization_result{self.exp_suffix}.json"
            
            if not result_file.exists():
                self.print_error("時間依存型最適化結果が見つかりません")
                self.print_info("先にフェーズ6を実行してください")
                return False
            
            with open(result_file, 'r', encoding='utf-8') as f:
                optimization_result = json.load(f)
                
            migration_sql_dir = self.exp_dir / "time_dependent_output" / self.query_set # This should point to the directory containing timestep_X_Y.sql
            rewritten_queries_base_dir = self.exp_dir / "time_dependent_output" / self.query_set / "jobs"
            
        elif mode == 'static':
            # 静的最適化結果を読み込み（アルゴリズムに応じてファイルを選択）
            if static_algorithm == 'bigsubs':
                result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"static_bigsubs_optimization_result{self.exp_suffix}.json"
                rewritten_queries_base_dir = self.exp_dir / "time_dependent_output" / self.query_set / "jobs" / "rewritten_static_bigsubs"
            else:
                result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"static_mv_optimization_result{self.exp_suffix}.json"
                rewritten_queries_base_dir = self.exp_dir / "time_dependent_output" / self.query_set / "jobs" / "rewritten_static"
            
            if not result_file.exists():
                self.print_error(f"静的最適化結果が見つかりません: {result_file}")
                self.print_info("先にフェーズ6bを実行してください")
                return False
                
            with open(result_file, 'r', encoding='utf-8') as f:
                optimization_result = json.load(f)
            
            self.print_info(f"静的最適化結果を使用 ({static_algorithm}): {result_file.name}")
                
            # 静的モード用の設定
            # migration_sql_dir は static_initial_mvs.sql があるディレクトリ
            migration_sql_dir = self.exp_dir / "time_dependent_output" / self.query_set
            
            if not rewritten_queries_base_dir.exists():
                self.print_error(f"静的モード用クエリディレクトリが見つかりません: {rewritten_queries_base_dir}")
                return False

        elif mode == 'baseline':
            # ベースラインモードでは最適化結果は不要だが、
            # タイムステップと頻度情報を取得するためにダミーで読み込むか、
            # あるいはoptimization_resultをNoneのままにする。
            # ここではNoneのままにして、executorに直接オリジナルクエリを渡す。
            optimization_result = None
            migration_sql_dir = None # ベースラインではMV操作SQLは不要
            rewritten_queries_base_dir = self.queries_dir # オリジナルクエリのディレクトリ
            
        # migration_sql_dirの存在確認 (dynamicモードのみ)
        if mode == 'dynamic' and (not migration_sql_dir or not migration_sql_dir.exists()):
            self.print_error(f"マイグレーションSQLディレクトリが見つかりません: {migration_sql_dir}")
            self.print_info("先にフェーズ7を実行してください")
            return False
        
        # 書き換えられたクエリファイルを使用
        # rewritten_base_dir = self.exp_dir / "time_dependent_output" / self.query_set / "jobs" # This line is now handled by rewritten_queries_base_dir
        
        # 元のクエリファイルリストを取得（クエリ名のリストとして使用）
        import re
        def natural_sort_key(s):
            return [int(text) if text.isdigit() else text.lower() for text in re.split("([0-9]+)", str(s))]
            
        original_query_files = sorted(self.queries_dir.glob("*.sql"), key=lambda x: natural_sort_key(x.name))
        
        if not original_query_files:
            self.print_error("クエリファイルが見つかりません")
            return False
        
        self.print_info(f"クエリ数: {len(original_query_files)}")
        
        # 頻度情報を読み込み
        self.print_info("頻度情報を読み込み中...")
        try:
            timesteps, frequencies_by_timestep = load_timesteps_and_frequencies(
                str(self.exp_dir), 
                self.query_set,
                freq_suffix=self.exp_suffix
            )
            self.print_success(f"  タイムステップ数: {len(timesteps)}")
        except Exception as e:
            self.print_error(f"頻度情報の読み込みに失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        # TimeDependentQueryExecutorを初期化
        self.print_info("ベンチマーク実行の準備中...")
        executor = TimeDependentQueryExecutor(self.settings)
        
        try:
            # モードに応じてベンチマークを実行
            self.print_info(f"ベンチマーク実行を開始します（モード: {mode}）...\n")
            
            if mode == 'baseline':
                # ベースライン: MVなし（元のクエリを使用）
                benchmark_results = executor.execute_baseline_benchmark(
                    query_files=original_query_files,
                    frequencies_by_timestep=frequencies_by_timestep,
                    timesteps=timesteps,
                    timeout_minutes=30,
                    verbose=True,
                    ease_mode=ease_mode
                )
            elif mode == 'static':
                # 静的MV: 最初のタイムステップのみ
                benchmark_results = executor.execute_static_mv_benchmark(
                    optimization_result=optimization_result,
                    migration_sql_dir=migration_sql_dir,
                    # query_files=query_files, # Not used directly, rewritten_queries_base_dir is used
                    rewritten_queries_base_dir = rewritten_queries_base_dir,
                    frequencies_by_timestep=frequencies_by_timestep,
                    timesteps=timesteps, # Pass timesteps for static mode as well
                    timeout_minutes=30,
                    verbose=True,
                    static_algorithm=static_algorithm,
                    ease_mode=ease_mode
                )
            else:  # dynamic
                # 動的MV: マイグレーションあり（既存）
                benchmark_results = executor.execute_time_dependent_benchmark(
                    optimization_result=optimization_result,
                    migration_sql_dir=migration_sql_dir,
                    #query_files=query_files, # Not used directly, rewritten_queries_base_dir is used
                    rewritten_queries_base_dir = rewritten_queries_base_dir,
                    frequencies_by_timestep=frequencies_by_timestep,
                    timeout_minutes=30,
                    verbose=True,
                    ease_mode=ease_mode
                )
            
            # 結果を保存
            output_dir = self.exp_dir / "time_dependent_output" / self.query_set
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 静的モード + bigsubs の場合は別ファイル名
            if mode == 'static' and static_algorithm == 'bigsubs':
                output_file = output_dir / f"benchmark_results_static_bigsubs{self.exp_suffix}.json"
            else:
                output_file = output_dir / f"benchmark_results_{mode}{self.exp_suffix}.json"
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(benchmark_results, f, indent=2, ensure_ascii=False)
            
            self.print_success(f"\nベンチマーク結果を保存: {output_file}")
            
            # サマリー表示
            summary = benchmark_results.get('summary', {})
            self.print_info(f"  総タイムステップ数: {summary.get('total_timesteps', 0)}")
            
            if mode == 'dynamic':
                self.print_info(f"  総マイグレーション時間: {summary.get('total_migration_time', 0):.2f}秒")
            elif mode == 'static':
                self.print_info(f"  初期MV作成時間: {summary.get('initial_mv_creation_time', 0):.2f}秒")
            
            self.print_info(f"  総クエリ実行時間: {summary.get('total_query_time', 0):.2f}秒")
            self.print_info(f"  総ベンチマーク時間: {summary.get('total_benchmark_time', 0):.2f}秒")
            
            # フェーズ時間を記録
            self.phase_times['phase9_benchmark'] = time.time() - phase_start
            
            return True
            
        except Exception as e:
            self.print_error(f"ベンチマーク実行に失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            executor.close()

    
    def run_post_optimization_phases(self, optimization_mode='dynamic', use_pruning=False, pruning_parallel=False, pruning_workers=None, static_timestep='last', use_static_protection=False, static_algorithm='normal', ease_mode=False):
        """最適化以降のフェーズを実行 (Phase 6-9)
        
        Args:
            optimization_mode: 'static' または 'dynamic' (デフォルト: 'dynamic')
            use_pruning: CF Pruningを使用するか (デフォルト: False)
            pruning_parallel: プルーニングを並列実行するか (デフォルト: False)
            pruning_workers: 並列実行時のワーカー数 (デフォルト: CPUコア数)
            static_timestep: 静的最適化時のタイムステップ ('first' or 'last')
            use_static_protection: 静的最適化のMVを聖域として保護する (デフォルト: False)
            static_algorithm: 静的最適化アルゴリズム ('normal', 'bigsubs', 'both')
        """
        self.print_header(f"最適化以降のフェーズ実行 ({optimization_mode}モード)")
        
        # 全体の開始時刻を記録
        total_start_time = time.time()
        
        # 最適化フェーズ（モードに応じて選択）
        optimization_phase = (6, "MV最適化", lambda: self.phase6_optimize(
            mode=optimization_mode, 
            use_pruning=use_pruning,
            pruning_parallel=pruning_parallel,
            pruning_workers=pruning_workers,
            static_timestep=static_timestep,
            use_static_protection=use_static_protection,
            static_algorithm=static_algorithm
        ))
        
        # SQL生成・クエリ書き換え・ベンチマークフェーズ
        post_optimization_phases = [
            (7, "MV生成SQL作成", lambda: self.phase7_generate_mv_sql(mode=optimization_mode, static_algorithm=static_algorithm)),
            (8, "クエリ書き換え", lambda: self.phase8_rewrite_queries(mode=optimization_mode, static_algorithm=static_algorithm)),
            (9, "ベンチマーク実行", lambda: self.phase9_execute_benchmark(mode=optimization_mode, static_algorithm=static_algorithm, ease_mode=ease_mode)),
        ]
        
        # 全フェーズをまとめる
        phases = [optimization_phase] + post_optimization_phases
        
        for phase_num, phase_name, phase_func in phases:
            try:
                if not phase_func():
                    self.print_error(f"フェーズ{phase_num}で失敗しました")
                    return False
            except Exception as e:
                self.print_error(f"フェーズ{phase_num}でエラー発生: {e}")
                import traceback
                traceback.print_exc()
                return False
        
        # 全体の実行時間を記録
        total_elapsed = time.time() - total_start_time
        
        self.print_header("最適化以降のフェーズ完了")
        self.print_success(f"総実行時間: {total_elapsed:.2f} 秒")
        
        if self.phase_times:
            self.print_info("フェーズ別実行時間:")
            for phase, elapsed in self.phase_times.items():
                if phase in ['phase6_optimization', 'phase7_mv_sql_generation', 'phase8_query_rewriting', 'phase9_benchmark']:
                    self.print_info(f"  {phase}: {elapsed:.2f} 秒")
        
        return True
    
    def run_all_phases(self, optimization_mode='dynamic', use_pruning=False, pruning_parallel=False, pruning_workers=None, static_timestep='last', use_static_protection=False, ease_mode=False):
        """全フェーズを順次実行
        
        Args:
            optimization_mode: 'static' または 'dynamic' (デフォルト: 'dynamic')
            use_pruning: CF Pruningを使用するか (デフォルト: False)
            pruning_parallel: プルーニングを並列実行するか (デフォルト: False)
            pruning_workers: 並列実行時のワーカー数 (デフォルト: CPUコア数)
            static_timestep: 静的最適化時のタイムステップ ('first' or 'last')
            use_static_protection: 静的最適化のMVを聖域として保護する (デフォルト: False)
        """
        self.print_header("小規模実験（通常モード） - 全フェーズ実行")
        
        success = True
        
        # 全体の開始時刻を記録
        total_start_time = time.time()
        
        
        # 基本フェーズ（モードに依存しない）
        basic_phases = [
            (1, "EXPLAIN JSON生成", self.phase1_generate_explain_json),
            (2, "クエリパース", self.phase2_parse_queries),
            (3, "JSONノードID付加", self.phase3_annotate_json),
            (4, "マイグレーションプラン列挙", self.phase4_enumerate_migration_plans),
            (5, "マイグレーションコスト計算", self.phase5_calculate_migration_costs),
        ]
        
        # 最適化フェーズ（モードに応じて選択）
        optimization_phase = (6, "MV最適化", lambda: self.phase6_optimize(
            mode=optimization_mode, 
            use_pruning=use_pruning,
            pruning_parallel=pruning_parallel,
            pruning_workers=pruning_workers,
            static_timestep=static_timestep,
            use_static_protection=use_static_protection
        ))
        
        # SQL生成・クエリ書き換え・ベンチマークフェーズ
        post_optimization_phases = [
            (7, "MV生成SQL作成", lambda: self.phase7_generate_mv_sql(mode=optimization_mode)),
            (8, "クエリ書き換え", lambda: self.phase8_rewrite_queries(mode=optimization_mode)),
            (9, "ベンチマーク実行", lambda: self.phase9_execute_benchmark(mode=optimization_mode, ease_mode=ease_mode)),
        ]
        
        # 全フェーズをまとめる
        phases = basic_phases + [optimization_phase] + post_optimization_phases
        
        for phase_num, phase_name, phase_func in phases:
            try:
                if not phase_func():
                    self.print_error(f"フェーズ{phase_num}で失敗しました")
                    return False
            except Exception as e:
                self.print_error(f"フェーズ{phase_num}でエラー発生: {e}")
                import traceback
                traceback.print_exc()
                return False
        
        # 全体の実行時間を記録
        total_elapsed = time.time() - total_start_time
        
        # フェーズ時間のサマリーを保存
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
        
        self.print_header("全フェーズ完了")
        self.print_success(f"総実行時間: {total_elapsed:.2f} 秒")
        if self.phase_times:
            self.print_info("フェーズ別実行時間:")
            for phase_name, phase_time in self.phase_times.items():
                self.print_info(f"  {phase_name}: {phase_time:.2f} 秒")
        self.print_success(f"サマリーを {summary_file} に保存")
        
        return True


def main():
    parser = argparse.ArgumentParser(description="小規模実験 - 通常モード")
    parser.add_argument(
        '--phase',
        type=str,
        default='all',
        choices=['all', 'post-opt', '0', '1', '2', '3', '4', '5', '6', '6.5', '7', '8', '9'],
        help='実行するフェーズ (all: 全実行, post-opt: 最適化以降(6-9), 0: DB setup, 1: EXPLAIN, 2: Parse, 3: Annotate, 4: Migration plans, 5: Migration costs, 6: Optimize, 6.5: Static Optimize, 7: MV SQL, 8: Rewrite, 9: Benchmark)'
    )
    parser.add_argument(
        '--config',
        type=str,
        default='experiments/small_test_ver2',
        help='実験ディレクトリのパス（設定ファイルは不要）'
    )
    parser.add_argument(
        '--query-set',
        type=str,
        default='job',
        help='実行するクエリセット(job, job_like, explicit_join, etc.)'
    )
    parser.add_argument(
        '--benchmark-mode',
        type=str,
        default='dynamic',
        choices=['dynamic', 'static', 'baseline'],
        help='ベンチマークモード (dynamic: マイグレーションあり, static: 最初のMVのみ, baseline: MVなし)'
    )
    parser.add_argument(
        '--optimization-mode',
        type=str,
        default='dynamic',
        choices=['static', 'dynamic'],
        help='最適化モード (static: 初期タイムステップのみ, dynamic: 時間依存型最適化)'
    )
    parser.add_argument(
        '--use-neurocard',
        action='store_true',
        help='NeuroCardを使用してコスト推定を行う'
    )
    parser.add_argument(
        '--use-deepdb',
        action='store_true',
        help='DeepDBを使用してコスト推定を行う（学習済みアンサンブル必須）'
    )
    parser.add_argument(
        '--use-sampling',
        action='store_true',
        help='サンプリングを使用してコスト推定を行う'
    )
    parser.add_argument(
        '--sampling-parallel',
        action='store_true',
        help='サンプリング計算を並列実行する'
    )
    parser.add_argument(
        '--sampling-workers',
        type=int,
        default=None,
        help='サンプリング並列実行時のワーカー数（デフォルト：CPUコア数）'
    )
    parser.add_argument(
        '--compare',
        action='store_true',
        help='コスト推定結果を比較する（DeepDB使用時のみ有効）'
    )
    parser.add_argument(
        '--use-pruning',
        action='store_true',
        help='CF Pruningを使用してMV候補を削減する（大きなタイムステップ数の場合に推奨）'
    )
    parser.add_argument(
        '--pruning-parallel',
        action='store_true',
        help='CF Pruningを並列実行する（多コアサーバーで推奨）'
    )
    parser.add_argument(
        '--pruning-workers',
        type=int,
        default=None,
        help='並列実行時のワーカー数（デフォルト：CPUコア数）'
    )
    parser.add_argument(
        '--static-protection',
        action='store_true',
        help='プルーニング時に静的最適化のMVを聖域として保護する（ハイブリッドアプローチ）'
    )
    parser.add_argument(
        '--exp-suffix',
        type=str,
        default='',
        help='実験識別用サフィックス（例：_16_2, _16_4）。頻度ファイルと最適化結果ファイルに適用'
    )
    parser.add_argument(
        '--static-timestep',
        type=str,
        default='last',
        choices=['first', 'last', 'average', 'addmv'],
        help='静的最適化で使用するタイムステップ (first: 最初, last: 最後, average: 全時刻の平均, addmv: 頻度和+MV作成コスト考慮)'
    )
    parser.add_argument(
        '--static-algorithm',
        type=str,
        default='normal',
        choices=['normal', 'bigsubs', 'both'],
        help='静的最適化で使用するアルゴリズム (normal: 通常ILP, bigsubs: BigSubs, both: 両方)'
    )
    parser.add_argument(
        '--ease',
        action='store_true',
        help='簡易ベンチマークモード: 各クエリを1回だけ実行し、実行時間に頻度を掛けて推定時間を算出'
    )
    parser.add_argument(
        '--recalc',
        action='store_true',
        help='再計算されたコスト（simple_migration_costs.json）を使用してマイグレーションと利得を計算する'
    )
    
    # Docker/Local switching arguments
    add_docker_args(parser)
    
    args = parser.parse_args()
    
    exp = NormalModeExperiment(
        exp_dir=args.config, 
        query_set=args.query_set, 
        exp_suffix=args.exp_suffix,
        use_docker=args.use_docker,
        recalc_mode=args.recalc
    )
    
    # 接続モードを表示
    print(f"\n[接続モード: {exp.pg_executor.get_mode_description()}]")
    
    if args.phase == 'all':
        success = exp.run_all_phases(
            optimization_mode=args.optimization_mode, 
            use_pruning=args.use_pruning,
            pruning_parallel=args.pruning_parallel,
            pruning_workers=args.pruning_workers,
            static_timestep=args.static_timestep,
            use_static_protection=args.static_protection
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
            ease_mode=args.ease
        )
    elif args.phase == '0':
        success = exp.phase0_setup()
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
            use_neurocard=args.use_neurocard,
            use_deepdb=args.use_deepdb,
            use_sampling=args.use_sampling,
            sampling_parallel=args.sampling_parallel,
            sampling_workers=args.sampling_workers,
            compare=args.compare
        )
    elif args.phase == '6':
        success = exp.phase6_optimize(
            mode=args.optimization_mode, 
            use_pruning=args.use_pruning,
            pruning_parallel=args.pruning_parallel,
            pruning_workers=args.pruning_workers,
            static_timestep=args.static_timestep,
            use_static_protection=args.static_protection
        )
    elif args.phase == '6.5':
        success = exp.phase6b_optimize_static(timestep_position=args.static_timestep)
    elif args.phase == '7':
        success = exp.phase7_generate_mv_sql(mode=args.optimization_mode)
    elif args.phase == '8':
        success = exp.phase8_rewrite_queries(mode=args.optimization_mode)
    elif args.phase == '9':
        success = exp.phase9_execute_benchmark(mode=args.benchmark_mode, ease_mode=args.ease)
    else:
        print(f"不明なフェーズ: {args.phase}")
        success = False
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
