# Custom Slash Commands for Kimi CLI

This directory contains examples of custom slash commands that you can add to your Kimi CLI installation.

## Quick Start

1. **Create the commands directory:**
   ```bash
   # For user-global commands (available in all projects)
   mkdir -p ~/.kimi/commands
   
   # OR for project-local commands (only in this project)
   mkdir -p .kimi/commands
   ```

2. **Copy example commands:**
   ```bash
   # Copy to user-global
   cp hello.py ~/.kimi/commands/
   
   # OR copy to project-local
   cp hello.py .kimi/commands/
   ```

3. **Restart Kimi CLI** and type `/hello`

## How It Works

Custom commands are loaded from Python files in the following locations:

1. **Project-local** (higher priority): `{work_dir}/.kimi/commands/*.py`
2. **User-global**: `~/.kimi/commands/*.py` (or `~/.config/kimi/commands/` on Linux)

Each Python file can define commands using decorators:

### Soul-Level Commands (`@soul_command`)

These commands operate on the KimiSoul (the AI agent). They can:
- Access conversation context
- Send messages to the AI
- Trigger AI workflows

```python
@soul_command(aliases=["short"])
async def my_command(soul, args: str):
    """Description shown in /help"""
    # Your code here
    pass
```

### Shell-Level Commands (`@shell_command`)

These commands operate on the Shell (UI layer). They can:
- Print to console
- Interact with the UI
- Run without involving the AI

```python
@shell_command(aliases=["sh"])
def my_shell_command(shell, args: str):
    """Description shown in /help"""
    from kimi_cli.ui.shell.console import console
    console.print("Hello!")
```

## Available Imports

### In Soul-Level Commands

The `soul` parameter provides access to:
- `soul.context` - Conversation context and history
- `soul.agent` - The current agent
- `soul.runtime` - Runtime configuration and services
- `soul.run()` - Run a message through the AI

### In Shell-Level Commands

The `shell` parameter provides access to:
- `shell.soul` - The current KimiSoul (if available)
- Console output via `kimi_cli.ui.shell.console.console`

## Example Commands

### hello.py
Basic greeting command demonstrating both soul and shell level commands.

**Usage:**
- `/hello` - Say hello
- `/hello Alice` - Say hello to Alice
- `/hi` - Alias for hello (shell level)

### ai_helper.py
More advanced examples showing AI interaction.

**Usage:**
- `/explain_code print('hello')` - Ask AI to explain code
- `/summarize` - Ask AI to summarize the conversation
- `/project_info` - Show project statistics

## Creating Your Own Commands

1. Create a new `.py` file in the commands directory
2. Define functions with `@soul_command` or `@shell_command` decorator
3. The function name becomes the command name (`/function_name`)
4. The docstring becomes the help description
5. The `args` parameter contains any text after the command

### Decorator Options

```python
@soul_command(
    name="custom_name",  # Override command name
    aliases=["c", "cn"]   # Alternative names
)
async def my_func(soul, args: str):
    """This description appears in /help"""
    pass
```

### Helper Functions

The following are injected into your command file by the loader:
- `soul_command` / `soul_cmd` - Register soul-level commands
- `shell_command` / `shell_cmd` - Register shell-level commands

Do not import these - they are automatically available at runtime.

## Debugging

If your command isn't loading:

1. Check the logs for error messages
2. Ensure the file is in the correct directory
3. Make sure the file has a `.py` extension
4. Files starting with `_` are ignored (private modules)

## Security Note

Custom commands execute with the same permissions as Kimi CLI. Be careful when:
- Running code from untrusted sources
- Accessing sensitive files
- Making network requests

Only install custom commands from sources you trust.
