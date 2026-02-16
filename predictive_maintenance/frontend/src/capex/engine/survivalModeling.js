/**
 * E. Survival/Hazard Modeling for Failure Prediction
 * Cox proportional hazards + Weibull parametric models
 * Reference: https://www.sciencedirect.com/science/article/pii/S0951832020306244
 */

/**
 * E1. Weibull distribution parameters by asset type
 * Based on industry failure data and equipment reliability studies
 */
export const WEIBULL_PARAMETERS = {
  RTU: { shape: 2.2, scale: 15, minAge: 0 },
  AHU: { shape: 2.5, scale: 20, minAge: 0 },
  COMPRESSOR_RACK: { shape: 2.0, scale: 12, minAge: 0 },
  CONDENSING_UNIT: { shape: 2.1, scale: 14, minAge: 0 },
  WALK_IN_COOLER: { shape: 2.3, scale: 18, minAge: 0 },
  WALK_IN_FREEZER: { shape: 2.1, scale: 16, minAge: 0 },
  REACH_IN_CASE: { shape: 2.4, scale: 12, minAge: 0 },
  CHILLER: { shape: 2.6, scale: 22, minAge: 0 },
  BOILER: { shape: 2.8, scale: 25, minAge: 0 },
  VFD: { shape: 2.0, scale: 12, minAge: 0 },
  DEFAULT: { shape: 2.2, scale: 15, minAge: 0 }
};

/**
 * Weibull survival function: S(t) = exp(-(t/scale)^shape)
 */
export function weibullSurvival(t, shape, scale) {
  if (t <= 0) return 1;
  return Math.exp(-Math.pow(t / scale, shape));
}

/**
 * Weibull hazard function: h(t) = (shape/scale) * (t/scale)^(shape-1)
 */
export function weibullHazard(t, shape, scale) {
  if (t <= 0) return 0;
  return (shape / scale) * Math.pow(t / scale, shape - 1);
}

/**
 * Weibull cumulative hazard: H(t) = (t/scale)^shape
 */
export function weibullCumulativeHazard(t, shape, scale) {
  if (t <= 0) return 0;
  return Math.pow(t / scale, shape);
}

/**
 * Probability of failure within time window [t, t+horizon]
 * P(T <= t+horizon | T > t) = 1 - S(t+horizon)/S(t)
 */
export function conditionalFailureProbability(currentAge, horizon, shape, scale) {
  const survivalNow = weibullSurvival(currentAge, shape, scale);
  const survivalFuture = weibullSurvival(currentAge + horizon, shape, scale);
  
  if (survivalNow <= 0) return 1;
  return 1 - (survivalFuture / survivalNow);
}

/**
 * Expected remaining useful life (RUL)
 * E[T-t | T > t] = integral from t to infinity of S(u)/S(t) du
 * Approximated numerically
 */
export function expectedRemainingLife(currentAge, shape, scale, maxLife = 50) {
  const survivalNow = weibullSurvival(currentAge, shape, scale);
  if (survivalNow <= 0.001) return 0;
  
  let integral = 0;
  const step = 0.1;
  
  for (let u = currentAge; u < currentAge + maxLife; u += step) {
    const survivalU = weibullSurvival(u, shape, scale);
    integral += (survivalU / survivalNow) * step;
  }
  
  return Math.round(integral * 10) / 10;
}

/**
 * E1b. Cox proportional hazards adjustment
 * Adjusts baseline hazard based on covariates (telemetry features)
 */
export const COX_COEFFICIENTS = {
  short_cycle_rate: 0.8,
  control_hunting_index: 0.4,
  energy_waste_percentile: 0.015,
  maintenance_burden_percentile: 0.012,
  fault_burden_score: 0.02,
  work_orders_365d: 0.15,
  anomaly_score: 1.2
};

export function computeCoxHazardRatio(features) {
  let logHazardRatio = 0;
  
  if (features.reliability?.short_cycle_rate !== undefined) {
    logHazardRatio += COX_COEFFICIENTS.short_cycle_rate * features.reliability.short_cycle_rate;
  }
  
  if (features.reliability?.control_hunting_index !== undefined) {
    logHazardRatio += COX_COEFFICIENTS.control_hunting_index * Math.max(0, features.reliability.control_hunting_index - 1);
  }
  
  if (features.peerComparison?.energyWaste?.percentile !== undefined) {
    logHazardRatio += COX_COEFFICIENTS.energy_waste_percentile * Math.max(0, features.peerComparison.energyWaste.percentile - 50);
  }
  
  if (features.peerComparison?.maintenanceBurden?.percentile !== undefined) {
    logHazardRatio += COX_COEFFICIENTS.maintenance_burden_percentile * Math.max(0, features.peerComparison.maintenanceBurden.percentile - 50);
  }
  
  if (features.faultDetection?.impact?.faultBurdenScore !== undefined) {
    logHazardRatio += COX_COEFFICIENTS.fault_burden_score * features.faultDetection.impact.faultBurdenScore;
  }
  
  if (features.maintenance?.work_orders_365d !== undefined) {
    logHazardRatio += COX_COEFFICIENTS.work_orders_365d * Math.max(0, features.maintenance.work_orders_365d - 2);
  }
  
  if (features.faultDetection?.anomaly?.anomalyScore !== undefined) {
    logHazardRatio += COX_COEFFICIENTS.anomaly_score * features.faultDetection.anomaly.anomalyScore;
  }
  
  return {
    logHazardRatio: Math.round(logHazardRatio * 1000) / 1000,
    hazardRatio: Math.round(Math.exp(logHazardRatio) * 100) / 100,
    riskMultiplier: Math.round(Math.exp(logHazardRatio) * 100) / 100
  };
}

/**
 * E2. Full survival analysis combining Weibull + Cox
 */
