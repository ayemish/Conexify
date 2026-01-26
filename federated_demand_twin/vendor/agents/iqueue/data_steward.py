"""
Data Steward / Quality Agents

Responsibilities:
- Validate incoming streams (spend, price, promo, distribution, competitor signals)
- Detect schema changes, outliers, missingness, and drift
- Produce "data confidence" scores gating downstream decisions

Business value: prevents silent model degradation and enables automation.
"""

import numpy as np
from scipy import stats
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from enum import Enum
import logging

from .base import (
    BaseIQueueAgent, AgentConfig, AgentType, BeliefState,
    AgentMessage, MessageType, ConfidenceLevel, AgentMessageBus
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataQualityDimension(str, Enum):
    """Dimensions of data quality"""
    COMPLETENESS = "completeness"
    ACCURACY = "accuracy"
    CONSISTENCY = "consistency"
    TIMELINESS = "timeliness"
    VALIDITY = "validity"
    UNIQUENESS = "uniqueness"


class DriftType(str, Enum):
    """Types of data drift"""
    SCHEMA = "schema"
    DISTRIBUTION = "distribution"
    VOLUME = "volume"
    CONCEPT = "concept"


@dataclass
class DataQualityReport:
    """Report from data quality validation"""
    stream_id: str
    timestamp: datetime
    
    # Overall scores
    overall_confidence: float
    quality_scores: Dict[str, float]
    
    # Issues detected
    schema_changes: List[Dict[str, Any]]
    outliers: List[Dict[str, Any]]
    missing_values: Dict[str, float]  # column -> pct missing
    drift_detected: List[Dict[str, Any]]
    
    # Recommendations
    is_usable: bool
    gate_downstream: bool
    recommendations: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'stream_id': self.stream_id,
            'timestamp': self.timestamp.isoformat(),
            'overall_confidence': self.overall_confidence,
            'quality_scores': self.quality_scores,
            'schema_changes': self.schema_changes,
            'outliers_count': len(self.outliers),
            'missing_values': self.missing_values,
            'drift_detected': self.drift_detected,
            'is_usable': self.is_usable,
            'gate_downstream': self.gate_downstream,
            'recommendations': self.recommendations
        }


@dataclass
class StreamProfile:
    """Statistical profile of a data stream"""
    stream_id: str
    last_schema: Dict[str, str]  # column -> dtype
    column_stats: Dict[str, Dict[str, float]]  # column -> {mean, std, min, max, etc.}
    expected_volume: float
    volume_std: float
    last_update: datetime
    
    # Historical for drift detection
    distribution_history: Dict[str, List[Tuple[datetime, float]]] = field(default_factory=dict)


