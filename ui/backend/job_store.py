"""
Persistent job storage backed by SQLite.

Implements a dict-like interface so existing code that does
``jobs[job_id] = {...}`` or ``jobs[job_id]["status"] = "running"``
continues to work without changes.

On startup, any previously stored jobs are loaded into memory.
Every mutation is written through to SQLite so state survives restarts.
"""

import json
import os
import sqlite3
import threading
from datetime import datetime
from typing import Any, Dict, Iterator, Optional, Tuple


_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id   TEXT PRIMARY KEY,
    data     TEXT NOT NULL,
    created  TEXT NOT NULL,
    updated  TEXT NOT NULL
);
"""

_DB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "vars",
)
_DB_PATH = os.path.join(_DB_DIR, "jobs.db")


def _serialize(obj: Any) -> Any:
    """Make a value JSON-serializable."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, set):
        return list(obj)
    return obj


def _default_serializer(obj: Any) -> Any:
    return _serialize(obj)


class _JobProxy(dict):
    """A dict subclass that writes back to SQLite on mutation."""

    def __init__(self, store: "JobStore", job_id: str, data: dict):
        super().__init__(data)
        self._store = store
        self._job_id = job_id

    def __setitem__(self, key: str, value: Any):
        super().__setitem__(key, value)
        self._store._persist(self._job_id)

    def setdefault(self, key: str, default=None):
        if key not in self:
            self[key] = default
        return self[key]

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        self._store._persist(self._job_id)


class JobStore:
    """Dict-like persistent job storage backed by SQLite.

    Usage is identical to a plain dict::

        store = JobStore()
        store["job-1"] = {"id": "job-1", "status": "running", ...}
        store["job-1"]["status"] = "completed"   # auto-persisted
        job = store.get("job-1")
        del store["job-1"]
        store.clear()
    """

    def __init__(self, db_path: str = _DB_PATH):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._cache: Dict[str, _JobProxy] = {}
        self._init_db()
        self._load_all()

    def _init_db(self):
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(_SCHEMA)
            conn.commit()

    def _load_all(self):
        """Load all jobs from SQLite into memory cache."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute("SELECT job_id, data FROM jobs").fetchall()
            for job_id, data_json in rows:
                data = json.loads(data_json)
                self._cache[job_id] = _JobProxy(self, job_id, data)
        except Exception:
            pass

    def _persist(self, job_id: str):
        """Write a single job to SQLite."""
        proxy = self._cache.get(job_id)
        if proxy is None:
            return
        now = datetime.now().isoformat()
        try:
            data_json = json.dumps(dict(proxy), default=_default_serializer)
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO jobs (job_id, data, created, updated) "
                    "VALUES (?, ?, COALESCE((SELECT created FROM jobs WHERE job_id = ?), ?), ?)",
                    (job_id, data_json, job_id, now, now),
                )
                conn.commit()
        except Exception:
            pass

    def __setitem__(self, job_id: str, value: dict):
        proxy = _JobProxy(self, job_id, value)
        self._cache[job_id] = proxy
        self._persist(job_id)

    def __getitem__(self, job_id: str) -> _JobProxy:
        return self._cache[job_id]

    def __delitem__(self, job_id: str):
        del self._cache[job_id]
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
                conn.commit()
        except Exception:
            pass

    def __contains__(self, job_id: str) -> bool:
        return job_id in self._cache

    def __len__(self) -> int:
        return len(self._cache)

    def __iter__(self) -> Iterator[str]:
        return iter(self._cache)

    def __bool__(self) -> bool:
        return bool(self._cache)

    def get(self, job_id: str, default=None) -> Optional[_JobProxy]:
        return self._cache.get(job_id, default)

    def items(self) -> list:
        return list(self._cache.items())

    def keys(self):
        return self._cache.keys()

    def values(self):
        return self._cache.values()

    def pop(self, job_id: str, *args):
        result = self._cache.pop(job_id, *args)
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
                conn.commit()
        except Exception:
            pass
        return result

    def clear(self):
        """Remove all jobs from memory and SQLite."""
        self._cache.clear()
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("DELETE FROM jobs")
                conn.commit()
        except Exception:
            pass
