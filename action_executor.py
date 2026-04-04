"""
action_executor.py
------------------
Centralized permission-gated execution for all AI Buddy tools/actions.
"""

from __future__ import annotations

from typing import Any, Callable


ToolMap = dict[str, Callable[..., Any]]
SAFE_ACTIONS = ["find_file", "read_file"]
REQUIRED_PARAMS = {
    "find_file": ["filename"],
    "read_file": ["filepath"],
}


def validate_params(action: str, params: dict) -> bool:
    """Validate required parameters for actions that define a required schema."""
    if action not in REQUIRED_PARAMS:
        return True

    required = REQUIRED_PARAMS[action]
    for key in required:
        value = params.get(key)
        if value is None:
            return False
        if isinstance(value, str) and not value.strip():
            return False

    return True


def _missing_params(action: str, params: dict) -> list[str]:
    """Return required parameter names that are missing or empty."""
    required = REQUIRED_PARAMS.get(action, [])
    missing: list[str] = []
    for key in required:
        value = params.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(key)
    return missing


def request_permission(action: str, params: dict) -> bool:
    """Ask user approval before running an action."""
    print(f"AI wants to perform: {action} with {params}")
    answer = input("Allow this action? (yes/no): ").strip().lower()
    return answer in ("yes", "y")


def execute_action(action: str, params: dict, tools: ToolMap) -> dict[str, Any]:
    """
    Execute a registered action only after explicit permission.

    Returns a standard result payload:
      {"success": bool, ...}
    """
    print(f"[DEBUG] Action received: {action}")
    print(f"AI suggests: {action} with {params}")
    print(f"[DEBUG] Params received: {params}")

    if action not in tools:
        print("Unknown action")
        return {"success": False, "error": f"Unknown action: {action}"}

    # Accept legacy key from model/tooling and normalize to required schema.
    if action == "read_file" and params.get("path") and not params.get("filepath"):
        params["filepath"] = params["path"]

    if not validate_params(action, params):
        print(f"Missing required parameters for {action}")
        print(f"Required: {REQUIRED_PARAMS[action]}")

        # Smart fallback: ask user for missing parameters, then re-validate.
        for key in _missing_params(action, params):
            user_value = input(f"Please provide {key}: ").strip()
            if user_value:
                params[key] = user_value

        if not validate_params(action, params):
            return {
                "success": False,
                "error": f"Missing required parameters for {action}",
                "required": REQUIRED_PARAMS[action],
            }

    # Map validated parameter names to current tool function signature.
    if action == "read_file" and params.get("filepath") and not params.get("path"):
        params["path"] = params["filepath"]

    if action not in SAFE_ACTIONS:
        if not request_permission(action, params):
            print("Action denied by user.")
            return {"success": False, "denied": True, "error": "User denied permission."}

    print(f"Executing action: {action}")
    try:
        raw_result = tools[action](**params)
    except Exception as exc:
        print(f"Execution failed: {exc}")
        return {"success": False, "error": str(exc)}

    if isinstance(raw_result, dict):
        result = dict(raw_result)
        result.setdefault("success", True)
    else:
        result = {"success": True, "result": raw_result}

    if result.get("success"):
        print(f"Result: {result}")
    else:
        print(f"Error: {result.get('error', 'Unknown error')}")

    return result
