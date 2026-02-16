/**
 * CapEx Generator Page
 *
 * Wraps the standalone CapEx Generator app inside the PDM shell.
 * Tailwind CSS is scoped to .capex-scope to avoid conflicts with PDM styles.
 */

import CapExApp from '../capex/CapExApp'
import '../capex/capex.css'

export default function CapExPage() {
  return (
    <div className="capex-scope" style={{ margin: '-1.5rem', minHeight: 'calc(100vh - 48px)' }}>
      <div style={{
        background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: 10,
        padding: '10px 14px', fontSize: '0.8rem', color: '#0c4a6e',
        margin: '1.5rem 1rem 0', lineHeight: 1.6, fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      }}>
        <strong>What this page does:</strong> Generate <strong>budget-constrained CapEx replacement plans</strong> from
        fleet telemetry. Scores each asset using peer comparisons, survival analysis, fault detection,
        and economic NPV — then ranks them for replacement within your budget, showing expected savings,
        payback periods, and deferred assets.
      </div>
      <CapExApp />
    </div>
  )
}
