/**
 * Explainability Action Packages + Evidence Bundles
 * 
 * Defines plain-language diagnosis, evidence snapshots, specific steps,
 * likely parts/tools, and safety/compliance notes.
 * Addresses FR-018.
 */

// =============================================================================
// EVIDENCE BUNDLE
// =============================================================================

export interface EvidenceBundle {
  bundle_id: string;
  case_id: string;
  generated_at: string;
  
  // Summary
  summary: {
    diagnosis_hypothesis: string;
    confidence: number;
    severity: 'critical' | 'warning' | 'info';
    urgency: string;
  };
  
  // Contributing factors
  contributing_factors: ContributingFactor[];
  
  // Baseline comparison
  baseline_comparison: BaselineComparison;
  
  // Charts and visualizations
  visualizations: Visualization[];
  
  // Key facts
  key_facts: KeyFact[];
  
  // Timeline
  event_timeline: TimelineEvent[];
  
  // Related context
  context: {
    weather_conditions?: WeatherContext;
    operating_mode?: string;
    load_conditions?: string;
    recent_maintenance?: string[];
    similar_past_cases?: string[];
  };
}

export interface ContributingFactor {
  factor_id: string;
  metric_name: string;
  canonical_name: string;
  
  contribution_score: number;
  contribution_rank: number;
  
  current_value: number;
  expected_value: number;
  deviation_percent: number;
  deviation_direction: 'above' | 'below';
  
  interpretation: string;
  
  trend: {
    direction: 'increasing' | 'decreasing' | 'stable' | 'fluctuating';
    rate_of_change: number;
    time_to_critical?: number;
  };
}

export interface BaselineComparison {
  baseline_type: 'historical_avg' | 'design_spec' | 'peer_group' | 'pre_fault';
  baseline_period?: { start: string; end: string };
  
  metrics: Array<{
    metric_name: string;
    baseline_value: number;
    current_value: number;
    delta: number;
    delta_percent: number;
    is_significant: boolean;
  }>;
  
  overall_deviation_score: number;
}

export interface Visualization {
  viz_id: string;
  viz_type: 'time_series' | 'comparison_bar' | 'gauge' | 'heatmap' | 'scatter';
  title: string;
  description: string;
  
  data: {
    series: Array<{
      name: string;
      values: Array<{ x: number | string; y: number }>;
      color?: string;
    }>;
    annotations?: Array<{
      x: number | string;
      label: string;
      type: 'event' | 'threshold' | 'baseline';
    }>;
  };
  
  config: {
    x_axis_label?: string;
    y_axis_label?: string;
    show_baseline?: boolean;
    show_thresholds?: boolean;
    highlight_anomalies?: boolean;
  };
}

export interface KeyFact {
  fact_id: string;
  category: 'symptom' | 'context' | 'history' | 'risk';
  statement: string;
  importance: 'high' | 'medium' | 'low';
  
  supporting_data?: {
    metric?: string;
    value?: number;
    timestamp?: string;
  };
}

export interface TimelineEvent {
  timestamp: string;
  event_type: 'anomaly_detected' | 'threshold_crossed' | 'mode_change' | 'alert_fired' | 'maintenance' | 'other';
  description: string;
  severity?: string;
  related_metrics?: string[];
}

export interface WeatherContext {
  temperature_f: number;
  humidity_percent: number;
  conditions: string;
  is_extreme: boolean;
  impact_assessment: string;
}

// =============================================================================
// ACTION PACKAGES
// =============================================================================

export interface ActionPackage {
  package_id: string;
  case_id: string;
  fault_type: string;
  
  // Diagnosis
  diagnosis: {
    hypothesis: string;
    confidence: number;
    alternative_hypotheses: Array<{
      hypothesis: string;
      probability: number;
    }>;
  };
  
  // Recommended actions
  recommended_actions: RecommendedActionStep[];
  
  // Parts and tools
  likely_parts: LikelyPart[];
  required_tools: RequiredTool[];
  
  // Safety and compliance
  safety_notes: SafetyNote[];
  compliance_requirements: ComplianceRequirement[];
  
