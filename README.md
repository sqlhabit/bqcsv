# bqcsv

Upload a local CSV file to BigQuery using the `bq` CLI and your existing `gcloud` authentication.

## Why a dedicated CLI tool?

Out of the box, Google's `bq` CLI tool can't create a table with column names from a CSV file.

`bqcsv` fixes that:

* it first detects the schema
* creates a table with proper column names and types
* finally, it uses `bq load` to upload the CSV file

## Authentication

No additional authentication needed.

`bqcsv` uses your existing authentication via `gcloud auth login`.

## Requirements

- Python 3.10+
- [Google Cloud SDK](https://cloud.google.com/sdk) with `bq` on your `PATH`

## How to use `bqcsv`

### How to upload a CSV file to a table

To upload a table, you need to specify your project ID, dataset ID and a table name:

```bash
bqcsv data.csv --project my-gcp-project --dataset staging --table events_raw
```

The `--table` argument is optional. `bqcsv` will derive table name from the CSV file by default:

```bash
bqcsv data.csv --project my-gcp-project --dataset staging

# is identical to

bqcsv data.csv --project my-gcp-project --dataset staging --table data
```

### Saving your configuration

To avoid always passing `--project`, `--dataset` or `--table` options, you can save them to your local config:

```bash
bqcsv config set --project my-gcp-project --dataset analytics --table events
bqcsv config show
```

Defaults are stored in `~/.config/bqcsv/config.toml`.

After you set your defaults, you can call `bqcsv` without params:

```bash
bqcsv data.csv
```

If you haven't set your default `--table` value, the table name will be derived from the CSV file.

## Development

### How to install `bqcsv` from your local repo

```bash
pip install -e .
```

### Testing

To delete a test table, use `bq`:

```bash
bq rm -f -t  PROJECT_ID:DATASET_ID.TABLE_NAME
```

You can call Python script directly when working on a new feature of fixing a bug:

```sh
python -m bqcsv.cli config set --project PROJECT_ID --dataset DATASET_ID --table TEST_TABLE_NAME
```
