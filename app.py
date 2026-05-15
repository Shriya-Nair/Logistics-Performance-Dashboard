"""
Trip & TAT Analytics Suite - Complete Production Application
A professional logistics performance dashboard for trip analysis and TAT monitoring.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
import re
import logging
import time
from functools import wraps

# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class ColumnMapping:
    """Column name mappings for different data sources."""
    trip_columns: Dict[str, str] = field(default_factory=lambda: {
        "trip_no": "Trip No",
        "client": "Client",
        "destination": "Destination",
        "plant": "Plant",
        "start_date": "Start Date",
        "trip_type": "Trip Type",
        "inv_qty": "Inv Qty"
    })
    
    tat_columns: Dict[str, str] = field(default_factory=lambda: {
        "trip_no": "Trip No",
        "client": "Client",
        "plant": "Plant",
        "destination": "Destination",
        "date": "Date",
        "stage1": "Actual DO Receipt (Mins)",
        "stage2": "Actual Gate In(Mins)",
        "stage3": "Actual Loaded Exit(Mins)",
        "stage4": "Actual Gate In for Unloading(Mins)",
        "stage5": "Actual Unloaded (Mins)",
        "inv_qty": "Inv Qty"
    })


@dataclass
class DedupConfig:
    """Configuration for deduplication."""
    sum_columns: List[str] = field(default_factory=lambda: ["Inv Qty"])
    avg_columns: List[str] = field(default_factory=lambda: [
        "Actual DO Receipt (Mins)", "Actual Gate In(Mins)",
        "Actual Loaded Exit(Mins)", "Actual Gate In for Unloading(Mins)",
        "Actual Unloaded (Mins)"
    ])
    fuzzy_match_threshold: float = 0.82


@dataclass
class AnalyticsConfig:
    """Analytics configuration."""
    tat_stages: Dict[str, str] = field(default_factory=lambda: {
        "stage1": "DO Receipt → Gate Entry",
        "stage2": "Gate Entry → Loading Bay",
        "stage3": "Loading Process",
        "stage4": "Gate In for Unloading",
        "stage5": "Unloading Process"
    })
    
    sla_thresholds: Dict[str, int] = field(default_factory=lambda: {
        "loading_total": 120,
        "unloading_total": 90,
        "total": 210
    })
    
    percentiles: List[int] = field(default_factory=lambda: [50, 75, 90, 95, 99])


ALLOWED_CLIENTS = [
    "ARCELORMITTAL NIPPON STEEL INDIA LIMITED",
    "DALMIA CEMENT (BHARAT)LIMITED",
    "HINDUSTAN ZINC LIMITED",
    "JINDAL STEEL AND POWER LIMITED",
    "JSW STEEL LIMITED",
    "TATA STEEL LIMITED CHENNAI",
    "TATA STEEL LIMITED"
]

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def minutes_to_hhmm(minutes: float) -> str:
    """Convert minutes to HH:MM format."""
    if pd.isna(minutes) or minutes < 0:
        return "00:00"
    hours = int(minutes // 60)
    mins = int(minutes % 60)
    return f"{hours:02d}:{mins:02d}"


def setup_logging():
    """Setup basic logging."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


logger = setup_logging()

# ============================================================================
# DEDUPLICATION ENGINE
# ============================================================================

class DestinationNormalizer:
    """Normalizes destination names using fuzzy matching."""
    
    def __init__(self, threshold: float = 0.82):
        self.threshold = threshold
        self.alias_map = {}
    
    def _normalize(self, name: str) -> str:
        if pd.isna(name):
            return "Unknown"
        name = str(name).lower().strip()
        name = re.sub(r"[^\w\s]", "", name)
        name = re.sub(r"\s+", " ", name)
        return name
    
    def _similar(self, a: str, b: str) -> bool:
        na, nb = self._normalize(a), self._normalize(b)
        if na == nb:
            return True
        return SequenceMatcher(None, na, nb).ratio() >= self.threshold
    
    def build_map(self, destinations: pd.Series) -> Dict[str, str]:
        unique_dests = destinations.dropna().unique().tolist()
        clusters = []
        
        for dest in unique_dests:
            placed = False
            for cluster in clusters:
                if self._similar(dest, cluster[0]):
                    cluster.append(dest)
                    placed = True
                    break
            if not placed:
                clusters.append([dest])
        
        alias_map = {}
        for cluster in clusters:
            canonical = max(cluster, key=len)
            for variant in cluster:
                alias_map[variant] = canonical
        return alias_map


