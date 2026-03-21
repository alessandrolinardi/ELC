"""
Advanced JobStore tests covering issues #1 (race conditions) and #2 (shallow copy).

Tests transition_status atomicity, deepcopy isolation, concurrent double-confirm,
and file operations under concurrent access.
"""
import threading
import time
from app.services.job_store import JobStore


class TestTransitionStatus:
    """Issue #1: Atomic check-then-act via transition_status."""

    def setup_method(self):
        self.store = JobStore(base_dir="/tmp/elc-test-transition", ttl_seconds=60)
        self.store.cleanup_all()

    def teardown_method(self):
        self.store.cleanup_all()

    def test_transition_success(self):
        job_id = self.store.create_job("validator")
        self.store.update_status(job_id, "parsed")
        assert self.store.transition_status(job_id, "parsed", "processing_validate") is True
        status = self.store.get_status(job_id)
        assert status["status"] == "processing_validate"

    def test_transition_wrong_expected_status(self):
        job_id = self.store.create_job("validator")
        # Status is "processing", not "parsed"
        assert self.store.transition_status(job_id, "parsed", "processing_validate") is False

    def test_transition_nonexistent_job(self):
        assert self.store.transition_status("fake-id", "parsed", "processing_validate") is False

    def test_transition_already_transitioned(self):
        """Double-transition should fail — only one can win."""
        job_id = self.store.create_job("validator")
        self.store.update_status(job_id, "parsed")
        assert self.store.transition_status(job_id, "parsed", "processing_validate") is True
        # Second attempt should fail
        assert self.store.transition_status(job_id, "parsed", "processing_validate") is False

    def test_concurrent_double_confirm_race(self):
        """Simulate two threads trying to confirm the same job simultaneously.
        Only one should succeed — this is the core test for issue #1."""
        job_id = self.store.create_job("validator")
        self.store.update_status(job_id, "parsed", result={
            "rows": [], "config": {"confidence": 90}
        })

        results = {"wins": 0, "losses": 0}
        barrier = threading.Barrier(2)

        def try_confirm():
            barrier.wait()  # Synchronize start
            success = self.store.transition_status(job_id, "parsed", "processing_validate")
            if success:
                results["wins"] += 1
            else:
                results["losses"] += 1

        threads = [threading.Thread(target=try_confirm) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results["wins"] == 1, "Exactly one thread should win the transition"
        assert results["losses"] == 1, "Exactly one thread should lose"

    def test_high_concurrency_transition(self):
        """10 threads racing on same transition — exactly 1 winner."""
        job_id = self.store.create_job("validator")
        self.store.update_status(job_id, "parsed")

        wins = []
        barrier = threading.Barrier(10)

        def try_transition():
            barrier.wait()
            if self.store.transition_status(job_id, "parsed", "processing_validate"):
                wins.append(True)

        threads = [threading.Thread(target=try_transition) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(wins) == 1


class TestDeepCopyIsolation:
    """Issue #2: get_status returns deep copy — mutations don't leak."""

    def setup_method(self):
        self.store = JobStore(base_dir="/tmp/elc-test-deepcopy", ttl_seconds=60)
        self.store.cleanup_all()

    def teardown_method(self):
        self.store.cleanup_all()

    def test_mutating_returned_status_does_not_affect_store(self):
        job_id = self.store.create_job("validator")
        self.store.update_status(job_id, "parsed", result={
            "rows": [{"index": 0, "parsed": {"street": "Via Roma 10"}}],
            "config": {"confidence": 90},
        })

        # Get status and mutate the returned copy
        status = self.store.get_status(job_id)
        status["result"]["rows"][0]["parsed"]["street"] = "MUTATED"
        status["result"]["config"]["confidence"] = 999

        # Original store data should be unaffected
        fresh = self.store.get_status(job_id)
        assert fresh["result"]["rows"][0]["parsed"]["street"] == "Via Roma 10"
        assert fresh["result"]["config"]["confidence"] == 90

    def test_mutating_nested_list_does_not_affect_store(self):
        job_id = self.store.create_job("validator")
        self.store.update_status(job_id, "parsed", result={
            "rows": [{"index": 0}, {"index": 1}],
        })

        status = self.store.get_status(job_id)
        status["result"]["rows"].append({"index": 99})
        status["result"]["rows"][0]["index"] = -1

        fresh = self.store.get_status(job_id)
        assert len(fresh["result"]["rows"]) == 2
        assert fresh["result"]["rows"][0]["index"] == 0

    def test_concurrent_reads_are_independent(self):
        """Two threads reading same job get independent copies."""
        job_id = self.store.create_job("validator")
        self.store.update_status(job_id, "parsed", result={
            "rows": [{"index": 0, "data": "original"}],
        })

        copies = []

        def read_and_mutate():
            status = self.store.get_status(job_id)
            status["result"]["rows"][0]["data"] = f"mutated-{threading.current_thread().name}"
            copies.append(status)

        threads = [threading.Thread(target=read_and_mutate) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All copies should have been mutated independently
        assert len(copies) == 5
        # Original store data unaffected
        fresh = self.store.get_status(job_id)
        assert fresh["result"]["rows"][0]["data"] == "original"


class TestConcurrentFileOperations:
    """File ops under concurrent access."""

    def setup_method(self):
        self.store = JobStore(base_dir="/tmp/elc-test-concurrent-files", ttl_seconds=60)
        self.store.cleanup_all()

    def teardown_method(self):
        self.store.cleanup_all()

    def test_save_file_after_cleanup_is_noop(self):
        """save_file on cleaned-up job should not create orphan files."""
        job_id = self.store.create_job("test")
        self.store.cleanup_all()
        # Should not raise or create files
        self.store.save_file(job_id, "test.xlsx", b"data")
        assert self.store.get_file_path(job_id, "test.xlsx") is None

    def test_path_traversal_blocked(self):
        job_id = self.store.create_job("test")
        self.store.save_file(job_id, "legit.xlsx", b"data")
        # Attempting path traversal
        path = self.store.get_file_path(job_id, "../../../etc/passwd")
        assert path is None

    def test_concurrent_save_and_read(self):
        """Multiple threads saving/reading files on same job."""
        job_id = self.store.create_job("test")
        errors = []

        def write_and_read(n):
            try:
                filename = f"file_{n}.xlsx"
                data = f"content_{n}".encode()
                self.store.save_file(job_id, filename, data)
                path = self.store.get_file_path(job_id, filename)
                if path is None or path.read_bytes() != data:
                    errors.append(f"file_{n} mismatch")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=write_and_read, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Errors: {errors}"
