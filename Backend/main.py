"""
Backend/main.py - Dual-Mode Execution: Headless CLI Generator & Flask REST Server
1. CLI Mode (GitHub Actions & CI/CD): Triggered by PROMPT_INPUT env var or --cli / --prompt flags.
   Executes pipeline synchronously, prints stdout telemetry, saves MP4, and exits cleanly with code 0 (or 1 on error).
2. Server Mode (Interactive & Web UI): Starts Flask REST API on Port 8080 with async ThreadPool workers, CORS, and progress polling.
"""

import os
import sys
import uuid
import time
import argparse
import traceback
import shutil
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

import settings
from classes.Shorts import Shorts
import search

load_dotenv()

# ==========================================
# 1. FLASK APPLICATION INITIALIZATION
# ==========================================
app = Flask(__name__, static_folder=str(settings.STATIC_DIR))
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# Background Task ThreadPool for Server Mode
executor = ThreadPoolExecutor(max_workers=4)
TASKS: dict = {}


def async_pipeline_worker(task_id: str, topic: str, duration: int, voice: str, subtitle_style: str, bg_music: str):
    """Executes the complete Shorts pipeline in a background thread for HTTP clients."""
    def progress_hook(progress: int, status: str, message: str):
        if task_id in TASKS:
            TASKS[task_id]["progress"] = progress
            TASKS[task_id]["status"] = status
            TASKS[task_id]["message"] = message

    try:
        generator = Shorts(
            topic=topic,
            duration=duration,
            voice=voice,
            subtitle_style=subtitle_style,
            bg_music_path=bg_music,
            task_id=task_id
        )
        
        result = generator.execute_pipeline(callback=progress_hook)
        
        TASKS[task_id].update({
            "status": "completed",
            "progress": 100,
            "message": "Video generated successfully!",
            "result": result,
            "video_url": result["video_url"],
            "static_url": result["static_url"],
            "output_path": result["output_path"]
        })
        
    except Exception as e:
        print(f"[ERROR] Task {task_id} failed: {e}")
        if task_id in TASKS:
            TASKS[task_id].update({
                "status": "failed",
                "progress": 0,
                "error": str(e),
                "message": f"Pipeline failure: {str(e)}"
            })


# ==========================================
# 2. REST API ENDPOINTS (SERVER MODE)
# ==========================================

