"""
ai_action_parser.py
-------------------
Safely parse and validate JSON actions suggested by the AI model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class AIAction:
    """Validated AI action object."""

    action: str
    parameters: dict[str, Any]


class AIActionParser:
    """Parses and validates AI JSON action responses."""

    def __init__(self, allowed_actions: set[str]):
        self.allowed_actions = allowed_actions

    def parse(self, raw_response: str) -> tuple[AIAction | None, str | None]:
        """
        Parse and validate a raw model response.

        Returns:
            (AIAction, None) on success, otherwise (None, reason).
        """
        payload, error = self._extract_json(raw_response)
        if error:
            return None, error

        if not isinstance(payload, dict):
            return None, "AI response JSON must be an object"

        action = payload.get("action")
        if not isinstance(action, str) or not action.strip():
            return None, "Missing or invalid 'action'"

        action = action.strip()

        params = payload.get("parameters", {})
        if action == "none":
            return AIAction(action="none", parameters={}), None

        if not isinstance(params, dict):
            return None, "'parameters' must be an object"

        return AIAction(action=action, parameters=params), None

    def _extract_json(self, raw_response: str) -> tuple[dict[str, Any] | None, str | None]:
        """Extract and parse JSON from model output (strict first, fallback bracket scan)."""
        text = (raw_response or "").strip()
        if not text:
            return None, "Empty AI response"

        try:
            return json.loads(text), None
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None, "No JSON object found in AI response"

        snippet = text[start : end + 1]
        try:
            return json.loads(snippet), None
        except json.JSONDecodeError as exc:
            return None, f"Malformed JSON: {exc}"

