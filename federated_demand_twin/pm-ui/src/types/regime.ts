/**
 * Operating Regime Awareness Types
 * 
 * Defines regime classification for operating modes, load conditions,
 * and store schedules that affect PdM accuracy and false-positive reduction.
 * Core to FR-001 context awareness.
 */

// =============================================================================
// OPERATING REGIMES
// =============================================================================

export type OperatingMode = 
  | 'normal'
  | 'defrost'
  | 'economizer'
  | 'heat_recovery'
  | 'night_setback'
  | 'unoccupied'
  | 'demand_response'
  | 'emergency'
  | 'startup'
  | 'shutdown'
  | 'maintenance';

export type LoadCondition = 
  | 'peak'
  | 'high'
  | 'normal'
  | 'low'
  | 'minimal';

export type StageStatus = 'stage_1' | 'stage_2' | 'stage_3' | 'stage_4' | 'all_stages';

export interface OperatingRegime {
  regime_id: string;
  asset_id: string;
  timestamp: string;
  
  // Current mode
  operating_mode: OperatingMode;
  mode_confidence: number;
  mode_duration_minutes: number;
  
  // Load
  load_condition: LoadCondition;
  load_percent: number;
  
  // Staging (for multi-stage equipment)
  staging?: {
    current_stage: StageStatus;
    stages_available: number;
    staging_history_1h: StageStatus[];
  };
  
  // Cycling
  cycling: {
    is_cycling: boolean;
    cycle_rate_per_hour: number;
    avg_run_time_minutes: number;
    avg_off_time_minutes: number;
  };
  
  // Context flags
  context_flags: {
    is_defrost: boolean;
    is_economizing: boolean;
    is_occupied: boolean;
    is_demand_response: boolean;
    is_scheduled_maintenance: boolean;
  };
  
  // Detection metadata
  detection: {
    method: 'rule_based' | 'ml_classifier' | 'schedule_based' | 'hybrid';
    model_version?: string;
    features_used?: string[];
  };
}

// =============================================================================
// REGIME CLASSIFICATION SERVICE
// =============================================================================

export interface RegimeClassifierConfig {
  config_id: string;
  equipment_type: string;
  
  // Classification methods
  methods: {
    // Rule-based detection
    rule_based: {
      enabled: boolean;
      rules: RegimeDetectionRule[];
    };
    
    // ML-based detection
    ml_classifier: {
      enabled: boolean;
      model_id: string;
      model_version: string;
      confidence_threshold: number;
    };
    
    // Schedule-based
    schedule_based: {
      enabled: boolean;
      schedule_source: 'site_schedule' | 'bms' | 'manual';
    };
  };
  
  // Fallback behavior
  fallback: {
    default_mode: OperatingMode;
    default_load: LoadCondition;
  };
  
  // Update frequency
  update_interval_seconds: number;
}

export interface RegimeDetectionRule {
  rule_id: string;
  rule_name: string;
  target_mode: OperatingMode;
  
  conditions: Array<{
    metric_id: string;
    operator: 'eq' | 'ne' | 'gt' | 'gte' | 'lt' | 'lte' | 'between' | 'rate_of_change';
    value: number | string | [number, number];
    duration_minutes?: number;
  }>;
  
  logic: 'all' | 'any';
  priority: number;
}

// =============================================================================
// REGIME-CONDITIONED THRESHOLDS
// =============================================================================

export interface RegimeConditionedThreshold {
  threshold_id: string;
  metric_id: string;
  asset_type: string;
  
  // Base threshold (when no regime match)
  base_threshold: ThresholdConfig;
  
  // Regime-specific overrides
  regime_overrides: Array<{
    regime_conditions: {
      operating_modes?: OperatingMode[];
      load_conditions?: LoadCondition[];
      context_flags?: Partial<Record<string, boolean>>;
    };
    
    threshold: ThresholdConfig;
    rationale: string;
  }>;
  
  // Transition handling
  transition_config: {
    grace_period_minutes: number;
    require_stable_regime: boolean;
    min_stability_minutes: number;
  };
}

export interface ThresholdConfig {
  warning_threshold: number;
  critical_threshold: number;
  operator: 'gt' | 'lt' | 'outside_range';
  range?: [number, number];
}

// =============================================================================
// REGIME-CONDITIONED BASELINES
// =============================================================================

