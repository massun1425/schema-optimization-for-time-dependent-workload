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
import pickle
import subprocess
import sys
import yaml
from pathlib import Path
from typing import Optional

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from src.core.query_parser import QueryParser
from src.optimization.factory import OptimizerFactory
from src.utils.legacy import get_all_job_queries, natural_sort_key


class NormalModeExperiment:
    """通常モード実験の段階的実行クラス"""
    
    def __init__(self, config_path: str = "config.yaml", query_set: str = "job_like"):
        """初期化
        
        Args:
            config_path: 設定ファイルのパス
            query_set: 使用するクエリセット名 (例: job_style, explicit_join)
        """
        self.config_path = Path(config_path)
        self.exp_dir = self.config_path.parent
        self.query_set = query_set  # クエリセット名を保存
        
        # UTF-8でYAMLを読み込む
        with open(self.config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        
        # 一時ファイルに書き込んでからSettingsを読み込む
        temp_config = self.exp_dir / '.temp_config.yaml'
        with open(temp_config, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f, allow_unicode=True)
        
        try:
            self.settings = Settings.from_yaml(str(temp_config))
        finally:
            if temp_config.exists():
                temp_config.unlink()
        
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
    
    def phase0_setup(self):
        """フェーズ0: データベースセットアップ (setup_imdb.pyを使用)"""
        self.print_header("データベースセットアップ", 0)
        
        try:
            # setup_imdbモジュールのインポート
            from experiments.small_test_ver2.scripts.setup_imdb import IMDBSetup
            
            # セットアップクラスの初期化
            setup = IMDBSetup(str(self.config_path))
            
            self.print_info("IMDBデータベースのセットアップを開始します...")
            
            # 1. データのダウンロード（存在確認含む）
            if not setup.download_imdb_data():
                self.print_error("IMDBデータのダウンロードに失敗しました")
                return False
            
            # 2. データベース作成とスキーマ適用
            if not setup.create_database():
                self.print_error("データベース作成に失敗しました")
                return False
            
            # 3. データインポート
            if not setup.import_data():
                self.print_error("データインポートに失敗しました")
                return False
            
            # 4. インデックス作成
            if not setup.create_indexes():
                self.print_error("インデックス作成に失敗しました")
                return False
            
            # 5. 検証
            if not setup.verify_setup():
                self.print_error("セットアップ検証に失敗しました")
                return False
                
            self.print_success("データベースセットアップ完了")
            return True
            
        except ImportError as e:
            self.print_error(f"setup_imdb.py のインポートに失敗しました: {e}")
            return False
        except Exception as e:
            self.print_error(f"セットアップ中にエラーが発生しました: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def phase1_generate_explain_json(self):
        """フェーズ1: EXPLAIN JSON 生成"""
        self.print_header("EXPLAIN JSON 生成", 1)
        
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
            explain_sql = f"EXPLAIN (FORMAT JSON, COSTS TRUE, VERBOSE FALSE) {query_sql}"
            
            try:
                result = subprocess.run(
                    ["psql", "-U", "postgres", "-d", self.settings.database.database,
                     "-t", "-A", 
                     "-c", "SET enable_bitmapscan = off;",
                     "-c", explain_sql],
                    capture_output=True,
                    text=True,
                    check=True,
                    encoding='utf-8',
                    errors='replace',
                    env={**subprocess.os.environ, 'PGPASSWORD': ''}
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
                query_paths = []
                query_count = {}
                
                job_dir = Path(path)
                print(f"  [DEBUG] custom_get_all_job_queries called with path: {path}")
                print(f"  [DEBUG] Directory exists: {job_dir.exists()}")
                
                if not job_dir.exists():
                    return [], {}
                
                for json_file in sorted(job_dir.glob("*.json")):
                    query_path = str(json_file)
                    query_paths.append(query_path)
                    query_count[query_path] = 1
                
                print(f"  [DEBUG] Found {len(query_paths)} JSON files")
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
            
            return True
            
        except Exception as e:
            self.print_error(f"マイグレーションプラン列挙に失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def phase5_calculate_migration_costs(self):
        """フェーズ5: マイグレーションコスト計算"""
        self.print_header("マイグレーションコスト計算", 5)
        
        # マイグレーションプランファイルの存在確認
        plans_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_plans.json"
        
        if not plans_file.exists():
            self.print_error("マイグレーションプランが見つかりません")
            self.print_info("先にフェーズ2.7を実行してください")
            return False
        
        try:
            from experiments.small_test_ver2.migration.simple_migration_cost_calculator import SimpleMigrationCostCalculator
            
            self.print_info("マイグレーションコストを計算中...")
            
            # SimpleMigrationCostCalculatorのインスタンスを作成
            calculator = SimpleMigrationCostCalculator(
                settings=self.settings,
                query_set=self.query_set
            )
            
            # コストを計算・保存
            costs = calculator.calculate_all_costs()
            
            # 出力ファイルのパスを確認
            output_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_costs.json"
            
            if output_file.exists():
                self.print_success(f"マイグレーションコストを保存: {output_file}")
                self.print_info(f"  {len(costs)}個のノードのコストを計算")
            else:
                self.print_error("マイグレーションコストファイルが見つかりません")
                return False
            
            return True
            
        except Exception as e:
            self.print_error(f"マイグレーションコスト計算に失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def phase6_optimize(self):
        """フェーズ6: ILP最適化（時間依存型・マイグレーションコスト考慮）"""
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
        
        try:
            from experiments.small_test_ver2.core.io_loaders import (
                load_timesteps_and_frequencies,
                parse_migration_costs,
            )
            from experiments.small_test_ver2.core.time_dependent_optimizer import TimeDependentOptimizer
            
            # ストレージ予算
            B_max = float(self.settings.optimization.storage_limit_bytes)
            
            # タイムステップと頻度を読み込み
            self.print_info("タイムステップと頻度情報を読み込み中...")
            timesteps, frequencies = load_timesteps_and_frequencies(str(self.exp_dir), self.query_set)
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
            
            # マイグレーションコストを読み込み
            self.print_info("マイグレーションコストを読み込み中...")
            recipes = parse_migration_costs(
                str(self.exp_dir), 
                self.qp.node_list, 
                self.query_set,
                "migration_costs.json"
            )
            self.print_success(f"  {len(recipes)}個のMVのレシピを読み込み完了")
            
            # オプティマイザを初期化
            self.print_info("オプティマイザを初期化中...")
            optimizer = TimeDependentOptimizer(
                node_list=self.qp.node_list,
                u_ij=self.qp.u_ij,
                X=self.qp.X,
                b_j=self.qp.b_j,
                B_max=B_max,
                timesteps=timesteps,
                migration_recipes=recipes,
                query_frequency_by_timestep=frequencies,
                gurobi_output=1,
            )
            
            # 最適化を実行
            self.print_info("最適化を実行中...")
            result = optimizer.optimize(time_limit=300)
            
            # マイグレーション分析
            self.print_info("マイグレーション分析を実行中...")
            enhanced_result = self._analyze_migration_transitions(result, recipes, B_max)
            
            # 結果を表示
            self.print_success("最適化完了")
            self.print_info(f"  総目的関数値: {enhanced_result['objective']:.4f}")
            self.print_info(f"  ワークロードコスト: {enhanced_result['workload_cost']:.4f}")
            self.print_info(f"  マイグレーションコスト: {enhanced_result['migration_cost']:.4f}")
            self.print_info(f"  実行時間: {enhanced_result['solve_time_sec']:.2f} 秒")
            
            # 結果を保存（run_time_dependent_with_migration.pyと同じディレクトリ構造）
            result_dir = self.exp_dir / "time_dependent_output" / self.query_set
            result_dir.mkdir(parents=True, exist_ok=True)
            result_file = result_dir / "td_mv_optimization_result.json"
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(enhanced_result, f, indent=2, ensure_ascii=False)
            self.print_success(f"結果を {result_file} に保存")
            
            # 結果をインスタンス変数に保存（後続フェーズで使用）
            self.result = enhanced_result
            
            return True

        except Exception as e:
            self.print_error(f"最適化に失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _analyze_migration_transitions(self, result: dict, recipes: dict, B_max: float) -> dict:
        """マイグレーション遷移を分析"""
        timesteps = result["timesteps"]
        z_by_timestep = result["z_by_timestep"]
        
        migration_analysis = []
        
        for t in range(len(timesteps)):
            timestep_name = timesteps[t]
            current_mvs = set(j for j, v in enumerate(z_by_timestep[t]) if v == 1)
            
            # タイムステップごとの情報
            selected_nodes = [self.qp.node_list[j] for j in sorted(current_mvs)]
            total_size = sum(self.qp.b_j[j] for j in current_mvs)
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
                        "total_size": round(sum(self.qp.b_j[j] for j in maintained), 2)
                    },
                    "created": {
                        "count": len(created),
                        "mvs": [self.qp.node_list[j] for j in sorted(created)],
                        "total_size": round(sum(self.qp.b_j[j] for j in created), 2)
                    },
                    "deleted": {
                        "count": len(deleted),
                        "mvs": [self.qp.node_list[j] for j in sorted(deleted)],
                        "total_size": round(sum(self.qp.b_j[j] for j in deleted), 2)
                    }
                }
                
                # 作成コストの計算
                creation_cost = 0.0
                creation_details = []
                
                for j in sorted(created):
                    mv_recipes = recipes.get(j, [(tuple(), float("inf"))])
                    applicable_recipes = [
                        (recipe, cost) for recipe, cost in mv_recipes
                        if all(dep in prev_mvs for dep in recipe)
                    ]
                    
                    if applicable_recipes:
                        best_recipe, best_cost = min(applicable_recipes, key=lambda x: x[1])
                        creation_cost += best_cost
                        creation_details.append({
                            "mv": self.qp.node_list[j],
                            "size": round(self.qp.b_j[j], 2),
                            "cost": round(best_cost, 2),
                            "dependencies": [self.qp.node_list[dep] for dep in best_recipe] if best_recipe else []
                        })
                
                migration_details["creation_cost"] = round(creation_cost, 2)
                migration_details["creation_details"] = creation_details
                
                timestep_info["migration"] = migration_details
            else:
                # 初期タイムステップ
                initial_cost = 0.0
                creation_details = []
                
                for j in sorted(current_mvs):
                    mv_recipes = recipes.get(j, [(tuple(), 0.0)])
                    empty_recipes = [(recipe, cost) for recipe, cost in mv_recipes if len(recipe) == 0]
                    if empty_recipes:
                        _, cost = min(empty_recipes, key=lambda x: x[1])
                        initial_cost += cost
                        creation_details.append({
                            "mv": self.qp.node_list[j],
                            "size": round(self.qp.b_j[j], 2),
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
    
    def phase7_generate_mv_sql(self):
        """フェーズ7: タイムステップごとのマイグレーションSQL作成"""
        self.print_header("マイグレーションSQL作成", 7)
        
        if self.qp is None:
            if not self.pickle_path.exists():
                self.print_error(f"{self.pickle_path} が見つかりません")
                return False
            
            self.print_info(f"パース結果を読み込み中: {self.pickle_path}")
            with open(self.pickle_path, 'rb') as f:
                self.qp = pickle.load(f)
        
        if self.result is None:
            # Load time-dependent optimization result
            result_file = self.exp_dir / "time_dependent_output" / self.query_set / "td_mv_optimization_result.json"
            
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
                                    f.write(f"{sql}\n\n")
                                    created_count += 1
                        
                        f.write(f"-- {created_count}個のMVを作成\n")
                
                sql_count = len(mvs_to_create) + len(mvs_to_drop)
                total_sql_count += sql_count
                
                self.print_success(f"  タイムステップ '{timestep_name}': {output_file.name}")
                self.print_info(f"    作成: {len(mvs_to_create)}個, 削除: {len(mvs_to_drop)}個")
            
            self.print_success(f"タイムステップごとのマイグレーションSQLを生成 → {output_dir}")
            self.print_info(f"  総操作数: {total_sql_count}")
            
            return True
            
        except Exception as e:
            self.print_error(f"SQL生成に失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
    


    
    def phase8_rewrite_queries(self):
        """フェーズ8: 時間依存型クエリ書き換え（タイムステップごと）"""
        self.print_header("時間依存型クエリ書き換え", 8)
        
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
        result_file = self.exp_dir / "time_dependent_output" / self.query_set / "td_mv_optimization_result.json"
        
        if not result_file.exists():
            self.print_error("時間依存型最適化結果が見つかりません")
            self.print_info("先にフェーズ3を実行してください")
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
                usage_positions = [[i, 0] for i in range(len(query_files))]
                
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
            rewriter = QueryRewriter(self.settings)
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
        
        self.print_success(f"\n合計 {total_rewritten}個のクエリを書き換え完了")
        self.print_info(f"  出力先: {base_output_dir}")
        
        return True
    
    def phase9_execute_benchmark(self, mode='dynamic'):
        """フェーズ9: 時間依存型ベンチマーク実行
        
        Args:
            mode: ベンチマークモード
                - 'dynamic': 動的MV（マイグレーションあり）
                - 'static': 静的MV（最初のタイムステップのみ）
                - 'baseline': ベースライン（MVなし）
        """
        mode_names = {
            'dynamic': '動的MV（マイグレーションあり）',
            'static': '静的MV（マイグレーションなし）',
            'baseline': 'ベースライン（MVなし）'
        }
        
        self.print_header(f"時間依存型ベンチマーク実行 - {mode_names.get(mode, mode)}", 9)
        
        from experiments.small_test_ver2.benchmark import TimeDependentQueryExecutor
        from experiments.small_test_ver2.core.io_loaders import load_timesteps_and_frequencies
        
        # モードに応じて最適化結果の読み込み要否を判定
        optimization_result = None
        migration_sql_dir = None
        
        if mode in ['dynamic', 'static']:
            # 最適化結果を読み込み
            result_file = self.exp_dir / "time_dependent_output" / self.query_set / "td_mv_optimization_result.json"
            
            if not result_file.exists():
                self.print_error("時間依存型最適化結果が見つかりません")
                self.print_info("先にフェーズ6を実行してください")
                return False
            
            with open(result_file, 'r', encoding='utf-8') as f:
                optimization_result = json.load(f)
            
            # migration_analysisの存在確認
            if 'migration_analysis' not in optimization_result:
                self.print_error("時間依存型最適化結果ではありません")
                return False
            
            # マイグレーションSQLディレクトリ
            migration_sql_dir = self.exp_dir / "time_dependent_output" / self.query_set
            
            if not migration_sql_dir.exists() and mode == 'dynamic':
                self.print_error(f"マイグレーションSQLディレクトリが見つかりません: {migration_sql_dir}")
                self.print_info("先にフェーズ7を実行してください")
                return False
        
        # クエリファイルを取得
        query_files = sorted(self.queries_dir.glob("*.sql"), key=lambda x: x.name)
        
        if not query_files:
            self.print_error("クエリファイルが見つかりません")
            return False
        
        self.print_info(f"クエリ数: {len(query_files)}")
        
        # 頻度情報を読み込み
        self.print_info("頻度情報を読み込み中...")
        try:
            timesteps, frequencies_by_timestep = load_timesteps_and_frequencies(
                str(self.exp_dir), 
                self.query_set
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
                # ベースライン: MVなし
                benchmark_results = executor.execute_baseline_benchmark(
                    query_files=query_files,
                    frequencies_by_timestep=frequencies_by_timestep,
                    timesteps=timesteps,
                    timeout_minutes=30,
                    verbose=True
                )
            elif mode == 'static':
                # 静的MV: 最初のタイムステップのみ
                benchmark_results = executor.execute_static_mv_benchmark(
                    optimization_result=optimization_result,
                    migration_sql_dir=migration_sql_dir,
                    query_files=query_files,
                    frequencies_by_timestep=frequencies_by_timestep,
                    timeout_minutes=30,
                    verbose=True
                )
            else:  # dynamic
                # 動的MV: マイグレーションあり（既存）
                benchmark_results = executor.execute_time_dependent_benchmark(
                    optimization_result=optimization_result,
                    migration_sql_dir=migration_sql_dir,
                    query_files=query_files,
                    frequencies_by_timestep=frequencies_by_timestep,
                    timeout_minutes=30,
                    verbose=True
                )
            
            # 結果を保存
            output_dir = self.exp_dir / "time_dependent_output" / self.query_set
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / f"benchmark_results_{mode}.json"
            
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
            
            return True
            
        except Exception as e:
            self.print_error(f"ベンチマーク実行に失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            executor.close()

    
    def run_all_phases(self):
        """全フェーズを順番に実行"""
        self.print_header("小規模実験（通常モード） - 全フェーズ実行")
        
        phases = [
            (0, "データベースセットアップ", self.phase0_setup),
            (1, "EXPLAIN JSON生成", self.phase1_generate_explain_json),
            (2, "クエリパース", self.phase2_parse_queries),
            (3, "JSONノードID付加", self.phase3_annotate_json),
            (4, "マイグレーションプラン列挙", self.phase4_enumerate_migration_plans),
            (5, "マイグレーションコスト計算", self.phase5_calculate_migration_costs),
            (6, "ILP最適化", self.phase6_optimize),
            (7, "MV生成SQL作成", self.phase7_generate_mv_sql),
            (8, "クエリ書き換え", self.phase8_rewrite_queries),
            (9, "ベンチマーク実行", self.phase9_execute_benchmark),
        ]
        
        for phase_num, phase_name, phase_func in phases:
            if not phase_func():
                print(f"\n✗ フェーズ{phase_num}で失敗しました")
                return False
        
        self.print_header("実験完了！")
        self.print_success("全フェーズが正常に完了しました")
        self.print_info(f"結果は {self.exp_dir} に保存されています")
        
        return True


def main():
    parser = argparse.ArgumentParser(description="小規模実験 - 通常モード")
    parser.add_argument(
        '--phase',
        type=str,
        default='all',
        choices=['all', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9'],
        help='実行するフェーズ (all: 全実行, 0: DB setup, 1: EXPLAIN, 2: Parse, 3: Annotate, 4: Migration plans, 5: Migration costs, 6: Optimize, 7: MV SQL, 8: Rewrite, 9: Benchmark)'
    )
    parser.add_argument(
        '--config',
        type=str,
        default='experiments/small_test_ver2/config.yaml',
        help='設定ファイルのパス'
    )
    parser.add_argument(
        '--query-set',
        type=str,
        default='job_like',
        help='実行するクエリセット(job_like, explicit_join, etc.)'
    )
    parser.add_argument(
        '--benchmark-mode',
        type=str,
        default='dynamic',
        choices=['dynamic', 'static', 'baseline'],
        help='ベンチマークモード (dynamic: マイグレーションあり, static: 最初のMVのみ, baseline: MVなし)'
    )
    
    args = parser.parse_args()
    
    exp = NormalModeExperiment(args.config, query_set=args.query_set)
    
    if args.phase == 'all':
        success = exp.run_all_phases()
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
        success = exp.phase5_calculate_migration_costs()
    elif args.phase == '6':
        success = exp.phase6_optimize()
    elif args.phase == '7':
        success = exp.phase7_generate_mv_sql()
    elif args.phase == '8':
        success = exp.phase8_rewrite_queries()
    elif args.phase == '9':
        success = exp.phase9_execute_benchmark(mode=args.benchmark_mode)
    else:
        print(f"不明なフェーズ: {args.phase}")
        success = False
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
