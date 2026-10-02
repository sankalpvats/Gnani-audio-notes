# Audio Notes: Day 1 starter

Goal: understand a backend route and get one real Gnani transcript from a 20–30 second spoken audio clip.

This is a local learning milestone, not a complete assessment submission. It has no mock-success mode in the application. The frontend, Postgres, bucket, durable worker, summary generation, upload history and deployment are still to be implemented.

## 1. Try Gnani first

Create your account using https://gnani.ai and try a recording at https://app.gnani.ai/voice/speech-to-text as requested by the assignment. Obtain an API key from the provider dashboard. Do not paste it into chat or commit it to Git.

Record 20–30 seconds of clear English or Hindi. Export as WAV, MP3, OGG, FLAC, AAC or M4A. English uses en-IN; Hindi uses hi-IN.

## 2. Run the backend on macOS

Install Python 3.10 or newer if needed. Extract this folder, open it in VS Code, and open Terminal > New Terminal. From the gnani-audio-notes folder:

```bash
cd backend
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Open backend/.env in your editor and replace the placeholder with your actual key. Keep the variable name GNANI_API_KEY unchanged. Then run:

```bash
python -m uvicorn app.main:app --reload
```

Keep this terminal open. Visit http://127.0.0.1:8000/docs in your browser.

1. Expand GET /health, choose Try it out, then Execute. Expect status: ok.
2. Expand POST /transcribe and choose Try it out.
3. Choose your audio file. Enter en-IN or hi-IN in language_code.
4. Choose Execute. The request stays open during this short-clip test.
5. A successful response contains transcript and request_id. Read the actual text and compare it with your recording.

The app uses a 10 MiB local test limit. The provider's REST endpoint accepts at most 60 seconds; duration and audio validity are checked by the provider at this stage. A .wav filename does not prove the file is valid audio. Do not deploy this unauthenticated local test endpoint publicly.

## 3. Understand the code in this order

1. app/main.py: FastAPI creates the server application. @app.get and @app.post register routes, similar to app.get and app.post in Express. /health proves the server responds. It does not verify Gnani credentials.
2. UploadFile and Form: the browser sends a multipart request containing the file and a language field. FastAPI parses those values into function arguments.
3. Input checks: reject missing content, unsupported filename extensions, unsupported languages and oversized local test files before spending API credits.
4. .env: python-dotenv loads configuration into the server environment. os.getenv retrieves the key. The browser never needs that key.
5. app/gnani.py: httpx sends a second HTTP request, this time from our backend to Gnani. The key goes in a header; audio and language go in multipart fields.
6. async/await: the handler can yield while waiting on network I/O. It is NOT a durable background job; the original browser request is still waiting.
7. Responses: successful provider JSON becomes a transcript response. Provider errors become readable HTTP errors. The app does not return raw provider errors or log secrets/audio.
8. finally: close the uploaded file whether transcription succeeds or fails.

Requirements explained: fastapi defines the API; uvicorn runs its server; httpx makes outgoing requests; python-multipart parses uploads; python-dotenv loads the local key.

## 4. Offline tests

From backend with the virtual environment active:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests simulate provider replies and cover validation, missing credentials, request fields, provider failures and timeouts. They do not call Gnani or demonstrate actual transcription quality. The real audio test above is still required.

## 5. The longer-audio design

Current provider documentation distinguishes REST (up to 60 seconds) and Batch (long recordings). Batch requires create, start, poll, and retrieve transcripts. For the final platform, our durable worker will coordinate Batch and the LLM, while Postgres stores status and results. The browser will poll our backend for progress. Gnani Batch does not replace our own durable coordination and storage.

Batch documentation currently states a four-hour duration cap per file and a 10 MB per-file direct-upload cap. Its cloud-storage path supports larger byte sizes with download/time limits. We must verify account access and the supported storage integration before selecting that path; longer files still need splitting. Avoid claiming unlimited uploads.

References checked on 30 September 2026:
- https://docs.gnani.ai/api/STT/speech-to-text
- https://docs.gnani.ai/api/STTBatch/Introduction
- https://fastapi.tiangolo.com/tutorial/request-forms-and-files/

## 6. Questions you should be able to answer

- Why does the frontend call our backend rather than expose the Gnani key?
- What is the difference between /health and /transcribe?
- Why is this request multipart instead of JSON?
- What does await do? Why is it different from a background worker?
- Where does the file go, and is it saved permanently? (Not in this milestone.)
- What happens when the provider times out or returns 403?
- Why will the final platform use Batch for a two-minute recording?

Day 1 is complete only after a real clip returns a transcript, you compare it with the speech, and you can trace the request through both Python modules. Account/key setup and that live check must happen on your machine unless a secure execution environment is configured.
