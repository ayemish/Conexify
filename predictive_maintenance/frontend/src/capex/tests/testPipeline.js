/**
 * Test Pipeline for CapEx Generator
 * Tests the full analysis pipeline with external data sources
 */

import { loadExternalDataForStore, generateLBNLStyleFaultData, generateORNLStyleExperiment, LBNL_FAULT_SCENARIOS } from '../data/externalDataSources.js';
import { getDataSourceStatus, loadNOAAWeather, loadBDG2Metadata } from '../data/externalDataLoader.js';
import { processRawTelemetry, computeDataQualityScore, mapRawPointToCanonical } from '../engine/semanticNormalization.js';
import { runFaultDetection, FAULT_TYPES } from '../engine/faultDetection.js';
import { computeSurvivalAnalysis } from '../engine/survivalModeling.js';
import { computeEnergyWasteEstimate } from '../engine/energyBaseline.js';
import { runEnhancedEconomicEvaluation } from '../engine/enhancedLCC.js';
import { generateCompleteStoreData, generateReplacementOptions } from '../data/sampleData.js';
import { runCapexAnalysis, runCapexAnalysisAsync } from '../engine/capexEngine.js';
import { loadBDG2Benchmark, getBaselineStatus } from '../engine/baselineNormalization.js';

export function runAllTests() {
  console.log('='.repeat(60));
  console.log('CapEx Generator - Full Pipeline Test Suite');
  console.log('='.repeat(60));
  
  const results = {
    passed: 0,
    failed: 0,
    tests: []
  };
  
  runTest(results, 'Semantic Normalization - Point Mapping', testPointMapping);
  runTest(results, 'Semantic Normalization - Data Quality', testDataQuality);
  runTest(results, 'External Data - Data Source Status', testDataSourceStatus);
  runTest(results, 'External Data - Real Weather Loading', testRealWeatherData);
  runTest(results, 'External Data - BDG2 Benchmarks', testBDG2Benchmarks);
  runTest(results, 'External Data - LBNL FDD Format', testLBNLData);
  runTest(results, 'External Data - ORNL Experiments', testORNLData);
  runTest(results, 'Fault Detection - Rule Based', testFaultDetection);
  runTest(results, 'Fault Detection - Anomaly Scoring', testAnomalyDetection);
  runTest(results, 'Survival Analysis - Weibull Model', testSurvivalAnalysis);
  runTest(results, 'Energy Baseline - Peer Residual', testEnergyBaseline);
  runTest(results, 'Enhanced LCC - Monte Carlo NPV', testEnhancedLCC);
  runTest(results, 'Full Pipeline - Store Analysis', testFullPipeline);
  
  console.log('\n' + '='.repeat(60));
  console.log(`Test Results: ${results.passed} passed, ${results.failed} failed`);
  console.log('='.repeat(60));
  
  return results;
}

function runTest(results, name, testFn) {
  console.log(`\n[TEST] ${name}...`);
  try {
    const result = testFn();
    if (result.success) {
      console.log(`  ✓ PASSED: ${result.message}`);
      results.passed++;
      results.tests.push({ name, status: 'passed', message: result.message });
    } else {
      console.log(`  ✗ FAILED: ${result.message}`);
      results.failed++;
      results.tests.push({ name, status: 'failed', message: result.message });
    }
  } catch (error) {
    console.log(`  ✗ ERROR: ${error.message}`);
    results.failed++;
    results.tests.push({ name, status: 'error', message: error.message });
  }
}

function testPointMapping() {
  const testPoints = [
    { name: 'RTU_01_Power_kW', expected: 'power_kw' },
    { name: 'AHU-1-SAT', expected: 'supply_temp_c' },
    { name: 'Compressor_Status', expected: 'compressor_state' },
    { name: 'Suction_Pressure_PSI', expected: 'suction_pressure_psi' },
    { name: 'Zone_Temperature', expected: 'zone_temp_c' }
  ];
  
  let matched = 0;
  testPoints.forEach(tp => {
    const result = mapRawPointToCanonical(tp.name);
    if (result.canonicalMetric === tp.expected) matched++;
  });
  
  return {
    success: matched >= 4,
    message: `Mapped ${matched}/${testPoints.length} points correctly`
  };
}

