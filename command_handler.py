"""
command_handler.py
------------------
Parses raw user input and classifies it as a built-in command or a
plain AI message. All recognised commands are intercepted here before
reaching the Ollama model, keeping the AI engine clean.

CommandType enum — every supported command has its own variant.
ParsedCommand   — a lightweight dataclass returned to main.py.
parse_command() — the single public function that main.py calls.

Supported commands
  Chat       : new chat | list chats | load chat <id> |
               delete chat <id> | clear chat
  Memory     : remember <text> | show memory | delete memory [<id>]
  Reminders  : remind me to <task> in <N> <unit> | list reminders
  System     : open <app> | show time | system info |
               shutdown pc | restart pc
  Monitoring : cpu usage | ram usage | disk usage |
               network stats | top processes | system status
  Files      : read file <path> | search files <kw> [in <dir>] |
               summarize file <path>
  Web        : research <topic>
  Task Agent : plan <goal> | agent <goal>
  Model      : /model <name>
  Misc       : help | ? | exit | quit | bye
"""

import re
from dataclasses import dataclass, field
from enum import Enum, auto


class CommandType(Enum):
    # ── Chat management ──────────────────────────────────────────────────
    NEW_CHAT       = auto()
    LIST_CHATS     = auto()
    LOAD_CHAT      = auto()
    DELETE_CHAT    = auto()
    CLEAR_CHAT     = auto()

    # ── Long-term memory ─────────────────────────────────────────────────
    REMEMBER       = auto()
    SHOW_MEMORY    = auto()
    DELETE_MEMORY  = auto()

    # ── Reminders ────────────────────────────────────────────────────────
    REMINDER       = auto()
    LIST_REMINDERS = auto()

    # ── System / OS ──────────────────────────────────────────────────────
    OPEN_APP       = auto()
    SHOW_TIME      = auto()
    SYSTEM_INFO    = auto()
    SHUTDOWN_PC    = auto()
    RESTART_PC     = auto()

    # ── System monitoring ─────────────────────────────────────────────────
    CPU_USAGE      = auto()
    RAM_USAGE      = auto()
    DISK_USAGE     = auto()
    NETWORK_STATS  = auto()
    TOP_PROCESSES  = auto()
    SYSTEM_STATUS  = auto()

    # ── File tools ───────────────────────────────────────────────────────
    READ_FILE      = auto()
    SEARCH_FILES   = auto()
    SUMMARIZE_FILE = auto()

    # ── Web research ─────────────────────────────────────────────────────
    RESEARCH       = auto()

    # ── Autonomous task agent ─────────────────────────────────────────────
    TASK_AGENT     = auto()

    # ── Model switching ──────────────────────────────────────────────────
    SET_MODEL      = auto()
    USE_CPU        = auto()
    USE_GPU        = auto()

    # ── Misc ─────────────────────────────────────────────────────────────
    HELP           = auto()
    EXIT           = auto()

    # ── Passthrough to AI ────────────────────────────────────────────────
    AI_MESSAGE     = auto()


@dataclass
class ParsedCommand:
    """Holds the detected command type and any extracted arguments."""
    type: CommandType
    args: dict = field(default_factory=dict)


