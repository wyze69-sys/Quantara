"""Command-line entry point.

``python -m quantara --descriptor <yaml> --data-root <dir> [--dry-run]``:
orchestrates the full slice pipeline; ``--dry-run`` performs descriptor,
rights-record, and existing-commit verification without network or mutation.
"""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the pipeline (implemented by the pipeline task)."""
    parser = argparse.ArgumentParser(prog="quantara")
    parser.add_argument("--descriptor", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    from quantara.pipeline import run_pipeline

    return run_pipeline(
        descriptor_path=args.descriptor,
        data_root=args.data_root,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
