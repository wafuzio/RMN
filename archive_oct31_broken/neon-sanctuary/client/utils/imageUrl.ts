// Route all image URLs through same-origin /api or a proxy,
// so the browser gets real image/* responses (not ngrok HTML).
declare global {
  interface Window { AD_BASE?: string }
}

export function toLocalImageUrl(u?: string | null) {
  const base = (typeof window !== 'undefined' ? window.AD_BASE : '') || '';

  // Reject falsy or whitespace-only strings (null/undefined is acceptable)
  if (!u || typeof u !== 'string' || !u.trim()) {
    // Only warn if it's an unexpected type (not null/undefined which are common from API)
    if (u !== null && u !== undefined && typeof u !== 'string') {
      console.warn('Invalid image URL type provided to toLocalImageUrl:', typeof u);
    }
    return null as unknown as string; // preserve type "string" if callers expect it, but return a falsy
  }

  const s = u.trim();

  // Data URLs are fine
  if (s.startsWith('data:')) return s;

  // Our API assets (/api/...)
  if (s.startsWith('/api/')) return base ? `${base}${s}` : s;

  // External absolute URLs → route via proxy so <img> gets image/*
  if (/^https?:\/\//i.test(s)) {
    return base ? `${base}/api/proxy-image?url=${encodeURIComponent(s)}` : s;
  }

  // Absolute path on same origin
  if (s.startsWith('/')) return base ? `${base}${s}` : s;

  // Unknown relative path → treat as invalid
  console.warn('Unhandled image URL shape:', s);
  return null as unknown as string;
}
