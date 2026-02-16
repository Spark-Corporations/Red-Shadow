Show GuardianRails safety statistics.

GuardianRails is RedClaw's safety system that prevents dangerous commands.

Use the Bash tool to check GuardianRails status:
```bash
if [ -f ~/.redclaw/logs/tool_audit.jsonl ]; then
    total=$(wc -l < ~/.redclaw/logs/tool_audit.jsonl)
    echo "GuardianRails Statistics"
    echo "========================"
    echo "Total commands audited: $total"
    echo "Audit log: ~/.redclaw/logs/tool_audit.jsonl"
    echo ""
    echo "Last 5 entries:"
    tail -5 ~/.redclaw/logs/tool_audit.jsonl | python3 -c "
import sys, json
for line in sys.stdin:
    entry = json.loads(line.strip())
    print(f\"  {entry.get('timestamp','')} | {entry.get('tool','')} | {entry.get('input_preview','')[:60]}\")
"
else
    echo "No audit log found. GuardianRails is active but no commands have been processed yet."
fi
```

Display the blocked/allowed ratio and recent command history.
