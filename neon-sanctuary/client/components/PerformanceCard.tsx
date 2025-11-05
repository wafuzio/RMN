import React, { useEffect, useMemo, useState } from 'react';
import { dump } from '../lib/metrics';

function formatBytes(n: number) {
  if (n > 1024*1024) return (n/(1024*1024)).toFixed(1) + ' MB';
  if (n > 1024) return (n/1024).toFixed(1) + ' KB';
  return n + ' B';
}

export const PerformanceCard: React.FC = () => {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    const id = setInterval(() => setData(dump()), 1000);
    setData(dump());
    return () => clearInterval(id);
  }, []);
  const devMode = useMemo(() => new URLSearchParams(location.search).get('devperf') === '1', []);
  if (!devMode) return null;

  const marks = data?.marks || [];
  const res = data?.resources || {};
  return (
    <div style={{
      position: 'fixed', right: 12, bottom: 12, zIndex: 99999,
      background: '#111', color: '#eee', padding: 12, borderRadius: 8, width: 300,
      boxShadow: '0 6px 20px rgba(0,0,0,0.35)', fontFamily: 'system-ui, sans-serif', fontSize: 12
    }}>
      <div style={{fontWeight:'bold', marginBottom: 6}}>Performance</div>
      <div>TTFB: {Math.round(data?.ttfb ?? 0)} ms</div>
      <div>LCP: {Math.round(data?.lcp ?? 0)} ms</div>
      <div>DOM Loaded: {Math.round(data?.domContentLoaded ?? 0)} ms</div>
      <div>Window Load: {Math.round(data?.loadEvent ?? 0)} ms</div>
      <div style={{marginTop: 8}}>Requests: {res.totalRequests} (cache hits {res.cacheHits})</div>
      <div>Transferred: {formatBytes(res.totalBytes || 0)}</div>
      <div style={{marginTop:8, maxHeight:120, overflow:'auto', borderTop: '1px solid #333', paddingTop: 8}}>
        {marks.slice(-8).map((m:any, i:number) => (
          <div key={i}>
            {m.name} — {Math.round(m.value)} ms
          </div>
        ))}
      </div>
    </div>
  );
};
