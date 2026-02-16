import { loadStoreTelemetry, loadStoreTelemetryAsync } from './telemetrySimulator.js';
import { computeAllFeatures, computeAssetScore } from './featureCalculator.js';
import { computePeerComparison, rankAssetsInStore, getGlobalBaseline } from './peerComparison.js';
import { evaluateAllOptions, recommendDecision } from './economicEvaluation.js';
import { optimizeCapexPlan, sensitivityAnalysis, getNextBestAssets } from './knapsackOptimizer.js';
import { getCohortKey } from '../data/models.js';
import { processRawTelemetry, computeDataQualityScore } from './semanticNormalization.js';
import { computeEnergyWasteEstimate } from './energyBaseline.js';
import { runFaultDetection } from './faultDetection.js';
import { computeSurvivalAnalysis, computeExpectedFailureCost } from './survivalModeling.js';
import { runEnhancedEconomicEvaluation } from './enhancedLCC.js';

/**
 * Run CapEx analysis using REAL data from external datasets
 * This async version loads real weather data from NOAA ISD
 */
export async function runCapexAnalysisAsync(store, assets, replacementOptionsMap, economicAssumption, utilityRate, budget, objective = 'max_expected_npv', platformData = null) {
  console.log(`[CapEx Engine] Starting analysis with REAL DATA for store: ${store.name}`);
  console.log(`[CapEx Engine] Budget: $${budget.toLocaleString()}`);
  console.log(`[CapEx Engine] Assets to analyze: ${assets.length}`);
  
  console.log('[CapEx Engine] Step 1: Loading telemetry data...');
  const telemetryData = await loadStoreTelemetryAsync(store, assets, 90, platformData);
  
  // Log data source information
  console.log('[CapEx Engine] Data sources:', telemetryData.dataSource);
  if (telemetryData.weatherObservations.length === 0) {
    console.warn('[CapEx Engine] WARNING: No real weather data available. Results may be less accurate.');
  } else {
    console.log(`[CapEx Engine] Loaded ${telemetryData.weatherObservations.length} real weather observations`);
  }
  
  return runCapexAnalysisWithData(store, assets, replacementOptionsMap, economicAssumption, utilityRate, budget, objective, telemetryData);
}

// DEPRECATED: Synchronous version - use runCapexAnalysisAsync for real data
export function runCapexAnalysis(store, assets, replacementOptionsMap, economicAssumption, utilityRate, budget, objective = 'max_expected_npv') {
  console.warn('[DEPRECATED] runCapexAnalysis is synchronous and cannot load real data.');
  console.warn('[DEPRECATED] Use runCapexAnalysisAsync() for real weather data from NOAA.');
  
  console.log(`[CapEx Engine] Starting analysis for store: ${store.name}`);
  console.log(`[CapEx Engine] Budget: $${budget.toLocaleString()}`);
  console.log(`[CapEx Engine] Assets to analyze: ${assets.length}`);
  
  console.log('[CapEx Engine] Step 1: Loading telemetry data (DEPRECATED - no real data)...');
  const telemetryData = loadStoreTelemetry(store, assets, 90);
  
  return runCapexAnalysisWithData(store, assets, replacementOptionsMap, economicAssumption, utilityRate, budget, objective, telemetryData);
}

/**
 * Internal function that runs analysis with provided telemetry data
 */
