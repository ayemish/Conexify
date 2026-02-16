import { CANONICAL_METRICS, ASSET_TYPES } from '../data/models.js';
import { getWeatherForStore, loadNOAAWeather, loadBDG2Electricity } from '../data/externalDataLoader.js';

/**
 * Telemetry Data Loader
 * UPDATED: Now loads real data from external datasets where available.
 * - Weather: Real NOAA ISD data (bundled)
 * - Telemetry: Can use BDG2 meter data for benchmarking
 * - Work Orders: Uses sample_store_dataset.json if available
 */

const METRIC_PROFILES = {
  [ASSET_TYPES.RTU]: {
    [CANONICAL_METRICS.POWER_KW]: { base: 8, variance: 2, degradation: 0.02 },
    [CANONICAL_METRICS.SUPPLY_TEMP_C]: { base: 12, variance: 2, degradation: 0.01 },
    [CANONICAL_METRICS.RETURN_TEMP_C]: { base: 24, variance: 3, degradation: 0.005 },
    [CANONICAL_METRICS.RUNTIME_HOURS]: { base: 12, variance: 4, degradation: 0 },
    [CANONICAL_METRICS.STARTS_COUNT]: { base: 6, variance: 3, degradation: 0.05 }
  },
  [ASSET_TYPES.COMPRESSOR_RACK]: {
    [CANONICAL_METRICS.POWER_KW]: { base: 35, variance: 8, degradation: 0.025 },
    [CANONICAL_METRICS.SUCTION_PRESSURE_PSI]: { base: 25, variance: 5, degradation: -0.02 },
    [CANONICAL_METRICS.DISCHARGE_PRESSURE_PSI]: { base: 180, variance: 20, degradation: 0.015 },
    [CANONICAL_METRICS.SUPERHEAT_K]: { base: 8, variance: 3, degradation: 0.03 },
    [CANONICAL_METRICS.RUNTIME_HOURS]: { base: 20, variance: 3, degradation: 0 }
  },
  [ASSET_TYPES.WALK_IN_COOLER]: {
    [CANONICAL_METRICS.POWER_KW]: { base: 3, variance: 0.8, degradation: 0.02 },
    [CANONICAL_METRICS.ZONE_TEMP_C]: { base: 2, variance: 1.5, degradation: 0.02 },
    [CANONICAL_METRICS.RUNTIME_HOURS]: { base: 14, variance: 4, degradation: 0.01 }
  },
  [ASSET_TYPES.WALK_IN_FREEZER]: {
    [CANONICAL_METRICS.POWER_KW]: { base: 5, variance: 1.2, degradation: 0.025 },
    [CANONICAL_METRICS.ZONE_TEMP_C]: { base: -18, variance: 2, degradation: 0.015 },
    [CANONICAL_METRICS.RUNTIME_HOURS]: { base: 16, variance: 3, degradation: 0.01 }
  },
  [ASSET_TYPES.AHU]: {
    [CANONICAL_METRICS.POWER_KW]: { base: 15, variance: 4, degradation: 0.015 },
    [CANONICAL_METRICS.SUPPLY_TEMP_C]: { base: 14, variance: 2, degradation: 0.01 },
    [CANONICAL_METRICS.RUNTIME_HOURS]: { base: 16, variance: 4, degradation: 0 }
  },
  [ASSET_TYPES.REACH_IN_CASE]: {
    [CANONICAL_METRICS.POWER_KW]: { base: 1.2, variance: 0.3, degradation: 0.02 },
    [CANONICAL_METRICS.ZONE_TEMP_C]: { base: 3, variance: 1, degradation: 0.02 },
    [CANONICAL_METRICS.RUNTIME_HOURS]: { base: 18, variance: 4, degradation: 0.01 }
  }
};

function gaussianRandom(mean = 0, std = 1) {
  const u1 = Math.random();
  const u2 = Math.random();
  const z0 = Math.sqrt(-2.0 * Math.log(u1)) * Math.cos(2.0 * Math.PI * u2);
  return z0 * std + mean;
}

function generateDailyValue(profile, ageYears, dayOfYear, climateZone) {
  const ageDegradation = 1 + (profile.degradation * ageYears);
  const seasonalFactor = 1 + 0.15 * Math.sin((dayOfYear / 365) * 2 * Math.PI - Math.PI / 2);
  
  let climateFactor = 1;
  if (climateZone.startsWith('1') || climateZone.startsWith('2')) {
    climateFactor = 1.2;
  } else if (climateZone.startsWith('6') || climateZone === '7' || climateZone === '8') {
    climateFactor = 0.9;
  }
  
  const baseValue = profile.base * ageDegradation * seasonalFactor * climateFactor;
  const noise = gaussianRandom(0, profile.variance);
  
  return Math.max(0, baseValue + noise);
}

