"""CLI command for accessing documentation."""

from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown

app = typer.Typer(help="Access ISV Lab Tools documentation")

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
    topic: str | None = typer.Argument(
        None,
        help="Documentation topic to display (use --list to see available topics)",
    ),
    list_topics: bool = typer.Option(False, "--list", "-l", help="List available documentation topics"),
    path_only: bool = typer.Option(False, "--path", "-p", help="Show file path instead of content"),
) -> None:
    """View documentation in the terminal.

    Examples:
        isvctl docs                    # Show docs index
        isvctl docs getting-started    # Show getting started guide
        isvctl docs configuration      # Show configuration guide
        isvctl docs --list             # List available topics
        isvctl docs isvctl --path      # Show path to isvctl docs
    """
    # Skip if a subcommand was invoked
    if ctx.invoked_subcommand is not None:
        return

    local_docs = _find_local_docs()

    if list_topics:
        typer.echo("Available documentation topics:\n")
        for name, filepath in TOPICS.items():
            typer.echo(f"  {name:20} {filepath}")
        typer.echo("\nUsage: isvctl docs <topic>")
        if local_docs:
            typer.echo(f"\nDocs location: {local_docs}")
        return

    if not local_docs:
        typer.echo("Documentation not found.")
        typer.echo("Run from the install directory or clone the repository.")
        raise typer.Exit(1)

    # Determine which file to show
    if topic:
        if topic not in TOPICS:
            typer.echo(f"Unknown topic: {topic}")
            typer.echo(f"Available: {', '.join(TOPICS.keys())}")
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

    # Render markdown in terminal
    content = doc_file.read_text()
    md = Markdown(content)
    console.print(md)
