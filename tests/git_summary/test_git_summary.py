"""Unit tests for the git-summary CLI tool and deep AST/diff analyzer."""

from subprocess import CompletedProcess
from unittest.mock import patch
import pytest

from git_summary.analyzer import (
    CommitSummary,
    categorize_changes,
    generate_summary,
    get_git_diff,
    parse_diff,
)
from git_summary.cli import main

SAMPLE_FEAT_DIFF = """diff --git a/src/git_summary/new_feature.py b/src/git_summary/new_feature.py
new file mode 100644
index 0000000..e69de29
--- /dev/null
+++ b/src/git_summary/new_feature.py
@@ -0,0 +1,6 @@
+\"\"\"Metrics calculation utilities.\"\"\"
+
+def calculate_metrics(data: list[int]) -> float:
+    return sum(data) / len(data)
"""

SAMPLE_FIX_DIFF = """diff --git a/src/git_summary/parser.py b/src/git_summary/parser.py
index 1234567..89abcdef 100644
--- a/src/git_summary/parser.py
+++ b/src/git_summary/parser.py
@@ -10,3 +10,5 @@ def parse(value: str) -> str:
-    return value.strip()
+    if value is None:
+        raise ValueError("Fix bug where value is None")
+    return value.strip()
"""

SAMPLE_DOCS_DIFF = """diff --git a/README.md b/README.md
index 1234567..89abcdef 100644
--- a/README.md
+++ b/README.md
@@ -1,2 +1,6 @@
 # Project Title
+
+## Installation
+Added installation instructions and usage documentation.
"""

SAMPLE_CHORE_DIFF = """diff --git a/requirements.txt b/requirements.txt
index 1234567..89abcdef 100644
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,2 +1,3 @@
 pytest>=8.0.0
+flake8>=7.0.0
"""

SAMPLE_REFACTOR_DIFF = """diff --git a/src/git_summary/utils.py b/src/git_summary/utils.py
index 1234567..89abcdef 100644
--- a/src/git_summary/utils.py
+++ b/src/git_summary/utils.py
@@ -1,4 +1,3 @@ def format_name(first: str, last: str) -> str:
-    result = f"{first} {last}"
-    return result.strip()
+    return f"{first} {last}".strip()
"""


class TestGetGitDiff:
    """Tests for retrieving staged or unstaged git diffs."""

    @patch("git_summary.analyzer.subprocess.run")
    def test_returns_staged_diff_when_present(self, mock_run: patch) -> None:
        mock_run.return_value = CompletedProcess(
            args=["git", "diff", "--staged"],
            returncode=0,
            stdout=SAMPLE_FEAT_DIFF,
            stderr="",
        )
        diff_text, is_staged = get_git_diff()
        assert diff_text == SAMPLE_FEAT_DIFF
        assert is_staged is True
        mock_run.assert_called_once_with(
            ["git", "diff", "--staged"],
            capture_output=True,
            text=True,
            check=True,
        )

    @patch("git_summary.analyzer.subprocess.run")
    def test_falls_back_to_unstaged_diff_when_staged_empty(
        self, mock_run: patch
    ) -> None:
        mock_run.side_effect = [
            CompletedProcess(
                args=["git", "diff", "--staged"],
                returncode=0,
                stdout="   \n",
                stderr="",
            ),
            CompletedProcess(
                args=["git", "diff"],
                returncode=0,
                stdout=SAMPLE_DOCS_DIFF,
                stderr="",
            ),
        ]
        diff_text, is_staged = get_git_diff()
        assert diff_text == SAMPLE_DOCS_DIFF
        assert is_staged is False
        assert mock_run.call_count == 2

    @patch("git_summary.analyzer.subprocess.run")
    def test_raises_runtime_error_on_git_failure(
        self, mock_run: patch
    ) -> None:
        from subprocess import CalledProcessError

        mock_run.side_effect = CalledProcessError(
            returncode=128,
            cmd=["git", "diff", "--staged"],
            stderr="fatal: not a git repository",
        )
        with pytest.raises(RuntimeError, match="Failed to run git diff"):
            get_git_diff()


