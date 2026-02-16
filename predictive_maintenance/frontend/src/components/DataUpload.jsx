import { useState, useCallback } from 'react'
import {
  Upload, FileText, CheckCircle, AlertTriangle, Loader2,
  Thermometer, Box, Wrench, Zap, ClipboardList, Droplets,
} from 'lucide-react'

const STATES = { idle: 'idle', uploading: 'uploading', success: 'success', error: 'error' }

const DATA_TYPES = [
  {
    id: 'telemetry',
    label: 'Telemetry',
    icon: Thermometer,
    color: '#3b82f6',
    endpoint: '/api/v1/upload/csv',
    description: 'Sensor readings from BMS/SCADA (temperature, pressure, current)',
    required: 'timestamp, asset_id, + sensor readings',
    example: 'timestamp,asset_id,suction_pressure,discharge_pressure,suction_line_temp,discharge_temp,compressor_current,superheat,subcool,compressor_on\n2024-01-15T14:30:00,RTU-001,115.2,385.6,48.3,165.2,12.5,8.2,7.9,true',
    kpis: ['Energy Reduction', 'Asset Failure Prediction', 'Asset Uptime'],
  },
  {
    id: 'assets',
    label: 'Asset Inventory',
    icon: Box,
    color: '#8b5cf6',
    endpoint: '/api/v1/upload/assets',
    description: 'Equipment master list with metadata and install dates',
    required: 'asset_id',
    example: 'asset_id,asset_type,site_id,manufacturer,model,serial_number,install_date,refrigerant_type,capacity_tons\nRTU-001,RTU,STORE-101,Carrier,50XC,SN12345,2018-06-15,R-410A,5.0',
    kpis: ['CapEx Planning', 'Location Ranking', 'All KPIs'],
  },
  {
    id: 'work_orders',
    label: 'Work Orders',
    icon: ClipboardList,
    color: '#f97316',
    endpoint: '/api/v1/upload/work-orders',
    description: 'Reactive and planned maintenance work orders from CMMS',
    required: 'wo_id, asset_id, opened_at',
    example: 'wo_id,asset_id,opened_at,wo_type,cost,labor_hours,provider,status,description\nWO-2024-001,RTU-001,2024-01-20,reactive,450,3.5,in_house,completed,Compressor short cycling',
    kpis: ['Work Order Reduction', 'PPM Maximization', 'Service Bureau Reduction'],
  },
  {
    id: 'energy',
    label: 'Energy Data',
    icon: Zap,
    color: '#eab308',
    endpoint: '/api/v1/upload/energy',
    description: 'Utility bills, submeter readings, or BMS energy consumption',
    required: 'period_start, kwh_consumed',
    example: 'period_start,period_end,site_id,kwh_consumed,cost,rate_per_kwh,demand_kw,source\n2024-01-01,2024-01-31,STORE-101,58500,7020,0.12,85,utility_bill',
    kpis: ['Energy Reduction', 'ESG Compliance'],
  },
  {
    id: 'maintenance',
    label: 'Maintenance History',
    icon: Wrench,
    color: '#22c55e',
    endpoint: '/api/v1/upload/maintenance',
    description: 'Service records including PM visits, repairs, and inspections',
    required: 'asset_id, service_date',
    example: 'asset_id,service_date,service_type,cost,labor_hours,provider,description,parts_replaced\nRTU-001,2024-02-10,pm,280,2.0,ACME HVAC,Quarterly PM,Filter + belt',
    kpis: ['PM Optimization', 'PPM Maximization'],
  },
  {
    id: 'refrigerant',
    label: 'Refrigerant Records',
    icon: Droplets,
    color: '#06b6d4',
    endpoint: '/api/v1/upload/refrigerant',
    description: 'Refrigerant charge tracking, leak detection, and EPA compliance',
    required: 'asset_id, record_date',
    example: 'asset_id,record_date,refrigerant_type,charge_lbs,lbs_added,leak_detected,leak_rate_pct,notes\nRTU-001,2024-03-01,R-410A,12.0,2.5,true,18.5,Detected at service valve',
    kpis: ['Refrigerant Leak Reduction', 'ESG Compliance', 'Food Safety'],
  },
]

