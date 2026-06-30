import json
import unittest
from pathlib import Path
from unittest.mock import patch

from bqcsv import __version__
from bqcsv.cli import _run_upload, build_sample_query, main, resolve_table_name


class VersionTests(unittest.TestCase):
    def test_short_version_flag(self) -> None:
        with patch("sys.stdout") as stdout:
            exit_code = main(["-v"])

        self.assertEqual(exit_code, 0)
        printed = "".join(call.args[0] for call in stdout.write.call_args_list)
        self.assertEqual(printed.strip(), f"bqcsv {__version__}")

    def test_long_version_flag(self) -> None:
        with patch("sys.stdout") as stdout:
            exit_code = main(["--version"])

        self.assertEqual(exit_code, 0)
        printed = "".join(call.args[0] for call in stdout.write.call_args_list)
        self.assertEqual(printed.strip(), f"bqcsv {__version__}")


class BuildSampleQueryTests(unittest.TestCase):
    def test_includes_project_when_provided(self) -> None:
        self.assertEqual(
            build_sample_query(project="proj", dataset="ds", table="tbl"),
            "SELECT *\nFROM proj.ds.tbl\nLIMIT 500",
        )

    def test_omits_project_when_not_provided(self) -> None:
        self.assertEqual(
            build_sample_query(project=None, dataset="ds", table="tbl"),
            "SELECT *\nFROM ds.tbl\nLIMIT 500",
        )


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


class RunUploadStatusTests(unittest.TestCase):
    def test_prints_success_status_on_upload(self) -> None:
        csv_path = Path(__file__).resolve().parent / "test_comma.csv"
        with patch("src.cli.upload_csv") as upload_csv:
            with patch("sys.stdout") as stdout:
                exit_code = _run_upload(
                    [
                        str(csv_path),
                        "--project",
                        "proj",
                        "--dataset",
                        "ds",
                    ]
                )

        self.assertEqual(exit_code, 0)
        upload_csv.assert_called_once()
        printed = " ".join(call.args[0] for call in stdout.write.call_args_list)
        self.assertIn("Status: success.", printed)
        self.assertIn("Here's a sample query:", printed)
        self.assertIn("SELECT *", printed)
        self.assertIn("FROM proj.ds.", printed)
        self.assertIn("LIMIT 500", printed)

    def test_prints_error_status_on_upload_failure(self) -> None:
        csv_path = Path(__file__).resolve().parent / "test_comma.csv"
        with patch(
            "src.cli.upload_csv",
            side_effect=RuntimeError("CSV parsing failed"),
        ):
            with patch("sys.stdout") as stdout:
                exit_code = _run_upload(
                    [
                        str(csv_path),
                        "--project",
                        "proj",
                        "--dataset",
                        "ds",
                    ]
                )

        self.assertEqual(exit_code, 1)
        printed = " ".join(call.args[0] for call in stdout.write.call_args_list)
        self.assertIn("Status: error.", printed)

    def test_prints_error_status_when_settings_missing(self) -> None:
        csv_path = Path(__file__).resolve().parent / "test_comma.csv"
        with patch("src.cli.load_config", return_value={}):
            with patch("sys.stdout") as stdout:
                exit_code = _run_upload([str(csv_path)])

        self.assertEqual(exit_code, 2)
        printed = " ".join(call.args[0] for call in stdout.write.call_args_list)
        self.assertIn("Status: error.", printed)

    def test_json_output_prints_single_result_on_success(self) -> None:
        csv_path = Path(__file__).resolve().parent / "test_comma.csv"

        def fake_upload(*_args, on_log=None, **_kwargs):
            if on_log is not None:
                on_log("Detected field delimiter: ','")
                on_log("Inferred schema: [id:INTEGER]")

        with patch("src.cli.upload_csv", side_effect=fake_upload):
            with patch("sys.stdout") as stdout:
                exit_code = _run_upload(
                    [
                        str(csv_path),
                        "--project",
                        "proj",
                        "--dataset",
                        "ds",
                        "--output",
                        "json",
                    ]
                )

        self.assertEqual(exit_code, 0)
        printed = "".join(call.args[0] for call in stdout.write.call_args_list)
        result = json.loads(printed)
        self.assertEqual(result["status"], "success")
        self.assertIn("Detected field delimiter", result["logs"])
        self.assertIn(f"Uploaded {csv_path} to proj:ds.", result["logs"])
        self.assertEqual(
            result["sample_query"],
            "SELECT *\nFROM proj.ds.test_comma\nLIMIT 500",
        )

    def test_json_output_prints_single_result_on_error(self) -> None:
        csv_path = Path(__file__).resolve().parent / "test_comma.csv"
        with patch(
            "src.cli.upload_csv",
            side_effect=RuntimeError("CSV parsing failed"),
        ):
            with patch("sys.stdout") as stdout:
                exit_code = _run_upload(
                    [
                        str(csv_path),
                        "--project",
                        "proj",
                        "--dataset",
                        "ds",
                        "--output",
                        "json",
                    ]
                )

        self.assertEqual(exit_code, 1)
        printed = "".join(call.args[0] for call in stdout.write.call_args_list)
        result = json.loads(printed)
        self.assertEqual(result["status"], "error")
        self.assertIn("CSV parsing failed", result["logs"])


if __name__ == "__main__":
    unittest.main()