class Deduplicator:
    """Advanced deduplication engine."""
    
    def __init__(self, config: DedupConfig):
        self.config = config
    
    def deduplicate(self, df: pd.DataFrame, key_column: str = "Trip No") -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
        """
        Deduplicate dataframe by key column.
        
        Returns: (deduplicated_df, audit_df, stats)
        """
        stats = {"original_rows": len(df), "duplicate_groups": 0, "rows_removed": 0}
        
        if df.empty or key_column not in df.columns:
            return df, pd.DataFrame(), stats
        
        df = df.copy()
        
        # Standardize destinations
        if "Destination" in df.columns:
            normalizer = DestinationNormalizer(self.config.fuzzy_match_threshold)
            alias_map = normalizer.build_map(df["Destination"])
            df["Destination"] = df["Destination"].map(lambda x: alias_map.get(x, x))
        
        # Clean key column
        df[key_column] = df[key_column].astype(str).str.strip()
        df[key_column] = df[key_column].str.replace(r'\.0$', '', regex=True)
        
        # Find duplicates
        dup_mask = df.duplicated(subset=[key_column], keep=False)
        unique_df = df[~dup_mask].copy()
        dup_df = df[dup_mask].copy()
        
        if dup_df.empty:
            return df, pd.DataFrame(), {**stats, "deduplicated_rows": len(df)}
        
        stats["duplicate_groups"] = dup_df[key_column].nunique()
        
        # Build aggregation dictionary
        agg_dict = {}
        for col in self.config.sum_columns:
            if col in df.columns:
                agg_dict[col] = 'sum'
        for col in self.config.avg_columns:
            if col in df.columns:
                agg_dict[col] = 'mean'
        
        # All other columns take first value
        for col in df.columns:
            if col != key_column and col not in agg_dict:
                agg_dict[col] = 'first'
        
        # Perform aggregation
        merged_df = dup_df.groupby(key_column, as_index=False).agg(agg_dict)
        
        # Create audit trail
        audit_records = []
        for trip_no, group in dup_df.groupby(key_column):
            record = {"Trip No": trip_no, "Original_Rows": len(group), "Action": "MERGED"}
            
            for col in self.config.sum_columns:
                if col in group.columns:
                    record[f"{col}_Summed"] = group[col].sum()
            
            for col in self.config.avg_columns:
                if col in group.columns:
                    record[f"{col}_Averaged"] = group[col].mean()
            
            audit_records.append(record)
        
        # Combine
        final_df = pd.concat([unique_df, merged_df], ignore_index=True)
        
        stats.update({
            "rows_removed": stats["original_rows"] - len(final_df),
            "deduplicated_rows": len(final_df)
        })
        
        return final_df, pd.DataFrame(audit_records), stats

# ============================================================================
# DATA VALIDATION & CLEANING
# ============================================================================