def parse_command(text: str) -> ParsedCommand:
    """
    Analyse a raw user input string and return a ParsedCommand.

    Matching is case-insensitive. Unrecognised input is returned as
    CommandType.AI_MESSAGE so it is forwarded directly to the AI model.

    Args:
        text: The raw string the user typed.

    Returns:
        A ParsedCommand with the matched type and any relevant args.
    """
    t  = text.strip()       # original casing (needed for paths / text)
    tl = t.lower()           # lowercase for case-insensitive matching

    # ── Exit ──────────────────────────────────────────────────────────────
    if tl in ("exit", "quit", "bye", "/exit", "/quit"):
        return ParsedCommand(CommandType.EXIT)

    # ── Help ──────────────────────────────────────────────────────────────
    if tl in ("help", "?", "/help"):
        return ParsedCommand(CommandType.HELP)

    # ── Chat management ───────────────────────────────────────────────────
    if tl == "new chat":
        return ParsedCommand(CommandType.NEW_CHAT)

    if tl in ("list chats", "/chats"):
        return ParsedCommand(CommandType.LIST_CHATS)

    m = re.fullmatch(r"load\s+chat\s+(\d+)", tl)
    if m:
        return ParsedCommand(CommandType.LOAD_CHAT, {"chat_id": int(m.group(1))})

    m = re.fullmatch(r"delete\s+chat\s+(\d+)", tl)
    if m:
        return ParsedCommand(CommandType.DELETE_CHAT, {"chat_id": int(m.group(1))})

    if tl == "clear chat":
        return ParsedCommand(CommandType.CLEAR_CHAT)

    # ── Memory ────────────────────────────────────────────────────────────
    m = re.fullmatch(r"remember\s+(.+)", t, re.IGNORECASE)
    if m:
        return ParsedCommand(CommandType.REMEMBER, {"text": m.group(1).strip()})

    if tl in ("show memory", "my memory", "/memory"):
        return ParsedCommand(CommandType.SHOW_MEMORY)

    m = re.fullmatch(r"delete\s+memory(?:\s+(\d+))?", tl)
    if m:
        mid = int(m.group(1)) if m.group(1) else None
        return ParsedCommand(CommandType.DELETE_MEMORY, {"memory_id": mid})

    # ── Reminders ─────────────────────────────────────────────────────────
    if re.search(r"remind\s+me\s+to\s+", tl):
        return ParsedCommand(CommandType.REMINDER, {"text": t})

    if tl in ("list reminders", "show reminders", "/reminders"):
        return ParsedCommand(CommandType.LIST_REMINDERS)

    # ── System power ──────────────────────────────────────────────────────
    if tl in ("shutdown pc", "shutdown", "shut down pc", "shut down"):
        return ParsedCommand(CommandType.SHUTDOWN_PC)

    if tl in ("restart pc", "restart", "reboot"):
        return ParsedCommand(CommandType.RESTART_PC)

    # ── App launcher ─────────────────────────────────────────────────────
    m = re.fullmatch(r"open\s+(.+)", tl)
    if m:
        return ParsedCommand(CommandType.OPEN_APP, {"app": m.group(1).strip()})

    # ── Time & basic system info ──────────────────────────────────────────
    if tl in ("show time", "time", "/time", "what time is it", "current time"):
        return ParsedCommand(CommandType.SHOW_TIME)

    if tl in ("system info", "sysinfo", "/sysinfo", "system information"):
        return ParsedCommand(CommandType.SYSTEM_INFO)

    # ── Monitoring ────────────────────────────────────────────────────────
    if tl in ("cpu usage", "cpu", "/cpu", "show cpu"):
        return ParsedCommand(CommandType.CPU_USAGE)

    if tl in ("ram usage", "ram", "memory usage", "/ram", "show ram"):
        return ParsedCommand(CommandType.RAM_USAGE)

    if tl in ("disk usage", "disk", "/disk", "show disk", "storage"):
        return ParsedCommand(CommandType.DISK_USAGE)

    if tl in ("network stats", "network", "/network", "net stats", "bandwidth"):
        return ParsedCommand(CommandType.NETWORK_STATS)

    if tl in ("top processes", "processes", "/processes", "running processes", "top procs"):
        return ParsedCommand(CommandType.TOP_PROCESSES)

    if tl in ("system status", "status", "/status", "dashboard", "monitor"):
        return ParsedCommand(CommandType.SYSTEM_STATUS)

    # ── File tools ────────────────────────────────────────────────────────
    m = re.fullmatch(r"read\s+file\s+(.+)", t, re.IGNORECASE)
    if m:
        return ParsedCommand(CommandType.READ_FILE, {"path": m.group(1).strip()})

    # "search files <keyword>" or "search files <keyword> in <dir>"
    m = re.fullmatch(r"search\s+files?\s+(.+?)(?:\s+in\s+(.+))?", t, re.IGNORECASE)
    if m:
        return ParsedCommand(CommandType.SEARCH_FILES, {
            "keyword": m.group(1).strip(),
            "root":    (m.group(2) or ".").strip(),
        })

    # "summarize file <path>" or "summarize <path>"
    m = re.fullmatch(r"summarize\s+(?:file\s+)?(.+)", t, re.IGNORECASE)
    if m:
        return ParsedCommand(CommandType.SUMMARIZE_FILE, {"path": m.group(1).strip()})

    # ── Web research ──────────────────────────────────────────────────────
    m = re.fullmatch(r"research\s+(.+)", t, re.IGNORECASE)
    if m:
        return ParsedCommand(CommandType.RESEARCH, {"topic": m.group(1).strip()})

    # ── Task agent ────────────────────────────────────────────────────────
    m = re.fullmatch(r"(?:plan|agent|task)\s+(.+)", t, re.IGNORECASE)
    if m:
        return ParsedCommand(CommandType.TASK_AGENT, {"goal": m.group(1).strip()})

    # ── Model switching ───────────────────────────────────────────────────
    m = re.fullmatch(r"/model\s+(\S+)", tl)
    if m:
        return ParsedCommand(CommandType.SET_MODEL, {"model": m.group(1)})
    if tl in ("use cpu", "cpu mode", "disable gpu", "gpu off"):
        return ParsedCommand(CommandType.USE_CPU)

    if tl in ("use gpu", "gpu mode", "enable gpu", "gpu on"):
        return ParsedCommand(CommandType.USE_GPU)
    # ── Default: send to AI ───────────────────────────────────────────────
    return ParsedCommand(CommandType.AI_MESSAGE, {"text": t})
