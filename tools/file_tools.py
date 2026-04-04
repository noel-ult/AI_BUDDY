"""
tools/file_tools.py
-------------------
File-related utilities for AI Buddy.

Features
  display_file(path)              — Pretty-print a file with syntax highlighting
  summarize_file(path, ai_engine) — Ask the AI to summarize a file's content
  get_file_for_summary(path)      — Read a file and return (name, content)
  search_files(keyword, root)     — Recursively find files matching a keyword
  read_pdf(path)                  — Extract text from a PDF file (requires pypdf)

File reading is capped at MAX_CHARS characters to avoid overflowing the
AI model's context window.  Unsupported binary files are rejected early.
"""

import os
import fnmatch
from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel
from rich.table import Table
from rich.spinner import Spinner
from rich.live import Live
from rich import box

console = Console()

# Maximum characters to read before truncating (≈ 4 000 tokens @ 2 chars/token)
MAX_CHARS = 8_000

# File extensions that are safe to read as UTF-8 text
_TEXT_EXTENSIONS: set[str] = {
    ".txt", ".md", ".rst", ".log",
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".html", ".htm", ".css", ".scss",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env",
    ".xml", ".csv", ".tsv",
    ".sh", ".bat", ".ps1", ".cmd",
    ".java", ".kt", ".groovy",
    ".c", ".cpp", ".h", ".hpp",
    ".cs", ".go", ".rs", ".rb", ".php",
    ".sql", ".graphql",
    ".dockerfile", ".gitignore", ".editorconfig",
    ".pdf",
}


# ── Internal helper ───────────────────────────────────────────────────────

def _read_text_file(path: str) -> str | None:
    """
    Read a text or PDF file and return its content capped at MAX_CHARS.

    Returns None and prints an error message if:
      - the file does not exist,
      - the extension is not in the allowed set,
      - the file cannot be opened due to permissions.

    Args:
        path: Absolute or relative path to the file.

    Returns:
        File content as a str, or None on failure.
    """
    path = os.path.expanduser(path)   # expand ~ on all platforms

    if not os.path.exists(path):
        console.print(f"[red]File not found:[/red] {path}")
        return None

    if not os.path.isfile(path):
        console.print(f"[red]'{path}' is a directory, not a file.[/red]")
        return None

    ext = os.path.splitext(path)[1].lower()
    if ext not in _TEXT_EXTENSIONS:
        console.print(
            f"[yellow]'{os.path.basename(path)}' has an unsupported extension "
            f"('[bold]{ext}[/bold]'). Only text, source and PDF files are supported.[/yellow]"
        )
        return None

    # ── PDF extraction ────────────────────────────────────────────────────
    if ext == ".pdf":
        return read_pdf(path)

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read(MAX_CHARS)

        if os.path.getsize(path) > MAX_CHARS:
            content += "\n\n... [content truncated] ..."

        return content

    except PermissionError:
        console.print(f"[red]Permission denied:[/red] {path}")
        return None
    except OSError as exc:
        console.print(f"[red]Error reading file:[/red] {exc}")
        return None


# ── Public functions ──────────────────────────────────────────────────────

def display_file(path: str):
    """
    Display a source/text file in the terminal with syntax highlighting.

    Uses Rich's Syntax component with the Monokai theme and line numbers.

    Args:
        path: Absolute or relative path to the file.
    """
    content = _read_text_file(path)
    if content is None:
        return

    ext = os.path.splitext(path)[1].lstrip(".") or "text"
    try:
        syntax = Syntax(content, ext, theme="monokai", line_numbers=True)
        console.print(
            Panel(syntax, title=f"[cyan]{os.path.basename(path)}[/cyan]", border_style="cyan")
        )
    except Exception:
        # Fall back to plain text if the lexer is unknown
        console.print(content)


def get_file_for_summary(path: str) -> tuple:
    """
    Read a file and return a (filename, content) tuple for AI summarization.

    Returns:
        (basename: str, content: str) on success.
        (None, None) on failure.
    """
    content = _read_text_file(path)
    if content is None:
        return None, None
    return os.path.basename(path), content


