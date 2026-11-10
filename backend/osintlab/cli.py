"""Command line interface.

The CLI is the reference implementation of the workflow: create a case, collect
against a target, inspect the graph, export a cited report. The web UI calls the
same service layer, so anything the UI can do the CLI can do.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .collectors.base import all_collectors, collectors_for
from .config import settings
from .db import init_db, session
from .graph import build_graph, to_dot
from .models import Case
from .report import render_report
from .service import CollectorService, infer_entity_type

app = typer.Typer(
    help="Educational OSINT workbench with full provenance tracking.",
    no_args_is_help=True,
    add_completion=False,
)
case_app = typer.Typer(help="Create and inspect cases.", no_args_is_help=True)
app.add_typer(case_app, name="case")

console = Console()


# -- setup ------------------------------------------------------------------


@app.command()
def init() -> None:
    """Create the database and data directories."""
    init_db()
    console.print(f"[green]initialised[/green] database at {settings.resolved_database_url}")
    console.print(f"evidence store: {settings.evidence_dir}")


@app.command()
def sources() -> None:
    """List available collectors, their inputs and their legal basis."""
    init_db()
    table = Table(title="Available collectors", show_lines=True)
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("accepts", style="magenta")
    table.add_column("source", style="white")
    table.add_column("legal basis", style="dim")

    for collector in all_collectors().values():
        table.add_row(
            collector.id,
            ", ".join(sorted(collector.accepts)),
            collector.label,
            collector.legal_basis,
        )
    console.print(table)


# -- cases ------------------------------------------------------------------


@case_app.command("create")
def case_create(
    title: str = typer.Option(..., "--title", "-t"),
    scope: str = typer.Option(
        "", "--scope", "-s", help="Why this target is in scope. Recorded in the audit log."
    ),
) -> None:
    """Create a new case."""
    init_db()
    with session() as db:
        case = Case(title=title, scope_note=scope)
        db.add(case)
        db.flush()
        CollectorService(db).audit(case.id, "case_created", title, scope)
        console.print(f"[green]created[/green] case #{case.id}: {case.title}")


@case_app.command("list")
def case_list() -> None:
    """List cases."""
    init_db()
    with session() as db:
        cases = db.query(Case).order_by(Case.id).all()
        if not cases:
            console.print("[dim]no cases yet[/dim]")
            return
        table = Table(title="Cases")
        table.add_column("#", style="cyan")
        table.add_column("title")
        table.add_column("entities", justify="right")
        table.add_column("created", style="dim")
        for case in cases:
            table.add_row(
                str(case.id),
                case.title,
                str(len(case.entities)),
                case.created_at.strftime("%Y-%m-%d %H:%M"),
            )
        console.print(table)


@case_app.command("show")
def case_show(case_id: int) -> None:
    """Show the entities and attributes of a case."""
    init_db()
    with session() as db:
        case = db.get(Case, case_id)
        if case is None:
            raise typer.BadParameter(f"no case #{case_id}")
        console.print(f"[bold]#{case.id} {case.title}[/bold]")
        if case.scope_note:
            console.print(f"[dim]scope: {case.scope_note}[/dim]")

        for entity in case.entities:
            table = Table(title=f"{entity.type}: {entity.display_name or entity.value}")
            table.add_column("attribute", style="cyan")
            table.add_column("value")
            table.add_column("source", style="dim")
            table.add_column("retrieved", style="dim")
            for attr in sorted(entity.attributes, key=lambda a: a.key):
                prov = attr.provenance
                table.add_row(
                    attr.key,
                    attr.value,
                    prov.source if prov else "-",
                    prov.retrieved_at.strftime("%Y-%m-%d %H:%M") if prov else "-",
                )
            console.print(table)


# -- collection -------------------------------------------------------------


@app.command()
def collect(
    target: str = typer.Argument(..., help="Domain, IP, URL or organisation name."),
    case_id: int = typer.Option(..., "--case", "-c"),
    collectors: str = typer.Option(
        "", "--collectors", help="Comma-separated collector ids. Default: all applicable."
    ),
    depth: int = typer.Option(
        0, "--depth", help="How many hops to expand. 0 collects only the target."
    ),
    max_entities: int = typer.Option(15, "--max-entities"),
) -> None:
    """Collect against a target and store the results in a case."""
    init_db()
    with session() as db:
        case = db.get(Case, case_id)
        if case is None:
            raise typer.BadParameter(f"no case #{case_id}")

        wanted = [item.strip() for item in collectors.split(",") if item.strip()] or None
        service = CollectorService(db)

        entity_type = infer_entity_type(target)
        applicable = collectors_for(entity_type)
        if not applicable:
            console.print(f"[yellow]no collectors accept {entity_type}[/yellow]")
            return

        console.print(
            f"[bold]collecting[/bold] {entity_type}:{target} "
            f"with {len(applicable)} collector(s), depth={depth}"
        )
        summary = service.run(
            case, target, collector_ids=wanted, depth=depth, max_entities=max_entities
        )

        table = Table(title="Collection summary")
        table.add_column("collector", style="cyan")
        table.add_column("status")
        table.add_column("facts", justify="right")
        table.add_column("links", justify="right")
        table.add_column("notes", style="dim")

        for run in summary.runs:
            status = (
                f"[green]{run.status}[/green]"
                if run.status == "ok"
                else f"[red]{run.status}[/red]"
                if run.status == "error"
                else run.status
            )
            notes = run.error or "; ".join(run.notes)
            table.add_row(
                run.collector_id,
                status,
                str(run.facts),
                str(run.links),
                notes[:80],
            )
        console.print(table)
        console.print(
            f"[green]{summary.ok} ok[/green], "
            f"[red]{summary.failed} failed[/red] — "
            f"run `osintlab case show {case_id}` to inspect"
        )


@app.command()
def graph(
    case_id: int = typer.Option(..., "--case", "-c"),
    fmt: str = typer.Option("dot", "--format", help="dot or json"),
    out: Path | None = typer.Option(None, "--out", "-o"),
) -> None:
    """Export the case graph as Graphviz DOT or JSON."""
    init_db()
    with session() as db:
        case = db.get(Case, case_id)
        if case is None:
            raise typer.BadParameter(f"no case #{case_id}")
        data = build_graph(db, case_id)

        if fmt == "json":
            payload = json.dumps(data, indent=2)
        elif fmt == "dot":
            payload = to_dot(data)
        else:
            raise typer.BadParameter("format must be 'dot' or 'json'")

        if out:
            out.write_text(payload)
            console.print(f"[green]wrote[/green] {out}")
        else:
            console.print(payload)


@app.command()
def report(
    case_id: int = typer.Option(..., "--case", "-c"),
    out: Path | None = typer.Option(None, "--out", "-o"),
) -> None:
    """Render a cited Markdown report for a case."""
    init_db()
    with session() as db:
        case = db.get(Case, case_id)
        if case is None:
            raise typer.BadParameter(f"no case #{case_id}")
        markdown = render_report(db, case)
        if out:
            out.write_text(markdown)
            console.print(f"[green]wrote[/green] {out}")
        else:
            console.print(markdown)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(False, "--reload"),
) -> None:
    """Run the HTTP API (and the built web UI, if present)."""
    import uvicorn

    init_db()
    console.print(f"API docs: http://{host}:{port}/docs")
    uvicorn.run("osintlab.api.app:app", host=host, port=port, reload=reload)


if __name__ == "__main__":  # pragma: no cover
    app()
