/**
 * Event-Based KPI Evaluation Protocol Types
 * 
 * Defines event recall, alert precision, lead-time distribution,
 * false-positive burden, and cost sensitivity analysis.
 * The "proof layer" for PdM differentiation.
 * Addresses FR-009.
 */

// =============================================================================
// EVENT LABELING
// =============================================================================

export type EventType = 'failure' | 'degradation' | 'anomaly' | 'maintenance' | 'false_alarm';
export type EventSource = 'work_order' | 'technician_report' | 'sensor_confirmed' | 'manual_label';

export interface FailureEvent {
  event_id: string;
  asset_id: string;
  site_id: string;
  
  // Event details
  event_type: EventType;
  fault_type: string;
  fault_code?: string;
  
  // Timing
  event_start: string;
  event_detected?: string;
  event_resolved?: string;
  
  // Labeling
  label_source: EventSource;
  label_confidence: number;
  labeled_by?: string;
  labeled_at: string;
  
  // Impact
  impact: {
    downtime_hours?: number;
    product_loss_value?: number;
    repair_cost?: number;
    total_cost?: number;
  };
  
  // Verification
  verified: boolean;
  verification_notes?: string;
}

export interface AlertToEventMatch {
  match_id: string;
  
  // Alert side
  alert_id: string;
  alert_fired_at: string;
  alert_type: string;
  alert_confidence: number;
  
  // Event side
  event_id?: string;
  event_start?: string;
  event_type?: EventType;
  
  // Match result
  match_result: 'true_positive' | 'false_positive' | 'false_negative' | 'unmatched';
  
  // Timing metrics
  lead_time_hours?: number;
  
  // Matching metadata
  match_method: 'time_window' | 'signature' | 'manual';
  match_confidence: number;
  match_window_hours: number;
}

// =============================================================================
// EVENT-SPACE METRICS
// =============================================================================

export interface EventSpaceMetrics {
  evaluation_id: string;
  model_id: string;
  model_version: string;
  
  period: { start: string; end: string };
  scope: {
    site_ids?: string[];
    asset_types?: string[];
    fault_types?: string[];
  };
  
  // Volume
  volume: {
    total_events: number;
    total_alerts: number;
    events_by_type: Record<EventType, number>;
  };
  
  // Core metrics
  event_recall: number;           // Events we caught / Total events
  alert_precision: number;        // True positives / Total alerts fired
  f1_score: number;
  
  // Breakdown by severity
  by_severity: Array<{
    severity: string;
    event_count: number;
    alert_count: number;
    recall: number;
    precision: number;
  }>;
  
  // Breakdown by fault type
  by_fault_type: Array<{
    fault_type: string;
    event_count: number;
    recall: number;
    precision: number;
    avg_lead_time_hours: number;
  }>;
  
  // Confusion matrix
  confusion_matrix: {
    true_positives: number;
    false_positives: number;
    false_negatives: number;
    true_negatives?: number;
  };
}

// =============================================================================
// LEAD TIME ANALYSIS
// =============================================================================

export interface LeadTimeDistribution {
  evaluation_id: string;
  model_id: string;
  
  period: { start: string; end: string };
  
  // Overall distribution
  overall: {
    mean_hours: number;
    median_hours: number;
    std_hours: number;
    min_hours: number;
    max_hours: number;
    percentiles: {
      p10: number;
      p25: number;
      p50: number;
      p75: number;
      p90: number;
    };
  };
  
  // Histogram bins
  histogram: Array<{
    bin_start_hours: number;
    bin_end_hours: number;
    count: number;
    percent: number;
  }>;
  
  // By fault type
  by_fault_type: Array<{
    fault_type: string;
    mean_hours: number;
    median_hours: number;
    target_hours: number;
    meets_target_percent: number;
  }>;
  
  // Actionability analysis
  actionability: {
    alerts_with_sufficient_lead_time: number;
    alerts_with_insufficient_lead_time: number;
    sufficient_lead_time_threshold_hours: number;
    actionable_rate: number;
  };
}

// =============================================================================
// FALSE POSITIVE BURDEN
// =============================================================================

export interface FalsePositiveBurden {
  evaluation_id: string;
  
  period: { start: string; end: string };
  scope_type: 'global' | 'site' | 'asset';
  scope_id: string;
  
  // Burden metrics
  metrics: {
    false_positives_total: number;
    false_positives_per_asset: number;
    false_positives_per_asset_month: number;
    
    operator_time_wasted_hours: number;
    unnecessary_dispatches: number;
    unnecessary_dispatch_cost: number;
    
    trust_erosion_score: number;  // 0-100, higher = more erosion risk
  };
  
  // By asset
  by_asset: Array<{
    asset_id: string;
    asset_name: string;
    false_positive_count: number;
    fp_per_month: number;
    is_problem_asset: boolean;
  }>;
  
  // By alert type
  by_alert_type: Array<{
    alert_type: string;
    false_positive_count: number;
    false_positive_rate: number;
    improvement_potential: 'high' | 'medium' | 'low';
  }>;
  
