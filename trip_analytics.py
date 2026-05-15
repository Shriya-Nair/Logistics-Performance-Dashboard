"""
Trip report analytics and metrics calculations.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from config.settings import AnalyticsConfig
from utils.logger import get_logger, log_performance

logger = get_logger(__name__)


@dataclass
class TripMetrics:
    """Container for trip analysis metrics."""
    
    # Basic metrics
    total_trips: int = 0
    loaded_trips: int = 0
    empty_trips: int = 0
    total_quantity: float = 0.0
    
    # Derived metrics
    load_rate: float = 0.0
    empty_rate: float = 0.0
    
    # Distribution metrics
    unique_destinations: int = 0
    unique_plants: int = 0
    unique_clients: int = 0
    
    # Period metrics (if date available)
    earliest_date: Optional[str] = None
    latest_date: Optional[str] = None
    days_span: int = 0
    avg_trips_per_day: float = 0.0
    
    def calculate_derived(self) -> 'TripMetrics':
        """Calculate derived metrics."""
        if self.total_trips > 0:
            self.load_rate = self.loaded_trips / self.total_trips * 100
            self.empty_rate = self.empty_trips / self.total_trips * 100
        return self
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for display."""
        return {
            "Total Trips": f"{self.total_trips:,}",
            "Loaded Trips": f"{self.loaded_trips:,}",
            "Empty Trips": f"{self.empty_trips:,}",
            "Load Rate": f"{self.load_rate:.1f}%",
            "Total Quantity": f"{self.total_quantity:,.2f}",
            "Unique Destinations": f"{self.unique_destinations:,}",
            "Unique Plants": f"{self.unique_plants:,}",
            "Avg Trips/Day": f"{self.avg_trips_per_day:.1f}"
        }


