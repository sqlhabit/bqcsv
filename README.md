# bqcsv

Upload a local CSV file to BigQuery using the `bq` CLI and your existing `gcloud` authentication.

## Why a dedicated CLI tool?

Out of the box, Google's `bq` CLI cannot create a table with column names inferred from a CSV file.

`bqcsv` fixes that:

* detects the schema from the CSV file
* creates a table with proper column names and types
* loads the CSV file using `bq load`

## Authentication

No additional authentication is needed.

`bqcsv` uses your existing authentication via `gcloud auth login`.

## Requirements

- Python 3.10+
- [Google Cloud SDK](https://cloud.google.com/sdk) with `bq` on your `PATH`

## How to use `bqcsv`

### Upload a CSV file to a table

To upload a CSV file, specify your project ID, dataset ID, and table name:

```bash
bqcsv data.csv --project my-gcp-project --dataset staging --table events_raw
```

The `--table` argument is optional. By default, `bqcsv` derives the table name from the CSV file:

```bash
bqcsv data.csv --project my-gcp-project --dataset staging

# is identical to

bqcsv data.csv --project my-gcp-project --dataset staging --table data
```

### Saving your configuration

To avoid passing `--project`, `--dataset`, or `--table` on every run, save them to your local config:

```bash
bqcsv config set --project my-gcp-project --dataset analytics --table events
bqcsv config show
```

Defaults are stored in `~/.config/bqcsv/config.toml`.

After you set your defaults, you can call `bqcsv` without arguments:

```bash
bqcsv data.csv
```

If you have not set a default `--table` value, the table name is derived from the CSV file.

## Development

### Install from your local repo

```bash
pip install -e .
```

### Testing

To delete a test table, use `bq`:

```bash
bq rm -f -t  PROJECT_ID:DATASET_ID.TABLE_NAME
```

You can run the module directly when working on a new feature or fixing a bug:

```sh
python -m src.cli config set --project PROJECT_ID --dataset DATASET_ID --table TEST_TABLE_NAME
```

## Releasing to PyPI

1. **Bump the version** in both places (they must match):
   - `pyproject.toml` → `[project].version`
   - `src/__init__.py` → `__version__`

2. **Install build tools** (one-time):

   ```bash
   pip install build twine
   ```

3. **Run tests** and commit the version bump.

4. **Build the package**:

   ```bash
   python -m build
   ```

   This creates `dist/bqcsv-<version>.tar.gz` and `dist/bqcsv-<version>-py3-none-any.whl`.

5. **Upload to PyPI**:

   ```bash
   twine upload dist/*
   ```

   On first upload, create an account at [pypi.org](https://pypi.org) and use an [API token](https://pypi.org/help/#apitoken) as the password (`__token__` as the username).

6. **Tag the release** (optional but recommended):

   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```

After publishing, users can install the new version with:

```bash
pip install --upgrade bqcsv
```
