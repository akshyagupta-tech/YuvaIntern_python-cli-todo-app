import streamlit as st
from dataclasses import dataclass
from typing import List

@dataclass
class Task:
    task_id: int
    title: str
    completed: bool = False

class TaskManager:
    def __init__(self):
        self.tasks: List[Task] = []
        self._next_id: int = 1

    def add_task(self, title: str) -> Task:
        clean = title.strip()
        if not clean:
            return None
        t = Task(self._next_id, clean)
        self.tasks.append(t)
        self._next_id += 1
        return t

    def list_tasks(self) -> List[Task]:
        return self.tasks

    def complete_task(self, task_id: int):
        for t in self.tasks:
            if t.task_id == task_id:
                t.completed = True

    def delete_task(self, task_id: int):
        self.tasks = [t for t in self.tasks if t.task_id != task_id]

st.set_page_config(page_title="Week 1: Task Manager", page_icon="📋", layout="centered")
st.title("📋 Week 1: Clean Architecture Task Engine")
st.caption("YuvaIntern Junior Python Developer Track • Intern: Akshya Gupta")

if "tm" not in st.session_state:
    st.session_state.tm = TaskManager()
    # Initial sample tasks
    st.session_state.tm.add_task("Review Clean Architecture Guidelines")
    st.session_state.tm.add_task("Set up automated unit testing")

col_in, col_btn = st.columns([4, 1])
with col_in:
    new_title = st.text_input("New Task Title", placeholder="e.g. Implement input validation...", label_visibility="collapsed")
with col_btn:
    if st.button("➕ Add", use_container_width=True) and new_title.strip():
        st.session_state.tm.add_task(new_title)
        st.rerun()

st.divider()

tasks = st.session_state.tm.list_tasks()
if not tasks:
    st.info("No active tasks found.")
else:
    for t in tasks:
        c1, c2, c3 = st.columns([5, 1.2, 1.2])
        status = "✅ Completed" if t.completed else "⏳ In Progress"
        c1.markdown(f"**[{t.task_id}]** {t.title}  \n`{status}`")
        if not t.completed:
            if c2.button("Done", key=f"d_{t.task_id}", use_container_width=True):
                st.session_state.tm.complete_task(t.task_id)
                st.rerun()
        else:
            c2.write("")
        if c3.button("Delete", key=f"del_{t.task_id}", use_container_width=True):
            st.session_state.tm.delete_task(t.task_id)
            st.rerun()
