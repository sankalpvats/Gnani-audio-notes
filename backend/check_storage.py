import asyncio
import io
import wave
from pathlib import Path

from dotenv import load_dotenv
from app.storage import upload_audio, StorageError

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

buffer = io.BytesIO()

with wave.open(buffer, "wb") as audio:
    audio.setnchannels(1)
    audio.setsampwidth(2)
    audio.setframerate(16000)
    audio.writeframes(b"\x00\x00" * 16000)

try:
    path = asyncio.run(
        upload_audio(buffer.getvalue(), "storage-test.wav", "audio/wav")
    )
    print("Uploaded successfully:", path)
except StorageError as exc:
    print("Storage failed:", exc)