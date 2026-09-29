# Get migration plans with only two patterns (no migration, and migration without dependent MVs)
import argparse
import pickle
import json
import sys
from pathlib import Path
from typing import Dict

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from src.core.query_parser import QueryParser
from mv_generation.simple_mv_sql_generator import SimpleMVSQLGenerator

class GetSimpleMigrationPlans:
    """Get only two patterns of migration plans for each MV"""
    def __init__(
            self,
            settings: Settings | None = None,
            query_set: str = "job_like",
            exp_dir: str | Path | None = None,
    ):
        self.settings = settings
        self.query_set = query_set
        # Experiment directory holding 03_parsed/ and 04_migration/ (default: the repository root)
        self.exp_dir = Path(exp_dir) if exp_dir is not None else Path(__file__).parent.parent

        # Load from 03_parsed/{queryset}/qp_class.pkl
        self.parser_file = self.exp_dir / "03_parsed" / self.query_set / "qp_class.pkl"

        # Holds the loaded data
        self.qp: QueryParser | None = None
        self.sql: Dict[str, Dict[str, str]] | None = None

        self.mv_sql_generator: SimpleMVSQLGenerator | None = None
        self.schema_provider = None  # SchemaProvider to reuse

        if self.parser_file and self.parser_file.exists():
            self.load_pickle()
            if self.qp:
                # Get db_config from settings and pass it to SimpleMVSQLGenerator
                db_config = None
                if self.settings and hasattr(self.settings, 'database'):
                    db_config = {
                        'host': self.settings.database.host,
                        'port': self.settings.database.port,
                        'database': self.settings.database.database,
                        'user': self.settings.database.user,
                        'password': self.settings.database.password,
                    }
                # Create the SchemaProvider only once (reuse the DB connection)
                from src.rewrite.schema_provider import SchemaProvider
                self.schema_provider = SchemaProvider(db_config)
                self.mv_sql_generator = SimpleMVSQLGenerator(self.qp, db_config)

    def load_pickle(self) -> None:
        try:
            with open(self.parser_file, 'rb') as f:
                self.qp = pickle.load(f, encoding='bytes')
        except Exception as e:
            print(f"Failed to load the pickle file: {e}")
            self.qp = None

    def generate_mv_sql_with_existing(self, node_id: str, existing_mvs: list[str]) -> str | None:
        """Create the SQL of a new MV using existing MVs"""
        if self.mv_sql_generator is None:
            print(f"  Error: MVSQLGenerator is not initialized")
            return None

        return self.mv_sql_generator.generate_mv_sql(
            node_id,
            existing_mvs,
        )

    def enumerate_simple_migration_plans(self, target_mv: str) -> Dict[str, str]:
        """
        Generate migration plans with only two patterns
        1. No migration (the MV itself already exists)
        2. Migration without dependent MVs (created from scratch with an empty list)
        """
        mv_sqls = {}
        
        # Pattern 1: no migration
        mv_sqls[str([target_mv])] = "NON_MIGRATE"
        
        # Pattern 2: migration without dependent MVs
        mv_sql = self.generate_mv_sql_with_existing(target_mv, [])
        if mv_sql:
            mv_sqls["[]"] = mv_sql

        return mv_sqls

    def save_migration_plans(
            self,
            filename: str = "simple_migration_plans.json"
    ):
        if not self.sql:
            print("Error: migration plans have not been generated")
            return
        
        # Path of the output dir
        output_dir = self.exp_dir / "04_migration" / self.query_set
        output_dir.mkdir(parents=True, exist_ok=True)
        # File path
        output_file = output_dir / filename

        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.sql, f, indent=2, ensure_ascii=False)
            print(f"Saved migration plans: {output_file}")
        except Exception as e:
            print(f"Failed to save the JSON file: {e}")
    
    def get_migration_sqls(self):
        """Get the two patterns of migration plans for all nodes"""
        if not self.qp or not hasattr(self.qp, 'qm'):
            print("  Error: QueryParser is not initialized")
            return
        
        self.sql = {}

        # Get all nodes (leaf + non_leaf)
        all_nodes = list(self.qp.qm.leaf_nodes_map_r.keys()) + list(self.qp.qm.non_leaf_nodes_info.keys())

        print(f"\nNumber of nodes to process: {len(all_nodes)}")
        print(f"  - leaf_nodes: {len(self.qp.qm.leaf_nodes_map_r)}")
        print(f"  - non_leaf_nodes: {len(self.qp.qm.non_leaf_nodes_info)}")
        print("\nGenerating migration plans (two patterns only)...")

        # For progress display
        processed = 0
        total = len(all_nodes)

        # Get the migration plans of each node
        for node in all_nodes:
            processed += 1
            if processed % 10 == 0 or processed == total:
                print(f"  Progress: {processed}/{total} ({processed*100//total}%)")
            
            # Generate only two patterns for every node
            self.sql[node] = self.enumerate_simple_migration_plans(node)
        
        print(f"\n✓ Finished processing all {total} nodes")
        # Save as a JSON file
        self.save_migration_plans()

if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(description="Enumerate MV migration plans (two patterns only)")
    parser.add_argument(
        "--query-set",
        type=str,
        default="job_like",
        help="Name of the query set to use (default: job_like)"
    )

    args = parser.parse_args()

    # Same settings as scripts/run_experiment_normal.py (config/default.yaml or $CONFIG_PATH)
    settings = Settings()
    migrator = GetSimpleMigrationPlans(settings=settings, query_set=args.query_set)

    migrator.get_migration_sqls()
