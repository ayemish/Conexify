/**
 * Baseline Normalization Module
 * Uses real data from external datasets for building comparisons:
 * - BDG2: Building Data Genome Project 2 (meter data, weather)
 * - ComStock: Commercial building stock baselines (when available)
 * - EULP: End-Use Load Profiles (when available)
 */

import { 
  loadBDG2Metadata, 
  loadBDG2Weather, 
  loadBDG2Electricity 
} from '../data/externalDataLoader.js';

/**
 * Building type mapping from application asset types to BDG2 categories
 */
const ASSET_TO_BDG2_MAPPING = {
  'RTU': ['Retail', 'Office', 'Education'],
  'AHU': ['Office', 'Education', 'Healthcare'],
  'COMPRESSOR_RACK': ['Retail', 'Food/Grocery'],
  'WALK_IN_COOLER': ['Retail', 'Food/Grocery', 'Lodging/residential'],
  'WALK_IN_FREEZER': ['Retail', 'Food/Grocery'],
  'REACH_IN_CASE': ['Retail', 'Food/Grocery']
};

/**
 * Climate zone mapping for BDG2 site selection
 */
const CLIMATE_ZONE_TO_SITES = {
  '1': ['Panther', 'Bear'], // Hot-humid
  '2': ['Peacock', 'Lamb'], // Hot-dry
  '3': ['Eagle', 'Moose'], // Warm-marine
  '4': ['Fox', 'Wolf'], // Mixed-humid
  '5': ['Bobcat', 'Crow'], // Cool-humid (Chicago-like)
  '6': ['Mouse', 'Hog'], // Cold
  '7': ['Rat', 'Bull'] // Very cold
};

/**
 * Load BDG2 benchmark data for a specific building type
 */
export async function loadBDG2Benchmark(buildingType = 'Retail') {
  try {
    const metadata = await loadBDG2Metadata();
    
    if (metadata.length === 0) {
      console.warn('[BaselineNorm] No BDG2 metadata available');
      return null;
    }
    
    // Find buildings matching the type
    const matchingBuildings = metadata.filter(b => 
      b.primaryUse?.toLowerCase().includes(buildingType.toLowerCase())
    );
    
    if (matchingBuildings.length === 0) {
      console.warn(`[BaselineNorm] No BDG2 buildings found for type: ${buildingType}`);
      return null;
    }
    
    // Calculate statistics
    const stats = computeBuildingStats(matchingBuildings);
    
    console.log(`[BaselineNorm] Loaded BDG2 benchmark for ${buildingType}: ${matchingBuildings.length} buildings`);
    
    return {
      buildingType,
      buildingCount: matchingBuildings.length,
      stats,
      source: 'bdg2',
      dataAvailable: true
    };
  } catch (error) {
    console.error('[BaselineNorm] Error loading BDG2 benchmark:', error.message);
    return null;
  }
}

/**
 * Compute statistics from BDG2 building metadata
 */
function computeBuildingStats(buildings) {
  const sqftValues = buildings.map(b => b.sqft).filter(v => v > 0);
  const euiValues = buildings.map(b => b.eui).filter(v => v > 0);
  
  return {
    sqft: {
      min: Math.min(...sqftValues),
      max: Math.max(...sqftValues),
      mean: sqftValues.reduce((a, b) => a + b, 0) / sqftValues.length,
      median: percentile(sqftValues, 50),
      p25: percentile(sqftValues, 25),
      p75: percentile(sqftValues, 75)
    },
    eui: euiValues.length > 0 ? {
      min: Math.min(...euiValues),
      max: Math.max(...euiValues),
      mean: euiValues.reduce((a, b) => a + b, 0) / euiValues.length,
      median: percentile(euiValues, 50),
      p25: percentile(euiValues, 25),
      p75: percentile(euiValues, 75)
    } : null
  };
}

/**
 * Calculate percentile
 */
function percentile(arr, p) {
  if (arr.length === 0) return 0;
  const sorted = [...arr].sort((a, b) => a - b);
  const idx = (p / 100) * (sorted.length - 1);
  const lower = Math.floor(idx);
  const upper = Math.ceil(idx);
  if (lower === upper) return sorted[lower];
  return sorted[lower] + (sorted[upper] - sorted[lower]) * (idx - lower);
}

/**
 * Compare a store's energy usage against BDG2 benchmarks
 */
export async function compareToBaseline(store, annualKwh, assetType = 'RTU') {
  const buildingTypes = ASSET_TO_BDG2_MAPPING[assetType] || ['Retail'];
  
  for (const buildingType of buildingTypes) {
    const benchmark = await loadBDG2Benchmark(buildingType);
    
    if (benchmark && benchmark.stats.eui) {
      // Calculate store's EUI
      const storeSqft = store.sqft || 50000; // Default if not available
      const storeEui = annualKwh / storeSqft;
      
      // Compare to benchmark
      const benchmarkEui = benchmark.stats.eui;
      const percentileRank = calculatePercentileRank(storeEui, benchmarkEui);
      
      return {
        storeEui,
        benchmarkMedianEui: benchmarkEui.median,
        benchmarkMeanEui: benchmarkEui.mean,
        percentileRank,
        comparison: getComparisonLabel(percentileRank),
        potentialSavings: calculatePotentialSavings(storeEui, benchmarkEui.median, storeSqft),
        buildingType,
        sampleSize: benchmark.buildingCount,
        source: 'bdg2',
        dataAvailable: true
      };
    }
  }
  
  return {
    storeEui: null,
    comparison: 'unknown',
    source: 'none',
    dataAvailable: false,
    message: 'No benchmark data available. Download BDG2 data from GitHub.'
  };
}

/**
 * Calculate percentile rank
 */
