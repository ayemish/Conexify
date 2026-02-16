import { CANONICAL_METRICS, createAssetFeatureDaily, createAssetScoreDaily } from '../data/models.js';

export const FEATURE_NAMES = {
  COVERAGE_PCT: 'coverage_pct',
  KWH_DAY: 'kwh_day',
  KW_MEAN: 'kw_mean',
  KW_PEAK: 'kw_peak',
  RUNTIME_HOURS_DAY: 'runtime_hours_day',
  KWH_PER_RUNTIME_HOUR: 'kwh_per_runtime_hour',
  KWH_PER_CDD: 'kwh_per_cooling_degree_day',
  BASELOAD_KW: 'baseload_kw',
  TREND_KW_VS_OAT: 'trend_kw_at_similar_oat',
  RESIDUAL_ENERGY_VS_PEER: 'residual_energy_vs_peer_baseline',
  SHORT_CYCLE_RATE: 'short_cycle_rate',
  CONTROL_HUNTING_INDEX: 'control_hunting_index',
  ANOMALY_MINUTES_DAY: 'anomaly_minutes_day',
  ALARM_COUNT_DAY: 'alarm_count_day',
  P_FAIL_30D: 'p_fail_30d',
  P_FAIL_90D: 'p_fail_90d',
  WORK_ORDERS_90D: 'work_orders_90d',
  WORK_ORDERS_365D: 'work_orders_365d',
  MAINTENANCE_COST_365D: 'maintenance_cost_365d',
  DOWNTIME_HOURS_365D: 'downtime_hours_365d',
  COST_PER_RUNTIME_HOUR: 'cost_per_runtime_hour'
};

function mean(arr) {
  if (arr.length === 0) return 0;
  return arr.reduce((a, b) => a + b, 0) / arr.length;
}

function max(arr) {
  if (arr.length === 0) return 0;
  return Math.max(...arr);
}

function percentile(arr, p) {
  if (arr.length === 0) return 0;
  const sorted = [...arr].sort((a, b) => a - b);
  const idx = Math.floor((p / 100) * sorted.length);
  return sorted[Math.min(idx, sorted.length - 1)];
}

function std(arr) {
  if (arr.length <= 1) return 0;
  const m = mean(arr);
  return Math.sqrt(arr.reduce((acc, val) => acc + Math.pow(val - m, 2), 0) / arr.length);
}

function linearRegression(x, y) {
  const n = x.length;
  if (n === 0) return { slope: 0, intercept: 0 };
  
  const sumX = x.reduce((a, b) => a + b, 0);
  const sumY = y.reduce((a, b) => a + b, 0);
  const sumXY = x.reduce((acc, xi, i) => acc + xi * y[i], 0);
  const sumXX = x.reduce((acc, xi) => acc + xi * xi, 0);
  
  const denom = n * sumXX - sumX * sumX;
  if (denom === 0) return { slope: 0, intercept: mean(y) };
  
  const slope = (n * sumXY - sumX * sumY) / denom;
  const intercept = (sumY - slope * sumX) / n;
  
  return { slope, intercept };
}

export function computeDataQualityFeatures(telemetryReadings, expectedSamplesPerDay = 288) {
  const days = {};
  
  telemetryReadings.forEach(r => {
    const date = r.ts.split('T')[0];
    if (!days[date]) days[date] = { count: 0, good: 0, imputed: 0, outlier: 0 };
    days[date].count++;
    if (r.qualityFlag === 'good') days[date].good++;
    else if (r.qualityFlag === 'imputed') days[date].imputed++;
    else if (r.qualityFlag === 'outlier') days[date].outlier++;
  });
  
  const coverages = Object.values(days).map(d => (d.count / expectedSamplesPerDay) * 100);
  const imputationRates = Object.values(days).map(d => d.count > 0 ? (d.imputed / d.count) * 100 : 0);
  
  return {
    [FEATURE_NAMES.COVERAGE_PCT]: mean(coverages),
    gapRate: 100 - mean(coverages),
    imputationRate: mean(imputationRates),
    isScoreable: mean(coverages) >= 85
  };
}