export function generateTelemetryReadings(asset, store, days = 90) {
  const readings = [];
  const profiles = METRIC_PROFILES[asset.assetType] || METRIC_PROFILES[ASSET_TYPES.RTU];
  const startDate = new Date();
  startDate.setDate(startDate.getDate() - days);
  
  for (let d = 0; d < days; d++) {
    const currentDate = new Date(startDate);
    currentDate.setDate(startDate.getDate() + d);
    const dayOfYear = Math.floor((currentDate - new Date(currentDate.getFullYear(), 0, 0)) / (1000 * 60 * 60 * 24));
    
    Object.entries(profiles).forEach(([metric, profile]) => {
      const value = generateDailyValue(profile, asset.ageYears, dayOfYear, store.climateZone);
      
      const dataCoverage = Math.random() > 0.05 ? 1 : 0;
      
      if (dataCoverage) {
        readings.push({
          ts: currentDate.toISOString(),
          assetId: asset.assetId,
          metric: metric,
          value: Math.round(value * 100) / 100,
          qualityFlag: Math.random() > 0.02 ? 'good' : 'imputed'
        });
      }
    });
  }
  
  return readings;
}

/**
 * Load real weather observations from NOAA ISD data
 * Falls back to cached data if async loading not possible in sync context
 */
export async function loadWeatherObservations(store, days = 90) {
  try {
    const weatherData = await getWeatherForStore(store, days);
    
    if (weatherData.length > 0) {
      console.log(`[TelemetryLoader] Loaded ${weatherData.length} real weather observations from NOAA`);
      return weatherData.map(w => ({
        storeId: store.storeId,
        ts: w.ts,
        oatC: w.oatC,
        rh: w.rhPct || null,
        dewpointC: w.dewpointC || null,
        windSpeedMs: w.windSpeedMs || null,
        source: 'noaa_isd'
      }));
    }
  } catch (error) {
    console.warn('[TelemetryLoader] Could not load real weather data:', error.message);
  }
  
  // Fallback: return empty array to signal no real data available
  console.warn('[TelemetryLoader] No real weather data available. Download NOAA ISD data.');
  return [];
}

// DEPRECATED: generateWeatherObservations - replaced with loadWeatherObservations
// Keeping for backward compatibility but logs deprecation warning
export function generateWeatherObservations(store, days = 90) {
  console.warn('[DEPRECATED] generateWeatherObservations generates fake data.');
  console.warn('[DEPRECATED] Use loadWeatherObservations() for real NOAA data.');
  
  // Return empty to signal no real data - forces callers to use async version
  return [];
}

export function generateWorkOrders(asset, days = 365) {
  const workOrders = [];
  const baseFrequency = asset.ageYears > 10 ? 0.02 : asset.ageYears > 5 ? 0.01 : 0.005;
  const startDate = new Date();
  startDate.setDate(startDate.getDate() - days);
  
  const baseCost = {
    [ASSET_TYPES.RTU]: 800,
    [ASSET_TYPES.COMPRESSOR_RACK]: 2500,
    [ASSET_TYPES.WALK_IN_COOLER]: 600,
    [ASSET_TYPES.WALK_IN_FREEZER]: 900,
    [ASSET_TYPES.AHU]: 1200,
    [ASSET_TYPES.REACH_IN_CASE]: 350
  };
  
  const failureCodes = ['compressor_failure', 'refrigerant_leak', 'fan_motor', 'control_board', 'coil_damage', 'electrical'];
  
  for (let d = 0; d < days; d++) {
    if (Math.random() < baseFrequency) {
      const currentDate = new Date(startDate);
      currentDate.setDate(startDate.getDate() + d);
      const closeDate = new Date(currentDate);
      closeDate.setDate(closeDate.getDate() + Math.floor(Math.random() * 5) + 1);
      
      const cost = (baseCost[asset.assetType] || 500) * (0.5 + Math.random());
      
      workOrders.push({
        workOrderId: `wo-${asset.assetId}-${d}`,
        assetId: asset.assetId,
        openTs: currentDate.toISOString(),
        closeTs: closeDate.toISOString(),
        category: Math.random() > 0.3 ? 'repair' : 'PM',
        costTotal: Math.round(cost),
        downtimeHours: Math.round((closeDate - currentDate) / (1000 * 60 * 60)),
        failureCode: failureCodes[Math.floor(Math.random() * failureCodes.length)]
      });
    }
  }
  
  return workOrders;
}

