import React, { useState, useCallback, useMemo, useRef } from 'react';
import { 
  Building2, DollarSign, TrendingUp, AlertTriangle, Download, 
  RefreshCw, Settings, BarChart3, Target, Zap, Wrench, Shield,
  ChevronDown, ChevronUp, Check, X, Clock, Eye, Upload, FileJson, Database, Loader2
} from 'lucide-react';
import { generateCompleteStoreData, generateSampleAssets, generateReplacementOptions, generateSampleUtilityRate, generateSampleEconomicAssumptions } from './data/sampleData.js';
import { useAppContext } from '../context/AppContext';
import { runCapexAnalysis, runCapexAnalysisAsync } from './engine/capexEngine.js';
import { getDataSourceStatus } from './data/externalDataLoader.js';
import { exportToExcel, exportToCsv } from './utils/exportUtils.js';
import { DECISION_TYPES, CLIMATE_ZONES } from './data/models.js';
import { runAllTests, testExternalDataIntegration } from './tests/testPipeline.js';

const formatCurrency = (value) => {
  return new Intl.NumberFormat('en-US', { 
    style: 'currency', 
    currency: 'USD', 
    maximumFractionDigits: 0 
  }).format(value);
};

const formatPercent = (value) => `${Math.round(value)}%`;

const ScoreBadge = ({ score, label }) => {
  const getScoreClass = (s) => {
    if (s >= 80) return 'bg-red-100 text-red-800 border-red-200';
    if (s >= 60) return 'bg-orange-100 text-orange-800 border-orange-200';
    if (s >= 40) return 'bg-yellow-100 text-yellow-800 border-yellow-200';
    if (s >= 20) return 'bg-blue-100 text-blue-800 border-blue-200';
    return 'bg-green-100 text-green-800 border-green-200';
  };
  
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${getScoreClass(score)}`}>
      {label ? `${label}: ` : ''}{score}
    </span>
  );
};

const DecisionBadge = ({ decision, isInBudget }) => {
  const config = {
    [DECISION_TYPES.REPLACE]: isInBudget 
      ? { bg: 'bg-green-100', text: 'text-green-800', border: 'border-green-200', icon: Check }
      : { bg: 'bg-yellow-100', text: 'text-yellow-800', border: 'border-yellow-200', icon: Clock },
    [DECISION_TYPES.DEFER]: { bg: 'bg-gray-100', text: 'text-gray-800', border: 'border-gray-200', icon: Clock },
    [DECISION_TYPES.INSPECT]: { bg: 'bg-blue-100', text: 'text-blue-800', border: 'border-blue-200', icon: Eye },
    [DECISION_TYPES.REPAIR]: { bg: 'bg-purple-100', text: 'text-purple-800', border: 'border-purple-200', icon: Wrench }
  };
  
  const c = config[decision] || config[DECISION_TYPES.DEFER];
  const Icon = c.icon;
  const displayText = decision === DECISION_TYPES.REPLACE && !isInBudget ? 'DEFERRED' : decision;
  
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium border ${c.bg} ${c.text} ${c.border}`}>
      <Icon size={12} />
      {displayText}
    </span>
  );
};

