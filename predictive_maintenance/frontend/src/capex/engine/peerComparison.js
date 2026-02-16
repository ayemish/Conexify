import { cohortKeyToString, getCohortKey, ASSET_TYPES } from '../data/models.js';
import { FEATURE_NAMES } from './featureCalculator.js';

const GLOBAL_BASELINES = {
  [`${ASSET_TYPES.RTU}|4A|Grocery|0-3`]: {
    energy_kwh_day: { p05: 60, p25: 80, p50: 100, p75: 130, p95: 180, mean: 105, std: 35, n_assets: 1200 },
    maintenance_cost: { p05: 200, p25: 800, p50: 1500, p75: 2800, p95: 5000, mean: 1800, std: 1200, n_assets: 1200 },
    p_fail_90d: { p05: 0.01, p25: 0.02, p50: 0.04, p75: 0.08, p95: 0.15, mean: 0.05, std: 0.04, n_assets: 1200 }
  },
  [`${ASSET_TYPES.RTU}|4A|Grocery|3-7`]: {
    energy_kwh_day: { p05: 70, p25: 95, p50: 120, p75: 155, p95: 210, mean: 125, std: 40, n_assets: 1800 },
    maintenance_cost: { p05: 400, p25: 1200, p50: 2200, p75: 3800, p95: 6500, mean: 2500, std: 1500, n_assets: 1800 },
    p_fail_90d: { p05: 0.02, p25: 0.04, p50: 0.07, p75: 0.12, p95: 0.22, mean: 0.08, std: 0.06, n_assets: 1800 }
  },
  [`${ASSET_TYPES.RTU}|4A|Grocery|7-12`]: {
    energy_kwh_day: { p05: 85, p25: 115, p50: 145, p75: 185, p95: 250, mean: 150, std: 50, n_assets: 2200 },
    maintenance_cost: { p05: 800, p25: 1800, p50: 3200, p75: 5200, p95: 9000, mean: 3500, std: 2000, n_assets: 2200 },
    p_fail_90d: { p05: 0.04, p25: 0.08, p50: 0.12, p75: 0.20, p95: 0.35, mean: 0.14, std: 0.09, n_assets: 2200 }
  },
  [`${ASSET_TYPES.RTU}|4A|Grocery|12+`]: {
    energy_kwh_day: { p05: 100, p25: 140, p50: 180, p75: 230, p95: 320, mean: 190, std: 65, n_assets: 1500 },
    maintenance_cost: { p05: 1500, p25: 3000, p50: 5000, p75: 8000, p95: 14000, mean: 5500, std: 3000, n_assets: 1500 },
    p_fail_90d: { p05: 0.08, p25: 0.15, p50: 0.25, p75: 0.40, p95: 0.60, mean: 0.28, std: 0.15, n_assets: 1500 }
  },
  [`${ASSET_TYPES.COMPRESSOR_RACK}|4A|Grocery|0-3`]: {
    energy_kwh_day: { p05: 400, p25: 550, p50: 700, p75: 900, p95: 1200, mean: 720, std: 200, n_assets: 400 },
    maintenance_cost: { p05: 1000, p25: 2500, p50: 4500, p75: 7500, p95: 15000, mean: 5000, std: 3500, n_assets: 400 },
    p_fail_90d: { p05: 0.01, p25: 0.02, p50: 0.03, p75: 0.06, p95: 0.12, mean: 0.04, std: 0.03, n_assets: 400 }
  },
  [`${ASSET_TYPES.COMPRESSOR_RACK}|4A|Grocery|7-12`]: {
    energy_kwh_day: { p05: 500, p25: 700, p50: 900, p75: 1150, p95: 1500, mean: 920, std: 280, n_assets: 600 },
    maintenance_cost: { p05: 3000, p25: 6000, p50: 10000, p75: 16000, p95: 28000, mean: 11000, std: 6500, n_assets: 600 },
    p_fail_90d: { p05: 0.03, p25: 0.06, p50: 0.10, p75: 0.18, p95: 0.30, mean: 0.12, std: 0.08, n_assets: 600 }
  }
};

