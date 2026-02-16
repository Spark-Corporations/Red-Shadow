List all vulnerability findings discovered during the current engagement.

Use the Bash tool to check if a state file exists:
```bash
if [ -f ~/.redclaw/state/pipeline_state.json ]; then
    python3 -c "
import json
state = json.load(open('$HOME/.redclaw/state/pipeline_state.json'))
findings = state.get('global_findings', [])
if not findings:
    print('No findings recorded yet.')
else:
    print(f'Total findings: {len(findings)}')
    print()
    for i, f in enumerate(findings, 1):
        sev = f.get('severity', 'info').upper()
        title = f.get('title', 'Untitled')
        target = f.get('target', 'N/A')
        print(f'{i}. [{sev}] {title} — {target}')
"
else
    echo "No active engagement state found. Start a scan first."
fi
```

Present the findings in a clean table format with severity, title, target, and phase.
