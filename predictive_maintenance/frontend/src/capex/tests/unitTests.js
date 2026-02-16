/**
 * Comprehensive Unit Tests for CapEx Generator Engine Modules
 */

import { processRawTelemetry, computeDataQualityScore, mapRawPointToCanonical, resampleTimeSeries, detectOutliers, imputeMissing } from '../engine/semanticNormalization.js';
import { computeDegreeDays, fitChangePointModel, computePeerResidualBaseline, computeEnergyWasteEstimate } from '../engine/energyBaseline.js';
import { runFaultDetection, detectRuleBasedFaults, isolationForestScore, estimateFaultImpact, FAULT_TYPES } from '../engine/faultDetection.js';
import { computeSurvivalAnalysis, weibullSurvival, weibullHazard, conditionalFailureProbability, expectedRemainingLife, computeCoxHazardRatio } from '../engine/survivalModeling.js';
import { computeKeepLCC, computeReplaceLCC, computeNPVComparison, equivalentAnnualCost, monteCarloNPV } from '../engine/enhancedLCC.js';
import { optimizeCapexPlan, greedyKnapsack } from '../engine/knapsackOptimizer.js';
import { computePeerComparison, getGlobalBaseline, computeRobustZScore } from '../engine/peerComparison.js';
import { generateLBNLStyleFaultData, generateORNLStyleExperiment, LBNL_FAULT_SCENARIOS } from '../data/externalDataSources.js';

class TestRunner {
  constructor() {
    this.results = { passed: 0, failed: 0, tests: [] };
  }
  
  test(name, fn) {
    try {
      const result = fn();
      if (result.success) {
        this.results.passed++;
        this.results.tests.push({ name, status: 'passed', message: result.message, details: result.details });
        console.log(`  ✓ ${name}`);
      } else {
        this.results.failed++;
        this.results.tests.push({ name, status: 'failed', message: result.message, details: result.details });
        console.log(`  ✗ ${name}: ${result.message}`);
      }
    } catch (error) {
      this.results.failed++;
      this.results.tests.push({ name, status: 'error', message: error.message });
      console.log(`  ✗ ${name}: ERROR - ${error.message}`);
    }
  }
  
  assert(condition, message) {
    if (!condition) throw new Error(message);
  }
  
  assertApproxEqual(actual, expected, tolerance = 0.01, message = '') {
    const diff = Math.abs(actual - expected);
    if (diff > tolerance) {
      throw new Error(`${message} Expected ${expected}, got ${actual} (diff: ${diff})`);
    }
  }
  
  summary() {
    console.log(`\n${'='.repeat(50)}`);
    console.log(`Results: ${this.results.passed} passed, ${this.results.failed} failed`);
    console.log(`${'='.repeat(50)}`);
    return this.results;
  }
}

