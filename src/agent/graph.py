"""LangGraph StateGraph — wires all nodes together with conditional edges."""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from src.agent.nodes import (
    evaluator_node,
    memory_updater_node,
    planner_node,
    synthesiser_node,
    tool_router_node,
)
from src.agent.state import AgentState


def _route_evaluator(state: AgentState) -> str:
    """Conditional edge: route to synthesiser or back to planner."""
    if state.get("evaluation") == "insufficient":
        return "planner"
    return "synthesiser"


def build_graph() -> StateGraph:
    """Construct and compile the agent graph.

    Control flow:
        START → planner → tool_router → evaluator
                                              ├── [sufficient]   → synthesiser → memory_updater → END
                                              └── [insufficient] → planner  (max 3 iterations)
    """
    graph = StateGraph(AgentState)

    # Register nodes
    graph.add_node("planner", planner_node)
    graph.add_node("tool_router", tool_router_node)
    graph.add_node("evaluator", evaluator_node)
    graph.add_node("synthesiser", synthesiser_node)
    graph.add_node("memory_updater", memory_updater_node)

    # Fixed edges
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "tool_router")
    graph.add_edge("tool_router", "evaluator")
    graph.add_edge("synthesiser", "memory_updater")
    graph.add_edge("memory_updater", END)

    # Conditional edge: evaluator decides whether to re-plan or synthesise
    graph.add_conditional_edges(
        "evaluator",
        _route_evaluator,
        {
            "planner": "planner",
            "synthesiser": "synthesiser",
        },
    )

    return graph.compile()


# Module-level compiled graph — import this elsewhere
agent_graph = build_graph()
