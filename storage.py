"""Atomic, lock-protected JSON storage for task snapshots."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, List, TypeVar, Union

from models import Priority, Status, Task, ValidationError, utc_now

try:
    import fcntl
except ImportError:  # pragma: no cover - used on Windows.
    fcntl = None  # type: ignore[assignment]

try:
    import msvcrt
except ImportError:  # pragma: no cover - used on POSIX.
    msvcrt = None  # type: ignore[assignment]


class StorageError(RuntimeError):
    """Raised when stored task data cannot be read or written safely."""


T = TypeVar("T")


class AtomicJsonStorage:
    """Persist tasks with atomic replacement and inter-process file locking."""

    SCHEMA_VERSION = 2

    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path).expanduser().resolve()
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self._thread_lock = threading.RLock()

    def load(self) -> List[Task]:
        """Load a consistent task snapshot, migrating old schemas if needed."""
        with self._thread_lock, self._file_lock(exclusive=True):
            return self._load_unlocked(migrate=True)

    def save(self, tasks: List[Task]) -> None:
        """Atomically replace the complete stored task snapshot."""
        with self._thread_lock, self._file_lock(exclusive=True):
            self._write_unlocked(tasks)

    def mutate(self, operation: Callable[[List[Task]], T]) -> T:
        """Apply one business operation under a single storage lock."""
        with self._thread_lock, self._file_lock(exclusive=True):
            tasks = self._load_unlocked(migrate=True)
            result = operation(tasks)
            self._write_unlocked(tasks)
            return result

    @staticmethod
    def write_text_atomic(path: Union[str, Path], contents: str) -> None:
        """Write an export file by replacing it atomically."""
        destination = Path(path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        AtomicJsonStorage._atomic_write(destination, contents)

    def _load_unlocked(self, migrate: bool) -> List[Task]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise StorageError(
                f"Unable to read task storage: {error}"
            ) from error

        migrated = False
        records: List[Any]
        if isinstance(payload, list):
            records = [self._migrate_record(record) for record in payload]
            migrated = True
        elif isinstance(payload, dict):
            version = payload.get("schema_version", 1)
            raw_records = payload.get("tasks")
            if not isinstance(raw_records, list):
                raise StorageError("Task storage must contain a task list.")
            records = raw_records
            if version == 1:
                records = [self._migrate_record(record) for record in records]
                migrated = True
            elif version != self.SCHEMA_VERSION:
                raise StorageError(
                    f"Unsupported task schema version: {version}."
                )
        else:
            raise StorageError(
                "Task storage root must be a JSON object or list."
            )

        try:
            tasks = [Task.from_dict(record) for record in records]
        except (TypeError, ValidationError) as error:
            raise StorageError(f"Invalid task data: {error}") from error
        if len({task.id for task in tasks}) != len(tasks):
            raise StorageError("Task storage contains duplicate IDs.")
        if migrated and migrate:
            self._write_unlocked(tasks)
        return tasks

    @staticmethod
    def _migrate_record(record: object) -> dict:
        if not isinstance(record, dict):
            raise StorageError("Legacy task records must be JSON objects.")
        now = utc_now().isoformat()
        completed = bool(record.get("completed", False))
        raw_priority = str(record.get("priority", "medium")).casefold()
        if raw_priority not in {priority.value for priority in Priority}:
            raw_priority = Priority.MEDIUM.value
        due_date = record.get("due_date") or None
        status = Status.COMPLETED.value if completed else Status.PENDING.value
        return {
            "id": record.get("id", record.get("task_id")),
            "title": record.get("title"),
            "description": record.get("description", ""),
            "priority": raw_priority,
            "status": status,
            "category": record.get("category", "General"),
            "tags": record.get("tags", []),
            "due_date": due_date,
            "created_at": record.get("created_at", now),
            "updated_at": record.get("updated_at", now),
            "completed_at": record.get(
                "completed_at", now if completed else None
            ),
            "history": record.get("history", []),
        }

    def _write_unlocked(self, tasks: List[Task]) -> None:
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "tasks": [task.to_dict() for task in tasks],
        }
        contents = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(self.path, contents)

    @staticmethod
    def _atomic_write(destination: Path, contents: str) -> None:
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as file:
                file.write(contents)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, destination)
            try:
                directory_fd = os.open(destination.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                pass
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    @contextmanager
    def _file_lock(self, exclusive: bool) -> Iterator[None]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as lock_file:
            if fcntl is not None:
                lock_type = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
                fcntl.flock(lock_file.fileno(), lock_type)
            elif msvcrt is not None:  # pragma: no cover - Windows path.
                lock_file.seek(0, os.SEEK_END)
                if lock_file.tell() == 0:
                    lock_file.write(b"0")
                    lock_file.flush()
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                elif msvcrt is not None:  # pragma: no cover - Windows path.
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