export function computeEnergyFeatures(telemetryReadings, weatherObservations) {
  const powerReadings = telemetryReadings.filter(r => r.metric === CANONICAL_METRICS.POWER_KW);
  const runtimeReadings = telemetryReadings.filter(r => r.metric === CANONICAL_METRICS.RUNTIME_HOURS);
  
  const dailyPower = {};
  powerReadings.forEach(r => {
    const date = r.ts.split('T')[0];
    if (!dailyPower[date]) dailyPower[date] = [];
    dailyPower[date].push(r.value);
  });
  
  const dailyRuntime = {};
  runtimeReadings.forEach(r => {
    const date = r.ts.split('T')[0];
    dailyRuntime[date] = r.value;
  });
  
  const dailyWeather = {};
  weatherObservations.forEach(w => {
    const date = w.ts.split('T')[0];
    dailyWeather[date] = w.oatC;
  });
  
  const kwhPerDay = Object.entries(dailyPower).map(([date, powers]) => {
    const avgKw = mean(powers);
    const runtime = dailyRuntime[date] || 12;
    return avgKw * runtime;
  });
  
  const kwMeans = Object.values(dailyPower).map(p => mean(p));
  const kwPeaks = Object.values(dailyPower).map(p => max(p));
  const runtimes = Object.values(dailyRuntime);
  
  const kwhPerRuntime = kwhPerDay.length > 0 && runtimes.length > 0 
    ? mean(kwhPerDay) / Math.max(1, mean(runtimes)) 
    : 0;
  
  const oats = [];
  const kws = [];
  Object.entries(dailyPower).forEach(([date, powers]) => {
    if (dailyWeather[date]) {
      oats.push(dailyWeather[date]);
      kws.push(mean(powers));
    }
  });
  
  const cdd = oats.filter(t => t > 18).map(t => t - 18);
  const totalCdd = cdd.reduce((a, b) => a + b, 0) || 1;
  const totalKwh = kwhPerDay.reduce((a, b) => a + b, 0);
  
  const trendResult = linearRegression(oats, kws);
  
  const nightPowers = powerReadings
    .filter(r => {
      const hour = new Date(r.ts).getHours();
      return hour >= 0 && hour <= 5;
    })
    .map(r => r.value);
  
  return {
    [FEATURE_NAMES.KWH_DAY]: mean(kwhPerDay),
    [FEATURE_NAMES.KW_MEAN]: mean(kwMeans),
    [FEATURE_NAMES.KW_PEAK]: mean(kwPeaks),
    [FEATURE_NAMES.RUNTIME_HOURS_DAY]: mean(runtimes),
    [FEATURE_NAMES.KWH_PER_RUNTIME_HOUR]: kwhPerRuntime,
    [FEATURE_NAMES.KWH_PER_CDD]: totalKwh / totalCdd,
    [FEATURE_NAMES.BASELOAD_KW]: percentile(nightPowers, 50),
    [FEATURE_NAMES.TREND_KW_VS_OAT]: trendResult.slope
  };
}

export function computeReliabilityFeatures(telemetryReadings, asset) {
  const startsReadings = telemetryReadings.filter(r => r.metric === CANONICAL_METRICS.STARTS_COUNT);
  const dailyStarts = {};
  startsReadings.forEach(r => {
    const date = r.ts.split('T')[0];
    if (!dailyStarts[date]) dailyStarts[date] = 0;
    dailyStarts[date] = Math.max(dailyStarts[date], r.value);
  });
  
  const avgStartsPerDay = mean(Object.values(dailyStarts));
  const shortCycleRate = avgStartsPerDay > 10 ? (avgStartsPerDay - 10) / 10 : 0;
  
  const tempReadings = telemetryReadings.filter(r => 
    r.metric === CANONICAL_METRICS.ZONE_TEMP_C || 
    r.metric === CANONICAL_METRICS.SUPPLY_TEMP_C
  );
  
  let huntingIndex = 0;
  if (tempReadings.length > 10) {
    const temps = tempReadings.map(r => r.value);
    const diffs = temps.slice(1).map((t, i) => Math.abs(t - temps[i]));
    huntingIndex = mean(diffs) / (std(temps) || 1);
  }
  
  const baseFailureRate = 0.02;
  const ageFactor = 1 + (asset.ageYears * 0.08);
  const conditionFactor = 1 + (shortCycleRate * 0.3) + (huntingIndex * 0.2);
  
  const pFail30d = Math.min(0.95, baseFailureRate * ageFactor * conditionFactor * 30 / 365);
  const pFail90d = Math.min(0.95, baseFailureRate * ageFactor * conditionFactor * 90 / 365);
  
  return {
    [FEATURE_NAMES.SHORT_CYCLE_RATE]: shortCycleRate,
    [FEATURE_NAMES.CONTROL_HUNTING_INDEX]: huntingIndex,
    [FEATURE_NAMES.ANOMALY_MINUTES_DAY]: Math.round(shortCycleRate * 30 + huntingIndex * 20),
    [FEATURE_NAMES.ALARM_COUNT_DAY]: Math.round(shortCycleRate * 2 + huntingIndex),
    [FEATURE_NAMES.P_FAIL_30D]: Math.round(pFail30d * 100) / 100,
    [FEATURE_NAMES.P_FAIL_90D]: Math.round(pFail90d * 100) / 100
  };
}

