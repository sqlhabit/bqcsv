# bqcsv

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

Defaults are stored in `~/.config/bqcsv/config.toml`.

```bash
bqcsv config set --project my-gcp-project --dataset analytics --table events
bqcsv config show
```

## Upload

```bash
# Uses saved defaults
bqcsv data.csv

# Override any default
bqcsv data.csv --project my-gcp-project --dataset staging --table events_raw

# Replace table contents instead of appending
bqcsv data.csv --replace

# CSV without a header row
bqcsv data.csv --no-header

# Provide an explicit JSON schema file
bqcsv data.csv --schema schema.json
```

`--project`, `--dataset`, and `--table` can each be set in config or passed on the command line.

## Testing

Upload a test CSV:

```
bqcsv test.csv --project einsk5g-dataplatform-prd --dataset anatoli_temp_dataset --table test
```

Delete a test table:

```
bq rm -f -t  einsk5g-dataplatform-prd:anatoli_temp_dataset.test
```

Full command to re-install and re-upload:

```sh
cd /path/to/bqcsv

# 1. Reinstall (editable install links to source; run again after entry-point changes)
pip install -e .

# 2. If you use pyenv, refresh shims so the shell finds the script
pyenv rehash

# 3. Verify you're running the local install
which bqcsv
# should point into your pyenv, e.g. ~/.pyenv/versions/.../bin/bqcsv

# 4. Drop old table (needed if schema changed) and upload
python -m bqcsv.cli config set --project einsk5g-dataplatform-prd --dataset anatoli_temp_dataset
bq rm -f -t einsk5g-dataplatform-prd:anatoli_temp_dataset.test
python -m bqcsv.cli tests/test_comma.csv --project einsk5g-dataplatform-prd --dataset anatoli_temp_dataset --table test --replace
```

With `pip install -e .`, code edits under `bqcsv/` are picked up immediately — you do **not** need to reinstall after every change unless you modify `pyproject.toml` entry points.

If the shell still runs an old version, bypass the shim:

```sh
python -m bqcsv.cli tests/test_comma.csv --project einsk5g-dataplatform-prd --dataset anatoli_temp_dataset --table test --replace
```
