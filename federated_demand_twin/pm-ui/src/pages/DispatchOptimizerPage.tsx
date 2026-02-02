import { useState, useMemo } from 'react';
import {
  Truck, MapPin, Clock, DollarSign, Route, Users, Calendar,
  ChevronRight, Check, X, AlertTriangle, Zap, Package,
  ArrowRight, RefreshCw, Settings, TrendingUp, Building2
} from 'lucide-react';

interface DispatchCase {
  id: string;
  caseNumber: string;
  asset: { name: string; type: string };
  site: { id: string; name: string; address: string; lat: number; lng: number };
  fault: { type: string; urgency: 'critical' | 'high' | 'medium' | 'low' };
  ev: number;
  skillsRequired: string[];
  estimatedDuration: number;
  partsNeeded: string[];
  deadline: string;
}

interface Technician {
  id: string;
  name: string;
  skills: string[];
  location: { lat: number; lng: number };
  availability: { start: string; end: string };
  assignedCases: number;
}

interface OptimizedVisit {
  caseId: string;
  arrivalTime: string;
  departureTime: string;
  travelTimeMinutes: number;
  sequence: number;
}

interface OptimizationResult {
  technicianId: string;
  visits: OptimizedVisit[];
  totalTravelTime: number;
  totalServiceTime: number;
  totalEV: number;
  utilizationPercent: number;
}

const mockCases: DispatchCase[] = [
  {
    id: 'case-001', caseNumber: 'PDM-2024-0142',
    asset: { name: 'RTU-101', type: 'rtu' },
    site: { id: 'store-42', name: 'Store #42 - Oakdale', address: '1234 Main St, Oakdale', lat: 37.7749, lng: -122.4194 },
    fault: { type: 'compressor_degradation', urgency: 'high' },
    ev: 2450, skillsRequired: ['hvac', 'refrigeration'], estimatedDuration: 90,
    partsNeeded: ['Run capacitor 45/5 MFD', 'Contactor 40A'], deadline: '2024-01-28T18:00:00Z'
  },
  {
    id: 'case-002', caseNumber: 'PDM-2024-0143',
    asset: { name: 'Dairy Rack B', type: 'rack' },
    site: { id: 'store-18', name: 'Store #18 - Riverside', address: '567 Oak Ave, Riverside', lat: 37.7849, lng: -122.4094 },
    fault: { type: 'refrigerant_leak', urgency: 'critical' },
    ev: 5800, skillsRequired: ['refrigeration', 'epa_608'], estimatedDuration: 120,
    partsNeeded: ['Refrigerant R-404A', 'Leak sealant'], deadline: '2024-01-28T14:00:00Z'
  },
  {
    id: 'case-003', caseNumber: 'PDM-2024-0144',
    asset: { name: 'Walk-in Freezer #3', type: 'walk_in' },
    site: { id: 'store-42', name: 'Store #42 - Oakdale', address: '1234 Main St, Oakdale', lat: 37.7749, lng: -122.4194 },
    fault: { type: 'evaporator_frost', urgency: 'medium' },
    ev: 890, skillsRequired: ['refrigeration'], estimatedDuration: 60,
    partsNeeded: ['Defrost heater'], deadline: '2024-01-29T12:00:00Z'
  },
  {
    id: 'case-004', caseNumber: 'PDM-2024-0145',
    asset: { name: 'RTU-205', type: 'rtu' },
    site: { id: 'store-55', name: 'Store #55 - Fremont', address: '890 Tech Blvd, Fremont', lat: 37.5485, lng: -121.9886 },
    fault: { type: 'fan_motor_failure', urgency: 'high' },
    ev: 1800, skillsRequired: ['hvac'], estimatedDuration: 75,
    partsNeeded: ['Fan motor 1/3 HP'], deadline: '2024-01-28T20:00:00Z'
  },
];

const mockTechnicians: Technician[] = [
  { id: 'tech-001', name: 'Mike Johnson', skills: ['hvac', 'refrigeration', 'epa_608'], location: { lat: 37.7749, lng: -122.4194 }, availability: { start: '08:00', end: '17:00' }, assignedCases: 0 },
  { id: 'tech-002', name: 'Sarah Chen', skills: ['refrigeration', 'epa_608', 'electrical'], location: { lat: 37.5585, lng: -122.2711 }, availability: { start: '07:00', end: '16:00' }, assignedCases: 1 },
  { id: 'tech-003', name: 'Carlos Rodriguez', skills: ['hvac', 'controls'], location: { lat: 37.8044, lng: -122.2712 }, availability: { start: '09:00', end: '18:00' }, assignedCases: 2 },
];

