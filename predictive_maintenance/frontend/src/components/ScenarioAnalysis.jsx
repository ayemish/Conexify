import { useState, useEffect, useCallback, useMemo } from 'react'
import { 
  GitBranch, AlertTriangle, Wrench, DollarSign, 
  TrendingUp, Send, Loader2, ChevronDown, ChevronRight,
  Zap, Calendar, BarChart3, Shield, Building, MapPin, Thermometer
} from 'lucide-react'
import { request } from '../services/apiClient'
import FleetApi from '../services/fleetApi'

const SCENARIO_TYPES = [
  { 
    id: 'defer_maintenance', 
    label: 'Defer Maintenance', 
    icon: AlertTriangle,
    description: 'What if we defer maintenance N days?',
    color: '#f59e0b',
    params: ['defer_days'],
  },
  { 
    id: 'replace_vs_repair', 
    label: 'Replace vs Repair', 
    icon: Wrench,
    description: 'Should we replace or repair this asset?',
    color: '#3b82f6',
    params: [],
  },
  { 
    id: 'run_to_failure', 
    label: 'Run to Failure', 
    icon: TrendingUp,
    description: "What's the cost of running to failure?",
    color: '#ef4444',
    params: [],
  },
  {
    id: 'energy_optimization',
    label: 'Energy Optimization',
    icon: Zap,
    description: 'Optimize energy consumption and estimate savings.',
    color: '#22c55e',
    params: ['target_reduction_pct'],
  },
  {
    id: 'preventive_schedule',
    label: 'PM Schedule Optimization',
    icon: Calendar,
    description: 'Find the optimal preventive maintenance interval.',
    color: '#8b5cf6',
    params: ['current_interval_days'],
  },
  {
    id: 'budget_allocation',
    label: 'Budget Allocation',
    icon: DollarSign,
    description: 'Optimize CapEx spend across selected assets.',
    color: '#0ea5e9',
    params: ['budget_amount'],
  },
  {
    id: 'efficiency_degradation',
    label: 'Efficiency Degradation',
    icon: TrendingUp,
    description: 'Model efficiency loss and intervention timing.',
    color: '#f97316',
    params: ['forecast_months'],
  },
  {
    id: 'fleet_prioritization',
    label: 'Fleet Prioritization',
    icon: BarChart3,
    description: 'Rank assets by maintenance urgency and ROI.',
    color: '#6366f1',
    params: [],
  },
  {
    id: 'risk_assessment',
    label: 'Risk Assessment',
    icon: Shield,
    description: 'Failure probability and business impact analysis.',
    color: '#dc2626',
    params: ['time_horizon_days'],
  },
]

const inputStyle = {
  width: '100%', padding: '0.5rem 0.75rem', borderRadius: 8,
  border: '1px solid #e2e8f0', fontSize: '0.85rem', boxSizing: 'border-box',
  background: '#fff', color: '#1e293b', fontFamily: 'inherit',
}

const labelStyle = {
  display: 'block', fontSize: '0.75rem', fontWeight: 600,
  color: '#475569', marginBottom: 4, textTransform: 'uppercase',
  letterSpacing: '0.03em',
}

