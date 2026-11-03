"""In-memory task management engine and optional Streamlit interface."""

from dataclasses import dataclass


ALLOWED_PRIORITIES = frozenset({"Low", "Medium", "High"})


@dataclass
class Task:
    """Represent a task managed by :class:`TaskManager`."""

    id: int
    title: str
    category: str
    completed: bool = False
    priority: str = "Medium"


class TaskManager:
    """Create and manage tasks in memory."""

    def __init__(self) -> None:
        self._tasks: list[Task] = []
        self._next_id = 1

    def add_task(
        self,
        title: str,
        category: str = "General",
        priority: str = "Medium",
    ) -> Task:
        """Validate and add a task, returning the created task."""
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Task title must not be empty.")
        if not isinstance(category, str) or not category.strip():
            raise ValueError("Task category must not be empty.")
        if not isinstance(priority, str) or priority not in ALLOWED_PRIORITIES:
            allowed_priorities = ", ".join(sorted(ALLOWED_PRIORITIES))
            raise ValueError(
                f"Priority must be one of: {allowed_priorities}."
            )

        task = Task(
            id=self._next_id,
            title=title.strip(),
            category=category.strip(),
            priority=priority,
        )
        self._tasks.append(task)
        self._next_id += 1
        return task

    def list_tasks(self) -> list[Task]:
        """Return a copy of the task list."""
        return self._tasks.copy()

    def toggle_task(self, task_id: int) -> bool:
        """Toggle a task's completion state; return whether it was found."""
        self._validate_task_id(task_id)
        task = self._find_task(task_id)
        if task is None:
            return False

        task.completed = not task.completed
        return True

    def delete_task(self, task_id: int) -> bool:
        """Delete a task; return whether it was found."""
        self._validate_task_id(task_id)
        task = self._find_task(task_id)
        if task is None:
            return False

        self._tasks.remove(task)
        return True

    def filter_by_status(self, completed: bool) -> list[Task]:
        """Return tasks matching the requested completion state."""
        if not isinstance(completed, bool):
            raise ValueError("Completed status must be a boolean.")
        return [task for task in self._tasks if task.completed is completed]

    def _find_task(self, task_id: int) -> Task | None:
        return next((task for task in self._tasks if task.id == task_id), None)

    @staticmethod
    def _validate_task_id(task_id: int) -> None:
        if (
            isinstance(task_id, bool)
            or not isinstance(task_id, int)
            or task_id < 1
        ):
            raise ValueError("Task ID must be a positive integer.")


def _run_streamlit_app() -> None:
    """Render the task manager as a Streamlit application."""
    import streamlit as st

    if "week1_task_manager" not in st.session_state:
        st.session_state.week1_task_manager = TaskManager()
    manager: TaskManager = st.session_state.week1_task_manager

    st.title("Task Manager")
    with st.form("add_task"):
        title = st.text_input("Title")
        category = st.text_input("Category", value="General")
        priority = st.selectbox("Priority", sorted(ALLOWED_PRIORITIES))
        submitted = st.form_submit_button("Add task")

    if submitted:
        try:
            manager.add_task(title, category, priority)
        except ValueError as error:
            st.error(str(error))
        else:
            st.success("Task added.")

    status_filter = st.selectbox(
        "Show tasks",
        ("All", "Pending", "Completed"),
    )
    if status_filter == "All":
        tasks = manager.list_tasks()
    else:
        tasks = manager.filter_by_status(status_filter == "Completed")

    st.dataframe(
        [
            {
                "ID": task.id,
                "Title": task.title,
                "Category": task.category,
                "Priority": task.priority,
                "Completed": task.completed,
            }
            for task in tasks
        ],
        hide_index=True,
        use_container_width=True,
    )

    st.subheader("Update task status")
    for task in manager.list_tasks():
        completed = st.checkbox(
            f"{task.id}: {task.title}",
            value=task.completed,
            key=f"week1_task_completed_{task.id}",
        )
        if completed != task.completed:
            manager.toggle_task(task.id)
            st.rerun()


if __name__ == "__main__":
    _run_streamlit_app()