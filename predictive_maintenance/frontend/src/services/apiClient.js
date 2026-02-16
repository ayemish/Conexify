/**
 * Shared API Client
 *
 * Centralized fetch wrapper used by all domain-specific API services.
 * Handles JSON serialization, error normalization, and base URL configuration.
 */

const API_BASE = '';  // Same-origin via Vite proxy

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const config = {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  };

  const res = await fetch(url, config);

  if (options.method === 'DELETE' && res.status === 204) return null;

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || err.error || `Request failed: ${res.status}`);
  }

  return res.json();
}

/**
 * Safe wrapper that returns { ok, data, error } instead of throwing.
 */
async function safeRequest(path, options = {}) {
  try {
    const data = await request(path, options);
    return { ok: true, data, error: null };
  } catch (err) {
    return { ok: false, data: null, error: err.message };
  }
}

export { request, safeRequest, API_BASE };
export default request;
