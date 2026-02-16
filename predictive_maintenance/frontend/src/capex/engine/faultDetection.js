/**
 * D. Fault Detection and Diagnostics (FDD)
 * Supervised classification + unsupervised anomaly detection
 * Reference datasets: LBNL FDD, ORNL Curated Fault Data
 */

export const FAULT_TYPES = {
  REFRIGERANT_LEAK: { code: 'F001', severity: 'high', category: 'refrigerant', description: 'Refrigerant undercharge/leak' },
  REFRIGERANT_OVERCHARGE: { code: 'F002', severity: 'medium', category: 'refrigerant', description: 'Refrigerant overcharge' },
  COMPRESSOR_VALVE_LEAK: { code: 'F003', severity: 'high', category: 'compressor', description: 'Compressor valve leakage' },
  CONDENSER_FOULING: { code: 'F004', severity: 'medium', category: 'heat_exchanger', description: 'Condenser coil fouling' },
  EVAPORATOR_FOULING: { code: 'F005', severity: 'medium', category: 'heat_exchanger', description: 'Evaporator coil fouling' },
  FILTER_RESTRICTION: { code: 'F006', severity: 'low', category: 'airflow', description: 'Air filter restriction' },
  FAN_DEGRADATION: { code: 'F007', severity: 'medium', category: 'fan', description: 'Fan motor/belt degradation' },
  SENSOR_DRIFT: { code: 'F008', severity: 'low', category: 'sensor', description: 'Temperature sensor drift' },
  CONTROL_HUNTING: { code: 'F009', severity: 'medium', category: 'control', description: 'Control loop oscillation' },
  SHORT_CYCLING: { code: 'F010', severity: 'high', category: 'compressor', description: 'Compressor short cycling' },
  ECONOMIZER_STUCK: { code: 'F011', severity: 'medium', category: 'economizer', description: 'Economizer damper stuck' },
  TXV_MALFUNCTION: { code: 'F012', severity: 'high', category: 'refrigerant', description: 'Expansion valve malfunction' },
  DEFROST_FAILURE: { code: 'F013', severity: 'high', category: 'refrigeration', description: 'Defrost cycle failure' },
  HIGH_HEAD_PRESSURE: { code: 'F014', severity: 'high', category: 'refrigerant', description: 'Abnormally high head pressure' },
  LOW_SUCTION_PRESSURE: { code: 'F015', severity: 'high', category: 'refrigerant', description: 'Abnormally low suction pressure' }
};

export const FAULT_SEVERITY_WEIGHTS = {
  low: 1,
  medium: 2,
  high: 3,
  critical: 4
};

/**
 * D1. Rule-based fault detection (threshold + pattern matching)
 * Simple but effective for known fault signatures
 */
