import { useState, useMemo } from 'react';
import {
  Target, TrendingUp, TrendingDown, AlertTriangle, CheckCircle, Clock,
  BarChart3, PieChart, Activity, Calendar, Download, Filter, RefreshCw,
  ArrowUpRight, ArrowDownRight, Minus, Eye, DollarSign, Truck, Users
} from 'lucide-react';

interface EventMetrics {
  period: string;
  eventRecall: number;
  alertPrecision: number;
  f1Score: number;
  avgLeadTimeHours: number;
  fpPerAssetMonth: number;
  truePositives: number;
  falsePositives: number;
  falseNegatives: number;
  totalEvents: number;
  totalAlerts: number;
}

interface FaultTypeMetrics {
  faultType: string;
  eventCount: number;
  recall: number;
  precision: number;
  avgLeadTimeHours: number;
  trend: 'improving' | 'stable' | 'worsening';
}

interface LeadTimeDistribution {
  binLabel: string;
  count: number;
  percent: number;
  isActionable: boolean;
}

const mockCurrentMetrics: EventMetrics = {
  period: 'Jan 2024',
  eventRecall: 0.87,
  alertPrecision: 0.72,
  f1Score: 0.79,
  avgLeadTimeHours: 18.5,
  fpPerAssetMonth: 1.2,
  truePositives: 156,
  falsePositives: 61,
  falseNegatives: 23,
  totalEvents: 179,
  totalAlerts: 217,
};

const mockPriorMetrics: EventMetrics = {
  period: 'Dec 2023',
  eventRecall: 0.82,
  alertPrecision: 0.68,
  f1Score: 0.74,
  avgLeadTimeHours: 14.2,
  fpPerAssetMonth: 1.8,
  truePositives: 142,
  falsePositives: 67,
  falseNegatives: 31,
  totalEvents: 173,
  totalAlerts: 209,
};

const mockFaultTypeMetrics: FaultTypeMetrics[] = [
  { faultType: 'Compressor Degradation', eventCount: 45, recall: 0.91, precision: 0.78, avgLeadTimeHours: 24, trend: 'improving' },
  { faultType: 'Refrigerant Leak', eventCount: 32, recall: 0.94, precision: 0.85, avgLeadTimeHours: 12, trend: 'stable' },
  { faultType: 'Condenser Fouling', eventCount: 28, recall: 0.82, precision: 0.71, avgLeadTimeHours: 36, trend: 'improving' },
  { faultType: 'Evaporator Frost', eventCount: 41, recall: 0.78, precision: 0.65, avgLeadTimeHours: 8, trend: 'worsening' },
  { faultType: 'Fan Motor Failure', eventCount: 18, recall: 0.89, precision: 0.76, avgLeadTimeHours: 16, trend: 'stable' },
  { faultType: 'Electrical Issues', eventCount: 15, recall: 0.73, precision: 0.62, avgLeadTimeHours: 6, trend: 'worsening' },
];

const mockLeadTimeDistribution: LeadTimeDistribution[] = [
  { binLabel: '0-4h', count: 28, percent: 15, isActionable: false },
  { binLabel: '4-8h', count: 35, percent: 19, isActionable: true },
  { binLabel: '8-16h', count: 42, percent: 23, isActionable: true },
  { binLabel: '16-24h', count: 38, percent: 21, isActionable: true },
  { binLabel: '24-48h', count: 26, percent: 14, isActionable: true },
  { binLabel: '48h+', count: 14, percent: 8, isActionable: true },
];

const mockTrendData = [
  { month: 'Aug', recall: 0.75, precision: 0.62 },
  { month: 'Sep', recall: 0.78, precision: 0.65 },
  { month: 'Oct', recall: 0.80, precision: 0.66 },
  { month: 'Nov', recall: 0.82, precision: 0.68 },
  { month: 'Dec', recall: 0.82, precision: 0.68 },
  { month: 'Jan', recall: 0.87, precision: 0.72 },
];