function runCapexAnalysisWithData(store, assets, replacementOptionsMap, economicAssumption, utilityRate, budget, objective, telemetryData) {
  
  console.log('[CapEx Engine] Step 2: Computing features for each asset...');
  const assetFeatures = {};
  const dataQuality = {};
  assets.forEach(asset => {
    const readings = telemetryData.telemetryByAsset[asset.assetId] || [];
    const workOrders = telemetryData.workOrdersByAsset[asset.assetId] || [];
    assetFeatures[asset.assetId] = computeAllFeatures(
      asset, 
      readings, 
      telemetryData.weatherObservations, 
      workOrders
    );
    dataQuality[asset.assetId] = assetFeatures[asset.assetId].dataQuality;
  });
  
  console.log('[CapEx Engine] Step 3: Computing peer comparisons...');
  const peerComparisons = {};
  assets.forEach(asset => {
    const features = assetFeatures[asset.assetId];
    peerComparisons[asset.assetId] = computePeerComparison(asset, store, features);
  });
  
  console.log('[CapEx Engine] Step 4: Running fault detection...');
  const faultResults = {};
  assets.forEach(asset => {
    const features = assetFeatures[asset.assetId];
    const cohortKey = getCohortKey(asset, store);
    const baseline = getGlobalBaseline(cohortKey);
    faultResults[asset.assetId] = runFaultDetection(features, asset.assetType, baseline);
  });
  
  console.log('[CapEx Engine] Step 5: Computing survival analysis...');
  const survivalResults = {};
  assets.forEach(asset => {
    const features = assetFeatures[asset.assetId];
    const enrichedFeatures = {
      ...features,
      peerComparison: peerComparisons[asset.assetId]?.peerComparison,
      faultDetection: faultResults[asset.assetId]
    };
    survivalResults[asset.assetId] = computeSurvivalAnalysis(asset, enrichedFeatures);
  });
  
  console.log('[CapEx Engine] Step 6: Computing energy waste estimates...');
  const energyWasteResults = {};
  assets.forEach(asset => {
    const features = assetFeatures[asset.assetId];
    const cohortKey = getCohortKey(asset, store);
    const baseline = getGlobalBaseline(cohortKey);
    energyWasteResults[asset.assetId] = computeEnergyWasteEstimate(
      asset, features, telemetryData.weatherObservations, baseline, utilityRate
    );
  });
  
  console.log('[CapEx Engine] Step 7: Scoring assets...');
  const assetScores = {};
  assets.forEach(asset => {
    const features = assetFeatures[asset.assetId];
    const cohortKey = getCohortKey(asset, store);
    const baseline = getGlobalBaseline(cohortKey);
    const baseScore = computeAssetScore(features, baseline);
    
    const survival = survivalResults[asset.assetId];
    const faults = faultResults[asset.assetId];
    const energyWaste = energyWasteResults[asset.assetId];
    
    const enhancedRiskScore = Math.min(100, Math.round(
      survival.riskScore * 0.6 + 
      (faults.impact?.faultBurdenScore || 0) * 0.4
    ));
    
    const enhancedEnergyScore = energyWaste.summary?.wastePercentile || baseScore.energyWasteScore;
    
    const enhancedPriorityScore = Math.round(
      (100 - baseScore.conditionScore) * 0.2 +
      enhancedEnergyScore * 0.25 +
      enhancedRiskScore * 0.35 +
      (features.maintenance?.maintenance_cost_365d || 0) / 100 * 0.2
    );
    
    assetScores[asset.assetId] = {
      ...baseScore,
      riskScore: enhancedRiskScore,
      energyWasteScore: enhancedEnergyScore,
      replacePriorityScore: Math.min(100, enhancedPriorityScore),
      survivalAnalysis: survival,
      faultDetection: faults,
      energyWaste: energyWaste.summary
    };
  });
  
  console.log('[CapEx Engine] Step 8: Evaluating replacement options with enhanced LCC...');
  const optionEvaluations = {};
  assets.forEach(asset => {
    const options = replacementOptionsMap[asset.assetId] || [];
    const features = assetFeatures[asset.assetId];
    const survival = survivalResults[asset.assetId];
    
    optionEvaluations[asset.assetId] = options.map(option => {
      const enhanced = runEnhancedEconomicEvaluation(
        asset, features, option, economicAssumption, utilityRate, survival
      );
      return {
        ...enhanced.summary,
        optionId: option.optionId,
        optionName: option.optionName,
        capex: option.capexInstalledCost,
        monteCarlo: enhanced.monteCarlo,
        keepLCC: enhanced.keepLCC,
        replaceLCC: enhanced.replaceLCC
      };
    }).sort((a, b) => b.npv - a.npv);
  });
  
  console.log('[CapEx Engine] Step 9: Generating recommendations...');
  const recommendations = {};
  assets.forEach(asset => {
    const score = assetScores[asset.assetId];
    const evals = optionEvaluations[asset.assetId];
    const bestOption = evals.length > 0 ? evals[0] : null;
    recommendations[asset.assetId] = recommendDecision(asset, score, bestOption);
  });
  
  const evaluatedAssets = assets.map(asset => ({
    asset,
    features: assetFeatures[asset.assetId],
    dataQuality: dataQuality[asset.assetId],
    score: assetScores[asset.assetId],
    peerComparison: peerComparisons[asset.assetId],
    faultDetection: faultResults[asset.assetId],
    survivalAnalysis: survivalResults[asset.assetId],
    energyWaste: energyWasteResults[asset.assetId],
    optionEvaluations: optionEvaluations[asset.assetId],
    bestOption: optionEvaluations[asset.assetId]?.[0] || null,
    recommendation: recommendations[asset.assetId]
  }));
  
  const rankedAssets = rankAssetsInStore(evaluatedAssets);
  
  console.log('[CapEx Engine] Step 10: Optimizing budget allocation...');
  const optimizedPlan = optimizeCapexPlan(rankedAssets, budget, objective);
  
  console.log('[CapEx Engine] Step 11: Running sensitivity analysis...');
  const sensitivity = sensitivityAnalysis(rankedAssets, budget);
  
  const nextBest = getNextBestAssets(rankedAssets, optimizedPlan, 3);
  
  console.log('[CapEx Engine] Analysis complete!');
  
  return {
    store,
    budget,
    objective,
    asOfDate: new Date().toISOString(),
    telemetryData,
    dataSource: telemetryData.dataSource || { weather: 'unknown', telemetry: 'unknown' },
    evaluatedAssets: rankedAssets,
    optimizedPlan,
    sensitivity,
    nextBestAssets: nextBest,
    summary: generatePlanSummary(optimizedPlan, rankedAssets, store)
  };
}

