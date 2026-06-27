import tempfile
import unittest
from pathlib import Path

from upload_bq_dataset.uploader import (
    _format_dataframe_for_bq_load,
    _read_csv_dataframe,
    build_load_command,
    detect_field_delimiter,
    infer_bq_schema_from_csv,
)


class InferSchemaTests(unittest.TestCase):
    def test_semicolon_csv_infers_typed_columns(self) -> None:
        csv_path = Path(__file__).resolve().parent / "test_semicolon.csv"
        delimiter = detect_field_delimiter(csv_path)
        schema = infer_bq_schema_from_csv(
            csv_path,
            field_delimiter=delimiter,
            skip_header=True,
        )

        self.assertEqual(delimiter, ";")
        self.assertEqual(len(schema), 7)
        self.assertEqual(
            [(field.name, field.field_type) for field in schema],
            [
                ("id", "INTEGER"),
                ("email", "STRING"),
                ("created_date", "DATE"),
                ("created_at", "TIMESTAMP"),
                ("is_active", "BOOLEAN"),
                ("score", "FLOAT"),
                ("notes", "STRING"),
            ],
        )

    def test_comma_csv_infers_typed_columns(self) -> None:
        csv_path = Path(__file__).resolve().parent / "test_comma.csv"
        delimiter = detect_field_delimiter(csv_path)
        schema = infer_bq_schema_from_csv(
            csv_path,
            field_delimiter=delimiter,
            skip_header=True,
        )

        self.assertEqual(delimiter, ",")
        self.assertEqual(len(schema), 7)
        self.assertEqual(
            [(field.name, field.field_type) for field in schema],
            [
                ("id", "INTEGER"),
                ("email", "STRING"),
                ("created_date", "DATE"),
                ("created_at", "TIMESTAMP"),
                ("is_active", "BOOLEAN"),
                ("score", "FLOAT"),
                ("notes", "STRING"),
            ],
        )

    def test_ambiguous_values_fall_back_to_string(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
            handle.write("id,mixed\n")
            handle.write("1,2026-05-14\n")
            handle.write("2,not-a-date\n")
            csv_path = Path(handle.name)

        try:
            schema = infer_bq_schema_from_csv(
                csv_path,
                field_delimiter=",",
                skip_header=True,
            )
            types = {field.name: field.field_type for field in schema}
            self.assertEqual(types["id"], "INTEGER")
            self.assertEqual(types["mixed"], "STRING")
        finally:
            csv_path.unlink(missing_ok=True)

    def test_build_load_command_disables_autodetect(self) -> None:
        cmd = build_load_command(
            Path("data.csv"),
            project="proj",
            dataset="ds",
            table="t",
            schema_path=Path("schema.json"),
            field_delimiter=";",
        )
        self.assertIn("--noautodetect", cmd)
        self.assertIn("--field_delimiter=;", cmd)

    def test_timestamp_values_are_normalized_for_bq_load(self) -> None:
        csv_path = Path(__file__).resolve().parent / "test_semicolon.csv"
        delimiter = detect_field_delimiter(csv_path)
        schema = infer_bq_schema_from_csv(
            csv_path,
            field_delimiter=delimiter,
            skip_header=True,
        )
        dataframe = _read_csv_dataframe(
            csv_path,
            field_delimiter=delimiter,
            skip_header=True,
        )
        prepared = _format_dataframe_for_bq_load(dataframe, schema)
        self.assertEqual(prepared.loc[0, "created_at"], "2026-05-14 09:21:11.183710")


if __name__ == "__main__":
    unittest.main()
