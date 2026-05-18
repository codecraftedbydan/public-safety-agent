#!/usr/bin/env python
"""Standalone ingestion script — usable without the full CLI."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure repo root is on the path when run as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
console = Console()


def main() -> None:
    from src.rag.ingestion import run_ingestion

    console.print("[bold]Fetching data and building vector store…[/bold]")
    console.print("[dim]This may take 1–3 minutes on a cold start.[/dim]\n")

    try:
        counts = run_ingestion(verbose=True)
    except Exception as exc:
        console.print(f"[bold red]Ingestion failed:[/bold red] {exc}")
        sys.exit(1)

    console.print(
        Panel.fit(
            f"[green]Done![/green]\n\n"
            f"  RSS articles  : {counts.get('rss_articles', 0)}\n"
            f"  Police UK docs: {counts.get('police_uk', 0)}\n"
            f"  arXiv papers  : {counts.get('arxiv_papers', 0)}\n"
            f"  Total chunks  : {counts.get('total_chunks', 0)}",
            title="Ingestion Summary",
            border_style="green",
        )
    )


if __name__ == "__main__":
    main()
