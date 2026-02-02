// AAO Entity Types

// Gap Analysis Types - P0/P1/P2 Capabilities
// Import as namespaced modules to avoid conflicts with existing types
import * as Canonical from './canonical';
import * as AlertPolicy from './alertPolicy';
import * as Uncertainty from './uncertainty';
import * as Verification from './verification';
import * as CMMS from './cmms';
import * as Dispatch from './dispatch';
import * as Explainability from './explainability';
import * as Regime from './regime';
import * as Evaluation from './evaluation';
import * as RBAC from './rbac';
import * as Integration from './integration';
import * as ModelArchitecture from './modelArchitecture';
import * as SSL from './selfSupervisedLearning';
import * as SyntheticData from './syntheticData';

export { 
  Canonical, AlertPolicy, Uncertainty, Verification, CMMS, Dispatch, 
  Explainability, Regime, Evaluation, RBAC, Integration,
  ModelArchitecture, SSL, SyntheticData 
};

// RBAC Types
export type UserRole = 'viewer' | 'operator' | 'senior_operator' | 'supervisor' | 'technician' | 'customer_admin' | 'platform_admin' | 'ml_admin';

export interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  avatar?: string;
  tenantId: string;
  permissions: string[];
}

export interface Tenant {
  id: string;
  name: string;
  industry: 'hvac' | 'refrigeration' | 'oil_gas' | 'energy';
  portfolios: Portfolio[];
}

export interface Portfolio {
  id: string;
  name: string;
  region: string;
  sites: Site[];
}

export interface Site {
  id: string;
  name: string;
  address: string;
  timezone: string;
  assets: Asset[];
}

// Asset Types
export type AssetStatus = 'normal' | 'warning' | 'critical' | 'offline' | 'maintenance';
export type AssetType = 'compressor' | 'hvac' | 'pump' | 'valve' | 'chiller' | 'ahu' | 'rtu' | 'sensor';

export interface Asset {
  id: string;
  name: string;
  type: AssetType;
  status: AssetStatus;
  siteId: string;
  location: string;
  manufacturer?: string;
  model?: string;
  serialNumber?: string;
  installDate?: string;
  lastMaintenance?: string;
  autonomyEnabled: boolean;
  metrics: AssetMetric[];
  recentAlerts: number;
  openCases: number;
}

export interface AssetMetric {
  name: string;
  value: number;
  unit: string;
  threshold?: { min?: number; max?: number };
  trend: 'up' | 'down' | 'stable';
  timestamp: string;
}

// Case Types
export type CaseSeverity = 'critical' | 'high' | 'medium' | 'low';
export type CaseStatus = 'new' | 'triaging' | 'diagnosing' | 'pending_approval' | 'executing' | 'verifying' | 'resolved' | 'closed';

export interface Case {
  id: string;
  title: string;
  description: string;
  severity: CaseSeverity;
  status: CaseStatus;
  assetId: string;
  assetName: string;
  siteId: string;
  siteName: string;
  faultType: string;
  confidence: number;
  customerImpact: 'high' | 'medium' | 'low';
  slaDue: string;
  slaStatus: 'on_track' | 'at_risk' | 'breached';
  assigneeId?: string;
  assigneeName?: string;
  createdAt: string;
  updatedAt: string;
  resolvedAt?: string;
  rootCause?: string;
  recommendedActions: RecommendedAction[];
  timeline: CaseTimelineEvent[];
}

export interface RecommendedAction {
  id: string;
  type: 'control_change' | 'work_order' | 'dispatch' | 'notify' | 'watchful_wait';
  title: string;
  description: string;
  riskTier: 'low' | 'medium' | 'high' | 'critical';
  confidence: number;
  expectedBenefit: string;
  preconditions: string[];
  constraints: string[];
  rollbackPlan: string;
  verificationPlan: string;
  status: 'pending' | 'approved' | 'rejected' | 'executed' | 'verified';
  approvalRequired: boolean;
}

