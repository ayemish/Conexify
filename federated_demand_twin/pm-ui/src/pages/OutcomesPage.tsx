import { useState } from 'react';
import {
  TrendingUp,
  TrendingDown,
  Zap,
  Clock,
  DollarSign,
  Truck,
  Shield,
  Activity,
  CheckCircle2,
  AlertTriangle,
  BarChart3,
  Download
} from 'lucide-react';
import { outcomeMetrics } from '../data/mockData';

export function OutcomesPage() {
  const [timeRange, setTimeRange] = useState('30d');

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Outcomes & M&V</h1>
          <p className="text-slate-500 mt-1">Measurement & verification of operational outcomes</p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={timeRange}
            onChange={(e) => setTimeRange(e.target.value)}
            className="px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm"
          >
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
            <option value="90d">Last 90 days</option>
            <option value="ytd">Year to date</option>
          </select>
          <button className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 transition-colors">
            <Download className="w-4 h-4" />
            Export Report
          </button>
        </div>
      </div>

      {/* Savings Summary */}
      <div className="bg-gradient-to-br from-green-500 to-emerald-600 rounded-xl p-6 text-white">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-green-100 text-sm">Total Verified Savings</p>
            <p className="text-4xl font-bold mt-1">${outcomeMetrics.energySavingsCost.toLocaleString()}</p>
            <p className="text-green-100 text-sm mt-2">{outcomeMetrics.energySavingsKwh.toLocaleString()} kWh saved</p>
          </div>
          <div className="w-20 h-20 bg-white/20 rounded-full flex items-center justify-center">
            <DollarSign className="w-10 h-10" />
          </div>
        </div>
        <div className="mt-6 pt-6 border-t border-white/20 grid grid-cols-3 gap-6">
          <div>
            <p className="text-green-100 text-xs">Downtime Avoided</p>
            <p className="text-2xl font-bold">{outcomeMetrics.downtimeAvoided}h</p>
          </div>
          <div>
            <p className="text-green-100 text-xs">Incidents Avoided</p>
            <p className="text-2xl font-bold">{outcomeMetrics.incidentsAvoided}</p>
          </div>
          <div>
            <p className="text-green-100 text-xs">Truck Rolls Avoided</p>
            <p className="text-2xl font-bold">{outcomeMetrics.truckRollsAvoided}</p>
          </div>
        </div>
      </div>

      {/* Response Time Metrics */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white rounded-xl p-5 border border-slate-200">
          <div className="flex items-center justify-between mb-3">
            <span className="text-slate-500 text-sm">Mean Time to Detect</span>
            <Activity className="w-5 h-5 text-blue-500" />
          </div>
          <p className="text-3xl font-bold text-slate-900">{outcomeMetrics.meanTimeToDetect}m</p>
          <p className="text-sm text-green-600 mt-1 flex items-center gap-1">
            <TrendingDown className="w-4 h-4" />
            -18% vs baseline
          </p>
        </div>

        <div className="bg-white rounded-xl p-5 border border-slate-200">
          <div className="flex items-center justify-between mb-3">
            <span className="text-slate-500 text-sm">Mean Time to Resolve</span>
            <Clock className="w-5 h-5 text-purple-500" />
          </div>
          <p className="text-3xl font-bold text-slate-900">{outcomeMetrics.meanTimeToResolve}h</p>
          <p className="text-sm text-green-600 mt-1 flex items-center gap-1">
            <TrendingDown className="w-4 h-4" />
            -32% vs baseline
          </p>
        </div>

        <div className="bg-white rounded-xl p-5 border border-slate-200">
          <div className="flex items-center justify-between mb-3">
            <span className="text-slate-500 text-sm">Approval Cycle Time</span>
            <CheckCircle2 className="w-5 h-5 text-green-500" />
          </div>
          <p className="text-3xl font-bold text-slate-900">{outcomeMetrics.approvalCycleTime}h</p>
          <p className="text-sm text-slate-500 mt-1">Average approval time</p>
        </div>

        <div className="bg-white rounded-xl p-5 border border-slate-200">
          <div className="flex items-center justify-between mb-3">
            <span className="text-slate-500 text-sm">Rollback Frequency</span>
            <AlertTriangle className="w-5 h-5 text-amber-500" />
          </div>
          <p className="text-3xl font-bold text-slate-900">{(outcomeMetrics.rollbackFrequency * 100).toFixed(1)}%</p>
          <p className="text-sm text-green-600 mt-1 flex items-center gap-1">
            <TrendingDown className="w-4 h-4" />
            Low rollback rate
          </p>
        </div>
      </div>

      {/* Autonomy Performance */}
      <div className="grid grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-slate-200">
          <div className="p-4 border-b border-slate-200">
            <h2 className="font-semibold text-slate-900">Autonomy Performance</h2>
          </div>
          <div className="p-6">
            <div className="grid grid-cols-3 gap-6 mb-6">
              <div className="text-center">
                <div className="w-16 h-16 mx-auto bg-green-100 rounded-full flex items-center justify-center mb-2">
                  <Zap className="w-8 h-8 text-green-600" />
                </div>
                <p className="text-2xl font-bold text-slate-900">{outcomeMetrics.autonomousActionsExecuted}</p>
                <p className="text-xs text-slate-500">Autonomous Actions</p>
              </div>
              <div className="text-center">
                <div className="w-16 h-16 mx-auto bg-amber-100 rounded-full flex items-center justify-center mb-2">
                  <Clock className="w-8 h-8 text-amber-600" />
                </div>
                <p className="text-2xl font-bold text-slate-900">{outcomeMetrics.actionsPendingApproval}</p>
                <p className="text-xs text-slate-500">Pending Approval</p>
              </div>
              <div className="text-center">
                <div className="w-16 h-16 mx-auto bg-red-100 rounded-full flex items-center justify-center mb-2">
                  <Shield className="w-8 h-8 text-red-600" />
                </div>
                <p className="text-2xl font-bold text-slate-900">{outcomeMetrics.actionsBlockedByPolicy}</p>
                <p className="text-xs text-slate-500">Blocked by Policy</p>
              </div>
            </div>
            <div className="bg-slate-50 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-slate-600">Autonomy Rate</span>
                <span className="text-sm font-medium text-slate-900">
                  {((outcomeMetrics.autonomousActionsExecuted / (outcomeMetrics.autonomousActionsExecuted + outcomeMetrics.actionsPendingApproval + outcomeMetrics.actionsBlockedByPolicy)) * 100).toFixed(1)}%
                </span>
              </div>
              <div className="h-3 bg-slate-200 rounded-full overflow-hidden">
                <div
                  className="h-full bg-green-500 rounded-full"
                  style={{
                    width: `${(outcomeMetrics.autonomousActionsExecuted / (outcomeMetrics.autonomousActionsExecuted + outcomeMetrics.actionsPendingApproval + outcomeMetrics.actionsBlockedByPolicy)) * 100}%`
                  }}
                />
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-slate-200">
          <div className="p-4 border-b border-slate-200">
            <h2 className="font-semibold text-slate-900">Attribution by Playbook</h2>
          </div>
          <div className="p-4">
            <div className="space-y-4">
              {[
                { name: 'Compressor Thermal Management', savings: 1842, actions: 45 },
                { name: 'HVAC Efficiency Optimization', savings: 1256, actions: 38 },
                { name: 'Pump Vibration Response', savings: 892, actions: 22 },
                { name: 'Predictive Bearing Replacement', savings: 599, actions: 12 },
              ].map((playbook) => (
                <div key={playbook.name} className="flex items-center gap-4">
                  <div className="flex-1">
                    <p className="text-sm font-medium text-slate-900">{playbook.name}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-xs text-green-600">${playbook.savings}</span>
                      <span className="text-xs text-slate-400">•</span>
                      <span className="text-xs text-slate-500">{playbook.actions} actions</span>
                    </div>
                  </div>
                  <div className="w-24 h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-orange-500 rounded-full"
                      style={{ width: `${(playbook.savings / 2000) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Site-level Attribution */}
      <div className="bg-white rounded-xl border border-slate-200">
        <div className="p-4 border-b border-slate-200 flex items-center justify-between">
          <h2 className="font-semibold text-slate-900">Site-Level Attribution</h2>
          <button className="text-sm text-orange-600 hover:text-orange-700 flex items-center gap-1">
            <BarChart3 className="w-4 h-4" />
            View Details
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-slate-50">
              <tr>
                <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Site</th>
                <th className="text-right px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Energy Saved (kWh)</th>
                <th className="text-right px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Cost Savings</th>
                <th className="text-right px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Downtime Avoided</th>
                <th className="text-right px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Actions Executed</th>
                <th className="text-right px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Trend</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {[
                { name: 'Galveston Platform A', energy: 18420, cost: 1842, downtime: 52, actions: 68, trend: 'up' },
                { name: 'Houston Processing', energy: 15230, cost: 1523, downtime: 41, actions: 52, trend: 'up' },
                { name: 'Midland Compression', energy: 12242, cost: 1224, downtime: 34, actions: 36, trend: 'stable' },
              ].map((site) => (
                <tr key={site.name} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <span className="font-medium text-slate-900">{site.name}</span>
                  </td>
                  <td className="px-4 py-3 text-right font-medium text-slate-900">
                    {site.energy.toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right font-medium text-green-600">
                    ${site.cost.toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right text-slate-700">
                    {site.downtime}h
                  </td>
                  <td className="px-4 py-3 text-right text-slate-700">
                    {site.actions}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {site.trend === 'up' ? (
                      <TrendingUp className="w-4 h-4 text-green-500 inline" />
                    ) : (
                      <Activity className="w-4 h-4 text-slate-400 inline" />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