class DataStewardAgent(BaseIQueueAgent):
    """
    Data Steward Agent for validating and scoring data quality.
    
    Validates:
    - Spend data streams
    - Price data streams
    - Promo data streams
    - Distribution data streams
    - Competitor signal streams
    
    Produces data confidence scores that gate downstream processing.
    """
    
    def __init__(
        self,
        config: AgentConfig,
        message_bus: Optional[AgentMessageBus] = None,
        stream_ids: Optional[List[str]] = None
    ):
        # Store stream IDs before calling parent init
        self.stream_ids = stream_ids or ['spend', 'price', 'promo', 'distribution', 'competitor']
        self.stream_profiles: Dict[str, StreamProfile] = {}
        self.quality_history: Dict[str, List[DataQualityReport]] = {}
        
        super().__init__(config, message_bus)
    
    def _initialize_beliefs(self):
        """Initialize beliefs about data quality"""
        for stream_id in self.stream_ids:
            # Belief about stream reliability
            self.beliefs[f'{stream_id}_reliability'] = BeliefState(
                name=f'{stream_id}_reliability',
                mean=0.9,
                variance=0.01,
                confidence=0.5,
                source='prior'
            )
            
            # Belief about expected volume
            self.beliefs[f'{stream_id}_volume'] = BeliefState(
                name=f'{stream_id}_volume',
                mean=1000.0,
                variance=10000.0,
                confidence=0.3,
                source='prior'
            )
    
    def _subscribe_to_messages(self):
        """Subscribe to data-related messages"""
        pass  # Data steward is primarily a producer, not consumer
    
    def _get_goal(self) -> str:
        return (
            "Validate all incoming data streams for quality, consistency, and reliability. "
            "Detect schema changes, outliers, missing values, and distribution drift. "
            "Produce data confidence scores that gate downstream model decisions."
        )
    
    def _get_backstory(self) -> str:
        return (
            "You are a meticulous data quality expert with deep experience in retail analytics. "
            "You understand that poor data quality silently degrades model performance. "
            "Your validation prevents automation failures and maintains system reliability. "
            f"You monitor streams: {', '.join(self.stream_ids)} for retailer {self.config.retailer_id}."
        )
    
    def process(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main processing: validate incoming data streams.
        
        Args:
            inputs: Dict containing data streams to validate
                - stream_id: stream identifier
                - data: DataFrame or dict of data
                - expected_schema: Optional expected schema
                
        Returns:
            Dict with validation results and confidence scores
        """
        stream_id = inputs.get('stream_id', 'unknown')
        data = inputs.get('data', {})
        expected_schema = inputs.get('expected_schema')
        
        # Validate the stream
        report = self.validate_stream(stream_id, data, expected_schema)
        
        # Update beliefs based on validation
        self._update_beliefs_from_report(stream_id, report)
        
        # Store history
        if stream_id not in self.quality_history:
            self.quality_history[stream_id] = []
        self.quality_history[stream_id].append(report)
        
        # Publish quality report
        self._publish_quality_report(report)
        
        self.last_update = datetime.utcnow()
        self.update_count += 1
        
        return {
            'stream_id': stream_id,
            'report': report.to_dict(),
            'confidence': report.overall_confidence,
            'is_usable': report.is_usable
        }
    
    def validate_stream(
        self,
        stream_id: str,
        data: Any,
        expected_schema: Optional[Dict[str, str]] = None
    ) -> DataQualityReport:
        """
        Validate a data stream and produce quality report.
        """
        timestamp = datetime.utcnow()
        
        # Convert to dict/list format for analysis
        if hasattr(data, 'to_dict'):
            data_dict = data.to_dict('records')
            columns = list(data.columns)
        elif isinstance(data, dict):
            data_dict = [data] if not isinstance(data.get(list(data.keys())[0] if data else 'x'), list) else data
            columns = list(data.keys()) if data else []
        elif isinstance(data, list):
            data_dict = data
            columns = list(data[0].keys()) if data else []
        else:
            data_dict = []
            columns = []
        
        # Schema validation
        schema_changes = self._detect_schema_changes(stream_id, columns, expected_schema)
        
        # Missing value analysis
        missing_values = self._analyze_missing_values(data_dict, columns)
        
        # Outlier detection
        outliers = self._detect_outliers(data_dict, columns)
        
        # Drift detection
        drift_detected = self._detect_drift(stream_id, data_dict, columns)
        
        # Compute quality scores
        quality_scores = self._compute_quality_scores(
            data_dict, columns, schema_changes, missing_values, outliers, drift_detected
        )
        
        # Overall confidence
        overall_confidence = self._compute_overall_confidence(quality_scores)
        
        # Determine usability
        is_usable = overall_confidence >= self.config.confidence_threshold
        gate_downstream = overall_confidence < self.config.alert_threshold
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            schema_changes, missing_values, outliers, drift_detected
        )
        
        return DataQualityReport(
            stream_id=stream_id,
            timestamp=timestamp,
            overall_confidence=overall_confidence,
            quality_scores=quality_scores,
            schema_changes=schema_changes,
            outliers=outliers,
            missing_values=missing_values,
            drift_detected=drift_detected,
            is_usable=is_usable,
            gate_downstream=gate_downstream,
            recommendations=recommendations
        )
    
    def _detect_schema_changes(
        self,
        stream_id: str,
        current_columns: List[str],
        expected_schema: Optional[Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """Detect schema changes from expected or historical schema"""
        changes = []
        
        if expected_schema:
            expected_cols = set(expected_schema.keys())
            current_cols = set(current_columns)
            
            # Missing columns
            for col in expected_cols - current_cols:
                changes.append({
                    'type': 'missing_column',
                    'column': col,
                    'severity': 'high'
                })
            
            # New columns
            for col in current_cols - expected_cols:
                changes.append({
                    'type': 'new_column',
                    'column': col,
                    'severity': 'low'
                })
        
        # Check against historical profile
        if stream_id in self.stream_profiles:
            profile = self.stream_profiles[stream_id]
            historical_cols = set(profile.last_schema.keys())
            current_cols = set(current_columns)
            
            for col in historical_cols - current_cols:
                if not any(c['column'] == col for c in changes):
                    changes.append({
                        'type': 'missing_column_vs_history',
                        'column': col,
                        'severity': 'medium'
                    })
        
        return changes
    
    def _analyze_missing_values(
        self,
        data: List[Dict],
        columns: List[str]
    ) -> Dict[str, float]:
        """Analyze missing values per column"""
        if not data:
            return {}
        
        missing_pct = {}
        n_rows = len(data)
        
        for col in columns:
            missing = sum(1 for row in data if row.get(col) is None or 
                         (isinstance(row.get(col), float) and np.isnan(row.get(col))))
            missing_pct[col] = missing / n_rows if n_rows > 0 else 0.0
        
        return missing_pct
    
    def _detect_outliers(
        self,
        data: List[Dict],
        columns: List[str],
        z_threshold: float = 3.0
    ) -> List[Dict[str, Any]]:
        """Detect outliers using z-score method"""
        outliers = []
        
        if not data:
            return outliers
        
        for col in columns:
            # Extract numeric values
            values = []
            for i, row in enumerate(data):
                val = row.get(col)
                if val is not None and isinstance(val, (int, float)) and not np.isnan(val):
                    values.append((i, val))
            
            if len(values) < 10:
                continue
            
            vals = [v for _, v in values]
            mean = np.mean(vals)
            std = np.std(vals)
            
            if std < 1e-8:
                continue
            
            for idx, val in values:
                z = abs(val - mean) / std
                if z > z_threshold:
                    outliers.append({
                        'column': col,
                        'row_index': idx,
                        'value': val,
                        'z_score': z,
                        'severity': 'high' if z > 4 else 'medium'
                    })
        
        return outliers[:100]  # Limit outliers reported
    
    def _detect_drift(
        self,
        stream_id: str,
        data: List[Dict],
        columns: List[str]
    ) -> List[Dict[str, Any]]:
        """Detect distribution drift from historical profile"""
        drift = []
        
        if stream_id not in self.stream_profiles or not data:
            return drift
        
        profile = self.stream_profiles[stream_id]
        
        for col in columns:
            if col not in profile.column_stats:
                continue
            
            hist_stats = profile.column_stats[col]
            
            # Extract current values
            values = [row.get(col) for row in data 
                     if row.get(col) is not None and isinstance(row.get(col), (int, float))]
            
            if len(values) < 10:
                continue
            
            current_mean = np.mean(values)
            current_std = np.std(values)
            
            # Compare means
            hist_mean = hist_stats.get('mean', current_mean)
            hist_std = hist_stats.get('std', current_std)
            
            if hist_std > 0:
                mean_shift = abs(current_mean - hist_mean) / hist_std
                if mean_shift > 2.0:
                    drift.append({
                        'type': DriftType.DISTRIBUTION.value,
                        'column': col,
                        'metric': 'mean',
                        'historical': hist_mean,
                        'current': current_mean,
                        'shift_magnitude': mean_shift,
                        'severity': 'high' if mean_shift > 3 else 'medium'
                    })
            
            # Compare variance
            if hist_std > 0:
                var_ratio = current_std / hist_std
                if var_ratio > 2.0 or var_ratio < 0.5:
                    drift.append({
                        'type': DriftType.DISTRIBUTION.value,
                        'column': col,
                        'metric': 'variance',
                        'historical': hist_std,
                        'current': current_std,
                        'ratio': var_ratio,
                        'severity': 'medium'
                    })
        
        # Volume drift
        current_volume = len(data)
        expected_volume = profile.expected_volume
        volume_std = profile.volume_std
        
        if volume_std > 0:
            volume_shift = abs(current_volume - expected_volume) / volume_std
            if volume_shift > 2.0:
                drift.append({
                    'type': DriftType.VOLUME.value,
                    'expected': expected_volume,
                    'current': current_volume,
                    'shift_magnitude': volume_shift,
                    'severity': 'high' if volume_shift > 3 else 'medium'
                })
        
        return drift
    
    def _compute_quality_scores(
        self,
        data: List[Dict],
        columns: List[str],
        schema_changes: List,
        missing_values: Dict[str, float],
        outliers: List,
        drift: List
    ) -> Dict[str, float]:
        """Compute quality scores for each dimension"""
        scores = {}
        
        # Completeness: based on missing values
        if missing_values:
            avg_missing = np.mean(list(missing_values.values()))
            scores['completeness'] = 1.0 - avg_missing
        else:
            scores['completeness'] = 1.0
        
        # Consistency: based on schema changes
        schema_penalty = len([c for c in schema_changes if c['severity'] == 'high']) * 0.2
        schema_penalty += len([c for c in schema_changes if c['severity'] == 'medium']) * 0.1
        scores['consistency'] = max(0, 1.0 - schema_penalty)
        
        # Validity: based on outliers
        if data:
            outlier_rate = len(outliers) / len(data)
            scores['validity'] = max(0, 1.0 - outlier_rate * 10)
        else:
            scores['validity'] = 0.5
        
        # Timeliness: assume current data is timely
        scores['timeliness'] = 1.0
        
        # Stability: based on drift
        drift_penalty = len([d for d in drift if d['severity'] == 'high']) * 0.15
        drift_penalty += len([d for d in drift if d['severity'] == 'medium']) * 0.08
        scores['stability'] = max(0, 1.0 - drift_penalty)
        
        return scores
    
    def _compute_overall_confidence(self, quality_scores: Dict[str, float]) -> float:
        """Compute overall confidence from dimension scores"""
        if not quality_scores:
            return 0.5
        
        # Weighted average with emphasis on completeness and consistency
        weights = {
            'completeness': 0.25,
            'consistency': 0.25,
            'validity': 0.20,
            'timeliness': 0.10,
            'stability': 0.20
        }
        
        weighted_sum = sum(
            quality_scores.get(dim, 0.5) * weight
            for dim, weight in weights.items()
        )
        
        return weighted_sum
    
    def _generate_recommendations(
        self,
        schema_changes: List,
        missing_values: Dict[str, float],
        outliers: List,
        drift: List
    ) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []
        
        # Schema recommendations
        missing_cols = [c['column'] for c in schema_changes if c['type'] == 'missing_column']
        if missing_cols:
            recommendations.append(
                f"Critical: Missing columns detected: {', '.join(missing_cols[:5])}. "
                "Verify data source configuration."
            )
        
        # Missing value recommendations
        high_missing = [col for col, pct in missing_values.items() if pct > 0.1]
        if high_missing:
            recommendations.append(
                f"Warning: High missing rate (>10%) in columns: {', '.join(high_missing[:5])}. "
                "Consider imputation or source investigation."
            )
        
        # Outlier recommendations
        if len(outliers) > 20:
            recommendations.append(
                f"Warning: {len(outliers)} outliers detected. "
                "Review for data entry errors or genuine anomalies."
            )
        
        # Drift recommendations
        high_drift = [d for d in drift if d['severity'] == 'high']
        if high_drift:
            recommendations.append(
                f"Alert: Significant distribution drift detected in {len(high_drift)} metrics. "
                "Investigate for concept drift or upstream changes."
            )
        
        if not recommendations:
            recommendations.append("Data quality checks passed. No action required.")
        
        return recommendations
    
    def _update_beliefs_from_report(self, stream_id: str, report: DataQualityReport):
        """Update agent beliefs based on quality report"""
        reliability_key = f'{stream_id}_reliability'
        if reliability_key in self.beliefs:
            self.update_belief(
                reliability_key,
                report.overall_confidence,
                0.01  # Low variance for direct observation
            )
    
    def _publish_quality_report(self, report: DataQualityReport):
        """Publish quality report to message bus"""
        self.message_bus.publish(AgentMessage(
            message_id=self._generate_id(),
            message_type=MessageType.DATA_QUALITY,
            sender_id=self.config.agent_id,
            recipient_id=None,
            payload=report.to_dict(),
            priority=1 if report.gate_downstream else 0
        ))
    
    def update_profile(self, stream_id: str, data: List[Dict], columns: List[str]):
        """Update the statistical profile for a stream"""
        column_stats = {}
        
        for col in columns:
            values = [row.get(col) for row in data 
                     if row.get(col) is not None and isinstance(row.get(col), (int, float))]
            
            if values:
                column_stats[col] = {
                    'mean': float(np.mean(values)),
                    'std': float(np.std(values)),
                    'min': float(np.min(values)),
                    'max': float(np.max(values)),
                    'median': float(np.median(values))
                }
        
        self.stream_profiles[stream_id] = StreamProfile(
            stream_id=stream_id,
            last_schema={col: 'inferred' for col in columns},
            column_stats=column_stats,
            expected_volume=float(len(data)),
            volume_std=float(len(data) * 0.2),  # Assume 20% variance initially
            last_update=datetime.utcnow()
        )
    
    def get_data_confidence_scores(self) -> Dict[str, float]:
        """Get current confidence scores for all streams"""
        return {
            stream_id: self.beliefs.get(f'{stream_id}_reliability', BeliefState(
                name='default', mean=0.5, variance=0.1, confidence=0.5
            )).mean
            for stream_id in self.stream_ids
        }


def create_data_steward_agent(
    retailer_id: str,
    segment_id: Optional[str] = None,
    stream_ids: Optional[List[str]] = None,
    message_bus: Optional[AgentMessageBus] = None
) -> DataStewardAgent:
    """Factory function for creating Data Steward Agent"""
    config = AgentConfig(
        agent_id=f"data_steward_{retailer_id}_{segment_id or 'all'}",
        agent_type=AgentType.DATA_STEWARD,
        retailer_id=retailer_id,
        segment_id=segment_id,
        confidence_threshold=0.7,
        alert_threshold=0.5
    )
    
    return DataStewardAgent(config, message_bus, stream_ids)