function AnalysisCard({ analysis }) {
  return (
    <div style={{
      background: '#fff', borderRadius: 10, border: '1px solid #e2e8f0',
      padding: '1rem 1.25rem', marginBottom: '0.75rem',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: '0.5rem' }}>
        <div style={{
          width: 28, height: 28, borderRadius: '50%', display: 'flex',
          alignItems: 'center', justifyContent: 'center',
          background: '#dbeafe', color: '#1d4ed8', fontSize: '0.7rem', fontWeight: 700,
        }}>
          {analysis.agent?.charAt(0) || 'A'}
        </div>
        <div>
          <div style={{ fontWeight: 600, fontSize: '0.85rem', color: '#1e293b' }}>{analysis.agent}</div>
          <div style={{ fontSize: '0.75rem', color: '#64748b' }}>{analysis.title}</div>
        </div>
      </div>
      <p style={{ fontSize: '0.85rem', color: '#475569', margin: '0.5rem 0', lineHeight: 1.5 }}>
        {analysis.summary}
      </p>
      {analysis.metrics && Object.keys(analysis.metrics).length > 0 && (
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', marginTop: '0.5rem' }}>
          {Object.entries(analysis.metrics).map(([key, val]) => (
            <div key={key} style={{
              padding: '0.25rem 0.5rem', background: '#f1f5f9', borderRadius: 6,
              fontSize: '0.75rem', color: '#334155',
            }}>
              <strong>{key.replace(/_/g, ' ')}:</strong>{' '}
              {typeof val === 'number' ? (val > 100 ? `$${val.toLocaleString()}` : val.toLocaleString()) : String(val)}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function ScenarioAnalysis({ embedded = false, initialAssetId = '' }) {
  // Fleet data
  const [assets, setAssets] = useState([])
  const [assetsLoading, setAssetsLoading] = useState(true)

  // Selection state
  const [selectedLocation, setSelectedLocation] = useState('all')
  const [assetId, setAssetId] = useState(initialAssetId)
  const [scenarioType, setScenarioType] = useState('defer_maintenance')

  // Scenario-specific params
  const [deferDays, setDeferDays] = useState(30)
  const [targetReductionPct, setTargetReductionPct] = useState(15)
  const [currentIntervalDays, setCurrentIntervalDays] = useState(90)
  const [budgetAmount, setBudgetAmount] = useState(100000)
  const [forecastMonths, setForecastMonths] = useState(12)
  const [timeHorizonDays, setTimeHorizonDays] = useState(180)

  // Results
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [history, setHistory] = useState([])

  // Fetch fleet assets on mount
  useEffect(() => {
    async function loadAssets() {
      try {
        const res = await FleetApi.getAssets()
        if (res.ok && res.data?.assets) {
          setAssets(res.data.assets)
        }
      } catch {
        // Fleet API unavailable — fall back to empty
      } finally {
        setAssetsLoading(false)
      }
    }
    loadAssets()
  }, [])

  // Build location hierarchy: { locationKey: { estate, location, assets[] } }
  const locationHierarchy = useMemo(() => {
    const map = {}
    assets.forEach(a => {
      const estate = a.estate || 'Unassigned'
      const loc = a.location || 'Unknown'
      const key = `${estate}|||${loc}`
      if (!map[key]) map[key] = { estate, location: loc, assets: [] }
      map[key].assets.push(a)
    })
    // Sort by estate then location
    return Object.values(map).sort((a, b) =>
      a.estate.localeCompare(b.estate) || a.location.localeCompare(b.location)
    )
  }, [assets])

  // Unique estates for grouping
  const estates = useMemo(() =>
    [...new Set(locationHierarchy.map(l => l.estate))].sort(),
  [locationHierarchy])

  // Filtered assets based on selected location
  const filteredAssets = useMemo(() => {
    if (selectedLocation === 'all') return assets
    const [estate, loc] = selectedLocation.split('|||')
    return assets.filter(a =>
      (a.estate || 'Unassigned') === estate && (a.location || 'Unknown') === loc
    )
  }, [assets, selectedLocation])

  // When location filter changes, reset asset if it's no longer in the filtered list
  useEffect(() => {
    if (assetId && filteredAssets.length > 0 && !filteredAssets.find(a => a.asset_id === assetId)) {
      setAssetId(filteredAssets[0].asset_id)
    }
  }, [filteredAssets]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleAnalyze = useCallback(async () => {
    if (!assetId) return
    setLoading(true)
    setError('')
    setResult(null)

    try {
      const body = {
        asset_id: assetId,
        scenario_type: scenarioType,
      }
      // Attach scenario-specific params
      if (scenarioType === 'defer_maintenance') body.defer_days = deferDays
      if (scenarioType === 'energy_optimization') body.target_reduction_pct = targetReductionPct
      if (scenarioType === 'preventive_schedule') body.current_interval_days = currentIntervalDays
      if (scenarioType === 'budget_allocation') body.budget_amount = budgetAmount
      if (scenarioType === 'efficiency_degradation') body.forecast_months = forecastMonths
      if (scenarioType === 'risk_assessment') body.time_horizon_days = timeHorizonDays

      const json = await request('/api/v1/scenarios/maintenance/analyze', {
        method: 'POST',
        body: JSON.stringify(body),
      })
      setResult(json)
      setHistory(prev => [json, ...prev].slice(0, 10))
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [assetId, scenarioType, deferDays, targetReductionPct, currentIntervalDays, budgetAmount, forecastMonths, timeHorizonDays])

  const selectedType = SCENARIO_TYPES.find(t => t.id === scenarioType) || SCENARIO_TYPES[0]

  return (
    <div style={embedded ? { padding: '0.5rem 0' } : { maxWidth: 960, margin: '2rem auto', padding: '1.5rem', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' }}>
      {!embedded && (
        <>
          <h2 style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '0 0 0.75rem', color: '#1e293b' }}>
            <GitBranch size={24} /> Maintenance Scenario Analysis
          </h2>
          <div style={{
            background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: 10,
            padding: '10px 14px', fontSize: '0.8rem', color: '#0c4a6e',
            marginBottom: '1.25rem', lineHeight: 1.6,
          }}>
            <strong>What this page does:</strong> Run <strong>what-if maintenance scenarios</strong> on
            individual assets or locations — defer maintenance, reduce energy consumption, optimize
            schedules, constrain budgets, or forecast failures. Compare outcomes to the baseline
            and see projected cost, risk, and operational impact before committing to a strategy.
          </div>
        </>
      )}

      {/* Scenario Type Selector */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(155px, 1fr))', gap: '0.6rem', marginBottom: '1.5rem' }}>
        {SCENARIO_TYPES.map(st => {
          const Icon = st.icon
          const active = scenarioType === st.id
          return (
            <button
              key={st.id}
              onClick={() => setScenarioType(st.id)}
              style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6,
                padding: '0.75rem 0.5rem', borderRadius: 10,
                border: active ? `2px solid ${st.color}` : '1px solid #e2e8f0',
                background: active ? `${st.color}10` : '#fff', cursor: 'pointer',
                transition: 'all 0.15s', fontFamily: 'inherit',
              }}
            >
              <Icon size={20} style={{ color: st.color }} />
              <span style={{ fontWeight: 600, fontSize: '0.75rem', color: '#1e293b', textAlign: 'center', lineHeight: 1.25 }}>{st.label}</span>
              <span style={{ fontSize: '0.62rem', color: '#64748b', textAlign: 'center', lineHeight: 1.3 }}>{st.description}</span>
            </button>
          )
        })}
      </div>

      {/* Input Form */}
      <div style={{
        background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0',
        padding: '1.25rem', marginBottom: '1.5rem',
      }}>
        {/* Location & Asset Selectors */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
          {/* Two-tiered Location dropdown */}
          <div>
            <label style={labelStyle}>
              <MapPin size={12} style={{ verticalAlign: -1, marginRight: 3 }} />
              Location
            </label>
            <select
              value={selectedLocation}
              onChange={(e) => { setSelectedLocation(e.target.value); setAssetId('') }}
              style={inputStyle}
            >
              <option value="all">All Locations ({assets.length} assets)</option>
              {estates.map(estate => {
                const estateLocs = locationHierarchy.filter(l => l.estate === estate)
                return (
                  <optgroup key={estate} label={estate}>
                    {estateLocs.map(loc => (
                      <option key={`${loc.estate}|||${loc.location}`} value={`${loc.estate}|||${loc.location}`}>
                        {loc.location} ({loc.assets.length} assets)
                      </option>
                    ))}
                  </optgroup>
                )
              })}
            </select>
          </div>

          {/* Asset ID dropdown */}
          <div>
            <label style={labelStyle}>
              <Thermometer size={12} style={{ verticalAlign: -1, marginRight: 3 }} />
              Asset
            </label>
            {assetsLoading ? (
              <div style={{ ...inputStyle, color: '#94a3b8', display: 'flex', alignItems: 'center', gap: 6 }}>
                <Loader2 size={14} className="spin" /> Loading assets…
              </div>
            ) : filteredAssets.length > 0 ? (
              <select
                value={assetId}
                onChange={(e) => setAssetId(e.target.value)}
                style={inputStyle}
              >
                <option value="">Select an asset…</option>
                {filteredAssets.map(a => (
                  <option key={a.asset_id} value={a.asset_id}>
                    {a.asset_id}{a.health_score != null ? ` (Health: ${Math.round(a.health_score)})` : ''}
                  </option>
                ))}
              </select>
            ) : (
              <input
                type="text"
                value={assetId}
                onChange={(e) => setAssetId(e.target.value)}
                placeholder="e.g. RTU-001"
                style={inputStyle}
              />
            )}
          </div>
        </div>

        {/* Scenario-specific parameters */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>
          {scenarioType === 'defer_maintenance' && (
            <div>
              <label style={labelStyle}>Defer Days</label>
              <input
                type="number" value={deferDays}
                onChange={(e) => setDeferDays(parseInt(e.target.value) || 30)}
                min={1} max={365} style={inputStyle}
              />
            </div>
          )}
          {scenarioType === 'energy_optimization' && (
            <div>
              <label style={labelStyle}>Target Reduction (%)</label>
              <input
                type="number" value={targetReductionPct}
                onChange={(e) => setTargetReductionPct(parseInt(e.target.value) || 10)}
                min={1} max={50} style={inputStyle}
              />
            </div>
          )}
          {scenarioType === 'preventive_schedule' && (
            <div>
              <label style={labelStyle}>Current PM Interval (days)</label>
              <input
                type="number" value={currentIntervalDays}
                onChange={(e) => setCurrentIntervalDays(parseInt(e.target.value) || 90)}
                min={7} max={365} style={inputStyle}
              />
            </div>
          )}
          {scenarioType === 'budget_allocation' && (
            <div>
              <label style={labelStyle}>Budget ($)</label>
              <input
                type="number" value={budgetAmount}
                onChange={(e) => setBudgetAmount(parseInt(e.target.value) || 50000)}
                min={1000} step={5000} style={inputStyle}
              />
            </div>
          )}
          {scenarioType === 'efficiency_degradation' && (
            <div>
              <label style={labelStyle}>Forecast Horizon (months)</label>
              <input
                type="number" value={forecastMonths}
                onChange={(e) => setForecastMonths(parseInt(e.target.value) || 6)}
                min={1} max={60} style={inputStyle}
              />
            </div>
          )}
          {scenarioType === 'risk_assessment' && (
            <div>
              <label style={labelStyle}>Time Horizon (days)</label>
              <input
                type="number" value={timeHorizonDays}
                onChange={(e) => setTimeHorizonDays(parseInt(e.target.value) || 90)}
                min={7} max={730} style={inputStyle}
              />
            </div>
          )}
        </div>

        <button
          onClick={handleAnalyze}
          disabled={!assetId || loading}
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            width: '100%', padding: '0.6rem', borderRadius: 8, border: 'none',
            background: !assetId ? '#e2e8f0' : selectedType.color,
            color: !assetId ? '#94a3b8' : '#fff',
            fontSize: '0.9rem', fontWeight: 600, cursor: assetId ? 'pointer' : 'default',
            fontFamily: 'inherit',
          }}
        >
          {loading ? <><Loader2 size={16} className="spin" /> Analyzing...</> : <><Send size={16} /> Run Scenario</>}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          padding: '1rem', borderRadius: 10, background: '#fef2f2',
          border: '1px solid #fecaca', marginBottom: '1.5rem',
          fontSize: '0.85rem', color: '#991b1b',
        }}>
          {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <div style={{ marginBottom: '2rem' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            marginBottom: '1rem',
          }}>
            <h3 style={{ margin: 0, color: '#1e293b', fontSize: '1rem' }}>
              Analysis: {result.asset_id} — {result.scenario_type?.replace(/_/g, ' ')}
            </h3>
            <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>{result.scenario_id}</span>
          </div>

          {result.analyses?.map((a, i) => <AnalysisCard key={i} analysis={a} />)}

          {/* Recommendation */}
          {result.recommendation && (
            <div style={{
              padding: '1rem 1.25rem', borderRadius: 10,
              background: 'linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%)',
              color: '#fff', marginTop: '0.75rem',
            }}>
              <div style={{ fontSize: '0.75rem', opacity: 0.7, textTransform: 'uppercase', marginBottom: 4 }}>
                Recommendation
              </div>
              <div style={{ fontSize: '0.95rem', fontWeight: 600 }}>
                {result.recommendation}
              </div>
            </div>
          )}
        </div>
      )}

      {/* History */}
      {history.length > 1 && (
        <div>
          <h3 style={{ fontSize: '0.9rem', color: '#64748b', margin: '0 0 0.75rem' }}>
            Previous Analyses ({history.length - (result ? 1 : 0)})
          </h3>
          {history.slice(result ? 1 : 0).map((h, i) => (
            <div
              key={i}
              onClick={() => setResult(h)}
              style={{
                padding: '0.75rem 1rem', borderRadius: 8, border: '1px solid #e2e8f0',
                background: '#f8fafc', marginBottom: '0.5rem', cursor: 'pointer',
                fontSize: '0.8rem', color: '#475569',
              }}
            >
              <strong>{h.asset_id}</strong> — {h.scenario_type?.replace(/_/g, ' ')} — {h.scenario_id}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
