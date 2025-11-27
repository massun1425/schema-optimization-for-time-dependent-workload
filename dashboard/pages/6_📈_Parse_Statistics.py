"""
Parse Statistics Page - Query Parsing Statistics Visualization

Displays statistics about parsed queries, utility distributions, and maintenance costs.
"""

import streamlit as st
import sys
import json
from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dashboard.utils.session_state import (
    initialize_session_state,
    get_session_value,
)

# Page config
st.set_page_config(page_title="Parse Statistics - MV Optimization", page_icon="📈", layout="wide")

# Load CSS
css_file = Path(__file__).parent.parent / "styles" / "main.css"
if css_file.exists():
    with open(css_file) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# Initialize session state
initialize_session_state()

st.title("📈 Parse Statistics")
st.markdown("クエリパース時の統計情報を表示します。利得（Utility）、更新コスト（Maintenance Cost）、純利益（Net Benefit）の分布を確認できます。")

# Get output directory
output_dir = Path(get_session_value('output_dir', 'Output'))

# Check for parse statistics file
stats_file = output_dir / "parse_statistics.json"

if not stats_file.exists():
    st.warning(f"⚠️ パース統計ファイルが見つかりません: `{stats_file}`")
    st.info("ℹ️ 実験を実行し、Query Parsingフェーズを完了してください。")
    
    # Try to load from pickle if available
    pickle_path = output_dir / "qp_class.pkl"
    if pickle_path.exists():
        st.markdown("---")
        st.markdown("### 🔄 キャッシュからの統計生成")
        st.markdown("保存済みのQuery Parserキャッシュから統計を生成できます。")
        
        if st.button("📊 統計を生成", type="primary"):
            try:
                import pickle
                with open(pickle_path, 'rb') as f:
                    qp = pickle.load(f)
                
                # Check if statistics method exists
                if hasattr(qp, '_compute_parse_statistics'):
                    stats = qp._compute_parse_statistics()
                    
                    # Save statistics
                    with open(stats_file, 'w') as f:
                        json.dump(stats, f, indent=2)
                    
                    st.success(f"✅ 統計を生成しました: `{stats_file}`")
                    st.rerun()
                else:
                    # Compute manually for older cache
                    st.info("キャッシュが古い形式です。実験を再実行してください。")
            except Exception as e:
                st.error(f"❌ エラー: {str(e)}")
    st.stop()

# Load statistics
with open(stats_file, 'r') as f:
    stats = json.load(f)

# Create tabs
tab1, tab2, tab3, tab4 = st.tabs(["📊 概要", "💹 利得分析", "🔧 コスト分析", "📋 詳細データ"])

with tab1:
    st.subheader("📊 パース概要")
    
    # Key metrics in columns
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "📝 クエリ数",
            stats.get('num_queries', 0),
            help="パースされたクエリの総数"
        )
    
    with col2:
        st.metric(
            "🌲 ノード数",
            stats.get('num_nodes', 0),
            help="MV候補となるノードの総数"
        )
    
    with col3:
        st.metric(
            "🍃 リーフノード",
            stats.get('num_leaf_nodes', 0),
            help="単一テーブルノード"
        )
    
    with col4:
        st.metric(
            "🔗 非リーフノード",
            stats.get('num_non_leaf_nodes', 0),
            help="結合ノード"
        )
    
    st.markdown("---")
    
    # Utility summary with gauge charts
    st.subheader("💡 利得（Utility）サマリー")
    
    col1, col2 = st.columns(2)
    
    nodes_positive_pct = stats.get('nodes_with_positive_utility_percentage', 0)
    net_benefit_pct = stats.get('nodes_with_positive_net_benefit_percentage', 0)
    
    with col1:
        # Gauge for nodes with positive utility
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=nodes_positive_pct,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': "正の利得ノード"},
            number={'suffix': '%', 'font': {'size': 30}},
            gauge={
                'axis': {'range': [0, 100]},
                'bar': {'color': "#3498db"},
                'steps': [
                    {'range': [0, 30], 'color': "#ffebee"},
                    {'range': [30, 70], 'color': "#fff3e0"},
                    {'range': [70, 100], 'color': "#e3f2fd"}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 2},
                    'thickness': 0.75,
                    'value': 50
                }
            }
        ))
        fig.update_layout(height=250, margin=dict(l=20, r=20, t=50, b=20))
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"{stats.get('nodes_with_positive_utility', 0):,} / {stats.get('num_nodes', 0):,} ノード")
    
    with col2:
        # Gauge for nodes with positive net benefit
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=net_benefit_pct,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': "正の純利益ノード"},
            number={'suffix': '%', 'font': {'size': 30}},
            gauge={
                'axis': {'range': [0, 100]},
                'bar': {'color': "#9b59b6"},
                'steps': [
                    {'range': [0, 30], 'color': "#ffebee"},
                    {'range': [30, 70], 'color': "#fff3e0"},
                    {'range': [70, 100], 'color': "#f3e5f5"}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 2},
                    'thickness': 0.75,
                    'value': 50
                }
            }
        ))
        fig.update_layout(height=250, margin=dict(l=20, r=20, t=50, b=20))
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"{stats.get('nodes_with_positive_net_benefit', 0):,} / {stats.get('num_nodes', 0):,} ノード")

