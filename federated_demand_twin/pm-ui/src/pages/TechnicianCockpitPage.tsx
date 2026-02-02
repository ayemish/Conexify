import { useState } from 'react';
import {
  Wrench, MapPin, Clock, CheckCircle, AlertTriangle, ChevronRight,
  Phone, Navigation, FileText, Camera, Package, Shield, ThermometerSun,
  ArrowLeft, Play, Pause, Check, X, MessageSquare
} from 'lucide-react';

interface Assignment {
  id: string;
  workOrderNumber: string;
  caseNumber: string;
  site: { name: string; address: string; phone: string };
  asset: { name: string; type: string; location: string };
  fault: { type: string; description: string; confidence: number };
  priority: 'emergency' | 'urgent' | 'high' | 'medium' | 'low';
  scheduledArrival: string;
  estimatedDuration: number;
  status: 'scheduled' | 'en_route' | 'on_site' | 'in_progress' | 'completed';
  brief: TechnicianBrief;
}

interface TechnicianBrief {
  headline: string;
  firstAction: string;
  requiredParts: string[];
  requiredTools: string[];
  safetyReminders: string[];
  expectedDuration: string;
}

const mockAssignments: Assignment[] = [
  {
    id: 'wo-001', workOrderNumber: 'WO-2024-0891', caseNumber: 'PDM-2024-0142',
    site: { name: 'Store #42 - Oakdale', address: '1234 Main St, Oakdale, CA 94561', phone: '(555) 123-4567' },
    asset: { name: 'RTU-101', type: 'Rooftop Unit', location: 'Roof, Northwest Corner' },
    fault: { type: 'Compressor Degradation', description: 'Compressor showing signs of degradation, reduced cooling capacity detected', confidence: 0.89 },
    priority: 'high', scheduledArrival: '2024-01-28T10:00:00Z', estimatedDuration: 90,
    status: 'en_route',
    brief: {
      headline: 'Check compressor amp draw and superheat - likely capacitor or valve issue',
      firstAction: 'Measure compressor amp draw and compare to nameplate',
      requiredParts: ['Run capacitor 45/5 MFD', 'Contactor 40A', 'Hard start kit'],
      requiredTools: ['Clamp meter', 'Refrigerant gauges', 'Multimeter', 'Capacitor tester'],
      safetyReminders: ['Lock out/tag out before electrical work', 'Verify capacitor discharge', 'Check for refrigerant leaks'],
      expectedDuration: '1.5 hours'
    }
  },
  {
    id: 'wo-002', workOrderNumber: 'WO-2024-0892', caseNumber: 'PDM-2024-0144',
    site: { name: 'Store #42 - Oakdale', address: '1234 Main St, Oakdale, CA 94561', phone: '(555) 123-4567' },
    asset: { name: 'Walk-in Freezer #3', type: 'Walk-in Freezer', location: 'Back of store, behind dairy' },
    fault: { type: 'Evaporator Frost', description: 'Excessive frost buildup on evaporator coils', confidence: 0.82 },
    priority: 'medium', scheduledArrival: '2024-01-28T12:00:00Z', estimatedDuration: 60,
    status: 'scheduled',
    brief: {
      headline: 'Check defrost system - likely heater or timer failure',
      firstAction: 'Verify defrost cycle is initiating per schedule',
      requiredParts: ['Defrost heater element', 'Defrost timer', 'Door gasket'],
      requiredTools: ['Multimeter', 'Temperature probe', 'Screwdriver set'],
      safetyReminders: ['Wait for defrost cycle to complete before inspection', 'Wear cold weather PPE'],
      expectedDuration: '1 hour'
    }
  },
];

const priorityConfig = {
  emergency: { bg: 'bg-red-100', text: 'text-red-700', border: 'border-red-300' },
  urgent: { bg: 'bg-orange-100', text: 'text-orange-700', border: 'border-orange-300' },
  high: { bg: 'bg-amber-100', text: 'text-amber-700', border: 'border-amber-300' },
  medium: { bg: 'bg-yellow-100', text: 'text-yellow-700', border: 'border-yellow-300' },
  low: { bg: 'bg-blue-100', text: 'text-blue-700', border: 'border-blue-300' },
};

