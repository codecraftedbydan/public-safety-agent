from src.tools.rag_retrieval import rag_retrieval_tool
from src.tools.live_fetch import live_fetch_tool
from src.tools.crime_stats import crime_statistics_tool
from src.tools.arxiv_search import research_search_tool

ALL_TOOLS = [
    rag_retrieval_tool,
    live_fetch_tool,
    crime_statistics_tool,
    research_search_tool,
]

TOOL_MAP = {t.name: t for t in ALL_TOOLS}