function MetricCard({ 
  label, 
  value, 
  format, 
  priorValue, 
  target, 
  icon: Icon,
  goodDirection = 'up'
}: { 
  label: string; 
  value: number; 
  format: 'percent' | 'number' | 'hours' | 'currency';
  priorValue?: number;
  target?: number;
  icon: typeof Target;
  goodDirection?: 'up' | 'down';
}) {
  const formatValue = (v: number) => {
    switch (format) {
      case 'percent': return `${(v * 100).toFixed(1)}%`;
      case 'hours': return `${v.toFixed(1)}h`;
      case 'currency': return `$${v.toLocaleString()}`;
      default: return v.toFixed(1);
    }
  };

  const change = priorValue ? ((value - priorValue) / priorValue) * 100 : 0;
  const isGood = goodDirection === 'up' ? change > 0 : change < 0;
  const meetsTarget = target ? (goodDirection === 'up' ? value >= target : value <= target) : null;

  return (
    <div className="bg-white rounded-xl p-4 border border-slate-200">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-slate-500">{label}</span>
        <Icon className="w-5 h-5 text-slate-400" />
      </div>
      <div className="flex items-end gap-2">
        <p className="text-2xl font-bold text-slate-900">{formatValue(value)}</p>
        {priorValue && change !== 0 && (
          <span className={`flex items-center text-sm ${isGood ? 'text-green-600' : 'text-red-600'}`}>
            {change > 0 ? <ArrowUpRight className="w-4 h-4" /> : <ArrowDownRight className="w-4 h-4" />}
            {Math.abs(change).toFixed(1)}%
          </span>
        )}
      </div>
      {target && (
        <div className="mt-2 flex items-center gap-2">
          <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
            <div 
              className={`h-full rounded-full ${meetsTarget ? 'bg-green-500' : 'bg-amber-500'}`}
              style={{ width: `${Math.min((value / target) * 100, 100)}%` }}
            />
          </div>
          <span className="text-xs text-slate-500">Target: {formatValue(target)}</span>
        </div>
      )}
    </div>
  );
}

