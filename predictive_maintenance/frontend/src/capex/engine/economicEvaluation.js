import { FEATURE_NAMES } from './featureCalculator.js';
import { DECISION_TYPES, createCapexPlanItem } from '../data/models.js';

export function computePresentValue(annualCashFlows, discountRate) {
  return annualCashFlows.reduce((pv, cf, year) => {
    return pv + cf / Math.pow(1 + discountRate, year + 1);
  }, 0);
}

export function computeNPV(initialCost, annualBenefits, discountRate, years) {
  const pvBenefits = computePresentValue(annualBenefits, discountRate);
  return pvBenefits - initialCost;
}

export function computeSimplePayback(initialCost, annualSavings) {
  if (annualSavings <= 0) return Infinity;
  return initialCost / annualSavings;
}

export function computeIRR(initialCost, annualCashFlows, maxIterations = 100) {
  let low = -0.99;
  let high = 5.0;
  
  for (let i = 0; i < maxIterations; i++) {
    const mid = (low + high) / 2;
    const npv = computeNPV(initialCost, annualCashFlows, mid, annualCashFlows.length);
    
    if (Math.abs(npv) < 0.01) return mid;
    if (npv > 0) low = mid;
    else high = mid;
  }
  
  return (low + high) / 2;
}

export function computeKeepCosts(asset, features, economicAssumption, utilityRate, years) {
  const kwhPerDay = features.energy[FEATURE_NAMES.KWH_DAY];
  const kwhPerYear = kwhPerDay * 365;
  const energyRate = utilityRate.energyRateSchedule.default || 0.12;
  const escalationRate = utilityRate.escalationRateAssumption || 0.03;
  
  const currentMaintCost = features.maintenance[FEATURE_NAMES.MAINTENANCE_COST_365D];
  const maintEscalation = 0.05;
  
  const pFail90d = features.reliability[FEATURE_NAMES.P_FAIL_90D];
  const pFailYear = 1 - Math.pow(1 - pFail90d, 4);
  const failureCost = economicAssumption.failureEventCostByAssetType[asset.assetType] || 15000;
  
  const annualCosts = [];
  
  for (let year = 0; year < years; year++) {
    const ageFactor = 1 + (year * 0.03);
    
    const energyCost = kwhPerYear * energyRate * Math.pow(1 + escalationRate, year) * ageFactor;
    const maintCost = currentMaintCost * Math.pow(1 + maintEscalation, year) * ageFactor;
    const expectedFailureCost = pFailYear * failureCost * ageFactor;
    
    annualCosts.push({
      year: year + 1,
      energyCost: Math.round(energyCost),
      maintenanceCost: Math.round(maintCost),
      expectedFailureCost: Math.round(expectedFailureCost),
      total: Math.round(energyCost + maintCost + expectedFailureCost)
    });
  }
  
  return annualCosts;
}

export function computeReplaceCosts(asset, features, replacementOption, economicAssumption, utilityRate, years) {
  const currentKwhPerDay = features.energy[FEATURE_NAMES.KWH_DAY];
  const efficiencyImprovement = replacementOption.expectedEfficiencyDelta;
  const newKwhPerDay = currentKwhPerDay * (1 - efficiencyImprovement);
  const kwhPerYear = newKwhPerDay * 365;
  
  const energyRate = utilityRate.energyRateSchedule.default || 0.12;
  const escalationRate = utilityRate.escalationRateAssumption || 0.03;
  
  const currentMaintCost = features.maintenance[FEATURE_NAMES.MAINTENANCE_COST_365D];
  const maintReduction = replacementOption.expectedMaintenanceDeltaPerYear;
  const newMaintCost = Math.max(200, currentMaintCost + maintReduction);
  const maintEscalation = 0.03;
  
  const newFailureRate = 0.02;
  const failureCost = economicAssumption.failureEventCostByAssetType[asset.assetType] || 15000;
  
  const annualCosts = [];
  
  for (let year = 0; year < years; year++) {
    const ageFactor = 1 + (year * 0.01);
    
    const energyCost = kwhPerYear * energyRate * Math.pow(1 + escalationRate, year) * ageFactor;
    const maintCost = newMaintCost * Math.pow(1 + maintEscalation, year) * ageFactor;
    const expectedFailureCost = newFailureRate * failureCost * ageFactor;
    
    annualCosts.push({
      year: year + 1,
      energyCost: Math.round(energyCost),
      maintenanceCost: Math.round(maintCost),
      expectedFailureCost: Math.round(expectedFailureCost),
      total: Math.round(energyCost + maintCost + expectedFailureCost)
    });
  }
  
  return annualCosts;
}

