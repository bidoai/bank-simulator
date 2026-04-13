/**
 * Shared API client for all Apex Bank dashboards.
 *
 * Usage:
 *   const data = await apiFetch('/api/trading/greeks');
 *   const result = await apiPost('/api/trading/orders', { ticker: 'AAPL', ... });
 *
 * Both functions return the parsed JSON object, or null on error.
 * Errors are logged to the browser console with the endpoint path.
 */

const API_BASE = typeof window !== 'undefined' && window.API_BASE ? window.API_BASE : '';

async function apiFetch(path, options = {}) {
    try {
        const res = await fetch(API_BASE + path, options);
        if (!res.ok) {
            console.warn(`[api-client] ${res.status} ${res.statusText} — ${path}`);
            return null;
        }
        return await res.json();
    } catch (err) {
        console.warn(`[api-client] fetch failed — ${path}:`, err.message);
        return null;
    }
}

async function apiPost(path, body, options = {}) {
    return apiFetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
        body: JSON.stringify(body),
        ...options,
    });
}
