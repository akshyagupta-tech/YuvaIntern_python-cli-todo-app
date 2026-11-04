"""Lifecycle, persistence, search, export, and metrics tests."""

import csv
import json
import re
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from pathlib import Path

from engine import TaskManager
from cli import format_task_table
from models import (
    InvalidStateTransitionError,
    Priority,
    Status,
    TaskNotFoundError,
    ValidationError,
)
from storage import StorageError


class TaskManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage_path = Path(self.temp_dir.name) / "tasks.json"
        self.manager = TaskManager(self.storage_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_create_persists_immutable_normalized_task(self) -> None:
        task = self.manager.create_task(
            "  Ship search  ",
            "  Implement search API ",
            Priority.HIGH,
            "Engineering",
            ["#Backend", "urgent", "backend"],
        )

        self.assertEqual(task.title, "Ship search")
        self.assertEqual(task.description, "Implement search API")
        self.assertEqual(task.tags, ("backend", "urgent"))
        self.assertEqual(task.priority, Priority.HIGH)
        self.assertEqual(task.status, Status.PENDING)
        self.assertEqual(task.history[0].action, "created")
        with self.assertRaises(FrozenInstanceError):
            task.title = "changed"  # type: ignore[misc]
        self.assertEqual(
            TaskManager(self.storage_path).get_task(task.id), task
        )

    def test_create_rejects_empty_fields_bad_tags_and_bad_due_dates(
        self,
    ) -> None:
        for title in ("", "  ", None):
            with self.subTest(title=title):
                with self.assertRaises(ValidationError):
                    self.manager.create_task(title)  # type: ignore[arg-type]
        with self.assertRaises(ValidationError):
            self.manager.create_task("Valid", tags=["has spaces"])
        with self.assertRaises(ValidationError):
            self.manager.create_task("Valid", due_date="not a date")

    def test_update_appends_immutable_field_diff(self) -> None:
        task = self.manager.create_task("Initial")
        updated = self.manager.update_task(
            task.id,
            title="Revised",
            description="New details",
            priority="critical",
        )

        self.assertEqual(updated.title, "Revised")
        self.assertEqual(updated.priority, Priority.CRITICAL)
        self.assertEqual(len(updated.history), 2)
        self.assertEqual(updated.history[-1].action, "updated")
        diff = {
            item[0]: (item[1], item[2]) for item in updated.history[-1].diff
        }
        self.assertEqual(json.loads(diff["title"][0]), "Initial")
        self.assertEqual(json.loads(diff["title"][1]), "Revised")

    def test_update_rejects_unknown_fields_and_invalid_values(self) -> None:
        task = self.manager.create_task("Initial")
        with self.assertRaises(ValidationError):
            self.manager.update_task(task.id, unknown="value")
        with self.assertRaises(ValidationError):
            self.manager.update_task(task.id, title=" ")
        with self.assertRaises(ValidationError):
            self.manager.update_task(task.id, due_date="2026-99-99")

    def test_status_lifecycle_and_invalid_transitions(self) -> None:
        task = self.manager.create_task("Lifecycle")
        in_progress = self.manager.advance_task_status(task.id)
        completed = self.manager.advance_task_status(task.id)
        self.assertEqual(in_progress.status, Status.IN_PROGRESS)
        self.assertEqual(completed.status, Status.COMPLETED)
        self.assertIsNotNone(completed.completed_at)

        reopened = self.manager.transition_task(task.id, Status.IN_PROGRESS)
        self.assertIsNone(reopened.completed_at)
        archived = self.manager.archive_task(task.id)
        self.assertEqual(archived.status, Status.ARCHIVED)
        with self.assertRaises(InvalidStateTransitionError):
            self.manager.complete_task(task.id)
        self.assertEqual(
            self.manager.transition_task(task.id, Status.PENDING).status,
            Status.PENDING,
        )

    def test_missing_task_errors_and_hard_delete_event(self) -> None:
        task = self.manager.create_task("Delete me")
        deleted = self.manager.hard_delete_task(task.id)

        self.assertEqual(deleted.history[-1].action, "hard_deleted")
        self.assertEqual(self.manager.list_tasks(), [])
        with self.assertRaises(TaskNotFoundError):
            self.manager.get_task(task.id)
        with self.assertRaises(TaskNotFoundError):
            self.manager.archive_task(500)
        with self.assertRaises(ValidationError):
            self.manager.get_task(True)  # type: ignore[arg-type]

    def test_priority_promotion_and_demotion_boundaries(self) -> None:
        task = self.manager.create_task("Priority", priority=Priority.MEDIUM)
        high = self.manager.promote_priority(task.id)
        critical = self.manager.promote_priority(task.id)
        self.assertEqual(high.priority, Priority.HIGH)
        self.assertEqual(critical.priority, Priority.CRITICAL)
        with self.assertRaises(ValidationError):
            self.manager.promote_priority(task.id)
        self.assertEqual(
            self.manager.demote_priority(task.id).priority, Priority.HIGH
        )
        low = self.manager.demote_priority(task.id)
        low = self.manager.demote_priority(task.id)
        self.assertEqual(low.priority, Priority.LOW)
        with self.assertRaises(ValidationError):
            self.manager.demote_priority(task.id)

    def test_tagging_and_multifield_fuzzy_search(self) -> None:
        task = self.manager.create_task(
            "Build Search",
            "Implement a title and description index",
            tags=["backend"],
        )
        self.manager.add_tag(task.id, "#Urgent")
        self.assertEqual(len(self.manager.list_tasks(tag="#URGENT")), 1)
        self.assertEqual(
            len(self.manager.list_tasks(query="description index")), 1
        )
        self.assertEqual(len(self.manager.list_tasks(query="Build Searh")), 1)
        self.assertEqual(
            self.manager.remove_tag(task.id, "urgent").tags, ("backend",)
        )
        with self.assertRaises(ValidationError):
            self.manager.remove_tag(task.id, "missing")

    def test_due_date_alerts_and_dynamic_overdue_detection(self) -> None:
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        task = self.manager.create_task("Late", due_date=yesterday.isoformat())

        self.assertTrue(task.is_overdue)
        self.assertEqual(task.due_alert, "Overdue")
        self.assertEqual(len(self.manager.list_tasks(overdue=True)), 1)
        completed = self.manager.complete_task(task.id)
        self.assertFalse(completed.is_overdue)
        self.assertEqual(completed.due_alert, None)
        self.assertIsNone(
            self.manager.create_task("No due date").days_remaining
        )
        due_today = self.manager.create_task(
            "Due today",
            due_date=datetime.now(timezone.utc).date(),
        )
        self.assertEqual(due_today.due_alert, "Due today")

    def test_sorting_on_supported_fields(self) -> None:
        due_later = (
            datetime.now(timezone.utc) + timedelta(days=4)
        ).isoformat()
        due_soon = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        first = self.manager.create_task(
            "Zulu", priority="low", due_date=due_later
        )
        second = self.manager.create_task(
            "Alpha", priority="critical", due_date=due_soon
        )
        third = self.manager.create_task("Middle", priority="high")

        self.assertEqual(
            [task.id for task in self.manager.list_tasks(sort_by="title")],
            [second.id, third.id, first.id],
        )
        self.assertEqual(
            [task.id for task in self.manager.list_tasks(sort_by="due_date")],
            [second.id, first.id, third.id],
        )
        self.assertEqual(
            [
                task.id
                for task in self.manager.list_tasks(sort_by="priority_rank")
            ],
            [first.id, third.id, second.id],
        )
        with self.assertRaises(ValidationError):
            self.manager.list_tasks(sort_by="description")

    def test_bulk_complete_archive_and_delete_by_filters(self) -> None:
        low_a = self.manager.create_task("A", priority="low")
        low_b = self.manager.create_task("B", priority="low")
        high = self.manager.create_task("C", priority="high")

        with self.assertRaises(ValidationError):
            self.manager.batch_delete()
        self.assertEqual(self.manager.batch_complete(priority="low"), 2)
        self.assertEqual(self.manager.batch_archive(status="completed"), 2)
        self.assertEqual(self.manager.batch_delete(priority="high"), 1)
        remaining = self.manager.list_tasks()
        self.assertEqual(len(remaining), 2)
        self.assertTrue(
            all(task.status is Status.ARCHIVED for task in remaining)
        )
        self.assertNotEqual(low_a.id, low_b.id)
        self.assertNotEqual(high.id, low_a.id)

    def test_cli_color_codes_do_not_break_table_alignment(self) -> None:
        self.manager.create_task("A shorter title", priority=Priority.CRITICAL)
        self.manager.create_task("A substantially longer task title")

        rendered = format_task_table(self.manager.list_tasks(), color=True)
        clean_lines = [
            re.sub(r"\033\[[0-9;]*m", "", line)
            for line in rendered.splitlines()
        ]

        self.assertEqual(len({len(line) for line in clean_lines}), 1)

    def test_metrics_and_completion_turnaround(self) -> None:
        late_date = datetime.now(timezone.utc) - timedelta(days=2)
        late = self.manager.create_task("Late", due_date=late_date.isoformat())
        completed = self.manager.create_task("Done", priority="high")
        self.manager.complete_task(completed.id)

        summary = self.manager.metrics()
        self.assertEqual(summary["total_tasks"], 2)
        self.assertEqual(summary["active_tasks"], 2)
        self.assertEqual(summary["completion_ratio"], 0.5)
        self.assertEqual(summary["overdue_count"], 1)
        self.assertEqual(summary["priority_distribution"]["high"], 1)
        self.assertGreaterEqual(summary["average_turnaround_days"], 0)
        self.assertTrue(self.manager.get_task(late.id).is_overdue)

    def test_json_and_csv_exports_are_formatted_and_writable(self) -> None:
        self.manager.create_task("Export task", tags=["csv", "json"])
        json_path = Path(self.temp_dir.name) / "export.json"
        csv_path = Path(self.temp_dir.name) / "export.csv"

        json_text = self.manager.export_json(json_path)
        csv_text = self.manager.export_csv(csv_path)
        self.assertEqual(json.loads(json_text)[0]["title"], "Export task")
        self.assertEqual(json_path.read_text(encoding="utf-8"), json_text)
        csv_rows = list(csv.DictReader(csv_text.splitlines()))
        self.assertEqual(csv_rows[0]["title"], "Export task")
        self.assertEqual(csv_path.read_text(encoding="utf-8"), csv_text)

    def test_schema_migration_from_legacy_task_array(self) -> None:
        legacy = [
            {
                "id": 9,
                "title": "Old task",
                "priority": "High",
                "category": "Work",
                "due_date": "",
                "completed": True,
            }
        ]
        self.storage_path.write_text(json.dumps(legacy), encoding="utf-8")

        migrated = self.manager.get_task(9)
        payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        self.assertEqual(migrated.priority, Priority.HIGH)
        self.assertEqual(migrated.status, Status.COMPLETED)
        self.assertEqual(payload["schema_version"], 2)

    def test_corrupted_storage_fails_with_storage_error(self) -> None:
        self.storage_path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(StorageError):
            self.manager.list_tasks()

    def test_separate_managers_allocate_unique_ids(self) -> None:
        first = self.manager.create_task("First")
        second = TaskManager(self.storage_path).create_task("Second")
        self.assertEqual((first.id, second.id), (1, 2))


if __name__ == "__main__":
    unittest.main()
