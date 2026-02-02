/**
 * Dispatch Batching Optimizer Types
 * 
 * Defines batching issues by geography/site/visit windows,
 * consolidating fixes into fewer truck rolls, and scheduling
 * under resource constraints.
 * Addresses FR-013, FR-017.
 */

// =============================================================================
// DISPATCH PLAN
// =============================================================================

export interface DispatchPlan {
  plan_id: string;
  plan_date: string;
  region_id: string;
  
  status: 'draft' | 'optimizing' | 'ready' | 'approved' | 'in_progress' | 'completed';
  
  // Optimization summary
  optimization_summary: {
    total_cases: number;
    total_visits: number;
    cases_batched: number;
    truck_rolls_saved: number;
    estimated_cost_savings: number;
    estimated_time_savings_hours: number;
  };
  
  // Visits
  visits: DispatchVisit[];
  
  // Unassigned cases
  unassigned_cases: Array<{
    case_id: string;
    reason: 'no_available_tech' | 'parts_unavailable' | 'outside_region' | 'constraint_conflict';
  }>;
  
  // Constraints applied
  constraints_applied: DispatchConstraint[];
  
  // Timestamps
  created_at: string;
  optimized_at?: string;
  approved_at?: string;
  approved_by?: string;
}

export interface DispatchVisit {
  visit_id: string;
  
  // Assignment
  technician_id: string;
  technician_name: string;
  
  // Location
  site_id: string;
  site_name: string;
  site_address: string;
  coordinates: { lat: number; lng: number };
  
  // Timing
  scheduled_arrival: string;
  estimated_duration_minutes: number;
  scheduled_departure: string;
  
  // Cases bundled in this visit
  cases: DispatchCase[];
  
  // Travel
  travel: {
    from_location: string;
    distance_miles: number;
    estimated_travel_minutes: number;
  };
  
  // Status
  status: 'scheduled' | 'en_route' | 'arrived' | 'in_progress' | 'completed' | 'cancelled';
}

export interface DispatchCase {
  case_id: string;
  work_order_id: string;
  
  asset_id: string;
  asset_name: string;
  
  fault_type: string;
  priority: string;
  sla_due: string;
  
  estimated_work_minutes: number;
  
  required_skills: string[];
  required_parts: Array<{
    part_number: string;
    quantity: number;
    available: boolean;
  }>;
  
  sequence_in_visit: number;
}

// =============================================================================
// CONSTRAINTS
// =============================================================================

export interface DispatchConstraint {
  constraint_id: string;
  constraint_type: ConstraintType;
  enabled: boolean;
  priority: number;
  
  // Constraint-specific config
  config: Record<string, unknown>;
  
  // Soft vs hard
  is_hard_constraint: boolean;
  violation_penalty?: number;
}

export type ConstraintType =
  | 'technician_availability'
  | 'technician_skills'
  | 'technician_certifications'
  | 'parts_availability'
  | 'sla_window'
  | 'store_hours'
  | 'travel_time_max'
  | 'workday_duration'
  | 'break_requirements'
  | 'overtime_limit'
  | 'geography_boundary'
  | 'case_dependency';

export interface TechnicianAvailability {
  technician_id: string;
  date: string;
  
  available_windows: Array<{
    start: string;
    end: string;
  }>;
  
  skills: string[];
  certifications: string[];
  
  home_base: { lat: number; lng: number };
  max_travel_radius_miles: number;
  
  current_assignments: string[];
  capacity_remaining_hours: number;
}

export interface PartsAvailability {
  part_number: string;
  description: string;
  
  availability: Array<{
    location_type: 'technician_truck' | 'warehouse' | 'supplier';
    location_id: string;
    quantity: number;
    lead_time_hours: number;
  }>;
}

// =============================================================================
// OPTIMIZATION
// =============================================================================

export interface OptimizationRequest {
  request_id: string;
  
  // Scope
  region_id: string;
  date_range: { start: string; end: string };
  
  // Cases to schedule
  case_ids: string[];
  
  // Resources
  technician_ids: string[];
  
  // Objectives (weighted)
  objectives: {
    minimize_truck_rolls: number;      // Weight 0-1
    minimize_travel_time: number;
    maximize_sla_compliance: number;
    balance_workload: number;
    minimize_overtime: number;
  };
  
  // Constraints
  constraints: DispatchConstraint[];
  
  // Options
  options: {
    allow_overtime: boolean;
    max_overtime_hours: number;
    allow_next_day_parts: boolean;
    allow_partial_visits: boolean;
  };
}

export interface OptimizationResult {
  result_id: string;
  request_id: string;
  
  status: 'optimal' | 'feasible' | 'infeasible' | 'timeout';
  solve_time_seconds: number;
  
  // Solution quality
  solution_quality: {
    objective_value: number;
    optimality_gap_percent?: number;
  };
  
  // Metrics
  metrics: {
    total_visits: number;
    total_cases_scheduled: number;
    cases_unscheduled: number;
    
    total_travel_miles: number;
    total_travel_hours: number;
    
    truck_rolls_baseline: number;
    truck_rolls_optimized: number;
    truck_rolls_saved: number;
    
    sla_compliance_rate: number;
    
    technician_utilization: Record<string, number>;
    overtime_hours: Record<string, number>;
  };
  
  // Comparison to baseline (no batching)
  savings_vs_baseline: {
    cost_saved: number;
    time_saved_hours: number;
    miles_saved: number;
    co2_avoided_kg: number;
  };
  
  // Generated plan
  plan: DispatchPlan;
}

// =============================================================================
// BATCHING RECOMMENDATIONS
// =============================================================================

export interface BatchingRecommendation {
  recommendation_id: string;
  generated_at: string;
  
  // Cases that can be batched
  case_group: Array<{
    case_id: string;
    site_id: string;
    asset_id: string;
    priority: string;
    sla_due: string;
  }>;
  
  // Why they can be batched
  batching_rationale: {
    same_site: boolean;
    nearby_sites: boolean;
    distance_miles?: number;
    compatible_skills: boolean;
    compatible_timing: boolean;
    shared_parts: boolean;
  };
  
  // Savings estimate
  savings_estimate: {
    truck_rolls_saved: number;
    travel_time_saved_minutes: number;
    cost_saved: number;
  };
  
  // Feasibility
  feasibility: {
    technician_available: boolean;
    parts_available: boolean;
    sla_achievable: boolean;
    constraints_satisfied: boolean;
  };
  
  // Confidence
  confidence: number;
  
  // User action
  status: 'pending' | 'accepted' | 'rejected' | 'expired';
  actioned_by?: string;
  actioned_at?: string;
}

// =============================================================================
// DISPATCH METRICS
// =============================================================================

export interface DispatchMetrics {
  period: { start: string; end: string };
  region_id: string;
  
  // Volume
  total_cases_dispatched: number;
  total_visits: number;
  
  // Efficiency
  batching_rate: number;  // Cases per visit average
  truck_rolls_saved: number;
  cost_savings: number;
  
  // Performance
  sla_compliance_rate: number;
  first_time_fix_rate: number;
  average_response_time_hours: number;
  
  // Utilization
  technician_utilization_avg: number;
  overtime_hours_total: number;
  
  // Travel
  total_miles_traveled: number;
  average_miles_per_visit: number;
  
  // Trends
  trends: {
    batching_rate_trend: 'improving' | 'stable' | 'declining';
    efficiency_vs_last_period: number;
  };
}
