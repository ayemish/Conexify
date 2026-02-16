import { useState, useEffect, useCallback } from 'react'
import {
  Settings, Plus, Trash2, Save, RefreshCw, CheckCircle2,
  AlertTriangle, ArrowRight, FileText, Loader2, Zap
} from 'lucide-react'
import { safeRequest } from '../services/apiClient'

function MappingRow({ mapping, canonicalFields, onChange, onRemove }) {
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '1fr 40px 1fr 120px 40px',
      gap: '0.5rem', alignItems: 'center', marginBottom: '0.5rem',
    }}>
      <input
        type="text"
        value={mapping.source_field}
        onChange={(e) => onChange({ ...mapping, source_field: e.target.value })}
        placeholder="Source column"
        style={{
          padding: '0.4rem 0.6rem', borderRadius: 6, border: '1px solid #e2e8f0',
          fontSize: '0.85rem', fontFamily: 'monospace',
        }}
      />
      <ArrowRight size={16} style={{ color: '#94a3b8', justifySelf: 'center' }} />
      <select
        value={mapping.target_field}
        onChange={(e) => onChange({ ...mapping, target_field: e.target.value })}
        style={{
          padding: '0.4rem 0.6rem', borderRadius: 6, border: '1px solid #e2e8f0',
          fontSize: '0.85rem', background: '#fff',
        }}
      >
        <option value="">— Select target —</option>
        {canonicalFields.map(f => (
          <option key={f.name} value={f.name}>
            {f.name} ({f.type}){f.required ? ' *' : ''}
          </option>
        ))}
      </select>
      <select
        value={mapping.transform || ''}
        onChange={(e) => onChange({ ...mapping, transform: e.target.value })}
        style={{
          padding: '0.4rem 0.6rem', borderRadius: 6, border: '1px solid #e2e8f0',
          fontSize: '0.8rem', background: '#fff',
        }}
      >
        <option value="">No transform</option>
        <option value="to_float">To Float</option>
        <option value="to_bool">To Boolean</option>
        <option value="parse_datetime">Parse DateTime</option>
        <option value="f_to_c">°F → °C</option>
        <option value="c_to_f">°C → °F</option>
        <option value="psi_to_kpa">PSI → kPa</option>
      </select>
      <button
        onClick={onRemove}
        style={{
          padding: '0.3rem', borderRadius: 6, border: 'none',
          background: '#fee2e2', color: '#ef4444', cursor: 'pointer',
        }}
      >
        <Trash2 size={14} />
      </button>
    </div>
  )
}

function SavedMappingCard({ mapping, onSelect, selected }) {
  return (
    <div
      onClick={() => onSelect(mapping)}
      style={{
        background: selected ? '#eff6ff' : '#fff',
        border: selected ? '2px solid #3b82f6' : '1px solid #e2e8f0',
        borderRadius: 10, padding: '0.75rem 1rem', cursor: 'pointer',
        marginBottom: '0.5rem', transition: 'all 0.15s',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontWeight: 600, fontSize: '0.85rem', color: '#1e293b' }}>
          {mapping.name}
        </span>
        <span style={{
          fontSize: '0.7rem', padding: '2px 6px', borderRadius: 8,
          background: '#dcfce7', color: '#166534',
        }}>
          {(mapping.field_mappings || []).length} fields
        </span>
      </div>
      <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: 2 }}>
        {mapping.source_type} · {mapping.records_processed || 0} records processed
      </div>
    </div>
  )
}