const urgencyConfig = {
  critical: { bg: 'bg-red-100', text: 'text-red-700', border: 'border-red-300' },
  high: { bg: 'bg-orange-100', text: 'text-orange-700', border: 'border-orange-300' },
  medium: { bg: 'bg-yellow-100', text: 'text-yellow-700', border: 'border-yellow-300' },
  low: { bg: 'bg-blue-100', text: 'text-blue-700', border: 'border-blue-300' },
};

export default function DispatchOptimizerPage() {
  const [selectedCases, setSelectedCases] = useState<Set<string>>(new Set(mockCases.map(c => c.id)));
  const [optimizationResult, setOptimizationResult] = useState<OptimizationResult[] | null>(null);
  const [optimizing, setOptimizing] = useState(false);
  const [objective, setObjective] = useState<'minimize_travel' | 'maximize_ev' | 'balance'>('balance');

  const selectedCasesList = useMemo(() => 
    mockCases.filter(c => selectedCases.has(c.id)),
    [selectedCases]
  );

  const batchOpportunities = useMemo(() => {
    const siteGroups = new Map<string, DispatchCase[]>();
    selectedCasesList.forEach(c => {
      const existing = siteGroups.get(c.site.id) || [];
      siteGroups.set(c.site.id, [...existing, c]);
    });
    return Array.from(siteGroups.entries()).filter(([_, cases]) => cases.length > 1);
  }, [selectedCasesList]);

  const stats = useMemo(() => ({
    totalCases: selectedCasesList.length,
    totalEV: selectedCasesList.reduce((sum, c) => sum + c.ev, 0),
    totalDuration: selectedCasesList.reduce((sum, c) => sum + c.estimatedDuration, 0),
    criticalCount: selectedCasesList.filter(c => c.fault.urgency === 'critical').length,
    batchableCount: batchOpportunities.reduce((sum, [_, cases]) => sum + cases.length, 0),
  }), [selectedCasesList, batchOpportunities]);

  const toggleCase = (caseId: string) => {
    const newSelected = new Set(selectedCases);
    if (newSelected.has(caseId)) {
      newSelected.delete(caseId);
    } else {
      newSelected.add(caseId);
    }
    setSelectedCases(newSelected);
  };

  const runOptimization = () => {
    setOptimizing(true);
    // Simulate optimization
    setTimeout(() => {
      setOptimizationResult([
        {
          technicianId: 'tech-001',
          visits: [
            { caseId: 'case-002', arrivalTime: '09:00', departureTime: '11:00', travelTimeMinutes: 25, sequence: 1 },
            { caseId: 'case-001', arrivalTime: '11:30', departureTime: '13:00', travelTimeMinutes: 15, sequence: 2 },
            { caseId: 'case-003', arrivalTime: '13:15', departureTime: '14:15', travelTimeMinutes: 0, sequence: 3 },
          ],
          totalTravelTime: 40,
          totalServiceTime: 270,
          totalEV: 9140,
          utilizationPercent: 87,
        },
        {
          technicianId: 'tech-002',
          visits: [
            { caseId: 'case-004', arrivalTime: '08:30', departureTime: '09:45', travelTimeMinutes: 35, sequence: 1 },
          ],
          totalTravelTime: 35,
          totalServiceTime: 75,
          totalEV: 1800,
          utilizationPercent: 24,
        },
      ]);
      setOptimizing(false);
    }, 1500);
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Dispatch Optimizer</h1>
          <p className="text-slate-500">Batch and optimize technician routes for maximum efficiency</p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={objective}
            onChange={(e) => setObjective(e.target.value as typeof objective)}
            className="px-3 py-2 border border-slate-200 rounded-lg text-sm"
          >
            <option value="minimize_travel">Minimize Travel</option>
            <option value="maximize_ev">Maximize EV</option>
            <option value="balance">Balanced</option>
          </select>
          <button
            onClick={runOptimization}
            disabled={optimizing || selectedCases.size === 0}
            className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 disabled:opacity-50"
          >
            {optimizing ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
            {optimizing ? 'Optimizing...' : 'Optimize Routes'}
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-5 gap-4">
        <div className="bg-white rounded-xl p-4 border border-slate-200">
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-500">Selected Cases</span>
            <Package className="w-5 h-5 text-slate-400" />
          </div>
          <p className="text-2xl font-bold text-slate-900 mt-1">{stats.totalCases}</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-green-200 bg-green-50">
          <div className="flex items-center justify-between">
            <span className="text-sm text-green-600">Total EV</span>
            <DollarSign className="w-5 h-5 text-green-500" />
          </div>
          <p className="text-2xl font-bold text-green-700 mt-1">${stats.totalEV.toLocaleString()}</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-slate-200">
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-500">Service Time</span>
            <Clock className="w-5 h-5 text-slate-400" />
          </div>
          <p className="text-2xl font-bold text-slate-900 mt-1">{Math.round(stats.totalDuration / 60)}h {stats.totalDuration % 60}m</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-red-200 bg-red-50">
          <div className="flex items-center justify-between">
            <span className="text-sm text-red-600">Critical</span>
            <AlertTriangle className="w-5 h-5 text-red-500" />
          </div>
          <p className="text-2xl font-bold text-red-700 mt-1">{stats.criticalCount}</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-blue-200 bg-blue-50">
          <div className="flex items-center justify-between">
            <span className="text-sm text-blue-600">Batchable</span>
            <Route className="w-5 h-5 text-blue-500" />
          </div>
          <p className="text-2xl font-bold text-blue-700 mt-1">{stats.batchableCount}</p>
        </div>
      </div>

      {/* Batch Opportunities */}
      {batchOpportunities.length > 0 && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <Route className="w-5 h-5 text-blue-600" />
            <h3 className="font-semibold text-blue-900">Batch Opportunities Detected</h3>
          </div>
          <div className="flex flex-wrap gap-3">
            {batchOpportunities.map(([siteId, cases]) => (
              <div key={siteId} className="flex items-center gap-2 px-3 py-2 bg-white rounded-lg border border-blue-200">
                <Building2 className="w-4 h-4 text-blue-600" />
                <span className="text-sm font-medium text-blue-900">{cases[0].site.name}</span>
                <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded-full">
                  {cases.length} cases
                </span>
                <span className="text-xs text-blue-600">
                  Save ~{(cases.length - 1) * 30}min travel
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-6">
        {/* Case Selection */}
        <div className="bg-white rounded-xl border border-slate-200">
          <div className="p-4 border-b border-slate-200 flex items-center justify-between">
            <h2 className="font-semibold text-slate-900">Cases to Dispatch</h2>
            <span className="text-sm text-slate-500">{selectedCases.size} selected</span>
          </div>
          <div className="divide-y divide-slate-100 max-h-[500px] overflow-auto">
            {mockCases.map((c) => (
              <div
                key={c.id}
                className={`p-4 cursor-pointer hover:bg-slate-50 ${selectedCases.has(c.id) ? 'bg-orange-50' : ''}`}
                onClick={() => toggleCase(c.id)}
              >
                <div className="flex items-start gap-3">
                  <div className={`w-5 h-5 rounded border-2 flex items-center justify-center ${
                    selectedCases.has(c.id) ? 'bg-orange-600 border-orange-600' : 'border-slate-300'
                  }`}>
                    {selectedCases.has(c.id) && <Check className="w-3 h-3 text-white" />}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium text-slate-900">{c.caseNumber}</span>
                      <span className={`px-2 py-0.5 text-xs font-medium rounded ${urgencyConfig[c.fault.urgency].bg} ${urgencyConfig[c.fault.urgency].text}`}>
                        {c.fault.urgency}
                      </span>
                    </div>
                    <p className="text-sm text-slate-600">{c.fault.type.replace(/_/g, ' ')}</p>
                    <div className="flex items-center gap-3 mt-2 text-xs text-slate-500">
                      <span className="flex items-center gap-1">
                        <MapPin className="w-3 h-3" />
                        {c.site.name}
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {c.estimatedDuration}min
                      </span>
                      <span className="flex items-center gap-1 text-green-600">
                        <DollarSign className="w-3 h-3" />
                        ${c.ev}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Optimization Results */}
        <div className="bg-white rounded-xl border border-slate-200">
          <div className="p-4 border-b border-slate-200">
            <h2 className="font-semibold text-slate-900">Optimized Routes</h2>
          </div>
          {optimizationResult ? (
            <div className="divide-y divide-slate-100">
              {optimizationResult.map((result) => {
                const tech = mockTechnicians.find(t => t.id === result.technicianId);
                return (
                  <div key={result.technicianId} className="p-4">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <div className="w-8 h-8 bg-orange-100 rounded-full flex items-center justify-center">
                          <Users className="w-4 h-4 text-orange-600" />
                        </div>
                        <div>
                          <p className="font-medium text-slate-900">{tech?.name}</p>
                          <p className="text-xs text-slate-500">{result.visits.length} visits</p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-lg font-bold text-green-600">${result.totalEV.toLocaleString()}</p>
                        <p className="text-xs text-slate-500">{result.utilizationPercent}% utilization</p>
                      </div>
                    </div>
                    
                    {/* Route visualization */}
                    <div className="space-y-2">
                      {result.visits.map((visit, idx) => {
                        const caseData = mockCases.find(c => c.id === visit.caseId);
                        return (
                          <div key={visit.caseId} className="flex items-center gap-2">
                            <div className="w-6 h-6 rounded-full bg-slate-200 flex items-center justify-center text-xs font-medium">
                              {idx + 1}
                            </div>
                            <div className="flex-1 flex items-center gap-2 px-3 py-2 bg-slate-50 rounded-lg">
                              <span className="font-medium text-sm">{caseData?.caseNumber}</span>
                              <span className="text-xs text-slate-500">@ {caseData?.site.name}</span>
                              <span className="ml-auto text-xs text-slate-500">
                                {visit.arrivalTime} - {visit.departureTime}
                              </span>
                            </div>
                            {idx < result.visits.length - 1 && (
                              <div className="text-xs text-blue-600 flex items-center gap-1">
                                <Truck className="w-3 h-3" />
                                {result.visits[idx + 1].travelTimeMinutes}min
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>

                    {/* Route stats */}
                    <div className="flex items-center gap-4 mt-3 pt-3 border-t border-slate-100 text-xs text-slate-500">
                      <span className="flex items-center gap-1">
                        <Truck className="w-3 h-3" />
                        Travel: {result.totalTravelTime}min
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        Service: {result.totalServiceTime}min
                      </span>
                    </div>
                  </div>
                );
              })}
              
              {/* Total summary */}
              <div className="p-4 bg-green-50">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-green-900">Optimization Summary</p>
                    <p className="text-xs text-green-700">
                      {optimizationResult.reduce((sum, r) => sum + r.visits.length, 0)} visits across {optimizationResult.length} technicians
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-xl font-bold text-green-700">
                      ${optimizationResult.reduce((sum, r) => sum + r.totalEV, 0).toLocaleString()}
                    </p>
                    <p className="text-xs text-green-600">
                      {optimizationResult.reduce((sum, r) => sum + r.totalTravelTime, 0)}min total travel
                    </p>
                  </div>
                </div>
                <button className="w-full mt-3 flex items-center justify-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700">
                  <Check className="w-4 h-4" />
                  Confirm & Dispatch
                </button>
              </div>
            </div>
          ) : (
            <div className="p-8 text-center text-slate-500">
              <Route className="w-12 h-12 text-slate-300 mx-auto mb-3" />
              <p>Select cases and click "Optimize Routes" to generate dispatch plan</p>
            </div>
          )}
        </div>
      </div>

      {/* Technician Availability */}
      <div className="bg-white rounded-xl border border-slate-200">
        <div className="p-4 border-b border-slate-200">
          <h2 className="font-semibold text-slate-900">Available Technicians</h2>
        </div>
        <div className="p-4">
          <div className="grid grid-cols-3 gap-4">
            {mockTechnicians.map((tech) => (
              <div key={tech.id} className="p-4 border border-slate-200 rounded-lg">
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-10 h-10 bg-slate-100 rounded-full flex items-center justify-center">
                    <Users className="w-5 h-5 text-slate-600" />
                  </div>
                  <div>
                    <p className="font-medium text-slate-900">{tech.name}</p>
                    <p className="text-xs text-slate-500">{tech.availability.start} - {tech.availability.end}</p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1">
                  {tech.skills.map((skill) => (
                    <span key={skill} className="px-2 py-0.5 bg-slate-100 text-slate-600 text-xs rounded">
                      {skill}
                    </span>
                  ))}
                </div>
                <div className="mt-2 text-xs text-slate-500">
                  {tech.assignedCases} cases assigned today
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
