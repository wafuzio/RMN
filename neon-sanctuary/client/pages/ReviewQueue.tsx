import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Trash2, X, Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { toLocalImageUrl } from "@/utils/imageUrl";
import { formatLocal } from "@/lib/date";

// ── Types ──────────────────────────────────────────────────────────────────

interface VideoOverlay {
  x: number;
  y: number;
  width: number;
  height: number;
  image_width: number;
  image_height: number;
  border_radius?: number;
}

interface ReviewItem {
  flag_id: number;
  flag_type: string;
  reason: string | null;
  flagged_at: string;
  flag_brand_name: string | null;
  ad_id: number | null;
  brand: string | null;
  ad_type: string | null;
  slot: number | null;
  title: string | null;
  image_path: string | null;
  image_url: string | null;
  video_url: string | null;
  video_overlay: VideoOverlay | null;
  retailer: string | null;
  client: string | null;
  keyword: string | null;
  run_timestamp: string | null;
}

// ── Known ad types for the dropdown ───────────────────────────────────────

const AD_TYPES = [
  "TOA",
  "SBA",
  "SBV",
  "Carousel",
  "Skyscraper",
  "Display_Ads",
  "Sponsored_Brand",
  "Sponsored_Product",
  "Sponsored_Display",
  "ListingPageBannerAd",
  "Sponsored_Logo",
  "Main",
];

// ── API helpers ────────────────────────────────────────────────────────────

async function fetchReviewQueue(): Promise<ReviewItem[]> {
  const res = await fetch("/api/review-queue");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return data.items as ReviewItem[];
}