const ProgressBar = ({ value, max, color = 'blue' }) => {
  const pct = Math.min(100, (value / max) * 100);
  const colorClasses = {
    blue: 'bg-blue-500',
    green: 'bg-green-500',
    yellow: 'bg-yellow-500',
    red: 'bg-red-500'
  };
  
  return (
    <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
      <div 
        className={`h-full rounded-full transition-all duration-500 ${colorClasses[color]}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
};

const StatCard = ({ icon: Icon, title, value, subtitle, trend, color = 'blue' }) => {
  const colorClasses = {
    blue: 'bg-blue-50 text-blue-600',
    green: 'bg-green-50 text-green-600',
    yellow: 'bg-yellow-50 text-yellow-600',
    red: 'bg-red-50 text-red-600',
    purple: 'bg-purple-50 text-purple-600'
  };
  
  return (
    <div className="card">
      <div className="flex items-start justify-between">
        <div className={`p-2 rounded-lg ${colorClasses[color]}`}>
          <Icon size={20} />
        </div>
        {trend && (
          <span className={`text-xs font-medium ${trend > 0 ? 'text-green-600' : 'text-red-600'}`}>
            {trend > 0 ? '+' : ''}{trend}%
          </span>
        )}
      </div>
      <div className="mt-3">
        <p className="text-2xl font-bold text-gray-900">{value}</p>
        <p className="text-sm text-gray-500">{title}</p>
        {subtitle && <p className="text-xs text-gray-400 mt-1">{subtitle}</p>}
      </div>
    </div>
  );
};

const RiskCategoryBadge = ({ category }) => {
  const config = {
    critical: 'bg-red-100 text-red-800 border-red-200',
    high: 'bg-orange-100 text-orange-800 border-orange-200',
    elevated: 'bg-yellow-100 text-yellow-800 border-yellow-200',
    moderate: 'bg-blue-100 text-blue-800 border-blue-200',
    low: 'bg-green-100 text-green-800 border-green-200'
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${config[category] || config.moderate}`}>
      {category?.toUpperCase()}
    </span>
  );
};

