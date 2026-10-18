"""Deep AST and unified diff hunk analyzer for conventional commit drafting."""

import ast
from dataclasses import dataclass, field
from pathlib import PurePath
import re
import subprocess
from typing import Literal

CommitType = Literal["feat", "fix", "docs", "refactor", "chore"]

DOC_EXTENSIONS = {".md", ".rst", ".txt", ".adoc"}
CHORE_FILENAMES = {
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Makefile",
    "Dockerfile",
    ".gitignore",
    ".flake8",
    "tox.ini",
}
CHORE_EXTENSIONS = {".toml", ".yaml", ".yml", ".json", ".ini", ".cfg", ".lock"}
FIX_KEYWORDS = re.compile(
    r"\b(fix|fixed|fixes|bug|bugfix|error|issue|exception|"
    r"resolve|crash|patch)\b",
    re.IGNORECASE,
)
HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@\s*(.*)$")
PY_SYMBOL_RE = re.compile(
    r"^\s*(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)"
)
PY_DEF_KIND_RE = re.compile(
    r"^\s*(async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)"
)
RAISE_RE = re.compile(r"\braise\s+([A-Za-z_][A-Za-z0-9_]*Error|\w+Exception)")
MD_HEADING_RE = re.compile(r"^#{1,3}\s+(.+?)\s*$")
TOML_SECTION_RE = re.compile(r"^\[([^\]]+)\]\s*$")
REQ_PKG_RE = re.compile(
    r"^([A-Za-z0-9_.-]+(?:\s*[<>=!~]=?\s*[A-Za-z0-9_.*-]+)?|-e\s+\S+)"
)


@dataclass
class FileChange:
    """Represents parsed diff metadata and extracted semantic content."""

    path: str
    is_new: bool = False
    is_deleted: bool = False
    additions: int = 0
    deletions: int = 0
    added_lines: list[str] = field(default_factory=list)
    removed_lines: list[str] = field(default_factory=list)
    hunk_contexts: list[str] = field(default_factory=list)
    docstring: str | None = None
    added_symbols: list[str] = field(default_factory=list)
    modified_symbols: list[str] = field(default_factory=list)
    removed_symbols: list[str] = field(default_factory=list)
    raised_exceptions: list[str] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)
    config_items: list[str] = field(default_factory=list)


@dataclass
class CommitSummary:
    """Represents a drafted conventional commit message."""

    commit_type: CommitType
    title: str
    bullets: list[str]

    def format(self) -> str:
        """Format the commit summary as a title followed by bullet points."""
        bullet_block = "\n".join(self.bullets)
        return (
            f"{self.title}\n\n{bullet_block}" if bullet_block else self.title
        )


def get_git_diff() -> tuple[str, bool]:
    """Inspect 'git diff --staged', or fallback to 'git diff'.

    Returns:
        A tuple of (diff_text, is_staged).

    Raises:
        RuntimeError: If invoking git fails.
    """
    try:
        staged = subprocess.run(
            ["git", "diff", "--staged"],
            capture_output=True,
            text=True,
            check=True,
        )
        if staged.stdout.strip():
            return staged.stdout, True

        unstaged = subprocess.run(
            ["git", "diff"],
            capture_output=True,
            text=True,
            check=True,
        )
        return unstaged.stdout, False
    except (subprocess.CalledProcessError, OSError) as exc:
        stderr = getattr(exc, "stderr", "") or str(exc)
        raise RuntimeError(
            f"Failed to run git diff: {stderr.strip()}"
        ) from exc


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _format_symbol(kind: str, name: str) -> str:
    return name if kind == "class" else f"{name}()"


