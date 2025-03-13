import openai
import requests
import os
from pydub import AudioSegment
from datetime import datetime

# Replace with your OpenAI API key
API_KEY = os.getenv("OPENAI_API_KEY")

# OpenAI TTS API endpoint
API_URL = "https://api.openai.com/v1/audio/speech"

# Map personas to OpenAI TTS voices
PERSONA_VOICES = {
    "Daddy": "onyx",           # Deep, authoritative male voice for a strict Italian father
    "Mommy": "nova",           # Bright, warm female voice for a nurturing yet firm mother
    "Babysitter": "shimmer",   # High-energy, slightly playful female voice for Gina
    "Bratty teen girl": "nova",# Youthful, sassy female voice for a rebellious teen
    "Strict girlfriend": "shimmer", # Confident, fiery female voice for Lara
    "Submissive Girlfriend": "alloy", # Soft, gentle voice for shy Sophie
    "Strict teacher": "echo"  # Firm, no-nonsense
}

def convert_text_to_audio(text, current_persona):
    MODEL = "tts-1-hd"  # or use "tts-1-hd" for higher quality
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }
    payload = {
        "model": MODEL,
        "input": text,
        "voice": PERSONA_VOICES[current_persona]  # Available voices: alloy, echo, fable, onyx, nova, shimmer
    }
    response = requests.post(API_URL, headers=headers, json=payload)
    if response.status_code == 200:
        audio_data = response.content
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        output_file = os.path.join("static", f"openai_output_{timestamp}.mp3")
        with open(output_file, "wb") as f:
            f.write(audio_data)
        return output_file
    else:
        raise Exception(f"Error: {response.status_code}, {response.text}")