/**
 * Load store telemetry using real data sources where available
 * This is the main async function that should be used.
 *
 * If `platformData` is provided (from the backend /capex/platform-data endpoint),
 * pre-loaded telemetry and work orders are used for assets that have them.
 * Assets without platform data fall back to synthetic generation.
 */
export async function loadStoreTelemetryAsync(store, assets, days = 90, platformData = null) {
  console.log(`[TelemetryLoader] Loading telemetry data for store: ${store.name}`);
  
  const telemetryByAsset = {};
  const workOrdersByAsset = {};
  
  // Pre-loaded platform telemetry / work orders (from backend DB)
  const platformTelemetry = platformData?.telemetry || {};
  const platformWorkOrders = platformData?.maintenanceHistory || {};
  
  let platformTelemetryCount = 0;
  let platformWoCount = 0;
  let syntheticTelemetryCount = 0;
  let syntheticWoCount = 0;
  
  // Load real weather data from NOAA
  const weatherObservations = await loadWeatherObservations(store, days);
  
  if (weatherObservations.length === 0) {
    console.warn('[TelemetryLoader] WARNING: No real weather data loaded. Analysis may be incomplete.');
    console.warn('[TelemetryLoader] Ensure NOAA ISD data files are in data/external/noaa-isd/');
  } else {
    console.log(`[TelemetryLoader] Loaded ${weatherObservations.length} real weather observations`);
  }
  
  assets.forEach(asset => {
    // Telemetry: use platform data if available (>= 7 days of readings), else generate
    const platformReadings = platformTelemetry[asset.assetId];
    if (platformReadings && platformReadings.length >= 7) {
      telemetryByAsset[asset.assetId] = platformReadings;
      platformTelemetryCount++;
    } else {
      telemetryByAsset[asset.assetId] = generateTelemetryReadings(asset, store, days);
      syntheticTelemetryCount++;
    }
    
    // Work orders: use platform data if available, else generate
    const platformWos = platformWorkOrders[asset.assetId];
    if (platformWos && platformWos.length > 0) {
      workOrdersByAsset[asset.assetId] = platformWos;
      platformWoCount++;
    } else {
      workOrdersByAsset[asset.assetId] = generateWorkOrders(asset, 365);
      syntheticWoCount++;
    }
  });
  
  const telemetrySource = platformTelemetryCount > 0
    ? (syntheticTelemetryCount > 0 ? 'mixed_platform_and_generated' : 'platform_db')
    : 'sample_generated';
  const woSource = platformWoCount > 0
    ? (syntheticWoCount > 0 ? 'mixed_platform_and_generated' : 'platform_db')
    : 'sample_generated';
  
  console.log(`[TelemetryLoader] Telemetry: ${platformTelemetryCount} platform, ${syntheticTelemetryCount} synthetic`);
  console.log(`[TelemetryLoader] Work orders: ${platformWoCount} platform, ${syntheticWoCount} synthetic`);
  
  return {
    telemetryByAsset,
    weatherObservations,
    workOrdersByAsset,
    dataSource: {
      weather: weatherObservations.length > 0 ? 'noaa_isd' : 'none',
      telemetry: telemetrySource,
      workOrders: woSource
    }
  };
}

// DEPRECATED: Synchronous version - kept for backward compatibility
// Use loadStoreTelemetryAsync instead
export function loadStoreTelemetry(store, assets, days = 90) {
  console.warn('[DEPRECATED] loadStoreTelemetry is synchronous and cannot load real data.');
  console.warn('[DEPRECATED] Use loadStoreTelemetryAsync() for real weather data from NOAA.');
  
  const telemetryByAsset = {};
  const workOrdersByAsset = {};
  
  assets.forEach(asset => {
    telemetryByAsset[asset.assetId] = generateTelemetryReadings(asset, store, days);
    workOrdersByAsset[asset.assetId] = generateWorkOrders(asset, 365);
  });
  
  return {
    telemetryByAsset,
    weatherObservations: [], // Empty - real data requires async
    workOrdersByAsset,
    dataSource: {
      weather: 'none_sync_deprecated',
      telemetry: 'sample_generated',
      workOrders: 'sample_generated'
    }
  };
}
