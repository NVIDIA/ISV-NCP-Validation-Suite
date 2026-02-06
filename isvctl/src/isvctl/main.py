"""Main CLI entry point for isvctl."""

from importlib.metadata import version
from typing import Annotated

import typer
from isvreporter.main import app as report_app

from isvctl.cli import clean, deploy, docs, test

app = typer.Typer(
    name="isvctl",
    help="ISV Lab controller for cluster lifecycle orchestration",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        typer.echo(f"isvctl {version('isvctl')}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", "-V", help="Show version and exit.", callback=_version_callback, is_eager=True),
    ] = False,
) -> None:
    """ISV Lab controller for cluster lifecycle orchestration."""


# Register subcommands
app.add_typer(clean.app, name="clean")
app.add_typer(deploy.app, name="deploy")
app.add_typer(docs.app, name="docs")
app.add_typer(test.app, name="test")
app.add_typer(report_app, name="report")


if __name__ == "__main__":
    app()
