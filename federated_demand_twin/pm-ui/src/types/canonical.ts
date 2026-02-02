/**
 * Canonical Data Schema + Asset Topology Types
 * 
 * Provides the foundational data model for retail HVAC/R predictive maintenance.
 * Addresses FR-002 (canonical telemetry) and FR-003 (asset topology).
 */

// =============================================================================
// CANONICAL METRIC MODEL
// =============================================================================

export type MetricQualityFlag = 'good' | 'suspect' | 'bad' | 'stale' | 'missing';
export type MetricUnit = 
  | 'degF' | 'degC' | 'psi' | 'kPa' | 'percent' | 'amps' | 'volts' | 'kW' | 'kWh'
  | 'cfm' | 'gpm' | 'rpm' | 'hz' | 'hours' | 'cycles' | 'count' | 'boolean' | 'enum';

export interface CanonicalMetric {
  metric_id: string;
  canonical_name: string;
  display_name: string;
  description: string;
  unit: MetricUnit;
  data_type: 'float' | 'int' | 'bool' | 'enum';
  
  // Normalization
  normalization: {
    method: 'none' | 'min_max' | 'z_score' | 'percentile';
    reference_min?: number;
    reference_max?: number;
    reference_mean?: number;
    reference_std?: number;
  };
  
  // Quality metadata
  quality_rules: {
    min_valid?: number;
    max_valid?: number;
    max_rate_of_change?: number;
    stale_threshold_seconds: number;
  };
  
  // Source lineage
  source_lineage: {
    vendor: string;
    controller_type: string;
    raw_tag_pattern: string;
    transformation?: string;
  };
  
  // Categorization
  category: 'temperature' | 'pressure' | 'electrical' | 'flow' | 'runtime' | 'state' | 'efficiency';
  equipment_types: EquipmentType[];
}

export interface MetricReading {
  metric_id: string;
  asset_id: string;
  timestamp: string;
  value: number | boolean | string;
  quality: MetricQualityFlag;
  raw_value?: number | boolean | string;
  raw_tag?: string;
}

// =============================================================================
// ASSET TOPOLOGY
// =============================================================================

export type EquipmentType = 
  | 'rack' | 'circuit' | 'case' | 'compressor' | 'condenser'
  | 'rtu' | 'ahu' | 'zone' | 'vav'
  | 'chiller' | 'cooling_tower' | 'pump' | 'loop'
  | 'walk_in_cooler' | 'walk_in_freezer' | 'reach_in';

export type CriticalityTier = 'critical' | 'high' | 'medium' | 'low';

export interface Asset {
  asset_id: string;
  asset_name: string;
  equipment_type: EquipmentType;
  
  // Hierarchy
  parent_asset_id: string | null;
  child_asset_ids: string[];
  
  // Location
  site_id: string;
  zone_id?: string;
  location_description?: string;
  
  // Classification
  criticality_tier: CriticalityTier;
  business_impact: {
    revenue_per_hour?: number;
    product_loss_risk?: 'high' | 'medium' | 'low';
    safety_critical: boolean;
    regulatory_monitored: boolean;
  };
  
  // Equipment details
  manufacturer?: string;
  model?: string;
  serial_number?: string;
  install_date?: string;
  warranty_expiration?: string;
  expected_life_years?: number;
  
  // Operational context
  design_capacity?: number;
  design_capacity_unit?: string;
  setpoint_temp_low?: number;
  setpoint_temp_high?: number;
  
  // Status
  status: 'operational' | 'degraded' | 'offline' | 'maintenance' | 'decommissioned';
  last_service_date?: string;
  next_scheduled_service?: string;
}

export interface Site {
  site_id: string;
  site_name: string;
  site_type: 'grocery' | 'convenience' | 'warehouse' | 'distribution_center' | 'restaurant';
  
  // Location
  address: {
    street: string;
    city: string;
    state: string;
    postal_code: string;
    country: string;
    timezone: string;
  };
  coordinates: {
    latitude: number;
    longitude: number;
  };
  
  // Context
  climate_zone: string;
  square_footage?: number;
  store_number?: string;
  region?: string;
  district?: string;
  
  // Operations
  operating_hours: {
    [day: string]: { open: string; close: string } | 'closed' | '24h';
  };
  
  // Contacts
  primary_contact?: {
    name: string;
    phone: string;
    email: string;
  };
}

export interface AssetRelationship {
  relationship_id: string;
  source_asset_id: string;
  target_asset_id: string;
  relationship_type: 'contains' | 'feeds' | 'controls' | 'monitors' | 'backup_for';
  metadata?: Record<string, unknown>;
}

// =============================================================================
// TAG MAPPING (Vendor → Canonical)
// =============================================================================

export interface TagMapping {
  mapping_id: string;
  version: number;
  effective_date: string;
  
  // Source
  vendor: string;
  controller_type: string;
  raw_tag_pattern: string;
  
  // Target
  canonical_metric_id: string;
  
  // Transformation
  transformation: {
    type: 'direct' | 'scale' | 'offset' | 'expression' | 'lookup';
    scale_factor?: number;
    offset?: number;
    expression?: string;
    lookup_table?: Record<string, number | string>;
  };
  
  // Quality inference
  quality_inference: {
    good_range?: [number, number];
    suspect_range?: [number, number];
    comm_fail_value?: number;
  };
  
  // Status
  status: 'active' | 'deprecated' | 'draft';
  created_by: string;
  created_at: string;
}

// =============================================================================
// ASSET TOPOLOGY GRAPH OPERATIONS
// =============================================================================

export interface TopologyQuery {
  root_asset_id?: string;
  site_id?: string;
  equipment_types?: EquipmentType[];
  criticality_tiers?: CriticalityTier[];
  include_children?: boolean;
  max_depth?: number;
}

export interface TopologyNode {
  asset: Asset;
  depth: number;
  path: string[];
  children: TopologyNode[];
  metrics: CanonicalMetric[];
}

// =============================================================================
// DATA READINESS
// =============================================================================

export interface DataReadinessScore {
  asset_id: string;
  site_id: string;
  calculated_at: string;
  
  overall_score: number; // 0-100
  
  components: {
    metric_coverage: number;      // % of expected metrics present
    data_freshness: number;       // % of metrics with recent data
    quality_ratio: number;        // % of readings with good quality
    history_depth: number;        // % of required history available
    topology_completeness: number; // % of relationships defined
  };
  
  missing_metrics: string[];
  stale_metrics: string[];
  quality_issues: Array<{
    metric_id: string;
    issue_type: 'out_of_range' | 'stuck' | 'excessive_noise' | 'gaps';
    severity: 'high' | 'medium' | 'low';
  }>;
  
  recommendations: string[];
}
