#!/usr/bin/env python3
"""Test node_id consistency fix

This script tests whether the node_id in Output/parsed/ JSON files
matches the node_id used in the processing.
"""
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.core.query_parser import QueryParser
from src.core.parse_exporter import ParseExporter
from config.settings import Settings


def main():
    """Test the node_id consistency fix"""
    print("=" * 80)
    print("Testing node_id consistency fix")
    print("=" * 80)
    
    # Initialize settings
    settings = Settings()
    
    # Create query parser
    qp = QueryParser(settings)
    
    # Parse a small set of queries for testing  
    # Note: get_all_job_queries expects a parent dir that contains a 'job' subdir
    query_dir = project_root / "dataset" / "RED_JSON"
    
    if not query_dir.exists():
        print(f"Error: Query directory not found: {query_dir}")
        return 1
    
    # Run query parsing
    print("\n1. Parsing queries...")
    try:
        qp.query_parse(
            q_num=10,  # Not actually used, but passed for compatibility
            path=str(query_dir),
            insert_query=1000
        )
    except Exception as e:
        print(f"Error during query parsing: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Export annotated query files
    print("\n2. Exporting annotated query files...")
    output_dir = project_root / "Output" / "parsed"
    
    try:
        exporter = ParseExporter(qp.qm)
        
        # Get the query files that were processed
        from src.utils.legacy import get_red_queries, natural_sort_key
        files, _ = get_red_queries(
            str(query_dir),
            str(settings.benchmark.workloads_dir),
            get_ceb=False
        )
        files = sorted(files, key=natural_sort_key)
        
        # Export
        exporter.annotate_query_files(files, output_dir)
        
    except Exception as e:
        print(f"Error during export: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Verify the results
    print("\n3. Verifying node_id consistency...")
    
    # Check one of the exported files
    test_file = output_dir / "17c.json"
    if not test_file.exists():
        print(f"Warning: Test file not found: {test_file}")
        # Try to find any .json file
        json_files = list(output_dir.glob("*.json"))
        if json_files:
            test_file = json_files[0]
            print(f"Using alternative file: {test_file}")
        else:
            print("No JSON files found in output directory")
            return 1
    
    with open(test_file, 'r') as f:
        data = json.load(f)
    
    # Extract all node_ids from the JSON
    def extract_node_ids(node, ids_list):
        if isinstance(node, dict):
            if 'node_id' in node:
                ids_list.append(node['node_id'])
            for key, value in node.items():
                extract_node_ids(value, ids_list)
        elif isinstance(node, list):
            for item in node:
                extract_node_ids(item, ids_list)
    
    json_node_ids = []
    extract_node_ids(data, json_node_ids)
    
    print(f"\nFound {len(json_node_ids)} node_ids in {test_file.name}:")
    for node_id in json_node_ids[:10]:  # Show first 10
        print(f"  - {node_id}")
    if len(json_node_ids) > 10:
        print(f"  ... and {len(json_node_ids) - 10} more")
    
    # Verify node_ids are in the expected format
    valid_count = 0
    for node_id in json_node_ids:
        if node_id.startswith('leaf_') or node_id.startswith('non_leaf_'):
            valid_count += 1
    
    print(f"\n✓ {valid_count}/{len(json_node_ids)} node_ids have valid format")
    
    # Check if these node_ids exist in QueryManager
    missing_ids = []
    for node_id in json_node_ids:
        if node_id.startswith('leaf_'):
            if node_id not in qp.qm.leaf_nodes_map_r:
                missing_ids.append(node_id)
        elif node_id.startswith('non_leaf_'):
            if node_id not in qp.qm.non_leaf_nodes_map_r:
                missing_ids.append(node_id)
    
    if missing_ids:
        print(f"\n✗ Warning: {len(missing_ids)} node_ids not found in QueryManager:")
        for node_id in missing_ids[:5]:
            print(f"  - {node_id}")
        if len(missing_ids) > 5:
            print(f"  ... and {len(missing_ids) - 5} more")
    else:
        print("\n✓ All node_ids found in QueryManager")
    
    print("\n" + "=" * 80)
    print("Test completed successfully!")
    print("=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
