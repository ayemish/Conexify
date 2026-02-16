/**
 * External Data Source Integration
 * FR-X1: NOAA ISD Weather
 * FR-X2: OpenEI URDB Utility Rates
 * FR-G2: LBNL/ORNL FDD Datasets
 * 
 * UPDATED: Now uses real data from external datasets instead of simulated data.
 * Real data sources:
 * - NOAA ISD: Downloaded weather data from NCEI
 * - BDG2: Building Data Genome Project 2 (meter data, weather)
 * - LBNL FDD: Fault detection datasets (requires manual download)
 * - ORNL: Curated fault experiments (requires manual download)
 */

import {
  loadNOAAWeather,
  loadBDG2Weather,
  loadLBNLFddData,
  loadORNLFaultExperiment,
  getWeatherForStore,
  getDataSourceStatus
} from './externalDataLoader.js';

/**
 * NOAA Integrated Surface Database (ISD) - Weather Data
 * Source: https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database
 */
export const NOAA_ISD_STATIONS = {
  'climate_zone_1': { stationId: '720534-00164', name: 'Miami Intl Airport', lat: 25.79, lon: -80.29 },
  'climate_zone_2': { stationId: '722880-23174', name: 'Los Angeles Intl', lat: 33.94, lon: -118.41 },
  'climate_zone_3': { stationId: '722900-23188', name: 'San Diego Lindbergh', lat: 32.73, lon: -117.17 },
  'climate_zone_4': { stationId: '724940-23234', name: 'San Francisco Intl', lat: 37.62, lon: -122.37 },
  'climate_zone_5': { stationId: '725300-14732', name: 'Chicago OHare', lat: 41.99, lon: -87.91 },
  'climate_zone_6': { stationId: '726580-14922', name: 'Minneapolis St Paul', lat: 44.88, lon: -93.23 },
  'climate_zone_7': { stationId: '727930-24233', name: 'Duluth Intl', lat: 46.84, lon: -92.18 }
};

export async function fetchNOAAWeatherData(stationId, startDate, endDate) {
  const baseUrl = 'https://www.ncei.noaa.gov/access/services/data/v1';
  const params = new URLSearchParams({
    dataset: 'global-hourly',
    stations: stationId,
    startDate: startDate,
    endDate: endDate,
    format: 'json',
    units: 'metric'
  });
  
  try {
    const response = await fetch(`${baseUrl}?${params}`);
    if (!response.ok) {
      console.warn(`NOAA API returned ${response.status}, loading from bundled NOAA data`);
      return loadBundledNOAAWeather(startDate, endDate);
    }
    const data = await response.json();
    return parseNOAAData(data);
  } catch (error) {
    console.warn('NOAA API unavailable, loading from bundled NOAA data:', error.message);
    return loadBundledNOAAWeather(startDate, endDate);
  }
}

function parseNOAAData(rawData) {
  return rawData.map(record => ({
    ts: record.DATE,
    oatC: parseFloat(record.TMP?.split(',')[0]) / 10 || null,
    rhPct: parseFloat(record.DEW?.split(',')[0]) || null,
    windSpeedMs: parseFloat(record.WND?.split(',')[3]) / 10 || null,
    precipitation: parseFloat(record.AA1?.split(',')[1]) || 0,
    source: 'noaa_isd'
  })).filter(r => r.oatC !== null);
}

/**
 * Load bundled NOAA weather data (real data from downloaded files)
 * Falls back to this when live API is unavailable
 */
async function loadBundledNOAAWeather(startDate, endDate) {
  try {
    const noaaData = await loadNOAAWeather(['2023', '2024'], 'chicago');
    
    if (noaaData.length === 0) {
      console.error('[ExternalDataSources] No bundled NOAA data available. Please download data files.');
      return [];
    }
    
    // Filter to requested date range
    const start = new Date(startDate);
    const end = new Date(endDate);
    
    const filtered = noaaData.filter(r => {
      const ts = new Date(r.ts);
      return ts >= start && ts <= end;
    });
    
    // If no data in range, return most recent available data
    if (filtered.length === 0) {
      console.warn('[ExternalDataSources] No data in requested range, returning available data');
      const days = Math.ceil((end - start) / (1000 * 60 * 60 * 24));
      return noaaData.slice(-days * 24);
    }
    
    console.log(`[ExternalDataSources] Loaded ${filtered.length} real NOAA weather readings`);
    return filtered;
  } catch (error) {
    console.error('[ExternalDataSources] Failed to load bundled NOAA data:', error.message);
    return [];
  }
}

