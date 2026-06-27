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
python -m bqcsv.cli config set --project PROJECT_ID --dataset DATASET_ID --table TEST_TABLE_NAME
```
