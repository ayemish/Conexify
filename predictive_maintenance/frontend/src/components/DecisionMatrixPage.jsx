import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Scale, RefreshCw, ChevronDown, ChevronUp, Filter,
  AlertTriangle, CheckCircle, Clock, TrendingUp, DollarSign,
  Zap, Shield, Leaf, Users, BarChart3, Info, Loader2,
  ArrowUpDown, Search, GitBranch
} from 'lucide-react';
import ScenarioAnalysis from './ScenarioAnalysis';
import '../DecisionMatrix.css';

const API_BASE = 'http://localhost:8000/api/v1/decision-matrix';

const DIMENSION_META = {
  financial_roi:    { icon: DollarSign,    color: '#2563eb', label: 'Financial ROI' },
  energy_savings:   { icon: Zap,           color: '#f59e0b', label: 'Energy Savings' },
  reliability_risk: { icon: AlertTriangle, color: '#ef4444', label: 'Reliability Risk' },
  regulatory_risk:  { icon: Shield,        color: '#8b5cf6', label: 'Regulatory Risk' },
  esg_impact:       { icon: Leaf,          color: '#10b981', label: 'ESG Impact' },
  customer_impact:  { icon: Users,         color: '#ec4899', label: 'Customer Impact' },
};

const DIMENSION_KEYS = Object.keys(DIMENSION_META);

const REC_BADGES = {
  REPLACE: { bg: '#fef2f2', color: '#dc2626', border: '#fecaca', label: 'Replace' },
  REPAIR:  { bg: '#fffbeb', color: '#d97706', border: '#fde68a', label: 'Repair' },
  DEFER:   { bg: '#f0fdf4', color: '#16a34a', border: '#bbf7d0', label: 'Defer' },
};

// ── Weight Slider ──────────────────────────────────────────────────
function WeightSlider({ dimKey, value, onChange }) {
  const meta = DIMENSION_META[dimKey];
  const Icon = meta.icon;
  return (
    <div className="dm-weight-slider">
      <div className="dm-weight-header">
        <Icon size={14} style={{ color: meta.color }} />
        <span className="dm-weight-label">{meta.label}</span>
        <span className="dm-weight-value" style={{ color: meta.color }}>{value}%</span>
      </div>
      <input
        type="range"
        min={0}
        max={100}
        step={5}
        value={value}
        onChange={e => onChange(dimKey, Number(e.target.value))}
        className="dm-slider"
        style={{ '--slider-color': meta.color }}
      />
    </div>
  );
}

// ── Radar Chart (pure SVG) ─────────────────────────────────────────
function RadarChart({ dimensions, size = 120 }) {
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 12;
  const n = DIMENSION_KEYS.length;

  const angleStep = (2 * Math.PI) / n;
  const offset = -Math.PI / 2;

  const gridLevels = [0.25, 0.5, 0.75, 1.0];

  const point = (i, pct) => {
    const angle = offset + i * angleStep;
    return {
      x: cx + r * pct * Math.cos(angle),
      y: cy + r * pct * Math.sin(angle),
    };
  };

  const dataPoints = DIMENSION_KEYS.map((k, i) => {
    const score = dimensions[k]?.score ?? 0;
    return point(i, score / 100);
  });

  const polygon = dataPoints.map(p => `${p.x},${p.y}`).join(' ');

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="dm-radar">
      {/* Grid */}
      {gridLevels.map(level => (
        <polygon
          key={level}
          points={DIMENSION_KEYS.map((_, i) => {
            const p = point(i, level);
            return `${p.x},${p.y}`;
          }).join(' ')}
          fill="none"
          stroke="#e2e8f0"
          strokeWidth={0.5}
        />
      ))}
      {/* Axes */}
      {DIMENSION_KEYS.map((k, i) => {
        const p = point(i, 1);
        return (
          <line key={k} x1={cx} y1={cy} x2={p.x} y2={p.y} stroke="#e2e8f0" strokeWidth={0.5} />
        );
      })}
      {/* Data polygon */}
      <polygon points={polygon} fill="rgba(37, 99, 235, 0.15)" stroke="#2563eb" strokeWidth={1.5} />
      {/* Data dots */}
      {dataPoints.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={2.5} fill={DIMENSION_META[DIMENSION_KEYS[i]].color} />
      ))}
      {/* Axis labels */}
      {DIMENSION_KEYS.map((k, i) => {
        const labelR = r + 10;
        const angle = offset + i * angleStep;
        const lx = cx + labelR * Math.cos(angle);
        const ly = cy + labelR * Math.sin(angle);
        const meta = DIMENSION_META[k];
        return (
          <text
            key={k}
            x={lx}
            y={ly}
            textAnchor="middle"
            dominantBaseline="central"
            fontSize={7}
            fill="#64748b"
          >
            {meta.label.split(' ')[0]}
          </text>
        );
      })}
    </svg>
  );
}

