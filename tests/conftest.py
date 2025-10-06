"""pytest共通設定とフィクスチャ"""
import pytest
from pathlib import Path
from typing import Dict, Any


@pytest.fixture(scope="session")
def test_data_dir():
    """テストデータディレクトリ"""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_config(tmp_path):
    """サンプル設定"""
    return {
        'database': {
            'name': 'test_db',
            'host': 'localhost',
            'port': 5432,
            'user': 'test_user',
            'password': 'test_password'
        },
        'paths': {
            'output_base': str(tmp_path / 'output'),
            'data_dir': str(tmp_path / 'data')
        },
        'workload': {
            'path': str(tmp_path / 'queries.json'),
            'query_ids': list(range(1, 6))
        },
        'optimization': {
            'storage_budget': 10000000,
            'time_limit': 300,
            'solver': 'gurobi'
        }
    }


@pytest.fixture
def sample_query_json():
    """サンプルクエリJSON"""
    return {
        "Plan": {
            "Node Type": "Aggregate",
            "Total Cost": 1000.0,
            "Plan Width": 10,
            "Plans": [
                {
                    "Node Type": "Seq Scan",
                    "Relation Name": "users",
                    "Alias": "u",
                    "Filter": "(age > 20)",
                    "Total Cost": 100.0,
                    "Plan Rows": 1000,
                    "Plan Width": 10
                }
            ]
        }
    }


@pytest.fixture
def sample_leaf_node():
    """サンプルリーフノード"""
    return {
        'node_id': 'leaf_1',
        'table_name': 'users',
        'alias': 'u',
        'conditions': 'u.age > 20',
        'cost': 100.0,
        'size': 1000
    }


@pytest.fixture
def sample_mv_data():
    """サンプルMVデータ"""
    return {
        'view_id': 'mv_test_1',
        'node_id': 'leaf_1',
        'create_sql': 'CREATE MATERIALIZED VIEW mv_test_1 AS SELECT * FROM users WHERE age > 20;',
        'size': 5000,
        'maintenance_cost': 10.0
    }


@pytest.fixture
def mock_query_manager():
    """モックQueryManager"""
    class MockQueryManager:
        def __init__(self):
            self.leaf_nodes_map = {
                'leaf_1': {
                    'table_name': 'users',
                    'alias': 'u',
                    'conditions': 'u.age > 20'
                },
                'leaf_2': {
                    'table_name': 'orders',
                    'alias': 'o',
                    'conditions': 'o.total > 1000'
                }
            }
            self.non_leaf_nodes_map = {}
            self.non_leaf_nodes_map_r = {}
            self.query_map = {
                1: {
                    'original_sql': 'SELECT u.name FROM users u WHERE u.age > 20',
                    'cost': 100.0
                }
            }
        
        def get_query_plan(self, query_id):
            return self.query_map.get(query_id, {})
        
        def get_query_sql(self, query_id):
            return self.query_map.get(query_id, {}).get('original_sql', '')
    
    return MockQueryManager()
