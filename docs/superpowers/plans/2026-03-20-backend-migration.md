# ELC Backend Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a FastAPI backend that wraps the existing ELC business logic as REST API endpoints, replacing the Streamlit app.

**Architecture:** FastAPI app with routers per feature, async job pattern for long operations (label sorting, address validation), existing `src/` modules copied to `backend/app/core/` with minimal changes. Job results stored on disk with in-memory index.

**Tech Stack:** FastAPI, Pydantic v2, uvicorn, slowapi, pytest, httpx

**Spec:** `docs/superpowers/specs/2026-03-19-fastapi-react-migration-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/app/__init__.py` | Create | Package init |
| `backend/app/main.py` | Create | FastAPI app, CORS, lifespan (cleanup task), middleware |
| `backend/app/config.py` | Create | Pydantic Settings, env var config |
| `backend/app/routers/__init__.py` | Create | Package init |
| `backend/app/routers/health.py` | Create | GET /api/v1/health |
| `backend/app/routers/jobs.py` | Create | GET /api/v1/jobs/{id}/status, GET /api/v1/jobs/{id}/files/{name} |
| `backend/app/routers/labels.py` | Create | POST /api/v1/jobs/labels |
| `backend/app/routers/validator.py` | Create | POST /api/v1/jobs/validator |
| `backend/app/routers/addresses.py` | Create | CRUD /api/v1/addresses |
| `backend/app/routers/pickup.py` | Create | POST /api/v1/pickup/request |
| `backend/app/schemas/__init__.py` | Create | Package init |
| `backend/app/schemas/common.py` | Create | ApiResponse, ErrorDetail |
| `backend/app/schemas/labels.py` | Create | Label Sorter request/response models |
| `backend/app/schemas/validator.py` | Create | Address Validator request/response models |
| `backend/app/schemas/addresses.py` | Create | Address CRUD models |
| `backend/app/schemas/pickup.py` | Create | Pickup request model |
| `backend/app/services/__init__.py` | Create | Package init |
| `backend/app/services/job_store.py` | Create | Job storage (in-memory index + disk files + TTL cleanup) |
| `backend/app/core/__init__.py` | Create | Package init |
| `backend/app/core/pdf_processor.py` | Copy from src/ | No changes |
| `backend/app/core/excel_parser.py` | Copy from src/ | No changes |
| `backend/app/core/matcher.py` | Copy from src/ | No changes |
| `backend/app/core/sorter.py` | Copy from src/ | No changes |
| `backend/app/core/models.py` | Copy from src/ | No changes |
| `backend/app/core/address_parser.py` | Copy from src/ | No changes |
| `backend/app/core/address_validator.py` | Copy from src/ | Fix `.config` import → `.config_compat` |
| `backend/app/core/italian_db.py` | Copy from src/ | Fix data file path |
| `backend/app/core/zip_validator.py` | Copy from src/ | Fix `.config` import → `.config_compat`, fix data file path, adapt progress_callback |
| `backend/app/core/address_book.py` | Copy from src/ | Remove streamlit imports, remove cache |
| `backend/app/core/security.py` | Copy from src/ | Remove streamlit imports, remove get_client_ip |
| `backend/app/core/logging_config.py` | Copy from src/ | Remove StreamlitLogHandler singleton |
| `backend/app/core/pickup.py` | Create | Extract send_pickup_request from app.py |
| `backend/app/core/label_report.py` | Create | Extract generate_csv_report from app.py |
| `backend/data/` | Copy from data/ | gi_comuni_cap.json, gi_province.json, valid_po_numbers.json |
| `backend/requirements.txt` | Create | FastAPI + all existing deps minus streamlit |
| `backend/tests/__init__.py` | Create | Package init |
| `backend/tests/test_core/__init__.py` | Create | Package init |
| `backend/tests/test_core/test_excel_parser.py` | Copy from tests/ | Fix imports |
| `backend/tests/test_core/test_address_parser.py` | Copy from tests/ | Fix imports |
| `backend/tests/test_core/test_address_validator.py` | Copy from tests/ | Fix imports |
| `backend/tests/test_core/test_italian_db.py` | Copy from tests/ | Fix imports |
| `backend/tests/test_core/test_models.py` | Copy from tests/ | Fix imports |
| `backend/tests/test_core/test_pdf_processor.py` | Copy from tests/ | Fix imports |
| `backend/tests/test_routers/__init__.py` | Create | Package init |
| `backend/tests/test_routers/test_health.py` | Create | Health endpoint test |
| `backend/tests/test_routers/test_addresses.py` | Create | Address CRUD tests |
| `backend/tests/test_routers/test_pickup.py` | Create | Pickup request tests |
| `backend/tests/test_services/__init__.py` | Create | Package init |
| `backend/tests/test_services/test_job_store.py` | Create | Job store tests |

---

## Task 1: Scaffold backend structure + config

