/**
 * A1. Semantic Normalization + Point Mapping
 * Uses Brick ontology concepts for canonical metric alignment
 * Reference: https://brickschema.org
 */

export const BRICK_POINT_CLASSES = {
  Power_Sensor: ['power_kw', 'power_kva', 'power_w'],
  Energy_Sensor: ['energy_kwh', 'energy_wh'],
  Temperature_Sensor: ['temp_c', 'temp_f'],
  Supply_Air_Temperature_Sensor: ['supply_temp_c', 'supply_temp_f', 'sat'],
  Return_Air_Temperature_Sensor: ['return_temp_c', 'return_temp_f', 'rat'],
  Discharge_Air_Temperature_Sensor: ['discharge_temp_c', 'discharge_temp_f', 'dat'],
  Zone_Air_Temperature_Sensor: ['zone_temp_c', 'zone_temp_f', 'space_temp'],
  Outside_Air_Temperature_Sensor: ['oat_c', 'oat_f', 'outdoor_temp'],
  Pressure_Sensor: ['pressure_psi', 'pressure_kpa', 'pressure_bar'],
  Suction_Pressure_Sensor: ['suction_pressure_psi', 'suction_psi'],
  Discharge_Pressure_Sensor: ['discharge_pressure_psi', 'head_pressure'],
  Humidity_Sensor: ['rh_pct', 'humidity', 'relative_humidity'],
  Status_Sensor: ['status', 'state', 'run_status'],
  Command: ['cmd', 'command', 'setpoint'],
  Flow_Sensor: ['flow_cfm', 'flow_gpm', 'airflow'],
  Speed_Sensor: ['speed_rpm', 'speed_pct', 'vfd_speed'],
  Current_Sensor: ['current_a', 'amps'],
  Voltage_Sensor: ['voltage_v', 'volts']
};

export const CANONICAL_METRICS = {
  power_kw: { unit: 'kW', brickClass: 'Power_Sensor', description: 'Active power consumption' },
  energy_kwh: { unit: 'kWh', brickClass: 'Energy_Sensor', description: 'Cumulative energy' },
  supply_temp_c: { unit: '°C', brickClass: 'Supply_Air_Temperature_Sensor', description: 'Supply air temperature' },
  return_temp_c: { unit: '°C', brickClass: 'Return_Air_Temperature_Sensor', description: 'Return air temperature' },
  discharge_temp_c: { unit: '°C', brickClass: 'Discharge_Air_Temperature_Sensor', description: 'Discharge temperature' },
  zone_temp_c: { unit: '°C', brickClass: 'Zone_Air_Temperature_Sensor', description: 'Zone/space temperature' },
  oat_c: { unit: '°C', brickClass: 'Outside_Air_Temperature_Sensor', description: 'Outside air temperature' },
  suction_pressure_psi: { unit: 'psi', brickClass: 'Suction_Pressure_Sensor', description: 'Suction pressure' },
  discharge_pressure_psi: { unit: 'psi', brickClass: 'Discharge_Pressure_Sensor', description: 'Discharge/head pressure' },
  rh_pct: { unit: '%', brickClass: 'Humidity_Sensor', description: 'Relative humidity' },
  compressor_state: { unit: 'bool', brickClass: 'Status_Sensor', description: 'Compressor run status' },
  fan_state: { unit: 'bool', brickClass: 'Status_Sensor', description: 'Fan run status' },
  runtime_hours: { unit: 'hours', brickClass: 'Status_Sensor', description: 'Daily runtime hours' },
  starts_count: { unit: 'count', brickClass: 'Status_Sensor', description: 'Daily start count' },
  superheat_k: { unit: 'K', brickClass: 'Temperature_Sensor', description: 'Superheat' },
  subcooling_k: { unit: 'K', brickClass: 'Temperature_Sensor', description: 'Subcooling' },
  setpoint_temp_c: { unit: '°C', brickClass: 'Command', description: 'Temperature setpoint' },
  valve_position: { unit: '%', brickClass: 'Command', description: 'Valve position' },
  vfd_speed_pct: { unit: '%', brickClass: 'Speed_Sensor', description: 'VFD speed percentage' }
};

