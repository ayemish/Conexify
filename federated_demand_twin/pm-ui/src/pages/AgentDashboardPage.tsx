import { useState, useEffect, useRef } from 'react';
import {
  Bot, CheckCircle, Clock, AlertTriangle, Send, RefreshCw,
  ThumbsUp, ThumbsDown, Activity, MessageSquare, Settings,
  Zap, Shield, Wrench, TrendingUp, Database, FlaskConical,
  ChevronRight, ChevronDown, Users, Bell, X
} from 'lucide-react';

// =============================================================================
// TYPES
// =============================================================================

interface AgentStatus {
  agent_id: string;
  role: string;
  pending_actions: number;
  completed_actions: number;
  beliefs: number;
  last_activity: string | null;
}

interface PendingApproval {
  approval_id: string;
  action_type: string;
  agent_id: string;
  description: string;
  priority: string;
  created_at: string;
  expires_at: string | null;
  payload: Record<string, unknown>;
}

interface AgentEvent {
  event_id: string;
  event_type: string;
  source_agent: string;
  timestamp: string;
  payload: Record<string, unknown>;
  case_id?: string;
  asset_id?: string;
  site_id?: string;
}

interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  data?: Record<string, unknown>;
  actions?: Array<{ type: string; label: string }>;
}

// =============================================================================
// MOCK DATA
// =============================================================================

const mockAgentStatuses: AgentStatus[] = [
  { agent_id: 'case_triage_agent', role: 'Case Triage', pending_actions: 3, completed_actions: 47, beliefs: 12, last_activity: '2024-01-28T14:32:00Z' },
  { agent_id: 'evidence_to_action_agent', role: 'Evidence-to-Action', pending_actions: 1, completed_actions: 38, beliefs: 8, last_activity: '2024-01-28T14:30:00Z' },
  { agent_id: 'work_order_composer_agent', role: 'Work Order Composer', pending_actions: 2, completed_actions: 35, beliefs: 5, last_activity: '2024-01-28T14:28:00Z' },
  { agent_id: 'dispatch_batching_agent', role: 'Dispatch Optimizer', pending_actions: 0, completed_actions: 22, beliefs: 15, last_activity: '2024-01-28T14:25:00Z' },
  { agent_id: 'verification_agent', role: 'Verification', pending_actions: 4, completed_actions: 31, beliefs: 7, last_activity: '2024-01-28T14:20:00Z' },
  { agent_id: 'experimentation_agent', role: 'Model Governance', pending_actions: 1, completed_actions: 12, beliefs: 3, last_activity: '2024-01-28T14:15:00Z' },
  { agent_id: 'data_steward_agent', role: 'Data Steward', pending_actions: 2, completed_actions: 28, beliefs: 9, last_activity: '2024-01-28T14:10:00Z' },
];

const mockPendingApprovals: PendingApproval[] = [
  {
    approval_id: 'apr-001',
    action_type: 'submit_work_order',
    agent_id: 'work_order_composer_agent',
    description: 'Submit work order for compressor anomaly at Site A-142',
    priority: 'high',
    created_at: '2024-01-28T14:00:00Z',
    expires_at: '2024-01-29T14:00:00Z',
    payload: { work_order_id: 'WO-2024-0142', case_id: 'CASE-2024-0089' },
  },
  {
    approval_id: 'apr-002',
    action_type: 'promote_model',
    agent_id: 'experimentation_agent',
    description: 'Promote failure prediction model v1.4.0 to production',
    priority: 'high',
    created_at: '2024-01-28T13:45:00Z',
    expires_at: '2024-01-29T13:45:00Z',
    payload: { model_id: 'fp-v1.4.0', improvement: '+8.2% F1' },
  },
  {
    approval_id: 'apr-003',
    action_type: 'triage_case',
    agent_id: 'case_triage_agent',
    description: 'Dispatch technician for critical refrigeration alert',
    priority: 'critical',
    created_at: '2024-01-28T14:20:00Z',
    expires_at: '2024-01-28T18:20:00Z',
    payload: { case_id: 'CASE-2024-0091', severity: 'critical' },
  },
];

