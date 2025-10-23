import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Ad } from "@/components/dashboard/AdCard";
import { api } from "@/lib/api";
import { toLocalImageUrl } from "@/utils/imageUrl";

function parseTs(ts: string, ad?: any) {
  // Handle Instacart format: 20251022_002600 -> 2025-10-22T00:26:00
  if (/^\d{8}_\d{6}$/.test(ts)) {
    const date = ts.slice(0, 8);
    const time = ts.slice(9, 15);
    const yyyy = date.slice(0, 4);
    const mm = date.slice(4, 6);
    const dd = date.slice(6, 8);
    const hh = time.slice(0, 2);
    const min = time.slice(2, 4);
    const ss = time.slice(4, 6);
    return new Date(`${yyyy}-${mm}-${dd}T${hh}:${min}:${ss}`);
  }

  // Handle Walmart format: "23-46-32" with date in run_file like "run_results_..._2025-10-21_23-46-32.json"
  if (/^\d{2}-\d{2}-\d{2}$/.test(ts) && ad?.run_file) {
    const match = ad.run_file.match(/(\d{4})-(\d{2})-(\d{2})_\d{2}-\d{2}-\d{2}/);
    if (match) {
      const [, yyyy, mm, dd] = match;
      const [hh, min, ss] = ts.split('-');
      return new Date(`${yyyy}-${mm}-${dd}T${hh}:${min}:${ss}`);
    }
  }

  // Handle Kroger format: 2025-10-22 00:26:00
  return new Date(ts.replace(" ", "T"));
}

function floorToGranularity(d: Date, g: Granularity) {
  const dd = new Date(d);
  if (g === "ampm") {
    const hour = dd.getHours();
    const ampmBucket = hour < 12 ? 0 : 12;
    dd.setHours(ampmBucket, 0, 0, 0);
  } else if (g === "day") {
    dd.setHours(0, 0, 0, 0);
  } else if (g === "month") {
    dd.setDate(1);
    dd.setHours(0, 0, 0, 0);
  }
  return dd;
}

function addGranularity(d: Date, g: Granularity) {
  const dd = new Date(d);
  if (g === "ampm") {
    dd.setHours(dd.getHours() + 12);
  } else if (g === "day") {
    dd.setDate(dd.getDate() + 1);
  } else if (g === "month") {
    dd.setMonth(dd.getMonth() + 1);
  }
  return dd;
}

function granularityMs(g: Granularity) {
  if (g === "ampm") return 43200e3; // 12 hours
  if (g === "day") return 86400e3;
  return 86400e3 * 30; // month approximation
}

type Granularity = "month"|"day"|"ampm";

function pickGranularity(pxPerDay: number): Granularity {
  if (pxPerDay < 10) return "month";
  if (pxPerDay < 50) return "day";
  return "ampm";
}

const imgCache = new Map<string, HTMLImageElement>();
let idbPromise: Promise<IDBDatabase> | null = null;
function openDB() {
  if (!('indexedDB' in window)) return Promise.reject('no idb');
  if (!idbPromise) {
    idbPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open('tvmap-cache', 1);
      req.onupgradeneeded = () => { req.result.createObjectStore('images'); };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  return idbPromise;
}
async function idbGet(url: string): Promise<Blob | null> {
  try {
    const db = await openDB();
    return await new Promise((res, rej) => {
      const tx = db.transaction('images');
      const store = tx.objectStore('images');
      const g = store.get(url); g.onsuccess = () => res(g.result || null); g.onerror = () => rej(g.error);
    });
  } catch { return null; }
}
async function idbSet(url: string, blob: Blob) {
  try {
    const db = await openDB();
    await new Promise<void>((res, rej) => {
      const tx = db.transaction('images', 'readwrite');
      tx.oncomplete = () => res();
      tx.onerror = () => rej(tx.error);
      tx.objectStore('images').put(blob, url);
    });
  } catch {}
}
async function getImage(src: string): Promise<HTMLImageElement> {
  const finalSrc = toLocalImageUrl(src);
  
  const cached = imgCache.get(finalSrc);
  if (cached) return cached;
  
  // try IDB
  const fromIDB = await idbGet(finalSrc);
  if (fromIDB) {
    const url = URL.createObjectURL(fromIDB);
    const img = await loadImage(url);
    URL.revokeObjectURL(url);
    imgCache.set(finalSrc, img);
    return img;
  }
  
  // fetch network with content-type validation
  const resp = await fetch(finalSrc, { mode: 'cors', redirect: 'follow', credentials: 'omit' });
  if (!resp.ok) throw new Error(`HTTP ${resp.status} for ${finalSrc}`);
  
  const ct = resp.headers.get('content-type') || '';
  if (!ct.startsWith('image/')) throw new Error(`Not an image (${ct}) for ${finalSrc}`);
  
  const blob = await resp.blob();
  idbSet(finalSrc, blob);
  
  const obj = URL.createObjectURL(blob);
  const img = await loadImage(obj);
  URL.revokeObjectURL(obj);
  imgCache.set(finalSrc, img);
  return img;
}
function loadImage(url: string) {
  return new Promise<HTMLImageElement>((res, rej) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => res(img);
    img.onerror = rej;
    img.src = url;
  });
}

