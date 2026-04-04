"""
main.py
-------
Entry point for AI Buddy — a fully local AI assistant powered by Ollama.

Run with:
    python main.py

What this module does
  1. Initialises all sub-systems (AI engine, chat, memory, reminders).
  2. Creates a default chat session on startup.
  3. Injects the user's long-term memories as a system prompt.
  4. Enters the main input loop.
  5. Routes each input through the command handler:
       - Built-in commands are executed directly.
       - Everything else is streamed to Ollama and the reply is saved.
  6. Cleans up database connections on exit.
"""

import sys
import os
import json
import logging
import re
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.markdown import Markdown
from rich.columns import Columns
from rich.live import Live
from rich.spinner import Spinner
from rich.rule import Rule
from rich import box

from ai_engine import AIEngine
from chat_manager import ChatManager
from memory_manager import MemoryManager
from reminder_manager import ReminderManager
from task_agent import TaskAgent
from command_handler import parse_command, CommandType
from ai_action_parser import AIActionParser
from ai_action_tools import build_default_registry
from action_executor import execute_action
from tools.system_tools import open_application, show_time, system_info, shutdown_pc, restart_pc
from tools.file_tools import display_file, summarize_file, search_files
from tools.web_tools import research, fetch_and_summarize
from tools.monitoring_tools import (
    cpu_usage, ram_usage, disk_usage,
    network_stats, top_processes, system_status,
)

console = Console()

# ── Help text ─────────────────────────────────────────────────────────────
HELP_TEXT = """
[bold cyan]╔═══════════  AI BUDDY — COMMAND REFERENCE  ═══════════╗[/bold cyan]

[bold yellow]CHAT MANAGEMENT[/bold yellow]
  [green]new chat[/green]                     Create a new chat session
  [green]list chats[/green]                   Show all saved sessions
  [green]load chat <id>[/green]               Restore a session by its ID
  [green]delete chat <id>[/green]             Permanently delete a session
  [green]clear chat[/green]                   Erase messages in current session

[bold yellow]LONG-TERM MEMORY[/bold yellow]
  [green]remember <text>[/green]              Save a fact to long-term memory
  [green]show memory[/green]                  List all stored memories
  [green]delete memory[/green]                Delete all memories
  [green]delete memory <id>[/green]           Delete one memory by ID

[bold yellow]REMINDERS[/bold yellow]
  [green]remind me to <task> in <N> minutes[/green]
  [green]remind me to <task> in <N> hours[/green]
  [green]list reminders[/green]               Show pending reminders

[bold yellow]SYSTEM[/bold yellow]
  [green]open <app>[/green]                   Launch an app (chrome, vscode…)
  [green]show time[/green]                    Display current date & time
  [green]system info[/green]                  OS, CPU, RAM summary
  [green]shutdown pc[/green]                  Schedule shutdown (60 s delay)
  [green]restart pc[/green]                   Schedule restart (60 s delay)

[bold yellow]MONITORING[/bold yellow]
  [green]cpu usage[/green]                    CPU % and per-core breakdown
  [green]ram usage[/green]                    RAM and swap statistics
  [green]disk usage[/green]                   Disk usage per partition
  [green]network stats[/green]                Bytes sent / received
  [green]top processes[/green]                Top-10 CPU-hungry processes
  [green]system status[/green]                Full monitoring dashboard

[bold yellow]FILES[/bold yellow]
  [green]read file <path>[/green]             Display with syntax highlighting
  [green]search files <keyword>[/green]       Search files by name or content
  [green]search files <kw> in <dir>[/green]   Search in a specific directory
  [green]summarize file <path>[/green]        AI summary of a file (txt/md/pdf)

[bold yellow]WEB RESEARCH[/bold yellow]
  [green]research <topic>[/green]             Fetch & summarise web results

[bold yellow]TASK AGENT[/bold yellow]
  [green]plan <goal>[/green]                  Break a goal into steps and execute
  [green]agent <goal>[/green]                 Alias for plan

[bold yellow]MODEL[/bold yellow]
  [green]/model <name>[/green]                Switch Ollama model (e.g. /model mistral)
  [green]use cpu[/green]  /  [green]disable gpu[/green]        Force CPU-only mode (fixes CUDA errors)
  [green]use gpu[/green]  /  [green]enable gpu[/green]         Re-enable GPU acceleration

[bold yellow]OTHER[/bold yellow]
  [green]help[/green]  or  [green]?[/green]                  Show this help
  [green]exit[/green] / [green]quit[/green] / [green]bye[/green]           Exit AI Buddy
"""


