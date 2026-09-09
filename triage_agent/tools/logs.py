"""Log tools for inspect_logs and gather_evidence: the collected log files only."""

import re
from collections.abc import Sequence
from pathlib import Path

from .errors import ToolAccessError

MAX_SLICE_LINES = 200
MAX_MATCHES = 50


class LogTools:
    """Reads only the files collect downloaded — never the wider filesystem."""

    def __init__(self, log_files: Sequence[Path]) -> None:
        self._log_files = tuple(path.resolve() for path in log_files)

    @property
    def log_names(self) -> tuple[str, ...]:
        return tuple(path.name for path in self._log_files)

    def read_log_slice(self, log: str, start_line: int = 1, line_count: int = 100) -> str:
        """Read at most MAX_SLICE_LINES lines of a collected log file."""
        lines = self._lines(self._resolve(log))
        start = max(start_line, 1)
        count = min(max(line_count, 1), MAX_SLICE_LINES)
        return "".join(lines[start - 1 : start - 1 + count])

    def search_logs(self, pattern: str, max_matches: int = MAX_MATCHES) -> list[str]:
        """Find `pattern` across the collected logs as `name:line: text` matches."""
        compiled = re.compile(pattern)
        limit = min(max(max_matches, 1), MAX_MATCHES)
        matches: list[str] = []
        for path in self._log_files:
            for number, line in enumerate(self._lines(path), start=1):
                if compiled.search(line):
                    matches.append(f"{path.name}:{number}: {line.rstrip()}")
                    if len(matches) == limit:
                        return matches
        return matches

    def _resolve(self, log: str) -> Path:
        wanted = Path(log)
        for path in self._log_files:
            if wanted == path or wanted.name == path.name:
                return path
        raise ToolAccessError(f"{log!r} is not a collected log file")

    def _lines(self, path: Path) -> list[str]:
        return path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
