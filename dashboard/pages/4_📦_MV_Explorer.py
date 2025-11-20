"""
MV Explorer Page - Materialized View Details and Analysis

Page for exploring materialized views and their characteristics.
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
st.set_page_config(page_title="MV Explorer - MV Optimization", page_icon="📦", layout="wide")

# Load CSS
css_file = Path(__file__).parent.parent / "styles" / "main.css"
if css_file.exists():
    with open(css_file) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# Initialize session state
initialize_session_state()

st.title("📦 Materialized View Explorer")

# Initialize result loader
output_dir = st.session_state.get('output_dir', 'Output')
loader = ResultLoader(output_dir)

# Algorithm selection
experiments = loader.list_experiments()
if not experiments:
    st.warning("⚠️ No experiment results found. Run an experiment first!")
    st.stop()

available_algorithms = [exp['algorithm'] for exp in experiments]
selected_algorithm = st.selectbox("Select Algorithm", options=available_algorithms)

if not selected_algorithm:
    st.stop()

# Load MV details
mv_details = loader.load_mv_details(selected_algorithm)

if not mv_details:
    st.warning(f"⚠️ No materialized view data found for {selected_algorithm}")
    st.stop()

st.markdown("---")

# Overview metrics
st.subheader("📊 MV Selection Overview")

total_storage = sum(mv['storage_size'] for mv in mv_details)
total_utility = sum(mv['utility'] for mv in mv_details)
avg_utility = total_utility / len(mv_details) if mv_details else 0

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(f"""
    <div class="metric-card">
        <h3>Total MVs</h3>
        <p>{len(mv_details)}</p>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="metric-card" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
        <h3>Total Utility</h3>
        <p>{total_utility:.2f}</p>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="metric-card" style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);">
        <h3>Total Storage</h3>
        <p>{DataProcessor.format_bytes(total_storage)}</p>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown(f"""
    <div class="metric-card" style="background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);">
        <h3>Avg Utility</h3>
        <p>{avg_utility:.2f}</p>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# Tabs for different views
tab1, tab2, tab3 = st.tabs(["📊 Overview", "📋 MV List", "🔍 MV Details"])

with tab1:
    st.markdown("### 💡 Utility Distribution")
    
    col1, col2 = st.columns(2)
    
    with col1:
        fig = Visualizations.create_mv_utility_distribution(mv_details)
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.markdown("### 💾 Storage Distribution")
        fig = Visualizations.create_storage_pie_chart(mv_details)
        st.plotly_chart(fig, use_container_width=True)
    
    # Summary statistics
    st.markdown("---")
    st.markdown("### 📈 Statistics")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**Utility Statistics**")
        utilities = [mv['utility'] for mv in mv_details]
        st.markdown(f"""
        - Max: {max(utilities):.2f}
        - Min: {min(utilities):.2f}
        - Median: {sorted(utilities)[len(utilities)//2]:.2f}
        """)
    
    with col2:
        st.markdown("**Storage Statistics**")
        sizes = [mv['storage_size'] for mv in mv_details]
        st.markdown(f"""
        - Max: {DataProcessor.format_bytes(max(sizes))}
        - Min: {DataProcessor.format_bytes(min(sizes))}
        - Median: {DataProcessor.format_bytes(sorted(sizes)[len(sizes)//2])}
        """)
    
    with col3:
        st.markdown("**Usage Statistics**")
        
        # Load optimization results to get actual usage counts
        opt_results = loader.load_optimization_results(selected_algorithm)
        selected_views = opt_results.get('selected_views', []) if opt_results else []
        
        # Calculate usage from usage_positions
        if selected_views:
            total_usage = sum(len(view.get('usage_positions', [])) for view in selected_views)
            avg_usage = total_usage / len(selected_views) if selected_views else 0
            max_usage = max((len(view.get('usage_positions', [])) for view in selected_views), default=0)
        else:
            # Fallback to old method
            total_usage = sum(len(mv.get('used_by_queries', [])) for mv in mv_details)
            avg_usage = total_usage / len(mv_details) if mv_details else 0
            max_usage = max((len(mv.get('used_by_queries', [])) for mv in mv_details), default=0)
        
        st.markdown(f"""
        - Total Usage Positions: {total_usage}
        - Avg per MV: {avg_usage:.1f}
        - Most Used: {max_usage}
        """)

with tab2:
    st.markdown("### 📋 Materialized Views List")
    
    # Sorting and filtering options
    col1, col2, col3 = st.columns(3)
    
    with col1:
        sort_by = st.selectbox(
            "Sort by",
            options=['utility', 'storage_size', 'query_count'],
            format_func=lambda x: x.replace('_', ' ').title()
        )
    
    with col2:
        sort_order = st.radio("Order", options=['Descending', 'Ascending'], index=0)
    
    with col3:
        min_utility = st.number_input("Min Utility", min_value=0.0, value=0.0, step=10.0)
    
    # Process data
    import pandas as pd
    df = DataProcessor.mv_details_to_dataframe(mv_details)
    
    # Filter
    if min_utility > 0:
        df = df[df['utility'] >= min_utility]
    
    # Sort
    ascending = sort_order == 'Ascending'
    if sort_by in df.columns:
        df = df.sort_values(by=sort_by, ascending=ascending)
    
    # Display columns
    display_cols = ['view_id', 'utility', 'storage_formatted', 'query_count', 'node_type']
    available_cols = [col for col in display_cols if col in df.columns]
    
    if available_cols:
        display_df = df[available_cols].copy()
        display_df.columns = [col.replace('_', ' ').title() for col in available_cols]
        
        st.dataframe(display_df, use_container_width=True, height=500)
        
        st.markdown(f"**Showing {len(df)} of {len(mv_details)} MVs**")
    else:
        st.error("Unable to display MV data")

with tab3:
    st.markdown("### 🔍 Materialized View Details")
    
    # MV selection
    mv_ids = [mv['view_id'] for mv in mv_details]
    selected_mv = st.selectbox("Select Materialized View", options=mv_ids)
    
    if selected_mv:
        # Find MV data
        mv_data = next((mv for mv in mv_details if mv['view_id'] == selected_mv), None)
        
        if mv_data:
            # Display metrics
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Utility", f"{mv_data['utility']:.2f}")
            
            with col2:
                st.metric("Storage Size", DataProcessor.format_bytes(mv_data['storage_size']))
            
            with col3:
                query_count = len(mv_data.get('used_by_queries', []))
                st.metric("Used by Queries", query_count)
            
            # Additional info
            st.markdown("---")
            st.markdown("### ℹ️ Additional Information")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown(f"""
                **Node Type:** `{mv_data.get('node_type', 'unknown')}`  
                **Maintenance Cost:** {mv_data.get('maintenance_cost', 0):.2f}
                """)
            
            with col2:
                # Load optimization results to get actual usage positions
                opt_results = loader.load_optimization_results(selected_algorithm)
                selected_views = opt_results.get('selected_views', []) if opt_results else []
                
                # Find this MV in selected views
                current_mv = None
                for view in selected_views:
                    if view.get('view_id') == selected_mv or view.get('node_id') == mv_data.get('view_id'):
                        current_mv = view
                        break
                
                if current_mv and current_mv.get('usage_positions'):
                    usage_pos = current_mv['usage_positions']
                    st.markdown(f"**Used in {len(usage_pos)} query positions:**")
                    
                    # Get query names
                    import os
                    parsed_dir = Path(output_dir).parent / "parsed"
                    query_files = sorted([f.stem for f in parsed_dir.glob("*.json")]) if parsed_dir.exists() else []
                    
                    for pos in usage_pos[:10]:  # Show first 10
                        query_idx, node_idx = pos
                        query_name = query_files[query_idx] if query_idx < len(query_files) else f"Query_{query_idx}"
                        st.markdown(f"- `{query_name}` at node position {node_idx}")
                    
                    if len(usage_pos) > 10:
                        st.markdown(f"*...and {len(usage_pos) - 10} more positions*")
                elif mv_data.get('used_by_queries'):
                    st.markdown(f"**Used by {len(mv_data['used_by_queries'])} queries:**")
                    for qid in mv_data['used_by_queries'][:10]:
                        st.markdown(f"- `{qid}`")
                    if len(mv_data['used_by_queries']) > 10:
                        st.markdown(f"*...and {len(mv_data['used_by_queries']) - 10} more*")
                else:
                    st.markdown("*Usage information not available*")
            
            # SQL definition
            if mv_data.get('sql'):
                st.markdown("---")
                st.markdown("### 📝 SQL Definition")
                st.code(mv_data['sql'], language='sql')
                
                if st.button("📋 Copy SQL"):
                    st.success("✅ SQL copied to clipboard! (Feature requires JavaScript)")
            
            # Actions
            st.markdown("---")
            st.markdown("### ⚙️ Actions")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("🔄 Refresh MV"):
                    st.info("💡 Refresh functionality will execute: REFRESH MATERIALIZED VIEW")
            
            with col2:
                if st.button("📊 Analyze Usage"):
                    st.info("💡 Usage analysis will show detailed query patterns")
            
            with col3:
                if st.button("🗑️ Drop MV"):
                    st.warning("⚠️ This will drop the materialized view from the database")

st.markdown("---")

# Export options
col1, col2 = st.columns(2)

with col1:
    if st.button("📥 Export MV List"):
        from dashboard.utils.file_manager import FileManager
        export_path = Path(output_dir) / f"{selected_algorithm}_mv_list.csv"
        FileManager.export_to_csv(mv_details, export_path)
        st.success(f"✅ Exported to {export_path}")

with col2:
    if st.button("📄 Generate MV Report"):
        st.info("💡 Report will include utility analysis, storage efficiency, and usage patterns")

st.markdown("---")
st.markdown("💡 **Tip:** Sort MVs by utility to identify the most beneficial views for your workload.")