async function patchAdBrand(ad_id: number, brand: string, flag_id: number) {
  const res = await fetch(`/api/ads/${ad_id}/brand`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ brand, flag_id }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function patchAdType(ad_id: number, ad_type: string, flag_id: number) {
  const res = await fetch(`/api/ads/${ad_id}/ad-type`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ad_type, flag_id }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function clearVideoOverlay(ad_id: number, flag_id: number) {
  const res = await fetch(`/api/ads/${ad_id}/video-overlay`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ clear: true, flag_id }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function deleteAd(ad_id: number) {
  const res = await fetch(`/api/ads/${ad_id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function dismissFlag(flag_id: number) {
  const res = await fetch(`/api/review-queue/${flag_id}/dismiss`, { method: "POST" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ── Card component ─────────────────────────────────────────────────────────

function ReviewCard({ item, onDone }: { item: ReviewItem; onDone: () => void }) {
  const [editBrand, setEditBrand] = useState(false);
  const [brandInput, setBrandInput] = useState(item.brand || "");
  const [editAdType, setEditAdType] = useState(false);
  const [adTypeInput, setAdTypeInput] = useState(item.ad_type || "");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ad_id = item.ad_id!;
  const flag_id = item.flag_id;

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const imageUrl = item.image_url ? toLocalImageUrl(item.image_url) : null;

  return (
    <div className={cn(
      "rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden",
      "flex flex-col",
      busy && "opacity-60 pointer-events-none"
    )}>
      {/* Image */}
      <div className="relative bg-gray-100 aspect-[4/3] flex items-center justify-center overflow-hidden">
        {imageUrl ? (
          <img
            src={imageUrl}
            alt={item.brand || "ad"}
            className="object-contain w-full h-full"
          />
        ) : (
          <span className="text-gray-400 text-sm">No image</span>
        )}
        {/* Retailer badge */}
        {item.retailer && (
          <span className="absolute top-2 left-2 px-2 py-0.5 rounded bg-black/60 text-white text-[10px] font-medium uppercase tracking-wide">
            {item.retailer}
          </span>
        )}
        {/* Overlay indicator */}
        {item.video_overlay && (
          <span className="absolute top-2 right-2 px-2 py-0.5 rounded bg-amber-500/90 text-white text-[10px] font-medium">
            overlay
          </span>
        )}
      </div>

      {/* Info */}
      <div className="p-3 flex flex-col gap-2 flex-1">
        {/* Meta row */}
        <div className="text-[11px] text-gray-400 space-y-0.5">
          {item.client && <div>Client: <span className="text-gray-600 font-medium">{item.client}</span></div>}
          {item.keyword && <div>Keyword: <span className="text-gray-600">{item.keyword}</span></div>}
          {item.flagged_at && <div>Flagged: <span className="text-gray-600">{formatLocal(item.flagged_at)}</span></div>}
          {item.reason && <div className="italic text-gray-500">"{item.reason}"</div>}
        </div>

        {/* Brand */}
        <div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wide mb-1">Brand</div>
          {editBrand ? (
            <div className="flex gap-1">
              <input
                className="flex-1 border rounded px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
                value={brandInput}
                onChange={(e) => setBrandInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") run(() => patchAdBrand(ad_id, brandInput, flag_id));
                  if (e.key === "Escape") { setEditBrand(false); setBrandInput(item.brand || ""); }
                }}
                autoFocus
              />
              <button
                onClick={() => run(() => patchAdBrand(ad_id, brandInput, flag_id))}
                className="px-2 rounded bg-green-500 text-white hover:bg-green-600"
              ><Check size={14} /></button>
              <button
                onClick={() => { setEditBrand(false); setBrandInput(item.brand || ""); }}
                className="px-2 rounded bg-gray-200 hover:bg-gray-300"
              ><X size={14} /></button>
            </div>
          ) : (
            <button
              onClick={() => setEditBrand(true)}
              className="w-full text-left text-sm px-2 py-1 rounded border border-dashed border-gray-300 hover:border-blue-400 hover:bg-blue-50 transition"
            >
              {item.brand || <span className="text-gray-400 italic">unknown</span>}
            </button>
          )}
        </div>

        {/* Ad Type */}
        <div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wide mb-1">Ad Type</div>
          {editAdType ? (
            <div className="flex gap-1">
              <div className="relative flex-1">
                <select
                  className="w-full border rounded px-2 py-1 text-sm appearance-none focus:outline-none focus:ring-2 focus:ring-blue-400 pr-6"
                  value={adTypeInput}
                  onChange={(e) => setAdTypeInput(e.target.value)}
                  autoFocus
                >
                  {AD_TYPES.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
                <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
              </div>
              <button
                onClick={() => run(() => patchAdType(ad_id, adTypeInput, flag_id))}
                className="px-2 rounded bg-green-500 text-white hover:bg-green-600"
              ><Check size={14} /></button>
              <button
                onClick={() => { setEditAdType(false); setAdTypeInput(item.ad_type || ""); }}
                className="px-2 rounded bg-gray-200 hover:bg-gray-300"
              ><X size={14} /></button>
            </div>
          ) : (
            <button
              onClick={() => setEditAdType(true)}
              className="w-full text-left text-sm px-2 py-1 rounded border border-dashed border-gray-300 hover:border-blue-400 hover:bg-blue-50 transition"
            >
              {item.ad_type || <span className="text-gray-400 italic">unknown</span>}
            </button>
          )}
        </div>

        {/* Video overlay actions */}
        {item.video_overlay && (
          <button
            onClick={() => run(() => clearVideoOverlay(ad_id, flag_id))}
            className="w-full text-sm py-1.5 rounded border border-amber-300 text-amber-700 hover:bg-amber-50 transition"
          >
            Clear video overlay
          </button>
        )}

        {/* Error */}
        {error && (
          <div className="text-xs text-red-500 bg-red-50 rounded px-2 py-1">{error}</div>
        )}

        {/* Bottom actions */}
        <div className="flex gap-2 mt-auto pt-1">
          {/* Dismiss */}
          <button
            onClick={() => run(() => dismissFlag(flag_id))}
            className="flex-1 text-sm py-1.5 rounded border border-gray-200 text-gray-500 hover:bg-gray-50 transition"
          >
            Dismiss
          </button>

          {/* Delete */}
          {confirmDelete ? (
            <div className="flex gap-1 flex-1">
              <button
                onClick={() => run(() => deleteAd(ad_id))}
                className="flex-1 text-sm py-1.5 rounded bg-red-600 text-white hover:bg-red-700 transition"
              >
                Confirm delete
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                className="px-2 rounded border border-gray-200 hover:bg-gray-50"
              ><X size={14} /></button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmDelete(true)}
              className="flex items-center gap-1 px-3 text-sm py-1.5 rounded border border-red-200 text-red-500 hover:bg-red-50 transition"
            >
              <Trash2 size={13} />
              Delete
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function ReviewQueue() {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: items, isLoading, isError, refetch } = useQuery({
    queryKey: ["review-queue"],
    queryFn: fetchReviewQueue,
    staleTime: 0,
  });

  function handleDone() {
    qc.invalidateQueries({ queryKey: ["review-queue"] });
  }

  const pending = items ?? [];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-white border-b border-gray-200 px-4 py-3 flex items-center gap-3">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 transition"
        >
          <ArrowLeft size={16} />
          Back
        </button>
        <h1 className="font-semibold text-gray-900">Review Queue</h1>
        <span className={cn(
          "ml-1 px-2 py-0.5 rounded-full text-xs font-medium",
          pending.length > 0 ? "bg-amber-100 text-amber-700" : "bg-gray-100 text-gray-500"
        )}>
          {isLoading ? "…" : pending.length}
        </span>
        <button
          onClick={() => refetch()}
          className="ml-auto text-xs text-gray-400 hover:text-gray-600 transition"
        >
          Refresh
        </button>
      </div>

      {/* Body */}
      <div className="max-w-7xl mx-auto px-4 py-6">
        {isLoading && (
          <div className="text-center py-20 text-gray-400">Loading review queue…</div>
        )}
        {isError && (
          <div className="text-center py-20 text-red-500">Failed to load review queue. Is the Flask server running?</div>
        )}
        {!isLoading && !isError && pending.length === 0 && (
          <div className="text-center py-20 text-gray-400">
            <div className="text-4xl mb-3">✓</div>
            <div className="font-medium text-gray-600">All clear — no items in the review queue</div>
          </div>
        )}
        {!isLoading && pending.length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
            {pending.map((item) => (
              <ReviewCard key={item.flag_id} item={item} onDone={handleDone} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
