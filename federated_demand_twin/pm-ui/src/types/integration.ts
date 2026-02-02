/**
 * Open Integration Posture Types
 * 
 * Defines webhooks, connector framework, and data lineage
 * for extensible integration with external systems.
 * Addresses FR-012 (open integration).
 */

// =============================================================================
// WEBHOOKS
// =============================================================================

export type WebhookEvent = 
  | 'case.created' | 'case.updated' | 'case.closed' | 'case.reopened'
  | 'alert.fired' | 'alert.resolved' | 'alert.acknowledged'
  | 'work_order.created' | 'work_order.dispatched' | 'work_order.completed'
  | 'model.deployed' | 'model.promoted'
  | 'experiment.concluded'
  | 'verification.passed' | 'verification.failed'
  | 'threshold.breached';

export interface WebhookConfig {
  webhook_id: string;
  name: string;
  description?: string;
  
  // Target
  url: string;
  method: 'POST' | 'PUT';
  
  // Authentication
  auth: {
    type: 'none' | 'api_key' | 'bearer' | 'basic' | 'hmac';
    credentials_ref?: string;
    header_name?: string;
  };
  
  // Events
  subscribed_events: WebhookEvent[];
  
  // Filters
  filters?: {
    site_ids?: string[];
    asset_types?: string[];
    severity_levels?: string[];
    custom_filter?: string;
  };
  
  // Delivery
  delivery: {
    retry_count: number;
    retry_delay_seconds: number;
    timeout_seconds: number;
    batch_size?: number;
    batch_delay_seconds?: number;
  };
  
  // Headers
  custom_headers?: Record<string, string>;
  
  // Payload
  payload_format: 'standard' | 'custom';
  payload_template?: string;
  
  // Status
  enabled: boolean;
  status: 'active' | 'failing' | 'disabled';
  
  // Metadata
  created_at: string;
  updated_at: string;
  created_by: string;
}

export interface WebhookDelivery {
  delivery_id: string;
  webhook_id: string;
  
  // Event
  event_type: WebhookEvent;
  event_id: string;
  event_timestamp: string;
  
  // Delivery attempt
  attempt_number: number;
  
  // Request
  request: {
    url: string;
    method: string;
    headers: Record<string, string>;
    body: string;
    sent_at: string;
  };
  
  // Response
  response?: {
    status_code: number;
    headers: Record<string, string>;
    body?: string;
    received_at: string;
    duration_ms: number;
  };
  
  // Outcome
  status: 'pending' | 'success' | 'failed' | 'retrying';
  error_message?: string;
  next_retry_at?: string;
}

export interface WebhookMetrics {
  webhook_id: string;
  period: { start: string; end: string };
  
  // Volume
  total_deliveries: number;
  successful_deliveries: number;
  failed_deliveries: number;
  
  // Performance
  avg_response_time_ms: number;
  p95_response_time_ms: number;
  
  // Reliability
  success_rate: number;
  
  // By event type
  by_event: Record<WebhookEvent, {
    count: number;
    success_rate: number;
  }>;
}

// =============================================================================
// CONNECTOR FRAMEWORK
// =============================================================================

export type ConnectorType = 
  | 'bms' | 'scada' | 'historian'
  | 'cmms' | 'erp'
  | 'weather' | 'energy'
  | 'file' | 'database' | 'api'
  | 'mqtt' | 'kafka' | 'custom';

export interface ConnectorDefinition {
  connector_type: ConnectorType;
  name: string;
  description: string;
  version: string;
  
  // Capabilities
  capabilities: {
    can_read: boolean;
    can_write: boolean;
    supports_streaming: boolean;
    supports_backfill: boolean;
  };
  
  // Configuration schema
  config_schema: {
    required_fields: ConnectorField[];
    optional_fields: ConnectorField[];
  };
  
  // Supported data types
  supported_data_types: string[];
  
  // Vendor-specific
  vendor?: string;
  supported_versions?: string[];
}

export interface ConnectorField {
  name: string;
  type: 'string' | 'number' | 'boolean' | 'secret' | 'select' | 'json';
  label: string;
  description: string;
  default_value?: unknown;
  options?: Array<{ value: string; label: string }>;
  validation?: {
    required?: boolean;
    pattern?: string;
    min?: number;
    max?: number;
  };
}

export interface ConnectorInstance {
  instance_id: string;
  connector_type: ConnectorType;
  name: string;
  description?: string;
  
  // Configuration
  config: Record<string, unknown>;
  credentials_ref?: string;
  
  // Scope
  tenant_id: string;
  site_ids?: string[];
  
  // Sync settings
  sync_config: {
    enabled: boolean;
    direction: 'inbound' | 'outbound' | 'bidirectional';
    interval_minutes?: number;
    real_time?: boolean;
  };
  
  // Tag mappings
  tag_mappings: TagMappingConfig[];
  
  // Status
  status: 'active' | 'inactive' | 'error' | 'configuring';
  last_sync?: string;
  last_error?: string;
  
