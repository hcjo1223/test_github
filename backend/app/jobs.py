"""A one-worker job queue for engine runs.

Backtests and ticks can take minutes once an LLM is involved, so they run
off the request. One worker on purpose: engine runs are serialized, which
means two requests can never advance the same ledger at the same time.

Job state lives in memory. What a job produces (a result file, ledger
records) is on disk and survives a restart; the job entry does not.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)
MAX_JOBS = 50


class JobError(RuntimeError):
    """A failure whose message is meant for the user as written."""


@dataclass
class Job:
    id: str
    kind: str
    label: str
    status: str = "queued"          # queued | running | succeeded | failed
    done: int = 0
    total: int = 0
    partial: dict[str, list] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    created: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def progress(self, done: int, total: int, **points: Any) -> None:
        """Report progress; each keyword appends one point to a partial series."""
        with self._lock:
            self.done, self.total = done, total
            for name, value in points.items():
                self.partial.setdefault(name, []).append(value)

    def view(self) -> dict[str, Any]:
        with self._lock:
            return {
                "id": self.id, "kind": self.kind, "label": self.label, "status": self.status,
                "progress": {"done": self.done, "total": self.total},
                "partial": {name: list(values) for name, values in self.partial.items()},
                "result": self.result, "error": self.error, "created": self.created,
            }


class JobQueue:
    def __init__(self) -> None:
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="engine")

    def submit(self, kind: str, label: str, work: Callable[[Job], dict[str, Any]]) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, label=label)
        with self._lock:
            self._jobs[job.id] = job
            while len(self._jobs) > MAX_JOBS:
                self._jobs.popitem(last=False)
        self._pool.submit(self._run, job, work)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _run(self, job: Job, work: Callable[[Job], dict[str, Any]]) -> None:
        job.status = "running"
        try:
            result = work(job)
        except JobError as exc:
            job.error = str(exc)
            job.status = "failed"
        except Exception as exc:  # the engine fails loud; the job reports it
            logger.exception("job %s (%s) failed", job.id, job.kind)
            job.error = f"{type(exc).__name__}: {exc}"
            job.status = "failed"
        else:
            job.result = result
            job.status = "succeeded"


queue = JobQueue()
