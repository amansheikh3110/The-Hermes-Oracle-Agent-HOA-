"""Optional Hermes AIAgent chat."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cwt_agent.config import Settings


def hermes_available() -> bool:
    try:
        import run_agent  # noqa: F401

        return True
    except ImportError:
        return False


def run_hermes_turn(
    *,
    model: str,
    user_message: str,
    system_message: str | None = None,
    conversation_history: list[dict[str, Any]] | None = None,
    skip_memory: bool = False,
    settings: "Settings | None" = None,
    max_iterations: int = 12,
) -> dict[str, Any]:
    from hermes_constants import OPENROUTER_BASE_URL
    from run_agent import AIAgent

    from cwt_agent.openrouter_client import resolve_openrouter_key

    kwargs: dict[str, Any] = {
        "model": model,
        "quiet_mode": True,
        "skip_memory": skip_memory,
        "skip_context_files": True,
        "max_iterations": max_iterations,
        "base_url": OPENROUTER_BASE_URL,
        "disabled_toolsets": ["terminal", "browser"],
    }
    if settings is not None:
        hk = resolve_openrouter_key(settings)
        if hk:
            kwargs["api_key"] = hk
            os.environ["OPENROUTER_API_KEY"] = hk
            os.environ["OPENAI_API_KEY"] = hk

    agent = AIAgent(**kwargs)
    return agent.run_conversation(
        user_message=user_message,
        system_message=system_message,
        conversation_history=conversation_history,
    )
