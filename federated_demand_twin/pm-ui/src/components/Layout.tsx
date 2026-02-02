import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { 
  Wrench, 
  LayoutDashboard, 
  Database, 
  FlaskConical, 
  RefreshCw, 
  Shield, 
  Heart, 
  BarChart3,
  Bell,
  LogOut,
  ChevronDown,
  User,
  Settings,
  Cpu,
  FileText,
  ClipboardList,
  TrendingUp,
  Search,
  Building2,
  X,
  AlertTriangle,
  Clock,
  Bot,
  Truck
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { notifications, cases } from '../data/mockData';

const operationsNav = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/cases', icon: FileText, label: 'Cases' },
  { to: '/work-orders', icon: ClipboardList, label: 'Work Orders' },
  { to: '/dispatch', icon: Truck, label: 'Dispatch' },
];

const assetsNav = [
  { to: '/assets', icon: Cpu, label: 'Asset Explorer' },
  { to: '/outcomes', icon: TrendingUp, label: 'Outcomes' },
  { to: '/evaluation', icon: BarChart3, label: 'KPI Evaluation' },
];

const agentsNav = [
  { to: '/agents', icon: Bot, label: 'Agent Control' },
];

const mlOpsNav = [
  { to: '/models', icon: Database, label: 'Models' },
  { to: '/experiments', icon: FlaskConical, label: 'Experiments' },
  { to: '/retraining', icon: RefreshCw, label: 'Retraining' },
  { to: '/calibration', icon: BarChart3, label: 'Calibration' },
];

const adminNav = [
  { to: '/governance', icon: Shield, label: 'Governance' },
  { to: '/health', icon: Heart, label: 'System Health' },
  { to: '/metrics', icon: BarChart3, label: 'Alerts' },
  { to: '/admin', icon: Settings, label: 'Settings' },
];

