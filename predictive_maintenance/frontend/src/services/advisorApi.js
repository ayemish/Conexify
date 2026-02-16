/**
 * Advisor API Service
 *
 * Wraps all Scenario Advisor endpoints with typed methods.
 * Uses the shared apiClient for consistent error handling.
 * Base URL: /api/advisor (same-origin via Vite proxy).
 */

import { request } from './apiClient';

const BASE = '/api/advisor';

const AdvisorApiService = {
  /** Create a new chat session. */
  createSession(ecosystem = 'auto') {
    return request(`${BASE}/chat`, {
      method: 'POST',
      body: JSON.stringify({ ecosystem }),
    });
  },

  /** Send a message to a session. */
  sendMessage(sessionId, message, stream = false) {
    return request(`${BASE}/chat/${sessionId}/message`, {
      method: 'POST',
      body: JSON.stringify({ message, stream }),
    });
  },

  /** Get conversation history. */
  getHistory(sessionId) {
    return request(`${BASE}/chat/${sessionId}/history`);
  },

  /** Delete a session. */
  deleteSession(sessionId) {
    return request(`${BASE}/chat/${sessionId}`, { method: 'DELETE' });
  },

  /** List scenarios for an ecosystem. */
  getScenarios(ecosystem = 'maintenance') {
    return request(`${BASE}/scenarios/${ecosystem}`);
  },

  /** List agents for an ecosystem. */
  getAgents(ecosystem = 'maintenance') {
    return request(`${BASE}/agents/${ecosystem}`);
  },

  /** Get system status. */
  getStatus() {
    return request(`${BASE}/status`);
  },

  /** Get current portfolio state, optionally with live KPI data. */
  getCurrentState(siteId = null, includeKpis = false) {
    const params = new URLSearchParams();
    if (siteId) params.set('site_id', siteId);
    if (includeKpis) params.set('include_kpis', 'true');
    const qs = params.toString() ? `?${params}` : '';
    return request(`${BASE}/current-state${qs}`);
  },

  /** Semantic search over knowledge base. */
  searchKnowledge(query, topK = 4) {
    return request(`${BASE}/search`, {
      method: 'POST',
      body: JSON.stringify({ query, top_k: topK }),
    });
  },
};

export default AdvisorApiService;
