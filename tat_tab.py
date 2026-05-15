"""
Turnaround Time (TAT) Report Analysis Tab UI.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from typing import Optional, Dict, Any, List

from config.settings import ALLOWED_CLIENTS, UIConfig
from analytics.tat_analytics import TATAnalyticsEngine, TATMetrics
from ui.components import (
    metric_card, filter_section, create_bar_chart, create_line_chart,
    download_button, data_table, show_status, expandable_section
)
from utils.logger import get_logger
from data.deduplicator import AdvancedDeduplicator, DeduplicationConfig

logger = get_logger(__name__)
ui_config = UIConfig()


def _minutes_to_hhmm(minutes: float) -> str:
    """Convert minutes to HH:MM format."""
    if pd.isna(minutes) or minutes < 0:
        return "00:00"
    hours = int(minutes // 60)
    mins = int(minutes % 60)
    return f"{hours:02d}:{mins:02d}"


def render_tat_tab(df: pd.DataFrame, analytics_engine: TATAnalyticsEngine,
                   trip_trip_nos: Optional[List[str]] = None):
    """Render the TAT Report Analysis tab."""
    
    st.markdown("## 📊 Turnaround Time (TAT) Analysis")
    st.markdown("*Monitor loading/unloading cycle times, identify bottlenecks, and track SLA compliance*")
    
    if df.empty:
        st.warning("No TAT data available. Please upload a TAT data file.")
        return
    
    # Sidebar filters
    with st.sidebar:
        st.markdown("### 🔍 TAT Filters")
        
        # Client filter with allowed clients
        available_clients = sorted(df["Client"].dropna().unique().tolist())
        client_options = ["All Clients"] + [c for c in ALLOWED_CLIENTS if c in available_clients]
        
        if not client_options or client_options == ["All Clients"]:
            client_options = ["All Clients"] + available_clients[:20]
        
        selected_client = st.selectbox(
            "🏢 Client",
            options=client_options,
            key="tat_client_filter"
        )
        
        # Plant filter
        plants = sorted(df["Plant"].dropna().unique().tolist())
        plant_options = ["All Plants"] + plants
        
        selected_plant = st.selectbox(
            "🏭 Plant/Source",
            options=plant_options,
            key="tat_plant_filter"
        )
        
        # Destination filter
        destinations = sorted(df["Destination"].dropna().unique().tolist())
        dest_options = ["All Destinations"] + destinations
        
        selected_destination = st.selectbox(
            "📍 Destination",
            options=dest_options,
            key="tat_destination_filter"
        )
        
        # Date filter
        if "Date" in df.columns and not df["Date"].isna().all():
            min_date = df["Date"].min().date()
            max_date = df["Date"].max().date()
            
            date_range = st.date_input(
                "📅 Date Range",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date,
                key="tat_date_filter"
            )
            start_date, end_date = date_range[0], date_range[1] if len(date_range) > 1 else None
        else:
            start_date, end_date = None, None
        
        # Trip filter from trip analysis
        if trip_trip_nos:
            use_trip_filter = st.checkbox(
                "🔗 Use Trip Analysis Selection",
                value=True,
                key="tat_trip_link"
            )
        else:
            use_trip_filter = False
        
        # Apply filters button
        apply_filters = st.button("Apply Filters", type="primary", use_container_width=True)
        clear_filters = st.button("Clear All", use_container_width=True)
        
        if clear_filters:
            st.session_state.clear()
            st.rerun()
    
    # Apply filters
    filtered_df = df.copy()
    
    if selected_client != "All Clients":
        filtered_df = filtered_df[filtered_df["Client"] == selected_client]
    
    if selected_plant != "All Plants":
        filtered_df = filtered_df[filtered_df["Plant"] == selected_plant]
    
    if selected_destination != "All Destinations":
        filtered_df = filtered_df[filtered_df["Destination"] == selected_destination]
    
    if start_date and end_date and "Date" in filtered_df.columns:
        filtered_df = filtered_df[
            (filtered_df["Date"] >= pd.Timestamp(start_date)) &
            (filtered_df["Date"] <= pd.Timestamp(end_date))
        ]
    
    if use_trip_filter and trip_trip_nos:
        filtered_df = filtered_df[filtered_df["Trip No"].isin(trip_trip_nos)]
    
    # Apply deduplication for TAT data
    dedup_config = DeduplicationConfig(
        sum_columns=["Inv Qty"],
        avg_columns=[
            "Actual DO Receipt (Mins)", "Actual Gate In(Mins)",
            "Actual Loaded Exit(Mins)", "Actual Gate In for Unloading(Mins)",
            "Actual Unloaded (Mins)"
        ]
    )
    deduplicator = AdvancedDeduplicator(dedup_config)
    
    with st.spinner("Processing TAT data..."):
        dedup_result = deduplicator.deduplicate(
            filtered_df,
            key_column="Trip No",
            standardize_destinations=False
        )
        processed_df = dedup_result.deduplicated_df
    
    # Show deduplication summary
    if dedup_result.stats.get("rows_removed", 0) > 0:
        with st.expander(f"🔁 Deduplication Summary - {dedup_result.stats['duplicate_groups']} duplicate groups merged"):
            st.info(
                f"**Original rows:** {dedup_result.stats['original_rows']:,}\n\n"
                f"**Unique trips:** {dedup_result.stats['deduplicated_rows']:,}\n\n"
                f"**Rows removed:** {dedup_result.stats['rows_removed']:,}\n\n"
                f"**Duplicate groups merged:** {dedup_result.stats['duplicate_groups']:,}"
            )
            
            if not dedup_result.audit_df.empty:
                st.markdown("#### Audit Trail")
                st.dataframe(dedup_result.audit_df.head(10), use_container_width=True, hide_index=True)
    
    # Calculate metrics
    metrics = analytics_engine.calculate_metrics(processed_df)
    
    # Display KPI row
    st.markdown("### 📊 Key TAT Metrics")
    
    kpi_cols = st.columns(4)
    with kpi_cols[0]:
        st.metric("Total Trips", f"{metrics.total_trips:,}")
    with kpi_cols[1]:
        st.metric("Avg Loading TAT", metrics._format_time(metrics.loading_tat_mean))
    with kpi_cols[2]:
        st.metric("Avg Unloading TAT", metrics._format_time(metrics.unloading_tat_mean))
    with kpi_cols[3]:
        st.metric("Avg Total TAT", metrics._format_time(metrics.total_tat_mean))
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Median Total TAT", metrics._format_time(metrics.total_tat_median))
    with col2:
        st.metric("SLA Compliance", f"{metrics.sla_compliance_rate:.1f}%",
                  delta=f"{metrics.sla_compliance_rate - 80:.1f}%" if metrics.sla_compliance_rate else None,
                  delta_color="normal" if metrics.sla_compliance_rate >= 80 else "inverse")
    with col3:
        st.metric("Delayed Trips", f"{metrics.delayed_trips:,}")
    with col4:
        st.metric("Complete Data", f"{metrics.trips_with_complete_data:,}")
    
    st.markdown("---")
    
    if processed_df.empty:
        st.info("No TAT data found for the selected filters.")
        return
    
    # TAT Breakdown Visualization
    st.markdown("### 📈 TAT Stage Breakdown")
    
    # Prepare stage data
    stage_data = {
        "DO Receipt": metrics.stage1_mean,
        "Gate In (Loading)": metrics.stage2_mean,
        "Loading Exit": metrics.stage3_mean,
        "Gate In (Unloading)": metrics.stage4_mean,
        "Unloading Exit": metrics.stage5_mean
    }
    
    stage_colors = ['#1a73e8', '#4285f4', '#8ab4f8', '#34a853', '#81c995']
    
    fig = go.Figure(data=[
        go.Bar(
            x=list(stage_data.keys()),
            y=list(stage_data.values()),
            text=[f"{v:.1f} min<br>{_minutes_to_hhmm(v)}" for v in stage_data.values()],
            textposition='outside',
            marker_color=stage_colors
        )
    ])
    
    fig.update_layout(
        title="Average Time per Stage",
        template=ui_config.chart_template,
        height=450,
        yaxis_title="Minutes",
        xaxis_title="Stage"
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Loading vs Unloading Comparison
    st.markdown("### ⚖️ Loading vs Unloading Comparison")
    
    comparison_cols = st.columns(2)
    
    with comparison_cols[0]:
        fig = go.Figure(data=[
            go.Bar(
                x=["Loading", "Unloading", "Total"],
                y=[metrics.loading_tat_mean, metrics.unloading_tat_mean, metrics.total_tat_mean],
                text=[f"{metrics.loading_tat_mean:.1f} min<br>{_minutes_to_hhmm(metrics.loading_tat_mean)}",
                      f"{metrics.unloading_tat_mean:.1f} min<br>{_minutes_to_hhmm(metrics.unloading_tat_mean)}",
                      f"{metrics.total_tat_mean:.1f} min<br>{_minutes_to_hhmm(metrics.total_tat_mean)}"],
                textposition='outside',
                marker_color=['#1a73e8', '#34a853', '#d32f2f']
            )
        ])
        fig.update_layout(
            title="Mean TAT",
            template=ui_config.chart_template,
            height=350,
            yaxis_title="Minutes"
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with comparison_cols[1]:
        fig = go.Figure(data=[
            go.Bar(
                x=["Loading", "Unloading", "Total"],
                y=[metrics.loading_tat_median, metrics.unloading_tat_median, metrics.total_tat_median],
                text=[f"{metrics.loading_tat_median:.1f} min<br>{_minutes_to_hhmm(metrics.loading_tat_median)}",
                      f"{metrics.unloading_tat_median:.1f} min<br>{_minutes_to_hhmm(metrics.unloading_tat_median)}",
                      f"{metrics.total_tat_median:.1f} min<br>{_minutes_to_hhmm(metrics.total_tat_median)}"],
                textposition='outside',
                marker_color=['#1a73e8', '#34a853', '#d32f2f']
            )
        ])
        fig.update_layout(
            title="Median TAT",
            template=ui_config.chart_template,
            height=350,
            yaxis_title="Minutes"
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Plant-wise TAT Analysis
    if processed_df["Plant"].nunique() > 1 and selected_plant == "All Plants":
        st.markdown("### 🏭 Plant-wise TAT Analysis")
        
        plant_summary = analytics_engine.plant_tat_summary(processed_df)
        
        if not plant_summary.empty:
            fig = create_bar_chart(
                plant_summary,
                x_col="Plant",
                y_col="Total_TAT_mean",
                title="Average Total TAT by Plant",
                top_n=15
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Plant summary table
            with st.expander("📋 Detailed Plant TAT Summary"):
                st.dataframe(plant_summary, use_container_width=True, hide_index=True)
    
    # Bottleneck Analysis
    st.markdown("### 🔍 Bottleneck Analysis")
    
    bottlenecks = analytics_engine.find_bottlenecks(processed_df)
    
    if not bottlenecks.empty:
        st.warning(f"⚠️ Found {len(bottlenecks)} stages with SLA violations")
        
        fig = go.Figure(data=[
            go.Bar(
                x=bottlenecks["Stage"],
                y=bottlenecks["Delayed Trips"],
                text=bottlenecks["Delay Rate"],
                textposition='outside',
                marker_color='#d32f2f'
            )
        ])
        fig.update_layout(
            title="Delayed Trips by Stage",
            template=ui_config.chart_template,
            height=350,
            yaxis_title="Number of Delayed Trips"
        )
        st.plotly_chart(fig, use_container_width=True)
        
        data_table(bottlenecks, height=300)
    else:
        st.success("✅ No significant bottlenecks detected. All stages are within SLA thresholds.")
    
    # Percentile Analysis
    with expandable_section("📊 Percentile Analysis", expanded=False):
        percentile_df = analytics_engine.percentile_analysis(processed_df)
        
        if not percentile_df.empty:
            fig = go.Figure(data=[
                go.Bar(
                    x=percentile_df["Percentile"],
                    y=percentile_df["Total TAT (min)"],
                    text=percentile_df["Total TAT (HH:MM)"],
                    textposition='outside',
                    marker_color='#1a73e8'
                )
            ])
            fig.update_layout(
                title="Total TAT Percentile Distribution",
                template=ui_config.chart_template,
                height=350,
                yaxis_title="Minutes"
            )
            st.plotly_chart(fig, use_container_width=True)
            
            data_table(percentile_df)
    
    # Export Section
    st.markdown("---")
    st.markdown("### 📥 Export Data")
    
    export_col1, export_col2, export_col3 = st.columns(3)
    
    with export_col1:
        if st.button("📊 Export TAT Summary", use_container_width=True):
            summary_data = {
                "Metric": list(metrics.to_dict().keys()),
                "Value": list(metrics.to_dict().values())
            }
            summary_df = pd.DataFrame(summary_data)
            download_button(summary_df, "tat_summary.csv", "Download Summary")
    
    with export_col2:
        download_button(processed_df, "tat_data.csv", "Download Processed Data")
    
    with export_col3:
        if not bottlenecks.empty:
            download_button(bottlenecks, "bottleneck_analysis.csv", "Download Bottlenecks")
