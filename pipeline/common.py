"""Shared helpers for pipeline stages: config loading, repo paths.

Deliberately independent of collectors/common.py — collection and
pipeline are separate concerns per architecture.md §8's repo layout, and
neither needs the other's internals.
"""
from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_RAW_DIR = REPO_ROOT / "data" / "raw"
DATA_PROCESSED_DIR = REPO_ROOT / "data" / "processed"
DATA_RUN_LOGS_DIR = REPO_ROOT / "data" / "run_logs"
CONFIG_PATH = REPO_ROOT / "config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