**Files:**
- Create: `backend/app/__init__.py`, `backend/app/config.py`, `backend/app/main.py`
- Create: `backend/app/routers/__init__.py`, `backend/app/routers/health.py`
- Create: `backend/app/schemas/__init__.py`, `backend/app/schemas/common.py`
- Create: `backend/app/services/__init__.py`, `backend/app/core/__init__.py`
- Create: `backend/requirements.txt`
- Create: `backend/tests/__init__.py`, `backend/tests/test_routers/__init__.py`, `backend/tests/test_routers/test_health.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p backend/app/{routers,schemas,services,core}
mkdir -p backend/tests/{test_core,test_routers,test_services}
touch backend/app/__init__.py backend/app/routers/__init__.py backend/app/schemas/__init__.py
touch backend/app/services/__init__.py backend/app/core/__init__.py
touch backend/tests/__init__.py backend/tests/test_core/__init__.py
touch backend/tests/test_routers/__init__.py backend/tests/test_services/__init__.py
```

- [ ] **Step 2: Write requirements.txt**

```
# backend/requirements.txt
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
python-multipart>=0.0.9
slowapi>=0.1.9
pydantic>=2.6.0
pydantic-settings>=2.1.0
pandas>=2.0.0,<3.0
pymupdf>=1.23.0
openpyxl>=3.1.0
xlrd>=2.0.1
lxml>=4.9.0
html5lib>=1.1
beautifulsoup4>=4.12.0
python-calamine>=0.1.7
requests>=2.28.0
anthropic>=0.80.0
supabase>=2.0.0
pytest>=8.0.0
httpx>=0.27.0
```

- [ ] **Step 3: Write config.py**

```python
# backend/app/config.py
"""Environment variable configuration using Pydantic Settings."""
import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""

    # External APIs
    anthropic_api_key: str = ""
    google_address_validation_api_key: str = ""
    zapier_webhook_url: str = ""

    # App
    bypass_pin: str = ""
    frontend_url: str = "http://localhost:5173"

    # Job store
    job_ttl_seconds: int = 3600  # 1 hour
    job_cleanup_interval_seconds: int = 600  # 10 minutes
    max_concurrent_jobs: int = 50

    # File limits
    max_file_size_mb: int = 50
    max_pdf_pages: int = 500
    max_excel_rows: int = 1000

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Write common schemas**

```python
# backend/app/schemas/common.py
"""Shared API response schemas."""
from typing import Generic, TypeVar, Optional
from pydantic import BaseModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str


class ApiResponse(BaseModel, Generic[T]):
    ok: bool
    data: Optional[T] = None
    error: Optional[ErrorDetail] = None


def success_response(data) -> dict:
    return {"ok": True, "data": data}


def error_response(code: str, message: str, status_code: int = 400) -> tuple[dict, int]:
    return {"ok": False, "error": {"code": code, "message": message}}, status_code
```

- [ ] **Step 5: Write main.py with health router**

```python
# backend/app/main.py
"""FastAPI application entry point."""
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import health


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: begin periodic job cleanup
    from .services.job_store import job_store
    cleanup_task = asyncio.create_task(_periodic_cleanup())
    yield
    # Shutdown: cancel cleanup
    cleanup_task.cancel()


async def _periodic_cleanup():
    from .services.job_store import job_store
    settings = get_settings()
    while True:
        await asyncio.sleep(settings.job_cleanup_interval_seconds)
        job_store.cleanup_expired()


app = FastAPI(
    title="ELC Tools API",
    version="3.0.0",
    lifespan=lifespan,
)

# CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router, prefix="/api/v1")
```

```python
# backend/app/routers/health.py
"""Health check endpoint."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"ok": True, "data": {"version": "3.0.0"}}
```

- [ ] **Step 6: Write health endpoint test**

```python
# backend/tests/test_routers/test_health.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["data"]["version"] == "3.0.0"
```

- [ ] **Step 7: Run test**

Run: `cd backend && python -m pytest tests/test_routers/test_health.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/
git commit -m "feat: scaffold FastAPI backend with config, schemas, health endpoint

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Job store service

**Files:**
- Create: `backend/app/services/job_store.py`
- Create: `backend/tests/test_services/test_job_store.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_services/test_job_store.py
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
        store = JobStore(base_dir="/tmp/elc-test-jobs-ttl", ttl_seconds=1)
        job_id = store.create_job("labels")
        store.save_file(job_id, "test.pdf", b"data")
        time.sleep(1.5)
        store.cleanup_expired()
        assert store.get_status(job_id) is None
        store.cleanup_all()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_services/test_job_store.py -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement job_store.py**

```python
# backend/app/services/job_store.py
"""Job storage — in-memory index + disk for result files."""
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
            # Check capacity
            active = sum(1 for j in self._jobs.values() if j["status"] == "processing")
            if active >= self._max_jobs:
                raise RuntimeError(f"Max concurrent jobs ({self._max_jobs}) reached")

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

    def get_status(self, job_id: str) -> Optional[dict]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return {**job}

    def save_file(self, job_id: str, filename: str, data: bytes):
        job_dir = self._base_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / filename).write_bytes(data)

    def get_file_path(self, job_id: str, filename: str) -> Optional[Path]:
        path = self._base_dir / job_id / filename
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


# Singleton instance
job_store = JobStore()
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_services/test_job_store.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/job_store.py backend/tests/test_services/
git commit -m "feat: add job store service with TTL cleanup and file storage

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Copy and adapt core business logic modules

**Files:**
- Copy: all `src/*.py` → `backend/app/core/` (except `ui_components.py`)
- Copy: `data/` → `backend/data/`
- Create: `backend/app/core/pickup.py` (extract from app.py)
- Create: `backend/app/core/label_report.py` (extract from app.py)
- Copy: `tests/test_excel_parser.py` → `backend/tests/test_core/`

- [ ] **Step 1: Copy data files**

```bash
cp -r data/ backend/data/
rm backend/data/addresses.json  # legacy, addresses are in Supabase
```

- [ ] **Step 2: Copy pure business logic modules (no changes needed)**

```bash
for f in pdf_processor.py excel_parser.py matcher.py sorter.py models.py address_parser.py; do
    cp src/$f backend/app/core/$f
done
```

- [ ] **Step 2b: Copy and fix address_validator.py**

Copy `src/address_validator.py` to `backend/app/core/address_validator.py`. Change line 12 from `from .config import get_secret` to `from .config_compat import get_secret`.

- [ ] **Step 2c: Copy and fix zip_validator.py data path + config import**

Copy `src/zip_validator.py` to `backend/app/core/zip_validator.py`. Changes:
- Line 22: `from .config import get_supabase_client` → `from .config_compat import get_supabase_client`
- Line 226: `Path(__file__).parent.parent / "data"` → `Path(__file__).parent.parent.parent / "data"` (goes from `core/` → `app/` → `backend/` → `backend/data/`)
- Keep `progress_callback` parameter (it's used by the validator router to update job progress)
```

- [ ] **Step 3: Copy and fix italian_db.py**

Copy `src/italian_db.py` to `backend/app/core/italian_db.py`. Fix the data file paths — change relative paths to use `Path(__file__).parent.parent.parent / "data"` (i.e., `backend/data/`). The current code loads from `data/gi_comuni_cap.json` relative to the working directory — update to use absolute paths relative to the module location.

- [ ] **Step 4: Copy and adapt config.py**

The new `backend/app/config.py` (already created in Task 1) replaces the old one entirely. Create a compatibility shim so existing core modules that call `get_secret()` still work:

```python
# Add to backend/app/core/__init__.py or create backend/app/core/config_compat.py
from ..config import get_settings

def get_secret(section: str, key: str):
    """Compatibility shim for core modules that use the old get_secret interface."""
    settings = get_settings()
    mapping = {
        ("supabase", "url"): settings.supabase_url,
        ("supabase", "key"): settings.supabase_key,
        ("anthropic", "api_key"): settings.anthropic_api_key,
        ("google", "api_key"): settings.google_address_validation_api_key,
        ("zapier", "webhook_url"): settings.zapier_webhook_url,
        ("app", "bypass_pin"): settings.bypass_pin,
    }
    return mapping.get((section, key)) or None

def get_supabase_client():
    """Get shared Supabase client."""
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_key:
        return None
    try:
        from supabase import create_client
        return create_client(settings.supabase_url, settings.supabase_key)
    except Exception:
        return None
```

Then update core modules that import from `.config` to import from this shim instead.

- [ ] **Step 5: Copy and adapt security.py**

Copy `src/security.py` to `backend/app/core/security.py`. Changes:
- Remove `import streamlit as st` (line 14)
- Remove the `get_client_ip()` function entirely (lines 54-89) — IP will come from FastAPI `Request.client.host`
- Remove any `st.session_state` references
- Keep: `check_rate_limit()`, `record_usage()`, `get_usage_stats()`, `validate_excel_content()`, `sanitize_filename()`, `record_failed_attempt()`, `get_debug_info()`
- Update import of `get_secret` to use the compatibility shim

- [ ] **Step 6: Copy and adapt address_book.py**

Copy `src/address_book.py` to `backend/app/core/address_book.py`. Changes:
- Remove `import streamlit as st` (line 10)
- Remove `_clear_cache()` function entirely (lines 78-79) — no caching needed
- Remove any calls to `_clear_cache()` in CRUD functions
- Update import of config to use compatibility shim
- `is_sheets_configured()` → use `get_secret()` from shim (already done in the latest version)

- [ ] **Step 7: Copy and adapt logging_config.py**

Copy `src/logging_config.py` to `backend/app/core/logging_config.py`. Changes:
- Keep `StreamlitLogHandler` class (it's just a buffer handler, name is historical)
- Keep `get_logger()`, `setup_logging()`, `get_streamlit_handler()`
- No actual changes needed — the module doesn't import streamlit

- [ ] **Step 8: Extract pickup.py from app.py**

```python
# backend/app/core/pickup.py
"""Pickup request business logic — sends to Zapier webhook."""
import requests
from datetime import datetime, date, time

from .config_compat import get_secret


def send_pickup_request(
    carrier: str,
    pickup_date: date,
    time_start: time,
    time_end: time,
    company: str,
    contact_name: str,
    address: str,
    zip_code: str,
    city: str,
    province: str,
    reference: str,
    num_packages: int,
    weight_per_package: float,
    length: float,
    width: float,
    height: float,
    use_pallet: bool,
    num_pallets: int,
    pallet_length: float,
    pallet_width: float,
    pallet_height: float,
    notes: str,
) -> tuple[bool, str]:
    # [COPY THE ENTIRE FUNCTION BODY FROM app.py lines 1006-1142 AS-IS]
    # Only change: import get_secret from config_compat instead of src.config
    ...
```

Copy the entire function body from the existing `send_pickup_request()` in `app.py`.

- [ ] **Step 9: Extract label_report.py from app.py**

```python
# backend/app/core/label_report.py
"""CSV report generation for unmatched labels."""
import io
import csv


def generate_csv_report(match_report) -> str:
    """Generate CSV report of unmatched labels."""
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Pagina Originale", "Tracking Estratto", "Corriere", "Motivo"])

    for result in match_report.unmatched:
        tracking = result.tracking if result.tracking else "(non estratto)"
        carrier = result.carrier if result.carrier else "-"
        reason = result.unmatched_reason.value if result.unmatched_reason else "Sconosciuto"
        writer.writerow([result.page_number, tracking, carrier, reason])

    return output.getvalue()
```

- [ ] **Step 10: Copy and fix all existing tests**

```bash
for f in test_excel_parser.py test_address_parser.py test_address_validator.py test_italian_db.py test_models.py test_pdf_processor.py; do
    cp tests/$f backend/tests/test_core/$f
done
```

Fix imports in ALL copied test files: change `from src.` to `from app.core.` throughout. For example:
- `from src.excel_parser import ...` → `from app.core.excel_parser import ...`
- `from src.models import ...` → `from app.core.models import ...`
- `from src.config import ...` → `from app.core.config_compat import ...`

Also fix any test that loads data files to use the correct relative path.

- [ ] **Step 11: Run all core tests**

Run: `cd backend && python -m pytest tests/test_core/ -v`
Expected: ALL PASS (some may need pymupdf/fitz installed)

- [ ] **Step 12: Commit**

```bash
git add backend/app/core/ backend/data/ backend/tests/test_core/
git commit -m "feat: migrate core business logic modules to backend

Copy 12 modules from src/ to backend/app/core/, extract pickup and
label_report from app.py, add config compatibility shim.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Pydantic schemas for all endpoints

**Files:**
- Create: `backend/app/schemas/labels.py`
- Create: `backend/app/schemas/validator.py`
- Create: `backend/app/schemas/addresses.py`
- Create: `backend/app/schemas/pickup.py`

- [ ] **Step 1: Write all schema files**

```python
# backend/app/schemas/labels.py
from pydantic import BaseModel
from typing import Optional


class LabelJobResult(BaseModel):
    total_pages: int
    matched: int
    unmatched: int
    match_rate: float
    unmatched_details: list[dict]
    files: dict[str, str]


class LabelJobStatus(BaseModel):
    status: str  # processing | complete | failed
    progress: Optional[dict] = None
    result: Optional[LabelJobResult] = None
    error: Optional[str] = None
```

```python
# backend/app/schemas/validator.py
from pydantic import BaseModel
from typing import Optional


class ValidatorResultRow(BaseModel):
    status: str  # verified | corrected | review
    city: str
    street: str
    original_zip: str
    suggested_zip: Optional[str] = None
    suggested_street: Optional[str] = None
    corrections: list[str] = []


class ValidatorJobResult(BaseModel):
    total_rows: int
    valid_count: int
    corrected_count: int
    review_count: int
    skipped_count: int
    street_verified_count: int
    street_corrected_count: int
    po_invalid_count: int
    results: list[ValidatorResultRow]
    files: dict[str, str]


class ValidatorJobStatus(BaseModel):
    status: str
    progress: Optional[dict] = None
    result: Optional[ValidatorJobResult] = None
    error: Optional[str] = None
```

```python
# backend/app/schemas/addresses.py
from pydantic import BaseModel, field_validator
from typing import Optional


class AddressCreate(BaseModel):
    name: str
    company: str
    contact_name: str = ""
    street: str
    zip_code: str
    city: str
    province: str = ""
    reference: str = ""
    is_default: bool = False

    @field_validator("zip_code")
    @classmethod
    def validate_zip(cls, v):
        if not v.isdigit() or len(v) != 5:
            raise ValueError("CAP must be 5 digits")
        return v


class AddressUpdate(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    contact_name: Optional[str] = None
    street: Optional[str] = None
    zip_code: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    reference: Optional[str] = None

    @field_validator("zip_code")
    @classmethod
    def validate_zip(cls, v):
        if v is not None and (not v.isdigit() or len(v) != 5):
            raise ValueError("CAP must be 5 digits")
        return v


class AddressResponse(BaseModel):
    id: str
    name: str
    company: str
    contact_name: str
    street: str
    zip: str
    city: str
    province: str
    reference: str
    is_default: bool
```

```python
# backend/app/schemas/pickup.py
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import date, time


class PickupRequest(BaseModel):
    carrier: str
    pickup_date: date
    time_start: time
    time_end: time
    company: str
    contact_name: str = ""
    address: str
    zip_code: str
    city: str
    province: str = ""
    reference: str = ""
    num_packages: int
    weight_per_package: float
    length: float
    width: float
    height: float
    use_pallet: bool = False
    num_pallets: int = 0
    pallet_length: float = 0.0
    pallet_width: float = 0.0
    pallet_height: float = 0.0
    notes: str = ""

    @field_validator("carrier")
    @classmethod
    def validate_carrier(cls, v):
        if v not in ("FedEx", "DHL", "UPS"):
            raise ValueError("Carrier must be FedEx, DHL, or UPS")
        return v

    @field_validator("zip_code")
    @classmethod
    def validate_zip(cls, v):
        if not v.isdigit() or len(v) != 5:
            raise ValueError("CAP must be 5 digits")
        return v
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/
git commit -m "feat: add Pydantic schemas for all API endpoints

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Job status + file download router

**Files:**
- Create: `backend/app/routers/jobs.py`
- Modify: `backend/app/main.py` (register router)

- [ ] **Step 1: Implement jobs router**

```python
# backend/app/routers/jobs.py
"""Job status and file download endpoints."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..services.job_store import job_store

