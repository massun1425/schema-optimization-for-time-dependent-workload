"""クエリ実行とベンチマーク機能"""

import time
from pathlib import Path
from typing import Optional
import logging

import psycopg2
from psycopg2.extensions import QueryCanceledError

from config.settings import Settings

logger = logging.getLogger(__name__)


class QueryExecutor:
    """クエリ実行管理クラス"""
    
    def __init__(self, settings: Settings):
        """初期化
        
        Args:
            settings: 設定オブジェクト
        """
        self.settings = settings
        self.db_config = settings.database
        self.connection = None
    
    def _get_connection(self):
        """データベース接続を取得または作成"""
        if self.connection is None or self.connection.closed:
            self.connection = psycopg2.connect(
                host=self.db_config.host,
                port=self.db_config.port,
                user=self.db_config.user,
                password=self.db_config.password,
                database=self.db_config.database
            )
        return self.connection
    
    def execute_query_file(
        self, 
        query_file: Path, 
        timeout_minutes: int = 30
    ) -> dict:
        """SQLファイルを実行
        
        Args:
            query_file: 実行するSQLファイルのパス
            timeout_minutes: タイムアウト時間（分）
            
        Returns:
            実行結果の辞書 {'success': bool, 'time': float, 'error': str}
        """
        start_time = time.time()
        
        # SQLファイルを読み込み
        try:
            with open(query_file, 'r', encoding='utf-8') as f:
                query = f.read().strip()
        except Exception as e:
            logger.error(f"Error reading {query_file.name}: {e}")
            return {
                'success': False,
                'time': 0.0,
                'error': str(e)
            }
        
        if not query:
            logger.warning(f"Empty query in {query_file.name}")
            return {
                'success': False,
                'time': 0.0,
                'error': 'Empty query'
            }
        
        # クエリを実行
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # タイムアウトを設定
            timeout_ms = timeout_minutes * 60 * 1000
            cursor.execute(f"SET statement_timeout = '{timeout_ms}'")
            
            logger.debug(f"Executing: {query_file.name}")
            
            # クエリを実行
            cursor.execute(query)
            
            # 結果を取得（実際にクエリを実行するために重要）
            try:
                results = cursor.fetchall()
                row_count = len(results)
            except psycopg2.ProgrammingError:
                # 結果を返さないクエリ（CREATE, INSERTなど）
                row_count = cursor.rowcount
            
            conn.commit()
            cursor.close()
            
            elapsed = time.time() - start_time
            
            return {
                'success': True,
                'time': elapsed,
                'error': None,
                'row_count': row_count
            }
                
        except QueryCanceledError:
            elapsed = time.time() - start_time
            logger.warning(f"Query {query_file.name} timed out after {timeout_minutes} minutes")
            if self.connection:
                self.connection.rollback()
            return {
                'success': False,
                'time': elapsed,
                'error': f'Timeout after {timeout_minutes} minutes'
            }
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Error executing {query_file.name}: {e}")
            if self.connection:
                self.connection.rollback()
            return {
                'success': False,
                'time': elapsed,
                'error': str(e)
            }
    
    def execute_benchmark(
        self, 
        query_dir: Path,
        timeout_minutes: int = 30,
        verbose: bool = False
    ) -> dict:
        """ベンチマークを実行
        
        Args:
            query_dir: クエリファイルが格納されているディレクトリ
            timeout_minutes: 各クエリのタイムアウト時間（分）
            verbose: 詳細ログを出力するか
            
        Returns:
            ベンチマーク結果の辞書
        """
        from src.utils.legacy import natural_sort_key
        
        logger.info(f"Starting benchmark execution from {query_dir}")
        
        # クエリファイルを取得してソート
        query_files = sorted(
            query_dir.glob("*.sql"),
            key=lambda x: natural_sort_key(str(x))
        )
        
        if not query_files:
            logger.error(f"No SQL files found in {query_dir}")
            return {
                'total_queries': 0,
                'successful': 0,
                'failed': 0,
                'total_time': 0,
                'queries': []
            }
        
        logger.info(f"Found {len(query_files)} queries to execute")
        
        results = []
        successful = 0
        failed = 0
        total_time = 0
        
        benchmark_start = time.time()
        
        for idx, query_file in enumerate(query_files, 1):
            logger.info(f"[{idx}/{len(query_files)}] Executing {query_file.name}...")
            
            result = self.execute_query_file(query_file, timeout_minutes)
            total_time += result['time']
            
            if result['success']:
                successful += 1
                logger.info(f"  ✓ Success ({result['time']:.2f}s)")
            else:
                failed += 1
                error_msg = result['error']
                if error_msg and len(error_msg) > 100:
                    error_msg = error_msg[:100] + "..."
                logger.warning(f"  ✗ Failed ({result['time']:.2f}s): {error_msg}")
                
                if verbose and result['error']:
                    logger.debug(f"Full error: {result['error']}")
            
            results.append({
                'query_id': query_file.stem,
                'query_file': str(query_file),
                'success': result['success'],
                'execution_time': round(result['time'], 2),
                'error': result['error']
            })
        
        benchmark_elapsed = time.time() - benchmark_start
        
        # サマリーを表示
        logger.info("")
        logger.info("Benchmark Summary:")
        logger.info(f"  Total queries: {len(query_files)}")
        logger.info(f"  ✓ Successful: {successful}")
        logger.info(f"  ✗ Failed: {failed}")
        logger.info(f"  Total execution time: {total_time:.2f}s")
        logger.info(f"  Avg time per query: {total_time/len(query_files):.2f}s")
        logger.info(f"  Benchmark elapsed: {benchmark_elapsed:.2f}s")
        
        return {
            'total_queries': len(query_files),
            'successful': successful,
            'failed': failed,
            'total_time': round(total_time, 2),
            'benchmark_elapsed': round(benchmark_elapsed, 2),
            'avg_time_per_query': round(total_time / len(query_files), 2) if query_files else 0,
            'queries': results
        }