with tab2:
    st.subheader("💹 利得（Utility）詳細分析")
    
    # Utility value statistics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "最小値",
            f"{stats.get('utility_min', 0):.2f}",
            help="全エントリの最小利得値"
        )
    
    with col2:
        st.metric(
            "最大値",
            f"{stats.get('utility_max', 0):.2f}",
            help="全エントリの最大利得値"
        )
    
    with col3:
        st.metric(
            "平均値",
            f"{stats.get('utility_mean', 0):.2f}",
            help="全エントリの平均利得値"
        )
    
    with col4:
        st.metric(
            "中央値",
            f"{stats.get('utility_median', 0):.2f}",
            help="全エントリの中央値"
        )
    
    st.markdown("---")
    
    # Positive utility statistics
    st.markdown("### 🌟 正の利得のみの統計")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "正の利得 - 平均",
            f"{stats.get('positive_utility_mean', 0):.2f}",
            help="正の利得値のみの平均値"
        )
    
    with col2:
        st.metric(
            "正の利得 - 最大",
            f"{stats.get('positive_utility_max', 0):.2f}",
            help="正の利得値の最大値"
        )
    
    with col3:
        st.metric(
            "正の利得を持つクエリ",
            f"{stats.get('queries_with_positive_utility', 0)} / {stats.get('num_queries', 0)}",
            f"({stats.get('queries_with_positive_utility_percentage', 0):.1f}%)",
            help="少なくとも1つのノードから利得を得られるクエリの数"
        )

with tab3:
    st.subheader("🔧 コスト分析")
    
    # Maintenance cost statistics
    st.markdown("### 🔄 更新コスト（Maintenance Cost）")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "最小値",
            f"{stats.get('maintenance_cost_min', 0):.4f}",
            help="最小更新コスト"
        )
    
    with col2:
        st.metric(
            "最大値",
            f"{stats.get('maintenance_cost_max', 0):.4f}",
            help="最大更新コスト"
        )
    
    with col3:
        st.metric(
            "平均値",
            f"{stats.get('maintenance_cost_mean', 0):.4f}",
            help="平均更新コスト"
        )
    
    with col4:
        st.metric(
            "合計",
            f"{stats.get('maintenance_cost_total', 0):.2f}",
            help="全ノードの更新コスト合計"
        )
    
    st.markdown("---")
    
    # Storage size statistics
    st.markdown("### 💾 ストレージサイズ")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "最小",
            f"{stats.get('storage_size_min', 0):,} bytes",
            help="最小ストレージサイズ"
        )
    
    with col2:
        st.metric(
            "最大",
            f"{stats.get('storage_size_max', 0):,} bytes",
            help="最大ストレージサイズ"
        )
    
    with col3:
        st.metric(
            "平均",
            f"{stats.get('storage_size_mean', 0):,.0f} bytes",
            help="平均ストレージサイズ"
        )
    
    with col4:
        total_mb = stats.get('storage_size_total', 0) / (1024 * 1024)
        st.metric(
            "合計",
            f"{total_mb:.2f} MB",
            help="全ノードのストレージサイズ合計"
        )
    
    st.markdown("---")
    
    # Net benefit analysis
    st.markdown("### 📊 純利益（Net Benefit = Max Utility - Maintenance Cost）")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "最小",
            f"{stats.get('net_benefit_min', 0):.2f}",
            help="最小純利益"
        )
    
    with col2:
        st.metric(
            "最大",
            f"{stats.get('net_benefit_max', 0):.2f}",
            help="最大純利益"
        )
    
    with col3:
        st.metric(
            "平均",
            f"{stats.get('net_benefit_mean', 0):.2f}",
            help="平均純利益"
        )
    
    with col4:
        st.metric(
            "正の純利益ノード",
            f"{stats.get('nodes_with_positive_net_benefit', 0)} / {stats.get('num_nodes', 0)}",
            help="純利益が正のノード数"
        )