def _extract_python_semantics(change: FileChange) -> None:
    """Use Python AST (with regex fallback) to extract docstrings & symbols."""
    raw_added = [line[1:] for line in change.added_lines]
    raw_removed = [line[1:] for line in change.removed_lines]
    added_source = "\n".join(raw_added)

    if change.is_new and added_source.strip():
        try:
            tree = ast.parse(added_source)
            doc = ast.get_docstring(tree)
            if doc:
                change.docstring = doc.strip().splitlines()[0].strip()
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    _append_unique(change.added_symbols, f"{node.name}()")
                elif isinstance(node, ast.ClassDef):
                    _append_unique(change.added_symbols, node.name)
        except SyntaxError:
            pass

    if not change.docstring:
        match = re.search(r'^\s*"""([^"]+)"""', added_source, re.MULTILINE)
        if match:
            change.docstring = match.group(1).strip().splitlines()[0].strip()

    added_defs: dict[str, str] = {}
    removed_defs: dict[str, str] = {}

    for line in raw_added:
        m = PY_DEF_KIND_RE.match(line)
        if m:
            kind, name = m.group(1), m.group(2)
            added_defs[name] = _format_symbol(kind, name)
        for exc_match in RAISE_RE.findall(line):
            _append_unique(change.raised_exceptions, exc_match)

    for line in raw_removed:
        m = PY_DEF_KIND_RE.match(line)
        if m:
            kind, name = m.group(1), m.group(2)
            removed_defs[name] = _format_symbol(kind, name)

    for name, sym in added_defs.items():
        if name in removed_defs:
            _append_unique(change.modified_symbols, sym)
        else:
            _append_unique(change.added_symbols, sym)

    # Prioritize public symbols (not starting with '_') before private helpers
    change.added_symbols.sort(key=lambda s: s.startswith("_"))
    change.modified_symbols.sort(key=lambda s: s.startswith("_"))

    for name, sym in removed_defs.items():
        if name not in added_defs:
            _append_unique(change.removed_symbols, sym)

    for ctx in change.hunk_contexts:
        m = PY_DEF_KIND_RE.match(ctx)
        if m:
            sym = _format_symbol(m.group(1), m.group(2))
            if (
                sym not in change.added_symbols
                and sym not in change.removed_symbols
            ):
                _append_unique(change.modified_symbols, sym)


def _extract_markdown_semantics(change: FileChange) -> None:
    """Extract markdown headings and summary lines from documentation diffs."""
    for line in change.added_lines:
        content = line[1:].strip()
        heading_match = MD_HEADING_RE.match(content)
        if heading_match:
            heading = heading_match.group(1).strip()
            _append_unique(change.headings, heading)
        elif (
            not change.docstring
            and content
            and not content.startswith(("-", "*", "`", "|", ">"))
            and not re.match(r"^\d+\.", content)
        ):
            clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", content)
            change.docstring = clean.rstrip(":")


def _extract_config_semantics(change: FileChange) -> None:
    """Extract package names or config sections from config/chore files."""
    name = PurePath(change.path).name
    for line in change.added_lines:
        content = line[1:].strip()
        if not content or content.startswith("#"):
            continue
        if name == "requirements.txt":
            m = REQ_PKG_RE.match(content)
            if m:
                _append_unique(change.config_items, m.group(1).strip())
        elif name.endswith(".toml") or name.endswith(".ini"):
            m = TOML_SECTION_RE.match(content)
            if m:
                _append_unique(change.config_items, f"[{m.group(1)}]")
        elif name == ".gitignore" and content.endswith("/"):
            _append_unique(change.config_items, content)


def _enrich_file_semantics(change: FileChange) -> None:
    """Populate semantic fields on a FileChange based on its file type."""
    suffix = PurePath(change.path).suffix.lower()
    if suffix == ".py":
        _extract_python_semantics(change)
    elif _is_chore_file(change.path):
        _extract_config_semantics(change)
    elif _is_doc_file(change.path):
        _extract_markdown_semantics(change)


def parse_diff(diff_text: str) -> list[FileChange]:
    """Parse raw unified git diff output into enriched FileChange objects."""
    changes: list[FileChange] = []
    current: FileChange | None = None

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            if current is not None:
                _enrich_file_semantics(current)
                changes.append(current)
            parts = line.split(" b/", 1)
            file_path = (
                parts[1].strip() if len(parts) == 2 else line[11:].strip()
            )
            current = FileChange(path=file_path)
        elif current is not None:
            if line.startswith("new file mode"):
                current.is_new = True
            elif line.startswith("deleted file mode"):
                current.is_deleted = True
            elif line.startswith("@@ "):
                m = HUNK_HEADER_RE.match(line)
                if m and m.group(1).strip():
                    _append_unique(current.hunk_contexts, m.group(1).strip())
            elif line.startswith("+") and not line.startswith("+++"):
                current.additions += 1
                current.added_lines.append(line)
            elif line.startswith("-") and not line.startswith("---"):
                current.deletions += 1
                current.removed_lines.append(line)

    if current is not None:
        _enrich_file_semantics(current)
        changes.append(current)

    return changes


