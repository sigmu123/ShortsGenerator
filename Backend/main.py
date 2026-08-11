import os
import sys
import json
import argparse
import time
import uuid
import threading
import shutil
import subprocess
import requests
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from termcolor import colored
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import Backend modules
from settings import *
from gpt import *
from search import *
from video import *
from utils import *
from classes.Shorts import Shorts
from classes.instagram_downloader import InstagramDownloader
from leadgen.campaign_store import *
from leadgen.scrape import scrape_url
from leadgen.enrichment import *
from leadgen.adapters.devtools_adapter import DevToolsAdapter

# ============================================================
# Flask App Initialization
# ============================================================
app = Flask(__name__)
CORS(app)

# ============================================================
# Configuration
# ============================================================
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "assets", "temp")
ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv', 'webm', 'flv', 'wmv'}

# ============================================================
# Helper Functions
# ============================================================
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def ensure_dirs():
    dirs = [
        "static/generated_videos",
        "static/generated_videos/instagram",
        "static/assets/temp",
        "static/assets/subtitles",
        "static/assets/custom_audio",
        "static/assets/music",
        "data"
    ]
    for d in dirs:
        os.makedirs(os.path.join(os.path.dirname(__file__), d), exist_ok=True)

# ============================================================
# API Routes
# ============================================================

