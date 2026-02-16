/**
 * F. Enhanced Life-Cycle Cost Analysis
 * ASTM E917 compliant with EAC, probabilistic NPV, and Monte Carlo
 * Reference: https://www.astm.org/e0917-17e01.html
 */

/**
 * Present value calculation with escalation
 */
export function presentValue(futureValue, discountRate, year) {
  return futureValue / Math.pow(1 + discountRate, year);
}

/**
 * Present value of annuity (equal payments)
 */
export function presentValueAnnuity(annualPayment, discountRate, years) {
  if (discountRate === 0) return annualPayment * years;
  return annualPayment * (1 - Math.pow(1 + discountRate, -years)) / discountRate;
}

/**
 * Present value of escalating annuity
 */
export function presentValueEscalatingAnnuity(initialPayment, discountRate, escalationRate, years) {
  if (discountRate === escalationRate) return initialPayment * years / (1 + discountRate);
  
  const effectiveRate = (1 + discountRate) / (1 + escalationRate) - 1;
  return initialPayment * (1 - Math.pow(1 + effectiveRate, -years)) / effectiveRate / (1 + discountRate);
}

/**
 * Equivalent Annual Cost (EAC) - annualizes NPV for comparison across different lifespans
 */
export function equivalentAnnualCost(npv, discountRate, years) {
  if (years === 0) return 0;
  if (discountRate === 0) return npv / years;
  
  const annuityFactor = (1 - Math.pow(1 + discountRate, -years)) / discountRate;
  return npv / annuityFactor;
}

/**
 * Capital Recovery Factor
 */
export function capitalRecoveryFactor(discountRate, years) {
  if (years === 0) return 0;
  if (discountRate === 0) return 1 / years;
  return (discountRate * Math.pow(1 + discountRate, years)) / (Math.pow(1 + discountRate, years) - 1);
}

/**
 * F1. Comprehensive LCC for "Keep" scenario
 */
export function computeKeepLCC(params) {
  const {
    currentAge,
    energyCostPerYear,
    maintenanceCostPerYear,
    failureProbabilities,
    failureEventCost,
    discountRate,
    energyEscalation,
    maintenanceEscalation,
    horizon
  } = params;
  
  const annualCosts = [];
  let pvTotal = 0;
  let cumulativeSurvival = 1;
  
  for (let year = 1; year <= horizon; year++) {
    const ageFactor = 1 + 0.02 * (currentAge + year - 1);
    
    const escalatedEnergyCost = energyCostPerYear * Math.pow(1 + energyEscalation, year - 1) * ageFactor;
    const escalatedMaintCost = maintenanceCostPerYear * Math.pow(1 + maintenanceEscalation, year - 1) * ageFactor;
    
    const pFailYear = failureProbabilities[`year${year}`] || 
      failureProbabilities.p1y * (1 + 0.1 * (year - 1));
    const expectedFailureCost = pFailYear * failureEventCost * cumulativeSurvival;
    cumulativeSurvival *= (1 - pFailYear);
    
    const totalYearCost = escalatedEnergyCost + escalatedMaintCost + expectedFailureCost;
    const pvYearCost = presentValue(totalYearCost, discountRate, year);
    pvTotal += pvYearCost;
    
    annualCosts.push({
      year,
      energyCost: Math.round(escalatedEnergyCost),
      maintenanceCost: Math.round(escalatedMaintCost),
      expectedFailureCost: Math.round(expectedFailureCost),
      totalCost: Math.round(totalYearCost),
      pvCost: Math.round(pvYearCost),
      cumulativeSurvival: Math.round(cumulativeSurvival * 1000) / 1000
    });
  }
  
  const eac = equivalentAnnualCost(pvTotal, discountRate, horizon);
  
  return {
    scenario: 'keep',
    initialCost: 0,
    pvOperatingCosts: Math.round(pvTotal),
    pvTotal: Math.round(pvTotal),
    eac: Math.round(eac),
    annualCosts,
    horizon,
    discountRate
  };
}

/**
 * F1b. Comprehensive LCC for "Replace" scenario
 */
