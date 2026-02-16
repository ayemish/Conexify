/**
 * DecisionSupportConfig — Platform page for managing all Decision Support
 * parameters, ownership mappings, and metric catalog entries.
 *
 * Tabs:
 *   1. Parameters — view/edit/override all ParameterHierarchy definitions
 *   2. Ownership Map — view/override RACI assignments per metric
 *   3. Metric Catalog — view/add metrics with quadrant classification
 *   4. Data Load — bulk import parameters or metric inputs from JSON/CSV
 */

import { useState, useEffect, useCallback } from 'react'
import {
  Sliders, Users, BarChart3, Upload, Save, Plus, Search, Filter,
  ChevronDown, ChevronUp, ChevronRight, Edit3, Check, X, RefreshCw,
  AlertTriangle, Info, Download, FileText, Layers, Shield, Wrench,
  DollarSign, Leaf, Building2, Zap, Database, Settings, Copy
} from 'lucide-react'

const API = '/api/v1/ownership'

// ═══════════════════════════════════════════════════════════════
// Shared Styles + Constants
// ═══════════════════════════════════════════════════════════════

const QUADRANT_COLORS = {
  Q1: { bg: '#3b82f620', border: '#3b82f6', text: '#93c5fd', label: 'Q1 — FM / Opex', icon: Wrench },
  Q2: { bg: '#22c55e20', border: '#22c55e', text: '#86efac', label: 'Q2 — Finance / Capex', icon: DollarSign },
  Q3: { bg: '#ef444420', border: '#ef4444', text: '#fca5a5', label: 'Q3 — Compliance / Risk', icon: Shield },
  Q4: { bg: '#a855f720', border: '#a855f7', text: '#d8b4fe', label: 'Q4 — Strategic / ESG', icon: Leaf },
}

const CATEGORY_LABELS = {
  geography: 'Geography & Service',
  asset: 'Asset Context',
  store: 'Store / Operations',
  compliance: 'Compliance',
  energy: 'Energy & Emissions',
  financial: 'Financial',
  data_quality: 'Data Quality',
}

const CATEGORY_ICONS = {
  geography: Building2, asset: Settings, store: Building2,
  compliance: Shield, energy: Zap, financial: DollarSign, data_quality: Database,
}

const HIERARCHY_LEVELS = ['global', 'region', 'banner', 'store']

const card = {
  background: '#0f172a', border: '1px solid #1e293b',
  borderRadius: '12px', padding: '1rem',
}

const input = {
  padding: '0.45rem 0.7rem', borderRadius: '6px', fontSize: '0.8rem',
  background: '#1e293b', color: '#e2e8f0', border: '1px solid #334155',
  outline: 'none', width: '100%',
}

const btn = (variant = 'default') => ({
  display: 'flex', alignItems: 'center', gap: '0.4rem',
  padding: '0.4rem 0.85rem', borderRadius: '8px', border: 'none',
  cursor: 'pointer', fontWeight: 600, fontSize: '0.75rem',
  transition: 'all 0.2s',
  ...(variant === 'primary' ? { background: '#4f46e5', color: '#fff' } :
     variant === 'success' ? { background: '#16a34a', color: '#fff' } :
     variant === 'danger' ? { background: '#dc2626', color: '#fff' } :
     { background: '#334155', color: '#cbd5e1' }),
})


// ═══════════════════════════════════════════════════════════════
// 1. Parameters Tab
// ═══════════════════════════════════════════════════════════════