with tab4:
    st.subheader("📋 詳細データ")
    
    # Show all statistics as a table
    st.markdown("### 📊 全統計データ")
    
    # Convert to DataFrame for better display
    stats_df = pd.DataFrame([
        {"カテゴリ": "基本情報", "項目": "クエリ数", "値": stats.get('num_queries', 0)},
        {"カテゴリ": "基本情報", "項目": "ノード数", "値": stats.get('num_nodes', 0)},
        {"カテゴリ": "基本情報", "項目": "リーフノード数", "値": stats.get('num_leaf_nodes', 0)},
        {"カテゴリ": "基本情報", "項目": "非リーフノード数", "値": stats.get('num_non_leaf_nodes', 0)},
        {"カテゴリ": "利得値", "項目": "最小値", "値": f"{stats.get('utility_min', 0):.4f}"},
        {"カテゴリ": "利得値", "項目": "最大値", "値": f"{stats.get('utility_max', 0):.4f}"},
        {"カテゴリ": "利得値", "項目": "平均値", "値": f"{stats.get('utility_mean', 0):.4f}"},
        {"カテゴリ": "利得値", "項目": "中央値", "値": f"{stats.get('utility_median', 0):.4f}"},
        {"カテゴリ": "正の利得", "項目": "平均値", "値": f"{stats.get('positive_utility_mean', 0):.4f}"},
        {"カテゴリ": "正の利得", "項目": "最大値", "値": f"{stats.get('positive_utility_max', 0):.4f}"},
        {"カテゴリ": "ノード分析", "項目": "正の利得ノード数", "値": stats.get('nodes_with_positive_utility', 0)},
        {"カテゴリ": "ノード分析", "項目": "正の利得ノード率 (%)", "値": f"{stats.get('nodes_with_positive_utility_percentage', 0):.2f}"},
        {"カテゴリ": "ノード分析", "項目": "正の純利益ノード数", "値": stats.get('nodes_with_positive_net_benefit', 0)},
        {"カテゴリ": "ノード分析", "項目": "正の純利益ノード率 (%)", "値": f"{stats.get('nodes_with_positive_net_benefit_percentage', 0):.2f}"},
        {"カテゴリ": "クエリ分析", "項目": "正の利得を持つクエリ数", "値": stats.get('queries_with_positive_utility', 0)},
        {"カテゴリ": "クエリ分析", "項目": "正の利得を持つクエリ率 (%)", "値": f"{stats.get('queries_with_positive_utility_percentage', 0):.2f}"},
        {"カテゴリ": "更新コスト", "項目": "最小値", "値": f"{stats.get('maintenance_cost_min', 0):.6f}"},
        {"カテゴリ": "更新コスト", "項目": "最大値", "値": f"{stats.get('maintenance_cost_max', 0):.6f}"},
        {"カテゴリ": "更新コスト", "項目": "平均値", "値": f"{stats.get('maintenance_cost_mean', 0):.6f}"},
        {"カテゴリ": "更新コスト", "項目": "合計", "値": f"{stats.get('maintenance_cost_total', 0):.4f}"},
        {"カテゴリ": "ストレージ", "項目": "最小 (bytes)", "値": stats.get('storage_size_min', 0)},
        {"カテゴリ": "ストレージ", "項目": "最大 (bytes)", "値": stats.get('storage_size_max', 0)},
        {"カテゴリ": "ストレージ", "項目": "平均 (bytes)", "値": f"{stats.get('storage_size_mean', 0):.0f}"},
        {"カテゴリ": "ストレージ", "項目": "合計 (bytes)", "値": stats.get('storage_size_total', 0)},
        {"カテゴリ": "純利益", "項目": "最小値", "値": f"{stats.get('net_benefit_min', 0):.4f}"},
        {"カテゴリ": "純利益", "項目": "最大値", "値": f"{stats.get('net_benefit_max', 0):.4f}"},
        {"カテゴリ": "純利益", "項目": "平均値", "値": f"{stats.get('net_benefit_mean', 0):.4f}"},
    ])
    
    st.dataframe(stats_df, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    # Export options
    st.markdown("### 📥 エクスポート")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Download as JSON
        st.download_button(
            label="📄 JSONでダウンロード",
            data=json.dumps(stats, indent=2, ensure_ascii=False),
            file_name="parse_statistics.json",
            mime="application/json"
        )
    
    with col2:
        # Download as CSV
        csv_data = stats_df.to_csv(index=False)
        st.download_button(
            label="📊 CSVでダウンロード",
            data=csv_data,
            file_name="parse_statistics.csv",
            mime="text/csv"
        )

# Footer
st.markdown("---")
st.markdown("""
💡 **ヒント:**
- **正の利得ノード率**は、少なくとも1つのクエリから利得を得られるノードの割合を示します
- **正の純利益ノード率**は、更新コストを考慮した実際に有効なMV候補の割合を示します
- 統計ファイルは `{output_dir}/parse_statistics.json` に保存されています
""".format(output_dir=output_dir))
