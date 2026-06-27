from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "upload_bq_dataset"
CONFIG_PATH = CONFIG_DIR / "config.toml"

CONFIG_KEYS = ("project", "dataset", "table")


def _ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, str]:
    if not CONFIG_PATH.is_file():
        return {}
    with CONFIG_PATH.open("rb") as f:
        data = tomllib.load(f)
    return {key: str(data[key]) for key in CONFIG_KEYS if key in data and data[key]}


def save_config(values: dict[str, str]) -> None:
    _ensure_config_dir()
    current = load_config()
    current.update(values)
    lines = [f'{key} = "{_escape_toml(value)}"' for key, value in current.items()]
    CONFIG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def unset_config(keys: list[str]) -> None:
    if not CONFIG_PATH.is_file():
        return
    current = load_config()
    for key in keys:
        current.pop(key, None)
    if not current:
        CONFIG_PATH.unlink(missing_ok=True)
        return
    lines = [f'{key} = "{_escape_toml(value)}"' for key, value in current.items()]
    CONFIG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def resolve_setting(cli_value: str | None, config: dict[str, str], key: str) -> str | None:
    if cli_value:
        return cli_value
    return config.get(key)


def _escape_toml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
