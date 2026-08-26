"""Command-line entry point.

``python -m quantara --descriptor <yaml> --data-root <dir> [--dry-run]``:
the descriptor's ``schema`` field selects the pipeline (spec design §3.8) —
``quantara.dataset-descriptor/v1`` runs the slice 001 acquisition pipeline,
``quantara.derived-dataset-descriptor/v1`` runs the derivation pipeline,
``quantara.research-descriptor/v1`` runs the research-table pipeline,
``quantara.validation-descriptor/v1`` runs the validation-folds pipeline,
``quantara.evaluation-descriptor/v1`` runs the evaluation pipeline, and
anything else is rejected with exit 3 ``invalid_descriptor``.

Alternatively, ``--dataset-type feature_evaluation`` routes directly to the
evaluation pipeline.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE_SCHEMA = "quantara.dataset-descriptor/v1"
BASE_SCHEMA_V2 = "quantara.dataset-descriptor/v2"
DERIVED_SCHEMA = "quantara.derived-dataset-descriptor/v1"
RESEARCH_SCHEMA = "quantara.research-descriptor/v1"
VALIDATION_SCHEMA = "quantara.validation-descriptor/v1"
EVALUATION_SCHEMA = "quantara.evaluation-descriptor/v1"

APPROVED_DATASET_TYPES = frozenset({"feature_evaluation"})


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch on dataset-type or descriptor schema."""
    parser = argparse.ArgumentParser(prog="quantara")
    parser.add_argument("--dataset-type", choices=None, help="Approved dataset type")
    parser.add_argument("--descriptor", help="Path to descriptor YAML file")
    parser.add_argument("--data-root", default="data", help="Root data directory")
    parser.add_argument("--dry-run", action="store_true", help="Run without publishing")

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    # Handle explicit --dataset-type flag
    if args.dataset_type is not None:
        if args.dataset_type not in APPROVED_DATASET_TYPES:
            print(
                f"unapproved_dataset_type: {args.dataset_type!r} is not an approved dataset type",
                file=sys.stderr,
            )
            return 2
        if not args.descriptor:
            print("--descriptor is required when --dataset-type is provided", file=sys.stderr)
            return 2
        descriptor_path = Path(args.descriptor)
        if not descriptor_path.is_file():
            print(f"descriptor file not found: {descriptor_path}", file=sys.stderr)
            return 2

        from quantara.evaluation_pipeline import run_evaluation_pipeline

        return run_evaluation_pipeline(
            descriptor_path=args.descriptor,
            data_root=args.data_root,
            dry_run=args.dry_run,
        )

    if not args.descriptor:
        print("--descriptor is required", file=sys.stderr)
        return 2

    descriptor_path = Path(args.descriptor)
    if not descriptor_path.is_file():
        print(f"descriptor file not found: {descriptor_path}", file=sys.stderr)
        return 2

    schema = None
    try:
        import yaml

        document = yaml.safe_load(descriptor_path.read_text(encoding="utf-8"))
        if isinstance(document, dict):
            schema = document.get("schema")
    except (OSError, yaml.YAMLError):
        schema = None

    if schema in (BASE_SCHEMA, BASE_SCHEMA_V2):
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
    if schema == EVALUATION_SCHEMA:
        from quantara.evaluation_pipeline import run_evaluation_pipeline

        return run_evaluation_pipeline(
            descriptor_path=args.descriptor,
            data_root=args.data_root,
            dry_run=args.dry_run,
        )

    print(
        f"invalid_descriptor: unrecognized descriptor schema {schema!r}",
        file=sys.stderr,
    )
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
