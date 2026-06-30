from __future__ import annotations

import re

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from bqcsv.schema import format_schema, schemas_match


class TableError(Exception):
    pass


def table_name_from_filename(filename_stem: str) -> str:
    name = re.sub(r"[^a-z0-9]+", "_", filename_stem.lower()).strip("_")
    if not name:
        name = "unnamed"
    if name[0].isdigit():
        name = f"csv_{name}"
    return name


def table_id(*, project: str | None, dataset: str, table: str) -> str:
    if project:
        return f"{project}.{dataset}.{table}"
    return f"{dataset}.{table}"


def get_bq_client(project: str | None) -> bigquery.Client:
    return bigquery.Client(project=project) if project else bigquery.Client()


def ensure_table_exists(
    client: bigquery.Client,
    destination_table_id: str,
    schema: list[bigquery.SchemaField],
    *,
    replace: bool = False,
) -> list[bigquery.SchemaField]:
    try:
        existing_table = client.get_table(destination_table_id)
    except NotFound:
        client.create_table(bigquery.Table(destination_table_id, schema=schema))
        return schema

    table_schema = list(existing_table.schema)
    if not schemas_match(schema, table_schema):
        if replace:
            return schema
        raise TableError(
            "CSV schema does not match the destination table schema. "
            f"CSV: [{format_schema(schema)}]. "
            f"Table: [{format_schema(table_schema)}]. "
            "Use --replace to recreate the table."
        )
    return table_schema
