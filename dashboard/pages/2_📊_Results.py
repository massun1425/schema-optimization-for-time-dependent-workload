"""
Results Page - Algorithm Comparison and Analysis

Page for viewing and comparing experiment results.
"""

import streamlit as st
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dashboard.components.result_loader import ResultLoader
from dashboard.components.visualizations import Visualizations
from dashboard.utils.session_state import initialize_session_state
from dashboard.utils.data_processor import DataProcessor

# Page config
st.set_page_config(page_title="Results - MV Optimization", page_icon="📊", layout="wide")

# Load CSS
css_file = Path(__file__).parent.parent / "styles" / "main.css"
if css_file.exists():
    with open(css_file) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# Initialize session state
initialize_session_state()

st.title("📊 Results Analysis")

# Initialize result loader
output_dir = st.session_state.get('output_dir', 'Output')
loader = ResultLoader(output_dir)

# List available experiments
experiments = loader.list_experiments()

if not experiments:
    st.warning("⚠️ No experiment results found. Run an experiment first!")
    st.stop()

# Algorithm selection for comparison
st.subheader("🔍 Select Algorithms to Compare")
available_algorithms = [exp['algorithm'] for exp in experiments]
selected_algorithms = st.multiselect(
    "Choose algorithms",
    options=available_algorithms,
    default=available_algorithms[:3] if len(available_algorithms) >= 3 else available_algorithms
)

if not selected_algorithms:
    st.info("ℹ️ Select at least one algorithm to view results")
    st.stop()

st.markdown("---")

# Load comparison data
comparison_data = loader.compare_algorithms(selected_algorithms)

# Key Metrics Cards
st.subheader("📈 Key Metrics")
cols = st.columns(len(selected_algorithms))

for idx, algo in enumerate(selected_algorithms):
    metrics = comparison_data['metrics'].get(algo, {})
    
    with cols[idx]:
        st.markdown(f"""
        <div class="metric-card">
            <h3>{algo}</h3>
            <p style="font-size: 1.5rem;">{metrics.get('num_views', 0)} MVs</p>
            <hr style="border-color: rgba(255,255,255,0.3);">
            <p style="font-size: 1rem;">Utility: {metrics.get('total_utility', 0):.2f}</p>
            <p style="font-size: 1rem;">Storage: {DataProcessor.format_bytes(metrics.get('storage_used_bytes', 0))}</p>
        </div>
        """, unsafe_allow_html=True)

st.markdown("---")

# Comparison visualizations
st.subheader("📊 Algorithm Comparison")

# Create tabs for different views
tab1, tab2, tab3 = st.tabs(["📊 Overview", "⏱️ Performance", "💾 Storage"])

with tab1:
    # Algorithm comparison chart
    if comparison_data['metrics']:
        fig = Visualizations.create_algorithm_comparison_chart(comparison_data)
        st.plotly_chart(fig, use_container_width=True)
    
    # Comparison table
    st.markdown("### 📋 Detailed Metrics")
    
    import pandas as pd
    metrics_df = pd.DataFrame(comparison_data['metrics']).T
    metrics_df.index.name = 'Algorithm'
    
    # Format columns
    if 'storage_used_bytes' in metrics_df.columns:
        metrics_df['storage_used'] = metrics_df['storage_used_bytes'].apply(
            lambda x: DataProcessor.format_bytes(x)
        )
        metrics_df.drop('storage_used_bytes', axis=1, inplace=True)
    if 'storage_used_mb' in metrics_df.columns:
        metrics_df.drop('storage_used_mb', axis=1, inplace=True)
    if 'optimization_time' in metrics_df.columns:
        metrics_df['optimization_time'] = metrics_df['optimization_time'].apply(
            lambda x: DataProcessor.format_duration(x)
        )
    
    st.dataframe(metrics_df, use_container_width=True)

with tab2:
    # Utility vs Storage scatter
    if len(comparison_data['metrics']) > 1:
        st.markdown("### 💡 Utility vs Storage Trade-off")
        fig = Visualizations.create_utility_storage_scatter(comparison_data)
        st.plotly_chart(fig, use_container_width=True)
    
    # Query performance comparison
    if comparison_data['queries']:
        st.markdown("### 🔍 Query Performance Heatmap")
        fig = Visualizations.create_query_performance_heatmap(comparison_data['queries'])
        st.plotly_chart(fig, use_container_width=True)
        
        # Performance statistics
        st.markdown("### 📈 Performance Statistics")
        
        for algo in selected_algorithms:
            query_perf = loader.load_query_performance(algo)
            if query_perf:
                stats = DataProcessor.aggregate_query_statistics(query_perf)
                
                with st.expander(f"📊 {algo} Statistics"):
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric("Total Queries", stats['total_queries'])
                        st.metric("Improved", stats['improved_queries'])
                    
                    with col2:
                        st.metric("Degraded", stats['degraded_queries'])
                        st.metric("Neutral", stats['neutral_queries'])
                    
                    with col3:
                        st.metric("Avg Speedup", f"{stats['avg_speedup']:.2f}x")
                        st.metric("Improvement Rate", f"{stats['improvement_rate']:.1f}%")

with tab3:
    # Storage analysis for each algorithm
    st.markdown("### 💾 Storage Analysis")
    
    for algo in selected_algorithms:
        mv_details = loader.load_mv_details(algo)
        if mv_details:
            with st.expander(f"📦 {algo} - Storage Distribution"):
                col1, col2 = st.columns(2)
                
                with col1:
                    fig = Visualizations.create_storage_pie_chart(mv_details)
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    # Storage summary
                    total_storage = sum(mv['storage_size'] for mv in mv_details)
                    avg_storage = total_storage / len(mv_details) if mv_details else 0
                    
                    st.markdown(f"""
                    **Storage Summary**
                    - Total Storage: {DataProcessor.format_bytes(total_storage)}
                    - Number of MVs: {len(mv_details)}
                    - Average per MV: {DataProcessor.format_bytes(avg_storage)}
                    """)
                    
                    # Top storage consumers
                    st.markdown("**Top Storage Consumers**")
                    sorted_mvs = sorted(mv_details, key=lambda x: x['storage_size'], reverse=True)[:5]
                    for mv in sorted_mvs:
                        st.markdown(f"- `{mv['view_id']}`: {DataProcessor.format_bytes(mv['storage_size'])}")

st.markdown("---")

# Export options
st.subheader("📥 Export Results")

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("📄 Export to CSV"):
        from dashboard.utils.file_manager import FileManager
        
        # Export comparison metrics
        export_path = Path(output_dir) / "comparison_results.csv"
        metrics_data = []
        
        for algo, metrics in comparison_data['metrics'].items():
            metrics_data.append({
                'algorithm': algo,
                **metrics
            })
        
        FileManager.export_to_csv(metrics_data, export_path)
        st.success(f"✅ Exported to {export_path}")

with col2:
    if st.button("📊 Export Charts"):
        st.info("💡 Right-click on any chart and select 'Download plot as PNG'")

with col3:
    if st.button("📦 Archive Results"):
        from dashboard.utils.file_manager import FileManager
        from datetime import datetime
        
        archive_name = f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        archive_path = FileManager.archive_experiment(
            Path(output_dir),
            Path(output_dir) / "archives",
            archive_name
        )
        st.success(f"✅ Archived to {archive_path}")

st.markdown("---")
st.markdown("💡 **Tip:** Use the filters and sorting options to explore specific aspects of the results.")