// DEPRECATED: generateSimulatedWeather - replaced with real data
// Keeping function signature for backward compatibility but it now loads real data
function generateSimulatedWeather(startDate, endDate, climateZone = 'temperate') {
  console.warn('[DEPRECATED] generateSimulatedWeather called - use loadBundledNOAAWeather instead');
  return loadBundledNOAAWeather(startDate, endDate);
}

/**
 * OpenEI Utility Rate Database (URDB)
 * Source: https://openei.org/wiki/Utility_Rate_Database
 */
export const SAMPLE_UTILITY_RATES = {
  'commercial_general': {
    utilityName: 'Sample Electric Co',
    rateName: 'Commercial General Service',
    energyRateSchedule: {
      default: 0.12,
      peak: 0.18,
      offPeak: 0.08,
      shoulder: 0.11
    },
    demandRateSchedule: {
      default: 12.50,
      peak: 18.00
    },
    peakHours: { start: 12, end: 18 },
    seasonalAdjustment: {
      summer: 1.15,
      winter: 0.95
    }
  },
  'commercial_tou': {
    utilityName: 'Sample Electric Co',
    rateName: 'Commercial Time-of-Use',
    energyRateSchedule: {
      default: 0.10,
      peak: 0.22,
      offPeak: 0.06,
      superOffPeak: 0.04
    },
    demandRateSchedule: {
      default: 15.00,
      peak: 22.00
    },
    peakHours: { start: 14, end: 20 },
    seasonalAdjustment: {
      summer: 1.25,
      winter: 0.85
    }
  }
};

export async function fetchOpenEIUtilityRates(zipCode, sector = 'commercial') {
  const apiKey = 'DEMO_KEY';
  const baseUrl = 'https://api.openei.org/utility_rates';
  
  try {
    const params = new URLSearchParams({
      version: 7,
      format: 'json',
      api_key: apiKey,
      address: zipCode,
      sector: sector,
      limit: 10
    });
    
    const response = await fetch(`${baseUrl}?${params}`);
    if (!response.ok) {
      console.warn(`OpenEI API returned ${response.status}, using sample rates`);
      return SAMPLE_UTILITY_RATES.commercial_general;
    }
    const data = await response.json();
    return parseOpenEIRates(data);
  } catch (error) {
    console.warn('OpenEI API unavailable, using sample utility rates:', error.message);
    return SAMPLE_UTILITY_RATES.commercial_general;
  }
}

function parseOpenEIRates(rawData) {
  if (!rawData.items || rawData.items.length === 0) {
    return SAMPLE_UTILITY_RATES.commercial_general;
  }
  
  const rate = rawData.items[0];
  return {
    utilityName: rate.utility || 'Unknown',
    rateName: rate.name || 'Standard Rate',
    energyRateSchedule: {
      default: rate.energyratestructure?.[0]?.[0]?.rate || 0.12,
      peak: rate.energyratestructure?.[0]?.[0]?.rate * 1.5 || 0.18,
      offPeak: rate.energyratestructure?.[0]?.[0]?.rate * 0.7 || 0.08
    },
    demandRateSchedule: {
      default: rate.demandratestructure?.[0]?.[0]?.rate || 12.00
    },
    source: 'openei_urdb'
  };
}

/**
 * LBNL FDD Dataset Format Parser
 * Source: https://data.openei.org/submissions/5763
 */
