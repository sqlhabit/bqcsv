from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
from google.api_core.exceptions import NotFound
from google.cloud import bigquery

_CANDIDATE_DELIMITERS = ",;\t|"
_DEFAULT_FIELD_DELIMITER = ","
_DELIMITER_SAMPLE_SIZE = 8192
_INTEGER_RE = re.compile(r"^-?\d+$")
_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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


def _delimiter_count_in_line(line: str) -> dict[str, int]:
    return {delimiter: line.count(delimiter) for delimiter in _CANDIDATE_DELIMITERS}


def _delimiter_from_header_line(line: str) -> str | None:
    counts = _delimiter_count_in_line(line)
    delimiter, count = max(counts.items(), key=lambda item: item[1])
    if count == 0:
        return None
    tied = [candidate for candidate, value in counts.items() if value == count]
    if len(tied) > 1:
        return None
    return delimiter


def detect_field_delimiter(csv_path: Path) -> str:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        sample = handle.read(_DELIMITER_SAMPLE_SIZE)
    if not sample.strip():
        return _DEFAULT_FIELD_DELIMITER

    first_line = sample.splitlines()[0]
    header_delimiter = _delimiter_from_header_line(first_line)

    try:
        sniffed = csv.Sniffer().sniff(sample, delimiters=_CANDIDATE_DELIMITERS).delimiter
    except csv.Error:
        return header_delimiter if header_delimiter is not None else _DEFAULT_FIELD_DELIMITER

    if header_delimiter is None:
        return sniffed

    sniffed_columns = first_line.count(sniffed) + (1 if sniffed in first_line else 1)
    header_columns = first_line.count(header_delimiter) + 1
    if header_columns > sniffed_columns:
        return header_delimiter
    return sniffed


def _table_id(*, project: str | None, dataset: str, table: str) -> str:
    if project:
        return f"{project}.{dataset}.{table}"
    return f"{dataset}.{table}"


def _non_empty_values(series: pd.Series) -> pd.Series:
    as_string = series.astype(str).str.strip()
    return as_string[as_string != ""]


def _infer_bq_type_for_series(series: pd.Series) -> str:
    values = _non_empty_values(series)
    if values.empty:
        return "STRING"

    if pd.api.types.is_bool_dtype(series.dtype):
        return "BOOLEAN"
    if pd.api.types.is_integer_dtype(series.dtype):
        return "INTEGER"
    if pd.api.types.is_float_dtype(series.dtype):
        if (series.dropna() % 1 == 0).all():
            return "INTEGER"
        return "FLOAT"
    if pd.api.types.is_datetime64_any_dtype(series.dtype):
        return "TIMESTAMP"

    if values.str.match(_INTEGER_RE).all():
        return "INTEGER"

    numeric = pd.to_numeric(series, errors="coerce")
    non_null = series.notna()
    if non_null.any() and numeric[non_null].notna().all():
        if (numeric[non_null] % 1 == 0).all():
            return "INTEGER"
        return "FLOAT"

    if values.str.match(_DATE_ONLY_RE).all():
        return "DATE"

    parsed = pd.to_datetime(series, errors="coerce", format="mixed")
    if non_null.any() and parsed[non_null].notna().all():
        return "TIMESTAMP"

    return "STRING"


def _load_schema_from_json(schema_path: Path) -> list[bigquery.SchemaField]:
    with schema_path.open(encoding="utf-8") as handle:
        raw_schema = json.load(handle)
    return [bigquery.SchemaField.from_api_repr(field) for field in raw_schema]


def _read_csv_dataframe(
    csv_path: Path,
    *,
    field_delimiter: str,
    skip_header: bool,
    column_names: list[str] | None = None,
) -> pd.DataFrame:
    read_kwargs = {
        "filepath_or_buffer": csv_path,
        "sep": field_delimiter,
        "encoding": "utf-8",
        "dtype": str,
        "keep_default_na": False,
    }
    if skip_header:
        dataframe = pd.read_csv(**read_kwargs)
    else:
        dataframe = pd.read_csv(**read_kwargs, header=None)
        if column_names is None:
            raise UploadError(
                "CSV has no header row. Create the destination table first or upload a CSV with a header."
            )
        if len(column_names) != len(dataframe.columns):
            raise UploadError(
                f"CSV has {len(dataframe.columns)} column(s) but the destination table has "
                f"{len(column_names)} column(s)."
            )
        dataframe.columns = column_names
    return dataframe


def _format_dataframe_for_bq_load(
    dataframe: pd.DataFrame,
    schema: list[bigquery.SchemaField],
) -> pd.DataFrame:
    formatted = dataframe.copy()
    for field in schema:
        if field.name not in formatted.columns:
            continue
        column = formatted[field.name]
        if field.field_type == "TIMESTAMP":
            parsed = pd.to_datetime(column, errors="coerce", format="mixed")
            formatted[field.name] = parsed.dt.strftime("%Y-%m-%d %H:%M:%S.%f")
        elif field.field_type == "DATE":
            parsed = pd.to_datetime(column, errors="coerce", format="mixed")
            formatted[field.name] = parsed.dt.strftime("%Y-%m-%d")
        elif field.field_type == "INTEGER":
            formatted[field.name] = (
                pd.to_numeric(column, errors="coerce").astype("Int64").astype(str)
            )
    return formatted