export interface CaseTimelineEvent {
  id: string;
  timestamp: string;
  type: 'detection' | 'recommendation' | 'approval' | 'denial' | 'execution' | 'verification' | 'note' | 'assignment';
  actor: string;
  actorType: 'system' | 'model' | 'user';
  description: string;
  details?: Record<string, unknown>;
  modelVersion?: string;
}

// Work Order Types
export type WorkOrderStatus = 'draft' | 'submitted' | 'assigned' | 'scheduled' | 'in_progress' | 'completed' | 'verified' | 'closed';
export type WorkOrderPriority = 'emergency' | 'urgent' | 'standard' | 'planned';

export interface WorkOrder {
  id: string;
  externalId?: string;
  caseId?: string;
  title: string;
  description: string;
  priority: WorkOrderPriority;
  status: WorkOrderStatus;
  assetId: string;
  assetName: string;
  siteId: string;
  siteName: string;
  assigneeId?: string;
  assigneeName?: string;
  assigneeType: 'internal' | 'vendor';
  diagnostics: string;
  suspectedRootCause: string;
  recommendedParts: string[];
  scheduledDate?: string;
  completedDate?: string;
  verificationStatus?: 'pending' | 'passed' | 'failed';
  technicianNotes?: string;
  partsUsed?: string[];
  resolutionCode?: string;
  createdAt: string;
  updatedAt: string;
}

// Outcome Types
export interface OutcomeMetrics {
  energySavingsKwh: number;
  energySavingsCost: number;
  downtimeAvoided: number;
  incidentsAvoided: number;
  truckRollsAvoided: number;
  meanTimeToDetect: number;
  meanTimeToResolve: number;
  autonomousActionsExecuted: number;
  actionsPendingApproval: number;
  actionsBlockedByPolicy: number;
  rollbackFrequency: number;
  approvalCycleTime: number;
}

// Connector Types
export type ConnectorType = 'bms' | 'scada' | 'iot_gateway' | 'cmms' | 'ticketing' | 'messaging';
export type ConnectorStatus = 'connected' | 'degraded' | 'disconnected' | 'error';

export interface Connector {
  id: string;
  name: string;
  type: ConnectorType;
  status: ConnectorStatus;
  endpoint: string;
  lastSync: string;
  uptime: number;
  latency: number;
  errorRate: number;
  writebackEnabled: boolean;
  credentials?: {
    configured: boolean;
    lastRotated?: string;
  };
}

// Notification Types
export type NotificationType = 'approval_required' | 'escalation' | 'sla_breach' | 'incident' | 'integration_failure' | 'model_drift';

export interface Notification {
  id: string;
  type: NotificationType;
  title: string;
  message: string;
  severity: 'critical' | 'warning' | 'info';
  entityId?: string;
  entityType?: 'case' | 'asset' | 'work_order' | 'model';
  createdAt: string;
  readAt?: string;
  acknowledgedAt?: string;
  snoozedUntil?: string;
}

// Policy Types
export interface Policy {
  id: string;
  name: string;
  scope: 'global' | 'tenant' | 'site' | 'asset_group';
  scopeId?: string;
  allowedActions: string[];
  parameterBounds: Record<string, { min?: number; max?: number }>;
  riskTierMapping: Record<string, 'low' | 'medium' | 'high' | 'critical'>;
  approvalRouting: ApprovalRoute[];
  lockouts: Lockout[];
  escalationRules: EscalationRule[];
  version: number;
  updatedAt: string;
  updatedBy: string;
}

export interface ApprovalRoute {
  actionType: string;
  riskTier: 'low' | 'medium' | 'high' | 'critical';
  requiredApprovers: string[];
  twoKeyRequired: boolean;
}

export interface Lockout {
  name: string;
  condition: string;
  startTime?: string;
  endTime?: string;
  daysOfWeek?: number[];
}

export interface EscalationRule {
  condition: string;
  escalateTo: string;
  afterMinutes: number;
}
