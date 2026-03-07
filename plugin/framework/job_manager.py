# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Generic background job manager.

Any module can submit a callable to run in a background thread.
MCP clients poll for results with get_job / list_jobs tools.

Includes endpoint locking to prevent concurrent access to the same
local server (e.g. Forge) from generation and interrogation jobs.
"""

import collections
import logging
import threading
import time
import uuid

log = logging.getLogger("nelson.jobs")


class Job:
    """A single background job."""

    __slots__ = (
        "job_id", "status", "kind", "params",
        "result", "error", "created_at", "finished_at",
    )

    def __init__(self, kind="", params=None):
        self.job_id = uuid.uuid4().hex[:8]
        self.status = "pending"
        self.kind = kind
        self.params = params or {}
        self.result = None
        self.error = None
        self.created_at = time.time()
        self.finished_at = None

    def to_dict(self):
        d = {
            "job_id": self.job_id,
            "status": self.status,
            "kind": self.kind,
            "params": self.params,
            "created_at": self.created_at,
        }
        if self.result is not None:
            d["result"] = self.result
        if self.error is not None:
            d["error"] = self.error
        if self.finished_at is not None:
            d["finished_at"] = self.finished_at
        return d


class JobManager:
    """Manages background jobs.

    Not a ServiceBase — registered as a plain instance via
    ``services.register_instance("jobs", job_manager)``.
    """

    def __init__(self, max_jobs=50):
        self._jobs = {}          # job_id -> Job
        self._lock = threading.Lock()
        self._max_jobs = max_jobs

    def submit(self, fn, kind="", params=None, **kwargs):
        """Submit a callable to run in a background thread.

        Args:
            fn: Callable to execute. Will be called as ``fn(**kwargs)``.
            kind: Label for the job type (e.g. "image_generate").
            params: Arbitrary metadata dict (shown in job status).
            **kwargs: Arguments passed to ``fn``.

        Returns:
            Job instance (status will be "pending" initially).
        """
        job = Job(kind=kind, params=params)
        with self._lock:
            self._evict_finished()
            self._jobs[job.job_id] = job

        t = threading.Thread(
            target=self._run, args=(job, fn, kwargs),
            daemon=True, name="nelson-job-%s" % job.job_id,
        )
        t.start()
        log.info("Job %s submitted: kind=%s", job.job_id, kind)
        return job

    def get(self, job_id):
        """Get a job by ID, or None."""
        with self._lock:
            return self._jobs.get(job_id)

    def list(self, limit=20):
        """List jobs, most recent first."""
        with self._lock:
            jobs = sorted(
                self._jobs.values(),
                key=lambda j: j.created_at,
                reverse=True,
            )
        return jobs[:limit]

    def _run(self, job, fn, kwargs):
        """Thread target — execute the callable and store the result."""
        job.status = "running"
        try:
            result = fn(**kwargs)
            job.status = "done"
            job.result = result if isinstance(result, dict) else {"value": result}
        except Exception as e:
            log.exception("Job %s failed", job.job_id)
            job.status = "error"
            job.error = str(e)
        job.finished_at = time.time()

    # -- Endpoint locking --------------------------------------------------------

    def acquire_endpoint(self, endpoint):
        """Acquire exclusive access to an endpoint. Blocks until available."""
        lock = self._get_endpoint_lock(endpoint)
        lock.acquire()

    def release_endpoint(self, endpoint):
        """Release exclusive access to an endpoint."""
        lock = self._get_endpoint_lock(endpoint)
        try:
            lock.release()
        except RuntimeError:
            pass  # already released

    def _get_endpoint_lock(self, endpoint):
        """Get or create a lock for an endpoint. Thread-safe."""
        with self._lock:
            if not hasattr(self, "_endpoint_locks"):
                self._endpoint_locks = {}
            if endpoint not in self._endpoint_locks:
                self._endpoint_locks[endpoint] = threading.Lock()
            return self._endpoint_locks[endpoint]

    # -- Sequential queue ------------------------------------------------------

    def enqueue(self, fn, kind="", params=None, **kwargs):
        """Submit a job to the sequential queue.

        Jobs submitted via enqueue() run one at a time, in FIFO order.
        Regular submit() jobs are unaffected and run immediately.

        Returns:
            Job instance.
        """
        job = Job(kind=kind, params=params)
        with self._lock:
            self._evict_finished()
            self._jobs[job.job_id] = job
            if not hasattr(self, "_queue"):
                self._queue = collections.deque()
                self._queue_thread = None
            self._queue.append((job, fn, kwargs))
            if self._queue_thread is None or not self._queue_thread.is_alive():
                self._queue_thread = threading.Thread(
                    target=self._drain_queue,
                    daemon=True, name="nelson-job-queue",
                )
                self._queue_thread.start()
        log.info("Job %s enqueued: kind=%s", job.job_id, kind)
        return job

    def _drain_queue(self):
        """Process queued jobs one at a time."""
        while True:
            with self._lock:
                if not hasattr(self, "_queue") or not self._queue:
                    return
                job, fn, kwargs = self._queue.popleft()
            self._run(job, fn, kwargs)

    # -- Internal --------------------------------------------------------------

    def _evict_finished(self):
        """Remove oldest finished jobs if over capacity. Caller holds _lock."""
        if len(self._jobs) < self._max_jobs:
            return
        finished = sorted(
            (j for j in self._jobs.values() if j.status in ("done", "error")),
            key=lambda j: j.created_at,
        )
        to_remove = len(self._jobs) - self._max_jobs + 1
        for j in finished[:to_remove]:
            del self._jobs[j.job_id]
