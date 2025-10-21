// Route all image URLs through same-origin /api or a proxy,
// so the browser gets real image/* responses (not ngrok HTML).
export function toLocalImageUrl(u?: string) {
  if (!u) return '';
  if (u.startsWith('blob:') || u.startsWith('data:')) return u;

  // Absolute URL?
  if (/^https?:\/\//i.test(u)) {
    try {
      const abs = new URL(u);
      // If it's already our host, return path+query (same-origin)
      if (abs.host === window.location.host) {
        return abs.pathname + abs.search;
      }
      // Otherwise go through backend proxy (see Step 4), avoids ORB
      return `/proxy-image?url=${encodeURIComponent(abs.toString())}`;
    } catch {
      // If URL constructor fails, fall through to relative handling
    }
  }

  // Relative path: ensure it's under /api so Vite proxy handles it
  return u.startsWith('/api') ? u : `/api${u.startsWith('/') ? '' : '/'}${u}`;
}
