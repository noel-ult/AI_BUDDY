"""
ai_engine.py
------------
Handles all communication with the Ollama language model.
Connects Python to Ollama using the official `ollama` Python package.

Default model : llama3
Supports      : single-shot chat and streaming chat
"""

import ollama
from rich.console import Console

console = Console()

DEFAULT_MODEL = "llama3"


class AIEngine:
    """Manages communication with a locally-running Ollama model."""

    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model
        self._gpu_disabled = False   # flipped to True on CUDA error or by user
        self._verify_model()

    # ── Internal helpers ────────────────────────────────────────────────

    def _verify_model(self):
        """
        Check whether the chosen model is available in the local Ollama
        installation and warn the user if it is not.
        """
        try:
            result = ollama.list()

            # Support both attribute-style (newer library) and dict-style responses
            if hasattr(result, "models"):
                models_data = result.models
            else:
                models_data = result.get("models", [])

            available: list[str] = []
            for m in models_data:
                if hasattr(m, "model"):
                    available.append(m.model)
                elif hasattr(m, "name"):
                    available.append(m.name)
                elif isinstance(m, dict):
                    available.append(m.get("model", m.get("name", "")))

            if available and not any(self.model in name for name in available):
                console.print(
                    f"[yellow]Warning: Model '[bold]{self.model}[/bold]' was not found locally. "
                    f"Run '[bold]ollama pull {self.model}[/bold]' to download it.[/yellow]"
                )
        except Exception as exc:
            console.print(f"[red]Could not connect to Ollama: {exc}[/red]")
            console.print(
                "[yellow]Make sure Ollama is running. "
                "Start it with: [bold]ollama serve[/bold][/yellow]"
            )

    # ── Public interface ────────────────────────────────────────────────

    # ── GPU helpers ─────────────────────────────────────────────────────

    def disable_gpu(self):
        """Force all future requests to run on CPU only (num_gpu=0)."""
        self._gpu_disabled = True
        console.print("[yellow]GPU disabled — running on CPU. Responses will be slower.[/yellow]")

    def enable_gpu(self):
        """Re-enable GPU acceleration."""
        self._gpu_disabled = False
        console.print("[green]GPU re-enabled.[/green]")

    @property
    def _options(self) -> dict:
        """Build the options dict passed to every Ollama call."""
        return {"num_gpu": 0} if self._gpu_disabled else {}

    # ── Public interface ────────────────────────────────────────────────

    def chat(self, messages: list) -> str:
        """
        Send a list of messages to the Ollama model and return the full response.

        Args:
            messages: List of dicts with keys 'role' and 'content'.
                      Roles: 'user', 'assistant', 'system'.

        Returns:
            The model's response as a plain string.
        """
        try:
            response = ollama.chat(model=self.model, messages=messages, options=self._options)
            # Support both attribute-style and dict-style responses
            msg = response.message if hasattr(response, "message") else response["message"]
            return msg.content if hasattr(msg, "content") else msg["content"]
        except Exception as exc:
            if "cuda" in str(exc).lower() and not self._gpu_disabled:
                console.print("\n[yellow]⚠ CUDA error — switching to CPU mode and retrying…[/yellow]")
                self._gpu_disabled = True
                try:
                    response = ollama.chat(model=self.model, messages=messages, options={"num_gpu": 0})
                    msg = response.message if hasattr(response, "message") else response["message"]
                    return msg.content if hasattr(msg, "content") else msg["content"]
                except Exception as retry_exc:
                    return f"[AI Error after CPU fallback: {retry_exc}]"
            return f"[AI Error: {exc}]"

    def stream_chat(self, messages: list):
        """
        Stream the AI response token by token.

        Args:
            messages: Same format as chat().

        Yields:
            str chunks of the response as they arrive from Ollama.
        """
        def _do_stream(opts: dict):
            stream = ollama.chat(model=self.model, messages=messages, stream=True, options=opts)
            for chunk in stream:
                msg = chunk.message if hasattr(chunk, "message") else chunk.get("message", {})
                token = msg.content if hasattr(msg, "content") else msg.get("content", "")
                if token:
                    yield token

        try:
            yield from _do_stream(self._options)
        except Exception as exc:
            if "cuda" in str(exc).lower() and not self._gpu_disabled:
                console.print("\n[yellow]⚠ CUDA error detected — switching to CPU mode and retrying…[/yellow]")
                self._gpu_disabled = True
                try:
                    yield from _do_stream({"num_gpu": 0})
                except Exception as retry_exc:
                    yield f"[Stream Error after CPU fallback: {retry_exc}]"
            else:
                yield f"[Stream Error: {exc}]"

    def set_model(self, model: str):
        """Switch to a different Ollama model at runtime."""
        self.model = model
        console.print(f"[green]Model switched to:[/green] [bold]{model}[/bold]")
        self._verify_model()
