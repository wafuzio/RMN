import React, { useEffect, useMemo, useState, useRef } from 'react';
import { dump } from '../lib/metrics';

function formatBytes(n: number) {
  if (n > 1024*1024) return (n/(1024*1024)).toFixed(1) + ' MB';
  if (n > 1024) return (n/1024).toFixed(1) + ' KB';
  return n + ' B';
}

interface PageLoadSnapshot {
  timestamp: number;
  ttfb: number;
  lcp: number;
  domContentLoaded: number;
  loadEvent: number;
  totalRequests: number;
  cacheHits: number;
  totalBytes: number;
  dedupeAbort: number;
  apiCalls: Array<{name: string; value: number}>;
}

export const PerformanceCard: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [copied, setCopied] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [snapshots, setSnapshots] = useState<PageLoadSnapshot[]>([]);
  const lastLoadEvent = useRef<number>(0);
  
  useEffect(() => {
    const id = setInterval(() => {
      const currentData = dump();
      setData(currentData);
      
      // Capture snapshot when window.load event completes (and changes)
      if (currentData?.loadEvent && currentData.loadEvent !== lastLoadEvent.current && currentData.loadEvent > 0) {
        lastLoadEvent.current = currentData.loadEvent;
        const snapshot: PageLoadSnapshot = {
          timestamp: Date.now(),
          ttfb: currentData.ttfb ?? 0,
          lcp: currentData.lcp ?? 0,
          domContentLoaded: currentData.domContentLoaded ?? 0,
          loadEvent: currentData.loadEvent ?? 0,
          totalRequests: currentData.resources?.totalRequests ?? 0,
          cacheHits: currentData.resources?.cacheHits ?? 0,
          totalBytes: currentData.resources?.totalBytes ?? 0,
          dedupeAbort: currentData.counters?.dedupe_abort ?? 0,
          apiCalls: (currentData.marks || []).slice(-16)
        };
        setSnapshots(prev => [...prev.slice(-3), snapshot]); // Keep last 4
      }
    }, 1000);
    
    // Initial data capture
    const initialData = dump();
    setData(initialData);
    
    // Capture initial snapshot after a delay to ensure metrics are ready
    const captureTimeout = setTimeout(() => {
      const currentData = dump();
      if (currentData?.loadEvent && currentData.loadEvent > 0) {
        lastLoadEvent.current = currentData.loadEvent;
        const snapshot: PageLoadSnapshot = {
          timestamp: Date.now(),
          ttfb: currentData.ttfb ?? 0,
          lcp: currentData.lcp ?? 0,
          domContentLoaded: currentData.domContentLoaded ?? 0,
          loadEvent: currentData.loadEvent ?? 0,
          totalRequests: currentData.resources?.totalRequests ?? 0,
          cacheHits: currentData.resources?.cacheHits ?? 0,
          totalBytes: currentData.resources?.totalBytes ?? 0,
          dedupeAbort: currentData.counters?.dedupe_abort ?? 0,
          apiCalls: (currentData.marks || []).slice(-16)
        };
        setSnapshots(prev => [...prev.slice(-3), snapshot]); // Keep last 4
      }
    }, 2000); // Wait 2 seconds for page to fully load
    
    return () => {
      clearInterval(id);
      clearTimeout(captureTimeout);
    };
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
  
  const Delta = ({ current, previous, unit = 'ms', invert = false }: { current: number; previous: number; unit?: string; invert?: boolean }) => {
    const delta = current - previous;
    const isImprovement = invert ? delta > 0 : delta < 0;
    const color = delta === 0 ? '#888' : isImprovement ? '#2a2' : '#d44';
    const sign = delta > 0 ? '+' : '';
    return <span style={{color, fontSize: 10, marginLeft: 4}}>({sign}{Math.round(delta)}{unit})</span>;
  };
  
  // Render current card (always visible in same position)
  const renderCurrentCard = () => {
    const currentSnapshot = snapshots[snapshots.length - 1];
    const prevSnapshot = snapshots.length > 1 ? snapshots[snapshots.length - 2] : null;
    
    return (
      <div style={{
        position: 'fixed', right: 12, bottom: 12, zIndex: 99999,
        background: '#111', color: '#eee', padding: 12, borderRadius: 8, width: 300,
        boxShadow: '0 6px 20px rgba(0,0,0,0.35)', fontFamily: 'system-ui, sans-serif', fontSize: 12,
        border: expanded ? '2px solid #4a4' : 'none'
      }}>
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6}}>
          <div style={{fontWeight:'bold'}}>Performance {expanded && <span style={{color: '#4a4'}}>(Current)</span>}</div>
          <div style={{display: 'flex', gap: 8}}>
            <button
              onClick={() => setExpanded(!expanded)}
              disabled={snapshots.length <= 1}
              style={{
                background: snapshots.length <= 1 ? '#222' : '#333',
                color: snapshots.length <= 1 ? '#666' : '#fff',
                border: 'none',
                padding: '4px 8px',
                borderRadius: 4,
                cursor: snapshots.length <= 1 ? 'not-allowed' : 'pointer',
                fontSize: 11
              }}
            >
              {expanded ? 'Collapse' : 'Expand'}
            </button>
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
              {copied ? '✓' : 'Copy'}
            </button>
          </div>
        </div>
        <div>
          TTFB: {Math.round(data?.ttfb ?? 0)} ms
          {prevSnapshot && currentSnapshot && <Delta current={currentSnapshot.ttfb} previous={prevSnapshot.ttfb} />}
        </div>
        <div>
          LCP: {Math.round(data?.lcp ?? 0)} ms
          {prevSnapshot && currentSnapshot && <Delta current={currentSnapshot.lcp} previous={prevSnapshot.lcp} />}
        </div>
        <div>
          DOM Loaded: {Math.round(data?.domContentLoaded ?? 0)} ms
          {prevSnapshot && currentSnapshot && <Delta current={currentSnapshot.domContentLoaded} previous={prevSnapshot.domContentLoaded} />}
        </div>
        <div>
          Window Load: {Math.round(data?.loadEvent ?? 0)} ms
          {prevSnapshot && currentSnapshot && <Delta current={currentSnapshot.loadEvent} previous={prevSnapshot.loadEvent} />}
        </div>
        <div style={{marginTop: 8}}>
          Requests: {res.totalRequests} (cache hits {res.cacheHits})
          {prevSnapshot && currentSnapshot && <Delta current={currentSnapshot.totalRequests} previous={prevSnapshot.totalRequests} unit="" />}
        </div>
        <div>
          Transferred: {formatBytes(res.totalBytes || 0)}
          {prevSnapshot && currentSnapshot && <Delta current={currentSnapshot.totalBytes} previous={prevSnapshot.totalBytes} unit="B" />}
        </div>
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
  
  // Render previous cards (only when expanded)
  const renderPreviousCards = () => {
    if (!expanded || snapshots.length <= 1) return null;
    
    // Show up to 3 previous loads (excluding current)
    const previousSnapshots = snapshots.slice(0, -1).slice(-3);
    
    return (
      <div style={{
        position: 'fixed', right: 324, bottom: 12, zIndex: 99998,
        display: 'flex', gap: 12, alignItems: 'flex-end'
      }}>
        {previousSnapshots.map((snapshot, index) => {
          const actualIndex = snapshots.length - previousSnapshots.length + index - 1;
          const prev = actualIndex > 0 ? snapshots[actualIndex - 1] : null;
          const time = new Date(snapshot.timestamp).toLocaleTimeString();
          
          return (
            <div key={snapshot.timestamp} style={{
              background: '#111', 
              color: '#eee', 
              padding: 12, 
              borderRadius: 8, 
              width: 300,
              boxShadow: '0 6px 20px rgba(0,0,0,0.35)', 
              fontFamily: 'system-ui, sans-serif', 
              fontSize: 12
            }}>
              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6}}>
                <div style={{fontWeight:'bold'}}>Load #{actualIndex + 1}</div>
              </div>
              <div style={{fontSize: 9, color: '#666', marginBottom: 8}}>{time}</div>
              
              <div>
                TTFB: {Math.round(snapshot.ttfb)} ms
                {prev && <Delta current={snapshot.ttfb} previous={prev.ttfb} />}
              </div>
              <div>
                LCP: {Math.round(snapshot.lcp)} ms
                {prev && <Delta current={snapshot.lcp} previous={prev.lcp} />}
              </div>
              <div>
                DOM Loaded: {Math.round(snapshot.domContentLoaded)} ms
                {prev && <Delta current={snapshot.domContentLoaded} previous={prev.domContentLoaded} />}
              </div>
              <div>
                Window Load: {Math.round(snapshot.loadEvent)} ms
                {prev && <Delta current={snapshot.loadEvent} previous={prev.loadEvent} />}
              </div>
              
              <div style={{marginTop: 8}}>
                Requests: {snapshot.totalRequests}
                {prev && <Delta current={snapshot.totalRequests} previous={prev.totalRequests} unit="" />}
              </div>
              <div>
                Cache: {snapshot.cacheHits}
                {prev && <Delta current={snapshot.cacheHits} previous={prev.cacheHits} unit="" invert />}
              </div>
              <div>
                Transferred: {formatBytes(snapshot.totalBytes)}
                {prev && <Delta current={snapshot.totalBytes} previous={prev.totalBytes} unit="B" />}
              </div>
              
              {snapshot.dedupeAbort > 0 && (
                <div style={{color: '#4a4', marginTop: 4}}>
                  Duplicates prevented: {snapshot.dedupeAbort}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  };
  
  return (
    <>
      {renderPreviousCards()}
      {renderCurrentCard()}
    </>
  );
};
