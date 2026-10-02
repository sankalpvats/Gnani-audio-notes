import asyncio
import os
from pathlib import Path
from uuid import uuid4

from supabase import create_client


class StorageError(Exception):
    pass


def _upload_audio(audio: bytes, filename: str, content_type: str) -> str:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SECRET_KEY", "").strip()
    bucket = os.getenv("SUPABASE_BUCKET", "audio-files").strip()

    if not url or not key or not bucket:
        raise StorageError("Supabase settings are missing from backend/.env.")

    extension = Path(filename).suffix.lower()
    object_path = f"audio/{uuid4().hex}{extension}"

    try:
        client = create_client(url, key)
        client.storage.from_(bucket).upload(
            path=object_path,
            file=audio,
            file_options={
                "content-type": content_type,
                "upsert": "false",
            },
        )
    except Exception as exc:
        detail = str(exc).replace(key, "[REDACTED]")
        raise StorageError(
            f"{type(exc).__name__}: {detail}"
        ) from exc

    return object_path


async def upload_audio(
    audio: bytes,
    filename: str,
    content_type: str = "application/octet-stream",
) -> str:
    return await asyncio.to_thread(
        _upload_audio, audio, filename, content_type
    )
def _download_audio(audio_path: str) -> bytes:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SECRET_KEY", "").strip()
    bucket = os.getenv("SUPABASE_BUCKET", "audio-files").strip()

    if not url or not key or not bucket:
        raise StorageError(
            "Supabase settings are missing from backend/.env."
        )

    if not audio_path:
        raise StorageError("This recording has no saved audio path.")

    try:
        client = create_client(url, key)
        audio = client.storage.from_(bucket).download(audio_path)
    except Exception as exc:
        raise StorageError(
            "Could not download the audio. Check the storage "
            "settings and whether the file still exists."
        ) from exc

    if not isinstance(audio, bytes) or not audio:
        raise StorageError("The stored audio file is empty or unreadable.")

    return audio


async def download_audio(audio_path: str) -> bytes:
    return await asyncio.to_thread(_download_audio, audio_path)
def _create_audio_signed_url(audio_path: str) -> str:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SECRET_KEY", "").strip()
    bucket = os.getenv("SUPABASE_BUCKET", "audio-files").strip()

    if not url or not key or not bucket:
        raise StorageError("Supabase settings are missing.")

    if not audio_path:
        raise StorageError("This recording has no audio path.")

    try:
        client = create_client(url, key)

        result = client.storage.from_(bucket).create_signed_url(
            audio_path,
            6 * 60 * 60,
        )

        signed_url = result["signedURL"]

    except Exception as exc:
        raise StorageError(
            "Could not create a temporary audio download link."
        ) from exc

    if (
        not isinstance(signed_url, str)
        or not signed_url.startswith("https://")
    ):
        raise StorageError("Supabase returned an invalid audio link.")

    return signed_url


async def create_audio_signed_url(audio_path: str) -> str:
    return await asyncio.to_thread(
        _create_audio_signed_url,
        audio_path,
    )