"""Job storage — in-memory index + disk for result files."""
import copy
import shutil
import time
import uuid
from pathlib import Path
from threading import Lock
from typing import Optional


class JobStore:
    def __init__(
        self,
        base_dir: str = "/tmp/elc-jobs",
        ttl_seconds: int = 3600,
        max_jobs: int = 50,
    ):
        self._base_dir = Path(base_dir)
        self._ttl = ttl_seconds
        self._max_jobs = max_jobs
        self._jobs: dict[str, dict] = {}
        self._lock = Lock()

    def create_job(self, job_type: str) -> str:
        with self._lock:
            # Check capacity (count ALL jobs, not just processing)
            if len(self._jobs) >= self._max_jobs:
                raise RuntimeError(f"Max jobs ({self._max_jobs}) reached")

            job_id = str(uuid.uuid4())
            job_dir = self._base_dir / job_id
            job_dir.mkdir(parents=True, exist_ok=True)

            self._jobs[job_id] = {
                "job_type": job_type,
                "status": "processing",
                "result": None,
                "error": None,
                "progress": None,
                "created_at": time.time(),
            }
            return job_id

    def update_status(
        self,
        job_id: str,
        status: str,
        result: Optional[dict] = None,
        error: Optional[str] = None,
    ):
        with self._lock:
            if job_id not in self._jobs:
                return
            self._jobs[job_id]["status"] = status
            if result is not None:
                self._jobs[job_id]["result"] = result
            if error is not None:
                self._jobs[job_id]["error"] = error

    def update_progress(
        self, job_id: str, current: int, total: int, message: str = ""
    ):
        with self._lock:
            if job_id not in self._jobs:
                return
            self._jobs[job_id]["progress"] = {
                "current": current,
                "total": total,
                "message": message,
            }

    def transition_status(self, job_id: str, expected: str, new_status: str) -> bool:
        """Atomically check current status and transition. Returns True if transitioned."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job["status"] != expected:
                return False
            job["status"] = new_status
            return True

    def get_status(self, job_id: str) -> Optional[dict]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return copy.deepcopy(job)

    def save_file(self, job_id: str, filename: str, data: bytes):
        with self._lock:
            if job_id not in self._jobs:
                return  # job was cleaned up, don't write
            job_dir = self._base_dir / job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            (job_dir / filename).write_bytes(data)

    def get_file_path(self, job_id: str, filename: str) -> Optional[Path]:
        safe_name = Path(filename).name  # strips directory components
        if not safe_name:
            return None
        path = (self._base_dir / job_id / safe_name).resolve()
        expected_root = (self._base_dir / job_id).resolve()
        if not str(path).startswith(str(expected_root)):
            return None
        if path.exists():
            return path
        return None

    def cleanup_expired(self):
        now = time.time()
        with self._lock:
            expired = [
                jid for jid, j in self._jobs.items()
                if now - j["created_at"] > self._ttl
            ]
            for jid in expired:
                del self._jobs[jid]
                job_dir = self._base_dir / jid
                if job_dir.exists():
                    shutil.rmtree(job_dir, ignore_errors=True)

    def cleanup_all(self):
        with self._lock:
            self._jobs.clear()
            if self._base_dir.exists():
                shutil.rmtree(self._base_dir, ignore_errors=True)


def _make_job_store() -> "JobStore":
    from ..config import get_settings
    s = get_settings()
    return JobStore(ttl_seconds=s.job_ttl_seconds, max_jobs=s.max_concurrent_jobs)

job_store = _make_job_store()
