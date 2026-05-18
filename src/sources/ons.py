from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BETA_API_BASE = "https://api.beta.ons.gov.uk/v1"
TIMEOUT = 15.0


class ONSClient:
    """
    ONS client using the official Beta API.
    Uses dataset listing + version metadata only — avoids the broken
    observations endpoint which requires per-dataset dimension filters.
    """

    def get_datasets(self) -> list[dict[str, Any]]:
        """Fetch all datasets from ONS Beta API."""
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                resp = client.get(f"{BETA_API_BASE}/datasets", params={"limit": 100, "offset": 0})
                resp.raise_for_status()
                return resp.json().get("items", [])
        except Exception as exc:
            logger.warning("ONS datasets fetch failed: %s", exc)
            return []

    def search_crime_datasets(self) -> list[dict[str, Any]]:
        """Filter datasets for crime-related content."""
        datasets = self.get_datasets()

        keywords = {
            "crime", "policing", "justice", "violence",
            "theft", "burglary", "offence", "offense", "safety",
        }

        results = []
        for d in datasets:
            text = ((d.get("title") or "") + " " + (d.get("description") or "")).lower()
            if any(k in text for k in keywords):
                results.append({
                    "id": d.get("id"),
                    "title": d.get("title"),
                    "description": d.get("description"),
                })

        return results

    def get_latest_version_metadata(self, dataset_id: str) -> dict[str, Any] | None:
        """
        Fetch the latest version metadata for a dataset.
        Avoids the observations endpoint entirely — it requires per-dataset
        dimension filters that can't be called generically.
        """
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                # Get editions
                ed_resp = client.get(f"{BETA_API_BASE}/datasets/{dataset_id}/editions")
                if ed_resp.status_code != 200:
                    return None
                editions = ed_resp.json().get("items", [])
                if not editions:
                    return None
                edition_id = editions[0].get("edition")

                # Get latest version
                ver_resp = client.get(
                    f"{BETA_API_BASE}/datasets/{dataset_id}/editions/{edition_id}/versions"
                )
                if ver_resp.status_code != 200:
                    return None
                versions = ver_resp.json().get("items", [])
                if not versions:
                    return None

                latest = versions[-1]
                return {
                    "release_date": latest.get("release_date", ""),
                    "state": latest.get("state", ""),
                    "version": latest.get("version"),
                }

        except Exception as exc:
            logger.warning("ONS version fetch failed for %s: %s", dataset_id, exc)
            return None

    def get_crime_summary(self) -> str:
        """
        Build a summary from crime-related dataset metadata.
        """
        datasets = self.search_crime_datasets()

        if not datasets:
            return (
                "ONS crime statistics unavailable. "
                "See https://www.ons.gov.uk/peoplepopulationandcommunity/crimeandjustice"
            )

        lines = ["ONS Crime-related datasets (Beta API)", ""]

        for d in datasets[:8]:
            dataset_id = d.get("id")
            title = d.get("title", "Untitled")
            description = d.get("description", "")

            lines.append(f"• {title}")

            if description:
                lines.append(f"  {description[:200]}")

            if dataset_id:
                meta = self.get_latest_version_metadata(dataset_id)
                if meta:
                    lines.append(f"  Latest release: {meta.get('release_date', 'unknown')}")

            lines.append("")

        return "\n".join(lines)