// Route all image URLs through same-origin /api or a proxy,
// so the browser gets real image/* responses (not ngrok HTML).
export function toLocalImageUrl(u?: string) {
  if (!u || typeof u !== 'string') {
    console.warn('Invalid image URL provided to toLocalImageUrl:', u, typeof u);
    return '';
  }

  const trimmed = u.trim();
  if (!trimmed) return '';

  if (trimmed.startsWith('blob:') || trimmed.startsWith('data:')) return trimmed;

  // Absolute URL?
  if (/^https?:\/\//i.test(trimmed)) {
    try {
      const abs = new URL(trimmed);
      // If it's already our host, return path+query (same-origin)
      if (abs.host === window.location.host) {
        return abs.pathname + abs.search;
      }
      // Otherwise go through backend proxy to avoid CORS issues
      return `/proxy-image?url=${encodeURIComponent(abs.toString())}`;
    } catch (error) {
      console.warn('Invalid URL provided to toLocalImageUrl:', {
        url: trimmed,
        error: error instanceof Error ? error.message : String(error),
      });
      // If URL constructor fails, fall through to relative handling
    }
  }

  // Relative path: ensure it's under /api so Vite proxy handles it
  if (!trimmed.startsWith('/api')) {
    return `/api${trimmed.startsWith('/') ? '' : '/'}${trimmed}`;
  }
  return trimmed;
}
