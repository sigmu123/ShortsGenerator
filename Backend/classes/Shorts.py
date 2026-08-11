import os
from utils import *
from settings import *
from gpt import *
from search import *
from termcolor import colored
from flask import jsonify, json
from video import *
from tiktokvoice import *
from uuid import uuid4
from apiclient.errors import HttpError
from moviepy.config import change_settings
import traceback  # <-- new import for detailed error

class Shorts:
    VIDEO_END_BUFFER = 3.0
    def __init__(self, video_subject, paragraph_number, ai_model, customPrompt="", extra_prompt="", script_template=""):
        global GENERATING
        GENERATING = True
        change_settings({"IMAGEMAGICK_BINARY": os.getenv("IMAGEMAGICK_BINARY")})
        self.video_subject = video_subject
        self.paragraph_number = paragraph_number
        self.ai_model = ai_model
        self.customPrompt = customPrompt
        self.extra_prompt = extra_prompt
        self.script_template = script_template
        self.globalSettings = get_settings()
        self.final_script = ""
        self.search_terms = []
        self.AMOUNT_OF_STOCK_VIDEOS = 5
        self.video_urls = []
        self.video_paths = []
        self.videos_quantity_search = 15
        self.min_duration_search = 5
        self.voice = "en_us_001"
        self.voice_prefix = self.voice[:2]
        self.tts_path = None
        self.subtitles_path = None
        self.final_video_path = None
        self.video_title = None
        self.video_description = None
        self.video_tags = None
        self.subtitles_position = ""
        self.subtitle_template = "classic"
        self.aspect_ratio = "9:16"
        self.custom_subtitle = ""
        self.final_music_video_path = ""
        self.image_paths = []
        self.image_duration = 5.0
        self.image_durations = []
        self.clip_duration = self.globalSettings.get("clipDurationSettings", {}).get("default", 10)

    # ... (baqi methods same rahenge, lekin GenerateVoice aur CombineVideos mein error handling improve karenge)

    def GenerateVoice(self, voice, custom_audio_path="", audio_start_time=0, audio_end_time=0, quality=None, speed=None):
        print(colored(f"[X] Generating voice: {voice} ", "green"))
        global GENERATING
        self.voice = voice
        self.voice_prefix = voice[:2]

        if self.custom_subtitle and self.custom_subtitle.strip():
            sentences = [s.strip() for s in self.custom_subtitle.split(". ") if s.strip()]
        else:
            sentences = self.final_script.split(". ")
            sentences = list(filter(lambda x: x != "", sentences))

        temp_dir_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static", "assets", "temp"))
        os.makedirs(temp_dir_path, exist_ok=True)
        paths = []
        self.tts_path = None
        sentence_durations = None

        # Custom audio path
        if custom_audio_path:
            abs_custom_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', custom_audio_path))
            if not os.path.exists(abs_custom_path):
                abs_custom_path = custom_audio_path
            custom_audio_path = abs_custom_path
        if custom_audio_path and os.path.exists(custom_audio_path):
            print(colored(f"[+] Using custom audio: {custom_audio_path}", "green"))
            try:
                from moviepy.editor import AudioFileClip
                audio_clip = AudioFileClip(custom_audio_path)
                dur = float(audio_clip.duration)
                audio_start = float(audio_start_time) if audio_start_time > 0 else 0
                audio_end = float(audio_end_time) if audio_end_time > 0 else dur
                if audio_end > dur:
                    audio_end = dur
                if audio_end > audio_start:
                    audio_clip = audio_clip.subclip(audio_start, audio_end)
                trimmed_path = os.path.join(temp_dir_path, f"{uuid4()}.mp3")
                audio_clip.write_audiofile(trimmed_path)
                audio_clip.close()
                self.tts_path = trimmed_path
                paths = [AudioFileClip(self.tts_path)]
                print(colored(f"[+] Custom audio trimmed to {audio_start}-{audio_end}s", "green"))
            except Exception as e:
                print(colored(f"[-] Error processing custom audio: {e}", "red"))
                self.tts_path = None

        if not paths:
            engine = get_tts_engine()
            if engine == "supertonic":
                if not GENERATING:
                    return jsonify({"status": "error", "message": "Video generation was cancelled.", "data": []})
                tts_settings = get_tts_settings()
                fileId = uuid4()
                supertonic_path = os.path.join(temp_dir_path, f"{fileId}.wav")
                try:
                    result = tts_with_fallback(
                        self.final_script,
                        self.voice,
                        filename=supertonic_path,
                        lang=tts_settings.get("tts_lang", "en"),
                        quality=quality if quality is not None else tts_settings.get("tts_quality", 8),
                        speed=speed if speed is not None else tts_settings.get("tts_speed", 1.05),
                    )
                except Exception as e:
                    print(colored(f"[-] Supertonic TTS exception: {e}", "red"))
                    result = {"success": False, "error": str(e)}

                if result["success"] and os.path.exists(supertonic_path):
                    from moviepy.editor import AudioFileClip
                    audio_clip = AudioFileClip(supertonic_path)
                    paths = [audio_clip]
                    self.tts_path = supertonic_path
                    print(colored(f"[+] Supertonic generated full audio ({len(sentences)} sentences in one call)", "green"))
                else:
                    print(colored("[-] Supertonic failed, using TikTok sentence-by-sentence fallback", "yellow"))

            # Fallback: TikTok sentence-by-sentence
            if not paths:
                tiktok_voice = "en_us_001"
                sentence_durations = []
                print(colored(f"[*] Using TikTok TTS sentence-by-sentence (voice: {tiktok_voice})", "yellow"))
                for sentence in sentences:
                    if not GENERATING:
                        return jsonify({"status": "error", "message": "Video generation was cancelled.", "data": []})
                    fileId = uuid4()
                    current_tts_path = os.path.join(temp_dir_path, f"{fileId}.mp3")
                    try:
                        tts_with_fallback(sentence, tiktok_voice, filename=current_tts_path)
                    except Exception as e:
                        print(colored(f"[-] TTS for sentence failed: {e}", "red"))
                        continue
                    if os.path.exists(current_tts_path):
                        try:
                            from moviepy.editor import AudioFileClip
                            audio_clip = AudioFileClip(current_tts_path)
                            sentence_durations.append(float(audio_clip.duration))
                            paths.append(audio_clip)
                        except Exception as e:
                            print(colored(f"[-] Failed to load audio clip: {e}", "red"))
                            sentence_durations.append(0.0)

                if paths:
                    print(colored(f"[X] Combining {len(paths)} sentence audio files", "green"))
                    from moviepy.editor import concatenate_audioclips
                    final_audio = concatenate_audioclips(paths)
                    self.tts_path = os.path.join(temp_dir_path, f"{uuid4()}.mp3")
                    final_audio.write_audiofile(self.tts_path)
                else:
                    print(colored("[-] No audio clips generated", "red"))

        # Generate subtitles
        if paths and self.tts_path and os.path.exists(self.tts_path):
            try:
                self.subtitles_path = generate_subtitles(audio_path=self.tts_path, sentences=sentences, voice=self.voice_prefix, sentence_durations=sentence_durations)
            except Exception as e:
                print(colored(f"[-] Error generating subtitles: {e}", "red"))
                print(colored(traceback.format_exc(), "red"))
                self.subtitles_path = None
        else:
            print(colored("[-] No audio generated for subtitles", "red"))
            self.subtitles_path = None

    def CombineVideos(self):
        if not self.tts_path or not os.path.exists(self.tts_path):
            print(colored("[-] No TTS audio found. Cannot combine videos.", "red"))
            return
        try:
            from moviepy.editor import AudioFileClip
            temp_audio = AudioFileClip(self.tts_path)
        except Exception as e:
            print(colored(f"[-] Failed to load TTS audio: {e}", "red"))
            return

        n_threads = 2
        aspect_ratio = getattr(self, "aspect_ratio", "9:16") or "9:16"
        subtitle_template = getattr(self, "subtitle_template", "classic") or "classic"
        clip_duration = getattr(self, "clip_duration", 10)

        combined_video_path = combine_videos(
            self.video_paths,
            temp_audio.duration,
            clip_duration,
            n_threads or 2,
            aspect_ratio=aspect_ratio,
            image_paths=self.image_paths if hasattr(self, 'image_paths') else None,
            image_duration=self.image_duration if hasattr(self, 'image_duration') else 5.0,
            image_durations=self.image_durations if hasattr(self, 'image_durations') else None,
            buffer_time=self.VIDEO_END_BUFFER,
        )

        if not combined_video_path or not os.path.exists(combined_video_path):
            print(colored("[-] combine_videos returned None or file not found", "red"))
            return

        print(colored(f"[-] Next step: {combined_video_path}", "green"))
        try:
            self.final_video_path = generate_video(
                combined_video_path,
                self.tts_path,
                self.subtitles_path,
                n_threads or 2,
                self.subtitles_position,
                subtitle_template=subtitle_template,
                aspect_ratio=aspect_ratio,
                buffer_time=self.VIDEO_END_BUFFER,
            )
        except Exception as e:
            print(colored(f"[-] Error generating final video: {e}", "red"))
            print(colored(traceback.format_exc(), "red"))
            self.final_video_path = None
