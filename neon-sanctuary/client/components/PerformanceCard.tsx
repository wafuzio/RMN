import React, { useEffect, useMemo, useState } from 'react';
import { dump } from '../lib/metrics';

function formatBytes(n: number) {
  if (n > 1024*1024) return (n/(1024*1024)).toFixed(1) + ' MB';
  if (n > 1024) return (n/1024).toFixed(1) + ' KB';
  return n + ' B';
}

export const PerformanceCard: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [copied, setCopied] = useState(false);
  
  useEffect(() => {
    const id = setInterval(() => setData(dump()), 1000);
    setData(dump());
    return () => clearInterval(id);
  }, []);
  
  const devMode = useMemo(() => new URLSearchParams(location.search).get('devperf') === '1', []);
  if (!devMode) return null;

  const handleCopy = () => {
    const marks = data?.marks || [];
    const res = data?.resources || {};
    const counters = data?.counters || {};
    
    const text = `Performance Metrics
==================
TTFB: ${Math.round(data?.ttfb ?? 0)} ms
LCP: ${Math.round(data?.lcp ?? 0)} ms
DOM Loaded: ${Math.round(data?.domContentLoaded ?? 0)} ms
Window Load: ${Math.round(data?.loadEvent ?? 0)} ms

Requests: ${res.totalRequests} (cache hits ${res.cacheHits})
Transferred: ${formatBytes(res.totalBytes || 0)}
${counters.dedupe_abort > 0 ? `Duplicates prevented: ${counters.dedupe_abort}\n` : ''}
Recent API Calls:
${marks.slice(-16).map((m: any) => `  ${m.name} — ${Math.round(m.value)} ms`).join('\n')}`;
    
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const marks = data?.marks || [];
  const res = data?.resources || {};
  const counters = data?.counters || {};
  
  return (
    <div style={{
      position: 'fixed', right: 12, bottom: 12, zIndex: 99999,
      background: '#111', color: '#eee', padding: 12, borderRadius: 8, width: 300,
      boxShadow: '0 6px 20px rgba(0,0,0,0.35)', fontFamily: 'system-ui, sans-serif', fontSize: 12
    }}>
      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6}}>
        <div style={{fontWeight:'bold'}}>Performance</div>
        <button
          onClick={handleCopy}
          style={{
            background: copied ? '#2a2' : '#333',
            color: '#fff',
            border: 'none',
            padding: '4px 8px',
            borderRadius: 4,
            cursor: 'pointer',
            fontSize: 11
          }}
        >
          {copied ? '✓ Copied' : 'Copy'}
        </button>
      </div>
      <div>TTFB: {Math.round(data?.ttfb ?? 0)} ms</div>
      <div>LCP: {Math.round(data?.lcp ?? 0)} ms</div>
      <div>DOM Loaded: {Math.round(data?.domContentLoaded ?? 0)} ms</div>
      <div>Window Load: {Math.round(data?.loadEvent ?? 0)} ms</div>
      <div style={{marginTop: 8}}>Requests: {res.totalRequests} (cache hits {res.cacheHits})</div>
      <div>Transferred: {formatBytes(res.totalBytes || 0)}</div>
      {counters.dedupe_abort > 0 && (
        <div style={{color: '#4a4'}}>Duplicates prevented: {counters.dedupe_abort}</div>
      )}
      <div style={{marginTop:8, maxHeight:240, overflow:'auto', borderTop: '1px solid #333', paddingTop: 8}}>
        {marks.slice(-16).map((m:any, i:number) => (
          <div key={i}>
            {m.name} — {Math.round(m.value)} ms
          </div>
        ))}
      </div>
    </div>
  );
};
