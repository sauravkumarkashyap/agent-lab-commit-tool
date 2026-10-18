"""Command-line interface for git-summary."""

import argparse
import sys
from typing import Sequence

from git_summary.analyzer import generate_summary, get_git_diff


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for git-summary."""
    parser = argparse.ArgumentParser(
        prog="git-summary",
        description="Parse git diffs and draft conventional commit messages.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the git-summary CLI tool."""
    parser = build_parser()
    parser.parse_args(argv)

    try:
        diff_text, is_staged = get_git_diff()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not diff_text.strip():
        print("No staged or unstaged changes found.")
        return 0

    summary = generate_summary(diff_text)
    source_label = "staged" if is_staged else "unstaged"
    print(f"Suggested Commit ({source_label} changes):")
    print(summary.format())
    return 0


if __name__ == "__main__":
    sys.exit(main())