export function runSemanticNormalizationTests() {
  console.log('\n--- Semantic Normalization Tests ---');
  const t = new TestRunner();
  
  t.test('mapRawPointToCanonical - power sensor', () => {
    const result = mapRawPointToCanonical('RTU_01_Power_kW');
    return {
      success: result.canonicalMetric === 'power_kw' && result.confidence > 0.5,
      message: `Mapped to ${result.canonicalMetric} with ${result.confidence} confidence`
    };
  });
  
  t.test('mapRawPointToCanonical - supply temp', () => {
    const result = mapRawPointToCanonical('AHU-1-SAT');
    return {
      success: result.canonicalMetric === 'supply_temp_c',
      message: `Mapped to ${result.canonicalMetric}`
    };
  });
  
  t.test('mapRawPointToCanonical - suction pressure', () => {
    const result = mapRawPointToCanonical('Suction_Pressure_PSI');
    return {
      success: result.canonicalMetric === 'suction_pressure_psi',
      message: `Mapped to ${result.canonicalMetric}`
    };
  });
  
  t.test('resampleTimeSeries - creates uniform intervals', () => {
    const readings = [];
    const baseTime = Date.now();
    for (let i = 0; i < 20; i++) {
      readings.push({ ts: new Date(baseTime + i * 60000).toISOString(), value: 50 + Math.random() * 10 });
    }
    const resampled = resampleTimeSeries(readings, 300);
    const allHaveTs = resampled.every(r => r.ts);
    return {
      success: resampled.length > 0 && allHaveTs,
      message: `Resampled ${readings.length} readings to ${resampled.length} at 5-min intervals`
    };
  });
  
  t.test('detectOutliers - identifies extreme values', () => {
    const readings = [];
    for (let i = 0; i < 50; i++) {
      readings.push({ ts: new Date().toISOString(), value: 50 + Math.random() * 5, qualityFlag: 'good' });
    }
    readings.push({ ts: new Date().toISOString(), value: 200, qualityFlag: 'good' });
    const result = detectOutliers(readings);
    const outlierCount = result.filter(r => r.qualityFlag === 'outlier').length;
    return {
      success: outlierCount >= 1,
      message: `Detected ${outlierCount} outlier(s)`
    };
  });
  
  t.test('imputeMissing - fills gaps with interpolation', () => {
    const readings = [
      { ts: '2024-01-01T00:00:00Z', value: 10, qualityFlag: 'good' },
      { ts: '2024-01-01T00:05:00Z', value: null, qualityFlag: 'missing' },
      { ts: '2024-01-01T00:10:00Z', value: 20, qualityFlag: 'good' }
    ];
    const result = imputeMissing(readings);
    return {
      success: result[1].value !== null && result[1].qualityFlag === 'imputed',
      message: `Imputed value: ${result[1].value}`
    };
  });
  
  t.test('computeDataQualityScore - calculates coverage', () => {
    const readings = [];
    for (let i = 0; i < 100; i++) {
      readings.push({
        ts: new Date().toISOString(),
        value: i % 5 === 0 ? null : 50,
        qualityFlag: i % 5 === 0 ? 'missing' : 'good'
      });
    }
    const quality = computeDataQualityScore(readings);
    return {
      success: quality.coveragePct >= 75 && quality.coveragePct <= 85,
      message: `Coverage: ${quality.coveragePct}%, Grade: ${quality.qualityGrade}`
    };
  });
  
  return t.summary();
}

export function runEnergyBaselineTests() {
  console.log('\n--- Energy Baseline Tests ---');
  const t = new TestRunner();
  
  t.test('computeDegreeDays - cooling degree days', () => {
    const weather = [
      { ts: '2024-07-01T12:00:00Z', oatC: 30 },
      { ts: '2024-07-01T13:00:00Z', oatC: 32 },
      { ts: '2024-07-01T14:00:00Z', oatC: 28 }
    ];
    const dd = computeDegreeDays(weather, 18, 'cooling');
    const totalCDD = dd.reduce((sum, d) => sum + d.cdd, 0);
    return {
      success: totalCDD > 30,
      message: `Total CDD: ${totalCDD.toFixed(1)}`
    };
  });
  
  t.test('fitChangePointModel - requires minimum data', () => {
    const dailyEnergy = Array.from({ length: 10 }, (_, i) => ({ date: `2024-01-${i+1}`, kwhDay: 100 }));
    const dailyDD = Array.from({ length: 10 }, (_, i) => ({ date: `2024-01-${i+1}`, avgOatC: 20 }));
    const model = fitChangePointModel(dailyEnergy, dailyDD);
    return {
      success: model.valid === false,
      message: model.reason || 'Model rejected insufficient data'
    };
  });
  
  t.test('fitChangePointModel - fits with sufficient data', () => {
    const dailyEnergy = [];
    const dailyDD = [];
    for (let i = 0; i < 30; i++) {
      const oat = 15 + Math.random() * 15;
      const kwh = 50 + oat * 2 + Math.random() * 10;
      dailyEnergy.push({ date: `2024-01-${i+1}`, kwhDay: kwh });
      dailyDD.push({ date: `2024-01-${i+1}`, avgOatC: oat, cdd: Math.max(0, oat - 18), hdd: Math.max(0, 18 - oat) });
    }
    const model = fitChangePointModel(dailyEnergy, dailyDD);
    return {
      success: model.valid === true && model.fit.rSquared > 0.3,
      message: `R²: ${model.fit.rSquared}, Slope: ${model.coefficients.slope}`
    };
  });
  
  t.test('computePeerResidualBaseline - calculates waste percentile', () => {
    const features = { kwhDay: 120 };
    const baseline = {
      energy_kwh_day: { p05: 60, p25: 80, p50: 95, p75: 115, p95: 150 }
    };
    const result = computePeerResidualBaseline(features, baseline);
    return {
      success: result.valid && result.energyWastePercentile > 50,
      message: `Waste percentile: P${result.energyWastePercentile}, Z-score: ${result.robustZScore}`
    };
  });
  
  return t.summary();
}

