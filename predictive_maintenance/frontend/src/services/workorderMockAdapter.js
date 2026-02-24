import { addDays, subDays } from 'date-fns'

const mockFlag = String(import.meta.env.VITE_WORKORDER_MOCKS || 'false').toLowerCase()
export const WORKORDER_MOCKS_ENABLED = mockFlag === '1' || mockFlag === 'true' || mockFlag === 'yes'

function seeded(seed) {
  let state = seed >>> 0
  return () => {
    state = (1664525 * state + 1013904223) >>> 0
    return state / 0xffffffff
  }
}

function hashText(text) {
  let hash = 2166136261
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

export function getProviderCatalog() {
  return [
    { id: 'prov-1', name: 'CoolTech HVAC Services', rating: 4.8, specialty: 'Commercial HVAC', avgCost: 850, ftfr: 0.92, avgResponseHrs: 2.1, proximity_miles: 3.2, certifications: ['EPA 608', 'NATE'], available: true },
    { id: 'prov-2', name: 'Arctic Mechanical', rating: 4.5, specialty: 'Refrigeration', avgCost: 720, ftfr: 0.88, avgResponseHrs: 3.4, proximity_miles: 7.8, certifications: ['EPA 608'], available: true },
    { id: 'prov-3', name: 'ProServ Building Solutions', rating: 4.6, specialty: 'Controls & BMS', avgCost: 950, ftfr: 0.85, avgResponseHrs: 1.8, proximity_miles: 5.1, certifications: ['NATE', 'BACnet'], available: false },
    { id: 'prov-4', name: 'Thermal Dynamics Inc', rating: 4.3, specialty: 'Industrial HVAC', avgCost: 680, ftfr: 0.90, avgResponseHrs: 4.2, proximity_miles: 12.4, certifications: ['EPA 608'], available: true },
    { id: 'prov-5', name: 'FirstFix Mechanical', rating: 4.7, specialty: 'Emergency Repair', avgCost: 1100, ftfr: 0.95, avgResponseHrs: 1.2, proximity_miles: 2.0, certifications: ['EPA 608', 'NATE', 'R-410A'], available: true },
  ]
}

export function generateMockWorkOrders(seed = 20260224) {
  const rand = seeded(seed)
  const estates = ['North Campus', 'South Campus', 'Downtown HQ', 'Warehouse District']
  const locations = ['Building A - Floor 2', 'Building B - Roof', 'Building C - Mech Room', 'Cold Storage Unit 4', 'Server Room 1', 'Retail Floor']
  const assets = ['RTU-001', 'AHU-003', 'CH-002', 'CU-007', 'FCU-012', 'VRF-005', 'CT-003']
  const faults = ['Compressor high discharge temp', 'Low refrigerant charge detected', 'Condenser fan motor degradation', 'Sensor drift on suction pressure', 'Filter differential pressure high', 'Evaporator coil icing', 'VFD fault code F7']
  const providers = getProviderCatalog()
  const statuses = ['open', 'assigned', 'in_progress', 'pending_approval', 'completed', 'verified', 'reopened']
  const priorities = ['critical', 'high', 'medium', 'low']
  const sources = ['ai_sensor', 'ai_sensor', 'manual', 'manual', 'ai_nlp', 'pdm_alert']

  return Array.from({ length: 18 }, (_, i) => {
    const priority = priorities[i % 4]
    const status = statuses[i % 7]
    const source = sources[i % 6]
    const created = subDays(new Date(), rand() * 14)
    return {
      id: `WO-2025-${String(1200 + i).padStart(4, '0')}`,
      title: faults[i % faults.length],
      description: `${faults[i % faults.length]} detected on ${assets[i % assets.length]}. ${source === 'ai_sensor' ? 'Auto-generated from PdM system anomaly detection.' : source === 'pdm_alert' ? 'Triggered by PdM alert dispatch recommendation.' : 'Reported by facility staff.'}`,
      asset_id: assets[i % assets.length],
      estate: estates[i % estates.length],
      location: locations[i % locations.length],
      priority,
      status,
      source,
      created_at: created.toISOString(),
      updated_at: addDays(created, rand() * 3).toISOString(),
      sla_deadline: addDays(created, priority === 'critical' ? 1 : priority === 'high' ? 3 : priority === 'medium' ? 7 : 14).toISOString(),
      estimated_cost: Math.round(400 + rand() * 1200),
      actual_cost: status === 'completed' || status === 'verified' ? Math.round(350 + rand() * 1000) : null,
      assigned_provider: (status !== 'open' && status !== 'draft') ? providers[i % providers.length] : null,
      ai_priority_score: Math.round(40 + rand() * 60),
      ai_impact_assessment: {
        safety_risk: rand() > 0.7 ? 'High' : rand() > 0.4 ? 'Medium' : 'Low',
        revenue_impact: Math.round(rand() * 5000),
        sla_breach_risk: rand(),
        brand_impact: rand() > 0.6 ? 'Yes' : 'No',
      },
      ai_rationale: priority === 'critical'
        ? 'Compressor anomaly with high safety risk. Immediate dispatch recommended to prevent cascading failure.'
        : priority === 'high'
        ? 'Elevated change detection scores persist >4h. SLA breach risk 78%. Recommend next-day service.'
        : 'Moderate sensor drift; no immediate operational impact. Schedule during next PM cycle.',
      verification: status === 'verified'
        ? { passed: true, confidence: 0.94, post_metrics_improved: true }
        : status === 'reopened'
          ? { passed: false, confidence: 0.45, post_metrics_improved: false, reopen_reason: 'Post-service sensor readings still anomalous' }
          : null,
    }
  })
}

export function getInitialWorkOrders() {
  return WORKORDER_MOCKS_ENABLED ? generateMockWorkOrders() : []
}

export function getMockInterpretation(text) {
  const raw = String(text || '')
  const lower = raw.toLowerCase()
  const token = hashText(lower)
  const assets = ['RTU-001', 'AHU-003', 'CH-002', 'CU-007']
  const locations = ['Building A - Roof', 'Building B - Floor 1', 'Server Room 1', 'Cold Storage Unit 4']
  const priorities = ['critical', 'high', 'medium', 'low']
  const priority = priorities[token % priorities.length]
  const assetId = assets[token % assets.length]
  const location = locations[(token >> 4) % locations.length]

  return {
    title: `Mock interpretation for ${assetId}`,
    description: raw || 'Operator reported issue from mock adapter.',
    asset_id: assetId,
    estate: 'North Campus',
    location,
    priority,
    problem_type: 'General',
    source: 'ai_nlp',
    ai_confidence: 0.82,
    symptoms: [],
    clarifications: [],
  }
}

export function getMockProviderMatches(workOrder, providers = getProviderCatalog()) {
  const base = hashText(`${workOrder?.id || ''}:${workOrder?.asset_id || ''}`)
  const scored = providers
    .map((provider, index) => {
      const scoreSeed = ((base >> (index % 8)) & 0xff) / 255
      const responseFactor = Math.max(0, 1 - provider.avgResponseHrs / 6)
      const score = Math.round(
        (provider.ftfr * 45) +
        (provider.rating / 5 * 25) +
        (responseFactor * 20) +
        (scoreSeed * 10),
      )
      return {
        ...provider,
        match_score: Math.max(10, Math.min(99, score)),
        recommended: false,
        rationale: `Mock adapter score based on FTFR, response time, and location fit for ${workOrder?.asset_id || 'asset'}.`,
      }
    })
    .sort((a, b) => b.match_score - a.match_score)

  if (scored.length > 0) {
    scored[0].recommended = true
  }
  return scored
}

export function getMockApprovalRecommendation(workOrder) {
  const cost = Number(workOrder?.estimated_cost || 0)
  if (cost <= 750) {
    return {
      action: 'approve',
      confidence: 0.88,
      reason: 'Mock adapter: cost is below historical midpoint.',
      historical_comparison: 'Below baseline cost band.',
    }
  }
  if (cost <= 1200) {
    return {
      action: 'approve',
      confidence: 0.74,
      reason: 'Mock adapter: cost is within expected operating range.',
      historical_comparison: 'Within baseline cost band.',
    }
  }
  return {
    action: 'review',
    confidence: 0.62,
    reason: 'Mock adapter: cost is above expected range, route for manual review.',
    historical_comparison: 'Above baseline cost band.',
  }
}

export function getMockForecast(workOrders, days = 30) {
  const today = new Date()
  const volumeBase = Math.max(2, Math.round((workOrders?.length || 12) / 6))
  const points = Array.from({ length: days }, (_, index) => {
    const date = addDays(today, index - 7)
    const wave = ((index * 7) % 6) - 2
    const predicted = Math.max(1, volumeBase + wave)
    const actual = date <= today ? Math.max(0, predicted - 1) : null
    return {
      date: date.toISOString(),
      predicted_count: predicted,
      actual_count: actual,
    }
  })

  return {
    narrative: 'Mock adapter forecast: steady workload with mild weekly seasonality and controlled escalation risk.',
    risk_estates: {
      'North Campus': 0.64,
      'South Campus': 0.42,
      'Downtown HQ': 0.57,
      'Warehouse District': 0.49,
    },
    points,
  }
}
