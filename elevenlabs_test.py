import requests
import json
import os
from pydub import AudioSegment
from pydub.playback import play

# Replace with your ElevenLabs API key
API_KEY = "sk_ad204da2c233a7a9b774433ebcdb576793364e5edca0f52f"

# ElevenLabs API URL
API_URL = "https://api.elevenlabs.io/v1/text-to-speech"

# Voice ID (choose from ElevenLabs dashboard, e.g., "Rachel" or "Domi")
VOICE_ID = "cgSgspJ2msm6clMCkdW9"

# Text to convert
TEXT = "Hello! This is a test of the ElevenLabs API."

# Request payload
headers = {
    "xi-api-key": API_KEY,
    "Content-Type": "application/json"
}

payload = {
    "text": TEXT,
    "voice_id": VOICE_ID,
    "model_id": "eleven_multilingual_v2",
    "settings": {
        "stability": 0.5,
        "similarity_boost": 0.5
    }
}

# Make API request
response = requests.post(f"{API_URL}/{VOICE_ID}", headers=headers, json=payload)

if response.status_code == 200:
    audio_data = response.content
    output_file = "output.mp3"
    
    # Save audio
    with open(output_file, "wb") as f:
        f.write(audio_data)
    
    print(f"Audio saved as {output_file}")
    
    # Play audio (optional)
    sound = AudioSegment.from_mp3(output_file)
    play(sound)
else:
    print("Error:", response.status_code, response.text)
