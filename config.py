# config.py
# -*- coding: utf-8 -*-
"""Carga parámetros de configuración desde `.env` y provee defaults seguros."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from dotenv import dotenv_values, load_dotenv


_ROOT = Path(__file__).resolve().parent
_ENV_FILENAMES = (".env", ".env.local")


def _load_file_values() -> Dict[str, str]:
    values: Dict[str, str] = {}
    for filename in _ENV_FILENAMES:
        file_path = _ROOT / filename
        if not file_path.exists():
            continue
        load_dotenv(file_path, override=filename != ".env")
        file_values = {
            key: value
            for key, value in dotenv_values(file_path).items()
            if value is not None
        }
        values.update(file_values)
    return values


def _coerce_int(value: str, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _coerce_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _coerce_path(value: str | None, default: Path) -> Path:
    if not value:
        return default
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (_ROOT / path).resolve()
    return path


@dataclass(frozen=True)
class Settings:
    max_per_account: int = 10
    max_concurrency: int = 5
    delay_min: int = 5
    delay_max: int = 15
    autoresponder_delay: int = 10
    quiet: bool = False
    log_dir: Path = _ROOT / "storage" / "logs"
    log_file: str = "app.log"


def load_settings() -> Settings:
    file_values = _load_file_values()
    env_values = {**file_values, **os.environ}
    defaults = Settings()
    return Settings(
        max_per_account=_coerce_int(env_values.get("MAX_PER_ACCOUNT", ""), defaults.max_per_account),
        max_concurrency=_coerce_int(
            env_values.get("MAX_CONCURRENCY", ""),
            defaults.max_concurrency,
        ),
        delay_min=_coerce_int(env_values.get("DELAY_MIN", ""), defaults.delay_min),
        delay_max=_coerce_int(env_values.get("DELAY_MAX", ""), defaults.delay_max),
        autoresponder_delay=_coerce_int(env_values.get("AUTORESPONDER_DELAY", ""), defaults.autoresponder_delay),
        quiet=_coerce_bool(env_values.get("QUIET"), defaults.quiet),
        log_dir=_coerce_path(env_values.get("LOG_DIR"), defaults.log_dir),
        log_file=env_values.get("LOG_FILE", defaults.log_file),
    )


SETTINGS = load_settings()
