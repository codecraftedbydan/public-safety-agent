"""All five LangGraph node functions."""
from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.agent.prompts import (
    EVALUATOR_SYSTEM,
    MEMORY_SUMMARISER_SYSTEM,
    PLANNER_SYSTEM,
    SYNTHESISER_SYSTEM,
)
from src.agent.state import AgentState
from src.config import settings
from src.memory.long_term import save_turn_summary
from src.tools import TOOL_MAP

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 3

# Optional Langfuse instrumentation
try:
    from langfuse.decorators import observe
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False
    # Dummy decorator if Langfuse is not available
    def observe(*args, **kwargs):
        def decorator(func):
            return func
        return decorator if args and callable(args[0]) is False else decorator


def _get_llm(temperature: float = 0.0) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_model,
        temperature=temperature,
        openai_api_key=settings.openai_api_key,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Node 1: Planner
# ─────────────────────────────────────────────────────────────────────────────

@observe(name="planner")
def planner_node(state: AgentState) -> dict[str, Any]:
    """Decide which tools to call and why."""
    llm = _get_llm()
    iterations = state.get("iterations", 0)

    refinement_note = ""
    if iterations > 0:
        eval_notes = state.get("evaluation_notes", "")
        refinement_note = (
            f"IMPORTANT: A previous retrieval attempt was marked insufficient. "
            f"Reason: {eval_notes}. "
            f"Adjust your tool selection or query arguments to address the gap."
        )

    system_prompt = PLANNER_SYSTEM.format(refinement_note=refinement_note)

    # Build context message
    context_parts = [f"User query: {state['query']}"]
    if state.get("session_summary"):
        context_parts.append(f"\nPrior session context:\n{state['session_summary']}")
    if iterations > 0 and state.get("tool_outputs"):
        outputs_preview = json.dumps(state["tool_outputs"], indent=2)[:1500]
        context_parts.append(f"\nPrevious tool outputs (summary):\n{outputs_preview}")

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content="\n".join(context_parts)),
    ]

    response = llm.invoke(messages)
    raw = response.content.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
        plan = [
            f"{tc['tool']}({json.dumps(tc.get('args', {}))})"
            for tc in parsed.get("tool_calls", [])
        ]
        rationale = parsed.get("rationale", "")
        tool_calls_raw = parsed.get("tool_calls", [])
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Planner produced invalid JSON: %s\nRaw: %s", exc, raw)
        # Fallback: use RAG retrieval only
        plan = [f"rag_retrieval_tool({{\"query\": \"{state['query']}\"}})" ]
        rationale = "Fallback plan — planner output was malformed."
        tool_calls_raw = [{"tool": "rag_retrieval_tool", "args": {"query": state["query"]}}]

    logger.info("Planner (iter %d): %s | %s", iterations, plan, rationale)

    return {
        "plan": plan,
        "plan_rationale": rationale,
        "iterations": iterations + 1,
        "_tool_calls_raw": tool_calls_raw,  # passed to tool_router via state trick
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 2: Tool Router
# ─────────────────────────────────────────────────────────────────────────────

@observe(name="tool_router")
def tool_router_node(state: AgentState) -> dict[str, Any]:
    """Execute the tools specified in the plan."""
    # Recover structured tool calls from the plan strings
    # We store them in state via a private key from planner
    tool_calls_raw = state.get("_tool_calls_raw", [])

    if not tool_calls_raw:
        # Parse from plan strings as fallback
        tool_calls_raw = []
        for step in state.get("plan", []):
            tool_name = step.split("(")[0]
            tool_calls_raw.append({"tool": tool_name, "args": {}})

    outputs: list[dict[str, Any]] = []
    for tc in tool_calls_raw:
        tool_name = tc.get("tool", "")
        tool_args = tc.get("args", {})

        if tool_name not in TOOL_MAP:
            logger.warning("Unknown tool requested: %s", tool_name)
            outputs.append({"tool": tool_name, "result": f"Unknown tool: {tool_name}", "error": True})
            continue

        try:
            tool_fn = TOOL_MAP[tool_name]
            result = tool_fn.invoke(tool_args)
            outputs.append({"tool": tool_name, "args": tool_args, "result": result})
            logger.info("Tool '%s' completed successfully", tool_name)
        except Exception as exc:
            logger.warning("Tool '%s' failed: %s", tool_name, exc)
            outputs.append({"tool": tool_name, "args": tool_args, "result": str(exc), "error": True})

    # Merge with any existing tool outputs (across iterations)
    existing = state.get("tool_outputs", [])
    return {"tool_outputs": existing + outputs}


# ─────────────────────────────────────────────────────────────────────────────
# Node 3: Evaluator
# ─────────────────────────────────────────────────────────────────────────────

@observe(name="evaluator")
def evaluator_node(state: AgentState) -> dict[str, Any]:
    """Assess whether retrieved information is sufficient to synthesise a briefing."""
    llm = _get_llm()

    tool_outputs_summary = json.dumps(state.get("tool_outputs", []), indent=2)[:3000]

    messages = [
        SystemMessage(content=EVALUATOR_SYSTEM),
        HumanMessage(
            content=(
                f"User query: {state['query']}\n\n"
                f"Tool outputs:\n{tool_outputs_summary}"
            )
        ),
    ]

    response = llm.invoke(messages)
    raw = response.content.strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
        evaluation = parsed.get("evaluation", "sufficient")
        notes = parsed.get("notes", "")
    except (json.JSONDecodeError, KeyError):
        evaluation = "sufficient"
        notes = "Could not parse evaluator output — proceeding to synthesis."

    # Force sufficient if we've hit the iteration cap
    if state.get("iterations", 0) >= MAX_ITERATIONS:
        evaluation = "sufficient"
        notes = f"Iteration cap ({MAX_ITERATIONS}) reached — proceeding regardless."

    logger.info("Evaluator: %s — %s", evaluation, notes)
    return {"evaluation": evaluation, "evaluation_notes": notes}


# ─────────────────────────────────────────────────────────────────────────────
# Node 4: Synthesiser
# ─────────────────────────────────────────────────────────────────────────────

@observe(name="synthesiser")
def synthesiser_node(state: AgentState) -> dict[str, Any]:
    """Write the structured intelligence briefing."""
    llm = _get_llm(temperature=0.2)

    tool_outputs_text = json.dumps(state.get("tool_outputs", []), indent=2)[:6000]

    messages = [
        SystemMessage(content=SYNTHESISER_SYSTEM),
        HumanMessage(
            content=(
                f"User query: {state['query']}\n\n"
                f"Retrieved information:\n{tool_outputs_text}"
            )
        ),
    ]

    response = llm.invoke(messages)
    briefing = response.content.strip()

    # Extract source URLs for structured output
    sources: list[dict[str, str]] = []
    for output in state.get("tool_outputs", []):
        raw_result = output.get("result", "")
        try:
            data = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
            # RSS / RAG results
            for item in data.get("results", data.get("articles", data.get("papers", []))):
                url = item.get("url", item.get("source_url", ""))
                if url:
                    sources.append(
                        {
                            "url": url,
                            "title": item.get("title", item.get("source_name", "")),
                            "date": item.get("date", item.get("publication_date", "")),
                            "source_name": item.get("source_name", ""),
                        }
                    )
        except Exception:
            pass

    # Build the reasoning trace footer
    plan_steps = state.get("plan", [])
    rationale = state.get("plan_rationale", "")
    eval_notes = state.get("evaluation_notes", "")
    iterations = state.get("iterations", 1)

    tool_summary = ", ".join(
        f"{o['tool']} → {len(o.get('result', '')) // 100 * 100}+ chars"
        for o in state.get("tool_outputs", [])
        if not o.get("error")
    )

    reasoning_trace = (
        f"\nAGENT REASONING TRACE\n"
        f"  Iterations: {iterations}\n"
        f"  Plan: {'; '.join(plan_steps)}\n"
        f"  Rationale: {rationale}\n"
        f"  Tool results: {tool_summary or 'none'}\n"
        f"  Evaluator: {eval_notes}"
    )

    final_response = briefing + reasoning_trace

    return {
        "final_response": final_response,
        "sources": sources,
        "messages": [AIMessage(content=final_response)],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 5: Memory Updater
# ─────────────────────────────────────────────────────────────────────────────

@observe(name="memory_updater")
def memory_updater_node(state: AgentState) -> dict[str, Any]:
    """Summarise this turn and persist to long-term memory."""
    llm = _get_llm()

    turn_text = (
        f"Query: {state['query']}\n\n"
        f"Response:\n{state.get('final_response', '')[:2000]}"
    )

    messages = [
        SystemMessage(content=MEMORY_SUMMARISER_SYSTEM),
        HumanMessage(content=turn_text),
    ]

    try:
        response = llm.invoke(messages)
        summary = response.content.strip()
        save_turn_summary(query=state["query"], summary=summary)
        logger.info("Memory updated for query: %s", state["query"][:60])
    except Exception as exc:
        logger.warning("Memory update failed: %s", exc)
        summary = ""

    return {}  # state is already complete; nothing to merge
