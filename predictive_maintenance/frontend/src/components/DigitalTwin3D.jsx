import { useEffect, useRef, useState, useCallback } from 'react'
import { RefreshCw, ZoomIn, ZoomOut, RotateCcw, Thermometer, Gauge, Activity, AlertTriangle } from 'lucide-react'
import clsx from 'clsx'

const COMPONENT_COLORS = {
  healthy: '#22c55e',
  warning: '#eab308',
  alert: '#f97316',
  critical: '#ef4444',
  inactive: '#94a3b8',
}

const HVAC_COMPONENTS = [
  { id: 'compressor', name: 'Compressor', x: 150, y: 200, width: 80, height: 80, type: 'mechanical' },
  { id: 'condenser', name: 'Condenser Coil', x: 300, y: 100, width: 120, height: 60, type: 'heat_exchanger' },
  { id: 'condenser_fan', name: 'Condenser Fan', x: 360, y: 50, width: 50, height: 50, type: 'fan' },
  { id: 'expansion_valve', name: 'Expansion Valve', x: 450, y: 200, width: 40, height: 40, type: 'valve' },
  { id: 'evaporator', name: 'Evaporator Coil', x: 300, y: 300, width: 120, height: 60, type: 'heat_exchanger' },
  { id: 'evaporator_fan', name: 'Evaporator Fan', x: 360, y: 360, width: 50, height: 50, type: 'fan' },
  { id: 'filter_drier', name: 'Filter Drier', x: 520, y: 150, width: 30, height: 50, type: 'filter' },
  { id: 'sight_glass', name: 'Sight Glass', x: 480, y: 150, width: 25, height: 25, type: 'indicator' },
]

const REFRIGERANT_LINES = [
  { from: 'compressor', to: 'condenser', type: 'discharge', color: '#ef4444' },
  { from: 'condenser', to: 'filter_drier', type: 'liquid', color: '#3b82f6' },
  { from: 'filter_drier', to: 'expansion_valve', type: 'liquid', color: '#3b82f6' },
  { from: 'expansion_valve', to: 'evaporator', type: 'mixed', color: '#8b5cf6' },
  { from: 'evaporator', to: 'compressor', type: 'suction', color: '#22c55e' },
]

function getComponentCenter(component) {
  return {
    x: component.x + component.width / 2,
    y: component.y + component.height / 2,
  }
}

function getHealthStatus(healthScore) {
  if (healthScore >= 80) return 'healthy'
  if (healthScore >= 60) return 'warning'
  if (healthScore >= 40) return 'alert'
  return 'critical'
}

function ComponentShape({ component, status, selected, onClick, sensorData }) {
  const color = COMPONENT_COLORS[status] || COMPONENT_COLORS.inactive
  
  const renderShape = () => {
    switch (component.type) {
      case 'mechanical':
        return (
          <g>
            <circle
              cx={component.x + component.width / 2}
              cy={component.y + component.height / 2}
              r={component.width / 2}
              fill={`${color}20`}
              stroke={color}
              strokeWidth={selected ? 3 : 2}
              className="component-shape"
            />
            <circle
              cx={component.x + component.width / 2}
              cy={component.y + component.height / 2}
              r={component.width / 4}
              fill={color}
              className="component-inner"
            />
          </g>
        )
      
      case 'heat_exchanger':
        return (
          <g>
            <rect
              x={component.x}
              y={component.y}
              width={component.width}
              height={component.height}
              rx={5}
              fill={`${color}20`}
              stroke={color}
              strokeWidth={selected ? 3 : 2}
            />
            {[...Array(5)].map((_, i) => (
              <line
                key={i}
                x1={component.x + 10 + i * 22}
                y1={component.y + 10}
                x2={component.x + 10 + i * 22}
                y2={component.y + component.height - 10}
                stroke={color}
                strokeWidth={2}
              />
            ))}
          </g>
        )
      
      case 'fan':
        return (
          <g>
            <circle
              cx={component.x + component.width / 2}
              cy={component.y + component.height / 2}
              r={component.width / 2}
              fill={`${color}20`}
              stroke={color}
              strokeWidth={selected ? 3 : 2}
            />
            {[0, 60, 120, 180, 240, 300].map(angle => (
              <line
                key={angle}
                x1={component.x + component.width / 2}
                y1={component.y + component.height / 2}
                x2={component.x + component.width / 2 + Math.cos(angle * Math.PI / 180) * component.width / 2.5}
                y2={component.y + component.height / 2 + Math.sin(angle * Math.PI / 180) * component.height / 2.5}
                stroke={color}
                strokeWidth={2}
                className={status === 'healthy' ? 'fan-blade-animated' : ''}
              />
            ))}
          </g>
        )
      
      case 'valve':
        return (
          <g>
            <polygon
              points={`
                ${component.x},${component.y + component.height / 2}
                ${component.x + component.width / 2},${component.y}
                ${component.x + component.width},${component.y + component.height / 2}
                ${component.x + component.width / 2},${component.y + component.height}
              `}
              fill={`${color}20`}
              stroke={color}
              strokeWidth={selected ? 3 : 2}
            />
          </g>
        )
      
      default:
        return (
          <rect
            x={component.x}
            y={component.y}
            width={component.width}
            height={component.height}
            rx={3}
            fill={`${color}20`}
            stroke={color}
            strokeWidth={selected ? 3 : 2}
          />
        )
    }
  }
  
  return (
    <g onClick={() => onClick?.(component)} className="digital-twin-component" style={{ cursor: 'pointer' }}>
      {renderShape()}
      <text
        x={component.x + component.width / 2}
        y={component.y + component.height + 15}
        textAnchor="middle"
        fontSize="10"
        fill="#64748b"
      >
        {component.name}
      </text>
      {sensorData && (
        <text
          x={component.x + component.width / 2}
          y={component.y - 5}
          textAnchor="middle"
          fontSize="9"
          fill={color}
          fontWeight="600"
        >
          {sensorData}
        </text>
      )}
    </g>
  )
}