class TestParseAndCategorize:
    """Tests for parsing diffs with AST/hunk extraction and categorization."""

    def test_parse_feat_diff_extracts_docstring_and_symbols(self) -> None:
        changes = parse_diff(SAMPLE_FEAT_DIFF)
        assert len(changes) == 1
        change = changes[0]
        assert change.path == "src/git_summary/new_feature.py"
        assert change.is_new is True
        assert change.docstring == "Metrics calculation utilities."
        assert "calculate_metrics()" in change.added_symbols
        assert categorize_changes(changes) == "feat"

    def test_categorize_fix_diff_extracts_hunk_context(self) -> None:
        changes = parse_diff(SAMPLE_FIX_DIFF)
        assert len(changes) == 1
        assert "parse()" in changes[0].modified_symbols
        assert categorize_changes(changes) == "fix"

    def test_categorize_docs_diff_extracts_headings(self) -> None:
        changes = parse_diff(SAMPLE_DOCS_DIFF)
        assert len(changes) == 1
        assert "Installation" in changes[0].headings
        assert categorize_changes(changes) == "docs"

    def test_categorize_chore_diff_extracts_dependencies(self) -> None:
        changes = parse_diff(SAMPLE_CHORE_DIFF)
        assert len(changes) == 1
        assert "flake8>=7.0.0" in changes[0].config_items
        assert categorize_changes(changes) == "chore"

    def test_categorize_refactor_diff(self) -> None:
        changes = parse_diff(SAMPLE_REFACTOR_DIFF)
        assert len(changes) == 1
        assert "format_name()" in changes[0].modified_symbols
        assert categorize_changes(changes) == "refactor"


class TestGenerateSummary:
    """Tests for generating semantic conventional commit titles and bullets."""

    def test_generate_summary_feat_includes_scope_and_symbol(self) -> None:
        summary: CommitSummary = generate_summary(SAMPLE_FEAT_DIFF)
        assert summary.commit_type == "feat"
        assert summary.title.startswith("feat(git_summary):")
        assert "calculate_metrics()" in summary.title
        assert len(summary.bullets) == 1
        bullet = summary.bullets[0]
        assert "`src/git_summary/new_feature.py`" in bullet
        assert "Metrics calculation utilities" in bullet
        assert "`calculate_metrics()`" in bullet

    def test_generate_summary_fix_describes_function_and_reason(self) -> None:
        summary = generate_summary(SAMPLE_FIX_DIFF)
        assert summary.commit_type == "fix"
        assert summary.title.startswith("fix(git_summary):")
        assert "parse()" in summary.title
        assert "`parse()`" in summary.bullets[0]
        assert "ValueError" in summary.bullets[0]

    def test_generate_summary_multiple_files_is_semantic(self) -> None:
        combined_diff = (
            SAMPLE_FEAT_DIFF
            + "\n"
            + SAMPLE_DOCS_DIFF
            + "\n"
            + SAMPLE_CHORE_DIFF
        )
        summary = generate_summary(combined_diff)
        assert summary.commit_type == "feat"
        assert "across" not in summary.title
        assert (
            "new_feature" in summary.title
            or "calculate_metrics" in summary.title
        )
        assert "docs" in summary.title
        assert len(summary.bullets) == 3


class TestCLI:
    """Tests for the CLI entry point."""

    @patch("git_summary.cli.get_git_diff")
    def test_cli_outputs_semantic_title_and_bullets(
        self, mock_get_diff: patch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_get_diff.return_value = (SAMPLE_FEAT_DIFF, True)
        exit_code = main([])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "feat(git_summary):" in captured.out
        assert "`src/git_summary/new_feature.py`" in captured.out
        assert "`calculate_metrics()`" in captured.out

    @patch("git_summary.cli.get_git_diff")
    def test_cli_handles_empty_diff(
        self, mock_get_diff: patch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_get_diff.return_value = ("", False)
        exit_code = main([])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "No staged or unstaged changes found" in captured.out

    @patch("git_summary.cli.get_git_diff")
    def test_cli_handles_runtime_error(
        self, mock_get_diff: patch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_get_diff.side_effect = RuntimeError(
            "Failed to run git diff: not a git repo"
        )
        exit_code = main([])
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "Error:" in captured.err
