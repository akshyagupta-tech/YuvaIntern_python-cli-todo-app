"""A simple command-line task manager."""

from dataclasses import dataclass


@dataclass
class Task:
    """Represent a single task."""

    id: int
    title: str
    completed: bool = False


class TaskManager:
    """Manage tasks in memory."""

    def __init__(self) -> None:
        self._tasks: list[Task] = []
        self._next_id = 1

    def add_task(self, title: str) -> Task:
        """Add a task with a non-empty title and return it."""
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Task title must not be empty.")

        task = Task(id=self._next_id, title=title.strip())
        self._tasks.append(task)
        self._next_id += 1
        return task

    def list_tasks(self) -> list[Task]:
        """Return a copy of the current task list."""
        return self._tasks.copy()

    def complete_task(self, task_id: int) -> bool:
        """Mark a task complete; return whether its ID was found."""
        self._validate_task_id(task_id)
        task = self._find_task(task_id)
        if task is None:
            return False

        task.completed = True
        return True

    def delete_task(self, task_id: int) -> bool:
        """Delete a task; return whether its ID was found."""
        self._validate_task_id(task_id)
        task = self._find_task(task_id)
        if task is None:
            return False

        self._tasks.remove(task)
        return True

    def _find_task(self, task_id: int) -> Task | None:
        for task in self._tasks:
            if task.id == task_id:
                return task
        return None

    @staticmethod
    def _validate_task_id(task_id: int) -> None:
        if isinstance(task_id, bool) or not isinstance(task_id, int) or task_id < 1:
            raise ValueError("Task ID must be a positive integer.")


def _read_task_id() -> int:
    """Read and validate a task ID from the terminal."""
    raw_task_id = input("Task ID: ").strip()
    try:
        task_id = int(raw_task_id)
    except ValueError as error:
        raise ValueError("Enter a valid integer task ID.") from error

    TaskManager._validate_task_id(task_id)
    return task_id


def main() -> None:
    """Run the interactive task manager."""
    manager = TaskManager()

    while True:
        print("\nTask Manager")
        print("1. List tasks")
        print("2. Add task")
        print("3. Complete task")
        print("4. Delete task")
        print("5. Exit")

        choice = input("Choose an option: ").strip()

        try:
            if choice == "1":
                tasks = manager.list_tasks()
                if not tasks:
                    print("No tasks yet.")
                for task in tasks:
                    status = "Done" if task.completed else "Pending"
                    print(f"{task.id}. [{status}] {task.title}")
            elif choice == "2":
                task = manager.add_task(input("Task title: "))
                print(f"Added task {task.id}.")
            elif choice == "3":
                task_id = _read_task_id()
                if manager.complete_task(task_id):
                    print(f"Completed task {task_id}.")
                else:
                    print(f"Task {task_id} was not found.")
            elif choice == "4":
                task_id = _read_task_id()
                if manager.delete_task(task_id):
                    print(f"Deleted task {task_id}.")
                else:
                    print(f"Task {task_id} was not found.")
            elif choice == "5":
                print("Goodbye.")
                break
            else:
                print("Choose an option from 1 to 5.")
        except ValueError as error:
            print(error)
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break


if __name__ == "__main__":
    main()
