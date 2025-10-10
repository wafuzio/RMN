import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Ad } from "@/components/dashboard/AdCard";
import { api } from "@/lib/api";

function parseTs(ts: string) { return new Date(ts.replace(" ", "T")); }

function floorToGranularity(d: Date, g: Granularity) {
  const dd = new Date(d);
  if (g === "hour") dd.setMinutes(0,0,0);
  else if (g === "day") dd.setHours(0,0,0,0);
  else if (g === "week") {
    const day = dd.getDay(); const diff = (day === 0 ? -6 : 1) - day; // start Monday
    dd.setDate(dd.getDate() + diff); dd.setHours(0,0,0,0);
  } else if (g === "month") { dd.setDate(1); dd.setHours(0,0,0,0); }
  return dd;
}

function addGranularity(d: Date, g: Granularity) {
  const dd = new Date(d);
  if (g === "hour") dd.setHours(dd.getHours()+1);
  else if (g === "day") dd.setDate(dd.getDate()+1);
  else if (g === "week") dd.setDate(dd.getDate()+7);
  else if (g === "month") dd.setMonth(dd.getMonth()+1);
  return dd;
}

function granularityMs(g: Granularity) {
  if (g === "hour") return 3600e3;
  if (g === "day") return 86400e3;
  if (g === "week") return 86400e3*7;
  return 86400e3*30;
}

type Granularity = "month"|"week"|"day"|"hour";