const statusConfig = {
  scheduled: { bg: 'bg-slate-100', text: 'text-slate-700', label: 'Scheduled' },
  en_route: { bg: 'bg-blue-100', text: 'text-blue-700', label: 'En Route' },
  on_site: { bg: 'bg-indigo-100', text: 'text-indigo-700', label: 'On Site' },
  in_progress: { bg: 'bg-purple-100', text: 'text-purple-700', label: 'In Progress' },
  completed: { bg: 'bg-green-100', text: 'text-green-700', label: 'Completed' },
};

export default function TechnicianCockpitPage() {
  const [selectedAssignment, setSelectedAssignment] = useState<Assignment | null>(null);
  const [activeTab, setActiveTab] = useState<'brief' | 'details' | 'completion'>('brief');

  if (selectedAssignment) {
    return (
      <AssignmentDetail 
        assignment={selectedAssignment} 
        onBack={() => setSelectedAssignment(null)}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
      />
    );
  }

  return (
    <div className="p-4 space-y-4 max-w-lg mx-auto">
      {/* Header */}
      <div className="text-center py-4">
        <h1 className="text-xl font-bold text-slate-900">My Assignments</h1>
        <p className="text-slate-500 text-sm">Today's work orders</p>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-white rounded-xl p-3 border border-slate-200 text-center">
          <p className="text-2xl font-bold text-slate-900">{mockAssignments.length}</p>
          <p className="text-xs text-slate-500">Total</p>
        </div>
        <div className="bg-white rounded-xl p-3 border border-blue-200 text-center bg-blue-50">
          <p className="text-2xl font-bold text-blue-700">
            {mockAssignments.filter(a => a.status === 'en_route' || a.status === 'in_progress').length}
          </p>
          <p className="text-xs text-blue-600">Active</p>
        </div>
        <div className="bg-white rounded-xl p-3 border border-green-200 text-center bg-green-50">
          <p className="text-2xl font-bold text-green-700">
            {mockAssignments.filter(a => a.status === 'completed').length}
          </p>
          <p className="text-xs text-green-600">Done</p>
        </div>
      </div>

      {/* Assignment List */}
      <div className="space-y-3">
        {mockAssignments.map((assignment) => (
          <div
            key={assignment.id}
            onClick={() => setSelectedAssignment(assignment)}
            className={`bg-white rounded-xl border ${priorityConfig[assignment.priority].border} p-4 cursor-pointer active:bg-slate-50`}
          >
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`px-2 py-0.5 text-xs font-medium rounded ${priorityConfig[assignment.priority].bg} ${priorityConfig[assignment.priority].text}`}>
                    {assignment.priority}
                  </span>
                  <span className={`px-2 py-0.5 text-xs font-medium rounded ${statusConfig[assignment.status].bg} ${statusConfig[assignment.status].text}`}>
                    {statusConfig[assignment.status].label}
                  </span>
                </div>
                <h3 className="font-semibold text-slate-900">{assignment.fault.type}</h3>
                <p className="text-sm text-slate-600 mt-1">{assignment.asset.name} • {assignment.site.name}</p>
                <div className="flex items-center gap-3 mt-2 text-xs text-slate-500">
                  <span className="flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {new Date(assignment.scheduledArrival).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                  <span className="flex items-center gap-1">
                    <Wrench className="w-3 h-3" />
                    ~{assignment.estimatedDuration} min
                  </span>
                </div>
              </div>
              <ChevronRight className="w-5 h-5 text-slate-400" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function AssignmentDetail({ 
  assignment, 
  onBack, 
  activeTab, 
  setActiveTab 
}: { 
  assignment: Assignment; 
  onBack: () => void;
  activeTab: 'brief' | 'details' | 'completion';
  setActiveTab: (tab: 'brief' | 'details' | 'completion') => void;
}) {
  const [workStatus, setWorkStatus] = useState(assignment.status);

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <div className={`${priorityConfig[assignment.priority].bg} px-4 py-3`}>
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="p-1">
            <ArrowLeft className="w-5 h-5 text-slate-700" />
          </button>
          <div className="flex-1">
            <p className="text-xs text-slate-600">{assignment.workOrderNumber}</p>
            <h1 className="font-bold text-slate-900">{assignment.fault.type}</h1>
          </div>
          <span className={`px-2 py-1 text-xs font-medium rounded ${statusConfig[workStatus].bg} ${statusConfig[workStatus].text}`}>
            {statusConfig[workStatus].label}
          </span>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="bg-white border-b border-slate-200 px-4 py-3">
        <div className="flex gap-2">
          {workStatus === 'scheduled' && (
            <button 
              onClick={() => setWorkStatus('en_route')}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg"
            >
              <Navigation className="w-4 h-4" />
              Start Route
            </button>
          )}
          {workStatus === 'en_route' && (
            <button 
              onClick={() => setWorkStatus('on_site')}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg"
            >
              <MapPin className="w-4 h-4" />
              Arrived
            </button>
          )}
          {workStatus === 'on_site' && (
            <button 
              onClick={() => setWorkStatus('in_progress')}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg"
            >
              <Play className="w-4 h-4" />
              Start Work
            </button>
          )}
          {workStatus === 'in_progress' && (
            <>
              <button className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-slate-200 text-slate-700 rounded-lg">
                <Pause className="w-4 h-4" />
                Pause
              </button>
              <button 
                onClick={() => { setWorkStatus('completed'); setActiveTab('completion'); }}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg"
              >
                <Check className="w-4 h-4" />
                Complete
              </button>
            </>
          )}
          <a href={`tel:${assignment.site.phone}`} className="p-2 bg-slate-100 rounded-lg">
            <Phone className="w-5 h-5 text-slate-600" />
          </a>
        </div>
      </div>

      {/* Tabs */}
      <div className="bg-white border-b border-slate-200 px-4">
        <div className="flex">
          {(['brief', 'details', 'completion'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`flex-1 py-3 text-sm font-medium border-b-2 ${
                activeTab === tab 
                  ? 'border-orange-500 text-orange-600' 
                  : 'border-transparent text-slate-500'
              }`}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      <div className="p-4">
        {activeTab === 'brief' && (
          <div className="space-y-4">
            {/* Headline */}
            <div className="bg-orange-50 border border-orange-200 rounded-xl p-4">
              <div className="flex items-start gap-3">
                <AlertTriangle className="w-5 h-5 text-orange-600 mt-0.5" />
                <div>
                  <p className="font-medium text-orange-900">{assignment.brief.headline}</p>
                  <p className="text-sm text-orange-700 mt-1">Confidence: {(assignment.fault.confidence * 100).toFixed(0)}%</p>
                </div>
              </div>
            </div>

            {/* First Action */}
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <h3 className="font-semibold text-slate-900 flex items-center gap-2">
                <Play className="w-4 h-4 text-green-600" />
                Start Here
              </h3>
              <p className="text-slate-700 mt-2">{assignment.brief.firstAction}</p>
            </div>

            {/* What to Bring */}
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <h3 className="font-semibold text-slate-900 flex items-center gap-2 mb-3">
                <Package className="w-4 h-4 text-blue-600" />
                What to Bring
              </h3>
              <div className="space-y-3">
                <div>
                  <p className="text-xs font-medium text-slate-500 uppercase mb-1">Parts</p>
                  <div className="flex flex-wrap gap-2">
                    {assignment.brief.requiredParts.map((part, i) => (
                      <span key={i} className="px-2 py-1 bg-blue-50 text-blue-700 text-sm rounded">
                        {part}
                      </span>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="text-xs font-medium text-slate-500 uppercase mb-1">Tools</p>
                  <div className="flex flex-wrap gap-2">
                    {assignment.brief.requiredTools.map((tool, i) => (
                      <span key={i} className="px-2 py-1 bg-slate-100 text-slate-700 text-sm rounded">
                        {tool}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Safety */}
            <div className="bg-red-50 rounded-xl border border-red-200 p-4">
              <h3 className="font-semibold text-red-900 flex items-center gap-2 mb-3">
                <Shield className="w-4 h-4" />
                Safety Reminders
              </h3>
              <ul className="space-y-2">
                {assignment.brief.safetyReminders.map((reminder, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-red-800">
                    <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                    {reminder}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {activeTab === 'details' && (
          <div className="space-y-4">
            {/* Location */}
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <h3 className="font-semibold text-slate-900 flex items-center gap-2 mb-3">
                <MapPin className="w-4 h-4 text-slate-600" />
                Location
              </h3>
              <p className="font-medium text-slate-900">{assignment.site.name}</p>
              <p className="text-slate-600">{assignment.site.address}</p>
              <p className="text-slate-600 mt-2">Asset Location: {assignment.asset.location}</p>
              <a 
                href={`https://maps.google.com/?q=${encodeURIComponent(assignment.site.address)}`}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-3 flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg"
              >
                <Navigation className="w-4 h-4" />
                Open in Maps
              </a>
            </div>

            {/* Asset Info */}
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <h3 className="font-semibold text-slate-900 flex items-center gap-2 mb-3">
                <ThermometerSun className="w-4 h-4 text-slate-600" />
                Asset Details
              </h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-slate-500">Name:</span>
                  <span className="font-medium">{assignment.asset.name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Type:</span>
                  <span className="font-medium">{assignment.asset.type}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Case #:</span>
                  <span className="font-medium">{assignment.caseNumber}</span>
                </div>
              </div>
            </div>

            {/* Fault Description */}
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <h3 className="font-semibold text-slate-900 flex items-center gap-2 mb-3">
                <FileText className="w-4 h-4 text-slate-600" />
                Issue Description
              </h3>
              <p className="text-slate-700">{assignment.fault.description}</p>
            </div>
          </div>
        )}

        {activeTab === 'completion' && (
          <div className="space-y-4">
            {/* Close Code */}
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <h3 className="font-semibold text-slate-900 mb-3">Resolution</h3>
              <div className="space-y-2">
                {['Confirmed & Fixed', 'No Fault Found', 'Deferred - Parts Needed', 'Unable to Repair'].map((option) => (
                  <label key={option} className="flex items-center gap-3 p-3 border border-slate-200 rounded-lg cursor-pointer hover:bg-slate-50">
                    <input type="radio" name="closeCode" className="w-4 h-4 text-orange-600" />
                    <span className="text-slate-700">{option}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* Notes */}
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <h3 className="font-semibold text-slate-900 flex items-center gap-2 mb-3">
                <MessageSquare className="w-4 h-4 text-slate-600" />
                Notes
              </h3>
              <textarea 
                className="w-full p-3 border border-slate-200 rounded-lg text-sm" 
                rows={4}
                placeholder="Describe work performed..."
              />
            </div>

            {/* Photos */}
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <h3 className="font-semibold text-slate-900 flex items-center gap-2 mb-3">
                <Camera className="w-4 h-4 text-slate-600" />
                Photos
              </h3>
              <button className="w-full flex items-center justify-center gap-2 px-4 py-3 border-2 border-dashed border-slate-300 rounded-lg text-slate-600 hover:bg-slate-50">
                <Camera className="w-5 h-5" />
                Add Photos
              </button>
            </div>

            {/* Submit */}
            <button className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-green-600 text-white rounded-lg font-medium">
              <CheckCircle className="w-5 h-5" />
              Submit Completion
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
