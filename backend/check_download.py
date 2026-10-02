import argparse
import asyncio
from pathlib import Path

from dotenv import load_dotenv

from app.storage import download_audio, StorageError


async def check(audio_path: str):
    audio = await download_audio(audio_path)
    print(f"Downloaded successfully: {len(audio):,} bytes")


if __name__ == "__main__":
    load_dotenv(Path(__file__).resolve().parent / ".env")

    parser = argparse.ArgumentParser()
    parser.add_argument("audio_path")
    args = parser.parse_args()

    try:
        asyncio.run(check(args.audio_path))
    except StorageError as exc:
        raise SystemExit(f"Download failed: {exc}")