  // Metadata
  created_at: string;
  updated_at: string;
}

export interface TagMappingConfig {
  mapping_id: string;
  
  // Source
  source_tag: string;
  source_pattern?: string;
  
  // Target
  canonical_metric_id: string;
  asset_id?: string;
  
  // Transformation
  transformation?: {
    type: 'direct' | 'scale' | 'offset' | 'expression' | 'lookup';
    params: Record<string, unknown>;
  };
  
  // Quality
  quality_rules?: {
    valid_range?: [number, number];
    stale_threshold_seconds?: number;
  };
  
  // Status
  enabled: boolean;
  last_value?: number;
  last_quality?: string;
  last_received?: string;
}

export interface ConnectorSyncJob {
  job_id: string;
  instance_id: string;
  
  // Job type
  job_type: 'scheduled' | 'manual' | 'backfill' | 'real_time';
  
  // Time range (for backfill)
  time_range?: { start: string; end: string };
  
  // Progress
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress: {
    total_records?: number;
    processed_records: number;
    failed_records: number;
  };
  
  // Timing
  started_at?: string;
  completed_at?: string;
  
  // Errors
  errors?: Array<{
    timestamp: string;
    message: string;
    details?: Record<string, unknown>;
  }>;
}

// =============================================================================
// DATA LINEAGE
// =============================================================================

export interface DataLineage {
  lineage_id: string;
  
  // Target
  target: {
    type: 'metric' | 'case' | 'prediction' | 'report';
    id: string;
    name: string;
  };
  
  // Lineage chain
  lineage_chain: LineageNode[];
  
  // Visualization
  graph: {
    nodes: Array<{
      id: string;
      type: string;
      label: string;
      metadata: Record<string, unknown>;
    }>;
    edges: Array<{
      source: string;
      target: string;
      relationship: string;
    }>;
  };
  
  // Quality
  quality_assessment: {
    completeness: number;
    freshness: number;
    accuracy_estimate: number;
  };
  
  // Timestamps
  traced_at: string;
}

export interface LineageNode {
  node_id: string;
  node_type: 'source' | 'transformation' | 'storage' | 'model' | 'output';
  
  // Details
  name: string;
  description: string;
  
  // Source-specific
  source_details?: {
    connector_id: string;
    connector_type: ConnectorType;
    raw_tag: string;
  };
  
  // Transformation-specific
  transformation_details?: {
    type: string;
    expression?: string;
    parameters?: Record<string, unknown>;
  };
  
  // Model-specific
  model_details?: {
    model_id: string;
    model_version: string;
    feature_importance?: number;
  };
  
  // Timing
  timestamp?: string;
  latency_ms?: number;
}

// =============================================================================
// API KEYS & EXTERNAL ACCESS
// =============================================================================

export interface APIKey {
  key_id: string;
  name: string;
  description?: string;
  
  // Scope
  tenant_id: string;
  permissions: string[];
  rate_limits: {
    requests_per_minute: number;
    requests_per_day: number;
  };
  
  // IP restrictions
  allowed_ips?: string[];
  
  // Status
  status: 'active' | 'revoked' | 'expired';
  
  // Metadata
  created_at: string;
  created_by: string;
  expires_at?: string;
  last_used_at?: string;
  
  // Usage
  usage: {
    total_requests: number;
    requests_today: number;
    last_request_ip?: string;
  };
}

export interface ExternalAPIEndpoint {
  endpoint_id: string;
  path: string;
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  
  // Documentation
  summary: string;
  description: string;
  
  // Parameters
  parameters: Array<{
    name: string;
    in: 'path' | 'query' | 'header' | 'body';
    type: string;
    required: boolean;
    description: string;
  }>;
  
  // Responses
  responses: Array<{
    status_code: number;
    description: string;
    schema?: Record<string, unknown>;
  }>;
  
  // Auth
  requires_auth: boolean;
  required_permissions: string[];
  
  // Rate limits
  rate_limit_tier: 'standard' | 'high' | 'unlimited';
}

// =============================================================================
// INTEGRATION HEALTH
// =============================================================================

export interface IntegrationHealth {
  timestamp: string;
  
  // Connectors
  connectors: Array<{
    instance_id: string;
    name: string;
    status: 'healthy' | 'degraded' | 'unhealthy';
    last_sync: string;
    sync_success_rate: number;
    error_count_24h: number;
  }>;
  
  // Webhooks
  webhooks: Array<{
    webhook_id: string;
    name: string;
    status: 'healthy' | 'degraded' | 'unhealthy';
    delivery_success_rate: number;
    avg_latency_ms: number;
  }>;
  
  // API
  api: {
    status: 'healthy' | 'degraded' | 'unhealthy';
    requests_24h: number;
    error_rate: number;
    avg_latency_ms: number;
  };
  
  // Overall
  overall_status: 'healthy' | 'degraded' | 'unhealthy';
  issues: Array<{
    severity: 'critical' | 'warning' | 'info';
    component: string;
    message: string;
    since: string;
  }>;
}