export const LBNL_FAULT_SCENARIOS = [
  { id: 'baseline', description: 'Fault-free baseline operation', severity: 0 },
  { id: 'refrigerant_undercharge_10', description: 'Refrigerant undercharge 10%', severity: 1 },
  { id: 'refrigerant_undercharge_20', description: 'Refrigerant undercharge 20%', severity: 2 },
  { id: 'refrigerant_undercharge_30', description: 'Refrigerant undercharge 30%', severity: 3 },
  { id: 'refrigerant_overcharge_10', description: 'Refrigerant overcharge 10%', severity: 1 },
  { id: 'refrigerant_overcharge_20', description: 'Refrigerant overcharge 20%', severity: 2 },
  { id: 'condenser_fouling_10', description: 'Condenser fouling 10%', severity: 1 },
  { id: 'condenser_fouling_20', description: 'Condenser fouling 20%', severity: 2 },
  { id: 'condenser_fouling_30', description: 'Condenser fouling 30%', severity: 3 },
  { id: 'evaporator_fouling_10', description: 'Evaporator fouling 10%', severity: 1 },
  { id: 'evaporator_fouling_20', description: 'Evaporator fouling 20%', severity: 2 },
  { id: 'compressor_valve_leak_5', description: 'Compressor valve leak 5%', severity: 2 },
  { id: 'compressor_valve_leak_10', description: 'Compressor valve leak 10%', severity: 3 },
  { id: 'txv_stuck_10', description: 'TXV stuck 10% closed', severity: 2 },
  { id: 'txv_stuck_20', description: 'TXV stuck 20% closed', severity: 3 }
];

/**
 * Load LBNL FDD data from real dataset files
 * If files not available, logs instructions for manual download
 */
export async function loadLBNLFaultData(equipmentType = 'rtu', scenario = 'fault_free') {
  try {
    const data = await loadLBNLFddData(equipmentType, scenario);
    
    if (data.length === 0) {
      console.warn(`[ExternalDataSources] LBNL FDD data not available for ${equipmentType}/${scenario}`);
      console.warn('[ExternalDataSources] Download from: https://data.openei.org/submissions/5763');
      return { scenario, readings: [], labels: [], source: 'lbnl_fdd', dataAvailable: false };
    }
    
    const readings = data.map(r => ({
      ts: r.ts,
      power_kw: r.compressorPowerKw || 0,
      supply_temp_c: r.satC || null,
      return_temp_c: r.ratC || null,
      discharge_pressure_psi: r.dischargePressurePsi || null,
      suction_pressure_psi: r.suctionPressurePsi || null,
      superheat_k: r.superheatK || null,
      subcooling_k: r.subcoolingK || null,
      compressor_state: 1,
      fan_state: 1
    }));
    
    const labels = data.map(r => r.faultLabel || 0);
    const faultConfig = LBNL_FAULT_SCENARIOS.find(f => f.id === scenario);
    
    return { scenario, readings, labels, faultConfig, source: 'lbnl_fdd', dataAvailable: true };
  } catch (error) {
    console.error('[ExternalDataSources] Error loading LBNL data:', error.message);
    return { scenario, readings: [], labels: [], source: 'lbnl_fdd', dataAvailable: false };
  }
}

// DEPRECATED: generateLBNLStyleFaultData - replaced with loadLBNLFaultData
// Keeping for backward compatibility but now returns empty with warning
export function generateLBNLStyleFaultData(scenario, durationHours = 24) {
  console.warn('[DEPRECATED] generateLBNLStyleFaultData generates fake data. Use loadLBNLFaultData() for real data.');
  console.warn('[DEPRECATED] Download LBNL FDD data from: https://data.openei.org/submissions/5763');
  
  // Return empty result to make it clear no real data is available
  const faultConfig = LBNL_FAULT_SCENARIOS.find(f => f.id === scenario);
  return { 
    scenario, 
    readings: [], 
    labels: [], 
    faultConfig,
    source: 'deprecated_simulation',
    dataAvailable: false,
    message: 'This function is deprecated. Download real LBNL FDD data and use loadLBNLFaultData()'
  };
}

function generateBaselineReadings(hours) {
  const readings = [];
  const startTime = new Date();
  
  for (let h = 0; h < hours; h++) {
    for (let m = 0; m < 60; m += 5) {
      const ts = new Date(startTime.getTime() + (h * 60 + m) * 60 * 1000);
      const loadFactor = 0.6 + 0.3 * Math.sin((h - 6) * Math.PI / 12);
      
      readings.push({
        ts: ts.toISOString(),
        power_kw: Math.round((3.5 * loadFactor + Math.random() * 0.3) * 100) / 100,
        supply_temp_c: Math.round((12 + Math.random() * 1) * 10) / 10,
        return_temp_c: Math.round((24 + Math.random() * 1) * 10) / 10,
        discharge_pressure_psi: Math.round((250 + Math.random() * 10) * 10) / 10,
        suction_pressure_psi: Math.round((70 + Math.random() * 5) * 10) / 10,
        superheat_k: Math.round((8 + Math.random() * 2) * 10) / 10,
        subcooling_k: Math.round((10 + Math.random() * 2) * 10) / 10,
        compressor_state: 1,
        fan_state: 1
      });
    }
  }
  
  return readings;
}

