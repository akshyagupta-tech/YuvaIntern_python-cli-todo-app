"""Immutable task domain entities and validation exceptions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from enum import Enum
from typing import Any, Dict, Optional, Tuple


class ValidationError(ValueError):
    """Raised when task data fails domain validation."""


class TaskNotFoundError(LookupError):
    """Raised when a requested task does not exist."""


class InvalidStateTransitionError(ValueError):
    """Raised when a task status transition is not permitted."""


class Priority(str, Enum):
    """Supported task priorities in ascending order."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Status(str, Enum):
    """Supported task lifecycle states."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ARCHIVED = "archived"


def utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def parse_datetime(value: object) -> Optional[datetime]:
    """Parse an ISO 8601 datetime or date and normalize it to UTC."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.max)
    elif isinstance(value, str):
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                parsed = datetime.combine(date.fromisoformat(value), time.max)
            else:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValidationError(
                "Date must be a valid ISO 8601 value."
            ) from error
    else:
        raise ValidationError(
            "Date must be a datetime, ISO 8601 string, or None."
        )

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_tag(value: str) -> str:
    """Validate and normalize a tag to lowercase without a leading hash."""
    if not isinstance(value, str):
        raise ValidationError("Tags must be strings.")
    cleaned = value.strip().removeprefix("#").casefold()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", cleaned):
        raise ValidationError(
            "Tags must be 1-32 alphanumeric, '_' or '-' characters."
        )
    return cleaned


@dataclass(frozen=True)
class AuditEvent:
    """Immutable event with JSON-encoded old/new field values."""

    timestamp: datetime
    action: str
    diff: Tuple[Tuple[str, str, str], ...] = ()

    def __post_init__(self) -> None:
        normalized = parse_datetime(self.timestamp)
        if normalized is None:
            raise ValidationError("Audit event timestamp is required.")
        if not isinstance(self.action, str) or not self.action.strip():
            raise ValidationError("Audit event action must not be empty.")
        object.__setattr__(self, "timestamp", normalized)
        object.__setattr__(self, "action", self.action.strip())
        object.__setattr__(
            self, "diff", tuple(tuple(item) for item in self.diff)
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "action": self.action,
            "diff": [
                {"field": field_name, "old": old_value, "new": new_value}
                for field_name, old_value, new_value in self.diff
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AuditEvent:
        if not isinstance(data, dict):
            raise ValidationError("Invalid audit event record.")
        try:
            diff = tuple(
                (
                    str(item["field"]),
                    str(item["old"]),
                    str(item["new"]),
                )
                for item in data.get("diff", [])
            )
            timestamp = parse_datetime(data.get("timestamp"))
            if timestamp is None:
                raise ValidationError("Audit event timestamp is required.")
            return cls(timestamp, str(data["action"]), diff)
        except (KeyError, TypeError) as error:
            raise ValidationError("Invalid audit event record.") from error


@dataclass(frozen=True)
class Task:
    """An immutable task snapshot with complete mutation history."""

    id: int
    title: str
    description: str = ""
    priority: Priority = Priority.MEDIUM
    status: Status = Status.PENDING
    category: str = "General"
    tags: Tuple[str, ...] = ()
    due_date: Optional[datetime] = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    completed_at: Optional[datetime] = None
    history: Tuple[AuditEvent, ...] = ()

    def __post_init__(self) -> None:
        if (
            isinstance(self.id, bool)
            or not isinstance(self.id, int)
            or self.id < 1
        ):
            raise ValidationError("Task ID must be a positive integer.")
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValidationError("Task title must not be empty.")
        if len(self.title.strip()) > 200:
            raise ValidationError(
                "Task title must be 200 characters or fewer."
            )
        if not isinstance(self.description, str):
            raise ValidationError("Task description must be a string.")
        if len(self.description) > 10_000:
            raise ValidationError(
                "Task description must be 10,000 characters or fewer."
            )
        if isinstance(self.tags, str) or not isinstance(
            self.tags,
            (tuple, list),
        ):
            raise ValidationError("Task tags must be a sequence of strings.")
        if not isinstance(self.history, (tuple, list)) or not all(
            isinstance(event, AuditEvent) for event in self.history
        ):
            raise ValidationError("Task history must contain audit events.")
        if not isinstance(self.category, str) or not self.category.strip():
            raise ValidationError("Task category must not be empty.")

        try:
            priority = Priority(self.priority)
            status = Status(self.status)
        except ValueError as error:
            raise ValidationError(
                "Task priority or status is invalid."
            ) from error

        created_at = parse_datetime(self.created_at)
        updated_at = parse_datetime(self.updated_at)
        if created_at is None or updated_at is None:
            raise ValidationError(
                "Task creation and update timestamps are required."
            )
        tags = tuple(dict.fromkeys(normalize_tag(tag) for tag in self.tags))
        due_date = parse_datetime(self.due_date)
        completed_at = parse_datetime(self.completed_at)

        object.__setattr__(self, "title", self.title.strip())
        object.__setattr__(self, "description", self.description.strip())
        object.__setattr__(self, "category", self.category.strip())
        object.__setattr__(self, "priority", priority)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "tags", tags)
        object.__setattr__(self, "due_date", due_date)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)
        object.__setattr__(self, "completed_at", completed_at)
        object.__setattr__(self, "history", tuple(self.history))

    @property
    def is_overdue(self) -> bool:
        """Whether this active task has passed its due date."""
        return bool(
            self.due_date is not None
            and self.status not in {Status.COMPLETED, Status.ARCHIVED}
            and utc_now() > self.due_date
        )

    @property
    def days_remaining(self) -> Optional[int]:
        """Return due days, negative if late, or None without a due date."""
        if self.due_date is None:
            return None
        return (self.due_date.date() - utc_now().date()).days

    @property
    def due_alert(self) -> Optional[str]:
        """Return a short due-date alert for active tasks."""
        if self.due_date is None or self.status in {
            Status.COMPLETED,
            Status.ARCHIVED,
        }:
            return None
        if self.is_overdue:
            return "Overdue"
        days = self.days_remaining
        if days == 0:
            return "Due today"
        if days is not None and days <= 3:
            return f"Due in {days} day(s)"
        return None

    @property
    def turnaround_days(self) -> Optional[float]:
        """Return elapsed days to completion when the task is complete."""
        if self.completed_at is None:
            return None
        return (self.completed_at - self.created_at).total_seconds() / 86_400

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.value,
            "status": self.status.value,
            "category": self.category,
            "tags": list(self.tags),
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "history": [event.to_dict() for event in self.history],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Task:
        if not isinstance(data, dict):
            raise ValidationError("Invalid task record.")
        try:
            created_at = parse_datetime(data.get("created_at")) or utc_now()
            updated_at = parse_datetime(data.get("updated_at")) or created_at
            return cls(
                id=data["id"],
                title=data["title"],
                description=data.get("description", ""),
                priority=data.get("priority", Priority.MEDIUM.value),
                status=data.get("status", Status.PENDING.value),
                category=data.get("category", "General"),
                tags=tuple(data.get("tags", ())),
                due_date=data.get("due_date"),
                created_at=created_at,
                updated_at=updated_at,
                completed_at=data.get("completed_at"),
                history=tuple(
                    AuditEvent.from_dict(event)
                    for event in data.get("history", [])
                ),
            )
        except (KeyError, TypeError) as error:
            raise ValidationError("Invalid task record.") from error
