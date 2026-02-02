import { useState, useEffect, useRef } from 'react';
import { 
  Play, RefreshCw, CheckCircle, XCircle, Loader2, 
  Terminal, Zap, Database, Brain, Users, Package, TrendingUp
} from 'lucide-react';
import { dpApi, type DemoStatus, type LogEntry } from '../../services/dpApi';

export function DPDashboardPage() {
  const [status, setStatus] = useState<DemoStatus | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [backendConnected, setBackendConnected] = useState<boolean | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const pollIntervalRef = useRef<number | null>(null);

  useEffect(() => {
    checkBackendConnection();
  }, []);

  useEffect(() => {
    if (isRunning) {
      pollIntervalRef.current = window.setInterval(async () => {
        try {
          const [statusRes, logsRes] = await Promise.all([
            dpApi.getStatus(),
            dpApi.getLogs()
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

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const checkBackendConnection = async () => {
    try {
      await dpApi.healthCheck();
      setBackendConnected(true);
      const statusRes = await dpApi.getStatus();
      setStatus(statusRes);
      if (statusRes.has_results) {
        const logsRes = await dpApi.getLogs();
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
      await dpApi.runDemo();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run demo');
      setIsRunning(false);
    }
  };

  const formatLogMessage = (message: string) => {
    if (message.startsWith('✓') || message.startsWith('✅')) {
      return <span className="text-green-400">{message}</span>;
    }
    if (message.startsWith('❌') || message.startsWith('✗')) {
      return <span className="text-red-400">{message}</span>;
    }
    if (message.startsWith('---') || message.includes('===')) {
      return <span className="text-emerald-400 font-semibold">{message}</span>;
    }
    if (message.startsWith('🎯') || message.startsWith('📦')) {
      return <span className="text-yellow-400 font-bold">{message}</span>;
    }
    return message;
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Demand & Procurement Control Center</h1>
          <p className="text-slate-500 mt-1">Run and monitor the Forecast → Optimize → Plan Pipeline</p>
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
                : 'bg-emerald-600 text-white hover:bg-emerald-700 shadow-lg shadow-emerald-200'
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
              <Package className="w-5 h-5 text-emerald-600" />
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
                <span className="flex items-center gap-1.5 px-3 py-1 bg-emerald-100 text-emerald-700 rounded-full text-sm font-medium">
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
                  'bg-emerald-500'
                }`}
                style={{ width: `${status.progress}%` }}
              />
            </div>
          </div>

          {/* Pipeline Steps */}
          <div className="grid grid-cols-7 gap-2 mt-6">
            {[
              { name: 'Forecast', icon: TrendingUp, threshold: 15 },
              { name: 'Optimize', icon: Zap, threshold: 30 },
              { name: 'Risk', icon: Database, threshold: 45 },
              { name: 'Simulate', icon: Brain, threshold: 60 },
              { name: 'Plan', icon: Package, threshold: 75 },
              { name: 'Govern', icon: Users, threshold: 90 },
              { name: 'Report', icon: CheckCircle, threshold: 100 },
            ].map((step, index) => {
              const isComplete = status.progress >= step.threshold;
              const prevThreshold = index > 0 ? [15, 30, 45, 60, 75, 90, 100][index - 1] : 0;
              const isActive = status.progress > prevThreshold && status.progress < step.threshold;
              
              return (
                <div 
                  key={step.name}
                  className={`flex flex-col items-center p-3 rounded-lg transition-all ${
                    isComplete ? 'bg-emerald-50' :
                    isActive ? 'bg-teal-50 animate-pulse' :
                    'bg-slate-50'
                  }`}
                >
                  <step.icon className={`w-6 h-6 mb-2 ${
                    isComplete ? 'text-emerald-600' :
                    isActive ? 'text-teal-600' :
                    'text-slate-400'
                  }`} />
                  <span className={`text-xs font-medium ${
                    isComplete ? 'text-emerald-700' :
                    isActive ? 'text-teal-700' :
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
            <Terminal className="w-5 h-5 text-emerald-400" />
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
          <div className="bg-gradient-to-br from-emerald-500 to-teal-600 rounded-xl p-5 text-white">
            <p className="text-emerald-200 text-sm mb-1">Pipeline Status</p>
            <p className="text-2xl font-bold">Complete</p>
          </div>
          <div className="bg-white rounded-xl border border-slate-200 p-5">
            <p className="text-slate-500 text-sm mb-1">Service Level</p>
            <p className="text-2xl font-bold text-slate-900">95%+</p>
          </div>
          <div className="bg-white rounded-xl border border-slate-200 p-5">
            <p className="text-slate-500 text-sm mb-1">SKUs Analyzed</p>
            <p className="text-2xl font-bold text-slate-900">5</p>
          </div>
          <div className="bg-white rounded-xl border border-slate-200 p-5">
            <p className="text-slate-500 text-sm mb-1">Suppliers</p>
            <p className="text-2xl font-bold text-slate-900">3</p>
          </div>
        </div>
      )}
    </div>
  );
}
