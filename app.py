"""Streamlit entry point for the Enterprise Task Engine."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Optional, cast

import streamlit as st

from engine import TaskManager
from models import Priority, Status, Task, ValidationError

st.set_page_config(page_title="Enterprise Task Engine", layout="wide")


@st.cache_resource
def _task_manager(storage_path: str) -> TaskManager:
    return TaskManager(storage_path)


def _toggle_completion(
    manager: TaskManager, task_id: int, state_key: str
) -> None:
    task = manager.get_task(task_id)
    is_checked = bool(st.session_state[state_key])
    if is_checked and task.status is not Status.COMPLETED:
        manager.complete_task(task_id)
    elif not is_checked and task.status is Status.COMPLETED:
        manager.transition_task(task_id, Status.IN_PROGRESS)


def _task_row(manager: TaskManager, task: Task) -> None:
    with st.container(border=True):
        status_col, info_col, edit_col, archive_col, delete_col = st.columns(
            [0.7, 5, 1, 1, 1]
        )
        if task.status is Status.ARCHIVED:
            status_col.write("Archived")
        else:
            state_key = f"task_complete_{task.id}"
            status_col.checkbox(
                "Complete",
                value=task.status is Status.COMPLETED,
                key=state_key,
                on_change=_toggle_completion,
                args=(manager, task.id, state_key),
            )

        status_text = task.status.value.replace("_", " ").title()
        due_text = task.due_alert or (
            task.due_date.date().isoformat()
            if task.due_date
            else "No due date"
        )
        info_col.markdown(f"**{task.title}** · {task.priority.value.title()}")
        info_col.caption(
            f"#{task.id} · {task.category} · {status_text} · {due_text}"
        )
        if task.description:
            info_col.write(task.description)
        if task.tags:
            info_col.caption(" ".join(f"#{tag}" for tag in task.tags))

        if edit_col.button("Edit", key=f"edit_open_{task.id}"):
            st.session_state[f"editing_task_{task.id}"] = True
        if task.status is not Status.ARCHIVED:
            if archive_col.button("Archive", key=f"archive_{task.id}"):
                manager.archive_task(task.id)
                st.rerun()
        if delete_col.button("Delete", key=f"delete_{task.id}"):
            st.session_state[f"confirm_delete_{task.id}"] = True

        if st.session_state.get(f"confirm_delete_{task.id}"):
            st.warning(f"Permanently delete task {task.id}?")
            confirm_col, cancel_col = st.columns(2)
            if confirm_col.button("Confirm delete", key=f"confirm_{task.id}"):
                manager.hard_delete_task(task.id)
                st.session_state.pop(f"confirm_delete_{task.id}", None)
                st.rerun()
            if cancel_col.button("Cancel", key=f"cancel_{task.id}"):
                st.session_state.pop(f"confirm_delete_{task.id}", None)
                st.rerun()

        if st.session_state.get(f"editing_task_{task.id}"):
            with st.form(f"edit_task_form_{task.id}"):
                title = st.text_input("Title", value=task.title)
                description = st.text_area(
                    "Description", value=task.description
                )
                category = st.text_input("Category", value=task.category)
                priority = st.selectbox(
                    "Priority",
                    list(Priority),
                    index=list(Priority).index(task.priority),
                    format_func=lambda value: value.value.title(),
                )
                due_date = st.text_input(
                    "Due date (ISO 8601)",
                    value=task.due_date.isoformat() if task.due_date else "",
                )
                tags = st.text_input(
                    "Tags (comma-separated)", value=", ".join(task.tags)
                )
                save_changes = st.form_submit_button("Save changes")
            if save_changes:
                try:
                    manager.update_task(
                        task.id,
                        title=title,
                        description=description,
                        category=category,
                        priority=priority,
                        due_date=due_date or None,
                        tags=[
                            tag.strip()
                            for tag in tags.split(",")
                            if tag.strip()
                        ],
                    )
                except ValidationError as error:
                    st.error(str(error))
                else:
                    st.session_state.pop(f"editing_task_{task.id}", None)
                    st.rerun()


def main() -> None:
    data_path = os.environ.get("TASK_ENGINE_DATA", "tasks.json")
    manager = _task_manager(str(Path(data_path).expanduser()))
    st.title("Enterprise Task Engine")

    metrics = manager.metrics()
    metric_cols = st.columns(4)
    metric_cols[0].metric("Active tasks", metrics["active_tasks"])
    metric_cols[1].metric("Completion", f"{metrics['completion_ratio']:.0%}")
    metric_cols[2].metric("Overdue", metrics["overdue_count"])
    metric_cols[3].metric(
        "Avg. turnaround",
        f"{metrics['average_turnaround_days']:.1f} days",
    )

    with st.form("create_task", clear_on_submit=True):
        st.subheader("Create task")
        title_col, category_col, priority_col = st.columns([3, 2, 1])
        title = title_col.text_input("Title")
        category = category_col.text_input("Category", value="General")
        priority: Priority = cast(
            Priority,
            priority_col.selectbox(
                "Priority",
                list(Priority),
                index=1,
                format_func=lambda value: value.value.title(),
            ),
        )
        description = st.text_area("Description")
        tag_col, date_col = st.columns(2)
        raw_tags = tag_col.text_input("Tags", placeholder="backend, urgent")
        due_date: Optional[date] = date_col.date_input("Due date", value=None)
        submitted = st.form_submit_button("Add task")
    if submitted:
        try:
            manager.create_task(
                title,
                description,
                priority,
                category,
                [tag.strip() for tag in raw_tags.split(",") if tag.strip()],
                due_date,
            )
        except ValidationError as error:
            st.error(str(error))
        else:
            st.rerun()

    st.divider()
    search_col, status_col, priority_col, tag_col, sort_col = st.columns(
        [3, 1.5, 1.5, 1.5, 2]
    )
    query = search_col.text_input("Search tasks")
    selected_status = status_col.selectbox(
        "Status",
        ["all", *(status.value for status in Status)],
    )
    selected_priority = priority_col.selectbox(
        "Priority",
        ["all", *(priority.value for priority in Priority)],
    )
    tag_filter = tag_col.text_input("Tag filter")
    sort_by = sort_col.selectbox(
        "Sort by",
        ("created_at", "due_date", "priority_rank", "title"),
    )
    overdue_only = st.checkbox("Overdue only")

    try:
        tasks = manager.list_tasks(
            status=None if selected_status == "all" else selected_status,
            priority=None if selected_priority == "all" else selected_priority,
            tag=tag_filter or None,
            query=query or None,
            overdue=True if overdue_only else None,
            sort_by=sort_by,
            include_archived=selected_status == Status.ARCHIVED.value,
        )
    except ValidationError as error:
        st.error(str(error))
        tasks = []

    st.subheader(f"Tasks ({len(tasks)})")
    st.download_button(
        "Download CSV",
        data=manager.export_csv(),
        file_name="enterprise_tasks.csv",
        mime="text/csv",
    )
    st.download_button(
        "Download JSON",
        data=manager.export_json(),
        file_name="enterprise_tasks.json",
        mime="application/json",
    )

    for task in tasks:
        _task_row(manager, task)
    if not tasks:
        st.info("No tasks match the selected filters.")


if __name__ == "__main__":
    main()
