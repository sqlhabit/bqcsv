from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bqcsv.config import (
    CONFIG_KEYS,
    CONFIG_PATH,
    load_config,
    resolve_setting,
    save_config,
    unset_config,
)
from bqcsv.table import table_id
from bqcsv.uploader import upload_csv


def _upload_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bqcsv",
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
    parser.add_argument(
        "--output",
        choices=("text", "json"),
        default="text",
        help="Output format: text prints progress as it runs; json prints a single JSON object at the end",
    )
    return parser


def _config_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bqcsv config")
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


def build_sample_query(*, project: str | None, dataset: str, table: str) -> str:
    final_table_name = table_id(project=project, dataset=dataset, table=table)
    return f"SELECT *\nFROM {final_table_name}\nLIMIT 500"


def _emit_upload_result(
    *,
    output: str,
    logs: list[str],
    status: str,
    sample_query: str | None = None,
) -> None:
    if output == "json":
        payload: dict[str, str] = {"logs": "\n".join(logs), "status": status}
        if sample_query is not None:
            payload["sample_query"] = sample_query
        print(json.dumps(payload))
        return
    for line in logs:
        print(line, file=sys.stderr if status == "error" else sys.stdout)
    if sample_query is not None:
        print()
        print(f"Status: {status}.")
        print()
        print("Here's a sample query:")
        print()
        print(sample_query)
    else:
        print(f"Status: {status}.")


def _run_upload(argv: list[str]) -> int:
    args = _upload_parser().parse_args(argv)
    config = load_config()
    csv_path = args.csv_path.expanduser().resolve()
    project = resolve_setting(args.project, config, "project")
    dataset = resolve_setting(args.dataset, config, "dataset")
    table = resolve_table_name(csv_path, args.table, config)
    json_output = args.output == "json"
    logs: list[str] = []

    missing = [
        name
        for name, value in (("project", project), ("dataset", dataset))
        if not value
    ]
    if missing:
        names = ", ".join(f"--{name}" for name in missing)
        logs.append(
            f"Missing required setting(s): {names}. "
            f"Set them on the command line or via `bqcsv config set`."
        )
        _emit_upload_result(output=args.output, logs=logs, status="error")
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
            on_log=logs.append if json_output else None,
        )
    except Exception as exc:
        logs.append(str(exc))
        _emit_upload_result(output=args.output, logs=logs, status="error")
        return 1

    destination = f"{project}:{dataset}.{table}" if project else f"{dataset}.{table}"
    logs.append(f"Uploaded {args.csv_path} to {destination}")
    sample_query = build_sample_query(project=project, dataset=dataset, table=table)
    _emit_upload_result(
        output=args.output,
        logs=logs,
        status="success",
        sample_query=sample_query,
    )
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