export function detectRuleBasedFaults(features, assetType) {
  const faults = [];
  
  if (features.reliability?.short_cycle_rate > 0.5) {
    faults.push({
      ...FAULT_TYPES.SHORT_CYCLING,
      confidence: Math.min(0.95, 0.6 + features.reliability.short_cycle_rate * 0.35),
      evidence: `Short cycle rate: ${(features.reliability.short_cycle_rate * 100).toFixed(1)}%`,
      metric: 'short_cycle_rate',
      value: features.reliability.short_cycle_rate
    });
  }
  
  if (features.reliability?.control_hunting_index > 1.5) {
    faults.push({
      ...FAULT_TYPES.CONTROL_HUNTING,
      confidence: Math.min(0.9, 0.5 + features.reliability.control_hunting_index * 0.2),
      evidence: `Hunting index: ${features.reliability.control_hunting_index.toFixed(2)}`,
      metric: 'control_hunting_index',
      value: features.reliability.control_hunting_index
    });
  }
  
  if (features.refrigeration) {
    const { superheat_k, subcooling_k, suction_pressure_deviation, discharge_pressure_deviation } = features.refrigeration;
    
    if (superheat_k > 15) {
      faults.push({
        ...FAULT_TYPES.REFRIGERANT_LEAK,
        confidence: Math.min(0.85, 0.4 + (superheat_k - 15) * 0.03),
        evidence: `High superheat: ${superheat_k.toFixed(1)}K (normal: 5-12K)`,
        metric: 'superheat_k',
        value: superheat_k
      });
    }
    
    if (superheat_k < 3) {
      faults.push({
        ...FAULT_TYPES.TXV_MALFUNCTION,
        confidence: 0.7,
        evidence: `Low superheat: ${superheat_k.toFixed(1)}K (risk of liquid floodback)`,
        metric: 'superheat_k',
        value: superheat_k
      });
    }
    
    if (subcooling_k > 20) {
      faults.push({
        ...FAULT_TYPES.REFRIGERANT_OVERCHARGE,
        confidence: Math.min(0.8, 0.5 + (subcooling_k - 20) * 0.02),
        evidence: `High subcooling: ${subcooling_k.toFixed(1)}K (normal: 8-14K)`,
        metric: 'subcooling_k',
        value: subcooling_k
      });
    }
    
    if (discharge_pressure_deviation > 15) {
      faults.push({
        ...FAULT_TYPES.HIGH_HEAD_PRESSURE,
        confidence: 0.75,
        evidence: `Discharge pressure ${discharge_pressure_deviation.toFixed(0)}% above expected`,
        metric: 'discharge_pressure_deviation',
        value: discharge_pressure_deviation
      });
    }
    
    if (suction_pressure_deviation < -15) {
      faults.push({
        ...FAULT_TYPES.LOW_SUCTION_PRESSURE,
        confidence: 0.75,
        evidence: `Suction pressure ${Math.abs(suction_pressure_deviation).toFixed(0)}% below expected`,
        metric: 'suction_pressure_deviation',
        value: suction_pressure_deviation
      });
    }
  }
  
  if (features.hvac) {
    const { supply_return_delta, economizer_effectiveness } = features.hvac;
    
    if (supply_return_delta < 8 && assetType === 'RTU') {
      faults.push({
        ...FAULT_TYPES.EVAPORATOR_FOULING,
        confidence: 0.6,
        evidence: `Low supply-return delta: ${supply_return_delta.toFixed(1)}°C (expected: 10-15°C)`,
        metric: 'supply_return_delta',
        value: supply_return_delta
      });
    }
    
    if (economizer_effectiveness !== undefined && economizer_effectiveness < 0.3) {
      faults.push({
        ...FAULT_TYPES.ECONOMIZER_STUCK,
        confidence: 0.65,
        evidence: `Low economizer effectiveness: ${(economizer_effectiveness * 100).toFixed(0)}%`,
        metric: 'economizer_effectiveness',
        value: economizer_effectiveness
      });
    }
  }
  
  const energyZScore = features.energy?.peer_z_score || 0;
  if (energyZScore > 2) {
    const existingFaultTypes = new Set(faults.map(f => f.category));
    if (!existingFaultTypes.has('heat_exchanger') && !existingFaultTypes.has('refrigerant')) {
      faults.push({
        ...FAULT_TYPES.CONDENSER_FOULING,
        confidence: Math.min(0.7, 0.4 + energyZScore * 0.1),
        evidence: `Energy consumption ${energyZScore.toFixed(1)} std dev above peers`,
        metric: 'energy_z_score',
        value: energyZScore
      });
    }
  }
  
  return faults;
}

/**
 * D2. Isolation Forest anomaly detection
 * Unsupervised detection for novel/unknown faults
 */