  // Trends
  trend: {
    direction: 'improving' | 'stable' | 'worsening';
    change_vs_prior_period: number;
  };
  
  // Recommendations
  recommendations: Array<{
    priority: 'high' | 'medium' | 'low';
    recommendation: string;
    expected_reduction: number;
  }>;
}

// =============================================================================
// COST CURVES & SENSITIVITY ANALYSIS
// =============================================================================

export interface CostCurveAnalysis {
  analysis_id: string;
  model_id: string;
  
  period: { start: string; end: string };
  
  // Cost parameters used
  cost_parameters: {
    truck_roll_cost: number;
    downtime_cost_per_hour: number;
    product_loss_cost_avg: number;
    false_positive_cost: number;
    false_negative_cost: number;
  };
  
  // Threshold sweep
  threshold_sweep: Array<{
    threshold: number;
    precision: number;
    recall: number;
    f1: number;
    total_cost: number;
    cost_breakdown: {
      fp_cost: number;
      fn_cost: number;
      intervention_cost: number;
    };
  }>;
  
  // Optimal thresholds
  optimal_thresholds: {
    min_cost_threshold: number;
    min_cost_value: number;
    
    target_recall_threshold: number;
    target_recall_value: number;
    cost_at_target_recall: number;
    
    target_precision_threshold: number;
    target_precision_value: number;
    cost_at_target_precision: number;
  };
  
  // ROC/PR curves
  roc_curve: Array<{ fpr: number; tpr: number; threshold: number }>;
  pr_curve: Array<{ precision: number; recall: number; threshold: number }>;
  
  // AUC metrics
  auc_roc: number;
  auc_pr: number;
}

export interface CostSensitivityAnalysis {
  analysis_id: string;
  model_id: string;
  
  // Base case
  base_case: {
    cost_parameters: Record<string, number>;
    optimal_threshold: number;
    expected_cost: number;
  };
  
  // Sensitivity scenarios
  scenarios: Array<{
    scenario_name: string;
    parameter_changed: string;
    parameter_values: number[];
    
    results: Array<{
      parameter_value: number;
      optimal_threshold: number;
      expected_cost: number;
      cost_change_vs_base: number;
    }>;
    
    sensitivity: 'high' | 'medium' | 'low';
  }>;
  
  // Key insights
  insights: Array<{
    insight: string;
    implication: string;
    recommendation: string;
  }>;
}

// =============================================================================
// EVALUATION DASHBOARD
// =============================================================================

export interface EvaluationDashboard {
  dashboard_id: string;
  generated_at: string;
  
  period: { start: string; end: string };
  
  // Summary cards
  summary: {
    overall_grade: 'A' | 'B' | 'C' | 'D' | 'F';
    event_recall: number;
    alert_precision: number;
    avg_lead_time_hours: number;
    fp_per_asset_month: number;
    estimated_value_delivered: number;
  };
  
  // Trend sparklines
  trends: {
    recall_7d: number[];
    precision_7d: number[];
    lead_time_7d: number[];
    fp_burden_7d: number[];
  };
  
  // Top issues
  top_issues: Array<{
    issue_type: 'low_recall' | 'high_fp' | 'short_lead_time' | 'calibration_drift';
    description: string;
    impact: string;
    suggested_action: string;
  }>;
  
  // Model comparison (if A/B testing)
  model_comparison?: {
    models: Array<{
      model_id: string;
      model_name: string;
      recall: number;
      precision: number;
      lead_time: number;
      cost: number;
    }>;
    winner?: string;
    statistical_significance: boolean;
  };
}

// =============================================================================
// PROOF REPORTING
// =============================================================================

export interface ProofReport {
  report_id: string;
  report_type: 'weekly' | 'monthly' | 'quarterly' | 'annual';
  
  period: { start: string; end: string };
  
  // Executive summary
  executive_summary: {
    headline: string;
    key_achievements: string[];
    areas_for_improvement: string[];
    value_delivered: number;
  };
  
  // Detailed metrics
  metrics: {
    event_space: EventSpaceMetrics;
    lead_time: LeadTimeDistribution;
    fp_burden: FalsePositiveBurden;
    cost_analysis: CostCurveAnalysis;
  };
  
  // Comparisons
  comparisons: {
    vs_prior_period: {
      recall_change: number;
      precision_change: number;
      cost_change: number;
    };
    vs_baseline: {
      baseline_description: string;
      improvement_percent: number;
    };
    vs_target: {
      recall_vs_target: number;
      precision_vs_target: number;
      on_track: boolean;
    };
  };
  
  // Recommendations
  recommendations: Array<{
    priority: 'high' | 'medium' | 'low';
    category: 'model' | 'threshold' | 'data' | 'process';
    recommendation: string;
    expected_impact: string;
    effort: 'low' | 'medium' | 'high';
  }>;
  
  // Appendix
  appendix: {
    methodology_notes: string;
    data_quality_notes: string;
    exclusions: string[];
  };
}
