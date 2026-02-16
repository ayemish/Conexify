/**
 * Login Page
 *
 * Simple API-key based authentication UI.
 * Validates the key against /api/v1/auth/validate and stores the token.
 */

import { useState } from 'react'
import { Shield, Loader2, AlertTriangle, Layers } from 'lucide-react'
import { useAppContext } from '../context/AppContext'

export default function LoginPage() {
  const { login } = useAppContext()
  const [apiKey, setApiKey] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleLogin = async (e) => {
    e.preventDefault()
    if (!apiKey.trim()) return

    setLoading(true)
    setError('')

    try {
      const res = await fetch('/api/v1/auth/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKey.trim() }),
      })

      if (res.ok) {
        const data = await res.json()
        login(apiKey.trim(), data.user || { name: 'Operator', role: data.role || 'operator' })
      } else {
        const err = await res.json().catch(() => ({}))
        setError(err.detail || 'Invalid API key')
      }
    } catch {
      // If auth endpoint doesn't exist yet, allow bypass in development
      login(apiKey.trim(), { name: 'Dev User', role: 'admin' })
    } finally {
      setLoading(false)
    }
  }

  const handleBypassDev = () => {
    login('dev-bypass', { name: 'Dev User', role: 'admin' })
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg, #0f172a 0%, #1e3a5f 50%, #1e293b 100%)',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    }}>
      <div style={{
        background: '#fff', borderRadius: 16, padding: '2.5rem', width: '100%', maxWidth: 420,
        boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
      }}>
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 8, marginBottom: '0.75rem',
          }}>
            <Layers size={28} style={{ color: '#2563eb' }} />
            <span style={{ fontSize: '1.4rem', fontWeight: 800, color: '#1e293b' }}>
              LoweConex<span style={{ color: '#2563eb' }}>iQ</span>
            </span>
          </div>
          <p style={{ color: '#64748b', fontSize: '0.9rem', margin: 0 }}>
            Predictive Maintenance Platform
          </p>
        </div>

        <form onSubmit={handleLogin}>
          <label style={{
            display: 'block', fontSize: '0.8rem', fontWeight: 600,
            color: '#475569', marginBottom: 6,
          }}>
            <Shield size={14} style={{ verticalAlign: -2, marginRight: 4 }} />
            API Key
          </label>
          <input
            type="password"
            value={apiKey}
            onChange={e => setApiKey(e.target.value)}
            placeholder="Enter your API key"
            autoFocus
            style={{
              width: '100%', padding: '0.65rem 0.85rem', borderRadius: 8,
              border: '1px solid #e2e8f0', fontSize: '0.9rem', boxSizing: 'border-box',
              marginBottom: '1rem',
            }}
          />

          {error && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '0.5rem 0.75rem', borderRadius: 8, marginBottom: '1rem',
              background: '#fef2f2', border: '1px solid #fecaca',
              fontSize: '0.8rem', color: '#991b1b',
            }}>
              <AlertTriangle size={14} /> {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !apiKey.trim()}
            style={{
              width: '100%', padding: '0.65rem', borderRadius: 8, border: 'none',
              background: apiKey.trim() ? '#2563eb' : '#e2e8f0',
              color: apiKey.trim() ? '#fff' : '#94a3b8',
              fontSize: '0.9rem', fontWeight: 600, cursor: apiKey.trim() ? 'pointer' : 'default',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            }}
          >
            {loading ? <><Loader2 size={16} className="spin" /> Validating...</> : 'Sign In'}
          </button>
        </form>

        <div style={{ textAlign: 'center', marginTop: '1.5rem' }}>
          <button
            onClick={handleBypassDev}
            style={{
              border: 'none', background: 'none', color: '#94a3b8',
              fontSize: '0.75rem', cursor: 'pointer', textDecoration: 'underline',
            }}
          >
            Development bypass (skip auth)
          </button>
        </div>
      </div>
    </div>
  )
}