const AssetRow = ({ item, onExpand, isExpanded }) => {
  const { asset, score, peerComparison, bestOption, planItem, recommendation, faultDetection, survivalAnalysis } = item;
  
  return (
    <>
      <tr 
        className={`border-b border-gray-100 hover:bg-gray-50 cursor-pointer transition-colors ${
          planItem.isInBudget ? 'bg-green-50/30' : ''
        }`}
        onClick={() => onExpand(asset.assetId)}
      >
        <td className="px-4 py-3">
          <div className="flex items-center gap-2">
            {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            <div>
              <p className="font-medium text-gray-900">{asset.assetType}</p>
              <p className="text-xs text-gray-500">{asset.assetId}</p>
            </div>
          </div>
        </td>
        <td className="px-4 py-3">
          <p className="text-sm text-gray-900">{asset.manufacturer}</p>
          <p className="text-xs text-gray-500">{asset.model}</p>
        </td>
        <td className="px-4 py-3 text-center">
          <span className={`font-medium ${asset.ageYears > 12 ? 'text-red-600' : asset.ageYears > 7 ? 'text-yellow-600' : 'text-gray-900'}`}>
            {asset.ageYears}y
          </span>
        </td>
        <td className="px-4 py-3 text-center">
          <ScoreBadge score={score.replacePriorityScore} />
        </td>
        <td className="px-4 py-3 text-center">
          <span className="text-sm text-gray-600">P{peerComparison?.peerComparison?.overall?.percentile || 50}</span>
        </td>
        <td className="px-4 py-3">
          <DecisionBadge decision={planItem.decision} isInBudget={planItem.isInBudget} />
        </td>
        <td className="px-4 py-3 text-right font-medium">
          {planItem.isInBudget ? formatCurrency(planItem.capexCost) : '-'}
        </td>
        <td className="px-4 py-3 text-right">
          <span className={bestOption?.npv > 0 ? 'text-green-600' : 'text-red-600'}>
            {bestOption ? formatCurrency(bestOption.npv) : '-'}
          </span>
        </td>
      </tr>
      {isExpanded && (
        <tr className="bg-gray-50">
          <td colSpan={8} className="px-4 py-4">
            <div className="grid grid-cols-5 gap-4">
              <div>
                <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Scores</h4>
                <div className="space-y-1">
                  <div className="flex justify-between text-sm">
                    <span>Condition</span>
                    <ScoreBadge score={score.conditionScore} />
                  </div>
                  <div className="flex justify-between text-sm">
                    <span>Risk</span>
                    <ScoreBadge score={score.riskScore} />
                  </div>
                  <div className="flex justify-between text-sm">
                    <span>Energy Waste</span>
                    <ScoreBadge score={score.energyWasteScore} />
                  </div>
                </div>
              </div>
              <div>
                <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Survival Analysis</h4>
                <div className="space-y-1 text-sm">
                  {survivalAnalysis ? (
                    <>
                      <div className="flex justify-between">
                        <span>Risk Category</span>
                        <RiskCategoryBadge category={survivalAnalysis.riskCategory} />
                      </div>
                      <div className="flex justify-between">
                        <span>P(Fail 1yr)</span>
                        <span className={survivalAnalysis.failureProbabilities?.p1y > 0.2 ? 'text-red-600 font-medium' : ''}>
                          {Math.round((survivalAnalysis.failureProbabilities?.p1y || 0) * 100)}%
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span>Expected RUL</span>
                        <span>{survivalAnalysis.expectedRemainingLifeYears}y</span>
                      </div>
                    </>
                  ) : (
                    <p className="text-xs text-gray-400">Not available</p>
                  )}
                </div>
              </div>
              <div>
                <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Fault Detection</h4>
                <div className="space-y-1 text-sm">
                  {faultDetection ? (
                    <>
                      <div className="flex justify-between">
                        <span>Faults</span>
                        <span className={faultDetection.summary?.totalFaults > 0 ? 'text-orange-600 font-medium' : 'text-green-600'}>
                          {faultDetection.summary?.totalFaults || 0}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span>Health Score</span>
                        <span>{faultDetection.summary?.overallHealthScore || 100}</span>
                      </div>
                      {faultDetection.summary?.primaryConcerns?.length > 0 && (
                        <p className="text-xs text-orange-600 mt-1">{faultDetection.summary.primaryConcerns[0]}</p>
                      )}
                    </>
                  ) : (
                    <p className="text-xs text-gray-400">Not available</p>
                  )}
                </div>
              </div>
              <div>
                <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Best Option (LCC)</h4>
                {bestOption ? (
                  <div className="space-y-1 text-sm">
                    <p className="font-medium">{bestOption.optionName}</p>
                    <p>Payback: {bestOption.simplePayback || bestOption.simplePaybackYears}y</p>
                    <p>EAC Savings: {formatCurrency(bestOption.eacSavings || 0)}</p>
                    {bestOption.pNpvPositive && (
                      <p className="text-xs">P(NPV+): {Math.round(bestOption.pNpvPositive * 100)}%</p>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-gray-500">No options evaluated</p>
                )}
              </div>
              <div>
                <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Key Drivers</h4>
                <ul className="space-y-1">
                  {(score.explainTopDrivers || []).slice(0, 3).map((driver, i) => (
                    <li key={i} className="text-xs text-gray-600 flex items-start gap-1">
                      <AlertTriangle size={12} className="text-yellow-500 mt-0.5 flex-shrink-0" />
                      {driver}
                    </li>
                  ))}
                  {(!score.explainTopDrivers || score.explainTopDrivers.length === 0) && (
                    <li className="text-xs text-gray-400">No significant issues detected</li>
                  )}
                </ul>
              </div>
            </div>
            {survivalAnalysis?.interpretation && (
              <div className="mt-3 pt-3 border-t border-gray-200">
                <p className="text-xs text-gray-500">
                  <span className="font-medium">Survival Analysis:</span> {survivalAnalysis.interpretation}
                </p>
              </div>
            )}
            <div className="mt-2 pt-2 border-t border-gray-200">
              <p className="text-sm text-gray-600">
                <span className="font-medium">Recommendation:</span> {planItem.reason || recommendation.reason}
              </p>
            </div>
          </td>
        </tr>
      )}
    </>
  );
};

// Build CapEx store data from platform availableSites so the dropdown matches every other page
function buildStoreDataFromSites(sites) {
  const climateZones = ['5A', '4A', '3A', '2A', '5B'];
  const storeTypes = ['Grocery', 'Big Box', 'Warehouse', 'Grocery', 'Grocery'];
  const stores = sites.map((site, i) => ({
    storeId: site.id,
    name: site.name || site.id,
    address: site.address || '',
    lat: 41.88,
    lon: -87.63,
    region: 'Midwest',
    climateZone: climateZones[i % climateZones.length],
    areaSqft: 50000,
    storeType: storeTypes[i % storeTypes.length],
    utilityRateId: `rate-${site.id}`,
  }));

  const allAssets = [];
  const allOptions = [];
  const utilityRates = [];
  const economicAssumptions = [];

  stores.forEach(store => {
    const assets = generateSampleAssets(store.storeId, store.storeType);
    allAssets.push(...assets);
    assets.forEach(asset => {
      allOptions.push(...generateReplacementOptions(asset));
    });
    utilityRates.push(generateSampleUtilityRate(store.storeId, store.climateZone));
    economicAssumptions.push(generateSampleEconomicAssumptions(store.storeId));
  });

  return { stores, assets: allAssets, replacementOptions: allOptions, utilityRates, economicAssumptions };
}

function App() {
  const { availableSites } = useAppContext();

  // Immediately initialize with sample data so calculator is always visible
  const [initialData] = useState(() => generateCompleteStoreData(5));
  const [sampleData, setSampleData] = useState(initialData);
  const [selectedStoreId, setSelectedStoreId] = useState(initialData.stores[0].storeId);
  const [budget, setBudget] = useState(200000);
  const [objective, setObjective] = useState('max_expected_npv');
  const [analysisResult, setAnalysisResult] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [expandedAssets, setExpandedAssets] = useState(new Set());
  const [sortConfig, setSortConfig] = useState({ key: 'replacePriorityScore', direction: 'desc' });
  const [filterDecision, setFilterDecision] = useState('all');
  const [testResults, setTestResults] = useState(null);
  const [showTestPanel, setShowTestPanel] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [dataSourceStatus, setDataSourceStatus] = useState(null);
  const [platformLoading, setPlatformLoading] = useState(false);
  const fileInputRef = useRef(null);

  // Re-seed store data when platform availableSites change (so dropdown matches other pages)
  React.useEffect(() => {
    if (availableSites && availableSites.length > 0) {
      const data = buildStoreDataFromSites(availableSites);
      setSampleData(data);
      setSelectedStoreId(prev => {
        // Keep current selection if it's still valid, otherwise pick first
        if (data.stores.some(s => s.storeId === prev)) return prev;
        return data.stores[0].storeId;
      });
      setAnalysisResult(null);
    }
  }, [availableSites]);

  // Fetch data source status on mount
  React.useEffect(() => {
    getDataSourceStatus().then(setDataSourceStatus).catch(() => {});
  }, []);
  
  const loadSampleData = useCallback(() => {
    const data = generateCompleteStoreData(5);
    setSampleData(data);
    setSelectedStoreId(data.stores[0].storeId);
    setAnalysisResult(null);
  }, []);

  const loadFromPlatform = useCallback(async () => {
    setPlatformLoading(true);
    setUploadError(null);
    try {
      const res = await fetch('/api/v1/capex/platform-data?site_id=default');
      if (!res.ok) throw new Error(`API error: ${res.status}`);
      const json = await res.json();

      // Normalize into the same shape handleFileUpload produces
      const normalizedData = {
        stores: json.stores || [],
        assets: json.assets || [],
        telemetry: json.telemetry || {},
        maintenanceHistory: json.maintenanceHistory || {},
        utilityRates: json.utilityRates || [],
        economicAssumptions: json.economicAssumptions || [],
        replacementOptions: json.replacementOptions || [],
        dataSource: json.dataSource || {},
      };

      // Ensure each asset has storeId linkage
      const defaultStoreId = normalizedData.stores[0]?.storeId || 'default';
      normalizedData.assets = normalizedData.assets.map((asset, idx) => ({
        ...asset,
        assetId: asset.assetId || asset.asset_id || `asset-${idx + 1}`,
        storeId: asset.storeId || asset.store_id || defaultStoreId,
      }));

      setSampleData(normalizedData);
      setSelectedStoreId(defaultStoreId);
      setBudget(json.budget?.annualCapexBudget || 200000);
      setAnalysisResult(null);

      console.log('[CapEx] Loaded platform data:', {
        assets: normalizedData.assets.length,
        telemetryAssets: Object.keys(normalizedData.telemetry).length,
        woAssets: Object.keys(normalizedData.maintenanceHistory).length,
      });
    } catch (err) {
      console.warn('[CapEx] Platform load failed, falling back to sample data:', err.message);
      // Auto-load sample data so the calculator is always visible
      const data = generateCompleteStoreData(5);
      setSampleData(data);
      setSelectedStoreId(data.stores[0].storeId);
      setAnalysisResult(null);
    } finally {
      setPlatformLoading(false);
    }
  }, []);
  
  const executeTests = useCallback(() => {
    setShowTestPanel(true);
    setTestResults(null);
    setTimeout(() => {
      const results = runAllTests();
      const externalResults = testExternalDataIntegration();
      setTestResults({ ...results, externalData: externalResults });
    }, 100);
  }, []);
  
  const handleFileUpload = useCallback((event) => {
    const file = event.target.files[0];
    if (!file) return;
    
    setUploadError(null);
    
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const json = JSON.parse(e.target.result);
        
        // Validate required fields
        if (!json.store && !json.stores) {
          throw new Error('JSON must contain "store" or "stores" field');
        }
        if (!json.assets || !Array.isArray(json.assets)) {
          throw new Error('JSON must contain "assets" array');
        }
        
        // Normalize to expected format
        const normalizedData = {
          stores: json.stores || [json.store],
          assets: json.assets,
          telemetry: json.telemetry || {},
          maintenanceHistory: json.maintenanceHistory || {},
          utilityRates: json.utilityRates ? [json.utilityRates] : [],
          economicAssumptions: json.economicAssumptions ? 
            [{ storeId: (json.store || json.stores[0]).storeId, ...json.economicAssumptions }] : 
            [{ storeId: (json.store || json.stores[0]).storeId, discountRate: 0.08, analysisHorizon: 10 }],
          replacementOptions: json.replacementOptions || []
        };
        
        // Ensure each store has valid storeId
        normalizedData.stores = normalizedData.stores.map((store, idx) => ({
          ...store,
          storeId: store.storeId || `store-${idx + 1}`
        }));
        
        // Ensure each asset has storeId linkage
        const defaultStoreId = normalizedData.stores[0].storeId;
        normalizedData.assets = normalizedData.assets.map((asset, idx) => ({
          ...asset,
          assetId: asset.assetId || `asset-${idx + 1}`,
          storeId: asset.storeId || defaultStoreId
        }));
        
        setSampleData(normalizedData);
        setSelectedStoreId(normalizedData.stores[0].storeId);
        setBudget(json.budget?.annualCapexBudget || 100000);
        setAnalysisResult(null);
        
        console.log('Loaded JSON data:', normalizedData);
      } catch (err) {
        console.error('JSON parse error:', err);
        setUploadError(err.message);
      }
    };
    reader.onerror = () => {
      setUploadError('Failed to read file');
    };
    reader.readAsText(file);
    
    // Reset file input
    event.target.value = '';
  }, []);
  
  const runAnalysis = useCallback(async () => {
    if (!sampleData || !selectedStoreId) return;
    
    setIsLoading(true);
    
    try {
      const store = sampleData.stores.find(s => s.storeId === selectedStoreId);
      const storeAssets = sampleData.assets.filter(a => a.storeId === selectedStoreId);
      const economicAssumption = sampleData.economicAssumptions.find(e => e.storeId === selectedStoreId);
      const utilityRate = sampleData.utilityRates.find(r => r.utilityRateId === `rate-${selectedStoreId}`);
      
      const replacementOptionsMap = {};
      storeAssets.forEach(asset => {
        // Use pre-loaded replacement options from platform if available
        // Options are keyed by optionId prefix matching the assetId
        const preloaded = (sampleData.replacementOptions || []).filter(
          opt => opt.optionId && opt.optionId.startsWith(asset.assetId + '-opt-')
        );
        replacementOptionsMap[asset.assetId] = preloaded.length > 0
          ? preloaded
          : generateReplacementOptions(asset);
      });
      
      // Pass platform data (telemetry + work orders) if loaded from backend
      const platformData = (sampleData.dataSource?.telemetry === 'platform_db' || sampleData.dataSource?.workOrders === 'platform_db')
        ? { telemetry: sampleData.telemetry, maintenanceHistory: sampleData.maintenanceHistory }
        : null;

      const result = await runCapexAnalysisAsync(
        store, storeAssets, replacementOptionsMap, 
        economicAssumption, utilityRate, budget, objective, platformData
      );
      
      setAnalysisResult(result);
    } catch (error) {
      console.error('Analysis error:', error);
    } finally {
      setIsLoading(false);
    }
  }, [sampleData, selectedStoreId, budget, objective]);
  
  const toggleAssetExpanded = useCallback((assetId) => {
    setExpandedAssets(prev => {
      const next = new Set(prev);
      if (next.has(assetId)) next.delete(assetId);
      else next.add(assetId);
      return next;
    });
  }, []);
  
  const sortedAndFilteredAssets = useMemo(() => {
    if (!analysisResult) return [];
    
    let items = [...analysisResult.optimizedPlan.items];
    
    if (filterDecision !== 'all') {
      if (filterDecision === 'in_budget') {
        items = items.filter(i => i.planItem.isInBudget);
      } else {
        items = items.filter(i => i.planItem.decision === filterDecision);
      }
    }
    
    items.sort((a, b) => {
      let aVal, bVal;
      switch (sortConfig.key) {
        case 'replacePriorityScore':
          aVal = a.score.replacePriorityScore;
          bVal = b.score.replacePriorityScore;
          break;
        case 'age':
          aVal = a.asset.ageYears;
          bVal = b.asset.ageYears;
          break;
        case 'npv':
          aVal = a.bestOption?.npv || -Infinity;
          bVal = b.bestOption?.npv || -Infinity;
          break;
        case 'capex':
          aVal = a.planItem.capexCost || 0;
          bVal = b.planItem.capexCost || 0;
          break;
        default:
          return 0;
      }
      return sortConfig.direction === 'asc' ? aVal - bVal : bVal - aVal;
    });
    
    return items;
  }, [analysisResult, sortConfig, filterDecision]);
  
  const handleExportExcel = () => {
    if (analysisResult) {
      exportToExcel(analysisResult, `capex-plan-${analysisResult.store.name.replace(/\s+/g, '-')}.xlsx`);
    }
  };
  
  const handleExportCsv = () => {
    if (analysisResult) {
      exportToCsv(analysisResult, `capex-assets-${analysisResult.store.name.replace(/\s+/g, '-')}.csv`);
    }
  };
  
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="bg-primary-600 text-white p-2 rounded-lg">
                <Target size={24} />
              </div>
              <div>
                <h1 className="text-xl font-bold text-gray-900">CapEx Generator</h1>
                <p className="text-sm text-gray-500">Capital Expenditure Planning & Analysis</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              {analysisResult && (
                <>
                  <button onClick={handleExportCsv} className="btn-secondary flex items-center gap-2">
                    <Download size={16} />
                    CSV
                  </button>
                  <button onClick={handleExportExcel} className="btn-primary flex items-center gap-2">
                    <Download size={16} />
                    Excel
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      </header>
      
      <main className="max-w-7xl mx-auto px-4 py-6">
          <>
            <div className="card mb-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Analysis Configuration</h2>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Store</label>
                  <select 
                    className="select"
                    value={selectedStoreId || ''}
                    onChange={(e) => { setSelectedStoreId(e.target.value); setAnalysisResult(null); }}
                  >
                    {sampleData.stores.map(store => (
                      <option key={store.storeId} value={store.storeId}>
                        {store.name} ({CLIMATE_ZONES[store.climateZone]})
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">CapEx Budget</label>
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">$</span>
                    <input 
                      type="number" 
                      className="input pl-7"
                      value={budget}
                      onChange={(e) => setBudget(Number(e.target.value))}
                      step={10000}
                      min={10000}
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Optimization Objective</label>
                  <select className="select" value={objective} onChange={(e) => setObjective(e.target.value)}>
                    <option value="max_expected_npv">Maximize Expected NPV</option>
                    <option value="risk_reduction">Maximize Risk Reduction</option>
                    <option value="blended">Blended (NPV + Risk)</option>
                  </select>
                </div>
                <div className="flex items-end">
                  <button 
                    onClick={runAnalysis} 
                    className="btn-primary w-full flex items-center justify-center gap-2"
                    disabled={isLoading}
                  >
                    {isLoading ? (
                      <RefreshCw size={16} className="animate-spin" />
                    ) : (
                      <Zap size={16} />
                    )}
                    {isLoading ? 'Analyzing...' : 'Run Analysis'}
                  </button>
                </div>
              </div>
            </div>
            
            {analysisResult && (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
                  <StatCard 
                    icon={DollarSign}
                    title="Budget Utilized"
                    value={formatCurrency(analysisResult.summary.totalCapexSelected)}
                    subtitle={`${analysisResult.summary.budgetUtilization}% of ${formatCurrency(budget)}`}
                    color="blue"
                  />
                  <StatCard 
                    icon={TrendingUp}
                    title="Expected NPV"
                    value={formatCurrency(analysisResult.summary.totalExpectedNpv)}
                    subtitle={`${formatCurrency(analysisResult.summary.totalAnnualSavings)}/year savings`}
                    color="green"
                  />
                  <StatCard 
                    icon={Wrench}
                    title="Assets Selected"
                    value={analysisResult.summary.assetsSelectedForReplacement}
                    subtitle={`of ${analysisResult.summary.assetsAnalyzed} analyzed`}
                    color="purple"
                  />
                  <StatCard 
                    icon={Clock}
                    title="Avg Payback"
                    value={`${analysisResult.summary.avgSimplePaybackYears}y`}
                    subtitle="Simple payback period"
                    color="yellow"
                  />
                  <StatCard 
                    icon={Shield}
                    title="Deferred"
                    value={analysisResult.summary.assetsDeferred}
                    subtitle="Budget constrained"
                    color="red"
                  />
                </div>
                
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
                  <div className="card lg:col-span-2">
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">Budget Allocation by Asset Type</h3>
                    <div className="space-y-3">
                      {Object.entries(analysisResult.summary.breakdownByAssetType).map(([type, data]) => (
                        <div key={type}>
                          <div className="flex justify-between text-sm mb-1">
                            <span className="font-medium text-gray-700">{type}</span>
                            <span className="text-gray-500">
                              {data.count} assets • {formatCurrency(data.totalCost)}
                            </span>
                          </div>
                          <ProgressBar 
                            value={data.totalCost} 
                            max={analysisResult.summary.totalCapexSelected || 1}
                            color="blue"
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                  
                  <div className="card">
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">Sensitivity Analysis</h3>
                    <div className="space-y-2">
                      {analysisResult.sensitivity.map((s, i) => (
                        <div 
                          key={i} 
                          className={`flex justify-between text-sm p-2 rounded ${
                            s.budgetMultiplier === 1 ? 'bg-primary-50 border border-primary-200' : ''
                          }`}
                        >
                          <span className="text-gray-600">
                            {s.budgetMultiplier === 1 ? '→ ' : ''}{formatCurrency(s.budget)}
                          </span>
                          <span className="font-medium">{s.assetsSelected} assets</span>
                          <span className="text-green-600">{formatCurrency(s.totalNpv)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
                
                {analysisResult.nextBestAssets.length > 0 && (
                  <div className="card mb-6 bg-yellow-50 border-yellow-200">
                    <h3 className="text-lg font-semibold text-yellow-800 mb-3 flex items-center gap-2">
                      <AlertTriangle size={20} />
                      Next Best Opportunities (if budget increased)
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      {analysisResult.nextBestAssets.map((asset, i) => (
                        <div key={i} className="bg-white rounded-lg p-3 border border-yellow-200">
                          <p className="font-medium text-gray-900">{asset.assetType}</p>
                          <p className="text-sm text-gray-500">{asset.assetId}</p>
                          <div className="mt-2 flex justify-between text-sm">
                            <span>Cost: {formatCurrency(asset.additionalCost)}</span>
                            <span className="text-green-600">NPV: {formatCurrency(asset.additionalNpv)}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                
                <div className="card">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-semibold text-gray-900">Asset Details</h3>
                    <div className="flex items-center gap-3">
                      <select 
                        className="select text-sm py-1"
                        value={filterDecision}
                        onChange={(e) => setFilterDecision(e.target.value)}
                      >
                        <option value="all">All Decisions</option>
                        <option value="in_budget">In Budget (Selected)</option>
                        <option value={DECISION_TYPES.REPLACE}>Recommended Replace</option>
                        <option value={DECISION_TYPES.DEFER}>Defer</option>
                        <option value={DECISION_TYPES.INSPECT}>Inspect</option>
                      </select>
                      <select 
                        className="select text-sm py-1"
                        value={`${sortConfig.key}-${sortConfig.direction}`}
                        onChange={(e) => {
                          const [key, direction] = e.target.value.split('-');
                          setSortConfig({ key, direction });
                        }}
                      >
                        <option value="replacePriorityScore-desc">Priority (High to Low)</option>
                        <option value="replacePriorityScore-asc">Priority (Low to High)</option>
                        <option value="npv-desc">NPV (High to Low)</option>
                        <option value="age-desc">Age (Oldest First)</option>
                        <option value="capex-desc">CapEx (High to Low)</option>
                      </select>
                    </div>
                  </div>
                  
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="table-header">
                          <th className="px-4 py-3">Asset</th>
                          <th className="px-4 py-3">Make/Model</th>
                          <th className="px-4 py-3 text-center">Age</th>
                          <th className="px-4 py-3 text-center">Priority</th>
                          <th className="px-4 py-3 text-center">Peer %</th>
                          <th className="px-4 py-3">Decision</th>
                          <th className="px-4 py-3 text-right">CapEx</th>
                          <th className="px-4 py-3 text-right">NPV</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sortedAndFilteredAssets.map(item => (
                          <AssetRow 
                            key={item.asset.assetId}
                            item={item}
                            onExpand={toggleAssetExpanded}
                            isExpanded={expandedAssets.has(item.asset.assetId)}
                          />
                        ))}
                      </tbody>
                    </table>
                  </div>
                  
                  {sortedAndFilteredAssets.length === 0 && (
                    <div className="text-center py-8 text-gray-500">
                      No assets match the current filter criteria
                    </div>
                  )}
                </div>
              </>
            )}
          </>
      </main>
      
      <footer className="bg-white border-t border-gray-200 mt-8">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="text-sm text-gray-500 text-center space-y-1">
            <p>
              CapEx Generator • LCC Analysis based on ASTM E917
            </p>
            <p className="text-xs">
              Data Sources: 
              <span className={dataSourceStatus?.noaaIsd?.available ? 'text-green-600' : 'text-gray-400'}>
                NOAA ISD Weather {dataSourceStatus?.noaaIsd?.available ? '✓' : '○'}
              </span>
              {' • '}
              <span className={dataSourceStatus?.bdg2Metadata?.available ? 'text-green-600' : 'text-gray-400'}>
                BDG2 Benchmarks {dataSourceStatus?.bdg2Metadata?.available ? '✓' : '○'}
              </span>
              {' • '}
              <span className="text-gray-400">
                LBNL FDD (manual download)
              </span>
            </p>
            <p className="text-xs text-gray-400">
              Real data from: NOAA NCEI, BDG2/ASHRAE GEPIII, LBNL, ORNL, NREL
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;