function RefrigerantLine({ line, components }) {
  const from = components.find(c => c.id === line.from)
  const to = components.find(c => c.id === line.to)
  
  if (!from || !to) return null
  
  const fromCenter = getComponentCenter(from)
  const toCenter = getComponentCenter(to)
  
  const midX = (fromCenter.x + toCenter.x) / 2
  const midY = (fromCenter.y + toCenter.y) / 2
  
  return (
    <g className="refrigerant-line">
      <path
        d={`M ${fromCenter.x} ${fromCenter.y} Q ${midX} ${midY - 30} ${toCenter.x} ${toCenter.y}`}
        fill="none"
        stroke={line.color}
        strokeWidth={3}
        strokeDasharray={line.type === 'mixed' ? '5,5' : 'none'}
        opacity={0.7}
        className="flow-line"
      />
      <circle
        r={4}
        fill={line.color}
        className="flow-particle"
      >
        <animateMotion
          dur="2s"
          repeatCount="indefinite"
          path={`M ${fromCenter.x} ${fromCenter.y} Q ${midX} ${midY - 30} ${toCenter.x} ${toCenter.y}`}
        />
      </circle>
    </g>
  )
}

function SensorPanel({ component, telemetry, onClose }) {
  if (!component) return null
  
  const getSensorReadings = () => {
    switch (component.id) {
      case 'compressor':
        return [
          { label: 'Current', value: telemetry?.compressor_current?.toFixed(1) || '—', unit: 'A', icon: Activity },
          { label: 'Suction P', value: telemetry?.suction_pressure?.toFixed(0) || '—', unit: 'psig', icon: Gauge },
          { label: 'Discharge P', value: telemetry?.discharge_pressure?.toFixed(0) || '—', unit: 'psig', icon: Gauge },
        ]
      case 'condenser':
        return [
          { label: 'Subcooling', value: telemetry?.subcooling?.toFixed(1) || '—', unit: '°F', icon: Thermometer },
          { label: 'Ambient', value: telemetry?.ambient_temp?.toFixed(1) || '—', unit: '°F', icon: Thermometer },
        ]
      case 'evaporator':
        return [
          { label: 'Superheat', value: telemetry?.superheat?.toFixed(1) || '—', unit: '°F', icon: Thermometer },
          { label: 'Supply Air', value: telemetry?.supply_air_temp?.toFixed(1) || '—', unit: '°F', icon: Thermometer },
          { label: 'Return Air', value: telemetry?.return_air_temp?.toFixed(1) || '—', unit: '°F', icon: Thermometer },
        ]
      default:
        return []
    }
  }
  
  const readings = getSensorReadings()
  
  return (
    <div className="sensor-panel">
      <div className="sensor-panel-header">
        <h4>{component.name}</h4>
        <button onClick={onClose}>&times;</button>
      </div>
      <div className="sensor-readings">
        {readings.map(reading => (
          <div key={reading.label} className="sensor-reading">
            <reading.icon size={14} />
            <span className="reading-label">{reading.label}</span>
            <span className="reading-value">{reading.value}</span>
            <span className="reading-unit">{reading.unit}</span>
          </div>
        ))}
        {readings.length === 0 && (
          <p className="no-sensors">No sensors for this component</p>
        )}
      </div>
    </div>
  )
}

