import { useEffect, useState } from 'react'
import clsx from 'clsx'
import { Brain, CheckCircle, Clock, DollarSign, MapPin, Sparkles, Star, Target, Truck } from 'lucide-react'

import WorkOrderApiService from '../../services/workorderApi'
import { PriorityBadge } from './shared'
import {
  getProviderCatalog,
  getMockProviderMatches,
  WORKORDER_MOCKS_ENABLED,
} from '../../services/workorderMockAdapter'

const PROVIDERS = getProviderCatalog()

export default function DispatchView({ workOrders }) {
  const dispatchable = workOrders.filter((w) => w.status === 'open' || w.status === 'reopened')
  const [selectedWO, setSelectedWO] = useState(dispatchable[0]?.id || null)
  const [matchResults, setMatchResults] = useState(null)
  const [dispatching, setDispatching] = useState(false)
  const [dispatched, setDispatched] = useState(null)
  const [matchSource, setMatchSource] = useState(null)
  const [error, setError] = useState('')

  const wo = dispatchable.find((workOrder) => workOrder.id === selectedWO)

  const runMatch = async () => {
    if (!wo) return
    setMatchSource(null)
    setError('')

    const { ok, data } = await WorkOrderApiService.matchProviders({
      work_order_id: wo.id,
      title: wo.title,
      description: wo.description,
      asset_id: wo.asset_id,
      priority: wo.priority,
      problem_type: wo.title,
      location: wo.location,
      providers: PROVIDERS.map((provider) => ({
        id: provider.id,
        name: provider.name,
        specialty: provider.specialty,
        rating: provider.rating,
        ftfr: provider.ftfr,
        avg_cost: provider.avgCost,
        avg_response_hrs: provider.avgResponseHrs,
        proximity_miles: provider.proximity_miles,
        certifications: provider.certifications,
        available: provider.available,
      })),
    })

    if (ok && data?.matches) {
      setMatchSource(data.raw_llm_response ? 'llm' : 'fallback')
      const scored = data.matches.map((match) => {
        const localProvider = PROVIDERS.find((provider) => provider.id === match.provider?.id)
        return {
          ...(localProvider || match.provider),
          match_score: match.match_score,
          recommended: match.recommended,
          rationale: match.rationale || '',
        }
      })
      setMatchResults(scored)
      return
    }

    if (WORKORDER_MOCKS_ENABLED) {
      setMatchSource('mock_adapter')
      setMatchResults(getMockProviderMatches(wo, PROVIDERS))
    } else {
      setMatchResults([])
      setError('Provider match service is unavailable. Retry once backend connectivity is restored.')
    }
  }

  useEffect(() => {
    if (wo) runMatch()
  }, [selectedWO])

  const handleDispatch = (provider) => {
    setDispatching(true)
    setTimeout(() => {
      setDispatching(false)
      setDispatched(provider.name)
      setTimeout(() => setDispatched(null), 3000)
    }, 1200)
  }

  return (
    <div className="wo-dispatch">
      <div className="wo-dispatch-select">
        <h3><Truck size={18} /> Select Work Order for Dispatch</h3>
        <div className="wo-dispatch-list">
          {dispatchable.map((workOrder) => (
            <button
              key={workOrder.id}
              className={clsx('wo-dispatch-wo-btn', { active: selectedWO === workOrder.id })}
              onClick={() => setSelectedWO(workOrder.id)}
            >
              <PriorityBadge priority={workOrder.priority} />
              <div>
                <div className="wo-mini-id">{workOrder.id}</div>
                <div className="wo-mini-title">{workOrder.title}</div>
              </div>
            </button>
          ))}
          {dispatchable.length === 0 ? <div className="wo-empty">No work orders awaiting dispatch.</div> : null}
        </div>
      </div>

      {error ? <div className="wo-clarification" role="alert">{error}</div> : null}

      {wo && matchResults ? (
        <div className="wo-match-results">
          <div className="wo-match-header">
            <h3><Target size={18} /> Provider Match Results</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span className="wo-match-subtitle">for {wo.id} - {wo.title}</span>
              {matchSource ? (
                <span style={{ fontSize: '0.6rem', fontWeight: 700, padding: '0.1rem 0.4rem', borderRadius: '99px', background: matchSource === 'llm' ? '#dcfce7' : '#fef9c3', color: matchSource === 'llm' ? '#059669' : '#854d0e' }}>
                  {matchSource === 'llm' ? '✦ GPT-4' : matchSource === 'mock_adapter' ? '⚙ Mock Adapter' : '⚙ Server Fallback'}
                </span>
              ) : null}
            </div>
          </div>

          <div className="wo-provider-list">
            {matchResults.map((provider) => (
              <div key={provider.id} className={clsx('wo-provider-card', { recommended: provider.recommended, unavailable: !provider.available })}>
                {provider.recommended ? <div className="wo-recommended-tag"><Sparkles size={12} /> AI Recommended</div> : null}
                <div className="wo-provider-top">
                  <div className="wo-provider-info">
                    <div className="wo-provider-name">{provider.name}</div>
                    <div className="wo-provider-spec">{provider.specialty}</div>
                  </div>
                  <div className="wo-provider-score" style={{ color: provider.match_score > 75 ? '#22c55e' : provider.match_score > 50 ? '#f59e0b' : '#94a3b8' }}>
                    {provider.match_score}
                  </div>
                </div>
                <div className="wo-provider-metrics">
                  <span><Star size={11} /> {provider.rating}</span>
                  <span><CheckCircle size={11} /> FTFR {(provider.ftfr * 100).toFixed(0)}%</span>
                  <span><Clock size={11} /> {provider.avgResponseHrs}h avg</span>
                  <span><MapPin size={11} /> {provider.proximity_miles} mi</span>
                  <span><DollarSign size={11} /> ${provider.avgCost} avg</span>
                </div>
                <div className="wo-provider-certs">
                  {provider.certifications.map((certification) => <span key={certification} className="wo-cert-tag">{certification}</span>)}
                </div>
                {provider.rationale ? (
                  <div style={{ fontSize: '0.72rem', color: 'var(--gray-600)', padding: '0.4rem 0.6rem', background: 'var(--gray-50)', borderRadius: 'var(--radius-sm)', marginBottom: '0.4rem', lineHeight: 1.4, fontStyle: 'italic' }}>
                    <Brain size={11} style={{ verticalAlign: -1, marginRight: 3 }} />{provider.rationale}
                  </div>
                ) : null}
                <button
                  className="wo-btn wo-btn-primary wo-btn-sm"
                  disabled={!provider.available || dispatching}
                  onClick={() => handleDispatch(provider)}
                >
                  {!provider.available ? 'Unavailable' : dispatching ? 'Dispatching...' : 'Dispatch'}
                </button>
              </div>
            ))}
          </div>
          {dispatched ? <div className="wo-success-msg"><CheckCircle size={16} /> Dispatched to {dispatched}!</div> : null}
        </div>
      ) : null}
    </div>
  )
}
