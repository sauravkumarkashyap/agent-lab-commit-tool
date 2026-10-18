# Functional Specification (`git-summary`)

## Overview
`git-summary` is a lightweight Python CLI tool that inspects local Git diffs and drafts semantic, content-aware [Conventional Commit](https://www.conventionalcommits.org/) messages using a deep AST + diff hunk parser.

## Core Requirements
1. **Diff Inspection & Fallback**:
   - Inspect staged changes first via `git diff --staged`.
   - Automatically fall back to unstaged changes via `git diff` if nothing is staged.
   - Handle clean working trees gracefully (`No staged or unstaged changes found.`) and surface clear errors if run outside a Git repository.

2. **Deep AST & Diff Hunk Parsing**:
   - Parse unified diff headers, file modes (new/deleted/modified), hunk headers (`@@ ... @@ <context>`), and added/removed lines.
   - Extract semantic details from changed files:
     - **Python (`*.py`)**: Module docstrings, added/modified/removed classes and functions (`def`, `async def`, `class`), and inline error/fix patterns.
     - **Markdown/Docs (`*.md`, `*.rst`, `*.txt`)**: Document title (`# Heading`), section headings (`## Section`), and summary sentences.
     - **Config/Dependencies (`requirements.txt`, `pyproject.toml`, etc.)**: Added/removed package dependencies and configuration sections (`[table]`).

3. **Conventional Commit Categorization**:
   - Categorize changes into one of five Conventional Commit types:
     - `feat`: New source files, new functions/classes, or net-new feature additions.
     - `fix`: Bug fixes, exception handling, guard clauses, or error/issue resolutions.
     - `docs`: Documentation updates (`*.md`, `*.rst`, `*.txt`, `docs/`).
     - `refactor`: Code restructuring with both additions and deletions in existing source files.
     - `chore`: Build, dependency, test, and configuration updates (`requirements.txt`, `pyproject.toml`, dotfiles, `tests/`).

4. **Semantic Output Format**:
   - **Title**: `<type>(<scope>): <concise semantic summary of actual changes>` (or `<type>: <summary>` when scope is root-level), describing the primary modules, symbols, or components affected rather than generic file counts.
   - **Bullet-Point Summary**: Content-aware per-file bullets `[<type>] <path>: <semantic description>` detailing the module purpose, added/modified symbols, markdown sections, or config keys changed.

5. **Testing & Quality**:
   - Full unit test suite under `tests/` mirroring `src/git_summary/` using `pytest` and `unittest.mock`.
   - Zero lint errors under `flake8 src/` and `black --check src/`.
