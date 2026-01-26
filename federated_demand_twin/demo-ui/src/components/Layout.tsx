import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { 
  Brain, 
  Box, 
  Users, 
  MessageSquare,
  Activity,
  Bell,
  FileText,
  LogOut,
  ChevronDown,
  Play,
  Loader2
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { api } from '../services/api';

const navItems = [
  { to: '/', icon: FileText, label: 'Log Files', end: true },
  { to: '/bayesian', icon: Brain, label: 'Bayesian Model' },
  { to: '/digital-twin', icon: Box, label: 'Digital Twin' },
  { to: '/orchestration', icon: Users, label: 'Agent Orchestration' },
  { to: '/output', icon: MessageSquare, label: 'Agent Output' },
];

export function Layout() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [showDropdown, setShowDropdown] = useState(false);
  const [isRunning, setIsRunning] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const handleRunOptimization = async () => {
    setShowDropdown(false);
    setIsRunning(true);
    try {
      const result = await api.runDemo();
      console.log('Optimization completed:', result);
      // Optionally refresh the page data here
      setTimeout(() => setIsRunning(false), 2000); // Show success for 2 seconds
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
          <div className="w-10 h-10 bg-gradient-to-br from-blue-600 to-indigo-700 rounded-lg flex items-center justify-center">
            <Activity className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-slate-900">Retail Media Optimization</h1>
            <p className="text-xs text-slate-500">Bayesian → Digital Twin → Agent Pipeline</p>
          </div>
        </div>
        
        <div className="flex items-center gap-4">
          {isRunning ? (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 border border-blue-200 rounded-full">
              <Loader2 className="w-4 h-4 text-blue-600 animate-spin" />
              <span className="text-sm text-blue-700 font-medium">Running Optimization...</span>
            </div>
          ) : (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-green-50 border border-green-200 rounded-full">
              <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
              <span className="text-sm text-green-700 font-medium">System Active</span>
            </div>
          )}
          <button className="relative p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors">
            <Bell className="w-5 h-5" />
            <span className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full"></span>
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
                  onClick={handleRunOptimization}
                  disabled={isRunning}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-left text-slate-700 hover:bg-blue-50 hover:text-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isRunning ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <Play className="w-5 h-5" />
                  )}
                  <div>
                    <div className="font-medium">Run Optimization</div>
                    <div className="text-xs text-slate-500">Execute media allocation pipeline</div>
                  </div>
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
                      ? 'bg-blue-50 text-blue-700 font-medium'
                      : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                  }`
                }
              >
                <item.icon className="w-5 h-5" />
                <span>{item.label}</span>
              </NavLink>
            ))}
          </div>

          {/* Campaign Card */}
          <div className="mt-8 p-4 bg-gradient-to-br from-indigo-50 to-purple-50 border border-indigo-200 rounded-xl">
            <div className="flex items-center gap-2 mb-2">
              <span className="w-2 h-2 bg-indigo-500 rounded-full animate-pulse"></span>
              <span className="text-xs font-semibold text-indigo-700 uppercase tracking-wide">Active Campaign</span>
            </div>
            <h3 className="text-sm font-semibold text-slate-900 mb-1">Q1 2024 Optimization</h3>
            <p className="text-xs text-slate-600 mb-3">Budget: $10M / 13 weeks</p>
            <div className="flex items-center justify-between">
              <span className="px-2 py-1 bg-indigo-100 text-indigo-700 text-xs font-medium rounded">$10M</span>
              <span className="text-xs text-slate-500">5 Retailers</span>
            </div>
          </div>

          {/* Quick Stats */}
          <div className="mt-6 grid grid-cols-2 gap-3">
            <div className="p-3 bg-slate-50 rounded-lg">
              <p className="text-2xl font-bold text-slate-900">5</p>
              <p className="text-xs text-slate-500">Retailers</p>
            </div>
            <div className="p-3 bg-slate-50 rounded-lg">
              <p className="text-2xl font-bold text-slate-900">6</p>
              <p className="text-xs text-slate-500">Channels</p>
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
