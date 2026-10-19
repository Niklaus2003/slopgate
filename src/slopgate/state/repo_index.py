"""Repository file tree and symbol index for deterministic fact extraction.

Enables matching cited paths and symbols against the codebase without external models.
Follows: problem-statement.md §6.2, architecture.md §6.2, PLAN_REVIEW.md §1.4.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


class RepoIndex:
    """Index of repository file paths and symbols."""

    # Matches file paths like src/foo/bar.py, flask/sessions.py, tests/test_app.py, setup.py
    # Also handles Windows backslash paths normalized to forward slashes
    PATH_PATTERN = re.compile(
        r"(?:[\w\-./\\]+[/\\launch]?[\w\-]+\.(?:py|md|rst|txt|html|js|ts|json|yml|yaml|toml|cfg|ini|sql|sh))",
        re.IGNORECASE,
    )

    # Matches class and function identifiers: e.g. `open_session`, `Flask.wsgi_app`
    IDENTIFIER_PATTERN = re.compile(r"`([A-Za-z_][A-Za-z0-9_.]*)`")

    def __init__(self, file_paths: list[str] | set[str] | None = None) -> None:
        self.file_paths: set[str] = set()
        self.file_basenames: set[str] = set()
        self.symbols: set[str] = set()

        if file_paths:
            for p in file_paths:
                # Normalize Windows path separators to forward slash
                norm = p.replace("\\", "/").strip().lstrip("./")
                self.file_paths.add(norm)
                self.file_basenames.add(norm.split("/")[-1].lower())

    @classmethod
    def from_json(cls, path: str | Path) -> RepoIndex:
        """Initialize from a saved file tree JSON file."""
        file_path = Path(path)
        if not file_path.is_file():
            return cls()
        data = json.loads(file_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return cls(data)
        if isinstance(data, dict) and "tree" in data:
            return cls([n["path"] for n in data["tree"] if n.get("type") == "blob"])
        return cls()

    @classmethod
    def from_file_list(cls, paths: list[str]) -> RepoIndex:
        """Initialize directly from a list of paths."""
        return cls(paths)

    def has_file(self, path: str) -> bool:
        """Check if an exact path or relative path exists in the repository."""
        norm = path.replace("\\", "/").strip().lstrip("./")
        if norm in self.file_paths:
            return True
        return bool("/" not in norm and norm.lower() in self.file_basenames)

    def extract_cited_paths(self, text: str) -> tuple[int, int]:
        """Extract paths cited in the text and verify against repo index.

        Returns:
            (found_count, cited_count)
        """
        if not text:
            return 0, 0

        # Find all candidate file paths
        raw_matches = self.PATH_PATTERN.findall(text)
        cited_candidates: set[str] = set()

        for m in raw_matches:
            cleaned = m.strip("`'\"()[],;:").replace("\\", "/")
            # Filter out URL schemes and trivial extensions
            if cleaned.startswith(("http://", "https://", "ftp://")):
                continue
            if len(cleaned) < 4:
                continue
            cited_candidates.add(cleaned)

        if not cited_candidates:
            return 0, 0

        cited_count = len(cited_candidates)
        found_count = 0

        for candidate in cited_candidates:
            if self.has_file(candidate):
                found_count += 1

        return found_count, cited_count
