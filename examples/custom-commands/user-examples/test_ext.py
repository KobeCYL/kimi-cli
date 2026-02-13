"""Test command to verify custom slash extension is working"""

@shell_command(aliases=["ext_test"])
def test_ext(shell, args: str):
    """🧪 Test custom extension system - shows a greeting message"""
    from kimi_cli.ui.shell.console import console
    
    console.print("[bold green]✅ Custom slash extension system is working![/bold green]")
    console.print(f"[cyan]This is a custom command running from:[/cyan]")
    console.print(f"  ~/.kimi/commands/test_ext.py")
    
    if args:
        console.print(f"\n[yellow]Arguments received:[/yellow] {args}")
    
    # Try to get soul info if available
    if hasattr(shell, 'soul') and shell.soul:
        console.print(f"\n[dim]Soul available: {shell.soul.name}[/dim]")