export function TemporalVisualMap({ ads, height=300, onRangeChange, onAdClick }: { ads: Ad[]; height?: number; onRangeChange?: (from: Date, to: Date)=>void; onAdClick?: (ad: Ad)=>void; }) {
  const canvasRef = useRef<HTMLCanvasElement|null>(null);
  const wrapRef = useRef<HTMLDivElement|null>(null);

  // Track ad positions for click detection
  const adPositionsRef = useRef<Map<string, { x: number; y: number; w: number; h: number; ad: Ad }>>(new Map());


  const dates = useMemo(()=> {
    const parsedDates = ads.map((a) => {
      try {
        return parseTs(a.timestamp, a);
      } catch (e) {
        console.error('[TemporalVisualMap] Failed to parse timestamp:', a.timestamp, e);
        return new Date(0);
      }
    }).sort((a,b)=>+a-+b);
    return parsedDates;
  }, [ads]);

  // Handle single time slot: expand range for better visualization
  const { minDate, maxDate } = useMemo(() => {
    let min = dates[0] || new Date();
    let max = dates[dates.length-1] || new Date();

    // If all ads are at same timestamp, expand to ±1 hour for visibility
    if (+min === +max) {
      const mid = +min;
      min = new Date(mid - 3600000); // 1 hour before
      max = new Date(mid + 3600000); // 1 hour after
    }

    return { minDate: min, maxDate: max };
  }, [dates]);

  const [state, setState] = useState({ scale: 1, offsetX: 0 }); // scale on x-axis
  const stateRef = useRef(state); // Keep ref in sync for event handlers
  const drawRef = useRef<() => Promise<void>>(() => Promise.resolve()); // Keep latest draw function
  const varsRef = useRef<{ pxPerMs: number; minDate: Date; onRangeChange?: (from: Date, to: Date) => void }>({ pxPerMs: 0, minDate: new Date(), onRangeChange }); // Keep changing values in ref

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  const size = useSize(wrapRef);
  const width = size.width || 800;

  const msTotal = Math.max(1, +maxDate - +minDate);
  const basePxPerMs = width / msTotal;
  const pxPerMs = basePxPerMs * state.scale;

  // Update varsRef after pxPerMs is calculated
  useEffect(() => {
    varsRef.current = { pxPerMs, minDate, onRangeChange };
  }, [pxPerMs, minDate, onRangeChange]);
  const pxPerDay = pxPerMs * 86400e3;
  const g: Granularity = pickGranularity(pxPerDay);

  const bins = useMemo(() => {
    const map = new Map<number, Ad[]>();
    for (const ad of ads) {
      const t = parseTs(ad.timestamp, ad);
      const key = +floorToGranularity(t, g);
      const arr = map.get(key) || [];
      arr.push(ad);
      map.set(key, arr);
    }
    const entries = Array.from(map.entries()).sort((a,b)=>a[0]-b[0]);
    return entries.map(([k, vals]) => ({ start: new Date(k), end: addGranularity(new Date(k), g), ads: vals }));
  }, [ads, g]);

  useEffect(() => {
    // light prefetch for smoother zoom: first 2 images per bin
    const toPrefetch: string[] = [];
    for (const b of bins) {
      for (let i=0;i<Math.min(2, b.ads.length); i++) {
        const ad = b.ads[i] as any;
        const url = (ad.image_url_full || ad.image_url);
        const full = toLocalImageUrl(url);
        toPrefetch.push(full);
      }
    }
    toPrefetch.forEach(u => { getImage(u).catch(()=>{}); });
  }, [bins]);

  const draw = useCallback(async () => {
    const canvas = canvasRef.current; if (!canvas) return;
    const ctx = canvas.getContext("2d"); if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    ctx.scale(dpr, dpr);

    // Clear ad positions for this draw
    adPositionsRef.current.clear();

    // Clear and fill background
    ctx.fillStyle = "rgba(255,255,255,0.9)";
    ctx.fillRect(0,0,width,height);

    // Clip drawing to visible area - this prevents rendering off-screen content
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, 0, width, height);
    ctx.clip();

    // Draw time markers grid (even for unpopulated periods)
    let currentTime = floorToGranularity(minDate, g);
    const timeMarkers: { x: number; label: string }[] = [];
    while (+currentTime <= +maxDate) {
      const x = Math.floor((+currentTime - +minDate) * pxPerMs + state.offsetX);

      // Draw light vertical gridline
      if (x >= 0 && x <= width) {
        ctx.strokeStyle = "rgba(17,24,39,0.1)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height - 20);
        ctx.stroke();

        // Store label to draw later (avoid overlaps)
        timeMarkers.push({ x, label: labelFor(currentTime, g) });
      }

      currentTime = addGranularity(currentTime, g);
    }

    // axis baseline
    ctx.strokeStyle = "rgba(17,24,39,0.2)";
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(0, height-20); ctx.lineTo(width, height-20); ctx.stroke();

    const binPx = granularityMs(g) * pxPerMs;
    const showImages = binPx > 60; // semantic zoom threshold

    for (const b of bins) {
      const x = Math.floor(((+b.start - +minDate) * pxPerMs) + state.offsetX);
      const w = Math.max(1, Math.floor((+b.end - +b.start) * pxPerMs));
      const c = b.ads.length;

      if (!showImages) {
        // density rectangle (draw even if off-screen)
        const h = Math.min(height-40, Math.max(6, c * 6));
        const y = height-22 - h;
        const grad = ctx.createLinearGradient(0, y, 0, y+h);
        grad.addColorStop(0, "#667eea"); grad.addColorStop(1, "#764ba2");
        ctx.fillStyle = grad;
        ctx.fillRect(x, y, w-1, h);
      } else {
        // draw images mosaic within column
        const colWidth = Math.max(56, w-2);
        const thumbH = 80; const gap = 4; let y = 6; let row = 0; let col = 0;
        for (let i=0;i<b.ads.length;i++) {
          const ad = b.ads[i];
          const url = (ad as any).image_url_full || ad.image_url; // fallback
          try {
            const full = toLocalImageUrl(url);
            const img = await getImage(full);
            const aspect = img.width / Math.max(1,img.height);
            const thumbW = Math.min(colWidth, Math.round(thumbH * aspect));
            const drawX = x + (col * (colWidth + gap));
            // Still render even if off-screen; CSS will clip it
            if (drawX < width + colWidth * 2 && drawX + thumbW > -colWidth * 2) {
              ctx.save();
              ctx.beginPath();
              ctx.roundRect(drawX, y, thumbW, thumbH, 8);
              ctx.clip();
              ctx.drawImage(img, drawX, y, thumbW, thumbH);
              ctx.restore();

              // Track ad position for click detection
              adPositionsRef.current.set(`${ad.id}`, { x: drawX, y, w: thumbW, h: thumbH, ad });
            }
            y += thumbH + gap; row++;
            if (y + thumbH > height - 30) { y = 6; row = 0; col++; }
          } catch {
            // fallback block
            ctx.fillStyle = "#e5e7eb"; ctx.fillRect(x, y, colWidth, thumbH); y += thumbH + gap;
          }
        }
      }
    }
    ctx.restore(); // Restore from clip region

    // Draw time labels outside clip region (spaced to avoid overlap)
    // Combine bin labels and empty time marker labels
    const allLabels: { x: number; label: string; isBin: boolean }[] = [];

    // Add bin labels
    for (const b of bins) {
      const x = Math.floor(((+b.start - +minDate) * pxPerMs) + state.offsetX);
      allLabels.push({ x, label: labelFor(b.start, g), isBin: true });
    }

    // Add empty time marker labels
    const binStartTimes = new Set(bins.map(b => +floorToGranularity(b.start, g)));
    for (const marker of timeMarkers) {
      const timeAtMarker = Math.round(marker.x - state.offsetX) / pxPerMs + (+minDate);
      const floorTime = +floorToGranularity(new Date(timeAtMarker), g);

      if (!binStartTimes.has(floorTime)) {
        allLabels.push({ x: marker.x, label: marker.label, isBin: false });
      }
    }

    // Sort by x position and draw with spacing to avoid overlap
    allLabels.sort((a, b) => a.x - b.x);

    const minLabelSpacing = 50; // Minimum pixels between labels
    let lastLabelX = -minLabelSpacing;
    for (const label of allLabels) {
      if (label.x - lastLabelX >= minLabelSpacing) {
        ctx.fillStyle = label.isBin ? "#6b7280" : "#9ca3af"; // Darker for bins, lighter for empty times
        ctx.font = "11px system-ui";
        ctx.fillText(label.label, label.x + 4, height - 5);
        lastLabelX = label.x;
      }
    }
  }, [width, height, bins, g, minDate, pxPerMs, state.offsetX]);

  // Keep drawRef up to date so event listeners can call latest version
  useEffect(() => {
    drawRef.current = draw;
  }, [draw]);

  useEffect(() => { draw(); }, [draw]);

  // interactions
  useEffect(() => {
    const wrap = wrapRef.current; if (!wrap) return;
    let mode: 'pan'|'brush'|null = null;
    let startX = 0; let startOff = 0; let brushX = 0; let brushW = 0;
    const pointers = new Map<number, { x: number; y: number }>();

    let clickX = 0, clickY = 0;
    const onDown = (e: MouseEvent) => {
      clickX = e.offsetX;
      clickY = e.offsetY;
      if ((e as any).shiftKey) { mode = 'brush'; brushX = e.offsetX; brushW = 0; drawOverlay(); }
      else { mode = 'pan'; startX = e.clientX; startOff = stateRef.current.offsetX; (wrap.style.cursor = "grabbing"); }
    };
    const onUp = (e: MouseEvent) => {
      if (mode === 'brush') {
        const x1 = Math.min(brushX, brushX + brushW);
        const x2 = Math.max(brushX, brushX + brushW);
        const { pxPerMs: px, minDate: md, onRangeChange: orc } = varsRef.current;
        const fromMs = (x1 - stateRef.current.offsetX) / px + (+md);
        const toMs = (x2 - stateRef.current.offsetX) / px + (+md);
        orc?.(new Date(fromMs), new Date(toMs));
      } else if (mode === 'pan') {
        // Check if this was a click (very small drag) on an ad
        const dragDist = Math.abs(e.clientX - startX);
        if (dragDist < 5) { // Less than 5px drag = click
          // Check if click was on an ad image
          for (const [, pos] of adPositionsRef.current) {
            if (clickX >= pos.x && clickX <= pos.x + pos.w &&
                clickY >= pos.y && clickY <= pos.y + pos.h) {
              onAdClick?.(pos.ad);
              break;
            }
          }
        }
      }
      mode = null; wrap.style.cursor = "grab"; brushW = 0; drawOverlay();
    };
    const onMove = (e: MouseEvent) => {
      if (mode === 'pan') {
        const dx = e.clientX - startX;
        // Amplify drag by zoom level squared for better responsiveness at high zoom
        const amplificationFactor = Math.max(1, stateRef.current.scale * stateRef.current.scale * 0.5);
        const amplifiedDx = dx * amplificationFactor;
        setState(s=>({ ...s, offsetX: startOff + amplifiedDx }));
      }
      else if (mode === 'brush') { brushW = e.offsetX - brushX; drawOverlay(); }
    };
    const onWheel = (e: WheelEvent) => { e.preventDefault(); const { offsetX } = e as any; const zoom = Math.exp(-e.deltaY * 0.0015); const cx = offsetX; setState(s=>({ scale: Math.min(64, Math.max(0.25, s.scale * zoom)), offsetX: cx - (cx - s.offsetX) * zoom })); };

    const onPointerDown = (e: PointerEvent) => { (e.target as HTMLElement).setPointerCapture(e.pointerId); pointers.set(e.pointerId, { x: e.clientX, y: e.clientY }); };
    const onPointerUp = (e: PointerEvent) => { pointers.delete(e.pointerId); };
    const onPointerMove = (e: PointerEvent) => {
      if (pointers.size === 2) {
        const [a,b] = Array.from(pointers.values());
        const prevDist = Math.hypot(a.x - b.x, a.y - b.y);
        pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
        const [a2,b2] = Array.from(pointers.values());
        const dist = Math.hypot(a2.x - b2.x, a2.y - b2.y);
        const zoom = dist / Math.max(1, prevDist);
        const cx = (a2.x + b2.x) / 2 - wrap.getBoundingClientRect().left;
        setState(s=>({ scale: Math.min(64, Math.max(0.25, s.scale * zoom)), offsetX: cx - (cx - s.offsetX) * zoom }));
      }
    };

    function drawOverlay() {
      const c = canvasRef.current; if (!c) return; const ctx = c.getContext('2d'); if (!ctx) return;
      drawRef.current();
      if (mode === 'brush' && Math.abs(brushW) > 2) {
        const dpr = window.devicePixelRatio || 1;
        ctx.save();
        ctx.fillStyle = 'rgba(59,130,246,0.15)';
        const x = Math.min(brushX, brushX + brushW) + state.offsetX;
        const w = Math.abs(brushW);
        ctx.fillRect(x, 0, w, height);
        ctx.strokeStyle = 'rgba(59,130,246,0.8)'; ctx.lineWidth = 2; ctx.strokeRect(x+0.5, 0.5, w-1, height-1);
        ctx.restore();
      }
    }

    wrap.addEventListener("mousedown", onDown);
    window.addEventListener("mouseup", onUp);
    window.addEventListener("mousemove", onMove, { passive: true });
    wrap.addEventListener("wheel", onWheel, { passive: false });
    wrap.addEventListener('pointerdown', onPointerDown);
    window.addEventListener('pointerup', onPointerUp);
    window.addEventListener('pointermove', onPointerMove, { passive: true });
    wrap.style.cursor = "grab";
    return () => {
      wrap.removeEventListener("mousedown", onDown);
      window.removeEventListener("mouseup", onUp);
      window.removeEventListener("mousemove", onMove);
      wrap.removeEventListener("wheel", onWheel);
      wrap.removeEventListener('pointerdown', onPointerDown);
      window.removeEventListener('pointerup', onPointerUp);
      window.removeEventListener('pointermove', onPointerMove);
    };
  }, []); // Event handlers use refs for current state - keeps listeners attached

  // range select via double click toggles to that bin
  const onDoubleClick = (e: React.MouseEvent) => {
    const x = e.nativeEvent.offsetX; const msAtX = (x - state.offsetX) / pxPerMs + (+minDate);
    const start = new Date(msAtX); const f = floorToGranularity(start, g); const t = addGranularity(f, g);
    onRangeChange?.(f, t);
  };

  return (
    <div className="w-full overflow-x-auto overflow-y-hidden" aria-label="Temporal Visual Map">
      <div className="flex items-center justify-between px-2 pb-2 text-sm text-[#6b7280]">
        <div>Visual Map • Semantic zoom ({g})</div>
        <div className="flex items-center gap-2">
          <button className="px-2 py-1 rounded bg-white/80 border" onClick={()=> setState({ scale: 1, offsetX: 0 })}>Reset</button>
        </div>
      </div>
      <div ref={wrapRef} className="relative" style={{ height, width: '100%', minWidth: '100%' }} onDoubleClick={onDoubleClick}>
        <canvas ref={canvasRef} width={width} height={height} style={{ display: 'block', width: '100%', height: '100%' }} />
      </div>
    </div>
  );
}

function labelFor(d: Date, g: Granularity) {
  if (g === "ampm") {
    const period = d.getHours() < 12 ? "AM" : "PM";
    return d.toLocaleDateString(undefined, { month: "short", day: "2-digit" }) + " " + period;
  }
  if (g === "day") return d.toLocaleDateString(undefined, { month: "short", day: "2-digit" });
  return d.toLocaleDateString(undefined, { month: "short", year: "numeric" });
}


function useSize<T extends HTMLElement>(ref: React.RefObject<T>) {
  const [size, set] = useState({ width: 0, height: 0 });
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const ro = new ResizeObserver(entries => {
      const cr = entries[0].contentRect; set({ width: Math.round(cr.width), height: Math.round(cr.height) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return size;
}
