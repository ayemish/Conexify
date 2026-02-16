export const ASSET_TYPES = {
  RTU: 'RTU',
  AHU: 'AHU',
  CHILLER: 'Chiller',
  BOILER: 'Boiler',
  CONDENSING_UNIT: 'Condensing Unit',
  COMPRESSOR_RACK: 'Compressor Rack',
  WALK_IN_COOLER: 'Walk-in Cooler',
  WALK_IN_FREEZER: 'Walk-in Freezer',
  REACH_IN_CASE: 'Reach-in Case',
  VFD: 'VFD',
  PUMP: 'Pump',
  EXHAUST_FAN: 'Exhaust Fan',
  LIGHTING: 'Lighting System',
  BMS: 'Building Management System'
};

export const CLIMATE_ZONES = {
  '1A': 'Very Hot-Humid',
  '2A': 'Hot-Humid',
  '2B': 'Hot-Dry',
  '3A': 'Warm-Humid',
  '3B': 'Warm-Dry',
  '3C': 'Warm-Marine',
  '4A': 'Mixed-Humid',
  '4B': 'Mixed-Dry',
  '4C': 'Mixed-Marine',
  '5A': 'Cool-Humid',
  '5B': 'Cool-Dry',
  '6A': 'Cold-Humid',
  '6B': 'Cold-Dry',
  '7': 'Very Cold',
  '8': 'Subarctic'
};

export const STORE_TYPES = {
  GROCERY: 'Grocery',
  BIG_BOX: 'Big Box',
  CONVENIENCE: 'Convenience Store',
  WAREHOUSE: 'Warehouse',
  DISTRIBUTION: 'Distribution Center',
  OFFICE: 'Office'
};

export const CRITICALITY_CLASSES = {
  FOOD_SAFETY: 'Food Safety',
  COMFORT: 'Comfort',
  MISSION_CRITICAL: 'Mission Critical',
  OPERATIONAL: 'Operational'
};

export const CANONICAL_METRICS = {
  POWER_KW: 'power_kw',
  ENERGY_KWH: 'energy_kwh',
  SUPPLY_TEMP_C: 'supply_temp_c',
  RETURN_TEMP_C: 'return_temp_c',
  DISCHARGE_TEMP_C: 'discharge_temp_c',
  SUCTION_PRESSURE_PSI: 'suction_pressure_psi',
  DISCHARGE_PRESSURE_PSI: 'discharge_pressure_psi',
  SUPERHEAT_K: 'superheat_k',
  SUBCOOLING_K: 'subcooling_k',
  COMPRESSOR_STATE: 'compressor_state',
  FAN_STATE: 'fan_state',
  VALVE_POSITION: 'valve_position',
  RUNTIME_HOURS: 'runtime_hours',
  STARTS_COUNT: 'starts_count',
  ALARM_ACTIVE: 'alarm_active',
  SETPOINT_TEMP_C: 'setpoint_temp_c',
  ZONE_TEMP_C: 'zone_temp_c',
  OAT_C: 'outdoor_air_temp_c',
  RH_PCT: 'relative_humidity_pct'
};

export const DECISION_TYPES = {
  REPLACE: 'REPLACE',
  DEFER: 'DEFER',
  INSPECT: 'INSPECT',
  REPAIR: 'REPAIR'
};

export const AGE_BINS = ['0-3', '3-7', '7-12', '12+'];

export function createStore(data) {
  return {
    storeId: data.storeId || crypto.randomUUID(),
    name: data.name || '',
    address: data.address || '',
    lat: data.lat || 0,
    lon: data.lon || 0,
    region: data.region || '',
    climateZone: data.climateZone || '4A',
    utilityRateId: data.utilityRateId || null,
    openHoursProfileId: data.openHoursProfileId || null,
    areaSqft: data.areaSqft || 0,
    storeType: data.storeType || STORE_TYPES.GROCERY
  };
}

export function createAsset(data) {
  const installDate = data.installDate ? new Date(data.installDate) : new Date();
  const ageYears = Math.floor((Date.now() - installDate.getTime()) / (365.25 * 24 * 60 * 60 * 1000));
  
  return {
    assetId: data.assetId || crypto.randomUUID(),
    storeId: data.storeId,
    assetType: data.assetType || ASSET_TYPES.RTU,
    manufacturer: data.manufacturer || '',
    model: data.model || '',
    capacityNominal: data.capacityNominal || 0,
    capacityUnit: data.capacityUnit || 'tons',
    installDate: installDate.toISOString(),
    ageYears: ageYears,
    criticalityClass: data.criticalityClass || CRITICALITY_CLASSES.COMFORT,
    replacementOptionSetId: data.replacementOptionSetId || null,
    brickEntityUri: data.brickEntityUri || null
  };
}