class TripAnalyticsEngine:
    """Engine for computing trip analytics."""
    
    def __init__(self, config: AnalyticsConfig):
        self.config = config
    
    @log_performance
    def calculate_metrics(self, df: pd.DataFrame) -> TripMetrics:
        """Calculate comprehensive trip metrics."""
        if df.empty:
            return TripMetrics()
        
        metrics = TripMetrics()
        
        # Basic counts
        metrics.total_trips = len(df)
        
        if "Trip Type" in df.columns:
            metrics.loaded_trips = len(df[df["Trip Type"] == "Loaded"])
            metrics.empty_trips = len(df[df["Trip Type"] == "Empty"])
        
        # Quantity
        if "Inv Qty" in df.columns:
            metrics.total_quantity = df["Inv Qty"].sum()
        
        # Unique values
        if "Destination" in df.columns:
            metrics.unique_destinations = df["Destination"].nunique()
        
        if "Plant" in df.columns:
            metrics.unique_plants = df["Plant"].nunique()
        
        if "Client" in df.columns:
            metrics.unique_clients = df["Client"].nunique()
        
        # Date-based metrics
        if "Start Date" in df.columns and not df["Start Date"].isna().all():
            valid_dates = df["Start Date"].dropna()
            if not valid_dates.empty:
                metrics.earliest_date = valid_dates.min().strftime("%Y-%m-%d")
                metrics.latest_date = valid_dates.max().strftime("%Y-%m-%d")
                metrics.days_span = (valid_dates.max() - valid_dates.min()).days
                if metrics.days_span > 0:
                    metrics.avg_trips_per_day = metrics.total_trips / metrics.days_span
        
        return metrics.calculate_derived()
    
    @log_performance
    def destination_summary(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate destination-wise trip summary."""
        if df.empty:
            return pd.DataFrame()
        
        # Define aggregation
        agg_dict = {
            "Trip No": "count",
            "Inv Qty": "sum"
        }
        
        if "Plant" in df.columns:
            agg_dict["Plant"] = lambda x: x.nunique()
        
        if "Trip Type" in df.columns:
            agg_dict["Loaded Trips"] = ("Trip Type", lambda x: (x == "Loaded").sum())
            agg_dict["Empty Trips"] = ("Trip Type", lambda x: (x == "Empty").sum())
        
        # Group by destination
        summary = df.groupby("Destination").agg(**agg_dict).reset_index()
        
        # Rename columns
        rename_map = {
            "Trip No": "Total Trips",
            "Inv Qty": "Total Quantity",
            "Plant": "Unique Plants"
        }
        summary = summary.rename(columns=rename_map)
        
        # Add percentage columns
        total_trips = summary["Total Trips"].sum()
        if total_trips > 0:
            summary["% of Trips"] = (summary["Total Trips"] / total_trips * 100).round(1)
        
        # Sort by total trips descending
        summary = summary.sort_values("Total Trips", ascending=False).reset_index(drop=True)
        
        return summary
    
    @log_performance
    def plant_summary(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate plant-wise trip summary."""
        if df.empty or "Plant" not in df.columns:
            return pd.DataFrame()
        
        agg_dict = {
            "Trip No": "count",
            "Inv Qty": "sum",
            "Destination": lambda x: x.nunique()
        }
        
        if "Client" in df.columns:
            agg_dict["Client"] = lambda x: x.nunique()
        
        summary = df.groupby("Plant").agg(**agg_dict).reset_index()
        
        rename_map = {
            "Trip No": "Total Trips",
            "Inv Qty": "Total Quantity",
            "Destination": "Unique Destinations",
            "Client": "Unique Clients"
        }
        summary = summary.rename(columns=rename_map)
        
        # Sort by total trips
        summary = summary.sort_values("Total Trips", ascending=False).reset_index(drop=True)
        
        return summary
    
    @log_performance
    def monthly_trend(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate monthly trend analysis."""
        if df.empty or "Month" not in df.columns or "Start Date" not in df.columns:
            return pd.DataFrame()
        
        # Group by month
        monthly = df.groupby("Month").agg({
            "Trip No": "count",
            "Inv Qty": "sum"
        }).reset_index()
        
        monthly = monthly.rename(columns={
            "Trip No": "Total Trips",
            "Inv Qty": "Total Quantity"
        })
        
        # Sort by month
        monthly = monthly.sort_values("Month").reset_index(drop=True)
        
        # Add cumulative totals
        monthly["Cumulative Trips"] = monthly["Total Trips"].cumsum()
        monthly["Cumulative Quantity"] = monthly["Total Quantity"].cumsum()
        
        return monthly
    
    @log_performance
    def client_summary(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate client-wise trip summary."""
        if df.empty or "Client" not in df.columns:
            return pd.DataFrame()
        
        agg_dict = {
            "Trip No": "count",
            "Inv Qty": "sum",
            "Destination": lambda x: x.nunique(),
            "Plant": lambda x: x.nunique()
        }
        
        summary = df.groupby("Client").agg(**agg_dict).reset_index()
        
        rename_map = {
            "Trip No": "Total Trips",
            "Inv Qty": "Total Quantity",
            "Destination": "Unique Destinations",
            "Plant": "Unique Plants"
        }
        summary = summary.rename(columns=rename_map)
        
        # Add percentage
        total_trips = summary["Total Trips"].sum()
        if total_trips > 0:
            summary["% of Trips"] = (summary["Total Trips"] / total_trips * 100).round(1)
        
        # Sort by total trips
        summary = summary.sort_values("Total Trips", ascending=False).reset_index(drop=True)
        
        return summary
    
    def find_anomalies(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Detect anomalies in trip data.
        
        Checks for:
        - Zero quantity on loaded trips
        - Extremely high quantity values (outliers)
        - Invalid trip types
        """
        if df.empty:
            return pd.DataFrame()
        
        anomalies = []
        
        # Check loaded trips with zero quantity
        if "Trip Type" in df.columns and "Inv Qty" in df.columns:
            zero_qty_loaded = df[(df["Trip Type"] == "Loaded") & (df["Inv Qty"] <= 0)]
            for _, row in zero_qty_loaded.iterrows():
                anomalies.append({
                    "Trip No": row.get("Trip No", "Unknown"),
                    "Anomaly Type": "Zero Quantity on Loaded Trip",
                    "Details": f"Trip marked as Loaded but quantity is {row.get('Inv Qty', 0)}",
                    "Severity": "High"
                })
        
        # Check quantity outliers (using IQR method)
        if "Inv Qty" in df.columns and len(df) > 1:
            q1 = df["Inv Qty"].quantile(0.25)
            q3 = df["Inv Qty"].quantile(0.75)
            iqr = q3 - q1
            upper_bound = q3 + 1.5 * iqr
            
            outliers = df[df["Inv Qty"] > upper_bound]
            for _, row in outliers.iterrows():
                anomalies.append({
                    "Trip No": row.get("Trip No", "Unknown"),
                    "Anomaly Type": "Quantity Outlier",
                    "Details": f"Quantity {row.get('Inv Qty', 0):,.2f} exceeds typical range",
                    "Severity": "Medium"
                })
        
        return pd.DataFrame(anomalies)
