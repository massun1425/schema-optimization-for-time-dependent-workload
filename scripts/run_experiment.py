#!/usr/bin/env python3
"""実験実行メインスクリプト

既存の experiment.py の機能を CLI 化したもの
"""
import argparse
import sys
import os
import time
from pathlib import Path
from typing import List, Dict, Any

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def parse_args():
    """コマンドライン引数解析"""
    parser = argparse.ArgumentParser(
        description="Run MV optimization experiment"
    )
    
    parser.add_argument(
        '--algorithms',
        nargs='+',
        choices=['none', 'normal', 'bigsubs', 'utility', 'utility_capacity', 'frequency'],
        default=['normal'],
        help='Optimization algorithms to run'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default='Output',
        help='Output directory'
    )
    
    parser.add_argument(
        '--skip-mv-creation',
        action='store_true',
        help='Skip MV creation in database'
    )
    
    parser.add_argument(
        '--skip-rewrite',
        action='store_true',
        help='Skip query rewriting'
    )
    
    parser.add_argument(
        '--skip-benchmark',
        action='store_true',
        help='Skip benchmark execution'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Verbose output'
    )
    
    parser.add_argument(
        '--initialize',
        action='store_true',
        help='Initialize CSV comparison before running'
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
        f"{output_dir}/query_rewrite"
    ]
    
    for d in dirs:
        os.makedirs(d, exist_ok=True)
        print(f"Created directory: {d}")


def initialize_csv() -> None:
    """CSV比較を初期化"""
    print("=== Initializing CSV for each ILP ===")
    os.system("python compare_bata.py > Output/compare_bata.out")


def cleanup_mv_files() -> None:
    """MV関連ファイルをクリーンアップ"""
    print("  Cleaning up MV files...")
    
    # MVファイル削除
    mv_dir = "Output/query_rewrite/mv"
    if os.path.exists(mv_dir):
        for file in Path(mv_dir).glob("*"):
            file.unlink()
    
    # データベースからMV削除
    if os.path.exists("delete_mv.sh"):
        os.system("bash delete_mv.sh > /dev/null 2>&1")


def run_ilp_optimization(
    ilp_type: str,
    output_dir: str,
    skip_mv_creation: bool = False,
    skip_rewrite: bool = False,
    skip_benchmark: bool = False,
    verbose: bool = False
) -> None:
    """ILP最適化を実行
    
    Args:
        ilp_type: ILPアルゴリズムタイプ
        output_dir: 出力ディレクトリ
        skip_mv_creation: MV作成をスキップ
        skip_rewrite: クエリ書き換えをスキップ
        skip_benchmark: ベンチマーク実行をスキップ
        verbose: 詳細出力
    """
    print(f"\n{'='*60}")
    print(f"Running ILP: {ilp_type}")
    print(f"{'='*60}")
    
    start_time = time.time()
    
    # MVファイルクリーンアップ
    cleanup_mv_files()
    
    if ilp_type != "none":
        # 1. MV作成SQLスクリプト生成
        if not skip_mv_creation:
            print("\n[1/4] Creating MV SQL scripts...")
            redirect = "" if verbose else f"> {output_dir}/experiment/mv_create/mv_{ilp_type}.out"
            os.system(f"python re_sql_exe.py {ilp_type} mv {redirect}")
        
        # 2. データベースにMV作成
        if not skip_mv_creation:
            print("[2/4] Creating MVs in database...")
            redirect = "" if verbose else f"> {output_dir}/experiment/run_mv/{ilp_type}.out"
            
            if os.path.exists("run_mv.sh"):
                os.system(f"bash run_mv.sh {ilp_type} {redirect}")
            else:
                print("  Warning: run_mv.sh not found, skipping MV creation in database")
        
        # 3. クエリ書き換え
        if not skip_rewrite:
            print("[3/4] Rewriting queries...")
            redirect = "" if verbose else f"> {output_dir}/experiment/mv_create/query_{ilp_type}.out"
            os.system(f"python re_sql_exe.py {ilp_type} {redirect}")
    
    # 4. 書き換えられたクエリを実行
    print("[4/4] Running rewritten queries...")
    redirect = "" if verbose else f"> {output_dir}/query_rewrite/{ilp_type}.out"
    os.system(f"python execute_rewritten.py {ilp_type} {redirect}")
    
    # 5. ワークロードセットアップ
    if not skip_benchmark:
        print("\n[Benchmark] Setting up workloads...")
        os.system(f"python setup_rewritten.py {ilp_type}")
        
        # 6. RedBench実行
        print("[Benchmark] Running RedBench...")
        cwd = os.getcwd()
        
        if os.path.exists("dataset/redbench"):
            os.chdir("dataset/redbench")
            redirect = "" if verbose else f"> ../../{output_dir}/redbench/{ilp_type}.out"
            os.system(f"python run.py {redirect}")
            os.chdir(cwd)
        else:
            print("  Warning: dataset/redbench not found, skipping benchmark")
    
    elapsed = time.time() - start_time
    print(f"\n✓ Completed {ilp_type} in {elapsed:.2f} seconds")


def main():
    """メイン処理"""
    args = parse_args()
    
    print("="*60)
    print("MV Query Optimization Experiment")
    print("="*60)
    print(f"Algorithms: {', '.join(args.algorithms)}")
    print(f"Output: {args.output}")
    print("="*60)
    
    # ディレクトリセットアップ
    setup_directories(args.output)
    
    # CSV初期化
    if args.initialize:
        initialize_csv()
    
    # 各アルゴリズムで実行
    total_start = time.time()
    
    for ilp_type in args.algorithms:
        try:
            run_ilp_optimization(
                ilp_type=ilp_type,
                output_dir=args.output,
                skip_mv_creation=args.skip_mv_creation,
                skip_rewrite=args.skip_rewrite,
                skip_benchmark=args.skip_benchmark,
                verbose=args.verbose
            )
        except Exception as e:
            print(f"\n✗ Error running {ilp_type}: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            continue
    
    total_elapsed = time.time() - total_start
    
    print("\n" + "="*60)
    print("Experiment completed successfully!")
    print(f"Total time: {total_elapsed:.2f} seconds")
    print(f"Results saved to: {args.output}/")
    print("="*60)


if __name__ == '__main__':
    main()