// ── Score Bar ──────────────────────────────────────────────────────
function ScoreBar({ dimKey, score, weight }) {
  const meta = DIMENSION_META[dimKey];
  const Icon = meta.icon;
  const weighted = ((score * weight) / 100).toFixed(1);
  return (
    <div className="dm-score-bar-row">
      <Icon size={12} style={{ color: meta.color }} />
      <span className="dm-score-bar-label">{meta.label}</span>
      <div className="dm-score-bar-track">
        <div
          className="dm-score-bar-fill"
          style={{ width: `${score}%`, backgroundColor: meta.color }}
        />
      </div>
      <span className="dm-score-bar-value">{score.toFixed(0)}</span>
      <span className="dm-score-bar-weighted" title={`Weighted contribution: ${weighted}`}>({weighted})</span>
    </div>
  );
}

// ── Asset Card ─────────────────────────────────────────────────────
function AssetCard({ asset, weights, expanded, onToggle }) {
  const badge = REC_BADGES[asset.recommendation] || REC_BADGES.DEFER;
  const dims = asset.dimensions || {};
  const [showScenarios, setShowScenarios] = useState(false);

  return (
    <div className={`dm-asset-card ${asset.recommendation.toLowerCase()}`}>
      <div className="dm-asset-header" onClick={onToggle}>
        <div className="dm-asset-primary">
          <span className="dm-asset-score" style={{
            background: asset.weighted_total >= 70 ? '#fef2f2' :
                        asset.weighted_total >= 45 ? '#fffbeb' : '#f0fdf4',
            color: asset.weighted_total >= 70 ? '#dc2626' :
                   asset.weighted_total >= 45 ? '#d97706' : '#16a34a',
          }}>
            {asset.weighted_total.toFixed(0)}
          </span>
          <div className="dm-asset-info">
            <div className="dm-asset-id">{asset.asset_id}</div>
            <div className="dm-asset-meta">
              {asset.asset_type.replace(/_/g, ' ')} · {asset.estate} / {asset.location}
            </div>
          </div>
        </div>
        <div className="dm-asset-right">
          <span className="dm-rec-badge" style={{
            background: badge.bg,
            color: badge.color,
            borderColor: badge.border,
          }}>
            {badge.label}
          </span>
          <div className="dm-asset-financials-mini">
            <span>NPV ${(asset.financials?.npv_5yr || 0).toLocaleString()}</span>
            <span>Payback {asset.financials?.simple_payback_years || '—'}yr</span>
          </div>
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </div>
      </div>

      {expanded && (
        <div className="dm-asset-detail">
          <div className="dm-detail-grid">
            <div className="dm-detail-scores">
              <h4>Dimension Scores</h4>
              {DIMENSION_KEYS.map(k => (
                <ScoreBar
                  key={k}
                  dimKey={k}
                  score={dims[k]?.score ?? 0}
                  weight={weights[k] ?? 0}
                />
              ))}
            </div>
            <div className="dm-detail-radar">
              <RadarChart dimensions={dims} size={160} />
            </div>
            <div className="dm-detail-financials">
              <h4>Financial Summary</h4>
              <div className="dm-fin-grid">
                <div className="dm-fin-item">
                  <span className="dm-fin-label">Replacement Cost</span>
                  <span className="dm-fin-value">${(asset.financials?.replacement_cost || 0).toLocaleString()}</span>
                </div>
                <div className="dm-fin-item">
                  <span className="dm-fin-label">Est. Annual Savings</span>
                  <span className="dm-fin-value">${(asset.financials?.estimated_annual_savings || 0).toLocaleString()}</span>
                </div>
                <div className="dm-fin-item">
                  <span className="dm-fin-label">Simple Payback</span>
                  <span className="dm-fin-value">{asset.financials?.simple_payback_years || '—'} years</span>
                </div>
                <div className="dm-fin-item">
                  <span className="dm-fin-label">5-Year NPV</span>
                  <span className="dm-fin-value">${(asset.financials?.npv_5yr || 0).toLocaleString()}</span>
                </div>
              </div>
            </div>
          </div>
          {asset.narrative && (
            <div className="dm-narrative">
              <Info size={14} />
              <p>{asset.narrative}</p>
            </div>
          )}
          {/* Dimension details */}
          <div className="dm-dim-details">
            {DIMENSION_KEYS.map(k => {
              const d = dims[k];
              if (!d?.detail) return null;
              const meta = DIMENSION_META[k];
              return (
                <span key={k} className="dm-dim-tag" style={{ borderColor: meta.color + '40', color: meta.color }}>
                  {d.detail}
                </span>
              );
            })}
          </div>

          {/* What-If Scenarios (embedded ScenarioAnalysis) */}
          <div style={{ marginTop: '0.75rem', borderTop: '1px solid #e2e8f0', paddingTop: '0.75rem' }}>
            <button
              onClick={(e) => { e.stopPropagation(); setShowScenarios(s => !s); }}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '0.45rem 0.85rem', borderRadius: 8, border: '1px solid #e2e8f0',
                background: showScenarios ? '#eff6ff' : '#fff', color: showScenarios ? '#1d4ed8' : '#475569',
                cursor: 'pointer', fontWeight: 600, fontSize: '0.78rem', transition: 'all 0.15s',
              }}
            >
              <GitBranch size={14} />
              {showScenarios ? 'Hide' : 'Run'} What-If Scenarios
              {showScenarios ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
            {showScenarios && (
              <ScenarioAnalysis embedded initialAssetId={asset.asset_id} />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Summary Cards ──────────────────────────────────────────────────
function SummaryCards({ summary }) {
  return (
    <div className="dm-summary-cards">
      <div className="dm-summary-card">
        <div className="dm-summary-icon replace"><AlertTriangle size={18} /></div>
        <div>
          <div className="dm-summary-value">{summary.replace_count}</div>
          <div className="dm-summary-label">Replace</div>
        </div>
        <div className="dm-summary-sub">${(summary.total_replace_capex || 0).toLocaleString()} CapEx</div>
      </div>
      <div className="dm-summary-card">
        <div className="dm-summary-icon repair"><Clock size={18} /></div>
        <div>
          <div className="dm-summary-value">{summary.repair_count}</div>
          <div className="dm-summary-label">Repair</div>
        </div>
      </div>
      <div className="dm-summary-card">
        <div className="dm-summary-icon defer"><CheckCircle size={18} /></div>
        <div>
          <div className="dm-summary-value">{summary.defer_count}</div>
          <div className="dm-summary-label">Defer</div>
        </div>
      </div>
      <div className="dm-summary-card">
        <div className="dm-summary-icon npv"><TrendingUp size={18} /></div>
        <div>
          <div className="dm-summary-value">${(summary.total_expected_npv || 0).toLocaleString()}</div>
          <div className="dm-summary-label">Total NPV (Replace)</div>
        </div>
      </div>
      <div className="dm-summary-card">
        <div className="dm-summary-icon avg"><BarChart3 size={18} /></div>
        <div>
          <div className="dm-summary-value">{summary.avg_weighted_score?.toFixed(1) || '—'}</div>
          <div className="dm-summary-label">Avg Score</div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Main Page Component
// ═══════════════════════════════════════════════════════════════════
export default function DecisionMatrixPage() {
  const [weights, setWeights] = useState({
    financial_roi: 30,
    energy_savings: 20,
    reliability_risk: 20,
    regulatory_risk: 10,
    esg_impact: 10,
    customer_impact: 10,
  });

  const [financials, setFinancials] = useState({
    discount_rate: 0.08,
    repair_threshold_pct: 50,
    payback_target_years: 5,
    energy_cost_per_kwh: 0.12,
    budget_constraint: null,
  });

  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const [filterRec, setFilterRec] = useState('ALL');
  const [searchTerm, setSearchTerm] = useState('');
  const [sortKey, setSortKey] = useState('weighted_total');
  const [sortDesc, setSortDesc] = useState(true);
  const [showFinancials, setShowFinancials] = useState(false);

  const totalWeight = useMemo(
    () => Object.values(weights).reduce((a, b) => a + b, 0),
    [weights]
  );

  const handleWeightChange = useCallback((key, value) => {
    setWeights(prev => ({ ...prev, [key]: value }));
  }, []);

  const handleFinancialChange = useCallback((key, value) => {
    setFinancials(prev => ({ ...prev, [key]: value }));
  }, []);

  const runEvaluation = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/evaluate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          weights,
          financials,
          site_id: 'default',
        }),
      });
      if (!res.ok) throw new Error(`API error: ${res.status}`);
      const data = await res.json();
      setResults(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [weights, financials]);

  // Run evaluation on mount
  useEffect(() => {
    runEvaluation();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Filter and sort assets
  const filteredAssets = useMemo(() => {
    if (!results?.assets) return [];
    let list = results.assets;

    if (filterRec !== 'ALL') {
      list = list.filter(a => a.recommendation === filterRec);
    }

    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      list = list.filter(a =>
        a.asset_id.toLowerCase().includes(q) ||
        a.estate.toLowerCase().includes(q) ||
        a.location.toLowerCase().includes(q) ||
        a.asset_type.toLowerCase().includes(q)
      );
    }

    list = [...list].sort((a, b) => {
      let aVal, bVal;
      if (sortKey === 'weighted_total') {
        aVal = a.weighted_total;
        bVal = b.weighted_total;
      } else if (sortKey === 'health_score') {
        aVal = a.health_score;
        bVal = b.health_score;
      } else if (sortKey === 'rul_hours') {
        aVal = a.rul_hours;
        bVal = b.rul_hours;
      } else if (DIMENSION_META[sortKey]) {
        aVal = a.dimensions?.[sortKey]?.score ?? 0;
        bVal = b.dimensions?.[sortKey]?.score ?? 0;
      } else {
        aVal = a[sortKey] ?? 0;
        bVal = b[sortKey] ?? 0;
      }
      return sortDesc ? bVal - aVal : aVal - bVal;
    });

    return list;
  }, [results, filterRec, searchTerm, sortKey, sortDesc]);

  return (
    <div className="dm-page">
      {/* ── Header ──────────────────────────────────────────── */}
      <div className="dm-header">
        <div className="dm-header-left">
          <Scale size={24} style={{ color: '#2563eb' }} />
          <div>
            <h1>Decision Matrix</h1>
            <p>Weighted repair / replace / defer analysis across your asset portfolio</p>
          </div>
        </div>
        <button
          className="dm-run-btn"
          onClick={runEvaluation}
          disabled={loading}
        >
          {loading ? <Loader2 size={16} className="dm-spin" /> : <RefreshCw size={16} />}
          {loading ? 'Evaluating…' : 'Run Evaluation'}
        </button>
      </div>

      {/* Page Description */}
      <div style={{
        background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: 10,
        padding: '10px 14px', fontSize: '0.8rem', color: '#0c4a6e',
        marginBottom: '1rem', lineHeight: 1.6,
      }}>
        <strong>What this page does:</strong> Scores every asset across <strong>6 weighted dimensions</strong> —
        financial ROI, energy savings, reliability risk, regulatory risk, ESG impact, and customer impact —
        then recommends <strong>Replace, Repair, or Defer</strong> for each. Adjust the dimension weights
        and financial parameters to see how the fleet-wide ranking changes in real time.
      </div>

      {/* ── Weight Configuration ────────────────────────────── */}
      <div className="dm-config-section">
        <div className="dm-config-header">
          <h2>Decision Weights</h2>
          <span className={`dm-weight-total ${totalWeight !== 100 ? 'warn' : ''}`}>
            Total: {totalWeight}%
            {totalWeight !== 100 && <span className="dm-weight-warn"> (weights auto-normalize)</span>}
          </span>
        </div>
        <div className="dm-weights-grid">
          {DIMENSION_KEYS.map(k => (
            <WeightSlider
              key={k}
              dimKey={k}
              value={weights[k]}
              onChange={handleWeightChange}
            />
          ))}
        </div>

        {/* Financial Parameters (collapsible) */}
        <button
          className="dm-financials-toggle"
          onClick={() => setShowFinancials(p => !p)}
        >
          <DollarSign size={14} />
          Financial Parameters
          {showFinancials ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>

        {showFinancials && (
          <div className="dm-financials-panel">
            <div className="dm-fin-input">
              <label>Discount Rate</label>
              <div className="dm-fin-input-row">
                <input
                  type="range"
                  min={1}
                  max={25}
                  step={0.5}
                  value={financials.discount_rate * 100}
                  onChange={e => handleFinancialChange('discount_rate', Number(e.target.value) / 100)}
                />
                <span>{(financials.discount_rate * 100).toFixed(1)}%</span>
              </div>
            </div>
            <div className="dm-fin-input">
              <label>Repair Threshold (% of replacement)</label>
              <div className="dm-fin-input-row">
                <input
                  type="range"
                  min={10}
                  max={90}
                  step={5}
                  value={financials.repair_threshold_pct}
                  onChange={e => handleFinancialChange('repair_threshold_pct', Number(e.target.value))}
                />
                <span>{financials.repair_threshold_pct}%</span>
              </div>
            </div>
            <div className="dm-fin-input">
              <label>Payback Target</label>
              <div className="dm-fin-input-row">
                <input
                  type="range"
                  min={1}
                  max={15}
                  step={0.5}
                  value={financials.payback_target_years}
                  onChange={e => handleFinancialChange('payback_target_years', Number(e.target.value))}
                />
                <span>{financials.payback_target_years} yr</span>
              </div>
            </div>
            <div className="dm-fin-input">
              <label>Energy Cost ($/kWh)</label>
              <div className="dm-fin-input-row">
                <input
                  type="range"
                  min={1}
                  max={50}
                  step={1}
                  value={financials.energy_cost_per_kwh * 100}
                  onChange={e => handleFinancialChange('energy_cost_per_kwh', Number(e.target.value) / 100)}
                />
                <span>${financials.energy_cost_per_kwh.toFixed(2)}</span>
              </div>
            </div>
            <div className="dm-fin-input">
              <label>Budget Constraint ($)</label>
              <input
                type="number"
                placeholder="No limit"
                value={financials.budget_constraint ?? ''}
                onChange={e => {
                  const v = e.target.value;
                  handleFinancialChange('budget_constraint', v === '' ? null : Number(v));
                }}
                className="dm-text-input"
              />
            </div>
          </div>
        )}
      </div>

      {/* ── Error ───────────────────────────────────────────── */}
      {error && (
        <div className="dm-error">
          <AlertTriangle size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* ── Summary Cards ───────────────────────────────────── */}
      {results?.summary && <SummaryCards summary={results.summary} />}

      {/* ── Filters & Sort ──────────────────────────────────── */}
      {results?.assets?.length > 0 && (
        <div className="dm-toolbar">
          <div className="dm-search">
            <Search size={14} />
            <input
              type="text"
              placeholder="Search assets…"
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
            />
          </div>
          <div className="dm-filters">
            <Filter size={14} />
            {['ALL', 'REPLACE', 'REPAIR', 'DEFER'].map(f => (
              <button
                key={f}
                className={`dm-filter-btn ${filterRec === f ? 'active' : ''}`}
                onClick={() => setFilterRec(f)}
              >
                {f === 'ALL' ? 'All' : f.charAt(0) + f.slice(1).toLowerCase()}
              </button>
            ))}
          </div>
          <div className="dm-sort">
            <ArrowUpDown size={14} />
            <select value={sortKey} onChange={e => setSortKey(e.target.value)}>
              <option value="weighted_total">Total Score</option>
              <option value="health_score">Health Score</option>
              <option value="rul_hours">RUL Hours</option>
              {DIMENSION_KEYS.map(k => (
                <option key={k} value={k}>{DIMENSION_META[k].label}</option>
              ))}
            </select>
            <button
              className="dm-sort-dir"
              onClick={() => setSortDesc(p => !p)}
              title={sortDesc ? 'Descending' : 'Ascending'}
            >
              {sortDesc ? '↓' : '↑'}
            </button>
          </div>
        </div>
      )}

      {/* ── Asset List ──────────────────────────────────────── */}
      <div className="dm-asset-list">
        {loading && !results && (
          <div className="dm-loading">
            <Loader2 size={24} className="dm-spin" />
            <span>Evaluating portfolio…</span>
          </div>
        )}
        {filteredAssets.map(asset => (
          <AssetCard
            key={asset.asset_id}
            asset={asset}
            weights={weights}
            expanded={expandedId === asset.asset_id}
            onToggle={() => setExpandedId(prev => prev === asset.asset_id ? null : asset.asset_id)}
          />
        ))}
        {results && filteredAssets.length === 0 && !loading && (
          <div className="dm-empty">No assets match current filters.</div>
        )}
      </div>
    </div>
  );
}