@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint for monitoring."""
    active_count = len([t for t in TASKS.values() if t.get("status") in [
        "queued", "generating_script", "synthesizing_audio", "downloading_footage", "rendering_video"
    ]])
    return jsonify({
        "status": "online",
        "service": "ShortsGenerator Backend",
        "port": settings.PORT,
        "active_tasks": active_count,
        "static_dir": str(settings.STATIC_DIR)
    }), 200


@app.route("/api/generate", methods=["POST"])
def start_generation():
    """Starts async Short generation and returns task_id immediately."""
    data = request.get_json() or {}
    topic = data.get("topic", "").strip()
    
    if not topic:
        return jsonify({"error": "Field 'topic' is required in JSON payload"}), 400
        
    duration = int(data.get("duration", settings.DEFAULT_DURATION_SEC))
    voice = data.get("voice", settings.DEFAULT_VOICE)
    subtitle_style = data.get("subtitle_style", "mrbeast")
    bg_music = data.get("bg_music", None)
    
    task_id = str(uuid.uuid4())[:8]
    
    TASKS[task_id] = {
        "id": task_id,
        "topic": topic,
        "duration": duration,
        "voice": voice,
        "subtitle_style": subtitle_style,
        "status": "queued",
        "progress": 5,
        "message": "Task queued in thread pool...",
        "created_at": time.time()
    }
    
    # Launch pipeline in background thread pool
    executor.submit(async_pipeline_worker, task_id, topic, duration, voice, subtitle_style, bg_music)
    
    return jsonify({
        "task_id": task_id,
        "status": "queued",
        "status_url": f"/api/status/{task_id}",
        "download_url": f"/api/download/{task_id}"
    }), 202


@app.route("/api/status/<task_id>", methods=["GET"])
def get_task_status(task_id):
    """Polls progress and status of a video generation task."""
    task = TASKS.get(task_id)
    if not task:
        return jsonify({"error": f"Task '{task_id}' not found"}), 404
        
    return jsonify(task), 200


@app.route("/api/download/<task_id>", methods=["GET"])
def download_video(task_id):
    """Streams the completed MP4 video file to client as attachment."""
    task = TASKS.get(task_id)
    if not task:
        target_path = settings.GENERATED_VIDEOS_DIR / f"short_{task_id}.mp4"
        if target_path.exists():
            return send_file(str(target_path), mimetype="video/mp4", as_attachment=True, download_name=f"short_{task_id}.mp4")
        return jsonify({"error": "Task not found"}), 404
        
    if task.get("status") != "completed":
        return jsonify({"error": f"Video is still processing (current status: {task.get('status')})"}), 400
        
    file_path = task.get("output_path")
    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": "Output video file missing from disk"}), 404
        
    return send_file(file_path, mimetype="video/mp4", as_attachment=True, download_name=f"short_{task_id}.mp4")


@app.route("/api/search-and-download", methods=["POST"])
def search_footage_endpoint():
    """Standalone endpoint for searching and downloading stock video clips."""
    data = request.get_json() or {}
    query = data.get("query", "").strip()
    target_portrait = bool(data.get("portrait", True))
    
    if not query:
        return jsonify({"error": "Field 'query' is required"}), 400
        
    clip_id = str(uuid.uuid4())[:8]
    output_path = str(settings.TEMP_DIR / f"clip_search_{clip_id}.mp4")
    
    result_path = search.search_and_download_video(query=query, output_path=output_path, target_portrait=target_portrait)
    
    return jsonify({
        "query": query,
        "downloaded_path": result_path,
        "filename": os.path.basename(result_path),
        "file_size_bytes": os.path.getsize(result_path) if os.path.exists(result_path) else 0
    }), 200


@app.route("/static/generated_videos/<filename>", methods=["GET"])
def serve_generated_video(filename):
    """Direct static file delivery for generated MP4 videos."""
    return send_from_directory(str(settings.GENERATED_VIDEOS_DIR), filename, mimetype="video/mp4")


# ==========================================
# 3. HEADLESS CLI RUNNER (FOR CI/CD & GITHUB ACTIONS)
# ==========================================

def run_cli_generator(
    topic: str,
    duration: int = settings.DEFAULT_DURATION_SEC,
    voice: str = settings.DEFAULT_VOICE,
    subtitle_style: str = "mrbeast",
    bg_music: str = None,
    task_id: str = None
) -> str:
    """
    Executes the video generation pipeline synchronously in headless CLI mode.
    Outputs step-by-step logs to stdout and returns the final MP4 path.
    Fails fast with non-zero exit code on unhandled errors.
    """
    print("=" * 65)
    print(" [CLI] SHORTSGENERATOR HEADLESS CI/CD VIDEO RUNNER")
    print("=" * 65)
    print(f"[*] Topic / Prompt : {topic}")
    print(f"[*] Target Duration: {duration} seconds")
    print(f"[*] Voice ID       : {voice}")
    print(f"[*] Subtitle Style : {subtitle_style}")
    print(f"[*] Output Directory: {settings.GENERATED_VIDEOS_DIR}")
    print("-" * 65)

    def cli_progress_callback(progress: int, status: str, message: str):
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] [{progress:3d}%] [{status.upper()}] {message}")

    try:
        generator = Shorts(
            topic=topic,
            duration=duration,
            voice=voice,
            subtitle_style=subtitle_style,
            bg_music_path=bg_music,
            task_id=task_id
        )

        result = generator.execute_pipeline(callback=cli_progress_callback)
        output_mp4 = result.get("output_path")

        # Create a deterministic copy 'latest_generated_video.mp4' for simplified CI/CD capture
        if output_mp4 and os.path.exists(output_mp4):
            latest_copy = settings.GENERATED_VIDEOS_DIR / "latest_generated_video.mp4"
            shutil.copy2(output_mp4, str(latest_copy))
            file_size_mb = round(os.path.getsize(output_mp4) / (1024 * 1024), 2)
            
            print("=" * 65)
            print(" [SUCCESS] VIDEO GENERATION COMPLETED CLEANLY!")
            print("=" * 65)
            print(f"[*] Output MP4       : {output_mp4}")
            print(f"[*] Artifact Path    : {latest_copy}")
            print(f"[*] Video File Size  : {file_size_mb} MB")
            print(f"[*] Script Hook      : {result.get('hook')}")
            print(f"[*] Execution Time   : {result.get('elapsed_time')}s")
            print("=" * 65)
            return output_mp4
        else:
            raise FileNotFoundError(f"Expected output file not found at: {output_mp4}")

    except Exception as e:
        print("\n" + "!" * 65)
        print(" [FATAL ERROR] VIDEO GENERATION PIPELINE FAILED")
        print("!" * 65)
        traceback.print_exc()
        print("!" * 65)
        sys.exit(1)


# ==========================================
# 4. ENTRYPOINT: DUAL-MODE DISPATCHER
# ==========================================

def main():
    parser = argparse.ArgumentParser(
        description="ShortsGenerator: AI-driven automated vertical video creator (CLI & Server Mode)",
        add_help=True
    )
    parser.add_argument("--cli", action="store_true", help="Force headless CLI execution instead of starting Flask server")
    parser.add_argument("--prompt", "-p", "--topic", "-t", type=str, default="", help="Video topic or prompt")
    parser.add_argument("--duration", "-d", type=int, default=settings.DEFAULT_DURATION_SEC, help="Target video duration in seconds (default: 45)")
    parser.add_argument("--voice", "-v", type=str, default=settings.DEFAULT_VOICE, help="TTS Voice ID (default: en_us_001)")
    parser.add_argument("--subtitle-style", "-s", type=str, default="mrbeast", choices=["mrbeast", "hormozi", "neon", "minimal"], help="Subtitle style preset")
    parser.add_argument("--bg-music", "-m", type=str, default=None, help="Path to optional background audio file")
    parser.add_argument("--task-id", type=str, default=None, help="Custom task ID for output naming")
    
    # Parse known arguments to avoid crashing if unknown flags are passed
    args, unknown = parser.parse_known_args()

    # Detect CI/CD environment variable or explicit CLI flags
    env_prompt = os.getenv("PROMPT_INPUT", "").strip()
    is_cli_mode = args.cli or bool(args.prompt) or bool(env_prompt)

    if is_cli_mode:
        # Determine effective prompt: flag takes precedence over env var
        chosen_prompt = args.prompt.strip() or env_prompt or "Top 5 Mind-Blowing Facts About Deep Space"
        
        # Determine duration from env or flag
        env_duration = os.getenv("DURATION")
        chosen_duration = int(env_duration) if (env_duration and env_duration.isdigit()) else args.duration
        
        # Determine voice from env or flag
        chosen_voice = os.getenv("VOICE", args.voice)
        
        # Determine subtitle style
        chosen_style = os.getenv("SUBTITLE_STYLE", args.subtitle_style)
        
        run_cli_generator(
            topic=chosen_prompt,
            duration=chosen_duration,
            voice=chosen_voice,
            subtitle_style=chosen_style,
            bg_music=args.bg_music,
            task_id=args.task_id
        )
        
        # Clean successful exit for GitHub Actions / CI runners
        sys.exit(0)

    else:
        # Standard Server Mode (Local development or Web UI)
        print("=" * 65)
        print(f"[*] ShortsGenerator Flask Backend starting on http://{settings.HOST}:{settings.PORT}")
        print(f"[*] Static Output Directory: {settings.GENERATED_VIDEOS_DIR}")
        print(f"[*] Mode: REST API Server (Async Workers)")
        print("=" * 65)
        app.run(host=settings.HOST, port=settings.PORT, debug=settings.DEBUG)


if __name__ == "__main__":
    main()