function generatePlanSummary(optimizedPlan, evaluatedAssets, store) {
  const selectedItems = optimizedPlan.items.filter(i => i.planItem.isInBudget);
  const deferredItems = optimizedPlan.items.filter(i => !i.planItem.isInBudget && i.recommendation.decision === 'REPLACE');
  
  const totalAnnualSavings = selectedItems.reduce((sum, item) => {
    return sum + (item.bestOption?.avgAnnualSavings || 0);
  }, 0);
  
  const avgPayback = selectedItems.length > 0 
    ? selectedItems.reduce((sum, item) => sum + (item.bestOption?.simplePaybackYears || 0), 0) / selectedItems.length
    : 0;
  
  const riskReduction = selectedItems.reduce((sum, item) => {
    const baseRisk = item.score.riskScore;
    const newRisk = 20;
    return sum + (baseRisk - newRisk);
  }, 0);
  
  const byAssetType = {};
  selectedItems.forEach(item => {
    const type = item.asset.assetType;
    if (!byAssetType[type]) {
      byAssetType[type] = { count: 0, totalCost: 0, totalNpv: 0 };
    }
    byAssetType[type].count++;
    byAssetType[type].totalCost += item.planItem.capexCost;
    byAssetType[type].totalNpv += item.bestOption?.npv || 0;
  });
  
  return {
    storeName: store.name,
    storeId: store.storeId,
    budget: optimizedPlan.summary.budget,
    totalCapexSelected: optimizedPlan.summary.totalSelectedCost,
    totalExpectedNpv: optimizedPlan.summary.totalExpectedNpv,
    remainingBudget: optimizedPlan.summary.remainingBudget,
    budgetUtilization: optimizedPlan.summary.utilizationPct,
    assetsAnalyzed: evaluatedAssets.length,
    assetsSelectedForReplacement: optimizedPlan.summary.assetsSelected,
    assetsDeferred: optimizedPlan.summary.assetsDeferred,
    totalAnnualSavings,
    avgSimplePaybackYears: Math.round(avgPayback * 10) / 10,
    estimatedRiskReduction: riskReduction,
    breakdownByAssetType: byAssetType,
    topDrivers: getTopDrivers(selectedItems),
    deferredOpportunities: deferredItems.slice(0, 5).map(item => ({
      assetId: item.asset.assetId,
      assetType: item.asset.assetType,
      capexRequired: item.bestOption?.capex || 0,
      npvIfFunded: item.bestOption?.npv || 0,
      priorityScore: item.score.replacePriorityScore
    }))
  };
}

function getTopDrivers(selectedItems) {
  const drivers = {};
  
  selectedItems.forEach(item => {
    const explainDrivers = item.score.explainTopDrivers || [];
    explainDrivers.forEach(driver => {
      if (!drivers[driver]) drivers[driver] = 0;
      drivers[driver]++;
    });
  });
  
  return Object.entries(drivers)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([driver, count]) => ({ driver, count }));
}

export function exportPlanToJson(analysisResult) {
  return JSON.stringify({
    metadata: {
      generatedAt: new Date().toISOString(),
      store: analysisResult.store.name,
      budget: analysisResult.budget
    },
    summary: analysisResult.summary,
    assets: analysisResult.optimizedPlan.items.map(item => ({
      assetId: item.asset.assetId,
      assetType: item.asset.assetType,
      manufacturer: item.asset.manufacturer,
      model: item.asset.model,
      ageYears: item.asset.ageYears,
      decision: item.planItem.decision,
      capexCost: item.planItem.capexCost,
      npv: item.planItem.npvP50,
      priorityScore: item.score.replacePriorityScore,
      peerPercentile: item.planItem.peerPercentile,
      isInBudget: item.planItem.isInBudget,
      reason: item.planItem.reason,
      topDrivers: item.score.explainTopDrivers
    })),
    sensitivity: analysisResult.sensitivity
  }, null, 2);
}
