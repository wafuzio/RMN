#!/usr/bin/env python3
"""
Global Video Index - Maps HLS URLs to local MP4 paths for deduplication.

This allows multiple ads to reference the same MP4 file, saving disk space.
The index is stored as a JSON file and loaded/updated by scrapers and backfill tools.

Usage:
    from utils.video_index import VideoIndex
    
    index = VideoIndex()
    
    # Check if video already exists
    mp4_path = index.get(hls_url)
    if mp4_path:
        # Reuse existing video
        ad['video_path'] = mp4_path
    else:
        # Download and register
        download_video(hls_url, new_path)
        index.set(hls_url, new_path)
        index.save()
"""

import json
import hashlib
from pathlib import Path
from typing import Optional
import threading

PROJECT_ROOT = Path(__file__).parent.parent
INDEX_FILE = PROJECT_ROOT / "cache" / "video_index.json"


def _hash_url(url: str) -> str:
    """Create a short hash of the URL for the index key."""
    return hashlib.md5(url.encode()).hexdigest()[:16]


class VideoIndex:
    """Thread-safe global video index mapping HLS URLs to MP4 paths."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern - only one index instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._data = {}  # url_hash -> {"url": full_url, "mp4": relative_path, "size": bytes}
        self._url_to_hash = {}  # full_url -> hash (for fast lookup)
        self._mp4_to_urls = {}  # mp4_path -> [urls] (reverse lookup)
        self._dirty = False
        self._load()
        self._initialized = True
    
    def _load(self):
        """Load index from disk."""
        if INDEX_FILE.exists():
            try:
                with open(INDEX_FILE, 'r') as f:
                    self._data = json.load(f)
                # Build reverse lookups
                for h, entry in self._data.items():
                    self._url_to_hash[entry["url"]] = h
                    mp4 = entry.get("mp4")
                    if mp4:
                        if mp4 not in self._mp4_to_urls:
                            self._mp4_to_urls[mp4] = []
                        self._mp4_to_urls[mp4].append(entry["url"])
                print(f"[VideoIndex] Loaded {len(self._data)} entries")
            except Exception as e:
                print(f"[VideoIndex] Error loading: {e}")
                self._data = {}
    
    def save(self):
        """Save index to disk if modified."""
        if not self._dirty:
            return
        
        INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(INDEX_FILE, 'w') as f:
            json.dump(self._data, f, indent=2)
        self._dirty = False
        print(f"[VideoIndex] Saved {len(self._data)} entries")
    
    def get(self, hls_url: str) -> Optional[str]:
        """Get MP4 path for an HLS URL, or None if not indexed."""
        h = self._url_to_hash.get(hls_url)
        if h and h in self._data:
            entry = self._data[h]
            mp4 = entry.get("mp4")
            # Verify file still exists
            if mp4:
                full_path = PROJECT_ROOT / "output" / mp4
                if full_path.exists():
                    return mp4
        return None
    
    def set(self, hls_url: str, mp4_rel_path: str, size: int = 0):
        """Register an HLS URL -> MP4 mapping."""
        h = _hash_url(hls_url)
        self._data[h] = {
            "url": hls_url,
            "mp4": mp4_rel_path,
            "size": size
        }
        self._url_to_hash[hls_url] = h
        
        if mp4_rel_path not in self._mp4_to_urls:
            self._mp4_to_urls[mp4_rel_path] = []
        if hls_url not in self._mp4_to_urls[mp4_rel_path]:
            self._mp4_to_urls[mp4_rel_path].append(hls_url)
        
        self._dirty = True
    
    def get_urls_for_mp4(self, mp4_path: str) -> list[str]:
        """Get all HLS URLs that map to a given MP4."""
        return self._mp4_to_urls.get(mp4_path, [])
    
    def stats(self) -> dict:
        """Get index statistics."""
        unique_mp4s = len(self._mp4_to_urls)
        total_urls = len(self._data)
        total_size = sum(e.get("size", 0) for e in self._data.values())
        
        # Count how many URLs share each MP4
        shared = sum(1 for urls in self._mp4_to_urls.values() if len(urls) > 1)
        
        return {
            "total_urls": total_urls,
            "unique_mp4s": unique_mp4s,
            "shared_mp4s": shared,
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "dedup_ratio": round(total_urls / unique_mp4s, 2) if unique_mp4s else 0
        }


def build_index_from_existing():
    """Scan all Instacart JSONs and build the video index from existing data."""
    import glob
    
    index = VideoIndex()
    added = 0
    
    for jf in glob.glob(str(PROJECT_ROOT / "output" / "instacart" / "**" / "run_results*.json"), recursive=True):
        try:
            with open(jf) as f:
                data = json.load(f)
            
            for ad in data.get("ads", []):
                hls_url = ad.get("video_url")
                mp4_path = ad.get("video_path")
                
                if hls_url and hls_url.startswith("http") and mp4_path:
                    # Normalize path to be relative to output/
                    if not mp4_path.startswith("instacart/"):
                        # It's relative to client folder, need to add retailer/client
                        # Extract from json path
                        parts = Path(jf).parts
                        try:
                            idx = parts.index("instacart")
                            client = parts[idx + 1]
                            mp4_path = f"instacart/{client}/{mp4_path}"
                        except (ValueError, IndexError):
                            pass
                    
                    # Check if MP4 exists
                    full_mp4 = PROJECT_ROOT / "output" / mp4_path
                    if full_mp4.exists():
                        size = full_mp4.stat().st_size
                        if not index.get(hls_url):
                            index.set(hls_url, mp4_path, size)
                            added += 1
        except Exception as e:
            pass
    
    index.save()
    print(f"[VideoIndex] Built index: {added} new entries")
    print(f"[VideoIndex] Stats: {index.stats()}")
    return index


if __name__ == "__main__":
    print("Building video index from existing data...")
    index = build_index_from_existing()
