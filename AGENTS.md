# Agent Instructions & Project Guidelines

## 1. Project Overview
A lightweight Python CLI tool (`git-summary`) that parses git diffs and drafts conventional commit messages. See [SPEC.md](SPEC.md) for functional requirements.

## 2. Core Commands
* Setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
* Run Tests: `pytest -v`
* Lint: `flake8 src/` or `black --check src/`

## 3. Architecture & Code Style
* Source code lives strictly under `src/git_summary/`.
* Tests live under `tests/` mirroring the `src/` hierarchy.
* Use Python 3.11+ type hints on all functions.
* Clean error handling: avoid bare `except:` statements.

## 4. Agent Operational Rules
* **TDD First:** Generate and verify tests alongside or before implementation.
* **Verification Rule:** Never announce a task as "complete" until you execute `pytest` and verify 100% tests pass.
* **Safety:** Never delete files or modify git history without explicit confirmation.
* **Dependencies:** Keep external dependencies minimal.