export function runFaultDetectionTests() {
  console.log('\n--- Fault Detection Tests ---');
  const t = new TestRunner();
  
  t.test('detectRuleBasedFaults - short cycling', () => {
    const features = {
      reliability: { short_cycle_rate: 0.7, control_hunting_index: 1.0 }
    };
    const faults = detectRuleBasedFaults(features, 'RTU');
    const shortCyclingFault = faults.find(f => f.code === 'F010');
    return {
      success: shortCyclingFault !== undefined,
      message: `Detected: ${shortCyclingFault?.description}, confidence: ${shortCyclingFault?.confidence}`
    };
  });
  
  t.test('detectRuleBasedFaults - high superheat (refrigerant leak)', () => {
    const features = {
      reliability: { short_cycle_rate: 0.2 },
      refrigeration: { superheat_k: 20, subcooling_k: 10, suction_pressure_deviation: 0, discharge_pressure_deviation: 0 }
    };
    const faults = detectRuleBasedFaults(features, 'CONDENSING_UNIT');
    const leakFault = faults.find(f => f.code === 'F001');
    return {
      success: leakFault !== undefined,
      message: `Detected: ${leakFault?.description}`
    };
  });
  
  t.test('detectRuleBasedFaults - no faults in healthy system', () => {
    const features = {
      reliability: { short_cycle_rate: 0.1, control_hunting_index: 0.5 },
      refrigeration: { superheat_k: 8, subcooling_k: 10, suction_pressure_deviation: 0, discharge_pressure_deviation: 0 },
      energy: { peer_z_score: 0.5 }
    };
    const faults = detectRuleBasedFaults(features, 'RTU');
    return {
      success: faults.length === 0,
      message: `Faults detected: ${faults.length}`
    };
  });
  
  t.test('isolationForestScore - flags anomalous features', () => {
    const features = {
      energy: { kwh_day: 500, kw_peak: 100, baseload_kw: 30 },
      reliability: { short_cycle_rate: 0.9, control_hunting_index: 4.0, p_fail_90d: 0.5 },
      maintenance: { work_orders_365d: 15, maintenance_cost_365d: 20000 }
    };
    const result = isolationForestScore(features);
    return {
      success: result.anomalyScore > 0.5,
      message: `Anomaly score: ${result.anomalyScore}, isAnomaly: ${result.isAnomaly}`
    };
  });
  
  t.test('estimateFaultImpact - calculates energy penalty', () => {
    const faults = [
      { code: 'F001', severity: 'high', confidence: 0.8 },
      { code: 'F004', severity: 'medium', confidence: 0.6 }
    ];
    const impact = estimateFaultImpact(faults, 10000, 2000);
    return {
      success: impact.totalEnergyPenaltyPct > 10 && impact.faultBurdenScore > 0,
      message: `Energy penalty: ${impact.totalEnergyPenaltyPct}%, Burden: ${impact.faultBurdenScore}`
    };
  });
  
  t.test('runFaultDetection - full pipeline', () => {
    const features = {
      reliability: { short_cycle_rate: 0.6, control_hunting_index: 2.5 },
      refrigeration: { superheat_k: 18, subcooling_k: 6 },
      energy: { kwh_day: 150, peer_z_score: 2.0 },
      maintenance: { work_orders_365d: 6, maintenance_cost_365d: 5000 }
    };
    const result = runFaultDetection(features, 'CONDENSING_UNIT');
    return {
      success: result.faults.length >= 2 && result.summary.overallHealthScore < 80,
      message: `Faults: ${result.faults.length}, Health: ${result.summary.overallHealthScore}`
    };
  });
  
  return t.summary();
}

