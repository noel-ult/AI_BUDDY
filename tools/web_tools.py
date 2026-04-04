"""
tools/web_tools.py
------------------
Web research tool for AI Buddy.

Fetches the textual content of a web page (DuckDuckGo search or direct URL),
strips HTML boilerplate, then passes the cleaned text to the AI model for a
concise summary.

Public API
  research(topic, ai_engine)  — search topic → fetch top result → summarise
  fetch_and_summarize(url, ai_engine) — fetch a specific URL and summarise

Strategy (no API key required)
  1. Build a DuckDuckGo Lite search URL for the topic.
  2. Parse the first real result link from the HTML response.
  3. Fetch that page, extract readable text with html.parser.
  4. Trim to MAX_CHARS and send to the AI model for summarization.
"""

import re
import urllib.request
import urllib.parse
import urllib.error
from html.parser import HTMLParser
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.spinner import Spinner
from rich.live import Live

console = Console()

MAX_CHARS = 6_000          # text sent to the AI — keep context manageable
REQUEST_TIMEOUT = 12       # seconds

# Browser-like User-Agent so sites do not reject the request
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


# ── Minimal HTML → plain-text parser ────────────────────────────────────

class _TextExtractor(HTMLParser):
    """Strip HTML tags and collect visible text nodes."""

    # Tags whose content we skip entirely
    _SKIP = {"script", "style", "noscript", "head", "nav", "footer",
              "header", "aside", "form", "button", "svg", "iframe"}

    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self.chunks: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self._SKIP and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self.chunks.append(stripped)


def _html_to_text(html: str) -> str:
    """Convert raw HTML to a clean plain-text string."""
    parser = _TextExtractor()
    parser.feed(html)
    text = " ".join(parser.chunks)
    # Collapse runs of whitespace
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


# ── HTTP helper ──────────────────────────────────────────────────────────

def _fetch(url: str) -> str | None:
    """
    Perform a simple GET request and return the response body as a string.

    Returns None on any network or HTTP error, printing a message first.
    """
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        console.print(f"[red]HTTP {exc.code} fetching:[/red] {url}")
    except urllib.error.URLError as exc:
        console.print(f"[red]Network error:[/red] {exc.reason}")
    except Exception as exc:
        console.print(f"[red]Fetch error:[/red] {exc}")
    return None


# ── DuckDuckGo search ─────────────────────────────────────────────────────

def _ddg_search(query: str) -> str | None:
    """
    Query DuckDuckGo Lite and return the URL of the first organic result.

    DuckDuckGo Lite is a lightweight HTML page — no JavaScript required.
    Results appear as <a rel="nofollow" href="..."> links.

    Returns the first result URL, or None if none is found.
    """
    encoded = urllib.parse.quote_plus(query)
    search_url = f"https://lite.duckduckgo.com/lite/?q={encoded}"
    html = _fetch(search_url)
    if not html:
        return None

    # DuckDuckGo Lite wraps result links — grab the first one
    matches = re.findall(
        r'<a[^>]+class=["\']result-link["\'][^>]*href=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if not matches:
        # Fallback: any link with a real domain
        matches = re.findall(
            r'href=["\']((https?://(?!duckduckgo)[^"\']+))["\']',
            html,
            re.IGNORECASE,
        )
    return matches[0] if matches else None


# ── Public API ────────────────────────────────────────────────────────────

def research(topic: str, ai_engine) -> str:
    """
    Research a topic: search DuckDuckGo, fetch the top page, summarise.

    Args:
        topic     : The research query (user-supplied text).
        ai_engine : An AIEngine instance used to produce the summary.

    Returns:
        AI-generated research summary string.
    """
    console.print(f"[dim]Searching for:[/dim] [bold]{topic}[/bold]")

    url = _ddg_search(topic)
    if not url:
        # Fall back to a direct Wikipedia search if DDG fails
        encoded = urllib.parse.quote_plus(topic)
        url = f"https://en.wikipedia.org/wiki/Special:Search?search={encoded}&go=Go"
        console.print(f"[yellow]DDG returned no results. Trying Wikipedia…[/yellow]")

    console.print(f"[dim]Fetching:[/dim] [cyan]{url}[/cyan]")
    return fetch_and_summarize(url, ai_engine, topic=topic)


def fetch_and_summarize(url: str, ai_engine, topic: str = "") -> str:
    """
    Fetch a URL, extract its text content, and ask the AI to summarise it.

    Args:
        url       : Fully qualified URL to fetch.
        ai_engine : An AIEngine instance used to produce the summary.
        topic     : Optional hint used in the AI prompt.

    Returns:
        AI-generated summary string, or an error message.
    """
    full_response = ""

    spinner = Spinner("dots", text=f"[dim]Fetching and analysing…[/dim]")
    with Live(spinner, refresh_per_second=12, transient=True):
        html = _fetch(url)
        if not html:
            return "Could not retrieve page content."

        text = _html_to_text(html)
        if not text:
            return "The page contained no readable text."

        truncated = text[:MAX_CHARS]
        if len(text) > MAX_CHARS:
            truncated += "\n\n...[content truncated]..."

        subject = topic or url
        messages = [
            {
                "role": "user",
                "content": (
                    f"I fetched a web page about: **{subject}**\n\n"
                    f"Here is the extracted text:\n\n{truncated}\n\n"
                    "Please provide a clear, structured summary with:\n"
                    "- A brief **overview** (2-3 sentences)\n"
                    "- **Key points** as a bullet list\n"
                    "- A short **conclusion**"
                ),
            }
        ]

        for token in ai_engine.stream_chat(messages):
            full_response += token

    return full_response
