import unittest
from pathlib import Path

from upload_bq_dataset.cli import resolve_table_name


class ResolveTableNameTests(unittest.TestCase):
    def test_uses_csv_stem_when_table_not_provided(self) -> None:
        csv_path = Path("/tmp/data/my_export.csv")
        self.assertEqual(resolve_table_name(csv_path, None, {}), "my_export")

    def test_cli_table_overrides_csv_stem(self) -> None:
        csv_path = Path("/tmp/data/my_export.csv")
        self.assertEqual(resolve_table_name(csv_path, "custom_table", {}), "custom_table")

    def test_config_table_overrides_csv_stem(self) -> None:
        csv_path = Path("/tmp/data/my_export.csv")
        self.assertEqual(
            resolve_table_name(csv_path, None, {"table": "saved_table"}),
            "saved_table",
        )

    def test_cli_table_overrides_config_table(self) -> None:
        csv_path = Path("/tmp/data/my_export.csv")
        self.assertEqual(
            resolve_table_name(csv_path, "cli_table", {"table": "saved_table"}),
            "cli_table",
        )


if __name__ == "__main__":
    unittest.main()
