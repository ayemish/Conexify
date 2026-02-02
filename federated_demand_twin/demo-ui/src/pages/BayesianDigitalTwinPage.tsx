import { useState, useEffect } from 'react';
import { 
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, 
  ResponsiveContainer
} from 'recharts';
import { 
  TrendingUp, Target, ArrowUpRight, RefreshCw, GitCompare, Percent
} from 'lucide-react';

interface PosteriorData {
  mean: number;
  std: number;
  ci: [number, number];
}

interface BrandBayesianData {
  brand_id: string;
  brand_name: string;
  category: string;
  bayesian_outputs: {
    incremental_sales: PosteriorData;
    efficiency_mean: number;
    efficiency_std: number;
    index_mean: number;
    lift_vs_prior_period: number;
    lift_vs_year_ago: number;
    prob_positive_lift: number;
    last_updated: string;
  };
  driver_rankings: Array<{ driver: string; prob_top_contributor: number }>;
}

interface RMNBayesianData {
  rmn_id: string;
  rmn_name: string;
  bayesian_outputs: {
    incremental_sales: PosteriorData;
    efficiency_mean: number;
    efficiency_std: number;
    index_mean: number;
    prob_best_overall: number;
    expected_rank: number;
    last_updated: string;
  };
  channel_mix: {
    search: number;
    display: number;
    video: number;
    email: number;
  };
}

interface ChannelBayesianData {
  channel_id: string;
  channel_name: string;
  channel_type: string;
  rmn_id: string;
  bayesian_outputs: {
    incremental_sales: PosteriorData;
    efficiency_mean: number;
    efficiency_std: number;
    index_mean: number;
    elasticity: PosteriorData;
    contribution_mean: number;
    contribution_pct_mean: number;
    prob_efficiency_above_target: number;
    efficiency_target: number;
    prob_rank_1_within_rmn: number;
    expected_rank_within_rmn: number;
    last_updated: string;
  };
}

interface ScenarioComparison {
  entity_type: string;
  entity_id: string;
  current_scenario: {
    scenario_name: string;
    incremental_sales_posterior: PosteriorData;
    efficiency_posterior: { mean: number; std: number };
    downside_risk_5pct: number;
    downside_risk_10pct: number;
  };
  optimized_scenario: {
    scenario_name: string;
    incremental_sales_posterior: PosteriorData;
    efficiency_posterior: { mean: number; std: number };
    downside_risk_5pct: number;
    downside_risk_10pct: number;
  };
  comparison: {
    expected_incremental_sales_delta: number;
    expected_delta_ci: [number, number];
    expected_efficiency_delta: number;
    prob_optimized_beats_current: number;
    prob_optimized_beats_current_by_5pct: number;
    prob_optimized_beats_current_by_10pct: number;
  };
  recommended_allocation: Record<string, number>;
}

const API_BASE = 'http://localhost:8000';

