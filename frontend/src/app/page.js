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

  const processing = ["queued", "transcribing", "summarizing"].includes(currentNote?.status);
  const stageIndex = ["queued", "transcribing", "summarizing", "completed"].indexOf(currentNote?.status);

  return (
    <div className="audio-app">
      <a className="skip-link" href="#workspace">Skip to workspace</a>
      <header className="app-header">
        <div className="header-inner">
          <Link href="/" className="brand" aria-label="Gnani Audio Notes home">
            <span className="brand-mark"><Icon name="wave" /></span>
            <span>gnani<span className="brand-subtitle">audio notes</span></span>
          </Link>
          <nav aria-label="Main navigation">
            <Link href="/architecture" className="nav-link">How it works <Icon name="arrow" /></Link>
            <a className="nav-link github-link" href="https://github.com/sankalpvats/Gnani-audio-notes" target="_blank" rel="noopener noreferrer">GitHub <Icon name="external" /></a>
          </nav>
        </div>
      </header>

      <main id="workspace" className="workspace">
        <header className="intro">
          <p className="eyebrow">LESS REPLAYING. MORE CLARITY.</p>
          <h1>Your recordings,<br /><span>worth a second look.</span></h1>
          <p className="intro-description">Turn conversations, lectures, and voice notes into<br className="desktop-break" /> readable transcripts and concise summaries.</p>
        </header>

        <div className="workspace-grid">
          <div className="workspace-main">
            <section className="panel upload-panel" aria-labelledby="upload-heading">
              <div className="panel-heading">
                <div><p className="section-kicker">START HERE</p><h2 id="upload-heading">New recording</h2></div>
                <span className="limit-label">Up to 10 MiB</span>
              </div>
              <form onSubmit={handleSubmit} aria-busy={uploading}>
                <label className={`file-picker ${file ? "has-file" : ""} ${uploading ? "is-disabled" : ""}`} htmlFor="audio">
                  <input id="audio" type="file" accept=".wav,.mp3,.ogg,.flac,.aac,.m4a" disabled={uploading}
                    aria-describedby="file-help"
                    onChange={(event) => { setFile(event.target.files?.[0] || null); setError(""); }} />
                  <span className="upload-icon"><Icon name={file ? "audio" : "upload"} /></span>
                  <span className="file-title">{file ? file.name : "Choose an audio recording"}</span>
                  <span className="file-description">{file ? `${(file.size / (1024 * 1024)).toFixed(2)} MiB · Click to change file` : "Browse files on your device"}</span>
                  <span className="file-formats" id="file-help">WAV, MP3, OGG, FLAC, AAC, or M4A</span>
                </label>
                <div className="upload-controls">
                  <div className="language-field">
                    <label htmlFor="language">Spoken language</label>
                    <select id="language" value={language} disabled={uploading} onChange={(event) => setLanguage(event.target.value)}>
                      <option value="en-IN">English</option>
                      <option value="hi-IN">Hindi</option>
                    </select>
                  </div>
                  <button type="submit" className="primary-button" disabled={uploading || !file}>
                    <Icon name={uploading ? "clock" : "spark"} />
                    {uploading ? "Uploading…" : "Transcribe & summarize"}
                  </button>
                </div>
                <p className="upload-hint" role={uploading ? "status" : undefined}>
                  <Icon name="info" />
                  {uploading ? "Saving your audio. Keep this page open until the upload is confirmed." : "Once saved, your recording processes in the background."}
                </p>
                {error && <p role="alert" className="notice notice-error">{error}</p>}
              </form>
            </section>

            {currentNote ? (
              <section className="panel result-panel" aria-labelledby="progress-heading">
                <div className="panel-heading result-heading">
                  <div className="result-title"><p className="section-kicker">YOUR RECORDING</p><h2 id="progress-heading">{currentNote.filename || "Recording"}</h2></div>
                  <span role="status"><StatusBadge status={currentNote.status} /></span>
                </div>
                {currentNote.status !== "failed" && (
                  <ol className="progress-steps" aria-label="Processing stages">
                    {["Queued", "Transcribing", "Summarizing", "Complete"].map((label, index) => (
                      <li key={label} className={index < stageIndex ? "step-done" : index === stageIndex ? "step-current" : ""} aria-current={index === stageIndex ? "step" : undefined}>
                        <span className="step-dot">{index < stageIndex || (index === 3 && stageIndex === 3) ? <Icon name="check" /> : index + 1}</span><span>{label}</span>
                      </li>
                    ))}
                  </ol>
                )}
                {processing && <p className="processing-note">Your recording is saved. You can leave this page and reopen it from history.</p>}
                {pollError && <p role="alert" className="notice notice-warning">{pollError}</p>}
                {currentNote.error_message && <p role="alert" className={`notice ${currentNote.status === "failed" ? "notice-error" : "notice-warning"}`}>{currentNote.error_message}</p>}
                {currentNote.status === "failed" && !currentNote.error_message && <p role="alert" className="notice notice-error">Processing failed. No error details were saved.</p>}
                {currentNote.summary && (
                  <section className="summary-section" aria-labelledby="summary-heading">
                    <h3 id="summary-heading"><Icon name="spark" /> At a glance <span>AI SUMMARY</span></h3>
                    <p className="result-text">{currentNote.summary}</p>
                  </section>
                )}
                {currentNote.transcript && (
                  <section className="transcript-section" aria-labelledby="transcript-heading">
                    <h3 id="transcript-heading"><Icon name="text" /> Full transcript</h3>
                    <p className="result-text">{currentNote.transcript}</p>
                  </section>
                )}
                {currentNote.status === "completed" && !currentNote.summary && !currentNote.error_message && <p className="notice notice-warning">No summary is saved for this recording.</p>}
                <details className="recording-details"><summary>Recording details</summary><p>ID: {currentNote.id}</p></details>
              </section>
            ) : (
              <section className="results-placeholder" aria-labelledby="placeholder-heading">
                <span className="placeholder-icon"><Icon name="text" /></span>
                <div><h2 id="placeholder-heading">A little audio. A lot of clarity.</h2><p>Your transcript and summary will appear here.<br />Upload a recording or open one from history.</p></div>
              </section>
            )}
          </div>

          <aside className="panel history-panel" aria-labelledby="history-heading">
            <div className="panel-heading">
              <div><p className="section-kicker">PICK UP WHERE YOU LEFT OFF</p><h2 id="history-heading">Recent recordings</h2></div>
              <button type="button" className="icon-button" onClick={loadHistory} disabled={historyLoading || uploading} aria-label="Refresh recordings" title="Refresh recordings"><Icon name="refresh" /></button>
            </div>
            <p className="history-description">Select a recording to view its notes.</p>
            {historyLoading && <p role="status" className="history-message">Loading recordings…</p>}
            {historyError && <p role="alert" className="notice notice-error">{historyError}</p>}
            {!historyLoading && !historyError && notes.length === 0 && <div className="empty-history"><Icon name="audio" /><h3>Your first note starts here</h3><p>Saved recordings will appear in this list.</p></div>}
            <ul className="history-list">
              {notes.map((note) => (
                <li key={note.id}>
                  <button type="button" onClick={() => openNote(note)} disabled={uploading} aria-pressed={currentNote?.id === note.id} className={`history-item ${currentNote?.id === note.id ? "is-selected" : ""}`}>
                    <span className="history-file-icon"><Icon name="audio" /></span>
                    <span className="history-item-content">
                      <span className="history-filename">{note.filename}</span>
                      <time dateTime={note.created_at}>{new Date(note.created_at).toLocaleString(undefined, {month: "short", day: "numeric", hour: "numeric", minute: "2-digit"})}</time>
                      <StatusBadge status={note.status} compact />
                    </span>
                    <span className="history-arrow"><Icon name="arrow" /></span>
                  </button>
                </li>
              ))}
            </ul>
            <p className="history-footnote"><Icon name="info" /> Demo history is shared. Use non-sensitive audio.</p>
          </aside>
        </div>
        <footer className="app-footer"><span>Speech to text. Thoughts to takeaways.</span><Link href="/architecture">Explore the architecture <Icon name="arrow" /></Link></footer>
      </main>
    </div>
  );
}