class DataProcessor:
    """Handle data validation and cleaning."""
    
    REQUIRED_TRIP_COLS = ["Client", "Destination", "Start Date", "Trip No", "Trip Type"]
    REQUIRED_TAT_COLS = ["Trip No", "Date"]
    
    @staticmethod
    def validate_trip_data(df: pd.DataFrame) -> Tuple[bool, List[str], List[str]]:
        """Validate trip data. Returns (is_valid, errors, warnings)."""
        errors = []
        warnings = []
        
        if df is None or df.empty:
            errors.append("DataFrame is empty")
            return False, errors, warnings
        
        # Check required columns
        missing = [col for col in DataProcessor.REQUIRED_TRIP_COLS if col not in df.columns]
        if missing:
            errors.append(f"Missing columns: {missing}")
        
        # Check duplicates
        if "Trip No" in df.columns:
            dup_count = df.duplicated(subset=["Trip No"]).sum()
            if dup_count > 0:
                warnings.append(f"Found {dup_count} duplicate Trip No(s)")
        
        return len(errors) == 0, errors, warnings
    
    @staticmethod
    def validate_tat_data(df: pd.DataFrame) -> Tuple[bool, List[str], List[str]]:
        """Validate TAT data."""
        errors = []
        warnings = []
        
        if df is None or df.empty:
            errors.append("DataFrame is empty")
            return False, errors, warnings
        
        missing = [col for col in DataProcessor.REQUIRED_TAT_COLS if col not in df.columns]
        if missing:
            errors.append(f"Missing columns: {missing}")
        
        return len(errors) == 0, errors, warnings
    
    @staticmethod
    def clean_trip_data(df: pd.DataFrame) -> pd.DataFrame:
        """Clean and standardize trip data."""
        df = df.copy()
        
        # Clean Trip No
        if "Trip No" in df.columns:
            df["Trip No"] = df["Trip No"].astype(str).str.strip()
            df["Trip No"] = df["Trip No"].str.replace(r'\.0$', '', regex=True)
        
        # Clean Client
        if "Client" in df.columns:
            df["Client"] = df["Client"].fillna("Unknown").astype(str).str.upper().str.strip()
        
        # Clean Destination
        if "Destination" in df.columns:
            df["Destination"] = df["Destination"].fillna("Unknown").astype(str).str.strip()
        
        # Handle Plant column
        if "Plant" not in df.columns:
            df["Plant"] = "All Plants"
        else:
            df["Plant"] = df["Plant"].fillna("Unknown").astype(str).str.upper().str.strip()
        
        # Handle empty trips
        if "Trip Type" in df.columns:
            empty_mask = df["Trip Type"].str.lower() == "empty"
            df.loc[empty_mask & df["Client"].isna(), "Client"] = "EMPTY TRIP"
            df["Trip Type"] = df["Trip Type"].astype(str).str.title()
        
        # Process dates
        if "Start Date" in df.columns:
            df["Start Date"] = pd.to_datetime(df["Start Date"], dayfirst=True, errors='coerce')
            df["Month"] = df["Start Date"].dt.to_period("M").astype(str)
        
        # Process quantity
        if "Inv Qty" not in df.columns:
            df["Inv Qty"] = 0.0
        df["Inv Qty"] = pd.to_numeric(df["Inv Qty"], errors='coerce').fillna(0)
        
        return df
    
    @staticmethod
    def clean_tat_data(df: pd.DataFrame) -> pd.DataFrame:
        """Clean and standardize TAT data."""
        df = df.copy()
        
        # Clean Trip No
        if "Trip No" in df.columns:
            df["Trip No"] = df["Trip No"].astype(str).str.strip()
            df["Trip No"] = df["Trip No"].str.replace(r'\.0$', '', regex=True)
        
        # Clean Client
        if "Client" in df.columns:
            df["Client"] = df["Client"].fillna("Unknown").astype(str).str.upper().str.strip()
        else:
            df["Client"] = "Unknown"
        
        # Clean Plant
        if "Plant" in df.columns:
            df["Plant"] = df["Plant"].fillna("Unknown").astype(str).str.upper().str.strip()
        else:
            df["Plant"] = "Unknown"
        
        # Clean Destination
        if "Destination" in df.columns:
            df["Destination"] = df["Destination"].fillna("Unknown").astype(str).str.strip()
        else:
            df["Destination"] = "Unknown"
        
        # Process date
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors='coerce')
            df["Month"] = df["Date"].dt.to_period("M").astype(str)
        
        # Process TAT stage columns
        stage_cols = [
            "Actual DO Receipt (Mins)", "Actual Gate In(Mins)",
            "Actual Loaded Exit(Mins)", "Actual Gate In for Unloading(Mins)",
            "Actual Unloaded (Mins)"
        ]
        
        for col in stage_cols:
            if col not in df.columns:
                df[col] = 0
            else:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).clip(lower=0)
        
        # Process quantity
        if "Inv Qty" not in df.columns:
            df["Inv Qty"] = 0
        df["Inv Qty"] = pd.to_numeric(df["Inv Qty"], errors='coerce').fillna(0)
        
        return df

# ============================================================================
# TRIP ANALYTICS ENGINE
# ============================================================================

