/**
 * Site Selector
 *
 * Multi-site/tenant dropdown for switching between sites.
 * Reads available sites from AppContext.
 */

import { useState } from 'react'
import { Building, ChevronDown, Check } from 'lucide-react'
import { useAppContext } from '../context/AppContext'

export default function SiteSelector() {
  const { siteId, setSiteId, availableSites } = useAppContext()
  const [open, setOpen] = useState(false)

  const current = availableSites.find(s => s.id === siteId) || { id: siteId, name: siteId }

  if (availableSites.length <= 1) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        padding: '0.3rem 0.65rem', borderRadius: 6,
        fontSize: '0.78rem', color: '#94a3b8',
      }}>
        <Building size={14} />
        <span>{current.name}</span>
      </div>
    )
  }

  return (
    <div style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '0.3rem 0.65rem', borderRadius: 6,
          border: '1px solid #334155', background: '#1e293b',
          color: '#e2e8f0', fontSize: '0.78rem', cursor: 'pointer',
        }}
      >
        <Building size={14} style={{ color: '#60a5fa' }} />
        <span style={{ maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {current.name}
        </span>
        <ChevronDown size={12} style={{ color: '#94a3b8' }} />
      </button>

      {open && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, zIndex: 1000,
          minWidth: 220, background: '#fff', borderRadius: 10,
          boxShadow: '0 8px 30px rgba(0,0,0,0.15)', border: '1px solid #e2e8f0',
          marginTop: 4, overflow: 'hidden',
        }}>
          <div style={{
            padding: '0.5rem 0.75rem', fontSize: '0.7rem', fontWeight: 700,
            color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.04em',
            borderBottom: '1px solid #f1f5f9',
          }}>
            Switch Site
          </div>
          {availableSites.map(site => (
            <button
              key={site.id}
              onClick={() => { setSiteId(site.id); setOpen(false) }}
              style={{
                display: 'flex', alignItems: 'center', gap: 8, width: '100%',
                padding: '0.5rem 0.75rem', border: 'none', cursor: 'pointer',
                background: site.id === siteId ? '#eff6ff' : '#fff',
                textAlign: 'left', fontSize: '0.82rem',
              }}
            >
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, color: '#1e293b' }}>{site.name}</div>
                {site.address && (
                  <div style={{ fontSize: '0.7rem', color: '#94a3b8' }}>{site.address}</div>
                )}
              </div>
              {site.id === siteId && <Check size={14} style={{ color: '#2563eb' }} />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
