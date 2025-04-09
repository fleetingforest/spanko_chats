import os
import httpx

# OpenAI API config
API_KEY = os.getenv("OPENAI_API_KEY")
API_URL = "https://api.openai.com/v1/audio/speech"

# Voice mapping
PERSONA_VOICES = {
    "Daddy": "onyx",
    "Mommy": "nova",
    "Babysitter": "shimmer",
    "Bratty teen girl": "nova",
    "Strict girlfriend": "shimmer",
    "Submissive Girlfriend": "alloy",
    "Strict teacher": "echo",
    "Cute little girl": "sage",
    "Mischevious student": "fable",
    "Cute little boy": "alloy"
}

def convert_text_to_audio(text, current_persona):
    model = "gpt-4o-mini-tts"
    voice = PERSONA_VOICES.get(current_persona, "nova")  # fallback to nova if unknown

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "input": text,
        "voice": voice,
        "response_format": "opus",  
        "speed": 1.0  # default speed, can be adjusted between 0.25 and 4.0
    }

    try:
        # Return the raw streaming response object
        return httpx.stream("POST", API_URL, headers=headers, json=payload)
    except Exception as e:
        print(f"Error in TTS conversion: {str(e)}")
        return None
