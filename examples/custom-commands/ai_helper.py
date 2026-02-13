"""Advanced example: AI-powered custom command.

This example shows how to create a custom command that interacts with the AI,
sending custom prompts or triggering specific workflows.
"""

from kosong.message import Message


@soul_command(aliases=["explain"])
async def explain_code(soul, args: str):
    """Explain the provided code in detail"""
    from kimi_cli.soul import wire_send
    from kimi_cli.wire.types import TextPart
    
    code = args.strip()
    if not code:
        wire_send(TextPart(text="Please provide some code after /explain_code, e.g., `/explain_code print('hello')`"))
        return
    
    prompt = f"""Please explain the following code in detail:

```
{code}
```

Explain:
1. What does this code do?
2. How does it work step by step?
3. Are there any potential issues or improvements?"""

    # Send the prompt to the AI
    await soul._turn(Message(role="user", content=prompt))


@soul_command
async def summarize(soul, args: str):
    """Summarize the current conversation context"""
    from kimi_cli.soul import wire_send
    from kimi_cli.wire.types import TextPart
    
    # Get context info
    ctx = soul.context
    n_messages = len(ctx.history)
    
    prompt = f"""Please summarize our conversation so far. 

Context info:
- Total messages: {n_messages}
- Checkpoints: {ctx.n_checkpoints}

Provide a brief summary of what we've discussed and what tasks have been completed."""

    await soul._turn(Message(role="user", content=prompt))


@shell_command
async def project_info(shell, args: str):
    """Show project information and statistics"""
    import os
    from pathlib import Path
    from kimi_cli.ui.shell.console import console
    
    work_dir = Path.cwd()
    
    # Count files by extension
    ext_counts = {}
    total_files = 0
    
    for root, dirs, files in os.walk(work_dir):
        # Skip common directories to ignore
        dirs[:] = [d for d in dirs if d not in {
            '.git', 'node_modules', '__pycache__', '.venv', 'venv',
            '.tox', '.pytest_cache', '.mypy_cache', '.ruff_cache'
        }]
        
        for file in files:
            total_files += 1
            ext = Path(file).suffix.lower() or '(no extension)'
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
    
    # Display results
    console.print(f"[bold]Project Info: {work_dir.name}[/bold]")
    console.print(f"Total files: {total_files}")
    
    if ext_counts:
        console.print("\n[bold]File types:[/bold]")
        for ext, count in sorted(ext_counts.items(), key=lambda x: -x[1])[:10]:
            console.print(f"  {ext}: {count}")
