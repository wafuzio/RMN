// Lightweight performance metrics store for the UI and console.
type Metric = {
  name: string;
  value: number;
  unit?: string;
  meta?: Record<string, any>;
  at?: number; // ms since navigationStart
};

type PerfState = {
  marks: Metric[];
  counters: Record<string, number>;
};

const state: PerfState = { marks: [], counters: {} };

export function mark(name: string, value: number, unit?: string, meta?: Record<string, any>) {
  state.marks.push({ name, value, unit, meta, at: performance.now() });
}

export function count(name: string, inc = 1) {
  state.counters[name] = (state.counters[name] || 0) + inc;
}

export function readServerTiming(headers: Headers) {
  const st = headers.get('server-timing');
  if (!st) return;
  // Example: "ads;dur=123, brands;dur=45"
  const parts = st.split(',');
  for (const p of parts) {
    const [token, ...rest] = p.trim().split(';');
    const dur = rest.find((r) => r.trim().startsWith('dur='));
    if (dur) {
      const val = parseFloat(dur.split('=')[1]);
      if (!Number.isNaN(val)) mark(`srv:${token}`, val, 'ms');
    }
  }
}

export function collectResourceSummary() {
  const entries = performance.getEntriesByType('resource') as PerformanceResourceTiming[];
  let totalBytes = 0, total = 0, cached = 0;
  for (const e of entries) {
    total++;
    totalBytes += (e.transferSize || 0);
    if (e.transferSize === 0 && e.encodedBodySize > 0) cached++; // strong proxy for cache hit
  }
  return { totalRequests: total, totalBytes, cacheHits: cached };
}

// Store LCP value from PerformanceObserver
let cachedLCP: number | undefined;

// Modern LCP observer (runs once on module load)
if (typeof window !== 'undefined' && 'PerformanceObserver' in window) {
  try {
    const observer = new PerformanceObserver((list) => {
      const entries = list.getEntries();
      const lastEntry = entries[entries.length - 1] as any;
      cachedLCP = lastEntry?.startTime;
    });
    observer.observe({ type: 'largest-contentful-paint', buffered: true });
  } catch (e) {
    // Silently fail if LCP is not supported
  }
}

export function userTimingSnapshot() {
  const nav = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined;
  return {
    ttfb: nav ? nav.responseStart - nav.requestStart : undefined,
    domContentLoaded: nav ? nav.domContentLoadedEventEnd - nav.startTime : undefined,
    loadEvent: nav ? nav.loadEventEnd - nav.startTime : undefined,
    lcp: cachedLCP,
  };
}

export function dump() {
  const res = collectResourceSummary();
  return { ...userTimingSnapshot(), marks: state.marks, counters: state.counters, resources: res };
}

// Debug helper in console
// window.__perf.dump()
;(window as any).__perf = { mark, count, dump };