function applyFaultSignature(readings, scenario, severity) {
  return readings.map(r => {
    const faulted = { ...r };
    
    if (scenario.includes('refrigerant_undercharge')) {
      const pct = parseInt(scenario.split('_').pop()) / 100;
      faulted.superheat_k = r.superheat_k * (1 + pct * 1.5);
      faulted.suction_pressure_psi = r.suction_pressure_psi * (1 - pct * 0.3);
      faulted.power_kw = r.power_kw * (1 + pct * 0.15);
    }
    
    if (scenario.includes('refrigerant_overcharge')) {
      const pct = parseInt(scenario.split('_').pop()) / 100;
      faulted.subcooling_k = r.subcooling_k * (1 + pct * 1.2);
      faulted.discharge_pressure_psi = r.discharge_pressure_psi * (1 + pct * 0.15);
      faulted.power_kw = r.power_kw * (1 + pct * 0.1);
    }
    
    if (scenario.includes('condenser_fouling')) {
      const pct = parseInt(scenario.split('_').pop()) / 100;
      faulted.discharge_pressure_psi = r.discharge_pressure_psi * (1 + pct * 0.25);
      faulted.power_kw = r.power_kw * (1 + pct * 0.2);
      faulted.subcooling_k = r.subcooling_k * (1 - pct * 0.3);
    }
    
    if (scenario.includes('evaporator_fouling')) {
      const pct = parseInt(scenario.split('_').pop()) / 100;
      faulted.suction_pressure_psi = r.suction_pressure_psi * (1 - pct * 0.2);
      faulted.superheat_k = r.superheat_k * (1 + pct * 0.8);
      faulted.supply_temp_c = r.supply_temp_c * (1 + pct * 0.3);
    }
    
    if (scenario.includes('compressor_valve_leak')) {
      const pct = parseInt(scenario.split('_').pop()) / 100;
      faulted.power_kw = r.power_kw * (1 + pct * 0.25);
      faulted.discharge_pressure_psi = r.discharge_pressure_psi * (1 - pct * 0.1);
      faulted.suction_pressure_psi = r.suction_pressure_psi * (1 + pct * 0.15);
    }
    
    if (scenario.includes('txv_stuck')) {
      const pct = parseInt(scenario.split('_').pop()) / 100;
      faulted.superheat_k = r.superheat_k * (1 + pct * 2);
      faulted.suction_pressure_psi = r.suction_pressure_psi * (1 - pct * 0.25);
    }
    
    Object.keys(faulted).forEach(key => {
      if (typeof faulted[key] === 'number' && key !== 'ts') {
        faulted[key] = Math.round(faulted[key] * 100) / 100;
      }
    });
    
    return faulted;
  });
}

/**
 * ORNL Curated Fault Dataset Format
 * Source: https://data.openei.org/submissions/909
 */
export const ORNL_FAULT_EXPERIMENTS = [
  { id: 'exp_001', fault: 'compressor_cycling', equipment: 'RTU', duration_hours: 4 },
  { id: 'exp_002', fault: 'economizer_stuck_open', equipment: 'RTU', duration_hours: 8 },
  { id: 'exp_003', fault: 'economizer_stuck_closed', equipment: 'RTU', duration_hours: 8 },
  { id: 'exp_004', fault: 'supply_fan_degradation', equipment: 'AHU', duration_hours: 24 },
  { id: 'exp_005', fault: 'damper_leakage', equipment: 'AHU', duration_hours: 12 },
  { id: 'exp_006', fault: 'sensor_bias_sat', equipment: 'RTU', duration_hours: 24 },
  { id: 'exp_007', fault: 'sensor_bias_rat', equipment: 'RTU', duration_hours: 24 },
  { id: 'exp_008', fault: 'heating_valve_leak', equipment: 'AHU', duration_hours: 12 },
  { id: 'exp_009', fault: 'cooling_valve_stuck', equipment: 'AHU', duration_hours: 12 },
  { id: 'exp_010', fault: 'vfd_failure', equipment: 'AHU', duration_hours: 4 }
];

