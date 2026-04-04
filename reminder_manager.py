"""
reminder_manager.py
-------------------
Reminder system for AI Buddy.

Users set reminders using natural language such as:
  "remind me to drink water in 30 minutes"
  "remind me to call John in 2 hours"

Each reminder is executed in a background daemon thread using
threading.Timer so it fires without blocking the main input loop.

Supported time units : seconds, minutes, hours
"""

import re
import threading
from datetime import datetime, timedelta
from rich.console import Console
from rich.table import Table

try:
    from plyer import notification as _plyer_notify
    _NOTIFY_AVAILABLE = True
except ImportError:
    _NOTIFY_AVAILABLE = False

console = Console()

# Map accepted time-unit strings to their equivalent in seconds
_TIME_UNITS: dict[str, int] = {
    "second":  1,
    "seconds": 1,
    "sec":     1,
    "secs":    1,
    "minute":  60,
    "minutes": 60,
    "min":     60,
    "mins":    60,
    "hour":    3600,
    "hours":   3600,
    "hr":      3600,
    "hrs":     3600,
}

# Pattern: "remind me to <task> in <N> <unit>"
_REMINDER_RE = re.compile(
    r"remind\s+me\s+to\s+(.+?)\s+in\s+(\d+(?:\.\d+)?)\s+(\w+)",
    re.IGNORECASE,
)


def _parse_reminder(text: str) -> tuple:
    """
    Parse a natural-language reminder string.

    Returns:
        (task: str, seconds: int)  on success.
        (None, None)               if the string could not be parsed.
    """
    match = _REMINDER_RE.search(text)
    if not match:
        return None, None

    task = match.group(1).strip()
    amount = float(match.group(2))
    unit = match.group(3).lower()

    multiplier = _TIME_UNITS.get(unit)
    if multiplier is None:
        return None, None

    return task, int(amount * multiplier)


class ReminderManager:
    """Schedules and fires reminders using background daemon threads."""

    def __init__(self):
        self._reminders: list[dict] = []
        self._lock = threading.Lock()

    # ── Public interface ─────────────────────────────────────────────────

    def set_reminder(self, text: str) -> bool:
        """
        Parse a natural-language reminder text and schedule it.

        Args:
            text: Full reminder string, e.g. "remind me to study in 10 minutes"

        Returns:
            True if the reminder was scheduled, False otherwise.
        """
        task, seconds = _parse_reminder(text)
        if task is None:
            console.print(
                "[yellow]Could not parse reminder. "
                "Format: [bold]remind me to <task> in <N> minutes[/bold][/yellow]"
            )
            return False

        fire_at = datetime.now() + timedelta(seconds=seconds)

        # Record the reminder so list_reminders() can display it
        entry = {"task": task, "fire_at": fire_at, "seconds": seconds}
        with self._lock:
            self._reminders.append(entry)

        # Fire the reminder in a background daemon thread
        timer = threading.Timer(seconds, self._fire, args=(task, entry))
        timer.daemon = True
        timer.start()

        # Human-friendly delay label
        if seconds < 60:
            delay_label = f"{seconds} second(s)"
        elif seconds < 3600:
            delay_label = f"{seconds // 60} minute(s)"
        else:
            delay_label = f"{seconds / 3600:.1f} hour(s)"

        console.print(
            f"[green]Reminder set:[/green] '[bold]{task}[/bold]' "
            f"in {delay_label} (at [cyan]{fire_at.strftime('%H:%M:%S')}[/cyan])"
        )
        return True

    def list_reminders(self):
        """Display all reminders that have not yet fired."""
        now = datetime.now()
        with self._lock:
            pending = [r for r in self._reminders if r["fire_at"] > now]

        if not pending:
            console.print("[yellow]No pending reminders.[/yellow]")
            return

        table = Table(title="Pending Reminders", show_lines=True)
        table.add_column("Task", style="white")
        table.add_column("Fires At", style="cyan")
        table.add_column("Time Left", style="dim")

        for r in pending:
            remaining = int((r["fire_at"] - now).total_seconds())
            if remaining < 60:
                left = f"{remaining}s"
            elif remaining < 3600:
                left = f"{remaining // 60}m {remaining % 60}s"
            else:
                left = f"{remaining // 3600}h {(remaining % 3600) // 60}m"

            table.add_row(r["task"], r["fire_at"].strftime("%H:%M:%S"), left)

        console.print(table)

    # ── Internal ─────────────────────────────────────────────────────────

    def _fire(self, task: str, entry: dict):
        """
        Called by the background timer when a reminder is due.
        Shows a desktop notification and prints a bold alert to the terminal.
        """
        # ── Desktop notification ──────────────────────────────────────────
        if _NOTIFY_AVAILABLE:
            try:
                _plyer_notify.notify(
                    title="⏰  AI Buddy Reminder",
                    message=task,
                    app_name="AI Buddy",
                    timeout=10,
                )
            except Exception:
                pass  # Never let a notification failure crash the app

        # ── Terminal alert (always shown) ─────────────────────────────────
        console.print(f"\n[bold yellow on dark_orange]  ⏰  REMINDER  [/bold yellow on dark_orange]")
        console.print(f"[bold white]{task}[/bold white]\n")
        # Mark the reminder as done by setting fire_at to the past
        with self._lock:
            entry["fire_at"] = datetime.min
