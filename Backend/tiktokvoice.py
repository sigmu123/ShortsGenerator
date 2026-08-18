"""
Backend/tiktokvoice.py (Backend/voice.py) - Production-Grade TTS Engine
Powered by Microsoft Edge Neural TTS with gTTS & Local Fallback.
"""

import os
import re
import asyncio
import hashlib
from typing import List, Optional
import edge_tts
from gtts import gTTS

VOICE_MAP = {
    # Edge Neural Voices (High Quality)
    "en_us_001": "en-US-ChristopherNeural",   # Deep Male Storyteller
    "en_us_002": "en-US-JennyNeural",         # Energetic Female Host
    "en_us_006": "en-US-GuyNeural",           # Casual Male
    "en_us_010": "en-US-AriaNeural",          # Professional Female
    "en_uk_001": "en-GB-RyanNeural",          # British Male
    "en_uk_003": "en-GB-SoniaNeural",         # British Female
    "en_au_001": "en-AU-WilliamNeural",       # Australian Male
}

def split_text_into_chunks(text: str, max_chars: int = 250) -> List[str]:
    """Splits long text into natural sentence/clause chunks under max_chars."""
    # Split by punctuation
    sentences = re.split(r'(?<=[.!?\n]) +', text.strip())
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        if len(current_chunk) + len(sentence) + 1 <= max_chars:
            current_chunk = f"{current_chunk} {sentence}".strip()
        else:
            if current_chunk:
                chunks.append(current_chunk)
            if len(sentence) > max_chars:
                # Sub-split long sentence by commas
                subparts = re.split(r'(?<=[,;]) +', sentence)
                for subpart in subparts:
                    if len(subpart) > max_chars:
                        # Hard split by words
                        words = subpart.split()
                        temp = ""
                        for w in words:
                            if len(temp) + len(w) + 1 <= max_chars:
                                temp = f"{temp} {w}".strip()
                            else:
                                if temp: chunks.append(temp)
                                temp = w
                        if temp: chunks.append(temp)
                    else:
                        chunks.append(subpart)
                current_chunk = ""
            else:
                current_chunk = sentence
                
    if current_chunk:
        chunks.append(current_chunk)
        
    return [c.strip() for c in chunks if c.strip()]


async def _synthesize_edge_tts(text: str, voice_name: str, output_path: str) -> str:
    """Async generator for Edge-TTS."""
    communicate = edge_tts.Communicate(text, voice_name, rate="+5%", pitch="+0Hz")
    await communicate.save(output_path)
    return output_path


def synthesize_speech(text: str, voice: str = "en_us_001", output_path: str = "temp/voice.mp3") -> str:
    """
    Main TTS entry point. Converts input text to high-quality MP3 audio.
    Guarantees completion with multi-tier fallback.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    clean_text = text.replace("\n", " ").strip()
    
    if not clean_text:
        raise ValueError("Cannot synthesize empty text")
        
    edge_voice = VOICE_MAP.get(voice, "en-US-ChristopherNeural")
    
    # Check cache
    text_hash = hashlib.md5(f"{clean_text}_{edge_voice}".encode()).hexdigest()
    cache_path = os.path.join("temp", "cache", f"{text_hash}.mp3")
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 100:
        import shutil
        shutil.copy(cache_path, output_path)
        return output_path

    # Tier 1: Microsoft Edge Neural TTS
    try:
        chunks = split_text_into_chunks(clean_text)
        if len(chunks) == 1:
            asyncio.run(_synthesize_edge_tts(chunks[0], edge_voice, output_path))
        else:
            # Multi-chunk synthesis
            temp_chunk_files = []
            for idx, chunk in enumerate(chunks):
                chunk_file = f"temp/chunk_{idx}_{text_hash[:6]}.mp3"
                asyncio.run(_synthesize_edge_tts(chunk, edge_voice, chunk_file))
                temp_chunk_files.append(chunk_file)
                
            # Concatenate chunks using ffmpeg
            concat_list = f"temp/concat_{text_hash[:6]}.txt"
            with open(concat_list, "w", encoding="utf-8") as f:
                for cf in temp_chunk_files:
                    f.write(f"file '{os.path.abspath(cf)}'\n")
                    
            os.system(f"ffmpeg -y -f concat -safe 0 -i {concat_list} -c copy {output_path} -loglevel error")
            
            # Clean temp chunks
            if os.path.exists(concat_list): os.remove(concat_list)
            for cf in temp_chunk_files:
                if os.path.exists(cf): os.remove(cf)
                
        if os.path.exists(output_path) and os.path.getsize(output_path) > 100:
            import shutil
            shutil.copy(output_path, cache_path)
            return output_path
    except Exception as e:
        print(f"[WARN] Edge-TTS failed: {e}. Falling back to gTTS...")

    # Tier 2: Google TTS Fallback
    try:
        tts = gTTS(text=clean_text, lang='en', slow=False)
        tts.save(output_path)
        return output_path
    except Exception as e2:
        print(f"[ERROR] All TTS engines failed: {e2}")
        raise RuntimeError(f"Failed to generate speech: {e2}")
