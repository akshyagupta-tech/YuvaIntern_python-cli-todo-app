"""Unit tests for the Week 1 task management engine."""

import unittest

from core.week1_tasks import TaskManager


class TestTaskManager(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = TaskManager()

    def test_add_task_assigns_id_and_strips_fields(self) -> None:
        task = self.manager.add_task("  Write tests  ", "  Work  ", "High")

        self.assertEqual(task.id, 1)
        self.assertEqual(task.title, "Write tests")
        self.assertEqual(task.category, "Work")
        self.assertEqual(task.priority, "High")
        self.assertFalse(task.completed)

    def test_add_task_rejects_empty_or_non_string_title(self) -> None:
        for title in ("", "   ", None):
            with self.subTest(title=title):
                with self.assertRaises(ValueError):
                    self.manager.add_task(title)  # type: ignore[arg-type]

    def test_add_task_rejects_invalid_priority(self) -> None:
        for priority in ("urgent", "high", "", None, []):
            with self.subTest(priority=priority):
                with self.assertRaises(ValueError):
                    self.manager.add_task(
                        "Review",
                        priority=priority,  # type: ignore[arg-type]
                    )

    def test_toggle_and_filter_by_status(self) -> None:
        task = self.manager.add_task("Review")

        self.assertTrue(self.manager.toggle_task(task.id))
        self.assertEqual(self.manager.filter_by_status(True), [task])
        self.assertEqual(self.manager.filter_by_status(False), [])
        self.assertFalse(self.manager.toggle_task(99))
        with self.assertRaises(ValueError):
            self.manager.filter_by_status(1)  # type: ignore[arg-type]

    def test_delete_task_and_missing_task(self) -> None:
        task = self.manager.add_task("Remove me")

        self.assertTrue(self.manager.delete_task(task.id))
        self.assertEqual(self.manager.list_tasks(), [])
        self.assertFalse(self.manager.delete_task(task.id))
        with self.assertRaises(ValueError):
            self.manager.delete_task(0)


if __name__ == "__main__":
    unittest.main()