export default function DigitalTwin3D({ assetId, telemetry, componentHealth, alerts }) {
  const svgRef = useRef(null)
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [selectedComponent, setSelectedComponent] = useState(null)
  const [isDragging, setIsDragging] = useState(false)
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 })
  
  const handleZoomIn = () => setZoom(z => Math.min(z + 0.2, 2))
  const handleZoomOut = () => setZoom(z => Math.max(z - 0.2, 0.5))
  const handleReset = () => {
    setZoom(1)
    setPan({ x: 0, y: 0 })
  }
  
  const handleMouseDown = (e) => {
    if (e.target === svgRef.current) {
      setIsDragging(true)
      setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y })
    }
  }
  
  const handleMouseMove = (e) => {
    if (isDragging) {
      setPan({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y })
    }
  }
  
  const handleMouseUp = () => setIsDragging(false)
  
  const getComponentStatus = (componentId) => {
    if (componentHealth?.[componentId]) {
      return getHealthStatus(componentHealth[componentId])
    }
    
    const hasAlert = alerts?.some(a => 
      a.affected_components?.includes(componentId) ||
      a.primary_fault?.toLowerCase().includes(componentId.replace('_', ' '))
    )
    
    if (hasAlert) return 'alert'
    
    return 'healthy'
  }
  
  const getSensorDisplay = (componentId) => {
    if (!telemetry) return null
    
    switch (componentId) {
      case 'compressor':
        return telemetry.compressor_current ? `${telemetry.compressor_current.toFixed(1)}A` : null
      case 'condenser':
        return telemetry.subcooling ? `SC: ${telemetry.subcooling.toFixed(0)}°F` : null
      case 'evaporator':
        return telemetry.superheat ? `SH: ${telemetry.superheat.toFixed(0)}°F` : null
      default:
        return null
    }
  }
  
  return (
    <div className="digital-twin-container">
      <div className="digital-twin-header">
        <h3>Digital Twin View</h3>
        <span className="asset-label">{assetId}</span>
        <div className="twin-controls">
          <button onClick={handleZoomOut} title="Zoom Out"><ZoomOut size={16} /></button>
          <span className="zoom-level">{Math.round(zoom * 100)}%</span>
          <button onClick={handleZoomIn} title="Zoom In"><ZoomIn size={16} /></button>
          <button onClick={handleReset} title="Reset View"><RotateCcw size={16} /></button>
        </div>
      </div>
      <div style={{
        background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: 8,
        padding: '8px 12px', fontSize: '0.75rem', color: '#0c4a6e',
        margin: '0 0 8px', lineHeight: 1.6,
      }}>
        <strong>What this page does:</strong> Interactive <strong>2D schematic</strong> of the selected HVAC/R
        asset — compressor, condenser, evaporator, and expansion valve. Component colors reflect real-time
        health status; hover for live sensor readings. Zoom, pan, and click components for detail.
      </div>
      
      <div className="digital-twin-viewport">
        <svg
          ref={svgRef}
          viewBox="0 0 600 450"
          className="digital-twin-svg"
          style={{
            transform: `scale(${zoom}) translate(${pan.x / zoom}px, ${pan.y / zoom}px)`,
          }}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
        >
          <defs>
            <filter id="glow">
              <feGaussianBlur stdDeviation="2" result="coloredBlur"/>
              <feMerge>
                <feMergeNode in="coloredBlur"/>
                <feMergeNode in="SourceGraphic"/>
              </feMerge>
            </filter>
          </defs>
          
          <rect x="0" y="0" width="600" height="450" fill="#f8fafc" rx="8" />
          
          <text x="300" y="25" textAnchor="middle" fontSize="14" fontWeight="600" fill="#1e293b">
            HVAC/R System Schematic
          </text>
          
          {REFRIGERANT_LINES.map(line => (
            <RefrigerantLine
              key={`${line.from}-${line.to}`}
              line={line}
              components={HVAC_COMPONENTS}
            />
          ))}
          
          {HVAC_COMPONENTS.map(component => (
            <ComponentShape
              key={component.id}
              component={component}
              status={getComponentStatus(component.id)}
              selected={selectedComponent?.id === component.id}
              onClick={setSelectedComponent}
              sensorData={getSensorDisplay(component.id)}
            />
          ))}
          
          <g className="legend" transform="translate(20, 400)">
            <text x="0" y="0" fontSize="10" fill="#64748b">Status:</text>
            {Object.entries(COMPONENT_COLORS).slice(0, 4).map(([status, color], i) => (
              <g key={status} transform={`translate(${50 + i * 80}, -5)`}>
                <circle r="5" fill={color} />
                <text x="10" y="4" fontSize="9" fill="#64748b">{status}</text>
              </g>
            ))}
          </g>
        </svg>
        
        {selectedComponent && (
          <SensorPanel
            component={selectedComponent}
            telemetry={telemetry}
            onClose={() => setSelectedComponent(null)}
          />
        )}
      </div>
      
      {alerts && alerts.length > 0 && (
        <div className="twin-alerts">
          <AlertTriangle size={14} />
          <span>{alerts.length} active alert(s) affecting this system</span>
        </div>
      )}
    </div>
  )
}
