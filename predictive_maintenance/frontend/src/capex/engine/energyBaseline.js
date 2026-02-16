/**
 * C. Energy Baseline + Waste Estimation
 * IPMVP-style baseline modeling with weather normalization
 * Reference: https://eeperformance.org/uploads/8/6/5/0/8650231/ipmvp_volume_i__2012.pdf
 */

export function computeDegreeDays(weatherData, baseTemp = 18, type = 'cooling') {
  return weatherData.map(w => {
    const temp = w.oatC;
    let dd = 0;
    if (type === 'cooling' && temp > baseTemp) {
      dd = temp - baseTemp;
    } else if (type === 'heating' && temp < baseTemp) {
      dd = baseTemp - temp;
    }
    return {
      date: w.ts.split('T')[0],
      oatC: temp,
      cdd: type === 'cooling' ? dd : 0,
      hdd: type === 'heating' ? dd : 0
    };
  });
}

export function aggregateDailyDegreeDays(hourlyDD) {
  const dailyMap = {};
  hourlyDD.forEach(h => {
    const date = h.date;
    if (!dailyMap[date]) {
      dailyMap[date] = { date, cdd: 0, hdd: 0, count: 0, avgOat: 0 };
    }
    dailyMap[date].cdd += h.cdd / 24;
    dailyMap[date].hdd += h.hdd / 24;
    dailyMap[date].avgOat += h.oatC;
    dailyMap[date].count++;
  });
  
  return Object.values(dailyMap).map(d => ({
    date: d.date,
    cdd: Math.round(d.cdd * 100) / 100,
    hdd: Math.round(d.hdd * 100) / 100,
    avgOatC: Math.round((d.avgOat / d.count) * 10) / 10
  }));
}

/**
 * C1. Change-point regression baseline model
 * Models energy as function of outdoor temperature with change points
 */
export function fitChangePointModel(dailyEnergy, dailyWeather, assetType = 'HVAC') {
  const merged = [];
  const weatherByDate = {};
  dailyWeather.forEach(w => { weatherByDate[w.date] = w; });
  
  dailyEnergy.forEach(e => {
    const w = weatherByDate[e.date];
    if (w && e.kwhDay !== null && !isNaN(e.kwhDay)) {
      merged.push({
        date: e.date,
        kwh: e.kwhDay,
        oat: w.avgOatC,
        cdd: w.cdd,
        hdd: w.hdd
      });
    }
  });
  
  if (merged.length < 14) {
    return { valid: false, reason: 'Insufficient data points (need >= 14 days)' };
  }
  
  const n = merged.length;
  const sumX = merged.reduce((s, m) => s + m.oat, 0);
  const sumY = merged.reduce((s, m) => s + m.kwh, 0);
  const sumXY = merged.reduce((s, m) => s + m.oat * m.kwh, 0);
  const sumXX = merged.reduce((s, m) => s + m.oat * m.oat, 0);
  
  const denom = n * sumXX - sumX * sumX;
  const slope = denom !== 0 ? (n * sumXY - sumX * sumY) / denom : 0;
  const intercept = (sumY - slope * sumX) / n;
  
  const predicted = merged.map(m => intercept + slope * m.oat);
  const residuals = merged.map((m, i) => m.kwh - predicted[i]);
  const ss_res = residuals.reduce((s, r) => s + r * r, 0);
  const meanY = sumY / n;
  const ss_tot = merged.reduce((s, m) => s + Math.pow(m.kwh - meanY, 2), 0);
  const rSquared = ss_tot > 0 ? 1 - (ss_res / ss_tot) : 0;
  
  const rmse = Math.sqrt(ss_res / n);
  const cvRmse = meanY > 0 ? (rmse / meanY) * 100 : 0;
  
  const balancePointCooling = slope > 0 ? Math.max(10, -intercept / slope) : 18;
  const balancePointHeating = slope < 0 ? Math.min(25, -intercept / slope) : 18;
  
  return {
    valid: true,
    modelType: 'linear_oat',
    coefficients: {
      intercept: Math.round(intercept * 100) / 100,
      slope: Math.round(slope * 1000) / 1000
    },
    balancePoints: {
      cooling: Math.round(balancePointCooling * 10) / 10,
      heating: Math.round(balancePointHeating * 10) / 10
    },
    fit: {
      rSquared: Math.round(rSquared * 1000) / 1000,
      rmse: Math.round(rmse * 100) / 100,
      cvRmse: Math.round(cvRmse * 10) / 10,
      n: n
    },
    data: merged,
    residuals
  };
}

/**
 * C1b. Compute expected energy and excess from baseline
 */
export function computeBaselineResiduals(model, recentData) {
  if (!model.valid) return null;
  
  const { intercept, slope } = model.coefficients;
  
  const results = recentData.map(d => {
    const expected = intercept + slope * d.oat;
    const actual = d.kwh;
    const residual = actual - expected;
    const residualPct = expected > 0 ? (residual / expected) * 100 : 0;
    
    return {
      date: d.date,
      oat: d.oat,
      actual: Math.round(actual * 100) / 100,
      expected: Math.round(expected * 100) / 100,
      residual: Math.round(residual * 100) / 100,
      residualPct: Math.round(residualPct * 10) / 10
    };
  });
  
  const avgResidual = results.reduce((s, r) => s + r.residual, 0) / results.length;
  const avgResidualPct = results.reduce((s, r) => s + r.residualPct, 0) / results.length;
  const totalExcess = results.filter(r => r.residual > 0).reduce((s, r) => s + r.residual, 0);
  
  return {
    daily: results,
    summary: {
      avgResidualKwh: Math.round(avgResidual * 100) / 100,
      avgResidualPct: Math.round(avgResidualPct * 10) / 10,
      totalExcessKwh: Math.round(totalExcess * 100) / 100,
      daysAnalyzed: results.length,
      daysWithExcess: results.filter(r => r.residual > 0).length
    }
  };
}

