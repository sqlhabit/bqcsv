from __future__ import annotations

import csv
import json
import re
import tempfile
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

_CANDIDATE_DELIMITERS = ",;\t|"
DEFAULT_FIELD_DELIMITER = ","
_DELIMITER_SAMPLE_SIZE = 8192
_INTEGER_RE = re.compile(r"^-?\d+$")
_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_BOOLEAN_VALUES = frozenset({"true", "false"})


class SchemaError(Exception):
    pass


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
        return DEFAULT_FIELD_DELIMITER

    first_line = sample.splitlines()[0]
    header_delimiter = _delimiter_from_header_line(first_line)

    try:
        sniffed = csv.Sniffer().sniff(sample, delimiters=_CANDIDATE_DELIMITERS).delimiter
    except csv.Error:
        return header_delimiter if header_delimiter is not None else DEFAULT_FIELD_DELIMITER

    if header_delimiter is None:
        return sniffed

    sniffed_columns = first_line.count(sniffed) + (1 if sniffed in first_line else 1)
    header_columns = first_line.count(header_delimiter) + 1
    if header_columns > sniffed_columns:
        return header_delimiter
    return sniffed


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

    if values.str.lower().isin(_BOOLEAN_VALUES).all():
        return "BOOLEAN"

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


def load_schema_from_json(schema_path: Path) -> list[bigquery.SchemaField]:
    with schema_path.open(encoding="utf-8") as handle:
        raw_schema = json.load(handle)
    return [bigquery.SchemaField.from_api_repr(field) for field in raw_schema]


def read_csv_dataframe(
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
            raise SchemaError(
                "CSV has no header row. Create the destination table first or upload a CSV with a header."
            )
        if len(column_names) != len(dataframe.columns):
            raise SchemaError(
                f"CSV has {len(dataframe.columns)} column(s) but the destination table has "
                f"{len(column_names)} column(s)."
            )
        dataframe.columns = column_names
    return dataframe


def format_dataframe_for_bq_load(
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


def infer_bq_schema_from_csv(
    csv_path: Path,
    *,
    field_delimiter: str,
    skip_header: bool,
    column_names: list[str] | None = None,
) -> list[bigquery.SchemaField]:
    dataframe = read_csv_dataframe(
        csv_path,
        field_delimiter=field_delimiter,
        skip_header=skip_header,
        column_names=column_names,
    )

    return [
        bigquery.SchemaField(str(column), _infer_bq_type_for_series(dataframe[column]))
        for column in dataframe.columns
    ]


def format_schema(schema: list[bigquery.SchemaField]) -> str:
    return ", ".join(f"{field.name}:{field.field_type}" for field in schema)


def schemas_match(
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


def write_schema_file(schema: list[bigquery.SchemaField]) -> Path:
    with tempfile.NamedTemporaryFile(
        "w",
        suffix=".json",
        delete=False,
        encoding="utf-8",
    ) as handle:
        json.dump([field.to_api_repr() for field in schema], handle)
        return Path(handle.name)