export function computeReplaceLCC(params) {
  const {
    capex,
    newEquipmentLife,
    newEnergyCostPerYear,
    newMaintenanceCostPerYear,
    newFailureProbability,
    failureEventCost,
    discountRate,
    energyEscalation,
    maintenanceEscalation,
    horizon,
    salvageValuePct = 0,
    warrantyYears = 1
  } = params;
  
  const annualCosts = [];
  let pvOperating = 0;
  let cumulativeSurvival = 1;
  
  for (let year = 1; year <= horizon; year++) {
    const equipmentAge = year;
    const ageFactor = 1 + 0.01 * equipmentAge;
    
    const escalatedEnergyCost = newEnergyCostPerYear * Math.pow(1 + energyEscalation, year - 1) * ageFactor;
    
    let escalatedMaintCost = newMaintenanceCostPerYear * Math.pow(1 + maintenanceEscalation, year - 1) * ageFactor;
    if (year <= warrantyYears) {
      escalatedMaintCost *= 0.3;
    }
    
    const pFailYear = newFailureProbability * (1 + 0.05 * Math.max(0, equipmentAge - 3));
    const expectedFailureCost = pFailYear * failureEventCost * cumulativeSurvival;
    cumulativeSurvival *= (1 - pFailYear);
    
    const totalYearCost = escalatedEnergyCost + escalatedMaintCost + expectedFailureCost;
    const pvYearCost = presentValue(totalYearCost, discountRate, year);
    pvOperating += pvYearCost;
    
    annualCosts.push({
      year,
      energyCost: Math.round(escalatedEnergyCost),
      maintenanceCost: Math.round(escalatedMaintCost),
      expectedFailureCost: Math.round(expectedFailureCost),
      totalCost: Math.round(totalYearCost),
      pvCost: Math.round(pvYearCost),
      cumulativeSurvival: Math.round(cumulativeSurvival * 1000) / 1000
    });
  }
  
  const salvageValue = capex * salvageValuePct * Math.max(0, (newEquipmentLife - horizon) / newEquipmentLife);
  const pvSalvage = presentValue(salvageValue, discountRate, horizon);
  
  const pvTotal = capex + pvOperating - pvSalvage;
  const eac = equivalentAnnualCost(pvTotal, discountRate, horizon);
  
  return {
    scenario: 'replace',
    initialCost: capex,
    pvOperatingCosts: Math.round(pvOperating),
    pvSalvageValue: Math.round(pvSalvage),
    pvTotal: Math.round(pvTotal),
    eac: Math.round(eac),
    annualCosts,
    horizon,
    discountRate,
    warrantyYears,
    newEquipmentLife
  };
}

/**
 * F2. NPV comparison (Keep vs Replace)
 */
export function computeNPVComparison(keepLCC, replaceLCC) {
  const npv = keepLCC.pvTotal - replaceLCC.pvTotal;
  const eacSavings = keepLCC.eac - replaceLCC.eac;
  
  const annualSavings = keepLCC.annualCosts.map((k, i) => ({
    year: k.year,
    keepCost: k.totalCost,
    replaceCost: replaceLCC.annualCosts[i]?.totalCost || 0,
    savings: k.totalCost - (replaceLCC.annualCosts[i]?.totalCost || 0),
    cumulativeSavings: 0
  }));
  
  let cumulative = -replaceLCC.initialCost;
  annualSavings.forEach(s => {
    cumulative += s.savings;
    s.cumulativeSavings = Math.round(cumulative);
  });
  
  const paybackYear = annualSavings.findIndex(s => s.cumulativeSavings >= 0);
  const simplePayback = paybackYear >= 0 ? paybackYear + 1 : null;
  
  let discountedPayback = null;
  let discountedCumulative = -replaceLCC.initialCost;
  for (let i = 0; i < annualSavings.length; i++) {
    discountedCumulative += presentValue(annualSavings[i].savings, keepLCC.discountRate, i + 1);
    if (discountedCumulative >= 0 && discountedPayback === null) {
      discountedPayback = i + 1;
      break;
    }
  }
  
  const irr = computeIRR(replaceLCC.initialCost, annualSavings.map(s => s.savings));
  
  return {
    npv: Math.round(npv),
    npvPerCapexDollar: Math.round((npv / replaceLCC.initialCost) * 100) / 100,
    eacSavings: Math.round(eacSavings),
    simplePaybackYears: simplePayback,
    discountedPaybackYears: discountedPayback,
    irr: irr ? Math.round(irr * 1000) / 10 : null,
    annualSavings,
    recommendation: npv > 0 ? 'REPLACE' : 'KEEP',
    confidenceLevel: getConfidenceLevel(npv, replaceLCC.initialCost)
  };
}