/**
 * C2. Peer-residual baseline (asset-level)
 * Compares asset to cohort median performance
 */
export function computePeerResidualBaseline(assetFeatures, cohortBaseline) {
  if (!cohortBaseline || !cohortBaseline.energy_kwh_day) {
    return { valid: false, reason: 'No cohort baseline available' };
  }
  
  const assetKwhDay = assetFeatures.kwhDay || 0;
  const peerMedian = cohortBaseline.energy_kwh_day.p50;
  const peerP75 = cohortBaseline.energy_kwh_day.p75;
  const peerP25 = cohortBaseline.energy_kwh_day.p25;
  
  const residualVsMedian = assetKwhDay - peerMedian;
  const residualPct = peerMedian > 0 ? (residualVsMedian / peerMedian) * 100 : 0;
  
  const iqr = peerP75 - peerP25;
  const mad = iqr / 1.349;
  const robustZScore = mad > 0 ? residualVsMedian / mad : 0;
  
  let percentile = 50;
  if (assetKwhDay <= cohortBaseline.energy_kwh_day.p05) percentile = 5;
  else if (assetKwhDay <= peerP25) percentile = 25 * (assetKwhDay - cohortBaseline.energy_kwh_day.p05) / (peerP25 - cohortBaseline.energy_kwh_day.p05);
  else if (assetKwhDay <= peerMedian) percentile = 25 + 25 * (assetKwhDay - peerP25) / (peerMedian - peerP25);
  else if (assetKwhDay <= peerP75) percentile = 50 + 25 * (assetKwhDay - peerMedian) / (peerP75 - peerMedian);
  else if (assetKwhDay <= cohortBaseline.energy_kwh_day.p95) percentile = 75 + 20 * (assetKwhDay - peerP75) / (cohortBaseline.energy_kwh_day.p95 - peerP75);
  else percentile = 95;
  
  const annualizedExcessKwh = residualVsMedian > 0 ? residualVsMedian * 365 : 0;
  
  return {
    valid: true,
    assetKwhDay: Math.round(assetKwhDay * 100) / 100,
    peerMedianKwhDay: Math.round(peerMedian * 100) / 100,
    residualKwhDay: Math.round(residualVsMedian * 100) / 100,
    residualPct: Math.round(residualPct * 10) / 10,
    robustZScore: Math.round(robustZScore * 100) / 100,
    energyWastePercentile: Math.round(percentile),
    annualizedExcessKwh: Math.round(annualizedExcessKwh),
    interpretation: getWasteInterpretation(percentile, robustZScore)
  };
}

function getWasteInterpretation(percentile, zScore) {
  if (percentile >= 90) return 'Critical energy waste - immediate attention recommended';
  if (percentile >= 75) return 'High energy waste - prioritize for investigation';
  if (percentile >= 60) return 'Moderate energy waste - monitor closely';
  if (percentile >= 40) return 'Normal energy consumption - within expected range';
  return 'Efficient - below peer average';
}

/**
 * Compute energy waste estimate combining baseline and peer methods
 */
export function computeEnergyWasteEstimate(asset, features, weatherData, cohortBaseline, utilityRate) {
  const dailyEnergy = [];
  const energyByDate = {};
  
  if (features.energy && features.energy.daily) {
    features.energy.daily.forEach(d => {
      dailyEnergy.push({ date: d.date, kwhDay: d.kwh });
      energyByDate[d.date] = d.kwh;
    });
  } else if (features.energy) {
    const kwhDay = features.energy.kwh_day || 0;
    const today = new Date().toISOString().split('T')[0];
    dailyEnergy.push({ date: today, kwhDay });
  }
  
  const dailyDD = weatherData ? aggregateDailyDegreeDays(computeDegreeDays(weatherData)) : [];
  
  const merged = dailyDD.map(w => ({
    date: w.date,
    oat: w.avgOatC,
    cdd: w.cdd,
    hdd: w.hdd,
    kwh: energyByDate[w.date] || features.energy?.kwh_day || 0
  }));
  
  const baselineModel = merged.length >= 14 ? fitChangePointModel(dailyEnergy, dailyDD, asset.assetType) : null;
  const baselineResiduals = baselineModel?.valid ? computeBaselineResiduals(baselineModel, merged.slice(-30)) : null;
  const peerResidual = computePeerResidualBaseline({ kwhDay: features.energy?.kwh_day || 0 }, cohortBaseline);
  
  const energyRate = utilityRate?.energyRateSchedule?.default || 0.12;
  
  let annualWasteKwh = 0;
  let confidence = 'low';
  
  if (baselineResiduals && peerResidual.valid) {
    annualWasteKwh = Math.max(
      baselineResiduals.summary.avgResidualKwh * 365,
      peerResidual.annualizedExcessKwh
    );
    confidence = 'high';
  } else if (peerResidual.valid) {
    annualWasteKwh = peerResidual.annualizedExcessKwh;
    confidence = 'medium';
  }
  
  return {
    baselineModel,
    baselineResiduals,
    peerResidual,
    summary: {
      annualWasteKwh: Math.round(Math.max(0, annualWasteKwh)),
      annualWasteCost: Math.round(Math.max(0, annualWasteKwh * energyRate)),
      wastePercentile: peerResidual.valid ? peerResidual.energyWastePercentile : null,
      confidence,
      method: baselineResiduals ? 'baseline_and_peer' : 'peer_only'
    }
  };
}
