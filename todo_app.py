"""
Advanced CLI To-Do List Manager
Features: Priority levels, due dates, categorisation, search/filter, and ANSI colors.
"""

import json
import os
import sys
from datetime import datetime

# ANSI Color codes for clean terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


class Task:
    """Encapsulates task details including priority, category, and due date."""
    def __init__(self, task_id: int, title: str, priority: str = "Medium", 
                 category: str = "General", due_date: str = "", completed: bool = False):
        self.task_id = task_id
        self.title = title
        self.priority = priority.capitalize()
        self.category = category.capitalize()
        self.due_date = due_date
        self.completed = completed

    def mark_complete(self):
        self.completed = True

    def to_dict(self):
        return {
            "id": self.task_id,
            "title": self.title,
            "priority": self.priority,
            "category": self.category,
            "due_date": self.due_date,
            "completed": self.completed
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            data["id"], 
            data["title"], 
            data.get("priority", "Medium"),
            data.get("category", "General"),
            data.get("due_date", ""),
            data.get("completed", False)
        )


class AdvancedTodoManager:
    """Handles advanced business logic, searching, filtering, and persistence."""
    def __init__(self, filename="tasks.json"):
        self.filename = filename
        self.tasks = []
        self.load_tasks()

    def load_tasks(self):
        if not os.path.exists(self.filename):
            self.tasks = []
            return
        try:
            with open(self.filename, "r") as file:
                data = json.load(file)
                self.tasks = [Task.from_dict(item) for item in data]
        except (json.JSONDecodeError, IOError):
            print(f"{YELLOW}[Notice] Error reading data. Initializing clean task list.{RESET}")
            self.tasks = []

    def save_tasks(self):
        try:
            with open(self.filename, "w") as file:
                json.dump([task.to_dict() for task in self.tasks], file, indent=4)
        except IOError as err:
            print(f"{RED}[Error] Could not save tasks: {err}{RESET}")

    def add_task(self, title: str, priority: str, category: str, due_date: str):
        title = title.strip()
        if not title:
            print(f"{RED}[Error] Task description cannot be blank.{RESET}")
            return
        next_id = (self.tasks[-1].task_id + 1) if self.tasks else 1
        new_task = Task(next_id, title, priority, category, due_date)
        self.tasks.append(new_task)
        self.save_tasks()
        print(f"{GREEN}[Success] Task #{next_id} added successfully!{RESET}")

    def display_task_table(self, task_list):
        if not task_list:
            print(f"{YELLOW}\nNo tasks found.{RESET}")
            return

        print("\n" + "=" * 80)
        print(f"{BOLD}{'ID':<5} {'Status':<12} {'Priority':<10} {'Category':<12} {'Due Date':<12} {'Description'}{RESET}")
        print("-" * 80)
        for task in task_list:
            status = f"{GREEN}[✓] Done{RESET}" if task.completed else f"{YELLOW}[ ] Pending{RESET}"
            
            p_color = RED if task.priority == "High" else (YELLOW if task.priority == "Medium" else CYAN)
            priority_display = f"{p_color}{task.priority:<10}{RESET}"
            
            due = task.due_date if task.due_date else "-"
            print(f"{task.task_id:<5} {status:<21} {priority_display} {task.category:<12} {due:<12} {task.title}")
        print("=" * 80 + "\n")

    def view_all_tasks(self):
        self.display_task_table(self.tasks)

    def search_tasks(self, query: str):
        query = query.lower().strip()
        matched = [t for t in self.tasks if query in t.title.lower() or query in t.category.lower()]
        self.display_task_table(matched)

    def filter_by_status(self, show_completed: bool):
        filtered = [t for t in self.tasks if t.completed == show_completed]
        self.display_task_table(filtered)

    def mark_complete(self, task_id: int):
        for task in self.tasks:
            if task.task_id == task_id:
                if task.completed:
                    print(f"{YELLOW}[Info] Task #{task_id} is already marked complete.{RESET}")
                else:
                    task.mark_complete()
                    self.save_tasks()
                    print(f"{GREEN}[Success] Task #{task_id} marked as completed!{RESET}")
                return
        print(f"{RED}[Error] Task ID #{task_id} not found.{RESET}")

    def remove_task(self, task_id: int):
        for index, task in enumerate(self.tasks):
            if task.task_id == task_id:
                deleted = self.tasks.pop(index)
                self.save_tasks()
                print(f"{GREEN}[Success] Deleted Task #{task_id}: '{deleted.title}'{RESET}")
                return
        print(f"{RED}[Error] Task ID #{task_id} not found.{RESET}")


def get_numeric_input(prompt: str) -> int:
    while True:
        raw = input(prompt).strip()
        try:
            return int(raw)
        except ValueError:
            print(f"{RED}[Invalid] Please provide a valid integer.{RESET}")


def main():
    manager = AdvancedTodoManager()

    while True:
        print(f"\n{BOLD}=== ADVANCED TASK MANAGER ==={RESET}")
        print("1. View All Tasks")
        print("2. Add New Task (With Priority & Category)")
        print("3. Search Tasks (Keyword / Category)")
        print("4. Filter (Pending / Completed)")
        print("5. Mark Task Complete")
        print("6. Delete Task")
        print("7. Exit")

        choice = input("Enter choice (1-7): ").strip()

        try:
            if choice == "1":
                manager.view_all_tasks()
            elif choice == "2":
                title = input("Description: ")
                priority = input("Priority (High/Medium/Low) [Default: Medium]: ").strip() or "Medium"
                category = input("Category (Work/Study/Personal) [Default: General]: ").strip() or "General"
                due = input("Due Date (YYYY-MM-DD) [Optional]: ").strip()
                manager.add_task(title, priority, category, due)
            elif choice == "3":
                q = input("Search title or category: ")
                manager.search_tasks(q)
            elif choice == "4":
                print("1. View Pending Tasks Only")
                print("2. View Completed Tasks Only")
                f_choice = input("Choose (1/2): ").strip()
                manager.filter_by_status(show_completed=(f_choice == "2"))
            elif choice == "5":
                t_id = get_numeric_input("Enter Task ID to complete: ")
                manager.mark_complete(t_id)
            elif choice == "6":
                t_id = get_numeric_input("Enter Task ID to delete: ")
                manager.remove_task(t_id)
            elif choice == "7":
                print(f"{CYAN}Exiting task manager. Goodbye!{RESET}")
                sys.exit(0)
            else:
                print(f"{RED}[Invalid] Enter a number from 1 to 7.{RESET}")
        except KeyboardInterrupt:
            print(f"\n{YELLOW}[Notice] Action interrupted. Back to menu.{RESET}")


if __name__ == "__main__":
    main()
