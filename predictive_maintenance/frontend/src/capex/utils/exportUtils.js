import * as XLSX from 'xlsx';

export function exportToExcel(analysisResult, filename = 'capex-plan.xlsx') {
  const wb = XLSX.utils.book_new();
  
  const summaryData = [
    ['CapEx Plan Summary'],
    [''],
    ['Store', analysisResult.store.name],
    ['Generated', new Date().toLocaleDateString()],
    [''],
    ['Budget', formatCurrency(analysisResult.budget)],
    ['Total CapEx Selected', formatCurrency(analysisResult.summary.totalCapexSelected)],
    ['Remaining Budget', formatCurrency(analysisResult.summary.remainingBudget)],
    ['Budget Utilization', `${analysisResult.summary.budgetUtilization}%`],
    [''],
    ['Expected NPV', formatCurrency(analysisResult.summary.totalExpectedNpv)],
    ['Annual Savings', formatCurrency(analysisResult.summary.totalAnnualSavings)],
    ['Avg Payback', `${analysisResult.summary.avgSimplePaybackYears} years`],
    [''],
    ['Assets Analyzed', analysisResult.summary.assetsAnalyzed],
    ['Assets for Replacement', analysisResult.summary.assetsSelectedForReplacement],
    ['Assets Deferred', analysisResult.summary.assetsDeferred]
  ];
  
  const summaryWs = XLSX.utils.aoa_to_sheet(summaryData);
  summaryWs['!cols'] = [{ wch: 25 }, { wch: 20 }];
  XLSX.utils.book_append_sheet(wb, summaryWs, 'Summary');
  
  const assetHeaders = [
    'Asset ID', 'Asset Type', 'Manufacturer', 'Model', 'Age (Years)',
    'Decision', 'In Budget', 'CapEx Cost', 'Expected NPV', 'Payback (Years)',
    'Priority Score', 'Condition Score', 'Risk Score', 'Energy Waste Score',
    'Peer Percentile', 'Top Drivers', 'Recommendation Reason'
  ];
  
  const assetRows = analysisResult.optimizedPlan.items.map(item => [
    item.asset.assetId,
    item.asset.assetType,
    item.asset.manufacturer,
    item.asset.model,
    item.asset.ageYears,
    item.planItem.decision,
    item.planItem.isInBudget ? 'Yes' : 'No',
    item.planItem.capexCost,
    item.planItem.npvP50,
    item.bestOption?.simplePaybackYears || '-',
    item.score.replacePriorityScore,
    item.score.conditionScore,
    item.score.riskScore,
    item.score.energyWasteScore,
    item.peerComparison.peerComparison.overall.percentile,
    (item.score.explainTopDrivers || []).join('; '),
    item.planItem.reason
  ]);
  
  const assetWs = XLSX.utils.aoa_to_sheet([assetHeaders, ...assetRows]);
  assetWs['!cols'] = assetHeaders.map((_, i) => ({ wch: i === 15 ? 40 : i === 16 ? 50 : 15 }));
  XLSX.utils.book_append_sheet(wb, assetWs, 'Asset Details');
  
  const replaceItems = analysisResult.optimizedPlan.items.filter(i => i.planItem.isInBudget);
  if (replaceItems.length > 0) {
    const replaceHeaders = [
      'Asset ID', 'Asset Type', 'Selected Option', 'CapEx Cost', 
      'Expected NPV', 'Annual Savings', 'Payback (Years)', 'IRR (%)',
      'PV Keep Costs', 'PV Replace Costs'
    ];
    
    const replaceRows = replaceItems.map(item => [
      item.asset.assetId,
      item.asset.assetType,
      item.bestOption?.optionName || '-',
      item.bestOption?.capex || 0,
      item.bestOption?.npv || 0,
      item.bestOption?.avgAnnualSavings || 0,
      item.bestOption?.simplePaybackYears || '-',
      item.bestOption?.irr || '-',
      item.bestOption?.pvKeep || 0,
      item.bestOption?.pvReplace || 0
    ]);
    
    const replaceWs = XLSX.utils.aoa_to_sheet([replaceHeaders, ...replaceRows]);
    replaceWs['!cols'] = replaceHeaders.map(() => ({ wch: 18 }));
    XLSX.utils.book_append_sheet(wb, replaceWs, 'Replacements');
  }
  
  const sensitivityHeaders = ['Budget Multiplier', 'Budget', 'Assets Selected', 'Total NPV', 'Utilization %'];
  const sensitivityRows = analysisResult.sensitivity.map(s => [
    `${s.budgetMultiplier}x`,
    s.budget,
    s.assetsSelected,
    s.totalNpv,
    `${s.utilizationPct}%`
  ]);
  
  const sensitivityWs = XLSX.utils.aoa_to_sheet([sensitivityHeaders, ...sensitivityRows]);
  sensitivityWs['!cols'] = sensitivityHeaders.map(() => ({ wch: 18 }));
  XLSX.utils.book_append_sheet(wb, sensitivityWs, 'Sensitivity');
  
  const byTypeHeaders = ['Asset Type', 'Count', 'Total Cost', 'Total NPV'];
  const byTypeRows = Object.entries(analysisResult.summary.breakdownByAssetType).map(([type, data]) => [
    type, data.count, data.totalCost, data.totalNpv
  ]);
  
  const byTypeWs = XLSX.utils.aoa_to_sheet([byTypeHeaders, ...byTypeRows]);
  byTypeWs['!cols'] = byTypeHeaders.map(() => ({ wch: 18 }));
  XLSX.utils.book_append_sheet(wb, byTypeWs, 'By Asset Type');
  
  XLSX.writeFile(wb, filename);
}

export function exportToCsv(analysisResult, filename = 'capex-assets.csv') {
  const headers = [
    'Asset ID', 'Asset Type', 'Manufacturer', 'Model', 'Age (Years)',
    'Decision', 'In Budget', 'CapEx Cost', 'Expected NPV', 
    'Priority Score', 'Peer Percentile', 'Reason'
  ];
  
  const rows = analysisResult.optimizedPlan.items.map(item => [
    item.asset.assetId,
    item.asset.assetType,
    item.asset.manufacturer,
    item.asset.model,
    item.asset.ageYears,
    item.planItem.decision,
    item.planItem.isInBudget ? 'Yes' : 'No',
    item.planItem.capexCost,
    item.planItem.npvP50,
    item.score.replacePriorityScore,
    item.peerComparison.peerComparison.overall.percentile,
    `"${item.planItem.reason}"`
  ]);
  
  const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
  
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
}

function formatCurrency(value) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value);
}
