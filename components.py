"""
Reusable UI components for the dashboard.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime

from config.settings import UIConfig

ui_config = UIConfig()


def metric_card(label: str, value: str, delta: Optional[str] = None, 
                delta_color: str = "normal", help_text: str = None):
    """Render a professional metric card."""
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-number">{value}</div>
            {f'<div class="metric-delta">{delta}</div>' if delta else ''}
        </div>
        """, unsafe_allow_html=True)


def kpi_row(metrics: Dict[str, Any], cols_per_row: int = 4):
    """Display a row of KPI metrics."""
    metrics_list = list(metrics.items())
    
    for i in range(0, len(metrics_list), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, (label, value) in enumerate(metrics_list[i:i+cols_per_row]):
            with cols[j]:
                st.markdown(f"""
                <div class="kpi-card">
                    <div class="kpi-label">{label}</div>
                    <div class="kpi-value">{value}</div>
                </div>
                """, unsafe_allow_html=True)


def filter_section(title: str, filters: Dict[str, Any]) -> Dict[str, Any]:
    """Render a filter section and return selected values."""
    st.markdown(f"""
    <div class="filter-section">
        <h4>{title}</h4>
    </div>
    """, unsafe_allow_html=True)
    
    results = {}
    
    # Create filter columns
    filter_cols = st.columns(len(filters))
    
    for i, (key, config) in enumerate(filters.items()):
        with filter_cols[i]:
            filter_type = config.get("type", "select")
            
            if filter_type == "select":
                options = config.get("options", [])
                default = config.get("default", options[0] if options else None)
                results[key] = st.selectbox(
                    config.get("label", key),
                    options=options,
                    index=options.index(default) if default in options else 0,
                    key=f"filter_{key}"
                )
            
            elif filter_type == "multiselect":
                options = config.get("options", [])
                default = config.get("default", [])
                results[key] = st.multiselect(
                    config.get("label", key),
                    options=options,
                    default=default,
                    key=f"filter_{key}"
                )
            
            elif filter_type == "date_range":
                min_date = config.get("min_date")
                max_date = config.get("max_date")
                if min_date and max_date:
                    date_range = st.date_input(
                        config.get("label", key),
                        value=(min_date, max_date),
                        min_value=min_date,
                        max_value=max_date,
                        key=f"filter_{key}"
                    )
                    results[key] = date_range if len(date_range) == 2 else (None, None)
                else:
                    results[key] = (None, None)
            
            elif filter_type == "checkbox":
                results[key] = st.checkbox(
                    config.get("label", key),
                    value=config.get("default", False),
                    key=f"filter_{key}"
                )
    
    return results


def create_bar_chart(df: pd.DataFrame, x_col: str, y_col: str, 
                     title: str, color_col: str = None,
                     height: int = 500, top_n: int = 20) -> go.Figure:
    """Create a professional bar chart."""
    if df.empty:
        return go.Figure()
    
    # Limit to top N
    if len(df) > top_n:
        df = df.head(top_n)
    
    fig = px.bar(
        df,
        x=x_col,
        y=y_col,
        title=title,
        color=color_col if color_col and color_col in df.columns else None,
        color_continuous_scale="Blues" if not color_col else None,
        text=y_col
    )
    
    fig.update_traces(textposition="outside")
    fig.update_layout(
        template=ui_config.chart_template,
        height=height,
        xaxis_tickangle=-45,
        margin=dict(l=10, r=10, t=50, b=50)
    )
    
    return fig


def create_line_chart(df: pd.DataFrame, x_col: str, y_cols: List[str],
                      title: str, height: int = 400) -> go.Figure:
    """Create a professional line chart."""
    if df.empty:
        return go.Figure()
    
    fig = go.Figure()
    
    for y_col in y_cols:
        if y_col in df.columns:
            fig.add_trace(go.Scatter(
                x=df[x_col],
                y=df[y_col],
                name=y_col,
                mode='lines+markers'
            ))
    
    fig.update_layout(
        title=title,
        template=ui_config.chart_template,
        height=height,
        xaxis_title=x_col,
        yaxis_title="Value",
        hovermode='x unified'
    )
    
    return fig


def create_tat_breakdown_card(stage_data: Dict[str, float], 
                               title: str, color: str) -> str:
    """Create HTML for TAT breakdown card."""
    html = f"""
    <div class="tat-column">
        <div class="tat-column-header" style="background: {color};">{title}</div>
        <div class="tat-column-body">
    """
    
    for stage, value in stage_data.items():
        html += f"""
        <div class="tat-stage-row">
            <div class="stage-info">
                <div class="stage-name">{stage}</div>
            </div>
            <div class="stage-time">
                <div class="stage-minutes">{value:.1f} min</div>
                <div class="stage-hhmm">{_minutes_to_hhmm(value)}</div>
            </div>
        </div>
        """
    
    html += "</div></div>"
    return html


def _minutes_to_hhmm(minutes: float) -> str:
    """Convert minutes to HH:MM format."""
    if pd.isna(minutes) or minutes < 0:
        return "00:00"
    hours = int(minutes // 60)
    mins = int(minutes % 60)
    return f"{hours:02d}:{mins:02d}"


def download_button(data: pd.DataFrame, filename: str, button_text: str = "📥 Download CSV"):
    """Create a download button for dataframe."""
    csv = data.to_csv(index=False).encode('utf-8')
    st.download_button(
        label=button_text,
        data=csv,
        file_name=filename,
        mime="text/csv"
    )


def show_status(message: str, type: str = "info"):
    """Show a status message with appropriate styling."""
    if type == "success":
        st.success(message)
    elif type == "warning":
        st.warning(message)
    elif type == "error":
        st.error(message)
    else:
        st.info(message)


def data_table(df: pd.DataFrame, title: str = None, height: int = 400):
    """Display a styled dataframe."""
    if title:
        st.markdown(f"#### {title}")
    
    if df.empty:
        st.info("No data to display")
        return
    
    st.dataframe(
        df,
        use_container_width=True,
        height=height,
        hide_index=True
    )


def expandable_section(title: str, expanded: bool = False):
    """Create an expandable section decorator."""
    return st.expander(title, expanded=expanded)
