"""
Backend/classes/Shorts.py - Master Pipeline Orchestrator Class
Coordinates AI Script Generation, Speech Synthesis, Stock Footage Retrieval,
and MoviePy/FFmpeg 9:16 Video Rendering into static output delivery.
"""

import os
import uuid
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

import settings
import gpt
import tiktokvoice
import search
import video


class Shorts:
    """
    Master pipeline orchestrator for creating automated YouTube Shorts and TikTok videos.
    """

    def __init__(
        self,
        topic: str,
        duration: int = settings.DEFAULT_DURATION_SEC,
        voice: str = settings.DEFAULT_VOICE,
        subtitle_style: str = "mrbeast",
        bg_music_path: Optional[str] = None,
        task_id: Optional[str] = None,
        aspect_ratio: str = settings.DEFAULT_ASPECT_RATIO
    ):
        self.task_id = task_id or str(uuid.uuid4())[:8]
        self.topic = topic.strip()
        self.duration = duration
        self.voice = voice
        self.subtitle_style = subtitle_style
        self.bg_music_path = bg_music_path
        self.aspect_ratio = aspect_ratio
        
        # Target Dimensions
        self.width, self.height = settings.ASPECT_RATIOS.get(aspect_ratio, (1080, 1920))
        
        # Pipeline State
        self.script_data: Dict[str, Any] = {}
        self.voiceover_path: Optional[str] = None
        self.video_clip_paths: List[str] = []
        self.output_video_path: Optional[str] = None
        self.download_url: Optional[str] = None
        self.temp_files_to_clean: List[str] = []
        
        # Output paths
        self.output_filename = f"short_{self.task_id}.mp4"
        self.output_video_path = str(settings.GENERATED_VIDEOS_DIR / self.output_filename)

    def update_progress(
        self,
        callback: Optional[Callable[[int, str, str], None]],
        progress: int,
        status: str,
        message: str
    ):
        """Notifies progress listener if registered."""
        if callback:
            try:
                callback(progress, status, message)
            except Exception as e:
                print(f"[WARN] Progress callback error: {e}")

    def generate_script(self, callback: Optional[Callable] = None) -> Dict[str, Any]:
        """Step 1: Generates structured script, hook, and scene keywords via Gemini / LLM."""
        self.update_progress(callback, 15, "generating_script", f"Generating viral script about '{self.topic}'...")
        self.script_data = gpt.generate_script(
            topic=self.topic,
            duration_sec=self.duration
        )
        self.update_progress(callback, 30, "generating_script", "Script and visual scenes generated successfully.")
        return self.script_data

    def synthesize_audio(self, callback: Optional[Callable] = None) -> str:
        """Step 2: Synthesizes high-retention voiceover audio using Edge Neural TTS / gTTS."""
        if not self.script_data:
            raise ValueError("Cannot synthesize audio before script generation.")

        self.update_progress(callback, 40, "synthesizing_audio", "Synthesizing ultra-realistic AI voiceover...")
        
        full_script = self.script_data.get("fullScript", "")
        self.voiceover_path = str(settings.TEMP_DIR / f"voice_{self.task_id}.mp3")
        self.temp_files_to_clean.append(self.voiceover_path)
        
        tiktokvoice.synthesize_speech(
            text=full_script,
            voice=self.voice,
            output_path=self.voiceover_path
        )
        
        self.update_progress(callback, 55, "synthesizing_audio", "Voiceover audio track ready.")
        return self.voiceover_path

    def retrieve_footage(self, callback: Optional[Callable] = None) -> List[str]:
        """Step 3: Searches and downloads portrait 9:16 video clips for each scene."""
        scenes = self.script_data.get("scenes", [])
        self.video_clip_paths = []
        
        total_scenes = max(len(scenes), 1)
        self.update_progress(callback, 60, "downloading_footage", f"Retrieving stock video footage for {total_scenes} scenes...")
        
        for idx, scene in enumerate(scenes):
            keyword = scene.get("searchKeyword", self.topic)
            clip_path = str(settings.TEMP_DIR / f"clip_{self.task_id}_{idx}.mp4")
            self.temp_files_to_clean.append(clip_path)
            
            search.search_and_download_video(
                query=keyword,
                output_path=clip_path,
                target_portrait=(self.aspect_ratio == "9:16")
            )
            self.video_clip_paths.append(clip_path)
            
            sub_progress = 60 + int((idx + 1) / total_scenes * 15)
            self.update_progress(callback, sub_progress, "downloading_footage", f"Downloaded clip {idx+1}/{total_scenes}: '{keyword}'")

        return self.video_clip_paths

    def render_final_video(self, callback: Optional[Callable] = None) -> str:
        """Step 4: Assembles video clips, audio ducking, and viral animated captions into MP4."""
        self.update_progress(callback, 80, "rendering_video", "Compositing 9:16 video, burning viral subtitles, and mixing audio...")
        
        video.build_final_short_video(
            video_clips_paths=self.video_clip_paths,
            voiceover_path=self.voiceover_path,
            scenes=self.script_data.get("scenes", []),
            output_path=self.output_video_path,
            bg_music_path=self.bg_music_path,
            subtitle_style=self.subtitle_style
        )
        
        self.download_url = f"/api/download/{self.task_id}"
        self.update_progress(callback, 100, "completed", "Video generation completed successfully!")
        return self.output_video_path

    def cleanup_temp_files(self):
        """Removes temporary intermediate files while keeping the final generated MP4."""
        for temp_file in self.temp_files_to_clean:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception as e:
                print(f"[WARN] Failed to remove temp file {temp_file}: {e}")

    def execute_pipeline(self, callback: Optional[Callable] = None) -> Dict[str, Any]:
        """
        Executes the entire end-to-end video creation pipeline.
        Returns complete task result metadata.
        """
        start_time = time.time()
        try:
            self.generate_script(callback)
            self.synthesize_audio(callback)
            self.retrieve_footage(callback)
            self.render_final_video(callback)
            
            elapsed = round(time.time() - start_time, 2)
            
            result = {
                "id": self.task_id,
                "status": "completed",
                "progress": 100,
                "message": f"Successfully generated short in {elapsed}s",
                "title": self.script_data.get("title", self.topic),
                "hook": self.script_data.get("hook", ""),
                "full_script": self.script_data.get("fullScript", ""),
                "scenes": self.script_data.get("scenes", []),
                "suggested_tags": self.script_data.get("suggestedTags", []),
                "video_url": self.download_url,
                "static_url": f"/static/generated_videos/{self.output_filename}",
                "output_path": self.output_video_path,
                "elapsed_time": elapsed
            }
            return result
            
        except Exception as e:
            self.update_progress(callback, 0, "failed", f"Generation error: {str(e)}")
            raise e
        finally:
            self.cleanup_temp_files()
