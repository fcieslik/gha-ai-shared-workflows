"""Repository and git tools for localize and gather_evidence, bounded to the checkout."""

import subprocess
from pathlib import Path

from .errors import ToolAccessError

MAX_FILE_LINES = 400
MAX_MATCHES = 50
FALLBACK_COMMITS = 15
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


class RepoTools:
    """Read-only view of `$GITHUB_WORKSPACE` and a bounded slice of its history.

    History is the merge-base range with the default branch, or the last
    FALLBACK_COMMITS commits when there is no merge-base — the usual case in CI,
    where `actions/checkout` clones shallow.
    """

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace.resolve()
        self._base: str | None = None
        self._range: tuple[str, ...] | None = None

    def list_dir(self, path: str = ".") -> list[str]:
        target = self._resolve(path)
        if not target.is_dir():
            raise ToolAccessError(f"{path!r} is not a directory")
        return sorted(
            f"{child.name}/" if child.is_dir() else child.name
            for child in target.iterdir()
        )

    def read_file(self, path: str, start_line: int = 1, line_count: int = 200) -> str:
        """Read at most MAX_FILE_LINES lines of a file inside the checkout."""
        target = self._resolve(path)
        if not target.is_file():
            raise ToolAccessError(f"{path!r} is not a file")
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines(
            keepends=True
        )
        start = max(start_line, 1)
        count = min(max(line_count, 1), MAX_FILE_LINES)
        return "".join(lines[start - 1 : start - 1 + count])

    def grep(self, pattern: str, path: str = ".", max_matches: int = MAX_MATCHES) -> list[str]:
        """Search tracked files for `pattern`, as `path:line: text` matches."""
        self._resolve(path)
        limit = min(max(max_matches, 1), MAX_MATCHES)
        found = self._git(
            "grep", "--line-number", "--no-color", "-e", pattern, "--", path
        )
        return found.splitlines()[:limit]

    def git_log(self) -> str:
        """One line per commit in the investigation range."""
        return self._git("log", "--oneline", "--no-decorate", *self._history_range())

    def git_diff(self, path: str | None = None) -> str:
        """The diff across the investigation range, optionally for one path."""
        scope = ["--", path] if path else []
        if path:
            self._resolve(path)
        return self._git("diff", f"{self._base_commit()}..HEAD", *scope)

    def git_show(self, commit: str) -> str:
        """Show one commit, refusing anything outside the investigation range."""
        if commit not in self._commits_in_range():
            raise ToolAccessError(f"{commit!r} is outside the investigation range")
        return self._git("show", "--no-color", commit)

    def _history_range(self) -> tuple[str, ...]:
        if self._range is None:
            base = self._merge_base()
            self._range = (f"{base}..HEAD",) if base else ("-n", str(FALLBACK_COMMITS))
        return self._range

    def _base_commit(self) -> str:
        """The commit the range starts from — the empty tree in a short history."""
        if self._base is None:
            base = self._merge_base()
            if base is None:
                commits = self._git(
                    "rev-list", f"--max-count={FALLBACK_COMMITS + 1}", "HEAD"
                ).split()
                base = commits[FALLBACK_COMMITS] if len(commits) > FALLBACK_COMMITS else EMPTY_TREE
            self._base = base
        return self._base

    def _merge_base(self) -> str | None:
        """Merge-base with the default branch, read from local git only."""
        try:
            default = self._git("rev-parse", "--abbrev-ref", "origin/HEAD").strip()
            return self._git("merge-base", "HEAD", default).strip() or None
        except ToolAccessError:
            return None

    def _commits_in_range(self) -> set[str]:
        listed = self._git("log", "--format=%H %h", *self._history_range()).split()
        return set(listed)

    def _resolve(self, path: str) -> Path:
        target = (self._workspace / path).resolve()
        if target != self._workspace and self._workspace not in target.parents:
            raise ToolAccessError(f"{path!r} is outside the checkout")
        return target

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self._workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        # git grep exits 1 with no output when nothing matched, which is not an error.
        if result.returncode != 0 and not result.stdout:
            raise ToolAccessError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result.stdout
