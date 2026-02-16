import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  Wallet, DollarSign, MapPin, Wrench, Save, RefreshCw,
  TrendingUp, AlertTriangle, CheckCircle, ChevronDown, ChevronUp,
  BarChart3, Building2, PieChart
} from 'lucide-react'

const API_BASE = '/api/v1'

const fmt = (v) => {
  if (v == null || isNaN(v)) return '$0'
  return '$' + Math.round(v).toLocaleString()
}

const pct = (part, total) => {
  if (!total || total === 0) return '0%'
  return `${((part / total) * 100).toFixed(1)}%`
}

// ── Known asset types with labels ───────────────────────────────────
const ASSET_TYPE_OPTIONS = [
  { value: 'RTU', label: 'Rooftop Unit (RTU)' },
  { value: 'HVAC_RTU', label: 'HVAC RTU' },
  { value: 'AHU', label: 'Air Handling Unit' },
  { value: 'COMPRESSOR_RACK', label: 'Compressor Rack' },
  { value: 'CONDENSING_UNIT', label: 'Condensing Unit' },
  { value: 'WALK_IN_COOLER', label: 'Walk-in Cooler' },
  { value: 'WALK_IN_FREEZER', label: 'Walk-in Freezer' },
  { value: 'REACH_IN_CASE', label: 'Reach-in Display Case' },
  { value: 'CHILLER', label: 'Chiller' },
  { value: 'HVAC_SPLIT_SYSTEM', label: 'Split System (HVAC)' },
  { value: 'HVAC_VRF', label: 'VRF System' },
  { value: 'HEAT_PUMP', label: 'Heat Pump' },
  { value: 'DISPLAY_CASE', label: 'Display Case' },
  { value: 'COOLER_COMPRESSOR', label: 'Cooler Compressor' },
]

// ── Styles ──────────────────────────────────────────────────────────
const card = {
  background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0',
  padding: '1.25rem', marginBottom: '1rem',
}
const inputStyle = {
  width: '100%', padding: '0.5rem 0.75rem', borderRadius: 8,
  border: '1px solid #e2e8f0', fontSize: '0.9rem', outline: 'none',
  transition: 'border 0.15s',
}
const labelStyle = {
  display: 'block', fontSize: '0.78rem', fontWeight: 600,
  color: '#64748b', marginBottom: 4,
}
const btnPrimary = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '0.5rem 1.25rem', borderRadius: 8, border: 'none',
  background: '#1d4ed8', color: '#fff', cursor: 'pointer',
  fontWeight: 600, fontSize: '0.85rem',
}
const btnSecondary = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '0.4rem 0.75rem', borderRadius: 6,
  border: '1px solid #e2e8f0', background: '#fff',
  color: '#64748b', cursor: 'pointer', fontSize: '0.8rem',
}