router = APIRouter()


@router.get("/jobs/{job_id}/status")
async def get_job_status(job_id: str):
    status = job_store.get_status(job_id)
    if status is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "error": {"code": "JOB_NOT_FOUND",
                    "message": "Job expired or server restarted. Please re-run."}}
        )
    return {"ok": True, "data": status}


@router.get("/jobs/{job_id}/files/{filename}")
async def download_file(job_id: str, filename: str):
    path = job_store.get_file_path(job_id, filename)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "error": {"code": "FILE_NOT_FOUND",
                    "message": "File not found or job expired."}}
        )

    # Determine media type
    media_types = {
        ".pdf": "application/pdf",
        ".csv": "text/csv",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    suffix = path.suffix.lower()
    media_type = media_types.get(suffix, "application/octet-stream")

    return FileResponse(path, media_type=media_type, filename=filename)
```

- [ ] **Step 2: Register in main.py**

Add to `backend/app/main.py`:
```python
from .routers import health, jobs

app.include_router(health.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/jobs.py backend/app/main.py
git commit -m "feat: add job status and file download endpoints

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Address Book CRUD router

**Files:**
- Create: `backend/app/routers/addresses.py`
- Create: `backend/tests/test_routers/test_addresses.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Implement addresses router**

```python
# backend/app/routers/addresses.py
"""Address Book CRUD endpoints."""
from fastapi import APIRouter, HTTPException

from ..core.address_book import (
    load_addresses, add_address, update_address, delete_address,
    get_address_by_id, set_default_address
)
from ..schemas.addresses import AddressCreate, AddressUpdate, AddressResponse

router = APIRouter()


@router.get("/addresses")
async def list_addresses():
    addresses = load_addresses()
    return {"ok": True, "data": [AddressResponse(
        id=a.id, name=a.name, company=a.company, contact_name=a.contact_name,
        street=a.street, zip=a.zip, city=a.city, province=a.province,
        reference=a.reference, is_default=a.is_default
    ).model_dump() for a in addresses]}


@router.post("/addresses")
async def create_address(body: AddressCreate):
    result = add_address(
        name=body.name, company=body.company, contact_name=body.contact_name,
        street=body.street, zip_code=body.zip_code, city=body.city,
        province=body.province, reference=body.reference, is_default=body.is_default
    )
    if result is None:
        raise HTTPException(status_code=409, detail={
            "ok": False, "error": {"code": "DUPLICATE_NAME", "message": "Address name already exists"}
        })
    return {"ok": True, "data": {"id": result}}


@router.put("/addresses/{address_id}")
async def update_address_endpoint(address_id: str, body: AddressUpdate):
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail={
            "ok": False, "error": {"code": "NO_FIELDS", "message": "No fields to update"}
        })
    success = update_address(address_id, **updates)
    if not success:
        raise HTTPException(status_code=404, detail={
            "ok": False, "error": {"code": "NOT_FOUND", "message": "Address not found"}
        })
    return {"ok": True, "data": {"updated": True}}


@router.delete("/addresses/{address_id}")
async def delete_address_endpoint(address_id: str):
    success = delete_address(address_id)
    if not success:
        raise HTTPException(status_code=400, detail={
            "ok": False, "error": {"code": "DELETE_FAILED", "message": "Cannot delete (last address or not found)"}
        })
    return {"ok": True, "data": {"deleted": True}}


@router.put("/addresses/{address_id}/default")
async def set_default(address_id: str):
    success = set_default_address(address_id)
    if not success:
        raise HTTPException(status_code=404, detail={
            "ok": False, "error": {"code": "NOT_FOUND", "message": "Address not found"}
        })
    return {"ok": True, "data": {"default": True}}
```

- [ ] **Step 2: Register in main.py**

```python
from .routers import health, jobs, addresses
app.include_router(addresses.router, prefix="/api/v1")
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/addresses.py backend/app/main.py
git commit -m "feat: add Address Book CRUD API endpoints

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Pickup Request router

**Files:**
- Create: `backend/app/routers/pickup.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Implement pickup router**

```python
# backend/app/routers/pickup.py
"""Pickup Request endpoint."""
from fastapi import APIRouter, HTTPException

from ..schemas.pickup import PickupRequest
from ..core.pickup import send_pickup_request

router = APIRouter()


@router.post("/pickup/request")
async def create_pickup_request(body: PickupRequest):
    success, message = send_pickup_request(
        carrier=body.carrier,
        pickup_date=body.pickup_date,
        time_start=body.time_start,
        time_end=body.time_end,
        company=body.company,
        contact_name=body.contact_name,
        address=body.address,
        zip_code=body.zip_code,
        city=body.city,
        province=body.province,
        reference=body.reference,
        num_packages=body.num_packages,
        weight_per_package=body.weight_per_package,
        length=body.length,
        width=body.width,
        height=body.height,
        use_pallet=body.use_pallet,
        num_pallets=body.num_pallets,
        pallet_length=body.pallet_length,
        pallet_width=body.pallet_width,
        pallet_height=body.pallet_height,
        notes=body.notes,
    )
    if not success:
        raise HTTPException(status_code=502, detail={
            "ok": False, "error": {"code": "ZAPIER_ERROR", "message": message}
        })
    return {"ok": True, "data": {"message": message}}
```

- [ ] **Step 2: Register in main.py and commit**

```bash
git add backend/app/routers/pickup.py backend/app/main.py
git commit -m "feat: add Pickup Request API endpoint

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Label Sorter job router

**Files:**
- Create: `backend/app/routers/labels.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Implement labels router**

```python
# backend/app/routers/labels.py
"""Label Sorter endpoints."""
import asyncio
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request

from ..config import get_settings
from ..services.job_store import job_store
from ..core.pdf_processor import PDFProcessor
from ..core.excel_parser import ExcelParser, ExcelParserError
from ..core.matcher import Matcher
from ..core.sorter import Sorter, SortMethod
from ..core.label_report import generate_csv_report
from ..core.security import validate_excel_content, sanitize_filename

router = APIRouter()


def _process_labels(job_id: str, pdf_bytes: bytes, excel_bytes: bytes, excel_filename: str, sort_method: str):
    """Run label processing in background thread."""
    settings = get_settings()
    try:
        pdf_processor = PDFProcessor()
        excel_parser = ExcelParser()

        # Process PDF
        pdf_data = pdf_processor.process_pdf(pdf_bytes)
        if pdf_data.total_pages > settings.max_pdf_pages:
            job_store.update_status(job_id, "failed", error=f"Too many pages ({pdf_data.total_pages}). Max: {settings.max_pdf_pages}")
            return

        # Parse Excel
        excel_data = excel_parser.parse_excel(excel_bytes, excel_filename)

        # Match
        matcher = Matcher(pdf_data, excel_data)
        match_report = matcher.match_all()

        # Sort
        method = SortMethod.EXCEL_ORDER if sort_method == "excel_order" else SortMethod.ORDER_ID_NUMERIC
        sorter = Sorter(match_report, excel_data)
        sorted_result = sorter.sort(method)

        # Reorder PDF
        reordered_pdf = pdf_processor.reorder_pdf(pdf_bytes, sorted_result.page_order)

        # Generate CSV report
        csv_report = generate_csv_report(match_report)

        # Save files
        job_store.save_file(job_id, "reordered.pdf", reordered_pdf)
        job_store.save_file(job_id, "unmatched.csv", csv_report.encode("utf-8"))

        # Build unmatched details
        unmatched_details = []
        for r in match_report.unmatched:
            unmatched_details.append({
                "page": r.page_number,
                "tracking": r.tracking or "(non estratto)",
                "carrier": r.carrier or "-",
                "reason": r.unmatched_reason.value if r.unmatched_reason else "Sconosciuto",
            })

        # Complete
        job_store.update_status(job_id, "complete", result={
            "total_pages": pdf_data.total_pages,
            "matched": len(match_report.matched),
            "unmatched": len(match_report.unmatched),
            "match_rate": match_report.match_rate,
            "unmatched_details": unmatched_details,
            "files": {
                "pdf": f"/api/v1/jobs/{job_id}/files/reordered.pdf",
                "csv": f"/api/v1/jobs/{job_id}/files/unmatched.csv",
            },
        })
    except Exception as e:
        job_store.update_status(job_id, "failed", error=str(e))


@router.post("/jobs/labels")
async def create_label_job(
    pdf_files: list[UploadFile] = File(...),
    excel_file: UploadFile = File(...),
    sort_method: str = Form("order_id_numeric"),
):
    settings = get_settings()

    # Validate file sizes
    total_pdf_size = 0
    for f in pdf_files:
        content = await f.read()
        size_mb = len(content) / (1024 * 1024)
        if size_mb > settings.max_file_size_mb:
            raise HTTPException(status_code=413, detail={
                "ok": False, "error": {"code": "FILE_TOO_LARGE", "message": f"PDF '{f.filename}' exceeds {settings.max_file_size_mb}MB"}
            })
        total_pdf_size += size_mb
        await f.seek(0)

    if total_pdf_size > settings.max_file_size_mb * 2:
        raise HTTPException(status_code=413, detail={
            "ok": False, "error": {"code": "FILE_TOO_LARGE", "message": f"Total PDF size ({total_pdf_size:.1f}MB) exceeds limit"}
        })

    excel_content = await excel_file.read()
    if len(excel_content) / (1024 * 1024) > settings.max_file_size_mb:
        raise HTTPException(status_code=413, detail={
            "ok": False, "error": {"code": "FILE_TOO_LARGE", "message": f"Excel file exceeds {settings.max_file_size_mb}MB"}
        })

    # Merge PDFs if multiple
    import fitz
    if len(pdf_files) == 1:
        await pdf_files[0].seek(0)
        pdf_bytes = await pdf_files[0].read()
    else:
        merged = fitz.open()
        for f in pdf_files:
            await f.seek(0)
            content = await f.read()
            doc = fitz.open(stream=content, filetype="pdf")
            merged.insert_pdf(doc)
            doc.close()
        pdf_bytes = merged.tobytes()
        merged.close()

    # Create job and run in background
    job_id = job_store.create_job("labels")
    excel_filename = sanitize_filename(excel_file.filename or "upload.xlsx")
    asyncio.get_event_loop().run_in_executor(
        None, _process_labels, job_id, pdf_bytes, excel_content, excel_filename, sort_method
    )

    return {"ok": True, "data": {"job_id": job_id}}
```

- [ ] **Step 2: Register in main.py and commit**

```bash
git add backend/app/routers/labels.py backend/app/main.py
git commit -m "feat: add Label Sorter async job endpoint

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Address Validator job router

**Files:**
- Create: `backend/app/routers/validator.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Implement validator router**

This is the most complex router. It needs to:
1. Accept Excel upload + config params
2. Validate file size, content injection, row count
3. Check rate limits (global 1000/12h + 3s cooldown)
4. Create job, run validation in background thread
5. Pipe progress updates to job store

```python
# backend/app/routers/validator.py
"""Address Validator endpoints."""
import asyncio
import io
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request

import pandas as pd

from ..config import get_settings
from ..services.job_store import job_store
from ..core.zip_validator import ZipValidator
from ..core.security import (
    check_rate_limit, record_usage, validate_excel_content,
    sanitize_filename, record_failed_attempt
)

router = APIRouter()


def _process_validation(
    job_id: str,
    excel_bytes: bytes,
    confidence: int,
    street_confidence: int,
    bypass_pin: str,
    client_ip: str,
):
    """Run address validation in background thread."""
    settings = get_settings()
    try:
        # Parse Excel
        df = pd.read_excel(io.BytesIO(excel_bytes))

        # Content validation
        valid, error = validate_excel_content(df)
        if not valid:
            record_failed_attempt(client_ip)
            job_store.update_status(job_id, "failed", error=f"Invalid content: {error}")
            return

        # Row limit
        if len(df) > settings.max_excel_rows:
            job_store.update_status(job_id, "failed", error=f"Too many rows ({len(df)}). Max: {settings.max_excel_rows}")
            return

        # Rate limit check
        pin_valid = bool(settings.bypass_pin) and bypass_pin == settings.bypass_pin
        if not pin_valid:
            allowed, message, _ = check_rate_limit(client_ip, len(df))
            if not allowed:
                job_store.update_status(job_id, "failed", error=message)
                return

        # Run validation
        validator = ZipValidator(
            confidence_threshold=confidence,
            street_confidence_threshold=street_confidence,
            google_api_key=settings.google_address_validation_api_key,
            anthropic_api_key=settings.anthropic_api_key,
        )

        def progress_callback(current, total, message):
            job_store.update_progress(job_id, current, total, message)

        report, preprocessed_df = validator.process_dataframe(df, progress_callback=progress_callback)

        # Generate output files
        corrected_excel = validator.generate_corrected_excel(preprocessed_df, report)
        review_excel = validator.generate_review_report(report)

        job_store.save_file(job_id, "corrected.xlsx", corrected_excel)
        job_store.save_file(job_id, "review.xlsx", review_excel)

        # Record usage
        if not pin_valid:
            record_usage(client_ip, len(df))

        # Build per-row results
        row_results = []
        for r in report.results:
            if r.is_valid and r.street_verified:
                status = "verified"
            elif r.auto_corrected or r.street_auto_corrected:
                status = "corrected"
            else:
                status = "review"
            corrections = []
            if r.auto_corrected and r.suggested_zip:
                corrections.append(f"CAP → {r.suggested_zip}")
            if r.street_auto_corrected and r.suggested_street:
                corrections.append(f"Via → {r.suggested_street}")

            row_results.append({
                "status": status,
                "city": r.city or "",
                "street": r.street or "",
                "original_zip": r.original_zip or "",
                "suggested_zip": r.suggested_zip,
                "suggested_street": r.suggested_street,
                "corrections": corrections,
            })

        # Complete
        job_store.update_status(job_id, "complete", result={
            "total_rows": report.total_rows,
            "valid_count": report.valid_count,
            "corrected_count": report.corrected_count,
            "review_count": report.review_count,
            "skipped_count": report.skipped_count,
            "street_verified_count": report.street_verified_count,
            "street_corrected_count": report.street_corrected_count,
            "po_invalid_count": report.po_invalid_count,
            "results": row_results,
            "files": {
                "corrected": f"/api/v1/jobs/{job_id}/files/corrected.xlsx",
                "review": f"/api/v1/jobs/{job_id}/files/review.xlsx",
            },
        })
    except Exception as e:
        job_store.update_status(job_id, "failed", error=str(e))


@router.post("/jobs/validator")
async def create_validator_job(
    request: Request,
    excel_file: UploadFile = File(...),
    confidence_threshold: int = Form(90),
    street_confidence_threshold: int = Form(85),
    bypass_pin: str = Form(""),
):
    settings = get_settings()

    # File size check
    content = await excel_file.read()
    if len(content) / (1024 * 1024) > settings.max_file_size_mb:
        raise HTTPException(status_code=413, detail={
            "ok": False, "error": {"code": "FILE_TOO_LARGE", "message": f"File exceeds {settings.max_file_size_mb}MB"}
        })

    client_ip = request.client.host if request.client else "unknown"

    # Create job and run in background
    job_id = job_store.create_job("validator")
    asyncio.get_event_loop().run_in_executor(
        None, _process_validation, job_id, content,
        confidence_threshold, street_confidence_threshold, bypass_pin, client_ip,
    )

    return {"ok": True, "data": {"job_id": job_id}}
```

- [ ] **Step 2: Register in main.py and commit**

```bash
git add backend/app/routers/validator.py backend/app/main.py
git commit -m "feat: add Address Validator async job endpoint with progress tracking

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Add slowapi rate limiting middleware

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/routers/labels.py`
- Modify: `backend/app/routers/pickup.py`
- Modify: `backend/app/routers/addresses.py`

- [ ] **Step 1: Configure slowapi Limiter in main.py**

```python
# Add to backend/app/main.py
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={"ok": False, "error": {"code": "RATE_LIMIT", "message": str(exc.detail)}}
    )
