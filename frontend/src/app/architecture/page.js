import Link from "next/link";

export const metadata = {
  title: "Architecture | Gnani Audio Notes",
  description: "How uploads become transcripts and summaries.",
};

const sections = [
  {
    title: "Overview",
    text: `The app uses a Next.js frontend, a FastAPI backend, and a
    separate Python worker. Supabase stores audio files, while Neon
    PostgreSQL stores recording details and processing results.
    Gnani Batch provides speech transcription, and Gemini generates
    a summary from the transcript.`,
  },
  {
    title: "From upload to transcript",
    text: `The browser sends an audio file and its selected language to
    POST /uploads. FastAPI validates the upload, stores the audio in
    Supabase, and inserts a queued recording into PostgreSQL. It returns
    the recording ID with HTTP 202. The worker claims the recording,
    creates a temporary signed audio URL, and submits it to Gnani Batch.
    It saves the Gnani job ID, starts the job, and polls for completion.
    Once available, the transcript is saved before summarization begins.`,
  },
  {
    title: "Summaries, progress, and history",
    text: `After saving the transcript, the worker sends it to Gemini
    and saves the resulting summary. The frontend polls the recording
    endpoint to display queued, transcribing, summarizing, completed,
    or failed states. History is loaded from PostgreSQL, so recordings
    can be reopened after leaving the page. If summarization fails,
    the saved transcript remains available with an explanatory message.`,
  },
  {
    title: "Where the data lives",
    text: `Audio files live in Supabase Storage under generated object
    paths. PostgreSQL stores the original filename, language, storage
    path, processing status, timestamps, transcript, summary, and job
    ownership information. The database stores the audio path rather
    than the audio bytes. The worker generates a temporary signed URL
    so Gnani can fetch the file. Provider credentials stay in backend
    and worker environment variables.`,
  },
  {
    title: "Handling longer recordings",
    text: `Transcription uses Gnani Batch rather than keeping the upload
    request open until speech processing finishes. A recording of about
    two to three minutes has been tested successfully. The current
    implementation still limits uploads to 10 MiB and reads the accepted
    file into backend memory. It therefore does not yet meet unrestricted
    file-size support. Longer recordings within the upload limit can
    continue processing after the browser page is closed, provided the
    worker remains running.`,
  },
  {
    title: "Request work versus background work",
    text: `Validation, audio storage, and creation of the queued database
    row happen within the upload request. Transcription, provider polling,
    and summarization run in a separate worker process. PostgreSQL acts
    as the durable queue. Row locking prevents workers from claiming the
    same recording simultaneously. Each claim has a token and an expiring
    lease that the worker renews. Updates require a valid claim.
    Expired claims can be reclaimed after a worker interruption. Saved
    job IDs and transcripts allow processing to resume from recorded
    progress, although this is not an exactly-once processing guarantee.`,
  },
  {
    title: "What I would improve with more time",
    text: `I would add direct, resumable uploads to storage and increase
    the upload limit within provider constraints. I would also add
    transcript chunking for very long summaries, bounded retries for
    failed jobs, user authentication and private per-user history,
    rate limits, and better monitoring. The current history is shared
    rather than separated by user. For higher traffic, I would evaluate
    a dedicated job queue and additional worker processes.`,
  },
];

export default function ArchitecturePage() {
  return (
    <main className="min-h-screen bg-slate-50 px-6 py-12 text-slate-900">
      <div className="mx-auto max-w-3xl">
        <nav
          aria-label="Architecture navigation"
          className="mb-8 flex flex-wrap gap-6 text-sm font-medium"
        >
          <Link href="/" className="text-indigo-700 underline">
            Back to audio notes
          </Link>

          <a
            href="https://github.com/sankalpvats/Gnani-audio-notes"
            target="_blank"
            rel="noopener noreferrer"
            className="text-indigo-700 underline"
          >
            View GitHub repository
          </a>
        </nav>

        <h1 className="text-3xl font-bold">System architecture</h1>
        <p className="mt-3 text-slate-600">
          How an uploaded recording becomes a saved transcript and summary.
        </p>

        <div className="mt-8 space-y-6">
          {sections.map(({ title, text }) => (
            <section
              key={title}
              className="rounded-xl border border-slate-200 bg-white p-6"
            >
              <h2 className="text-xl font-semibold">{title}</h2>
              <p className="mt-3 leading-7 text-slate-700">{text}</p>
            </section>
          ))}
        </div>
      </div>
    </main>
  );
}