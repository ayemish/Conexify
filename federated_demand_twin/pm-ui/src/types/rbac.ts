/**
 * Multi-Tenant RBAC + Audit Coverage Types
 * 
 * Defines tenant isolation, scoped permissions, and comprehensive
 * audit logging for all operational actions.
 * Addresses FR-023, FR-024.
 */

// =============================================================================
// TENANT & ORGANIZATION
// =============================================================================

export interface Tenant {
  tenant_id: string;
  tenant_name: string;
  tenant_type: 'enterprise' | 'regional' | 'franchise' | 'demo';
  
  // Hierarchy
  parent_tenant_id?: string;
  child_tenant_ids: string[];
  
  // Configuration
  config: {
    features_enabled: string[];
    data_retention_days: number;
    max_users: number;
    max_sites: number;
  };
  
  // Isolation
  isolation: {
    data_isolated: boolean;
    shared_models: boolean;
    custom_branding: boolean;
  };
  
  // Status
  status: 'active' | 'suspended' | 'pending' | 'decommissioned';
  created_at: string;
}

export interface Organization {
  org_id: string;
  tenant_id: string;
  org_name: string;
  org_type: 'customer' | 'service_provider' | 'partner';
  
  // Scope
  assigned_sites: string[];
  assigned_regions: string[];
  
  // Settings
  settings: {
    timezone: string;
    locale: string;
    notification_preferences: Record<string, boolean>;
  };
}

// =============================================================================
// USERS & ROLES
// =============================================================================

export interface User {
  user_id: string;
  tenant_id: string;
  org_id?: string;
  
  // Identity
  email: string;
  display_name: string;
  
  // Roles
  roles: UserRole[];
  
  // Scope restrictions
  scope: UserScope;
  
  // Status
  status: 'active' | 'inactive' | 'locked' | 'pending_activation';
  last_login?: string;
  created_at: string;
}

export interface UserRole {
  role_id: string;
  role_name: string;
  assigned_at: string;
  assigned_by: string;
  expires_at?: string;
  
  // Scope for this role assignment
  scope_type: 'global' | 'tenant' | 'org' | 'region' | 'site';
  scope_ids: string[];
}

export interface UserScope {
  // What the user can see/access
  tenant_ids: string[];
  org_ids: string[];
  region_ids: string[];
  site_ids: string[];
  asset_ids?: string[];  // For very granular access
  
  // Scope mode
  mode: 'explicit' | 'inherited' | 'all_in_tenant';
}

// =============================================================================
// ROLES & PERMISSIONS
// =============================================================================

export interface Role {
  role_id: string;
  role_name: string;
  description: string;
  
  // Type
  role_type: 'system' | 'custom';
  tenant_id?: string;  // null for system roles
  
  // Permissions
  permissions: Permission[];
  
  // Hierarchy
  inherits_from?: string[];
  
  // Metadata
  created_at: string;
  updated_at: string;
}

export interface Permission {
  permission_id: string;
  
  // Resource
  resource_type: ResourceType;
  resource_scope: 'all' | 'owned' | 'scoped';
  
  // Actions
  actions: PermissionAction[];
  
  // Conditions (optional fine-grained control)
  conditions?: PermissionCondition[];
}

export type ResourceType = 
  | 'case' | 'work_order' | 'alert' | 'asset' | 'site'
  | 'model' | 'experiment' | 'retraining_job'
  | 'approval' | 'policy' | 'threshold'
  | 'user' | 'role' | 'tenant' | 'org'
  | 'report' | 'dashboard' | 'audit_log'
  | 'integration' | 'webhook' | 'api_key';

export type PermissionAction = 
  | 'create' | 'read' | 'update' | 'delete'
  | 'approve' | 'reject' | 'assign' | 'dispatch'
  | 'promote' | 'rollback' | 'configure'
  | 'export' | 'import';

export interface PermissionCondition {
  field: string;
  operator: 'eq' | 'ne' | 'in' | 'not_in' | 'gt' | 'lt';
  value: string | number | string[];
}

// =============================================================================
// PREDEFINED ROLES
// =============================================================================

export const SYSTEM_ROLES = {
  SUPER_ADMIN: 'super_admin',
  TENANT_ADMIN: 'tenant_admin',
  ORG_ADMIN: 'org_admin',
  OPERATIONS_MANAGER: 'operations_manager',
  DISPATCHER: 'dispatcher',
  OPERATOR: 'operator',
  TECHNICIAN: 'technician',
  DATA_SCIENTIST: 'data_scientist',
  ANALYST: 'analyst',
  VIEWER: 'viewer',
} as const;

export interface RoleDefinition {
  role_id: string;
  name: string;
  description: string;
  permissions_summary: string[];
}

