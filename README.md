# upload-bq-dataset

Upload a local CSV file to BigQuery using the `bq` CLI and your existing `gcloud` authentication.

## Requirements

- Python 3.10+
- [Google Cloud SDK](https://cloud.google.com/sdk) with `bq` on your `PATH`
- An authenticated account: `gcloud auth login`

## Install

```bash
pip install -e .
```

## Configure defaults

Defaults are stored in `~/.config/upload_bq_dataset/config.toml`.

```bash
upload-bq-dataset config set --project my-gcp-project --dataset analytics --table events
upload-bq-dataset config show
```

## Upload

```bash
# Uses saved defaults
upload-bq-dataset data.csv

# Override any default
upload-bq-dataset data.csv --project my-gcp-project --dataset staging --table events_raw

# Replace table contents instead of appending
upload-bq-dataset data.csv --replace

# CSV without a header row
upload-bq-dataset data.csv --no-header

# Provide an explicit JSON schema file
upload-bq-dataset data.csv --schema schema.json
```

`--project`, `--dataset`, and `--table` can each be set in config or passed on the command line.

## Testing

Upload a test CSV:

```
upload-bq-dataset test.csv --project einsk5g-dataplatform-prd --dataset anatoli_temp_dataset --table test
```

Delete a test table:

```
bq rm -f -t  einsk5g-dataplatform-prd:anatoli_temp_dataset.test
```

Full command to re-install and re-upload:

```sh
cd /path/to/upload_bq_dataset

# 1. Reinstall (editable install links to source; run again after entry-point changes)
pip install -e .

# 2. If you use pyenv, refresh shims so the shell finds the script
pyenv rehash

# 3. Verify you're running the local install
which upload-bq-dataset
# should point into your pyenv, e.g. ~/.pyenv/versions/.../bin/upload-bq-dataset

# 4. Drop old table (needed if schema changed) and upload
bq rm -f -t einsk5g-dataplatform-prd:anatoli_temp_dataset.test
# upload-bq-dataset test.csv --project einsk5g-dataplatform-prd --dataset anatoli_temp_dataset --table test --replace
python -m upload_bq_dataset.cli test.csv --project einsk5g-dataplatform-prd --dataset anatoli_temp_dataset --table test --replace
```

With `pip install -e .`, code edits under `upload_bq_dataset/` are picked up immediately — you do **not** need to reinstall after every change unless you modify `pyproject.toml` entry points.

If the shell still runs an old version, bypass the shim:

```sh
python -m upload_bq_dataset.cli test.csv --project einsk5g-dataplatform-prd --dataset anatoli_temp_dataset --table test --replace
```
