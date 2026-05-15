"""
Advanced deduplication logic for accurate data aggregation.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict
import re

from config.settings import DeduplicationConfig
from utils.logger import get_logger, log_performance
from difflib import SequenceMatcher

logger = get_logger(__name__)


@dataclass
class DeduplicationResult:
    """Result of deduplication process."""
    deduplicated_df: pd.DataFrame
    audit_df: pd.DataFrame
    stats: Dict[str, Any]
    
    def to_dict(self) -> Dict:
        return {
            "original_rows": self.stats.get("original_rows", 0),
            "deduplicated_rows": self.stats.get("deduplicated_rows", 0),
            "duplicate_groups": self.stats.get("duplicate_groups", 0),
            "rows_removed": self.stats.get("rows_removed", 0)
        }


class DestinationNormalizer:
    """Normalizes destination names using fuzzy matching."""
    
    def __init__(self, threshold: float = 0.82):
        self.threshold = threshold
        self.alias_map: Dict[str, str] = {}
    
    def _normalize(self, name: str) -> str:
        """Normalize a destination name."""
        if pd.isna(name):
            return "Unknown"
        name = str(name).lower().strip()
        name = re.sub(r"[^\w\s]", "", name)
        name = re.sub(r"\s+", " ", name)
        return name
    
    def _similar(self, a: str, b: str) -> bool:
        """Check if two names are similar."""
        na, nb = self._normalize(a), self._normalize(b)
        if na == nb:
            return True
        return SequenceMatcher(None, na, nb).ratio() >= self.threshold
    
    def build_alias_map(self, destinations: pd.Series) -> Dict[str, str]:
        """Build mapping of variants to canonical names."""
        unique_dests = destinations.dropna().unique().tolist()
        
        if not unique_dests:
            return {}
        
        # Cluster similar destinations
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
        
        # Choose canonical name (longest as it's likely most complete)
        alias_map = {}
        for cluster in clusters:
            canonical = max(cluster, key=len)
            for variant in cluster:
                alias_map[variant] = canonical
        
        self.alias_map = alias_map
        return alias_map
    
    def normalize_column(self, df: pd.DataFrame, column: str) -> pd.Series:
        """Apply normalization to a dataframe column."""
        if column not in df.columns:
            return df[column] if column in df.columns else pd.Series()
        
        if not self.alias_map:
            self.build_alias_map(df[column])
        
        return df[column].map(lambda x: self.alias_map.get(x, x))


class AdvancedDeduplicator:
    """
    Advanced deduplication engine with configurable aggregation strategies.
    
    Key improvements over the old implementation:
    1. Multiple aggregation strategies per column (sum, avg, first, max, min, last)
    2. Proper handling of edge cases (all nulls, mixed types)
    3. Audit trail with detailed transformation logs
    4. Statistical validation of results
    5. Configurable business rules
    """
    
    def __init__(self, config: DeduplicationConfig):
        self.config = config
    
    def _aggregate_group(self, group: pd.DataFrame, key: str, strategy: str) -> Any:
        """Apply aggregation strategy to a group."""
        if key not in group.columns:
            return None
        
        values = group[key]
        
        # Remove NaN for certain strategies
        if strategy in ['sum', 'mean', 'min', 'max', 'median']:
            values = values.dropna()
        
        if len(values) == 0:
            return None
        
        try:
            if strategy == 'sum':
                return values.sum()
            elif strategy == 'mean':
                return values.mean()
            elif strategy == 'first':
                return values.iloc[0]
            elif strategy == 'last':
                return values.iloc[-1]
            elif strategy == 'min':
                return values.min()
            elif strategy == 'max':
                return values.max()
            elif strategy == 'median':
                return values.median()
            elif strategy == 'mode':
                return values.mode().iloc[0] if not values.mode().empty else values.iloc[0]
            elif strategy == 'concat':
                return '; '.join(values.astype(str).unique())
            else:
                return values.iloc[0]
        except Exception as e:
            logger.warning(f"Aggregation failed for {key} with {strategy}: {str(e)}")
            return values.iloc[0] if len(values) > 0 else None
    
    def _create_aggregation_dict(self, df: pd.DataFrame, group_key: str) -> Dict[str, str]:
        """Create aggregation dictionary based on configuration."""
        agg_dict = {}
        
        # Sum columns
        for col in self.config.sum_columns:
            if col in df.columns:
                agg_dict[col] = 'sum'
        
        # Average columns
        for col in self.config.avg_columns:
            if col in df.columns:
                agg_dict[col] = 'mean'
        
        # Max columns
        for col in self.config.max_columns:
            if col in df.columns:
                agg_dict[col] = 'max'
        
        # Min columns
        for col in self.config.min_columns:
            if col in df.columns:
                agg_dict[col] = 'min'
        
        # For all other columns, take first
        all_other_cols = [c for c in df.columns if c != group_key and c not in agg_dict]
        for col in all_other_cols:
            agg_dict[col] = 'first'
        
        return agg_dict
    
    def _create_audit_record(self, group_key: str, group: pd.DataFrame, 
                             aggregated: pd.Series, agg_dict: Dict) -> Dict:
        """Create an audit record for a duplicate group."""
        record = {
            "Group_Key": group_key,
            "Original_Rows": len(group),
            "Action": "MERGED"
        }
        
        # Log summed columns
        for col in self.config.sum_columns:
            if col in group.columns and col in agg_dict:
                original_vals = group[col].tolist()
                original_str = "; ".join([f"{v:.2f}" if isinstance(v, (int, float)) else str(v) for v in original_vals])
                record[f"{col}_Original"] = original_str
                record[f"{col}_Summed"] = aggregated[col] if col in aggregated else None
        
        # Log averaged columns
        for col in self.config.avg_columns:
            if col in group.columns and col in agg_dict:
                original_vals = group[col].tolist()
                original_str = "; ".join([f"{v:.2f}" if isinstance(v, (int, float)) else str(v) for v in original_vals])
                record[f"{col}_Original"] = original_str
                record[f"{col}_Averaged"] = aggregated[col] if col in aggregated else None
        
        # Log other differences
        other_cols = [c for c in group.columns if c not in [group_key] + self.config.sum_columns + self.config.avg_columns]
        for col in other_cols:
            unique_vals = group[col].dropna().unique()
            if len(unique_vals) > 1:
                record[f"{col}_Values"] = "; ".join(unique_vals.astype(str))
        
        return record
    
    @log_performance
    def deduplicate(self, df: pd.DataFrame, 
                    key_column: str,
                    standardize_destinations: bool = True) -> DeduplicationResult:
        """
        Deduplicate dataframe based on key column.
        
        Args:
            df: Input dataframe
            key_column: Column to use as unique key (e.g., "Trip No")
            standardize_destinations: Whether to standardize destination names
            
        Returns:
            DeduplicationResult with deduplicated dataframe and audit trail
        """
        stats = {
            "original_rows": len(df),
            "duplicate_groups": 0,
            "rows_removed": 0,
            "deduplicated_rows": 0
        }
        
        if df.empty or key_column not in df.columns:
            return DeduplicationResult(
                deduplicated_df=df,
                audit_df=pd.DataFrame(),
                stats=stats
            )
        
        df = df.copy()
        
        # Standardize destinations if enabled
        if standardize_destinations and "Destination" in df.columns:
            normalizer = DestinationNormalizer(threshold=self.config.fuzzy_match_threshold)
            df["Destination"] = normalizer.normalize_column(df, "Destination")
        
        # Clean the key column
        df[key_column] = df[key_column].astype(str).str.strip()
        df[key_column] = df[key_column].str.replace(r'\.0$', '', regex=True)
        
        # Find duplicates
        duplicate_mask = df.duplicated(subset=[key_column], keep=False)
        unique_df = df[~duplicate_mask].copy()
        dup_df = df[duplicate_mask].copy()
        
        if dup_df.empty:
            return DeduplicationResult(
                deduplicated_df=df,
                audit_df=pd.DataFrame(),
                stats={**stats, "deduplicated_rows": len(df)}
            )
        
        # Create aggregation dictionary
        agg_dict = self._create_aggregation_dict(df, key_column)
        stats["duplicate_groups"] = dup_df[key_column].nunique()
        
        # Perform aggregation
        audit_records = []
        aggregated_rows = []
        
        for group_key, group in dup_df.groupby(key_column):
            # Aggregate the group
            aggregated = {}
            for col, strategy in agg_dict.items():
                aggregated[col] = self._aggregate_group(group, col, strategy)
            
            aggregated[key_column] = group_key
            aggregated_rows.append(aggregated)
            
            # Create audit record
            audit_records.append(self._create_audit_record(group_key, group, aggregated, agg_dict))
        
        # Create merged dataframe
        merged_df = pd.DataFrame(aggregated_rows)
        
        # Ensure all columns from original are present
        for col in df.columns:
            if col not in merged_df.columns:
                merged_df[col] = None
        
        # Combine unique and merged
        final_df = pd.concat([unique_df, merged_df], ignore_index=True)
        
        # Create audit dataframe
        audit_df = pd.DataFrame(audit_records) if audit_records else pd.DataFrame()
        
        stats.update({
            "rows_removed": stats["original_rows"] - len(final_df),
            "deduplicated_rows": len(final_df)
        })
        
        logger.info(f"Deduplication complete: {stats['original_rows']} -> {stats['deduplicated_rows']} rows "
                   f"({stats['duplicate_groups']} duplicate groups merged)")
        
        return DeduplicationResult(
            deduplicated_df=final_df,
            audit_df=audit_df,
            stats=stats
        )


class DataQualityChecker:
    """Check data quality after deduplication."""
    
    @staticmethod
    def validate_deduplication(original: pd.DataFrame, 
                               deduplicated: pd.DataFrame,
                               key_column: str) -> Dict[str, Any]:
        """Validate that deduplication was correct."""
        
        results = {
            "is_valid": True,
            "issues": [],
            "warnings": []
        }
        
        # Check that no duplicates remain
        remaining_dups = deduplicated.duplicated(subset=[key_column]).sum()
        if remaining_dups > 0:
            results["is_valid"] = False
            results["issues"].append(f"Still have {remaining_dups} duplicate {key_column}(s) after deduplication")
        
        # Check that original keys are preserved
        original_keys = set(original[key_column].astype(str).unique())
        dedup_keys = set(deduplicated[key_column].astype(str).unique())
        
        if original_keys != dedup_keys:
            missing = original_keys - dedup_keys
            if missing:
                results["warnings"].append(f"Missing {len(missing)} original keys after deduplication")
        
        return results