export function evaluateReplacementOption(asset, features, replacementOption, economicAssumption, utilityRate) {
  const years = economicAssumption.analysisHorizonYears;
  const discountRate = economicAssumption.discountRate;
  
  const keepCosts = computeKeepCosts(asset, features, economicAssumption, utilityRate, years);
  const replaceCosts = computeReplaceCosts(asset, features, replacementOption, economicAssumption, utilityRate, years);
  
  const pvKeep = computePresentValue(keepCosts.map(c => c.total), discountRate);
  const pvReplace = computePresentValue(replaceCosts.map(c => c.total), discountRate);
  const capex = replacementOption.capexInstalledCost;
  
  const npv = pvKeep - pvReplace - capex;
  
  const annualSavings = keepCosts.map((kc, i) => kc.total - replaceCosts[i].total);
  const avgAnnualSavings = annualSavings.reduce((a, b) => a + b, 0) / annualSavings.length;
  const simplePayback = computeSimplePayback(capex, avgAnnualSavings);
  
  let irr = null;
  if (avgAnnualSavings > 0) {
    irr = computeIRR(capex, annualSavings);
  }
  
  const npvPositiveProbability = npv > 0 ? 
    Math.min(0.95, 0.5 + (npv / capex) * 0.3) : 
    Math.max(0.05, 0.5 + (npv / capex) * 0.3);
  
  return {
    optionId: replacementOption.optionId,
    optionName: replacementOption.optionName,
    capex,
    pvKeep: Math.round(pvKeep),
    pvReplace: Math.round(pvReplace),
    npv: Math.round(npv),
    npvPerCapexDollar: Math.round((npv / capex) * 100) / 100,
    simplePaybackYears: Math.round(simplePayback * 10) / 10,
    irr: irr ? Math.round(irr * 1000) / 10 : null,
    avgAnnualSavings: Math.round(avgAnnualSavings),
    firstYearSavings: annualSavings[0],
    pNpvPositive: Math.round(npvPositiveProbability * 100) / 100,
    keepCosts,
    replaceCosts,
    annualSavings
  };
}

export function evaluateAllOptions(asset, features, replacementOptions, economicAssumption, utilityRate) {
  const evaluations = replacementOptions.map(option => 
    evaluateReplacementOption(asset, features, option, economicAssumption, utilityRate)
  );
  
  evaluations.sort((a, b) => b.npv - a.npv);
  
  return evaluations;
}

export function recommendDecision(asset, score, bestOption) {
  if (!score.isScoreable) {
    return {
      decision: DECISION_TYPES.INSPECT,
      reason: 'Insufficient data coverage for reliable scoring'
    };
  }
  
  if (score.replacePriorityScore >= 70 && bestOption && bestOption.npv > 0) {
    return {
      decision: DECISION_TYPES.REPLACE,
      reason: `High priority score (${score.replacePriorityScore}) with positive NPV ($${bestOption.npv.toLocaleString()})`
    };
  }
  
  if (score.riskScore >= 60 && score.conditionScore <= 40) {
    return {
      decision: DECISION_TYPES.REPLACE,
      reason: `High risk (${score.riskScore}) and poor condition (${score.conditionScore})`
    };
  }
  
  if (score.replacePriorityScore >= 50 && score.replacePriorityScore < 70) {
    if (bestOption && bestOption.npv > 0 && bestOption.simplePaybackYears <= 5) {
      return {
        decision: DECISION_TYPES.REPLACE,
        reason: `Moderate priority with good payback (${bestOption.simplePaybackYears} years)`
      };
    }
    return {
      decision: DECISION_TYPES.INSPECT,
      reason: `Moderate priority score (${score.replacePriorityScore}) - recommend inspection`
    };
  }
  
  if (asset.ageYears >= 15 && score.conditionScore <= 60) {
    return {
      decision: DECISION_TYPES.INSPECT,
      reason: `Age (${asset.ageYears} years) warrants inspection`
    };
  }
  
  return {
    decision: DECISION_TYPES.DEFER,
    reason: `Low priority score (${score.replacePriorityScore}) - continue monitoring`
  };
}

export function createPlanItem(asset, score, peerComparison, optionEvaluations, recommendation, rankInStore) {
  const bestOption = optionEvaluations[0];
  
  return createCapexPlanItem({
    planId: null,
    assetId: asset.assetId,
    decision: recommendation.decision,
    selectedOptionId: recommendation.decision === DECISION_TYPES.REPLACE ? bestOption?.optionId : null,
    capexCost: recommendation.decision === DECISION_TYPES.REPLACE ? bestOption?.capex || 0 : 0,
    npvP50: bestOption?.npv || 0,
    pNpvPositive: bestOption?.pNpvPositive || 0,
    peerPercentile: peerComparison.peerComparison.overall.percentile,
    rankInStore
  });
}