export function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [showDropdown, setShowDropdown] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const unreadNotifications = notifications.filter(n => !n.readAt).length;
  const criticalCases = cases.filter(c => c.severity === 'critical' && c.status !== 'closed').length;

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Top Header */}
      <header className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-orange-500 to-red-600 rounded-lg flex items-center justify-center">
              <Wrench className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-slate-900">Arctic Pulse</h1>
              <p className="text-xs text-slate-500">Autonomous Asset Operations</p>
            </div>
          </div>

          {/* Tenant Selector */}
          <div className="ml-4 pl-4 border-l border-slate-200">
            <button className="flex items-center gap-2 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors">
              <Building2 className="w-4 h-4 text-slate-600" />
              <span className="text-sm font-medium text-slate-700">Northwind Energy</span>
              <ChevronDown className="w-4 h-4 text-slate-400" />
            </button>
          </div>
        </div>

        {/* Global Search */}
        <div className="flex-1 max-w-md mx-8">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search assets, cases, work orders..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onFocus={() => setShowSearch(true)}
              className="w-full pl-10 pr-4 py-2 bg-slate-100 border border-transparent rounded-lg text-sm focus:outline-none focus:bg-white focus:border-slate-200 focus:ring-2 focus:ring-orange-500/20"
            />
            {showSearch && searchQuery && (
              <div className="absolute top-full left-0 right-0 mt-2 bg-white rounded-xl shadow-lg border border-slate-200 py-2 z-50">
                <p className="px-4 py-2 text-xs text-slate-500">Search results for "{searchQuery}"</p>
                <button
                  onClick={() => { setShowSearch(false); setSearchQuery(''); }}
                  className="w-full px-4 py-2 text-left text-sm text-slate-600 hover:bg-slate-50"
                >
                  Press Enter to search...
                </button>
              </div>
            )}
          </div>
        </div>
        
        <div className="flex items-center gap-3">
          {/* Critical Cases Alert */}
          {criticalCases > 0 && (
            <button
              onClick={() => navigate('/cases')}
              className="flex items-center gap-2 px-3 py-1.5 bg-red-50 border border-red-200 rounded-full hover:bg-red-100 transition-colors"
            >
              <AlertTriangle className="w-4 h-4 text-red-600" />
              <span className="text-sm text-red-700 font-medium">{criticalCases} Critical</span>
            </button>
          )}

          <div className="flex items-center gap-2 px-3 py-1.5 bg-green-50 border border-green-200 rounded-full">
            <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
            <span className="text-sm text-green-700 font-medium">Healthy</span>
          </div>
          
          {/* Notifications */}
          <div className="relative">
            <button
              onClick={() => setShowNotifications(!showNotifications)}
              className="relative p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
            >
              <Bell className="w-5 h-5" />
              {unreadNotifications > 0 && (
                <span className="absolute top-1 right-1 w-4 h-4 bg-red-500 rounded-full text-[10px] text-white flex items-center justify-center font-medium">
                  {unreadNotifications}
                </span>
              )}
            </button>

            {showNotifications && (
              <div className="absolute right-0 mt-2 w-80 bg-white rounded-xl shadow-lg border border-slate-200 z-50">
                <div className="p-4 border-b border-slate-100 flex items-center justify-between">
                  <h3 className="font-semibold text-slate-900">Notifications</h3>
                  <button onClick={() => setShowNotifications(false)}>
                    <X className="w-4 h-4 text-slate-400" />
                  </button>
                </div>
                <div className="max-h-80 overflow-auto">
                  {notifications.slice(0, 5).map((notif) => (
                    <div
                      key={notif.id}
                      className={`p-3 border-b border-slate-50 hover:bg-slate-50 cursor-pointer ${!notif.readAt ? 'bg-orange-50/50' : ''}`}
                    >
                      <div className="flex items-start gap-3">
                        <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                          notif.severity === 'critical' ? 'bg-red-100' :
                          notif.severity === 'warning' ? 'bg-amber-100' : 'bg-blue-100'
                        }`}>
                          {notif.severity === 'critical' ? (
                            <AlertTriangle className="w-4 h-4 text-red-600" />
                          ) : (
                            <Bell className="w-4 h-4 text-amber-600" />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-slate-900 truncate">{notif.title}</p>
                          <p className="text-xs text-slate-500 truncate">{notif.message}</p>
                          <p className="text-xs text-slate-400 mt-1 flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {new Date(notif.createdAt).toLocaleTimeString()}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="p-3 border-t border-slate-100">
                  <button className="w-full text-sm text-orange-600 hover:text-orange-700 font-medium">
                    View all notifications
                  </button>
                </div>
              </div>
            )}
          </div>
          
          {/* User Menu Dropdown */}
          <div className="relative">
            <button 
              onClick={() => setShowDropdown(!showDropdown)}
              className="flex items-center gap-2 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors"
            >
              <div className="w-8 h-8 bg-orange-100 rounded-full flex items-center justify-center">
                <User className="w-4 h-4 text-orange-600" />
              </div>
              <span className="text-sm font-medium">{user?.name || 'User'}</span>
              <ChevronDown className="w-4 h-4" />
            </button>
            
            {showDropdown && (
              <div className="absolute right-0 mt-2 w-56 bg-white rounded-xl shadow-lg border border-slate-200 py-2 z-50">
                <div className="px-4 py-2 border-b border-slate-100">
                  <p className="text-sm font-medium text-slate-900">{user?.name}</p>
                  <p className="text-xs text-slate-500">{user?.email}</p>
                  <p className="text-xs text-orange-600 mt-1">Senior Operator</p>
                </div>
                <button
                  onClick={() => { setShowDropdown(false); navigate('/admin'); }}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-left text-slate-700 hover:bg-slate-50 transition-colors"
                >
                  <Settings className="w-5 h-5" />
                  <div className="font-medium">Settings</div>
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
        <nav className="w-64 bg-white border-r border-slate-200 min-h-[calc(100vh-60px)] p-4 overflow-auto">
          {/* Operations Section */}
          <div className="mb-6">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2 px-4">
              Operations
            </h3>
            <div className="space-y-1">
              {operationsNav.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-4 py-2.5 rounded-lg transition-colors ${
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
          </div>

          {/* Assets & Analytics Section */}
          <div className="mb-6">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2 px-4">
              Assets
            </h3>
            <div className="space-y-1">
              {assetsNav.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-4 py-2.5 rounded-lg transition-colors ${
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
          </div>

          {/* AI Agents Section */}
          <div className="mb-6">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2 px-4">
              AI Agents
            </h3>
            <div className="space-y-1">
              {agentsNav.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-4 py-2.5 rounded-lg transition-colors ${
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
          </div>

          {/* ML Ops Section */}
          <div className="mb-6">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2 px-4">
              ML Ops
            </h3>
            <div className="space-y-1">
              {mlOpsNav.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-4 py-2.5 rounded-lg transition-colors ${
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
          </div>

          {/* Admin Section */}
          <div className="mb-6">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2 px-4">
              System
            </h3>
            <div className="space-y-1">
              {adminNav.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-4 py-2.5 rounded-lg transition-colors ${
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
          </div>

          {/* Quick Stats */}
          <div className="pt-4 border-t border-slate-200">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3 px-4">
              Quick Stats
            </h3>
            <div className="space-y-3 px-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-600">Open Cases</span>
                <span className="text-sm font-semibold text-red-600">{cases.filter(c => c.status !== 'closed').length}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-600">Models in Prod</span>
                <span className="text-sm font-semibold text-slate-900">3</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-600">Pending Approvals</span>
                <span className="text-sm font-semibold text-amber-600">2</span>
              </div>
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
