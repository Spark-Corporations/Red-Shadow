View or update the ngrok LLM backend URL used by RedClaw's reverse proxy.

## Without arguments
Show the current REDCLAW_LLM_URL from the environment and the saved URL from `~/.redclaw/link.txt`.

Use the Bash tool to run:
```bash
echo "Active URL: ${REDCLAW_LLM_URL:-not set}"
if [ -f ~/.redclaw/link.txt ]; then echo "Saved URL: $(cat ~/.redclaw/link.txt)"; else echo "Saved URL: none"; fi
```

## With a URL argument: /link $ARGUMENTS
Update the LLM backend URL. Use the Bash tool to run:
```bash
mkdir -p ~/.redclaw
echo "$ARGUMENTS" > ~/.redclaw/link.txt
export REDCLAW_LLM_URL="$ARGUMENTS"
echo "✅ LLM backend URL updated to: $ARGUMENTS"
echo "   Saved to ~/.redclaw/link.txt"
```

Tell the user the URL has been updated and will take effect on next proxy restart.