function ParametersTab() {
  const [params, setParams] = useState([])
  const [filterCat, setFilterCat] = useState('')
  const [search, setSearch] = useState('')
  const [editingId, setEditingId] = useState(null)
  const [editValue, setEditValue] = useState('')
  const [editLevel, setEditLevel] = useState('global')
  const [editEntity, setEditEntity] = useState('')
  const [editReason, setEditReason] = useState('')
  const [saving, setSaving] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [newParam, setNewParam] = useState({
    param_id: '', name: '', category: 'financial', default_value: 0,
    unit: '', min_value: 0, max_value: 100, step: 1,
  })

  const load = useCallback(() => {
    const url = filterCat ? `${API}/parameters?category=${filterCat}` : `${API}/parameters`
    fetch(url).then(r => r.json()).then(d => setParams(d.parameters || [])).catch(() => {})
  }, [filterCat])

  useEffect(() => { load() }, [load])

  const filtered = params.filter(p =>
    !search || p.name?.toLowerCase().includes(search.toLowerCase()) ||
    p.param_id?.toLowerCase().includes(search.toLowerCase())
  )

  const grouped = {}
  filtered.forEach(p => {
    const cat = p.category || 'other'
    if (!grouped[cat]) grouped[cat] = []
    grouped[cat].push(p)
  })

  const handleSave = async (paramId) => {
    setSaving(true)
    try {
      await fetch(`${API}/parameters/${paramId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          level: editLevel, entity: editEntity,
          value: parseFloat(editValue), reason: editReason,
        }),
      })
      setEditingId(null)
      load()
    } catch (e) { console.error(e) }
    setSaving(false)
  }

  const handleAddParam = async () => {
    // Parameters are seeded backend-side; this adds an override at global level
    // to effectively "register" a new default value
    if (!newParam.param_id) return
    setSaving(true)
    try {
      await fetch(`${API}/parameters/${newParam.param_id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          level: 'global', entity: '',
          value: parseFloat(newParam.default_value),
          reason: `Added via config UI: ${newParam.name}`,
        }),
      })
      setShowAdd(false)
      setNewParam({ param_id: '', name: '', category: 'financial', default_value: 0, unit: '', min_value: 0, max_value: 100, step: 1 })
      load()
    } catch (e) { console.error(e) }
    setSaving(false)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {/* Toolbar */}
      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
          <Search size={14} style={{ position: 'absolute', left: 10, top: 10, color: '#64748b' }} />
          <input
            placeholder="Search parameters..."
            value={search} onChange={e => setSearch(e.target.value)}
            style={{ ...input, paddingLeft: '2rem' }}
          />
        </div>
        <select value={filterCat} onChange={e => setFilterCat(e.target.value)}
          style={{ ...input, width: 'auto', minWidth: 150 }}>
          <option value="">All Categories</option>
          {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <button style={btn('primary')} onClick={() => setShowAdd(!showAdd)}>
          <Plus size={14} /> Add Override
        </button>
        <button style={btn()} onClick={load}><RefreshCw size={14} /> Refresh</button>
      </div>

      {/* Add Parameter Override Form */}
      {showAdd && (
        <div style={{ ...card, border: '1px solid #4f46e540' }}>
          <div style={{ fontWeight: 700, fontSize: '0.85rem', color: '#e2e8f0', marginBottom: '0.75rem' }}>
            Add Parameter Override
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '0.5rem' }}>
            <div>
              <label style={labelStyle}>Parameter ID</label>
              <select value={newParam.param_id} onChange={e => setNewParam({ ...newParam, param_id: e.target.value })} style={input}>
                <option value="">Select parameter...</option>
                {params.map(p => <option key={p.param_id} value={p.param_id}>{p.name} ({p.param_id})</option>)}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Value</label>
              <input type="number" value={newParam.default_value}
                onChange={e => setNewParam({ ...newParam, default_value: e.target.value })}
                style={input} />
            </div>
            <div>
              <label style={labelStyle}>Hierarchy Level</label>
              <select value={editLevel} onChange={e => setEditLevel(e.target.value)} style={input}>
                {HIERARCHY_LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Entity (optional)</label>
              <input value={editEntity} onChange={e => setEditEntity(e.target.value)}
                placeholder="e.g. northeast, store-42" style={input} />
            </div>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem' }}>
            <button style={btn('success')} onClick={handleAddParam} disabled={!newParam.param_id || saving}>
              <Save size={14} /> {saving ? 'Saving...' : 'Save Override'}
            </button>
            <button style={btn()} onClick={() => setShowAdd(false)}><X size={14} /> Cancel</button>
          </div>
        </div>
      )}

      {/* Parameter Groups */}
      {Object.entries(grouped).map(([cat, items]) => {
        const CatIcon = CATEGORY_ICONS[cat] || Settings
        return (
          <div key={cat} style={card}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
              <CatIcon size={16} color="#a78bfa" />
              <span style={{ fontWeight: 700, fontSize: '0.85rem', color: '#e2e8f0' }}>
                {CATEGORY_LABELS[cat] || cat}
              </span>
              <span style={{ fontSize: '0.65rem', color: '#64748b', marginLeft: 'auto' }}>
                {items.length} parameter{items.length !== 1 ? 's' : ''}
              </span>
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #1e293b' }}>
                  <th style={thStyle}>Parameter</th>
                  <th style={thStyle}>Default</th>
                  <th style={thStyle}>Unit</th>
                  <th style={thStyle}>Range</th>
                  <th style={thStyle}>Quadrants</th>
                  <th style={{ ...thStyle, width: 80 }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map(p => (
                  <tr key={p.param_id} style={{ borderBottom: '1px solid #0f172a' }}>
                    <td style={tdStyle}>
                      <div style={{ fontWeight: 600, color: '#e2e8f0' }}>{p.name}</div>
                      <div style={{ fontSize: '0.65rem', color: '#64748b', fontFamily: 'monospace' }}>{p.param_id}</div>
                    </td>
                    <td style={tdStyle}>
                      {editingId === p.param_id ? (
                        <input type="number" value={editValue}
                          onChange={e => setEditValue(e.target.value)}
                          style={{ ...input, width: 80 }}
                          step={p.step || 1}
                          min={p.min_value} max={p.max_value}
                        />
                      ) : (
                        <span style={{ fontWeight: 700, color: '#e2e8f0' }}>
                          {typeof p.default_value === 'number' ? p.default_value.toLocaleString() : p.default_value}
                        </span>
                      )}
                    </td>
                    <td style={tdStyle}><span style={{ color: '#94a3b8' }}>{p.unit}</span></td>
                    <td style={tdStyle}>
                      <span style={{ color: '#64748b', fontSize: '0.7rem' }}>
                        {p.min_value != null ? `${p.min_value} – ${p.max_value}` : '—'}
                      </span>
                    </td>
                    <td style={tdStyle}>
                      <div style={{ display: 'flex', gap: '3px', flexWrap: 'wrap' }}>
                        {(p.affects_quadrants || []).map(q => (
                          <span key={q} style={{
                            fontSize: '0.6rem', padding: '1px 5px', borderRadius: '4px',
                            background: QUADRANT_COLORS[q]?.bg || '#1e293b',
                            color: QUADRANT_COLORS[q]?.text || '#94a3b8',
                            border: `1px solid ${QUADRANT_COLORS[q]?.border || '#334155'}40`,
                          }}>{q}</span>
                        ))}
                      </div>
                    </td>
                    <td style={tdStyle}>
                      {editingId === p.param_id ? (
                        <div style={{ display: 'flex', gap: '4px' }}>
                          <button style={{ ...btn('success'), padding: '3px 6px' }}
                            onClick={() => handleSave(p.param_id)} disabled={saving}>
                            <Check size={12} />
                          </button>
                          <button style={{ ...btn(), padding: '3px 6px' }}
                            onClick={() => setEditingId(null)}>
                            <X size={12} />
                          </button>
                        </div>
                      ) : (
                        <button style={{ ...btn(), padding: '3px 8px' }}
                          onClick={() => {
                            setEditingId(p.param_id)
                            setEditValue(p.default_value)
                            setEditLevel('global')
                            setEditEntity('')
                            setEditReason('')
                          }}>
                          <Edit3 size={12} /> Edit
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      })}

      {filtered.length === 0 && (
        <div style={{ textAlign: 'center', color: '#64748b', padding: '2rem' }}>
          No parameters found.
        </div>
      )}
    </div>
  )
}


// ═══════════════════════════════════════════════════════════════
// 2. Ownership Map Tab
// ═══════════════════════════════════════════════════════════════

function OwnershipTab() {
  const [owners, setOwners] = useState([])
  const [metrics, setMetrics] = useState([])
  const [filterQuad, setFilterQuad] = useState('')
  const [editMetric, setEditMetric] = useState(null)
  const [editData, setEditData] = useState({})
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => {
    Promise.all([
      fetch(`${API}/owners`).then(r => r.json()),
      fetch(`${API}/metrics`).then(r => r.json()),
    ]).then(([ownData, metData]) => {
      setOwners(ownData.ownership_map || [])
      setMetrics(metData.metrics || [])
    }).catch(() => {})
  }, [])

  useEffect(() => { load() }, [load])

  const filtered = owners.filter(o =>
    !filterQuad || (metrics.find(m => m.metric_id === o.metric_id)?.quadrant === filterQuad)
  )

  const handleSaveOwnership = async () => {
    if (!editMetric) return
    setSaving(true)
    try {
      await fetch(`${API}/owners/${editMetric}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          org_level: editData.org_level || 'global',
          org_entity: editData.org_entity || '',
          accountable: editData.accountable || undefined,
          responsible: editData.responsible || undefined,
          consulted: editData.consulted ? editData.consulted.split(',').map(s => s.trim()) : undefined,
          informed: editData.informed ? editData.informed.split(',').map(s => s.trim()) : undefined,
        }),
      })
      setEditMetric(null)
      load()
    } catch (e) { console.error(e) }
    setSaving(false)
  }

  const roles = ['fm', 'finance', 'food_safety', 'ops', 'executive', 'esg']

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {/* Filter */}
      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
        <select value={filterQuad} onChange={e => setFilterQuad(e.target.value)}
          style={{ ...input, width: 'auto', minWidth: 180 }}>
          <option value="">All Quadrants</option>
          {Object.entries(QUADRANT_COLORS).map(([q, c]) => (
            <option key={q} value={q}>{c.label}</option>
          ))}
        </select>
        <button style={btn()} onClick={load}><RefreshCw size={14} /> Refresh</button>
        <span style={{ fontSize: '0.72rem', color: '#64748b', marginLeft: 'auto' }}>
          {filtered.length} metric{filtered.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Ownership Edit Modal */}
      {editMetric && (
        <div style={{ ...card, border: '1px solid #4f46e540' }}>
          <div style={{ fontWeight: 700, fontSize: '0.85rem', color: '#e2e8f0', marginBottom: '0.75rem' }}>
            Edit Ownership: <span style={{ color: '#a78bfa', fontFamily: 'monospace' }}>{editMetric}</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '0.5rem' }}>
            <div>
              <label style={labelStyle}>Accountable</label>
              <select value={editData.accountable || ''} onChange={e => setEditData({ ...editData, accountable: e.target.value })} style={input}>
                <option value="">—</option>
                {roles.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Responsible</label>
              <select value={editData.responsible || ''} onChange={e => setEditData({ ...editData, responsible: e.target.value })} style={input}>
                <option value="">—</option>
                {roles.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Consulted (comma-sep)</label>
              <input value={editData.consulted || ''} onChange={e => setEditData({ ...editData, consulted: e.target.value })}
                placeholder="finance, ops" style={input} />
            </div>
            <div>
              <label style={labelStyle}>Informed (comma-sep)</label>
              <input value={editData.informed || ''} onChange={e => setEditData({ ...editData, informed: e.target.value })}
                placeholder="executive, esg" style={input} />
            </div>
            <div>
              <label style={labelStyle}>Org Level</label>
              <select value={editData.org_level || 'global'} onChange={e => setEditData({ ...editData, org_level: e.target.value })} style={input}>
                {HIERARCHY_LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Org Entity</label>
              <input value={editData.org_entity || ''} onChange={e => setEditData({ ...editData, org_entity: e.target.value })}
                placeholder="e.g. northeast" style={input} />
            </div>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem' }}>
            <button style={btn('success')} onClick={handleSaveOwnership} disabled={saving}>
              <Save size={14} /> {saving ? 'Saving...' : 'Save'}
            </button>
            <button style={btn()} onClick={() => setEditMetric(null)}><X size={14} /> Cancel</button>
          </div>
        </div>
      )}

      {/* Ownership Table */}
      <div style={card}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #1e293b' }}>
              <th style={thStyle}>Metric</th>
              <th style={thStyle}>Quadrant</th>
              <th style={thStyle}>Accountable</th>
              <th style={thStyle}>Responsible</th>
              <th style={thStyle}>Consulted</th>
              <th style={thStyle}>Informed</th>
              <th style={{ ...thStyle, width: 60 }}></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(o => {
              const met = metrics.find(m => m.metric_id === o.metric_id)
              const q = met?.quadrant || ''
              const qc = QUADRANT_COLORS[q] || {}
              return (
                <tr key={o.metric_id} style={{ borderBottom: '1px solid #0f172a' }}>
                  <td style={tdStyle}>
                    <div style={{ fontWeight: 600, color: '#e2e8f0' }}>{met?.name || o.metric_id}</div>
                    <div style={{ fontSize: '0.6rem', color: '#64748b', fontFamily: 'monospace' }}>{o.metric_id}</div>
                  </td>
                  <td style={tdStyle}>
                    <span style={{
                      fontSize: '0.65rem', padding: '2px 6px', borderRadius: '4px',
                      background: qc.bg || '#1e293b', color: qc.text || '#94a3b8',
                      border: `1px solid ${qc.border || '#334155'}40`,
                    }}>{q}</span>
                  </td>
                  <td style={tdStyle}><RoleBadge role={o.accountable} /></td>
                  <td style={tdStyle}><RoleBadge role={o.responsible} /></td>
                  <td style={tdStyle}>
                    {(Array.isArray(o.consulted) ? o.consulted : [o.consulted]).filter(Boolean).map(r => (
                      <RoleBadge key={r} role={r} />
                    ))}
                  </td>
                  <td style={tdStyle}>
                    {(Array.isArray(o.informed) ? o.informed : [o.informed]).filter(Boolean).map(r => (
                      <RoleBadge key={r} role={r} />
                    ))}
                  </td>
                  <td style={tdStyle}>
                    <button style={{ ...btn(), padding: '3px 8px' }}
                      onClick={() => {
                        setEditMetric(o.metric_id)
                        setEditData({
                          accountable: o.accountable || '',
                          responsible: o.responsible || '',
                          consulted: Array.isArray(o.consulted) ? o.consulted.join(', ') : (o.consulted || ''),
                          informed: Array.isArray(o.informed) ? o.informed.join(', ') : (o.informed || ''),
                          org_level: 'global', org_entity: '',
                        })
                      }}>
                      <Edit3 size={12} />
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function RoleBadge({ role }) {
  if (!role) return null
  const colors = {
    fm: '#3b82f6', finance: '#22c55e', food_safety: '#ef4444',
    ops: '#f59e0b', executive: '#a855f7', esg: '#06b6d4',
  }
  return (
    <span style={{
      fontSize: '0.65rem', padding: '1px 6px', borderRadius: '4px',
      background: `${colors[role] || '#64748b'}20`,
      color: colors[role] || '#94a3b8',
      border: `1px solid ${colors[role] || '#64748b'}30`,
      marginRight: 3, display: 'inline-block',
    }}>{role}</span>
  )
}


// ═══════════════════════════════════════════════════════════════
// 3. Metric Catalog Tab
// ═══════════════════════════════════════════════════════════════

function MetricCatalogTab() {
  const [metrics, setMetrics] = useState([])
  const [showAdd, setShowAdd] = useState(false)
  const [search, setSearch] = useState('')
  const [newMetric, setNewMetric] = useState({
    name: '', description: '', quadrant: 'Q1',
    default_owner_role: 'fm', unit_type: 'count',
    measurement_frequency: 'monthly', source_type: 'manual',
  })
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => {
    fetch(`${API}/metrics`).then(r => r.json()).then(d => setMetrics(d.metrics || [])).catch(() => {})
  }, [])

  useEffect(() => { load() }, [load])

  const filtered = metrics.filter(m =>
    !search || m.name?.toLowerCase().includes(search.toLowerCase()) ||
    m.metric_id?.toLowerCase().includes(search.toLowerCase())
  )

  const handleAddMetric = async () => {
    if (!newMetric.name) return
    setSaving(true)
    try {
      await fetch(`${API}/metrics`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newMetric),
      })
      setShowAdd(false)
      setNewMetric({ name: '', description: '', quadrant: 'Q1', default_owner_role: 'fm', unit_type: 'count', measurement_frequency: 'monthly', source_type: 'manual' })
      load()
    } catch (e) { console.error(e) }
    setSaving(false)
  }

  const byQuadrant = {}
  filtered.forEach(m => {
    const q = m.quadrant || 'Q1'
    if (!byQuadrant[q]) byQuadrant[q] = []
    byQuadrant[q].push(m)
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
        <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
          <Search size={14} style={{ position: 'absolute', left: 10, top: 10, color: '#64748b' }} />
          <input placeholder="Search metrics..." value={search} onChange={e => setSearch(e.target.value)}
            style={{ ...input, paddingLeft: '2rem' }} />
        </div>
        <button style={btn('primary')} onClick={() => setShowAdd(!showAdd)}>
          <Plus size={14} /> Add Metric
        </button>
        <button style={btn()} onClick={load}><RefreshCw size={14} /></button>
      </div>

      {showAdd && (
        <div style={{ ...card, border: '1px solid #4f46e540' }}>
          <div style={{ fontWeight: 700, fontSize: '0.85rem', color: '#e2e8f0', marginBottom: '0.75rem' }}>
            Add New Metric
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '0.5rem' }}>
            <div>
              <label style={labelStyle}>Name *</label>
              <input value={newMetric.name} onChange={e => setNewMetric({ ...newMetric, name: e.target.value })}
                placeholder="e.g. Refrigerant Leak Rate" style={input} />
            </div>
            <div>
              <label style={labelStyle}>Description</label>
              <input value={newMetric.description} onChange={e => setNewMetric({ ...newMetric, description: e.target.value })}
                placeholder="Optional description" style={input} />
            </div>
            <div>
              <label style={labelStyle}>Quadrant</label>
              <select value={newMetric.quadrant} onChange={e => setNewMetric({ ...newMetric, quadrant: e.target.value })} style={input}>
                {Object.entries(QUADRANT_COLORS).map(([q, c]) => (
                  <option key={q} value={q}>{c.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Default Owner</label>
              <select value={newMetric.default_owner_role} onChange={e => setNewMetric({ ...newMetric, default_owner_role: e.target.value })} style={input}>
                {['fm', 'finance', 'food_safety', 'ops', 'executive', 'esg'].map(r => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Unit Type</label>
              <select value={newMetric.unit_type} onChange={e => setNewMetric({ ...newMetric, unit_type: e.target.value })} style={input}>
                {['count', 'hours', '$', 'kWh', 'incidents', 'probability', '%', 'temperature', 'weight', 'tCO2e'].map(u => (
                  <option key={u} value={u}>{u}</option>
                ))}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Frequency</label>
              <select value={newMetric.measurement_frequency} onChange={e => setNewMetric({ ...newMetric, measurement_frequency: e.target.value })} style={input}>
                {['real_time', 'daily', 'weekly', 'monthly', 'quarterly', 'annually'].map(f => (
                  <option key={f} value={f}>{f}</option>
                ))}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Source</label>
              <select value={newMetric.source_type} onChange={e => setNewMetric({ ...newMetric, source_type: e.target.value })} style={input}>
                {['cmms', 'iot', 'energy_bills', 'audits', 'erp', 'manual', 'calculated'].map(s => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem' }}>
            <button style={btn('success')} onClick={handleAddMetric} disabled={!newMetric.name || saving}>
              <Save size={14} /> {saving ? 'Saving...' : 'Create Metric'}
            </button>
            <button style={btn()} onClick={() => setShowAdd(false)}><X size={14} /> Cancel</button>
          </div>
        </div>
      )}

      {/* Metrics by Quadrant */}
      {['Q1', 'Q2', 'Q3', 'Q4'].map(q => {
        const items = byQuadrant[q] || []
        if (!items.length) return null
        const qc = QUADRANT_COLORS[q]
        const QIcon = qc.icon
        return (
          <div key={q} style={{ ...card, borderLeft: `3px solid ${qc.border}` }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
              <QIcon size={16} color={qc.text} />
              <span style={{ fontWeight: 700, fontSize: '0.85rem', color: qc.text }}>{qc.label}</span>
              <span style={{ fontSize: '0.65rem', color: '#64748b', marginLeft: 'auto' }}>{items.length} metrics</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '0.5rem' }}>
              {items.map(m => (
                <div key={m.metric_id} style={{
                  padding: '0.6rem 0.8rem', borderRadius: '8px',
                  background: '#1e293b50', border: '1px solid #334155',
                }}>
                  <div style={{ fontWeight: 600, fontSize: '0.8rem', color: '#e2e8f0' }}>{m.name}</div>
                  <div style={{ fontSize: '0.65rem', color: '#64748b', fontFamily: 'monospace', marginTop: 2 }}>{m.metric_id}</div>
                  <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.4rem', fontSize: '0.65rem', color: '#94a3b8' }}>
                    <span>Owner: <RoleBadge role={m.default_owner_role} /></span>
                    <span>Unit: {m.unit_type}</span>
                    <span>Source: {m.source_type}</span>
                  </div>
                  {m.description && (
                    <div style={{ fontSize: '0.7rem', color: '#64748b', marginTop: 4 }}>{m.description}</div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}


// ═══════════════════════════════════════════════════════════════
// 4. Data Load Tab
// ═══════════════════════════════════════════════════════════════

function DataLoadTab() {
  const [mode, setMode] = useState('parameters')
  const [jsonText, setJsonText] = useState('')
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(false)

  const sampleParamJson = JSON.stringify({
    overrides: [
      { param_id: "p_electricity_rate", level: "region", entity: "northeast", value: 0.18, reason: "Higher NE utility rates" },
      { param_id: "p_discount_rate", level: "global", entity: "", value: 0.10, reason: "Updated WACC" },
    ]
  }, null, 2)

  const sampleOwnerJson = JSON.stringify({
    overrides: [
      { metric_id: "m_reactive_jobs", accountable: "ops", responsible: "fm", org_level: "banner", org_entity: "west" },
    ]
  }, null, 2)

  const sampleMetricJson = JSON.stringify({
    metrics: [
      { name: "Custom Leak Rate", description: "Refrigerant leak rate tracking", quadrant: "Q3", default_owner_role: "food_safety", unit_type: "probability", source_type: "iot" },
    ]
  }, null, 2)

  const handleLoad = async () => {
    setLoading(true)
    setStatus(null)
    try {
      const data = JSON.parse(jsonText)
      let successes = 0
      let errors = 0

      if (mode === 'parameters') {
        for (const o of (data.overrides || [])) {
          const r = await fetch(`${API}/parameters/${o.param_id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ level: o.level || 'global', entity: o.entity || '', value: o.value, reason: o.reason || '' }),
          })
          r.ok ? successes++ : errors++
        }
      } else if (mode === 'ownership') {
        for (const o of (data.overrides || [])) {
          const r = await fetch(`${API}/owners/${o.metric_id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(o),
          })
          r.ok ? successes++ : errors++
        }
      } else if (mode === 'metrics') {
        for (const m of (data.metrics || [])) {
          const r = await fetch(`${API}/metrics`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(m),
          })
          r.ok ? successes++ : errors++
        }
      }

      setStatus({ type: errors > 0 ? 'warning' : 'success', message: `${successes} succeeded, ${errors} failed` })
    } catch (e) {
      setStatus({ type: 'error', message: `Parse error: ${e.message}` })
    }
    setLoading(false)
  }

  const handleFileUpload = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => setJsonText(ev.target.result)
    reader.readAsText(file)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      <div style={card}>
        <div style={{ fontWeight: 700, fontSize: '0.88rem', color: '#e2e8f0', marginBottom: '0.75rem' }}>
          Bulk Data Load
        </div>
        <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginBottom: '1rem', lineHeight: 1.5 }}>
          Import parameter overrides, ownership mappings, or new metrics in bulk via JSON.
          Select the data type, paste or upload JSON, then click Load.
        </div>

        {/* Mode Selector */}
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
          {[
            { id: 'parameters', label: 'Parameter Overrides', icon: Sliders },
            { id: 'ownership', label: 'Ownership Mappings', icon: Users },
            { id: 'metrics', label: 'New Metrics', icon: BarChart3 },
          ].map(m => (
            <button key={m.id} onClick={() => {
              setMode(m.id)
              setJsonText(m.id === 'parameters' ? sampleParamJson : m.id === 'ownership' ? sampleOwnerJson : sampleMetricJson)
            }} style={{
              ...btn(mode === m.id ? 'primary' : 'default'),
              flex: 1, justifyContent: 'center',
            }}>
              <m.icon size={14} /> {m.label}
            </button>
          ))}
        </div>

        {/* File Upload */}
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.75rem', alignItems: 'center' }}>
          <label style={{
            ...btn(), cursor: 'pointer', position: 'relative', overflow: 'hidden',
          }}>
            <Upload size={14} /> Upload JSON File
            <input type="file" accept=".json" onChange={handleFileUpload}
              style={{ position: 'absolute', opacity: 0, width: '100%', height: '100%', top: 0, left: 0, cursor: 'pointer' }} />
          </label>
          <button style={btn()} onClick={() => {
            setJsonText(mode === 'parameters' ? sampleParamJson : mode === 'ownership' ? sampleOwnerJson : sampleMetricJson)
          }}>
            <Copy size={14} /> Load Sample
          </button>
        </div>

        {/* JSON Editor */}
        <textarea
          value={jsonText}
          onChange={e => setJsonText(e.target.value)}
          placeholder="Paste JSON here..."
          style={{
            width: '100%', minHeight: 220, padding: '0.75rem', borderRadius: '8px',
            background: '#1e293b', color: '#e2e8f0', border: '1px solid #334155',
            fontFamily: 'monospace', fontSize: '0.75rem', resize: 'vertical', outline: 'none',
          }}
        />

        {/* Actions */}
        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem', alignItems: 'center' }}>
          <button style={btn('success')} onClick={handleLoad} disabled={!jsonText || loading}>
            <Database size={14} /> {loading ? 'Loading...' : `Load ${mode}`}
          </button>
          <button style={btn()} onClick={() => setJsonText('')}><X size={14} /> Clear</button>

          {status && (
            <div style={{
              marginLeft: 'auto', padding: '0.35rem 0.75rem', borderRadius: '6px',
              fontSize: '0.75rem', fontWeight: 600,
              background: status.type === 'success' ? '#16a34a20' : status.type === 'warning' ? '#f59e0b20' : '#dc262620',
              color: status.type === 'success' ? '#4ade80' : status.type === 'warning' ? '#fbbf24' : '#f87171',
              border: `1px solid ${status.type === 'success' ? '#16a34a' : status.type === 'warning' ? '#f59e0b' : '#dc2626'}30`,
            }}>
              {status.type === 'success' ? <Check size={12} style={{ verticalAlign: 'middle', marginRight: 4 }} /> :
               status.type === 'error' ? <AlertTriangle size={12} style={{ verticalAlign: 'middle', marginRight: 4 }} /> : null}
              {status.message}
            </div>
          )}
        </div>
      </div>

      {/* Schema Reference */}
      <div style={card}>
        <div style={{ fontWeight: 700, fontSize: '0.8rem', color: '#e2e8f0', marginBottom: '0.5rem' }}>
          JSON Schema Reference
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '0.75rem' }}>
          <SchemaCard title="Parameter Override" fields={[
            { name: 'param_id', type: 'string', desc: 'e.g. p_electricity_rate' },
            { name: 'level', type: 'string', desc: 'global | region | banner | store' },
            { name: 'entity', type: 'string', desc: 'e.g. northeast, store-42' },
            { name: 'value', type: 'number', desc: 'New parameter value' },
            { name: 'reason', type: 'string', desc: 'Justification for change' },
          ]} />
          <SchemaCard title="Ownership Override" fields={[
            { name: 'metric_id', type: 'string', desc: 'e.g. m_reactive_jobs' },
            { name: 'accountable', type: 'string', desc: 'RACI role' },
            { name: 'responsible', type: 'string', desc: 'RACI role' },
            { name: 'consulted', type: 'string[]', desc: 'Comma-separated roles' },
            { name: 'informed', type: 'string[]', desc: 'Comma-separated roles' },
            { name: 'org_level', type: 'string', desc: 'global | region | banner | store' },
          ]} />
          <SchemaCard title="New Metric" fields={[
            { name: 'name', type: 'string', desc: 'Display name (required)' },
            { name: 'quadrant', type: 'string', desc: 'Q1 | Q2 | Q3 | Q4' },
            { name: 'default_owner_role', type: 'string', desc: 'fm, finance, etc.' },
            { name: 'unit_type', type: 'string', desc: 'count, $, kWh, etc.' },
            { name: 'source_type', type: 'string', desc: 'cmms, iot, manual, etc.' },
          ]} />
        </div>
      </div>
    </div>
  )
}

function SchemaCard({ title, fields }) {
  return (
    <div style={{ padding: '0.6rem 0.8rem', borderRadius: '8px', background: '#1e293b50', border: '1px solid #334155' }}>
      <div style={{ fontWeight: 600, fontSize: '0.75rem', color: '#a78bfa', marginBottom: '0.4rem' }}>{title}</div>
      {fields.map(f => (
        <div key={f.name} style={{ display: 'flex', gap: '0.5rem', fontSize: '0.7rem', padding: '2px 0' }}>
          <code style={{ color: '#60a5fa', minWidth: 100 }}>{f.name}</code>
          <span style={{ color: '#64748b', minWidth: 50 }}>{f.type}</span>
          <span style={{ color: '#94a3b8' }}>{f.desc}</span>
        </div>
      ))}
    </div>
  )
}


// ═══════════════════════════════════════════════════════════════
// Shared style helpers
// ═══════════════════════════════════════════════════════════════

const labelStyle = { fontSize: '0.65rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'block', marginBottom: 2 }
const thStyle = { padding: '0.5rem 0.6rem', textAlign: 'left', color: '#64748b', fontWeight: 600, fontSize: '0.7rem', textTransform: 'uppercase' }
const tdStyle = { padding: '0.45rem 0.6rem', color: '#cbd5e1' }


// ═══════════════════════════════════════════════════════════════
// Main Component
// ═══════════════════════════════════════════════════════════════

const TABS = [
  { id: 'parameters', label: 'Parameters', icon: Sliders },
  { id: 'ownership', label: 'Ownership Map', icon: Users },
  { id: 'metrics', label: 'Metric Catalog', icon: BarChart3 },
  { id: 'data-load', label: 'Data Load', icon: Upload },
]

export default function DecisionSupportConfig() {
  const [activeTab, setActiveTab] = useState('parameters')

  return (
    <div style={{ padding: '1.5rem', maxWidth: 1200, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.25rem' }}>
        <div style={{
          width: 40, height: 40, borderRadius: '12px',
          background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Settings size={20} color="#fff" />
        </div>
        <div>
          <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#e2e8f0' }}>
            Decision Support Configuration
          </div>
          <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
            Parameters &middot; Ownership Mapping &middot; Metric Catalog &middot; Data Import
          </div>
        </div>
      </div>

      <div style={{
        background: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.2)',
        borderRadius: 10, padding: '10px 14px', fontSize: '0.78rem', color: '#c7d2fe',
        marginBottom: '0.75rem', lineHeight: 1.6,
      }}>
        <strong style={{ color: '#e0e7ff' }}>What this page does:</strong> Configure the inputs that
        drive the Ecosystem Optimizer — edit <strong>metric parameters</strong>, define
        <strong> ownership mappings</strong> (which role owns each metric), browse the
        <strong> metric catalog</strong>, and import data loads. Changes here flow into cost stack
        translation and ROI calculations.
      </div>

      {/* Tab Bar */}
      <div style={{
        display: 'flex', gap: '2px', background: '#1e293b',
        borderRadius: '10px', padding: '3px', border: '1px solid #334155',
        marginBottom: '1rem',
      }}>
        {TABS.map(tab => {
          const TIcon = tab.icon
          const isActive = activeTab === tab.id
          return (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)} style={{
              flex: 1, padding: '0.55rem 0.75rem',
              borderRadius: '8px', border: 'none', cursor: 'pointer',
              background: isActive ? '#4f46e5' : 'transparent',
              color: isActive ? '#fff' : '#94a3b8',
              fontWeight: isActive ? 600 : 400, fontSize: '0.78rem',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem',
              transition: 'all 0.2s',
            }}>
              <TIcon size={14} />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* Tab Content */}
      {activeTab === 'parameters' && <ParametersTab />}
      {activeTab === 'ownership' && <OwnershipTab />}
      {activeTab === 'metrics' && <MetricCatalogTab />}
      {activeTab === 'data-load' && <DataLoadTab />}
    </div>
  )
}
