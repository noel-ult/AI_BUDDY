"""
tools/system_tools.py
---------------------
System-level utilities for AI Buddy.

Features
  open_application(name)  — Launch a named application (cross-platform)
  show_time()             — Print the current date and time
  system_info()           — Display CPU, RAM, disk, and OS information

Application aliases map friendly names (chrome, vscode, etc.) to the
correct executable/app name on Windows, macOS, and Linux.
"""

import os
import sys
import platform
import subprocess
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

# ── Application name aliases ────────────────────────────────────────────
# Each entry maps a friendly name -> platform key -> executable/app name
_APP_ALIASES: dict[str, dict[str, str]] = {
    "chrome":    {"win": "chrome",        "mac": "Google Chrome",    "linux": "google-chrome"},
    "firefox":   {"win": "firefox",       "mac": "Firefox",          "linux": "firefox"},
    "edge":      {"win": "msedge",        "mac": "Microsoft Edge",   "linux": "microsoft-edge"},
    "vscode":    {"win": "code",          "mac": "Visual Studio Code","linux": "code"},
    "notepad":   {"win": "notepad",       "mac": "TextEdit",         "linux": "gedit"},
    "explorer":  {"win": "explorer",      "mac": "Finder",           "linux": "nautilus"},
    "terminal":  {"win": "wt",            "mac": "Terminal",         "linux": "gnome-terminal"},
    "calculator":{"win": "calc",          "mac": "Calculator",       "linux": "gnome-calculator"},
    "calc":      {"win": "calc",          "mac": "Calculator",       "linux": "gnome-calculator"},
    "spotify":   {"win": "spotify",       "mac": "Spotify",          "linux": "spotify"},
    "word":      {"win": "winword",       "mac": "Microsoft Word",   "linux": "libreoffice --writer"},
    "excel":     {"win": "excel",         "mac": "Microsoft Excel",  "linux": "libreoffice --calc"},
    "paint":     {"win": "mspaint",       "mac": "Preview",          "linux": "gimp"},
    "discord":   {"win": "discord",       "mac": "Discord",          "linux": "discord"},
}

# Detect the current platform once at import time
_SYS = platform.system().lower()   # "windows" | "darwin" | "linux"


def _platform_key() -> str:
    """Return the short platform key used in _APP_ALIASES."""
    if _SYS == "windows":
        return "win"
    if _SYS == "darwin":
        return "mac"
    return "linux"


