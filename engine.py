"""Task lifecycle, querying, exports, and metrics business services."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import replace
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    TypedDict,
    Union,
    cast,
)

from models import (
    AuditEvent,
    InvalidStateTransitionError,
    Priority,
    Status,
    Task,
    TaskNotFoundError,
    ValidationError,
    normalize_tag,
    parse_datetime,
    utc_now,
)
from storage import AtomicJsonStorage


class TaskMetrics(TypedDict):
    """Computed task counts and performance indicators."""

    total_tasks: int
    active_tasks: int
    completion_ratio: float
    overdue_count: int
    priority_distribution: Dict[str, int]
    average_turnaround_days: float


class TaskManager:
    """Orchestrate task operations without depending on a UI or CLI."""

    _PRIORITIES: Sequence[Priority] = tuple(Priority)
    _ALLOWED_TRANSITIONS = {
        Status.PENDING: {
            Status.IN_PROGRESS,
            Status.COMPLETED,
            Status.ARCHIVED,
        },
        Status.IN_PROGRESS: {
            Status.PENDING,
            Status.COMPLETED,
            Status.ARCHIVED,
        },
        Status.COMPLETED: {Status.IN_PROGRESS, Status.ARCHIVED},
        Status.ARCHIVED: {Status.PENDING},
    }
    _SORT_KEYS = {"created_at", "due_date", "priority_rank", "title"}

    def __init__(
        self,
        storage_path: Union[str, Path] = "tasks.json",
        storage: Optional[AtomicJsonStorage] = None,
    ) -> None:
        self.storage = storage or AtomicJsonStorage(storage_path)

    def create_task(
        self,
        title: str,
        description: str = "",
        priority: Union[Priority, str] = Priority.MEDIUM,
        category: str = "General",
        tags: Iterable[str] = (),
        due_date: object = None,
    ) -> Task:
        """Create and persist a validated task with a creation audit event."""
        clean_title = self._required_text(title, "Title", 200)
        clean_description = self._optional_text(
            description, "Description", 10_000
        )
        clean_category = self._required_text(category, "Category", 80)
        selected_priority = self._priority(priority)
        normalized_tags = self._tags(tags)
        normalized_due_date = parse_datetime(due_date)
        now = utc_now()

        def add(tasks: List[Task]) -> Task:
            task_id = max((task.id for task in tasks), default=0) + 1
            task = Task(
                id=task_id,
                title=clean_title,
                description=clean_description,
                priority=selected_priority,
                category=clean_category,
                tags=normalized_tags,
                due_date=normalized_due_date,
                created_at=now,
                updated_at=now,
            )
            event = self._event(
                task,
                "created",
                {
                    "title": clean_title,
                    "description": clean_description,
                    "priority": selected_priority,
                    "status": Status.PENDING,
                    "category": clean_category,
                    "tags": normalized_tags,
                    "due_date": normalized_due_date,
                },
                include_old=False,
            )
            task = replace(task, history=(event,))
            tasks.append(task)
            return task

        return self.storage.mutate(add)

    def get_task(self, task_id: int) -> Task:
        """Return a task by ID or raise :class:`TaskNotFoundError`."""
        self._validate_task_id(task_id)
        for task in self.storage.load():
            if task.id == task_id:
                return task
        raise TaskNotFoundError(f"Task {task_id} was not found.")

    def list_tasks(
        self,
        status: Optional[Union[Status, str]] = None,
        priority: Optional[Union[Priority, str]] = None,
        tag: Optional[str] = None,
        query: Optional[str] = None,
        overdue: Optional[bool] = None,
        sort_by: str = "created_at",
        descending: bool = False,
        include_archived: bool = True,
    ) -> List[Task]:
        """Filter and sort tasks across lifecycle, tags, dates, and text."""
        if not isinstance(sort_by, str) or sort_by not in self._SORT_KEYS:
            valid_fields = ", ".join(sorted(self._SORT_KEYS))
            raise ValidationError(
                f"Sort field must be one of: {valid_fields}."
            )
        if not isinstance(descending, bool):
            raise ValidationError("Descending must be a boolean.")
        if not isinstance(include_archived, bool):
            raise ValidationError("Include-archived must be a boolean.")
        if overdue is not None and not isinstance(overdue, bool):
            raise ValidationError("Overdue filter must be a boolean or None.")

        selected_status = self._status(status) if status is not None else None
        selected_priority = (
            self._priority(priority) if priority is not None else None
        )
        selected_tag = normalize_tag(tag) if tag is not None else None
        search_query = (
            query.strip().casefold() if isinstance(query, str) else None
        )
        if query is not None and not isinstance(query, str):
            raise ValidationError("Search query must be a string or None.")

        tasks = self.storage.load()
        filtered = [
            task
            for task in tasks
            if (include_archived or task.status is not Status.ARCHIVED)
            and (selected_status is None or task.status is selected_status)
            and (
                selected_priority is None or task.priority is selected_priority
            )
            and (selected_tag is None or selected_tag in task.tags)
            and (overdue is None or task.is_overdue is overdue)
            and (not search_query or self._matches_query(task, search_query))
        ]
        return self._sort_tasks(filtered, sort_by, descending)

    def update_task(self, task_id: int, **changes: object) -> Task:
        """Update supported task fields and append a field-level audit diff."""
        self._validate_task_id(task_id)
        allowed = {
            "title",
            "description",
            "category",
            "priority",
            "due_date",
            "tags",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise ValidationError(
                f"Unsupported task fields: {', '.join(sorted(unknown))}."
            )
        if not changes:
            return self.get_task(task_id)

        normalized: Dict[str, object] = {}
        for field_name, value in changes.items():
            if field_name == "title":
                normalized[field_name] = self._required_text(
                    value, "Title", 200
                )
            elif field_name == "description":
                normalized[field_name] = self._optional_text(
                    value,
                    "Description",
                    10_000,
                )
            elif field_name == "category":
                normalized[field_name] = self._required_text(
                    value, "Category", 80
                )
            elif field_name == "priority":
                normalized[field_name] = self._priority(value)
            elif field_name == "due_date":
                normalized[field_name] = parse_datetime(value)
            elif field_name == "tags":
                normalized[field_name] = self._tags(value)

        return self._update(task_id, normalized, "updated")

    def transition_task(
        self, task_id: int, status: Union[Status, str]
    ) -> Task:
        """Move a task to an allowed lifecycle state."""
        selected_status = self._status(status)

        def transform(task: Task, now: datetime) -> Task:
            if selected_status not in self._ALLOWED_TRANSITIONS[task.status]:
                raise InvalidStateTransitionError(
                    f"Cannot move a task from {task.status.value} "
                    f"to {selected_status.value}."
                )
            completed_at = task.completed_at
            if selected_status is Status.COMPLETED:
                completed_at = now
            elif task.status is Status.COMPLETED:
                completed_at = None
            return self._replace_with_event(
                task,
                "status_changed",
                {"status": selected_status, "completed_at": completed_at},
                now,
            )

        return self._mutate_task(task_id, transform)

    def complete_task(self, task_id: int) -> Task:
        """Complete a pending or in-progress task."""
        return self.transition_task(task_id, Status.COMPLETED)

    def archive_task(self, task_id: int) -> Task:
        """Archive any task that is not already archived."""
        return self.transition_task(task_id, Status.ARCHIVED)

    def advance_task_status(self, task_id: int) -> Task:
        """Advance pending → in-progress → completed."""
        task = self.get_task(task_id)
        next_status = {
            Status.PENDING: Status.IN_PROGRESS,
            Status.IN_PROGRESS: Status.COMPLETED,
        }.get(task.status)
        if next_status is None:
            raise InvalidStateTransitionError(
                f"Task in {task.status.value} cannot be advanced."
            )
        return self.transition_task(task_id, next_status)

    def hard_delete_task(self, task_id: int) -> Task:
        """Remove a task and return its final snapshot with a delete event."""
        self._validate_task_id(task_id)

        def delete(tasks: List[Task]) -> Task:
            index = self._find_index(tasks, task_id)
            task = tasks.pop(index)
            event = self._event(
                task,
                "hard_deleted",
                {"deleted": True},
                include_old=False,
            )
            return replace(
                task,
                updated_at=event.timestamp,
                history=task.history + (event,),
            )

        return self.storage.mutate(delete)

    def promote_priority(self, task_id: int) -> Task:
        """Move the task one step toward critical priority."""
        return self._change_priority(task_id, 1)

    def demote_priority(self, task_id: int) -> Task:
        """Move the task one step toward low priority."""
        return self._change_priority(task_id, -1)

    def add_tag(self, task_id: int, tag: str) -> Task:
        """Add a normalized tag to the task if it is not already present."""
        normalized_tag = normalize_tag(tag)

        def transform(task: Task, now: datetime) -> Task:
            if normalized_tag in task.tags:
                return task
            return self._replace_with_event(
                task,
                "updated",
                {"tags": task.tags + (normalized_tag,)},
                now,
            )

        return self._mutate_task(task_id, transform)

    def remove_tag(self, task_id: int, tag: str) -> Task:
        """Remove a normalized tag, raising ValidationError if absent."""
        normalized_tag = normalize_tag(tag)

        def transform(task: Task, now: datetime) -> Task:
            if normalized_tag not in task.tags:
                raise ValidationError(
                    f"Task does not have tag #{normalized_tag}."
                )
            updated_tags = tuple(
                item for item in task.tags if item != normalized_tag
            )
            return self._replace_with_event(
                task,
                "updated",
                {"tags": updated_tags},
                now,
            )

        return self._mutate_task(task_id, transform)

    def batch_complete(
        self,
        status: Optional[Union[Status, str]] = None,
        priority: Optional[Union[Priority, str]] = None,
    ) -> int:
        """Complete matching tasks in a single storage transaction."""
        return self._bulk_change("complete", status, priority)

    def batch_archive(
        self,
        status: Optional[Union[Status, str]] = None,
        priority: Optional[Union[Priority, str]] = None,
    ) -> int:
        """Archive matching tasks in a single storage transaction."""
        return self._bulk_change("archive", status, priority)

    def batch_delete(
        self,
        status: Optional[Union[Status, str]] = None,
        priority: Optional[Union[Priority, str]] = None,
    ) -> int:
        """Hard-delete matching tasks in a single storage transaction."""
        return self._bulk_change("delete", status, priority)

    def metrics(self) -> TaskMetrics:
        """Compute completion, overdue, priority, and turnaround metrics."""
        tasks = self.storage.load()
        active = [task for task in tasks if task.status is not Status.ARCHIVED]
        completed_count = sum(
            task.status is Status.COMPLETED for task in active
        )
        turnarounds = [
            task.turnaround_days
            for task in active
            if task.turnaround_days is not None
        ]
        distribution = {
            priority.value: sum(task.priority is priority for task in active)
            for priority in Priority
        }
        return {
            "total_tasks": len(tasks),
            "active_tasks": len(active),
            "completion_ratio": (
                completed_count / len(active) if active else 0.0
            ),
            "overdue_count": sum(task.is_overdue for task in active),
            "priority_distribution": distribution,
            "average_turnaround_days": (
                sum(turnarounds) / len(turnarounds) if turnarounds else 0.0
            ),
        }

    def export_json(self, path: Optional[Union[str, Path]] = None) -> str:
        """Return formatted JSON and optionally write it atomically."""
        contents = (
            json.dumps(
                [task.to_dict() for task in self.storage.load()],
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
        if path is not None:
            AtomicJsonStorage.write_text_atomic(path, contents)
        return contents

    def export_csv(self, path: Optional[Union[str, Path]] = None) -> str:
        """Return CSV and optionally atomically write it to a file."""
        output = io.StringIO(newline="")
        fields = (
            "id",
            "title",
            "description",
            "priority",
            "status",
            "category",
            "tags",
            "due_date",
            "created_at",
            "updated_at",
            "completed_at",
        )
        writer = csv.DictWriter(
            output,
            fieldnames=fields,
            lineterminator="\n",
        )
        writer.writeheader()
        for task in self.storage.load():
            record = task.to_dict()
            record["tags"] = ",".join(task.tags)
            writer.writerow({field: record[field] or "" for field in fields})
        contents = output.getvalue()
        if path is not None:
            AtomicJsonStorage.write_text_atomic(path, contents)
        return contents

    def _change_priority(self, task_id: int, direction: int) -> Task:
        def transform(task: Task, now: datetime) -> Task:
            index = self._PRIORITIES.index(task.priority)
            next_index = index + direction
            if not 0 <= next_index < len(self._PRIORITIES):
                raise ValidationError("Task priority is already at its limit.")
            priority = self._PRIORITIES[next_index]
            return self._replace_with_event(
                task,
                "priority_changed",
                {"priority": priority},
                now,
            )

        return self._mutate_task(task_id, transform)

    def _update(
        self, task_id: int, changes: Dict[str, object], action: str
    ) -> Task:
        def transform(task: Task, now: datetime) -> Task:
            return self._replace_with_event(task, action, changes, now)

        return self._mutate_task(task_id, transform)

    def _mutate_task(
        self,
        task_id: int,
        transform: Callable[[Task, datetime], Task],
    ) -> Task:
        self._validate_task_id(task_id)

        def mutate(tasks: List[Task]) -> Task:
            index = self._find_index(tasks, task_id)
            updated = transform(tasks[index], utc_now())
            tasks[index] = updated
            return updated

        return self.storage.mutate(mutate)

    @staticmethod
    def _replace_with_event(
        task: Task,
        action: str,
        changes: Dict[str, object],
        now: datetime,
    ) -> Task:
        effective = {
            field_name: value
            for field_name, value in changes.items()
            if getattr(task, field_name) != value
        }
        if not effective:
            return task
        event = TaskManager._event(task, action, effective, timestamp=now)
        return replace(
            task,
            **cast(Any, effective),
            updated_at=now,
            history=task.history + (event,),
        )

    @staticmethod
    def _event(
        task: Task,
        action: str,
        changes: Dict[str, object],
        include_old: bool = True,
        timestamp: Optional[datetime] = None,
    ) -> AuditEvent:
        diff = tuple(
            (
                field_name,
                json.dumps(
                    (
                        TaskManager._serialize_value(getattr(task, field_name))
                        if include_old
                        else None
                    ),
                    sort_keys=True,
                ),
                json.dumps(
                    TaskManager._serialize_value(value),
                    sort_keys=True,
                ),
            )
            for field_name, value in sorted(changes.items())
        )
        return AuditEvent(timestamp or utc_now(), action, diff)

    @staticmethod
    def _serialize_value(value: object) -> object:
        if isinstance(value, (Priority, Status)):
            return value.value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, tuple):
            return [TaskManager._serialize_value(item) for item in value]
        return value

    def _bulk_change(
        self,
        action: str,
        status: Optional[Union[Status, str]],
        priority: Optional[Union[Priority, str]],
    ) -> int:
        if status is None and priority is None:
            raise ValidationError(
                "Select a status or priority for a batch operation."
            )
        selected_status = self._status(status) if status is not None else None
        selected_priority = (
            self._priority(priority) if priority is not None else None
        )
        now = utc_now()

        def mutate(tasks: List[Task]) -> int:
            selected = [
                task
                for task in tasks
                if (selected_status is None or task.status is selected_status)
                and (
                    selected_priority is None
                    or task.priority is selected_priority
                )
            ]
            if action == "delete":
                selected_ids = {task.id for task in selected}
                tasks[:] = [
                    task for task in tasks if task.id not in selected_ids
                ]
                return len(selected)

            changed = 0
            selected_ids = {task.id for task in selected}
            for index, task in enumerate(tasks):
                if task.id not in selected_ids:
                    continue
                if action == "complete" and task.status not in {
                    Status.COMPLETED,
                    Status.ARCHIVED,
                }:
                    tasks[index] = self._replace_with_event(
                        task,
                        "status_changed",
                        {"status": Status.COMPLETED, "completed_at": now},
                        now,
                    )
                    changed += 1
                elif (
                    action == "archive" and task.status is not Status.ARCHIVED
                ):
                    tasks[index] = self._replace_with_event(
                        task,
                        "status_changed",
                        {"status": Status.ARCHIVED},
                        now,
                    )
                    changed += 1
            return changed

        return self.storage.mutate(mutate)

    @classmethod
    def _sort_tasks(
        cls,
        tasks: List[Task],
        sort_by: str,
        descending: bool,
    ) -> List[Task]:
        if sort_by == "due_date":
            dated = [task for task in tasks if task.due_date is not None]
            undated = [task for task in tasks if task.due_date is None]
            dated.sort(
                key=lambda task: cast(datetime, task.due_date),
                reverse=descending,
            )
            return dated + undated
        if sort_by == "priority_rank":
            priorities = {
                priority: index
                for index, priority in enumerate(cls._PRIORITIES)
            }
            return sorted(
                tasks,
                key=lambda task: priorities[task.priority],
                reverse=descending,
            )
        return sorted(
            tasks,
            key=lambda task: (
                getattr(task, sort_by).casefold()
                if sort_by == "title"
                else getattr(task, sort_by)
            ),
            reverse=descending,
        )

    @staticmethod
    def _matches_query(task: Task, query: str) -> bool:
        fields = (
            task.title.casefold(),
            task.description.casefold(),
            *task.tags,
        )
        if any(query in field for field in fields):
            return True
        query_terms = query.split()
        if all(any(term in field for field in fields) for term in query_terms):
            return True
        return len(query) >= 3 and any(
            SequenceMatcher(None, query, field).ratio() >= 0.72
            for field in fields
        )

    @staticmethod
    def _required_text(value: object, label: str, maximum: int) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"{label} must not be empty.")
        cleaned = value.strip()
        if len(cleaned) > maximum:
            raise ValidationError(
                f"{label} must be {maximum} characters or fewer."
            )
        return cleaned

    @staticmethod
    def _optional_text(value: object, label: str, maximum: int) -> str:
        if not isinstance(value, str):
            raise ValidationError(f"{label} must be a string.")
        cleaned = value.strip()
        if len(cleaned) > maximum:
            raise ValidationError(
                f"{label} must be {maximum} characters or fewer."
            )
        return cleaned

    @staticmethod
    def _priority(value: object) -> Priority:
        try:
            return value if isinstance(value, Priority) else Priority(value)
        except (ValueError, TypeError) as error:
            raise ValidationError(
                "Priority must be low, medium, high, or critical."
            ) from error

    @staticmethod
    def _status(value: object) -> Status:
        try:
            return value if isinstance(value, Status) else Status(value)
        except (ValueError, TypeError) as error:
            raise ValidationError(
                "Status must be pending, in_progress, completed, or archived."
            ) from error

    @staticmethod
    def _tags(values: object) -> tuple[str, ...]:
        if isinstance(values, str):
            values = (values,)
        if not isinstance(values, Iterable):
            raise ValidationError("Tags must be an iterable of strings.")
        try:
            return tuple(
                dict.fromkeys(normalize_tag(value) for value in values)
            )
        except TypeError as error:
            raise ValidationError(
                "Tags must be an iterable of strings."
            ) from error

    @staticmethod
    def _validate_task_id(task_id: int) -> None:
        if (
            isinstance(task_id, bool)
            or not isinstance(task_id, int)
            or task_id < 1
        ):
            raise ValidationError("Task ID must be a positive integer.")

    @staticmethod
    def _find_index(tasks: List[Task], task_id: int) -> int:
        for index, task in enumerate(tasks):
            if task.id == task_id:
                return index
        raise TaskNotFoundError(f"Task {task_id} was not found.")
