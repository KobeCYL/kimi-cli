# Custom Slash Commands

This fork of Kimi CLI adds support for custom `/xxx` slash commands via external Python plugins.

## Features

- ✅ Define custom slash commands in Python files
- ✅ Support for both Soul-level (AI) and Shell-level (UI) commands
- ✅ Project-local or user-global command directories
- ✅ Command aliases support
- ✅ Auto-discovery and loading on startup

## Installation

This is already integrated into the fork. To use custom commands:

1. Create the commands directory:
   ```bash
   # User-global (applies to all projects)
   mkdir -p ~/.kimi/commands
   
   # OR project-local (applies to specific project only)
   mkdir -p .kimi/commands
   ```

2. Add Python files with your custom commands

3. Restart Kimi CLI - commands are auto-loaded

## Quick Example

Create `~/.kimi/commands/greet.py`:

```python
@soul_command(aliases=["hi"])
async def greet(soul, args: str):
    """Send a greeting message"""
    from kimi_cli.soul import wire_send
    from kimi_cli.wire.types import TextPart
    
    name = args.strip() or "friend"
    wire_send(TextPart(text=f"Hello, {name}!"))
```

Then in Kimi CLI:
```
/greet Alice
# Output: Hello, Alice!
```

## Documentation

- [Full Documentation](examples/custom-commands/README.md)
- [Example Commands](examples/custom-commands/)

## Architecture Changes

### New Files
- `src/kimi_cli/soul/slash_ext.py` - Extension loader and registry

### Modified Files
- `src/kimi_cli/soul/slash.py` - Added `find_command()` and `list_commands()`
- `src/kimi_cli/soul/kimisoul.py` - Integrated custom command loading
- `src/kimi_cli/ui/shell/slash.py` - Added custom command support
- `src/kimi_cli/ui/shell/__init__.py` - Load custom commands on startup

## License

Same as upstream: Apache License 2.0
