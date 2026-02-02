import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { 
  Wrench,
  Activity,
  Bell,
  LogOut,
  ChevronDown,
  Home,
  LayoutDashboard,
  Database,
  FlaskConical,
  RefreshCw,
  Shield,
  Heart,
  BarChart3,
  AlertTriangle
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

const navItems = [
  { to: '/predictive-maintenance', icon: LayoutDashboard, label: 'Dashboard', end: true },
  { to: '/predictive-maintenance/models', icon: Database, label: 'Model Registry' },
  { to: '/predictive-maintenance/experiments', icon: FlaskConical, label: 'A/B Experiments' },
  { to: '/predictive-maintenance/retraining', icon: RefreshCw, label: 'Retraining Pipeline' },
  { to: '/predictive-maintenance/governance', icon: Shield, label: 'Governance' },
  { to: '/predictive-maintenance/health', icon: Heart, label: 'System Health' },
  { to: '/predictive-maintenance/metrics', icon: BarChart3, label: 'Metrics & Alerts' },
];

export function PredictiveMaintenanceLayout() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [showDropdown, setShowDropdown] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Top Header */}
      <header className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-orange-500 to-red-600 rounded-lg flex items-center justify-center">
            <Wrench className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-slate-900">Predictive Maintenance</h1>
            <p className="text-xs text-slate-500">ML Learning Loop → Observability → API</p>
          </div>
        </div>
        
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-green-50 border border-green-200 rounded-full">
            <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
            <span className="text-sm text-green-700 font-medium">System Healthy</span>
          </div>
          <button className="relative p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors">
            <Bell className="w-5 h-5" />
            <span className="absolute top-1 right-1 w-2 h-2 bg-orange-500 rounded-full"></span>
          </button>
          
          {/* User Menu Dropdown */}
          <div className="relative">
            <button 
              onClick={() => setShowDropdown(!showDropdown)}
              className="flex items-center gap-2 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors"
            >
              <Activity className="w-5 h-5" />
              <span className="text-sm font-medium">Actions</span>
              <ChevronDown className="w-4 h-4" />
            </button>
            
            {showDropdown && (
              <div className="absolute right-0 mt-2 w-56 bg-white rounded-xl shadow-lg border border-slate-200 py-2 z-50">
                <button 
                  onClick={() => { setShowDropdown(false); navigate('/'); }}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-left text-slate-700 hover:bg-slate-50 transition-colors"
                >
                  <Home className="w-5 h-5" />
                  <div className="font-medium">Switch Ecosystem</div>
                </button>
                <div className="border-t border-slate-200 my-2"></div>
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
                      ? 'bg-orange-50 text-orange-700 font-medium'
                      : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                  }`
                }
              >
                <item.icon className="w-5 h-5" />
                <span>{item.label}</span>
              </NavLink>
            ))}
          </div>

          {/* System Status Card */}
          <div className="mt-8 p-4 bg-gradient-to-br from-orange-50 to-red-50 border border-orange-200 rounded-xl">
            <div className="flex items-center gap-2 mb-2">
              <span className="w-2 h-2 bg-orange-500 rounded-full animate-pulse"></span>
              <span className="text-xs font-semibold text-orange-700 uppercase tracking-wide">Arctic Pulse Predictive Maintenance</span>
            </div>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Oil & Gas Monitoring</h3>
            <p className="text-xs text-slate-600 mb-3">Predictive Equipment Maintenance</p>
            <div className="flex items-center justify-between">
              <span className="px-2 py-1 bg-orange-100 text-orange-700 text-xs font-medium rounded">Active</span>
              <span className="text-xs text-slate-500">3 Models</span>
            </div>
          </div>

          {/* Quick Stats */}
          <div className="mt-6 grid grid-cols-2 gap-3">
            <div className="p-3 bg-slate-50 rounded-lg">
              <p className="text-2xl font-bold text-slate-900">98%</p>
              <p className="text-xs text-slate-500">Accuracy</p>
            </div>
            <div className="p-3 bg-slate-50 rounded-lg">
              <div className="flex items-center gap-1">
                <AlertTriangle className="w-4 h-4 text-amber-500" />
                <p className="text-2xl font-bold text-slate-900">2</p>
              </div>
              <p className="text-xs text-slate-500">Alerts</p>
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
