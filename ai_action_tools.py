"""
ai_action_tools.py
------------------
Secure tool registry and sandboxed file actions for AI-triggered operations.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Callable

from tools.file_tools import _TEXT_EXTENSIONS
from action_executor import execute_action


ToolFunction = Callable[..., dict[str, Any]]


class AIActionToolRegistry:
    """Holds a whitelist of safe, callable AI action tools."""

    def __init__(self):
        self.tools: dict[str, ToolFunction] = {}

    def register(self, name: str, func: ToolFunction):
        self.tools[name] = func

    def execute(self, action: str, parameters: dict[str, Any]) -> dict[str, Any]:
        return execute_action(action, parameters, self.tools)


def _allowed_roots() -> list[str]:
    home = os.path.expanduser("~")
    roots = [
        os.path.abspath(os.path.join(home, "Documents")),
        os.path.abspath(os.path.join(home, "Downloads")),
    ]
    return [p for p in roots if os.path.isdir(p)]


def _is_allowed_path(path: str, roots: list[str]) -> bool:
    abs_path = os.path.abspath(path)
    for root in roots:
        try:
            if os.path.commonpath([abs_path, root]) == root:
                return True
        except ValueError:
            continue
    return False


def find_file_function(filename: str) -> dict[str, Any]:
    """Search for a file by name only inside Documents and Downloads."""
    name = filename.strip()
    roots = _allowed_roots()

    if not roots:
        return {"success": False, "error": "No allowed directories found (Documents/Downloads)."}

    if not name or any(sep in name for sep in ("/", "\\")):
        return {"success": False, "error": "Invalid filename. Use only a file name, not a path."}

    matches: list[str] = []
    match_details: list[dict[str, str]] = []
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "__pycache__"]
            for fname in filenames:
                if fname.lower() == name.lower():
                    full_path = os.path.join(dirpath, fname)
                    matches.append(full_path)
                    try:
                        stat = os.stat(full_path)
                        created_at = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
                        modified_at = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                    except OSError:
                        created_at = "unknown"
                        modified_at = "unknown"

                    match_details.append(
                        {
                            "path": full_path,
                            "created_at": created_at,
                            "modified_at": modified_at,
                        }
                    )
                    if len(matches) >= 20:
                        break
            if len(matches) >= 20:
                break
        if len(matches) >= 20:
            break

    return {
        "success": True,
        "action": "find_file",
        "query": name,
        "matches": matches,
        "match_details": match_details,
        "allowed_roots": roots,
    }


def read_file_function(path: str) -> dict[str, Any]:
    """Read a text file only when it resides in Documents/Downloads."""
    roots = _allowed_roots()
    if not roots:
        return {"success": False, "error": "No allowed directories found (Documents/Downloads)."}

    target = os.path.abspath(os.path.expanduser(path.strip()))

    if not _is_allowed_path(target, roots):
        return {"success": False, "error": "Access denied. File must be in Documents or Downloads."}

    if not os.path.exists(target) or not os.path.isfile(target):
        return {"success": False, "error": "File not found."}

    ext = os.path.splitext(target)[1].lower()
    if ext not in _TEXT_EXTENSIONS or ext == ".pdf":
        return {"success": False, "error": "Only non-PDF text/source files are allowed for read_file."}

    try:
        with open(target, "r", encoding="utf-8", errors="replace") as handle:
            content = handle.read(8000)
    except OSError as exc:
        return {"success": False, "error": f"Failed to read file: {exc}"}

    return {
        "success": True,
        "action": "read_file",
        "path": target,
        "content": content,
        "truncated": os.path.getsize(target) > 8000,
    }


def build_default_registry() -> AIActionToolRegistry:
    """Build default whitelist registry for AI actions."""
    registry = AIActionToolRegistry()
    registry.register("find_file", find_file_function)
    registry.register("read_file", read_file_function)
    return registry
