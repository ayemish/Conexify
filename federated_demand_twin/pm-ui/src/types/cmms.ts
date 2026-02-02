/**
 * CMMS/Work Order Integration Types
 * 
 * Defines bidirectional CMMS sync, standardized payloads,
 * and integration failure handling.
 * Addresses FR-015.
 */

export type WorkOrderStatus = 
  | 'draft' | 'pending_dispatch' | 'dispatched' | 'assigned'
  | 'en_route' | 'on_site' | 'in_progress' | 'parts_ordered'
  | 'on_hold' | 'completed' | 'verified_closed' | 'cancelled';

export type WorkOrderPriority = 'emergency' | 'urgent' | 'high' | 'medium' | 'low' | 'scheduled';

export interface WorkOrder {
  work_order_id: string;
  external_id?: string;
  case_id: string;
  
  status: WorkOrderStatus;
  priority: WorkOrderPriority;
  
  site: { site_id: string; site_name: string; address: string };
  asset: { asset_id: string; asset_name: string; equipment_type: string };
  
  fault: {
    fault_type: string;
    fault_code: string;
    description: string;
    symptoms: string[];
    confidence: number;
  };
  
  assignment: {
    assigned_to?: string;
    technician_name?: string;
    technician_phone?: string;
    dispatch_time?: string;
    eta?: string;
  };
  
  scheduling: {
    requested_date?: string;
    scheduled_date?: string;
    sla_due_date?: string;
    sla_status: 'on_track' | 'at_risk' | 'breached';
  };
  
  recommended_actions: RecommendedAction[];
  recommended_parts: RecommendedPart[];
  
  evidence_bundle_id?: string;
  
  timestamps: {
    created_at: string;
    updated_at: string;
    dispatched_at?: string;
    arrived_at?: string;
    started_at?: string;
    completed_at?: string;
  };
}

export interface RecommendedAction {
  action_id: string;
  sequence: number;
  action_type: 'inspect' | 'test' | 'adjust' | 'repair' | 'replace' | 'clean';
  description: string;
  estimated_duration_minutes: number;
  skill_required?: string;
  safety_notes?: string[];
}

export interface RecommendedPart {
  part_id: string;
  part_number: string;
  description: string;
  quantity: number;
  likelihood_needed: number;
  estimated_cost?: number;
  availability?: 'in_stock' | 'order_required' | 'unknown';
}

export interface WorkOrderCompletion {
  work_order_id: string;
  completed_at: string;
  technician_id: string;
  
  close_code: CloseCode;
  resolution_notes: string;
  
  work_performed: Array<{
    action_description: string;
    duration_minutes: number;
    outcome: 'completed' | 'partial' | 'not_needed' | 'unable';
  }>;
  
  parts_used: Array<{
    part_number: string;
    quantity: number;
    cost: number;
  }>;
  
  labor: {
    travel_time_minutes: number;
    on_site_time_minutes: number;
    total_labor_cost: number;
  };
  
  attachments: Attachment[];
  
  verification_status: 'pending' | 'passed' | 'failed';
  follow_up_required: boolean;
  follow_up_notes?: string;
}

export interface CloseCode {
  code: string;
  category: 'confirmed_fix' | 'no_fault_found' | 'customer_issue' | 'deferred' | 'cannot_repair';
  description: string;
  requires_follow_up: boolean;
}

export interface Attachment {
  attachment_id: string;
  type: 'photo' | 'video' | 'document' | 'signature';
  filename: string;
  url: string;
  uploaded_at: string;
  description?: string;
}

export interface CMSSyncConfig {
  config_id: string;
  cmms_system: string;
  
  connection: {
    base_url: string;
    auth_type: 'api_key' | 'oauth2' | 'basic';
    credentials_ref: string;
  };
  
  sync_settings: {
    outbound_enabled: boolean;
    inbound_enabled: boolean;
    sync_interval_minutes: number;
    real_time_webhooks: boolean;
  };
  
  field_mappings: FieldMapping[];
  
  status_mappings: Array<{
    internal_status: WorkOrderStatus;
    external_status: string;
    bidirectional: boolean;
  }>;
  
  close_code_mappings: Array<{
    internal_code: string;
    external_code: string;
  }>;
}

export interface FieldMapping {
  internal_field: string;
  external_field: string;
  direction: 'outbound' | 'inbound' | 'bidirectional';
  transformation?: string;
  required: boolean;
}

export interface CMSSSyncJob {
  job_id: string;
  job_type: 'outbound_create' | 'outbound_update' | 'inbound_sync' | 'full_reconciliation';
  
  work_order_id?: string;
  external_id?: string;
  
  status: 'pending' | 'in_progress' | 'completed' | 'failed' | 'retry_scheduled';
  
  attempts: number;
  max_attempts: number;
  next_retry?: string;
  
  request_payload?: Record<string, unknown>;
  response_payload?: Record<string, unknown>;
  
  error?: {
    code: string;
    message: string;
    retryable: boolean;
  };
  
  timestamps: {
    created_at: string;
    started_at?: string;
    completed_at?: string;
  };
}

export interface CMSSSyncMetrics {
  period: { start: string; end: string };
  
  outbound: {
    total_synced: number;
    successful: number;
    failed: number;
    avg_latency_ms: number;
  };
  
  inbound: {
    total_received: number;
    processed: number;
    failed: number;
    avg_processing_ms: number;
  };
  
  reconciliation: {
    last_run: string;
    discrepancies_found: number;
    auto_resolved: number;
    manual_review_needed: number;
  };
  
  health: {
    status: 'healthy' | 'degraded' | 'unhealthy';
    last_successful_sync: string;
    error_rate_percent: number;
  };
}

export interface FaultTaxonomy {
  taxonomy_id: string;
  fault_code: string;
  fault_name: string;
  category: string;
  subcategory: string;
  
  description: string;
  symptoms: string[];
  common_causes: string[];
  
  recommended_actions: string[];
  typical_parts: string[];
  estimated_repair_time_minutes: number;
  
  skill_level_required: 'basic' | 'intermediate' | 'advanced' | 'specialist';
  safety_considerations: string[];
  regulatory_notes?: string[];
  
  cmms_mappings: Array<{
    cmms_system: string;
    external_code: string;
  }>;
}
