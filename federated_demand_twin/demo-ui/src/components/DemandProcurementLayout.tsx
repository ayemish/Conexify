import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { 
  Brain, 
  Box, 
  Users, 
  MessageSquare,
  Package,
  Bell,
  FileText,
  LogOut,
  ChevronDown,
  Play,
  Loader2,
  Home
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { dpApi } from '../services/dpApi';

const navItems = [
  { to: '/demand-procurement', icon: FileText, label: 'Forecast Dashboard', end: true },
  { to: '/demand-procurement/bayesian', icon: Brain, label: 'Demand Model' },
  { to: '/demand-procurement/digital-twin', icon: Box, label: 'Inventory Twin' },
  { to: '/demand-procurement/orchestration', icon: Users, label: 'Procurement Workflow' },
  { to: '/demand-procurement/output', icon: MessageSquare, label: 'Order Decisions' },
];

export function DemandProcurementLayout() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [showDropdown, setShowDropdown] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [sidebarData, setSidebarData] = useState<{
    totalSKUs: number;
    totalSuppliers: number;
    activePlan: string;
    workingCapital: string;
  }>({
    totalSKUs: 0,
    totalSuppliers: 0,
    activePlan: 'Awaiting Run',
    workingCapital: '$0'
  });

  useEffect(() => {
    loadSidebarData();
  }, []);

  const loadSidebarData = async () => {
    try {
      const config = await dpApi.getConfig();
      setSidebarData({
        totalSKUs: config.skus?.length || 0,
        totalSuppliers: config.suppliers?.length || 0,
        activePlan: config.organization_name || 'Demo Org',
        workingCapital: config.working_capital_limit ? `$${(config.working_capital_limit / 1000).toFixed(0)}K` : '$500K'
      });
    } catch (error) {
      console.error('Failed to load sidebar data:', error);
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const handleRunOptimization = async () => {
    setShowDropdown(false);
    setIsRunning(true);
    try {
      const result = await dpApi.runDemo();
      console.log('Optimization completed:', result);
      await loadSidebarData();
      setTimeout(() => setIsRunning(false), 2000);
    } catch (error) {
      console.error('Failed to run optimization:', error);
      alert('Failed to run optimization: ' + (error instanceof Error ? error.message : 'Unknown error'));
      setIsRunning(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Top Header */}
      <header className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-emerald-600 to-teal-700 rounded-lg flex items-center justify-center">
            <Package className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-slate-900">Demand & Procurement</h1>
            <p className="text-xs text-slate-500">Forecast → Optimize → Plan Pipeline</p>
          </div>
        </div>
        
        <div className="flex items-center gap-4">
          {isRunning ? (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-emerald-50 border border-emerald-200 rounded-full">
              <Loader2 className="w-4 h-4 text-emerald-600 animate-spin" />
              <span className="text-sm text-emerald-700 font-medium">Running Pipeline...</span>
            </div>
          ) : (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-green-50 border border-green-200 rounded-full">
              <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
              <span className="text-sm text-green-700 font-medium">System Active</span>
            </div>
          )}
          <button className="relative p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors">
            <Bell className="w-5 h-5" />
            <span className="absolute top-1 right-1 w-2 h-2 bg-amber-500 rounded-full"></span>
          </button>
          
          {/* User Menu Dropdown */}
          <div className="relative">
            <button 
              onClick={() => setShowDropdown(!showDropdown)}
              className="flex items-center gap-2 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors"
            >
              <Package className="w-5 h-5" />
              <span className="text-sm font-medium">Actions</span>
              <ChevronDown className="w-4 h-4" />
            </button>
            
            {showDropdown && (
              <div className="absolute right-0 mt-2 w-56 bg-white rounded-xl shadow-lg border border-slate-200 py-2 z-50">
                <button
                  onClick={handleRunOptimization}
                  disabled={isRunning}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-left text-slate-700 hover:bg-emerald-50 hover:text-emerald-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isRunning ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <Play className="w-5 h-5" />
                  )}
                  <div>
                    <div className="font-medium">Run Pipeline</div>
                    <div className="text-xs text-slate-500">Execute D&P workflow</div>
                  </div>
                </button>
                <div className="border-t border-slate-200 my-2"></div>
                <button 
                  onClick={() => navigate('/')}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-left text-slate-700 hover:bg-slate-50 transition-colors"
                >
                  <Home className="w-5 h-5" />
                  <div className="font-medium">Switch Ecosystem</div>
                </button>
                <button 
                  onClick={handleLogout}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-left text-slate-700 hover:bg-red-50 hover:text-red-600 transition-colors"
                >
                  <LogOut className="w-5 h-5" />
                  <div className="font-medium">Logout</div>
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      <div className="flex">
        {/* Sidebar Navigation */}
        <nav className="w-64 bg-white border-r border-slate-200 min-h-[calc(100vh-60px)] p-4">
          <div className="space-y-1">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={'end' in item ? item.end : undefined}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-4 py-3 rounded-lg transition-all ${
                    isActive
                      ? 'bg-emerald-50 text-emerald-700 font-medium'
                      : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                  }`
                }
              >
                <item.icon className="w-5 h-5" />
                <span>{item.label}</span>
              </NavLink>
            ))}
          </div>

          {/* Active Plan Card */}
          <div className="mt-8 p-4 bg-gradient-to-br from-emerald-50 to-teal-50 border border-emerald-200 rounded-xl">
            <div className="flex items-center gap-2 mb-2">
              <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse"></span>
              <span className="text-xs font-semibold text-emerald-700 uppercase tracking-wide">Planning Mode</span>
            </div>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">{sidebarData.activePlan}</h3>
            <p className="text-xs text-slate-600 mb-3">Horizon: 13 weeks</p>
            <div className="flex items-center justify-between">
              <span className="px-2 py-1 bg-emerald-100 text-emerald-700 text-xs font-medium rounded">{sidebarData.workingCapital}</span>
              <span className="text-xs text-slate-500">Working Cap.</span>
            </div>
          </div>

          {/* Quick Stats */}
          <div className="mt-6 grid grid-cols-2 gap-3">
            <div className="p-3 bg-slate-50 rounded-lg">
              <p className="text-2xl font-bold text-slate-900">{sidebarData.totalSKUs}</p>
              <p className="text-xs text-slate-500">SKUs</p>
            </div>
            <div className="p-3 bg-slate-50 rounded-lg">
              <p className="text-2xl font-bold text-slate-900">{sidebarData.totalSuppliers}</p>
              <p className="text-xs text-slate-500">Suppliers</p>
            </div>
          </div>
        </nav>

        {/* Main Content */}
        <main className="flex-1 p-6 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