function computeIRR(initialCost, cashFlows, maxIterations = 100) {
  let low = -0.5;
  let high = 2.0;
  
  const npvAtRate = (rate) => {
    let npv = -initialCost;
    cashFlows.forEach((cf, i) => {
      npv += cf / Math.pow(1 + rate, i + 1);
    });
    return npv;
  };
  
  if (npvAtRate(high) > 0) return high;
  if (npvAtRate(low) < 0) return null;
  
  for (let i = 0; i < maxIterations; i++) {
    const mid = (low + high) / 2;
    const npv = npvAtRate(mid);
    
    if (Math.abs(npv) < 1) return mid;
    if (npv > 0) low = mid;
    else high = mid;
  }
  
  return (low + high) / 2;
}

function getConfidenceLevel(npv, capex) {
  const ratio = npv / capex;
  if (ratio > 0.5) return 'high';
  if (ratio > 0.2) return 'medium';
  if (ratio > 0) return 'low';
  return 'negative';
}

/**
 * F3. Monte Carlo simulation for probabilistic NPV
 */
export function monteCarloNPV(params, iterations = 1000) {
  const {
    baseKeepParams,
    baseReplaceParams,
    uncertaintyRanges
  } = params;
  
  const results = [];
  
  for (let i = 0; i < iterations; i++) {
    const perturbedKeepParams = { ...baseKeepParams };
    const perturbedReplaceParams = { ...baseReplaceParams };
    
    if (uncertaintyRanges.energyCost) {
      const factor = 1 + (Math.random() - 0.5) * 2 * uncertaintyRanges.energyCost;
      perturbedKeepParams.energyCostPerYear *= factor;
      perturbedReplaceParams.newEnergyCostPerYear *= factor;
    }
    
    if (uncertaintyRanges.maintenanceCost) {
      const factor = 1 + (Math.random() - 0.5) * 2 * uncertaintyRanges.maintenanceCost;
      perturbedKeepParams.maintenanceCostPerYear *= factor;
      perturbedReplaceParams.newMaintenanceCostPerYear *= factor;
    }
    
    if (uncertaintyRanges.failureProbability) {
      const factor = 1 + (Math.random() - 0.5) * 2 * uncertaintyRanges.failureProbability;
      Object.keys(perturbedKeepParams.failureProbabilities).forEach(key => {
        perturbedKeepParams.failureProbabilities[key] *= factor;
      });
    }
    
    if (uncertaintyRanges.efficiencyGain) {
      const efficiency = baseReplaceParams.efficiencyGain * (1 + (Math.random() - 0.5) * 2 * uncertaintyRanges.efficiencyGain);
      perturbedReplaceParams.newEnergyCostPerYear = baseKeepParams.energyCostPerYear * (1 - efficiency);
    }
    
    const keepLCC = computeKeepLCC(perturbedKeepParams);
    const replaceLCC = computeReplaceLCC(perturbedReplaceParams);
    const npv = keepLCC.pvTotal - replaceLCC.pvTotal;
    
    results.push(npv);
  }
  
  results.sort((a, b) => a - b);
  
  const mean = results.reduce((a, b) => a + b, 0) / results.length;
  const variance = results.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / results.length;
  const stdDev = Math.sqrt(variance);
  
  const p05 = results[Math.floor(iterations * 0.05)];
  const p25 = results[Math.floor(iterations * 0.25)];
  const p50 = results[Math.floor(iterations * 0.50)];
  const p75 = results[Math.floor(iterations * 0.75)];
  const p95 = results[Math.floor(iterations * 0.95)];
  
  const positiveCount = results.filter(npv => npv > 0).length;
  const pNPVPositive = positiveCount / iterations;
  
  return {
    iterations,
    mean: Math.round(mean),
    stdDev: Math.round(stdDev),
    percentiles: {
      p05: Math.round(p05),
      p25: Math.round(p25),
      p50: Math.round(p50),
      p75: Math.round(p75),
      p95: Math.round(p95)
    },
    pNPVPositive: Math.round(pNPVPositive * 100) / 100,
    riskAssessment: pNPVPositive >= 0.9 ? 'low_risk' :
                    pNPVPositive >= 0.7 ? 'moderate_risk' :
                    pNPVPositive >= 0.5 ? 'balanced' : 'high_risk',
    valueAtRisk5: Math.round(p05),
    expectedShortfall5: Math.round(results.slice(0, Math.floor(iterations * 0.05)).reduce((a, b) => a + b, 0) / Math.floor(iterations * 0.05))
  };
}

