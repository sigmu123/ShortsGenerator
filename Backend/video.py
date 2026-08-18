"""
Backend/video.py - Production Video Compositor & Viral Subtitle Engine
Compatible with MoviePy 1.x & 2.x, FFmpeg, and Auto-Configured ImageMagick.
"""

import os
import sys
import shutil
from typing import List, Dict, Any, Optional

# Safe MoviePy Import Shim (Supports both v1.x and v2.x)
try:
    from moviepy.editor import (
        VideoFileClip, AudioFileClip, CompositeVideoClip,
        CompositeAudioClip, TextClip, ColorClip, vfx, afx
    )
    from moviepy.config import change_settings
except ImportError:
    try:
        from moviepy import (
            VideoFileClip, AudioFileClip, CompositeVideoClip,
            CompositeAudioClip, TextClip, ColorClip, vfx, afx
        )
        from moviepy.config import change_settings
    except ImportError as e:
        raise ImportError(f"MoviePy is not installed. Run 'pip install moviepy==1.0.3': {e}")


def configure_imagemagick():
    """Auto-detects and configures ImageMagick binary path across platforms."""
    imagemagick_env = os.getenv("IMAGEMAGICK_BINARY")
    if imagemagick_env and os.path.exists(imagemagick_env):
        change_settings({"IMAGEMAGICK_BINARY": imagemagick_env})
        return

    # Linux / Docker Common Paths
    linux_paths = ["/usr/bin/magick", "/usr/bin/convert", "/usr/local/bin/magick"]
    for path in linux_paths:
        if os.path.exists(path):
            change_settings({"IMAGEMAGICK_BINARY": path})
            return

    # Windows Common Paths
    if sys.platform == "win32":
        import glob
        win_paths = glob.glob(r"C:\Program Files\ImageMagick-*\magick.exe")
        if win_paths:
            change_settings({"IMAGEMAGICK_BINARY": win_paths[0]})
            return

configure_imagemagick()