def open_application(app_name: str):
    """
    Attempt to open a named application.

    Accepts friendly aliases (chrome, vscode, notepad …) or any raw
    executable name. Uses os.startfile on Windows, 'open -a' on macOS,
    and a direct subprocess call on Linux.

    Args:
        app_name: Friendly or raw application name (case-insensitive).
    """
    key     = app_name.lower().strip()
    pkey    = _platform_key()
    exe     = _APP_ALIASES.get(key, {}).get(pkey, app_name)

    try:
        if _SYS == "windows":
            os.startfile(exe)  # type: ignore[attr-defined]
        elif _SYS == "darwin":
            subprocess.Popen(["open", "-a", exe])
        else:
            # Support multi-word commands (e.g. "libreoffice --writer")
            subprocess.Popen(
                exe.split(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        console.print(f"[green]Opening[/green] [bold]{app_name}[/bold]…")
    except FileNotFoundError:
        console.print(
            f"[red]Could not open '[bold]{app_name}[/bold]'. "
            "Is it installed and on your PATH?[/red]"
        )
    except OSError as exc:
        console.print(f"[red]OS error opening '{app_name}': {exc}[/red]")


def show_time():
    """Print the current date and time in a styled Rich panel."""
    now = datetime.now()
    console.print(
        Panel(
            f"[bold cyan]{now.strftime('%A, %B %d %Y')}[/bold cyan]\n"
            f"[bold white]{now.strftime('%H:%M:%S')}[/bold white]",
            title="[blue]Current Time[/blue]",
            border_style="blue",
            expand=False,
        )
    )


def system_info():
    """
    Display system hardware and OS statistics using psutil.

    Shows: OS, CPU usage & core count, RAM total/used/free,
           disk total/used/free, and Python version.
    """
    try:
        import psutil
    except ImportError:
        console.print(
            "[red]psutil is not installed.[/red] "
            "Run [bold]pip install psutil[/bold] to enable this feature."
        )
        return

    uname   = platform.uname()
    cpu_pct = psutil.cpu_percent(interval=0.5)
    cpu_freq = psutil.cpu_freq()
    ram     = psutil.virtual_memory()
    disk    = psutil.disk_usage("/")
    boot_time = datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")

    table = Table(title="System Information", show_lines=True, min_width=50)
    table.add_column("Property", style="cyan", min_width=18)
    table.add_column("Value", style="white")

    # OS
    table.add_row("OS", f"{uname.system} {uname.release} ({uname.machine})")
    table.add_row("Hostname", uname.node)
    table.add_row("Python", sys.version.split()[0])
    table.add_row("Boot Time", boot_time)

    # CPU
    table.add_row("", "")  # visual separator
    table.add_row("CPU Usage", f"[bold]{cpu_pct}%[/bold]")
    table.add_row("CPU Cores (logical)", str(psutil.cpu_count(logical=True)))
    table.add_row("CPU Cores (physical)", str(psutil.cpu_count(logical=False)))
    if cpu_freq:
        table.add_row("CPU Frequency", f"{cpu_freq.current:.0f} MHz")

    # RAM
    table.add_row("", "")
    table.add_row("RAM Total", f"{ram.total / 1e9:.2f} GB")
    table.add_row("RAM Used", f"{ram.used / 1e9:.2f} GB  ({ram.percent}%)")
    table.add_row("RAM Free", f"{ram.available / 1e9:.2f} GB")

    # Disk
    table.add_row("", "")
    table.add_row("Disk Total", f"{disk.total / 1e9:.2f} GB")
    table.add_row("Disk Used", f"{disk.used / 1e9:.2f} GB  ({disk.percent}%)")
    table.add_row("Disk Free", f"{disk.free / 1e9:.2f} GB")

    console.print(table)


def shutdown_pc(delay: int = 60):
    """
    Schedule a system shutdown.

    A 60-second delay is used by default so the user can cancel with
    `shutdown /a` (Windows) or `shutdown -c` (Linux/macOS).

    Args:
        delay: Seconds before the machine shuts down (default 60).
    """
    import shlex

    console.print(
        f"[bold red]⚠  Shutdown scheduled in {delay} second(s).[/bold red]\n"
        f"[dim]Cancel: [bold]shutdown /a[/bold] (Windows)  or  "
        f"[bold]shutdown -c[/bold] (Linux/macOS)[/dim]"
    )

    try:
        if _SYS == "windows":
            subprocess.Popen(["shutdown", "/s", "/t", str(delay)])
        else:
            subprocess.Popen(["shutdown", "-h", f"+{delay // 60}"])
    except Exception as exc:
        console.print(f"[red]Shutdown failed:[/red] {exc}")


def restart_pc(delay: int = 60):
    """
    Schedule a system restart.

    Args:
        delay: Seconds before the machine restarts (default 60).
    """
    console.print(
        f"[bold yellow]⚠  Restart scheduled in {delay} second(s).[/bold yellow]\n"
        f"[dim]Cancel: [bold]shutdown /a[/bold] (Windows)  or  "
        f"[bold]shutdown -c[/bold] (Linux/macOS)[/dim]"
    )

    try:
        if _SYS == "windows":
            subprocess.Popen(["shutdown", "/r", "/t", str(delay)])
        else:
            subprocess.Popen(["shutdown", "-r", f"+{delay // 60}"])
    except Exception as exc:
        console.print(f"[red]Restart failed:[/red] {exc}")
