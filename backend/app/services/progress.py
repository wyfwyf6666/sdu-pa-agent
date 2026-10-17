import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional


class ProgressService:
    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def init_progress(self, progress_id: str) -> None:
        if not progress_id:
            return
        with self._lock:
            if progress_id not in self._store:  # create if new
                self._store[progress_id] = {
                    "status": "running",
                    "updates": [],
                    "final_trace": None,
                    "error": None,
                    "updated_at": time.time(),
                }
            else:  # reset existing progress
                bucket = self._store[progress_id]
                bucket.update(
                    {"status": "running", "updates": [], "final_trace": None, "error": None, "updated_at": time.time()}
                )

    def add_update(
        self,
        progress_id: Optional[str],
        phase: str,
        title: str,
        message: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not progress_id:
            return
        update = {
            "id": str(uuid.uuid4()),
            "phase": phase,
            "title": title,
            "message": message,
            "data": data or {},
            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
        with self._lock:
            bucket = self._store.get(progress_id)
            if not bucket:
                return
            bucket["updates"].append(update)
            bucket["updated_at"] = time.time()

    def finish_progress(
        self,
        progress_id: Optional[str],
        final_trace: Optional[Dict[str, Any]] = None,
        final_payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not progress_id:
            return
        with self._lock:
            bucket = self._store.get(progress_id)
            if not bucket:
                return
            bucket["status"] = "finished"
            bucket["final_trace"] = final_trace or final_payload
            bucket["updated_at"] = time.time()

    def mark_error(self, progress_id: Optional[str], error_message: str) -> None:
        if not progress_id:
            return
        with self._lock:
            bucket = self._store.get(progress_id)
            if not bucket:
                return
            bucket["status"] = "error"
            bucket["error"] = error_message
            bucket["updated_at"] = time.time()

    def cancel_progress(self, progress_id: Optional[str]) -> None:
        if not progress_id:
            return
        with self._lock:
            bucket = self._store.get(progress_id)
            if not bucket:
                return
            bucket["status"] = "cancelled"
            bucket["error"] = None
            bucket["updated_at"] = time.time()

    def get_progress(self, progress_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            data = self._store.get(progress_id)
            if not data:
                return None
            # shallow copy to avoid mutation outside lock
            return {
                "status": data["status"],
                "updates": list(data["updates"]),
                "final_trace": data.get("final_trace"),
                "error": data.get("error"),
            }


progress_service = ProgressService()
