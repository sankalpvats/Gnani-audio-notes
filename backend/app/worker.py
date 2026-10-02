import asyncio
import logging
import os

from pathlib import Path

from dotenv import load_dotenv

from app.database import (
    claim_next_note,
    renew_note_claim,
    save_note_transcript,
    complete_note,
    fail_note,
    save_gnani_job_id
)
from app.storage import create_audio_signed_url, StorageError
from app.gnani import TranscriptionError
from app.gnani_batch import (
    create_batch_job,
    wait_for_batch_transcript,
)
from app.summarizer import summarize_transcript, SummaryError

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

logger = logging.getLogger("audio-worker")


class ClaimLost(Exception):
    pass


async def keep_claim_alive(note_id, token):
    while True:
        await asyncio.sleep(30)

        if not await renew_note_claim(note_id, token):
            raise ClaimLost(
                "The worker no longer owns this recording."
            )


async def process_note(note):
    note_id = str(note["id"])
    token = str(note["claim_token"])

    try:
        transcript = note["transcript"]

        # Only transcribe if a transcript is not already saved.
        if transcript is None:
            api_key = os.environ["GNANI_API_KEY"]
            gnani_job_id = note["gnani_job_id"]

            # Only create a job if its ID is not already saved.
            if gnani_job_id is None:
                audio_url = await create_audio_signed_url(
                    note["audio_path"]
                )

                gnani_job_id = await create_batch_job(
                    audio_url,
                    note["language_code"],
                    api_key,
                )

                saved = await save_gnani_job_id(
                    note_id,
                    token,
                    gnani_job_id,
                )

                if not saved:
                    raise ClaimLost(
                        "Could not save ownership of the Gnani job."
                    )

            # These lines must remain inside the transcript check.
            transcript = await wait_for_batch_transcript(
                gnani_job_id,
                api_key,
            )

            saved = await save_note_transcript(
                note_id,
                token,
                transcript,
            )

            if not saved:
                raise ClaimLost(
                    "Transcript update was rejected."
                )

        # Both new and previously saved transcripts reach this point.
        summary = None
        summary_error = None

        try:
            summary = await summarize_transcript(transcript)
        except SummaryError:
            summary_error = (
                "Transcript saved, but summarization failed."
            )

        saved = await complete_note(
            note_id,
            token,
            summary,
            summary_error,
        )

        if not saved:
            raise ClaimLost("Completion update was rejected.")

        logger.info("Finished %s", note_id)

    except ClaimLost:
        raise

    except (StorageError, TranscriptionError) as exc:
        if not await fail_note(note_id, token, str(exc)):
            raise ClaimLost(
                "Failure update was rejected."
            ) from exc

        logger.warning(
            "Failed %s (%s)",
            note_id,
            type(exc).__name__,
        )

    except Exception as exc:
        logger.error(
            "Processing error for %s (%s)",
            note_id,
            type(exc).__name__,
        )

        saved = await fail_note(
            note_id,
            token,
            "Processing failed because of a server error.",
        )

        if not saved:
            raise ClaimLost(
                "Failure update was rejected."
            ) from exc


async def run_claimed_note(note):
    processing = asyncio.create_task(process_note(note))

    heartbeat = asyncio.create_task(
        keep_claim_alive(
            str(note["id"]),
            str(note["claim_token"]),
        )
    )

    tasks = {processing, heartbeat}

    try:
        done, _ = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in done:
            await task

    finally:
        for task in tasks:
            task.cancel()

        await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )


async def main():
    required = (
        "DATABASE_URL",
        "SUPABASE_URL",
        "SUPABASE_SECRET_KEY",
        "GNANI_API_KEY",
        "GEMINI_API_KEY",
    )

    missing = [
        name
        for name in required
        if not os.getenv(name, "").strip()
    ]

    if missing:
        raise SystemExit(
            "Missing settings: " + ", ".join(missing)
        )

    logger.info(
        "Worker started. Waiting for queued recordings."
    )

    while True:
        try:
            note = await claim_next_note()

            if note is None:
                await asyncio.sleep(3)
                continue

            logger.info("Claimed %s", note["id"])

            await run_claimed_note(note)

        except ClaimLost:
            logger.warning(
                "Stopped processing after losing ownership."
            )

        except Exception as exc:
            logger.error(
                "Worker error (%s); retrying shortly.",
                type(exc).__name__,
            )
            await asyncio.sleep(5)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped.")