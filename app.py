"""
Trip & TAT Analytics Suite - Main Application Entry Point

A production-ready Streamlit application for logistics performance analytics.
"""

import streamlit as st
import pandas as pd
from typing import Optional, List
import time

# Configure page - MUST be the first Streamlit command
st.set_page_config(
    page_title="Trip & TAT Analytics Suite | Logistics Performance Dashboard",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Import application modules
from config.settings import (
    ColumnMapping, DeduplicationConfig, AnalyticsConfig, UIConfig,
    REQUIRED_TRIP_COLUMNS, REQUIRED_TAT_COLUMNS
)
from data.validators import DataValidator, DataCleaner, ValidationResult
from data.deduplicator import AdvancedDeduplicator, DeduplicationResult
from analytics.trip_analytics import TripAnalyticsEngine
from analytics.tat_analytics import TATAnalyticsEngine
from ui.trip_tab import render_trip_tab
from ui.tat_tab import render_tat_tab
from ui.components import show_status
from utils.logger import get_logger, TimingContext

# Initialize logger
logger = get_logger(__name__)

# Initialize configurations
column_mapping = ColumnMapping()
dedup_config = DeduplicationConfig()
analytics_config = AnalyticsConfig()
ui_config = UIConfig()

# Initialize engines
trip_analytics = TripAnalyticsEngine(analytics_config)
tat_analytics = TATAnalyticsEngine(analytics_config)
data_validator = DataValidator(column_mapping)
data_cleaner = DataCleaner()
deduplicator = AdvancedDeduplicator(dedup_config)


# Custom CSS for professional styling
def load_custom_css():
    """Load custom CSS for the dashboard."""
    st.markdown("""
    <style>
        /* Main container */
        .main {
            background-color: #f5f7fa;
        }
        
        /* Header styling */
        .dashboard-header {
            background: linear-gradient(135deg, #1a73e8, #0d47a1);
            padding: 1.5rem 2rem;
            border-radius: 12px;
            margin-bottom: 1.5rem;
            color: white;
        }
        
        .dashboard-header h1 {
            color: white;
            margin: 0;
            font-size: 1.75rem;
            font-weight: 600;
        }
        
        .dashboard-header p {
            color: #e3f2fd;
            margin: 0.5rem 0 0 0;
            font-size: 1rem;
        }
        
        /* Metric cards */
        .metric-card {
            background: white;
            border-radius: 12px;
            padding: 1rem 1.5rem;
            text-align: center;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            transition: transform 0.2s, box-shadow 0.2s;
            margin-bottom: 1rem;
        }
        
        .metric-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.12);
        }
        
        .metric-number {
            font-size: 2rem;
            font-weight: 700;
            color: #1a73e8;
            line-height: 1.2;
        }
        
        .metric-label {
            font-size: 0.8rem;
            color: #666;
            margin-top: 0.25rem;
        }
        
        .metric-delta {
            font-size: 0.75rem;
            margin-top: 0.25rem;
        }
        
        /* KPI cards */
        .kpi-card {
            background: white;
            border-radius: 10px;
            padding: 0.75rem 1rem;
            text-align: center;
            box-shadow: 0 1px 4px rgba(0,0,0,0.05);
        }
        
        .kpi-label {
            font-size: 0.7rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #666;
        }
        
        .kpi-value {
            font-size: 1.25rem;
            font-weight: 600;
            color: #1a73e8;
        }
        
        /* Filter section */
        .filter-section {
            background: white;
            padding: 1rem 1.25rem;
            border-radius: 10px;
            margin-bottom: 1rem;
            box-shadow: 0 1px 4px rgba(0,0,0,0.05);
        }
        
        .filter-section h4 {
            margin: 0 0 0.75rem 0;
            font-size: 0.9rem;
            font-weight: 600;
            color: #333;
        }
        
        /* TAT containers */
        .tat-container {
            display: flex;
            gap: 1.25rem;
            margin: 1rem 0;
            flex-wrap: wrap;
        }
        
        .tat-column {
            flex: 1;
            min-width: 280px;
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }
        
        .tat-column-header {
            padding: 0.75rem 1.25rem;
            font-weight: 700;
            font-size: 1rem;
            color: white;
            text-align: center;
        }
        
        .tat-column-body {
            padding: 0.75rem 1rem;
        }
        
        .tat-stage-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.625rem 0;
            border-bottom: 1px solid #e8eaed;
        }
        
        .tat-stage-row:last-child {
            border-bottom: none;
        }
        
        .stage-name {
            font-weight: 600;
            color: #333;
            font-size: 0.85rem;
        }
        
        .stage-minutes {
            font-weight: 600;
            color: #333;
            font-size: 0.85rem;
        }
        
        .stage-hhmm {
            font-size: 0.75rem;
            color: #1a73e8;
        }
        
        .tat-total-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem 1rem;
            background: #e8f5e9;
            border-top: 2px solid #c8e6c9;
            margin-top: 0.5rem;
            border-radius: 8px;
        }
        
        .tat-total-label {
            font-weight: 700;
            color: #2e7d32;
        }
        
        /* Data tables */
        .stDataFrame {
            border-radius: 10px;
            overflow: hidden;
        }
        
        /* Buttons */
        .stButton button {
            border-radius: 8px;
            font-weight: 500;
            transition: all 0.2s;
        }
        
        .stButton button:hover {
            transform: translateY(-1px);
        }
        
        /* Success/Info/Warning boxes */
        .stAlert {
            border-radius: 10px;
        }
        
        /* Expander */
        .streamlit-expanderHeader {
            border-radius: 10px;
            font-weight: 500;
        }
        
        /* Sidebar */
        .css-1d391kg {
            background-color: #f8f9fa;
        }
        
        /* Typography */
        h1, h2, h3 {
            font-weight: 600;
        }
        
        hr {
            margin: 1rem 0;
        }
    </style>
    """, unsafe_allow_html=True)


def initialize_session_state():
    """Initialize session state variables."""
    if "trip_data" not in st.session_state:
        st.session_state.trip_data = None
    if "tat_data" not in st.session_state:
        st.session_state.tat_data = None
    if "trip_dedup_result" not in st.session_state:
        st.session_state.trip_dedup_result = None
    if "tat_dedup_result" not in st.session_state:
        st.session_state.tat_dedup_result = None
    if "trip_loaded" not in st.session_state:
        st.session_state.trip_loaded = False
    if "tat_loaded" not in st.session_state:
        st.session_state.tat_loaded = False


def render_header():
    """Render the dashboard header."""
    st.markdown("""
    <div class="dashboard-header">
        <h1>🚛 Trip & TAT Analytics Suite</h1>
        <p>Logistics Performance Dashboard | Track deliveries, monitor turnaround times, optimize operations</p>
    </div>
    """, unsafe_allow_html=True)


def file_upload_section():
    """Render the file upload section."""
    st.markdown("### 📂 Data Upload")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 🚛 Trip Reports")
        trip_files = st.file_uploader(
            "Upload Trip Report(s) (.xlsx, .csv)",
            type=["xlsx", "csv"],
            accept_multiple_files=True,
            key="trip_uploader",
            help="Upload monthly trip reports containing trip details, quantities, and delivery information."
        )
        
        if trip_files:
            with st.spinner("Processing trip reports..."):
                with TimingContext("Trip data processing", logger):
                    all_frames = []
                    validation_errors = []
                    
                    for file in trip_files:
                        # Validate file format
                        is_valid, msg = data_validator.validate_file_format(file)
                        if not is_valid:
                            validation_errors.append(msg)
                            continue
                        
                        # Read file
                        df, read_errors = data_validator.read_file(file)
                        if df is None:
                            validation_errors.extend(read_errors)
                            continue
                        
                        # Validate schema
                        validation_result = data_validator.validate_trip_data(df)
                        
                        if validation_result.is_valid:
                            # Clean data
                            df_clean = data_cleaner.clean_trip_data(df, validation_result.inferred_columns)
                            df_clean["Source File"] = file.name
                            all_frames.append(df_clean)
                        else:
                            for error in validation_result.errors:
                                validation_errors.append(f"{file.name}: {error}")
                            for warning in validation_result.warnings:
                                st.warning(f"{file.name}: {warning}")
                    
                    if validation_errors:
                        for error in validation_errors:
                            st.error(error)
                    
                    if all_frames:
                        combined_df = pd.concat(all_frames, ignore_index=True)
                        
                        # Apply deduplication
                        dedup_result = deduplicator.deduplicate(
                            combined_df,
                            key_column="Trip No",
                            standardize_destinations=True
                        )
                        
                        st.session_state.trip_data = dedup_result.deduplicated_df
                        st.session_state.trip_dedup_result = dedup_result
                        st.session_state.trip_loaded = True
                        
                        show_status(f"✅ Successfully loaded {len(dedup_result.deduplicated_df):,} unique trip records from {len(trip_files)} file(s)", "success")
                        
                        if dedup_result.stats.get("rows_removed", 0) > 0:
                            show_status(f"🔁 Deduplication: {dedup_result.stats['rows_removed']:,} duplicate rows merged into {dedup_result.stats['duplicate_groups']:,} groups", "info")
                    else:
                        st.error("No valid trip data could be loaded. Please check your files.")
    
    with col2:
        st.markdown("#### 📊 TAT Data")
        tat_file = st.file_uploader(
            "Upload TAT Data File (.xlsx, .csv)",
            type=["xlsx", "csv"],
            accept_multiple_files=False,
            key="tat_uploader",
            help="Upload Turnaround Time dataset with loading/unloading stage timings."
        )
        
        if tat_file:
            with st.spinner("Processing TAT data..."):
                with TimingContext("TAT data processing", logger):
                    # Validate file format
                    is_valid, msg = data_validator.validate_file_format(tat_file)
                    if not is_valid:
                        st.error(msg)
                    else:
                        # Read file
                        df, read_errors = data_validator.read_file(tat_file)
                        if df is None:
                            for error in read_errors:
                                st.error(error)
                        else:
                            # Validate schema
                            validation_result = data_validator.validate_tat_data(df)
                            
                            if validation_result.is_valid:
                                # Clean data
                                df_clean = data_cleaner.clean_tat_data(df, validation_result.inferred_columns)
                                
                                # Apply deduplication
                                dedup_result = deduplicator.deduplicate(
                                    df_clean,
                                    key_column="Trip No",
                                    standardize_destinations=False
                                )
                                
                                st.session_state.tat_data = dedup_result.deduplicated_df
                                st.session_state.tat_dedup_result = dedup_result
                                st.session_state.tat_loaded = True
                                
                                show_status(f"✅ Successfully loaded {len(dedup_result.deduplicated_df):,} unique TAT records", "success")
                                
                                if dedup_result.stats.get("rows_removed", 0) > 0:
                                    show_status(f"🔁 Deduplication: {dedup_result.stats['rows_removed']:,} duplicate rows merged into {dedup_result.stats['duplicate_groups']:,} groups", "info")
                                
                                for warning in validation_result.warnings:
                                    st.warning(warning)
                            else:
                                for error in validation_result.errors:
                                    st.error(error)


def main():
    """Main application entry point."""
    
    # Load custom CSS
    load_custom_css()
    
    # Initialize session state
    initialize_session_state()
    
    # Render header
    render_header()
    
    # File upload section
    file_upload_section()
    
    st.divider()
    
    # Check if any data is loaded
    has_trip_data = st.session_state.trip_loaded and st.session_state.trip_data is not None and not st.session_state.trip_data.empty
    has_tat_data = st.session_state.tat_loaded and st.session_state.tat_data is not None and not st.session_state.tat_data.empty
    
    if not has_trip_data and not has_tat_data:
        st.info("👈 Please upload trip reports and/or TAT data files to begin analysis")
        
        # Show sample data template info
        with st.expander("📋 Need help with data format?"):
           
