from __future__ import annotations

import argparse
import sys
from pathlib import Path

from upload_bq_dataset.config import (
    CONFIG_KEYS,
    CONFIG_PATH,
    load_config,
    resolve_setting,
    save_config,
    unset_config,
)
from upload_bq_dataset.uploader import UploadError, upload_csv


def _upload_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="upload-bq-dataset",
        description="Upload a local CSV file to BigQuery using the authenticated `bq` CLI.",
    )
    parser.add_argument("csv_path", type=Path, help="Path to the local CSV file to upload")
    parser.add_argument("--project", help="GCP project ID (overrides config)")
    parser.add_argument("--dataset", help="BigQuery dataset ID (overrides config)")
    parser.add_argument(
        "--table",
        help="BigQuery table ID (overrides config; defaults to the CSV file name without extension)",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace the destination table instead of appending rows",
    )
    parser.add_argument(
        "--no-header",
        action="store_true",
        help="Treat the first row as data instead of a header row",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        help="Optional JSON schema file for the table (disables autodetect)",
    )
    return parser


def _config_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="upload-bq-dataset config")
    subparsers = parser.add_subparsers(dest="config_command", required=True)

    show_parser = subparsers.add_parser("show", help="Show saved defaults")
    show_parser.set_defaults(func=_run_config_show)

    set_parser = subparsers.add_parser("set", help="Save default project/dataset/table")
    set_parser.add_argument("--project", help="Default GCP project ID")
    set_parser.add_argument("--dataset", help="Default BigQuery dataset ID")
    set_parser.add_argument("--table", help="Default BigQuery table ID")
    set_parser.set_defaults(func=_run_config_set)

    unset_parser = subparsers.add_parser("unset", help="Remove saved defaults")
    unset_parser.add_argument("--project", action="store_true", help="Remove default project")
    unset_parser.add_argument("--dataset", action="store_true", help="Remove default dataset")
    unset_parser.add_argument("--table", action="store_true", help="Remove default table")
    unset_parser.set_defaults(func=_run_config_unset)

    return parser


def resolve_table_name(
    csv_path: Path,
    cli_table: str | None,
    config: dict[str, str],
) -> str:
    table = resolve_setting(cli_table, config, "table")
    if table:
        return table
    return csv_path.expanduser().resolve().stem


def _run_upload(argv: list[str]) -> int:
    args = _upload_parser().parse_args(argv)
    config = load_config()
    csv_path = args.csv_path.expanduser().resolve()
    project = resolve_setting(args.project, config, "project")
    dataset = resolve_setting(args.dataset, config, "dataset")
    table = resolve_table_name(csv_path, args.table, config)

    missing = [
        name
        for name, value in (("project", project), ("dataset", dataset))
        if not value
    ]
    if missing:
        names = ", ".join(f"--{name}" for name in missing)
        print(
            f"Missing required setting(s): {names}. "
            f"Set them on the command line or via `upload-bq-dataset config set`.",
            file=sys.stderr,
        )
        return 2

    try:
        upload_csv(
            csv_path,
            project=project,
            dataset=dataset,
            table=table,
            replace=args.replace,
            skip_header=not args.no_header,
            schema_path=args.schema.expanduser().resolve() if args.schema else None,
        )
    except UploadError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    destination = f"{project}:{dataset}.{table}" if project else f"{dataset}.{table}"
    print(f"Uploaded {args.csv_path} to {destination}")
    return 0


def _run_config_show(_: argparse.Namespace) -> int:
    config = load_config()
    if not config:
        print(f"No config saved at {CONFIG_PATH}")
        return 0
    for key in CONFIG_KEYS:
        if key in config:
            print(f"{key} = {config[key]}")
    print(f"\nConfig file: {CONFIG_PATH}")
    return 0


def _run_config_set(args: argparse.Namespace) -> int:
    updates = {
        key: value
        for key, value in (
            ("project", args.project),
            ("dataset", args.dataset),
            ("table", args.table),
        )
        if value
    }
    if not updates:
        print("Provide at least one of --project, --dataset, or --table.", file=sys.stderr)
        return 2
    save_config(updates)
    print(f"Saved defaults to {CONFIG_PATH}")
    return 0


def _run_config_unset(args: argparse.Namespace) -> int:
    keys = [key for key in CONFIG_KEYS if getattr(args, key)]
    if not keys:
        print("Provide at least one of --project, --dataset, or --table.", file=sys.stderr)
        return 2
    unset_config(keys)
    print(f"Removed {', '.join(keys)} from {CONFIG_PATH}")
    return 0


def _run_config(argv: list[str]) -> int:
    args = _config_parser().parse_args(argv)
    return args.func(args)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "config":
        return _run_config(argv[1:])
    return _run_upload(argv)


if __name__ == "__main__":
    raise SystemExit(main())
