# Enterprise Task Engine

A local-first task application with immutable domain entities, atomic JSON
storage, an argument-driven CLI, and a Streamlit dashboard.

## Architecture

- `models.py`: enums, immutable task/event dataclasses, and domain exceptions.
- `storage.py`: schema-aware JSON storage with atomic replace and file locking.
- `engine.py`: lifecycle, search, sorting, batch operations, exports, and metrics.
- `cli.py`: interactive menu and command-driven terminal interface.
- `app.py`: Streamlit dashboard backed by the same JSON store.
- `test_engine.py`: lifecycle, migration, persistence, and export tests.

## Requirements

Python 3.11 or newer. Install the web adapter dependency with:

```bash
python3 -m pip install -r requirements.txt
```

## Run

Interactive CLI:

```bash
python3 cli.py
```

Command-driven examples:

```bash
python3 cli.py create "Review release plan" --priority high --tag backend
python3 cli.py list --status pending --sort due_date
python3 cli.py complete 1
python3 cli.py export csv tasks-export.csv
```

Use `--data PATH` before a command or set `TASK_ENGINE_DATA` to select a store.
The default store is `tasks.json`; existing legacy task arrays are migrated on
first load.

Streamlit dashboard:

```bash
streamlit run app.py
```

Run the unit suite:

```bash
python3 -m unittest -v test_engine.py
python3 -m unittest discover -s tests -p 'test_*.py'
```
