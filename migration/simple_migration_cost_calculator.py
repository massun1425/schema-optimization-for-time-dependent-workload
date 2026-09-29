# Simple migration cost calculation with only two patterns

# python experiments/small_test_ver2/migration/simple_migration_cost_calculator.py --query-set job

import json
import psycopg2
import yaml
import sys
import os
import re
from pathlib import Path
from typing import Dict, Any, Optional

# Add the project root to the path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings

class SimpleMigrationCostCalculator:
    """Class that calculates the costs of simple migration plans (two patterns only)
        
        Reads each SQL from simple_migration_plans.json and gets the totalcost with EXPLAIN.
        Two patterns: 1) NON_MIGRATE (no migration), 2) [] (no dependent MVs)
    """

    def __init__(self, settings: Settings, query_set: str = "job_like", exp_dir: str | Path | None = None):
        """
        Args:
            settings: Settings loaded from config.yaml
            query_set: Name of the query set
        """
        self.settings = settings
        self.query_set = query_set
        
        # Set the JSON file path
        # Experiment directory holding 04_migration/ (default: the repository root)
        base_dir = Path(exp_dir) if exp_dir is not None else Path(__file__).parent.parent
        self.json_file_path = base_dir / "04_migration" / query_set / "simple_migration_plans.json"
        
        # Path of the output directory
        self.output_dir = self.json_file_path.parent
        
        self.plans = self._load_plans()
        self.costs = {}

    def _load_plans(self) -> Dict[str, Any]:
        with open(self.json_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
        
    def _get_connection(self):
        """Get a database connection (using the settings in config.yaml)"""
        return psycopg2.connect(
            host=self.settings.database.host,
            port=self.settings.database.port,
            dbname=self.settings.database.database,
            user=self.settings.database.user,
            password=self.settings.database.password
        )
    

    def _explain_sql(self, cursor, sql: str) -> tuple[float, int, int]:
        """Run EXPLAIN on the SQL and get totalcost, rows, and width
        
        Args:
            cursor: Database cursor (to reuse the connection)
            sql: SQL to run
            
        Returns:
            A tuple (totalcost, plan_rows, plan_width), or (0.0, 0, 0) on error
        """
        if not sql or sql.strip() == "" or not isinstance(sql, str):
            return (0.0, 0, 0)
        
        # "NON_MIGRATE" is not an actual SQL, so return 0
        if sql == "NON_MIGRATE":
            return (0.0, 0, 0)
        
        # For CREATE MATERIALIZED VIEW, extract the SELECT part with a regular expression
        # re.DOTALL makes the match span newlines
        match = re.search(r'CREATE\s+MATERIALIZED\s+VIEW\s+\S+\s+AS\s+(.*)', sql, re.IGNORECASE | re.DOTALL)
        if match:
            sql = match.group(1).strip()
        else:
            # Error if "AS" is not found
            print(f"  Parse error in CREATE statement: {sql[:80]}...")
            return (0.0, 0, 0)
        
        try:
            # Run EXPLAIN
            explain_query = f"EXPLAIN (FORMAT JSON) {sql}"
            cursor.execute(explain_query)
            result = cursor.fetchone()

            if result and result[0]:
                # Get total_cost, plan_rows, and plan_width from the JSON result
                plan = result[0][0]  # First plan
                plan_data = plan.get('Plan', {})
                total_cost = float(plan_data.get('Total Cost', 0.0))
                plan_rows = int(plan_data.get('Plan Rows', 0))
                plan_width = int(plan_data.get('Plan Width', 0))
                return (total_cost, plan_rows, plan_width)
            else:
                return (0.0, 0, 0)
        except Exception as e:
            print(f"  Error: EXPLAIN failed - {e}")
            print(f"  SQL: {sql[:100]}...")
            return (0.0, 0, 0)
        

    def calculate_all_costs(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Calculate the costs of all migration plans (two patterns only)
        
        Returns:
            Dict of node name -> {plan key: {cost, utility, rows, width, size}}
            - cost: creation cost (read + write)
            - utility: utility (EXPLAIN Total Cost = read cost only)
        """
        print("\n" + "="*70)
        print("Calculating migration costs (including write costs)...")
        print("="*70)
        
        total_nodes = len(self.plans)
        processed = 0
        
        # Open the database connection only once (reused for all EXPLAIN runs)
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # Apply the same settings as Phase 1 (better estimation accuracy)
                    cursor.execute("SET enable_bitmapscan = off;")
                    cursor.execute("SET default_statistics_target = 1000;")
                    cursor.execute("SET random_page_cost = 1.1;")
                    
                    # Keep the order read from simple_migration_plans.json (leaf -> non_leaf, ascending ID)
                    for node, plans in self.plans.items():
                        processed += 1
                        if processed % 10 == 0 or processed == total_nodes:
                            print(f"  Progress: {processed}/{total_nodes} ({processed*100//total_nodes}%)")
                        
                        self.costs[node] = {}
                        
                        # Process only the two patterns (sorted to guarantee the order)
                        for plan_key in sorted(plans.keys()):
                            sql = plans[plan_key]
                            
                            if plan_key == "[]":
                                # Migration without dependent MVs
                                total_cost, rows, width = self._explain_sql(cursor, sql)
                                size = rows * width
                                
                                # Calculate the write cost
                                # Page write cost = (size / page size) * SEQ_PAGE_COST
                                # Tuple processing cost = number of rows * CPU_TUPLE_COST
                                write_pages = (size // 8192) + 1 if size > 0 else 0
                                write_cost = (write_pages * 1.0) + (rows * 0.01)
                                
                                # Creation cost = read cost + write cost
                                creation_cost = total_cost + write_cost
                                
                                self.costs[node][plan_key] = {
                                    "cost": creation_cost,      # Creation cost (read + write)
                                    "utility": total_cost,      # Utility (EXPLAIN cost = read only)
                                    "rows": rows,
                                    "width": width,
                                    "size": size
                                }
                            else:
                                # NON_MIGRATE pattern (in the form str([target_mv]))
                                # The SQL is the string "NON_MIGRATE", so cost and size are 0
                                self.costs[node][plan_key] = {
                                    "cost": 0.0,
                                    "utility": 0.0,
                                    "rows": 0,
                                    "width": 0,
                                    "size": 0
                                }

            print(f"\n✓ Calculation finished: {len(self.costs)} nodes")
            print("="*70 + "\n")
            
        except Exception as e:
            print(f"\nError: failed to connect to the database - {e}")
            raise
        
        # Save the costs to a JSON file
        self.save_costs()
        
        return self.costs
    
    def save_costs(self, output_file: str = "simple_migration_costs.json"):
        """Save the calculated costs to a JSON file"""
        try:
            output_path = self.output_dir / output_file
            with open(output_path, 'w', encoding='utf-8') as f:
                # Keep the loading order (do not use sort_keys)
                json.dump(self.costs, f, indent=2, ensure_ascii=False)
            print(f"Saved migration costs: {output_path}")
        except Exception as e:
            print(f"Failed to save the JSON file: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Cost calculation of simple migration plans (two patterns)")
    parser.add_argument(
        "--query-set",
        type = str,
        default = "job_like",
        help = "Name of the query set to use (default: job_like)"
    )

    args = parser.parse_args()

    # Load settings from config.yaml (explicitly read as UTF-8)
    config_path = Path(__file__).parent.parent / "config.yaml"
    
    # Read the YAML as UTF-8
    with open(config_path, 'r', encoding='utf-8') as f:
        config_data = yaml.safe_load(f)
    
    # Write to a temporary file, then load Settings from it
    temp_config = config_path.parent / '.temp_config.yaml'
    with open(temp_config, 'w', encoding='utf-8') as f:
        yaml.dump(config_data, f, allow_unicode=True)
    
    try:
        settings = Settings.from_yaml(str(temp_config))
    finally:
        if temp_config.exists():
            temp_config.unlink()
    
    # Instantiate the cost calculation class
    calculator = SimpleMigrationCostCalculator(settings, query_set=args.query_set)
    
    # Simple migration plans do not use existing MVs,
    # so MV creation and ANALYZE are unnecessary. Run the cost calculation directly.
    print("\n[Simple migration cost calculation]")
    print("  - NON_MIGRATE: cost = 0")
    print("  - []: run EXPLAIN without dependent MVs")
    costs = calculator.calculate_all_costs()
    
    print("\n✓ Processing finished")
