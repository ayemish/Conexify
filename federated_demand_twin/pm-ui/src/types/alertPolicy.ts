/**
 * Alert Policy Mechanics Types
 * 
 * Defines persistence, cooldown, dedupe, and case merging policies
 * that prevent alert spam and ensure field trust.
 * Addresses FR-006, FR-011, FR-017.
 */

// =============================================================================
// ALERT POLICY CONFIGURATION
// =============================================================================

export interface AlertPolicy {
  policy_id: string;
  policy_name: string;
  description: string;
  enabled: boolean;
  priority: number; // Lower = higher priority, evaluated first
  
  // Scope
  scope: {
    site_ids?: string[];
    asset_ids?: string[];
    equipment_types?: string[];
    alert_types?: string[];
    severity_levels?: ('critical' | 'warning' | 'info')[];
  };
  
  // Persistence: must be true for duration before firing
  persistence: {
    enabled: boolean;
    duration_minutes: number;
    consecutive_required: boolean; // Must be consecutive readings
    sample_threshold?: number;     // Min samples in window
  };
  
  // Cooldown: don't re-alert for duration unless escalates
  cooldown: {
    enabled: boolean;
    duration_hours: number;
    reset_on_clear: boolean;        // Reset cooldown if condition clears
    escalation_override: boolean;   // Allow re-alert if severity increases
    escalation_threshold?: number;  // Value change that triggers escalation
  };
  
  // Dedupe: same underlying issue shouldn't generate multiple alerts
  dedupe: {
    enabled: boolean;
    window_hours: number;
    match_criteria: DedupeMatchCriteria;
    action: 'suppress' | 'merge' | 'update_existing';
  };
  
  // Rate limiting
  rate_limit: {
    enabled: boolean;
    max_alerts_per_hour: number;
    max_alerts_per_day: number;
    overflow_action: 'queue' | 'suppress' | 'batch_summary';
  };
  
  // Metadata
  created_at: string;
  updated_at: string;
  created_by: string;
  version: number;
}

export interface DedupeMatchCriteria {
  same_asset: boolean;
  same_alert_type: boolean;
  same_fault_signature: boolean;
  same_root_cause?: boolean;
  similarity_threshold?: number; // 0-1 for fuzzy matching
}

// =============================================================================
// ALERT BURDEN CONTROLS
// =============================================================================

export interface AlertBurdenConfig {
  config_id: string;
  
  // Scope
  scope_type: 'global' | 'site' | 'asset' | 'customer';
  scope_id: string;
  
  // Limits
  limits: {
    max_open_cases_per_asset: number;
    max_alerts_per_asset_month: number;
    max_alerts_per_site_month: number;
    max_critical_alerts_per_day: number;
  };
  
  // Actions when exceeded
  overflow_actions: {
    alert_action: 'suppress' | 'batch' | 'escalate_to_supervisor';
    notification_action: 'summary_only' | 'none' | 'daily_digest';
    review_required: boolean;
  };
  
  // Tracking
  current_counts: {
    period_start: string;
    alerts_this_month: number;
    open_cases: number;
    critical_today: number;
  };
}

// =============================================================================
// CASE CORRELATION & MERGING
// =============================================================================

export interface CaseCorrelationRule {
  rule_id: string;
  rule_name: string;
  description: string;
  enabled: boolean;
  
  // Matching criteria
  match_criteria: {
    time_window_hours: number;
    same_asset: boolean;
    same_parent_asset: boolean;     // Same rack, same RTU, etc.
    same_site: boolean;
    fault_signature_similarity: number; // 0-1
    root_cause_match: boolean;
  };
  
  // Actions
  merge_action: {
    type: 'merge_into_existing' | 'create_parent_case' | 'link_related';
    primary_case_selection: 'oldest' | 'highest_severity' | 'highest_confidence';
    preserve_individual_alerts: boolean;
  };
  
  // Priority (for conflicting rules)
  priority: number;
}

export interface CaseMergeResult {
  merge_id: string;
  timestamp: string;
  
  primary_case_id: string;
  merged_case_ids: string[];
  
  rule_applied: string;
  
  merge_summary: {
    total_alerts_combined: number;
    assets_affected: string[];
    severity_after_merge: 'critical' | 'warning' | 'info';
    combined_confidence: number;
  };
  
  audit_trail: {
    automated: boolean;
    approved_by?: string;
    notes?: string;
  };
}

// =============================================================================
// ESCALATION LADDER
// =============================================================================

export interface EscalationLadder {
  ladder_id: string;
  name: string;
  description: string;
  
  // Trigger conditions
  trigger: {
    alert_types?: string[];
    severity_levels?: string[];
    asset_criticality?: string[];
    after_duration_hours?: number;
    after_failed_attempts?: number;
  };
  
  // Escalation steps
  steps: EscalationStep[];
  
  // Final action if all steps exhausted
  final_action: {
    action_type: 'auto_dispatch' | 'supervisor_alert' | 'executive_escalation';
    notification_channels: string[];
  };
}

export interface EscalationStep {
  step_number: number;
  name: string;
  
  // Timing
  wait_duration_hours: number;
  
  // Actions
  actions: {
    notify_roles: string[];
    notify_channels: ('email' | 'sms' | 'push' | 'slack' | 'teams')[];
    update_priority: boolean;
    new_priority?: 'critical' | 'high' | 'medium' | 'low';
  };
  
  // Exit conditions
  exit_conditions: {
    acknowledged: boolean;
    assigned: boolean;
    work_order_created: boolean;
  };
}

// =============================================================================
// ALERT POLICY EVALUATION
// =============================================================================

export interface AlertPolicyEvaluation {
  evaluation_id: string;
  alert_id: string;
  timestamp: string;
  
  // Policies evaluated
  policies_evaluated: Array<{
    policy_id: string;
    policy_name: string;
    result: 'pass' | 'suppress' | 'modify';
    reason?: string;
  }>;
  
  // Final outcome
  outcome: {
    action: 'fire' | 'suppress' | 'defer' | 'merge';
    reason: string;
    merged_into_case_id?: string;
    deferred_until?: string;
  };
  
  // State at evaluation
  state_snapshot: {
    persistence_met: boolean;
    persistence_duration_so_far: number;
    cooldown_active: boolean;
    cooldown_remaining_hours?: number;
    duplicate_found: boolean;
    duplicate_case_id?: string;
    rate_limit_status: 'ok' | 'approaching' | 'exceeded';
  };
}

// =============================================================================
// ALERT SPAM METRICS
// =============================================================================

export interface AlertSpamMetrics {
  period_start: string;
  period_end: string;
  scope_type: 'global' | 'site' | 'asset';
  scope_id: string;
  
  // Volume metrics
  total_alerts_generated: number;
  alerts_suppressed: number;
  alerts_merged: number;
  alerts_delivered: number;
  
  // Quality metrics
  false_positive_rate: number;
  actionable_rate: number;
  average_time_to_acknowledge: number;
  average_time_to_resolve: number;
  
  // Burden metrics
  alerts_per_asset: number;
  alerts_per_operator_hour: number;
  alert_fatigue_score: number; // 0-100, higher = more fatigue risk
  
  // Trend
  trend_vs_prior_period: {
    volume_change_percent: number;
    quality_change_percent: number;
  };
}
