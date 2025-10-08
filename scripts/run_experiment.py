#!/usr/bin/env python3
"""実験実行メインスクリプト

src/ 配下のリファクタリング済みコードを使用した実験実行スクリプト
"""
import argparse
import os
import sys
import time
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# src/ 配下のモジュールをインポート
from src.core.query_manager import QueryManager
from src.core.query_parser import QueryParser
from src.optimization.factory import OptimizerFactory
from src.database.connection import DatabaseConnection
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


def _topological_sort_mvs(mvs: list, qm) -> list:
    """Sort MVs in topological order (dependencies first).
    
    Args:
        mvs: List of MaterializedView objects
        qm: QueryManager with node information
        
    Returns:
        Sorted list of MVs
    """
    from collections import defaultdict, deque
    
    # Build dependency graph
    mv_dict = {mv.node_id: mv for mv in mvs}
    in_degree = {node_id: 0 for node_id in mv_dict}
    graph = defaultdict(list)
    
    for node_id in mv_dict:
        if node_id.startswith('non_leaf_'):
            # Get children from non_leaf_nodes_map_r
            if node_id in qm.non_leaf_nodes_map_r:
                children = qm.non_leaf_nodes_map_r[node_id]
                for child_id in children:
                    if child_id in mv_dict:
                        # child_id depends on nothing (or other nodes)
                        # node_id depends on child_id
                        graph[child_id].append(node_id)
                        in_degree[node_id] += 1
    
    # Topological sort using Kahn's algorithm
    queue = deque([node_id for node_id in mv_dict if in_degree[node_id] == 0])
    sorted_node_ids = []
    
    while queue:
        node_id = queue.popleft()
        sorted_node_ids.append(node_id)
        
        for neighbor in graph[node_id]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    
    # Check for cycles
    if len(sorted_node_ids) != len(mv_dict):
        logger.warning(f"Circular dependency detected! Only {len(sorted_node_ids)}/{len(mv_dict)} nodes sorted")
        # Add remaining nodes at the end
        remaining = [node_id for node_id in mv_dict if node_id not in sorted_node_ids]
        sorted_node_ids.extend(remaining)
    
    # Convert back to MV objects
    return [mv_dict[node_id] for node_id in sorted_node_ids]


def parse_args():
    """コマンドライン引数解析"""
    parser = argparse.ArgumentParser(description="Run MV optimization experiment")

    parser.add_argument(
        "--algorithms",
        nargs="+",
        choices=["none", "normal", "bigsubs", "utility", "utility_capacity", "frequency"],
        default=["normal"],
        help="Optimization algorithms to run",
    )

    parser.add_argument("--output", type=str, default="Output", help="Output directory")

    # Legacy skip flags (deprecated, use --phases instead)
    parser.add_argument(
        "--skip-mv-creation", action="store_true", 
        help="(Deprecated) Skip MV creation in database. Use --phases instead."
    )
    parser.add_argument(
        "--skip-rewrite", action="store_true", 
        help="(Deprecated) Skip query rewriting. Use --phases instead."
    )
    parser.add_argument(
        "--skip-benchmark", action="store_true", 
        help="(Deprecated) Skip benchmark execution. Use --phases instead."
    )

    # New phase control options
    parser.add_argument(
        "--phases",
        nargs="+",
        choices=["query_parsing", "optimization", "mv_creation", "query_rewriting", "benchmark"],
        help="Specify which phases to run (e.g., --phases query_parsing optimization)"
    )
    
    parser.add_argument(
        "--start-from",
        choices=["query_parsing", "optimization", "mv_creation", "query_rewriting", "benchmark"],
        help="Start execution from this phase (inclusive)"
    )
    
    parser.add_argument(
        "--end-at",
        choices=["query_parsing", "optimization", "mv_creation", "query_rewriting", "benchmark"],
        help="End execution at this phase (inclusive)"
    )

    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    
    parser.add_argument(
        "--storage-limit", 
        type=int, 
        default=50 * 1024 * 1024,  # 50MB
        help="Storage limit for materialized views in bytes (default: 50MB)"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        help="Path to configuration YAML file (overrides default)"
    )

    return parser.parse_args()


