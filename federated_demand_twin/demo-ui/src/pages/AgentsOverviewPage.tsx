import { useState, useEffect } from 'react';
import { 
  Users, Database, BarChart3, Play, Settings, Shield, MessageSquare,
  CheckCircle, Clock, AlertTriangle, Activity, RefreshCw, Search,
  ChevronDown, ChevronRight, Cpu, Zap, Target, TrendingUp, Box,
  FileCheck, Scale, PieChart, Layers, Factory, Truck, AlertOctagon,
  FileText, ShoppingCart, DollarSign, Package, Gauge, Workflow
} from 'lucide-react';

// Agent Category definitions
type AgentCategory = 'data' | 'analytics' | 'simulation' | 'optimization' | 'governance' | 'communication';

interface AgentDefinition {
  id: string;
  name: string;
  role: string;
  category: AgentCategory;
  ecosystem: string;
  description: string;
  goal: string;
  status: 'active' | 'idle' | 'working' | 'error';
  lastActivity?: string;
  tasksCompleted?: number;
  avgResponseTime?: number;
}

interface CategoryInfo {
  name: string;
  icon: typeof Users;
  color: string;
  bgColor: string;
  borderColor: string;
  description: string;
}

const categoryConfig: Record<AgentCategory, CategoryInfo> = {
  data: {
    name: 'Data Agents',
    icon: Database,
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-200',
    description: 'Data quality, validation, and transformation'
  },
  analytics: {
    name: 'Analytics Agents',
    icon: BarChart3,
    color: 'text-purple-600',
    bgColor: 'bg-purple-50',
    borderColor: 'border-purple-200',
    description: 'Attribution, elasticity, and forecasting'
  },
  simulation: {
    name: 'Simulation Agents',
    icon: Play,
    color: 'text-emerald-600',
    bgColor: 'bg-emerald-50',
    borderColor: 'border-emerald-200',
    description: 'Digital Twin and scenario generation'
  },
  optimization: {
    name: 'Optimization Agents',
    icon: Target,
    color: 'text-amber-600',
    bgColor: 'bg-amber-50',
    borderColor: 'border-amber-200',
    description: 'Budget allocation and resource planning'
  },
  governance: {
    name: 'Governance Agents',
    icon: Shield,
    color: 'text-red-600',
    bgColor: 'bg-red-50',
    borderColor: 'border-red-200',
    description: 'Policy validation and compliance'
  },
  communication: {
    name: 'Communication Agents',
    icon: MessageSquare,
    color: 'text-indigo-600',
    bgColor: 'bg-indigo-50',
    borderColor: 'border-indigo-200',
    description: 'Reporting and rationale generation'
  },
};

const ecosystemConfig: Record<string, { name: string; icon: typeof Users; color: string }> = {
  core: { name: 'Core Platform', icon: Cpu, color: 'text-slate-600' },
  rmn: { name: 'Retail Media Network', icon: ShoppingCart, color: 'text-blue-600' },
  demand_procurement: { name: 'Demand & Procurement', icon: Package, color: 'text-green-600' },
  oil_gas: { name: 'Oil & Gas / Predictive Maintenance', icon: Factory, color: 'text-orange-600' },
  tee: { name: 'TEE / Data Federation', icon: Shield, color: 'text-purple-600' },
};