export function createReplacementOption(data) {
  return {
    optionId: data.optionId || crypto.randomUUID(),
    replacementOptionSetId: data.replacementOptionSetId,
    optionName: data.optionName || '',
    capexInstalledCost: data.capexInstalledCost || 0,
    expectedLifeYears: data.expectedLifeYears || 15,
    expectedEfficiencyDelta: data.expectedEfficiencyDelta || 0,
    expectedMaintenanceDeltaPerYear: data.expectedMaintenanceDeltaPerYear || 0,
    leadTimeDays: data.leadTimeDays || 30,
    warrantyYears: data.warrantyYears || 1
  };
}

export function createUtilityRate(data) {
  return {
    utilityRateId: data.utilityRateId || crypto.randomUUID(),
    currency: data.currency || 'USD',
    rateType: data.rateType || 'flat',
    energyRateSchedule: data.energyRateSchedule || { default: 0.12 },
    demandChargeSchedule: data.demandChargeSchedule || null,
    escalationRateAssumption: data.escalationRateAssumption || 0.03
  };
}

export function createEconomicAssumption(data) {
  return {
    storeId: data.storeId,
    discountRate: data.discountRate || 0.08,
    analysisHorizonYears: data.analysisHorizonYears || 10,
    inflationAssumption: data.inflationAssumption || 0.025,
    failureEventCostByAssetType: data.failureEventCostByAssetType || {
      [ASSET_TYPES.RTU]: 15000,
      [ASSET_TYPES.COMPRESSOR_RACK]: 50000,
      [ASSET_TYPES.WALK_IN_COOLER]: 25000,
      [ASSET_TYPES.WALK_IN_FREEZER]: 35000
    },
    truckRollCost: data.truckRollCost || 250,
    laborRate: data.laborRate || 85
  };
}

export function createTelemetryPoint(data) {
  return {
    pointId: data.pointId || crypto.randomUUID(),
    assetId: data.assetId,
    pointNameRaw: data.pointNameRaw || '',
    canonicalMetric: data.canonicalMetric || CANONICAL_METRICS.POWER_KW,
    unit: data.unit || '',
    samplingIntervalSec: data.samplingIntervalSec || 300,
    brickPointUri: data.brickPointUri || null,
    qualityFlagsDefault: data.qualityFlagsDefault || 'good'
  };
}

export function createAssetFeatureDaily(data) {
  return {
    assetId: data.assetId,
    date: data.date,
    featureName: data.featureName,
    featureValue: data.featureValue,
    windowDays: data.windowDays || 30,
    dataCoveragePct: data.dataCoveragePct || 100
  };
}

export function createAssetScoreDaily(data) {
  return {
    assetId: data.assetId,
    date: data.date,
    conditionScore: data.conditionScore || 50,
    energyWasteScore: data.energyWasteScore || 50,
    riskScore: data.riskScore || 50,
    replacePriorityScore: data.replacePriorityScore || 50,
    peerPercentile: data.peerPercentile || 50,
    explainTopDrivers: data.explainTopDrivers || []
  };
}

export function createCapexPlan(data) {
  return {
    planId: data.planId || crypto.randomUUID(),
    storeId: data.storeId,
    asOfDate: data.asOfDate || new Date().toISOString(),
    budgetCapex: data.budgetCapex || 0,
    objective: data.objective || 'max_expected_npv'
  };
}

export function createCapexPlanItem(data) {
  return {
    planId: data.planId,
    assetId: data.assetId,
    decision: data.decision || DECISION_TYPES.DEFER,
    selectedOptionId: data.selectedOptionId || null,
    capexCost: data.capexCost || 0,
    npvP50: data.npvP50 || 0,
    pNpvPositive: data.pNpvPositive || 0,
    peerPercentile: data.peerPercentile || 50,
    rankInStore: data.rankInStore || 0
  };
}

export function getCohortKey(asset, store) {
  const ageBin = asset.ageYears <= 3 ? '0-3' :
                 asset.ageYears <= 7 ? '3-7' :
                 asset.ageYears <= 12 ? '7-12' : '12+';
  
  return {
    assetType: asset.assetType,
    manufacturerModelGroup: `${asset.manufacturer}_${asset.model}`.toLowerCase().replace(/\s+/g, '_'),
    climateZone: store.climateZone,
    storeType: store.storeType,
    ageBin: ageBin
  };
}

export function cohortKeyToString(cohortKey) {
  return `${cohortKey.assetType}|${cohortKey.climateZone}|${cohortKey.storeType}|${cohortKey.ageBin}`;
}
