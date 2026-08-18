"""
Backend/gpt.py - Production-Ready AI Script & Scene Generator
Powered by Google GenAI SDK (gemini-3.6-flash) with structured JSON output and Offline Fallback.
"""

import os
import json
import re
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

# Initialize Gemini API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


def clean_json_response(raw_text: str) -> Dict[str, Any]:
    """Extracts and parses JSON even if wrapped in markdown codeblocks or conversational text."""
    if not raw_text:
        raise ValueError("Empty response from AI model")
        
    # Strip markdown codeblocks
    cleaned = re.sub(r"^\s*```(json)?", "", raw_text, flags=re.MULTILINE)
    cleaned = re.sub(r"```\s*$", "", cleaned, flags=re.MULTILINE).strip()
    
    # Locate first { and last }
    start_idx = cleaned.find("{")
    end_idx = cleaned.rfind("}")
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        json_str = cleaned[start_idx:end_idx + 1]
        return json.loads(json_str)
        
    return json.loads(cleaned)


def generate_with_gemini(topic: str, duration_sec: int = 45, tone: str = "viral") -> Dict[str, Any]:
    """Generates structured Short script and scene keywords using Google Gemini SDK with gemini-3.6-flash model."""
    from google import genai
    from google.genai import types
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    word_count = int((duration_sec / 60.0) * 140)  # ~140 words per minute
    
    system_instruction = (
        "You are an elite YouTube Shorts and TikTok viral content creator. "
        "Create punchy, high-retention vertical short scripts with strong hooks, "
        "engaging facts, and clear visual stock video keywords for each scene."
    )
    
    prompt = f"""
Create a high-retention YouTube Short script about: "{topic}".
Target duration: {duration_sec} seconds (~{word_count} words).
Tone: {tone}.

Output MUST be a single valid JSON object with the following schema:
{{
  "title": "Compelling Title",
  "hook": "First 3 seconds attention grabbing sentence",
  "fullScript": "Complete continuous voiceover script without sound effect tags",
  "scenes": [
    {{
      "id": 1,
      "text": "Sentence spoken in this scene",
      "searchKeyword": "2-3 word high quality Pexels stock video search term (e.g. 'cyber hacker matrix' or 'luxury sports car')",
      "visualDescription": "Brief description of the visual scene",
      "estimatedDuration": 5.0
    }}
  ],
  "searchTerms": ["broad_keyword_1", "broad_keyword_2", "broad_keyword_3"],
  "suggestedTags": ["#shorts", "#facts", "#viral"]
}}
"""

    # Primary target model: gemini-3.6-flash with dynamic fallbacks
    target_models = ["gemini-3.6-flash", "gemini-2.5-flash", "gemini-flash"]
    
    last_error = None
    for model_name in target_models:
        try:
            print(f"[INFO] Attempting script generation with model: {model_name}")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.7,
                    response_mime_type="application/json"
                )
            )
            return clean_json_response(response.text)
        except Exception as err:
            print(f"[WARN] Model {model_name} failed: {err}")
            last_error = err

    raise RuntimeError(f"All Gemini models failed. Last error: {last_error}")


def generate_offline_fallback(topic: str, duration_sec: int = 45) -> Dict[str, Any]:
    """Fallback generator when external AI APIs are offline or unconfigured."""
    return {
        "title": f"The Mind-Blowing Truth About {topic}",
        "hook": f"Did you know this crazy fact about {topic}?",
        "fullScript": f"Did you know this crazy fact about {topic}? Most people have no idea how it really works. Scientists discovered that {topic} is constantly shaping the world around us in ways we never imagined. Subscribe for more unbelievable daily facts!",
        "scenes": [
            {
                "id": 1,
                "text": f"Did you know this crazy fact about {topic}?",
                "searchKeyword": f"{topic} mysterious cinematic",
                "visualDescription": "Dramatic opening hook visual",
                "estimatedDuration": 4.0
            },
            {
                "id": 2,
                "text": "Most people have no idea how it really works.",
                "searchKeyword": "shocked person thinking",
                "visualDescription": "Curiosity builder",
                "estimatedDuration": 4.0
            },
            {
                "id": 3,
                "text": f"Scientists discovered that {topic} is constantly shaping the world around us in ways we never imagined.",
                "searchKeyword": "technology futuristic laboratory",
                "visualDescription": "Revealing core explanation",
                "estimatedDuration": 6.0
            },
            {
                "id": 4,
                "text": "Subscribe for more unbelievable daily facts!",
                "searchKeyword": "neon subscribe button glow",
                "visualDescription": "Call to action ending",
                "estimatedDuration": 3.0
            }
        ],
        "searchTerms": [topic, "mysterious nature", "cinematic technology"],
        "suggestedTags": ["#shorts", f"#{topic.replace(' ', '')}", "#facts", "#viral"]
    }


def generate_script(topic: str, duration_sec: int = 45, tone: str = "viral") -> Dict[str, Any]:
    """Master entry point for script generation with multi-provider fallback."""
    if GEMINI_API_KEY:
        try:
            return generate_with_gemini(topic, duration_sec, tone)
        except Exception as e:
            print(f"[WARN] Gemini generation failed: {e}. Trying fallback...")
            
    print("[INFO] Utilizing high-retention template fallback generator.")
    return generate_offline_fallback(topic, duration_sec)
