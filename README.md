# Advanced CLI To-Do List Application

A modular, enterprise-grade Command-Line Interface (CLI) task management system built using native Python 3 and object-oriented programming (OOP) principles.

## Features
- **Task Metadata:** Supports Priority levels (`High`, `Medium`, `Low`), Functional Categories (`Work`, `Study`, `Personal`), and Due Dates.
- **Search & Filtering:** In-memory keyword queries across task titles and categories, with status filters for pending and completed tasks.
- **Data Persistence:** Built-in JSON serialization ensuring state persists across terminal restarts without third-party database dependencies.
- **Defensive Error Handling:** Safe integer conversion, validation against blank whitespace entries, and clean handling of terminal interrupt signals (`Ctrl+C`).
- **ANSI Terminal Interface:** Color-coded status badges and priority tags formatted in structured tables.

## Project Structure
```text
Week_01_CLI_ToDo_App/
|-- todo_app.py                   # Main executable application
|-- README.md                     # Technical documentation & testing guide
|-- tasks.json                    # Local storage state
`-- Week1_Python_CLI_Report.docx  # Formal technical completion report
```

## System Requirements
- Python 3.8 or higher
- Zero third-party library dependencies (runs on standard Python libraries: `json`, `os`, `sys`, `datetime`)

## How to Run
Execute the application from your terminal:
```bash
python3 todo_app.py
```

## Verification & Manual Test Cases
1. **Defensive Input Handling:** Enter non-numeric strings (e.g., `abc`) when prompted for Task IDs in Options 5 or 6. The application alerts the user without crashing.
2. **Blank String Trapping:** Attempt to add a task with an empty description or whitespace only. The input is rejected.
3. **Data Durability:** Create multiple tasks, mark items complete, exit via Option 7, and restart the CLI. State is preserved from `tasks.json`.
4. **Search Functionality:** Filter tasks by category keywords to verify scoped query handling.

## Technical Report
The formal project report (`Week1_Python_CLI_Report.docx`) is included directly within this repository, detailing architectural decisions, entity-controller design, and testing methodology.
