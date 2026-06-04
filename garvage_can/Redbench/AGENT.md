# Agent Manifest for `Redbench`

## 1. Directory Overview
This directory (`Redbench`) is dedicated to generating and analyzing **time-varying workloads (時刻変化するワークロード)** using the Redbench dataset for the MV Query Optimization project. 
The tools and scripts here process real-world or synthesized temporal query patterns to supply workload files and frequency configurations for the experimental pipelines (e.g., `experiments/small_test_ver2`).

## 2. Directory Structure

- **Analysis Scripts**
  - `analyze_clusters.py`, `analyze_high_density_periods.py`, `search_all_high_density_clusters.py`: Scripts used to find periods with high query density or specific access patterns.
  - `analyze_temporal_distribution_*.py`, `analyze_workload_*.py`: Scripts dedicated to understanding how query workloads shift over specific instances and timeframes.
  - `analyze_scanset_complexity.py`: Evaluates the complexity of table scans within the workload.
- **Data Transformation & Generation**
  - `generate_frequency_json.py`: Generates the JSON configurations representing the time-varying query frequencies across different periods.
  - `copy_and_transform_queries.py`: Processes and converts queries to be compatible with the downstream experimental pipelines.
- **Configurations (`*.json`)**
  - Various config files (e.g., `config_select_only.json`, `config_matching_*.json`) that govern the specific parameters, time ranges, and cluster IDs used during workload generation.
- **Subdirectories**
  - `src/`: Core Python modules for interacting with and processing the Redbench dataset.
  - `data/`: Raw or intermediate Redbench data files.
  - `output/`: Destination for generated query files and configurations.

## 3. Interaction Guidelines for AI Agents

1. **Role of this Directory**: Treat this directory exclusively as the **Workload Generator & Analyzer**. When the project requires a new time-varying workload, or changes to how query frequencies shift over time, the implementation and execution must happen here.
2. **Project Integration**: 
   - The outputs from this directory (frequency JSON files, SQL queries) are heavily utilized by `experiments/small_test_ver2` and the core `src/` optimization algorithms.
   - When generating outputs here, strictly ensure that their schema and formatting align with the parser/executor boundaries expected by the main MV optimization pipeline.
3. **Configurations and State**: Changes to how time-dependent workloads are built should typically be reflected in the JSON config files. Always review the respective `config_*.json` file before running the analysis or generation scripts.

## 4. Workflows

- **Analyzing Workloads**: Run the `analyze_*.py` scripts to discover interesting patterns or test the properties of a specific cluster/instance.
- **Generating for Experiments**: Configure the generation parameters in the JSON files, run `generate_frequency_json.py` or the copy/transform scripts, and move the resulting time-varying data sets to the appropriate experiment directories (like `experiments/small_test_ver2/01_queries` or configuration paths).