const mockEvents: AgentEvent[] = [
  { event_id: 'evt-001', event_type: 'case.triaged', source_agent: 'case_triage_agent', timestamp: '2024-01-28T14:32:00Z', payload: { decision: 'dispatch' }, case_id: 'CASE-2024-0091' },
  { event_id: 'evt-002', event_type: 'maintenance.packet_created', source_agent: 'evidence_to_action_agent', timestamp: '2024-01-28T14:30:00Z', payload: { packet_id: 'PKT-001' }, case_id: 'CASE-2024-0089' },
  { event_id: 'evt-003', event_type: 'work_order.drafted', source_agent: 'work_order_composer_agent', timestamp: '2024-01-28T14:28:00Z', payload: { priority: 'urgent' }, case_id: 'CASE-2024-0089' },
  { event_id: 'evt-004', event_type: 'dispatch.batch_created', source_agent: 'dispatch_batching_agent', timestamp: '2024-01-28T14:25:00Z', payload: { batch_size: 3, savings: 300 }, site_id: 'SITE-A-142' },
  { event_id: 'evt-005', event_type: 'verification.started', source_agent: 'verification_agent', timestamp: '2024-01-28T14:20:00Z', payload: { window_hours: 24 }, case_id: 'CASE-2024-0085' },
  { event_id: 'evt-006', event_type: 'data.quality_issue', source_agent: 'data_steward_agent', timestamp: '2024-01-28T14:10:00Z', payload: { severity: 'medium' }, asset_id: 'ASSET-0234' },
];

const mockConversation: ChatMessage[] = [
  { role: 'system', content: 'PdM Assistant ready. How can I help you today?', timestamp: '2024-01-28T14:00:00Z' },
];

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

function getAgentIcon(role: string) {
  const roleMap: Record<string, typeof Bot> = {
    'Case Triage': Shield,
    'Evidence-to-Action': Zap,
    'Work Order Composer': Wrench,
    'Dispatch Optimizer': TrendingUp,
    'Verification': CheckCircle,
    'Model Governance': FlaskConical,
    'Data Steward': Database,
  };
  return roleMap[role] || Bot;
}

function getPriorityColor(priority: string) {
  const colors: Record<string, string> = {
    critical: 'bg-red-100 text-red-700 border-red-200',
    high: 'bg-orange-100 text-orange-700 border-orange-200',
    medium: 'bg-amber-100 text-amber-700 border-amber-200',
    low: 'bg-slate-100 text-slate-600 border-slate-200',
  };
  return colors[priority] || colors.medium;
}

function getEventTypeLabel(eventType: string) {
  const labels: Record<string, string> = {
    'case.triaged': 'Case Triaged',
    'case.created': 'Case Created',
    'maintenance.packet_created': 'Maintenance Packet',
    'work_order.drafted': 'Work Order Drafted',
    'dispatch.batch_created': 'Dispatch Batch',
    'verification.started': 'Verification Started',
    'verification.passed': 'Verification Passed',
    'verification.failed': 'Verification Failed',
    'data.quality_issue': 'Data Quality Issue',
    'model.promotion_requested': 'Model Promotion',
  };
  return labels[eventType] || eventType.replace(/\./g, ' ').replace(/_/g, ' ');
}

