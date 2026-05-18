"""FBI Crime Data API client — DECOMMISSIONED.

The FBI SAPI public API (https://api.usa.gov/crime/fbi/sapi) has been
decommissioned. As of May 2026, all structured API endpoints return 404.
The base URL now serves the CDE frontend website only.

Confirmed dead endpoints (tested 2026-05-17):
  - /api/estimates/national/{year_from}/{year_to}                   -> 404
  - /api/summarized/national/{offense}/{year_from}/{year_to}        -> 404
  - /api/offenses/count/national/{offense}/{year_from}/{year_to}    -> 404

The replacement (cde.ucr.cjis.gov) does not expose a public REST API.
FBI UCR data is still available as annual CSV downloads from:
  https://cde.ucr.cjis.gov/LATEST/webapp/#/pages/downloads

Design decision: rather than maintain a client that silently fails with
404s on every query, this module is retired. US statistical context is
now provided via:
  - NewsAPI (live US crime news, cross-jurisdictional)
  - RAG corpus (ingested US-scoped RSS: DoJ, NPR)
  - arXiv (US academic research on crime and policing)

See README.md Data Sources section for full rationale.
"""