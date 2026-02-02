/**
 * Resolution Verification + Auto-Reopen Types
 * 
 * Defines telemetry-based verification that issues are actually resolved
 * post-service, with automatic reopening if they aren't.
 * Addresses FR-016.
 */

// =============================================================================
// VERIFICATION CONFIGURATION
// =============================================================================

export interface VerificationConfig {
  config_id: string;
  fault_type: string;
  fault_category: string;
  
  // Verification window
  window: {
    start_delay_hours: number;      // Wait before starting verification
    duration_hours: number;          // How long to monitor
    min_data_points: number;         // Minimum readings required
  };
  
  // Pass criteria
  pass_criteria: {
    type: 'threshold' | 'baseline_return' | 'stability' | 'composite';
    
    // Threshold-based
    threshold_criteria?: {
      metric_id: string;
      operator: 'lt' | 'lte' | 'gt' | 'gte' | 'between';
      value: number;
      value_upper?: number;
    }[];
    
    // Baseline return
    baseline_criteria?: {
      metric_id: string;
      baseline_reference: 'pre_fault' | 'historical_avg' | 'design_spec';
      tolerance_percent: number;
    }[];
    
    // Stability (no recurring anomalies)
    stability_criteria?: {
      max_anomaly_count: number;
      max_deviation_from_mean: number;
      require_trend_stable: boolean;
    };
  };
  
  // Fail actions
  fail_actions: {
    auto_reopen: boolean;
    reopen_severity: 'same' | 'escalate';
    notify_roles: string[];
    add_notes: boolean;
  };
  
  // Metadata
  created_at: string;
  updated_at: string;
  version: number;
}

// =============================================================================
// VERIFICATION EXECUTION
// =============================================================================

export interface VerificationJob {
  job_id: string;
  case_id: string;
  work_order_id: string;
  asset_id: string;
  
  // Configuration
  config_id: string;
  fault_type: string;
  
  // Timing
  service_completed_at: string;
  verification_start: string;
  verification_end: string;
  
  // Status
  status: 'pending' | 'in_progress' | 'passed' | 'failed' | 'inconclusive' | 'cancelled';
  
  // Progress
  progress: {
    data_points_collected: number;
    data_points_required: number;
    time_elapsed_hours: number;
    time_required_hours: number;
  };
  
  // Intermediate results
  intermediate_results?: {
    timestamp: string;
    metrics_status: Array<{
      metric_id: string;
      current_value: number;
      target_value: number;
      status: 'passing' | 'failing' | 'pending';
    }>;
    overall_trend: 'improving' | 'stable' | 'degrading';
  };
}

export interface VerificationResult {
  result_id: string;
  job_id: string;
  case_id: string;
  
  // Outcome
  outcome: 'verified' | 'failed' | 'inconclusive';
  outcome_reason: string;
  
  // Detailed results
  criteria_results: Array<{
    criterion_type: string;
    criterion_description: string;
    passed: boolean;
    actual_value: number | string;
    expected_value: number | string;
    evidence: {
      metric_id: string;
      readings: Array<{ timestamp: string; value: number }>;
    };
  }>;
  
  // Comparison to baseline
  baseline_comparison?: {
    pre_fault_baseline: Record<string, number>;
    post_fix_values: Record<string, number>;
    percent_recovery: Record<string, number>;
  };
  
  // Timestamps
  verified_at: string;
  
  // Actions taken
  actions_taken: {
    case_auto_closed: boolean;
    case_reopened: boolean;
    notifications_sent: string[];
    escalation_triggered: boolean;
  };
}

// =============================================================================
// AUTO-REOPEN LOGIC
// =============================================================================

export interface ReopenTrigger {
  trigger_id: string;
  original_case_id: string;
  
  // Trigger source
  source: 'verification_failed' | 'symptom_recurrence' | 'related_fault' | 'manual';
  
  // Detection details
  detection: {
    detected_at: string;
    detection_method: string;
    confidence: number;
    
    // For symptom recurrence
    symptom_match?: {
      original_signature: string;
      current_signature: string;
      similarity_score: number;
    };
    
    // For verification failure
    verification_failure?: {
      job_id: string;
      failed_criteria: string[];
    };
  };
  
  // Reopen decision
  decision: {
    auto_reopened: boolean;
    decision_reason: string;
    human_review_required: boolean;
    reviewed_by?: string;
    review_decision?: 'confirm_reopen' | 'dismiss' | 'new_case';
  };
  
  // New case details (if reopened)
  reopened_case?: {
    new_case_id: string;
    linked_to_original: boolean;
    severity: string;
    priority: string;
    notes: string;
  };
}

export interface RecurrenceDetectionConfig {
  config_id: string;
  fault_type: string;
  
  // Detection window
  monitoring_window: {
    days_after_close: number;
    continuous_monitoring: boolean;
  };
  
  // Recurrence criteria
  recurrence_criteria: {
    symptom_similarity_threshold: number;  // 0-1
    same_root_cause_required: boolean;
    min_time_between_occurrences_hours: number;
  };
  
  // Actions
  actions: {
    auto_reopen_threshold: number;  // Similarity score above which to auto-reopen
    create_new_case_threshold: number;  // Below this, create new case instead
    escalate_on_multiple_recurrences: boolean;
    max_recurrences_before_escalation: number;
  };
}

// =============================================================================
// VERIFICATION METRICS
// =============================================================================

export interface VerificationMetrics {
  period: { start: string; end: string };
  scope: { type: 'global' | 'site' | 'fault_type'; id: string };
  
  // Volume
  total_verifications: number;
  verifications_passed: number;
  verifications_failed: number;
  verifications_inconclusive: number;
  
  // Rates
  first_time_fix_rate: number;      // Passed on first attempt
  reopen_rate: number;              // Cases reopened after close
  recurrence_rate: number;          // Issues recurring within window
  
  // Timing
  average_verification_duration_hours: number;
  average_time_to_resolution_hours: number;
  
  // By fault type
  by_fault_type: Array<{
    fault_type: string;
    count: number;
    pass_rate: number;
    avg_verification_hours: number;
  }>;
  
  // Problem areas
  problem_areas: Array<{
    asset_id: string;
    asset_name: string;
    reopen_count: number;
    recurrence_count: number;
    investigation_recommended: boolean;
  }>;
}

// =============================================================================
// AUDIT TRAIL
// =============================================================================

export interface VerificationAuditEntry {
  entry_id: string;
  case_id: string;
  timestamp: string;
  
  action: 
    | 'verification_started'
    | 'verification_completed'
    | 'auto_closed'
    | 'auto_reopened'
    | 'manual_override'
    | 'recurrence_detected'
    | 'escalation_triggered';
  
  actor: {
    type: 'system' | 'user';
    id: string;
    name?: string;
  };
  
  details: {
    description: string;
    before_state?: Record<string, unknown>;
    after_state?: Record<string, unknown>;
    evidence?: string[];
    notes?: string;
  };
}