def _write_prepared_csv(
    dataframe: pd.DataFrame,
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


def infer_bq_schema_from_csv(
    csv_path: Path,
    *,
    field_delimiter: str,
    skip_header: bool,
    column_names: list[str] | None = None,
) -> list[bigquery.SchemaField]:
    dataframe = _read_csv_dataframe(
        csv_path,
        field_delimiter=field_delimiter,
        skip_header=skip_header,
        column_names=column_names,
    )

    return [
        bigquery.SchemaField(str(column), _infer_bq_type_for_series(dataframe[column]))
        for column in dataframe.columns
    ]


def _format_schema(schema: list[bigquery.SchemaField]) -> str:
    return ", ".join(f"{field.name}:{field.field_type}" for field in schema)


def _schemas_match(
    csv_schema: list[bigquery.SchemaField],
    table_schema: list[bigquery.SchemaField],
) -> bool:
    if len(csv_schema) != len(table_schema):
        return False
    for csv_field, table_field in zip(csv_schema, table_schema, strict=True):
        if csv_field.name != table_field.name:
            return False
        if csv_field.field_type.upper() != table_field.field_type.upper():
            return False
    return True


def _get_bq_client(project: str | None) -> bigquery.Client:
    return bigquery.Client(project=project) if project else bigquery.Client()


def _ensure_table_exists(
    client: bigquery.Client,
    table_id: str,
    schema: list[bigquery.SchemaField],
    *,
    replace: bool = False,
) -> list[bigquery.SchemaField]:
    try:
        existing_table = client.get_table(table_id)
    except NotFound:
        client.create_table(bigquery.Table(table_id, schema=schema))
        return schema

    table_schema = list(existing_table.schema)
    if not _schemas_match(schema, table_schema):
        if replace:
            return schema
        raise UploadError(
            "CSV schema does not match the destination table schema. "
            f"CSV: [{_format_schema(schema)}]. "
            f"Table: [{_format_schema(table_schema)}]. "
            "Use --replace to recreate the table."
        )
    return table_schema


def _write_schema_file(schema: list[bigquery.SchemaField]) -> Path:
    with tempfile.NamedTemporaryFile(
        "w",
        suffix=".json",
        delete=False,
        encoding="utf-8",
    ) as handle:
        json.dump([field.to_api_repr() for field in schema], handle)
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
    field_delimiter: str = _DEFAULT_FIELD_DELIMITER,
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


def upload_csv(
    csv_path: Path,
    *,
    project: str | None,
    dataset: str,
    table: str,
    replace: bool = False,
    skip_header: bool = True,
    schema_path: Path | None = None,
) -> None:
    ensure_bq_available()
    if not csv_path.is_file():
        raise UploadError(f"CSV file not found: {csv_path}")
    if schema_path is not None and not schema_path.is_file():
        raise UploadError(f"Schema file not found: {schema_path}")

    field_delimiter = detect_field_delimiter(csv_path)
    table_id = _table_id(project=project, dataset=dataset, table=table)
    client = _get_bq_client(project)

    explicit_schema = (
        _load_schema_from_json(schema_path) if schema_path is not None else None
    )

    column_names: list[str] | None = None
    if not skip_header:
        if explicit_schema is not None:
            column_names = [field.name for field in explicit_schema]
        else:
            try:
                existing_table = client.get_table(table_id)
            except NotFound as exc:
                raise UploadError(
                    "CSV has no header row and destination table does not exist. "
                    "Upload a CSV with a header or create the table first."
                ) from exc
            column_names = [field.name for field in existing_table.schema]

    if explicit_schema is not None:
        csv_schema = explicit_schema
    else:
        csv_schema = infer_bq_schema_from_csv(
            csv_path,
            field_delimiter=field_delimiter,
            skip_header=skip_header,
            column_names=column_names,
        )

    load_schema = _ensure_table_exists(
        client,
        table_id,
        csv_schema,
        replace=replace,
    )

    dataframe = _read_csv_dataframe(
        csv_path,
        field_delimiter=field_delimiter,
        skip_header=skip_header,
        column_names=column_names,
    )
    prepared_csv_path = _write_prepared_csv(
        _format_dataframe_for_bq_load(dataframe, load_schema),
        field_delimiter=field_delimiter,
        skip_header=skip_header,
    )

    temp_schema_path = _write_schema_file(load_schema)
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
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as exc:
            raise UploadError(f"`bq load` failed with exit code {exc.returncode}") from exc
    finally:
        temp_schema_path.unlink(missing_ok=True)
        prepared_csv_path.unlink(missing_ok=True)