export function computeMaintenanceFeatures(workOrders) {
  const now = new Date();
  const d90Ago = new Date(now);
  d90Ago.setDate(d90Ago.getDate() - 90);
  const d365Ago = new Date(now);
  d365Ago.setDate(d365Ago.getDate() - 365);
  
  const wo90d = workOrders.filter(wo => new Date(wo.openTs) >= d90Ago);
  const wo365d = workOrders.filter(wo => new Date(wo.openTs) >= d365Ago);
  
  const cost365d = wo365d.reduce((sum, wo) => sum + (wo.costTotal || 0), 0);
  const downtime365d = wo365d.reduce((sum, wo) => sum + (wo.downtimeHours || 0), 0);
  
  return {
    [FEATURE_NAMES.WORK_ORDERS_90D]: wo90d.length,
    [FEATURE_NAMES.WORK_ORDERS_365D]: wo365d.length,
    [FEATURE_NAMES.MAINTENANCE_COST_365D]: cost365d,
    [FEATURE_NAMES.DOWNTIME_HOURS_365D]: downtime365d,
    [FEATURE_NAMES.COST_PER_RUNTIME_HOUR]: cost365d / Math.max(1, 365 * 12)
  };
}

export function computeAllFeatures(asset, telemetryReadings, weatherObservations, workOrders) {
  const dataQuality = computeDataQualityFeatures(telemetryReadings);
  const energy = computeEnergyFeatures(telemetryReadings, weatherObservations);
  const reliability = computeReliabilityFeatures(telemetryReadings, asset);
  const maintenance = computeMaintenanceFeatures(workOrders);
  
  return {
    assetId: asset.assetId,
    date: new Date().toISOString().split('T')[0],
    isScoreable: dataQuality.isScoreable,
    dataQuality,
    energy,
    reliability,
    maintenance
  };
}

export function computeAssetScore(features, peerBaseline) {
  const normalize = (value, p50, std) => {
    if (!std || std === 0) return 50;
    const zScore = (value - p50) / std;
    return Math.max(0, Math.min(100, 50 + zScore * 20));
  };
  
  const energyWasteScore = normalize(
    features.energy[FEATURE_NAMES.KWH_DAY],
    peerBaseline?.energy_kwh_day?.p50 || features.energy[FEATURE_NAMES.KWH_DAY],
    peerBaseline?.energy_kwh_day?.std || 10
  );
  
  const riskScore = Math.min(100, features.reliability[FEATURE_NAMES.P_FAIL_90D] * 100 * 1.5);
  
  const conditionScore = 100 - (
    (features.reliability[FEATURE_NAMES.SHORT_CYCLE_RATE] * 20) +
    (features.reliability[FEATURE_NAMES.CONTROL_HUNTING_INDEX] * 15) +
    (Math.min(features.maintenance[FEATURE_NAMES.WORK_ORDERS_365D], 10) * 3)
  );
  
  const maintenanceBurden = normalize(
    features.maintenance[FEATURE_NAMES.MAINTENANCE_COST_365D],
    peerBaseline?.maintenance_cost?.p50 || 2000,
    peerBaseline?.maintenance_cost?.std || 1500
  );
  
  const replacePriorityScore = Math.round(
    (100 - conditionScore) * 0.3 +
    energyWasteScore * 0.25 +
    riskScore * 0.3 +
    maintenanceBurden * 0.15
  );
  
  const explainTopDrivers = [];
  if (riskScore > 60) explainTopDrivers.push(`High failure risk (${Math.round(features.reliability[FEATURE_NAMES.P_FAIL_90D] * 100)}% in 90d)`);
  if (energyWasteScore > 60) explainTopDrivers.push(`Energy waste above peer median`);
  if (features.reliability[FEATURE_NAMES.SHORT_CYCLE_RATE] > 0.5) explainTopDrivers.push(`Short cycling detected`);
  if (features.maintenance[FEATURE_NAMES.WORK_ORDERS_365D] > 5) explainTopDrivers.push(`High work order frequency`);
  if (conditionScore < 50) explainTopDrivers.push(`Poor condition indicators`);
  
  return createAssetScoreDaily({
    assetId: features.assetId,
    date: features.date,
    conditionScore: Math.round(Math.max(0, Math.min(100, conditionScore))),
    energyWasteScore: Math.round(energyWasteScore),
    riskScore: Math.round(riskScore),
    replacePriorityScore: Math.round(Math.max(0, Math.min(100, replacePriorityScore))),
    peerPercentile: 50,
    explainTopDrivers
  });
}
