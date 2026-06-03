"""
Home Page - Experiment Configuration and Execution

Main page for configuring and running optimization experiments.
"""

import streamlit as st
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dashboard.components.experiment_runner import ExperimentRunner
from dashboard.components.progress_tracker import ProgressTracker
from dashboard.utils.session_state import (
    initialize_session_state,
    get_session_value,
    set_session_value,
    update_experiment_history,
    clear_experiment_logs,
    append_experiment_log,
    get_experiment_logs
)

# Page config
st.set_page_config(page_title="Home - MV Optimization", page_icon="🏠", layout="wide")

# Load CSS
css_file = Path(__file__).parent.parent / "styles" / "main.css"
if css_file.exists():
    with open(css_file) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# Initialize session state
initialize_session_state()

st.title("🏠 Experiment Configuration")

# Create tabs
tab1, tab2, tab3 = st.tabs(["⚙️ Configuration", "▶️ Execution", "📜 History"])

with tab1:
    st.subheader("Experiment Settings")
    
    # Algorithm selection
    st.markdown("### 📋 Select Algorithms")
    
    # Get previously selected algorithms from session
    prev_selected = get_session_value('selected_algorithms', [])
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        normal = st.checkbox("Normal", value='normal' in prev_selected if prev_selected else True, help="Basic algorithm")
        bigsubs = st.checkbox("BigSubs", value='bigsubs' in prev_selected if prev_selected else True, help="BigSubs algorithm")
    
    with col2:
        frequency = st.checkbox("Frequency", value='frequency' in prev_selected if prev_selected else True, help="Frequency-based algorithm")
        utility = st.checkbox("Utility", value='utility' in prev_selected if prev_selected else False, help="Utility-based algorithm")
    
    with col3:
        utility_capacity = st.checkbox("Utility+Capacity", value='utility_capacity' in prev_selected if prev_selected else False, 
                                      help="Utility with capacity constraints")
        none_algo = st.checkbox("None (Baseline)", value='none' in prev_selected if prev_selected else False,
                               help="No optimization - baseline benchmark")
    
    # Build selected algorithms list
    selected_algorithms = []
    if normal:
        selected_algorithms.append("normal")
    if bigsubs:
        selected_algorithms.append("bigsubs")
    if frequency:
        selected_algorithms.append("frequency")
    if utility:
        selected_algorithms.append("utility")
    if utility_capacity:
        selected_algorithms.append("utility_capacity")
    if none_algo:
        selected_algorithms.append("none")
    
    set_session_value('selected_algorithms', selected_algorithms)
    
    if not selected_algorithms:
        st.warning("⚠️ Please select at least one algorithm")
    else:
        st.success(f"✅ Selected {len(selected_algorithms)} algorithm(s): {', '.join(selected_algorithms)}")
    
    st.markdown("---")
    
    # Storage configuration
    st.markdown("### 💾 Storage Configuration")
    storage_limit_mb = st.slider(
        "Storage Limit (MB)",
        min_value=10,
        max_value=500,
        value=get_session_value('storage_limit_mb', 50),
        step=10,
        help="Maximum storage capacity for materialized views"
    )
    set_session_value('storage_limit_mb', storage_limit_mb)
    
    st.info(f"💿 Storage limit set to: **{storage_limit_mb} MB** ({storage_limit_mb * 1024 * 1024:,} bytes)")
    
    st.markdown("---")
    
    # Insert Query configuration
    st.markdown("### 📝 Insert Query Configuration")
    insert_queries = st.slider(
        "Number of Insert Queries",
        min_value=100,
        max_value=10000,
        value=get_session_value('insert_queries', 1000),
        step=100,
        help="Number of insert queries for maintenance cost calculation"
    )
    set_session_value('insert_queries', insert_queries)
    
    st.info(f"📝 Insert queries set to: **{insert_queries:,}** queries")
    
    st.markdown("---")
    
    # Phase selection
    st.markdown("### 🔧 Execution Phases")
    st.markdown("Select which phases to execute:")
    
    # Get previously enabled phases from session
    prev_phases = get_session_value('enabled_phases', {})
    
    col1, col2 = st.columns(2)
    
    with col1:
        query_parsing = st.checkbox("Query Parsing", 
                                    value=prev_phases.get('query_parsing', True), 
                                    help="Parse and analyze query structure")
        optimization = st.checkbox("ILP Optimization", 
                                  value=prev_phases.get('optimization', True),
                                  help="Run ILP solver to select optimal MVs")
        sql_generation = st.checkbox("SQL Generation", 
                                    value=prev_phases.get('sql_generation', True),
                                    help="Generate SQL for materialized views")
    
    with col2:
        mv_creation = st.checkbox("MV Creation", 
                                 value=prev_phases.get('mv_creation', True),
                                 help="Create MVs in the database")
        query_rewriting = st.checkbox("Query Rewriting", 
                                     value=prev_phases.get('query_rewriting', True),
                                     help="Rewrite queries to use MVs")
        benchmark = st.checkbox("Benchmark", 
                               value=prev_phases.get('benchmark', True),
                               help="Execute benchmark to measure performance")
    
    enabled_phases = {
        'query_parsing': query_parsing,
        'optimization': optimization,
        'sql_generation': sql_generation,
        'mv_creation': mv_creation,
        'query_rewriting': query_rewriting,
        'benchmark': benchmark
    }
    set_session_value('enabled_phases', enabled_phases)
    
    enabled_count = sum(enabled_phases.values())
    st.info(f"✓ {enabled_count}/6 phases enabled")
    
    st.markdown("---")
    
    # Advanced settings
    with st.expander("⚙️ Advanced Settings"):
        output_dir = st.text_input("Output Directory", value=get_session_value('output_dir', 'Output'))
        set_session_value('output_dir', output_dir)
        
        verbose = st.checkbox("Verbose Logging", value=get_session_value('verbose', False))
        set_session_value('verbose', verbose)
    
    st.markdown("---")
    
    # Action buttons
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🚀 Run Experiment", type="primary", disabled=len(selected_algorithms) == 0):
            if not get_session_value('experiment_running', False):
                # Start experiment
                clear_experiment_logs()
                set_session_value('experiment_running', True)
                
                # Create progress tracker
                tracker = ProgressTracker(selected_algorithms, enabled_phases)
                set_session_value('progress_tracker', tracker)
                
                # Create experiment runner
                runner = ExperimentRunner()
                set_session_value('experiment_runner', runner)
                
                # Log experiment start
                experiment_data = {
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'algorithms': selected_algorithms,
                    'storage_limit': storage_limit_mb,
                    'insert_queries': get_session_value('insert_queries', 1000),
                    'phases': enabled_phases,
                    'status': 'running'
                }
                set_session_value('current_experiment', experiment_data)
                
                # Define callbacks
                def on_complete():
                    experiment_data['status'] = 'completed'
                    update_experiment_history(experiment_data)
                    set_session_value('experiment_running', False)
                
                def on_error(error_msg):
                    experiment_data['status'] = 'failed'
                    experiment_data['error'] = error_msg
                    update_experiment_history(experiment_data)
                    set_session_value('experiment_running', False)
                
                def on_progress(progress, phase, algorithm):
                    if tracker:
                        tracker.update_phase_progress(phase, progress)
                
                # Start experiment in background
                settings_dict = {
                    'output_dir': output_dir,
                    'verbose': verbose,
                    'insert_queries': get_session_value('insert_queries', 1000)
                }
                
                try:
                    runner.run_experiment(
                        algorithms=selected_algorithms,
                        storage_limit_mb=storage_limit_mb,
                        phases=enabled_phases,
                        settings=settings_dict,
                        on_progress=on_progress,
                        on_complete=on_complete,
                        on_error=on_error
                    )
                    st.success("✅ Experiment started! Check the Execution tab for progress.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed to start experiment: {str(e)}")
                    set_session_value('experiment_running', False)
            else:
                st.warning("⚠️ An experiment is already running")
    
    with col2:
        if st.button("💾 Save Configuration"):
            from dashboard.utils.file_manager import FileManager
            config = {
                'algorithms': selected_algorithms,
                'storage_limit_mb': storage_limit_mb,
                'insert_queries': get_session_value('insert_queries', 1000),
                'enabled_phases': enabled_phases,
                'output_dir': output_dir,
                'verbose': verbose
            }
            config_path = Path(output_dir) / "dashboard_config.json"
            FileManager.save_json(config, config_path)
            st.success(f"✅ Configuration saved to {config_path}")
    
    with col3:
        if st.button("📂 Load Configuration"):
            from dashboard.utils.file_manager import FileManager
            config_path = Path(get_session_value('output_dir', 'Output')) / "dashboard_config.json"
            
            if not config_path.exists():
                st.error(f"❌ Configuration file not found: {config_path}")
            else:
                config = FileManager.load_json(config_path)
                if config:
                    # Load each configuration item with proper key mapping
                    loaded_items = []
                    if 'algorithms' in config:
                        set_session_value('selected_algorithms', config['algorithms'])
                        loaded_items.append(f"Algorithms: {', '.join(config['algorithms'])}")
                    if 'storage_limit_mb' in config:
                        set_session_value('storage_limit_mb', config['storage_limit_mb'])
                        loaded_items.append(f"Storage: {config['storage_limit_mb']}MB")
                    if 'insert_queries' in config:
                        set_session_value('insert_queries', config['insert_queries'])
                        loaded_items.append(f"Insert Queries: {config['insert_queries']:,}")
                    if 'enabled_phases' in config:
                        set_session_value('enabled_phases', config['enabled_phases'])
                        enabled_count = sum(config['enabled_phases'].values())
                        loaded_items.append(f"Phases: {enabled_count}/6 enabled")
                    if 'output_dir' in config:
                        set_session_value('output_dir', config['output_dir'])
                        loaded_items.append(f"Output: {config['output_dir']}")
                    if 'verbose' in config:
                        set_session_value('verbose', config['verbose'])
                    
                    st.success(f"✅ Configuration loaded successfully!\n\n" + "\n".join([f"- {item}" for item in loaded_items]))
                    st.info("🔄 Page will reload in 2 seconds...")
                    import time
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error(f"❌ Failed to parse configuration file: {config_path}")