/**
 * Load ORNL fault experiment data from real dataset files
 * If files not available, logs instructions for manual download
 */
export async function loadORNLExperiment(experimentId) {
  const exp = ORNL_FAULT_EXPERIMENTS.find(e => e.id === experimentId);
  if (!exp) {
    console.warn(`[ExternalDataSources] Unknown experiment: ${experimentId}`);
    return null;
  }
  
  try {
    const data = await loadORNLFaultExperiment(experimentId);
    
    if (data.length === 0) {
      console.warn(`[ExternalDataSources] ORNL experiment data not available for ${experimentId}`);
      console.warn('[ExternalDataSources] Download from: https://data.openei.org/submissions/909');
      return {
        experimentId: exp.id,
        fault: exp.fault,
        equipment: exp.equipment,
        readings: [],
        metadata: {
          duration: exp.duration_hours,
          samplingRate: '5min',
          source: 'ornl_curated',
          dataAvailable: false
        }
      };
    }
    
    return {
      experimentId: exp.id,
      fault: exp.fault,
      equipment: exp.equipment,
      readings: data,
      metadata: {
        duration: exp.duration_hours,
        samplingRate: '5min',
        source: 'ornl_curated',
        dataAvailable: true
      }
    };
  } catch (error) {
    console.error('[ExternalDataSources] Error loading ORNL data:', error.message);
    return null;
  }
}

// DEPRECATED: generateORNLStyleExperiment - replaced with loadORNLExperiment
// Keeping for backward compatibility but now returns empty with warning
export function generateORNLStyleExperiment(experimentId) {
  console.warn('[DEPRECATED] generateORNLStyleExperiment generates fake data. Use loadORNLExperiment() for real data.');
  console.warn('[DEPRECATED] Download ORNL fault data from: https://data.openei.org/submissions/909');
  
  const exp = ORNL_FAULT_EXPERIMENTS.find(e => e.id === experimentId);
  if (!exp) {
    return null;
  }
  
  return {
    experimentId: exp.id,
    fault: exp.fault,
    equipment: exp.equipment,
    readings: [],
    metadata: {
      duration: exp.duration_hours,
      samplingRate: '5min',
      source: 'deprecated_simulation',
      dataAvailable: false,
      message: 'This function is deprecated. Download real ORNL data and use loadORNLExperiment()'
    }
  };
}

function generateHVACBaselineReadings(hours, equipmentType) {
  const readings = [];
  const startTime = new Date();
  
  for (let h = 0; h < hours; h++) {
    for (let m = 0; m < 60; m += 5) {
      const ts = new Date(startTime.getTime() + (h * 60 + m) * 60 * 1000);
      const oat = 25 + Math.sin(h * Math.PI / 12) * 8;
      
      const base = {
        ts: ts.toISOString(),
        oat_c: Math.round(oat * 10) / 10,
        zone_temp_c: Math.round((22 + Math.random() * 1) * 10) / 10,
        zone_temp_setpoint_c: 22,
        supply_temp_c: Math.round((14 + Math.random() * 1) * 10) / 10,
        return_temp_c: Math.round((23 + Math.random() * 0.5) * 10) / 10,
        mixed_air_temp_c: Math.round((18 + Math.random() * 2) * 10) / 10,
        supply_fan_speed_pct: 75 + Math.random() * 10,
        damper_position_pct: oat < 18 ? 100 : (oat > 24 ? 20 : 50 + (24 - oat) * 10),
        cooling_valve_pct: oat > 22 ? Math.min(100, (oat - 22) * 20) : 0,
        heating_valve_pct: oat < 18 ? Math.min(100, (18 - oat) * 15) : 0,
        power_kw: equipmentType === 'RTU' ? 8 + Math.random() * 2 : 15 + Math.random() * 3
      };
      
      readings.push(base);
    }
  }
  
  return readings;
}

