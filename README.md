# Gnani Audio Notes

Upload an audio recording, follow its processing progress, and return later to read its transcript and AI-generated summary.

Built with **Next.js**, **FastAPI**, **PostgreSQL**, **Supabase Storage**, **Gnani Batch ASR**, and **Gemini**. A separate Python worker performs transcription and summarization outside the upload request.

- **Repository:** [sankalpvats/Gnani-audio-notes](https://github.com/sankalpvats/Gnani-audio-notes)
- **Live application:** Deployment pending — add the frontend URL here after verification.
- **Architecture:** `/architecture` on the frontend; locally, [http://localhost:3000/architecture](http://localhost:3000/architecture).

> Current scope: recordings of approximately two to three minutes have been tested locally. Uploads are limited to **10 MiB**. Unlimited file sizes and arbitrary recording durations are not yet supported.

## Features

- Audio uploads with file-extension, size, and language validation.
- Background transcription through Gnani Batch.
- Concise English summaries generated from transcripts using Gemini.
- Visible processing stages and failure messages.
- Persistent upload history and saved recording details.
- Transcript preservation when summarization fails.
- Database-backed job claims, lease renewal, and recovery of interrupted jobs.
- An in-app architecture explanation with a repository link.

## Technology stack

| Component | Technology | Responsibility |
| --- | --- | --- |
| Frontend | Next.js, React, Tailwind CSS | Upload form, progress, history, and results |
| API | FastAPI, Uvicorn | Validate uploads, store audio, queue work, and serve saved notes |
| Database | Neon PostgreSQL, Psycopg | Recording metadata, transcripts, summaries, and durable job state |
| File storage | Supabase Storage | Audio objects and temporary signed download URLs |
| Worker | Python, asyncio | Claim recordings and coordinate background processing |
| Speech recognition | Gnani Batch ASR | Convert audio into text |
| Summarization | Gemini API | Produce a concise English overview and key points |

## How it works

1. The browser sends the audio and selected language to `POST /uploads`.
2. FastAPI validates the request and uploads the audio to Supabase under a generated object path.
3. The API inserts a recording with status `queued` into PostgreSQL and returns HTTP `202` with its ID.
4. The worker claims a recording and marks it `transcribing`. A temporary signed URL lets Gnani download the stored audio.
5. The worker creates a Gnani Batch job, saves its ID, starts it, and polls for completion.
6. The transcript is saved before the recording moves to `summarizing`.
7. Gemini summarizes the transcript. The worker saves the summary and marks the recording `completed`.
8. The frontend polls the recording endpoint and displays the latest status and saved results. History allows the recording to be reopened later.

### Request work and background work

| Within the upload request | In the separate worker |
| --- | --- |
| Validate the file and language | Claim queued or interrupted recordings |
| Upload audio to Supabase | Create/start/poll Gnani Batch jobs |
| Insert the queued database row | Save transcripts and request summaries |
| Return the recording ID | Save completion or failure state |

The HTTP response waits for storage and queue insertion, but not for transcription or summarization. Closing the browser after a confirmed upload does not cancel the worker. The worker must remain running independently of the API and frontend.

### Job ownership and recovery

PostgreSQL acts as the queue, avoiding a separate queue service for this project. Claims use `FOR UPDATE SKIP LOCKED`, a unique claim token, and a five-minute lease. The worker renews the lease every 30 seconds, and result updates require a matching, unexpired claim.

Expired processing claims can be reclaimed after an interruption. A saved Gnani job ID allows the worker to resume checking an existing provider job; a saved transcript allows it to resume at summarization. Each worker processes one recording at a time.

This is **not an exactly-once guarantee**: a crash between a provider request and its database update can leave external work unrecorded. Failed recordings are not automatically requeued. Transient errors during provider polling are retried within a bounded loop.

### Storage and data handling

- **Supabase:** audio bytes, stored under generated paths such as `audio/<uuid>.mp3`.
- **PostgreSQL:** filename, language, audio path, transcript, summary, timestamps, status, error information, claim state, and Gnani job ID.
- **Signed links:** temporary access for Gnani; the worker currently creates links valid for six hours.
- **Credentials:** server environment variables, never frontend public variables.

Audio is sent to Gnani for transcription, and transcript text is sent to Gemini for summarization. The current application has shared history and no user authentication. Use non-sensitive demonstration recordings.

## Audio support and limits

Accepted file extensions: `.wav`, `.mp3`, `.ogg`, `.flac`, `.aac`, and `.m4a`. The recording must also be readable by the transcription provider; an accepted extension alone does not guarantee a valid codec or audio file.

The Batch integration supports these language codes:

| Language | Code |
| --- | --- |
| English | `en-IN` |
| Hindi | `hi-IN` |

The API currently also accepts `gu-IN` and `pa-IN`, but the Batch worker rejects them. Use the eight codes above for the background workflow; aligning the API and UI validation is a remaining improvement.

Uploads are capped at **10 MiB (10,485,760 bytes)** and are read into backend memory before storage. Batch processing avoids keeping the upload request open during transcription, but it does not remove file-size, provider, or model-context limits. The six-hour polling deadline is a waiting limit, not a supported audio-duration guarantee.

## Source layout

| Path | Purpose |
| --- | --- |
| `backend/app/main.py` | FastAPI application, CORS, upload and note endpoints |
| `backend/app/database.py` | Persistence, queue claims, and guarded state updates |
| `backend/app/storage.py` | Supabase uploads and signed audio URLs |
| `backend/app/gnani_batch.py` | Gnani Batch creation, polling, and transcript retrieval |
| `backend/app/gnani.py` | Original synchronous transcription integration and shared error type |
| `backend/app/summarizer.py` | Gemini summary generation |
| `backend/app/worker.py` | Background processing loop and claim heartbeat |
| `backend/Schema.sql` | Database schema and migrations |
| `backend/requirements.txt` | Python dependencies |
| `frontend/src/app/page.js` | Upload, progress, history, and results interface |
| `frontend/src/app/architecture/page.js` | Architecture explanation |

## Local setup

### 1. Prerequisites and source

Use Python 3.11 and Node.js 22 as a setup baseline, with npm and Git available. You also need a Neon/PostgreSQL database, a Supabase project and storage bucket, a Gnani key with Batch access, and a Gemini API key with available quota.

```bash
git clone https://github.com/sankalpvats/Gnani-audio-notes.git
cd Gnani-audio-notes
```

Confirm that `frontend/package.json` and the frontend source files are present. The frontend must be committed as ordinary project files, not an unresolved nested repository reference.

### 2. Configure Python

From the project root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Create `backend/.env` with your own values:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_SECRET_KEY=YOUR_SERVER_SIDE_SUPABASE_KEY
SUPABASE_BUCKET=audio-files
GNANI_API_KEY=YOUR_GNANI_API_KEY
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
GEMINI_MODEL=gemini-2.5-flash-lite
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

`SUPABASE_BUCKET` must match an existing bucket exactly. If your bucket has another name, use that name rather than creating a second bucket unnecessarily. Keep the bucket private and provide the backend with credentials authorized to upload objects and create signed links. The application does not create the bucket automatically.

`GEMINI_MODEL` is optional and defaults to `gemini-2.5-flash-lite`. Never commit real `.env` files or expose server keys through `NEXT_PUBLIC_*` variables.

### 3. Initialize the database

Run the following SQL in the SQL editor for the database referenced by `DATABASE_URL`. It covers a new database and the earlier project schema without deleting recordings. Keep `backend/Schema.sql` synchronized with this block.

```sql
CREATE TABLE IF NOT EXISTS audio_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename TEXT NOT NULL,
    language_code TEXT NOT NULL,
    transcript TEXT,
    summary TEXT,
    audio_path TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE audio_notes
    ADD COLUMN IF NOT EXISTS audio_path TEXT,
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'completed',
    ADD COLUMN IF NOT EXISTS error_message TEXT,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS claim_token UUID,
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS gnani_job_id TEXT;

ALTER TABLE audio_notes
    ALTER COLUMN transcript DROP NOT NULL;
```

The `completed` default preserves the meaning of older saved notes. The upload endpoint explicitly inserts new recordings as `queued`. The API does not automatically apply migrations at startup.

### 4. Start the API

In a terminal inside `backend`, with its virtual environment active:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Health: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- Interactive API documentation: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 5. Start the worker

In a second terminal, from the project root:

```bash
cd backend
source .venv/bin/activate
python -m app.worker
```

Keep this process running. Without it, successful uploads remain queued.

### 6. Start the frontend

Create `frontend/.env.local`:

```dotenv
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

In a third terminal, from the project root:

```bash
cd frontend
npm ci
npm run dev
```

`npm ci` requires the committed `package-lock.json`; use `npm install` if initializing dependencies without a lockfile, then commit the generated lockfile.

Open [http://localhost:3000](http://localhost:3000). Upload a supported recording, watch its status, and reopen it from history after completion.

## API reference

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Process liveness; does not verify external dependencies |
| `POST` | `/uploads` | Store audio and queue background work; returns HTTP `202` |
| `GET` | `/notes` | Return the latest 50 recording summaries, newest first |
| `GET` | `/notes/{note_id}` | Return a saved recording, status, transcript, and summary |
| `POST` | `/transcribe` | Legacy synchronous short-clip endpoint; not the main background flow |

Upload fields are multipart form data: `audio_file` and `language_code` (default `en-IN`).

```bash
curl -X POST http://127.0.0.1:8000/uploads \
  -F "audio_file=@/absolute/path/to/recording.mp3" \
  -F "language_code=en-IN"
```

Example accepted response:

```json
{
  "id": "00000000-0000-0000-0000-000000000001",
  "status": "queued",
  "message": "Audio stored and queued for processing."
}
```

Use the actual returned ID with `GET /notes/{note_id}`.

| Status | Meaning |
| --- | --- |
| `queued` | Audio saved and waiting for a worker |
| `transcribing` | Worker processing transcription |
| `summarizing` | Transcript saved; summary processing underway |
| `completed` | Processing finished; inspect `summary` and `error_message` for partial success |
| `failed` | Processing failed; inspect `error_message` |

## Deployment configuration

Deployment requires three processes plus the existing database and storage services. A frontend deployment alone does not run the Python API or worker.

| Service | Root directory | Install/build | Start |
| --- | --- | --- | --- |
| Next.js frontend | `frontend` | `npm ci` then `npm run build` | `npm run start` when self-hosting; managed Next.js hosting handles serving |
| FastAPI web service | `backend` | `pip install -r requirements.txt` | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Persistent Python worker | `backend` | `pip install -r requirements.txt` | `python -m app.worker` |

The planned frontend host is Vercel. The API needs a Python web service, and the worker needs a host that supports a continuously running background process. Choose and configure the backend host separately; worker hosting is not assumed to be free.

Deployment steps:

1. Push both frontend and backend source files, including the architecture page and complete database schema.
2. Apply the schema to the intended PostgreSQL database and verify the Supabase bucket exists.
3. Configure the API and worker with the backend environment variables. Both must use the same database and storage settings.
4. Start both backend services. Use `/health` as the API liveness endpoint and check worker startup logs separately.
5. Set frontend `NEXT_PUBLIC_API_URL` to the public HTTPS API URL **before building** the frontend.
6. Set backend `ALLOWED_ORIGINS` to the exact frontend origin, such as `https://your-app.example`, without a path. Multiple origins are comma-separated.
7. Deploy the frontend and verify an upload reaches a saved transcript and summary. Test history reopening and `/architecture` from the public URL.
8. Replace the deployment-pending line at the top of this README with the verified live URL.

Changing `NEXT_PUBLIC_API_URL` requires a new frontend build. An API health response alone does not prove the worker, database, storage, or provider integrations are working.

## Verification and troubleshooting

A two-to-three-minute recording has been tested successfully during local development. Hosted end-to-end verification remains pending; this README does not claim comprehensive automated test coverage.

Useful manual checks include a valid upload, empty/oversized file rejection, history reopening, visible provider failures, and transcript preservation when summarization fails. Use non-sensitive audio because history is shared.

| Symptom | Check |
| --- | --- |
| Recordings stay queued | Worker is running, all required variables exist, and API/worker use the same database |
| Worker repeatedly reports a database error | Schema contains `gnani_job_id` and claim columns; database credentials and network access work |
| Storage reports “Bucket not found” | `SUPABASE_BUCKET` matches a bucket in the configured Supabase project |
| Browser cannot reach the API | Public API URL, HTTPS, CORS origin, and frontend build-time configuration |
| Upload rejected with HTTP `413` | File exceeds the 10 MiB application cap or an upstream host limit |
| Gnani cannot start a job | Batch access, credits, audio format, and signed URL accessibility/expiry |
| Transcript exists but no summary | Gemini key, model access, quota, or request failure; inspect the saved error |
| GitHub does not show frontend files | Frontend was committed as a nested repository instead of regular files |

After an ambiguous upload/network failure, check history before uploading again: storage or queue insertion may already have succeeded.

## Known limitations and next improvements

- **Upload size:** 10 MiB cap and backend memory buffering; add direct resumable uploads to storage.
- **Very long transcripts:** no chunked summarization; add chunking and a final synthesis step.
- **User isolation:** no authentication, private per-user history, or ownership checks yet.
- **Recovery:** failed jobs are not automatically requeued; add bounded retries, backoff, and a retry interface.
- **Consistency:** provider creation and database updates are not atomic; improve idempotency and orphan-job handling.
- **Storage cleanup:** a successful storage upload followed by a database failure can leave an orphaned object.
- **Validation:** align API/UI languages with the Batch integration and strengthen file-content validation.
- **Operations:** add rate limits, dependency-aware health checks, metrics, and structured error monitoring.
- **Scaling:** add queue indexes and pagination; evaluate a dedicated queue and worker concurrency under load.

These are future improvements, not claims about functionality already implemented.

## Author

[Sankalp Vats](https://github.com/sankalpvats)
