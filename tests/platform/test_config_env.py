"""Tests for the `.env` loader in `app.config`."""

from __future__ import annotations

import os
from pathlib import Path

from app.config import _load_env_file


def test_env_file_sets_missing_keys(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("TIJORI_TEST_DOTENV_A", raising=False)
    monkeypatch.delenv("TIJORI_DISABLE_DOTENV", raising=False)
    path = tmp_path / ".env"
    path.write_text(
        "# comment\n"
        "TIJORI_TEST_DOTENV_A=from-file\n"
        'TIJORI_TEST_DOTENV_B="quoted value"\n'
        "\n"
        "not a pair\n",
        encoding="utf-8",
    )

    _load_env_file(path)

    assert os.environ["TIJORI_TEST_DOTENV_A"] == "from-file"
    assert os.environ["TIJORI_TEST_DOTENV_B"] == "quoted value"


def test_real_environment_wins(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("TIJORI_DISABLE_DOTENV", raising=False)
    monkeypatch.setenv("TIJORI_TEST_DOTENV_C", "from-shell")
    path = tmp_path / ".env"
    path.write_text("TIJORI_TEST_DOTENV_C=from-file\n", encoding="utf-8")

    _load_env_file(path)

    assert os.environ["TIJORI_TEST_DOTENV_C"] == "from-shell"


def test_missing_file_is_ignored(tmp_path: Path) -> None:
    _load_env_file(tmp_path / "absent.env")


def test_disable_switch_skips_loading(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TIJORI_DISABLE_DOTENV", "1")
    monkeypatch.delenv("TIJORI_TEST_DOTENV_D", raising=False)
    path = tmp_path / ".env"
    path.write_text("TIJORI_TEST_DOTENV_D=from-file\n", encoding="utf-8")

    _load_env_file(path)

    assert "TIJORI_TEST_DOTENV_D" not in os.environ
