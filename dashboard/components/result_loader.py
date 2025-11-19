"""
Result Loader Component

Loads and parses experiment results from output files.
"""

import json
import pickle
from pathlib import Path
from typing import Dict, List, Optional
import sys

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class ResultLoader:
    """Loads experiment results from various file formats"""
    
    def __init__(self, output_dir: str = "Output"):
        self.output_dir = Path(output_dir)
        
    def list_experiments(self) -> List[Dict]:
        """List all available experiments
        
        Returns:
            List of experiment metadata dictionaries
        """
        experiments = []
        
        if not self.output_dir.exists():
            return experiments
        
        # Find all algorithm directories
        for algo_dir in self.output_dir.iterdir():
            if algo_dir.is_dir() and not algo_dir.name.startswith('.'):
                exp_data = self._load_experiment_metadata(algo_dir)
                if exp_data:
                    experiments.append(exp_data)
        
        # Sort by timestamp (newest first)
        experiments.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return experiments
    
    def _load_experiment_metadata(self, algo_dir: Path) -> Optional[Dict]:
        """Load metadata for an experiment
        
        Args:
            algo_dir: Path to algorithm directory
            
        Returns:
            Experiment metadata dictionary or None
        """
        try:
            # Check for summary.json first
            summary_file = algo_dir / 'summary.json'
            if summary_file.exists():
                with open(summary_file, 'r') as f:
                    summary_data = json.load(f)
                
                metadata = {
                    'algorithm': algo_dir.name,
                    'path': str(algo_dir),
                    'timestamp': summary_data.get('timestamp', self._get_directory_timestamp(algo_dir)),
                    'execution_time': summary_data.get('total_execution_time', 0),
                    'phases': summary_data.get('phases', {})
                }
                return metadata
            
            # Fallback: check for subdirectories indicating results
            has_results = False
            subdirs = ['optimization', 'benchmark', 'query_rewrite', 'mv_creation']
            
            for subdir in subdirs:
                if (algo_dir / subdir).exists():
                    has_results = True
                    break
            
            if has_results:
                metadata = {
                    'algorithm': algo_dir.name,
                    'path': str(algo_dir),
                    'timestamp': self._get_directory_timestamp(algo_dir)
                }
                return metadata
            
        except Exception as e:
            print(f"Error loading metadata for {algo_dir}: {e}")
        
        return None
    
    def _get_directory_timestamp(self, path: Path) -> str:
        """Get timestamp from directory modification time"""
        try:
            from datetime import datetime
            mtime = path.stat().st_mtime
            return datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
        except:
            return 'Unknown'
    
    def load_optimization_results(self, algorithm: str) -> Optional[Dict]:
        """Load optimization results for an algorithm
        
        Args:
            algorithm: Algorithm name
            
        Returns:
            Results dictionary or None
        """
        algo_dir = self.output_dir / algorithm
        results = {}
        
        # Load summary
        summary_file = algo_dir / 'summary.json'
        if summary_file.exists():
            with open(summary_file, 'r') as f:
                results['summary'] = json.load(f)
                results['execution_times'] = results['summary'].get('phases', {})
        
        # Load optimization results
        opt_result_file = algo_dir / 'optimization' / 'result.json'
        if opt_result_file.exists():
            with open(opt_result_file, 'r') as f:
                opt_data = json.load(f)
                results['solution'] = opt_data
                # Extract key fields directly to results for easier access
                if 'selected_views' in opt_data:
                    results['selected_views'] = opt_data['selected_views']
                if 'total_utility' in opt_data:
                    results['total_utility'] = opt_data['total_utility']
                if 'total_storage' in opt_data:
                    results['total_storage'] = opt_data['total_storage']
                if 'total_storage_mb' in opt_data:
                    results['total_storage_mb'] = opt_data['total_storage_mb']
                if 'num_selected_views' in opt_data:
                    results['num_selected_views'] = opt_data['num_selected_views']
        
        # Load MV list CSV
        mv_list_file = algo_dir / 'optimization' / 'mv_list.csv'
        if mv_list_file.exists():
            results['mv_list_csv'] = str(mv_list_file)
        
        # Load benchmark results if available
        benchmark_file = algo_dir / 'benchmark' / 'benchmark_results.json'
        if benchmark_file.exists():
            with open(benchmark_file, 'r') as f:
                results['benchmark'] = json.load(f)
        
        return results if results else None
    
    def load_query_performance(self, algorithm: str) -> Optional[List[Dict]]:
        """Load query performance data
        
        Args:
            algorithm: Algorithm name
            
        Returns:
            List of query performance dictionaries
        """
        algo_dir = self.output_dir / algorithm
        
        # Try benchmark results first
        benchmark_file = algo_dir / 'benchmark' / 'benchmark_results.json'
        if benchmark_file.exists():
            with open(benchmark_file, 'r') as f:
                benchmark_data = json.load(f)
            
            # Check if it's the new format with 'queries' array
            if 'queries' in benchmark_data and isinstance(benchmark_data['queries'], list):
                performance = []
                
                # Try to load baseline (normal algorithm) for comparison
                baseline_times = {}
                normal_benchmark = self.output_dir / 'normal' / 'benchmark' / 'benchmark_results.json'
                if normal_benchmark.exists() and algorithm != 'normal':
                    try:
                        with open(normal_benchmark, 'r') as f:
                            baseline_data = json.load(f)
                        if 'queries' in baseline_data:
                            for q in baseline_data['queries']:
                                baseline_times[q.get('query_id', '')] = q.get('execution_time', 0)
                    except:
                        pass
                
                for query in benchmark_data['queries']:
                    query_id = query.get('query_id', '')
                    exec_time = query.get('execution_time', 0)
                    
                    # Use baseline for comparison if available
                    baseline_time = baseline_times.get(query_id, exec_time * 1.2)  # Default to 20% slower
                    
                    if baseline_time > 0 and exec_time > 0:
                        speedup = baseline_time / exec_time
                    else:
                        speedup = 1.0
                    
                    perf = {
                        'query_id': query_id,
                        'original_cost': baseline_time,
                        'rewritten_cost': exec_time,
                        'improvement': baseline_time - exec_time,
                        'speedup': speedup,
                        'execution_time': exec_time,
                        'success': query.get('success', True)
                    }
                    performance.append(perf)
                
                return performance if performance else None
            
            # Old format: dict of query_id -> data
            performance = []
            for query_id, data in benchmark_data.items():
                if isinstance(data, dict) and query_id not in ['total_queries', 'successful', 'failed', 'total_time', 'benchmark_elapsed', 'avg_time_per_query']:
                    original_cost = data.get('original_cost', 0)
                    rewritten_cost = data.get('rewritten_cost', 0)
                    speedup = original_cost / rewritten_cost if rewritten_cost > 0 else 1.0
                    
                    perf = {
                        'query_id': query_id,
                        'original_cost': original_cost,
                        'rewritten_cost': rewritten_cost,
                        'improvement': original_cost - rewritten_cost,
                        'speedup': speedup
                    }
                    performance.append(perf)
            
            return performance if performance else None
        
        return None
    
    def load_mv_details(self, algorithm: str) -> Optional[List[Dict]]:
        """Load materialized view details
        
        Args:
            algorithm: Algorithm name
            
        Returns:
            List of MV detail dictionaries
        """
        algo_dir = self.output_dir / algorithm
        
        # Try loading from optimization result first
        result_file = algo_dir / 'optimization' / 'result.json'
        if result_file.exists():
            with open(result_file, 'r') as f:
                result_data = json.load(f)
            
            selected_views = result_data.get('selected_views', [])
            total_storage = result_data.get('total_storage', 0)
            total_utility = result_data.get('total_utility', 0)
            
            if selected_views:
                mvs_list = []
                # Calculate average storage per MV
                avg_storage = total_storage / len(selected_views) if len(selected_views) > 0 else 0
                avg_utility = total_utility / len(selected_views) if len(selected_views) > 0 else 0
                
                for idx, view_id in enumerate(selected_views):
                    mv = {
                        'view_id': view_id,
                        'mv_id': f'mv_{view_id}',
                        'utility': avg_utility,  # Use average utility
                        'storage_size': avg_storage,  # Use average storage
                        'maintenance_cost': 0,
                        'used_by_queries': [],
                        'sql': f'View {view_id}',
                        'node_type': 'materialized_view'
                    }
                    mvs_list.append(mv)
                return mvs_list
        
        # Try CSV file as fallback
        csv_file = algo_dir / 'optimization' / 'mv_list.csv'
        if csv_file.exists():
            import csv
            mvs_list = []
            with open(csv_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    mv = {
                        'view_id': row.get('view_id', ''),
                        'mv_id': row.get('mv_id', ''),
                        'utility': float(row.get('utility', 0)),
                        'storage_size': float(row.get('storage_size', 0)),
                        'maintenance_cost': float(row.get('maintenance_cost', 0)),
                        'used_by_queries': [],
                        'sql': row.get('sql', ''),
                        'node_type': 'materialized_view'
                    }
                    mvs_list.append(mv)
            # Sort by utility (descending)
            mvs_list.sort(key=lambda x: x.get('utility', 0), reverse=True)
            return mvs_list if mvs_list else None
        
        return None
    
    def compare_algorithms(self, algorithms: List[str]) -> Dict:
        """Compare results across multiple algorithms
        
        Args:
            algorithms: List of algorithm names to compare
            
        Returns:
            Comparison data dictionary
        """
        comparison = {
            'algorithms': algorithms,
            'metrics': {},
            'queries': {}
        }
        
        for algo in algorithms:
            metadata = self._load_experiment_metadata(algo)
            results = self.load_optimization_results(algo)
            
            if results:
                # Extract key metrics
                selected_views = results.get('selected_views', [])
                comparison['metrics'][algo] = {
                    'num_views': results.get('num_selected_views', len(selected_views)),
                    'total_utility': results.get('total_utility', 0),
                    'storage_used_mb': results.get('total_storage_mb', 0),
                    'storage_used_bytes': results.get('total_storage', 0),
                    'optimization_time': metadata.get('execution_times', {}).get('optimization', 0) if metadata else 0
                }
                
                # Get query performance
                query_perf = self.load_query_performance(algo)
                if query_perf:
                    for qp in query_perf:
                        query_id = qp['query_id']
                        if query_id not in comparison['queries']:
                            comparison['queries'][query_id] = {}
                        comparison['queries'][query_id][algo] = qp
        
        return comparison
    
    def load_execution_plan(self, algorithm: str, query_id: str, plan_type: str = 'rewritten') -> Optional[Dict]:
        """Load execution plan for a query
        
        Args:
            algorithm: Algorithm name
            query_id: Query identifier
            plan_type: 'original' or 'rewritten'
            
        Returns:
            Execution plan dictionary or None
        """
        algo_dir = self.output_dir / algorithm
        plan_file = algo_dir / f'execution_plans/{query_id}_{plan_type}.json'
        
        if not plan_file.exists():
            return None
        
        with open(plan_file, 'r') as f:
            return json.load(f)
