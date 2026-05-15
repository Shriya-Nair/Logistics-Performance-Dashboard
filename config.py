"""
Configuration settings for the Trip & TAT Analytics Suite.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import os
from pathlib import Path

# Project paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
SAMPLE_DATA_DIR = BASE_DIR / "sample_data"

# Create directories if they don't exist
for dir_path in [DATA_DIR, LOGS_DIR, SAMPLE_DATA_DIR]:
    dir_path.mkdir(exist_ok=True)


@dataclass
class ColumnMapping:
    """Column name mappings for different data sources."""
    
    # Trip report columns
    trip_report: Dict[str, str] = field(default_factory=lambda: {
        "trip_no": "Trip No",
        "client": "Client",
        "destination": "Destination",
        "plant": "Plant",
        "start_date": "Start Date",
        "trip_type": "Trip Type",
        "inv_qty": "Inv Qty",
        "source_file": "Source File"
    })
    
    # TAT report columns
    tat_report: Dict[str, str] = field(default_factory=lambda: {
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
    
    # Alternative column names for fuzzy matching
    trip_report_alternatives: Dict[str, List[str]] = field(default_factory=lambda: {
        "trip_no": ["Trip Number", "TripNo", "Trip ID"],
        "client": ["Customer", "Client Name", "Customer Name"],
        "destination": ["To", "Delivery Location", "Drop Location"],
        "plant": ["Source", "Source Place", "Origin", "From"],
        "start_date": ["Trip Date", "Transaction Date", "Date"],
        "trip_type": ["Type", "Trip Category"],
        "inv_qty": ["Quantity", "Qty", "Invoice Quantity"]
    })
    
    tat_report_alternatives: Dict[str, List[str]] = field(default_factory=lambda: {
        "trip_no": ["Trip Number", "TripNo", "Trip ID"],
        "client": ["Customer", "Client Name", "Customer Name"],
        "plant": ["Source Plant", "Source", "Origin"],
        "destination": ["To", "Delivery Location", "Unloading Point"],
        "date": ["Start Date", "Trip Date", "Transaction Date"],
        "stage1": ["DO Receipt (Mins)", "Actual DO Receipt"],
        "stage2": ["Gate In (Mins)", "Actual Gate In"],
        "stage3": ["Loaded Exit (Mins)", "Actual Loaded Exit"],
        "stage4": ["Gate In for Unloading (Mins)", "Actual Gate In for Unloading"],
        "stage5": ["Unloaded (Mins)", "Actual Unloaded"]
    })


@dataclass
class DeduplicationConfig:
    """Configuration for deduplication logic."""
    
    # Columns to sum when merging duplicates
    sum_columns: List[str] = field(default_factory=lambda: ["Inv Qty"])
    
    # Columns to average when merging duplicates
    avg_columns: List[str] = field(default_factory=lambda: [
        "Actual DO Receipt (Mins)", "Actual Gate In(Mins)", 
        "Actual Loaded Exit(Mins)", "Actual Gate In for Unloading(Mins)", 
        "Actual Unloaded (Mins)"
    ])
    
    # Columns to take first value
    first_columns: List[str] = field(default_factory=lambda: [
        "Client", "Destination", "Plant", "Start Date", "Trip Type", "Source File"
    ])
    
    # Columns to take max value
    max_columns: List[str] = field(default_factory=list)
    
    # Columns to take min value
    min_columns: List[str] = field(default_factory=list)
    
    # Fuzzy matching threshold for destination names
    fuzzy_match_threshold: float = 0.82
    
    # Whether to standardize destination names
    standardize_destinations: bool = True


@dataclass
class AnalyticsConfig:
    """Configuration for analytics calculations."""
    
    # TAT stage descriptions
    tat_stages: Dict[str, str] = field(default_factory=lambda: {
        "stage1": "DO Receipt to Gate Entry",
        "stage2": "Gate Entry to Loading Bay",
        "stage3": "Loading Process & Exit",
        "stage4": "Gate In for Unloading",
        "stage5": "Unloading Process"
    })
    
    # TAT thresholds for SLA monitoring (in minutes)
    tat_sla_thresholds: Dict[str, int] = field(default_factory=lambda: {
        "stage1": 30,
        "stage2": 30,
        "stage3": 60,
        "stage4": 30,
        "stage5": 60,
        "loading_total": 120,
        "unloading_total": 90,
        "total": 210
    })
    
    # Percentiles to calculate
    percentiles: List[int] = field(default_factory=lambda: [50, 75, 90, 95, 99])
    
    # Outlier detection (IQR multiplier)
    outlier_iqr_multiplier: float = 1.5


@dataclass
class UIConfig:
    """Configuration for UI components."""
    
    # Color schemes
    colors: Dict[str, str] = field(default_factory=lambda: {
        "primary": "#1a73e8",
        "secondary": "#34a853",
        "danger": "#d32f2f",
        "warning": "#f9ab00",
        "info": "#4285f4",
        "dark": "#1a1a2e",
        "light": "#f5f7fa",
        "success": "#0d47a1"
    })
    
    # Chart themes
    chart_template: str = "plotly_white"
    
    # Pagination
    page_size: int = 50
    
    # Date format
    date_format: str = "%Y-%m-%d"
    
    # Number format
    number_format: str = "{:,.2f}"


# Allowed clients for filtering
ALLOWED_CLIENTS = [
    "ARCELORMITTAL NIPPON STEEL INDIA LIMITED",
    "DALMIA CEMENT (BHARAT)LIMITED", 
    "HINDUSTAN ZINC LIMITED",
    "JINDAL STEEL AND POWER LIMITED",
    "JSW STEEL LIMITED",
    "TATA STEEL LIMITED CHENNAI",
    "TATA STEEL LIMITED"
]

# Column validation requirements
REQUIRED_TRIP_COLUMNS = ["Client", "Destination", "Start Date", "Trip No", "Trip Type"]
REQUIRED_TAT_COLUMNS = ["Trip No", "Date"]

# Logging configuration
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        }
    },
    "handlers": {
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOGS_DIR / "app.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5,
            "formatter": "standard"
        },
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard"
        }
    },
    "root": {
        "level": "INFO",
        "handlers": ["console", "file"]
    }
}
