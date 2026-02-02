/**
 * Uncertainty and Calibration Types
 * 
 * Defines calibrated uncertainty quantification for decision-grade predictions.
 * Addresses FR-009, FR-011.
 */

// =============================================================================
// CALIBRATION PIPELINE
// =============================================================================

export type CalibrationMethod = 
  | 'platt_scaling' 
  | 'isotonic_regression' 
  | 'temperature_scaling'
  | 'beta_calibration'
  | 'conformal_prediction';

export interface CalibrationConfig {
  config_id: string;
  model_id: string;
  model_version: string;
  
  // Method
  method: CalibrationMethod;
  method_params: Record<string, number | string | boolean>;
  
  // Training data
  calibration_dataset: {
    dataset_id: string;
    n_samples: number;
    date_range: { start: string; end: string };
    stratification?: string[];
  };
  
  // Coverage targets
  coverage_targets: {
    confidence_level: number;      // e.g., 0.80 for 80%
    target_coverage: number;       // Target empirical coverage
    tolerance: number;             // Acceptable deviation
  };
  
  // Status
  status: 'active' | 'training' | 'validation' | 'deprecated';
  created_at: string;
  last_validated: string;
}

export interface CalibrationResult {
  result_id: string;
  config_id: string;
  evaluated_at: string;
  
  // Reliability metrics
  reliability_metrics: {
    expected_calibration_error: number;  // ECE
    maximum_calibration_error: number;   // MCE
    brier_score: number;
    log_loss: number;
  };
  
  // Coverage metrics (for interval predictions)
  coverage_metrics: {
    nominal_coverage: number;
    empirical_coverage: number;
    coverage_gap: number;
    average_interval_width: number;
  };
  
  // Reliability diagram data
  reliability_diagram: {
    bins: Array<{
      bin_center: number;
      predicted_probability: number;
      observed_frequency: number;
      n_samples: number;
    }>;
  };
  
  // Sharpness (narrower intervals = sharper, but must maintain coverage)
  sharpness_metrics: {
    mean_interval_width: number;
    median_interval_width: number;
    interval_width_std: number;
  };
  
  // Pass/fail
  validation_passed: boolean;
  failure_reasons?: string[];
}

// =============================================================================
// PREDICTION UNCERTAINTY
// =============================================================================

export interface UncertaintyEstimate {
  // Point estimate
  point_estimate: number;
  
  // Confidence/probability
  confidence: number;              // Calibrated probability (0-1)
  raw_score: number;               // Uncalibrated model output
  
  // Prediction intervals (for RUL, continuous predictions)
  prediction_interval?: {
    lower: number;
    upper: number;
    confidence_level: number;      // e.g., 0.80 or 0.95
  };
  
  // Uncertainty decomposition
  uncertainty_decomposition?: {
    aleatoric: number;             // Data/inherent uncertainty
    epistemic: number;             // Model uncertainty
    total: number;
  };
  
  // Calibration info
  calibration: {
    method_used: CalibrationMethod;
    calibration_date: string;
    coverage_validated: boolean;
  };
}

export interface RULPrediction {
  asset_id: string;
  prediction_time: string;
  
  // Point estimate
  rul_hours: number;
  rul_days: number;
  
  // Intervals at different confidence levels
  intervals: Array<{
    confidence_level: number;
    lower_hours: number;
    upper_hours: number;
  }>;
  
  // Risk curve (probability of failure by time)
  survival_curve: Array<{
    time_hours: number;
    survival_probability: number;
  }>;
  
  // Uncertainty quality
  uncertainty_estimate: UncertaintyEstimate;
  
  // Factors driving uncertainty
  uncertainty_drivers: Array<{
    factor: string;
    contribution: number;
    description: string;
  }>;
}

// =============================================================================
// UNCERTAINTY GATING POLICIES
// =============================================================================

export interface UncertaintyGatingPolicy {
  policy_id: string;
  policy_name: string;
  description: string;
  enabled: boolean;
  
  // Scope
  scope: {
    model_types?: string[];
    asset_criticality?: string[];
    action_types?: string[];
  };
  
  // Gating thresholds
  thresholds: {
    // For auto-dispatch
    auto_dispatch: {
      min_confidence: number;        // Only auto-dispatch if confidence >= this
      max_uncertainty: number;       // Only auto-dispatch if uncertainty <= this
      min_coverage_validated: boolean;
    };
    
    // For case creation
    case_creation: {
      min_confidence: number;
      require_interval_validation: boolean;
    };
    
    // For human review escalation
    human_review: {
      confidence_range: [number, number];  // Escalate if in this range
      uncertainty_threshold: number;        // Escalate if uncertainty >= this
    };
  };
  
  // Actions when thresholds not met
  fallback_actions: {
    low_confidence: 'suppress' | 'queue_for_review' | 'flag_uncertain';
    high_uncertainty: 'widen_interval' | 'defer_decision' | 'request_more_data';
  };
}

export interface UncertaintyGatingEvaluation {
  evaluation_id: string;
  prediction_id: string;
  policy_id: string;
  timestamp: string;
  
  // Input
  input: {
    confidence: number;
    uncertainty: number;
    interval_width?: number;
    coverage_validated: boolean;
  };
  
  // Thresholds applied
  thresholds_applied: {
    threshold_name: string;
    threshold_value: number;
    actual_value: number;
    passed: boolean;
  }[];
  
  // Outcome
  outcome: {
    action_allowed: 'auto_dispatch' | 'case_create' | 'human_review' | 'suppress';
    gating_passed: boolean;
    reason: string;
  };
}

// =============================================================================
// CALIBRATION MONITORING
// =============================================================================

export interface CalibrationDriftMonitor {
  monitor_id: string;
  model_id: string;
  
  // Monitoring config
  config: {
    window_size_days: number;
    min_samples: number;
    check_frequency_hours: number;
  };
  
  // Drift thresholds
  drift_thresholds: {
    ece_threshold: number;         // Alert if ECE exceeds this
    coverage_gap_threshold: number; // Alert if coverage gap exceeds this
    brier_score_threshold: number;
  };
  
  // Current status
  current_status: {
    last_check: string;
    current_ece: number;
    current_coverage_gap: number;
    drift_detected: boolean;
    drift_severity: 'none' | 'mild' | 'moderate' | 'severe';
  };
  
  // Historical trend
  history: Array<{
    timestamp: string;
    ece: number;
    coverage_gap: number;
    n_samples: number;
  }>;
}

// =============================================================================
// DECISION-GRADE UNCERTAINTY REPORT
// =============================================================================

export interface DecisionGradeReport {
  report_id: string;
  model_id: string;
  report_period: { start: string; end: string };
  generated_at: string;
  
  // Overall assessment
  decision_grade: 'A' | 'B' | 'C' | 'D' | 'F';
  decision_grade_explanation: string;
  
  // Calibration quality
  calibration_assessment: {
    is_well_calibrated: boolean;
    ece: number;
    coverage_met: boolean;
    reliability_score: number;
  };
  
  // Sharpness assessment
  sharpness_assessment: {
    intervals_are_informative: boolean;
    mean_width: number;
    width_vs_baseline: number;
  };
  
  // Operational impact
  operational_impact: {
    predictions_gated: number;
    predictions_auto_actioned: number;
    predictions_escalated: number;
    estimated_value_of_uncertainty: number;
  };
  
  // Recommendations
  recommendations: Array<{
    priority: 'high' | 'medium' | 'low';
    recommendation: string;
    expected_impact: string;
  }>;
}