def setup_directories(output_dir: str) -> None:
    """必要なディレクトリを作成

    Args:
        output_dir: 出力ベースディレクトリ
    """
    dirs = [
        f"{output_dir}/experiment/run_mv",
        f"{output_dir}/experiment/mv_create",
        f"{output_dir}/redbench",
        f"{output_dir}/query_rewrite",
    ]

    for d in dirs:
        os.makedirs(d, exist_ok=True)
        print(f"Created directory: {d}")


def cleanup_mv_files() -> None:
    """MV関連ファイルをクリーンアップ"""
    logger.info("Cleaning up MV files...")

    # MVファイル削除
    mv_dir = "Output/query_rewrite/mv"
    if os.path.exists(mv_dir):
        for file in Path(mv_dir).glob("*"):
            file.unlink()
            logger.debug(f"Deleted: {file}")

    # データベースからMV削除
    try:
        from config.settings import Settings
        settings = Settings()
        db = DatabaseConnection(settings.database)
        
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                # 既存のMVを削除
                cur.execute("""
                    SELECT matviewname FROM pg_matviews 
                    WHERE schemaname = 'public'
                """)
                mvs = cur.fetchall()
                for (mv_name,) in mvs:
                    logger.debug(f"Dropping MV: {mv_name}")
                    cur.execute(f"DROP MATERIALIZED VIEW IF EXISTS {mv_name} CASCADE")
            conn.commit()
        logger.info(f"Dropped {len(mvs)} materialized views")
    except Exception as e:
        logger.warning(f"Error cleaning up MVs: {e}")


