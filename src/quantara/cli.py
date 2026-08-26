"""Command-line entry point.

``python -m quantara --descriptor <yaml> --data-root <dir> [--dry-run]``:
the descriptor's ``schema`` field selects the pipeline (spec design §3.8) —
``quantara.dataset-descriptor/v1`` runs the slice 001 acquisition pipeline,
``quantara.derived-dataset-descriptor/v1`` runs the derivation pipeline,
``quantara.research-descriptor/v1`` runs the research-table pipeline,
``quantara.validation-descriptor/v1`` runs the validation-folds pipeline, and
anything else is rejected with exit 3 ``invalid_descriptor``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE_SCHEMA = "quantara.dataset-descriptor/v1"
DERIVED_SCHEMA = "quantara.derived-dataset-descriptor/v1"
RESEARCH_SCHEMA = "quantara.research-descriptor/v1"
VALIDATION_SCHEMA = "quantara.validation-descriptor/v1"


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch on the descriptor's schema field."""
    parser = argparse.ArgumentParser(prog="quantara")
    parser.add_argument("--descriptor", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    schema = None
    try:
        import yaml

        document = yaml.safe_load(Path(args.descriptor).read_text(encoding="utf-8"))
        if isinstance(document, dict):
            schema = document.get("schema")
    except (OSError, yaml.YAMLError):
        schema = None

    if schema == BASE_SCHEMA:
        from quantara.pipeline import run_pipeline

        return run_pipeline(
            descriptor_path=args.descriptor,
            data_root=args.data_root,
            dry_run=args.dry_run,
        )
    if schema == DERIVED_SCHEMA:
        from quantara.derive_pipeline import run_derivation_pipeline

        return run_derivation_pipeline(
            descriptor_path=args.descriptor,
            data_root=args.data_root,
            dry_run=args.dry_run,
        )
    if schema == RESEARCH_SCHEMA:
        from quantara.research_pipeline import run_research_pipeline

        return run_research_pipeline(
            descriptor_path=args.descriptor,
            data_root=args.data_root,
            dry_run=args.dry_run,
        )
    if schema == VALIDATION_SCHEMA:
        from quantara.validation_pipeline import run_validation_pipeline

        return run_validation_pipeline(
            descriptor_path=args.descriptor,
            data_root=args.data_root,
            dry_run=args.dry_run,
        )

    print(f"invalid_descriptor: unrecognized descriptor schema {schema!r}",
          file=sys.stderr)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