@app.route('/api/script', methods=['POST'])
def generate_script():
    """Generate script and search terms using AI"""
    data = request.json
    video_subject = data.get('videoSubject')
    ai_model = data.get('aiModel', 'g4f')
    extra_prompt = data.get('extraPrompt', '')
    script_template = data.get('scriptTemplate', 'viral_shorts')

    if not video_subject:
        return jsonify({"status": "error", "message": "videoSubject is required"}), 400

    try:
        shorts = Shorts(video_subject, 1, ai_model, extra_prompt=extra_prompt, script_template=script_template)
        script = shorts.GenerateScript()
        search_terms = shorts.GenerateSearchTerms()
        return jsonify({
            "status": "success",
            "data": {
                "script": script,
                "search": search_terms
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/search-and-download', methods=['POST'])
def search_and_download():
    """Full video generation pipeline"""
    data = request.json
    script = data.get('script')
    voice = data.get('voice', 'M3')
    search_terms = data.get('search', [])
    ai_model = data.get('aiModel', 'g4f')
    selected_video_urls = data.get('selectedVideoUrls', [])
    subtitles_position = data.get('subtitlesPosition', 'center,bottom')
    subtitle_template = data.get('subtitleTemplate', 'classic')
    aspect_ratio = data.get('aspectRatio', '9:16')
    custom_subtitle = data.get('customSubtitle', '')
    script_template = data.get('scriptTemplate', 'viral_shorts')
    custom_audio_path = data.get('customAudioPath', '')
    audio_start_time = data.get('audioStartTime', 0)
    audio_end_time = data.get('audioEndTime', 0)
    images = data.get('images', [])
    image_durations = data.get('imageDurations', [])
    image_duration = data.get('imageDuration', 5)
    clip_duration = data.get('clipDuration', 10)

    if not script:
        return jsonify({"status": "error", "message": "Script is required"}), 400

    try:
        # Use a dummy subject for metadata generation
        video_subject = "Generated Video"
        shorts = Shorts(video_subject, 1, ai_model, extra_prompt="", script_template=script_template)
        shorts.final_script = script
        shorts.custom_subtitle = custom_subtitle
        shorts.aspect_ratio = aspect_ratio
        shorts.subtitle_template = subtitle_template
        shorts.subtitles_position = subtitles_position
        shorts.clip_duration = clip_duration
        shorts.image_paths = images
        shorts.image_durations = image_durations
        shorts.image_duration = image_duration

        # Handle search terms
        if isinstance(search_terms, str):
            search_terms = [s.strip() for s in search_terms.split(',') if s.strip()]
        shorts.search_terms = search_terms

        # Download videos
        shorts.DownloadVideos(selected_video_urls)

        # Generate voice
        shorts.GenerateVoice(voice, custom_audio_path, audio_start_time, audio_end_time)

        # Combine videos
        shorts.CombineVideos()

        # Generate metadata
        shorts.GenerateMetadata()

        return jsonify({
            "status": "success",
            "data": {
                "finalVideo": shorts.get_final_video_path,
                "finalAudio": shorts.get_tts_path,
                "subtitles": shorts.get_subtitles_path,
                "metadata": {
                    "title": shorts.video_title,
                    "description": shorts.video_description,
                    "tags": shorts.video_tags,
                    "post_content": shorts.video_post_content,
                    "suggested_schedule": shorts.suggested_schedule
                }
            }
        })
    except RuntimeError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/addAudio', methods=['POST'])
def add_audio():
    """Add background music to video"""
    data = request.json
    final_video = data.get('finalVideo')
    song_path = data.get('songPath')
    ai_model = data.get('aiModel', 'g4f')
    music_source = data.get('musicSource', 'library')
    background_music_from_video = data.get('backgroundMusicFromVideo', '')
    aspect_ratio = data.get('aspectRatio', '9:16')

    if not final_video:
        return jsonify({"status": "error", "message": "finalVideo is required"}), 400

    try:
        video_subject = "Music Video"
        shorts = Shorts(video_subject, 1, ai_model)
        shorts.final_video_path = final_video
        shorts.aspect_ratio = aspect_ratio

        use_music = True
        if music_source == "video":
            shorts.AddMusic(use_music, custom_song_path=background_music_from_video, music_source="video")
        else:
            shorts.AddMusic(use_music, custom_song_path=song_path, music_source="library")

        return jsonify({
            "status": "success",
            "data": {
                "finalVideo": shorts.get_final_music_video_path
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/getVideos', methods=['GET'])
def get_videos():
    """List all generated videos"""
    try:
        videos_dir = os.path.join(os.path.dirname(__file__), "static", "generated_videos")
        videos = []
        for f in os.listdir(videos_dir):
            if f.endswith('.mp4'):
                basename = os.path.splitext(f)[0]
                meta_path = os.path.join(videos_dir, f"{basename}.json")
                metadata = None
                if os.path.exists(meta_path):
                    with open(meta_path, 'r') as mf:
                        metadata = json.load(mf)
                videos.append({
                    "filename": f,
                    "url": f"/api/video/{f}",
                    "metadata": metadata
                })

        # Instagram videos
        instagram_dir = os.path.join(videos_dir, "instagram")
        instagram_videos = []
        if os.path.exists(instagram_dir):
            for f in os.listdir(instagram_dir):
                if f.endswith('.mp4'):
                    instagram_videos.append({
                        "filename": f,
                        "url": f"/static/generated_videos/instagram/{f}",
                        "metadata": None
                    })

        return jsonify({
            "status": "success",
            "data": {
                "videos": videos,
                "instagram": instagram_videos
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/video/<filename>', methods=['GET'])
def serve_video(filename):
    """Serve generated video file"""
    try:
        videos_dir = os.path.join(os.path.dirname(__file__), "static", "generated_videos")
        return send_from_directory(videos_dir, filename)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 404


@app.route('/api/video/delete', methods=['POST'])
def delete_video():
    """Delete a generated video and its metadata"""
    data = request.json
    filename = data.get('filename')
    if not filename:
        return jsonify({"status": "error", "message": "filename is required"}), 400

    try:
        videos_dir = os.path.join(os.path.dirname(__file__), "static", "generated_videos")
        video_path = os.path.join(videos_dir, filename)
        if os.path.exists(video_path):
            os.remove(video_path)
        basename = os.path.splitext(filename)[0]
        meta_path = os.path.join(videos_dir, f"{basename}.json")
        if os.path.exists(meta_path):
            os.remove(meta_path)
        return jsonify({"status": "success", "message": "Video deleted"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/getSongs', methods=['GET'])
def get_songs():
    """List available music files"""
    try:
        music_dir = os.path.join(os.path.dirname(__file__), "static", "assets", "music")
        songs = []
        if os.path.exists(music_dir):
            for f in os.listdir(music_dir):
                if f.endswith(('.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac')):
                    songs.append(f)
        return jsonify({"status": "success", "data": {"songs": songs}})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/upload-music', methods=['POST'])
def upload_music():
    """Upload music file to library"""
    try:
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file provided"}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({"status": "error", "message": "No file selected"}), 400
        filename = secure_filename(file.filename)
        music_dir = os.path.join(os.path.dirname(__file__), "static", "assets", "music")
        os.makedirs(music_dir, exist_ok=True)
        file.save(os.path.join(music_dir, filename))
        return jsonify({"status": "success", "message": "File uploaded"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/download-music-url', methods=['POST'])
def download_music_url():
    """Download music from URL using yt-dlp"""
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({"status": "error", "message": "URL is required"}), 400

    try:
        music_dir = os.path.join(os.path.dirname(__file__), "static", "assets", "music")
        os.makedirs(music_dir, exist_ok=True)
        import yt_dlp
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': os.path.join(music_dir, '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return jsonify({"status": "success", "message": "Downloaded successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/upload-image', methods=['POST'])
def upload_image():
    """Upload image for thumbnail/frame"""
    try:
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file provided"}), 400
        files = request.files.getlist('file')
        paths = []
        for file in files:
            if file.filename == '':
                continue
            filename = f"{uuid.uuid4()}_{secure_filename(file.filename)}"
            images_dir = os.path.join(os.path.dirname(__file__), "static", "assets", "temp")
            os.makedirs(images_dir, exist_ok=True)
            filepath = os.path.join(images_dir, filename)
            file.save(filepath)
            paths.append(f"static/assets/temp/{filename}")
        return jsonify({"status": "success", "data": {"paths": paths}})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/upload-custom-audio', methods=['POST'])
def upload_custom_audio():
    """Upload custom audio for TTS replacement"""
    try:
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file provided"}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({"status": "error", "message": "No file selected"}), 400
        filename = f"{uuid.uuid4()}_{secure_filename(file.filename)}"
        audio_dir = os.path.join(os.path.dirname(__file__), "static", "assets", "custom_audio")
        os.makedirs(audio_dir, exist_ok=True)
        filepath = os.path.join(audio_dir, filename)
        file.save(filepath)
        return jsonify({"status": "success", "data": {"path": f"static/assets/custom_audio/{filename}"}})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/instagram/download', methods=['POST'])
def instagram_download():
    """Download Instagram video"""
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({"status": "error", "message": "URL is required"}), 400

    try:
        downloader = InstagramDownloader(
            output_path=os.path.join(os.path.dirname(__file__), "static", "generated_videos", "instagram")
        )
        result = downloader.download_video(url)
        return jsonify({"status": "success", "data": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    """Get or update global settings"""
    if request.method == 'GET':
        return jsonify({"status": "success", "data": get_settings()})

    data = request.json
    setting_type = data.get('type', 'FONT')
    settings = data.get('settings', {})
    update_settings(settings, setting_type)
    return jsonify({"status": "success", "message": "Settings updated"})


@app.route('/api/tts/status', methods=['GET'])
def tts_status():
    """Get TTS engine health status"""
    return jsonify({"status": "success", "data": get_tts_status()})


@app.route('/api/tts/voices', methods=['GET'])
def tts_voices():
    """Get voices for specific TTS engine"""
    engine = request.args.get('engine', 'supertonic')
    if engine == 'supertonic':
        return jsonify({
            "status": "success",
            "data": {
                "voices": get_supertonic_voices(),
                "voiceStyles": get_supertonic_voices_detailed(),
                "languages": get_supertonic_languages(),
                "qualityPresets": get_supertonic_quality_presets()
            }
        })
    else:
        return jsonify({
            "status": "success",
            "data": {
                "voices": get_tiktok_voices()
            }
        })


@app.route('/api/models', methods=['GET'])
def get_models():
    """Get all available voice models"""
    return jsonify({
        "status": "success",
        "data": {
            "voices": get_all_voices()['supertonic'],
            "voiceStyles": get_supertonic_voices_detailed()
        }
    })


@app.route('/api/magicsync/accounts', methods=['POST'])
def magicsync_accounts():
    """Get MagicSync connected accounts"""
    data = request.json
    url = data.get('url', os.getenv('MAGICSYNC_BASE_URL', 'http://localhost:3000'))
    api_token = data.get('apiToken', os.getenv('MAGICSYNC_API_TOKEN', ''))

    if not api_token:
        return jsonify({"status": "error", "message": "API token is required"}), 400

    try:
        response = requests.post(
            f"{url}/api/connected-accounts",
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=10
        )
        if response.status_code == 200:
            accounts = response.json().get('data', {}).get('accounts', [])
            return jsonify({"status": "success", "data": {"accounts": accounts}})
        return jsonify({"status": "error", "message": response.text}), response.status_code
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/schedule-to-magicsync', methods=['POST'])
def schedule_to_magicsync():
    """Schedule a video post via MagicSync"""
    data = request.json
    video_filename = data.get('videoFilename')
    scheduled_at = data.get('scheduledAt')
    content = data.get('content', '')
    title = data.get('title', '')
    description = data.get('description', '')
    platforms = data.get('platforms', [])
    url = data.get('url', os.getenv('MAGICSYNC_BASE_URL', 'http://localhost:3000'))
    api_token = data.get('apiToken', os.getenv('MAGICSYNC_API_TOKEN', ''))
    video_base_url = data.get('videoBaseUrl', os.getenv('VIDEO_BASE_URL', 'http://localhost:8080'))

    if not video_filename or not api_token or not platforms:
        return jsonify({"status": "error", "message": "videoFilename, apiToken, and platforms are required"}), 400

    try:
        video_url = f"{video_base_url}/api/video/{video_filename}"

        payload = {
            "videoUrl": video_url,
            "scheduledAt": scheduled_at,
            "content": content,
            "title": title,
            "description": description,
            "platforms": platforms,
        }

        response = requests.post(
            f"{url}/api/schedule-post",
            headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"},
            json=payload,
            timeout=30
        )

        if response.status_code in [200, 201]:
            return jsonify({"status": "success", "data": response.json().get('data', {})})
        return jsonify({"status": "error", "message": response.text}), response.status_code
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ============================================================
# Lead Generation Routes (Simplified)
# ============================================================

@app.route('/api/leadgen/campaigns', methods=['GET', 'POST'])
def leadgen_campaigns():
    if request.method == 'GET':
        return jsonify({"status": "success", "data": get_campaigns()})

    data = request.json
    name = data.get('name')
    description = data.get('description')
    keywords = data.get('keywords', [])
    platforms = data.get('platforms', ['twitter'])

    if not name or not description:
        return jsonify({"status": "error", "message": "name and description are required"}), 400

    enrichment = enrich_campaign_description(description)
    campaign = create_campaign(name, description, keywords, platforms, enrichment)
    return jsonify({"status": "success", "data": campaign})


@app.route('/api/leadgen/campaigns/<campaign_id>', methods=['GET', 'PUT', 'DELETE'])
def leadgen_campaign_detail(campaign_id):
    if request.method == 'GET':
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({"status": "error", "message": "Campaign not found"}), 404
        return jsonify({"status": "success", "data": campaign})

    if request.method == 'DELETE':
        if delete_campaign(campaign_id):
            return jsonify({"status": "success", "message": "Campaign deleted"})
        return jsonify({"status": "error", "message": "Campaign not found"}), 404

    data = request.json
    campaign = update_campaign(campaign_id, data)
    if not campaign:
        return jsonify({"status": "error", "message": "Campaign not found"}), 404
    return jsonify({"status": "success", "data": campaign})


@app.route('/api/leadgen/campaigns/<campaign_id>/leads', methods=['GET', 'POST'])
def leadgen_leads(campaign_id):
    if request.method == 'GET':
        leads = get_leads(campaign_id)
        return jsonify({"status": "success", "data": leads})

    data = request.json
    lead = add_lead(campaign_id, data)
    return jsonify({"status": "success", "data": lead})


# ============================================================
# Health Check & Static Routes
# ============================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


@app.route('/static/<path:path>', methods=['GET'])
def serve_static(path):
    return send_from_directory(os.path.join(os.path.dirname(__file__), "static"), path)


# ============================================================
# Main Entry Point
# ============================================================

if __name__ == "__main__":
    # Ensure directories exist
    ensure_dirs()

    # Check environment variables
    check_env_vars()

    # Parse command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--cli', action='store_true', help='Run in CLI mode')
    parser.add_argument('--prompt', type=str, help='Video topic prompt')
    args = parser.parse_args()

    if args.cli and args.prompt:
        try:
            print(colored(f"[*] Starting Direct HD Video Generation for Topic: '{args.prompt}'...", "cyan"))
            videoClass = Shorts(args.prompt, 1, "g4f")
            videoClass.GenerateScript()
            videoClass.GenerateSearchTerms()
            videoClass.DownloadVideos([])
            videoClass.GenerateVoice("M3")
            videoClass.CombineVideos()
            videoClass.GenerateMetadata()
            print(colored(f"[+] Video generated successfully: {videoClass.get_final_video_path}", "green"))
        except RuntimeError as e:
            print(colored(f"[-] Error: {e}", "red"))
            sys.exit(1)
        except Exception as e:
            print(colored(f"[-] Unexpected error: {e}", "red"))
            sys.exit(1)
    else:
        # Normal Flask app run
        port = int(os.getenv('API_PORT', 8080))
        print(colored(f"[*] Starting Flask server on port {port}...", "cyan"))
        app.run(host='0.0.0.0', port=port, debug=False)
