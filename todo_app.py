"""
CLI To-Do List Manager
A modular, object-oriented command-line task manager with JSON storage.
"""

import json
import os
import sys

class Task:
    """Encapsulates a task item with id, description, and status."""
    def __init__(self, task_id: int, title: str, completed: bool = False):
        self.task_id = task_id
        self.title = title
        self.completed = completed

    def mark_complete(self):
        self.completed = True

    def to_dict(self):
        return {
            "id": self.task_id,
            "title": self.title,
            "completed": self.completed,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(data["id"], data["title"], data.get("completed", False))


class TodoManager:
    """Handles task operations and file persistence."""
    def __init__(self, filename="tasks.json"):
        self.filename = filename
        self.tasks = []
        self.load_tasks()

    def load_tasks(self):
        """Loads existing tasks safely from local storage."""
        if not os.path.exists(self.filename):
            self.tasks = []
            return
        try:
            with open(self.filename, "r") as file:
                data = json.load(file)
                self.tasks = [Task.from_dict(item) for item in data]
        except (json.JSONDecodeError, IOError):
            print("[Notice] Could not parse existing tasks file. Initializing empty list.")
            self.tasks = []

    def save_tasks(self):
        """Persists current state to JSON."""
        try:
            with open(self.filename, "w") as file:
                json.dump([task.to_dict() for task in self.tasks], file, indent=4)
        except IOError as err:
            print(f"[Error] Failed to save tasks: {err}")

    def add_task(self, title: str):
        clean_title = title.strip()
        if not clean_title:
            print("[Error] Task description cannot be blank.")
            return
        next_id = (self.tasks[-1].task_id + 1) if self.tasks else 1
        self.tasks.append(Task(next_id, clean_title))
        self.save_tasks()
        print(f"[Success] Added task #{next_id}: '{clean_title}'")

    def view_tasks(self):
        if not self.tasks:
            print("\nYour to-do list is empty.")
            return
        print("\n" + "-" * 50)
        print(f"{'ID':<6} {'Status':<12} {'Description'}")
        print("-" * 50)
        for task in self.tasks:
            status = "[✓] Done" if task.completed else "[ ] Pending"
            print(f"{task.task_id:<6} {status:<12} {task.title}")
        print("-" * 50 + "\n")

    def mark_task_complete(self, task_id: int):
        for task in self.tasks:
            if task.task_id == task_id:
                if task.completed:
                    print(f"[Info] Task #{task_id} is already completed.")
                else:
                    task.mark_complete()
                    self.save_tasks()
                    print(f"[Success] Task #{task_id} marked as completed.")
                return
        print(f"[Error] Task with ID #{task_id} does not exist.")

    def remove_task(self, task_id: int):
        for i, task in enumerate(self.tasks):
            if task.task_id == task_id:
                removed = self.tasks.pop(i)
                self.save_tasks()
                print(f"[Success] Removed task #{task_id}: '{removed.title}'")
                return
        print(f"[Error] Task with ID #{task_id} does not exist.")


def prompt_integer(prompt: str) -> int:
    """Ensures robust numeric input without application crashes."""
    while True:
        val = input(prompt).strip()
        try:
            return int(val)
        except ValueError:
            print("[Invalid Input] Please enter a valid number.")


def main():
    manager = TodoManager()
    while True:
        print("\n=== TO-DO LIST MANAGER ===")
        print("1. View Tasks")
        print("2. Add Task")
        print("3. Mark Task as Complete")
        print("4. Remove Task")
        print("5. Exit")

        choice = input("Enter choice (1-5): ").strip()

        try:
            if choice == "1":
                manager.view_tasks()
            elif choice == "2":
                title = input("Enter task description: ")
                manager.add_task(title)
            elif choice == "3":
                task_id = prompt_integer("Enter Task ID: ")
                manager.mark_task_complete(task_id)
            elif choice == "4":
                task_id = prompt_integer("Enter Task ID to remove: ")
                manager.remove_task(task_id)
            elif choice == "5":
                print("Exiting application. Goodbye!")
                sys.exit(0)
            else:
                print("[Invalid Choice] Please select an option from 1 to 5.")
        except KeyboardInterrupt:
            print("\n[Notice] Operation cancelled. Returning to main menu.")


if __name__ == "__main__":
    main()
