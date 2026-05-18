"""AgentState — the single source of truth passed between all graph nodes."""
from __future__ import annotations

from typing import Annotated, Any
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    # ── Conversation ────────────────────────────────────────────────────────
    messages: Annotated[list[BaseMessage], add_messages]  # full message history
    query: str                                             # current user query

    # ── Planning ─────────────────────────────────────────────────────────────
    plan: list[str]      # tool calls the planner decided to make
    plan_rationale: str  # planner's explanation — surfaced in briefing trace

    # ── Tool execution ───────────────────────────────────────────────────────
    tool_outputs: list[dict[str, Any]]  # raw outputs from every tool call this turn

    # ── Memory ───────────────────────────────────────────────────────────────
    session_summary: str  # rolling summary of prior turns loaded at session start

    # ── Evaluation ───────────────────────────────────────────────────────────
    evaluation: str  # "sufficient" | "insufficient"
    evaluation_notes: str  # evaluator's explanation

    # ── Output ───────────────────────────────────────────────────────────────
    final_response: str         # the formatted briefing
    sources: list[dict[str, str]]  # {title, url, date, source_name}

    # ── Loop guard ───────────────────────────────────────────────────────────
    iterations: int  # incremented each time planner runs; capped at 3

    # ── Internal planner→router handoff ──────────────────────────────────────
    # Structured tool calls produced by planner_node; consumed by tool_router_node.
    # Stored in state so LangGraph persists them across the edge.
    _tool_calls_raw: list[dict[str, Any]]