```

- [ ] **Step 2: Add rate limit decorators to routers**

```python
# backend/app/routers/labels.py
from slowapi import Limiter
from slowapi.util import get_remote_address
limiter = Limiter(key_func=get_remote_address)

@router.post("/jobs/labels")
@limiter.limit("20/hour")
async def create_label_job(request: Request, ...):
```

```python
# backend/app/routers/pickup.py
@router.post("/pickup/request")
@limiter.limit("30/hour")
async def create_pickup_request(request: Request, body: PickupRequest):
```

```python
# backend/app/routers/addresses.py — apply to all endpoints
@router.get("/addresses")
@limiter.limit("100/hour")
async def list_addresses(request: Request):
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py backend/app/routers/
git commit -m "feat: add slowapi per-IP rate limiting on all endpoints

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Final integration — run all tests, verify app starts

**Files:**
- Modify: `backend/app/main.py` (ensure all routers registered)

- [ ] **Step 1: Verify all routers are registered in main.py**

```python
from .routers import health, jobs, labels, validator, addresses, pickup

app.include_router(health.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(labels.router, prefix="/api/v1")
app.include_router(validator.router, prefix="/api/v1")
app.include_router(addresses.router, prefix="/api/v1")
app.include_router(pickup.router, prefix="/api/v1")
```

- [ ] **Step 2: Install dependencies and run all tests**

```bash
cd backend
pip install -r requirements.txt
python -m pytest tests/ -v
```

Expected: ALL PASS

- [ ] **Step 3: Start the server and verify health endpoint**

```bash
cd backend
uvicorn app.main:app --reload --port 8000
# In another terminal:
curl http://localhost:8000/api/v1/health
```

Expected: `{"ok":true,"data":{"version":"3.0.0"}}`

- [ ] **Step 4: Verify API docs**

Open `http://localhost:8000/docs` — should show all endpoints in Swagger UI.

- [ ] **Step 5: Final commit**

```bash
git add backend/
git commit -m "feat: complete FastAPI backend — all endpoints, job store, core modules

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```