def run_ilp_optimization(
    ilp_type: str,
    output_dir: str,
    settings,  # Settings object with execution phase config
    storage_limit: int = 50 * 1024 * 1024,
    verbose: bool = False,
) -> None:
    """ILP最適化を実行（src/ モジュールのみ使用）

    Args:
        ilp_type: ILPアルゴリズムタイプ
        output_dir: 出力ディレクトリ
        settings: Settings object with execution configuration
        storage_limit: ストレージ上限（バイト）
        verbose: 詳細出力
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Running ILP: {ilp_type}")
    logger.info(f"{'='*60}")

    # Display which phases will run
    phases_to_run = []
    for phase in ['query_parsing', 'optimization', 'mv_creation', 'query_rewriting', 'benchmark']:
        if settings.execution.should_run_phase(phase):
            phases_to_run.append(phase)
    logger.info(f"Phases to execute: {', '.join(phases_to_run)}")

    start_time = time.time()
    
    # アルゴリズム専用のディレクトリを作成
    algorithm_dir = Path(output_dir) / ilp_type
    algorithm_dir.mkdir(parents=True, exist_ok=True)
    
    # 各フェーズの実行時間を記録
    phase_times = {}

    # MVファイルクリーンアップ (always run before optimization)
    if settings.execution.should_run_phase('optimization'):
        cleanup_mv_files()

    if ilp_type == "none":
        logger.info("Running with 'none' algorithm (no optimization)")
        elapsed = time.time() - start_time
        logger.info(f"\n✓ Completed {ilp_type} in {elapsed:.2f} seconds")
        return

    try:
        from src.rewrite.query_rewriter import QueryRewriter
        from src.database.mv_manager import MaterializedViewManager
        
        # [1/5] クエリパース
        if settings.execution.should_run_phase('query_parsing'):
            logger.info("[1/5] Parsing queries...")
            pickle_path = Path(output_dir) / "qp_class.pkl"
            
            if pickle_path.exists():
                logger.info(f"Loading query parser from {pickle_path}")
                import pickle
                with open(pickle_path, 'rb') as f:
                    qp = pickle.load(f)
            else:
                logger.info("Creating QueryParser using src/ modules...")
                qp = QueryParser(settings)
                
                query_path = settings.benchmark.queries_dir
                q_num = 0
                insert_query = settings.optimization.insert_queries
                
                qp.query_parse(q_num, query_path, insert_query)
                
                logger.info(f"Saving query parser to {pickle_path}")
                import pickle
                with open(pickle_path, 'wb') as f:
                    pickle.dump(qp, f)
        else:
            logger.info("[1/5] Skipping query parsing (loading from cache)")
            pickle_path = Path(output_dir) / "qp_class.pkl"
            if not pickle_path.exists():
                logger.error("Query parser cache not found! Run with query_parsing phase first.")
                return
            import pickle
            with open(pickle_path, 'rb') as f:
                qp = pickle.load(f)
        
        # [2/5] ILP最適化実行
        if settings.execution.should_run_phase('optimization'):
            phase_start = time.time()
            logger.info(f"[2/5] Running {ilp_type} optimization...")
            logger.info(f"Storage limit: {storage_limit / (1024*1024):.2f} MB")
            
            if not OptimizerFactory.is_available(ilp_type):
                logger.error(f"Algorithm {ilp_type} is not available")
                return
            
            # オプティマイザーのパラメータを準備
            optimizer_params = {
                "qm": qp.qm,
                "s_num": qp.s_num,
                "m_cost": qp.m_cost,
                "node_list": qp.node_list,
                "B_max": storage_limit,
                "b_j": qp.b_j,
                "u_ij": qp.u_ij,
                "X": qp.X,
                "q_s_list": qp.q_s_list,
                "settings": settings,
            }
            
            # BigSubs固有のパラメータを追加
            if ilp_type == "bigsubs":
                optimizer_params.update({
                    "U_j_max": qp.U_j_max if hasattr(qp, 'U_j_max') else [0] * qp.s_num,
                    "U_max": qp.U_max if hasattr(qp, 'U_max') else 0.0,
                    "y_ij": qp.y_ij if hasattr(qp, 'y_ij') else [[0] * qp.s_num for _ in range(len(qp.u_ij))],
                })
                
            optimizer = OptimizerFactory.create(ilp_type, **optimizer_params)
            
            result = optimizer.optimize()
            phase_times['optimization'] = time.time() - phase_start
            
            logger.info(f"Selected {len(result.selected_views)} materialized views")
            logger.info(f"Total utility: {result.total_utility:,.2f}")
            logger.info(f"Total storage: {result.total_storage / (1024*1024):.2f} MB")
            logger.info(f"Optimization time: {phase_times['optimization']:.2f} seconds")
            
            if len(result.selected_views) == 0:
                logger.warning("No MVs selected. Check query parsing and optimization parameters.")
                return
            
            # 最適化結果を保存
            optimization_dir = algorithm_dir / "optimization"
            optimization_dir.mkdir(parents=True, exist_ok=True)
            
            # JSON形式で保存
            result.save_to_json(str(optimization_dir / "result.json"))
            logger.info(f"Saved optimization result to {optimization_dir / 'result.json'}")
            
            # CSV形式で保存（旧形式互換）
            result.save_to_csv(str(optimization_dir / "mv_list.csv"))
            logger.info(f"Saved MV list to {optimization_dir / 'mv_list.csv'}")
        else:
            logger.info("[2/5] Skipping optimization (loading existing results)")
            # Load optimization results from file
            optimization_dir = algorithm_dir / "optimization"
            result_json_path = optimization_dir / "result.json"
            
            if not result_json_path.exists():
                logger.error(f"Optimization result not found: {result_json_path}")
                logger.error("Please run Phase 2 (optimization) first, or check the algorithm name.")
                return
            
            logger.info(f"Loading optimization result from {result_json_path}")
            
            # Load OptimizationResult using the new load_from_json method
            from src.core.models import OptimizationResult
            
            result = OptimizationResult.load_from_json(str(result_json_path))
            logger.info(f"Loaded {len(result.selected_views)} materialized views")
            logger.info(f"Total utility: {result.total_utility:,.2f}")
            logger.info(f"Total storage: {result.total_storage / (1024*1024):.2f} MB")

        
        # [3/5] MV作成SQL生成とデータベースへの登録
        if settings.execution.should_run_phase('mv_creation'):
            phase_start = time.time()
            logger.info("[3/5] Creating MVs in database...")
            mv_manager = MaterializedViewManager(DatabaseConnection(settings.database))
            
            # Sort MVs by dependency order using topological sort
            sorted_mvs = _topological_sort_mvs(result.selected_views, qp.qm)
            
            logger.info(f"Creating {len(sorted_mvs)} MVs in dependency order")
            
            created_count = 0
            failed_count = 0
            mv_creation_log = []
            
            for mv in sorted_mvs:
                mv_start = time.time()
                try:
                    success = mv_manager.create_view_from_model(mv, replace=True)
                    mv_time = time.time() - mv_start
                    
                    if success:
                        created_count += 1
                        status = "SUCCESS"
                        if verbose:
                            logger.info(f"Created MV: {mv.view_id} ({mv_time:.2f}s)")
                    else:
                        failed_count += 1
                        status = "FAILED"
                        logger.warning(f"Failed to create MV: {mv.view_id}")
                    
                    mv_creation_log.append({
                        "view_id": mv.view_id,
                        "node_id": mv.node_id,
                        "status": status,
                        "creation_time": round(mv_time, 2),
                        "size_mb": round(mv.size / (1024 * 1024), 2),
                    })
                except Exception as e:
                    failed_count += 1
                    mv_time = time.time() - mv_start
                    logger.error(f"Failed to create MV {mv.view_id}: {e}")
                    
                    mv_creation_log.append({
                        "view_id": mv.view_id,
                        "node_id": mv.node_id,
                        "status": "ERROR",
                        "creation_time": round(mv_time, 2),
                        "error": str(e),
                    })
                    
                    if verbose:
                        import traceback
                        traceback.print_exc()
            
            phase_times['mv_creation'] = time.time() - phase_start
            logger.info(f"Created {created_count}/{len(sorted_mvs)} MVs ({failed_count} failed)")
            logger.info(f"MV creation time: {phase_times['mv_creation']:.2f} seconds")
            
            # MV作成結果を保存
            mv_creation_dir = algorithm_dir / "mv_creation"
            mv_creation_dir.mkdir(parents=True, exist_ok=True)
            
            import json
            with open(mv_creation_dir / "creation_log.json", 'w', encoding='utf-8') as f:
                json.dump({
                    "total_mvs": len(sorted_mvs),
                    "created": created_count,
                    "failed": failed_count,
                    "total_time": round(phase_times['mv_creation'], 2),
                    "mvs": mv_creation_log,
                }, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved MV creation log to {mv_creation_dir / 'creation_log.json'}")
        else:
            logger.info("[3/5] Skipping MV creation in database")
        
        # [4/5] クエリ書き換え
        if settings.execution.should_run_phase('query_rewriting'):
            phase_start = time.time()
            logger.info("[4/5] Rewriting queries...")
            rewriter = QueryRewriter(settings)
            
            rewritten_dir = Path(output_dir) / "query_rewrite" / "re_sql" / ilp_type
            rewritten_dir.mkdir(parents=True, exist_ok=True)
            
            rewritten_queries = rewriter.rewrite_queries(result.selected_views)
            
            rewrite_log = []
            for query_id, rewritten_sql in rewritten_queries.items():
                query_start = time.time()
                output_file = rewritten_dir / f"{query_id}.sql"
                with open(output_file, 'w') as f:
                    f.write(rewritten_sql)
                query_time = time.time() - query_start
                
                rewrite_log.append({
                    "query_id": query_id,
                    "output_file": str(output_file),
                    "rewrite_time": round(query_time, 4),
                })
            
            phase_times['query_rewriting'] = time.time() - phase_start
            logger.info(f"Rewritten {len(rewritten_queries)} queries to {rewritten_dir}")
            logger.info(f"Query rewriting time: {phase_times['query_rewriting']:.2f} seconds")
            
            # クエリ書き換え結果を保存
            query_rewrite_dir = algorithm_dir / "query_rewrite"
            query_rewrite_dir.mkdir(parents=True, exist_ok=True)
            
            import json
            with open(query_rewrite_dir / "rewrite_log.json", 'w', encoding='utf-8') as f:
                json.dump({
                    "total_queries": len(rewritten_queries),
                    "total_time": round(phase_times['query_rewriting'], 2),
                    "output_directory": str(rewritten_dir),
                    "queries": rewrite_log,
                }, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved query rewrite log to {query_rewrite_dir / 'rewrite_log.json'}")
        else:
            logger.info("[4/5] Skipping query rewriting")
        
        # [5/5] 書き換えられたクエリの実行
        if settings.execution.should_run_phase('benchmark'):
            logger.info("[5/5] Executing rewritten queries...")
            # TODO: ベンチマーク実行機能を src/ に実装
            logger.warning("Benchmark execution not yet implemented in src/ modules")
        else:
            logger.info("[5/5] Skipping benchmark execution")
            
    except Exception as e:
        logger.error(f"Error in ILP optimization: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return

    elapsed = time.time() - start_time
    
    # 統合サマリーを保存
    import json
    summary = {
        "algorithm": ilp_type,
        "total_execution_time": round(elapsed, 2),
        "phases": phase_times,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    
    with open(algorithm_dir / "summary.json", 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n✓ Completed {ilp_type} in {elapsed:.2f} seconds")
    logger.info(f"Results saved to {algorithm_dir}")
    logger.info(f"Summary: {algorithm_dir / 'summary.json'}")


def main():
    """メイン処理"""
    args = parse_args()

    # Load settings from config file or use defaults
    from config.settings import Settings
    if args.config:
        settings = Settings.from_yaml(args.config)
    else:
        settings = Settings()
    
    # Override settings with command-line arguments
    if args.phases or args.start_from or args.end_at:
        # Use new phase control
        if args.phases:
            # Only run specified phases
            settings.execution.query_parsing = 'query_parsing' in args.phases
            settings.execution.optimization = 'optimization' in args.phases
            settings.execution.mv_creation = 'mv_creation' in args.phases
            settings.execution.query_rewriting = 'query_rewriting' in args.phases
            settings.execution.benchmark = 'benchmark' in args.phases
        
        if args.start_from:
            settings.execution.start_from = args.start_from
        
        if args.end_at:
            settings.execution.end_at = args.end_at
    else:
        # Legacy skip flags (backward compatibility)
        if args.skip_mv_creation:
            settings.execution.mv_creation = False
            logger.warning("--skip-mv-creation is deprecated. Use --phases or execution.phases in config YAML.")
        if args.skip_rewrite:
            settings.execution.query_rewriting = False
            logger.warning("--skip-rewrite is deprecated. Use --phases or execution.phases in config YAML.")
        if args.skip_benchmark:
            settings.execution.benchmark = False
            logger.warning("--skip-benchmark is deprecated. Use --phases or execution.phases in config YAML.")

    logger.info("=" * 60)
    logger.info("MV Query Optimization Experiment")
    logger.info("=" * 60)
    logger.info(f"Algorithms: {', '.join(args.algorithms)}")
    logger.info(f"Output: {args.output}")
    logger.info(f"Storage Limit: {args.storage_limit / (1024*1024):.2f} MB")
    
    # Display execution phases
    phases_status = []
    for phase in ['query_parsing', 'optimization', 'mv_creation', 'query_rewriting', 'benchmark']:
        status = "✓" if settings.execution.should_run_phase(phase) else "✗"
        phases_status.append(f"{status} {phase}")
    logger.info(f"Execution Phases:\n  " + "\n  ".join(phases_status))
    logger.info("=" * 60)

    # ディレクトリセットアップ
    setup_directories(args.output)

    # 各アルゴリズムで実行
    total_start = time.time()

    for ilp_type in args.algorithms:
        try:
            run_ilp_optimization(
                ilp_type=ilp_type,
                output_dir=args.output,
                settings=settings,
                storage_limit=args.storage_limit,
                verbose=args.verbose,
            )
        except Exception as e:
            logger.error(f"\n✗ Error running {ilp_type}: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            continue

    total_elapsed = time.time() - total_start

    logger.info("\n" + "=" * 60)
    logger.info("Experiment completed successfully!")
    logger.info(f"Total time: {total_elapsed:.2f} seconds")
    logger.info(f"Results saved to: {args.output}/")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
