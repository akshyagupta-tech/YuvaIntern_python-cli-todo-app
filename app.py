import streamlit as st
from todo_app import TaskManager

st.set_page_config(page_title="Week 1: Task Manager", layout="centered")
st.title("📋 Week 1: Clean Architecture Task Engine")

if "tm" not in st.session_state:
    st.session_state.tm = TaskManager()

new_title = st.text_input("Enter new task:")
if st.button("Add Task") and new_title.strip():
    st.session_state.tm.add_task(new_title)
    st.success(f"Added: {new_title}")

st.subheader("Current Tasks")
tasks = st.session_state.tm.list_tasks()
if not tasks:
    st.info("No tasks added yet.")
for t in tasks:
    col1, col2 = st.columns([4, 1])
    col1.write(f"**[{t.task_id}]** {t.title} - {'✅ Done' if t.completed else '⏳ Pending'}")
    if col2.button("Complete", key=f"c_{t.task_id}"):
        st.session_state.tm.complete_task(t.task_id)
        st.rerun()