export function BayesianDigitalTwinPage() {
  const [brands, setBrands] = useState<BrandBayesianData[]>([]);
  const [rmns, setRmns] = useState<RMNBayesianData[]>([]);
  const [channels, setChannels] = useState<ChannelBayesianData[]>([]);
  const [scenarioComparison, setScenarioComparison] = useState<ScenarioComparison | null>(null);
  const [selectedRmn, setSelectedRmn] = useState<string>('rmn-walmart');
  const [selectedEntity, setSelectedEntity] = useState<{ type: string; id: string }>({ type: 'brand', id: 'brand-001' });
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'brands' | 'rmns' | 'channels' | 'scenarios'>('brands');

  const fetchData = async () => {
    try {
      setLoading(true);
      const [brandsRes, rmnsRes, channelsRes, scenarioRes] = await Promise.all([
        fetch(`${API_BASE}/api/bayesian/brands`),
        fetch(`${API_BASE}/api/bayesian/rmns`),
        fetch(`${API_BASE}/api/bayesian/channels/${selectedRmn}`),
        fetch(`${API_BASE}/api/bayesian/scenario-comparison/${selectedEntity.type}/${selectedEntity.id}`),
      ]);
      
      const brandsData = await brandsRes.json();
      const rmnsData = await rmnsRes.json();
      const channelsData = await channelsRes.json();
      const scenarioData = await scenarioRes.json();
      
      setBrands(brandsData.brands || []);
      setRmns(rmnsData.rmns || []);
      setChannels(channelsData.channels || []);
      setScenarioComparison(scenarioData);
    } catch (error) {
      console.error('Error fetching Bayesian data:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [selectedRmn, selectedEntity]);

  const formatCurrency = (value: number) => {
    if (value >= 1000000) return `$${(value / 1000000).toFixed(1)}M`;
    if (value >= 1000) return `$${(value / 1000).toFixed(0)}K`;
    return `$${value.toFixed(0)}`;
  };

  const formatPercent = (value: number) => `${(value * 100).toFixed(1)}%`;

  if (loading && brands.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-blue-600 animate-spin" />
        <span className="ml-2 text-slate-600">Loading Bayesian digital twin data...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Bayesian Digital Twin Outputs</h1>
          <p className="text-slate-500 mt-1">Posterior distributions, lift decompositions, and scenario comparisons</p>
        </div>
        <button
          onClick={fetchData}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-2 border-b border-slate-200">
        {(['brands', 'rmns', 'channels', 'scenarios'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 font-medium text-sm border-b-2 transition-colors ${
              activeTab === tab
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            {tab === 'brands' && 'Brand Posteriors'}
            {tab === 'rmns' && 'RMN Posteriors'}
            {tab === 'channels' && 'Channel Posteriors'}
            {tab === 'scenarios' && 'Scenario Comparison'}
          </button>
        ))}
      </div>

      {/* Brands Tab */}
      {activeTab === 'brands' && (
        <div className="space-y-6">
          {/* Summary Cards */}
          <div className="grid grid-cols-4 gap-4">
            <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
              <div className="flex items-center gap-2 mb-2">
                <TrendingUp className="w-5 h-5 text-green-600" />
                <span className="text-sm text-slate-500">Avg Incremental Sales</span>
              </div>
              <p className="text-2xl font-bold text-slate-900">
                {formatCurrency(brands.reduce((sum, b) => sum + b.bayesian_outputs.incremental_sales.mean, 0) / Math.max(brands.length, 1))}
              </p>
            </div>
            <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
              <div className="flex items-center gap-2 mb-2">
                <Target className="w-5 h-5 text-blue-600" />
                <span className="text-sm text-slate-500">Avg Efficiency</span>
              </div>
              <p className="text-2xl font-bold text-slate-900">
                {(brands.reduce((sum, b) => sum + b.bayesian_outputs.efficiency_mean, 0) / Math.max(brands.length, 1)).toFixed(2)}
              </p>
            </div>
            <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
              <div className="flex items-center gap-2 mb-2">
                <ArrowUpRight className="w-5 h-5 text-emerald-600" />
                <span className="text-sm text-slate-500">Avg Lift vs Prior</span>
              </div>
              <p className="text-2xl font-bold text-emerald-600">
                +{(brands.reduce((sum, b) => sum + b.bayesian_outputs.lift_vs_prior_period, 0) / Math.max(brands.length, 1)).toFixed(1)}%
              </p>
            </div>
            <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
              <div className="flex items-center gap-2 mb-2">
                <Percent className="w-5 h-5 text-purple-600" />
                <span className="text-sm text-slate-500">Avg P(Positive Lift)</span>
              </div>
              <p className="text-2xl font-bold text-purple-600">
                {formatPercent(brands.reduce((sum, b) => sum + b.bayesian_outputs.prob_positive_lift, 0) / Math.max(brands.length, 1))}
              </p>
            </div>
          </div>

          {/* Brand Posterior Table */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="p-4 border-b border-slate-200">
              <h3 className="font-semibold text-slate-900">Brand Bayesian Posteriors</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">Brand</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">Category</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-slate-500 uppercase">Incr. Sales (Mean)</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-slate-500 uppercase">90% CI</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-slate-500 uppercase">Efficiency</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-slate-500 uppercase">Index</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-slate-500 uppercase">Lift vs Prior</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-slate-500 uppercase">P(Lift &gt; 0)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {brands.map((brand) => (
                    <tr key={brand.brand_id} className="hover:bg-slate-50">
                      <td className="px-4 py-3 font-medium text-slate-900">{brand.brand_name}</td>
                      <td className="px-4 py-3 text-slate-600">{brand.category}</td>
                      <td className="px-4 py-3 text-right font-mono text-slate-900">
                        {formatCurrency(brand.bayesian_outputs.incremental_sales.mean)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-xs text-slate-500">
                        [{formatCurrency(brand.bayesian_outputs.incremental_sales.ci[0])}, {formatCurrency(brand.bayesian_outputs.incremental_sales.ci[1])}]
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className={`font-mono ${brand.bayesian_outputs.efficiency_mean >= 1 ? 'text-green-600' : 'text-amber-600'}`}>
                          {brand.bayesian_outputs.efficiency_mean.toFixed(2)}
                        </span>
                        <span className="text-xs text-slate-400 ml-1">±{brand.bayesian_outputs.efficiency_std.toFixed(2)}</span>
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-slate-700">
                        {brand.bayesian_outputs.index_mean.toFixed(0)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className={`font-mono ${brand.bayesian_outputs.lift_vs_prior_period >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                          {brand.bayesian_outputs.lift_vs_prior_period >= 0 ? '+' : ''}{brand.bayesian_outputs.lift_vs_prior_period.toFixed(1)}%
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <div className="w-16 h-2 bg-slate-100 rounded-full overflow-hidden">
                            <div 
                              className={`h-full rounded-full ${
                                brand.bayesian_outputs.prob_positive_lift > 0.9 ? 'bg-green-500' :
                                brand.bayesian_outputs.prob_positive_lift > 0.7 ? 'bg-amber-500' : 'bg-red-500'
                              }`}
                              style={{ width: `${brand.bayesian_outputs.prob_positive_lift * 100}%` }}
                            />
                          </div>
                          <span className="font-mono text-sm">{formatPercent(brand.bayesian_outputs.prob_positive_lift)}</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Brand Incremental Sales Chart */}
          <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
            <h3 className="font-semibold text-slate-900 mb-4">Incremental Sales Posteriors by Brand</h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={brands} layout="vertical" margin={{ left: 100 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis type="number" tickFormatter={(v) => formatCurrency(v)} />
                  <YAxis type="category" dataKey="brand_name" tick={{ fontSize: 12 }} width={90} />
                  <Tooltip formatter={(value) => formatCurrency(Number(value) || 0)} />
                  <Bar dataKey="bayesian_outputs.incremental_sales.mean" fill="#3b82f6" name="Mean" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* RMNs Tab */}
      {activeTab === 'rmns' && (
        <div className="space-y-6">
          {/* RMN Posterior Cards */}
          <div className="grid grid-cols-3 gap-4">
            {rmns.map((rmn) => (
              <div 
                key={rmn.rmn_id}
                className={`bg-white p-5 rounded-xl border shadow-sm cursor-pointer transition-all ${
                  selectedRmn === rmn.rmn_id ? 'border-blue-500 ring-2 ring-blue-100' : 'border-slate-200 hover:border-blue-300'
                }`}
                onClick={() => setSelectedRmn(rmn.rmn_id)}
              >
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-semibold text-slate-900">{rmn.rmn_name}</h3>
                  <span className={`text-xs px-2 py-1 rounded-full ${
                    rmn.bayesian_outputs.prob_best_overall > 0.25 ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-600'
                  }`}>
                    P(Best): {formatPercent(rmn.bayesian_outputs.prob_best_overall)}
                  </span>
                </div>
                
                <div className="space-y-3">
                  <div>
                    <p className="text-xs text-slate-500 mb-1">Incremental Sales Posterior</p>
                    <p className="text-xl font-bold text-slate-900">
                      {formatCurrency(rmn.bayesian_outputs.incremental_sales.mean)}
                    </p>
                    <p className="text-xs text-slate-400">
                      CI: [{formatCurrency(rmn.bayesian_outputs.incremental_sales.ci[0])}, {formatCurrency(rmn.bayesian_outputs.incremental_sales.ci[1])}]
                    </p>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <p className="text-slate-500">Efficiency</p>
                      <p className={`font-mono font-medium ${rmn.bayesian_outputs.efficiency_mean >= 1 ? 'text-green-600' : 'text-amber-600'}`}>
                        {rmn.bayesian_outputs.efficiency_mean.toFixed(2)}
                      </p>
                    </div>
                    <div>
                      <p className="text-slate-500">Expected Rank</p>
                      <p className="font-mono font-medium text-slate-700">
                        #{rmn.bayesian_outputs.expected_rank.toFixed(1)}
                      </p>
                    </div>
                  </div>
                  
                  <div>
                    <p className="text-xs text-slate-500 mb-2">Channel Mix</p>
                    <div className="flex gap-1 h-2 rounded-full overflow-hidden">
                      <div className="bg-blue-500" style={{ width: `${rmn.channel_mix.search * 100}%` }} title="Search" />
                      <div className="bg-green-500" style={{ width: `${rmn.channel_mix.display * 100}%` }} title="Display" />
                      <div className="bg-purple-500" style={{ width: `${rmn.channel_mix.video * 100}%` }} title="Video" />
                      <div className="bg-orange-500" style={{ width: `${rmn.channel_mix.email * 100}%` }} title="Email" />
                    </div>
                    <div className="flex justify-between text-xs text-slate-400 mt-1">
                      <span>Search {formatPercent(rmn.channel_mix.search)}</span>
                      <span>Display {formatPercent(rmn.channel_mix.display)}</span>
                      <span>Video {formatPercent(rmn.channel_mix.video)}</span>
                      <span>Email {formatPercent(rmn.channel_mix.email)}</span>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* RMN Ranking Chart */}
          <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
            <h3 className="font-semibold text-slate-900 mb-4">RMN Ranking Posteriors</h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={rmns}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="rmn_name" tick={{ fontSize: 11 }} />
                  <YAxis domain={[0, 1]} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
                  <Tooltip formatter={(value) => formatPercent(Number(value) || 0)} />
                  <Bar dataKey="bayesian_outputs.prob_best_overall" fill="#10b981" name="P(Best Overall)" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* Channels Tab */}
      {activeTab === 'channels' && (
        <div className="space-y-6">
          <div className="flex items-center gap-4 mb-4">
            <label className="text-sm text-slate-600">Select RMN:</label>
            <select
              value={selectedRmn}
              onChange={(e) => setSelectedRmn(e.target.value)}
              className="px-3 py-2 border border-slate-300 rounded-lg text-sm"
            >
              {rmns.map((rmn) => (
                <option key={rmn.rmn_id} value={rmn.rmn_id}>{rmn.rmn_name}</option>
              ))}
            </select>
          </div>

          {/* Channel Cards */}
          <div className="grid grid-cols-2 gap-4">
            {channels.map((channel) => (
              <div key={channel.channel_id} className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-semibold text-slate-900">{channel.channel_name}</h3>
                  <span className="text-xs px-2 py-1 bg-blue-100 text-blue-700 rounded-full">
                    {channel.channel_type.toUpperCase()}
                  </span>
                </div>
                
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-slate-500 mb-1">Incremental Sales</p>
                    <p className="text-lg font-bold text-slate-900">
                      {formatCurrency(channel.bayesian_outputs.incremental_sales.mean)}
                    </p>
                    <p className="text-xs text-slate-400">
                      ±{formatCurrency(channel.bayesian_outputs.incremental_sales.std)}
                    </p>
                  </div>
                  
                  <div>
                    <p className="text-xs text-slate-500 mb-1">Elasticity</p>
                    <p className="text-lg font-bold text-blue-600">
                      {channel.bayesian_outputs.elasticity.mean.toFixed(3)}
                    </p>
                    <p className="text-xs text-slate-400">
                      CI: [{channel.bayesian_outputs.elasticity.ci[0].toFixed(3)}, {channel.bayesian_outputs.elasticity.ci[1].toFixed(3)}]
                    </p>
                  </div>
                  
                  <div>
                    <p className="text-xs text-slate-500 mb-1">Efficiency</p>
                    <p className={`text-lg font-bold ${channel.bayesian_outputs.efficiency_mean >= 1 ? 'text-green-600' : 'text-amber-600'}`}>
                      {channel.bayesian_outputs.efficiency_mean.toFixed(2)}
                    </p>
                    <p className="text-xs text-slate-400">
                      P(&gt;{channel.bayesian_outputs.efficiency_target}): {formatPercent(channel.bayesian_outputs.prob_efficiency_above_target)}
                    </p>
                  </div>
                  
                  <div>
                    <p className="text-xs text-slate-500 mb-1">Contribution %</p>
                    <p className="text-lg font-bold text-purple-600">
                      {formatPercent(channel.bayesian_outputs.contribution_pct_mean)}
                    </p>
                    <p className="text-xs text-slate-400">
                      P(Rank #1): {formatPercent(channel.bayesian_outputs.prob_rank_1_within_rmn)}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Channel Elasticity Chart */}
          <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
            <h3 className="font-semibold text-slate-900 mb-4">Channel Elasticity Posteriors</h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={channels}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="channel_name" tick={{ fontSize: 11 }} />
                  <YAxis domain={[0, 0.4]} />
                  <Tooltip formatter={(value) => (Number(value) || 0).toFixed(3)} />
                  <Bar dataKey="bayesian_outputs.elasticity.mean" fill="#6366f1" name="Elasticity (Mean)" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* Scenarios Tab */}
      {activeTab === 'scenarios' && scenarioComparison && (
        <div className="space-y-6">
          <div className="flex items-center gap-4 mb-4">
            <label className="text-sm text-slate-600">Entity Type:</label>
            <select
              value={selectedEntity.type}
              onChange={(e) => setSelectedEntity({ ...selectedEntity, type: e.target.value })}
              className="px-3 py-2 border border-slate-300 rounded-lg text-sm"
            >
              <option value="brand">Brand</option>
              <option value="rmn">RMN</option>
              <option value="channel">Channel</option>
            </select>
            <label className="text-sm text-slate-600">Entity ID:</label>
            <select
              value={selectedEntity.id}
              onChange={(e) => setSelectedEntity({ ...selectedEntity, id: e.target.value })}
              className="px-3 py-2 border border-slate-300 rounded-lg text-sm"
            >
              {selectedEntity.type === 'brand' && brands.map((b) => (
                <option key={b.brand_id} value={b.brand_id}>{b.brand_name}</option>
              ))}
              {selectedEntity.type === 'rmn' && rmns.map((r) => (
                <option key={r.rmn_id} value={r.rmn_id}>{r.rmn_name}</option>
              ))}
            </select>
          </div>

          {/* Scenario Comparison Cards */}
          <div className="grid grid-cols-3 gap-6">
            {/* Current Scenario */}
            <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-3 h-3 bg-slate-400 rounded-full" />
                <h3 className="font-semibold text-slate-900">Current Scenario</h3>
              </div>
              <div className="space-y-4">
                <div>
                  <p className="text-xs text-slate-500 mb-1">Incremental Sales</p>
                  <p className="text-2xl font-bold text-slate-900">
                    {formatCurrency(scenarioComparison.current_scenario.incremental_sales_posterior.mean)}
                  </p>
                  <p className="text-xs text-slate-400">
                    CI: [{formatCurrency(scenarioComparison.current_scenario.incremental_sales_posterior.ci[0])}, {formatCurrency(scenarioComparison.current_scenario.incremental_sales_posterior.ci[1])}]
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 mb-1">Efficiency</p>
                  <p className="text-xl font-bold text-slate-700">
                    {scenarioComparison.current_scenario.efficiency_posterior.mean.toFixed(2)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 mb-1">Downside Risk (5%)</p>
                  <p className="text-lg font-mono text-red-600">
                    {formatCurrency(scenarioComparison.current_scenario.downside_risk_5pct)}
                  </p>
                </div>
              </div>
            </div>

            {/* Delta/Comparison */}
            <div className="bg-gradient-to-br from-blue-50 to-indigo-50 p-6 rounded-xl border border-blue-200 shadow-sm">
              <div className="flex items-center gap-2 mb-4">
                <GitCompare className="w-5 h-5 text-blue-600" />
                <h3 className="font-semibold text-blue-900">Expected Improvement</h3>
              </div>
              <div className="space-y-4">
                <div>
                  <p className="text-xs text-blue-600 mb-1">Expected Δ Incremental Sales</p>
                  <p className="text-2xl font-bold text-green-600">
                    +{formatCurrency(scenarioComparison.comparison.expected_incremental_sales_delta)}
                  </p>
                  <p className="text-xs text-blue-400">
                    CI: [{formatCurrency(scenarioComparison.comparison.expected_delta_ci[0])}, {formatCurrency(scenarioComparison.comparison.expected_delta_ci[1])}]
                  </p>
                </div>
                <div>
                  <p className="text-xs text-blue-600 mb-1">P(Optimized &gt; Current)</p>
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-3 bg-blue-200 rounded-full overflow-hidden">
                      <div 
                        className="h-full bg-green-500 rounded-full"
                        style={{ width: `${scenarioComparison.comparison.prob_optimized_beats_current * 100}%` }}
                      />
                    </div>
                    <span className="text-lg font-bold text-green-600">
                      {formatPercent(scenarioComparison.comparison.prob_optimized_beats_current)}
                    </span>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <p className="text-blue-600">P(+5%)</p>
                    <p className="font-bold text-slate-700">{formatPercent(scenarioComparison.comparison.prob_optimized_beats_current_by_5pct)}</p>
                  </div>
                  <div>
                    <p className="text-blue-600">P(+10%)</p>
                    <p className="font-bold text-slate-700">{formatPercent(scenarioComparison.comparison.prob_optimized_beats_current_by_10pct)}</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Optimized Scenario */}
            <div className="bg-white p-6 rounded-xl border border-green-200 shadow-sm">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-3 h-3 bg-green-500 rounded-full" />
                <h3 className="font-semibold text-slate-900">Optimized Scenario</h3>
              </div>
              <div className="space-y-4">
                <div>
                  <p className="text-xs text-slate-500 mb-1">Incremental Sales</p>
                  <p className="text-2xl font-bold text-green-600">
                    {formatCurrency(scenarioComparison.optimized_scenario.incremental_sales_posterior.mean)}
                  </p>
                  <p className="text-xs text-slate-400">
                    CI: [{formatCurrency(scenarioComparison.optimized_scenario.incremental_sales_posterior.ci[0])}, {formatCurrency(scenarioComparison.optimized_scenario.incremental_sales_posterior.ci[1])}]
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 mb-1">Efficiency</p>
                  <p className="text-xl font-bold text-green-600">
                    {scenarioComparison.optimized_scenario.efficiency_posterior.mean.toFixed(2)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 mb-1">Downside Risk (5%)</p>
                  <p className="text-lg font-mono text-amber-600">
                    {formatCurrency(scenarioComparison.optimized_scenario.downside_risk_5pct)}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Recommended Allocation */}
          <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
            <h3 className="font-semibold text-slate-900 mb-4">Recommended Channel Allocation</h3>
            <div className="grid grid-cols-4 gap-4">
              {Object.entries(scenarioComparison.recommended_allocation).map(([channel, pct]) => (
                <div key={channel} className="text-center p-4 bg-slate-50 rounded-lg">
                  <p className="text-sm text-slate-600 capitalize mb-2">{channel}</p>
                  <p className="text-2xl font-bold text-blue-600">{formatPercent(pct)}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
