# AI Buddy

A terminal assistant that talks to a local Ollama model, stores chats and memories in SQLite, schedules reminders, and exposes file, web, and system tools. Web research uses network access even though model inference is local.

## Setup

Install Python with support for the source's modern type annotations and an Ollama installation. From this directory:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
ollama pull llama3
```

Start Ollama with `ollama serve` if it is not already running, then start the assistant in another terminal:

```sh
.venv/bin/python main.py
```

The default model is `llama3` in `ai_engine.py`. Use `/model <name>` to select another installed model. `use cpu` disables GPU acceleration; CUDA errors also trigger a CPU retry.

## Usage and architecture

Start with `help`. Examples include `summarize file notes.txt`, `search files report`, `research <topic>`, and `plan <goal>`. Exit with `exit` or `quit`.

`main.py` initializes chat, memory, reminders, and tools and routes terminal input through `command_handler.py`. `ai_engine.py` streams Ollama responses. `chat_manager.py` and `memory_manager.py` persist data; `reminder_manager.py` schedules notifications. `ai_action_parser.py`, `ai_action_tools.py`, and `action_executor.py` parse and execute registered actions. `tools/` contains file, web, monitoring, and operating-system helpers.

The separate planner in `task_agent.py` generates a 3–7 step plan and executes recognized reminder/note steps. THINK, SEARCH, and RESPOND planning steps are acknowledged rather than executed by that planner.

## Data and operational limits

`database/` contains tracked SQLite files and an action log. Those files may already contain data; use a separate disposable checkout for experiments and avoid committing new personal chats, memories, or log content. The app includes system actions such as opening programs, shutdown, and restart; inspect the command and action handlers before enabling unfamiliar actions. Desktop notifications and system commands depend on the operating system.

No automated tests or packaged deployment configuration are included. Check ordinary chat, model switching, a disposable memory, and a short reminder manually. If connection fails, verify the Ollama server and downloaded model; if notifications fail, check the desktop environment and plyer support.

## More documentation

- [Source, command, and configuration reference](docs/REFERENCE.md)
- [Contributing](CONTRIBUTING.md)