function formatTimeAgo(timestamp: string) {
  const diff = Date.now() - new Date(timestamp).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

// =============================================================================
// COMPONENTS
// =============================================================================

function AgentCard({ agent }: { agent: AgentStatus }) {
  const Icon = getAgentIcon(agent.role);
  const isActive = agent.pending_actions > 0;
  
  return (
    <div className={`bg-white rounded-xl border p-4 ${isActive ? 'border-orange-200 bg-orange-50/50' : 'border-slate-200'}`}>
      <div className="flex items-start gap-3">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${isActive ? 'bg-orange-100' : 'bg-slate-100'}`}>
          <Icon className={`w-5 h-5 ${isActive ? 'text-orange-600' : 'text-slate-600'}`} />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="font-medium text-slate-900 truncate">{agent.role}</h3>
          <p className="text-xs text-slate-500">
            {agent.last_activity ? formatTimeAgo(agent.last_activity) : 'No activity'}
          </p>
        </div>
        {agent.pending_actions > 0 && (
          <span className="px-2 py-1 bg-orange-500 text-white text-xs font-medium rounded-full">
            {agent.pending_actions}
          </span>
        )}
      </div>
      <div className="mt-3 flex items-center gap-4 text-xs text-slate-500">
        <span>{agent.completed_actions} completed</span>
        <span>{agent.beliefs} beliefs</span>
      </div>
    </div>
  );
}

function ApprovalCard({ 
  approval, 
  onApprove, 
  onReject 
}: { 
  approval: PendingApproval; 
  onApprove: () => void; 
  onReject: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  
  return (
    <div className={`bg-white rounded-xl border p-4 ${getPriorityColor(approval.priority)}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className={`px-2 py-0.5 text-xs font-medium rounded ${getPriorityColor(approval.priority)}`}>
              {approval.priority}
            </span>
            <span className="text-xs text-slate-500">
              {approval.action_type.replace(/_/g, ' ')}
            </span>
          </div>
          <p className="text-sm font-medium text-slate-900">{approval.description}</p>
          <p className="text-xs text-slate-500 mt-1">
            From: {approval.agent_id.replace(/_/g, ' ')} • {formatTimeAgo(approval.created_at)}
          </p>
        </div>
      </div>
      
      <button 
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700 mt-2"
      >
        {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        {expanded ? 'Hide details' : 'Show details'}
      </button>
      
      {expanded && (
        <div className="mt-2 p-2 bg-slate-50 rounded-lg text-xs">
          <pre className="whitespace-pre-wrap text-slate-600">
            {JSON.stringify(approval.payload, null, 2)}
          </pre>
        </div>
      )}
      
      <div className="flex items-center gap-2 mt-3">
        <button
          onClick={onApprove}
          className="flex-1 flex items-center justify-center gap-1 px-3 py-2 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700"
        >
          <ThumbsUp className="w-4 h-4" />
          Approve
        </button>
        <button
          onClick={onReject}
          className="flex-1 flex items-center justify-center gap-1 px-3 py-2 bg-slate-200 text-slate-700 text-sm font-medium rounded-lg hover:bg-slate-300"
        >
          <ThumbsDown className="w-4 h-4" />
          Reject
        </button>
      </div>
    </div>
  );
}

function EventFeed({ events }: { events: AgentEvent[] }) {
  return (
    <div className="space-y-2">
      {events.map((event) => (
        <div key={event.event_id} className="flex items-start gap-3 p-3 bg-slate-50 rounded-lg">
          <div className="w-2 h-2 rounded-full bg-blue-500 mt-2" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-900">
              {getEventTypeLabel(event.event_type)}
            </p>
            <p className="text-xs text-slate-500">
              {event.source_agent.replace(/_/g, ' ')} • {formatTimeAgo(event.timestamp)}
            </p>
            {event.case_id && (
              <span className="inline-block mt-1 px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded">
                {event.case_id}
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function ChatInterface({ 
  messages, 
  onSendMessage 
}: { 
  messages: ChatMessage[]; 
  onSendMessage: (message: string) => void;
}) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  const handleSend = () => {
    if (input.trim()) {
      onSendMessage(input.trim());
      setInput('');
    }
  };
  
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);
  
  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.filter(m => m.role !== 'system').map((message, idx) => (
          <div 
            key={idx}
            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div className={`max-w-[80%] rounded-xl p-3 ${
              message.role === 'user' 
                ? 'bg-orange-500 text-white' 
                : 'bg-slate-100 text-slate-900'
            }`}>
              <p className="text-sm whitespace-pre-wrap">{message.content}</p>
              {message.data && (
                <div className="mt-2 p-2 bg-white/20 rounded-lg text-xs">
                  <pre className="whitespace-pre-wrap overflow-x-auto">
                    {JSON.stringify(message.data, null, 2)}
                  </pre>
                </div>
              )}
              {message.actions && message.actions.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {message.actions.map((action, i) => (
                    <button 
                      key={i}
                      className="px-2 py-1 bg-white/20 hover:bg-white/30 rounded text-xs"
                    >
                      {action.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>
      
      <div className="border-t border-slate-200 p-4">
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder="Ask about agents, approvals, cases..."
            className="flex-1 px-4 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-orange-500"
          />
          <button
            onClick={handleSend}
            className="p-2 bg-orange-500 text-white rounded-xl hover:bg-orange-600"
          >
            <Send className="w-5 h-5" />
          </button>
        </div>
        <div className="flex flex-wrap gap-2 mt-2">
          {['Pending approvals?', 'Agent status', 'Data quality', 'Dispatch batches'].map((suggestion) => (
            <button
              key={suggestion}
              onClick={() => onSendMessage(suggestion)}
              className="px-2 py-1 bg-slate-100 hover:bg-slate-200 text-slate-600 text-xs rounded-lg"
            >
              {suggestion}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// MAIN PAGE
// =============================================================================

export default function AgentDashboardPage() {
  const [agents, setAgents] = useState<AgentStatus[]>(mockAgentStatuses);
  const [approvals, setApprovals] = useState<PendingApproval[]>(mockPendingApprovals);
  const [events, setEvents] = useState<AgentEvent[]>(mockEvents);
  const [messages, setMessages] = useState<ChatMessage[]>(mockConversation);
  const [activeTab, setActiveTab] = useState<'approvals' | 'activity' | 'chat'>('approvals');
  const [showChat, setShowChat] = useState(false);

  const handleApprove = (approvalId: string) => {
    setApprovals(prev => prev.filter(a => a.approval_id !== approvalId));
    // In production, this would call the API
  };

  const handleReject = (approvalId: string) => {
    setApprovals(prev => prev.filter(a => a.approval_id !== approvalId));
    // In production, this would call the API
  };

  const handleSendMessage = (message: string) => {
    // Add user message
    setMessages(prev => [...prev, {
      role: 'user',
      content: message,
      timestamp: new Date().toISOString(),
    }]);
    
    // Simulate response (in production, this would call the API)
    setTimeout(() => {
      let response: ChatMessage = {
        role: 'assistant',
        content: '',
        timestamp: new Date().toISOString(),
      };
      
      if (message.toLowerCase().includes('approval')) {
        response.content = `There are ${approvals.length} pending approvals:\n${approvals.map(a => `• ${a.description}`).join('\n')}`;
        response.data = { count: approvals.length };
      } else if (message.toLowerCase().includes('agent') || message.toLowerCase().includes('status')) {
        response.content = `All ${agents.length} agents are operational. ${agents.filter(a => a.pending_actions > 0).length} have pending actions.`;
        response.data = { agents: agents.map(a => ({ role: a.role, pending: a.pending_actions })) };
      } else if (message.toLowerCase().includes('data quality')) {
        response.content = 'The Data Steward agent is tracking 2 active data quality issues. Both are medium severity and under investigation.';
      } else if (message.toLowerCase().includes('dispatch') || message.toLowerCase().includes('batch')) {
        response.content = 'The Dispatch Optimizer has created 1 batch today combining 3 work orders at Site A-142, saving an estimated $300 in truck rolls.';
      } else {
        response.content = 'I can help you with pending approvals, agent status, data quality issues, and dispatch batches. What would you like to know?';
      }
      
      setMessages(prev => [...prev, response]);
    }, 500);
  };

  const totalPending = agents.reduce((sum, a) => sum + a.pending_actions, 0);

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Agent Control Center</h1>
          <p className="text-slate-500">Multi-agent orchestration for predictive maintenance</p>
        </div>
        <div className="flex items-center gap-3">
          <button 
            onClick={() => setShowChat(!showChat)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg ${
              showChat ? 'bg-orange-100 text-orange-700' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
            }`}
          >
            <MessageSquare className="w-4 h-4" />
            Chat
          </button>
          <button className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700">
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border border-slate-200 p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
              <Bot className="w-5 h-5 text-green-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{agents.length}</p>
              <p className="text-sm text-slate-500">Active Agents</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl border border-orange-200 bg-orange-50 p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-orange-100 rounded-lg flex items-center justify-center">
              <Clock className="w-5 h-5 text-orange-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-orange-700">{approvals.length}</p>
              <p className="text-sm text-orange-600">Pending Approvals</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
              <Activity className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{totalPending}</p>
              <p className="text-sm text-slate-500">Pending Actions</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
              <CheckCircle className="w-5 h-5 text-purple-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">
                {agents.reduce((sum, a) => sum + a.completed_actions, 0)}
              </p>
              <p className="text-sm text-slate-500">Completed Today</p>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-3 gap-6">
        {/* Agents Column */}
        <div className="col-span-1">
          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <h2 className="font-semibold text-slate-900 mb-4 flex items-center gap-2">
              <Users className="w-5 h-5 text-slate-400" />
              Agent Fleet
            </h2>
            <div className="space-y-3">
              {agents.map((agent) => (
                <AgentCard key={agent.agent_id} agent={agent} />
              ))}
            </div>
          </div>
        </div>

        {/* Approvals & Activity Column */}
        <div className="col-span-2">
          {/* Tabs */}
          <div className="flex gap-2 mb-4">
            <button
              onClick={() => setActiveTab('approvals')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium ${
                activeTab === 'approvals'
                  ? 'bg-orange-100 text-orange-700'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              <Bell className="w-4 h-4" />
              Approvals
              {approvals.length > 0 && (
                <span className="px-2 py-0.5 bg-orange-500 text-white text-xs rounded-full">
                  {approvals.length}
                </span>
              )}
            </button>
            <button
              onClick={() => setActiveTab('activity')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium ${
                activeTab === 'activity'
                  ? 'bg-blue-100 text-blue-700'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              <Activity className="w-4 h-4" />
              Activity Feed
            </button>
          </div>

          {/* Tab Content */}
          <div className="bg-white rounded-xl border border-slate-200 p-4">
            {activeTab === 'approvals' && (
              <div className="space-y-4">
                {approvals.length === 0 ? (
                  <div className="text-center py-8 text-slate-500">
                    <CheckCircle className="w-12 h-12 mx-auto mb-3 text-green-500" />
                    <p>All caught up! No pending approvals.</p>
                  </div>
                ) : (
                  approvals.map((approval) => (
                    <ApprovalCard
                      key={approval.approval_id}
                      approval={approval}
                      onApprove={() => handleApprove(approval.approval_id)}
                      onReject={() => handleReject(approval.approval_id)}
                    />
                  ))
                )}
              </div>
            )}
            {activeTab === 'activity' && (
              <EventFeed events={events} />
            )}
          </div>
        </div>
      </div>

      {/* Chat Drawer */}
      {showChat && (
        <div className="fixed right-0 top-0 h-full w-96 bg-white border-l border-slate-200 shadow-xl z-50 flex flex-col">
          <div className="flex items-center justify-between p-4 border-b border-slate-200">
            <div className="flex items-center gap-2">
              <Bot className="w-5 h-5 text-orange-500" />
              <h3 className="font-semibold text-slate-900">PdM Assistant</h3>
            </div>
            <button onClick={() => setShowChat(false)} className="p-1 hover:bg-slate-100 rounded">
              <X className="w-5 h-5 text-slate-400" />
            </button>
          </div>
          <div className="flex-1 overflow-hidden">
            <ChatInterface messages={messages} onSendMessage={handleSendMessage} />
          </div>
        </div>
      )}
    </div>
  );
}
