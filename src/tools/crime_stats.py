"""Tool 3: Crime statistics — structured data from Police UK API and ONS."""
from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

from src.sources.ons import ONSClient
from src.sources.police_uk import PoliceUKClient

logger = logging.getLogger(__name__)

_uk_client = PoliceUKClient()
_ons_client = ONSClient()

# NOTE: FBIClient has been removed. The FBI SAPI public API
# (api.usa.gov/crime/fbi/sapi) was decommissioned in 2025/2026 —
# all endpoints return 404. US statistical context is now served
# via the RAG corpus (DoJ/NPR RSS) and NewsAPI live fetch.
# See src/sources/fbi.py and README.md for full rationale.


@tool
def crime_statistics_tool(
    jurisdiction: str,
    category: str = "all-crime",
    location: str = "",
) -> str:
    """Retrieve structured crime statistics from official government APIs.

    Use this tool when the query asks for specific crime counts, trends,
    comparisons, or official statistics. Returns data directly from
    Police UK and ONS (for England and Wales).

    For US statistics, use rag_retrieval_tool or live_fetch_tool instead —
    the FBI UCR public API has been decommissioned and is no longer available.

    This tool returns structured statistical data, not news articles.
    Use rag_retrieval_tool or live_fetch_tool for qualitative context
    or for US-jurisdiction queries.

    Args:
        jurisdiction: "UK" for Police UK / ONS data. "US" queries will
                      be redirected to a helpful message explaining the
                      data source change.
        category:     Crime category. UK examples: "all-crime",
                      "violent-crime", "burglary", "drugs".
        location:     Optional. UK: city name (London, Manchester,
                      Birmingham, Leeds).

    Returns:
        JSON string with statistics and a prose summary.
    """
    jur = jurisdiction.upper()

    if jur == "UK":
        parts: list[str] = []

        # Police UK — street-level counts for specific category/location
        try:
            result = _uk_client.get_crime_summary(
                category=category,
                location_name=location or None,
            )
            if result.get("prose"):
                parts.append(result["prose"])
        except Exception as exc:
            logger.warning("crime_statistics_tool Police UK error: %s", exc)

        # ONS CSEW — national survey-based headline figures
        if not location:  # ONS data is national only
            try:
                ons_prose = _ons_client.get_crime_summary()
                if ons_prose:
                    parts.append(ons_prose)
            except Exception as exc:
                logger.warning("crime_statistics_tool ONS error: %s", exc)

        if not parts:
            return json.dumps({"error": "UK crime data unavailable", "jurisdiction": "UK"})

        return json.dumps(
            {
                "jurisdiction": "UK",
                "sources": ["Police UK API", "ONS Crime Survey (CSEW)"],
                "category": category,
                "location": location or "national",
                "prose": "\n\n".join(parts),
            }
        )

    elif jur == "US":
        # The FBI SAPI public API was decommissioned — all endpoints return 404.
        # Direct the agent to use rag_retrieval_tool or live_fetch_tool for US queries.
        return json.dumps(
            {
                "jurisdiction": "US",
                "message": (
                    "US structured crime statistics are not available via API — "
                    "the FBI SAPI (api.usa.gov/crime/fbi/sapi) was decommissioned "
                    "in 2025/2026. Use rag_retrieval_tool for US crime context from "
                    "ingested DoJ/NPR sources, or live_fetch_tool for recent US "
                    "crime news. Raw FBI UCR data is available as CSV downloads at "
                    "https://cde.ucr.cjis.gov/LATEST/webapp/#/pages/downloads"
                ),
                "suggested_tools": ["rag_retrieval_tool", "live_fetch_tool"],
            }
        )

    else:
        return json.dumps(
            {"error": f"Unknown jurisdiction '{jurisdiction}'. Use 'UK' or 'US'."}
        )