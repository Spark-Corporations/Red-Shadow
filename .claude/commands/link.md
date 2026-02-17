View or update the ngrok LLM backend URL used by RedClaw.

Use the Bash tool to run: `python -m redclaw.claude_skin.hook_handler link $ARGUMENTS`

This will:
- Without arguments: Show current active/saved/env URLs and **test real connectivity**
- With a URL argument: Save the new URL to `~/.redclaw/link.txt`, update the environment, and test connectivity

The handler performs an actual HTTP request to verify the LLM endpoint is reachable.
Report the results to the user clearly.
