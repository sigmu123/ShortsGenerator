"""
Backend/settings.py - Global Configuration & Preset Registry for ShortsGenerator
Defines directory paths, 9:16 video resolutions, subtitle templates, and TTS defaults.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# 1. DIRECTORY & FILE PATHS
# ==========================================
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
STATIC_DIR = BACKEND_DIR / "static"
GENERATED_VIDEOS_DIR = STATIC_DIR / "generated_videos"
ASSETS_DIR = STATIC_DIR / "assets"
TEMP_DIR = ASSETS_DIR / "temp"
CACHE_DIR = ASSETS_DIR / "cache"

# Ensure all critical directories exist at startup
for directory in [STATIC_DIR, GENERATED_VIDEOS_DIR, ASSETS_DIR, TEMP_DIR, CACHE_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# ==========================================
# 2. SERVER CONFIGURATION
# ==========================================
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8080))
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")

# ==========================================
# 3. VIDEO DIMENSIONS & ASPECT RATIOS
# ==========================================
ASPECT_RATIOS = {
    "9:16": (1080, 1920),  # Standard YouTube Shorts & TikTok Vertical
    "16:9": (1920, 1080),  # Standard YouTube Landscape
    "1:1":  (1080, 1080),  # Square Instagram Feed
}

DEFAULT_ASPECT_RATIO = "9:16"
DEFAULT_WIDTH, DEFAULT_HEIGHT = ASPECT_RATIOS[DEFAULT_ASPECT_RATIO]
DEFAULT_FPS = 30
VIDEO_CODEC = "libx264"
AUDIO_CODEC = "aac"
PRESET = "fast"

# ==========================================
# 4. AUDIO & DUCKING SETTINGS
# ==========================================
VOICE_VOLUME = 1.0
BG_MUSIC_DUCKING_VOLUME = 0.12  # -18dB under speech
BG_MUSIC_FADEIN_SEC = 1.0
BG_MUSIC_FADEOUT_SEC = 2.0

# ==========================
# 5. SUBTITLE STYLE PRESETS
# ==========================
SUBTITLE_STYLES = {
    "mrbeast": {
        "name": "MrBeast Viral Yellow",
        "primary_color": "#FFFF00",
        "stroke_color": "#000000",
        "stroke_width": 4,
        "font": "Arial-Bold",
        "font_size": 64,
        "uppercase": True,
        "max_words_per_chunk": 4,
        "safe_zone_y": 0.70  # 70% from top (lower-middle safe area)
    },
    "hormozi": {
        "name": "Hormozi Neon Green",
        "primary_color": "#00FF66",
        "stroke_color": "#000000",
        "stroke_width": 5,
        "font": "Arial-Bold",
        "font_size": 68,
        "uppercase": True,
        "max_words_per_chunk": 3,
        "safe_zone_y": 0.68
    },
    "neon": {
        "name": "Cyber Neon Cyan",
        "primary_color": "#00FFFF",
        "stroke_color": "#000000",
        "stroke_width": 4,
        "font": "Arial-Bold",
        "font_size": 62,
        "uppercase": True,
        "max_words_per_chunk": 4,
        "safe_zone_y": 0.70
    },
    "minimal": {
        "name": "Minimalist Clean White",
        "primary_color": "#FFFFFF",
        "stroke_color": "#111111",
        "stroke_width": 3,
        "font": "Arial",
        "font_size": 54,
        "uppercase": False,
        "max_words_per_chunk": 5,
        "safe_zone_y": 0.72
    }
}

# ==========================================
# 6. TTS VOICE REGISTRY
# ==========================================
VOICE_MAP = {
    "en_us_001": "en-US-ChristopherNeural",   # Deep Male Storyteller
    "en_us_002": "en-US-JennyNeural",         # Energetic Female Host
    "en_us_006": "en-US-GuyNeural",           # Casual Male
    "en_us_010": "en-US-AriaNeural",          # Professional Female
    "en_uk_001": "en-GB-RyanNeural",          # British Male Narrator
    "en_uk_003": "en-GB-SoniaNeural",         # British Female Host
    "en_au_001": "en-AU-WilliamNeural",       # Australian Male
}

DEFAULT_VOICE = "en_us_001"
DEFAULT_DURATION_SEC = 45
