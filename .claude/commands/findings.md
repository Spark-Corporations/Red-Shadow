List all vulnerability findings discovered during the current engagement.

Use the Bash tool to run: `python -m redclaw.claude_skin.hook_handler findings`

This reads the REAL state file from `~/.redclaw/state/pipeline_state.json` and displays:
- Total number of findings
- Each finding with severity, title, target, and phase

Present the findings in a clean table format with severity, title, target, and phase.
If no findings exist, suggest starting a scan first.
