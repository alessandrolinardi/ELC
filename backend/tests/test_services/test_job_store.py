import threading
import time
from pathlib import Path
from app.services.job_store import JobStore


class TestJobStore:
    def setup_method(self):
        self.store = JobStore(base_dir="/tmp/elc-test-jobs", ttl_seconds=5)
        self.store.cleanup_all()  # clean slate

    def teardown_method(self):
        self.store.cleanup_all()

    def test_create_job_returns_uuid(self):
        job_id = self.store.create_job("labels")
        assert len(job_id) == 36  # UUID format
        assert "-" in job_id

    def test_get_status_new_job(self):
        job_id = self.store.create_job("labels")
        status = self.store.get_status(job_id)
        assert status["status"] == "processing"
        assert status["job_type"] == "labels"

    def test_update_status_complete(self):
        job_id = self.store.create_job("labels")
        self.store.update_status(job_id, "complete", result={"matched": 100})
        status = self.store.get_status(job_id)
        assert status["status"] == "complete"
        assert status["result"]["matched"] == 100

    def test_update_status_failed(self):
        job_id = self.store.create_job("labels")
        self.store.update_status(job_id, "failed", error="File too large")
        status = self.store.get_status(job_id)
        assert status["status"] == "failed"
        assert status["error"] == "File too large"

    def test_update_progress(self):
        job_id = self.store.create_job("validator")
        self.store.update_progress(job_id, current=42, total=100, message="Validating")
        status = self.store.get_status(job_id)
        assert status["progress"]["current"] == 42
        assert status["progress"]["total"] == 100

    def test_save_and_get_file(self):
        job_id = self.store.create_job("labels")
        self.store.save_file(job_id, "result.pdf", b"fake pdf content")
        path = self.store.get_file_path(job_id, "result.pdf")
        assert path is not None
        assert path.exists()
        assert path.read_bytes() == b"fake pdf content"

    def test_get_file_not_found(self):
        job_id = self.store.create_job("labels")
        path = self.store.get_file_path(job_id, "nonexistent.pdf")
        assert path is None

    def test_get_status_nonexistent_job(self):
        status = self.store.get_status("nonexistent-uuid")
        assert status is None

    def test_max_concurrent_jobs(self):
        store = JobStore(base_dir="/tmp/elc-test-jobs-max", ttl_seconds=60, max_jobs=2)
        store.create_job("a")
        store.create_job("b")
        try:
            store.create_job("c")
            assert False, "Should have raised"
        except RuntimeError:
            pass
        finally:
            store.cleanup_all()

    def test_cleanup_expired(self):
        store = JobStore(base_dir="/tmp/elc-test-jobs-ttl", ttl_seconds=0)
        try:
            job_id = store.create_job("labels")
            store.save_file(job_id, "test.pdf", b"data")
            time.sleep(0.1)
            store.cleanup_expired()
            assert store.get_status(job_id) is None
        finally:
            store.cleanup_all()

    def test_concurrent_create_jobs(self):
        """Verify thread safety of create_job under concurrent access."""
        store = JobStore(base_dir="/tmp/elc-test-concurrent", ttl_seconds=60, max_jobs=10)
        results = []
        errors = []

        def create():
            try:
                job_id = store.create_job("test")
                results.append(job_id)
            except RuntimeError:
                errors.append(True)

        threads = [threading.Thread(target=create) for _ in range(15)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have exactly 10 successes and 5 failures
        assert len(results) == 10
        assert len(errors) == 5
        # All job IDs should be unique
        assert len(set(results)) == 10
        store.cleanup_all()

    def test_cleanup_removes_files_from_disk(self):
        store = JobStore(base_dir="/tmp/elc-test-cleanup-files", ttl_seconds=0)
        try:
            job_id = store.create_job("test")
            store.save_file(job_id, "test.pdf", b"data")
            path = store.get_file_path(job_id, "test.pdf")
            assert path is not None and path.exists()

            time.sleep(0.1)
            store.cleanup_expired()

            assert store.get_status(job_id) is None
            assert not path.exists()
        finally:
            store.cleanup_all()
