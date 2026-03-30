from rich.console import Console
from rich.table import Table

console = Console()
err_console = Console(stderr=True)


def print_spec_list(stage: str, files: list[str]) -> None:
    if not files:
        console.print(f"[dim]No specs in {stage}.[/dim]")
        return
    table = Table(title=stage, show_header=False, box=None, padding=(0, 1))
    table.add_column("file", style="cyan")
    for f in files:
        table.add_row(f)
    console.print(table)


def print_success(message: str) -> None:
    console.print(f"[green]{message}[/green]")


def print_error(message: str) -> None:
    err_console.print(f"[red]{message}[/red]")
