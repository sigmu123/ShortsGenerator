"""
Backend/main.py - Production Flask REST Server for ShortsGenerator
Features Async Worker Tasks, Progress Status Polling, CORS, and Health Monitoring.
"""

import os
import uuid
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from dotenv import load_dotenv

import gpt
import tiktokvoice
import search
import video

load_dotenv()

app = Flask(__name__)
# Enable CORS for all routes and origins
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# Background Task Pool
executor = ThreadPoolExecutor(max_workers=4)
TASKS: dict = {}

# Ensure output directories exist
os.makedirs("temp", exist_ok=True)
os.makedirs("output", exist_ok=True)


def process_short_generation(task_id: str, topic: str, duration_sec: int, voice: str, subtitle_style: str):
    """Worker function executed asynchronously in background thread."""
    try:
        # Step 1: Generate AI Script & Scenes
        TASKS[task_id]["status"] = "generating_script"
        TASKS[task_id]["progress"] = 15
        TASKS[task_id]["message"] = "Generating viral script and scene breakdowns..."
        
        script_data = gpt.generate_script(topic=topic, duration_sec=duration_sec)
        TASKS[task_id]["script_data"] = script_data
        TASKS[task_id]["progress"] = 35
        
        # Step 2: Synthesize Voiceover Audio
        TASKS[task_id]["status"] = "synthesizing_audio"
        TASKS[task_id]["message"] = "Synthesizing ultra-realistic voiceover..."
        voice_path = os.path.join("temp", f"voice_{task_id}.mp3")
        tiktokvoice.synthesize_speech(text=script_data["fullScript"], voice=voice, output_path=voice_path)
        TASKS[task_id]["progress"] = 55
        
        # Step 3: Search and Download Stock Footage Clips
        TASKS[task_id]["status"] = "downloading_footage"
        TASKS[task_id]["message"] = "Searching and downloading 9:16 vertical stock video clips..."
        video_clips = []
        scenes = script_data.get("scenes", [])
        
        for idx, scene in enumerate(scenes):
            kw = scene.get("searchKeyword", topic)
            clip_path = os.path.join("temp", f"clip_{task_id}_{idx}.mp4")
            search.search_and_download_video(query=kw, output_path=clip_path, target_portrait=True)
            video_clips.append(clip_path)
            
        TASKS[task_id]["progress"] = 75
        
        # Step 4: Assemble Final Video with Captions
        TASKS[task_id]["status"] = "rendering_video"
        TASKS[task_id]["message"] = "Compositing video, burning subtitles, and ducking audio..."
        output_video_path = os.path.join("output", f"short_{task_id}.mp4")
        
        video.build_final_short_video(
            video_clips_paths=video_clips,
            voiceover_path=voice_path,
            scenes=scenes,
            output_path=output_video_path,
            subtitle_style=subtitle_style
        )
        
        # Step 5: Completed
        TASKS[task_id]["status"] = "completed"
        TASKS[task_id]["progress"] = 100
        TASKS[task_id]["message"] = "Video generation complete!"
        TASKS[task_id]["video_url"] = f"/api/download/{task_id}"
        TASKS[task_id]["output_path"] = output_video_path
        
    except Exception as e:
        print(f"[ERROR] Task {task_id} failed: {e}")
        TASKS[task_id]["status"] = "failed"
        TASKS[task_id]["error"] = str(e)
        TASKS[task_id]["message"] = f"Generation failed: {str(e)}"


@app.route("/api/health", methods=["GET"])
def health_check():
    """Healthcheck endpoint for monitoring."""
    return jsonify({
        "status": "online",
        "service": "ShortsGenerator Backend",
        "active_tasks": len([t for t in TASKS.values() if t.get("status") in ["generating_script", "synthesizing_audio", "downloading_footage", "rendering_video"]])
    }), 200


@app.route("/api/generate", methods=["POST"])
def start_generation():
    """Starts async Short generation and returns task_id."""
    data = request.get_json() or {}
    topic = data.get("topic", "").strip()
    
    if not topic:
        return jsonify({"error": "Missing 'topic' in request payload"}), 400
        
    duration_sec = int(data.get("duration", 45))
    voice = data.get("voice", "en_us_001")
    subtitle_style = data.get("subtitle_style", "mrbeast")
    
    task_id = str(uuid.uuid4())[:8]
    
    TASKS[task_id] = {
        "id": task_id,
        "topic": topic,
        "status": "queued",
        "progress": 5,
        "message": "Task queued for processing...",
        "created_at": time.time()
    }
    
    # Launch worker in background
    executor.submit(process_short_generation, task_id, topic, duration_sec, voice, subtitle_style)
    
    return jsonify({
        "task_id": task_id,
        "status": "queued",
        "status_url": f"/api/status/{task_id}"
    }), 202


@app.route("/api/status/<task_id>", methods=["GET"])
def get_task_status(task_id):
    """Polls progress and status of a video generation task."""
    task = TASKS.get(task_id)
    if not task:
        return jsonify({"error": "Task ID not found"}), 404
        
    return jsonify(task), 200


@app.route("/api/download/<task_id>", methods=["GET"])
def download_video(task_id):
    """Streams the completed MP4 video file to client."""
    task = TASKS.get(task_id)
    if not task or task.get("status") != "completed":
        return jsonify({"error": "Video not ready or does not exist"}), 404
        
    file_path = task.get("output_path")
    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": "Output file missing on server"}), 404
        
    return send_file(file_path, mimetype="video/mp4", as_attachment=True, download_name=f"short_{task_id}.mp4")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"[*] ShortsGenerator Backend listening on http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