function applyORNLFault(readings, faultType) {
  return readings.map((r, idx) => {
    const faulted = { ...r };
    
    switch (faultType) {
      case 'compressor_cycling':
        if (idx % 6 < 2) {
          faulted.supply_temp_c = r.return_temp_c - 2;
          faulted.power_kw = r.power_kw * 0.4;
        }
        break;
        
      case 'economizer_stuck_open':
        faulted.damper_position_pct = 100;
        faulted.mixed_air_temp_c = r.oat_c;
        if (r.oat_c > 24) faulted.power_kw = r.power_kw * 1.3;
        break;
        
      case 'economizer_stuck_closed':
        faulted.damper_position_pct = 20;
        faulted.mixed_air_temp_c = r.return_temp_c * 0.8 + r.oat_c * 0.2;
        if (r.oat_c < 18) faulted.power_kw = r.power_kw * 1.2;
        break;
        
      case 'supply_fan_degradation':
        faulted.supply_fan_speed_pct = r.supply_fan_speed_pct * 0.7;
        faulted.supply_temp_c = r.supply_temp_c + 2;
        break;
        
      case 'sensor_bias_sat':
        faulted.supply_temp_c = r.supply_temp_c + 3;
        break;
        
      case 'sensor_bias_rat':
        faulted.return_temp_c = r.return_temp_c - 2;
        break;
        
      case 'cooling_valve_stuck':
        faulted.cooling_valve_pct = 50;
        break;
        
      case 'heating_valve_leak':
        faulted.heating_valve_pct = Math.max(10, r.heating_valve_pct);
        if (r.cooling_valve_pct > 0) faulted.power_kw = r.power_kw * 1.15;
        break;
        
      case 'vfd_failure':
        faulted.supply_fan_speed_pct = 100;
        faulted.power_kw = r.power_kw * 1.4;
        break;
    }
    
    return faulted;
  });
}

/**
 * Aggregate function to load all external data for a store
 */
/**
 * Load all external data for a store using real data sources
 */
export async function loadExternalDataForStore(store, startDate, endDate) {
  console.log(`[External Data] Loading REAL data for store: ${store.name}`);
  
  // Check data source availability
  const dataStatus = await getDataSourceStatus();
  console.log('[External Data] Data source status:', dataStatus);
  
  const climateZoneKey = `climate_zone_${store.climateZone || 5}`;
  const station = NOAA_ISD_STATIONS[climateZoneKey] || NOAA_ISD_STATIONS.climate_zone_5;
  
  // Load weather from bundled NOAA data (real data)
  console.log('[External Data] Loading bundled NOAA weather data...');
  let weatherData = await loadBundledNOAAWeather(startDate, endDate);
  
  // Fallback to API if bundled data not available
  if (weatherData.length === 0) {
    console.log('[External Data] Attempting NOAA API...');
    weatherData = await fetchNOAAWeatherData(station.stationId, startDate, endDate);
  }
  
  console.log('[External Data] Fetching utility rates...');
  const utilityRates = await fetchOpenEIUtilityRates(store.zipCode || '60601', 'commercial');
  
  // Load LBNL FDD data (real data if available)
  console.log('[External Data] Loading LBNL FDD data...');
  const fddTrainingData = [];
  for (const scenario of LBNL_FAULT_SCENARIOS.slice(0, 5)) {
    const data = await loadLBNLFaultData('rtu', scenario.id);
    fddTrainingData.push(data);
  }
  
  const hasRealFddData = fddTrainingData.some(d => d.dataAvailable);
  
  return {
    weather: {
      data: weatherData,
      station: station,
      period: { start: startDate, end: endDate },
      source: weatherData.length > 0 && weatherData[0].source === 'noaa_isd' ? 'noaa_isd_bundled' : 'noaa_api',
      recordCount: weatherData.length
    },
    utilityRates: {
      ...utilityRates,
      storeId: store.storeId
    },
    fddTrainingData: {
      scenarios: fddTrainingData,
      totalReadings: fddTrainingData.reduce((sum, s) => sum + s.readings.length, 0),
      hasRealData: hasRealFddData,
      downloadInstructions: hasRealFddData ? null : 'Download LBNL FDD data from https://data.openei.org/submissions/5763'
    },
    dataStatus,
    loadedAt: new Date().toISOString()
  };
}

// Re-export data status function for external use
export { getDataSourceStatus };