const POINT_NAME_PATTERNS = [
  { pattern: /power|pwr|kw|watts/i, metric: 'power_kw' },
  { pattern: /energy|kwh|consumption/i, metric: 'energy_kwh' },
  { pattern: /supply.*(temp|air)|sat\b|sa_temp/i, metric: 'supply_temp_c' },
  { pattern: /return.*(temp|air)|rat\b|ra_temp/i, metric: 'return_temp_c' },
  { pattern: /discharge.*(temp|air)|dat\b|da_temp/i, metric: 'discharge_temp_c' },
  { pattern: /zone.*temp|space.*temp|room.*temp/i, metric: 'zone_temp_c' },
  { pattern: /outdoor.*temp|outside.*temp|oat\b|oa_temp|ambient/i, metric: 'oat_c' },
  { pattern: /suction.*(press|psi)|low.*side.*press/i, metric: 'suction_pressure_psi' },
  { pattern: /discharge.*(press|psi)|head.*press|high.*side/i, metric: 'discharge_pressure_psi' },
  { pattern: /humid|rh\b|%rh/i, metric: 'rh_pct' },
  { pattern: /comp.*status|comp.*state|comp.*run/i, metric: 'compressor_state' },
  { pattern: /fan.*status|fan.*state|fan.*run|blower/i, metric: 'fan_state' },
  { pattern: /runtime|run.*hours|operating.*hours/i, metric: 'runtime_hours' },
  { pattern: /start.*count|starts|cycles/i, metric: 'starts_count' },
  { pattern: /superheat|sh\b/i, metric: 'superheat_k' },
  { pattern: /subcool|sc\b/i, metric: 'subcooling_k' },
  { pattern: /setpoint|set.*point|sp\b/i, metric: 'setpoint_temp_c' },
  { pattern: /valve.*pos|valve.*%|exp.*valve|eev/i, metric: 'valve_position' },
  { pattern: /vfd.*speed|drive.*speed|motor.*speed/i, metric: 'vfd_speed_pct' }
];

export function mapRawPointToCanonical(rawPointName, assetType = null) {
  const normalized = rawPointName.toLowerCase().trim();
  
  for (const { pattern, metric } of POINT_NAME_PATTERNS) {
    if (pattern.test(normalized)) {
      return {
        canonicalMetric: metric,
        brickClass: CANONICAL_METRICS[metric].brickClass,
        unit: CANONICAL_METRICS[metric].unit,
        confidence: 0.85,
        matchedPattern: pattern.source
      };
    }
  }
  
  return {
    canonicalMetric: null,
    brickClass: null,
    unit: null,
    confidence: 0,
    matchedPattern: null
  };
}

export function createPointMapping(rawPoints, assetId, assetType) {
  return rawPoints.map(point => {
    const mapping = mapRawPointToCanonical(point.name, assetType);
    return {
      pointId: point.id || `${assetId}-${point.name}`,
      assetId,
      pointNameRaw: point.name,
      canonicalMetric: mapping.canonicalMetric,
      brickClass: mapping.brickClass,
      unit: mapping.unit || point.unit,
      samplingIntervalSec: point.interval || 300,
      mappingConfidence: mapping.confidence,
      brickPointUri: mapping.brickClass ? `brick:${mapping.brickClass}` : null
    };
  });
}

/**
 * A2. Resampling + Quality Scoring
 */

export const QUALITY_FLAGS = {
  GOOD: 'good',
  MISSING: 'missing',
  IMPUTED: 'imputed',
  OUTLIER: 'outlier',
  STALE: 'stale',
  OUT_OF_RANGE: 'out_of_range'
};

export function resampleTimeSeries(readings, targetIntervalSec = 300, method = 'mean') {
  if (readings.length === 0) return [];
  
  const sorted = [...readings].sort((a, b) => new Date(a.ts) - new Date(b.ts));
  const startTime = new Date(sorted[0].ts);
  const endTime = new Date(sorted[sorted.length - 1].ts);
  
  const resampled = [];
  let currentBucketStart = new Date(Math.floor(startTime.getTime() / (targetIntervalSec * 1000)) * targetIntervalSec * 1000);
  
  while (currentBucketStart <= endTime) {
    const bucketEnd = new Date(currentBucketStart.getTime() + targetIntervalSec * 1000);
    const bucketReadings = sorted.filter(r => {
      const t = new Date(r.ts);
      return t >= currentBucketStart && t < bucketEnd;
    });
    
    let value = null;
    let qualityFlag = QUALITY_FLAGS.MISSING;
    
    if (bucketReadings.length > 0) {
      const values = bucketReadings.map(r => r.value).filter(v => v !== null && !isNaN(v));
      if (values.length > 0) {
        switch (method) {
          case 'mean':
            value = values.reduce((a, b) => a + b, 0) / values.length;
            break;
          case 'max':
            value = Math.max(...values);
            break;
          case 'min':
            value = Math.min(...values);
            break;
          case 'last':
            value = values[values.length - 1];
            break;
          default:
            value = values.reduce((a, b) => a + b, 0) / values.length;
        }
        qualityFlag = QUALITY_FLAGS.GOOD;
      }
    }
    
    resampled.push({
      ts: currentBucketStart.toISOString(),
      value: value !== null ? Math.round(value * 1000) / 1000 : null,
      qualityFlag,
      sourceCount: bucketReadings.length
    });
    
    currentBucketStart = bucketEnd;
  }
  
  return resampled;
}

