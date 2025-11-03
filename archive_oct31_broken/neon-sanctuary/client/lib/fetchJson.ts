import { apiUrl, API_BASE } from './apiBase';

export async function fetchJson(path: string, init: RequestInit = {}) {
  const url = apiUrl(path);
  const headers = new Headers(init.headers || {});
  headers.set('Accept', 'application/json');
  if (API_BASE) headers.set('ngrok-skip-browser-warning', 'true');

  const res = await fetch(url, { ...init, headers, mode: 'cors', credentials: 'omit', cache: 'no-store' });
  if (!res.ok) {
    const t = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status} @ ${url}\n${t.slice(0, 400)}`);
  }
  return res.json();
}
