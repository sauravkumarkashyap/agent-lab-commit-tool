# git-summary

A lightweight Python CLI tool that parses Git diffs (`--staged` or unstaged) and drafts [Conventional Commit](https://www.conventionalcommits.org/) messages with a title and per-file bullet summary.

## Features
- **Automatic Staged/Unstaged Detection:** Inspects `git diff --staged` first and falls back to `git diff` when no changes are staged.
- **Conventional Commit Classification:** Categorizes changes into `feat`, `fix`, `docs`, `refactor`, or `chore`.
- **Clean Summary Output:** Generates a ready-to-use commit title and bulleted per-file diff statistics (`+additions/-deletions`).

## Installation & Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

Run `git-summary` inside any Git repository with staged or unstaged changes:

```bash
git-summary
```

### Example Output

```text
Suggested Commit (staged changes):
feat: add new_feature.py

- Add `src/git_summary/new_feature.py` (+2/-0)
```

## Development & Testing

Run the test suite:
```bash
pytest -v
```

Run code formatting and lint checks:
```bash
flake8 src/
black --check src/
```

## Project Documentation
- [SPEC.md](SPEC.md) — Functional requirements and categorization specification.
- [AGENTS.md](AGENTS.md) — Agent operational rules and architecture guidelines.
