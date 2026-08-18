"""
Backend/search.py - Robust Stock Video Search & Downloader
Supports Pexels API with Portrait (9:16) Filtering & Smart Keyword Fallbacks.
"""

import os
import requests
import hashlib
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
import settings

load_dotenv()

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")

FALLBACK_KEYWORDS = [
    "dark technology cyber",
    "nature drone cinematic",
    "space galaxy stars",
    "luxury modern architecture",
    "abstract neon light motion",
    "deep ocean underwater"
]

def get_best_video_link(video_files: List[Dict[str, Any]], target_portrait: bool = True) -> Optional[str]:
    """Finds the optimal video stream matching 9:16 vertical resolution."""
    candidates = []
    
    for f in video_files:
        link = f.get("link")
        width = f.get("width", 0)
        height = f.get("height", 0)
        file_type = f.get("file_type", "")
        
        if not link or "video/mp4" not in file_type:
            continue
            
        is_vertical = height > width
        
        if target_portrait and is_vertical:
            score = 1000 - abs(height - 1920)
            candidates.append((score, link))
        elif not target_portrait and not is_vertical:
            score = 1000 - abs(width - 1920)
            candidates.append((score, link))
        else:
            score = 100 - abs(height - 1080)
            candidates.append((score, link))
            
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
        
    return video_files[0].get("link") if video_files else None


def download_video_file(url: str, output_path: str) -> bool:
    """Downloads a video file using stream chunks with verification."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    try:
        with requests.get(url, stream=True, timeout=20) as r:
            r.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
                        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 50000:
            return True
    except Exception as e:
        print(f"[ERROR] Failed to download video from {url}: {e}")
        if os.path.exists(output_path):
            os.remove(output_path)
    return False


def search_and_download_video(query: str, output_path: str, target_portrait: bool = True) -> str:
    """
    Searches Pexels for relevant video footage and downloads it.
    Falls back gracefully if query returns 0 hits.
    """
    clean_query = query.strip()
    if not clean_query:
        clean_query = "cinematic abstract background"
        
    # Check local cache first
    query_hash = hashlib.md5(f"{clean_query}_{target_portrait}".encode()).hexdigest()
    cache_path = os.path.join(str(settings.CACHE_DIR), "videos", f"{query_hash}.mp4")
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 100000:
        import shutil
        shutil.copy(cache_path, output_path)
        return output_path

    if not PEXELS_API_KEY:
        print("[WARN] PEXELS_API_KEY not set. Generating procedural background video placeholder.")
        return _generate_procedural_background(output_path, target_portrait)

    headers = {"Authorization": PEXELS_API_KEY}
    queries_to_try = [
        clean_query,
        " ".join(clean_query.split()[:2]),
        clean_query.split()[0] if clean_query.split() else "nature",
        "cinematic technology motion",
        "aesthetic dark background"
    ]
    
    for q in queries_to_try:
        try:
            orientation_param = "&orientation=portrait" if target_portrait else "&orientation=landscape"
            url = f"https://api.pexels.com/videos/search?query={requests.utils.quote(q)}&per_page=5{orientation_param}"
            
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                videos = data.get("videos", [])
                
                for video_entry in videos:
                    video_files = video_entry.get("video_files", [])
                    best_link = get_best_video_link(video_files, target_portrait)
                    
                    if best_link and download_video_file(best_link, output_path):
                        import shutil
                        shutil.copy(output_path, cache_path)
                        return output_path
        except Exception as e:
            print(f"[WARN] Pexels search failed for query '{q}': {e}")
            
    return _generate_procedural_background(output_path, target_portrait)


def _generate_procedural_background(output_path: str, target_portrait: bool = True) -> str:
    """Generates an aesthetic vertical video using FFmpeg if no network video is found."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    w, h = (1080, 1920) if target_portrait else (1920, 1080)
    cmd = (
        f'ffmpeg -y -f lavfi -i testsrc=size={w}x{h}:rate=30 '
        f'-vf "hue=s=0,curves=vintage,boxblur=20:1" '
        f'-t 15 -c:v libx264 -pix_fmt yuv420p {output_path} -loglevel error'
    )
    os.system(cmd)
    return output_path
