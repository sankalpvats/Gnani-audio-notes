"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
const API_URL = (
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

const STATUS_LABELS = {
  queued: "Waiting for a worker",
  transcribing: "Transcribing audio",
  summarizing: "Generating summary",
  completed: "Processing complete",
  failed: "Processing failed",
};

// This timeout limits one HTTP request, not the background job.
async function requestJSON(path, options = {}, timeoutMs = 15000) {
  const controller = new AbortController();
  const parentSignal = options.signal;
  const abort = () => controller.abort();

  parentSignal?.addEventListener("abort", abort, { once: true });

  if (parentSignal?.aborted) {
    controller.abort();
  }

  const timeout = setTimeout(abort, timeoutMs);

  try {
    const response = await fetch(`${API_URL}${path}`, {
      ...options,
      signal: controller.signal,
    });

    const data = await response.json().catch(() => null);

    if (controller.signal.aborted) {
      throw new DOMException("Request aborted", "AbortError");
    }

    if (!response.ok) {
      const error = new Error(
        typeof data?.detail === "string"
          ? data.detail
          : `Request failed (HTTP ${response.status}).`
      );

      error.status = response.status;
      throw error;
    }

    if (data === null) {
      throw new Error("The server returned invalid data.");
    }

    return data;
  } catch (error) {
    if (controller.signal.aborted && !parentSignal?.aborted) {
      throw new Error("The server took too long to respond.");
    }

    if (error instanceof TypeError) {
      throw new Error(
        "Cannot reach the backend. Check that it is running."
      );
    }

    throw error;
  } finally {
    clearTimeout(timeout);
    parentSignal?.removeEventListener("abort", abort);
  }
}

export default function Home() {
  const [file, setFile] = useState(null);
  const [language, setLanguage] = useState("en-IN");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");

  const [notes, setNotes] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState("");

  const [currentNote, setCurrentNote] = useState(null);
  const [watch, setWatch] = useState(null);
  const [pollError, setPollError] = useState("");

  const historyRequest = useRef(null);
  const uploadRequest = useRef(null);

  const loadHistory = useCallback(async () => {
    historyRequest.current?.abort();

    const controller = new AbortController();
    historyRequest.current = controller;

    setHistoryLoading(true);
    setHistoryError("");

    try {
      const data = await requestJSON("/notes", {
        cache: "no-store",
        signal: controller.signal,
      });

      if (!Array.isArray(data)) {
        throw new Error("Invalid upload history.");
      }

      if (!controller.signal.aborted) {
        setNotes(data);
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        setHistoryError(err.message);
      }
    } finally {
      if (!controller.signal.aborted) {
        setHistoryLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadHistory();

    return () => {
      historyRequest.current?.abort();
      uploadRequest.current?.abort();
    };
  }, [loadHistory]);

  // Check the selected recording until it completes or fails.
  useEffect(() => {
    if (!watch) return;

    const controller = new AbortController();
    let timer;

    async function poll() {
      try {
        const note = await requestJSON(
          `/notes/${encodeURIComponent(watch.id)}`,
          {
            cache: "no-store",
            signal: controller.signal,
          }
        );

        if (controller.signal.aborted) return;

        if (!note || !Object.hasOwn(STATUS_LABELS, note.status)) {
          throw new Error(
            "The server returned an unknown processing status."
          );
        }

        setCurrentNote(note);
        setPollError("");

        setNotes((previous) =>
          previous.map((item) =>
            item.id === note.id
              ? { ...item, status: note.status }
              : item
          )
        );

        if (
          note.status === "completed" ||
          note.status === "failed"
        ) {
          void loadHistory();
          return;
        }

        timer = setTimeout(poll, 2000);
      } catch (err) {
        if (controller.signal.aborted) return;

        if (err.status === 404) {
          setPollError(
            "Recording not found. Refresh history to check available recordings."
          );
          return;
        }

        setPollError(
          `${err.message} Checking again shortly; do not upload again.`
        );

        timer = setTimeout(poll, 5000);
      }
    }

    void poll();

    // Stop checking the old recording when switching or leaving.
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [watch, loadHistory]);

  function openNote(note) {
    if (uploading) return;

    setError("");
    setPollError("");
    setCurrentNote(note);

    // A new object also lets us reopen the same recording.
    setWatch({ id: note.id });
  }

  async function handleSubmit(event) {
    event.preventDefault();

    if (uploading) return;

    setError("");

    if (!file || file.size === 0) {
      setError("Select a non-empty audio file.");
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      setError("This version accepts files up to 10 MiB.");
      return;
    }

    setWatch(null);
    setCurrentNote(null);
    setPollError("");
    setUploading(true);

    const controller = new AbortController();
    uploadRequest.current = controller;

    const formData = new FormData();
    formData.append("audio_file", file);
    formData.append("language_code", language);

    try {
      const data = await requestJSON(
        "/uploads",
        {
          method: "POST",
          body: formData,
          signal: controller.signal,
        },
        120000
      );

      if (controller.signal.aborted) return;

      if (typeof data.id !== "string" || !data.id) {
        throw new Error("The server returned no recording ID.");
      }

      setCurrentNote({
        id: data.id,
        filename: file.name,
        status: "queued",
      });

      setWatch({ id: data.id });
    } catch (err) {
      if (!controller.signal.aborted) {
        const uncertain = !err.status || err.status >= 500;

        setError(
          err.message +
            (uncertain
              ? " Check upload history before trying another upload."
              : "")
        );
      }
    } finally {
      if (!controller.signal.aborted) {
        setUploading(false);
        void loadHistory();
      }
    }
  }

  return (
    <main className="min-h-screen bg-slate-100 px-4 py-12 text-slate-900">
      <Link
  href="/architecture"
  className="mt-2 inline-block text-sm font-medium text-indigo-700 underline"
>
  How this app works
</Link>
      <div className="mx-auto max-w-2xl space-y-6">
        <header>
          <p className="text-sm font-semibold text-indigo-600">
            AUDIO NOTES
          </p>

          <h1 className="mt-2 text-3xl font-bold">
            Turn your audio into text
          </h1>

          <p className="mt-3 text-slate-600">
            Upload an audio recording up to 10 MiB. Transcription runs in the background.
          </p>
        </header>

        <form
          onSubmit={handleSubmit}
          aria-busy={uploading}
          className="space-y-5 rounded-2xl bg-white p-6 shadow-sm"
        >
          <div>
            <label
              htmlFor="audio"
              className="mb-2 block font-medium"
            >
              Audio file
            </label>

            <input
              id="audio"
              type="file"
              accept=".wav,.mp3,.ogg,.flac,.aac,.m4a"
              disabled={uploading}
              onChange={(event) =>
                setFile(event.target.files?.[0] || null)
              }
              className="block w-full rounded-lg border border-slate-300 p-3"
            />

            <p className="mt-2 text-sm text-slate-500">
              WAV, MP3, OGG, FLAC, AAC, or M4A
            </p>
          </div>

          <div>
            <label
              htmlFor="language"
              className="mb-2 block font-medium"
            >
              Spoken language
            </label>

            <select
              id="language"
              value={language}
              disabled={uploading}
              onChange={(event) => setLanguage(event.target.value)}
              className="w-full rounded-lg border border-slate-300 p-3"
            >
              <option value="en-IN">English</option>
              <option value="hi-IN">Hindi</option>
            </select>
          </div>

          <button
            type="submit"
            disabled={uploading || !file}
            className="w-full rounded-lg bg-indigo-600 px-4 py-3 font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {uploading
              ? "Uploading and saving…"
              : "Transcribe and summarize"}
          </button>

          {uploading && (
            <p role="status" className="text-sm text-slate-600">
              Saving your audio. Wait for confirmation before
              closing this page.
            </p>
          )}

          {error && (
            <p
              role="alert"
              className="rounded-lg bg-red-50 p-3 text-red-700"
            >
              {error}
            </p>
          )}
        </form>

        {currentNote && (
          <section
            aria-labelledby="progress-heading"
            className="space-y-3 rounded-2xl bg-white p-6 shadow-sm"
          >
            <h2
              id="progress-heading"
              className="break-words text-xl font-semibold"
            >
              {currentNote.filename || "Recording"}
            </h2>

            <p
              role="status"
              className="font-medium text-indigo-700"
            >
              {STATUS_LABELS[currentNote.status] ||
                "Checking recording…"}
            </p>

            <p className="break-all text-xs text-slate-500">
              Recording ID: {currentNote.id}
            </p>

            {["queued", "transcribing", "summarizing"].includes(
              currentNote.status
            ) && (
              <p className="text-sm text-slate-600">
                Your recording is saved. You can leave this page
                and reopen it from history.
              </p>
            )}

            {pollError && (
              <p
                role="alert"
                className="rounded-lg bg-amber-50 p-3 text-amber-800"
              >
                {pollError}
              </p>
            )}

            {currentNote.error_message && (
              <p
                role="alert"
                className={
                  currentNote.status === "failed"
                    ? "rounded-lg bg-red-50 p-3 text-red-700"
                    : "rounded-lg bg-amber-50 p-3 text-amber-800"
                }
              >
                {currentNote.error_message}
              </p>
            )}

            {currentNote.status === "failed" &&
              !currentNote.error_message && (
                <p role="alert" className="text-red-700">
                  Processing failed. No error details were saved.
                </p>
              )}
          </section>
        )}

        {currentNote?.transcript && (
          <section
            aria-labelledby="transcript-heading"
            className="rounded-2xl bg-white p-6 shadow-sm"
          >
            <h2
              id="transcript-heading"
              className="text-xl font-semibold"
            >
              Transcript
            </h2>

            <p className="mt-4 whitespace-pre-wrap break-words leading-7">
              {currentNote.transcript}
            </p>
          </section>
        )}

        {currentNote?.summary && (
          <section
            aria-labelledby="summary-heading"
            className="rounded-2xl bg-white p-6 shadow-sm"
          >
            <h2
              id="summary-heading"
              className="text-xl font-semibold"
            >
              Summary
            </h2>

            <p className="mt-4 whitespace-pre-wrap break-words leading-7">
              {currentNote.summary}
            </p>
          </section>
        )}

        {currentNote?.status === "completed" &&
          !currentNote.summary &&
          !currentNote.error_message && (
            <p className="rounded-lg bg-amber-50 p-3 text-amber-800">
              No summary is saved for this recording.
            </p>
          )}

        <section
          aria-labelledby="history-heading"
          className="rounded-2xl bg-white p-6 shadow-sm"
        >
          <div className="flex items-center justify-between gap-4">
            <h2
              id="history-heading"
              className="text-xl font-semibold"
            >
              Past uploads
            </h2>

            <button
              type="button"
              onClick={loadHistory}
              disabled={historyLoading || uploading}
              className="text-sm font-medium text-indigo-600 disabled:opacity-50"
            >
              Refresh
            </button>
          </div>

          {historyLoading && (
            <p role="status" className="mt-4 text-slate-600">
              Loading history…
            </p>
          )}

          {historyError && (
            <p role="alert" className="mt-4 text-red-700">
              {historyError}
            </p>
          )}

          {!historyLoading &&
            !historyError &&
            notes.length === 0 && (
              <p className="mt-4 text-slate-600">
                No uploads yet.
              </p>
            )}

          <ul className="mt-4 space-y-3">
            {notes.map((note) => (
              <li key={note.id}>
                <button
                  type="button"
                  onClick={() => openNote(note)}
                  disabled={uploading}
                  className="w-full rounded-lg border border-slate-200 p-3 text-left hover:bg-indigo-50 disabled:opacity-50"
                >
                  <span className="block break-words font-medium">
                    {note.filename}
                  </span>

                  <span className="mt-1 block text-sm text-indigo-700">
                    {STATUS_LABELS[note.status] ||
                      "Unknown status"}
                  </span>

                  <span className="mt-1 block text-sm text-slate-500">
                    {new Date(note.created_at).toLocaleString()}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </main>
  );
}