with tab2:
    st.subheader("📊 Execution Status")
    
    if get_session_value('experiment_running', False):
        runner = get_session_value('experiment_runner')
        tracker = get_session_value('progress_tracker')
        
        if runner and tracker:
            # Check if experiment is still running
            runner_status = runner.get_status()
            
            if not runner_status['is_running'] and runner.thread and not runner.thread.is_alive():
                # Experiment finished
                set_session_value('experiment_running', False)
                st.success("✅ Experiment completed! Check the Results page for analysis.")
                if st.button("🔄 View Results"):
                    st.switch_page("pages/2_📊_Results.py")
                st.stop()
            
            # Collect new logs from runner
            new_logs = runner.get_logs(max_lines=100)
            for log_line in new_logs:
                append_experiment_log(log_line)
            
            # Display overall progress
            status = tracker.get_status_summary()
            
            st.markdown(f"""
            ### Current Status
            - **Algorithm:** {status['current_algorithm'] or 'Starting...'} ({status['algorithm_progress']})
            - **Overall Progress:** {status['overall_progress']:.1f}%
            """)
            
            # Progress bar
            progress_bar = st.progress(status['overall_progress'] / 100.0)
            
            # Phase status
            st.markdown("### Phase Status")
            phases = tracker.get_phase_summary()
            
            for phase in phases:
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.markdown(f"{phase['status_icon']} **{phase['name']}**")
                with col2:
                    st.markdown(f"`{phase['status']}`")
                with col3:
                    if phase['duration']:
                        from dashboard.utils.data_processor import DataProcessor
                        st.markdown(f"_{DataProcessor.format_duration(phase['duration'])}_")
            
            # Live logs
            st.markdown("### 📝 Live Logs")
            all_logs = get_experiment_logs(max_lines=100)
            
            log_container = st.container()
            with log_container:
                log_text = "".join(all_logs[-50:]) if all_logs else "Waiting for logs..."
                st.code(log_text, language="text")
            
            # Control buttons
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("⏹️ Stop Experiment"):
                    if runner:
                        runner.stop_experiment()
                        set_session_value('experiment_running', False)
                        st.warning("⏹️ Experiment stopped")
                        st.rerun()
            
            with col2:
                if st.button("🔄 Refresh Status"):
                    st.rerun()
            
            # Auto-refresh every 3 seconds while running
            if runner_status['is_running']:
                import time
                time.sleep(3)
                st.rerun()
        else:
            st.warning("⚠️ Experiment status not available")
            set_session_value('experiment_running', False)
    else:
        st.info("ℹ️ No experiment is currently running. Configure and start an experiment in the Configuration tab.")

with tab3:
    st.subheader("📜 Experiment History")
    
    history = get_session_value('experiment_history', [])
    
    if history:
        for idx, exp in enumerate(reversed(history[-10:]), 1):
            with st.expander(f"{exp['timestamp']} - {', '.join(exp['algorithms'])}"):
                col1, col2 = st.columns(2)
                
                with col1:
                    insert_q = exp.get('insert_queries', 1000)
                    st.markdown(f"""
                    **Algorithms:** {', '.join(exp['algorithms'])}  
                    **Storage Limit:** {exp['storage_limit']} MB  
                    **Insert Queries:** {insert_q:,}  
                    **Status:** {exp['status']}
                    """)
                
                with col2:
                    enabled_phases_list = [k for k, v in exp['phases'].items() if v]
                    st.markdown(f"""
                    **Enabled Phases:** {len(enabled_phases_list)}  
                    {', '.join(enabled_phases_list)}
                    """)
    else:
        st.info("ℹ️ No experiments in history yet. Run your first experiment to see it here!")

st.markdown("---")
st.markdown("💡 **Tip:** Start with a small experiment to verify your setup before running large-scale tests.")
