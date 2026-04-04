"""
memory_manager.py
-----------------
Long-term memory system for AI Buddy.

Stores important user facts in SQLite so they persist across sessions.
On startup, these memories are injected into the AI context so the
assistant remembers the user's preferences and past information.

Database : database/memory.db
Table    : memory (memory_id, content, created_at)

Commands
  remember <text>        — Store a new memory entry
  show memory            — Display all memories as a table
  delete memory [<id>]   — Delete one entry by ID, or all entries
"""

import os
import sqlite3
from datetime import datetime
from rich.console import Console
from rich.table import Table

console = Console()

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_BASE_DIR, "database", "memory.db")


class MemoryManager:
    """Stores and retrieves long-term user memory from SQLite."""

    def __init__(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    # ── Schema ──────────────────────────────────────────────────────────

    def _init_db(self):
        """Create the memory table if it does not already exist."""
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory (
                memory_id  INTEGER PRIMARY KEY AUTOINCREMENT,
                content    TEXT    NOT NULL,
                created_at TEXT    NOT NULL
            );
            """
        )
        self.conn.commit()

    # ── CRUD operations ─────────────────────────────────────────────────

    def remember(self, text: str):
        """
        Store a new memory entry.

        Args:
            text: The fact or piece of information to remember.
        """
        text = text.strip()
        if not text:
            console.print("[yellow]Nothing to remember — empty input.[/yellow]")
            return
        self.conn.execute(
            "INSERT INTO memory (content, created_at) VALUES (?, ?)",
            (text, datetime.now().isoformat()),
        )
        self.conn.commit()
        console.print(f"[green]Remembered:[/green] {text}")

    def show_memory(self):
        """Display all stored memories in a formatted Rich table."""
        rows = self.conn.execute(
            "SELECT memory_id, content, created_at FROM memory ORDER BY memory_id"
        ).fetchall()

        if not rows:
            console.print("[yellow]No memories stored yet.[/yellow]")
            return

        table = Table(title="Long-Term Memory", show_lines=True)
        table.add_column("ID", style="cyan", justify="right")
        table.add_column("Memory", style="white")
        table.add_column("Saved At", style="dim")

        for row in rows:
            table.add_row(str(row["memory_id"]), row["content"], row["created_at"])

        console.print(table)

    def delete_memory(self, memory_id: int | None = None):
        """
        Delete a specific memory by ID, or all memories if no ID is provided.

        Args:
            memory_id: Integer ID from the memory table. Pass None to wipe all.
        """
        if memory_id is not None:
            self.conn.execute("DELETE FROM memory WHERE memory_id = ?", (memory_id,))
            self.conn.commit()
            console.print(f"[red]Memory {memory_id} deleted.[/red]")
        else:
            self.conn.execute("DELETE FROM memory")
            self.conn.commit()
            console.print("[red]All memories deleted.[/red]")

    # ── AI context injection ─────────────────────────────────────────────

    def get_all_memories(self) -> list:
        """
        Return all memory entries as plain strings.
        Used to build a system message that primes the AI with known facts.

        Returns:
            List of memory content strings (oldest first).
        """
        rows = self.conn.execute(
            "SELECT content FROM memory ORDER BY memory_id"
        ).fetchall()
        return [r["content"] for r in rows]

    # ── Cleanup ──────────────────────────────────────────────────────────

    def close(self):
        """Close the underlying SQLite connection."""
        self.conn.close()
