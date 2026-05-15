"""
Turnaround Time (TAT) analytics and metrics calculations.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from config.settings import AnalyticsConfig
from utils.logger import get_logger, log_performance

logger = get_logger(__name__)


@dataclass
class TATMetrics:
    """Container for TAT analysis metrics."""
    
    # Stage metrics (minutes)
    stage1_mean: float = 0.0
    stage2_mean: float = 0.0
    stage3_mean: float = 0.0
    stage4_mean: float = 0.0
    stage5_mean: float = 0.0
    
    # Stage medians
    stage1_median: float = 0.0
    stage2_median: float = 0.0
    stage3_median: float = 0.0
    stage4_median: float = 0.0
    stage5_median: float = 0.0
    
    # Aggregate metrics
    loading_tat_mean: float = 0.0
    loading_tat_median: float = 0.0
    unloading_tat_mean: float = 0.0
    unloading_tat_median: float = 0.0
    total_tat_mean: float = 0.0
    total_tat_median: float = 0.0
    
    # SLA metrics
    sla_compliance_rate: float = 0.0
    delayed_trips: int = 0
    
    # Data quality
    total_trips: int = 0
    trips_with_complete_data: int = 0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for display."""
        return {
            "Total Trips": f"{self.total_trips:,}",
            "Avg Loading TAT": self._format_time(self.loading_tat_mean),
            "Avg Unloading TAT": self._format_time(self.unloading_tat_mean),
            "Avg Total TAT": self._format_time(self.total_tat_mean),
            "Median Loading TAT": self._format_time(self.loading_tat_median),
            "Median Unloading TAT": self._format_time(self.unloading_tat_median),
            "Median Total TAT": self._format_time(self.total_tat_median),
            "SLA Compliance": f"{self.sla_compliance_rate:.1f}%",
            "Delayed Trips": f"{self.delayed_trips:,}"
        }
    
    @staticmethod
    def _format_time(minutes: float) -> str:
        """Format minutes to HH:MM."""
        if pd.isna(minutes) or minutes < 0:
            return "00:00"
        hours = int(minutes // 60)
        mins = int(minutes % 60)
        return f"{hours:02d}:{mins:02d}"


class TATAnalyticsEngine:
    """Engine for computing TAT analytics."""
    
    def __init__(self, config: AnalyticsConfig):
        self.config = config
        self.stage_cols = [
            "Actual DO Receipt (Mins)",
            "Actual Gate In(Mins)",
            "Actual Loaded Exit(Mins)",
            "Actual Gate In for Unloading(Mins)",
            "Actual Unloaded (Mins)"
        ]
    
    def _calculate_stage_metrics(self, df: pd.DataFrame) -> Tuple[Dict, Dict]:
        """Calculate mean and median for each TAT stage."""
        means = {}
        medians = {}
        
        for i, col in enumerate(self.stage_cols, 1):
            if col in df.columns:
                values = df[col].dropna()
                if len(values) > 0:
                    means[f"stage{i}_mean"] = values.mean()
                    medians[f"stage{i}_median"] = values.median()
                else:
                    means[f"stage{i}_mean"] = 0.0
                    medians[f"stage{i}_median"] = 0.0
            else:
                means[f"stage{i}_mean"] = 0.0
                medians[f"stage{i}_median"] = 0.0
        
        return means, medians
    
    def _calculate_aggregate_metrics(self, df: pd.DataFrame) -> Dict:
        """Calculate loading, unloading, and total TAT metrics."""
        metrics = {}
        
        # Calculate TAT values for each row
        if all(col in df.columns for col in self.stage_cols):
            df = df.copy()
            df["_loading_tat"] = df[self.stage_cols[0]] + df[self.stage_cols[1]] + df[self.stage_cols[2]]
            df["_unloading_tat"] = df[self.stage_cols[3]] + df[self.stage_cols[4]]
            df["_total_tat"] = df["_loading_tat"] + df["_unloading_tat"]
            
            metrics["loading_tat_mean"] = df["_loading_tat"].mean()
            metrics["loading_tat_median"] = df["_loading_tat"].median()
            metrics["unloading_tat_mean"] = df["_unloading_tat"].mean()
            metrics["unloading_tat_median"] = df["_unloading_tat"].median()
            metrics["total_tat_mean"] = df["_total_tat"].mean()
            metrics["total_tat_median"] = df["_total_tat"].median()
            
            # SLA calculation
            total_loading_sla = self.config.tat_sla_thresholds.get("loading_total", 120)
            total_unloading_sla = self.config.tat_sla_thresholds.get("unloading_total", 90)
            total_sla = self.config.tat_sla_thresholds.get("total", 210)
            
            compliant = df[
                (df["_loading_tat"] <= total_loading_sla) &
                (df["_unloading_tat"] <= total_unloading_sla) &
                (df["_total_tat"] <= total_sla)
            ]
            metrics["sla_compliance_rate"] = (len(compliant) / len(df) * 100) if len(df) > 0 else 0
            metrics["delayed_trips"] = len(df) - len(compliant)
        else:
            metrics["loading_tat_mean"] = 0.0
            metrics["loading_tat_median"] = 0.0
            metrics["unloading_tat_mean"] = 0.0
            metrics["unloading_tat_median"] = 0.0
            metrics["total_tat_mean"] = 0.0
            metrics["total_tat_median"] = 0.0
            metrics["sla_compliance_rate"] = 0.0
            metrics["delayed_trips"] = 0
        
        return metrics
    
    @log_performance
    def calculate_metrics(self, df: pd.DataFrame) -> TATMetrics:
        """Calculate comprehensive TAT metrics."""
        if df.empty:
            return TATMetrics()
        
        metrics = TATMetrics()
        metrics.total_trips = len(df)
        
        # Check data completeness
        complete_mask = df[self.stage_cols].notna().all(axis=1)
        metrics.trips_with_complete_data = complete_mask.sum()
        
        # Calculate stage metrics
        means, medians = self._calculate_stage_metrics(df[complete_mask] if complete_mask.any() else df)
        
        metrics.stage1_mean = means.get("stage1_mean", 0.0)
        metrics.stage2_mean = means.get("stage2_mean", 0.0)
        metrics.stage3_mean = means.get("stage3_mean", 0.0)
        metrics.stage4_mean = means.get("stage4_mean", 0.0)
        metrics.stage5_mean = means.get("stage5_mean", 0.0)
        
        metrics.stage1_median = medians.get("stage1_median", 0.0)
        metrics.stage2_median = medians.get("stage2_median", 0.0)
        metrics.stage3_median = medians.get("stage3_median", 0.0)
        metrics.stage4_median = medians.get("stage4_median", 0.0)
        metrics.stage5_median = medians.get("stage5_median", 0.0)
        
        # Calculate aggregate metrics
        agg_metrics = self._calculate_aggregate_metrics(df[complete_mask] if complete_mask.any() else df)
        
        metrics.loading_tat_mean = agg_metrics.get("loading_tat_mean", 0.0)
        metrics.loading_tat_median = agg_metrics.get("loading_tat_median", 0.0)
        metrics.unloading_tat_mean = agg_metrics.get("unloading_tat_mean", 0.0)
        metrics.unloading_tat_median = agg_metrics.get("unloading_tat_median", 0.0)
        metrics.total_tat_mean = agg_metrics.get("total_tat_mean", 0.0)
        metrics.total_tat_median = agg_metrics.get("total_tat_median", 0.0)
        metrics.sla_compliance_rate = agg_metrics.get("sla_compliance_rate", 0.0)
        metrics.delayed_trips = agg_metrics.get("delayed_trips", 0)
        
        return metrics
    
    @log_performance
    def plant_tat_summary(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate plant-wise TAT summary."""
        if df.empty or "Plant" not in df.columns:
            return pd.DataFrame()
        
        # Calculate TAT for each row
        df = df.copy()
        if all(col in df.columns for col in self.stage_cols):
            df["Loading_TAT"] = df[self.stage_cols[0]] + df[self.stage_cols[1]] + df[self.stage_cols[2]]
            df["Unloading_TAT"] = df[self.stage_cols[3]] + df[self.stage_cols[4]]
            df["Total_TAT"] = df["Loading_TAT"] + df["Unloading_TAT"]
        else:
            df["Loading_TAT"] = 0
            df["Unloading_TAT"] = 0
            df["Total_TAT"] = 0
        
        # Group by plant
        summary = df.groupby("Plant").agg({
            "Trip No": "count",
            "Loading_TAT": ["mean", "median"],
            "Unloading_TAT": ["mean", "median"],
            "Total_TAT": ["mean", "median"]
        }).round(2)
        
        # Flatten column names
        summary.columns = [f"{col[0]}_{col[1]}" if col[1] else col[0] for col in summary.columns]
        summary = summary.reset_index()
        
        # Add formatted time columns
        for col in ["Loading_TAT_mean", "Unloading_TAT_mean", "Total_TAT_mean"]:
            if col in summary.columns:
                summary[f"{col}_HHMM"] = summary[col].apply(self._minutes_to_hhmm)
        
        return summary
    
    @log_performance
    def client_tat_summary(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate client-wise TAT summary."""
        if df.empty or "Client" not in df.columns:
            return pd.DataFrame()
        
        df = df.copy()
        if all(col in df.columns for col in self.stage_cols):
            df["Loading_TAT"] = df[self.stage_cols[0]] + df[self.stage_cols[1]] + df[self.stage_cols[2]]
            df["Unloading_TAT"] = df[self.stage_cols[3]] + df[self.stage_cols[4]]
            df["Total_TAT"] = df["Loading_TAT"] + df["Unloading_TAT"]
        else:
            df["Loading_TAT"] = 0
            df["Unloading_TAT"] = 0
            df["Total_TAT"] = 0
        
        summary = df.groupby("Client").agg({
            "Trip No": "count",
            "Loading_TAT": ["mean", "median"],
            "Unloading_TAT": ["mean", "median"],
            "Total_TAT": ["mean", "median"]
        }).round(2)
        
        summary.columns = [f"{col[0]}_{col[1]}" if col[1] else col[0] for col in summary.columns]
        summary = summary.reset_index()
        
        return summary
    
    @log_performance
    def find_bottlenecks(self, df: pd.DataFrame) -> pd.DataFrame:
        """Identify TAT bottlenecks by analyzing stage delays."""
        if df.empty:
            return pd.DataFrame()
        
        bottlenecks = []
        
        for i, col in enumerate(self.stage_cols, 1):
            if col in df.columns:
                sla = self.config.tat_sla_thresholds.get(f"stage{i}", 60)
                delayed = df[df[col] > sla]
                
                if len(delayed) > 0:
                    bottlenecks.append({
                        "Stage": f"Stage {i}",
                        "Description": self.config.tat_stages.get(f"stage{i}", f"Stage {i}"),
                        "SLA Threshold (min)": sla,
                        "Delayed Trips": len(delayed),
                        "Delay Rate": f"{len(delayed)/len(df)*100:.1f}%",
                        "Avg Delay (min)": delayed[col].mean() - sla,
                        "Max Delay (min)": (delayed[col] - sla).max()
                    })
        
        return pd.DataFrame(bottlenecks).sort_values("Delayed Trips", ascending=False)
    
    @log_performance
    def percentile_analysis(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate percentile distribution for TAT metrics."""
        if df.empty:
            return pd.DataFrame()
        
        df = df.copy()
        if all(col in df.columns for col in self.stage_cols):
            df["Loading_TAT"] = df[self.stage_cols[0]] + df[self.stage_cols[1]] + df[self.stage_cols[2]]
            df["Unloading_TAT"] = df[self.stage_cols[3]] + df[self.stage_cols[4]]
            df["Total_TAT"] = df["Loading_TAT"] + df["Unloading_TAT"]
        else:
            df["Total_TAT"] = 0
        
        percentiles = self.config.percentiles
        results = []
        
        for p in percentiles:
            results.append({
                "Percentile": f"{p}th",
                "Total TAT (min)": df["Total_TAT"].quantile(p / 100),
                "Total TAT (HH:MM)": self._minutes_to_hhmm(df["Total_TAT"].quantile(p / 100))
            })
        
        return pd.DataFrame(results)
    
    @staticmethod
    def _minutes_to_hhmm(minutes: float) -> str:
        """Convert minutes to HH:MM format."""
        if pd.isna(minutes) or minutes < 0:
            return "00:00"
        hours = int(minutes // 60)
        mins = int(minutes % 60)
        return f"{hours:02d}:{mins:02d}"