/**
 * F4. Full economic evaluation combining all methods
 */
export function runEnhancedEconomicEvaluation(asset, features, replacementOption, economicAssumption, utilityRate, survivalAnalysis) {
  const horizon = economicAssumption.analysisHorizonYears || 10;
  const discountRate = economicAssumption.discountRate || 0.08;
  
  const kwhPerYear = (features.energy?.kwh_day || 100) * 365;
  const energyRate = utilityRate?.energyRateSchedule?.default || 0.12;
  const currentEnergyCost = kwhPerYear * energyRate;
  const currentMaintCost = features.maintenance?.maintenance_cost_365d || 2000;
  const failureEventCost = economicAssumption.failureEventCostByAssetType?.[asset.assetType] || 15000;
  
  const keepParams = {
    currentAge: asset.ageYears,
    energyCostPerYear: currentEnergyCost,
    maintenanceCostPerYear: currentMaintCost,
    failureProbabilities: survivalAnalysis?.failureProbabilities || { p1y: 0.1 },
    failureEventCost,
    discountRate,
    energyEscalation: utilityRate?.escalationRateAssumption || 0.03,
    maintenanceEscalation: 0.04,
    horizon
  };
  
  const efficiencyGain = replacementOption.expectedEfficiencyDelta || 0.15;
  const newEnergyCost = currentEnergyCost * (1 - efficiencyGain);
  const newMaintCost = Math.max(500, currentMaintCost + (replacementOption.expectedMaintenanceDeltaPerYear || -500));
  
  const replaceParams = {
    capex: replacementOption.capexInstalledCost,
    newEquipmentLife: replacementOption.expectedLifeYears || 15,
    newEnergyCostPerYear: newEnergyCost,
    newMaintenanceCostPerYear: newMaintCost,
    newFailureProbability: 0.02,
    failureEventCost,
    discountRate,
    energyEscalation: utilityRate?.escalationRateAssumption || 0.03,
    maintenanceEscalation: 0.03,
    horizon,
    salvageValuePct: 0.1,
    warrantyYears: replacementOption.warrantyYears || 1
  };
  
  const keepLCC = computeKeepLCC(keepParams);
  const replaceLCC = computeReplaceLCC(replaceParams);
  const comparison = computeNPVComparison(keepLCC, replaceLCC);
  
  const mcParams = {
    baseKeepParams: keepParams,
    baseReplaceParams: { ...replaceParams, efficiencyGain },
    uncertaintyRanges: {
      energyCost: 0.15,
      maintenanceCost: 0.25,
      failureProbability: 0.30,
      efficiencyGain: 0.20
    }
  };
  const mcResults = monteCarloNPV(mcParams, 500);
  
  return {
    option: {
      id: replacementOption.optionId,
      name: replacementOption.optionName,
      capex: replacementOption.capexInstalledCost
    },
    keepLCC,
    replaceLCC,
    comparison,
    monteCarlo: mcResults,
    summary: {
      npv: comparison.npv,
      npvP50: mcResults.percentiles.p50,
      pNpvPositive: mcResults.pNPVPositive,
      eacSavings: comparison.eacSavings,
      simplePayback: comparison.simplePaybackYears,
      discountedPayback: comparison.discountedPaybackYears,
      irr: comparison.irr,
      riskAssessment: mcResults.riskAssessment,
      recommendation: comparison.recommendation,
      confidenceLevel: mcResults.pNPVPositive >= 0.8 ? 'high' : mcResults.pNPVPositive >= 0.6 ? 'medium' : 'low'
    }
  };
}