export function isolationForestScore(features, forestParams = null) {
  const featureVector = extractFeatureVector(features);
  if (featureVector.length === 0) return { anomalyScore: 0, isAnomaly: false };
  
  const referenceDistribution = forestParams?.distribution || {
    means: featureVector.map(() => 0),
    stds: featureVector.map(() => 1)
  };
  
  const zScores = featureVector.map((v, i) => {
    const std = referenceDistribution.stds[i] || 1;
    return std > 0 ? Math.abs(v - referenceDistribution.means[i]) / std : 0;
  });
  
  const maxZScore = Math.max(...zScores);
  const avgZScore = zScores.reduce((a, b) => a + b, 0) / zScores.length;
  
  const anomalyScore = Math.min(1, (maxZScore * 0.6 + avgZScore * 0.4) / 3);
  
  return {
    anomalyScore: Math.round(anomalyScore * 100) / 100,
    isAnomaly: anomalyScore > 0.65,
    maxZScore: Math.round(maxZScore * 100) / 100,
    avgZScore: Math.round(avgZScore * 100) / 100,
    featureContributions: zScores.map((z, i) => ({
      feature: getFeatureName(i),
      zScore: Math.round(z * 100) / 100
    })).sort((a, b) => b.zScore - a.zScore).slice(0, 5)
  };
}

function extractFeatureVector(features) {
  const vector = [];
  
  if (features.energy) {
    if (features.energy.kwh_day !== undefined) vector.push(features.energy.kwh_day);
    if (features.energy.kw_peak !== undefined) vector.push(features.energy.kw_peak);
    if (features.energy.baseload_kw !== undefined) vector.push(features.energy.baseload_kw);
  }
  
  if (features.reliability) {
    if (features.reliability.short_cycle_rate !== undefined) vector.push(features.reliability.short_cycle_rate * 100);
    if (features.reliability.control_hunting_index !== undefined) vector.push(features.reliability.control_hunting_index);
    if (features.reliability.p_fail_90d !== undefined) vector.push(features.reliability.p_fail_90d * 100);
  }
  
  if (features.maintenance) {
    if (features.maintenance.work_orders_365d !== undefined) vector.push(features.maintenance.work_orders_365d);
    if (features.maintenance.maintenance_cost_365d !== undefined) vector.push(features.maintenance.maintenance_cost_365d / 1000);
  }
  
  return vector;
}

function getFeatureName(index) {
  const names = [
    'kwh_day', 'kw_peak', 'baseload_kw',
    'short_cycle_rate', 'control_hunting_index', 'p_fail_90d',
    'work_orders_365d', 'maintenance_cost_365d'
  ];
  return names[index] || `feature_${index}`;
}

/**
 * D3. Fault impact estimation
 * Maps detected faults to energy and maintenance cost impacts
 */
export const FAULT_IMPACT_MODELS = {
  F001: { energyPenaltyPct: 15, maintenanceCostMultiplier: 2.5, failureRiskMultiplier: 2.0 },
  F002: { energyPenaltyPct: 8, maintenanceCostMultiplier: 1.5, failureRiskMultiplier: 1.3 },
  F003: { energyPenaltyPct: 20, maintenanceCostMultiplier: 3.0, failureRiskMultiplier: 3.0 },
  F004: { energyPenaltyPct: 12, maintenanceCostMultiplier: 1.3, failureRiskMultiplier: 1.2 },
  F005: { energyPenaltyPct: 10, maintenanceCostMultiplier: 1.2, failureRiskMultiplier: 1.1 },
  F006: { energyPenaltyPct: 5, maintenanceCostMultiplier: 1.1, failureRiskMultiplier: 1.0 },
  F007: { energyPenaltyPct: 8, maintenanceCostMultiplier: 1.5, failureRiskMultiplier: 1.4 },
  F008: { energyPenaltyPct: 3, maintenanceCostMultiplier: 1.1, failureRiskMultiplier: 1.0 },
  F009: { energyPenaltyPct: 5, maintenanceCostMultiplier: 1.2, failureRiskMultiplier: 1.1 },
  F010: { energyPenaltyPct: 15, maintenanceCostMultiplier: 2.0, failureRiskMultiplier: 2.5 },
  F011: { energyPenaltyPct: 20, maintenanceCostMultiplier: 1.2, failureRiskMultiplier: 1.0 },
  F012: { energyPenaltyPct: 18, maintenanceCostMultiplier: 2.0, failureRiskMultiplier: 1.8 },
  F013: { energyPenaltyPct: 25, maintenanceCostMultiplier: 1.5, failureRiskMultiplier: 1.5 },
  F014: { energyPenaltyPct: 15, maintenanceCostMultiplier: 1.8, failureRiskMultiplier: 2.0 },
  F015: { energyPenaltyPct: 12, maintenanceCostMultiplier: 1.6, failureRiskMultiplier: 1.8 }
};

