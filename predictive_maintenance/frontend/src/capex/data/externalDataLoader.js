/**
 * External Data Loader
 * Loads and parses real data from external datasets:
 * - BDG2: Building Data Genome Project 2
 * - NOAA ISD: Weather data
 * - LBNL FDD: Fault detection datasets
 * - ORNL: Curated fault experiments
 * - ComStock/EULP: Building baselines
 */

// Cache for loaded datasets
const dataCache = {
  bdg2Metadata: null,
  bdg2Weather: null,
  bdg2Electricity: null,
  noaaWeather: null,
  lbnlFdd: null,
  ornlFaults: null
};

/**
 * Parse CSV string to array of objects
 */
function parseCSV(csvString, options = {}) {
  const { delimiter = ',', hasHeader = true } = options;
  const lines = csvString.trim().split('\n');
  
  if (lines.length === 0) return [];
  
  const headers = hasHeader 
    ? lines[0].split(delimiter).map(h => h.trim())
    : null;
  
  const startIdx = hasHeader ? 1 : 0;
  const results = [];
  
  for (let i = startIdx; i < lines.length; i++) {
    const values = lines[i].split(delimiter);
    if (headers) {
      const obj = {};
      headers.forEach((header, idx) => {
        let value = values[idx]?.trim() || '';
        // Try to parse as number
        if (value !== '' && !isNaN(value)) {
          value = parseFloat(value);
        }
        obj[header] = value;
      });
      results.push(obj);
    } else {
      results.push(values.map(v => v.trim()));
    }
  }
  
  return results;
}

/**
 * Parse NOAA ISD-Lite fixed-width format
 * Columns: YYYY MM DD HH Temp Dewpoint Pressure WindDir WindSpeed Precip1 Precip6 SkyCover
 * Temp/Dewpoint in 0.1°C, -9999 = missing
 */
function parseNOAAISDLite(content) {
  const lines = content.trim().split('\n');
  const readings = [];
  
  for (const line of lines) {
    const parts = line.trim().split(/\s+/);
    if (parts.length < 8) continue;
    
    const year = parseInt(parts[0]);
    const month = parseInt(parts[1]);
    const day = parseInt(parts[2]);
    const hour = parseInt(parts[3]);
    const tempRaw = parseInt(parts[4]);
    const dewpointRaw = parseInt(parts[5]);
    const pressureRaw = parseInt(parts[6]);
    const windDirRaw = parseInt(parts[7]);
    const windSpeedRaw = parseInt(parts[8]);
    const precip1Raw = parts[9] ? parseInt(parts[9]) : -9999;
    
    // Skip if essential data is missing
    if (tempRaw === -9999) continue;
    
    const ts = new Date(year, month - 1, day, hour).toISOString();
    
    readings.push({
      ts,
      oatC: tempRaw / 10, // Convert from 0.1°C to °C
      dewpointC: dewpointRaw !== -9999 ? dewpointRaw / 10 : null,
      pressureHpa: pressureRaw !== -9999 ? pressureRaw / 10 : null,
      windDirection: windDirRaw !== -9999 ? windDirRaw : null,
      windSpeedMs: windSpeedRaw !== -9999 ? windSpeedRaw / 10 : null,
      precipMm: precip1Raw !== -9999 && precip1Raw >= 0 ? precip1Raw / 10 : 0,
      source: 'noaa_isd'
    });
  }
  
  return readings;
}

/**
 * Parse BDG2 metadata CSV
 */
function parseBDG2Metadata(csvContent) {
  const records = parseCSV(csvContent);
  return records.map(r => ({
    buildingId: r.building_id,
    siteId: r.site_id,
    primaryUse: r.primaryspaceusage,
    subUse: r.sub_primaryspaceusage,
    sqm: parseFloat(r.sqm) || 0,
    sqft: parseFloat(r.sqft) || 0,
    lat: parseFloat(r.lat) || 0,
    lng: parseFloat(r.lng) || 0,
    timezone: r.timezone,
    hasElectricity: r.electricity === 'Yes',
    hasHotwater: r.hotwater === 'Yes',
    hasChilledwater: r.chilledwater === 'Yes',
    hasSteam: r.steam === 'Yes',
    industry: r.industry,
    yearBuilt: parseInt(r.yearbuilt) || null,
    floors: parseInt(r.numberoffloors) || null,
    eui: parseFloat(r.eui) || null,
    source: 'bdg2'
  }));
}

