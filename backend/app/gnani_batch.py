import asyncio
import time
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from app.gnani import TranscriptionError


BASE_URL = "https://api.vachana.ai/stt/v3/batch/jobs"

LANGUAGES = {
    "en-IN", "hi-IN", "bn-IN", "kn-IN",
    "ml-IN", "mr-IN", "ta-IN", "te-IN",
}


class BatchError(TranscriptionError):
    pass


class RetryableBatchError(BatchError):
    pass


def job_url(job_id):
    try:
        return f"{BASE_URL}/{UUID(str(job_id))}"
    except ValueError as exc:
        raise BatchError("Invalid Gnani job ID.") from exc


def require_https(url):
    if not isinstance(url, str):
        raise BatchError("A download link is missing.")

    parsed = urlsplit(url)

    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise BatchError("An invalid download link was returned.")

    return url


async def request_json(
    client,
    method,
    url,
    *,
    api_key=None,
    allow_started=False,
    **kwargs,
):
    headers = {"X-API-Key-ID": api_key} if api_key else {}

    try:
        response = await client.request(
            method,
            url,
            headers=headers,
            **kwargs,
        )
        if not response.is_success:
            target = "Gnani API" if api_key else "transcript download"
            print(
        f"[batch] {target}: {method} returned HTTP {response.status_code}",
        flush=True,
    )
    except (httpx.TimeoutException, httpx.RequestError) as exc:
            print(
            f"[batch] Request failed: {type(exc).__name__}",
            flush=True,
                )
            raise RetryableBatchError(
            "Could not reach Gnani or its transcript storage."
        ) from exc

    # The job may already have started before a worker restarted.
    # The next status check determines its actual state.
    if allow_started and response.status_code == 409:
        return {}

    if response.status_code == 429 or response.status_code >= 500:
        raise RetryableBatchError(
            "Gnani is temporarily unavailable or rate limiting requests."
        )

    if response.status_code in (401, 403):
        if api_key:
            raise BatchError(
                "Check your Gnani API key, Batch access, and account credits.",
                503,
            )

        raise RetryableBatchError(
            "The transcript download link could not be used."
        )

    if not response.is_success:
        raise BatchError(
            f"Gnani Batch request failed (HTTP {response.status_code})."
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise BatchError("Gnani returned unreadable JSON.") from exc

    if not isinstance(data, dict):
        raise BatchError("Gnani returned an unexpected response.")

    return data


async def create_batch_job(
    audio_url: str,
    language: str,
    api_key: str,
) -> str:
    if not api_key.strip():
        raise BatchError("GNANI_API_KEY is missing.", 503)

    if language not in LANGUAGES:
        raise BatchError(
            "This language is not supported by Gnani Batch.",
            400,
        )

    payload = {
        "config": {
            "model": "gnani-prisma-v2.5",
            "language_code": language,
            "mode": "transcribe",
            "with_diarization": False,
            "is_multi_channel": False,
        },
        "source": {
            "type": "cloud_storage",
            "auth": {"mode": "public"},
            "paths": [require_https(audio_url)],
        },
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        data = await request_json(
            client,
            "POST",
            BASE_URL,
            api_key=api_key,
            json=payload,
        )

    job_id = data.get("job_id")

    if not isinstance(job_id, str):
        raise BatchError("Gnani did not return a job ID.")

    job_url(job_id)
    return job_id


async def download_transcript(client, url, api_key):
    files = await request_json(
        client,
        "GET",
        f"{url}/files",
        api_key=api_key,
    )

    items = files.get("data")

    if not isinstance(items, list) or len(items) != 1:
        raise BatchError("Expected one audio result from Gnani.")

    if files.get("pagination", {}).get("has_more"):
        raise BatchError("Gnani returned more than one audio result.")

    item = items[0]

    if (
        not isinstance(item, dict)
        or item.get("status") != "COMPLETED"
    ):
        raise BatchError("Gnani did not complete this audio file.")

    transcript_url = require_https(item.get("transcript_url"))

    # This signed URL needs no Gnani API key.
    data = await request_json(
        client,
        "GET",
        transcript_url,
        follow_redirects=True,
    )

    transcript = data.get("full_transcript")

    if not isinstance(transcript, str) or not transcript.strip():
        raise BatchError("Gnani returned no speech transcript.", 422)

    return transcript.strip()


async def wait_for_batch_transcript(
    job_id: str,
    api_key: str,
) -> str:
    url = job_url(job_id)

    # Application waiting limit, separate from audio duration.
    deadline = time.monotonic() + 6 * 60 * 60
    consecutive_errors = 0

    async with httpx.AsyncClient(timeout=60.0) as client:
        while time.monotonic() < deadline:
            try:
                data = await request_json(
                    client,
                    "GET",
                    url,
                    api_key=api_key,
                )

                status = data.get("status")

                if status == "CREATED":
                    await request_json(
                        client,
                        "POST",
                        f"{url}/start",
                        api_key=api_key,
                        allow_started=True,
                    )

                elif status == "COMPLETED":
                    return await download_transcript(
                        client,
                        url,
                        api_key,
                    )

                elif status == "START_FAILED":
                    raise BatchError(
                        "Gnani could not start this job. Check whether "
                        "the audio link is accessible and unexpired."
                    )

                elif status in {
                    "FAILED",
                    "PARTIAL_FAILURE",
                    "CANCELLED",
                }:
                    raise BatchError(
                        "Gnani could not complete this recording "
                        f"(status: {status})."
                    )

                elif status not in {
                    "STARTING",
                    "QUEUED",
                    "IN_PROGRESS",
                    "CANCELLING",
                }:
                    raise BatchError(
                        "Gnani returned an unknown job status."
                    )

                consecutive_errors = 0

            except RetryableBatchError:
                consecutive_errors += 1

                if consecutive_errors >= 6:
                    raise BatchError(
                        "Gnani remained unavailable after repeated checks. "
                        "The provider job may still be running."
                    )

            await asyncio.sleep(10)

    raise BatchError(
        "Stopped waiting after six hours. "
        "The Gnani job may still be running.",
        504,
    )