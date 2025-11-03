const RAW = (import.meta.env.VITE_API_BASE || '').trim().replace(/\/+$/, '');
export const API_BASE = RAW; // '' locally, 'https://<ngrok>' for Builder

export function apiUrl(path: string) {
  // Always talk to Flask under /api/*
  const p = path.startsWith('/api') ? path : `/api${path.startsWith('/') ? path : `/${path}`}`;
  return `${API_BASE}${p}`;
}

if (typeof window !== 'undefined') {
  console.info('[api] API_BASE:', API_BASE || '(relative via Vite proxy)');
}