function testDataQuality() {
  const readings = [];
  for (let i = 0; i < 100; i++) {
    readings.push({
      ts: new Date(Date.now() - (100 - i) * 300000).toISOString(),
      value: i % 10 === 0 ? null : 50 + Math.random() * 10
    });
  }
  
  const processed = processRawTelemetry(readings, 300);
  const quality = processed.quality;
  
  return {
    success: quality.coveragePct >= 80 && quality.qualityGrade !== 'F',
    message: `Coverage: ${quality.coveragePct}%, Grade: ${quality.qualityGrade}, Outliers: ${quality.outlierRate}%`
  };
}

function testDataSourceStatus() {
  // Test that getDataSourceStatus returns expected structure
  // Note: This is a sync wrapper for async function - in real tests, use async
  const statusPromise = getDataSourceStatus();
  
  // For sync test, we just verify the function exists and returns a promise
  const isPromise = statusPromise && typeof statusPromise.then === 'function';
  
  return {
    success: isPromise,
    message: `getDataSourceStatus returns promise: ${isPromise}`
  };
}

function testRealWeatherData() {
  // Test that real weather loading function exists and returns promise
  const weatherPromise = loadNOAAWeather('725300');
  const isPromise = weatherPromise && typeof weatherPromise.then === 'function';
  
  return {
    success: isPromise,
    message: `loadNOAAWeather returns promise for real data loading`
  };
}

function testBDG2Benchmarks() {
  // Test BDG2 benchmark loading
  const benchmarkPromise = loadBDG2Benchmark('Office');
  const isPromise = benchmarkPromise && typeof benchmarkPromise.then === 'function';
  
  // Also test baseline status function
  const statusPromise = getBaselineStatus();
  const statusIsPromise = statusPromise && typeof statusPromise.then === 'function';
  
  return {
    success: isPromise && statusIsPromise,
    message: `BDG2 benchmark loading: ${isPromise}, baseline status: ${statusIsPromise}`
  };
}

function testLBNLData() {
  const baseline = generateLBNLStyleFaultData('baseline', 4);
  const undercharge = generateLBNLStyleFaultData('refrigerant_undercharge_20', 4);
  
  const baselineSuperheat = baseline.readings.reduce((sum, r) => sum + r.superheat_k, 0) / baseline.readings.length;
  const faultedSuperheat = undercharge.readings.reduce((sum, r) => sum + r.superheat_k, 0) / undercharge.readings.length;
  
  return {
    success: faultedSuperheat > baselineSuperheat * 1.2,
    message: `Baseline SH: ${baselineSuperheat.toFixed(1)}K, Faulted SH: ${faultedSuperheat.toFixed(1)}K (${((faultedSuperheat/baselineSuperheat - 1) * 100).toFixed(0)}% increase)`
  };
}

function testORNLData() {
  const experiment = generateORNLStyleExperiment('exp_002');
  
  const avgDamperPos = experiment.readings.reduce((sum, r) => sum + r.damper_position_pct, 0) / experiment.readings.length;
  
  return {
    success: experiment !== null && avgDamperPos === 100,
    message: `Experiment: ${experiment.fault}, Avg damper: ${avgDamperPos.toFixed(0)}% (stuck open)`
  };
}

function testFaultDetection() {
  const features = {
    reliability: {
      short_cycle_rate: 0.6,
      control_hunting_index: 2.0
    },
    refrigeration: {
      superheat_k: 18,
      subcooling_k: 8,
      suction_pressure_deviation: -10,
      discharge_pressure_deviation: 5
    },
    energy: {
      kwh_day: 150,
      peer_z_score: 1.5
    },
    maintenance: {
      work_orders_365d: 4,
      maintenance_cost_365d: 3500
    }
  };
  
  const result = runFaultDetection(features, 'RTU');
  
  return {
    success: result.faults.length >= 2 && result.impact.faultBurdenScore > 0,
    message: `Detected ${result.faults.length} faults, health score: ${result.summary.overallHealthScore}, burden: ${result.impact.faultBurdenScore}`
  };
}

