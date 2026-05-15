"""
Trip Report Analysis Tab UI.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from typing import Optional, Dict, Any

from config.settings import ALLOWED_CLIENTS, UIConfig
from analytics.trip_analytics import TripAnalyticsEngine, TripMetrics
from ui.components import (
    metric_card, filter_section, create_bar_chart, create_line_chart,
    download_button, data_table, show_status, expandable_section
)
from utils.logger import get_logger

logger = get_logger(__name__)
ui_config = UIConfig()


def render_trip_tab(df: pd.DataFrame, analytics_engine: TripAnalyticsEngine):
    """Render the Trip Report Analysis tab."""
    
    st.markdown("## 🚛 Trip Report Analysis")
    st.markdown("*Analyze trip patterns, destination performance, and quantity trends*")
    
    if df.empty:
        st.warning("No trip data available. Please upload trip report files.")
        return
    
    # Sidebar filters
    with st.sidebar:
        st.markdown("### 🔍 Filters")
        
        # Client filter
        clients = sorted(df["Client"].dropna().unique().tolist())
        regular_clients = [c for c in clients if not c.startswith("EMPTY TRIP")]
        empty_trip_opts = [c for c in clients if c.startswith("EMPTY TRIP")]
        client_options = regular_clients + empty_trip_opts
        
        selected_client = st.selectbox(
            "🏢 Client",
            options=client_options,
            key="trip_client_filter"
        )
        
        # Plant filter (dynamic based on client)
        client_plants = sorted(df[df["Client"] == selected_client]["Plant"].dropna().unique().tolist())
        plant_options = ["All Plants"] + client_plants
        
        selected_plants = st.multiselect(
            "🏭 Plant/Source",
            options=plant_options,
            default=["All Plants"],
            key="trip_plant_filter"
        )
        
        # Handle "All Plants" selection
        if "All Plants" in selected_plants:
            selected_plants = client_plants
        elif not selected_plants:
            selected_plants = client_plants
        
        # Month filter
        months = sorted(df["Month"].dropna().unique().tolist(), reverse=True)
        selected_month = st.selectbox(
            "📅 Month",
            options=["All Months"] + months,
            key="trip_month_filter"
        )
        
        # Trip type filter
        trip_types = ["All Types"] + sorted(df["Trip Type"].dropna().unique().tolist())
        selected_type = st.selectbox(
            "🔄 Trip Type",
            options=trip_types,
            key="trip_type_filter"
        )
        
        # Destination search
        destinations = sorted(df["Destination"].dropna().unique().tolist())
        search_dest = st.text_input("🔍 Search Destination", placeholder="Type to filter...")
        
        # Apply filters button
        apply_filters = st.button("Apply Filters", type="primary", use_container_width=True)
        clear_filters = st.button("Clear All", use_container_width=True)
        
        if clear_filters:
            st.session_state.clear()
            st.rerun()
    
    # Apply filters to data
    filtered_df = df[df["Client"] == selected_client].copy()
    
    if selected_plants:
        filtered_df = filtered_df[filtered_df["Plant"].isin(selected_plants)]
    
    if selected_month != "All Months":
        filtered_df = filtered_df[filtered_df["Month"] == selected_month]
    
    if selected_type != "All Types":
        filtered_df = filtered_df[filtered_df["Trip Type"] == selected_type]
    
    if search_dest:
        filtered_df = filtered_df[filtered_df["Destination"].str.contains(search_dest, case=False, na=False)]
    
    # Show filter summary
    st.caption(f"📌 **Active Filters:** Client: {selected_client} | Plants: {len(selected_plants)} | Month: {selected_month} | Type: {selected_type}")
    
    # Calculate metrics
    metrics = analytics_engine.calculate_metrics(filtered_df)
    
    # Display KPI row
    st.markdown("### 📊 Key Metrics")
    
    kpi_cols = st.columns(4)
    
    with kpi_cols[0]:
        st.metric("Total Trips", f"{metrics.total_trips:,}")
    with kpi_cols[1]:
        st.metric("Loaded Trips", f"{metrics.loaded_trips:,}", 
                  delta=f"{metrics.load_rate:.1f}%" if metrics.total_trips > 0 else None)
    with kpi_cols[2]:
        st.metric("Empty Trips", f"{metrics.empty_trips:,}",
                  delta=f"{metrics.empty_rate:.1f}%" if metrics.total_trips > 0 else None)
    with kpi_cols[3]:
        st.metric("Total Quantity", f"{metrics.total_quantity:,.2f}")
    
    # Second row of metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Unique Destinations", f"{metrics.unique_destinations:,}")
    with col2:
        st.metric("Unique Plants", f"{metrics.unique_plants:,}")
    with col3:
        st.metric("Unique Clients", f"{metrics.unique_clients:,}")
    with col4:
        st.metric("Avg Trips/Day", f"{metrics.avg_trips_per_day:.1f}")
    
    st.markdown("---")
    
    if filtered_df.empty:
        st.info("No trips found for the selected filters. Try adjusting your criteria.")
        return
    
    # Destination Analysis Section
    st.markdown("### 📍 Destination Analysis")
    
    dest_summary = analytics_engine.destination_summary(filtered_df)
    
    if not dest_summary.empty:
        # Chart type selector
        chart_type = st.radio(
            "Display Chart Type",
            options=["Total Trips", "Total Quantity"],
            horizontal=True
        )
        
        chart_col, table_col = st.columns([1, 1])
        
        with chart_col:
            if chart_type == "Total Trips":
                fig = create_bar_chart(
                    dest_summary,
                    x_col="Destination",
                    y_col="Total Trips",
                    title="Top Destinations by Trip Count",
                    top_n=15
                )
            else:
                fig = create_bar_chart(
                    dest_summary,
                    x_col="Destination",
                    y_col="Total Quantity",
                    title="Top Destinations by Total Quantity",
                    top_n=15
                )
                fig.update_traces(texttemplate="%{text:,.2f}")
            
            st.plotly_chart(fig, use_container_width=True)
        
        with table_col:
            st.markdown("#### 📋 Destinations Summary")
            display_cols = ["Destination", "Total Trips", "Total Quantity", "Unique Plants", "% of Trips"]
            available_cols = [c for c in display_cols if c in dest_summary.columns]
            
            st.dataframe(
                dest_summary[available_cols].head(20),
                use_container_width=True,
                hide_index=True
            )
    
    # Plant Analysis Section
    if "Plant" in filtered_df.columns and filtered_df["Plant"].nunique() > 1:
        st.markdown("### 🏭 Plant Analysis")
        
        plant_summary = analytics_engine.plant_summary(filtered_df)
        
        if not plant_summary.empty:
            fig = create_bar_chart(
                plant_summary,
                x_col="Plant",
                y_col="Total Trips",
                title="Trips by Plant",
                top_n=15
            )
            st.plotly_chart(fig, use_container_width=True)
    
    # Monthly Trend Section
    if "Month" in filtered_df.columns:
        st.markdown("### 📈 Monthly Trends")
        
        monthly_trend = analytics_engine.monthly_trend(filtered_df)
        
        if not monthly_trend.empty:
            fig = create_line_chart(
                monthly_trend,
                x_col="Month",
                y_cols=["Total Trips", "Cumulative Trips"],
                title="Trip Volume Trends"
            )
            st.plotly_chart(fig, use_container_width=True)
    
    # Anomaly Detection
    with expandable_section("⚠️ Anomaly Detection", expanded=False):
        anomalies = analytics_engine.find_anomalies(filtered_df)
        
        if not anomalies.empty:
            st.warning(f"Found {len(anomalies)} potential anomalies")
            data_table(anomalies, height=300)
        else:
            st.success("No anomalies detected in the data")
    
    # Export Section
    st.markdown("---")
    st.markdown("### 📥 Export Data")
    
    export_col1, export_col2 = st.columns(2)
    
    with export_col1:
        if st.button("📊 Export Summary Report", use_container_width=True):
            summary_data = {
                "Metrics": list(metrics.to_dict().keys()),
                "Values": list(metrics.to_dict().values())
            }
            summary_df = pd.DataFrame(summary_data)
            download_button(summary_df, f"trip_summary_{selected_client}.csv", "Download Summary")
    
    with export_col2:
        download_button(filtered_df, f"trip_data_{selected_client}.csv", "Download Raw Data")