class TripAnalytics:
    """Trip report analytics calculations."""
    
    @staticmethod
    def calculate_metrics(df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate key trip metrics."""
        if df.empty:
            return {
                "total_trips": 0, "loaded_trips": 0, "empty_trips": 0,
                "total_quantity": 0, "unique_destinations": 0, "unique_plants": 0
            }
        
        metrics = {
            "total_trips": len(df),
            "loaded_trips": len(df[df["Trip Type"] == "Loaded"]) if "Trip Type" in df.columns else 0,
            "empty_trips": len(df[df["Trip Type"] == "Empty"]) if "Trip Type" in df.columns else 0,
            "total_quantity": df["Inv Qty"].sum() if "Inv Qty" in df.columns else 0,
            "unique_destinations": df["Destination"].nunique() if "Destination" in df.columns else 0,
            "unique_plants": df["Plant"].nunique() if "Plant" in df.columns else 0,
        }
        
        if metrics["total_trips"] > 0:
            metrics["load_rate"] = metrics["loaded_trips"] / metrics["total_trips"] * 100
            metrics["empty_rate"] = metrics["empty_trips"] / metrics["total_trips"] * 100
        
        return metrics
    
    @staticmethod
    def destination_summary(df: pd.DataFrame) -> pd.DataFrame:
        """Generate destination-wise summary."""
        if df.empty or "Destination" not in df.columns:
            return pd.DataFrame()
        
        summary = df.groupby("Destination").agg({
            "Trip No": "count",
            "Inv Qty": "sum"
        }).reset_index()
        
        summary = summary.rename(columns={"Trip No": "Total Trips", "Inv Qty": "Total Quantity"})
        
        if "Plant" in df.columns:
            plants_per_dest = df.groupby("Destination")["Plant"].nunique().reset_index()
            plants_per_dest.columns = ["Destination", "Unique Plants"]
            summary = summary.merge(plants_per_dest, on="Destination", how="left")
        
        # Add percentage
        total_trips = summary["Total Trips"].sum()
        if total_trips > 0:
            summary["% of Trips"] = (summary["Total Trips"] / total_trips * 100).round(1)
        
        return summary.sort_values("Total Trips", ascending=False).reset_index(drop=True)
    
    @staticmethod
    def monthly_trend(df: pd.DataFrame) -> pd.DataFrame:
        """Generate monthly trend."""
        if df.empty or "Month" not in df.columns:
            return pd.DataFrame()
        
        monthly = df.groupby("Month").agg({
            "Trip No": "count",
            "Inv Qty": "sum"
        }).reset_index()
        
        monthly = monthly.rename(columns={"Trip No": "Total Trips", "Inv Qty": "Total Quantity"})
        monthly = monthly.sort_values("Month")
        
        monthly["Cumulative Trips"] = monthly["Total Trips"].cumsum()
        
        return monthly

# ============================================================================
# TAT ANALYTICS ENGINE
# ============================================================================

class TATAnalytics:
    """Turnaround time analytics calculations."""
    
    STAGE_COLS = [
        "Actual DO Receipt (Mins)", "Actual Gate In(Mins)",
        "Actual Loaded Exit(Mins)", "Actual Gate In for Unloading(Mins)",
        "Actual Unloaded (Mins)"
    ]
    
    @staticmethod
    def calculate_metrics(df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate TAT metrics."""
        if df.empty:
            return {
                "total_trips": 0, "loading_tat_mean": 0, "unloading_tat_mean": 0,
                "total_tat_mean": 0, "loading_tat_median": 0, "unloading_tat_median": 0,
                "total_tat_median": 0, "sla_compliance": 0
            }
        
        # Calculate TAT values
        df = df.copy()
        if all(col in df.columns for col in TATAnalytics.STAGE_COLS):
            df["Loading_TAT"] = df[TATAnalytics.STAGE_COLS[0]] + df[TATAnalytics.STAGE_COLS[1]] + df[TATAnalytics.STAGE_COLS[2]]
            df["Unloading_TAT"] = df[TATAnalytics.STAGE_COLS[3]] + df[TATAnalytics.STAGE_COLS[4]]
            df["Total_TAT"] = df["Loading_TAT"] + df["Unloading_TAT"]
            
            # Stage means
            stage_means = [df[col].mean() for col in TATAnalytics.STAGE_COLS]
        else:
            df["Loading_TAT"] = 0
            df["Unloading_TAT"] = 0
            df["Total_TAT"] = 0
            stage_means = [0, 0, 0, 0, 0]
        
        # SLA compliance
        compliant = df[
            (df["Loading_TAT"] <= 120) & 
            (df["Unloading_TAT"] <= 90) & 
            (df["Total_TAT"] <= 210)
        ]
        sla_compliance = (len(compliant) / len(df) * 100) if len(df) > 0 else 0
        
        return {
            "total_trips": len(df),
            "stage1_mean": stage_means[0],
            "stage2_mean": stage_means[1],
            "stage3_mean": stage_means[2],
            "stage4_mean": stage_means[3],
            "stage5_mean": stage_means[4],
            "loading_tat_mean": df["Loading_TAT"].mean(),
            "unloading_tat_mean": df["Unloading_TAT"].mean(),
            "total_tat_mean": df["Total_TAT"].mean(),
            "loading_tat_median": df["Loading_TAT"].median(),
            "unloading_tat_median": df["Unloading_TAT"].median(),
            "total_tat_median": df["Total_TAT"].median(),
            "sla_compliance": sla_compliance,
            "delayed_trips": len(df) - len(compliant)
        }
    
    @staticmethod
    def plant_summary(df: pd.DataFrame) -> pd.DataFrame:
        """Generate plant-wise TAT summary."""
        if df.empty or "Plant" not in df.columns:
            return pd.DataFrame()
        
        df = df.copy()
        if all(col in df.columns for col in TATAnalytics.STAGE_COLS):
            df["Total_TAT"] = (df[TATAnalytics.STAGE_COLS[0]] + df[TATAnalytics.STAGE_COLS[1]] + 
                              df[TATAnalytics.STAGE_COLS[2]] + df[TATAnalytics.STAGE_COLS[3]] + 
                              df[TATAnalytics.STAGE_COLS[4]])
        else:
            df["Total_TAT"] = 0
        
        summary = df.groupby("Plant").agg({
            "Trip No": "count",
            "Total_TAT": "mean"
        }).reset_index()
        
        summary = summary.rename(columns={"Trip No": "Trips", "Total_TAT": "Avg TAT (min)"})
        summary["Avg TAT (HH:MM)"] = summary["Avg TAT (min)"].apply(minutes_to_hhmm)
        
        return summary.sort_values("Avg TAT (min)").reset_index(drop=True)
    
    @staticmethod
    def find_bottlenecks(df: pd.DataFrame) -> pd.DataFrame:
        """Identify bottlenecks in TAT stages."""
        if df.empty:
            return pd.DataFrame()
        
        bottlenecks = []
        sla_map = {"stage1": 30, "stage2": 30, "stage3": 60, "stage4": 30, "stage5": 60}
        
        for i, col in enumerate(TATAnalytics.STAGE_COLS, 1):
            if col in df.columns:
                sla = sla_map.get(f"stage{i}", 60)
                delayed = df[df[col] > sla]
                
                if len(delayed) > 0:
                    bottlenecks.append({
                        "Stage": f"Stage {i}",
                        "Description": f"Stage {i}",
                        "SLA (min)": sla,
                        "Delayed Trips": len(delayed),
                        "Delay Rate": f"{len(delayed)/len(df)*100:.1f}%",
                        "Avg Delay (min)": (delayed[col] - sla).mean()
                    })
        
        return pd.DataFrame(bottlenecks).sort_values("Delayed Trips", ascending=False)
    
    @staticmethod
    def percentile_analysis(df: pd.DataFrame) -> pd.DataFrame:
        """Calculate percentile distribution."""
        if df.empty:
            return pd.DataFrame()
        
        percentiles = [50, 75, 90, 95, 99]
        results = []
        
        if all(col in df.columns for col in TATAnalytics.STAGE_COLS):
            df = df.copy()
            df["Total_TAT"] = (df[TATAnalytics.STAGE_COLS[0]] + df[TATAnalytics.STAGE_COLS[1]] + 
                              df[TATAnalytics.STAGE_COLS[2]] + df[TATAnalytics.STAGE_COLS[3]] + 
                              df[TATAnalytics.STAGE_COLS[4]])
            
            for p in percentiles:
                val = df["Total_TAT"].quantile(p / 100)
                results.append({
                    "Percentile": f"{p}th",
                    "Total TAT (min)": round(val, 1),
                    "Total TAT (HH:MM)": minutes_to_hhmm(val)
                })
        
        return pd.DataFrame(results)

# ============================================================================
# UI COMPONENTS
# ============================================================================

def load_custom_css():
    """Load custom CSS for the dashboard."""
    st.markdown("""
    <style>
        .main { background-color: #f5f7fa; }
        
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
        
        .metric-card {
            background: white;
            border-radius: 12px;
            padding: 1rem 1.5rem;
            text-align: center;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            transition: transform 0.2s;
            margin-bottom: 1rem;
        }
        .metric-card:hover { transform: translateY(-2px); }
        .metric-number { font-size: 2rem; font-weight: 700; color: #1a73e8; }
        .metric-label { font-size: 0.8rem; color: #666; margin-top: 0.25rem; }
        
        .filter-section {
            background: white;
            padding: 1rem 1.25rem;
            border-radius: 10px;
            margin-bottom: 1rem;
            box-shadow: 0 1px 4px rgba(0,0,0,0.05);
        }
        
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
        .tat-column-body { padding: 0.75rem 1rem; }
        .tat-stage-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.625rem 0;
            border-bottom: 1px solid #e8eaed;
        }
        .tat-stage-row:last-child { border-bottom: none; }
        .stage-name { font-weight: 600; color: #333; font-size: 0.85rem; }
        .stage-minutes { font-weight: 600; color: #333; font-size: 0.85rem; }
        .stage-hhmm { font-size: 0.75rem; color: #1a73e8; }
        .tat-total-row {
            display: flex;
            justify-content: space-between;
            padding: 0.75rem 1rem;
            background: #e8f5e9;
            border-radius: 8px;
            margin-top: 0.5rem;
            font-weight: 700;
        }
        
        .stButton button { border-radius: 8px; font-weight: 500; }
        .stAlert { border-radius: 10px; }
        
        h1, h2, h3 { font-weight: 600; }
        hr { margin: 1rem 0; }
    </style>
    """, unsafe_allow_html=True)


def render_trip_tab(df: pd.DataFrame):
    """Render the Trip Analysis tab."""
    st.markdown("## 🚛 Trip Report Analysis")
    st.markdown("*Analyze trip patterns, destination performance, and quantity trends*")
    
    if df.empty:
        st.warning("No trip data available.")
        return
    
    # Sidebar filters
    with st.sidebar:
        st.markdown("### 🔍 Filters")
        
        clients = sorted(df["Client"].dropna().unique().tolist())
        selected_client = st.selectbox("🏢 Client", clients, key="trip_client")
        
        client_plants = sorted(df[df["Client"] == selected_client]["Plant"].dropna().unique().tolist())
        selected_plants = st.multiselect("🏭 Plant", ["All Plants"] + client_plants, default=["All Plants"], key="trip_plants")
        
        if "All Plants" in selected_plants:
            selected_plants = client_plants
        
        months = sorted(df["Month"].dropna().unique().tolist(), reverse=True)
        selected_month = st.selectbox("📅 Month", ["All Months"] + months, key="trip_month")
        
        trip_types = ["All Types"] + sorted(df["Trip Type"].dropna().unique().tolist())
        selected_type = st.selectbox("🔄 Trip Type", trip_types, key="trip_type")
    
    # Apply filters
    filtered = df[df["Client"] == selected_client].copy()
    if selected_plants:
        filtered = filtered[filtered["Plant"].isin(selected_plants)]
    if selected_month != "All Months":
        filtered = filtered[filtered["Month"] == selected_month]
    if selected_type != "All Types":
        filtered = filtered[filtered["Trip Type"] == selected_type]
    
    st.caption(f"📌 Filters: {len(selected_plants)} plants | {selected_month} | {selected_type}")
    
    # Metrics
    metrics = TripAnalytics.calculate_metrics(filtered)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Trips", f"{metrics['total_trips']:,}")
    with col2:
        st.metric("Loaded Trips", f"{metrics['loaded_trips']:,}", delta=f"{metrics.get('load_rate', 0):.1f}%")
    with col3:
        st.metric("Empty Trips", f"{metrics['empty_trips']:,}")
    with col4:
        st.metric("Total Quantity", f"{metrics['total_quantity']:,.2f}")
    
    st.markdown("---")
    
    if filtered.empty:
        st.info("No trips found for selected filters.")
        return
    
    # Destination Analysis
    st.markdown("### 📍 Destination Analysis")
    
    dest_summary = TripAnalytics.destination_summary(filtered)
    
    if not dest_summary.empty:
        col1, col2 = st.columns([1, 1])
        
        with col1:
            chart_type = st.radio("Chart Type", ["Total Trips", "Total Quantity"], horizontal=True)
            
            if chart_type == "Total Trips":
                fig = px.bar(dest_summary.head(15), x="Destination", y="Total Trips", 
                            title="Top Destinations by Trip Count", color="Total Trips",
                            color_continuous_scale="Blues", text="Total Trips")
            else:
                fig = px.bar(dest_summary.head(15), x="Destination", y="Total Quantity",
                            title="Top Destinations by Quantity", color="Total Quantity",
                            color_continuous_scale="Greens", text="Total Quantity")
                fig.update_traces(texttemplate="%{text:,.0f}")
            
            fig.update_traces(textposition="outside")
            fig.update_layout(xaxis_tickangle=-45, height=450)
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.dataframe(dest_summary.head(20), use_container_width=True, hide_index=True)
    
    # Monthly Trend
    if "Month" in filtered.columns:
        st.markdown("### 📈 Monthly Trend")
        monthly = TripAnalytics.monthly_trend(filtered)
        
        if not monthly.empty:
            fig = px.line(monthly, x="Month", y=["Total Trips", "Cumulative Trips"],
                         title="Trip Volume Trends", markers=True)
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
    
    # Export
    st.markdown("---")
    csv = filtered.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Download Filtered Data (CSV)", csv, f"trip_data_{selected_client}.csv", "text/csv")


def render_tat_tab(df: pd.DataFrame, linked_trips: List[str] = None):
    """Render the TAT Analysis tab."""
    st.markdown("## 📊 Turnaround Time (TAT) Analysis")
    st.markdown("*Monitor loading/unloading cycle times, identify bottlenecks, and track SLA compliance*")
    
    if df.empty:
        st.warning("No TAT data available.")
        return
    
    # Sidebar filters
    with st.sidebar:
        st.markdown("### 🔍 TAT Filters")
        
        clients = ["All Clients"] + sorted(df["Client"].dropna().unique().tolist())
        selected_client = st.selectbox("🏢 Client", clients, key="tat_client")
        
        plants = ["All Plants"] + sorted(df["Plant"].dropna().unique().tolist())
        selected_plant = st.selectbox("🏭 Plant", plants, key="tat_plant")
        
        destinations = ["All Destinations"] + sorted(df["Destination"].dropna().unique().tolist())
        selected_dest = st.selectbox("📍 Destination", destinations, key="tat_dest")
        
        if linked_trips:
            use_link = st.checkbox("🔗 Use Trip Analysis Selection", value=True, key="tat_link")
        else:
            use_link = False
    
    # Apply filters
    filtered = df.copy()
    
    if selected_client != "All Clients":
        filtered = filtered[filtered["Client"] == selected_client]
    if selected_plant != "All Plants":
        filtered = filtered[filtered["Plant"] == selected_plant]
    if selected_dest != "All Destinations":
        filtered = filtered[filtered["Destination"] == selected_dest]
    if use_link and linked_trips:
        filtered = filtered[filtered["Trip No"].isin(linked_trips)]
    
    # Deduplicate
    dedup_config = DedupConfig()
    deduplicator = Deduplicator(dedup_config)
    processed_df, audit_df, stats = deduplicator.deduplicate(filtered, "Trip No")
    
    if stats.get("rows_removed", 0) > 0:
        st.info(f"🔁 Deduplication: {stats['rows_removed']} duplicate rows merged into {stats['duplicate_groups']} groups")
    
    # Metrics
    metrics = TATAnalytics.calculate_metrics(processed_df)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Trips", f"{metrics['total_trips']:,}")
    with col2:
        st.metric("Avg Loading TAT", minutes_to_hhmm(metrics['loading_tat_mean']))
    with col3:
        st.metric("Avg Unloading TAT", minutes_to_hhmm(metrics['unloading_tat_mean']))
    with col4:
        st.metric("Avg Total TAT", minutes_to_hhmm(metrics['total_tat_mean']))
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Median Total TAT", minutes_to_hhmm(metrics['total_tat_median']))
    with col2:
        st.metric("SLA Compliance", f"{metrics['sla_compliance']:.1f}%")
    with col3:
        st.metric("Delayed Trips", f"{metrics['delayed_trips']:,}")
    with col4:
        st.metric("Unique Trips", f"{len(processed_df):,}")
    
    st.markdown("---")
    
    if processed_df.empty:
        st.info("No TAT data found for selected filters.")
        return
    
    # Stage Breakdown
    st.markdown("### 📈 TAT Stage Breakdown")
    
    stage_data = {
        "DO Receipt": metrics['stage1_mean'],
        "Gate In (Loading)": metrics['stage2_mean'],
        "Loading Exit": metrics['stage3_mean'],
        "Gate In (Unloading)": metrics['stage4_mean'],
        "Unloading Exit": metrics['stage5_mean']
    }
    
    fig = go.Figure(data=[
        go.Bar(x=list(stage_data.keys()), y=list(stage_data.values()),
               text=[f"{v:.1f} min<br>{minutes_to_hhmm(v)}" for v in stage_data.values()],
               textposition='outside', marker_color=['#1a73e8', '#4285f4', '#8ab4f8', '#34a853', '#81c995'])
    ])
    fig.update_layout(title="Average Time per Stage", height=450, yaxis_title="Minutes")
    st.plotly_chart(fig, use_container_width=True)
    
    # Loading vs Unloading
    col1, col2 = st.columns(2)
    
    with col1:
        fig = go.Figure(data=[
            go.Bar(x=["Loading", "Unloading", "Total"],
                   y=[metrics['loading_tat_mean'], metrics['unloading_tat_mean'], metrics['total_tat_mean']],
                   text=[minutes_to_hhmm(metrics['loading_tat_mean']), minutes_to_hhmm(metrics['unloading_tat_mean']), 
                         minutes_to_hhmm(metrics['total_tat_mean'])],
                   textposition='outside',
                   marker_color=['#1a73e8', '#34a853', '#d32f2f'])
        ])
        fig.update_layout(title="Mean TAT", height=350, yaxis_title="Minutes")
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        fig = go.Figure(data=[
            go.Bar(x=["Loading", "Unloading", "Total"],
                   y=[metrics['loading_tat_median'], metrics['unloading_tat_median'], metrics['total_tat_median']],
                   text=[minutes_to_hhmm(metrics['loading_tat_median']), minutes_to_hhmm(metrics['unloading_tat_median']),
                         minutes_to_hhmm(metrics['total_tat_median'])],
                   textposition='outside',
                   marker_color=['#1a73e8', '#34a853', '#d32f2f'])
        ])
        fig.update_layout(title="Median TAT", height=350, yaxis_title="Minutes")
        st.plotly_chart(fig, use_container_width=True)
    
    # Bottlenecks
    st.markdown("### 🔍 Bottleneck Analysis")
    bottlenecks = TATAnalytics.find_bottlenecks(processed_df)
    
    if not bottlenecks.empty:
        st.warning(f"⚠️ Found {len(bottlenecks)} stages with SLA violations")
        
        fig = go.Figure(data=[
            go.Bar(x=bottlenecks["Stage"], y=bottlenecks["Delayed Trips"],
                   text=bottlenecks["Delay Rate"], textposition='outside',
                   marker_color='#d32f2f')
        ])
        fig.update_layout(title="Delayed Trips by Stage", height=350)
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(bottlenecks, use_container_width=True, hide_index=True)
    else:
        st.success("✅ No significant bottlenecks detected")
    
    # Percentile Analysis
    with st.expander("📊 Percentile Analysis"):
        percentiles = TATAnalytics.percentile_analysis(processed_df)
        if not percentiles.empty:
            fig = go.Figure(data=[
                go.Bar(x=percentiles["Percentile"], y=percentiles["Total TAT (min)"],
                       text=percentiles["Total TAT (HH:MM)"], textposition='outside',
                       marker_color='#1a73e8')
            ])
            fig.update_layout(title="Total TAT Percentile Distribution", height=350)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(percentiles, use_container_width=True, hide_index=True)
    
    # Export
    st.markdown("---")
    csv = processed_df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Download Processed TAT Data (CSV)", csv, "tat_data.csv", "text/csv")


# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    """Main application entry point."""
    
    # Page config
    st.set_page_config(
        page_title="Trip & TAT Analytics Suite",
        page_icon="🚛",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Load CSS
    load_custom_css()
    
    # Header
    st.markdown("""
    <div class="dashboard-header">
        <h1>🚛 Trip & TAT Analytics Suite</h1>
        <p>Logistics Performance Dashboard | Track deliveries, monitor turnaround times, optimize operations</p>
    </div>
    """, unsafe_allow_html=True)
    
    # File upload section
    st.markdown("### 📂 Data Upload")
    
    col1, col2 = st.columns(2)
    
    trip_data = None
    tat_data = None
    
    with col1:
        st.markdown("#### 🚛 Trip Reports")
        trip_files = st.file_uploader(
            "Upload Trip Report(s) (.xlsx, .csv)",
            type=["xlsx", "csv"],
            accept_multiple_files=True,
            key="trip_upload"
        )
        
        if trip_files:
            all_frames = []
            for file in trip_files:
                try:
                    if file.name.endswith('.csv'):
                        df = pd.read_csv(file)
                    else:
                        df = pd.read_excel(file, sheet_name=0)
                    
                    is_valid, errors, warnings = DataProcessor.validate_trip_data(df)
                    
                    if is_valid:
                        df_clean = DataProcessor.clean_trip_data(df)
                        df_clean["Source File"] = file.name
                        all_frames.append(df_clean)
                        
                        for warning in warnings:
                            st.warning(f"{file.name}: {warning}")
                    else:
                        for error in errors:
                            st.error(f"{file.name}: {error}")
                except Exception as e:
                    st.error(f"Error reading {file.name}: {str(e)}")
            
            if all_frames:
                combined = pd.concat(all_frames, ignore_index=True)
                dedup_config = DedupConfig()
                deduplicator = Deduplicator(dedup_config)
                trip_data, audit, stats = deduplicator.deduplicate(combined, "Trip No")
                
                st.success(f"✅ Loaded {len(trip_data):,} unique trip records from {len(trip_files)} file(s)")
                if stats.get("rows_removed", 0) > 0:
                    st.info(f"🔁 Deduplication removed {stats['rows_removed']} duplicate rows")
    
    with col2:
        st.markdown("#### 📊 TAT Data")
        tat_file = st.file_uploader(
            "Upload TAT Data File (.xlsx, .csv)",
            type=["xlsx", "csv"],
            key="tat_upload"
        )
        
        if tat_file:
            try:
                if tat_file.name.endswith('.csv'):
                    df = pd.read_csv(tat_file)
                else:
                    df = pd.read_excel(tat_file, sheet_name=0)
                
                is_valid, errors, warnings = DataProcessor.validate_tat_data(df)
                
                if is_valid:
                    df_clean = DataProcessor.clean_tat_data(df)
                    dedup_config = DedupConfig()
                    deduplicator = Deduplicator(dedup_config)
                    tat_data, audit, stats = deduplicator.deduplicate(df_clean, "Trip No")
                    
                    st.success(f"✅ Loaded {len(tat_data):,} unique TAT records")
                    for warning in warnings:
                        st.warning(warning)
                    if stats.get("rows_removed", 0) > 0:
                        st.info(f"🔁 Deduplication removed {stats['rows_removed']} duplicate rows")
                else:
                    for error in errors:
                        st.error(error)
            except Exception as e:
                st.error(f"Error reading TAT file: {str(e)}")
    
    st.divider()
    
    # Check if any data is loaded
    if trip_data is None and tat_data is None:
        st.info("👈 Please upload trip reports and/or TAT data files to begin analysis")
        
        with st.expander("📋 Data Format Requirements"):
            st.markdown("""
            ### Trip Report Requirements
            - **Trip No** (required) - Unique trip identifier
            - **Client** (required) - Customer name  
            - **Destination** (required) - Delivery location
            - **Start Date** (required) - Trip start date
            - **Trip Type** (required) - "Loaded" or "Empty"
            
            ### TAT Data Requirements
            - **Trip No** (required) - Trip identifier
            - **Date** (required) - Transaction date
            - TAT stage columns (optional but recommended)
            """)
        return
    
    # Create tabs
    tabs = []
    if trip_data is not None:
        tabs.append(("🚛 Trip Analysis", "trip"))
    if tat_data is not None:
        tabs.append(("📊 TAT Report", "tat"))
    
    if len(tabs) == 2:
        tab1, tab2 = st.tabs([t[0] for t in tabs])
        
        with tab1:
            render_trip_tab(trip_data)
        
        with tab2:
            linked_trips = trip_data["Trip No"].unique().tolist() if trip_data is not None else None
            render_tat_tab(tat_data, linked_trips)
    
    elif trip_data is not None:
        render_trip_tab(trip_data)
    
    elif tat_data is not None:
        render_tat_tab(tat_data)


if __name__ == "__main__":
    main()
