import { 
  createStore, createAsset, createReplacementOption, createUtilityRate, 
  createEconomicAssumption, ASSET_TYPES, STORE_TYPES, CRITICALITY_CLASSES, CLIMATE_ZONES 
} from './models.js';

const MANUFACTURERS = {
  RTU: ['Carrier', 'Trane', 'Lennox', 'York', 'Daikin'],
  COMPRESSOR_RACK: ['Hussmann', 'Hill Phoenix', 'Zero Zone', 'Kysor Warren'],
  CONDENSING_UNIT: ['Bohn', 'Heatcraft', 'Copeland', 'Emerson'],
  WALK_IN: ['Kolpak', 'Master-Bilt', 'Amerikooler', 'US Cooler']
};

function randomFromArray(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

function randomBetween(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function generateInstallDate(minYearsAgo, maxYearsAgo) {
  const yearsAgo = randomBetween(minYearsAgo, maxYearsAgo);
  const date = new Date();
  date.setFullYear(date.getFullYear() - yearsAgo);
  date.setMonth(randomBetween(0, 11));
  return date.toISOString();
}

export function generateSampleStores(count = 5) {
  const storeNames = [
    'Downtown Market', 'Westside Fresh', 'Harbor View Store', 'Mountain Plaza',
    'Riverside Grocery', 'Central Station', 'Northgate Market', 'Southpark Fresh',
    'Eastwood Store', 'Valley View Market'
  ];
  
  const regions = ['Northeast', 'Southeast', 'Midwest', 'Southwest', 'Northwest'];
  const climateZones = Object.keys(CLIMATE_ZONES);
  
  return Array.from({ length: count }, (_, i) => createStore({
    storeId: `store-${i + 1}`,
    name: storeNames[i % storeNames.length] + (i >= storeNames.length ? ` #${Math.floor(i / storeNames.length) + 1}` : ''),
    address: `${randomBetween(100, 9999)} ${['Main St', 'Oak Ave', 'Commerce Blvd', 'Market St'][i % 4]}, City ${i + 1}`,
    lat: randomBetween(30, 45) + Math.random(),
    lon: -randomBetween(75, 120) + Math.random(),
    region: randomFromArray(regions),
    climateZone: randomFromArray(climateZones),
    areaSqft: randomBetween(25000, 80000),
    storeType: randomFromArray([STORE_TYPES.GROCERY, STORE_TYPES.BIG_BOX, STORE_TYPES.WAREHOUSE])
  }));
}

export function generateSampleAssets(storeId, storeType = STORE_TYPES.GROCERY) {
  const assets = [];
  const optionSetId = `opt-set-${storeId}`;
  
  const rtuCount = randomBetween(4, 8);
  for (let i = 0; i < rtuCount; i++) {
    assets.push(createAsset({
      assetId: `${storeId}-rtu-${i + 1}`,
      storeId,
      assetType: ASSET_TYPES.RTU,
      manufacturer: randomFromArray(MANUFACTURERS.RTU),
      model: `Model ${randomBetween(100, 999)}`,
      capacityNominal: randomBetween(5, 25),
      capacityUnit: 'tons',
      installDate: generateInstallDate(1, 18),
      criticalityClass: CRITICALITY_CLASSES.COMFORT,
      replacementOptionSetId: optionSetId
    }));
  }
  
  if (storeType === STORE_TYPES.GROCERY) {
    const rackCount = randomBetween(2, 4);
    for (let i = 0; i < rackCount; i++) {
      const isLowTemp = i < Math.ceil(rackCount / 2);
      assets.push(createAsset({
        assetId: `${storeId}-rack-${i + 1}`,
        storeId,
        assetType: ASSET_TYPES.COMPRESSOR_RACK,
        manufacturer: randomFromArray(MANUFACTURERS.COMPRESSOR_RACK),
        model: `${isLowTemp ? 'LT' : 'MT'}-${randomBetween(100, 500)}`,
        capacityNominal: randomBetween(80, 200),
        capacityUnit: 'kBTU/hr',
        installDate: generateInstallDate(2, 15),
        criticalityClass: CRITICALITY_CLASSES.FOOD_SAFETY,
        replacementOptionSetId: optionSetId
      }));
    }
    
    const walkinCount = randomBetween(3, 6);
    for (let i = 0; i < walkinCount; i++) {
      const isFreezer = i % 3 === 0;
      assets.push(createAsset({
        assetId: `${storeId}-walkin-${i + 1}`,
        storeId,
        assetType: isFreezer ? ASSET_TYPES.WALK_IN_FREEZER : ASSET_TYPES.WALK_IN_COOLER,
        manufacturer: randomFromArray(MANUFACTURERS.WALK_IN),
        model: `WI-${randomBetween(100, 300)}`,
        capacityNominal: randomBetween(200, 800),
        capacityUnit: 'sqft',
        installDate: generateInstallDate(3, 20),
        criticalityClass: CRITICALITY_CLASSES.FOOD_SAFETY,
        replacementOptionSetId: optionSetId
      }));
    }
    
    const caseCount = randomBetween(8, 15);
    for (let i = 0; i < caseCount; i++) {
      assets.push(createAsset({
        assetId: `${storeId}-case-${i + 1}`,
        storeId,
        assetType: ASSET_TYPES.REACH_IN_CASE,
        manufacturer: randomFromArray(MANUFACTURERS.COMPRESSOR_RACK),
        model: `RC-${randomBetween(100, 500)}`,
        capacityNominal: randomBetween(8, 24),
        capacityUnit: 'linear_ft',
        installDate: generateInstallDate(2, 12),
        criticalityClass: CRITICALITY_CLASSES.FOOD_SAFETY,
        replacementOptionSetId: optionSetId
      }));
    }
  }
  
  const ahuCount = randomBetween(1, 3);
  for (let i = 0; i < ahuCount; i++) {
    assets.push(createAsset({
      assetId: `${storeId}-ahu-${i + 1}`,
      storeId,
      assetType: ASSET_TYPES.AHU,
      manufacturer: randomFromArray(MANUFACTURERS.RTU),
      model: `AHU-${randomBetween(1000, 5000)}`,
      capacityNominal: randomBetween(5000, 20000),
      capacityUnit: 'cfm',
      installDate: generateInstallDate(3, 20),
      criticalityClass: CRITICALITY_CLASSES.COMFORT,
      replacementOptionSetId: optionSetId
    }));
  }
  
  return assets;
}

export function generateReplacementOptions(asset) {
  const baseMultiplier = {
    [ASSET_TYPES.RTU]: { cost: 8000, life: 15 },
    [ASSET_TYPES.AHU]: { cost: 25000, life: 20 },
    [ASSET_TYPES.COMPRESSOR_RACK]: { cost: 75000, life: 15 },
    [ASSET_TYPES.WALK_IN_COOLER]: { cost: 15000, life: 20 },
    [ASSET_TYPES.WALK_IN_FREEZER]: { cost: 25000, life: 20 },
    [ASSET_TYPES.REACH_IN_CASE]: { cost: 5000, life: 12 },
    [ASSET_TYPES.CONDENSING_UNIT]: { cost: 8000, life: 15 }
  };
  
  const base = baseMultiplier[asset.assetType] || { cost: 10000, life: 15 };
  const capacityFactor = Math.max(1, asset.capacityNominal / 10);
  
  return [
    createReplacementOption({
      optionId: `${asset.assetId}-opt-standard`,
      replacementOptionSetId: asset.replacementOptionSetId,
      optionName: 'Standard Replacement',
      capexInstalledCost: Math.round(base.cost * capacityFactor),
      expectedLifeYears: base.life,
      expectedEfficiencyDelta: 0.10,
      expectedMaintenanceDeltaPerYear: -500,
      leadTimeDays: 21,
      warrantyYears: 1
    }),
    createReplacementOption({
      optionId: `${asset.assetId}-opt-higheff`,
      replacementOptionSetId: asset.replacementOptionSetId,
      optionName: 'High Efficiency',
      capexInstalledCost: Math.round(base.cost * capacityFactor * 1.35),
      expectedLifeYears: base.life + 3,
      expectedEfficiencyDelta: 0.25,
      expectedMaintenanceDeltaPerYear: -800,
      leadTimeDays: 35,
      warrantyYears: 3
    }),
    createReplacementOption({
      optionId: `${asset.assetId}-opt-premium`,
      replacementOptionSetId: asset.replacementOptionSetId,
      optionName: 'Premium / VRF',
      capexInstalledCost: Math.round(base.cost * capacityFactor * 1.8),
      expectedLifeYears: base.life + 5,
      expectedEfficiencyDelta: 0.35,
      expectedMaintenanceDeltaPerYear: -1200,
      leadTimeDays: 60,
      warrantyYears: 5
    })
  ];
}

export function generateSampleUtilityRate(storeId, climateZone) {
  const baseRate = climateZone.startsWith('1') || climateZone.startsWith('2') ? 0.14 :
                   climateZone.startsWith('5') || climateZone.startsWith('6') ? 0.11 : 0.12;
  
  return createUtilityRate({
    utilityRateId: `rate-${storeId}`,
    currency: 'USD',
    rateType: 'TOU',
    energyRateSchedule: {
      offPeak: baseRate * 0.7,
      midPeak: baseRate,
      onPeak: baseRate * 1.5,
      default: baseRate
    },
    demandChargeSchedule: {
      summer: 15,
      winter: 10
    },
    escalationRateAssumption: 0.03
  });
}

export function generateSampleEconomicAssumptions(storeId) {
  return createEconomicAssumption({
    storeId,
    discountRate: 0.08,
    analysisHorizonYears: 10,
    inflationAssumption: 0.025,
    failureEventCostByAssetType: {
      [ASSET_TYPES.RTU]: 15000,
      [ASSET_TYPES.AHU]: 20000,
      [ASSET_TYPES.COMPRESSOR_RACK]: 75000,
      [ASSET_TYPES.WALK_IN_COOLER]: 25000,
      [ASSET_TYPES.WALK_IN_FREEZER]: 50000,
      [ASSET_TYPES.REACH_IN_CASE]: 8000,
      [ASSET_TYPES.CONDENSING_UNIT]: 12000
    },
    truckRollCost: 250,
    laborRate: 95
  });
}

export function generateCompleteStoreData(count = 5) {
  const stores = generateSampleStores(count);
  const allAssets = [];
  const allOptions = [];
  const utilityRates = [];
  const economicAssumptions = [];
  
  stores.forEach(store => {
    const assets = generateSampleAssets(store.storeId, store.storeType);
    allAssets.push(...assets);
    
    assets.forEach(asset => {
      const options = generateReplacementOptions(asset);
      allOptions.push(...options);
    });
    
    utilityRates.push(generateSampleUtilityRate(store.storeId, store.climateZone));
    economicAssumptions.push(generateSampleEconomicAssumptions(store.storeId));
  });
  
  return {
    stores,
    assets: allAssets,
    replacementOptions: allOptions,
    utilityRates,
    economicAssumptions
  };
}