/**
 * Parse BDG2 weather CSV
 */
function parseBDG2Weather(csvContent) {
  const records = parseCSV(csvContent);
  return records.map(r => ({
    ts: r.timestamp,
    siteId: r.site_id,
    oatC: parseFloat(r.airTemperature) || null,
    cloudCoverage: parseFloat(r.cloudCoverage) || null,
    dewpointC: parseFloat(r.dewTemperature) || null,
    precipMm: parseFloat(r.precipDepth1HR) || 0,
    pressureHpa: parseFloat(r.seaLvlPressure) || null,
    windDirection: parseFloat(r.windDirection) || null,
    windSpeedMs: parseFloat(r.windSpeed) || null,
    source: 'bdg2'
  })).filter(r => r.oatC !== null);
}

/**
 * Parse BDG2 electricity meter CSV
 * Wide format: timestamp, building1, building2, ...
 */
function parseBDG2Electricity(csvContent, targetBuildings = null) {
  const lines = csvContent.trim().split('\n');
  if (lines.length === 0) return {};
  
  const headers = lines[0].split(',').map(h => h.trim());
  const timestampIdx = 0;
  const buildingIds = headers.slice(1);
  
  // Filter to target buildings if specified
  const targetSet = targetBuildings ? new Set(targetBuildings) : null;
  
  const meterData = {};
  buildingIds.forEach((id, idx) => {
    if (!targetSet || targetSet.has(id)) {
      meterData[id] = [];
    }
  });
  
  for (let i = 1; i < lines.length; i++) {
    const values = lines[i].split(',');
    const ts = values[0];
    
    buildingIds.forEach((buildingId, idx) => {
      if (meterData[buildingId]) {
        const value = parseFloat(values[idx + 1]);
        if (!isNaN(value)) {
          meterData[buildingId].push({
            ts,
            kWh: value,
            source: 'bdg2'
          });
        }
      }
    });
  }
  
  return meterData;
}

/**
 * Parse LBNL FDD dataset CSV
 * Expected columns: timestamp, fault_label, plus sensor columns
 */
function parseLBNLFdd(csvContent) {
  const records = parseCSV(csvContent);
  
  return records.map(r => {
    const reading = {
      ts: r.timestamp || r.ts || r.Time,
      faultLabel: parseInt(r.fault_label || r.Fault || 0),
      faultType: r.fault_type || r.FaultType || 'unknown',
      source: 'lbnl_fdd'
    };
    
    // Map common sensor columns
    if (r.OAT !== undefined) reading.oatC = parseFloat(r.OAT);
    if (r.RAT !== undefined) reading.ratC = parseFloat(r.RAT);
    if (r.SAT !== undefined) reading.satC = parseFloat(r.SAT);
    if (r.MAT !== undefined) reading.matC = parseFloat(r.MAT);
    if (r.Superheat !== undefined) reading.superheatK = parseFloat(r.Superheat);
    if (r.Subcooling !== undefined) reading.subcoolingK = parseFloat(r.Subcooling);
    if (r.DischargePressure !== undefined) reading.dischargePressurePsi = parseFloat(r.DischargePressure);
    if (r.SuctionPressure !== undefined) reading.suctionPressurePsi = parseFloat(r.SuctionPressure);
    if (r.CompressorPower !== undefined) reading.compressorPowerKw = parseFloat(r.CompressorPower);
    if (r.EvaporatorFanPower !== undefined) reading.evapFanPowerKw = parseFloat(r.EvaporatorFanPower);
    if (r.CondenserFanPower !== undefined) reading.condFanPowerKw = parseFloat(r.CondenserFanPower);
    
    return reading;
  });
}

/**
 * Parse ORNL Curated Fault Experiment data
 */
function parseORNLFaultExperiment(csvContent) {
  const records = parseCSV(csvContent);
  
  return records.map(r => ({
    ts: r.timestamp || r.Time,
    experimentId: r.experiment_id || r.ExperimentID,
    faultType: r.fault_type || r.FaultType,
    isBaseline: (r.is_baseline === 'true' || r.IsBaseline === 'true' || r.baseline === '1'),
    oatC: parseFloat(r.OAT || r.outdoor_air_temp) || null,
    ratC: parseFloat(r.RAT || r.return_air_temp) || null,
    satC: parseFloat(r.SAT || r.supply_air_temp) || null,
    damperPosition: parseFloat(r.damper_position || r.DamperPosition) || null,
    fanSpeedPct: parseFloat(r.fan_speed || r.FanSpeed) || null,
    compressorStatus: parseInt(r.compressor_status || r.CompressorStatus) || 0,
    heatingStage: parseInt(r.heating_stage || r.HeatingStage) || 0,
    powerKw: parseFloat(r.power_kw || r.Power) || null,
    source: 'ornl_curated'
  }));
}

