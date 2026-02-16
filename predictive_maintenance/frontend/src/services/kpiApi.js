/**
 * KPI Dashboard API Service
 *
 * Centralizes all KPI-related API calls used by KpiDashboard and related components.
 */

import { request, safeRequest } from './apiClient';

const KPI_BASE = '/api/v1/kpi';

const KpiApiService = {
  /** Fetch the full KPI dashboard for a site. */
  getDashboard(siteId = 'default') {
    return request(`${KPI_BASE}/${siteId}/dashboard`);
  },

  /** Run CapEx analysis for a site. */
  getCapex(siteId = 'default', { budget = 1000000, objective = 'max_expected_npv' } = {}) {
    return request(`${KPI_BASE}/${siteId}/capex?budget=${budget}&objective=${objective}`);
  },

  /** Approve or reject a KPI result. */
  approveKpi(siteId = 'default', kpiName, action) {
    return request(`${KPI_BASE}/${siteId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ kpi_name: kpiName, action }),
    });
  },

  /** Export ROI workbook. Returns a blob URL for download. */
  async exportRoiWorkbook(payload) {
    const res = await fetch('/api/v1/export/roi-workbook', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Export failed: ${res.status}`);
    }
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  },
};

export default KpiApiService;
