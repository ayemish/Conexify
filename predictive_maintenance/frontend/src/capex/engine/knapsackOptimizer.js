import { DECISION_TYPES } from '../data/models.js';

export function solveKnapsack(items, budget) {
  const n = items.length;
  if (n === 0 || budget <= 0) return { selected: [], totalCost: 0, totalNpv: 0 };
  
  const scaleFactor = 100;
  const scaledBudget = Math.floor(budget / scaleFactor);
  
  const dp = new Array(n + 1).fill(null).map(() => new Array(scaledBudget + 1).fill(0));
  const keep = new Array(n + 1).fill(null).map(() => new Array(scaledBudget + 1).fill(false));
  
  for (let i = 1; i <= n; i++) {
    const item = items[i - 1];
    const scaledCost = Math.ceil(item.cost / scaleFactor);
    const value = item.npv;
    
    for (let w = 0; w <= scaledBudget; w++) {
      if (scaledCost <= w && value > 0) {
        const withItem = dp[i - 1][w - scaledCost] + value;
        const withoutItem = dp[i - 1][w];
        
        if (withItem > withoutItem) {
          dp[i][w] = withItem;
          keep[i][w] = true;
        } else {
          dp[i][w] = withoutItem;
          keep[i][w] = false;
        }
      } else {
        dp[i][w] = dp[i - 1][w];
        keep[i][w] = false;
      }
    }
  }
  
  const selected = [];
  let w = scaledBudget;
  for (let i = n; i > 0; i--) {
    if (keep[i][w]) {
      selected.push(items[i - 1]);
      w -= Math.ceil(items[i - 1].cost / scaleFactor);
    }
  }
  
  selected.reverse();
  
  const totalCost = selected.reduce((sum, item) => sum + item.cost, 0);
  const totalNpv = selected.reduce((sum, item) => sum + item.npv, 0);
  
  return { selected, totalCost, totalNpv };
}

export function greedyKnapsack(items, budget) {
  const validItems = items.filter(item => item.cost <= budget && item.npv > 0);
  
  const sorted = [...validItems].sort((a, b) => {
    const ratioA = a.npv / a.cost;
    const ratioB = b.npv / b.cost;
    return ratioB - ratioA;
  });
  
  const selected = [];
  let remainingBudget = budget;
  
  for (const item of sorted) {
    if (item.cost <= remainingBudget) {
      selected.push(item);
      remainingBudget -= item.cost;
    }
  }
  
  const totalCost = selected.reduce((sum, item) => sum + item.cost, 0);
  const totalNpv = selected.reduce((sum, item) => sum + item.npv, 0);
  
  return { selected, totalCost, totalNpv };
}

export function optimizeCapexPlan(evaluatedAssets, budget, objective = 'max_expected_npv') {
  const candidates = evaluatedAssets
    .filter(a => a.recommendation.decision === DECISION_TYPES.REPLACE && a.bestOption)
    .map(a => ({
      assetId: a.asset.assetId,
      asset: a.asset,
      cost: a.bestOption.capex,
      npv: a.bestOption.npv,
      npvPerDollar: a.bestOption.npvPerCapexDollar,
      riskScore: a.score.riskScore,
      priorityScore: a.score.replacePriorityScore,
      option: a.bestOption,
      evaluation: a
    }));
  
  let items = candidates;
  
  if (objective === 'risk_reduction') {
    items = candidates.map(c => ({
      ...c,
      npv: c.riskScore * 1000
    }));
  } else if (objective === 'blended') {
    items = candidates.map(c => ({
      ...c,
      npv: c.npv * 0.5 + c.riskScore * 500 + c.priorityScore * 300
    }));
  }
  
  const dpResult = solveKnapsack(items, budget);
  const greedyResult = greedyKnapsack(items, budget);
  
  const bestResult = dpResult.totalNpv >= greedyResult.totalNpv ? dpResult : greedyResult;
  
  const selectedIds = new Set(bestResult.selected.map(s => s.assetId));
  
  const result = evaluatedAssets.map(a => {
    const isSelected = selectedIds.has(a.asset.assetId);
    const candidate = candidates.find(c => c.assetId === a.asset.assetId);
    
    return {
      ...a,
      planItem: {
        assetId: a.asset.assetId,
        decision: isSelected ? DECISION_TYPES.REPLACE : 
                  a.recommendation.decision === DECISION_TYPES.REPLACE ? DECISION_TYPES.DEFER :
                  a.recommendation.decision,
        selectedOptionId: isSelected ? a.bestOption?.optionId : null,
        capexCost: isSelected ? a.bestOption?.capex || 0 : 0,
        npvP50: a.bestOption?.npv || 0,
        pNpvPositive: a.bestOption?.pNpvPositive || 0,
        isInBudget: isSelected,
        reason: isSelected ? 'Selected for budget optimization' :
                a.recommendation.decision === DECISION_TYPES.REPLACE ? 'Deferred due to budget constraints' :
                a.recommendation.reason
      }
    };
  });
  
  return {
    items: result,
    summary: {
      budget,
      totalSelectedCost: bestResult.totalCost,
      totalExpectedNpv: bestResult.totalNpv,
      remainingBudget: budget - bestResult.totalCost,
      assetsSelected: bestResult.selected.length,
      assetsDeferred: candidates.length - bestResult.selected.length,
      assetsTotal: evaluatedAssets.length,
      utilizationPct: Math.round((bestResult.totalCost / budget) * 100)
    }
  };
}

export function sensitivityAnalysis(evaluatedAssets, baseBudget, steps = 5) {
  const results = [];
  const budgetMultipliers = [0.5, 0.75, 1.0, 1.25, 1.5];
  
  budgetMultipliers.forEach(mult => {
    const testBudget = Math.round(baseBudget * mult);
    const plan = optimizeCapexPlan(evaluatedAssets, testBudget);
    
    results.push({
      budgetMultiplier: mult,
      budget: testBudget,
      assetsSelected: plan.summary.assetsSelected,
      totalNpv: plan.summary.totalExpectedNpv,
      utilizationPct: plan.summary.utilizationPct,
      marginalNpvPerDollar: mult > 0.5 ? 
        (plan.summary.totalExpectedNpv - results[results.length - 1]?.totalNpv || 0) / 
        (testBudget - results[results.length - 1]?.budget || testBudget) : null
    });
  });
  
  return results;
}

export function getNextBestAssets(evaluatedAssets, currentPlan, count = 3) {
  const selectedIds = new Set(
    currentPlan.items.filter(i => i.planItem.isInBudget).map(i => i.asset.assetId)
  );
  
  const deferred = evaluatedAssets
    .filter(a => 
      !selectedIds.has(a.asset.assetId) && 
      a.recommendation.decision === DECISION_TYPES.REPLACE &&
      a.bestOption?.npv > 0
    )
    .sort((a, b) => b.bestOption.npvPerCapexDollar - a.bestOption.npvPerCapexDollar)
    .slice(0, count);
  
  return deferred.map(a => ({
    assetId: a.asset.assetId,
    assetType: a.asset.assetType,
    additionalCost: a.bestOption.capex,
    additionalNpv: a.bestOption.npv,
    npvPerDollar: a.bestOption.npvPerCapexDollar,
    priorityScore: a.score.replacePriorityScore
  }));
}