def summarize_file(path: str, ai_engine) -> str:
    """
    Use the AI engine to produce a concise summary of a file.

    Reads the file, builds a prompt asking the AI to summarize it, then
    returns the AI's response as a string ready for display.

    Args:
        path      : Absolute or relative path to the file.
        ai_engine : An AIEngine instance (from ai_engine.py).

    Returns:
        AI-generated summary string, or an error message.
    """
    filename, content = get_file_for_summary(path)
    if content is None:
        return "Could not read the file."

    console.print(f"[dim]Asking AI to summarize '[bold]{filename}[/bold]'…[/dim]")

    full_response = ""
    messages = [
        {
            "role": "user",
            "content": (
                f"Please provide a clear and concise summary of the following file "
                f"named '{filename}'.\n\n"
                f"Describe its purpose, key sections, and any notable details.\n\n"
                f"--- FILE CONTENT ---\n{content}"
            ),
        }
    ]

    spinner = Spinner("dots", text="[dim]Summarizing…[/dim]")
    with Live(spinner, refresh_per_second=12, transient=True):
        for token in ai_engine.stream_chat(messages):
            full_response += token

    return full_response


def read_pdf(path: str) -> str | None:
    """
    Extract plain text from a PDF file using pypdf.

    Args:
        path: Absolute or relative path to the PDF file.

    Returns:
        Extracted text (capped at MAX_CHARS), or None on failure.
    """
    try:
        import pypdf  # optional dependency
    except ImportError:
        console.print(
            "[yellow]pypdf is not installed — cannot read PDF files.[/yellow]\n"
            "Run [bold]pip install pypdf[/bold] to enable PDF support."
        )
        return None

    path = os.path.expanduser(path)
    try:
        reader = pypdf.PdfReader(path)
        pages  = [page.extract_text() or "" for page in reader.pages]
        text   = "\n".join(pages)
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS] + "\n\n... [content truncated] ..."
        return text or "(PDF contained no extractable text)"
    except Exception as exc:
        console.print(f"[red]Error reading PDF:[/red] {exc}")
        return None


def search_files(keyword: str, root: str = ".") -> list[str]:
    """
    Recursively search for files whose name or content matches a keyword.

    Searches file *names* (glob-style) and the first 2 KB of each text
    file's *content* for the keyword.

    Args:
        keyword : The search term (case-insensitive).
        root    : Directory to start searching from (default: current dir).

    Returns:
        List of matching file paths (relative to root).
    """
    root    = os.path.expanduser(root)
    keyword_lower = keyword.lower()
    matches: list[str] = []

    table = Table(
        title=f'File Search — "{keyword}"',
        box=box.ROUNDED,
        show_lines=False,
    )
    table.add_column("Path",       style="cyan")
    table.add_column("Match Type", style="dim", justify="center")
    table.add_column("Size",       style="dim", justify="right")

    spinner = Spinner("dots", text=f"[dim]Searching in {root}…[/dim]")
    found: list[tuple] = []

    with Live(spinner, refresh_per_second=12, transient=True):
        for dirpath, _dirnames, filenames in os.walk(root):
            # Skip hidden / system directories
            _dirnames[:] = [
                d for d in _dirnames
                if not d.startswith(".") and d not in ("node_modules", "__pycache__", ".git")
            ]
            for fname in filenames:
                full_path = os.path.join(dirpath, fname)
                rel_path  = os.path.relpath(full_path, root)
                match_type = None

                # Name match
                if keyword_lower in fname.lower():
                    match_type = "name"

                # Content match (text files only, first 2 KB)
                if match_type is None:
                    ext = os.path.splitext(fname)[1].lower()
                    if ext in _TEXT_EXTENSIONS and ext != ".pdf":
                        try:
                            with open(full_path, "r", encoding="utf-8", errors="ignore") as fh:
                                snippet = fh.read(2048)
                            if keyword_lower in snippet.lower():
                                match_type = "content"
                        except OSError:
                            pass

                if match_type:
                    try:
                        size = os.path.getsize(full_path)
                        size_str = (
                            f"{size} B" if size < 1024
                            else f"{size/1024:.1f} KB" if size < 1e6
                            else f"{size/1e6:.1f} MB"
                        )
                    except OSError:
                        size_str = "?"
                    found.append((rel_path, match_type, size_str))

    if not found:
        console.print(f"[yellow]No files matching '[bold]{keyword}[/bold]' found in {root}[/yellow]")
        return []

    for rel_path, match_type, size_str in found:
        symbol = "[green]●[/green]" if match_type == "name" else "[blue]◈[/blue]"
        table.add_row(rel_path, f"{symbol} {match_type}", size_str)

    console.print(table)
    console.print(f"[dim]{len(found)} file(s) found.[/dim]")
    return [r[0] for r in found]
