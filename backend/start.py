"""Run the API and one queue worker together on a small Render web service."""

import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def main():
    backend = Path(__file__).resolve().parent
    children = []
    stopping = False

    def request_stop(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    commands = [
        ("worker", [sys.executable, "-u", "-m", "app.worker"]),
        ("api", [
            sys.executable, "-u", "-m", "uvicorn", "app.main:app",
            "--host", "0.0.0.0", "--port", os.getenv("PORT", "8000"),
            "--workers", "1", "--timeout-graceful-shutdown", "15",
        ]),
    ]

    try:
        for name, command in commands:
            if stopping:
                break
            process = subprocess.Popen(command, cwd=backend)
            children.append((name, process))
            print(f"[launcher] Started {name} (PID {process.pid})", flush=True)

        while not stopping:
            for name, process in children:
                code = process.poll()
                if code is not None:
                    print(
                        f"[launcher] {name} exited unexpectedly ({code}); stopping both.",
                        flush=True,
                    )
                    return 1
            time.sleep(0.5)
        return 0
    finally:
        print("[launcher] Shutting down API and worker...", flush=True)
        for name, process in children:
            if process.poll() is None:
                process.terminate()

        deadline = time.monotonic() + 20
        for name, process in children:
            try:
                process.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                print(f"[launcher] Force-stopping {name}", flush=True)
                process.kill()
                process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
