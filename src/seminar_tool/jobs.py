"""Tiny background-job helper: one thread per job, progress + Hebrew status message + stop button."""
from __future__ import annotations

import logging
import threading
import time
import traceback
from typing import Any, Callable

log = logging.getLogger("seminar_tool")


class JobStopped(Exception):
    """Raised inside a job when the user pressed 'stop'."""


class Job:
    def __init__(self, name: str) -> None:
        self.name = name
        self.state = "idle"            # idle | running | done | error | stopped
        self.progress = 0.0            # 0..1 (or -1 when unknown)
        self.message = ""
        self.log: list[str] = []
        self.result: Any = None
        self.error = ""
        self.started = 0.0
        self.finished = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- called from the job thread
    def update(self, progress: float | None = None, message: str | None = None, log_line: str | None = None) -> None:
        with self._lock:
            if progress is not None:
                self.progress = progress
            if message is not None:
                self.message = message
            if log_line:
                self.log.append(time.strftime("%H:%M:%S ") + log_line)
                self.log = self.log[-300:]
        if self._stop.is_set():
            raise JobStopped()

    def stopped(self) -> bool:
        return self._stop.is_set()

    def sleep(self, seconds: float) -> None:
        """Sleep that wakes up immediately when 'stop' is pressed."""
        if self._stop.wait(seconds):
            raise JobStopped()

    # ---------------------------------------------------------------- called from the server
    @property
    def running(self) -> bool:
        return self.state == "running"

    def start(self, target: Callable[..., Any], *args: Any, **kwargs: Any) -> bool:
        if self.running:
            return False
        self._stop.clear()
        self.state, self.progress, self.message, self.error, self.result = "running", 0.0, "מתחיל...", "", None
        self.log = []
        self.started, self.finished = time.time(), 0.0

        def run() -> None:
            try:
                self.result = target(self, *args, **kwargs)
                self.state = "done"
            except JobStopped:
                self.state, self.message = "stopped", "נעצר לבקשתך. אפשר להמשיך מאותה נקודה."
            except Exception as exc:  # noqa: BLE001 - shown to the user in Hebrew + logged
                log.error("job %s failed: %s", self.name, traceback.format_exc())
                self.state, self.error = "error", str(exc)
                self.message = "אירעה שגיאה: " + str(exc)
            finally:
                self.finished = time.time()

        self._thread = threading.Thread(target=run, name=f"job-{self.name}", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {"name": self.name, "state": self.state, "progress": self.progress, "message": self.message,
                    "log": list(self.log[-60:]), "error": self.error,
                    "elapsed": round((self.finished or time.time()) - self.started, 1) if self.started else 0}
