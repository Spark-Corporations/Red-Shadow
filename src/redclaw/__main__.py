"""Entry point for `python -m redclaw`."""

import sys


def main():
    from redclaw.cli.app import main as cli_main
    cli_main()


if __name__ == "__main__":
    sys.exit(main())
