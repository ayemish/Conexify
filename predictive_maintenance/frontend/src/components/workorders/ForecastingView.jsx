import { useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'
import { BarChart3, Brain, Target, TrendingUp } from 'lucide-react'
import { format, subDays } from 'date-fns'

import WorkOrderApiService from '../../services/workorderApi'
import { getMockForecast, WORKORDER_MOCKS_ENABLED } from '../../services/workorderMockAdapter'

export default function ForecastingView({ workOrders }) {
  const days = 30
  const [forecastData, setForecastData] = useState([])
  const [narrative, setNarrative] = useState('')
  const [riskEstates, setRiskEstates] = useState(null)
  const [forecastSource, setForecastSource] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    async function loadForecast() {
      setError('')
      const historicalCounts = workOrders.slice(0, 30).map((workOrder, index) => ({
        date: format(subDays(new Date(), 30 - index), 'yyyy-MM-dd'),
        count: workOrder.ai_priority_score ? Math.max(1, Math.round(workOrder.ai_priority_score / 20)) : 2,
      }))

      const { ok, data } = await WorkOrderApiService.forecast({
        site_id: 'default',
        horizon_days: days,
        historical_wo_counts: historicalCounts,
        asset_risk_scores: { 'RTU-001': 0.82, 'AHU-003': 0.65, 'CH-002': 0.45, 'CU-007': 0.71 },
      })

      if (ok && data?.points) {
        setForecastSource(data.raw_llm_response ? 'llm' : 'fallback')
        setNarrative(data.narrative || '')
        setRiskEstates(data.risk_estates || null)
        setForecastData(
          data.points.map((point) => {
            const date = new Date(point.date)
            const isPast = date <= new Date()
            return {
              date,
              label: format(date, 'MMM d'),
              shortLabel: format(date, 'd'),
              predicted: point.predicted_count,
              actual: isPast ? Math.max(0, point.predicted_count - 1) : null,
              isToday: format(date, 'yyyy-MM-dd') === format(new Date(), 'yyyy-MM-dd'),
            }
          }),
        )
        return
      }

      if (WORKORDER_MOCKS_ENABLED) {
        const mockForecast = getMockForecast(workOrders, days)
        setForecastSource('mock_adapter')
        setNarrative(mockForecast.narrative)
        setRiskEstates(mockForecast.risk_estates)
        setForecastData(mockForecast.points.map((point) => {
          const date = new Date(point.date)
          const isPast = date <= new Date()
          return {
            date,
            label: format(date, 'MMM d'),
            shortLabel: format(date, 'd'),
            predicted: point.predicted_count,
            actual: isPast ? point.actual_count : null,
            isToday: format(date, 'yyyy-MM-dd') === format(new Date(), 'yyyy-MM-dd'),
          }
        }))
      } else {
        setForecastSource('error')
        setNarrative('')
        setRiskEstates(null)
        setForecastData([])
        setError('Forecast service is unavailable. Retry once backend connectivity is restored.')
      }
    }

    loadForecast()
  }, [workOrders])

  const maxVal = useMemo(
    () => (forecastData.length > 0 ? Math.max(...forecastData.map((d) => Math.max(d.predicted, d.actual || 0)), 1) : 1),
    [forecastData],
  )

  const estates = ['North Campus', 'South Campus', 'Downtown HQ', 'Warehouse District']
  const riskWeeks = ['This Week', 'Next Week', 'Week 3', 'Week 4']
  const heatData = useMemo(
    () => (
      riskEstates
        ? estates.map((estate) => riskWeeks.map(() => riskEstates[estate] ?? 0.5))
        : estates.map(() => riskWeeks.map(() => 0.5))
    ),
    [riskEstates],
  )

  return (
    <div className="wo-forecasting">
      <h3><TrendingUp size={18} /> Predictive Work Order Forecasting</h3>
      <p className="wo-forecast-subtitle">Time-series models predict future work order volumes based on historical patterns, sensor trends, and seasonal factors.</p>

      {error ? <div className="wo-clarification" role="alert">{error}</div> : null}

      {narrative ? (
        <div className="wo-signal-box" style={{ marginBottom: '1rem' }}>
          <div className="wo-signal-header">
            <Brain size={16} style={{ color: '#6366f1' }} />
            <strong>AI Forecast Narrative</strong>
            {forecastSource ? (
              <span style={{ marginLeft: 'auto', fontSize: '0.6rem', fontWeight: 700, padding: '0.1rem 0.4rem', borderRadius: '99px', background: forecastSource === 'llm' ? '#dcfce7' : '#fef9c3', color: forecastSource === 'llm' ? '#059669' : '#854d0e' }}>
                {forecastSource === 'llm' ? '✦ GPT-4' : forecastSource === 'mock_adapter' ? '⚙ Mock Adapter' : '⚙ Fallback'}
              </span>
            ) : null}
          </div>
          <p style={{ margin: 0 }}>{narrative}</p>
        </div>
      ) : null}

      <div className="wo-panel">
        <div className="wo-panel-header"><h3><BarChart3 size={16} /> 30-Day Volume Forecast</h3></div>
        <div className="wo-panel-body">
          <div className="wo-forecast-chart">
            <div className="wo-forecast-y-axis">
              {[maxVal, Math.round(maxVal / 2), 0].map((value) => <span key={value}>{value}</span>)}
            </div>
            <div className="wo-forecast-bars">
              {forecastData.map((day, index) => (
                <div key={`${day.label}-${index}`} className={clsx('wo-fbar-col', { today: day.isToday })} title={`${day.label}: Predicted ${day.predicted}${day.actual != null ? `, Actual ${day.actual}` : ''}`}>
                  <div className="wo-fbar-wrapper">
                    {day.actual != null ? <div className="wo-fbar wo-fbar-actual" style={{ height: `${(day.actual / maxVal) * 100}%` }} /> : null}
                    <div className="wo-fbar wo-fbar-pred" style={{ height: `${(day.predicted / maxVal) * 100}%` }} />
                  </div>
                  {(index % 3 === 0 || day.isToday) ? <span className="wo-fbar-label">{day.shortLabel}</span> : null}
                </div>
              ))}
            </div>
          </div>
          <div className="wo-forecast-legend">
            <span><span className="wo-legend-dot" style={{ background: '#6366f1' }} /> Predicted</span>
            <span><span className="wo-legend-dot" style={{ background: '#22c55e' }} /> Actual</span>
          </div>
        </div>
      </div>

      <div className="wo-panel">
        <div className="wo-panel-header"><h3><Target size={16} /> Risk Heat Map by Estate</h3></div>
        <div className="wo-panel-body">
          <div className="wo-heatmap">
            <div className="wo-heatmap-header">
              <div className="wo-heatmap-label" />
              {riskWeeks.map((week) => <div key={week} className="wo-heatmap-col-label">{week}</div>)}
            </div>
            {estates.map((estate, estateIndex) => (
              <div key={estate} className="wo-heatmap-row">
                <div className="wo-heatmap-label">{estate}</div>
                {heatData[estateIndex].map((risk, weekIndex) => {
                  const red = Math.round(risk * 255)
                  return (
                    <div key={`${estate}-${weekIndex}`} className="wo-heatmap-cell" style={{ background: `rgba(${red > 180 ? 239 : red > 100 ? 249 : 34}, ${red > 180 ? 68 : red > 100 ? 115 : 197}, ${red > 180 ? 68 : red > 100 ? 22 : 94}, ${0.15 + risk * 0.55})` }}>
                      {(risk * 100).toFixed(0)}%
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