def _is_doc_file(path: str) -> bool:
    p = PurePath(path)
    return p.suffix.lower() in DOC_EXTENSIONS or "docs" in p.parts


def _is_test_file(path: str) -> bool:
    p = PurePath(path)
    return "tests" in p.parts or p.name.startswith("test_")


def _is_chore_file(path: str) -> bool:
    p = PurePath(path)
    return (
        p.name in CHORE_FILENAMES
        or p.suffix.lower() in CHORE_EXTENSIONS
        or p.name.startswith(".")
        or _is_test_file(path)
    )


def _classify_single_file(change: FileChange) -> CommitType:
    """Classify a file change into feat, fix, docs, refactor, or chore."""
    if _is_chore_file(change.path):
        return "chore"

    if _is_doc_file(change.path):
        return "docs"

    added_content = "\n".join(change.added_lines)
    if not change.is_new and FIX_KEYWORDS.search(added_content):
        return "fix"

    if change.is_new or change.added_symbols:
        return "feat"

    if FIX_KEYWORDS.search(added_content):
        return "fix"

    if change.additions > 0 and change.deletions > 0:
        return "refactor"

    if change.additions > 0 and change.deletions == 0:
        return "feat"

    return "chore"


def categorize_changes(changes: list[FileChange]) -> CommitType:
    """Determine the primary conventional commit type across changed files."""
    if not changes:
        return "chore"

    categories = [_classify_single_file(change) for change in changes]
    if all(cat == "docs" for cat in categories):
        return "docs"
    if all(cat == "chore" for cat in categories):
        return "chore"

    priority: list[CommitType] = ["feat", "fix", "refactor", "docs", "chore"]
    for commit_type in priority:
        if commit_type in categories:
            return commit_type

    return "chore"


def _infer_scope(changes: list[FileChange]) -> str | None:
    """Infer a conventional commit scope from changed file paths."""
    src_packages: list[str] = []
    for change in changes:
        parts = PurePath(change.path).parts
        if len(parts) >= 2 and parts[0] == "src":
            _append_unique(src_packages, parts[1])
    if len(src_packages) == 1:
        return src_packages[0]

    if len(changes) == 1:
        p = PurePath(changes[0].path)
        if len(p.parts) > 1:
            return p.parts[0]
    return None


def _format_symbol_list(symbols: list[str], limit: int = 4) -> str:
    formatted = [f"`{s}`" for s in symbols[:limit]]
    if len(symbols) > limit:
        formatted.append(f"+{len(symbols) - limit} more")
    return ", ".join(formatted)


def _describe_action(change: FileChange, commit_type: CommitType) -> str:
    """Build a rich, content-aware bullet description for a file change."""
    details: list[str] = []

    if change.docstring:
        doc_clean = change.docstring.rstrip(".")
        details.append(doc_clean)

    if change.added_symbols:
        sym_str = _format_symbol_list(change.added_symbols)
        label = "defines" if change.is_new else "adds"
        details.append(f"{label} {sym_str}")

    if change.modified_symbols:
        sym_str = _format_symbol_list(change.modified_symbols)
        if commit_type == "fix" and change.raised_exceptions:
            exc_str = ", ".join(f"`{e}`" for e in change.raised_exceptions[:2])
            details.append(f"updates {sym_str} (raises {exc_str})")
        elif commit_type == "refactor":
            details.append(f"simplifies {sym_str}")
        else:
            details.append(f"updates {sym_str}")

    if change.removed_symbols:
        sym_str = _format_symbol_list(change.removed_symbols)
        details.append(f"removes {sym_str}")

    if change.headings and not change.added_symbols:
        head_str = ", ".join(f"'{h}'" for h in change.headings[:3])
        details.append(f"sections {head_str}")

    if change.config_items:
        cfg_str = ", ".join(f"`{c}`" for c in change.config_items[:4])
        details.append(f"configures {cfg_str}")

    if change.is_new:
        action = "Add"
    elif change.is_deleted:
        action = "Remove"
    elif commit_type == "fix":
        action = "Fix"
    elif commit_type == "refactor":
        action = "Refactor"
    elif commit_type == "docs":
        action = "Document"
    else:
        action = "Update"

    stats = f"(+{change.additions}/-{change.deletions})"
    if details:
        detail_str = "; ".join(details)
        return f"- {action} `{change.path}`: {detail_str} {stats}"
    return f"- {action} `{change.path}` {stats}"


