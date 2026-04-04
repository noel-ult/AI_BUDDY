"""
tools/monitoring_tools.py
--------------------------
Real-time system monitoring for AI Buddy.

Uses psutil to read CPU, RAM, disk, network, and process data,
then renders everything with Rich tables and progress bars.

Public API
  cpu_usage()       — CPU percent and per-core breakdown
  ram_usage()       — RAM total / used / free
  disk_usage()      — disk partitions usage
  network_stats()   — bytes sent / received since boot
  top_processes()   — top-10 CPU-hungry processes
  system_status()   — full dashboard (all of the above)
"""

import os
import sys
import platform
from datetime import datetime, timedelta
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn, ProgressColumn
from rich.text import Text
from rich.columns import Columns
from rich import box

console = Console()


def _require_psutil():
    """Import psutil or print an install hint and return None."""
    try:
        import psutil
        return psutil
    except ImportError:
        console.print(
            "[red]psutil is not installed.[/red] "
            "Run [bold]pip install psutil[/bold] to enable monitoring."
        )
        return None


def _bar(value: float, width: int = 20) -> Text:
    """
    Build a simple ASCII progress bar as a Rich Text object.

    Args:
        value : Float 0-100 representing percentage fill.
        width : Total number of characters in the bar.

    Returns:
        Coloured Rich Text bar.
    """
    filled = int(value / 100 * width)
    empty  = width - filled
    bar    = "█" * filled + "░" * empty

    if value >= 85:
        colour = "red"
    elif value >= 60:
        colour = "yellow"
    else:
        colour = "green"

    t = Text()
    t.append(f"[{bar}] ", style=colour)
    t.append(f"{value:5.1f}%", style=f"bold {colour}")
    return t


# ── Public functions ──────────────────────────────────────────────────────

def cpu_usage():
    """Display overall CPU usage plus a per-core breakdown."""
    psutil = _require_psutil()
    if not psutil:
        return

    overall   = psutil.cpu_percent(interval=0.5)
    per_core  = psutil.cpu_percent(interval=0.5, percpu=True)
    freq      = psutil.cpu_freq()
    load_avg  = os.getloadavg() if hasattr(os, "getloadavg") else None

    table = Table(title="CPU Usage", box=box.ROUNDED, show_lines=True)
    table.add_column("Core", style="cyan", justify="center")
    table.add_column("Usage", min_width=28)
    table.add_column("Info", style="dim")

    table.add_row(
        "Overall",
        _bar(overall),
        f"{psutil.cpu_count(logical=False)} physical  /  {psutil.cpu_count()} logical"
        + (f"  |  {freq.current:.0f} MHz" if freq else ""),
    )
    table.add_row("", "", "")
    for i, pct in enumerate(per_core):
        table.add_row(f"Core {i}", _bar(pct), "")

    if load_avg:
        table.caption = f"Load average  1m: {load_avg[0]:.2f}  5m: {load_avg[1]:.2f}  15m: {load_avg[2]:.2f}"

    console.print(table)


def ram_usage():
    """Display RAM (virtual + swap) usage statistics."""
    psutil = _require_psutil()
    if not psutil:
        return

    vm   = psutil.virtual_memory()
    swap = psutil.swap_memory()

    table = Table(title="RAM Usage", box=box.ROUNDED, show_lines=True)
    table.add_column("Type",  style="cyan")
    table.add_column("Usage", min_width=28)
    table.add_column("Total",  style="dim")
    table.add_column("Used",   style="dim")
    table.add_column("Free",   style="dim")

    def gb(b):
        return f"{b / 1e9:.2f} GB"

    table.add_row(
        "RAM",
        _bar(vm.percent),
        gb(vm.total), gb(vm.used), gb(vm.available),
    )
    table.add_row(
        "Swap",
        _bar(swap.percent),
        gb(swap.total), gb(swap.used), gb(swap.free),
    )

    console.print(table)