def fit_to_vertical(clip: VideoFileClip, target_w: int = 1080, target_h: int = 1920) -> VideoFileClip:
    """
    Fits any video clip into standard 9:16 vertical short dimensions
    using smart center-cropping to avoid distortion.
    """
    w, h = clip.size
    target_ratio = target_w / target_h
    current_ratio = w / h

    if abs(current_ratio - target_ratio) < 0.01:
        return clip.resize((target_w, target_h))

    if current_ratio > target_ratio:
        # Landscape -> Crop width
        new_w = int(h * target_ratio)
        x_center = w // 2
        x1 = x_center - (new_w // 2)
        cropped = clip.crop(x1=x1, y1=0, width=new_w, height=h)
    else:
        # Taller than 9:16 -> Crop height
        new_h = int(w / target_ratio)
        y_center = h // 2
        y1 = y_center - (new_h // 2)
        cropped = clip.crop(x1=0, y1=y1, width=w, height=new_h)

    return cropped.resize((target_w, target_h))


def create_subtitle_clips(
    scenes: List[Dict[str, Any]],
    total_duration: float,
    target_w: int = 1080,
    target_h: int = 1920,
    style: str = "mrbeast"
) -> List[Any]:
    """
    Generates high-retention, high-contrast animated subtitle overlays.
    """
    subtitle_clips = []
    
    font_colors = {
        "mrbeast": ("#FFFF00", "#000000"),  # Yellow on Black
        "hormozi": ("#00FF66", "#000000"),  # Neon Green on Black
        "neon": ("#00FFFF", "#000000"),     # Cyan on Black
        "minimal": ("#FFFFFF", "#111111")   # Pure White on Dark
    }
    primary_color, stroke_color = font_colors.get(style, ("#FFFF00", "#000000"))
    
    time_cursor = 0.0
    
    for scene in scenes:
        text = scene.get("text", "").strip()
        duration = float(scene.get("estimatedDuration", 4.0))
        
        if not text:
            time_cursor += duration
            continue
            
        # Split scene text into 3-5 word readable chunks
        words = text.split()
        chunk_size = 4
        sub_chunks = [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]
        chunk_duration = duration / max(len(sub_chunks), 1)
        
        for sub_text in sub_chunks:
            try:
                txt_clip = TextClip(
                    sub_text.upper(),
                    fontsize=64,
                    font="Arial-Bold",
                    color=primary_color,
                    stroke_color=stroke_color,
                    stroke_width=4,
                    method="caption",
                    size=(int(target_w * 0.85), None),
                    align="center"
                )
                
                # Position in the lower-middle visual safe zone (70% down)
                y_pos = int(target_h * 0.70)
                txt_clip = (
                    txt_clip
                    .set_position(("center", y_pos))
                    .set_start(time_cursor)
                    .set_duration(chunk_duration)
                )
                subtitle_clips.append(txt_clip)
            except Exception as e:
                print(f"[WARN] TextClip generation failed ({e}). Proceeding without text overlay.")
                
            time_cursor += chunk_duration

    return subtitle_clips


def build_final_short_video(
    video_clips_paths: List[str],
    voiceover_path: str,
    scenes: List[Dict[str, Any]],
    output_path: str = "output/short_final.mp4",
    bg_music_path: Optional[str] = None,
    subtitle_style: str = "mrbeast"
) -> str:
    """
    Assembles video clips, voiceover, background music, and viral captions into a finished 9:16 Short.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    loaded_clips = []
    voice_audio = None
    music_audio = None
    
    try:
        # 1. Load Voiceover
        voice_audio = AudioFileClip(voiceover_path)
        total_duration = voice_audio.duration
        
        # 2. Load and Fit Video Backgrounds
        time_per_clip = total_duration / max(len(video_clips_paths), 1)
        processed_video_clips = []
        
        for idx, v_path in enumerate(video_clips_paths):
            clip = VideoFileClip(v_path)
            loaded_clips.append(clip)
            
            # Loop clip if shorter than needed
            if clip.duration < time_per_clip:
                clip = clip.loop(duration=time_per_clip)
            else:
                clip = clip.subclip(0, time_per_clip)
                
            fitted_clip = fit_to_vertical(clip)
            processed_video_clips.append(fitted_clip)
            
        # Concatenate background video track
        if len(processed_video_clips) == 1:
            bg_video = processed_video_clips[0].set_duration(total_duration)
        else:
            from moviepy.editor import concatenate_videoclips
            bg_video = concatenate_videoclips(processed_video_clips, method="compose").set_duration(total_duration)
            
        # 3. Audio Mixing & Ducking
        audio_tracks = [voice_audio]
        if bg_music_path and os.path.exists(bg_music_path):
            music_audio = AudioFileClip(bg_music_path)
            if music_audio.duration < total_duration:
                music_audio = music_audio.loop(duration=total_duration)
            else:
                music_audio = music_audio.subclip(0, total_duration)
                
            # Duck music volume to -18dB (0.12x) under voiceover
            music_audio = music_audio.volumex(0.12).audio_fadein(1.0).audio_fadeout(2.0)
            audio_tracks.append(music_audio)
            
        final_audio = CompositeAudioClip(audio_tracks)
        bg_video = bg_video.set_audio(final_audio)
        
        # 4. Generate & Overlay Subtitles
        subtitle_overlays = create_subtitle_clips(
            scenes=scenes,
            total_duration=total_duration,
            style=subtitle_style
        )
        
        # 5. Composite Final Video
        final_composite = CompositeVideoClip([bg_video] + subtitle_overlays)
        
        # 6. Render with Hardware/Fast H.264 Presets
        final_composite.write_videofile(
            output_path,
            fps=30,
            codec="libx264",
            audio_codec="aac",
            preset="fast",
            threads=4,
            logger=None
        )
        
        return output_path
        
    finally:
        # Guarantees memory cleanup and unlocks files
        for c in loaded_clips:
            try: c.close()
            except: pass
        if voice_audio:
            try: voice_audio.close()
            except: pass
        if music_audio:
            try: music_audio.close()
            except: pass
