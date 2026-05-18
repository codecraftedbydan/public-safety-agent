"""Police UK API client — street-level crime data for England and Wales."""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://data.police.uk/api"
TIMEOUT = 15.0

# Well-known city centres used for representative statistics
UK_LOCATIONS = [
    {"name": "London", "lat": 51.5074, "lng": -0.1278},
    {"name": "Manchester", "lat": 53.4808, "lng": -2.2426},
    {"name": "Birmingham", "lat": 52.4862, "lng": -1.8904},
    {"name": "Leeds", "lat": 53.8008, "lng": -1.5491},
]


class PoliceUKClient:
    """Wrapper around the data.police.uk REST API. No API key required."""

    # ------------------------------------------------------------------ #
    #  Core API methods                                                    #
    # ------------------------------------------------------------------ #

    def get_categories(self) -> list[dict[str, Any]]:
        """Return all available crime category codes and display names."""
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.get(f"{BASE_URL}/crime-categories")
            resp.raise_for_status()
            return resp.json()

    def get_street_crimes(
        self,
        lat: float,
        lng: float,
        category: str = "all-crime",
        date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return street-level crimes near a lat/lng point.

        ``date`` is YYYY-MM; defaults to the most recent available month.
        """
        params: dict[str, Any] = {"lat": lat, "lng": lng}
        if date:
            params["date"] = date

        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.get(
                f"{BASE_URL}/crimes-street/{category}",
                params=params,
            )
            resp.raise_for_status()
            return resp.json()

    def get_forces(self) -> list[dict[str, Any]]:
        """Return all police forces in England, Wales, and Northern Ireland."""
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.get(f"{BASE_URL}/forces")
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------ #
    #  Higher-level helpers                                               #
    # ------------------------------------------------------------------ #

    def get_crime_summary(
        self,
        category: str = "all-crime",
        location_name: str | None = None,
    ) -> dict[str, Any]:
        """Aggregate crime counts across key UK cities for a given category.

        Returns a dict with location-keyed counts and a prose summary.
        """
        locations = UK_LOCATIONS
        if location_name:
            locations = [
                loc for loc in UK_LOCATIONS
                if loc["name"].lower() == location_name.lower()
            ] or UK_LOCATIONS[:1]

        results: dict[str, int] = {}
        for i, loc in enumerate(locations):
            # Polite delay between requests to avoid 429 rate-limiting.
            # The Police UK API asks for reasonable usage; 1 s between calls
            # keeps the burst rate well within their limits.
            if i > 0:
                time.sleep(1.0)
            retries = 2
            for attempt in range(retries + 1):
                try:
                    crimes = self.get_street_crimes(loc["lat"], loc["lng"], category)
                    results[loc["name"]] = len(crimes)
                    break
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 429 and attempt < retries:
                        wait = 2 ** attempt * 2  # 2 s, 4 s
                        logger.warning(
                            "Police UK: 429 on %s, retrying in %ss (attempt %d/%d)",
                            loc["name"], wait, attempt + 1, retries,
                        )
                        time.sleep(wait)
                    else:
                        logger.warning(
                            "Police UK: failed to fetch %s for %s: %s",
                            category, loc["name"], exc,
                        )
                        break
                except Exception as exc:
                    logger.warning(
                        "Police UK: failed to fetch %s for %s: %s",
                        category, loc["name"], exc,
                    )
                    break

        prose = self.crimes_to_prose(results, category)
        return {"counts": results, "category": category, "prose": prose}

    @staticmethod
    def crimes_to_prose(counts: dict[str, int], category: str) -> str:
        """Convert a counts dict to a readable paragraph for chunking."""
        if not counts:
            return f"No crime data available for category '{category}'."
        lines = [
            f"Police UK crime statistics — category: {category}",
            "",
        ]
        for location, count in counts.items():
            lines.append(f"  {location}: {count} recorded incidents (most recent available month)")
        total = sum(counts.values())
        lines.append(f"\n  Total across sampled locations: {total} incidents.")
        return "\n".join(lines)