export const ROLE_DEFINITIONS: RoleDefinition[] = [
  {
    role_id: 'super_admin',
    name: 'Super Admin',
    description: 'Full system access across all tenants',
    permissions_summary: ['All resources', 'All actions', 'All scopes'],
  },
  {
    role_id: 'tenant_admin',
    name: 'Tenant Admin',
    description: 'Full access within tenant',
    permissions_summary: ['All tenant resources', 'User management', 'Configuration'],
  },
  {
    role_id: 'operations_manager',
    name: 'Operations Manager',
    description: 'Manage cases, dispatch, and approvals',
    permissions_summary: ['Cases', 'Work orders', 'Approvals', 'Reports'],
  },
  {
    role_id: 'dispatcher',
    name: 'Dispatcher',
    description: 'Assign and schedule work orders',
    permissions_summary: ['Cases (read)', 'Work orders (full)', 'Technicians (assign)'],
  },
  {
    role_id: 'operator',
    name: 'Operator',
    description: 'Triage alerts and manage cases',
    permissions_summary: ['Alerts', 'Cases', 'Assets (read)'],
  },
  {
    role_id: 'technician',
    name: 'Technician',
    description: 'View and complete assigned work',
    permissions_summary: ['Assigned work orders', 'Case details (read)', 'Completion'],
  },
  {
    role_id: 'data_scientist',
    name: 'Data Scientist',
    description: 'Manage models, experiments, and analytics',
    permissions_summary: ['Models', 'Experiments', 'Retraining', 'Metrics'],
  },
  {
    role_id: 'viewer',
    name: 'Viewer',
    description: 'Read-only access to dashboards',
    permissions_summary: ['Dashboards (read)', 'Reports (read)'],
  },
];

// =============================================================================
// ACCESS CONTROL EVALUATION
// =============================================================================

export interface AccessCheckRequest {
  user_id: string;
  resource_type: ResourceType;
  resource_id?: string;
  action: PermissionAction;
  context?: Record<string, unknown>;
}

export interface AccessCheckResult {
  allowed: boolean;
  
  // Reason
  reason: 'permission_granted' | 'permission_denied' | 'scope_denied' | 'condition_failed';
  
  // Details
  details: {
    matching_role?: string;
    matching_permission?: string;
    failed_condition?: string;
    scope_violation?: string;
  };
  
  // For auditing
  evaluated_at: string;
  evaluation_duration_ms: number;
}

// =============================================================================
// COMPREHENSIVE AUDIT LOG
// =============================================================================

export type AuditAction = 
  // Operational
  | 'case_created' | 'case_updated' | 'case_closed' | 'case_reopened'
  | 'alert_acknowledged' | 'alert_silenced'
  | 'work_order_created' | 'work_order_dispatched' | 'work_order_completed'
  | 'approval_requested' | 'approval_granted' | 'approval_denied'
  
  // Model management
  | 'model_deployed' | 'model_promoted' | 'model_rolled_back'
  | 'experiment_started' | 'experiment_concluded'
  | 'retraining_triggered' | 'retraining_completed'
  
  // Configuration
  | 'policy_created' | 'policy_updated' | 'policy_deleted'
  | 'threshold_changed' | 'config_changed'
  
  // User management
  | 'user_created' | 'user_updated' | 'user_deactivated'
  | 'role_assigned' | 'role_revoked'
  | 'login' | 'logout' | 'login_failed'
  
  // Integration
  | 'webhook_created' | 'webhook_triggered'
  | 'api_key_created' | 'api_key_revoked'
  | 'integration_synced';

export interface AuditLogEntry {
  entry_id: string;
  timestamp: string;
  
  // Who
  actor: {
    type: 'user' | 'system' | 'integration' | 'scheduled';
    id: string;
    name?: string;
    ip_address?: string;
    user_agent?: string;
  };
  
  // What
  action: AuditAction;
  action_category: 'operational' | 'model' | 'config' | 'user' | 'integration' | 'security';
  
  // On what
  resource: {
    type: ResourceType;
    id: string;
    name?: string;
  };
  
  // Context
  context: {
    tenant_id: string;
    org_id?: string;
    site_id?: string;
  };
  
  // Details
  details: {
    description: string;
    before?: Record<string, unknown>;
    after?: Record<string, unknown>;
    metadata?: Record<string, unknown>;
  };
  
  // Outcome
  outcome: 'success' | 'failure' | 'partial';
  error_message?: string;
  
  // Flags
  flags: {
    is_sensitive: boolean;
    requires_review: boolean;
    is_compliance_relevant: boolean;
  };
}

export interface AuditLogQuery {
  // Time range
  start_time: string;
  end_time: string;
  
  // Filters
  filters?: {
    actor_ids?: string[];
    actions?: AuditAction[];
    action_categories?: string[];
    resource_types?: ResourceType[];
    resource_ids?: string[];
    tenant_ids?: string[];
    outcomes?: string[];
    flags?: Partial<Record<string, boolean>>;
  };
  
  // Pagination
  page: number;
  page_size: number;
  
  // Sort
  sort_by: 'timestamp' | 'action' | 'actor';
  sort_order: 'asc' | 'desc';
}

export interface AuditLogSummary {
  period: { start: string; end: string };
  
  // Totals
  total_entries: number;
  
  // By category
  by_category: Record<string, number>;
  
  // By action
  by_action: Record<string, number>;
  
  // By outcome
  by_outcome: Record<string, number>;
  
  // Top actors
  top_actors: Array<{
    actor_id: string;
    actor_name: string;
    action_count: number;
  }>;
  
  // Anomalies
  anomalies: Array<{
    description: string;
    severity: 'high' | 'medium' | 'low';
    timestamp: string;
  }>;
}
