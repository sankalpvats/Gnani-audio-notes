"""The only module that knows how to talk to Gnani's short-clip API."""
import httpx #supports both standard synchronous requests and native asynchronous operations
URL = "https://api.vachana.ai/stt/v3"
class TranscriptionError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code
async def transcribe_audio(audio: bytes, filename: str, language: str, api_key: str) -> dict:
    # Let httpx construct the multipart Content-Type and its boundary.
    # A fresh client also ensures the API key is used only for this provider call.
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                URL,
                headers={"X-API-Key-ID": api_key},
                data={"language_code": language},
                files={"audio_file": (filename, audio, "application/octet-stream")},
            )
    except httpx.TimeoutException as exc:
        raise TranscriptionError("Gnani timed out. Try a shorter clip or retry later.", 504) from exc
    except httpx.RequestError as exc:
        raise TranscriptionError("Cannot reach Gnani. Check connectivity and try again.", 502) from exc

    if response.status_code in (401, 403):
        raise TranscriptionError("Check the backend Gnani API key, account access, and credits.", 503)
    if response.status_code == 429:
        raise TranscriptionError("Gnani is rate limiting requests. Wait before trying again.", 429)
    if response.status_code in (400, 413, 415, 422):
        raise TranscriptionError("Gnani rejected the audio. Check its format and keep this test below 60 seconds.", 400)
    if not response.is_success:
        raise TranscriptionError("Gnani returned a service error. Try again later.")

    try:
        result = response.json()
    except ValueError as exc:
        raise TranscriptionError("Gnani returned an unreadable response.") from exc
    if not isinstance(result, dict) or result.get("success") is not True:
        raise TranscriptionError("Gnani did not report a successful transcription.")
    transcript = result.get("transcript")
    if not isinstance(transcript, str):
        raise TranscriptionError("Gnani's response did not contain a valid transcript.")
    if not transcript.strip():
        raise TranscriptionError("No speech was transcribed. Try a clear spoken recording.", 422)
    return {"transcript": transcript, "request_id": result.get("request_id")}
