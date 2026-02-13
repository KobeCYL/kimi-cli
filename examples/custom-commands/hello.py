"""Example custom slash command for Kimi CLI.

This is a simple example showing how to create a custom /hello command.

To use this command:
1. Copy this file to ~/.kimi/commands/hello.py
2. Or copy to your project: .kimi/commands/hello.py
3. Restart Kimi CLI
4. Type /hello in the prompt

Available decorators:
- @soul_command: For commands that operate on the KimiSoul (AI agent)
- @shell_command: For commands that operate on the Shell (UI layer)
- @soul_cmd / @shell_cmd: Shorthand aliases
"""

# soul_command and shell_command are injected by the loader
# Do not import them - they will be available at runtime


@soul_command
async def hello(soul, args: str):
    """Say hello to the user - a simple greeting command"""
    from kimi_cli.soul import wire_send
    from kimi_cli.wire.types import TextPart
    
    name = args.strip() or "friend"
    wire_send(TextPart(text=f"👋 Hello, {name}! Welcome to Kimi CLI with custom commands!"))


@shell_command(aliases=["hi"])
def hello_shell(shell, args: str):
    """Shell-level hello command - demonstrates UI interaction"""
    from kimi_cli.ui.shell.console import console
    
    name = args.strip() or "friend"
    console.print(f"[green]👋 Hello from shell, {name}![/green]")
    console.print("[grey50]This command runs at the UI shell level.[/grey50]")
