import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field

from app.config import JOB_TTL_SECONDS


@dataclass
class Job:
    job_id: str
    mode: str = "4stems"
    requested_model: str | None = None
    model_used: str | None = None
    # Terminal values MUST be exactly "complete" / "failed" — the Base44
    # frontend (src/lib/demucsClient.js) polls this field and only treats
    # those two exact strings as terminal; anything else keeps polling.
    status: str = "queued"  # queued | processing | complete | failed
    stage: str = "upload_received"
    progress: int = 0
    stems: dict = field(default_factory=dict)  # stem name -> absolute file path
    zip_path: str | None = None
    error: dict | None = None
    temp_dir: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def touch(self):
        self.updated_at = time.time()

    def to_public_dict(self):
        stems = {}
        zip_url = None
        if self.status == "complete":
            stems = {name: f"/api/download/{self.job_id}/{name}" for name in self.stems}
            zip_url = f"/api/download/{self.job_id}/zip"
        return {
            "job_id": self.job_id,
            "status": self.status,
            "stage": self.stage,
            "progress": self.progress,
            "mode": self.mode,
            "model_used": self.model_used,
            "stems": stems,
            "zip_url": zip_url,
            "error": self.error,
        }


class JobManager:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def create(self, mode: str, requested_model: str | None) -> Job:
        job = Job(job_id=uuid.uuid4().hex, mode=mode, requested_model=requested_model)
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def count_active(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.status in ("queued", "processing"))

    def count_all(self) -> int:
        with self._lock:
            return len(self._jobs)

    def _cleanup_loop(self):
        while True:
            time.sleep(60)
            now = time.time()
            with self._lock:
                expired = [
                    j for j in self._jobs.values()
                    if now - j.updated_at > JOB_TTL_SECONDS and j.status in ("complete", "failed")
                ]
            for job in expired:
                if job.temp_dir:
                    shutil.rmtree(job.temp_dir, ignore_errors=True)
                with self._lock:
                    self._jobs.pop(job.job_id, None)


jobs = JobManager()
