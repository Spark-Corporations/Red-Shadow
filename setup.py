"""
setup.py — Post-install bootstrap for RedClaw.

When the user runs `pip install redclaw`, this script:
  1. Installs all Python dependencies (handled by pip from pyproject.toml)
  2. Triggers the first-run bootstrap automatically:
     - Creates ~/.redclaw/ directory structure
     - Detects and installs missing pentesting tools
     - Installs Claude Code CLI (+ Node.js if needed)
     - Writes .initialized marker

This gives the same experience as `npm install -g @anthropic-ai/claude-code`:
  pip install redclaw  →  `redclaw` command ready, all tools installed.
"""

import subprocess
import sys

from setuptools import setup
from setuptools.command.install import install
from setuptools.command.develop import develop


class PostInstallBootstrap:
    """Mixin to run bootstrap after pip install."""

    def _run_bootstrap(self):
        """Run RedClaw bootstrap after install completes."""
        print("\n" + "=" * 60)
        print("🔴 RedClaw — Running post-install setup...")
        print("=" * 60 + "\n")

        try:
            # Run bootstrap as a subprocess to avoid import issues
            # during the install process itself
            subprocess.run(
                [sys.executable, "-c", """
import sys
sys.path.insert(0, 'src')
try:
    from redclaw.core.bootstrap import ensure_ready
    result = ensure_ready(force=True)
    if result.get('ready'):
        print()
        print("=" * 60)
        print("✅ RedClaw is ready!")
        print("   Type 'redclaw' to start.")
        print("=" * 60)
    else:
        print("⚠️  Partial setup — run 'redclaw' to complete.")
except Exception as e:
    print(f"⚠️  Bootstrap skipped: {e}")
    print("   Bootstrap will run on first 'redclaw' launch.")
"""],
                check=False,
                timeout=600,
            )
        except Exception as e:
            print(f"⚠️  Post-install bootstrap skipped: {e}")
            print("   Will run automatically on first launch.\n")


class InstallWithBootstrap(PostInstallBootstrap, install):
    """pip install redclaw → runs bootstrap after install."""

    def run(self):
        install.run(self)
        self._run_bootstrap()


class DevelopWithBootstrap(PostInstallBootstrap, develop):
    """pip install -e . → runs bootstrap after develop install."""

    def run(self):
        develop.run(self)
        self._run_bootstrap()


setup(
    cmdclass={
        "install": InstallWithBootstrap,
        "develop": DevelopWithBootstrap,
    },
)