function pickGranularity(pxPerDay: number): Granularity {
  if (pxPerDay < 2) return "month";
  if (pxPerDay < 12) return "week";
  if (pxPerDay < 48) return "day";
  return "hour";
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
  const cached = imgCache.get(src);
  if (cached) return Promise.resolve(cached);
  // try IDB
  const fromIDB = await idbGet(src);
  if (fromIDB) {
    const url = URL.createObjectURL(fromIDB);
    const img = await loadImage(url);
    URL.revokeObjectURL(url);
    imgCache.set(src, img);
    return img;
  }
  // fetch network
  const resp = await fetch(src, { mode: 'cors' });
  const blob = await resp.blob();
  idbSet(src, blob);
  const url = URL.createObjectURL(blob);
  const img = await loadImage(url);
  URL.revokeObjectURL(url);
  imgCache.set(src, img);
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

export function TemporalVisualMap({ ads, height=300, onRangeChange }: { ads: Ad[]; height?: number; onRangeChange?: (from: Date, to: Date)=>void; }) {
  const canvasRef = useRef<HTMLCanvasElement|null>(null);
  const wrapRef = useRef<HTMLDivElement|null>(null);

  const dates = useMemo(()=> ads.map(a => parseTs(a.timestamp)).sort((a,b)=>+a-+b), [ads]);
  const minDate = dates[0] || new Date();
  const maxDate = dates[dates.length-1] || new Date();

  const [state, setState] = useState({ scale: 1, offsetX: 0 }); // scale on x-axis

  const width = useSize(wrapRef).width || 800;
  const msTotal = Math.max(1, +maxDate - +minDate);
  const basePxPerMs = width / msTotal;
  const pxPerMs = basePxPerMs * state.scale;
  const pxPerDay = pxPerMs * 86400e3;
  const g: Granularity = pickGranularity(pxPerDay);

  const bins = useMemo(() => {
    const map = new Map<number, Ad[]>();
    for (const ad of ads) {
      const t = parseTs(ad.timestamp);
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
        const full = url.startsWith('http') ? url : api.imageUrl(url);
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

    ctx.clearRect(0,0,width,height);
    // background
    ctx.fillStyle = "rgba(255,255,255,0.9)";
    ctx.fillRect(0,0,width,height);

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
        // density rectangle
        const h = Math.min(height-40, Math.max(6, c * 6));
        const y = height-22 - h;
        const grad = ctx.createLinearGradient(0, y, 0, y+h);
        grad.addColorStop(0, "#667eea"); grad.addColorStop(1, "#764ba2");
        ctx.fillStyle = grad;
        ctx.fillRect(x, y, w-1, h);
        // tick label
        if (w > 48) {
          ctx.fillStyle = "#6b7280"; ctx.font = "12px system-ui";
          ctx.fillText(labelFor(b.start, g), x+4, height-6);
        }
      } else {
        // draw images mosaic within column
        const colWidth = Math.max(56, w-2);
        const thumbH = 80; const gap = 4; let y = 6; let row = 0; let col = 0;
        for (let i=0;i<b.ads.length;i++) {
          const ad = b.ads[i];
          const url = (ad as any).image_url_full || ad.image_url; // fallback
          try {
            const full = url.startsWith("http") ? url : api.imageUrl(url);
            const img = await getImage(full);
            const aspect = img.width / Math.max(1,img.height);
            const thumbW = Math.min(colWidth, Math.round(thumbH * aspect));
            const drawX = x + (col * (colWidth + gap));
            if (drawX > width) break;
            ctx.save();
            ctx.beginPath();
            ctx.roundRect(drawX, y, thumbW, thumbH, 8);
            ctx.clip();
            ctx.drawImage(img, drawX, y, thumbW, thumbH);
            ctx.restore();
            y += thumbH + gap; row++;
            if (y + thumbH > height - 30) { y = 6; row = 0; col++; }
          } catch {
            // fallback block
            ctx.fillStyle = "#e5e7eb"; ctx.fillRect(x, y, colWidth, thumbH); y += thumbH + gap;
          }
        }
        // label
        if (w > 60) { ctx.fillStyle = "#6b7280"; ctx.font = "12px system-ui"; ctx.fillText(labelFor(b.start, g), x+4, height-6); }
      }
    }
  }, [width, height, bins, g, minDate, pxPerMs, state.offsetX]);

  useEffect(() => { draw(); }, [draw]);

  // interactions
  useEffect(() => {
    const wrap = wrapRef.current; if (!wrap) return;
    let mode: 'pan'|'brush'|null = null;
    let startX = 0; let startOff = 0; let brushX = 0; let brushW = 0;
    const pointers = new Map<number, { x: number; y: number }>();

    const onDown = (e: MouseEvent) => {
      if ((e as any).shiftKey) { mode = 'brush'; brushX = e.offsetX; brushW = 0; drawOverlay(); }
      else { mode = 'pan'; startX = e.clientX; startOff = state.offsetX; (wrap.style.cursor = "grabbing"); }
    };
    const onUp = () => {
      if (mode === 'brush') {
        const x1 = Math.min(brushX, brushX + brushW);
        const x2 = Math.max(brushX, brushX + brushW);
        const fromMs = (x1 - state.offsetX) / pxPerMs + (+minDate);
        const toMs = (x2 - state.offsetX) / pxPerMs + (+minDate);
        onRangeChange?.(new Date(fromMs), new Date(toMs));
      }
      mode = null; wrap.style.cursor = "grab"; brushW = 0; drawOverlay();
    };
    const onMove = (e: MouseEvent) => {
      if (mode === 'pan') { const dx = e.clientX - startX; setState(s=>({ ...s, offsetX: startOff + dx })); }
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
      draw();
      if (mode === 'brush' && Math.abs(brushW) > 2) {
        const dpr = window.devicePixelRatio || 1;
        ctx.save(); ctx.scale(dpr, dpr);
        ctx.fillStyle = 'rgba(59,130,246,0.15)';
        const x = Math.min(brushX, brushX + brushW); const w = Math.abs(brushW);
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
  }, [state.offsetX, pxPerMs, minDate, height, draw, onRangeChange]);

  // range select via double click toggles to that bin
  const onDoubleClick = (e: React.MouseEvent) => {
    const x = e.nativeEvent.offsetX; const msAtX = (x - state.offsetX) / pxPerMs + (+minDate);
    const start = new Date(msAtX); const f = floorToGranularity(start, g); const t = addGranularity(f, g);
    onRangeChange?.(f, t);
  };

  return (
    <div className="w-full" aria-label="Temporal Visual Map">
      <div className="flex items-center justify-between px-2 pb-2 text-sm text-[#6b7280]">
        <div>Visual Map • Semantic zoom ({g})</div>
        <div className="flex items-center gap-2">
          <button className="px-2 py-1 rounded bg-white/80 border" onClick={()=> setState({ scale: 1, offsetX: 0 })}>Reset</button>
        </div>
      </div>
      <div ref={wrapRef} className="w-full relative px-2" style={{ height }} onDoubleClick={onDoubleClick}>
        <canvas ref={canvasRef} width={width} height={height} className="w-full h-full" />
      </div>
    </div>
  );
}

function labelFor(d: Date, g: Granularity) {
  if (g === "hour") return d.toLocaleString(undefined, { month: "short", day: "2-digit", hour: "2-digit" });
  if (g === "day") return d.toLocaleDateString(undefined, { month: "short", day: "2-digit" });
  if (g === "week") return `W${weekNumber(d)} ${d.getFullYear()}`;
  return d.toLocaleDateString(undefined, { month: "short", year: "numeric" });
}

function weekNumber(d: Date) {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = date.getUTCDay() || 7; date.setUTCDate(date.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(),0,1));
  return Math.ceil((((date as any) - (+yearStart)) / 86400000 + 1) / 7);
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
