"""CLI command for accessing documentation."""

import inspect
from collections import defaultdict
from pathlib import Path
from textwrap import dedent

import typer
from isvtest.core.discovery import discover_tests
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(help="Access ISV NCP Validation Suite documentation")

console = Console()


def _find_local_docs() -> Path | None:
    """Find local docs directory.

    Checks in order:
    1. ./docs/ (current working directory - installed via install.sh)
    2. Relative to this package (development mode)
    """
    # Check current working directory (install.sh extracts here)
    cwd_docs = Path.cwd() / "docs"
    if cwd_docs.is_dir() and (cwd_docs / "README.md").exists():
        return cwd_docs

    # Check relative to package (development mode)
    package_dir = Path(__file__).parent.parent.parent.parent.parent.parent
    dev_docs = package_dir / "docs"
    if dev_docs.is_dir() and (dev_docs / "README.md").exists():
        return dev_docs

    return None


# Topic mapping
TOPICS = {
    "getting-started": "getting-started.md",
    "configuration": "guides/configuration.md",
    "remote-deployment": "guides/remote-deployment.md",
    "workloads": "guides/workloads.md",
    "local-development": "guides/local-development.md",
    "contributing": "contributing.md",
    "isvctl": "packages/isvctl.md",
    "isvtest": "packages/isvtest.md",
    "isvreporter": "packages/isvreporter.md",
}


@app.callback(invoke_without_command=True)
def docs(
    ctx: typer.Context,
    topic: str | None = typer.Option(
        None,
        "--topic",
        "-t",
        help=f"Documentation topic: {', '.join(TOPICS)}",
    ),
    list_topics: bool = typer.Option(False, "--list", "-l", help="List available documentation topics"),
    path_only: bool = typer.Option(False, "--path", "-p", help="Show file path instead of content"),
) -> None:
    """View documentation in the terminal.

    Examples:
        isvctl docs                              # Show docs index
        isvctl docs -t getting-started           # Show getting started guide
        isvctl docs --list                       # List available topics
        isvctl docs tests                        # List all validation tests
        isvctl docs tests -m kubernetes          # Only kubernetes tests
    """
    if ctx.invoked_subcommand is not None:
        return

    if list_topics:
        typer.echo("Available documentation topics:\n")
        for name, filepath in TOPICS.items():
            typer.echo(f"  {name:20} {filepath}")
        typer.echo(f"\n  {'tests':20} (subcommand) List validation tests by category")
        typer.echo("\nUsage: isvctl docs -t <topic>  or  isvctl docs tests [OPTIONS]")
        local_docs = _find_local_docs()
        if local_docs:
            typer.echo(f"\nDocs location: {local_docs}")
        return

    local_docs = _find_local_docs()

    if not local_docs:
        typer.echo("Documentation not found.")
        typer.echo("Run from the install directory or clone the repository.")
        raise typer.Exit(1)

    if topic:
        if topic not in TOPICS:
            typer.echo(f"Unknown topic: {topic}")
            typer.echo(f"Available: {', '.join(TOPICS)}")
            raise typer.Exit(1)
        doc_file = local_docs / TOPICS[topic]
        if not doc_file.exists():
            typer.echo(f"Topic file not found: {doc_file}")
            raise typer.Exit(1)
    else:
        doc_file = local_docs / "README.md"

    if path_only:
        typer.echo(str(doc_file))
        return

    content = doc_file.read_text()
    md = Markdown(content)
    console.print(md)


@app.command()
def tests(
    marker: list[str] = typer.Option(
        None,
        "--marker",
        "-m",
        help="Filter by marker (repeatable, e.g. -m kubernetes -m gpu)",
    ),
    flat: bool = typer.Option(False, "--flat", help="Flat list without grouping by marker"),
    info: str | None = typer.Option(
        None,
        "--info",
        "-i",
        help="Show detailed info for a specific test (e.g. -i SshGpuStressCheck)",
    ),
) -> None:
    """List all available validation tests grouped by category.

    Examples:
        isvctl docs tests                          # All tests by category
        isvctl docs tests -m kubernetes            # Only kubernetes tests
        isvctl docs tests -m gpu -m ssh            # GPU and SSH tests
        isvctl docs tests --flat                   # Flat alphabetical list
        isvctl docs tests -i SshGpuStressCheck     # Detailed info for a test
    """
    import isvtest.validations as validations_pkg

    pkg_path = Path(validations_pkg.__file__).parent
    all_classes = list(discover_tests(pkg_path, "isvtest.validations"))

    if not all_classes:
        console.print("[yellow]No validation tests discovered.[/yellow]")
        raise typer.Exit(1)

    if info:
        _print_test_info(all_classes, info)
        return

    if flat:
        _print_flat(all_classes, marker)
    else:
        _print_grouped(all_classes, marker)


