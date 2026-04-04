"""
task_agent.py
-------------
Autonomous Task Agent for AI Buddy.

The agent receives a high-level goal from the user and:
  1. Asks the AI model to decompose it into numbered steps.
  2. Parses each step back from the AI response.
  3. Executes actionable steps (set reminders, create notes, etc.) and
     presents the full plan to the user in a formatted Rich panel.

This implements a minimal "plan-and-execute" loop without requiring
LangChain or any external agent framework — just plain Ollama calls.

Public API
  TaskAgent.run(goal)  — analyse, plan, and (optionally) execute a goal
"""

import re
from dataclasses import dataclass, field
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from rich.spinner import Spinner
from rich.live import Live
from rich import box

console = Console()


# ── Data structures ───────────────────────────────────────────────────────

@dataclass
class Step:
    """A single step in the agent's action plan."""
    number:      int
    description: str
    action_type: str = "think"       # "think" | "reminder" | "note" | "search"
    action_args: dict = field(default_factory=dict)
    executed:    bool = False
    result:      str  = ""


# ── Planning prompt ───────────────────────────────────────────────────────

_PLAN_SYSTEM = """You are an autonomous task planning agent.
When given a goal, respond ONLY with a numbered action plan.

Format each step exactly like this:
1. [ACTION_TYPE] Description of the step
2. [ACTION_TYPE] Description of the step
...

ACTION_TYPE must be one of:
- THINK     : analyse or consider something
- REMINDER  : set a reminder for the user
- NOTE      : save a note or important information
- SEARCH    : look up information
- RESPOND   : provide a response or output to the user

Keep the plan concise (3-7 steps). No preamble, no explanation outside the list."""

_PLAN_USER = "Goal: {goal}\n\nCreate a step-by-step action plan."


# ── Step parser ───────────────────────────────────────────────────────────

_STEP_RE = re.compile(
    r"^\s*(\d+)[.)]\s*(?:\[([A-Z_]+)\])?\s*(.+)$",
    re.MULTILINE,
)

def _parse_steps(plan_text: str) -> list[Step]:
    """
    Extract numbered steps from the AI planning response.

    Args:
        plan_text: Raw text returned by the AI model.

    Returns:
        List of Step objects.
    """
    steps = []
    for m in _STEP_RE.finditer(plan_text):
        num         = int(m.group(1))
        action_type = (m.group(2) or "THINK").upper()
        description = m.group(3).strip()

        # Normalise to known types
        if action_type not in ("THINK", "REMINDER", "NOTE", "SEARCH", "RESPOND"):
            action_type = "THINK"

        steps.append(Step(
            number=num,
            description=description,
            action_type=action_type.lower(),
        ))

    return steps


# ── Step executor ─────────────────────────────────────────────────────────

def _execute_step(step: Step, reminder_manager, memory_manager) -> str:
    """
    Attempt to automatically execute an actionable step.

    Args:
        step              : The Step to execute.
        reminder_manager  : ReminderManager instance.
        memory_manager    : MemoryManager instance (for NOTE steps).

    Returns:
        A short result string describing what happened.
    """
    if step.action_type == "reminder":
        # Try to extract a duration from the description
        m = re.search(r"(\d+)\s*(minute|hour|second|min|hr)", step.description, re.I)
        if m:
            task_text = re.sub(
                r"\s*in\s+\d+\s*\w+", "", step.description, flags=re.I
            ).strip()
            synthetic = f"remind me to {task_text} in {m.group(1)} {m.group(2)}"
            success = reminder_manager.set_reminder(synthetic)
            return "Reminder set." if success else "Could not set reminder."
        return "Reminder step noted (no specific time found — please set manually)."

    if step.action_type == "note":
        memory_manager.remember(step.description)
        return "Saved to long-term memory."

    # THINK / SEARCH / RESPOND — non-executable, just acknowledged
    return ""


# ── Main agent class ──────────────────────────────────────────────────────