export function runSurvivalModelingTests() {
  console.log('\n--- Survival Modeling Tests ---');
  const t = new TestRunner();
  
  t.test('weibullSurvival - decreases with age', () => {
    const s0 = weibullSurvival(0, 2.2, 15);
    const s5 = weibullSurvival(5, 2.2, 15);
    const s10 = weibullSurvival(10, 2.2, 15);
    const s15 = weibullSurvival(15, 2.2, 15);
    return {
      success: s0 === 1 && s5 > s10 && s10 > s15,
      message: `S(0)=${s0}, S(5)=${s5.toFixed(3)}, S(10)=${s10.toFixed(3)}, S(15)=${s15.toFixed(3)}`
    };
  });
  
  t.test('weibullHazard - increases with age (shape > 1)', () => {
    const h5 = weibullHazard(5, 2.2, 15);
    const h10 = weibullHazard(10, 2.2, 15);
    const h15 = weibullHazard(15, 2.2, 15);
    return {
      success: h5 < h10 && h10 < h15,
      message: `h(5)=${h5.toFixed(4)}, h(10)=${h10.toFixed(4)}, h(15)=${h15.toFixed(4)}`
    };
  });
  
  t.test('conditionalFailureProbability - correct range', () => {
    const pFail = conditionalFailureProbability(10, 1, 2.2, 15);
    return {
      success: pFail >= 0 && pFail <= 1,
      message: `P(fail in 1yr | age=10): ${(pFail * 100).toFixed(1)}%`
    };
  });
  
  t.test('expectedRemainingLife - reasonable estimate', () => {
    const rul = expectedRemainingLife(5, 2.2, 15);
    return {
      success: rul > 5 && rul < 20,
      message: `Expected RUL at age 5: ${rul} years`
    };
  });
  
  t.test('computeCoxHazardRatio - adjusts for covariates', () => {
    const healthyFeatures = { reliability: { short_cycle_rate: 0.1 } };
    const riskyFeatures = {
      reliability: { short_cycle_rate: 0.8, control_hunting_index: 3.0 },
      maintenance: { work_orders_365d: 8 },
      faultDetection: { impact: { faultBurdenScore: 50 } }
    };
    const healthyHR = computeCoxHazardRatio(healthyFeatures);
    const riskyHR = computeCoxHazardRatio(riskyFeatures);
    return {
      success: riskyHR.hazardRatio > healthyHR.hazardRatio,
      message: `Healthy HR: ${healthyHR.hazardRatio}, Risky HR: ${riskyHR.hazardRatio}`
    };
  });
  
  t.test('computeSurvivalAnalysis - full analysis', () => {
    const asset = { assetId: 'test-001', assetType: 'RTU', ageYears: 12 };
    const features = {
      reliability: { short_cycle_rate: 0.5, control_hunting_index: 2.0 },
      maintenance: { work_orders_365d: 5 }
    };
    const result = computeSurvivalAnalysis(asset, features);
    return {
      success: result.failureProbabilities.p1y > 0 && result.riskCategory !== undefined,
      message: `P(1yr): ${(result.failureProbabilities.p1y * 100).toFixed(1)}%, Category: ${result.riskCategory}, RUL: ${result.expectedRemainingLifeYears}y`
    };
  });
  
  return t.summary();
}

