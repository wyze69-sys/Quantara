"""Allow execution as ``python -m quantara``."""

from quantara.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