class TaskAgent:
    """
    Autonomous planning agent backed by an Ollama LLM.

    Usage:
        agent = TaskAgent(ai_engine, reminder_manager, memory_manager)
        agent.run("prepare a study plan for tomorrow")
    """

    def __init__(self, ai_engine, reminder_manager=None, memory_manager=None):
        self.ai_engine        = ai_engine
        self.reminder_manager = reminder_manager
        self.memory_manager   = memory_manager

    # ── Public interface ──────────────────────────────────────────────────

    def run(self, goal: str) -> str:
        """
        Plan and execute a goal.

        Args:
            goal: Natural-language description of what the user wants.

        Returns:
            The full plan text for display / saving to chat history.
        """
        console.print(
            f"\n[bold yellow]Task Agent[/bold yellow] [dim]— analysing goal:[/dim] "
            f"[white]{goal}[/white]\n"
        )

        # ── Phase 1: generate the plan ────────────────────────────────────
        plan_text = ""
        spinner = Spinner("dots2", text="[dim]Planning…[/dim]")
        messages = [
            {"role": "system", "content": _PLAN_SYSTEM},
            {"role": "user",   "content": _PLAN_USER.format(goal=goal)},
        ]

        with Live(spinner, refresh_per_second=12, transient=True):
            for token in self.ai_engine.stream_chat(messages):
                plan_text += token

        # ── Phase 2: parse into steps ─────────────────────────────────────
        steps = _parse_steps(plan_text)

        if not steps:
            # Fallback: display raw plan if steps could not be parsed
            console.print(
                Panel(
                    Markdown(plan_text),
                    title="[yellow]Task Plan[/yellow]",
                    border_style="yellow",
                    padding=(1, 2),
                )
            )
            return plan_text

        # ── Phase 3: display formatted step table ─────────────────────────
        table = Table(
            title=f"Task Plan — {goal[:60]}{'…' if len(goal) > 60 else ''}",
            box=box.ROUNDED,
            show_lines=True,
            expand=True,
        )
        table.add_column("#",    style="bold cyan",  justify="center", width=3)
        table.add_column("Type", style="dim",        justify="center", width=9)
        table.add_column("Action",                   min_width=40)
        table.add_column("Status", justify="center", width=12)

        _TYPE_STYLE = {
            "think":   "dim",
            "reminder":"magenta",
            "note":    "cyan",
            "search":  "blue",
            "respond": "green",
        }

        for step in steps:
            style  = _TYPE_STYLE.get(step.action_type, "white")
            status = "[dim]—[/dim]"

            # Auto-execute reminders and notes when managers are available
            if step.action_type in ("reminder", "note") and (
                self.reminder_manager or self.memory_manager
            ):
                result = _execute_step(step, self.reminder_manager, self.memory_manager)
                step.executed = True
                step.result   = result
                status = f"[green]✔ Done[/green]"
            elif step.action_type == "think":
                status = "[dim]✎ Planned[/dim]"
            elif step.action_type in ("search", "respond"):
                status = "[blue]⬡ Ready[/blue]"

            table.add_row(
                str(step.number),
                f"[{style}]{step.action_type.upper()}[/{style}]",
                step.description,
                status,
            )

        console.print(table)

        # ── Phase 4: elaborate on the plan ───────────────────────────────
        console.print(
            f"\n[dim]Asking AI to elaborate on the plan…[/dim]"
        )
        elaboration = ""
        elaborate_messages = [
            {"role": "system",    "content": (
                "You are AI Buddy. Provide helpful, structured advice. "
                "Use Markdown with headings, bullets, and **bold** for key points."
            )},
            {"role": "assistant", "content": plan_text},
            {"role": "user",      "content": (
                f"Based on this plan for '{goal}', give detailed, practical advice "
                "for each step. Keep it concise and actionable."
            )},
        ]

        spinner2 = Spinner("dots", text="[dim]Elaborating…[/dim]")
        with Live(spinner2, refresh_per_second=12, transient=True):
            for token in self.ai_engine.stream_chat(elaborate_messages):
                elaboration += token

        if elaboration.strip():
            console.print(
                Panel(
                    Markdown(elaboration),
                    title="[yellow]Detailed Guidance[/yellow]",
                    border_style="yellow",
                    padding=(1, 2),
                )
            )

        return plan_text + "\n\n" + elaboration