function testAnomalyDetection() {
  const features = {
    energy: {
      kwh_day: 250,
      kw_peak: 45,
      baseload_kw: 8
    },
    reliability: {
      short_cycle_rate: 0.8,
      control_hunting_index: 3.0,
      p_fail_90d: 0.25
    },
    maintenance: {
      work_orders_365d: 8,
      maintenance_cost_365d: 8000
    }
  };
  
  const result = runFaultDetection(features, 'RTU');
  
  return {
    success: result.anomaly.anomalyScore > 0.3,
    message: `Anomaly score: ${result.anomaly.anomalyScore}, is anomaly: ${result.anomaly.isAnomaly}`
  };
}

function testSurvivalAnalysis() {
  const asset = {
    assetId: 'test-001',
    assetType: 'RTU',
    ageYears: 12
  };
  
  const features = {
    reliability: {
      short_cycle_rate: 0.4,
      control_hunting_index: 1.8
    },
    maintenance: {
      work_orders_365d: 5
    }
  };
  
  const result = computeSurvivalAnalysis(asset, features);
  
  return {
    success: result.failureProbabilities.p1y > 0.1 && result.expectedRemainingLifeYears < 10,
    message: `P(fail 1yr): ${(result.failureProbabilities.p1y * 100).toFixed(1)}%, RUL: ${result.expectedRemainingLifeYears}y, category: ${result.riskCategory}`
  };
}

function testEnergyBaseline() {
  const asset = { assetId: 'test-001', assetType: 'RTU' };
  const features = {
    energy: { kwh_day: 120 }
  };
  
  const cohortBaseline = {
    energy_kwh_day: {
      p05: 60, p25: 80, p50: 95, p75: 115, p95: 150
    }
  };
  
  const weatherData = [];
  for (let i = 0; i < 30 * 24; i++) {
    weatherData.push({
      ts: new Date(Date.now() - i * 3600000).toISOString(),
      oatC: 22 + Math.sin(i * Math.PI / 12) * 8
    });
  }
  
  const utilityRate = { energyRateSchedule: { default: 0.12 } };
  
  const result = computeEnergyWasteEstimate(asset, features, weatherData, cohortBaseline, utilityRate);
  
  return {
    success: result.peerResidual.valid && result.peerResidual.energyWastePercentile > 50,
    message: `Waste percentile: P${result.peerResidual.energyWastePercentile}, annual waste: ${result.summary.annualWasteKwh} kWh, cost: $${result.summary.annualWasteCost}`
  };
}

function testEnhancedLCC() {
  const asset = { assetId: 'test-001', assetType: 'RTU', ageYears: 10 };
  const features = {
    energy: { kwh_day: 100 },
    maintenance: { maintenance_cost_365d: 2500 }
  };
  const option = {
    optionId: 'opt-1',
    optionName: 'High Efficiency RTU',
    capexInstalledCost: 25000,
    expectedEfficiencyDelta: 0.20,
    expectedMaintenanceDeltaPerYear: -800,
    expectedLifeYears: 15
  };
  const economicAssumption = {
    discountRate: 0.08,
    analysisHorizonYears: 10
  };
  const utilityRate = {
    energyRateSchedule: { default: 0.12 },
    escalationRateAssumption: 0.03
  };
  const survivalAnalysis = {
    failureProbabilities: { p1y: 0.15 },
    riskScore: 45
  };
  
  const result = runEnhancedEconomicEvaluation(asset, features, option, economicAssumption, utilityRate, survivalAnalysis);
  
  return {
    success: result.monteCarlo && result.monteCarlo.iterations >= 100,
    message: `NPV: $${result.summary.npv}, P(NPV+): ${(result.summary.pNpvPositive * 100).toFixed(0)}%, IRR: ${result.summary.irr}%, recommendation: ${result.summary.recommendation}`
  };
}