/**
 * Load file from path (works in browser with fetch for bundled files)
 */
async function loadFile(path) {
  try {
    const response = await fetch(path);
    if (!response.ok) {
      throw new Error(`Failed to load ${path}: ${response.status}`);
    }
    return await response.text();
  } catch (error) {
    console.error(`Error loading file ${path}:`, error.message);
    return null;
  }
}

/**
 * Load NOAA ISD weather data
 */
export async function loadNOAAWeather(years = ['2023', '2024'], station = 'chicago') {
  if (dataCache.noaaWeather) return dataCache.noaaWeather;
  
  const allReadings = [];
  
  for (const year of years) {
    const content = await loadFile(`/data/external/noaa-isd/${station}_${year}`);
    if (content) {
      const readings = parseNOAAISDLite(content);
      allReadings.push(...readings);
    }
  }
  
  // Sort by timestamp
  allReadings.sort((a, b) => new Date(a.ts) - new Date(b.ts));
  
  dataCache.noaaWeather = allReadings;
  console.log(`[ExternalDataLoader] Loaded ${allReadings.length} NOAA weather readings`);
  return allReadings;
}

/**
 * Load BDG2 building metadata
 */
export async function loadBDG2Metadata() {
  if (dataCache.bdg2Metadata) return dataCache.bdg2Metadata;
  
  const content = await loadFile('/data/external/bdg2/metadata.csv');
  if (!content) return [];
  
  const buildings = parseBDG2Metadata(content);
  dataCache.bdg2Metadata = buildings;
  console.log(`[ExternalDataLoader] Loaded ${buildings.length} BDG2 buildings`);
  return buildings;
}

/**
 * Load BDG2 weather data
 */
export async function loadBDG2Weather(siteId = null) {
  if (dataCache.bdg2Weather) {
    if (siteId) {
      return dataCache.bdg2Weather.filter(r => r.siteId === siteId);
    }
    return dataCache.bdg2Weather;
  }
  
  const content = await loadFile('/data/external/bdg2/weather.csv');
  if (!content) return [];
  
  const weather = parseBDG2Weather(content);
  dataCache.bdg2Weather = weather;
  console.log(`[ExternalDataLoader] Loaded ${weather.length} BDG2 weather readings`);
  
  if (siteId) {
    return weather.filter(r => r.siteId === siteId);
  }
  return weather;
}

/**
 * Load BDG2 electricity meter data
 */
export async function loadBDG2Electricity(buildingIds = null) {
  if (dataCache.bdg2Electricity) {
    if (buildingIds) {
      const filtered = {};
      buildingIds.forEach(id => {
        if (dataCache.bdg2Electricity[id]) {
          filtered[id] = dataCache.bdg2Electricity[id];
        }
      });
      return filtered;
    }
    return dataCache.bdg2Electricity;
  }
  
  const content = await loadFile('/data/external/bdg2/electricity.csv');
  if (!content) return {};
  
  const meterData = parseBDG2Electricity(content, buildingIds);
  dataCache.bdg2Electricity = meterData;
  console.log(`[ExternalDataLoader] Loaded BDG2 electricity for ${Object.keys(meterData).length} buildings`);
  return meterData;
}

/**
 * Load LBNL FDD data
 */
export async function loadLBNLFddData(equipmentType = 'rtu', scenario = 'fault_free') {
  const cacheKey = `${equipmentType}_${scenario}`;
  if (dataCache.lbnlFdd?.[cacheKey]) return dataCache.lbnlFdd[cacheKey];
  
  const filename = `${equipmentType}_${scenario}.csv`;
  const content = await loadFile(`/data/external/lbnl-fdd/${filename}`);
  if (!content) {
    console.warn(`[ExternalDataLoader] LBNL FDD data not found: ${filename}. Download from https://data.openei.org/submissions/5763`);
    return [];
  }
  
  const data = parseLBNLFdd(content);
  if (!dataCache.lbnlFdd) dataCache.lbnlFdd = {};
  dataCache.lbnlFdd[cacheKey] = data;
  console.log(`[ExternalDataLoader] Loaded ${data.length} LBNL FDD readings for ${equipmentType}/${scenario}`);
  return data;
}

