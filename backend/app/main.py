"""Day 1: receive a short audio file and return its real Gnani transcript."""

import os
import psycopg
from app.database import save_note
from pathlib import Path
from typing import Annotated
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from app.gnani import TranscriptionError, transcribe_audio
from app.database import save_note, update_note_summary
from app.summarizer import summarize_transcript, SummaryError
from uuid import UUID
from app.storage import upload_audio, StorageError
from app.database import list_notes, get_note
from app.database import create_queued_note
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


app = FastAPI(title="Audio Notes — Day 1", description="Local short-clip API proof. Use a spoken clip below 60 seconds.")
allowed_origins = [
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
# This is a local learning milestone, not the final large-file upload route.
MAX_BYTES = 10 * 1024 * 1024
EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".aac", ".m4a"}
LANGUAGES = {"en-IN", "hi-IN", "bn-IN", "gu-IN", "kn-IN", "ml-IN", "mr-IN", "pa-IN", "ta-IN", "te-IN"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/transcribe")
async def transcribe(
    audio_file: Annotated[UploadFile, File(description="Spoken audio shorter than 60 seconds")],
    language_code: Annotated[str, Form()] = "en-IN",
):
    try:
        if language_code not in LANGUAGES:
            raise HTTPException(400, "Unsupported language code. Try en-IN or hi-IN.")
        filename = Path(audio_file.filename or "audio").name
        if Path(filename).suffix.lower() not in EXTENSIONS:
            raise HTTPException(400, "Use WAV, MP3, OGG, FLAC, AAC, or M4A.")
        # Reading one byte beyond the limit lets us detect oversized uploads.
        audio = await audio_file.read(MAX_BYTES + 1)
        if not audio:
            raise HTTPException(400, "The audio file is empty.")
        if len(audio) > MAX_BYTES:
            raise HTTPException(413, "This Day 1 test accepts up to 10 MiB. Use a short clip.")
        key = os.getenv("GNANI_API_KEY", "").strip()
        if not key or key == "replace_with_your_key":
            raise HTTPException(503, "Set GNANI_API_KEY in backend/.env, then restart the server.")
        result = await transcribe_audio(audio, filename, language_code, key)

        try:
            audio_path = await upload_audio(
                audio=audio,
                filename=filename,
                content_type=audio_file.content_type or "application/octet-stream",
            )
        except StorageError as exc:
            raise HTTPException(
                status_code=503,
                detail="Transcription succeeded, but storing the audio failed.",
            ) from exc

        try:
            note_id = await save_note(
                filename=filename,
                language_code=language_code,
                transcript=result["transcript"],
                audio_path=audio_path,
            )
        except psycopg.Error as exc: 
            raise HTTPException(
                status_code=503,
                detail="Audio uploaded, but saving the note failed.",
            ) from exc
        summary = None
        summary_error = None

        try:
            summary = await summarize_transcript(result["transcript"])
            await update_note_summary(note_id, summary)
        except SummaryError as exc:
            summary_error = str(exc)
        except psycopg.Error:
            summary_error = "Summary generated, but saving it failed."

        return {
            **result,
            "id": note_id,
            "summary": summary,
            "summary_error": summary_error,
        }
    except TranscriptionError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    finally:
        await audio_file.close()
@app.get("/notes")
async def notes_history():
    try:
        return await list_notes()
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Could not load upload history.",
        ) from exc

@app.get("/notes/{note_id}")
async def note_details(note_id: UUID):
    try:
        note = await get_note(str(note_id))
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Could not load this recording.",
        ) from exc

    if note is None:
        raise HTTPException(status_code=404, detail="Recording not found.")

    return note
@app.post("/uploads", status_code=202)
async def queue_upload(
    audio_file: Annotated[UploadFile, File()],
    language_code: Annotated[str, Form()] = "en-IN",
):
    try:
        if language_code not in LANGUAGES:
            raise HTTPException(
                status_code=400,
                detail="Unsupported language code.",
            )

        filename = Path(audio_file.filename or "audio").name

        if Path(filename).suffix.lower() not in EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail="Use WAV, MP3, OGG, FLAC, AAC, or M4A.",
            )

        audio = await audio_file.read(MAX_BYTES + 1)

        if not audio:
            raise HTTPException(
                status_code=400,
                detail="The audio file is empty.",
            )

        if len(audio) > MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail="This version accepts files up to 10 MiB.",
            )

        try:
            audio_path = await upload_audio(
                audio=audio,
                filename=filename,
                content_type=(
                    audio_file.content_type
                    or "application/octet-stream"
                ),
            )
        except StorageError as exc:
            raise HTTPException(
                status_code=503,
                detail="Could not store the audio. Please try again.",
            ) from exc

        try:
            note_id = await create_queued_note(
                filename=filename,
                language_code=language_code,
                audio_path=audio_path,
            )
        except psycopg.Error as exc:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Audio was stored, but queueing could not be "
                    "confirmed. Check upload history before retrying."
                ),
            ) from exc

        return {
            "id": note_id,
            "status": "queued",
            "message": "Audio stored and queued for processing.",
        }

    finally:
        await audio_file.close()