export default function DataMapping() {
  const [canonicalFields, setCanonicalFields] = useState([])
  const [savedMappings, setSavedMappings] = useState([])
  const [selectedMapping, setSelectedMapping] = useState(null)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [fieldMappings, setFieldMappings] = useState([])
  const [sourceColumns, setSourceColumns] = useState('')
  const [saving, setSaving] = useState(false)
  const [detecting, setDetecting] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)

  const fetchData = useCallback(async () => {
    try {
      const [fieldsResult, mappingsResult] = await Promise.all([
        safeRequest('/api/v1/mappings/canonical-fields'),
        safeRequest('/api/v1/mappings/'),
      ])
      if (fieldsResult.ok) {
        setCanonicalFields(fieldsResult.data.fields || [])
      }
      if (mappingsResult.ok) {
        setSavedMappings(mappingsResult.data || [])
      }
    } catch (e) {
      setError(e.message)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const handleAddRow = () => {
    setFieldMappings(prev => [...prev, { source_field: '', target_field: '', transform: '' }])
  }

  const handleChangeRow = (index, updated) => {
    setFieldMappings(prev => prev.map((m, i) => i === index ? updated : m))
  }

  const handleRemoveRow = (index) => {
    setFieldMappings(prev => prev.filter((_, i) => i !== index))
  }

  const handleAutoDetect = async () => {
    const cols = sourceColumns.split(',').map(c => c.trim()).filter(Boolean)
    if (cols.length === 0) return
    setDetecting(true)
    try {
      const { ok, data } = await safeRequest('/api/v1/mappings/auto-detect', {
        method: 'POST',
        body: JSON.stringify(cols),
      })
      if (ok && data) {
        const suggestions = (data.suggestions || []).filter(s => s.target_field)
        setFieldMappings(suggestions.map(s => ({
          source_field: s.source_field,
          target_field: s.target_field,
          transform: s.transform || '',
        })))
        setSuccess(`Auto-detected ${suggestions.length} of ${cols.length} columns`)
        setTimeout(() => setSuccess(null), 3000)
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setDetecting(false)
    }
  }

  const handleSave = async () => {
    if (!name.trim()) { setError('Name is required'); return }
    setSaving(true)
    setError(null)
    try {
      const method = selectedMapping ? 'PUT' : 'POST'
      const url = selectedMapping
        ? `/api/v1/mappings/${selectedMapping.mapping_id}`
        : '/api/v1/mappings/'
      const { ok } = await safeRequest(url, {
        method,
        body: JSON.stringify({
          site_id: 'default',
          name: name.trim(),
          description,
          source_type: 'csv',
          source_columns: sourceColumns.split(',').map(c => c.trim()).filter(Boolean),
          field_mappings: fieldMappings.filter(m => m.source_field && m.target_field),
          validation_rules: [],
        }),
      })
      if (ok) {
        setSuccess('Mapping saved successfully')
        setTimeout(() => setSuccess(null), 3000)
        fetchData()
      } else {
        setError('Save failed')
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  const handleSelectMapping = (mapping) => {
    setSelectedMapping(mapping)
    setName(mapping.name || '')
    setDescription(mapping.description || '')
    setSourceColumns((mapping.source_columns || []).join(', '))
    setFieldMappings((mapping.field_mappings || []).map(m => ({
      source_field: m.source_field || '',
      target_field: m.target_field || '',
      transform: m.transform || '',
    })))
  }

  const handleNewMapping = () => {
    setSelectedMapping(null)
    setName('')
    setDescription('')
    setSourceColumns('')
    setFieldMappings([])
  }

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '1.5rem', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' }}>
      <h2 style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '0 0 0.75rem', color: '#1e293b' }}>
        <Settings size={24} /> Data Mapping Configuration
      </h2>
      <div style={{
        background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: 10,
        padding: '10px 14px', fontSize: '0.8rem', color: '#0c4a6e',
        marginBottom: '1.25rem', lineHeight: 1.6,
      }}>
        <strong>What this page does:</strong> Define how <strong>source CSV columns map to canonical fields</strong>
        (e.g., mapping "Temp_Discharge" → "discharge_temp_f"). Create reusable mapping profiles,
        auto-detect column mappings from headers, and apply transforms so uploaded data normalizes
        correctly for the analytics pipeline.
      </div>

      {error && (
        <div style={{
          padding: '0.75rem 1rem', borderRadius: 10, background: '#fef2f2',
          border: '1px solid #fecaca', marginBottom: '1rem',
          fontSize: '0.85rem', color: '#991b1b', display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <AlertTriangle size={16} /> {error}
          <button onClick={() => setError(null)} style={{ marginLeft: 'auto', border: 'none', background: 'none', cursor: 'pointer', color: '#991b1b' }}>×</button>
        </div>
      )}
      {success && (
        <div style={{
          padding: '0.75rem 1rem', borderRadius: 10, background: '#f0fdf4',
          border: '1px solid #bbf7d0', marginBottom: '1rem',
          fontSize: '0.85rem', color: '#166534', display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <CheckCircle2 size={16} /> {success}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: '1.5rem' }}>
        {/* Saved mappings sidebar */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
            <h3 style={{ margin: 0, fontSize: '0.9rem', color: '#1e293b' }}>Saved Mappings</h3>
            <button
              onClick={handleNewMapping}
              style={{
                display: 'flex', alignItems: 'center', gap: 4,
                padding: '0.3rem 0.6rem', borderRadius: 6, border: 'none',
                background: '#2563eb', color: '#fff', fontSize: '0.75rem',
                fontWeight: 600, cursor: 'pointer',
              }}
            >
              <Plus size={12} /> New
            </button>
          </div>
          {savedMappings.length === 0 && (
            <div style={{ padding: '1.5rem', textAlign: 'center', color: '#94a3b8', fontSize: '0.8rem' }}>
              No mappings configured yet.
            </div>
          )}
          {savedMappings.map(m => (
            <SavedMappingCard
              key={m.mapping_id}
              mapping={m}
              onSelect={handleSelectMapping}
              selected={selectedMapping?.mapping_id === m.mapping_id}
            />
          ))}
        </div>

        {/* Mapping editor */}
        <div>
          <div style={{
            background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0',
            padding: '1.25rem', marginBottom: '1.5rem',
          }}>
            <h3 style={{ margin: '0 0 1rem', fontSize: '1rem', color: '#1e293b' }}>
              {selectedMapping ? `Edit: ${selectedMapping.name}` : 'New Mapping'}
            </h3>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: '#475569', marginBottom: 4 }}>Name</label>
                <input
                  type="text" value={name} onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. BMS Toshiba Format"
                  style={{
                    width: '100%', padding: '0.5rem 0.75rem', borderRadius: 8,
                    border: '1px solid #e2e8f0', fontSize: '0.85rem', boxSizing: 'border-box',
                  }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: '#475569', marginBottom: 4 }}>Description</label>
                <input
                  type="text" value={description} onChange={(e) => setDescription(e.target.value)}
                  placeholder="Optional description"
                  style={{
                    width: '100%', padding: '0.5rem 0.75rem', borderRadius: 8,
                    border: '1px solid #e2e8f0', fontSize: '0.85rem', boxSizing: 'border-box',
                  }}
                />
              </div>
            </div>

            {/* Source columns for auto-detect */}
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: '#475569', marginBottom: 4 }}>
                Source Columns (comma-separated — paste from CSV header)
              </label>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <input
                  type="text" value={sourceColumns} onChange={(e) => setSourceColumns(e.target.value)}
                  placeholder="timestamp, asset_id, suction_pressure, discharge_pressure, ..."
                  style={{
                    flex: 1, padding: '0.5rem 0.75rem', borderRadius: 8,
                    border: '1px solid #e2e8f0', fontSize: '0.85rem', fontFamily: 'monospace',
                  }}
                />
                <button
                  onClick={handleAutoDetect}
                  disabled={detecting || !sourceColumns.trim()}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 4,
                    padding: '0.5rem 1rem', borderRadius: 8, border: 'none',
                    background: sourceColumns.trim() ? '#8b5cf6' : '#e2e8f0',
                    color: sourceColumns.trim() ? '#fff' : '#94a3b8',
                    fontSize: '0.85rem', fontWeight: 600, cursor: sourceColumns.trim() ? 'pointer' : 'default',
                  }}
                >
                  {detecting ? <Loader2 size={14} className="spin" /> : <Zap size={14} />}
                  Auto-Detect
                </button>
              </div>
            </div>

            {/* Field mapping rows */}
            <div style={{ marginBottom: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <label style={{ fontSize: '0.8rem', fontWeight: 600, color: '#475569' }}>Field Mappings</label>
                <button
                  onClick={handleAddRow}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 4,
                    padding: '0.25rem 0.5rem', borderRadius: 6, border: '1px solid #e2e8f0',
                    background: '#fff', fontSize: '0.75rem', cursor: 'pointer', color: '#475569',
                  }}
                >
                  <Plus size={12} /> Add Row
                </button>
              </div>

              {/* Header */}
              <div style={{
                display: 'grid', gridTemplateColumns: '1fr 40px 1fr 120px 40px',
                gap: '0.5rem', marginBottom: '0.25rem',
              }}>
                <span style={{ fontSize: '0.7rem', color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase' }}>Source</span>
                <span />
                <span style={{ fontSize: '0.7rem', color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase' }}>Target</span>
                <span style={{ fontSize: '0.7rem', color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase' }}>Transform</span>
                <span />
              </div>

              {fieldMappings.map((m, i) => (
                <MappingRow
                  key={i}
                  mapping={m}
                  canonicalFields={canonicalFields}
                  onChange={(updated) => handleChangeRow(i, updated)}
                  onRemove={() => handleRemoveRow(i)}
                />
              ))}

              {fieldMappings.length === 0 && (
                <div style={{
                  padding: '1.5rem', textAlign: 'center', color: '#94a3b8',
                  fontSize: '0.8rem', border: '1px dashed #e2e8f0', borderRadius: 8,
                }}>
                  No field mappings yet. Paste source columns above and click Auto-Detect, or add rows manually.
                </div>
              )}
            </div>

            {/* Save button */}
            <button
              onClick={handleSave}
              disabled={saving || !name.trim()}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                width: '100%', padding: '0.6rem', borderRadius: 8, border: 'none',
                background: name.trim() ? '#2563eb' : '#e2e8f0',
                color: name.trim() ? '#fff' : '#94a3b8',
                fontSize: '0.9rem', fontWeight: 600,
                cursor: name.trim() ? 'pointer' : 'default',
              }}
            >
              {saving ? <><Loader2 size={16} className="spin" /> Saving...</> : <><Save size={16} /> Save Mapping</>}
            </button>
          </div>

          {/* Canonical field reference */}
          <div style={{
            background: '#f8fafc', borderRadius: 12, border: '1px solid #e2e8f0',
            padding: '1.25rem',
          }}>
            <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.85rem', color: '#334155' }}>
              <FileText size={14} style={{ verticalAlign: -2, marginRight: 4 }} />
              Canonical Target Fields
            </h4>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.25rem' }}>
              {canonicalFields.map(f => (
                <div key={f.name} style={{ fontSize: '0.75rem', color: '#475569', padding: '0.15rem 0' }}>
                  <code style={{ background: '#e2e8f0', padding: '1px 4px', borderRadius: 3, fontSize: '0.7rem' }}>
                    {f.name}
                  </code>
                  <span style={{ color: '#94a3b8', marginLeft: 4 }}>{f.type}</span>
                  {f.required && <span style={{ color: '#ef4444', marginLeft: 2 }}>*</span>}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