export function runEnhancedLCCTests() {
  console.log('\n--- Enhanced LCC Tests ---');
  const t = new TestRunner();
  
  t.test('equivalentAnnualCost - correct calculation', () => {
    const npv = 100000;
    const eac = equivalentAnnualCost(npv, 0.08, 10);
    const expected = 14903;
    return {
      success: Math.abs(eac - expected) < 100,
      message: `EAC of $100k over 10yr @ 8%: $${Math.round(eac)}`
    };
  });
  
  t.test('computeKeepLCC - calculates present value', () => {
    const params = {
      currentAge: 10,
      energyCostPerYear: 5000,
      maintenanceCostPerYear: 2000,
      failureProbabilities: { p1y: 0.15 },
      failureEventCost: 15000,
      discountRate: 0.08,
      energyEscalation: 0.03,
      maintenanceEscalation: 0.04,
      horizon: 10
    };
    const result = computeKeepLCC(params);
    return {
      success: result.pvTotal > 0 && result.eac > 0,
      message: `Keep PV: $${result.pvTotal}, EAC: $${result.eac}`
    };
  });
  
  t.test('computeReplaceLCC - includes capex', () => {
    const params = {
      capex: 25000,
      newEquipmentLife: 15,
      newEnergyCostPerYear: 4000,
      newMaintenanceCostPerYear: 1000,
      newFailureProbability: 0.02,
      failureEventCost: 15000,
      discountRate: 0.08,
      energyEscalation: 0.03,
      maintenanceEscalation: 0.03,
      horizon: 10,
      warrantyYears: 1
    };
    const result = computeReplaceLCC(params);
    return {
      success: result.pvTotal > params.capex && result.initialCost === params.capex,
      message: `Replace PV: $${result.pvTotal}, Capex: $${result.initialCost}`
    };
  });
  
  t.test('computeNPVComparison - correct recommendation', () => {
    const keepLCC = { pvTotal: 80000, eac: 12000, annualCosts: Array(10).fill({ totalCost: 8000 }), discountRate: 0.08 };
    const replaceLCC = { pvTotal: 60000, eac: 9000, initialCost: 25000, annualCosts: Array(10).fill({ totalCost: 5000 }) };
    const result = computeNPVComparison(keepLCC, replaceLCC);
    return {
      success: result.npv > 0 && result.recommendation === 'REPLACE',
      message: `NPV: $${result.npv}, Recommendation: ${result.recommendation}`
    };
  });
  
  t.test('monteCarloNPV - generates distribution', () => {
    const params = {
      baseKeepParams: {
        currentAge: 10, energyCostPerYear: 5000, maintenanceCostPerYear: 2000,
        failureProbabilities: { p1y: 0.15 }, failureEventCost: 15000,
        discountRate: 0.08, energyEscalation: 0.03, maintenanceEscalation: 0.04, horizon: 10
      },
      baseReplaceParams: {
        capex: 25000, newEquipmentLife: 15, newEnergyCostPerYear: 4000,
        newMaintenanceCostPerYear: 1000, newFailureProbability: 0.02,
        failureEventCost: 15000, discountRate: 0.08, energyEscalation: 0.03,
        maintenanceEscalation: 0.03, horizon: 10, efficiencyGain: 0.2
      },
      uncertaintyRanges: { energyCost: 0.15, maintenanceCost: 0.2 }
    };
    const result = monteCarloNPV(params, 100);
    return {
      success: result.iterations === 100 && result.percentiles.p50 !== undefined,
      message: `Mean: $${result.mean}, P50: $${result.percentiles.p50}, P(NPV+): ${(result.pNPVPositive * 100).toFixed(0)}%`
    };
  });
  
  return t.summary();
}