function testFullPipeline() {
  const data = generateCompleteStoreData(1);
  const store = data.stores[0];
  const storeAssets = data.assets.filter(a => a.storeId === store.storeId);
  const economicAssumption = data.economicAssumptions[0];
  const utilityRate = data.utilityRates[0];
  
  const replacementOptionsMap = {};
  storeAssets.forEach(asset => {
    replacementOptionsMap[asset.assetId] = generateReplacementOptions(asset);
  });
  
  const budget = 150000;
  const result = runCapexAnalysis(
    store, storeAssets, replacementOptionsMap,
    economicAssumption, utilityRate, budget, 'max_expected_npv'
  );
  
  const hasAllComponents = 
    result.evaluatedAssets.length > 0 &&
    result.optimizedPlan &&
    result.summary;
  
  const hasFaultData = result.evaluatedAssets.some(a => a.faultDetection);
  const hasSurvivalData = result.evaluatedAssets.some(a => a.survivalAnalysis);
  
  return {
    success: hasAllComponents && hasFaultData && hasSurvivalData,
    message: `Analyzed ${result.evaluatedAssets.length} assets, selected ${result.summary.assetsSelectedForReplacement} for replacement, total NPV: $${result.summary.totalExpectedNpv}`
  };
}

export function testExternalDataIntegration() {
  console.log('\n' + '='.repeat(60));
  console.log('Testing External Data Source Integration');
  console.log('='.repeat(60));
  
  console.log('\n[TEST] LBNL Fault Scenarios...');
  const scenarios = LBNL_FAULT_SCENARIOS.slice(0, 5);
  scenarios.forEach(s => {
    const data = generateLBNLStyleFaultData(s.id, 2);
    console.log(`  - ${s.id}: ${data.readings.length} readings, severity ${s.severity}`);
  });
  
  console.log('\n[TEST] Fault Detection on FDD Data...');
  const fddData = generateLBNLStyleFaultData('refrigerant_undercharge_30', 4);
  const avgSuperheat = fddData.readings.reduce((s, r) => s + r.superheat_k, 0) / fddData.readings.length;
  const avgPower = fddData.readings.reduce((s, r) => s + r.power_kw, 0) / fddData.readings.length;
  
  const features = {
    refrigeration: {
      superheat_k: avgSuperheat,
      subcooling_k: 8,
      suction_pressure_deviation: -15,
      discharge_pressure_deviation: 0
    },
    energy: {
      kwh_day: avgPower * 24,
      peer_z_score: 1.8
    },
    reliability: {
      short_cycle_rate: 0.3,
      control_hunting_index: 1.2
    }
  };
  
  const fddResult = runFaultDetection(features, 'CONDENSING_UNIT');
  console.log(`  Detected faults: ${fddResult.faults.length}`);
  fddResult.faults.forEach(f => {
    console.log(`    - ${f.description} (confidence: ${(f.confidence * 100).toFixed(0)}%)`);
  });
  
  console.log('\n[TEST] Survival Analysis with Fault Data...');
  const asset = { assetId: 'fdd-test', assetType: 'CONDENSING_UNIT', ageYears: 8 };
  const enrichedFeatures = {
    ...features,
    faultDetection: fddResult,
    maintenance: { work_orders_365d: 4 }
  };
  
  const survivalResult = computeSurvivalAnalysis(asset, enrichedFeatures);
  console.log(`  Risk category: ${survivalResult.riskCategory}`);
  console.log(`  P(fail 1yr): ${(survivalResult.failureProbabilities.p1y * 100).toFixed(1)}%`);
  console.log(`  Expected RUL: ${survivalResult.expectedRemainingLifeYears} years`);
  
  return {
    fddData,
    fddResult,
    survivalResult
  };
}

if (typeof window !== 'undefined') {
  window.runCapexTests = runAllTests;
  window.testExternalData = testExternalDataIntegration;
}

export default runAllTests;
