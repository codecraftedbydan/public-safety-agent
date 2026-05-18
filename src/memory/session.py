"""Session state helpers — initialise and reset per-conversation state."""
from __future__ import annotations

from langchain_core.messages import HumanMessage

from src.agent.state import AgentState
from src.memory.long_term import build_session_context


def new_session_state(query: str) -> AgentState:
    """Create a fresh AgentState for a new conversation turn.

    Loads long-term memory context (Tier 2 + Tier 3) so the agent has
    awareness of prior sessions without carrying stale raw history.
    """
    session_summary = build_session_context(query)

    return AgentState(
        messages=[HumanMessage(content=query)],
        query=query,
        plan=[],
        plan_rationale="",
        tool_outputs=[],
        session_summary=session_summary,
        evaluation="",
        evaluation_notes="",
        final_response="",
        sources=[],
        iterations=0,
        _tool_calls_raw=[],
    )