export function runFDDDataTests() {
  console.log('\n--- FDD Data Generation Tests ---');
  const t = new TestRunner();
  
  t.test('generateLBNLStyleFaultData - baseline has normal values', () => {
    const data = generateLBNLStyleFaultData('baseline', 2);
    const avgSuperheat = data.readings.reduce((s, r) => s + r.superheat_k, 0) / data.readings.length;
    return {
      success: avgSuperheat > 6 && avgSuperheat < 12,
      message: `Baseline avg superheat: ${avgSuperheat.toFixed(1)}K`
    };
  });
  
  t.test('generateLBNLStyleFaultData - undercharge increases superheat', () => {
    const baseline = generateLBNLStyleFaultData('baseline', 2);
    const faulted = generateLBNLStyleFaultData('refrigerant_undercharge_30', 2);
    const baseAvg = baseline.readings.reduce((s, r) => s + r.superheat_k, 0) / baseline.readings.length;
    const faultAvg = faulted.readings.reduce((s, r) => s + r.superheat_k, 0) / faulted.readings.length;
    return {
      success: faultAvg > baseAvg * 1.3,
      message: `Baseline SH: ${baseAvg.toFixed(1)}K, Faulted SH: ${faultAvg.toFixed(1)}K`
    };
  });
  
  t.test('generateLBNLStyleFaultData - overcharge increases subcooling', () => {
    const baseline = generateLBNLStyleFaultData('baseline', 2);
    const faulted = generateLBNLStyleFaultData('refrigerant_overcharge_20', 2);
    const baseAvg = baseline.readings.reduce((s, r) => s + r.subcooling_k, 0) / baseline.readings.length;
    const faultAvg = faulted.readings.reduce((s, r) => s + r.subcooling_k, 0) / faulted.readings.length;
    return {
      success: faultAvg > baseAvg * 1.1,
      message: `Baseline SC: ${baseAvg.toFixed(1)}K, Faulted SC: ${faultAvg.toFixed(1)}K`
    };
  });
  
  t.test('generateLBNLStyleFaultData - condenser fouling increases head pressure', () => {
    const baseline = generateLBNLStyleFaultData('baseline', 2);
    const faulted = generateLBNLStyleFaultData('condenser_fouling_30', 2);
    const baseAvg = baseline.readings.reduce((s, r) => s + r.discharge_pressure_psi, 0) / baseline.readings.length;
    const faultAvg = faulted.readings.reduce((s, r) => s + r.discharge_pressure_psi, 0) / faulted.readings.length;
    return {
      success: faultAvg > baseAvg * 1.05,
      message: `Baseline DP: ${baseAvg.toFixed(0)} psi, Faulted DP: ${faultAvg.toFixed(0)} psi`
    };
  });
  
  t.test('generateORNLStyleExperiment - economizer stuck open', () => {
    const exp = generateORNLStyleExperiment('exp_002');
    const avgDamper = exp.readings.reduce((s, r) => s + r.damper_position_pct, 0) / exp.readings.length;
    return {
      success: exp.fault === 'economizer_stuck_open' && avgDamper === 100,
      message: `Fault: ${exp.fault}, Avg damper: ${avgDamper}%`
    };
  });
  
  t.test('LBNL_FAULT_SCENARIOS - all scenarios defined', () => {
    const requiredScenarios = ['baseline', 'refrigerant_undercharge_20', 'condenser_fouling_20', 'compressor_valve_leak_10'];
    const found = requiredScenarios.every(s => LBNL_FAULT_SCENARIOS.some(f => f.id === s));
    return {
      success: found && LBNL_FAULT_SCENARIOS.length >= 10,
      message: `${LBNL_FAULT_SCENARIOS.length} scenarios defined`
    };
  });
  
  return t.summary();
}

export function runAllUnitTests() {
  console.log('='.repeat(60));
  console.log('CAPEX GENERATOR - COMPREHENSIVE UNIT TEST SUITE');
  console.log('='.repeat(60));
  
  const allResults = {
    semanticNormalization: runSemanticNormalizationTests(),
    energyBaseline: runEnergyBaselineTests(),
    faultDetection: runFaultDetectionTests(),
    survivalModeling: runSurvivalModelingTests(),
    enhancedLCC: runEnhancedLCCTests(),
    fddData: runFDDDataTests()
  };
  
  let totalPassed = 0;
  let totalFailed = 0;
  
  Object.values(allResults).forEach(r => {
    totalPassed += r.passed;
    totalFailed += r.failed;
  });
  
  console.log('\n' + '='.repeat(60));
  console.log('FINAL SUMMARY');
  console.log('='.repeat(60));
  console.log(`Total: ${totalPassed + totalFailed} tests`);
  console.log(`Passed: ${totalPassed}`);
  console.log(`Failed: ${totalFailed}`);
  console.log(`Success Rate: ${((totalPassed / (totalPassed + totalFailed)) * 100).toFixed(1)}%`);
  console.log('='.repeat(60));
  
  return {
    totalPassed,
    totalFailed,
    successRate: totalPassed / (totalPassed + totalFailed),
    modules: allResults
  };
}

if (typeof window !== 'undefined') {
  window.runAllUnitTests = runAllUnitTests;
}

export default runAllUnitTests;
