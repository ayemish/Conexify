import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'

import DashboardView from '../DashboardView'

const WORK_ORDERS = [
  {
    id: 'WO-2025-1001',
    title: 'Compressor temperature drift',
    asset_id: 'RTU-001',
    status: 'open',
    priority: 'high',
    source: 'ai_sensor',
    estimated_cost: 1200,
    created_at: '2026-02-20T10:00:00.000Z',
    ai_priority_score: 88,
    ai_impact_assessment: { sla_breach_risk: 0.72 },
  },
  {
    id: 'WO-2025-1002',
    title: 'Refrigerant leak signal',
    asset_id: 'AHU-003',
    status: 'pending_approval',
    priority: 'critical',
    source: 'pdm_alert',
    estimated_cost: 900,
    created_at: '2026-02-19T08:00:00.000Z',
    ai_priority_score: 79,
    ai_impact_assessment: { sla_breach_risk: 0.43 },
  },
]

describe('DashboardView', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-02-24T00:00:00.000Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders deterministic forecast output for stable props', () => {
    const onNavigate = vi.fn()
    const { container, rerender } = render(<DashboardView workOrders={WORK_ORDERS} onNavigate={onNavigate} />)

    const first = container.querySelector('.wo-forecast-mini')?.textContent
    expect(first).toBeTruthy()

    rerender(<DashboardView workOrders={WORK_ORDERS} onNavigate={onNavigate} />)
    const second = container.querySelector('.wo-forecast-mini')?.textContent

    expect(second).toBe(first)
    expect(screen.getByText('Open Work Orders')).toBeInTheDocument()
    expect(screen.getAllByText('Pending Approvals').length).toBeGreaterThan(0)
  })
})