function generateBaselineForCohort(assetType, climateZone, storeType, ageBin) {
  const ageFactor = ageBin === '0-3' ? 1.0 : ageBin === '3-7' ? 1.2 : ageBin === '7-12' ? 1.5 : 2.0;
  const climateFactor = climateZone.startsWith('1') || climateZone.startsWith('2') ? 1.3 :
                        climateZone.startsWith('5') || climateZone.startsWith('6') ? 0.85 : 1.0;
  
  const baseEnergy = {
    [ASSET_TYPES.RTU]: 100,
    [ASSET_TYPES.COMPRESSOR_RACK]: 700,
    [ASSET_TYPES.WALK_IN_COOLER]: 45,
    [ASSET_TYPES.WALK_IN_FREEZER]: 80,
    [ASSET_TYPES.AHU]: 200,
    [ASSET_TYPES.REACH_IN_CASE]: 25
  }[assetType] || 100;
  
  const baseMaintenance = {
    [ASSET_TYPES.RTU]: 1500,
    [ASSET_TYPES.COMPRESSOR_RACK]: 5000,
    [ASSET_TYPES.WALK_IN_COOLER]: 1000,
    [ASSET_TYPES.WALK_IN_FREEZER]: 1500,
    [ASSET_TYPES.AHU]: 2500,
    [ASSET_TYPES.REACH_IN_CASE]: 600
  }[assetType] || 1500;
  
  const energyP50 = baseEnergy * ageFactor * climateFactor;
  const maintP50 = baseMaintenance * ageFactor;
  const failP50 = 0.04 * ageFactor;
  
  return {
    energy_kwh_day: {
      p05: energyP50 * 0.6, p25: energyP50 * 0.8, p50: energyP50, 
      p75: energyP50 * 1.3, p95: energyP50 * 1.8,
      mean: energyP50 * 1.05, std: energyP50 * 0.35, n_assets: 500
    },
    maintenance_cost: {
      p05: maintP50 * 0.15, p25: maintP50 * 0.5, p50: maintP50,
      p75: maintP50 * 1.7, p95: maintP50 * 3,
      mean: maintP50 * 1.1, std: maintP50 * 0.7, n_assets: 500
    },
    p_fail_90d: {
      p05: failP50 * 0.25, p25: failP50 * 0.5, p50: failP50,
      p75: failP50 * 1.6, p95: failP50 * 2.5,
      mean: failP50 * 1.1, std: failP50 * 0.5, n_assets: 500
    }
  };
}

export function getGlobalBaseline(cohortKey) {
  const key = cohortKeyToString(cohortKey);
  
  if (GLOBAL_BASELINES[key]) {
    return GLOBAL_BASELINES[key];
  }
  
  return generateBaselineForCohort(
    cohortKey.assetType,
    cohortKey.climateZone,
    cohortKey.storeType,
    cohortKey.ageBin
  );
}

export function computePeerPercentile(value, distribution) {
  if (!distribution || value === undefined || value === null) return 50;
  
  const { p05, p25, p50, p75, p95 } = distribution;
  
  if (value <= p05) return 5;
  if (value <= p25) return 5 + ((value - p05) / (p25 - p05)) * 20;
  if (value <= p50) return 25 + ((value - p25) / (p50 - p25)) * 25;
  if (value <= p75) return 50 + ((value - p50) / (p75 - p50)) * 25;
  if (value <= p95) return 75 + ((value - p75) / (p95 - p75)) * 20;
  return 95 + Math.min(5, ((value - p95) / p95) * 5);
}

export function computeRobustZScore(value, distribution) {
  if (!distribution) return 0;
  
  const mad = (distribution.p75 - distribution.p25) / 1.349;
  if (mad === 0) return 0;
  
  return (value - distribution.p50) / mad;
}

export function computePeerComparison(asset, store, features) {
  const cohortKey = getCohortKey(asset, store);
  const baseline = getGlobalBaseline(cohortKey);
  
  const energyValue = features.energy[FEATURE_NAMES.KWH_DAY];
  const maintValue = features.maintenance[FEATURE_NAMES.MAINTENANCE_COST_365D];
  const failValue = features.reliability[FEATURE_NAMES.P_FAIL_90D];
  
  const energyPercentile = computePeerPercentile(energyValue, baseline.energy_kwh_day);
  const maintPercentile = computePeerPercentile(maintValue, baseline.maintenance_cost);
  const failPercentile = computePeerPercentile(failValue, baseline.p_fail_90d);
  
  const energyZScore = computeRobustZScore(energyValue, baseline.energy_kwh_day);
  const maintZScore = computeRobustZScore(maintValue, baseline.maintenance_cost);
  const failZScore = computeRobustZScore(failValue, baseline.p_fail_90d);
  
  const overallPercentile = (energyPercentile * 0.35 + maintPercentile * 0.25 + failPercentile * 0.40);
  
  return {
    cohortKey,
    cohortKeyString: cohortKeyToString(cohortKey),
    baseline,
    peerComparison: {
      energyWaste: {
        value: energyValue,
        percentile: Math.round(energyPercentile),
        zScore: Math.round(energyZScore * 100) / 100,
        peerMedian: baseline.energy_kwh_day.p50,
        distanceFromMedian: Math.round((energyValue - baseline.energy_kwh_day.p50) * 100) / 100
      },
      maintenanceBurden: {
        value: maintValue,
        percentile: Math.round(maintPercentile),
        zScore: Math.round(maintZScore * 100) / 100,
        peerMedian: baseline.maintenance_cost.p50,
        distanceFromMedian: Math.round(maintValue - baseline.maintenance_cost.p50)
      },
      failureRisk: {
        value: failValue,
        percentile: Math.round(failPercentile),
        zScore: Math.round(failZScore * 100) / 100,
        peerMedian: baseline.p_fail_90d.p50,
        distanceFromMedian: Math.round((failValue - baseline.p_fail_90d.p50) * 100) / 100
      },
      overall: {
        percentile: Math.round(overallPercentile),
        nPeers: baseline.energy_kwh_day.n_assets
      }
    }
  };
}

export function rankAssetsInStore(assetsWithScores) {
  const sorted = [...assetsWithScores].sort((a, b) => 
    b.score.replacePriorityScore - a.score.replacePriorityScore
  );
  
  return sorted.map((item, idx) => ({
    ...item,
    rankInStore: idx + 1
  }));
}