export default function EvaluationDashboardPage() {
  const [period, setPeriod] = useState('30d');
  const [view, setView] = useState<'overview' | 'faults' | 'leadtime' | 'burden'>('overview');

  const confusionMatrix = useMemo(() => ({
    tp: mockCurrentMetrics.truePositives,
    fp: mockCurrentMetrics.falsePositives,
    fn: mockCurrentMetrics.falseNegatives,
    total: mockCurrentMetrics.totalAlerts,
  }), []);

  const actionableRate = useMemo(() => {
    const actionable = mockLeadTimeDistribution.filter(d => d.isActionable).reduce((sum, d) => sum + d.count, 0);
    const total = mockLeadTimeDistribution.reduce((sum, d) => sum + d.count, 0);
    return actionable / total;
  }, []);

  const gradeScore = useMemo(() => {
    const recallScore = mockCurrentMetrics.eventRecall >= 0.85 ? 25 : mockCurrentMetrics.eventRecall >= 0.75 ? 20 : 15;
    const precisionScore = mockCurrentMetrics.alertPrecision >= 0.75 ? 25 : mockCurrentMetrics.alertPrecision >= 0.65 ? 20 : 15;
    const leadTimeScore = mockCurrentMetrics.avgLeadTimeHours >= 16 ? 25 : mockCurrentMetrics.avgLeadTimeHours >= 8 ? 20 : 15;
    const fpScore = mockCurrentMetrics.fpPerAssetMonth <= 1 ? 25 : mockCurrentMetrics.fpPerAssetMonth <= 2 ? 20 : 15;
    const total = recallScore + precisionScore + leadTimeScore + fpScore;
    if (total >= 90) return 'A';
    if (total >= 80) return 'B';
    if (total >= 70) return 'C';
    if (total >= 60) return 'D';
    return 'F';
  }, []);

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">PdM Evaluation Dashboard</h1>
          <p className="text-slate-500">Event-based KPI analysis and model performance proof</p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            className="px-3 py-2 border border-slate-200 rounded-lg text-sm"
          >
            <option value="7d">Last 7 Days</option>
            <option value="30d">Last 30 Days</option>
            <option value="90d">Last 90 Days</option>
            <option value="ytd">Year to Date</option>
          </select>
          <button className="flex items-center gap-2 px-4 py-2 bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200">
            <Download className="w-4 h-4" />
            Export Report
          </button>
        </div>
      </div>

      {/* Overall Grade */}
      <div className="bg-gradient-to-r from-orange-50 to-amber-50 rounded-xl border border-orange-200 p-6">
        <div className="flex items-center gap-6">
          <div className={`w-20 h-20 rounded-full flex items-center justify-center text-3xl font-bold ${
            gradeScore === 'A' ? 'bg-green-100 text-green-700' :
            gradeScore === 'B' ? 'bg-blue-100 text-blue-700' :
            gradeScore === 'C' ? 'bg-amber-100 text-amber-700' :
            'bg-red-100 text-red-700'
          }`}>
            {gradeScore}
          </div>
          <div className="flex-1">
            <h2 className="text-xl font-bold text-slate-900">Overall Performance Grade</h2>
            <p className="text-slate-600 mt-1">
              {gradeScore === 'A' ? 'Excellent - All metrics meeting or exceeding targets' :
               gradeScore === 'B' ? 'Good - Most metrics on track, minor improvements needed' :
               gradeScore === 'C' ? 'Fair - Several metrics need attention' :
               'Needs Improvement - Significant gaps in performance'}
            </p>
          </div>
          <div className="grid grid-cols-2 gap-4 text-center">
            <div>
              <p className="text-2xl font-bold text-green-600">${(mockCurrentMetrics.truePositives * 2500).toLocaleString()}</p>
              <p className="text-xs text-slate-500">Est. Value Delivered</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-red-600">${(mockCurrentMetrics.falsePositives * 350).toLocaleString()}</p>
              <p className="text-xs text-slate-500">FP Cost</p>
            </div>
          </div>
        </div>
      </div>

      {/* View Tabs */}
      <div className="flex gap-2 border-b border-slate-200">
        {[
          { id: 'overview', label: 'Overview', icon: BarChart3 },
          { id: 'faults', label: 'By Fault Type', icon: Activity },
          { id: 'leadtime', label: 'Lead Time', icon: Clock },
          { id: 'burden', label: 'FP Burden', icon: AlertTriangle },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setView(tab.id as typeof view)}
            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
              view === tab.id 
                ? 'border-orange-500 text-orange-600' 
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            <tab.icon className="w-4 h-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Overview View */}
      {view === 'overview' && (
        <div className="space-y-6">
          {/* Key Metrics */}
          <div className="grid grid-cols-5 gap-4">
            <MetricCard 
              label="Event Recall" 
              value={mockCurrentMetrics.eventRecall} 
              format="percent"
              priorValue={mockPriorMetrics.eventRecall}
              target={0.85}
              icon={Target}
            />
            <MetricCard 
              label="Alert Precision" 
              value={mockCurrentMetrics.alertPrecision} 
              format="percent"
              priorValue={mockPriorMetrics.alertPrecision}
              target={0.75}
              icon={CheckCircle}
            />
            <MetricCard 
              label="F1 Score" 
              value={mockCurrentMetrics.f1Score} 
              format="percent"
              priorValue={mockPriorMetrics.f1Score}
              icon={TrendingUp}
            />
            <MetricCard 
              label="Avg Lead Time" 
              value={mockCurrentMetrics.avgLeadTimeHours} 
              format="hours"
              priorValue={mockPriorMetrics.avgLeadTimeHours}
              target={12}
              icon={Clock}
            />
            <MetricCard 
              label="FP/Asset/Month" 
              value={mockCurrentMetrics.fpPerAssetMonth} 
              format="number"
              priorValue={mockPriorMetrics.fpPerAssetMonth}
              target={1.5}
              icon={AlertTriangle}
              goodDirection="down"
            />
          </div>

          {/* Confusion Matrix & Trend */}
          <div className="grid grid-cols-2 gap-6">
            {/* Confusion Matrix */}
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <h3 className="font-semibold text-slate-900 mb-4">Alert-Event Confusion Matrix</h3>
              <div className="grid grid-cols-3 gap-2">
                <div></div>
                <div className="text-center text-xs font-medium text-slate-500 py-2">Event Occurred</div>
                <div className="text-center text-xs font-medium text-slate-500 py-2">No Event</div>
                
                <div className="text-xs font-medium text-slate-500 py-6 text-right pr-2">Alert Fired</div>
                <div className="bg-green-100 rounded-lg p-4 text-center">
                  <p className="text-2xl font-bold text-green-700">{confusionMatrix.tp}</p>
                  <p className="text-xs text-green-600">True Positive</p>
                </div>
                <div className="bg-red-100 rounded-lg p-4 text-center">
                  <p className="text-2xl font-bold text-red-700">{confusionMatrix.fp}</p>
                  <p className="text-xs text-red-600">False Positive</p>
                </div>
                
                <div className="text-xs font-medium text-slate-500 py-6 text-right pr-2">No Alert</div>
                <div className="bg-orange-100 rounded-lg p-4 text-center">
                  <p className="text-2xl font-bold text-orange-700">{confusionMatrix.fn}</p>
                  <p className="text-xs text-orange-600">False Negative</p>
                </div>
                <div className="bg-slate-100 rounded-lg p-4 text-center">
                  <p className="text-2xl font-bold text-slate-500">—</p>
                  <p className="text-xs text-slate-500">True Negative</p>
                </div>
              </div>
            </div>

            {/* Trend Chart */}
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <h3 className="font-semibold text-slate-900 mb-4">6-Month Trend</h3>
              <div className="h-48 flex items-end gap-2">
                {mockTrendData.map((d, i) => (
                  <div key={d.month} className="flex-1 flex flex-col items-center gap-1">
                    <div className="w-full flex gap-1 justify-center" style={{ height: '140px' }}>
                      <div 
                        className="w-3 bg-blue-500 rounded-t"
                        style={{ height: `${d.recall * 140}px`, marginTop: 'auto' }}
                        title={`Recall: ${(d.recall * 100).toFixed(0)}%`}
                      />
                      <div 
                        className="w-3 bg-green-500 rounded-t"
                        style={{ height: `${d.precision * 140}px`, marginTop: 'auto' }}
                        title={`Precision: ${(d.precision * 100).toFixed(0)}%`}
                      />
                    </div>
                    <span className="text-xs text-slate-500">{d.month}</span>
                  </div>
                ))}
              </div>
              <div className="flex justify-center gap-4 mt-2">
                <span className="flex items-center gap-1 text-xs text-slate-600">
                  <div className="w-3 h-3 bg-blue-500 rounded" /> Recall
                </span>
                <span className="flex items-center gap-1 text-xs text-slate-600">
                  <div className="w-3 h-3 bg-green-500 rounded" /> Precision
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* By Fault Type View */}
      {view === 'faults' && (
        <div className="bg-white rounded-xl border border-slate-200">
          <div className="p-4 border-b border-slate-200">
            <h3 className="font-semibold text-slate-900">Performance by Fault Type</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-slate-50">
                  <th className="text-left text-xs font-medium text-slate-500 px-4 py-3">Fault Type</th>
                  <th className="text-center text-xs font-medium text-slate-500 px-4 py-3">Events</th>
                  <th className="text-center text-xs font-medium text-slate-500 px-4 py-3">Recall</th>
                  <th className="text-center text-xs font-medium text-slate-500 px-4 py-3">Precision</th>
                  <th className="text-center text-xs font-medium text-slate-500 px-4 py-3">Avg Lead Time</th>
                  <th className="text-center text-xs font-medium text-slate-500 px-4 py-3">Trend</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {mockFaultTypeMetrics.map((ft) => (
                  <tr key={ft.faultType} className="hover:bg-slate-50">
                    <td className="px-4 py-3 font-medium text-slate-900">{ft.faultType}</td>
                    <td className="px-4 py-3 text-center text-slate-600">{ft.eventCount}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`px-2 py-1 rounded text-sm font-medium ${
                        ft.recall >= 0.85 ? 'bg-green-100 text-green-700' :
                        ft.recall >= 0.75 ? 'bg-amber-100 text-amber-700' :
                        'bg-red-100 text-red-700'
                      }`}>
                        {(ft.recall * 100).toFixed(0)}%
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={`px-2 py-1 rounded text-sm font-medium ${
                        ft.precision >= 0.75 ? 'bg-green-100 text-green-700' :
                        ft.precision >= 0.65 ? 'bg-amber-100 text-amber-700' :
                        'bg-red-100 text-red-700'
                      }`}>
                        {(ft.precision * 100).toFixed(0)}%
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center text-slate-600">{ft.avgLeadTimeHours}h</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`flex items-center justify-center gap-1 text-sm ${
                        ft.trend === 'improving' ? 'text-green-600' :
                        ft.trend === 'worsening' ? 'text-red-600' :
                        'text-slate-500'
                      }`}>
                        {ft.trend === 'improving' ? <TrendingUp className="w-4 h-4" /> :
                         ft.trend === 'worsening' ? <TrendingDown className="w-4 h-4" /> :
                         <Minus className="w-4 h-4" />}
                        {ft.trend}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Lead Time View */}
      {view === 'leadtime' && (
        <div className="space-y-6">
          <div className="grid grid-cols-3 gap-4">
            <MetricCard label="Mean Lead Time" value={mockCurrentMetrics.avgLeadTimeHours} format="hours" icon={Clock} />
            <MetricCard label="Actionable Rate" value={actionableRate} format="percent" target={0.8} icon={CheckCircle} />
            <MetricCard label="<4h (Too Late)" value={0.15} format="percent" icon={AlertTriangle} goodDirection="down" />
          </div>
          
          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <h3 className="font-semibold text-slate-900 mb-4">Lead Time Distribution</h3>
            <div className="h-64 flex items-end gap-2">
              {mockLeadTimeDistribution.map((bin) => (
                <div key={bin.binLabel} className="flex-1 flex flex-col items-center">
                  <div 
                    className={`w-full rounded-t ${bin.isActionable ? 'bg-green-500' : 'bg-red-400'}`}
                    style={{ height: `${bin.percent * 3}px` }}
                  />
                  <div className="mt-2 text-center">
                    <p className="text-sm font-medium text-slate-900">{bin.count}</p>
                    <p className="text-xs text-slate-500">{bin.binLabel}</p>
                  </div>
                </div>
              ))}
            </div>
            <div className="flex justify-center gap-4 mt-4 pt-4 border-t border-slate-100">
              <span className="flex items-center gap-2 text-sm text-slate-600">
                <div className="w-4 h-4 bg-green-500 rounded" /> Actionable (≥4h lead time)
              </span>
              <span className="flex items-center gap-2 text-sm text-slate-600">
                <div className="w-4 h-4 bg-red-400 rounded" /> Too Late (&lt;4h lead time)
              </span>
            </div>
          </div>
        </div>
      )}

      {/* FP Burden View */}
      {view === 'burden' && (
        <div className="space-y-6">
          <div className="grid grid-cols-4 gap-4">
            <MetricCard label="FP Total" value={mockCurrentMetrics.falsePositives} format="number" icon={AlertTriangle} />
            <MetricCard label="FP/Asset/Month" value={mockCurrentMetrics.fpPerAssetMonth} format="number" target={1.5} icon={Users} goodDirection="down" />
            <MetricCard label="Est. Wasted Hours" value={mockCurrentMetrics.falsePositives * 0.5} format="hours" icon={Clock} goodDirection="down" />
            <MetricCard label="Unnecessary Dispatches" value={Math.round(mockCurrentMetrics.falsePositives * 0.3)} format="number" icon={Truck} goodDirection="down" />
          </div>

          <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-600 mt-0.5" />
              <div>
                <h3 className="font-semibold text-amber-900">Trust Erosion Risk: Medium</h3>
                <p className="text-sm text-amber-700 mt-1">
                  At {mockCurrentMetrics.fpPerAssetMonth.toFixed(1)} false positives per asset per month, 
                  operator trust may begin to erode. Target is ≤1.5 FP/asset/month. 
                  Focus on improving precision for Evaporator Frost and Electrical Issues fault types.
                </p>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <h3 className="font-semibold text-slate-900 mb-4">Improvement Recommendations</h3>
            <div className="space-y-3">
              {[
                { priority: 'high', rec: 'Increase confidence threshold for Evaporator Frost alerts from 0.7 to 0.8', impact: '-12 FP/month' },
                { priority: 'high', rec: 'Add regime gating to suppress alerts during scheduled defrost cycles', impact: '-8 FP/month' },
                { priority: 'medium', rec: 'Retrain Electrical Issues model with more labeled examples', impact: '-5 FP/month' },
                { priority: 'low', rec: 'Extend cooldown window for low-severity repeated alerts', impact: '-3 FP/month' },
              ].map((item, i) => (
                <div key={i} className="flex items-start gap-3 p-3 bg-slate-50 rounded-lg">
                  <span className={`px-2 py-0.5 text-xs font-medium rounded ${
                    item.priority === 'high' ? 'bg-red-100 text-red-700' :
                    item.priority === 'medium' ? 'bg-amber-100 text-amber-700' :
                    'bg-blue-100 text-blue-700'
                  }`}>
                    {item.priority}
                  </span>
                  <div className="flex-1">
                    <p className="text-sm text-slate-700">{item.rec}</p>
                  </div>
                  <span className="text-sm font-medium text-green-600">{item.impact}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