export function detectOutliers(readings, method = 'iqr', threshold = 1.5) {
  const values = readings.map(r => r.value).filter(v => v !== null && !isNaN(v));
  if (values.length < 4) return readings;
  
  const sorted = [...values].sort((a, b) => a - b);
  const q1Idx = Math.floor(sorted.length * 0.25);
  const q3Idx = Math.floor(sorted.length * 0.75);
  const q1 = sorted[q1Idx];
  const q3 = sorted[q3Idx];
  const iqr = q3 - q1;
  
  const lowerBound = q1 - threshold * iqr;
  const upperBound = q3 + threshold * iqr;
  
  return readings.map(r => {
    if (r.value === null) return r;
    const isOutlier = r.value < lowerBound || r.value > upperBound;
    return {
      ...r,
      qualityFlag: isOutlier ? QUALITY_FLAGS.OUTLIER : r.qualityFlag,
      outlierBounds: isOutlier ? { lower: lowerBound, upper: upperBound } : null
    };
  });
}

export function imputeMissing(readings, method = 'linear') {
  const result = [...readings];
  
  for (let i = 0; i < result.length; i++) {
    if (result[i].value === null || result[i].qualityFlag === QUALITY_FLAGS.MISSING) {
      let prevIdx = i - 1;
      let nextIdx = i + 1;
      
      while (prevIdx >= 0 && result[prevIdx].value === null) prevIdx--;
      while (nextIdx < result.length && result[nextIdx].value === null) nextIdx++;
      
      if (prevIdx >= 0 && nextIdx < result.length) {
        const prevVal = result[prevIdx].value;
        const nextVal = result[nextIdx].value;
        const ratio = (i - prevIdx) / (nextIdx - prevIdx);
        result[i] = {
          ...result[i],
          value: Math.round((prevVal + ratio * (nextVal - prevVal)) * 1000) / 1000,
          qualityFlag: QUALITY_FLAGS.IMPUTED,
          imputationMethod: 'linear'
        };
      } else if (prevIdx >= 0) {
        result[i] = {
          ...result[i],
          value: result[prevIdx].value,
          qualityFlag: QUALITY_FLAGS.IMPUTED,
          imputationMethod: 'forward_fill'
        };
      }
    }
  }
  
  return result;
}

export function computeDataQualityScore(readings, expectedInterval = 300) {
  if (readings.length === 0) {
    return { coveragePct: 0, gapRate: 100, outlierRate: 0, imputationRate: 0, isScoreable: false, qualityGrade: 'F' };
  }
  
  const totalPoints = readings.length;
  const goodPoints = readings.filter(r => r.qualityFlag === QUALITY_FLAGS.GOOD).length;
  const missingPoints = readings.filter(r => r.qualityFlag === QUALITY_FLAGS.MISSING || r.value === null).length;
  const outlierPoints = readings.filter(r => r.qualityFlag === QUALITY_FLAGS.OUTLIER).length;
  const imputedPoints = readings.filter(r => r.qualityFlag === QUALITY_FLAGS.IMPUTED).length;
  
  const coveragePct = ((totalPoints - missingPoints) / totalPoints) * 100;
  const gapRate = (missingPoints / totalPoints) * 100;
  const outlierRate = (outlierPoints / totalPoints) * 100;
  const imputationRate = (imputedPoints / totalPoints) * 100;
  
  const qualityScore = coveragePct * 0.6 + (100 - outlierRate) * 0.25 + (100 - imputationRate) * 0.15;
  
  let qualityGrade;
  if (qualityScore >= 95) qualityGrade = 'A';
  else if (qualityScore >= 85) qualityGrade = 'B';
  else if (qualityScore >= 75) qualityGrade = 'C';
  else if (qualityScore >= 60) qualityGrade = 'D';
  else qualityGrade = 'F';
  
  return {
    coveragePct: Math.round(coveragePct * 10) / 10,
    gapRate: Math.round(gapRate * 10) / 10,
    outlierRate: Math.round(outlierRate * 10) / 10,
    imputationRate: Math.round(imputationRate * 10) / 10,
    qualityScore: Math.round(qualityScore * 10) / 10,
    qualityGrade,
    isScoreable: coveragePct >= 85,
    totalPoints,
    goodPoints,
    missingPoints,
    outlierPoints,
    imputedPoints
  };
}

export function processRawTelemetry(rawReadings, targetIntervalSec = 300) {
  let processed = resampleTimeSeries(rawReadings, targetIntervalSec);
  processed = detectOutliers(processed);
  processed = imputeMissing(processed);
  const qualityScore = computeDataQualityScore(processed, targetIntervalSec);
  
  return {
    readings: processed,
    quality: qualityScore
  };
}
