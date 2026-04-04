"""
chat_manager.py
---------------
Manages persistent chat sessions and message history using SQLite.

Database    : database/chats.db
Tables      : chats, messages

Supported operations
  - Create a new chat session
  - List all saved sessions
  - Load a session (restores full message history)
  - Delete a session (cascades to its messages)
  - Clear messages in the current session
  - Save / retrieve individual messages
"""

import os
import sqlite3
from datetime import datetime
from rich.console import Console
from rich.table import Table

console = Console()

# Resolve path relative to this file so the DB ends up in database/chats.db
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_BASE_DIR, "database", "chats.db")


class ChatManager:
    """Handles all chat-session operations backed by SQLite."""

    def __init__(self):
        # Create the database directory if it does not exist
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_db()

        # Track the currently active session
        self.current_chat_id: int | None = None
        self.current_title: str | None = None

    # ── Schema ──────────────────────────────────────────────────────────

    def _init_db(self):
        """Create database tables if they do not already exist."""
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chats (
                chat_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                title      TEXT    NOT NULL,
                created_at TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id    INTEGER NOT NULL,
                role       TEXT    NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                content    TEXT    NOT NULL,
                timestamp  TEXT    NOT NULL,
                FOREIGN KEY (chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE
            );
            """
        )
        self.conn.commit()

    # ── Session management ───────────────────────────────────────────────

    def new_chat(self, title: str = "") -> int:
        """
        Create a new chat session and set it as the active session.

        Args:
            title: Optional human-readable title. Auto-generated if not given.

        Returns:
            The new chat_id (integer).
        """
        if not title:
            title = f"Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        cur = self.conn.execute(
            "INSERT INTO chats (title, created_at) VALUES (?, ?)",
            (title, datetime.now().isoformat()),
        )
        self.conn.commit()
        self.current_chat_id = cur.lastrowid
        self.current_title = title
        console.print(
            f"[green]New chat started:[/green] [bold]{title}[/bold] "
            f"[dim](ID: {self.current_chat_id})[/dim]"
        )
        return self.current_chat_id

    def list_chats(self):
        """Display all saved chat sessions as a formatted Rich table."""
        rows = self.conn.execute(
            "SELECT chat_id, title, created_at FROM chats ORDER BY created_at DESC"
        ).fetchall()

        if not rows:
            console.print("[yellow]No saved chats found.[/yellow]")
            return

        table = Table(title="Saved Chat Sessions", show_lines=True)
        table.add_column("ID", style="cyan", justify="right")
        table.add_column("Title", style="white")
        table.add_column("Created At", style="dim")

        for row in rows:
            active_marker = " [green](active)[/green]" if row["chat_id"] == self.current_chat_id else ""
            table.add_row(str(row["chat_id"]), row["title"] + active_marker, row["created_at"])

        console.print(table)

    def load_chat(self, chat_id: int) -> list:
        """
        Load a chat session by ID and return its full message history.

        Args:
            chat_id: The integer ID of the session to load.

        Returns:
            List of message dicts [{'role': ..., 'content': ...}, ...].
            Returns an empty list if the session is not found.
        """
        row = self.conn.execute(
            "SELECT chat_id, title FROM chats WHERE chat_id = ?", (chat_id,)
        ).fetchone()

        if not row:
            console.print(f"[red]Chat ID {chat_id} not found.[/red]")
            return []

        self.current_chat_id = row["chat_id"]
        self.current_title = row["title"]
        console.print(f"[green]Loaded:[/green] [bold]{row['title']}[/bold]")

        messages = self.conn.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY message_id",
            (chat_id,),
        ).fetchall()

        return [{"role": m["role"], "content": m["content"]} for m in messages]

    def delete_chat(self, chat_id: int):
        """Delete a chat session and all its messages (via CASCADE)."""
        self.conn.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))
        self.conn.commit()
        console.print(f"[red]Chat {chat_id} deleted.[/red]")
        if self.current_chat_id == chat_id:
            self.current_chat_id = None
            self.current_title = None

    def clear_chat(self):
        """Erase all messages in the currently active session."""
        if not self.current_chat_id:
            console.print("[yellow]No active chat session to clear.[/yellow]")
            return
        self.conn.execute(
            "DELETE FROM messages WHERE chat_id = ?", (self.current_chat_id,)
        )
        self.conn.commit()
        console.print("[yellow]Chat history cleared.[/yellow]")

    # ── Message persistence ──────────────────────────────────────────────

    def save_message(self, role: str, content: str):
        """
        Persist a message to the currently active chat session.

        Args:
            role   : 'user', 'assistant', or 'system'
            content: The message text.
        """
        if not self.current_chat_id:
            return  # No active session — nothing to save
        self.conn.execute(
            "INSERT INTO messages (chat_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (self.current_chat_id, role, content, datetime.now().isoformat()),
        )
        self.conn.commit()

    def get_messages(self) -> list:
        """
        Return all messages for the active session as a list of dicts.

        Returns:
            [{'role': ..., 'content': ...}, ...]   (oldest first)
        """
        if not self.current_chat_id:
            return []
        rows = self.conn.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY message_id",
            (self.current_chat_id,),
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in rows]

    # ── Cleanup ──────────────────────────────────────────────────────────

    def close(self):
        """Close the underlying SQLite connection."""
        self.conn.close()
