"""Parse result exporter for annotating query plans with node IDs.

This module provides functionality to annotate original query plan JSON files
with the node_id assigned during parsing.
"""

import json
from pathlib import Path
from typing import Any

from .query_manager import QueryManager


class ParseExporter:
    """Annotates query plan JSON files with assigned node IDs.
    
    This class takes the original query plan JSON files and adds node_id
    annotations to each operator node based on the parsing results.
    """
    
    def __init__(self, qm: QueryManager) -> None:
        """Initialize the ParseExporter.
        
        Args:
            qm: QueryManager instance containing parsed node information
        """
        self.qm = qm
        # Build a mapping from query position to node_id
        self.position_to_node: dict[tuple[int, int], str] = {}
        for node_id, positions in self.qm.subquery_positions.items():
            for pos in positions:
                query_id, position = pos
                self.position_to_node[(query_id, position)] = node_id
    
    def annotate_query_files(
        self,
        query_files: list[str],
        output_dir: str | Path
    ) -> None:
        """Annotate query plan JSON files with node IDs.
        
        Args:
            query_files: List of query file paths to process
            output_dir: Directory where annotated files will be saved
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        position_counter = [0]  # Mutable counter for DFS traversal
        
        for query_idx, query_file in enumerate(query_files):
            try:
                with open(query_file, 'r', encoding='utf-8') as f:
                    query_data = json.load(f)
                
                # Reset position counter for each query
                position_counter[0] = 0
                
                # Handle both array format [{...}] and single object format {...}
                if isinstance(query_data, list):
                    annotated_list = []
                    for item in query_data:
                        if isinstance(item, dict) and 'Plan' in item:
                            # Annotate the Plan inside the wrapper
                            item_copy = item.copy()
                            item_copy['Plan'] = self._annotate_plan_node(
                                item['Plan'],
                                query_idx,
                                position_counter
                            )
                            annotated_list.append(item_copy)
                        else:
                            annotated_list.append(item)
                    annotated_data = annotated_list
                else:
                    # Single object with 'Plan' key
                    if 'Plan' in query_data:
                        annotated_data = query_data.copy()
                        annotated_data['Plan'] = self._annotate_plan_node(
                            query_data['Plan'],
                            query_idx,
                            position_counter
                        )
                    else:
                        # Direct plan node
                        annotated_data = self._annotate_plan_node(
                            query_data,
                            query_idx,
                            position_counter
                        )
                
                # Save annotated plan
                output_file = output_path / Path(query_file).name
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(annotated_data, f, indent=2, ensure_ascii=False)
                    
            except Exception as e:
                print(f"Warning: Failed to annotate {query_file}: {e}")
        
        print(f"Annotated {len(query_files)} query files")
        print(f"Output directory: {output_path}")
    
    def _annotate_plan_node(
        self,
        node: Any,
        query_idx: int,
        position_counter: list[int]
    ) -> Any:
        """Recursively annotate a plan node with node_id using DFS.
        
        Args:
            node: Plan node (dict or other type)
            query_idx: Query index
            position_counter: Mutable counter for position tracking
            
        Returns:
            Annotated node
        """
        if not isinstance(node, dict):
            return node
        
        # Get current position and increment counter
        current_position = position_counter[0]
        position_counter[0] += 1
        
        # Check if this position has a node_id
        key = (query_idx, current_position)
        node_id = self.position_to_node.get(key)
        
        # Create ordered dict with node_id first (if exists), then other fields, Plans last
        from collections import OrderedDict
        annotated = OrderedDict()
        
        # Add node_id first if it exists
        if node_id:
            annotated['node_id'] = node_id
        
        # Add all other fields except 'Plans'
        for k, v in node.items():
            if k != 'Plans':
                annotated[k] = v
        
        # Recursively process Plans (child nodes) in DFS order and add them last
        if 'Plans' in node and isinstance(node['Plans'], list):
            annotated['Plans'] = [
                self._annotate_plan_node(child, query_idx, position_counter)
                for child in node['Plans']
            ]
        
        return annotated