function StatusBadge({ status, compact = false }) {
  const shortLabels = { queued: "Queued", transcribing: "Transcribing", summarizing: "Summarizing", completed: "Complete", failed: "Failed" };
  const safeStatus = Object.hasOwn(STATUS_LABELS, status) ? status : "unknown";
  return <span className={`status-badge status-${safeStatus}`}><span className="status-dot" />{(compact ? shortLabels[status] : STATUS_LABELS[status]) || "Checking…"}</span>;
}

function Icon({ name }) {
  const paths = {
    wave: "M3 10v4M7 6v12M12 3v18M17 7v10M21 10v4",
    upload: "M12 16V3m-5 5 5-5 5 5M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5",
    audio: "M5 4h9l5 5v11H5V4Zm9 0v5h5M8 13v3m4-5v7m4-5v3",
    text: "M5 4h14v16H5V4Zm3 4h8M8 12h8M8 16h5",
    arrow: "M5 12h14m-5-5 5 5-5 5",
    external: "M14 3h7v7m0-7L10 14M10 5H4v15h15v-6",
    check: "m5 12 4 4L19 6",
    clock: "M12 8v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
    refresh: "M20 7v5h-5M4 17v-5h5M6.1 6.1A8 8 0 0 1 20 12M4 12a8 8 0 0 0 13.9 5.9",
    info: "M12 11v6m0-10v.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
    spark: "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z",
  };
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] || paths.audio} /></svg>;
}

