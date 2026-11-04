"""Interactive and argument-driven CLI for Enterprise Task Engine."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional, Sequence

from engine import TaskManager
from models import (
    InvalidStateTransitionError,
    Priority,
    Status,
    Task,
    TaskNotFoundError,
    ValidationError,
)
from storage import StorageError

_COLORS = {
    "reset": "\033[0m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "cyan": "\033[36m",
}


def _paint(value: str, color: str, enabled: bool) -> str:
    if not enabled:
        return value
    return f"{_COLORS[color]}{value}{_COLORS['reset']}"


def format_task_table(tasks: Sequence[Task], color: bool = True) -> str:
    """Return a structured, aligned ASCII table of tasks."""
    headers = (
        "ID",
        "STATUS",
        "PRIORITY",
        "CATEGORY",
        "DUE",
        "TITLE",
        "TAGS",
    )
    rows = [
        (
            str(task.id),
            f"[{task.status.value.replace('_', ' ').upper()}]",
            task.priority.value.upper(),
            task.category,
            task.due_date.date().isoformat() if task.due_date else "-",
            task.title,
            ", ".join(f"#{tag}" for tag in task.tags) or "-",
        )
        for task in tasks
    ]
    widths = [
        (
            max(len(headers[index]), *(len(row[index]) for row in rows))
            if rows
            else len(headers[index])
        )
        for index in range(len(headers))
    ]

    def format_row(row: Sequence[str]) -> str:
        cells = []
        for index, value in enumerate(row):
            cell = value.ljust(widths[index])
            if index == 1:
                cell = _paint(
                    cell,
                    "green" if value == "[COMPLETED]" else "yellow",
                    color,
                )
            elif index == 2:
                cell = _paint(
                    cell,
                    "red" if value == "CRITICAL" else "cyan",
                    color,
                )
            cells.append(cell)
        return " | ".join(cells)

    divider = "-+-".join("-" * width for width in widths)
    lines = [format_row(headers), divider]
    for row in rows:
        lines.append(format_row(row))
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="enterprise-task-engine",
        description="Manage durable tasks from the terminal.",
    )
    parser.add_argument(
        "--data",
        default=os.environ.get("TASK_ENGINE_DATA", "tasks.json"),
        help="Path to the JSON task store (default: tasks.json).",
    )
    commands = parser.add_subparsers(dest="command")

    create = commands.add_parser("create", help="Create a task.")
    create.add_argument("title")
    create.add_argument("--description", default="")
    create.add_argument("--category", default="General")
    create.add_argument(
        "--priority",
        choices=[item.value for item in Priority],
        default="medium",
    )
    create.add_argument("--due-date")
    create.add_argument("--tag", action="append", default=[])

    listing = commands.add_parser("list", help="List, search, and sort tasks.")
    listing.add_argument("--status", choices=[item.value for item in Status])
    listing.add_argument(
        "--priority", choices=[item.value for item in Priority]
    )
    listing.add_argument("--tag")
    listing.add_argument("--query")
    listing.add_argument("--overdue", action="store_true", default=None)
    listing.add_argument(
        "--sort",
        choices=sorted(TaskManager._SORT_KEYS),
        default="created_at",
    )
    listing.add_argument("--desc", action="store_true")
    listing.add_argument("--hide-archived", action="store_true")

    update = commands.add_parser("update", help="Update task fields.")
    update.add_argument("task_id", type=int)
    update.add_argument("--title")
    update.add_argument("--description")
    update.add_argument("--category")
    update.add_argument(
        "--priority", choices=[item.value for item in Priority]
    )
    update.add_argument("--due-date")
    update.add_argument("--clear-due-date", action="store_true")

    for name, help_text in (
        ("complete", "Complete a task."),
        ("archive", "Archive a task."),
        ("delete", "Permanently delete a task."),
        ("promote", "Increase task priority."),
        ("demote", "Decrease task priority."),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("task_id", type=int)

    transition = commands.add_parser("transition", help="Set a task status.")
    transition.add_argument("task_id", type=int)
    transition.add_argument("status", choices=[item.value for item in Status])

    tag = commands.add_parser("tag", help="Add or remove a task tag.")
    tag.add_argument("action", choices=("add", "remove"))
    tag.add_argument("task_id", type=int)
    tag.add_argument("value")

    batch = commands.add_parser(
        "batch", help="Apply an operation to matching tasks."
    )
    batch.add_argument("action", choices=("complete", "archive", "delete"))
    batch.add_argument("--status", choices=[item.value for item in Status])
    batch.add_argument("--priority", choices=[item.value for item in Priority])

    export = commands.add_parser("export", help="Export tasks to JSON or CSV.")
    export.add_argument("format", choices=("json", "csv"))
    export.add_argument("path")

    commands.add_parser("metrics", help="Show task metrics.")
    return parser


def _interactive(manager: TaskManager) -> int:
    while True:
        print("\nEnterprise Task Engine")
        print("1. List tasks  2. Create  3. Complete  4. Archive")
        print("5. Hard delete  6. Metrics  7. Exit")
        choice = input("Select an action: ").strip()
        try:
            if choice == "1":
                tasks = manager.list_tasks(sort_by="created_at")
                print(format_task_table(tasks) if tasks else "No tasks found.")
            elif choice == "2":
                title = input("Title: ")
                description = input("Description: ")
                task = manager.create_task(title, description)
                print(f"Created task {task.id}.")
            elif choice in {"3", "4", "5"}:
                task_id = int(input("Task ID: ").strip())
                if choice == "3":
                    manager.complete_task(task_id)
                    print("Task completed.")
                elif choice == "4":
                    manager.archive_task(task_id)
                    print("Task archived.")
                else:
                    manager.hard_delete_task(task_id)
                    print("Task deleted.")
            elif choice == "6":
                for key, value in manager.metrics().items():
                    print(f"{key}: {value}")
            elif choice == "7":
                return 0
            else:
                print("Choose a number from 1 to 7.")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        except (ValueError, TaskNotFoundError, StorageError) as error:
            print(_paint(str(error), "red", True))


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the selected CLI command or enter interactive mode."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    if not arguments:
        return _interactive(TaskManager())

    args = parser.parse_args(arguments)
    manager = TaskManager(args.data)
    try:
        if args.command == "create":
            task = manager.create_task(
                args.title,
                args.description,
                args.priority,
                args.category,
                args.tag,
                args.due_date,
            )
            print(f"Created task {task.id}: {task.title}")
        elif args.command == "list":
            tasks = manager.list_tasks(
                status=args.status,
                priority=args.priority,
                tag=args.tag,
                query=args.query,
                overdue=args.overdue,
                sort_by=args.sort,
                descending=args.desc,
                include_archived=not args.hide_archived,
            )
            print(format_task_table(tasks) if tasks else "No tasks found.")
        elif args.command == "update":
            changes = {
                key: value
                for key, value in {
                    "title": args.title,
                    "description": args.description,
                    "category": args.category,
                    "priority": args.priority,
                }.items()
                if value is not None
            }
            if args.clear_due_date:
                changes["due_date"] = None
            elif args.due_date is not None:
                changes["due_date"] = args.due_date
            task = manager.update_task(args.task_id, **changes)
            print(f"Updated task {task.id}.")
        elif args.command == "complete":
            manager.complete_task(args.task_id)
            print(f"Completed task {args.task_id}.")
        elif args.command == "archive":
            manager.archive_task(args.task_id)
            print(f"Archived task {args.task_id}.")
        elif args.command == "delete":
            manager.hard_delete_task(args.task_id)
            print(f"Deleted task {args.task_id}.")
        elif args.command == "transition":
            manager.transition_task(args.task_id, args.status)
            print(f"Moved task {args.task_id} to {args.status}.")
        elif args.command == "promote":
            task = manager.promote_priority(args.task_id)
            print(f"Priority for task {task.id}: {task.priority.value}.")
        elif args.command == "demote":
            task = manager.demote_priority(args.task_id)
            print(f"Priority for task {task.id}: {task.priority.value}.")
        elif args.command == "tag":
            method = (
                manager.add_tag if args.action == "add" else manager.remove_tag
            )
            task = method(args.task_id, args.value)
            print(f"Tags for task {task.id}: {', '.join(task.tags) or '-'}.")
        elif args.command == "batch":
            if args.action == "complete":
                count = manager.batch_complete(
                    status=args.status,
                    priority=args.priority,
                )
            elif args.action == "archive":
                count = manager.batch_archive(
                    status=args.status,
                    priority=args.priority,
                )
            else:
                count = manager.batch_delete(
                    status=args.status,
                    priority=args.priority,
                )
            print(f"{args.action.title()}d {count} task(s).")
        elif args.command == "export":
            contents = (
                manager.export_json(args.path)
                if args.format == "json"
                else manager.export_csv(args.path)
            )
            print(f"Exported {len(contents)} characters to {args.path}.")
        elif args.command == "metrics":
            for key, value in manager.metrics().items():
                print(f"{key}: {value}")
        return 0
    except (
        ValidationError,
        InvalidStateTransitionError,
        TaskNotFoundError,
    ) as error:
        print(_paint(f"Error: {error}", "red", True), file=sys.stderr)
        return 2
    except (OSError, StorageError) as error:
        print(_paint(f"Storage error: {error}", "red", True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