def _print_test_info(classes: list[type], name: str) -> None:
    """Print detailed info for a single test class."""
    # Case-insensitive lookup
    by_name = {cls.__name__.lower(): cls for cls in classes}
    cls = by_name.get(name.lower())

    if cls is None:
        console.print(f"[red]Test not found:[/red] {name}")
        close = [c.__name__ for c in classes if name.lower() in c.__name__.lower()]
        if close:
            console.print(f"[dim]Did you mean: {', '.join(close)}?[/dim]")
        raise typer.Exit(1)

    source_file = Path(inspect.getfile(cls))
    _, start_line = inspect.getsourcelines(cls)
    try:
        source_display = f"{source_file.relative_to(Path.cwd())}:{start_line}"
    except ValueError:
        source_display = f"{source_file}:{start_line}"

    console.print()
    console.print(
        Panel(
            f"[bold green]{cls.__name__}[/bold green]",
            subtitle=f"[dim]{cls.description}[/dim]" if cls.description else None,
        )
    )

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold cyan")
    table.add_column()
    table.add_row("Markers", ", ".join(cls.markers) if cls.markers else "(none)")
    table.add_row("Timeout", f"{cls.timeout}s")
    table.add_row("Source", source_display)
    console.print(table)

    docstring = inspect.getdoc(cls)
    if docstring:
        console.print()
        console.print(Panel(dedent(docstring), title="[bold]Documentation[/bold]", title_align="left"))
    else:
        console.print("\n[dim]No docstring available.[/dim]")

    console.print()


def _print_grouped(classes: list[type], marker_filter: list[str] | None) -> None:
    """Print tests grouped by marker category."""
    by_marker: dict[str, list[type]] = defaultdict(list)

    for cls in classes:
        markers = cls.markers if cls.markers else ["uncategorized"]
        for m in markers:
            by_marker[m].append(cls)

    if marker_filter:
        by_marker = {k: v for k, v in by_marker.items() if k in marker_filter}

    if not by_marker:
        console.print("[yellow]No tests found for the given markers.[/yellow]")
        raise typer.Exit(1)

    total = len({cls.__name__ for group in by_marker.values() for cls in group})
    console.print(f"\n[bold]Validation Tests[/bold] ({total} unique across {len(by_marker)} categories)\n")

    for marker in sorted(by_marker):
        table = Table(
            title=f"[bold cyan]{marker}[/bold cyan] ({len(by_marker[marker])})",
            title_justify="left",
            show_header=True,
            header_style="bold",
            padding=(0, 1),
            show_lines=False,
        )
        table.add_column("Test", style="green", no_wrap=True)
        table.add_column("Description")
        table.add_column("Markers", style="dim")

        for cls in sorted(by_marker[marker], key=lambda c: c.__name__):
            table.add_row(
                cls.__name__,
                cls.description or "-",
                ", ".join(cls.markers) if cls.markers else "-",
            )

        console.print(table)
        console.print()


def _print_flat(classes: list[type], marker_filter: list[str] | None) -> None:
    """Print a flat alphabetical list of tests."""
    if marker_filter:
        classes = [cls for cls in classes if any(m in (cls.markers or []) for m in marker_filter)]

    if not classes:
        console.print("[yellow]No tests found for the given markers.[/yellow]")
        raise typer.Exit(1)

    table = Table(
        title=f"[bold]All Validation Tests[/bold] ({len(classes)})",
        title_justify="left",
        show_header=True,
        header_style="bold",
        padding=(0, 1),
    )
    table.add_column("Test", style="green", no_wrap=True)
    table.add_column("Description")
    table.add_column("Markers", style="dim")

    for cls in sorted(classes, key=lambda c: c.__name__):
        table.add_row(
            cls.__name__,
            cls.description or "-",
            ", ".join(cls.markers) if cls.markers else "-",
        )

    console.print()
    console.print(table)
    console.print()