/**
 * Load ORNL fault experiment data
 */
export async function loadORNLFaultExperiment(experimentId) {
  const cacheKey = experimentId;
  if (dataCache.ornlFaults?.[cacheKey]) return dataCache.ornlFaults[cacheKey];
  
  const filename = `experiment_${experimentId}.csv`;
  const content = await loadFile(`/data/external/ornl-faults/${filename}`);
  if (!content) {
    console.warn(`[ExternalDataLoader] ORNL fault data not found: ${filename}. Download from https://data.openei.org/submissions/909`);
    return [];
  }
  
  const data = parseORNLFaultExperiment(content);
  if (!dataCache.ornlFaults) dataCache.ornlFaults = {};
  dataCache.ornlFaults[cacheKey] = data;
  console.log(`[ExternalDataLoader] Loaded ${data.length} ORNL fault readings for experiment ${experimentId}`);
  return data;
}

/**
 * Get weather observations for a store location
 * Uses NOAA ISD data matched to store location
 */
export async function getWeatherForStore(store, days = 90) {
  // Load NOAA weather data
  const noaaWeather = await loadNOAAWeather();
  
  if (noaaWeather.length === 0) {
    console.warn('[ExternalDataLoader] No NOAA weather data available');
    return [];
  }
  
  // Get the most recent 'days' worth of data
  const endDate = new Date();
  const startDate = new Date();
  startDate.setDate(endDate.getDate() - days);
  
  // Filter to date range
  const filteredWeather = noaaWeather.filter(r => {
    const date = new Date(r.ts);
    return date >= startDate && date <= endDate;
  });
  
  // If not enough data, use all available
  const weatherData = filteredWeather.length > 0 ? filteredWeather : noaaWeather.slice(-days * 24);
  
  // Add store ID to readings
  return weatherData.map(r => ({
    ...r,
    storeId: store.storeId
  }));
}

/**
 * Get sample telemetry from BDG2 for benchmarking
 */
export async function getSampleTelemetryForBenchmark(buildingType = 'Retail') {
  const metadata = await loadBDG2Metadata();
  
  // Find buildings matching type
  const matchingBuildings = metadata.filter(b => 
    b.primaryUse?.toLowerCase().includes(buildingType.toLowerCase())
  );
  
  if (matchingBuildings.length === 0) {
    console.warn(`[ExternalDataLoader] No BDG2 buildings found for type: ${buildingType}`);
    return { buildings: [], meterData: {} };
  }
  
  // Get electricity data for first few matching buildings
  const buildingIds = matchingBuildings.slice(0, 5).map(b => b.buildingId);
  const meterData = await loadBDG2Electricity(buildingIds);
  
  return {
    buildings: matchingBuildings.slice(0, 5),
    meterData
  };
}

/**
 * Clear cached data
 */
export function clearCache() {
  Object.keys(dataCache).forEach(key => {
    dataCache[key] = null;
  });
  console.log('[ExternalDataLoader] Cache cleared');
}

/**
 * Get data source status
 */
export async function getDataSourceStatus() {
  const status = {
    noaaIsd: { available: false, records: 0 },
    bdg2Metadata: { available: false, records: 0 },
    bdg2Weather: { available: false, records: 0 },
    bdg2Electricity: { available: false, buildings: 0 },
    lbnlFdd: { available: false, note: 'Requires manual download' },
    ornlFaults: { available: false, note: 'Requires manual download' }
  };
  
  try {
    const noaa = await loadNOAAWeather();
    status.noaaIsd = { available: noaa.length > 0, records: noaa.length };
  } catch (e) { /* ignore */ }
  
  try {
    const metadata = await loadBDG2Metadata();
    status.bdg2Metadata = { available: metadata.length > 0, records: metadata.length };
  } catch (e) { /* ignore */ }
  
  try {
    const weather = await loadBDG2Weather();
    status.bdg2Weather = { available: weather.length > 0, records: weather.length };
  } catch (e) { /* ignore */ }
  
  try {
    const electricity = await loadBDG2Electricity();
    status.bdg2Electricity = { available: Object.keys(electricity).length > 0, buildings: Object.keys(electricity).length };
  } catch (e) { /* ignore */ }
  
  return status;
}
