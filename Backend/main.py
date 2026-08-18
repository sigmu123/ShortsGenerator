"""
Backend/main.py - Production Flask REST Server for ShortsGenerator
Running on Port 8080 with Async Task Execution, Progress Polling, Static File Delivery, and CORS.
"""

import os
import uuid
import time
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

import settings
from classes.Shorts import Shorts
import search

load_dotenv()

app = Flask(__name__, static_folder=str(settings.STATIC_DIR))
# Enable CORS for all routes and origins
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# Background Task ThreadPool
executor = ThreadPoolExecutor(max_workers=4)
TASKS: dict = {}


def async_pipeline_worker(task_id: str, topic: str, duration: int, voice: str, subtitle_style: str, bg_music: str):
    """Executes the complete Shorts pipeline in a background thread."""
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
# REST API ENDPOINTS
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
        # Check if direct file exists in static folder
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


if __name__ == "__main__":
    print(f"[*] ShortsGenerator Flask Backend starting on http://{settings.HOST}:{settings.PORT}")
    print(f"[*] Static output directory: {settings.GENERATED_VIDEOS_DIR}")
    app.run(host=settings.HOST, port=settings.PORT, debug=settings.DEBUG)