function DataTypeCard({ dtype, selected, onClick }) {
  const Icon = dtype.icon
  return (
    <div
      onClick={onClick}
      style={{
        padding: '0.75rem 1rem', borderRadius: 10, cursor: 'pointer',
        border: selected ? `2px solid ${dtype.color}` : '1px solid #e2e8f0',
        background: selected ? `${dtype.color}08` : '#fff',
        transition: 'all 0.15s',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <Icon size={18} style={{ color: dtype.color }} />
        <span style={{ fontWeight: 600, fontSize: '0.9rem', color: '#1e293b' }}>{dtype.label}</span>
      </div>
      <p style={{ fontSize: '0.75rem', color: '#64748b', margin: 0, lineHeight: 1.4 }}>{dtype.description}</p>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
        {dtype.kpis.map(k => (
          <span key={k} style={{
            fontSize: '0.6rem', padding: '1px 6px', borderRadius: 4,
            background: `${dtype.color}15`, color: dtype.color, fontWeight: 500,
          }}>{k}</span>
        ))}
      </div>
    </div>
  )
}

export default function DataUpload() {
  const [state, setState] = useState(STATES.idle)
  const [file, setFile] = useState(null)
  const [siteId, setSiteId] = useState('default')
  const [result, setResult] = useState(null)
  const [dragOver, setDragOver] = useState(false)
  const [selectedType, setSelectedType] = useState('telemetry')

  const activeType = DATA_TYPES.find(d => d.id === selectedType) || DATA_TYPES[0]
  const ActiveIcon = activeType.icon

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer?.files?.[0]
    if (f && f.name.endsWith('.csv')) setFile(f)
  }, [])

  const handleFileSelect = useCallback((e) => {
    const f = e.target.files?.[0]
    if (f) setFile(f)
  }, [])

  const handleUpload = useCallback(async () => {
    if (!file) return
    setState(STATES.uploading)
    setResult(null)

    const formData = new FormData()
    formData.append('file', file)
    formData.append('site_id', siteId)

    try {
      const res = await fetch(activeType.endpoint, { method: 'POST', body: formData })
      const json = await res.json()
      if (res.ok) {
        setState(STATES.success)
        setResult(json)
      } else {
        setState(STATES.error)
        setResult({ message: json.detail || json.message || 'Upload failed' })
      }
    } catch (err) {
      setState(STATES.error)
      setResult({ message: err.message })
    }
  }, [file, siteId, activeType])

  const resetUpload = useCallback(() => {
    setState(STATES.idle)
    setFile(null)
    setResult(null)
  }, [])

  return (
    <div style={{ maxWidth: 960, margin: '2rem auto', padding: '1.5rem', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' }}>
      <h2 style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '0 0 0.5rem', color: '#1e293b' }}>
        <Upload size={24} /> Data Upload
      </h2>
      <p style={{ color: '#64748b', fontSize: '0.85rem', margin: '0 0 0.75rem' }}>
        Upload operational data to power KPI computations. Select a data type, then upload a CSV file.
      </p>
      <div style={{
        background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: 10,
        padding: '10px 14px', fontSize: '0.8rem', color: '#0c4a6e',
        marginBottom: '1.25rem', lineHeight: 1.6,
      }}>
        <strong>What this page does:</strong> Ingest <strong>CSV files</strong> containing telemetry readings,
        asset metadata, or alert history. Uploaded data is normalized, validated, and stored — it then
        feeds into KPI scorecards, health scoring, scenario analysis, and all downstream analytics.
      </div>

      {/* Data Type Selector */}
      <div style={{ marginBottom: '1.5rem' }}>
        <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: '#475569', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          1. Select Data Type
        </label>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem' }}>
          {DATA_TYPES.map(dt => (
            <DataTypeCard
              key={dt.id}
              dtype={dt}
              selected={selectedType === dt.id}
              onClick={() => { setSelectedType(dt.id); resetUpload() }}
            />
          ))}
        </div>
      </div>

      {/* Site ID + Upload */}
      <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
        <div>
          <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: '#475569', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            2. Site ID
          </label>
          <input
            type="text"
            value={siteId}
            onChange={(e) => setSiteId(e.target.value)}
            style={{
              width: '100%', padding: '0.5rem 0.75rem', borderRadius: 8,
              border: '1px solid #e2e8f0', fontSize: '0.9rem', boxSizing: 'border-box',
            }}
          />
        </div>
        <div>
          <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: '#475569', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            3. Upload CSV
          </label>
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => document.getElementById('csv-file-input')?.click()}
            style={{
              border: `2px dashed ${dragOver ? activeType.color : '#cbd5e1'}`,
              borderRadius: 10, padding: '1rem 1.5rem', textAlign: 'center',
              cursor: 'pointer', background: dragOver ? `${activeType.color}08` : '#f8fafc',
              transition: 'all 0.15s',
            }}
          >
            <input
              id="csv-file-input"
              type="file"
              accept=".csv"
              onChange={handleFileSelect}
              style={{ display: 'none' }}
            />
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
              <ActiveIcon size={20} style={{ color: activeType.color }} />
              <span style={{ fontWeight: 600, fontSize: '0.85rem', color: '#334155' }}>
                {file ? file.name : `Drop ${activeType.label} CSV here or click to browse`}
              </span>
              {file && (
                <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                  ({(file.size / 1024).toFixed(1)} KB)
                </span>
              )}
            </div>
            <p style={{ margin: '4px 0 0', fontSize: '0.7rem', color: '#94a3b8' }}>
              Required: {activeType.required}
            </p>
          </div>
        </div>
      </div>

      {/* Upload button */}
      <button
        onClick={handleUpload}
        disabled={!file || state === STATES.uploading}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
          width: '100%', padding: '0.75rem', borderRadius: 8, border: 'none',
          background: !file ? '#e2e8f0' : activeType.color, color: !file ? '#94a3b8' : '#fff',
          fontSize: '0.95rem', fontWeight: 600, cursor: file ? 'pointer' : 'default',
          transition: 'background 0.15s', marginBottom: '1rem',
        }}
      >
        {state === STATES.uploading ? (
          <><Loader2 size={18} className="spin" /> Uploading {activeType.label}...</>
        ) : (
          <><Upload size={18} /> Upload {activeType.label}</>
        )}
      </button>

      {/* Result */}
      {result && state === STATES.success && (
        <div style={{
          padding: '1.25rem', borderRadius: 12,
          background: '#f0fdf4', border: '1px solid #bbf7d0', marginBottom: '1rem',
        }}>
          <h3 style={{ display: 'flex', alignItems: 'center', gap: 6, margin: '0 0 0.75rem', color: '#166534' }}>
            <CheckCircle size={18} /> {activeType.label} Upload Successful
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem', marginBottom: '0.75rem' }}>
            <div style={{ textAlign: 'center', padding: '0.5rem', background: '#fff', borderRadius: 8 }}>
              <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#166534' }}>{result.records_processed}</div>
              <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Records Processed</div>
            </div>
            <div style={{ textAlign: 'center', padding: '0.5rem', background: '#fff', borderRadius: 8 }}>
              <div style={{ fontSize: '1.4rem', fontWeight: 700, color: result.records_failed > 0 ? '#dc2626' : '#166534' }}>{result.records_failed}</div>
              <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Records Failed</div>
            </div>
            <div style={{ textAlign: 'center', padding: '0.5rem', background: '#fff', borderRadius: 8 }}>
              <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#1d4ed8' }}>{result.asset_ids?.length || 0}</div>
              <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Assets Found</div>
            </div>
          </div>
          {result.asset_ids?.length > 0 && (
            <div style={{ fontSize: '0.8rem', color: '#475569' }}>
              <strong>Assets:</strong> {result.asset_ids.join(', ')}
            </div>
          )}
          {result.message && (
            <p style={{ fontSize: '0.8rem', color: '#475569', margin: '0.5rem 0 0' }}>{result.message}</p>
          )}
          <button onClick={resetUpload} style={{
            marginTop: '0.75rem', padding: '0.4rem 1rem', borderRadius: 6, border: '1px solid #bbf7d0',
            background: '#fff', color: '#166534', fontSize: '0.8rem', fontWeight: 600, cursor: 'pointer',
          }}>
            Upload Another File
          </button>
        </div>
      )}

      {result && state === STATES.error && (
        <div style={{
          padding: '1.25rem', borderRadius: 12,
          background: '#fef2f2', border: '1px solid #fecaca', marginBottom: '1rem',
        }}>
          <h3 style={{ display: 'flex', alignItems: 'center', gap: 6, margin: '0 0 0.5rem', color: '#991b1b' }}>
            <AlertTriangle size={18} /> Upload Failed
          </h3>
          <p style={{ fontSize: '0.85rem', color: '#991b1b', margin: 0 }}>{result.message}</p>
        </div>
      )}

      {/* Format Guide for selected type */}
      <div style={{
        padding: '1.25rem', borderRadius: 12,
        background: '#f8fafc', border: `1px solid ${activeType.color}30`,
      }}>
        <h4 style={{ margin: '0 0 0.5rem', color: '#334155', fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: 6 }}>
          <ActiveIcon size={16} style={{ color: activeType.color }} />
          {activeType.label} CSV Format
        </h4>
        <div style={{
          fontFamily: 'monospace', fontSize: '0.7rem', color: '#475569',
          background: '#f1f5f9', padding: '0.75rem', borderRadius: 6,
          overflowX: 'auto', whiteSpace: 'pre', lineHeight: 1.5,
        }}>
          {activeType.example}
        </div>
        <p style={{ fontSize: '0.72rem', color: '#94a3b8', margin: '0.5rem 0 0' }}>
          <strong>Required:</strong> {activeType.required}.
          Column names are flexibly matched (e.g., asset_id, AssetID, equipment_id all work).
        </p>
      </div>
    </div>
  )
}