# ── Banner ────────────────────────────────────────────────────────────────

def print_banner():
    """Display the startup banner with instructions."""
    title = Text()
    title.append("   AI BUDDY   ", style="bold white on blue")
    title.append("  Powered by Ollama  ", style="italic dim")

    console.print()
    console.print(Panel(title, border_style="blue", padding=(1, 6), expand=False))
    console.print(
        "[dim]Your local AI assistant is ready. "
        "Type [bold]help[/bold] or [bold]?[/bold] for commands.[/dim]\n"
    )


# ── Memory injection ──────────────────────────────────────────────────────

def inject_memory_context(chat_manager: ChatManager, memory_manager: MemoryManager):
    """
    Build a system message and store it as the first message in a new session.

    Always injects the formatting rules. Appends known user facts only when
    long-term memories exist. Skips injection if the session already has messages.
    """
    # Only inject at the very start of a fresh session
    if chat_manager.get_messages():
        return

    memories = memory_manager.get_all_memories()

    # Base prompt that enforces Markdown formatting in every response
    system_content = (
        "You are AI Buddy, a helpful, friendly, and knowledgeable personal assistant "
        "running entirely on the user's local machine.\n\n"
        "RESPONSE FORMAT RULES — always follow these:\n"
        "- Use Markdown formatting in every response.\n"
        "- Use **bold** for key terms and important points.\n"
        "- Use numbered lists or bullet points when listing multiple items.\n"
        "- Use `inline code` for commands, file names, or technical values.\n"
        "- Use fenced code blocks (```language) for any code snippets.\n"
        "- Use headings (## or ###) to separate major sections in longer answers.\n"
        "- Keep responses concise and well-structured."
    )

    if memories:
        memory_lines = "\n".join(f"- {m}" for m in memories)
        system_content += (
            "\n\nImportant facts you already know about the user:\n"
            f"{memory_lines}\n\n"
            "Use these facts naturally in conversation when relevant."
        )

    chat_manager.save_message("system", system_content)


# ── Streaming AI response ─────────────────────────────────────────────────

def stream_response(ai_engine: AIEngine, messages: list) -> str:
    """
    Collect the AI response while showing a live spinner, then render the
    complete reply as structured Markdown inside a styled Rich panel.

    Args:
        ai_engine: The initialised AIEngine instance.
        messages : The full conversation history to send.

    Returns:
        The complete AI response as a single string.
    """
    full_response = ""

    # ── Phase 1: collect tokens behind a live spinner ─────────────────────
    spinner = Spinner("dots", text="[dim]AI Buddy is thinking…[/dim]")
    with Live(spinner, refresh_per_second=12, transient=True):
        try:
            for token in ai_engine.stream_chat(messages):
                full_response += token
        except KeyboardInterrupt:
            pass

    # ── Phase 2: render as structured Markdown in a panel ─────────────────
    if full_response.strip():
        console.print(
            Panel(
                Markdown(full_response),
                title="[bold blue] AI Buddy [/bold blue]",
                border_style="blue",
                padding=(1, 2),
                expand=True,
            )
        )
    else:
        console.print("[dim]No response received.[/dim]")

    return full_response


def run_standard_chat(chat_manager: ChatManager, ai_engine: AIEngine):
    """Run the normal chat flow and persist assistant output."""
    messages = chat_manager.get_messages()
    response = stream_response(ai_engine, messages)
    if response:
        chat_manager.save_message("assistant", response)


def _setup_ai_action_logger() -> logging.Logger:
    """Create a dedicated file logger for AI action suggestions and outcomes."""
    logger = logging.getLogger("ai_actions")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database")
    os.makedirs(log_dir, exist_ok=True)
    handler = logging.FileHandler(os.path.join(log_dir, "ai_actions.log"), encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
    return logger


def _request_ai_action(ai_engine: AIEngine, user_input: str) -> str:
    """Ask Ollama for a JSON-only action suggestion."""
    system_prompt = (
        "You are an AI assistant that can suggest actions in JSON format. Only respond with JSON. "
        "Allowed actions: find_file, read_file, none. "
        "For find_file you must include parameters.filename. "
        "For read_file you must include parameters.filepath. "
        "Never suggest delete_file, command execution, or unrestricted file access."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},
    ]
    return ai_engine.chat(messages)


