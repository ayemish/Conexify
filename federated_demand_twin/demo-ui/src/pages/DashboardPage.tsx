import { useState, useEffect, useRef } from 'react';
import { 
  Play, RefreshCw, CheckCircle, XCircle, Loader2, 
  Terminal, Zap, Database, Brain, Users
} from 'lucide-react';
import api, { type DemoStatus, type LogEntry } from '../services/api';

export function DashboardPage() {
  const [status, setStatus] = useState<DemoStatus | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [backendConnected, setBackendConnected] = useState<boolean | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const pollIntervalRef = useRef<number | null>(null);

  // Check backend connection on mount
  useEffect(() => {
    checkBackendConnection();
  }, []);

  // Poll for status and logs while running
  useEffect(() => {
    if (isRunning) {
      pollIntervalRef.current = window.setInterval(async () => {
        try {
          const [statusRes, logsRes] = await Promise.all([
            api.getStatus(),
            api.getLogs()
          ]);
          setStatus(statusRes);
          setLogs(logsRes.logs);
          
          if (statusRes.status === 'completed' || statusRes.status === 'error') {
            setIsRunning(false);
            if (pollIntervalRef.current) {
              clearInterval(pollIntervalRef.current);
            }
          }
        } catch (err) {
          console.error('Polling error:', err);
        }
      }, 500);
    }

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [isRunning]);

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const checkBackendConnection = async () => {
    try {
      await api.healthCheck();
      setBackendConnected(true);
      const statusRes = await api.getStatus();
      setStatus(statusRes);
      if (statusRes.has_results) {
        const logsRes = await api.getLogs();
        setLogs(logsRes.logs);
      }
    } catch (err) {
      setBackendConnected(false);
      setError('Backend not connected. Start the backend server first.');
    }
  };

  const handleRunDemo = async () => {
    setIsRunning(true);
    setError(null);
    setLogs([]);
    
    try {
      await api.runDemo();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run demo');
      setIsRunning(false);
    }
  };

  const formatLogMessage = (message: string) => {
    // Highlight different log types
    if (message.startsWith('✓') || message.startsWith('✅')) {
      return <span className="text-green-400">{message}</span>;
    }
    if (message.startsWith('❌') || message.startsWith('✗')) {
      return <span className="text-red-400">{message}</span>;
    }
    if (message.startsWith('---') || message.includes('===')) {
      return <span className="text-blue-400 font-semibold">{message}</span>;
    }
    if (message.startsWith('🎯')) {
      return <span className="text-yellow-400 font-bold">{message}</span>;
    }
    return message;
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Media Spend Control Center</h1>
          <p className="text-slate-500 mt-1">Run and monitor the Retail Media Budget Allocation Pipeline</p>
        </div>
        <div className="flex items-center gap-3">
          {backendConnected === false && (
            <button
              onClick={checkBackendConnection}
              className="flex items-center gap-2 px-4 py-2 bg-amber-100 text-amber-700 rounded-lg hover:bg-amber-200 transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              Retry Connection
            </button>
          )}
          <button
            onClick={handleRunDemo}
            disabled={isRunning || backendConnected === false}
            className={`flex items-center gap-2 px-6 py-2.5 rounded-lg font-medium transition-all ${
              isRunning || backendConnected === false
                ? 'bg-slate-200 text-slate-500 cursor-not-allowed'
                : 'bg-indigo-600 text-white hover:bg-indigo-700 shadow-lg shadow-indigo-200'
            }`}
          >
            {isRunning ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                Running...
              </>
            ) : (
              <>
                <Play className="w-5 h-5" />
                Execute
              </>
            )}
          </button>
        </div>
      </div>

      {/* Connection Status */}
      {backendConnected === false && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4">
          <div className="flex items-start gap-3">
            <XCircle className="w-5 h-5 text-red-500 mt-0.5" />
            <div>
              <h3 className="font-semibold text-red-800">Backend Not Connected</h3>
              <p className="text-red-600 text-sm mt-1">
                Start the backend server by running:
              </p>
              <code className="block mt-2 px-3 py-2 bg-red-100 rounded text-sm text-red-800 font-mono">
                cd demo-ui/backend && python api.py
              </code>
            </div>
          </div>
        </div>
      )}

      {/* Progress Section */}
      {status && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-slate-900 flex items-center gap-2">
              <Zap className="w-5 h-5 text-indigo-600" />
              Pipeline Progress
            </h2>
            <div className="flex items-center gap-2">
              {status.status === 'completed' && (
                <span className="flex items-center gap-1.5 px-3 py-1 bg-green-100 text-green-700 rounded-full text-sm font-medium">
                  <CheckCircle className="w-4 h-4" />
                  Completed
                </span>
              )}
              {status.status === 'running' && (
                <span className="flex items-center gap-1.5 px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-sm font-medium">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Running
                </span>
              )}
              {status.status === 'error' && (
                <span className="flex items-center gap-1.5 px-3 py-1 bg-red-100 text-red-700 rounded-full text-sm font-medium">
                  <XCircle className="w-4 h-4" />
                  Error
                </span>
              )}
              {status.status === 'idle' && (
                <span className="px-3 py-1 bg-slate-100 text-slate-600 rounded-full text-sm font-medium">
                  Idle
                </span>
              )}
            </div>
          </div>

          {/* Progress Bar */}
          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-slate-600">{status.current_step || 'Ready to run'}</span>
              <span className="text-sm font-semibold text-slate-700">{status.progress}%</span>
            </div>
            <div className="h-3 bg-slate-100 rounded-full overflow-hidden">
              <div 
                className={`h-full rounded-full transition-all duration-500 ${
                  status.status === 'error' ? 'bg-red-500' :
                  status.status === 'completed' ? 'bg-green-500' :
                  'bg-indigo-500'
                }`}
                style={{ width: `${status.progress}%` }}
              />
            </div>
          </div>

          {/* Pipeline Steps */}
          <div className="grid grid-cols-5 gap-2 mt-6">
            {[
              { name: 'Configure', icon: Database, threshold: 10 },
              { name: 'Channels', icon: Users, threshold: 40 },
              { name: 'Elasticity', icon: Brain, threshold: 65 },
              { name: 'Simulate', icon: Zap, threshold: 85 },
              { name: 'Allocate', icon: CheckCircle, threshold: 100 },
            ].map((step, index) => {
              const isComplete = status.progress >= step.threshold;
              const isActive = status.progress > (index > 0 ? [10, 40, 65, 85, 100][index - 1] : 0) && status.progress < step.threshold;
              
              return (
                <div 
                  key={step.name}
                  className={`flex flex-col items-center p-3 rounded-lg transition-all ${
                    isComplete ? 'bg-green-50' :
                    isActive ? 'bg-blue-50 animate-pulse' :
                    'bg-slate-50'
                  }`}
                >
                  <step.icon className={`w-6 h-6 mb-2 ${
                    isComplete ? 'text-green-600' :
                    isActive ? 'text-blue-600' :
                    'text-slate-400'
                  }`} />
                  <span className={`text-xs font-medium ${
                    isComplete ? 'text-green-700' :
                    isActive ? 'text-blue-700' :
                    'text-slate-500'
                  }`}>{step.name}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Live Logs */}
      <div className="bg-slate-900 rounded-xl border border-slate-700 shadow-lg overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 bg-slate-800 border-b border-slate-700">
          <div className="flex items-center gap-2">
            <Terminal className="w-5 h-5 text-green-400" />
            <span className="text-slate-200 font-medium">Live Output</span>
          </div>
          <span className="text-xs text-slate-400">{logs.length} lines</span>
        </div>
        <div className="h-96 overflow-y-auto p-4 font-mono text-sm">
          {logs.length === 0 ? (
            <div className="text-slate-500 text-center py-8">
              Click "Execute" to start the pipeline...
            </div>
          ) : (
            logs.map((log, index) => (
              <div key={index} className="text-slate-300 leading-relaxed">
                {formatLogMessage(log.message)}
              </div>
            ))
          )}
          <div ref={logsEndRef} />
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4">
          <div className="flex items-start gap-3">
            <XCircle className="w-5 h-5 text-red-500 mt-0.5" />
            <div>
              <h3 className="font-semibold text-red-800">Error</h3>
              <p className="text-red-600 text-sm mt-1">{error}</p>
            </div>
          </div>
        </div>
      )}

      {/* Quick Stats (after completion) */}
      {status?.has_results && (
        <div className="grid grid-cols-4 gap-4">
          <div className="bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl p-5 text-white">
            <p className="text-indigo-200 text-sm mb-1">Pipeline Status</p>
            <p className="text-2xl font-bold">Complete</p>
          </div>
          <div className="bg-white rounded-xl border border-slate-200 p-5">
            <p className="text-slate-500 text-sm mb-1">Media Budget</p>
            <p className="text-2xl font-bold text-slate-900">$10M</p>
          </div>
          <div className="bg-white rounded-xl border border-slate-200 p-5">
            <p className="text-slate-500 text-sm mb-1">Retailers</p>
            <p className="text-2xl font-bold text-slate-900">5</p>
          </div>
          <div className="bg-white rounded-xl border border-slate-200 p-5">
            <p className="text-slate-500 text-sm mb-1">SKUs</p>
            <p className="text-2xl font-bold text-slate-900">4</p>
          </div>
        </div>
      )}
    </div>
  );
}