function StatusBadge({ status }: { status: AgentDefinition['status'] }) {
  const config = {
    active: { icon: CheckCircle, color: 'text-green-600', bg: 'bg-green-100', label: 'Active' },
    idle: { icon: Clock, color: 'text-slate-500', bg: 'bg-slate-100', label: 'Idle' },
    working: { icon: Activity, color: 'text-amber-600', bg: 'bg-amber-100', label: 'Working' },
    error: { icon: AlertTriangle, color: 'text-red-600', bg: 'bg-red-100', label: 'Error' },
  }[status];

  const Icon = config.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full ${config.bg} ${config.color}`}>
      <Icon className={`w-3 h-3 ${status === 'working' ? 'animate-pulse' : ''}`} />
      {config.label}
    </span>
  );
}

function AgentCard({ agent, expanded, onToggle }: { 
  agent: AgentDefinition; 
  expanded: boolean; 
  onToggle: () => void 
}) {
  const category = categoryConfig[agent.category];
  const ecosystem = ecosystemConfig[agent.ecosystem] || ecosystemConfig.core;
  const EcosystemIcon = ecosystem.icon;

  return (
    <div className={`bg-white rounded-lg border ${category.borderColor} shadow-sm overflow-hidden`}>
      <div 
        className={`p-4 cursor-pointer hover:bg-slate-50 transition-colors`}
        onClick={onToggle}
      >
        <div className="flex items-start gap-3">
          <div className={`p-2 rounded-lg ${category.bgColor}`}>
            <Cpu className={`w-5 h-5 ${category.color}`} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h4 className="font-semibold text-slate-900">{agent.name}</h4>
              <StatusBadge status={agent.status} />
            </div>
            <p className="text-sm text-slate-500 truncate">{agent.role}</p>
            <div className="flex items-center gap-2 mt-2">
              <span className={`inline-flex items-center gap-1 text-xs ${ecosystem.color}`}>
                <EcosystemIcon className="w-3 h-3" />
                {ecosystem.name}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {expanded ? <ChevronDown className="w-5 h-5 text-slate-400" /> : <ChevronRight className="w-5 h-5 text-slate-400" />}
          </div>
        </div>
      </div>
      
      {expanded && (
        <div className="px-4 pb-4 border-t border-slate-100">
          <div className="pt-4 space-y-4">
            <div>
              <p className="text-xs font-medium text-slate-500 mb-1">Goal</p>
              <p className="text-sm text-slate-700">{agent.goal}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500 mb-1">Description</p>
              <p className="text-sm text-slate-600">{agent.description}</p>
            </div>
            <div className="grid grid-cols-3 gap-4 pt-2">
              <div className="p-3 bg-slate-50 rounded-lg">
                <p className="text-xs text-slate-500">Tasks Completed</p>
                <p className="text-lg font-bold text-slate-900">{agent.tasksCompleted || 0}</p>
              </div>
              <div className="p-3 bg-slate-50 rounded-lg">
                <p className="text-xs text-slate-500">Avg Response</p>
                <p className="text-lg font-bold text-slate-900">{agent.avgResponseTime || 0}ms</p>
              </div>
              <div className="p-3 bg-slate-50 rounded-lg">
                <p className="text-xs text-slate-500">Last Activity</p>
                <p className="text-sm font-medium text-slate-700">{agent.lastActivity || 'Never'}</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CategorySection({ 
  category, 
  agents, 
  expandedAgents, 
  onToggleAgent 
}: { 
  category: AgentCategory;
  agents: AgentDefinition[];
  expandedAgents: Set<string>;
  onToggleAgent: (id: string) => void;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const config = categoryConfig[category];
  const Icon = config.icon;
  
  const activeCount = agents.filter(a => a.status === 'active' || a.status === 'working').length;

  return (
    <div className="mb-8">
      <div 
        className={`flex items-center gap-3 mb-4 cursor-pointer`}
        onClick={() => setCollapsed(!collapsed)}
      >
        <div className={`p-2 rounded-lg ${config.bgColor}`}>
          <Icon className={`w-6 h-6 ${config.color}`} />
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-bold text-slate-900">{config.name}</h2>
            <span className="px-2 py-0.5 text-xs font-medium bg-slate-100 text-slate-600 rounded-full">
              {agents.length} agents
            </span>
            {activeCount > 0 && (
              <span className="px-2 py-0.5 text-xs font-medium bg-green-100 text-green-700 rounded-full">
                {activeCount} active
              </span>
            )}
          </div>
          <p className="text-sm text-slate-500">{config.description}</p>
        </div>
        {collapsed ? <ChevronRight className="w-5 h-5 text-slate-400" /> : <ChevronDown className="w-5 h-5 text-slate-400" />}
      </div>
      
      {!collapsed && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {agents.map(agent => (
            <AgentCard 
              key={agent.id} 
              agent={agent}
              expanded={expandedAgents.has(agent.id)}
              onToggle={() => onToggleAgent(agent.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function AgentsOverviewPage() {
  const [agents, setAgents] = useState<AgentDefinition[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedEcosystem, setSelectedEcosystem] = useState<string>('all');
  const [expandedAgents, setExpandedAgents] = useState<Set<string>>(new Set());

  const fetchAgents = async () => {
    try {
      const res = await fetch('/api/agents/overview');
      if (res.ok) {
        const data = await res.json();
        setAgents(data.agents);
      }
    } catch (err) {
      console.error('Failed to fetch agents:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAgents();
    const interval = setInterval(fetchAgents, 10000);
    return () => clearInterval(interval);
  }, []);

  const toggleAgent = (id: string) => {
    setExpandedAgents(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const filteredAgents = agents.filter(agent => {
    const matchesSearch = searchQuery === '' || 
      agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.role.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.description.toLowerCase().includes(searchQuery.toLowerCase());
    
    const matchesEcosystem = selectedEcosystem === 'all' || agent.ecosystem === selectedEcosystem;
    
    return matchesSearch && matchesEcosystem;
  });

  const agentsByCategory = filteredAgents.reduce((acc, agent) => {
    if (!acc[agent.category]) {
      acc[agent.category] = [];
    }
    acc[agent.category].push(agent);
    return acc;
  }, {} as Record<AgentCategory, AgentDefinition[]>);

  const totalActive = agents.filter(a => a.status === 'active' || a.status === 'working').length;
  const totalTasks = agents.reduce((sum, a) => sum + (a.tasksCompleted || 0), 0);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-indigo-600 animate-spin" />
        <span className="ml-2 text-slate-600">Loading Agents...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-3">
            <Users className="w-8 h-8 text-indigo-600" />
            Agents Overview
          </h1>
          <p className="text-slate-500 mt-1">All AI agents in the Federated Demand Twin system organized by activity</p>
        </div>
        <button 
          onClick={fetchAgents}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border border-slate-200 p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-indigo-100 rounded-lg">
              <Users className="w-5 h-5 text-indigo-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{agents.length}</p>
              <p className="text-sm text-slate-500">Total Agents</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-green-100 rounded-lg">
              <Activity className="w-5 h-5 text-green-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{totalActive}</p>
              <p className="text-sm text-slate-500">Active Now</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-100 rounded-lg">
              <Workflow className="w-5 h-5 text-purple-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{Object.keys(agentsByCategory).length}</p>
              <p className="text-sm text-slate-500">Categories</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-amber-100 rounded-lg">
              <CheckCircle className="w-5 h-5 text-amber-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{totalTasks.toLocaleString()}</p>
              <p className="text-sm text-slate-500">Tasks Completed</p>
            </div>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
          <input
            type="text"
            placeholder="Search agents by name, role, or description..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          />
        </div>
        <select
          value={selectedEcosystem}
          onChange={(e) => setSelectedEcosystem(e.target.value)}
          className="px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
        >
          <option value="all">All Ecosystems</option>
          {Object.entries(ecosystemConfig).map(([key, config]) => (
            <option key={key} value={key}>{config.name}</option>
          ))}
        </select>
      </div>

      {/* Agents by Category */}
      <div>
        {(['data', 'analytics', 'simulation', 'optimization', 'governance', 'communication'] as AgentCategory[]).map(category => {
          const categoryAgents = agentsByCategory[category];
          if (!categoryAgents || categoryAgents.length === 0) return null;
          
          return (
            <CategorySection
              key={category}
              category={category}
              agents={categoryAgents}
              expandedAgents={expandedAgents}
              onToggleAgent={toggleAgent}
            />
          );
        })}
      </div>

      {filteredAgents.length === 0 && (
        <div className="text-center py-12">
          <Users className="w-12 h-12 text-slate-300 mx-auto mb-4" />
          <p className="text-slate-500">No agents found matching your filters</p>
        </div>
      )}
    </div>
  );
}