  // Estimated effort
  estimated_effort: {
    diagnosis_time_minutes: number;
    repair_time_minutes: number;
    total_time_minutes: number;
    skill_level_required: 'basic' | 'intermediate' | 'advanced' | 'specialist';
  };
  
  // References
  references: Array<{
    type: 'manual' | 'bulletin' | 'video' | 'past_case';
    title: string;
    url?: string;
    relevance: string;
  }>;
}

export interface RecommendedActionStep {
  step_number: number;
  action_type: 'inspect' | 'test' | 'measure' | 'adjust' | 'repair' | 'replace' | 'clean' | 'verify';
  
  title: string;
  description: string;
  detailed_instructions?: string[];
  
  expected_outcome: string;
  decision_point?: {
    if_condition: string;
    then_action: string;
    else_action: string;
  };
  
  duration_minutes: number;
  skill_level: 'basic' | 'intermediate' | 'advanced';
  
  safety_precautions?: string[];
  tools_needed?: string[];
  parts_needed?: string[];
  
  verification?: {
    method: string;
    expected_value?: string;
    acceptable_range?: string;
  };
}

export interface LikelyPart {
  part_number: string;
  part_name: string;
  description: string;
  
  likelihood_needed: number;
  confidence: number;
  
  quantity: number;
  estimated_cost: number;
  
  availability: {
    in_stock: boolean;
    location?: string;
    lead_time_hours?: number;
  };
  
  alternatives?: Array<{
    part_number: string;
    part_name: string;
    compatibility_notes: string;
  }>;
}

export interface RequiredTool {
  tool_name: string;
  tool_category: 'measurement' | 'diagnostic' | 'hand_tool' | 'power_tool' | 'safety' | 'specialized';
  
  purpose: string;
  required: boolean;
  
  specifications?: string;
  calibration_required?: boolean;
}

export interface SafetyNote {
  note_id: string;
  severity: 'critical' | 'warning' | 'caution';
  category: 'electrical' | 'refrigerant' | 'mechanical' | 'chemical' | 'environmental' | 'ppe';
  
  title: string;
  description: string;
  
  required_ppe?: string[];
  required_certifications?: string[];
  
  regulatory_reference?: string;
}

export interface ComplianceRequirement {
  requirement_id: string;
  regulation: string;
  description: string;
  
  actions_required: string[];
  documentation_required: string[];
  
  applies_when: string;
  penalty_for_non_compliance?: string;
}

// =============================================================================
// FAULT NARRATIVES
// =============================================================================

export interface FaultNarrative {
  narrative_id: string;
  fault_type: string;
  fault_code: string;
  
  // Plain language description
  title: string;
  summary: string;
  detailed_description: string;
  
  // What the technician will observe
  observable_symptoms: string[];
  
  // Root cause explanation
  root_cause_explanation: string;
  common_causes: Array<{
    cause: string;
    frequency: 'common' | 'occasional' | 'rare';
    how_to_confirm: string;
  }>;
  
  // Impact if not addressed
  impact_if_unaddressed: {
    immediate: string;
    short_term: string;
    long_term: string;
  };
  
  // Historical context
  historical_context?: {
    typical_occurrence_rate: string;
    seasonal_pattern?: string;
    equipment_age_correlation?: string;
  };
}

// =============================================================================
// TECHNICIAN-FRIENDLY OUTPUT
// =============================================================================

export interface TechnicianBrief {
  brief_id: string;
  case_id: string;
  generated_at: string;
  
  // One-liner
  headline: string;
  
  // Quick facts (mobile-friendly)
  quick_facts: Array<{
    label: string;
    value: string;
    highlight: boolean;
  }>;
  
  // What to do first
  first_action: string;
  
  // What to bring
  bring_list: {
    required_parts: string[];
    required_tools: string[];
    optional_parts: string[];
  };
  
  // Safety reminders
  safety_reminders: string[];
  
  // Expected time
  expected_duration: string;
  
  // Contact if needed
  escalation_contact?: {
    name: string;
    role: string;
    phone: string;
  };
}
