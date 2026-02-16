"""
RedClaw CLI shortcuts — additional entry points for convenience.

These are registered in pyproject.toml [project.scripts]:
  redclaw-doctor  →  quick health check
  redclaw-skin    →  launch Claude Code skin mode

These provide the same functionality as `redclaw doctor` and `redclaw skin`,
but as standalone commands for faster access.
"""

from __future__ import annotations

import sys


def doctor() -> None:
    """Entry point for `redclaw-doctor` command."""
    # Inject subcommand and delegate to main
    sys.argv = ["redclaw", "doctor"] + sys.argv[1:]
    from redclaw.cli.app import main
    main()


def skin() -> None:
    """Entry point for `redclaw-skin` command."""
    sys.argv = ["redclaw", "skin"] + sys.argv[1:]
    from redclaw.cli.app import main
    main()