export default function BudgetPage({ embedded = false }) {
  const [budget, setBudget] = useState({
    overall_capex: 0,
    overall_opex: 0,
    by_location: [],
    by_asset_type: [],
    notes: '',
  })
  const [locations, setLocations] = useState([])
  const [assetTypes, setAssetTypes] = useState([])
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState(null)
  const [expandedSection, setExpandedSection] = useState('overall')
  const [siteMetadata, setSiteMetadata] = useState({})

  // Load saved budget, then fetch ecosystem mapping and backfill missing locations/types
  useEffect(() => {
    async function initialize() {
      setLoading(true)

      // 1. Load saved budget first
      let savedBudget = null
      try {
        const res = await fetch(`${API_BASE}/budget/default`)
        if (res.ok) {
          const data = await res.json()
          if (data.budget) {
            savedBudget = {
              overall_capex: data.budget.overall_capex || 0,
              overall_opex: data.budget.overall_opex || 0,
              by_location: data.budget.by_location || [],
              by_asset_type: data.budget.by_asset_type || [],
              notes: data.budget.notes || '',
            }
          }
        }
      } catch (e) {
        console.warn('Failed to load budget:', e)
      }

      // 2. Fetch ecosystem mapping (locations + asset types) from TwinStore
      let sites = []
      let types = []
      try {
        const res = await fetch(`${API_BASE}/fleet/sites`)
        if (res.ok) {
          const data = await res.json()
          sites = data.sites || []
          types = (data.asset_types || []).map(t => t.asset_type)
          setLocations(sites.map(s => s.id))
          setAssetTypes(types)
          setSiteMetadata(sites.reduce((m, s) => { m[s.id] = s; return m }, {}))
        }
      } catch (e) {
        console.warn('Failed to fetch ecosystem data:', e)
      }

      // 3. Merge: start from saved budget, backfill any ecosystem entries not yet allocated
      const base = savedBudget || { overall_capex: 0, overall_opex: 0, by_location: [], by_asset_type: [], notes: '' }
      const existingLocIds = new Set(base.by_location.map(l => l.location_id))
      const newLocs = sites
        .filter(s => !existingLocIds.has(s.id))
        .map(s => ({ location_id: s.id, capex: 0, opex: 0 }))
      const existingTypeIds = new Set(base.by_asset_type.map(t => t.asset_type))
      const newTypes = types
        .filter(t => !existingTypeIds.has(t))
        .map(t => ({ asset_type: t, capex: 0, opex: 0 }))

      setBudget({
        ...base,
        by_location: [...base.by_location, ...newLocs],
        by_asset_type: [...base.by_asset_type, ...newTypes],
      })

      setLoading(false)
    }
    initialize()
  }, [])

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/budget/default`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ site_id: 'default', ...budget }),
      })
      if (!res.ok) throw new Error(`Save failed: ${res.statusText}`)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  // Computed totals
  const locCapexTotal = budget.by_location.reduce((s, l) => s + (l.capex || 0), 0)
  const locOpexTotal = budget.by_location.reduce((s, l) => s + (l.opex || 0), 0)
  const typeCapexTotal = budget.by_asset_type.reduce((s, t) => s + (t.capex || 0), 0)
  const typeOpexTotal = budget.by_asset_type.reduce((s, t) => s + (t.opex || 0), 0)
  const totalBudget = budget.overall_capex + budget.overall_opex
  const allocatedCapex = Math.max(locCapexTotal, typeCapexTotal)
  const allocatedOpex = Math.max(locOpexTotal, typeOpexTotal)
  const unallocatedCapex = budget.overall_capex - allocatedCapex
  const unallocatedOpex = budget.overall_opex - allocatedOpex

  // Location helpers
  const addLocation = () => {
    const available = locations.filter(l => !budget.by_location.find(bl => bl.location_id === l))
    if (available.length > 0) {
      setBudget(prev => ({
        ...prev,
        by_location: [...prev.by_location, { location_id: available[0], capex: 0, opex: 0 }],
      }))
    }
  }
  const removeLocation = (idx) => {
    setBudget(prev => ({
      ...prev,
      by_location: prev.by_location.filter((_, i) => i !== idx),
    }))
  }
  const updateLocation = (idx, field, value) => {
    setBudget(prev => ({
      ...prev,
      by_location: prev.by_location.map((l, i) =>
        i === idx ? { ...l, [field]: field === 'location_id' ? value : Number(value) || 0 } : l
      ),
    }))
  }

  // Asset type helpers
  const addAssetType = () => {
    const used = budget.by_asset_type.map(t => t.asset_type)
    const available = ASSET_TYPE_OPTIONS.filter(o => !used.includes(o.value))
    if (available.length > 0) {
      setBudget(prev => ({
        ...prev,
        by_asset_type: [...prev.by_asset_type, { asset_type: available[0].value, capex: 0, opex: 0 }],
      }))
    }
  }
  const removeAssetType = (idx) => {
    setBudget(prev => ({
      ...prev,
      by_asset_type: prev.by_asset_type.filter((_, i) => i !== idx),
    }))
  }
  const updateAssetType = (idx, field, value) => {
    setBudget(prev => ({
      ...prev,
      by_asset_type: prev.by_asset_type.map((t, i) =>
        i === idx ? { ...t, [field]: field === 'asset_type' ? value : Number(value) || 0 } : t
      ),
    }))
  }

  const formatLocId = (id) => {
    const meta = siteMetadata[id]
    if (meta) {
      const label = meta.address || meta.name || id
      const extra = [meta.store_format, meta.sqft ? `${meta.sqft.toLocaleString()} sqft` : ''].filter(Boolean).join(' · ')
      return extra ? `${label} (${extra})` : label
    }
    return id ? id.replace(/^test site\s*/i, 'Location ') : id
  }

  const SectionHeader = ({ title, icon: Icon, section, subtitle }) => (
    <div
      onClick={() => setExpandedSection(expandedSection === section ? null : section)}
      style={{
        display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer',
        padding: '0.75rem 0', userSelect: 'none',
      }}
    >
      <Icon size={18} style={{ color: '#3b82f6' }} />
      <span style={{ fontWeight: 700, color: '#1e293b', fontSize: '1rem', flex: 1 }}>{title}</span>
      {subtitle && <span style={{ fontSize: '0.78rem', color: '#94a3b8', marginRight: 8 }}>{subtitle}</span>}
      {expandedSection === section ? <ChevronUp size={16} style={{ color: '#94a3b8' }} /> : <ChevronDown size={16} style={{ color: '#94a3b8' }} />}
    </div>
  )

  if (loading) return (
    <div style={{ padding: '3rem', textAlign: 'center', color: '#94a3b8' }}>
      <RefreshCw size={24} style={{ animation: 'spin 1s linear infinite', margin: '0 auto 1rem' }} />
      <p>Loading budget data...</p>
    </div>
  )

  return (
    <div style={embedded ? {} : { maxWidth: 1200, margin: '0 auto', padding: '1.5rem', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' }}>
      {/* Page Header — hidden when embedded */}
      {!embedded && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
            <div>
              <h1 style={{ margin: 0, fontSize: '1.5rem', color: '#1e293b', display: 'flex', alignItems: 'center', gap: 10 }}>
                <Wallet size={28} style={{ color: '#3b82f6' }} /> Financial Management
              </h1>
              <p style={{ margin: '0.25rem 0 0', color: '#64748b', fontSize: '0.85rem' }}>
                Define CapEx and OpEx budgets by location and asset type. These figures feed into ROI analysis.
              </p>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {saved && (
                <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#16a34a', fontSize: '0.82rem', fontWeight: 600 }}>
                  <CheckCircle size={16} /> Saved
                </span>
              )}
              {error && (
                <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#ef4444', fontSize: '0.82rem' }}>
                  <AlertTriangle size={16} /> {error}
                </span>
              )}
              <button style={btnPrimary} onClick={handleSave} disabled={saving}>
                {saving ? <RefreshCw size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <Save size={14} />}
                {saving ? 'Saving...' : 'Save Budget'}
              </button>
            </div>
          </div>

          <div style={{
            background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: 10,
            padding: '10px 14px', fontSize: '0.8rem', color: '#0c4a6e',
            marginBottom: '1rem', lineHeight: 1.6,
          }}>
            <strong>What this page does:</strong> Set <strong>overall CapEx and OpEx budgets</strong>, then
            allocate them by location and asset type. Budget figures are referenced by the Decision Matrix,
            CapEx Generator, and Business Case Builder to constrain recommendations and track utilization.
          </div>

          <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 10, padding: '10px 14px', marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <TrendingUp size={18} style={{ color: '#1d4ed8' }} />
              <span style={{ fontWeight: 700, color: '#1e3a5f', fontSize: '0.9rem' }}>ROI Integration</span>
            </div>
            <p style={{ margin: 0, fontSize: '0.82rem', color: '#1e40af', lineHeight: 1.5 }}>
              Budget figures entered here are used in the <strong>Estate Intelligence → ROI</strong> analysis.
              The overall CapEx budget serves as the <em>implementation cost</em> for payback period, NPV, and
              IRR calculations. Location and asset-type breakdowns enable per-site and per-category ROI comparisons.
              Changes take effect on the next dashboard refresh.
            </p>
          </div>
        </>
      )}

      {/* Save bar when embedded */}
      {embedded && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 8, marginBottom: '1rem' }}>
          {saved && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#16a34a', fontSize: '0.82rem', fontWeight: 600 }}>
              <CheckCircle size={16} /> Saved
            </span>
          )}
          {error && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#ef4444', fontSize: '0.82rem' }}>
              <AlertTriangle size={16} /> {error}
            </span>
          )}
          <button style={btnPrimary} onClick={handleSave} disabled={saving}>
            {saving ? <RefreshCw size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <Save size={14} />}
            {saving ? 'Saving...' : 'Save Budget'}
          </button>
        </div>
      )}

      {/* Summary Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem', marginBottom: '1.25rem' }}>
        {[
          { icon: DollarSign, label: 'Total Budget', value: fmt(totalBudget), color: '#3b82f6', sub: `CapEx ${fmt(budget.overall_capex)} + OpEx ${fmt(budget.overall_opex)}` },
          { icon: Building2, label: 'By Location', value: `${budget.by_location.length} allocated`, color: '#8b5cf6', sub: `${fmt(locCapexTotal)} CapEx · ${fmt(locOpexTotal)} OpEx` },
          { icon: Wrench, label: 'By Asset Type', value: `${budget.by_asset_type.length} allocated`, color: '#f59e0b', sub: `${fmt(typeCapexTotal)} CapEx · ${fmt(typeOpexTotal)} OpEx` },
          {
            icon: PieChart, label: 'Unallocated', color: unallocatedCapex < 0 || unallocatedOpex < 0 ? '#ef4444' : '#22c55e',
            value: fmt(Math.max(0, unallocatedCapex) + Math.max(0, unallocatedOpex)),
            sub: unallocatedCapex < 0 || unallocatedOpex < 0 ? 'Over-allocated!' : 'Remaining to assign'
          },
        ].map((c, i) => {
          const Icon = c.icon
          return (
            <div key={i} style={card}>
              <Icon size={18} style={{ color: c.color, marginBottom: 8 }} />
              <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#1e293b' }}>{c.value}</div>
              <div style={{ fontSize: '0.8rem', color: '#64748b' }}>{c.label}</div>
              <div style={{ fontSize: '0.7rem', color: '#94a3b8', marginTop: 2 }}>{c.sub}</div>
            </div>
          )
        })}
      </div>

      {/* ── Overall Budget ────────────────────────────────────────── */}
      <div style={card}>
        <SectionHeader title="Overall Budget" icon={DollarSign} section="overall" subtitle={fmt(totalBudget)} />
        {expandedSection === 'overall' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', padding: '0.75rem 0' }}>
            <div>
              <label style={labelStyle}>Total CapEx Budget</label>
              <div style={{ position: 'relative' }}>
                <span style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#94a3b8', fontSize: '0.9rem' }}>$</span>
                <input
                  type="number" value={budget.overall_capex || ''} min={0} step={10000}
                  onChange={e => setBudget(prev => ({ ...prev, overall_capex: Number(e.target.value) || 0 }))}
                  style={{ ...inputStyle, paddingLeft: '1.5rem' }}
                  placeholder="e.g. 500000"
                />
              </div>
              <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginTop: 4 }}>
                Capital expenditure for asset replacements, upgrades, and new equipment
              </div>
            </div>
            <div>
              <label style={labelStyle}>Total OpEx Budget</label>
              <div style={{ position: 'relative' }}>
                <span style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#94a3b8', fontSize: '0.9rem' }}>$</span>
                <input
                  type="number" value={budget.overall_opex || ''} min={0} step={10000}
                  onChange={e => setBudget(prev => ({ ...prev, overall_opex: Number(e.target.value) || 0 }))}
                  style={{ ...inputStyle, paddingLeft: '1.5rem' }}
                  placeholder="e.g. 200000"
                />
              </div>
              <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginTop: 4 }}>
                Operating expenditure for maintenance, repairs, energy, and labor
              </div>
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={labelStyle}>Notes</label>
              <textarea
                value={budget.notes}
                onChange={e => setBudget(prev => ({ ...prev, notes: e.target.value }))}
                style={{ ...inputStyle, minHeight: 60, resize: 'vertical', fontFamily: 'inherit' }}
                placeholder="Budget assumptions, fiscal year, approval references..."
              />
            </div>
          </div>
        )}
      </div>

      {/* ── CapEx / OpEx by Location ──────────────────────────────── */}
      <div style={card}>
        <SectionHeader
          title="Budget by Location"
          icon={MapPin}
          section="location"
          subtitle={`${budget.by_location.length} locations · ${fmt(locCapexTotal + locOpexTotal)}`}
        />
        {expandedSection === 'location' && (
          <div style={{ padding: '0.5rem 0' }}>
            {budget.by_location.length > 0 && (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem', marginBottom: '0.75rem' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid #e2e8f0' }}>
                    <th style={{ textAlign: 'left', padding: '0.5rem', color: '#64748b', fontWeight: 600 }}>Location</th>
                    <th style={{ textAlign: 'right', padding: '0.5rem', color: '#64748b', fontWeight: 600, width: 160 }}>CapEx</th>
                    <th style={{ textAlign: 'right', padding: '0.5rem', color: '#64748b', fontWeight: 600, width: 160 }}>OpEx</th>
                    <th style={{ textAlign: 'right', padding: '0.5rem', color: '#64748b', fontWeight: 600, width: 100 }}>% of Total</th>
                    <th style={{ width: 40 }}></th>
                  </tr>
                </thead>
                <tbody>
                  {budget.by_location.map((loc, i) => {
                    const meta = siteMetadata[loc.location_id]
                    return (
                      <tr key={loc.location_id || i} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: '0.5rem' }}>
                          <div style={{ fontWeight: 600, color: '#1e293b', fontSize: '0.85rem' }}>
                            {formatLocId(loc.location_id)}
                          </div>
                          {meta && (
                            <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginTop: 2 }}>
                              {[meta.climate_zone && `Zone ${meta.climate_zone}`, meta.asset_count && `${meta.asset_count} assets`].filter(Boolean).join(' · ')}
                            </div>
                          )}
                        </td>
                        <td style={{ padding: '0.5rem' }}>
                          <input
                            type="number" value={loc.capex || ''} min={0} step={5000}
                            onChange={e => updateLocation(i, 'capex', e.target.value)}
                            style={{ ...inputStyle, textAlign: 'right', width: 140 }}
                          />
                        </td>
                        <td style={{ padding: '0.5rem' }}>
                          <input
                            type="number" value={loc.opex || ''} min={0} step={5000}
                            onChange={e => updateLocation(i, 'opex', e.target.value)}
                            style={{ ...inputStyle, textAlign: 'right', width: 140 }}
                          />
                        </td>
                        <td style={{ padding: '0.5rem', textAlign: 'right', fontSize: '0.8rem', color: '#64748b' }}>
                          {pct((loc.capex || 0) + (loc.opex || 0), totalBudget)}
                        </td>
                        <td></td>
                      </tr>
                    )
                  })}
                  <tr style={{ background: '#f8fafc', fontWeight: 700 }}>
                    <td style={{ padding: '0.5rem', color: '#1e293b' }}>Total</td>
                    <td style={{ padding: '0.5rem', textAlign: 'right', color: '#1e293b' }}>{fmt(locCapexTotal)}</td>
                    <td style={{ padding: '0.5rem', textAlign: 'right', color: '#1e293b' }}>{fmt(locOpexTotal)}</td>
                    <td style={{ padding: '0.5rem', textAlign: 'right', color: '#64748b' }}>
                      {pct(locCapexTotal + locOpexTotal, totalBudget)}
                    </td>
                    <td></td>
                  </tr>
                </tbody>
              </table>
            )}
            {budget.by_location.length === 0 && (
              <p style={{ color: '#94a3b8', fontSize: '0.85rem', textAlign: 'center', padding: '1rem 0' }}>
                No locations found in the ecosystem. Configure locations in the Digital Twin store.
              </p>
            )}
            {unallocatedCapex < 0 && (
              <div style={{ marginTop: '0.5rem', padding: '0.5rem 0.75rem', background: '#fef2f2', borderRadius: 6, fontSize: '0.78rem', color: '#991b1b', display: 'flex', alignItems: 'center', gap: 6 }}>
                <AlertTriangle size={14} /> Location CapEx allocations ({fmt(locCapexTotal)}) exceed overall CapEx budget ({fmt(budget.overall_capex)}) by {fmt(Math.abs(unallocatedCapex))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── CapEx / OpEx by Asset Type ────────────────────────────── */}
      <div style={card}>
        <SectionHeader
          title="Budget by Asset Type"
          icon={Wrench}
          section="assetType"
          subtitle={`${budget.by_asset_type.length} types · ${fmt(typeCapexTotal + typeOpexTotal)}`}
        />
        {expandedSection === 'assetType' && (
          <div style={{ padding: '0.5rem 0' }}>
            {budget.by_asset_type.length > 0 && (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem', marginBottom: '0.75rem' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid #e2e8f0' }}>
                    <th style={{ textAlign: 'left', padding: '0.5rem', color: '#64748b', fontWeight: 600 }}>Asset Type</th>
                    <th style={{ textAlign: 'right', padding: '0.5rem', color: '#64748b', fontWeight: 600, width: 160 }}>CapEx</th>
                    <th style={{ textAlign: 'right', padding: '0.5rem', color: '#64748b', fontWeight: 600, width: 160 }}>OpEx</th>
                    <th style={{ textAlign: 'right', padding: '0.5rem', color: '#64748b', fontWeight: 600, width: 100 }}>% of Total</th>
                    <th style={{ width: 40 }}></th>
                  </tr>
                </thead>
                <tbody>
                  {budget.by_asset_type.map((at, i) => {
                    const typeLabel = ASSET_TYPE_OPTIONS.find(o => o.value === at.asset_type)?.label || at.asset_type.replace(/_/g, ' ')
                    return (
                      <tr key={at.asset_type || i} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: '0.5rem' }}>
                          <div style={{ fontWeight: 600, color: '#1e293b', fontSize: '0.85rem' }}>
                            {typeLabel}
                          </div>
                        </td>
                        <td style={{ padding: '0.5rem' }}>
                          <input
                            type="number" value={at.capex || ''} min={0} step={5000}
                            onChange={e => updateAssetType(i, 'capex', e.target.value)}
                            style={{ ...inputStyle, textAlign: 'right', width: 140 }}
                          />
                        </td>
                        <td style={{ padding: '0.5rem' }}>
                          <input
                            type="number" value={at.opex || ''} min={0} step={5000}
                            onChange={e => updateAssetType(i, 'opex', e.target.value)}
                            style={{ ...inputStyle, textAlign: 'right', width: 140 }}
                          />
                        </td>
                        <td style={{ padding: '0.5rem', textAlign: 'right', fontSize: '0.8rem', color: '#64748b' }}>
                          {pct((at.capex || 0) + (at.opex || 0), totalBudget)}
                        </td>
                        <td></td>
                      </tr>
                    )
                  })}
                  <tr style={{ background: '#f8fafc', fontWeight: 700 }}>
                    <td style={{ padding: '0.5rem', color: '#1e293b' }}>Total</td>
                    <td style={{ padding: '0.5rem', textAlign: 'right', color: '#1e293b' }}>{fmt(typeCapexTotal)}</td>
                    <td style={{ padding: '0.5rem', textAlign: 'right', color: '#1e293b' }}>{fmt(typeOpexTotal)}</td>
                    <td style={{ padding: '0.5rem', textAlign: 'right', color: '#64748b' }}>
                      {pct(typeCapexTotal + typeOpexTotal, totalBudget)}
                    </td>
                    <td></td>
                  </tr>
                </tbody>
              </table>
            )}
            {budget.by_asset_type.length === 0 && (
              <p style={{ color: '#94a3b8', fontSize: '0.85rem', textAlign: 'center', padding: '1rem 0' }}>
                No asset types found in the ecosystem. Configure assets in the Digital Twin store.
              </p>
            )}
          </div>
        )}
      </div>

    </div>
  )
}
