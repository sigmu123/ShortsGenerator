def generate_video(
    combined_video_path: str,
    tts_path: str,
    subtitles_path: str,
    threads: int,
    subtitles_position: str,
    subtitle_template: str = "classic",
    aspect_ratio: str = "9:16",
    buffer_time: float = 3.0,
) -> str:
    print(colored("[+] Starting video generation with MoviePy Subtitles Renderer...", "green"))
    # ... (baqi code same)

    # Subtitles ko try karein, agar fail ho to bina subtitles ke video bana dein
    try:
        if subtitles_path and os.path.exists(subtitles_path):
            subtitles = SubtitlesClip(subtitles_path, generator)
        else:
            subtitles = None
    except Exception as e:
        print(colored(f"[-] Subtitle loading failed: {e}. Proceeding without subtitles.", "yellow"))
        subtitles = None

    # ... (rest of the function)