function calculatePercentileRank(value, stats) {
  if (value <= stats.p25) return 25 - (stats.p25 - value) / (stats.p25 - stats.min) * 25;
  if (value <= stats.median) return 25 + (value - stats.p25) / (stats.median - stats.p25) * 25;
  if (value <= stats.p75) return 50 + (value - stats.median) / (stats.p75 - stats.median) * 25;
  return 75 + Math.min(25, (value - stats.p75) / (stats.max - stats.p75) * 25);
}

/**
 * Get comparison label
 */
function getComparisonLabel(percentileRank) {
  if (percentileRank < 25) return 'excellent';
  if (percentileRank < 50) return 'good';
  if (percentileRank < 75) return 'average';
  return 'poor';
}

/**
 * Calculate potential savings if store performed at median level
 */
function calculatePotentialSavings(storeEui, medianEui, sqft) {
  if (storeEui <= medianEui) {
    return { kwhSavings: 0, percentImprovement: 0 };
  }
  
  const excessEui = storeEui - medianEui;
  const kwhSavings = excessEui * sqft;
  const percentImprovement = (excessEui / storeEui) * 100;
  
  return {
    kwhSavings: Math.round(kwhSavings),
    percentImprovement: Math.round(percentImprovement * 10) / 10
  };
}

/**
 * Get weather normalization factors from BDG2
 */
export async function getWeatherNormalization(climateZone) {
  try {
    const sites = CLIMATE_ZONE_TO_SITES[climateZone] || CLIMATE_ZONE_TO_SITES['5'];
    const weather = await loadBDG2Weather();
    
    if (weather.length === 0) {
      return { available: false };
    }
    
    // Filter to matching sites
    const siteWeather = weather.filter(w => 
      sites.some(s => w.siteId?.includes(s))
    );
    
    if (siteWeather.length === 0) {
      // Use all weather data
      return computeWeatherStats(weather);
    }
    
    return computeWeatherStats(siteWeather);
  } catch (error) {
    console.error('[BaselineNorm] Error loading weather normalization:', error.message);
    return { available: false };
  }
}

/**
 * Compute weather statistics for normalization
 */
function computeWeatherStats(weatherData) {
  const temps = weatherData.map(w => w.oatC).filter(v => v !== null);
  
  if (temps.length === 0) {
    return { available: false };
  }
  
  // Calculate heating and cooling degree days base
  const hddBase = 18; // °C
  const cddBase = 18; // °C
  
  let totalHdd = 0;
  let totalCdd = 0;
  
  temps.forEach(t => {
    if (t < hddBase) totalHdd += (hddBase - t) / 24; // Hourly data
    if (t > cddBase) totalCdd += (t - cddBase) / 24;
  });
  
  return {
    available: true,
    meanTemp: temps.reduce((a, b) => a + b, 0) / temps.length,
    minTemp: Math.min(...temps),
    maxTemp: Math.max(...temps),
    hdd: Math.round(totalHdd),
    cdd: Math.round(totalCdd),
    hoursOfData: temps.length,
    source: 'bdg2'
  };
}

/**
 * Load electricity consumption patterns from BDG2
 */
export async function loadConsumptionPatterns(buildingIds = null) {
  try {
    const electricity = await loadBDG2Electricity(buildingIds);
    
    if (Object.keys(electricity).length === 0) {
      return { available: false };
    }
    
    // Analyze patterns
    const patterns = {};
    
    for (const [buildingId, readings] of Object.entries(electricity)) {
      if (readings.length < 24) continue;
      
      // Calculate hourly averages
      const hourlyAvg = Array(24).fill(0).map(() => ({ sum: 0, count: 0 }));
      
      readings.forEach(r => {
        const hour = new Date(r.ts).getHours();
        hourlyAvg[hour].sum += r.kWh;
        hourlyAvg[hour].count++;
      });
      
      const hourlyProfile = hourlyAvg.map(h => 
        h.count > 0 ? h.sum / h.count : 0
      );
      
      // Calculate peak/off-peak ratio
      const peakHours = hourlyProfile.slice(8, 20);
      const offPeakHours = [...hourlyProfile.slice(0, 8), ...hourlyProfile.slice(20)];
      const peakAvg = peakHours.reduce((a, b) => a + b, 0) / peakHours.length;
      const offPeakAvg = offPeakHours.reduce((a, b) => a + b, 0) / offPeakHours.length;
      
      patterns[buildingId] = {
        hourlyProfile,
        peakToOffPeakRatio: offPeakAvg > 0 ? peakAvg / offPeakAvg : 1,
        totalKwh: readings.reduce((sum, r) => sum + r.kWh, 0),
        recordCount: readings.length
      };
    }
    
    return {
      available: true,
      buildingCount: Object.keys(patterns).length,
      patterns,
      source: 'bdg2'
    };
  } catch (error) {
    console.error('[BaselineNorm] Error loading consumption patterns:', error.message);
    return { available: false };
  }
}

/**
 * Get baseline status - check what data is available
 */
export async function getBaselineStatus() {
  const status = {
    bdg2Metadata: false,
    bdg2Weather: false,
    bdg2Electricity: false,
    comstock: false,
    eulp: false
  };
  
  try {
    const metadata = await loadBDG2Metadata();
    status.bdg2Metadata = metadata.length > 0;
    
    const weather = await loadBDG2Weather();
    status.bdg2Weather = weather.length > 0;
    
    const electricity = await loadBDG2Electricity();
    status.bdg2Electricity = Object.keys(electricity).length > 0;
  } catch (e) {
    // Ignore errors
  }
  
  // ComStock and EULP require manual download
  status.comstock = false; // TODO: Check for comstock files
  status.eulp = false; // TODO: Check for eulp files
  
  return status;
}
