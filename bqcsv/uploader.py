from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from google.api_core.exceptions import NotFound

from bqcsv.schema import (
    DEFAULT_FIELD_DELIMITER,
    SchemaError,
    detect_field_delimiter,
    format_dataframe_for_bq_load,
    format_schema,
    infer_bq_schema_from_csv,
    load_schema_from_json,
    read_csv_dataframe,
    write_schema_file,
)
from bqcsv.table import TableError, ensure_table_exists, get_bq_client, table_id


class UploadError(Exception):
    pass


def ensure_bq_available() -> str:
    bq_path = shutil.which("bq")
    if not bq_path:
        raise UploadError(
            "The `bq` CLI was not found on PATH. Install the Google Cloud SDK and run "
            "`gcloud auth login` before uploading."
        )
    return bq_path


def _write_prepared_csv(
    dataframe,
    *,
    field_delimiter: str,
    skip_header: bool,
) -> Path:
    with tempfile.NamedTemporaryFile(
        "w",
        suffix=".csv",
        delete=False,
        newline="",
        encoding="utf-8",
    ) as handle:
        dataframe.to_csv(
            handle,
            index=False,
            sep=field_delimiter,
            header=skip_header,
        )
        return Path(handle.name)


def build_load_command(
    csv_path: Path,
    *,
    project: str | None,
    dataset: str,
    table: str,
    schema_path: Path,
    replace: bool = False,
    skip_header: bool = True,
    field_delimiter: str = DEFAULT_FIELD_DELIMITER,
) -> list[str]:
    destination = f"{project}:{dataset}.{table}" if project else f"{dataset}.{table}"
    cmd = ["bq", "load", "--source_format=CSV", "--noautodetect"]
    if project:
        cmd.extend(["--project_id", project])
    cmd.append(f"--field_delimiter={field_delimiter}")
    if skip_header:
        cmd.append("--skip_leading_rows=1")
    if replace:
        cmd.append("--replace")
    cmd.append(destination)
    cmd.append(str(csv_path))
    cmd.append(str(schema_path))
    return cmd


def _log(on_log: Callable[[str], None] | None, message: str) -> None:
    if on_log is not None:
        on_log(message)


def upload_csv(
    csv_path: Path,
    *,
    project: str | None,
    dataset: str,
    table: str,
    replace: bool = False,
    skip_header: bool = True,
    schema_path: Path | None = None,
    on_log: Callable[[str], None] | None = None,
) -> None:
    ensure_bq_available()
    if not csv_path.is_file():
        raise UploadError(f"CSV file not found: {csv_path}")
    if schema_path is not None and not schema_path.is_file():
        raise UploadError(f"Schema file not found: {schema_path}")

    try:
        field_delimiter = detect_field_delimiter(csv_path)
        _log(on_log, f"Detected field delimiter: {field_delimiter!r}")
        destination_table_id = table_id(project=project, dataset=dataset, table=table)
        client = get_bq_client(project)

        explicit_schema = (
            load_schema_from_json(schema_path) if schema_path is not None else None
        )

        column_names: list[str] | None = None
        if not skip_header:
            if explicit_schema is not None:
                column_names = [field.name for field in explicit_schema]
            else:
                try:
                    existing_table = client.get_table(destination_table_id)
                except NotFound as exc:
                    raise UploadError(
                        "CSV has no header row and destination table does not exist. "
                        "Upload a CSV with a header or create the table first."
                    ) from exc
                column_names = [field.name for field in existing_table.schema]

        if explicit_schema is not None:
            csv_schema = explicit_schema
            _log(on_log, f"Using schema from {schema_path}")
        else:
            csv_schema = infer_bq_schema_from_csv(
                csv_path,
                field_delimiter=field_delimiter,
                skip_header=skip_header,
                column_names=column_names,
            )
            _log(on_log, f"Inferred schema: [{format_schema(csv_schema)}]")

        load_schema = ensure_table_exists(
            client,
            destination_table_id,
            csv_schema,
            replace=replace,
        )
        _log(on_log, f"Destination table ready: {destination_table_id}")

        dataframe = read_csv_dataframe(
            csv_path,
            field_delimiter=field_delimiter,
            skip_header=skip_header,
            column_names=column_names,
        )
        prepared_csv_path = _write_prepared_csv(
            format_dataframe_for_bq_load(dataframe, load_schema),
            field_delimiter=field_delimiter,
            skip_header=skip_header,
        )

        temp_schema_path = write_schema_file(load_schema)
        try:
            cmd = build_load_command(
                prepared_csv_path,
                project=project,
                dataset=dataset,
                table=table,
                schema_path=temp_schema_path,
                replace=replace,
                skip_header=skip_header,
                field_delimiter=field_delimiter,
            )
            _log(on_log, f"Running: {' '.join(cmd)}")
            try:
                if on_log is not None:
                    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                    if result.stdout.strip():
                        _log(on_log, result.stdout.rstrip())
                    if result.stderr.strip():
                        _log(on_log, result.stderr.rstrip())
                else:
                    subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as exc:
                raise UploadError(f"`bq load` failed with exit code {exc.returncode}") from exc
        finally:
            temp_schema_path.unlink(missing_ok=True)
            prepared_csv_path.unlink(missing_ok=True)
    except (SchemaError, TableError) as exc:
        raise UploadError(str(exc)) from exc
