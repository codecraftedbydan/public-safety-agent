#!/usr/bin/env python
"""Public Safety Intelligence Agent — CLI entrypoint."""
from __future__ import annotations

import logging
import sys
import time
import os

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

app = typer.Typer(add_completion=False, help="Public Safety Intelligence Agent")
console = Console()

_langfuse_handler = None
_langfuse_ready = False


def _configure_logging(log_level: str) -> None:
    numeric = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )


def _init_langfuse():
    global _langfuse_handler, _langfuse_ready

    from src.config import settings
    import logging

    if not settings.langfuse_enabled:
        return None

    try:
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
        os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
        os.environ.setdefault("LANGFUSE_BASE_URL", settings.langfuse_base_url.rstrip("/"))

        from langfuse.langchain import CallbackHandler

        _langfuse_handler = CallbackHandler()
        _langfuse_ready = True

        logging.getLogger(__name__).info("Langfuse initialized")
        return _langfuse_handler

    except Exception as exc:
        logging.getLogger(__name__).warning(f"Langfuse disabled: {exc}")
        _langfuse_ready = False
        return None


def _startup():
    _configure_logging("WARNING")

    from src.config import settings as s
    if hasattr(s, "openai_model"):
        object.__setattr__(s, "openai_model", os.getenv("OPENAI_MODEL", s.openai_model))

    _init_langfuse()

    time.sleep(5)


@app.command()
def chat(
    quality: bool = typer.Option(False, "--quality", "-q"),
    log_level: str = typer.Option("WARNING", "--log-level", "-l"),
) -> None:
    """Start interactive chat session."""
    _configure_logging(log_level)

    _startup()

    if quality:
        os.environ["OPENAI_MODEL"] = "gpt-4o"

    from src.agent.graph import agent_graph
    from src.memory.session import new_session_state

    callbacks = [_langfuse_handler] if _langfuse_handler else []
    config = {"callbacks": callbacks} if callbacks else {}

    console.print(
        Panel.fit(
            "[bold blue]Public Safety Intelligence Agent[/bold blue]\n"
            "[dim]Type exit to quit[/dim]",
            border_style="blue",
        )
    )

    if quality:
        console.print("[dim]Model: gpt-4o[/dim]")

    if _langfuse_ready:
        console.print("[dim]Langfuse enabled[/dim]")

    while True:
        try:
            query = Prompt.ask("\n[bold cyan]Query[/bold cyan]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye[/dim]")
            break

        query = query.strip()

        if query.lower() in {"exit", "quit", "q"}:
            break
        if not query:
            continue

        with console.status("[green]Thinking...[/green]"):
            try:
                state = new_session_state(query)
                result = agent_graph.invoke(state, config=config)

                response = result.get("final_response", "No response generated.")
                sources = result.get("sources", [])

                if _langfuse_handler:
                    try:
                        from langfuse import get_client
                        get_client().flush()
                    except Exception:
                        pass

            except Exception as exc:
                logging.getLogger(__name__).exception("Agent error")
                console.print(f"[red]Error:[/red] {exc}")
                continue

        console.print("\n")
        console.print(Markdown(response))

        if sources:
            console.print("\n[dim]Sources:[/dim]")
            for src in sources[:8]:
                title = src.get("title", "Unknown")
                url = src.get("url", "")
                console.print(f"  • {title}" + (f" — {url}" if url else ""))

        console.rule()


@app.command()
def ingest(
    verbose: bool = typer.Option(True, "--verbose/--quiet", "-v/-q"),
) -> None:
    """Ingest RAG corpus."""
    _configure_logging("INFO")

    from src.rag.ingestion import run_ingestion

    console.print("[bold]Starting ingestion...[/bold]")

    try:
        counts = run_ingestion(verbose=verbose)

        console.print(
            Panel.fit(
                f"RSS: {counts.get('rss_articles', 0)}\n"
                f"ONS: {counts.get('ons', 0)}\n"
                f"Police: {counts.get('police_uk', 0)}\n"
                f"NewsAPI: {counts.get('newsapi', 0)}\n"
                f"arXiv: {counts.get('arxiv_papers', 0)}\n"
                f"Duplicates: {counts.get('duplicates_removed', 0)}\n"
                f"Chunks: {counts.get('total_chunks', 0)}",
                title="Ingestion Complete",
                border_style="green",
            )
        )

    except Exception as exc:
        console.print(f"[red]Ingestion failed:[/red] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    app()