def _build_title(
    changes: list[FileChange], commit_type: CommitType, scope: str | None
) -> str:
    """Draft a semantic Conventional Commit title from analyzed changes."""
    prefix = f"{commit_type}({scope})" if scope else commit_type

    if len(changes) == 1:
        only = changes[0]
        filename = PurePath(only.path).name
        stem = PurePath(only.path).stem

        if commit_type == "feat":
            if only.added_symbols:
                syms = ", ".join(only.added_symbols[:2])
                return f"{prefix}: implement {syms} in {filename}"
            action = "add" if only.is_new else "update"
            return f"{prefix}: {action} {filename}"

        if commit_type == "fix":
            target = (
                only.modified_symbols[0] if only.modified_symbols else filename
            )
            if only.raised_exceptions:
                exc = only.raised_exceptions[0]
                return f"{prefix}: handle {exc} in {target}"
            return f"{prefix}: resolve issue in {target}"

        if commit_type == "refactor":
            target = (
                only.modified_symbols[0] if only.modified_symbols else filename
            )
            return f"{prefix}: refactor {target} in {stem}"

        if commit_type == "docs":
            if only.headings:
                section = only.headings[0]
                return f"{prefix}: document {section} in {filename}"
            return f"{prefix}: update {filename} documentation"

        if only.config_items:
            items = ", ".join(only.config_items[:2])
            return f"{prefix}: add {items} to {filename}"
        return f"{prefix}: update {filename}"

    # Multi-file semantic title synthesis
    src_modules: list[str] = []
    has_tests = False
    has_docs = False
    has_config = False

    for c in changes:
        p = PurePath(c.path)
        if _is_test_file(c.path):
            has_tests = True
        elif _is_doc_file(c.path):
            has_docs = True
        elif _is_chore_file(c.path):
            has_config = True
        elif p.stem != "__init__":
            _append_unique(src_modules, p.stem)

    parts: list[str] = []
    if src_modules:
        mod_list = ", ".join(src_modules[:3])
        verb = (
            "implement"
            if commit_type == "feat"
            else ("fix" if commit_type == "fix" else "refactor")
        )
        parts.append(f"{verb} {mod_list} modules")

    extras: list[str] = []
    if has_tests:
        extras.append("unit tests")
    if has_docs:
        extras.append("docs")
    if has_config and not src_modules:
        extras.append("project config")

    if parts and extras:
        return f"{prefix}: {parts[0]} with {' and '.join(extras)}"
    if parts:
        return f"{prefix}: {parts[0]}"
    if extras:
        return f"{prefix}: update {' and '.join(extras)}"
    return f"{prefix}: update {len(changes)} files"


def generate_summary(diff_text: str) -> CommitSummary:
    """Generate a CommitSummary (title and bullets) from raw diff text."""
    changes = parse_diff(diff_text)
    commit_type = categorize_changes(changes)

    if not changes:
        return CommitSummary(
            commit_type=commit_type,
            title=f"{commit_type}: no file changes detected",
            bullets=[],
        )

    scope = _infer_scope(changes)
    title = _build_title(changes, commit_type, scope)
    bullets = [_describe_action(c, _classify_single_file(c)) for c in changes]
    return CommitSummary(commit_type=commit_type, title=title, bullets=bullets)
