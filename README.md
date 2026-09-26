# CLI To-Do List Application

A command-line task management application built using Python object-oriented programming.

## Logic Flow & Pseudo-code
1. Initialize TodoManager and load tasks.json if available.
2. Present continuous menu loop:
   - Option 1: Iterate list and display formatted records.
   - Option 2: Validate input string -> Instantiate Task -> Append to collection -> Write to storage.
   - Option 3: Accept integer ID -> Locate matching task -> Set completed = True -> Write to storage.
   - Option 4: Accept integer ID -> Find match -> Remove from list -> Write to storage.
   - Option 5: Exit process.

## Installation & Setup
- Requires Python 3.8+ (no third-party dependencies required).

## Execution
Run the application from your terminal:
  python3 todo_app.py

## Manual Test Cases
1. Input Validation: Enter text like "abc" when asked for an ID to verify that non-numeric values do not crash the app.
2. Whitespace Check: Submit an empty task description to verify it is rejected.
3. State Persistence: Add tasks, exit, re-run python3 todo_app.py, and choose Option 1 to verify tasks remain intact.