def _extract_candidate_file_ref(user_input: str) -> str | None:
    """Extract a likely file reference from natural language input."""
    text = user_input.strip()
    if not text:
        return None

    # Prefer quoted file references first.
    quoted = re.findall(r"['\"]([^'\"]+)['\"]", text)
    for value in quoted:
        cleaned = value.strip().strip(".,;:!?")
        if cleaned:
            return cleaned

    # Then try plain tokens that look like file names or relative paths.
    token_matches = re.findall(r"\b[\w./\\-]+\.[A-Za-z0-9]{1,8}\b", text)
    if token_matches:
        return token_matches[-1].strip().strip(".,;:!?")

    return None


def _enrich_action_params(user_input: str, action_name: str, params: dict) -> dict:
    """Fill missing tool parameters from the user's original request when possible."""
    enriched = dict(params or {})
    candidate = _extract_candidate_file_ref(user_input)

    if action_name == "find_file" and candidate and not enriched.get("filename"):
        # find_file expects a filename, not a full path.
        enriched["filename"] = os.path.basename(candidate)

    if action_name == "read_file" and candidate and not enriched.get("filepath"):
        enriched["filepath"] = candidate

    return enriched


# ── Main application loop ─────────────────────────────────────────────────

def main():
    """
    Primary entry point.

    Initialises all components, starts a default chat session, then
    enters the interactive input loop.
    """
    # ── Boot all sub-systems ──────────────────────────────────────────────
    ai_engine        = AIEngine()
    chat_manager     = ChatManager()
    memory_manager   = MemoryManager()
    reminder_manager = ReminderManager()
    task_agent       = TaskAgent(ai_engine, reminder_manager, memory_manager)
    action_registry  = build_default_registry()
    action_parser    = AIActionParser(set(action_registry.tools.keys()) | {"none"})
    action_logger    = _setup_ai_action_logger()
    print_banner()

    # Start a fresh default session
    chat_manager.new_chat()
    inject_memory_context(chat_manager, memory_manager)

    # ── Input loop ────────────────────────────────────────────────────────
    while True:
        try:
            session_label = chat_manager.current_title or "no session"
            user_input = console.input(
                f"[bold green]You[/bold green] [dim]({session_label})[/dim]> "
            ).strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Interrupt received — exiting AI Buddy.[/dim]")
            break

        if not user_input:
            continue

        cmd = parse_command(user_input)

        # ── Route to the appropriate handler ─────────────────────────────
        match cmd.type:

            # ── Exit ──────────────────────────────────────────────────────
            case CommandType.EXIT:
                console.print("[dim]Goodbye! See you next time.[/dim]")
                break

            # ── Help ──────────────────────────────────────────────────────
            case CommandType.HELP:
                console.print(HELP_TEXT)

            # ── Chat management ───────────────────────────────────────────
            case CommandType.NEW_CHAT:
                chat_manager.new_chat()
                inject_memory_context(chat_manager, memory_manager)

            case CommandType.LIST_CHATS:
                chat_manager.list_chats()

            case CommandType.LOAD_CHAT:
                history = chat_manager.load_chat(cmd.args["chat_id"])
                if history:
                    console.print(
                        f"[dim]Restored [bold]{len(history)}[/bold] message(s) from history.[/dim]"
                    )

            case CommandType.DELETE_CHAT:
                chat_manager.delete_chat(cmd.args["chat_id"])

            case CommandType.CLEAR_CHAT:
                chat_manager.clear_chat()

            # ── Memory ────────────────────────────────────────────────────
            case CommandType.REMEMBER:
                memory_manager.remember(cmd.args["text"])

            case CommandType.SHOW_MEMORY:
                memory_manager.show_memory()

            case CommandType.DELETE_MEMORY:
                memory_manager.delete_memory(cmd.args.get("memory_id"))

            # ── Reminders ─────────────────────────────────────────────────
            case CommandType.REMINDER:
                reminder_manager.set_reminder(cmd.args["text"])

            case CommandType.LIST_REMINDERS:
                reminder_manager.list_reminders()

            # ── System ────────────────────────────────────────────────────
            case CommandType.OPEN_APP:
                open_application(cmd.args["app"])

            case CommandType.SHOW_TIME:
                show_time()

            case CommandType.SYSTEM_INFO:
                system_info()

            case CommandType.SHUTDOWN_PC:
                shutdown_pc()

            case CommandType.RESTART_PC:
                restart_pc()

            # ── Monitoring ────────────────────────────────────────────────
            case CommandType.CPU_USAGE:
                cpu_usage()

            case CommandType.RAM_USAGE:
                ram_usage()

            case CommandType.DISK_USAGE:
                disk_usage()

            case CommandType.NETWORK_STATS:
                network_stats()

            case CommandType.TOP_PROCESSES:
                top_processes()

            case CommandType.SYSTEM_STATUS:
                system_status()

            # ── Files ─────────────────────────────────────────────────────
            case CommandType.READ_FILE:
                display_file(cmd.args["path"])

            case CommandType.SEARCH_FILES:
                search_files(cmd.args["keyword"], cmd.args.get("root", "."))

            case CommandType.SUMMARIZE_FILE:
                summary = summarize_file(cmd.args["path"], ai_engine)
                console.print(
                    Panel(
                        Markdown(summary),
                        title="[cyan]File Summary[/cyan]",
                        border_style="cyan",
                    )
                )
                chat_manager.save_message("assistant", summary)

            # ── Web research ──────────────────────────────────────────────
            case CommandType.RESEARCH:
                result = research(cmd.args["topic"], ai_engine)
                if result:
                    console.print(
                        Panel(
                            Markdown(result),
                            title=f"[blue]Research: {cmd.args['topic'][:50]}[/blue]",
                            border_style="blue",
                            padding=(1, 2),
                        )
                    )
                    chat_manager.save_message("assistant", result)

            # ── Task agent ────────────────────────────────────────────────
            case CommandType.TASK_AGENT:
                plan = task_agent.run(cmd.args["goal"])
                if plan:
                    chat_manager.save_message("assistant", plan)

            # ── Model switching ───────────────────────────────────────────
            case CommandType.SET_MODEL:
                ai_engine.set_model(cmd.args["model"])

            case CommandType.USE_CPU:
                ai_engine.disable_gpu()

            case CommandType.USE_GPU:
                ai_engine.enable_gpu()

            # ── Forward to AI ─────────────────────────────────────────────
            case CommandType.AI_MESSAGE:
                # 1. Save the user message
                chat_manager.save_message("user", user_input)

                # 2. Ask AI for a structured action first
                raw_action = _request_ai_action(ai_engine, user_input)
                action, parse_error = action_parser.parse(raw_action)

                if parse_error:
                    action_logger.warning(
                        "invalid_action_response | error=%s | raw=%s",
                        parse_error,
                        raw_action,
                    )
                    run_standard_chat(chat_manager, ai_engine)
                    continue

                action_logger.info(
                    "suggested_action | action=%s | parameters=%s",
                    action.action,
                    json.dumps(action.parameters, ensure_ascii=True),
                )

                # 3. If no action is needed, fallback to normal chat
                if action.action == "none":
                    run_standard_chat(chat_manager, ai_engine)
                    continue

                # 4. Execute action through centralized permission gate
                effective_params = _enrich_action_params(user_input, action.action, action.parameters)
                result = execute_action(action.action, effective_params, action_registry.tools)
                action_logger.info(
                    "execution_result | action=%s | success=%s | result=%s",
                    action.action,
                    result.get("success", False),
                    json.dumps(result, ensure_ascii=True),
                )

                if result.get("success"):
                    console.print("Execution successful")
                    if action.action == "find_file":
                        matches = result.get("matches", [])
                        details = result.get("match_details", [])
                        if matches:
                            console.print("Found file(s):")
                            if details:
                                for item in details:
                                    console.print(f"- {item.get('path', '')}")
                                    console.print(f"  created: {item.get('created_at', 'unknown')}")
                                    console.print(f"  modified: {item.get('modified_at', 'unknown')}")
                            else:
                                for match in matches:
                                    console.print(f"- {match}")
                            chat_manager.save_message(
                                "assistant",
                                f"Executed find_file and found {len(matches)} match(es).",
                            )
                        else:
                            console.print("No matching file found in allowed directories.")
                            chat_manager.save_message("assistant", "Executed find_file: no matches found.")
                    elif action.action == "read_file":
                        content = result.get("content", "")
                        path = result.get("path", "")
                        console.print(
                            Panel(
                                content,
                                title=f"[cyan]read_file: {path}[/cyan]",
                                border_style="cyan",
                            )
                        )
                        chat_manager.save_message("assistant", f"Executed read_file on: {path}")
                else:
                    error_msg = result.get("error", "Unknown error")
                    console.print(f"Execution failed: {error_msg}")
                    chat_manager.save_message("assistant", f"Action failed: {error_msg}")

    # ── Cleanup ───────────────────────────────────────────────────────────
    chat_manager.close()
    memory_manager.close()


if __name__ == "__main__":
    main()