def disk_usage():
    """Display usage for every mounted disk partition."""
    psutil = _require_psutil()
    if not psutil:
        return

    table = Table(title="Disk Usage", box=box.ROUNDED, show_lines=True)
    table.add_column("Mount",  style="cyan")
    table.add_column("FS",     style="dim")
    table.add_column("Usage",  min_width=28)
    table.add_column("Total",  style="dim")
    table.add_column("Used",   style="dim")
    table.add_column("Free",   style="dim")

    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except PermissionError:
            continue

        def gb(b):
            return f"{b / 1e9:.2f} GB"

        table.add_row(
            part.mountpoint,
            part.fstype,
            _bar(usage.percent),
            gb(usage.total), gb(usage.used), gb(usage.free),
        )

    console.print(table)


def network_stats():
    """Display bytes and packets sent/received since system boot."""
    psutil = _require_psutil()
    if not psutil:
        return

    net = psutil.net_io_counters()

    def fmt(b):
        for unit in ("B", "KB", "MB", "GB"):
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} TB"

    table = Table(title="Network Statistics (since boot)", box=box.ROUNDED)
    table.add_column("Direction", style="cyan")
    table.add_column("Bytes",     style="white")
    table.add_column("Packets",   style="dim")
    table.add_column("Errors",    style="red")
    table.add_column("Drop",      style="red")

    table.add_row(
        "Sent ↑",
        fmt(net.bytes_sent), str(net.packets_sent),
        str(net.errout), str(net.dropout),
    )
    table.add_row(
        "Received ↓",
        fmt(net.bytes_recv), str(net.packets_recv),
        str(net.errin), str(net.dropin),
    )

    console.print(table)


def top_processes(n: int = 10):
    """
    Display the top-N processes sorted by CPU usage.

    Args:
        n: Number of processes to show (default 10).
    """
    psutil = _require_psutil()
    if not psutil:
        return

    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
        try:
            procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # Warm up CPU counters, wait briefly, then re-sample
    for p in psutil.process_iter(["pid", "cpu_percent"]):
        try:
            p.cpu_percent()
        except Exception:
            pass

    import time; time.sleep(0.3)

    procs_live = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
        try:
            procs_live.append(p.info)
        except Exception:
            pass

    procs_live.sort(key=lambda x: x.get("cpu_percent") or 0, reverse=True)

    table = Table(title=f"Top {n} Processes by CPU", box=box.ROUNDED, show_lines=False)
    table.add_column("PID",    style="dim",   justify="right")
    table.add_column("Name",   style="white", max_width=30)
    table.add_column("CPU %",  style="cyan",  justify="right")
    table.add_column("RAM %",  style="green", justify="right")
    table.add_column("Status", style="dim")

    for proc in procs_live[:n]:
        cpu  = proc.get("cpu_percent")  or 0.0
        mem  = proc.get("memory_percent") or 0.0
        cpu_colour = "red" if cpu > 50 else "cyan"
        table.add_row(
            str(proc.get("pid", "?")),
            proc.get("name", "?"),
            f"[{cpu_colour}]{cpu:5.1f}[/{cpu_colour}]",
            f"{mem:5.1f}",
            proc.get("status", "?"),
        )

    console.print(table)


def system_status():
    """Print a full monitoring dashboard: CPU, RAM, disk, network."""
    psutil = _require_psutil()
    if not psutil:
        return

    uname     = platform.uname()
    boot_ts   = datetime.fromtimestamp(psutil.boot_time())
    uptime    = datetime.now() - boot_ts
    uptime_str = str(timedelta(seconds=int(uptime.total_seconds())))

    console.print(
        Panel(
            f"[bold white]{uname.system} {uname.release}[/bold white]  "
            f"[dim]{uname.node}[/dim]\n"
            f"Uptime [cyan]{uptime_str}[/cyan]  |  "
            f"Boot [dim]{boot_ts.strftime('%Y-%m-%d %H:%M')}[/dim]",
            title="[blue]System Status Dashboard[/blue]",
            border_style="blue",
        )
    )

    cpu_usage()
    ram_usage()
    disk_usage()
    network_stats()
