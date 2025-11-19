"""
Query Analysis Page - Detailed Query Performance Analysis

Page for analyzing individual query performance and execution plans.
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
st.set_page_config(page_title="Query Analysis - MV Optimization", page_icon="🔍", layout="wide")

# Load CSS
css_file = Path(__file__).parent.parent / "styles" / "main.css"
if css_file.exists():
    with open(css_file) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# Initialize session state
initialize_session_state()

st.title("🔍 Query Performance Analysis")

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

# Load query performance data
query_perf = loader.load_query_performance(selected_algorithm)

if not query_perf:
    st.warning(f"⚠️ No query performance data found for {selected_algorithm}")
    st.stop()

st.markdown("---")

# Performance overview
st.subheader("📊 Query Performance Overview")

stats = DataProcessor.aggregate_query_statistics(query_perf)

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(f"""
    <div class="metric-card">
        <h3>Total Queries</h3>
        <p>{stats['total_queries']}</p>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="metric-card" style="background: linear-gradient(135deg, #48bb78 0%, #38a169 100%);">
        <h3>Improved</h3>
        <p>{stats['improved_queries']}</p>
        <small>{stats['improvement_rate']:.1f}%</small>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="metric-card" style="background: linear-gradient(135deg, #f56565 0%, #e53e3e 100%);">
        <h3>Degraded</h3>
        <p>{stats['degraded_queries']}</p>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown(f"""
    <div class="metric-card" style="background: linear-gradient(135deg, #4299e1 0%, #3182ce 100%);">
        <h3>Avg Speedup</h3>
        <p>{stats['avg_speedup']:.2f}x</p>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# Visualizations
tab1, tab2, tab3 = st.tabs(["📊 Distribution", "📋 Query List", "🔍 Query Details"])

with tab1:
    st.markdown("### 📈 Speedup Distribution")
    fig = Visualizations.create_query_improvement_histogram(query_perf)
    st.plotly_chart(fig, use_container_width=True)
    
    # Performance categories
    st.markdown("### 🎯 Performance Categories")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        major_improvement = len([q for q in query_perf if q['speedup'] > 2.0])
        st.metric(
            "Major Improvement (>2x)",
            major_improvement,
            f"{major_improvement/len(query_perf)*100:.1f}%"
        )
    
    with col2:
        minor_improvement = len([q for q in query_perf if 1.1 < q['speedup'] <= 2.0])
        st.metric(
            "Minor Improvement (1.1-2x)",
            minor_improvement,
            f"{minor_improvement/len(query_perf)*100:.1f}%"
        )
    
    with col3:
        degradation = len([q for q in query_perf if q['speedup'] < 0.9])
        st.metric(
            "Degradation (<0.9x)",
            degradation,
            f"{degradation/len(query_perf)*100:.1f}%",
            delta_color="inverse"
        )

with tab2:
    st.markdown("### 📋 Query Performance List")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        sort_by = st.selectbox(
            "Sort by",
            options=['speedup', 'original_cost', 'rewritten_cost'],
            index=0
        )
    
    with col2:
        sort_order = st.radio("Order", options=['Descending', 'Ascending'], index=0)
    
    with col3:
        filter_category = st.multiselect(
            "Filter by category",
            options=['Major Improvement', 'Improvement', 'Neutral', 'Degradation'],
            default=[]
        )
    
    # Convert to DataFrame
    import pandas as pd
    df = DataProcessor.query_performance_to_dataframe(query_perf)
    
    # Apply filters
    if filter_category:
        df = df[df['category'].isin(filter_category)]
    
    # Sort
    ascending = sort_order == 'Ascending'
    df = df.sort_values(by=sort_by, ascending=ascending)
    
    # Format for display
    display_df = df[['query_id', 'original_cost', 'rewritten_cost', 'speedup', 'category']].copy()
    display_df['original_cost'] = display_df['original_cost'].round(2)
    display_df['rewritten_cost'] = display_df['rewritten_cost'].round(2)
    display_df['speedup'] = display_df['speedup'].round(2)
    
    # Color code speedup
    def color_speedup(val):
        if val > 2.0:
            return 'background-color: #c6f6d5'
        elif val > 1.1:
            return 'background-color: #e6fffa'
        elif val < 0.9:
            return 'background-color: #fed7d7'
        return ''
    
    styled_df = display_df.style.applymap(color_speedup, subset=['speedup'])
    st.dataframe(styled_df, use_container_width=True, height=400)
    
    # Summary stats for filtered data
    if len(df) > 0:
        st.markdown(f"""
        **Filtered Results:** {len(df)} queries  
        **Avg Speedup:** {df['speedup'].mean():.2f}x  
        **Median Speedup:** {df['speedup'].median():.2f}x
        """)

with tab3:
    st.markdown("### 🔍 Query Details")
    
    # Create a two-column layout: query selector on left, details on right
    query_ids = [q['query_id'] for q in query_perf]
    
    # Use sidebar for query selection
    with st.sidebar:
        st.markdown("### 📋 Query Navigator")
        st.markdown("---")
        
        # Search/filter queries
        search_query = st.text_input("🔍 Search Query ID", "")
        
        # Filter query list
        filtered_ids = [qid for qid in query_ids if search_query.lower() in qid.lower()] if search_query else query_ids
        
        # Show performance category filter
        show_improved_only = st.checkbox("Show Improved Only", value=False)
        show_degraded_only = st.checkbox("Show Degraded Only", value=False)
        
        if show_improved_only:
            filtered_ids = [q['query_id'] for q in query_perf if q['speedup'] > 1.1 and q['query_id'] in filtered_ids]
        elif show_degraded_only:
            filtered_ids = [q['query_id'] for q in query_perf if q['speedup'] < 0.9 and q['query_id'] in filtered_ids]
        
        st.markdown(f"**{len(filtered_ids)}** queries")
        st.markdown("---")
        
        # Query selection with performance indicators
        selected_query = st.radio(
            "Select Query",
            options=filtered_ids,
            format_func=lambda x: f"{x} ({next((q['speedup'] for q in query_perf if q['query_id'] == x), 1.0):.2f}x)",
            key="query_selector"
        )
    
    if selected_query:
        # Find query data
        query_data = next((q for q in query_perf if q['query_id'] == selected_query), None)
        
        if query_data:
            # Display metrics at the top
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric(
                    "Original Cost",
                    f"{query_data['original_cost']:.2f}"
                )
            
            with col2:
                st.metric(
                    "Rewritten Cost",
                    f"{query_data['rewritten_cost']:.2f}"
                )
            
            with col3:
                speedup = query_data['speedup']
                delta = f"{(speedup - 1) * 100:+.1f}%"
                st.metric(
                    "Speedup",
                    f"{speedup:.2f}x",
                    delta,
                    delta_color="normal" if speedup >= 1.0 else "inverse"
                )
            
            # Performance assessment
            st.markdown("---")
            st.markdown("### 🎯 Performance Assessment")
            
            category = DataProcessor.categorize_speedup(speedup)
            
            if category == "Major Improvement":
                st.success(f"✅ **{category}**: This query shows significant performance improvement!")
            elif category == "Improvement":
                st.info(f"ℹ️ **{category}**: This query has moderate performance improvement.")
            elif category == "Neutral":
                st.warning(f"⚠️ **{category}**: This query shows minimal performance change.")
            else:
                st.error(f"❌ **{category}**: This query performance has degraded. Consider investigating.")
            
            # Additional details (if available)
            st.markdown("---")
            st.markdown("### 📝 Query Information")
            
            # Load optimization results to get selected views
            opt_results = loader.load_optimization_results(selected_algorithm)
            selected_views = opt_results.get('selected_views', []) if opt_results else []
            
            # Find MVs used in this query
            query_idx = query_ids.index(selected_query)
            used_mvs = []
            mv_node_positions = {}  # node_id -> mv info
            
            for view in selected_views:
                for pos in view.get('usage_positions', []):
                    if pos[0] == query_idx:  # This query uses this MV
                        used_mvs.append(view)
                        node_id = view.get('node_id', '')
                        mv_node_positions[node_id] = view
                        break
            
            if used_mvs:
                st.markdown(f"**Materialized Views Used:** {len(used_mvs)}")
                for mv in used_mvs:
                    node_id = mv.get('node_id', 'N/A')
                    view_id = mv.get('view_id', 'N/A')
                    size_mb = mv.get('size_mb', 0)
                    st.markdown(f"- `{view_id}` (Node: `{node_id}`, Size: {size_mb:.2f} MB)")
            else:
                st.markdown("*No materialized views used for this query*")
            
            # Display execution plan tree
            st.markdown("---")
            st.markdown("### 🌳 Execution Plan Tree")
            
            # Load parsed query plan
            from pathlib import Path
            import json
            parsed_dir = Path(output_dir) / "parsed"
            query_file = parsed_dir / f"{selected_query}.json"
            
            if query_file.exists():
                try:
                    with open(query_file, 'r') as f:
                        plan_data = json.load(f)
                    
                    # Create tabs for different views
                    plan_tab1, plan_tab2 = st.tabs(["🌲 Tree View", "📄 JSON View"])
                    
                    with plan_tab1:
                        st.markdown("**Query Execution Plan with Selected MVs**")
                        
                        # Build graph structure for visualization
                        import plotly.graph_objects as go
                        import networkx as nx
                        
                        def build_graph_from_plan(node, graph=None, parent_id=None, pos_x=0, pos_y=0, level_width=None, mv_positions=None):
                            """Build networkx graph from execution plan"""
                            if graph is None:
                                graph = nx.DiGraph()
                                level_width = {}
                            if mv_positions is None:
                                mv_positions = mv_node_positions
                            
                            node_id = node.get('node_id', 'N/A')
                            node_type = node.get('Node Type', 'Unknown')
                            cost = node.get('Total Cost', 0)
                            rows = node.get('Plan Rows', 0)
                            
                            # Check if this node is a selected MV
                            is_mv = node_id in mv_positions
                            mv_info = mv_positions.get(node_id, None)
                            
                            # Create node label
                            if is_mv:
                                label = f"{node_type}\n(MV: {mv_info['view_id']})\nID: {node_id}\nCost: {cost:.2f}"
                                color = '#48bb78'
                            else:
                                label = f"{node_type}\nID: {node_id}\nCost: {cost:.2f}\nRows: {rows}"
                                color = '#4299e1'
                            
                            # Add node to graph
                            graph.add_node(node_id, 
                                         label=label, 
                                         node_type=node_type,
                                         cost=cost,
                                         is_mv=is_mv,
                                         color=color)
                            
                            # Add edge from parent
                            if parent_id is not None:
                                graph.add_edge(parent_id, node_id)
                            
                            # Process children
                            children = node.get('Plans', [])
                            for i, child in enumerate(children):
                                build_graph_from_plan(child, graph, node_id, pos_x, pos_y, level_width, mv_positions)
                            
                            return graph
                        
                        # Render the plan tree
                        if isinstance(plan_data, list) and len(plan_data) > 0:
                            st.info(f"💡 Green nodes indicate materialized views selected by the {selected_algorithm} algorithm")
                            
                            # Build graph
                            G = build_graph_from_plan(plan_data[0].get('Plan', {}))
                            
                            # Use hierarchical layout
                            pos = nx.spring_layout(G, k=2, iterations=50)
                            
                            # Alternative: Try to use hierarchical layout
                            try:
                                # Get topological generations for hierarchical layout
                                for layer, nodes in enumerate(nx.topological_generations(G)):
                                    for i, node in enumerate(nodes):
                                        pos[node] = (i - len(nodes)/2, -layer)
                            except:
                                pass  # Use spring layout if topological fails
                            
                            # Extract positions and edges
                            edge_x = []
                            edge_y = []
                            for edge in G.edges():
                                x0, y0 = pos[edge[0]]
                                x1, y1 = pos[edge[1]]
                                edge_x.extend([x0, x1, None])
                                edge_y.extend([y0, y1, None])
                            
                            edge_trace = go.Scatter(
                                x=edge_x, y=edge_y,
                                line=dict(width=2, color='#718096'),
                                hoverinfo='none',
                                mode='lines')
                            
                            # Create node trace
                            node_x = []
                            node_y = []
                            node_text = []
                            node_color = []
                            node_size = []
                            
                            for node in G.nodes():
                                x, y = pos[node]
                                node_x.append(x)
                                node_y.append(y)
                                
                                node_data = G.nodes[node]
                                node_text.append(node_data['label'])
                                node_color.append(node_data['color'])
                                
                                # Size based on cost
                                size = min(50, max(20, node_data['cost'] / 10 + 20))
                                node_size.append(size)
                            
                            node_trace = go.Scatter(
                                x=node_x, y=node_y,
                                mode='markers+text',
                                hoverinfo='text',
                                text=[G.nodes[node]['node_type'] for node in G.nodes()],
                                hovertext=node_text,
                                textposition="top center",
                                marker=dict(
                                    showscale=False,
                                    color=node_color,
                                    size=node_size,
                                    line=dict(width=2, color='white')))
                            
                            # Create figure
                            fig = go.Figure(data=[edge_trace, node_trace],
                                          layout=go.Layout(
                                              title=dict(text=f'Execution Plan for Query {selected_query}', font=dict(size=16)),
                                              showlegend=False,
                                              hovermode='closest',
                                              margin=dict(b=20, l=5, r=5, t=40),
                                              xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                                              yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                                              plot_bgcolor='rgba(0,0,0,0)',
                                              paper_bgcolor='rgba(0,0,0,0)',
                                              height=600))
                            
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.warning("Unable to parse plan data")
                    
                    with plan_tab2:
                        st.json(plan_data)
                
                except Exception as e:
                    st.error(f"Error loading execution plan: {str(e)}")
            else:
                st.warning(f"Execution plan file not found: {query_file}")

st.markdown("---")

# Export options
col1, col2 = st.columns(2)

with col1:
    if st.button("📥 Export Query Performance"):
        from dashboard.utils.file_manager import FileManager
        export_path = Path(output_dir) / f"{selected_algorithm}_query_performance.csv"
        FileManager.export_to_csv(query_perf, export_path)
        st.success(f"✅ Exported to {export_path}")

with col2:
    if st.button("📊 Generate Report"):
        st.info("💡 Report generation feature coming soon!")

st.markdown("---")
st.markdown("💡 **Tip:** Click on individual queries to see detailed execution plans and optimization recommendations.")