export interface RegimeConditionedBaseline {
  baseline_id: string;
  asset_id: string;
  metric_id: string;
  
  // Baseline by regime
  regime_baselines: Array<{
    regime_key: string;  // e.g., "normal_peak", "defrost_any"
    operating_mode: OperatingMode;
    load_condition?: LoadCondition;
    
    baseline: {
      mean: number;
      std: number;
      percentiles: { p5: number; p25: number; p50: number; p75: number; p95: number };
      sample_count: number;
      last_updated: string;
    };
  }>;
  
  // Calculation config
  calculation_config: {
    lookback_days: number;
    min_samples: number;
    outlier_removal: boolean;
    outlier_threshold_std: number;
    update_frequency_hours: number;
  };
}

// =============================================================================
// SCHEDULE & OCCUPANCY
// =============================================================================

export interface SiteSchedule {
  schedule_id: string;
  site_id: string;
  
  // Regular hours
  regular_hours: {
    [day: string]: {
      open: string;
      close: string;
      is_closed: boolean;
    };
  };
  
  // Special dates
  special_dates: Array<{
    date: string;
    type: 'holiday' | 'extended_hours' | 'early_close' | 'closed';
    hours?: { open: string; close: string };
  }>;
  
  // Occupancy zones
  occupancy_transitions: {
    pre_open_minutes: number;
    post_close_minutes: number;
    night_setback_start_offset_minutes: number;
  };
}

export interface OccupancyState {
  site_id: string;
  timestamp: string;
  
  is_occupied: boolean;
  occupancy_phase: 'pre_open' | 'open' | 'post_close' | 'night' | 'closed';
  
  // Inferred from schedule or sensors
  source: 'schedule' | 'sensor' | 'bms' | 'override';
  
  // For sensor-based
  occupancy_level?: 'high' | 'medium' | 'low' | 'empty';
  people_count?: number;
}

// =============================================================================
// REGIME GATING FOR ALERTS
// =============================================================================

export interface RegimeGatingPolicy {
  policy_id: string;
  alert_type: string;
  
  // Suppress during these regimes
  suppress_during: Array<{
    operating_modes?: OperatingMode[];
    context_flags?: Partial<Record<string, boolean>>;
    duration_limit_minutes?: number;
    reason: string;
  }>;
  
  // Require stable regime before alerting
  require_stable_regime: {
    enabled: boolean;
    min_stable_minutes: number;
    exclude_transitions: boolean;
  };
  
  // Adjust severity based on regime
  severity_adjustments: Array<{
    regime_condition: {
      operating_modes?: OperatingMode[];
      load_conditions?: LoadCondition[];
    };
    severity_modifier: 'increase' | 'decrease' | 'no_change';
    reason: string;
  }>;
}

export interface RegimeGatingEvaluation {
  evaluation_id: string;
  alert_id: string;
  timestamp: string;
  
  // Current regime
  current_regime: OperatingRegime;
  
  // Policy applied
  policy_id: string;
  
  // Evaluation result
  result: {
    action: 'allow' | 'suppress' | 'defer' | 'adjust_severity';
    reason: string;
    original_severity?: string;
    adjusted_severity?: string;
    deferred_until?: string;
  };
}

// =============================================================================
// REGIME ANALYTICS
// =============================================================================

export interface RegimeAnalytics {
  asset_id: string;
  period: { start: string; end: string };
  
  // Time in each mode
  mode_distribution: Array<{
    mode: OperatingMode;
    hours: number;
    percent: number;
  }>;
  
  // Load distribution
  load_distribution: Array<{
    load: LoadCondition;
    hours: number;
    percent: number;
  }>;
  
  // Transitions
  transition_stats: {
    total_transitions: number;
    transitions_per_day: number;
    most_common_transition: string;
    avg_mode_duration_minutes: number;
  };
  
  // Cycling analysis
  cycling_analysis: {
    excessive_cycling_hours: number;
    short_cycle_count: number;
    long_run_count: number;
  };
  
  // Anomalies
  regime_anomalies: Array<{
    timestamp: string;
    anomaly_type: 'unexpected_mode' | 'excessive_duration' | 'unusual_transition';
    description: string;
    severity: 'high' | 'medium' | 'low';
  }>;
}