export function estimateFaultImpact(faults, baselineEnergyCost, baselineMaintenanceCost) {
  if (faults.length === 0) {
    return {
      totalEnergyPenaltyPct: 0,
      totalEnergyPenaltyCost: 0,
      maintenanceCostMultiplier: 1.0,
      failureRiskMultiplier: 1.0,
      faultBurdenScore: 0
    };
  }
  
  let combinedEnergyPenalty = 0;
  let maxMaintMultiplier = 1.0;
  let maxFailureMultiplier = 1.0;
  let totalSeverityWeight = 0;
  
  faults.forEach(fault => {
    const impact = FAULT_IMPACT_MODELS[fault.code] || { energyPenaltyPct: 5, maintenanceCostMultiplier: 1.2, failureRiskMultiplier: 1.1 };
    const confidence = fault.confidence || 0.5;
    const severityWeight = FAULT_SEVERITY_WEIGHTS[fault.severity] || 1;
    
    combinedEnergyPenalty += impact.energyPenaltyPct * confidence * (1 - combinedEnergyPenalty / 100 * 0.5);
    maxMaintMultiplier = Math.max(maxMaintMultiplier, 1 + (impact.maintenanceCostMultiplier - 1) * confidence);
    maxFailureMultiplier = Math.max(maxFailureMultiplier, 1 + (impact.failureRiskMultiplier - 1) * confidence);
    totalSeverityWeight += severityWeight * confidence;
  });
  
  combinedEnergyPenalty = Math.min(50, combinedEnergyPenalty);
  
  const faultBurdenScore = Math.min(100, totalSeverityWeight * 15);
  
  return {
    totalEnergyPenaltyPct: Math.round(combinedEnergyPenalty * 10) / 10,
    totalEnergyPenaltyCost: Math.round(baselineEnergyCost * combinedEnergyPenalty / 100),
    maintenanceCostMultiplier: Math.round(maxMaintMultiplier * 100) / 100,
    estimatedMaintenanceCost: Math.round(baselineMaintenanceCost * maxMaintMultiplier),
    failureRiskMultiplier: Math.round(maxFailureMultiplier * 100) / 100,
    faultBurdenScore: Math.round(faultBurdenScore),
    faultCount: faults.length,
    highSeverityCount: faults.filter(f => f.severity === 'high' || f.severity === 'critical').length
  };
}

/**
 * Combined fault detection pipeline
 */
export function runFaultDetection(features, assetType, cohortBaseline = null) {
  const ruleBasedFaults = detectRuleBasedFaults(features, assetType);
  const anomalyResult = isolationForestScore(features);
  
  const baseEnergyCost = (features.energy?.kwh_day || 100) * 365 * 0.12;
  const baseMaintCost = features.maintenance?.maintenance_cost_365d || 2000;
  const faultImpact = estimateFaultImpact(ruleBasedFaults, baseEnergyCost, baseMaintCost);
  
  return {
    faults: ruleBasedFaults,
    anomaly: anomalyResult,
    impact: faultImpact,
    summary: {
      totalFaults: ruleBasedFaults.length,
      highConfidenceFaults: ruleBasedFaults.filter(f => f.confidence >= 0.7).length,
      isAnomalous: anomalyResult.isAnomaly,
      overallHealthScore: Math.max(0, 100 - faultImpact.faultBurdenScore - (anomalyResult.isAnomaly ? 15 : 0)),
      primaryConcerns: ruleBasedFaults
        .filter(f => f.confidence >= 0.6)
        .sort((a, b) => FAULT_SEVERITY_WEIGHTS[b.severity] - FAULT_SEVERITY_WEIGHTS[a.severity])
        .slice(0, 3)
        .map(f => f.description)
    }
  };
}
