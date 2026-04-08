"""Feature store for managing and caching features."""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from trading_bot.config import get_logger

logger = get_logger(__name__)


class FeatureStore:
    """Feature store for managing engineered features."""
    
    def __init__(self, base_path: Path):
        """Initialize feature store.
        
        Args:
            base_path: Base directory for feature storage
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.metadata_path = self.base_path / "metadata.json"
        self._metadata: Dict = self._load_metadata()
    
    def _load_metadata(self) -> Dict:
        """Load feature store metadata."""
        if self.metadata_path.exists():
            with open(self.metadata_path, "r") as f:
                return json.load(f)
        return {"datasets": {}}
    
    def _save_metadata(self) -> None:
        """Save feature store metadata."""
        with open(self.metadata_path, "w") as f:
            json.dump(self._metadata, f, indent=2, default=str)
    
    def _compute_hash(self, df: pd.DataFrame) -> str:
        """Compute hash of dataframe for versioning."""
        # Use first and last few rows + shape for hash
        sample = pd.concat([df.head(5), df.tail(5)])
        hash_str = f"{df.shape}_{sample.to_json()}"
        return hashlib.md5(hash_str.encode()).hexdigest()[:16]
    
    def _get_feature_path(self, symbol: str, timeframe: str, version: str) -> Path:
        """Get path for feature file."""
        clean_symbol = symbol.replace("/", "_")
        return self.base_path / f"{clean_symbol}_{timeframe}_{version}.parquet"
    
    def save_features(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        feature_names: List[str],
        tags: Optional[Dict] = None,
    ) -> str:
        """Save features to store.
        
        Args:
            df: DataFrame with features
            symbol: Trading symbol
            timeframe: Data timeframe
            feature_names: List of feature column names
            tags: Optional metadata tags
            
        Returns:
            Feature set version string
        """
        version = self._compute_hash(df)
        file_path = self._get_feature_path(symbol, timeframe, version)
        
        # Save to parquet
        table = pa.Table.from_pandas(df)
        pq.write_table(table, file_path)
        
        # Update metadata
        key = f"{symbol}_{timeframe}"
        self._metadata["datasets"][key] = {
            "version": version,
            "symbol": symbol,
            "timeframe": timeframe,
            "created_at": datetime.now().isoformat(),
            "rows": len(df),
            "columns": len(df.columns),
            "feature_names": feature_names,
            "file_path": str(file_path),
            "tags": tags or {},
        }
        
        self._save_metadata()
        
        logger.info(
            "Features saved to store",
            symbol=symbol,
            timeframe=timeframe,
            version=version,
            features=len(feature_names),
        )
        
        return version
    
    def load_features(
        self,
        symbol: str,
        timeframe: str,
        version: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        """Load features from store.
        
        Args:
            symbol: Trading symbol
            timeframe: Data timeframe
            version: Specific version (None = latest)
            
        Returns:
            DataFrame with features or None
        """
        key = f"{symbol}_{timeframe}"
        
        if key not in self._metadata["datasets"]:
            logger.warning("Features not found in store", key=key)
            return None
        
        dataset_info = self._metadata["datasets"][key]
        
        if version is None:
            version = dataset_info["version"]
        
        file_path = Path(dataset_info["file_path"])
        
        if not file_path.exists():
            logger.error("Feature file not found", path=str(file_path))
            return None
        
        try:
            df = pq.read_table(file_path).to_pandas()
            df.index = pd.to_datetime(df.index)
            
            logger.info(
                "Features loaded from store",
                symbol=symbol,
                timeframe=timeframe,
                version=version,
                rows=len(df),
            )
            
            return df
            
        except Exception as e:
            logger.error("Failed to load features", error=str(e))
            return None
    
    def get_feature_metadata(
        self,
        symbol: str,
        timeframe: str,
    ) -> Optional[Dict]:
        """Get metadata for feature set.
        
        Args:
            symbol: Trading symbol
            timeframe: Data timeframe
            
        Returns:
            Metadata dictionary or None
        """
        key = f"{symbol}_{timeframe}"
        return self._metadata["datasets"].get(key)
    
    def list_feature_sets(self) -> List[Dict]:
        """List all available feature sets.
        
        Returns:
            List of feature set metadata
        """
        return list(self._metadata["datasets"].values())
    
    def delete_feature_set(self, symbol: str, timeframe: str) -> bool:
        """Delete a feature set.
        
        Args:
            symbol: Trading symbol
            timeframe: Data timeframe
            
        Returns:
            True if deleted successfully
        """
        key = f"{symbol}_{timeframe}"
        
        if key not in self._metadata["datasets"]:
            return False
        
        dataset_info = self._metadata["datasets"][key]
        file_path = Path(dataset_info["file_path"])
        
        # Delete file
        if file_path.exists():
            file_path.unlink()
        
        # Remove from metadata
        del self._metadata["datasets"][key]
        self._save_metadata()
        
        logger.info("Feature set deleted", symbol=symbol, timeframe=timeframe)
        
        return True
    
    def get_feature_statistics(self, df: pd.DataFrame, feature_names: List[str]) -> pd.DataFrame:
        """Calculate statistics for features.
        
        Args:
            df: DataFrame with features
            feature_names: List of feature columns
            
        Returns:
            Statistics DataFrame
        """
        stats = []
        
        for feature in feature_names:
            if feature not in df.columns:
                continue
            
            feature_stats = {
                "feature": feature,
                "mean": df[feature].mean(),
                "std": df[feature].std(),
                "min": df[feature].min(),
                "max": df[feature].max(),
                "median": df[feature].median(),
                "skew": df[feature].skew(),
                "kurt": df[feature].kurt(),
                "missing": df[feature].isna().sum(),
                "missing_pct": df[feature].isna().mean() * 100,
            }
            stats.append(feature_stats)
        
        return pd.DataFrame(stats)
    
    def validate_features(
        self,
        df: pd.DataFrame,
        feature_names: List[str],
        max_missing_pct: float = 5.0,
        max_inf_pct: float = 1.0,
    ) -> Dict:
        """Validate feature quality.
        
        Args:
            df: DataFrame with features
            feature_names: List of feature columns
            max_missing_pct: Maximum allowed missing percentage
            max_inf_pct: Maximum allowed infinite values percentage
            
        Returns:
            Validation results dictionary
        """
        issues = []
        
        for feature in feature_names:
            if feature not in df.columns:
                issues.append(f"Missing feature: {feature}")
                continue
            
            col = df[feature]
            
            # Check missing values
            missing_pct = col.isna().mean() * 100
            if missing_pct > max_missing_pct:
                issues.append(f"{feature}: {missing_pct:.1f}% missing values")
            
            # Check infinite values
            inf_pct = (np.isinf(col) | np.isneginf(col)).mean() * 100
            if inf_pct > max_inf_pct:
                issues.append(f"{feature}: {inf_pct:.1f}% infinite values")
            
            # Check for constant features
            if col.nunique() <= 1:
                issues.append(f"{feature}: Constant feature")
            
            # Check for extreme outliers
            if col.std() > 0:
                z_scores = (col - col.mean()) / col.std()
                outlier_pct = (abs(z_scores) > 5).mean() * 100
                if outlier_pct > 10:
                    issues.append(f"{feature}: {outlier_pct:.1f}% extreme outliers")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "num_features": len(feature_names),
            "num_issues": len(issues),
        }