export function computeSurvivalAnalysis(asset, features) {
  const params = WEIBULL_PARAMETERS[asset.assetType] || WEIBULL_PARAMETERS.DEFAULT;
  const currentAge = asset.ageYears || 0;
  
  const coxAdjustment = computeCoxHazardRatio(features);
  
  const adjustedScale = params.scale / Math.pow(coxAdjustment.hazardRatio, 1 / params.shape);
  
  const pFail30d = conditionalFailureProbability(currentAge, 30 / 365, params.shape, adjustedScale);
  const pFail90d = conditionalFailureProbability(currentAge, 90 / 365, params.shape, adjustedScale);
  const pFail1y = conditionalFailureProbability(currentAge, 1, params.shape, adjustedScale);
  const pFail3y = conditionalFailureProbability(currentAge, 3, params.shape, adjustedScale);
  
  const expectedRUL = expectedRemainingLife(currentAge, params.shape, adjustedScale);
  
  const baselinePFail1y = conditionalFailureProbability(currentAge, 1, params.shape, params.scale);
  
  const currentHazard = weibullHazard(currentAge, params.shape, adjustedScale);
  const medianLifeHazard = weibullHazard(params.scale * Math.pow(Math.log(2), 1 / params.shape), params.shape, params.scale);
  
  let riskCategory;
  if (pFail1y >= 0.4 || pFail90d >= 0.2) riskCategory = 'critical';
  else if (pFail1y >= 0.25 || pFail90d >= 0.1) riskCategory = 'high';
  else if (pFail1y >= 0.15) riskCategory = 'elevated';
  else if (pFail1y >= 0.08) riskCategory = 'moderate';
  else riskCategory = 'low';
  
  return {
    model: {
      type: 'weibull_cox',
      baselineShape: params.shape,
      baselineScale: params.scale,
      adjustedScale: Math.round(adjustedScale * 100) / 100,
      coxAdjustment
    },
    currentAge,
    failureProbabilities: {
      p30d: Math.round(pFail30d * 1000) / 1000,
      p90d: Math.round(pFail90d * 1000) / 1000,
      p1y: Math.round(pFail1y * 1000) / 1000,
      p3y: Math.round(pFail3y * 1000) / 1000
    },
    expectedRemainingLifeYears: expectedRUL,
    riskCategory,
    riskScore: Math.round(Math.min(100, pFail1y * 150 + (coxAdjustment.hazardRatio - 1) * 30)),
    comparison: {
      baselinePFail1y: Math.round(baselinePFail1y * 1000) / 1000,
      riskElevation: Math.round((pFail1y / baselinePFail1y - 1) * 100),
      hazardVsMedian: Math.round((currentHazard / medianLifeHazard) * 100) / 100
    },
    interpretation: getRiskInterpretation(riskCategory, pFail1y, expectedRUL, coxAdjustment.hazardRatio)
  };
}

function getRiskInterpretation(category, pFail1y, rul, hazardRatio) {
  const pct = Math.round(pFail1y * 100);
  
  switch (category) {
    case 'critical':
      return `Critical failure risk (${pct}% in next year). Immediate replacement recommended. Expected RUL: ${rul} years.`;
    case 'high':
      return `High failure risk (${pct}% in next year). Plan replacement within 6-12 months. Hazard ${hazardRatio.toFixed(1)}x baseline.`;
    case 'elevated':
      return `Elevated failure risk (${pct}% in next year). Monitor closely and budget for replacement. RUL: ${rul} years.`;
    case 'moderate':
      return `Moderate failure risk (${pct}% in next year). Continue monitoring, standard maintenance schedule.`;
    default:
      return `Low failure risk (${pct}% in next year). Asset performing within expected parameters. RUL: ${rul} years.`;
  }
}

/**
 * E2b. Bayesian updating of failure probability (simplified)
 * Updates prior based on observed time without failure
 */
export function bayesianUpdateFailureProb(priorPFail, observedTimeWithoutFailure, expectedMTBF) {
  const likelihoodNoFailure = Math.exp(-observedTimeWithoutFailure / expectedMTBF);
  const posteriorPFail = priorPFail * (1 - likelihoodNoFailure) / 
    (priorPFail * (1 - likelihoodNoFailure) + (1 - priorPFail));
  
  return Math.round(posteriorPFail * 1000) / 1000;
}

/**
 * Compute expected failure cost for LCC calculations
 */
export function computeExpectedFailureCost(survivalAnalysis, failureEventCost, horizon = 10) {
  const annualExpectedCosts = [];
  let cumulativeSurvival = 1;
  
  const shape = survivalAnalysis.model.baselineShape;
  const scale = survivalAnalysis.model.adjustedScale;
  const startAge = survivalAnalysis.currentAge;
  
  for (let year = 1; year <= horizon; year++) {
    const pFailThisYear = conditionalFailureProbability(
      startAge + year - 1, 
      1, 
      shape, 
      scale
    );
    
    const expectedCost = pFailThisYear * failureEventCost * cumulativeSurvival;
    cumulativeSurvival *= (1 - pFailThisYear);
    
    annualExpectedCosts.push({
      year,
      pFail: Math.round(pFailThisYear * 1000) / 1000,
      cumulativeSurvival: Math.round(cumulativeSurvival * 1000) / 1000,
      expectedCost: Math.round(expectedCost)
    });
  }
  
  const totalExpectedFailureCost = annualExpectedCosts.reduce((sum, y) => sum + y.expectedCost, 0);
  
  return {
    annualBreakdown: annualExpectedCosts,
    totalExpectedCost: Math.round(totalExpectedFailureCost),
    avgAnnualExpectedCost: Math.round(totalExpectedFailureCost / horizon)
  };
}
